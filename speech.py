# Copyright (C) 2009, Aleksey Lim
# Copyright (C) 2019, Chihurumnaya Ibiam <ibiamchihurumnaya@sugarlabs.org>
# Copyright (C) 2025, Mebin J Thattil <mail@mebin.in>
# Copyright (C) 2026, Dashpreet Singh <dashpreetsinghhanda@gmail.com>
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
import threading

from gi.repository import Gst
from gi.repository import GLib
from gi.repository import GObject

import logging
logger = logging.getLogger('speak')

from sugar3.speech import GstSpeechPlayer

# Kokoro TTS imports
try:
    from kokoro import KPipeline
    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False
    logger.warning("Kokoro not available, falling back to espeak")

# LanguageManager - provides lang_code, voice, and espeak fallback per language
from language_manager import LanguageManager

PITCH_MIN = 0
PITCH_MAX = 200
RATE_MIN = 0
RATE_MAX = 200


class Speech(GstSpeechPlayer):
    __gsignals__ = {
        'peak': (GObject.SIGNAL_RUN_FIRST, None, [GObject.TYPE_PYOBJECT]),
        'wave': (GObject.SIGNAL_RUN_FIRST, None, [GObject.TYPE_PYOBJECT]),
        'idle': (GObject.SIGNAL_RUN_FIRST, None, []),
    }

    def __init__(self):
        GstSpeechPlayer.__init__(self)
        self.pipeline = None

        # Language manager — single source of truth for language/voice config
        self.language_manager = LanguageManager()

        # Initialize Kokoro pipeline if available
        # Pipeline is (re)created whenever the language changes via set_language()
        self.kokoro_pipeline = None
        if KOKORO_AVAILABLE:
            threading.Thread(target=self._setup_kokoro, daemon=True).start()

        # Predefined Kokoro voices for future GUI selection - TODO
        self.kokoro_voices = [
            'af_heart', 'af_alloy', 'af_aoede', 'af_bella', 'af_jessica',
            'af_kore', 'af_nicole', 'af_nova', 'af_river', 'af_sarah',
            'af_sky', 'am_adam', 'am_echo', 'am_eric', 'am_fenrir',
            'am_liam', 'am_michael', 'am_onyx', 'am_puck', 'am_santa',
            'bf_alice', 'bf_emma', 'bf_isabella', 'bf_lily', 'bm_daniel',
            'bm_fable', 'bm_george', 'bm_lewis', 'jf_alpha', 'jf_gongitsune',
            'jf_nezumi', 'jf_tebukuro', 'jm_kumo', 'zf_xiaobei', 'zf_xiaoni',
            'zf_xiaoxiao', 'zf_xiaoyi', 'zm_yunjian', 'zm_yunxi', 'zm_yunxia',
            'zm_yunyang', 'ef_dora', 'em_alex', 'em_santa', 'ff_siwis',
            'hf_alpha', 'hf_beta', 'hm_omega', 'hm_psi', 'if_sara',
            'im_nicola', 'pf_dora', 'pm_alex', 'pm_santa'
        ]

        # current_kokoro_voice is now driven by language_manager, but we keep
        # this attribute for backward compatibility with any existing callers.
        self.current_kokoro_voice = self.language_manager.kokoro_voice or 'af_heart'

        self._cb = {}
        for cb in ['peak', 'wave', 'idle']:
            self._cb[cb] = None

    # ------------------------------------------------------------------
    # Language control (new public API for PR 1)
    # ------------------------------------------------------------------

    def set_language(self, language_name):
        """Switch the active language.

        Updates LanguageManager and rebuilds the Kokoro pipeline with the
        correct lang_code if Kokoro supports the new language natively.
        Falls back to espeak-ng for languages not in Kokoro v1.0.

        Called by LanguageSelectorWidget when the user picks a language.
        """
        self.language_manager.set_language(language_name)
        self.current_kokoro_voice = self.language_manager.kokoro_voice or 'af_heart'

        if KOKORO_AVAILABLE and self.language_manager.uses_kokoro:
            # Rebuild Kokoro pipeline with new lang_code in background
            threading.Thread(target=self._setup_kokoro, daemon=True).start()
            logger.info(
                'Language changed to %s — reloading Kokoro (lang_code=%s, voice=%s)',
                language_name,
                self.language_manager.kokoro_lang_code,
                self.current_kokoro_voice,
            )
        else:
            # Language not in Kokoro — clear pipeline so speak() uses espeak
            self.kokoro_pipeline = None
            logger.info(
                'Language changed to %s — using espeak-ng (%s)',
                language_name,
                self.language_manager.espeak_lang,
            )

    def get_language(self):
        """Return the currently active language name."""
        return self.language_manager.language

    def get_available_languages(self):
        """Return the full list of supported language names."""
        return self.language_manager.all_languages()

    # ------------------------------------------------------------------
    # Kokoro pipeline setup
    # ------------------------------------------------------------------

    def _setup_kokoro(self):
        """Build (or rebuild) the Kokoro KPipeline for the current language.

        Runs in a daemon thread to avoid blocking the UI.
        Uses lang_code from LanguageManager instead of the old hardcoded 'a'.
        """
        lang_code = self.language_manager.kokoro_lang_code or 'a'
        try:
            self.kokoro_pipeline = KPipeline(lang_code=lang_code)
            logger.info('Kokoro pipeline ready (lang_code=%s)', lang_code)
        except Exception as e:
            logger.error('Failed to initialise Kokoro pipeline: %s', e)
            self.kokoro_pipeline = None

    # Keep old name as alias so nothing else in the codebase breaks
    def setup_kokoro(self):
        self._setup_kokoro()

    # ------------------------------------------------------------------
    # Existing public API — unchanged
    # ------------------------------------------------------------------

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

    def set_kokoro_voice(self, voice_name):
        if voice_name in self.kokoro_voices:
            self.current_kokoro_voice = voice_name
            logger.debug('Kokoro voice set to: %s', voice_name)
        else:
            logger.warning('Invalid Kokoro voice: %s.', voice_name)

    def get_available_kokoro_voices(self):
        return self.kokoro_voices.copy()

    def get_default_kokoro_voices(self):
        """Return the default Kokoro voices for UI display."""
        return ['af_heart', 'af_alloy', 'af_aoede']

    def get_addon_kokoro_voices(self):
        """Return the add-on Kokoro voices for UI display."""
        return [v for v in self.kokoro_voices
                if v not in self.get_default_kokoro_voices()]

    # ------------------------------------------------------------------
    # GStreamer pipeline — unchanged from original
    # ------------------------------------------------------------------

    def make_pipeline(self):
        if self.pipeline is not None:
            self.stop_sound_device()
            del self.pipeline

        # If kokoro is available build pipeline using kokoro, else use espeak
        # The pipeline has two sinks : `ears` & `fakesink`
        # ears play to the audio device - we hear the sound output from Kokoro / espeak
        # fakesink is used to draw the mouth movements

        if KOKORO_AVAILABLE and self.kokoro_pipeline:
            # Build pipeline for Kokoro using appsrc
            # fakesink audio converted to S16LE 16KHz so it's backward compatible with the previous mouth drawing logic
            cmd = 'appsrc name=kokoro_src' \
                ' ! audioconvert' \
                ' ! audio/x-raw,channels=(int)1,format=F32LE,rate=24000' \
                ' ! tee name=me' \
                ' me.! queue ! autoaudiosink name=ears' \
                ' me.! queue ! audioconvert ! audioresample ! audio/x-raw,format=S16LE,channels=1,rate=16000 ! fakesink name=sink'

        else:
            # Fallback to espeak pipeline
            cmd = 'espeak name=espeak' \
                ' ! capsfilter name=caps' \
                ' ! tee name=me' \
                ' me.! queue ! autoaudiosink name=ears' \
                ' me.! queue ! fakesink name=sink'

        self.pipeline = Gst.parse_launch(cmd)

        # Configure caps to ensure compatibility with numpy int16 processing
        if not (KOKORO_AVAILABLE and self.kokoro_pipeline):
            # force a sample bit width to match our numpy code below
            caps = self.pipeline.get_by_name('caps')
            want = 'audio/x-raw,channels=(int)1,depth=(int)16'
            caps.set_property('caps', Gst.caps_from_string(want))

        # grab reference to the output element for scheduling mouth moves
        ears = self.pipeline.get_by_name('ears')

        def handoff(element, data, pad):
            size = data.get_size()

            if size == 0:
                logger.debug("Size is equal to zero, skipping handoff")
                return True

            # Handle invalid duration
            if (data.duration == 0
                    or data.duration == Gst.CLOCK_TIME_NONE
                    or data.duration > Gst.SECOND * 10):
                logger.debug("Invalid duration detected, using fallback duration calculation")
                # Assume 16-bit, 1 channel, 16000 Hz for duration calculation
                SAMPLE_RATE = 16000
                samples = size // 2  # 16-bit = 2 bytes per sample
                fallback_duration = samples * Gst.SECOND // SAMPLE_RATE
                actual_duration = fallback_duration
            else:
                actual_duration = data.duration

            npc = 50000000  # npc - nanoseconds per chunk; here 50ms audio = 1 chunk
            bpc = size * npc // actual_duration  # bytes per chunk
            bpc = bpc // 2 * 2  # force alignment for int16

            # Ensuring minimum chunk size
            if bpc == 0:
                bpc = min(4096, size)
                bpc = bpc // 2 * 2  # force alignment for int16

            a = []  # list of waveform data
            p = []  # list of peak values, representing absolute amplitude
            w = []  # list of timestamps for corresponding chunk

            here = 0  # offset in bytes
            when = data.pts
            last = data.pts + actual_duration
            logger.debug('Processing audio chunk: size=%d, duration=%d, bpc=%d',
                         size, actual_duration, bpc)

            while True:
                try:
                    raw_bytes = data.extract_dup(here, bpc)

                    if len(raw_bytes) == 0:
                        logger.debug("Empty audio chunk - breaking")
                        break

                    wave = numpy.frombuffer(raw_bytes, dtype='int16')
                    if len(wave) == 0:
                        logger.debug("Empty wave array after conversion - breaking")
                        break

                    peak = numpy.max(numpy.abs(wave))
                    logger.debug('Processed wave chunk: length=%d, peak=%d',
                                 len(wave), peak)

                except (ValueError, TypeError) as e:
                    logger.warning('Error processing audio data for lip sync: %s', e)
                    break

                except Exception as e:
                    logger.error('Unexpected error in handoff function: %s', e)
                    break

                a.append(wave)
                p.append(peak)
                w.append(when)

                here += bpc
                when += npc
                if when < last:
                    continue
                break

            def poke(pts):
                success, position = ears.query_position(Gst.Format.TIME)
                if not success:
                    logger.debug("Position query failed, using fallback timing")

                    if len(w) > 0:
                        logger.debug('Emitting signals (fallback): wave length=%d, peak=%d',
                                     len(a[0]), p[0])
                        self.emit("wave", a[0])
                        self.emit("peak", p[0])
                        del a[0]
                        del w[0]
                        del p[0]
                        if len(w) > 0:
                            GLib.timeout_add(25, poke, pts)
                        return False
                    return False

                if len(w) == 0:
                    return False

                if position < w[0]:
                    return True

                logger.debug('Emitting signals: wave length=%d, peak=%d',
                             len(a[0]), p[0])
                self.emit("wave", a[0])
                self.emit("peak", p[0])
                del a[0]
                del w[0]
                del p[0]

                if len(w) > 0:
                    return True

                return False

            total_chunks = len(a)
            if total_chunks > 0:
                interval_ms = max(10, int(actual_duration / total_chunks / 1000000))
            else:
                interval_ms = 25

            def emit_next_chunk():
                if len(a) > 0:
                    self.emit("wave", a[0])
                    self.emit("peak", p[0])
                    del a[0]
                    del p[0]
                    del w[0]
                    if len(a) > 0:
                        GLib.timeout_add(interval_ms, emit_next_chunk)
                    return False
                return False

            if KOKORO_AVAILABLE and self.kokoro_pipeline:
                GLib.timeout_add(interval_ms, emit_next_chunk)
            else:
                GLib.timeout_add(25, poke, data.pts)

            return True

        sink = self.pipeline.get_by_name('sink')
        sink.props.signal_handoffs = True
        sink.connect('handoff', handoff)

        def gst_message_cb(bus, message):
            self._was_message = True

            if message.type == Gst.MessageType.WARNING:
                def check_after_warnings():
                    if not self._was_message:
                        self.stop_sound_device()
                    return True

                logger.debug(message.type)
                self._was_message = False
                GLib.timeout_add(500, check_after_warnings)

            elif message.type in (Gst.MessageType.EOS, Gst.MessageType.ERROR):
                logger.debug(message.type)
                self.stop_sound_device()
            return True

        self._was_message = False
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect('message', gst_message_cb)

    def _stream_kokoro_audio(self, text, voice):
        """Stream Kokoro audio chunks to the GStreamer pipeline."""
        try:
            appsrc = self.pipeline.get_by_name('kokoro_src')
            if not appsrc:
                logger.error("Could not find kokoro_src element")
                return

            caps = Gst.Caps.from_string(
                "audio/x-raw,format=F32LE,layout=interleaved,rate=24000,channels=1"
            )
            appsrc.set_property("caps", caps)

            audio_generator = self.kokoro_pipeline(text, voice=voice)

            for i, (gs, ps, audio_chunk) in enumerate(audio_generator):
                data_bytes = audio_chunk.numpy().tobytes()
                buf = Gst.Buffer.new_wrapped(data_bytes)
                ret = appsrc.emit("push-buffer", buf)
                if ret != Gst.FlowReturn.OK:
                    logger.error('Error pushing buffer %d to GStreamer', i)
                    break

            appsrc.emit("end-of-stream")

        except Exception as e:
            logger.error('Error in Kokoro audio streaming: %s', e)
            if appsrc:
                appsrc.emit("end-of-stream")

    def speak(self, status, text):
        self.make_pipeline()

        if KOKORO_AVAILABLE and self.kokoro_pipeline:
            # Use the voice from LanguageManager (language-appropriate default),
            # unless the user has manually overridden it via set_kokoro_voice().
            voice = self.current_kokoro_voice
            logger.debug('Using Kokoro TTS: lang=%s voice=%s text=%s',
                         self.language_manager.language, voice, text)
            self.restart_sound_device()
            self._stream_kokoro_audio(text, voice)

        else:
            # espeak-ng fallback — used for languages not in Kokoro v1.0
            # (Arabic, Swahili, Kinyarwanda, Quechua, Guaraní) and when
            # Kokoro is not installed.
            src = self.pipeline.get_by_name('espeak')

            pitch = int(status.pitch) - 100
            rate = int(status.rate) - 100

            # For multilingual espeak fallback, prefer the language-specific
            # espeak voice code over the legacy status.voice.name when the
            # active language isn't English.
            if self.language_manager.uses_kokoro is False:
                espeak_voice = self.language_manager.espeak_lang
            else:
                espeak_voice = status.voice.name

            logger.debug('Using espeak fallback: lang=%s pitch=%d rate=%d voice=%s text=%s',
                         self.language_manager.language, pitch, rate, espeak_voice, text)

            src.props.pitch = pitch
            src.props.rate = rate
            src.props.voice = espeak_voice
            src.props.track = 1
            src.props.text = text

            self.restart_sound_device()


_speech = None


def get_speech():
    global _speech

    if _speech is None:
        _speech = Speech()

    return _speech