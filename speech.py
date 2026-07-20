# Copyright (C) 2009, Aleksey Lim
# Copyright (C) 2019, Chihurumnaya Ibiam <ibiamchihurumnaya@sugarlabs.org>
# Copyright (C) 2025, Mebin J Thattil <mail@mebin.in>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import numpy
import queue
import re
import threading
import time
from typing import List, Optional

from gi.repository import Gst
from gi.repository import GLib
from gi.repository import GObject

import logging
logger = logging.getLogger('speak')

from sugar3.speech import GstSpeechPlayer

try:
    from kokoro import KPipeline
    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False
    logger.warning("Kokoro not available, falling back to espeak")

try:
    from alt_tts_backends import get_tts_backend
    ALT_BACKENDS_AVAILABLE = True
except ImportError:
    ALT_BACKENDS_AVAILABLE = False
    logger.debug("Alternative TTS backends not available")

try:
    from tts_cache import TTSCache
    TTS_CACHE_AVAILABLE = True
except ImportError:
    TTS_CACHE_AVAILABLE = False
    logger.debug("TTS cache not available")

PITCH_MIN = 0
PITCH_MAX = 200
RATE_MIN = 0
RATE_MAX = 200

_NS_PER_CHUNK = 50_000_000
_DEFAULT_CHUNK_BYTES = 4096
_MIN_INTERVAL_MS = 10
_DEFAULT_INTERVAL_MS = 25
_MAX_FAILURES = 3
_CHUNK_SECONDS = 0.05
_DEFAULT_SAMPLE_RATE = 24000
_KOKORO_SR = 24000
_ESPEAK_SR = 16000

_LANG_DETECT_RANGES = [
    ('\u0600', '\u06FF', 'ar'),
    ('\u0900', '\u097F', 'hi'),
    ('\u0980', '\u09FF', 'bn'),
    ('\u0A00', '\u0A7F', 'pa'),
    ('\u0B00', '\u0B7F', 'or'),
    ('\u0B80', '\u0BFF', 'ta'),
    ('\u0C00', '\u0C7F', 'te'),
    ('\u0C80', '\u0CFF', 'kn'),
    ('\u0D00', '\u0D7F', 'ml'),
    ('\u0E00', '\u0E7F', 'th'),
    ('\u10A0', '\u10FF', 'ka'),
    ('\u1100', '\u11FF', 'ko'),
    ('\u1200', '\u137F', 'am'),
    ('\u1E00', '\u1EFF', 'vi'),
    ('\u3040', '\u309F', 'ja'),
    ('\u30A0', '\u30FF', 'ja'),
    ('\u4E00', '\u9FFF', 'zh'),
]

_LATIN_HINTS = {
    'es': ['hola', 'gracias', 'por', 'favor', 'buenos', 'días', 'cómo', 'está', 'qué', 'tienes'],
    'fr': ['bonjour', 'merci', 's\'il', 'vous', 'plaît', 'comment', 'allez', 'quoi', 'pouvez'],
    'pt-br': ['olá', 'obrigado', 'por', 'favor', 'bom', 'dia', 'como', 'você', 'está', 'pode'],
    'sw': ['jambo', 'asante', 'ndio', 'hapana', 'habari', 'mambo', 'pole', 'karibu'],
    'qu': ['imayna', 'allin', 'ñan', 'rimaykullayki', 'pachamama', 'yanapay'],
    'gn': ['mba\'echu', 'aguiejaty', 'nde', 'ha', 'ore', 'gua', 'porã'],
    'rw': ['muraho', 'amakuru', 'ndego', 'ubuntu', 'ibanga', 'isoko'],
    'ay': ['kamisaki', 'waliki', 'sumawa', 'napa', 'kunjta', 'jisul'],
}


def _detect_language(text: str, lang_code: str = None) -> str:
    if lang_code:
        return lang_code
    if not text or not text.strip():
        return 'en-us'

    script_counts = {}
    for char in text:
        for start, end, code in _LANG_DETECT_RANGES:
            if start <= char <= end:
                script_counts[code] = script_counts.get(code, 0) + 1
                break

    if script_counts:
        dominant = max(script_counts, key=script_counts.get)
        return dominant

    # Match hint words as whole tokens, not substrings — otherwise e.g. the
    # Guarani hint "gua" matches inside the English word "languages".
    tokens = set(re.findall(r"[^\W\d_]+", text.lower(), flags=re.UNICODE))
    best_lang = 'en-us'
    best_score = 0
    for lang, words in _LATIN_HINTS.items():
        score = sum(1 for w in words if w in tokens)
        if score > best_score:
            best_score = score
            best_lang = lang
    return best_lang


