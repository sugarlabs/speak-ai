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
import threading
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

    text_lower = text.lower()
    best_lang = 'en-us'
    best_score = 0
    for lang, words in _LATIN_HINTS.items():
        score = sum(1 for w in words if w in text_lower)
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
    }

    def __init__(self):
        GstSpeechPlayer.__init__(self)
        self.pipeline = None

        self.kokoro_pipeline = None
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

        self._backend_failures = {}
        self._backend_lock = threading.Lock()

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
            self.kokoro_pipeline = KPipeline(lang_code='a')
            self._kokoro_ready.set()
        except Exception as e:
            logger.error(f"Failed to initialize Kokoro: {e}")
            self._kokoro_failed = True

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

        handoff_cb = _make_handoff_cb(self, sample_rate)
        sink = self.pipeline.get_by_name('sink')
        sink.props.signal_handoffs = True
        sink.connect('handoff', handoff_cb)

        self._was_message.clear()
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        self._gst_handler_id = bus.connect('message', self._on_gst_message)

    def _push_waveform_to_appsrc(self, waveform: numpy.ndarray, sr: int) -> Optional[numpy.ndarray]:
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

            while offset < total_samples:
                end = min(offset + chunk_samples, total_samples)
                chunk = waveform[offset:end]
                buf = Gst.Buffer.new_wrapped(chunk.tobytes())
                ret = appsrc.emit("push-buffer", buf)
                if ret != Gst.FlowReturn.OK:
                    logger.error("Error pushing buffer to GStreamer")
                    break
                offset = end

            appsrc.emit("end-of-stream")
            return waveform

        except Exception as e:
            logger.error(f"Error pushing waveform to appsrc: {e}")
            if appsrc:
                try:
                    appsrc.emit("end-of-stream")
                except Exception:
                    pass
            return None

    def _stream_kokoro_audio(self, text: str, voice: str) -> List[numpy.ndarray]:
        waveform_chunks = []
        try:
            self._build_pipeline('kokoro_src', _KOKORO_SR)
            appsrc = self.pipeline.get_by_name('kokoro_src')
            if not appsrc:
                logger.error("Could not find kokoro_src element")
                return []

            caps = Gst.Caps.from_string(
                "audio/x-raw,format=F32LE,layout=interleaved,rate=24000,channels=1"
            )
            appsrc.set_property("caps", caps)

            for gs, ps, audio_chunk in self.kokoro_pipeline(text, voice=voice):
                wave_np = audio_chunk.numpy()
                waveform_chunks.append(wave_np)
                buf = Gst.Buffer.new_wrapped(wave_np.tobytes())
                ret = appsrc.emit("push-buffer", buf)
                if ret != Gst.FlowReturn.OK:
                    logger.error("Error pushing buffer to GStreamer")
                    break

            appsrc.emit("end-of-stream")
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
        try:
            self._build_pipeline('espeak', _ESPEAK_SR)
            self.restart_sound_device()

            if KOKORO_AVAILABLE and self.kokoro_pipeline and not self._kokoro_failed:
                self._kokoro_ready.wait(timeout=5)
                if self.kokoro_pipeline:
                    self._stream_kokoro_audio(text, self.current_kokoro_voice)
                    return

            src = self.pipeline.get_by_name('espeak')
            if src:
                src.props.pitch = int(status.pitch) - 100
                src.props.rate = int(status.rate) - 100
                src.props.voice = status.voice.name
                src.props.track = 1
                src.props.text = text
        except Exception as e:
            logger.error(f"Error in speak: {e}")

    def speak_multilingual(self, text: str, lang_code: str = None, voice: str = None):
        if not text or not text.strip():
            return

        text = text.strip()
        detected = _detect_language(text, lang_code)
        speed = 1.0

        if self._tts_cache is not None:
            cache_voice = voice or self._lang_voice_map.get(detected, 'af_heart')
            cached, cached_sr = self._tts_cache.get(text, cache_voice, detected, speed)
            if cached is not None:
                sr = cached_sr or _DEFAULT_SAMPLE_RATE
                self._build_pipeline('audio_src', sr)
                self.restart_sound_device()
                self._push_waveform_to_appsrc(cached, sr)
                logger.debug(f"Cache hit for lang={detected}, {sr}Hz")
                return

        backend = self._get_backend_for_lang(detected)
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
                            self._tts_cache.put(text, 'alt', detected, speed, waveform, final_sr)
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

        if KOKORO_AVAILABLE and self.kokoro_pipeline and not self._kokoro_failed:
            try:
                self._kokoro_ready.wait(timeout=5)
                if self.kokoro_pipeline:
                    kokoro_voice = voice or self._lang_voice_map.get(detected, self.current_kokoro_voice)
                    self._current_sample_rate = _KOKORO_SR
                    self._current_backend_type = 'kokoro'
                    waveform_chunks = self._stream_kokoro_audio(text, kokoro_voice)
                    if waveform_chunks:
                        if self._tts_cache is not None:
                            try:
                                full_waveform = numpy.concatenate(waveform_chunks)
                                self._tts_cache.put(text, 'kokoro', detected, speed, full_waveform, _KOKORO_SR)
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