def _make_handoff_cb(speech: 'Speech', sample_rate: int):
    def handoff(element, data, pad):
        size = data.get_size()
        if size == 0:
            return True

        if (data.duration == 0
                or data.duration == Gst.CLOCK_TIME_NONE
                or data.duration > Gst.SECOND * 10):
            samples = size // 2
            actual_duration = samples * Gst.SECOND // sample_rate
        else:
            actual_duration = data.duration

        bpc = size * _NS_PER_CHUNK // actual_duration
        bpc = bpc // 2 * 2
        if bpc == 0:
            bpc = min(_DEFAULT_CHUNK_BYTES, size)
            bpc = bpc // 2 * 2

        a, p, w = [], [], []
        here = 0
        when = data.pts
        last = data.pts + actual_duration

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                f"handoff: size={size}, duration={actual_duration}, bpc={bpc}"
            )

        while True:
            try:
                raw_bytes = data.extract_dup(here, bpc)
                if len(raw_bytes) == 0:
                    break
                wave = numpy.frombuffer(raw_bytes, dtype='int16')
                if len(wave) == 0:
                    break
                peak = numpy.max(numpy.abs(wave))
            except (ValueError, TypeError) as e:
                logger.warning(f"Error processing audio data for lip sync: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected error in handoff function: {e}")
                break

            a.append(wave)
            p.append(peak)
            w.append(when)
            here += bpc
            when += _NS_PER_CHUNK
            if when < last:
                continue
            break

        total_chunks = len(a)
        if total_chunks > 0:
            interval_ms = max(
                _MIN_INTERVAL_MS,
                int(actual_duration / total_chunks / 1_000_000)
            )
        else:
            interval_ms = _DEFAULT_INTERVAL_MS

        def emit_next_chunk():
            if len(a) > 0:
                speech.emit("wave", a[0])
                speech.emit("peak", p[0])
                del a[0]
                del p[0]
                del w[0]
                if len(a) > 0:
                    GLib.timeout_add(interval_ms, emit_next_chunk)
            return False

        GLib.timeout_add(interval_ms, emit_next_chunk)
        return True

    return handoff


class Speech(GstSpeechPlayer):
    __gsignals__ = {
        'peak': (GObject.SIGNAL_RUN_FIRST, None, [GObject.TYPE_PYOBJECT]),
        'wave': (GObject.SIGNAL_RUN_FIRST, None, [GObject.TYPE_PYOBJECT]),
        'idle': (GObject.SIGNAL_RUN_FIRST, None, []),
        # (start_char, end_char) into the spoken text, for a karaoke-style
        # current-word highlight. (-1, -1) means "clear the highlight".
        'word': (GObject.SIGNAL_RUN_FIRST, None, [GObject.TYPE_INT, GObject.TYPE_INT]),
    }

    def __init__(self):
        GstSpeechPlayer.__init__(self)
        self.pipeline = None

        self.kokoro_pipeline = None
        self._kokoro_model = None
        self._kokoro_pipelines = {}
        self._kokoro_pipelines_lock = threading.Lock()
        self._kokoro_ready = threading.Event()
        self._kokoro_failed = False
        if KOKORO_AVAILABLE:
            threading.Thread(target=self._setup_kokoro, daemon=True).start()

        self.kokoro_voices = [
            'af_heart', 'af_alloy', 'af_aoede', 'af_bella', 'af_jessica', 'af_kore', 'af_nicole',
            'af_nova', 'af_river', 'af_sarah', 'af_sky', 'am_adam', 'am_echo', 'am_eric', 'am_fenrir',
            'am_liam', 'am_michael', 'am_onyx',
            'am_puck', 'am_santa', 'bf_alice', 'bf_emma', 'bf_isabella', 'bf_lily', 'bm_daniel',
            'bm_fable', 'bm_george', 'bm_lewis', 'jf_alpha', 'jf_gongitsune', 'jf_nezumi', 'jf_tebukuro',
            'jm_kumo', 'zf_xiaobei', 'zf_xiaoni', 'zf_xiaoxiao', 'zf_xiaoyi', 'zm_yunjian',
            'zm_yunxi', 'zm_yunxia', 'zm_yunyang', 'ef_dora', 'em_alex', 'em_santa',
            'ff_siwis', 'hf_alpha', 'hf_beta', 'hm_omega', 'hm_psi',
            'if_sara', 'im_nicola', 'pf_dora', 'pm_alex', 'pm_santa'
        ]
        self.current_kokoro_voice = 'af_heart'

        self._alt_backend_cache = {}
        self._current_sample_rate = _DEFAULT_SAMPLE_RATE
        self._current_backend_type = 'kokoro'

        self._tts_cache = None
        if TTS_CACHE_AVAILABLE:
            try:
                self._tts_cache = TTSCache()
                logger.debug("TTS cache initialized")
            except Exception as e:
                logger.warning(f"TTS cache init failed: {e}")

        self._lang_voice_map = {
            'ar': 'hf_alpha', 'sw': 'hf_alpha', 'qu': 'hf_alpha',
            'gn': 'hf_alpha', 'rw': 'hf_alpha', 'ay': 'hf_alpha',
        }

        # Detected language -> (kokoro pipeline lang_code, default voice).
        # Mirrors tests/evaluation/common.py so live TTS matches the demo WAVs.
        self._kokoro_lang_map = {
            'en-us': ('a', 'af_heart'), 'en-gb': ('a', 'af_heart'),
            'es': ('e', 'ef_dora'), 'fr': ('f', 'ff_siwis'),
            'hi': ('h', 'hf_alpha'), 'pt-br': ('p', 'pf_dora'),
            'zh': ('z', 'zf_xiaoxiao'), 'ja': ('j', 'jf_alpha'),
            'it': ('i', 'if_sara'),
            'ar': ('r', 'hf_alpha'), 'sw': ('w', 'hf_alpha'),
            'qu': ('q', 'hf_alpha'), 'gn': ('g', 'hf_alpha'),
        }

        self._backend_failures = {}
        self._backend_lock = threading.Lock()
        self._speak_lock = threading.Lock()

        self._preload_queue = queue.Queue()
        self._preload_worker_running = False
        self._preload_lock = threading.Lock()

        self._was_message = threading.Event()
        self._gst_handler_id = None

        self._cb = {'peak': None, 'wave': None, 'idle': None}

    def _on_gst_message(self, bus, message):
        self._was_message.set()
        if message.type == Gst.MessageType.WARNING:
            self._was_message.clear()

            def check_after_warnings():
                if not self._was_message.is_set():
                    self.stop_sound_device()
                return True
            GLib.timeout_add(500, check_after_warnings)
        elif message.type in (Gst.MessageType.EOS, Gst.MessageType.ERROR):
            self.stop_sound_device()
        return True

    def _setup_kokoro(self):
        try:
            # Load the model once via the English pipeline; every other
            # language reuses this model with its own lang_code (g2p).
            self.kokoro_pipeline = KPipeline(lang_code='a')
            self._kokoro_model = self.kokoro_pipeline.model
            with self._kokoro_pipelines_lock:
                self._kokoro_pipelines['a'] = self.kokoro_pipeline
            self._kokoro_ready.set()
        except Exception as e:
            logger.error(f"Failed to initialize Kokoro: {e}")
            self._kokoro_failed = True

    def _get_kokoro_pipeline(self, pl_code: str):
        """Return a KPipeline for the given lang_code, creating it lazily and
        sharing the single loaded model (matches tests/evaluation pattern)."""
        with self._kokoro_pipelines_lock:
            pipe = self._kokoro_pipelines.get(pl_code)
            if pipe is not None:
                return pipe
            pipe = KPipeline(lang_code=pl_code, model=self._kokoro_model)
            self._kokoro_pipelines[pl_code] = pipe
            return pipe

    def preload_backend(self, lang_code: str):
        self._preload_queue.put(lang_code)
        self._start_preload_worker()

    def _start_preload_worker(self):
        with self._preload_lock:
            if self._preload_worker_running:
                return
            self._preload_worker_running = True

        def _worker():
            while True:
                try:
                    lang_code = self._preload_queue.get(timeout=2)
                except queue.Empty:
                    break
                try:
                    self._get_backend_for_lang(lang_code)
                    logger.debug(f"Preloaded backend for {lang_code}")
                except Exception as e:
                    logger.debug(f"Preload failed for {lang_code}: {e}")
                finally:
                    self._preload_queue.task_done()
            with self._preload_lock:
                self._preload_worker_running = False

        threading.Thread(target=_worker, daemon=True).start()

    def preload_languages(self, lang_codes: List[str]):
        for lc in lang_codes:
            self._preload_queue.put(lc)
        self._start_preload_worker()

    def disconnect_all(self):
        for cb in ['peak', 'wave', 'idle']:
            hid = self._cb[cb]
            if hid is not None:
                self.disconnect(hid)
                self._cb[cb] = None

    def connect_peak(self, cb):
        self._cb['peak'] = self.connect('peak', cb)

    def connect_wave(self, cb):
        self._cb['wave'] = self.connect('wave', cb)

    def connect_idle(self, cb):
        self._cb['idle'] = self.connect('idle', cb)

    def _emit_peak_wave(self, wave_i16, peak_val):
        self.emit("wave", wave_i16)
        self.emit("peak", peak_val)
        return False

    def _emit_idle(self):
        self.emit("idle")
        return False

    def _schedule_mouth_from_waveform(self, wave_np, sr, anchor: float, chunk_start_offset: float):
        """Schedule 'peak'/'wave' mouth-animation events for one already
        real-time-paced audio chunk, at absolute wall-clock offsets from
        `anchor` (a time.monotonic() reference shared across the whole
        utterance).

        This replaces relying on the GStreamer fakesink 'handoff' signal for
        mouth timing: that branch runs down its own independent tee/queue,
        decoupled from the autoaudiosink branch that's actually audible, and
        in practice drains faster — so the mouth would stop animating up to
        ~1s before the real sound finished. Driving the animation directly
        from the same samples/timing used to pace real playback keeps it in
        sync with what's actually heard, regardless of backend.
        """
        chunk_ms = _NS_PER_CHUNK / 1_000_000.0
        step = max(int(sr * chunk_ms / 1000.0), 1)
        n = len(wave_np)
        is_float = numpy.issubdtype(wave_np.dtype, numpy.floating)
        for i in range(0, n, step):
            sub = wave_np[i:i + step]
            if len(sub) == 0:
                continue
            if is_float:
                wave_i16 = numpy.clip(sub * 32767.0, -32768, 32767).astype(numpy.int16)
            else:
                wave_i16 = sub.astype(numpy.int16)
            peak_val = int(numpy.max(numpy.abs(wave_i16))) if len(wave_i16) else 0
            target = anchor + chunk_start_offset + i / float(sr)
            delay_ms = max(0, int((target - time.monotonic()) * 1000))
            GLib.timeout_add(delay_ms, self._emit_peak_wave, wave_i16, peak_val)

    def _schedule_idle_at(self, anchor: float, offset: float):
        target = anchor + offset
        delay_ms = max(0, int((target - time.monotonic()) * 1000))
        GLib.timeout_add(delay_ms, self._emit_idle)

    @staticmethod
    def _find_words(segment: str):
        """Return [(start, end), ...] character spans of whitespace-separated
        words within `segment` (local to that string)."""
        words = []
        i, n = 0, len(segment)
        while i < n:
            while i < n and segment[i].isspace():
                i += 1
            start = i
            while i < n and not segment[i].isspace():
                i += 1
            if i > start:
                words.append((start, i))
        return words

    def _emit_word(self, start, end):
        self.emit("word", start, end)
        return False

    def _schedule_word_highlights(self, segment: str, base_offset: int,
                                  anchor: float, chunk_start_offset: float,
                                  chunk_duration: float):
        """Estimate per-word timing within one chunk of text (proportional
        to word length vs. that chunk's real synthesized duration) and
        schedule 'word' emissions with GLOBAL character offsets (base_offset
        + local position) so the UI can highlight the matching span in the
        full text entry. This is an estimate, not true phoneme alignment —
        it's the only thing that works identically across every backend
        (Kokoro or MMS), since none of them expose per-word timing here.
        """
        words = self._find_words(segment)
        if not words:
            return
        total_chars = sum(end - start for start, end in words)
        if total_chars <= 0:
            return
        t = 0.0
        for start, end in words:
            word_dur = chunk_duration * (end - start) / total_chars
            target = anchor + chunk_start_offset + t
            delay_ms = max(0, int((target - time.monotonic()) * 1000))
            GLib.timeout_add(
                delay_ms, self._emit_word, base_offset + start, base_offset + end)
            t += word_dur

    def _schedule_word_clear_at(self, anchor: float, offset: float):
        target = anchor + offset
        delay_ms = max(0, int((target - time.monotonic()) * 1000))
        GLib.timeout_add(delay_ms, self._emit_word, -1, -1)

    def set_kokoro_voice(self, voice_name: str):
        if voice_name in self.kokoro_voices:
            self.current_kokoro_voice = voice_name
            logger.debug(f"Kokoro voice set to: {voice_name}")
        else:
            logger.warning(f"Invalid Kokoro voice: {voice_name}")

    def get_available_kokoro_voices(self) -> List[str]:
        return self.kokoro_voices.copy()

    def get_default_kokoro_voices(self) -> List[str]:
        return ['af_heart', 'af_alloy', 'af_aoede']

    def get_addon_kokoro_voices(self) -> List[str]:
        default = self.get_default_kokoro_voices()
        return [v for v in self.kokoro_voices if v not in default]

    def get_available_backends(self, lang_code: str) -> dict:
        result = {'kokoro': KOKORO_AVAILABLE and self.kokoro_pipeline is not None}
        if ALT_BACKENDS_AVAILABLE:
            try:
                from alt_tts_backends import MMSTTSBackend as _MMSTTS, PiperBackend as _Piper
                if lang_code in _MMSTTS.SUPPORTED_LANGUAGES:
                    result['mms'] = True
                if lang_code in _Piper.SUPPORTED_LANGUAGES:
                    result['piper'] = True
            except ImportError:
                pass
        result['espeak'] = True
        return result

    def get_status(self) -> dict:
        return {
            'kokoro_available': KOKORO_AVAILABLE and self.kokoro_pipeline is not None,
            'alt_backends_available': ALT_BACKENDS_AVAILABLE,
            'cache_available': self._tts_cache is not None,
            'cache_stats': self._tts_cache.stats if self._tts_cache else None,
            'current_backend': self._current_backend_type,
            'current_sample_rate': self._current_sample_rate,
            'current_voice': self.current_kokoro_voice,
            'loaded_backends': list(self._alt_backend_cache.keys()),
            'failed_backends': dict(self._backend_failures),
        }

    def get_cache_stats(self) -> dict:
        if self._tts_cache:
            return self._tts_cache.stats
        return {'entries': 0, 'disk_mb': 0, 'disk_bytes': 0}

    def _cache_voice_key(self, detected: str, pl_code, backend) -> str:
        """The voice slot for a cache entry.

        The get and the put have to agree on this or the cache never hits. It
        has to capture whatever actually changes the audio: for Kokoro that's
        the voice embedding, for an alt backend it's which backend (one per
        language, so the class name is enough). Computing it in one place is
        the whole point, since the original bug was the lookup keying on the
        voice name while the store keyed on the literal 'kokoro'.
        """
        if backend is not None:
            return type(backend).__name__
        if pl_code == 'a':
            return self.current_kokoro_voice
        mapped = self._kokoro_lang_map.get(detected, (None, None))[1]
        return mapped or self._lang_voice_map.get(detected, 'af_heart')

    def clear_cache(self):
        if self._tts_cache:
            self._tts_cache.clear()
            logger.debug("TTS cache cleared")

    def _build_pipeline(self, source_name: str, sample_rate: int):
        if self.pipeline is not None:
            self.stop_sound_device()
            if self._gst_handler_id is not None:
                bus = self.pipeline.get_bus()
                bus.disconnect(self._gst_handler_id)
                self._gst_handler_id = None
            self.pipeline.set_state(Gst.State.NULL)
            del self.pipeline
            self.pipeline = None

        if source_name == 'espeak':
            cmd = (
                'espeak name=espeak'
                ' ! capsfilter name=caps'
                ' ! tee name=me'
                ' me.! queue ! autoaudiosink name=ears'
                ' me.! queue ! fakesink name=sink'
            )
        else:
            cmd = (
                f'appsrc name={source_name}'
                f' ! audioconvert'
                f' ! audio/x-raw,channels=(int)1,format=F32LE,rate={sample_rate}'
                f' ! tee name=me'
                f' me.! queue ! autoaudiosink name=ears'
                f' me.! queue ! audioconvert ! audioresample'
                f' ! audio/x-raw,format=S16LE,channels=1,rate={_ESPEAK_SR}'
                f' ! fakesink name=sink'
            )

        self.pipeline = Gst.parse_launch(cmd)

        if source_name == 'espeak':
            caps = self.pipeline.get_by_name('caps')
            caps.set_property('caps', Gst.caps_from_string(
                'audio/x-raw,channels=(int)1,depth=(int)16'
            ))

        # Only wire the fakesink 'handoff' analysis for the espeak path (a
        # genuinely live GStreamer source with no other timing information
        # available). The appsrc-based paths (kokoro_src/audio_src) drive the
        # mouth directly from _schedule_mouth_from_waveform instead, using
        # the same real-time-paced samples that get pushed for playback; if
        # this handoff were ALSO connected for them, both mechanisms would
        # emit 'peak'/'wave' concurrently and race each other, making the
        # mouth flicker between two independently-computed values instead of
        # tracking the actual sound.
        if source_name == 'espeak':
            handoff_cb = _make_handoff_cb(self, sample_rate)
            sink = self.pipeline.get_by_name('sink')
            sink.props.signal_handoffs = True
            sink.connect('handoff', handoff_cb)

        self._was_message.clear()
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        self._gst_handler_id = bus.connect('message', self._on_gst_message)

    def _push_waveform_to_appsrc(self, waveform: numpy.ndarray, sr: int,
                                 text: str = "") -> Optional[numpy.ndarray]:
        appsrc = None
        try:
            appsrc = self.pipeline.get_by_name('kokoro_src') or self.pipeline.get_by_name('audio_src')
            if not appsrc:
                logger.error("Could not find appsrc element")
                return None

            caps = Gst.Caps.from_string(
                f"audio/x-raw,format=F32LE,layout=interleaved,rate={sr},channels=1"
            )
            appsrc.set_property("caps", caps)

            chunk_samples = int(sr * _CHUNK_SECONDS)
            chunk_samples = max(chunk_samples, 256)
            total_samples = len(waveform)
            offset = 0

            # Alt-backend waveforms arrive fully computed (no natural
            # per-chunk delay like Kokoro's generator), so pace pushes to
            # real playback time and drive the mouth directly from these
            # same samples/timings — see _schedule_mouth_from_waveform for
            # why relying on the GStreamer fakesink 'handoff' signal cuts
            # the animation short instead.
            chunk_seconds = chunk_samples / float(sr)
            start = time.monotonic()
            total_seconds = total_samples / float(sr)
            if text:
                self._schedule_word_highlights(text, 0, start, 0.0, total_seconds)

            while offset < total_samples:
                end = min(offset + chunk_samples, total_samples)
                chunk = waveform[offset:end]
                buf = Gst.Buffer.new_wrapped(chunk.tobytes())
                ret = appsrc.emit("push-buffer", buf)
                if ret != Gst.FlowReturn.OK:
                    logger.error("Error pushing buffer to GStreamer")
                    break
                self._schedule_mouth_from_waveform(
                    chunk, sr, start, offset / float(sr))
                offset = end
                if offset < total_samples:
                    time.sleep(chunk_seconds)

            appsrc.emit("end-of-stream")
            self._schedule_idle_at(start, total_seconds)
            if text:
                self._schedule_word_clear_at(start, total_seconds)
            return waveform

        except Exception as e:
            logger.error(f"Error pushing waveform to appsrc: {e}")
            if appsrc:
                try:
                    appsrc.emit("end-of-stream")
                except Exception:
                    pass
            return None

    def _stream_kokoro_audio(self, text: str, voice: str,
                             pl_code: str = 'a') -> List[numpy.ndarray]:
        waveform_chunks = []
        try:
            pipeline = self._get_kokoro_pipeline(pl_code)
            self._build_pipeline('kokoro_src', _KOKORO_SR)
            appsrc = self.pipeline.get_by_name('kokoro_src')
            if not appsrc:
                logger.error("Could not find kokoro_src element")
                return []

            caps = Gst.Caps.from_string(
                "audio/x-raw,format=F32LE,layout=interleaved,rate=24000,channels=1"
            )
            appsrc.set_property("caps", caps)

            # Start the pipeline before pushing buffers, otherwise the audio
            # is generated but never reaches the sink (silent playback).
            self.restart_sound_device()

            # Real-time throttle + mouth scheduling, anchored to the moment
            # audio actually starts flowing (not when we started waiting for
            # Kokoro to synthesize it — that per-chunk CPU synthesis time can
            # itself be over a second, and counting it as elapsed "playback"
            # time made every later sub-window's target already in the past,
            # clamping them to fire in an instant burst instead of spread out
            # — which is also why the mouth used to stop noticeably before
            # the audio actually finished playing.
            start = None
            pushed_seconds = 0.0
            lead = 0.30  # stay this far ahead of playback
            text_cursor = 0  # where to resume searching for each chunk's text in `text`

            for gs, ps, audio_chunk in pipeline(text, voice=voice):
                wave_np = audio_chunk.numpy()
                waveform_chunks.append(wave_np)
                buf = Gst.Buffer.new_wrapped(wave_np.tobytes())
                ret = appsrc.emit("push-buffer", buf)
                if ret != Gst.FlowReturn.OK:
                    logger.error("Error pushing buffer to GStreamer")
                    break
                if start is None:
                    start = time.monotonic()
                self._schedule_mouth_from_waveform(
                    wave_np, _KOKORO_SR, start, pushed_seconds)
                chunk_duration = len(wave_np) / float(_KOKORO_SR)
                if gs:
                    found = text.find(gs.strip(), text_cursor) if gs.strip() else -1
                    if found != -1:
                        self._schedule_word_highlights(
                            gs, found, start, pushed_seconds, chunk_duration)
                        text_cursor = found + len(gs.strip())
                pushed_seconds += chunk_duration
                ahead = pushed_seconds - (time.monotonic() - start)
                if ahead > lead:
                    time.sleep(ahead - lead)

            appsrc.emit("end-of-stream")
            if start is not None:
                self._schedule_idle_at(start, pushed_seconds)
                self._schedule_word_clear_at(start, pushed_seconds)
            return waveform_chunks

        except Exception as e:
            logger.error(f"Error in Kokoro audio streaming: {e}")
            appsrc = self.pipeline.get_by_name('kokoro_src') if self.pipeline else None
            if appsrc:
                try:
                    appsrc.emit("end-of-stream")
                except Exception:
                    pass
            return []

    def _get_backend_for_lang(self, lang_code: str):
        if not ALT_BACKENDS_AVAILABLE:
            return None

        with self._backend_lock:
            failures = self._backend_failures.get(lang_code, 0)
            if failures >= _MAX_FAILURES:
                logger.debug(f"Skipping alt backend for {lang_code} ({failures} failures)")
                return None

            if lang_code in self._alt_backend_cache:
                return self._alt_backend_cache[lang_code]

            try:
                backend = get_tts_backend(lang_code)
                if backend is not None:
                    self._alt_backend_cache[lang_code] = backend
                    logger.debug(f"Created alt backend for {lang_code}: {backend}")
                return backend
            except Exception as e:
                logger.warning(f"Failed to create backend for {lang_code}: {e}")
                self._backend_failures[lang_code] = failures + 1
                return None

    def _record_backend_failure(self, lang_code: str):
        with self._backend_lock:
            self._backend_failures[lang_code] = self._backend_failures.get(lang_code, 0) + 1
            self._alt_backend_cache.pop(lang_code, None)

    def _record_backend_success(self, lang_code: str):
        with self._backend_lock:
            self._backend_failures.pop(lang_code, None)

    def speak(self, status, text: str):
        # Runs the real work on a background thread. speak() used to block
        # the caller (GTK main thread) for the whole synthesis+playback
        # duration, which starves the GLib.timeout_add-scheduled 'peak'/'wave'
        # emissions that drive the mouth animation — audio kept playing
        # (GStreamer has its own streaming threads) but the mouth froze until
        # everything finished, then caught up in one burst. Moving synthesis
        # off the main thread lets those timers fire in real time instead.
        threading.Thread(
            target=self._speak_worker, args=(status, text), daemon=True
        ).start()

    def _speak_worker(self, status, text: str):
        with self._speak_lock:
            self._speak_impl(status, text)

    def _speak_impl(self, status, text: str):
        try:
            if not text or not text.strip():
                return
            text = text.strip()

            detected = _detect_language(text)
            pl_code, mapped_voice = self._kokoro_lang_map.get(detected, (None, None))
            speed = 1.0

            # 1. Dedicated backend (Piper/MMS) where a language prefers one.
            backend = self._get_backend_for_lang(detected)

            # Cache lookup before any synthesis. The voice key has to be the
            # same one the store below uses, which is what _cache_voice_key is
            # for. A hit skips the network entirely and just replays the audio.
            cache_key = self._cache_voice_key(detected, pl_code, backend)
            if self._tts_cache is not None:
                cached, cached_sr = self._tts_cache.get(text, cache_key, detected, speed)
                if cached is not None:
                    sr = cached_sr or _DEFAULT_SAMPLE_RATE
                    self._current_sample_rate = sr
                    self._build_pipeline('audio_src', sr)
                    self.restart_sound_device()
                    self._push_waveform_to_appsrc(cached, sr, text)
                    logger.debug(f"Cache hit for lang={detected}, {sr}Hz")
                    return

            if backend is not None:
                try:
                    sr = backend.sample_rate
                    self._current_sample_rate = sr
                    self._current_backend_type = type(backend).__name__
                    self._build_pipeline('audio_src', sr)
                    self.restart_sound_device()
                    waveform, actual_sr = backend.synthesize(text)
                    if waveform is not None and len(waveform) > 0:
                        final_sr = int(actual_sr) if actual_sr else int(sr)
                        self._push_waveform_to_appsrc(waveform, final_sr, text)
                        self._record_backend_success(detected)
                        if self._tts_cache is not None:
                            try:
                                self._tts_cache.put(text, cache_key, detected,
                                                    speed, waveform, final_sr)
                            except Exception:
                                pass
                        logger.debug(f"Speaking via {backend} for lang={detected}")
                        return
                    self._record_backend_failure(detected)
                except Exception as e:
                    logger.warning(f"Alt backend failed for {detected}: {e}")
                    self._record_backend_failure(detected)

            # 2. Kokoro with the language-appropriate pipeline and voice.
            if (KOKORO_AVAILABLE and not self._kokoro_failed
                    and pl_code is not None):
                try:
                    self._kokoro_ready.wait(timeout=30)
                    if self._kokoro_model is not None:
                        # English respects the user/persona-selected voice;
                        # other languages use their mapped native voice.
                        voice = (self.current_kokoro_voice if pl_code == 'a'
                                 else mapped_voice)
                        self._current_sample_rate = _KOKORO_SR
                        self._current_backend_type = 'kokoro'
                        chunks = self._stream_kokoro_audio(text, voice, pl_code)
                        if chunks:
                            if self._tts_cache is not None:
                                try:
                                    full = numpy.concatenate(chunks)
                                    self._tts_cache.put(text, cache_key, detected,
                                                        speed, full, _KOKORO_SR)
                                except Exception:
                                    pass
                            logger.debug(
                                f"Speaking via Kokoro ({voice}, pl={pl_code}) "
                                f"for lang={detected}")
                            return
                except Exception as e:
                    logger.warning(f"Kokoro failed for {detected}: {e}")

            # 3. espeak fallback (unsupported language or Kokoro unavailable).
            self._build_pipeline('espeak', _ESPEAK_SR)
            self.restart_sound_device()
            src = self.pipeline.get_by_name('espeak')
            if src:
                src.props.pitch = int(status.pitch) - 100
                src.props.rate = int(status.rate) - 100
                src.props.voice = status.voice.name
                src.props.track = 1
                src.props.text = text
            logger.debug(f"Speaking via espeak for lang={detected}")
        except Exception as e:
            logger.error(f"Error in speak: {e}")

    def speak_multilingual(self, text: str, lang_code: str = None, voice: str = None):
        if not text or not text.strip():
            return

        text = text.strip()
        detected = _detect_language(text, lang_code)
        speed = 1.0

        backend = self._get_backend_for_lang(detected)
        pl_code = self._kokoro_lang_map.get(detected, ('a', None))[0]
        # Same key for lookup and store, or the cache silently never hits.
        cache_key = voice or self._cache_voice_key(detected, pl_code, backend)

        if self._tts_cache is not None:
            cached, cached_sr = self._tts_cache.get(text, cache_key, detected, speed)
            if cached is not None:
                sr = cached_sr or _DEFAULT_SAMPLE_RATE
                self._build_pipeline('audio_src', sr)
                self.restart_sound_device()
                self._push_waveform_to_appsrc(cached, sr)
                logger.debug(f"Cache hit for lang={detected}, {sr}Hz")
                return

        if backend is not None:
            try:
                sr = backend.sample_rate
                self._current_sample_rate = sr
                self._current_backend_type = type(backend).__name__
                self._build_pipeline('audio_src', sr)
                self.restart_sound_device()
                waveform, actual_sr = backend.synthesize(text)
                if waveform is not None and len(waveform) > 0:
                    final_sr = int(actual_sr) if actual_sr else int(sr)
                    self._push_waveform_to_appsrc(waveform, final_sr)
                    self._record_backend_success(detected)
                    if self._tts_cache is not None:
                        try:
                            self._tts_cache.put(text, cache_key, detected, speed, waveform, final_sr)
                        except Exception:
                            pass
                    logger.debug(f"Speaking via {backend} at {sr}Hz")
                    return
                else:
                    logger.warning(f"Alt backend returned empty audio for {detected}")
                self._record_backend_failure(detected)
            except Exception as e:
                logger.warning(f"Alt backend failed for {detected}: {e}")
                self._record_backend_failure(detected)

        if KOKORO_AVAILABLE and not self._kokoro_failed:
            try:
                self._kokoro_ready.wait(timeout=30)
                if self._kokoro_model is not None:
                    pl_code, mapped_voice = self._kokoro_lang_map.get(
                        detected, ('a', self.current_kokoro_voice))
                    kokoro_voice = voice or mapped_voice
                    self._current_sample_rate = _KOKORO_SR
                    self._current_backend_type = 'kokoro'
                    waveform_chunks = self._stream_kokoro_audio(
                        text, kokoro_voice, pl_code)
                    if waveform_chunks:
                        if self._tts_cache is not None:
                            try:
                                full_waveform = numpy.concatenate(waveform_chunks)
                                self._tts_cache.put(text, cache_key, detected, speed, full_waveform, _KOKORO_SR)
                            except Exception:
                                pass
                        logger.debug(f"Speaking via Kokoro ({kokoro_voice}) for lang={detected}")
                        return
            except Exception as e:
                logger.warning(f"Kokoro failed for {detected}: {e}")

        self._build_pipeline('espeak', _ESPEAK_SR)
        src = self.pipeline.get_by_name('espeak')
        if src:
            src.props.pitch = 0
            src.props.rate = 0
            src.props.voice = 'en-us'
            src.props.track = 1
            src.props.text = text
        self.restart_sound_device()
        logger.debug(f"No backend available for lang={detected}, using espeak")

    def stop(self):
        if self.pipeline is not None:
            self.pipeline.set_state(Gst.State.NULL)
        self.stop_sound_device()


_speech = None
_speech_lock = threading.Lock()


def get_speech() -> 'Speech':
    global _speech
    if _speech is None:
        with _speech_lock:
            if _speech is None:
                _speech = Speech()
    return _speech
