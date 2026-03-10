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
import threading

from gi.repository import Gst
from gi.repository import GLib
from gi.repository import GObject

import logging
logger = logging.getLogger('speak')

from sugar3.speech import GstSpeechPlayer

# Kokoro TTS imports
try:
    from kokoro import KPipeline, KModel
    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False
    logger.warning("Kokoro not available, falling back to espeak")

import language_config

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

        # Initialize Kokoro multilingual pipeline system
        # We share one KModel across all language pipelines to save memory.
        # Each language gets its own KPipeline (lazy-loaded on first use).
        self._kokoro_model = None        # shared KModel instance
        self._kokoro_pipelines = {}      # lang_code -> KPipeline
        self._kokoro_lock = threading.Lock()  # guards _kokoro_pipelines
        self.kokoro_pipeline = None       # active pipeline (backward compat)
        self._kokoro_ready = False

        if KOKORO_AVAILABLE:
            threading.Thread(target=self._setup_kokoro_model, daemon=True).start()

        # Voice list sourced from centralized language_config
        self.kokoro_voices = language_config.get_all_voices()
        self.current_kokoro_voice = 'af_heart'

        self._cb = {}
        for cb in ['peak', 'wave', 'idle']:
            self._cb[cb] = None

    # -- Kokoro initialization helpers ----------------------------------------

    def _setup_kokoro_model(self):
        """Load the shared KModel once, then bootstrap the default pipeline."""
        try:
            self._kokoro_model = KModel(repo_id='hexgrad/Kokoro-82M')
            logger.debug('Kokoro KModel loaded successfully')
            # Mark ready as soon as the model is loaded so other threads
            # can request pipelines via _get_or_create_pipeline.
            self._kokoro_ready = True
            # Pre-load the default (American English) pipeline
            self._get_or_create_pipeline('a')
        except Exception as e:
            logger.error('Failed to load Kokoro model: %s', e)

    def _get_or_create_pipeline(self, lang_code):
        """Return a KPipeline for *lang_code*, creating it lazily if needed.

        All pipelines share the same underlying KModel so only the G2P layer
        is duplicated — this keeps memory usage low.
        """
        with self._kokoro_lock:
            if lang_code in self._kokoro_pipelines:
                return self._kokoro_pipelines[lang_code]

            if self._kokoro_model is None:
                logger.warning(
                    'KModel not yet loaded; cannot create pipeline for %s',
                    lang_code)
                return None

            try:
                pipe = KPipeline(
                    lang_code=lang_code,
                    repo_id='hexgrad/Kokoro-82M',
                    model=self._kokoro_model,
                )
                self._kokoro_pipelines[lang_code] = pipe
                logger.info(
                    'Created Kokoro pipeline for %s (%s)',
                    lang_code,
                    language_config.get_language_name(lang_code))
                return pipe
            except Exception as e:
                logger.error(
                    'Failed to create Kokoro pipeline for %s: %s',
                    lang_code, e)
                return None

    def _resolve_pipeline_for_voice(self, voice_name):
        """Return the correct KPipeline for a given voice name."""
        lang_code = language_config.get_lang_code_for_voice(voice_name)
        pipe = self._get_or_create_pipeline(lang_code)
        if pipe is None:
            # Fall back to American English pipeline
            logger.warning(
                'Falling back to American English pipeline for voice %s',
                voice_name)
            pipe = self._get_or_create_pipeline('a')
        return pipe

    def setup_kokoro(self):
        """Legacy setup method — delegates to new model-based init."""
        self._setup_kokoro_model()

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
        """Set the active Kokoro voice and update the active pipeline."""
        if voice_name in self.kokoro_voices:
            old_lang = language_config.get_lang_code_for_voice(
                self.current_kokoro_voice)
            new_lang = language_config.get_lang_code_for_voice(voice_name)

            # Switch the active pipeline if the language changed.
            # Resolve the pipeline *before* updating current_kokoro_voice
            # so the voice stays consistent if pipeline creation fails.
            if old_lang != new_lang:
                new_pipe = self._resolve_pipeline_for_voice(voice_name)
                if new_pipe is not None:
                    self.kokoro_pipeline = new_pipe
                    self.current_kokoro_voice = voice_name
                    logger.info(
                        'Switched Kokoro pipeline: %s -> %s (%s)',
                        language_config.get_language_name(old_lang),
                        language_config.get_language_name(new_lang),
                        voice_name)
                else:
                    logger.warning(
                        'Pipeline creation failed for %s; keeping %s',
                        voice_name, self.current_kokoro_voice)
                    return
            else:
                self.current_kokoro_voice = voice_name

            logger.debug('Kokoro voice set to: %s', voice_name)
        else:
            logger.warning('Invalid Kokoro voice: %s', voice_name)

    def get_available_kokoro_voices(self):
        return self.kokoro_voices.copy()

    def get_voices_by_language(self):
        """Return voices organised by language for UI display.

        Returns:
            dict mapping language display-name to list of voice names.
        """
        result = {}
        for lang_code in language_config.get_supported_language_codes():
            voices = language_config.get_voices_for_language(lang_code)
            # voices is always non-empty for codes in VOICE_REGISTRY,
            # but we guard defensively for future registry changes.
            if voices:
                label = language_config.get_language_display_label(
                    voices[0])
                result[label] = voices
        return result

    def get_default_kokoro_voices(self):
        """Return the default Kokoro voices for UI display."""
        return ['af_heart', 'af_alloy', 'af_aoede']

    def get_addon_kokoro_voices(self):
        """Return the add-on Kokoro voices for UI display."""
        return [v for v in self.kokoro_voices
                if v not in self.get_default_kokoro_voices()]

    def get_current_language(self):
        """Return the language name of the currently active voice."""
        return language_config.get_language_display_label(
            self.current_kokoro_voice)

    def make_pipeline(self):
        if self.pipeline is not None:
            self.stop_sound_device()
            del self.pipeline

        # If kokoro is available build pipeline using kokoro, else use espeak
        # The pipeline has two sinks : `ears` & `fakesink`
        # ears play to the audio device - we hear the sound output from Kokoro / espeak
        # fakesink is used to draw the mouth movements

        if KOKORO_AVAILABLE and self._kokoro_ready:
            # Build pipeline for Kokoro using appsrc
            # fakesink audio converted to S16LE 16KHz so it's backward compatable with the previous mouth drawing logic
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
        if not (KOKORO_AVAILABLE and self._kokoro_ready):
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
            if ( data.duration == 0 
                or data.duration == Gst.CLOCK_TIME_NONE 
                or data.duration > Gst.SECOND * 10
            ):
                logger.debug("Invalid duration detected, using fallback duration calculation")
                # Assume 16-bit, 1 channel, 16000 Hz for duration calculation
                SAMPLE_RATE = 16000
                samples = size // 2  # 16-bit = 2 bytes per sample
                fallback_duration = samples * Gst.SECOND // SAMPLE_RATE
                actual_duration = fallback_duration
            else:
                actual_duration = data.duration

            npc = 50000000  # npc - nanoseconds per chunk; here 50ms audio = 1 chunks
            bpc = size * npc // actual_duration  # bytes per chunk
            bpc = bpc // 2 * 2  # force alignment for int16

            # Ensuring minimum chunk size
            if bpc == 0:
                bpc = min(4096, size)  # I think 4096 is a reasonable chunk size, if not will change later.
                bpc = bpc // 2 * 2  # force alignment for int16

            a = [] # list of waveform data
            p = [] # list of peak values, representing absolute amplitude
            w = [] # list of timestamps for corresponding chunk

            here = 0  # offset in bytes
            when = data.pts
            last = data.pts + actual_duration
            logger.debug(f"Processing audio chunk: size={size}, duration={actual_duration}, bpc={bpc}")
            
            while True:
                try:
                    # Extract raw bytes from the buffer
                    # `extract_dup` -> Extracts a copy of at most size bytes the data at offset into newly-allocated memory. (from docs)
                    raw_bytes = data.extract_dup(here, bpc)
                    
                    if len(raw_bytes) == 0: # Handling case when chunk is empty - this happens sometimes.
                        logger.debug("Empty audio chunk - breaking")
                        break
                    
                    # Convert to int16 array
                    wave = numpy.frombuffer(raw_bytes, dtype='int16')
                    if len(wave) == 0:
                        logger.debug("Empty wave array after conversion - breaking")
                        break
                        
                    peak = numpy.max(numpy.abs(wave))
                    logger.debug(f"Processed wave chunk: length={len(wave)}, peak={peak}")

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
                when += npc
                if when < last:
                    continue
                break

            def poke(pts):
                success, position = ears.query_position(Gst.Format.TIME)
                if not success:
                    logger.debug("Position query failed, using fallback timing")

                    # Fallback: emit one chunk per tick, re-schedule until done
                    if len(w) > 0:
                        logger.debug(f"Emitting signals (fallback): wave length={len(a[0])}, peak={p[0]}")
                        self.emit("wave", a[0])
                        self.emit("peak", p[0])
                        del a[0]
                        del w[0]
                        del p[0]
                        # Re-schedule timer if more chunks remain
                        if len(w) > 0:
                            GLib.timeout_add(25, poke, pts)
                        return False
                    return False

                if len(w) == 0:
                    return False

                if position < w[0]:
                    return True

                logger.debug(f"Emitting signals: wave length={len(a[0])}, peak={p[0]}")
                self.emit("wave", a[0])
                self.emit("peak", p[0])
                del a[0]
                del w[0]
                del p[0]

                if len(w) > 0:
                    return True

                return False

            # Calculate interval so that all chunks are spread evenly over the audio duration
            total_chunks = len(a)
            if total_chunks > 0:
                # `actual_duration` -> duration of audio buffer in nanoseconds
                # `total_chunks` -> number of chunks the buffer was split into
                # so `actual_duration / total_chunks` will give us the duration in nanosecond per chunk
                # and ensuring interval never smaller than 10 to avoid rapid updates, it looks odd.
                interval_ms = max(10, int(actual_duration / total_chunks / 1000000))
            else:
                interval_ms = 25  # fallback default

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

            # For Kokoro, use time-based emission since position queries will fail while streaming in chunks
            if KOKORO_AVAILABLE and self._kokoro_ready:
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
        """Stream Kokoro audio chunks to the GStreamer pipeline.

        Automatically selects the correct language pipeline based on the
        voice prefix so that the right G2P (Grapheme-to-Phoneme) layer is
        used for each language.
        """
        try:
            # Getting the appsrc element
            appsrc = self.pipeline.get_by_name('kokoro_src')
            if not appsrc:
                logger.error("Could not find kokoro_src element")
                return

            # Set caps for Kokoro audio
            caps = Gst.Caps.from_string(
                "audio/x-raw,format=F32LE,layout=interleaved,rate=24000,channels=1"
            )
            appsrc.set_property("caps", caps)

            # Resolve the correct language pipeline for this voice
            active_pipeline = self._resolve_pipeline_for_voice(voice)
            if active_pipeline is None:
                logger.error("No Kokoro pipeline available for voice %s", voice)
                return

            audio_generator = active_pipeline(text, voice=voice)  # actual audio generation by kokoro

            # Stream audio chunks
            for i, (gs, ps, audio_chunk) in enumerate(audio_generator):
                # Convert tensor to numpy array then to bytes
                data_bytes = audio_chunk.numpy().tobytes()
                
                # Create GStreamer buffer
                buf = Gst.Buffer.new_wrapped(data_bytes)
                
                # Push buffer to appsrc
                ret = appsrc.emit("push-buffer", buf)
                if ret != Gst.FlowReturn.OK:
                    logger.error(f"Error pushing buffer {i} to GStreamer")
                    break

            appsrc.emit("end-of-stream") # Signal EOS
            
        except Exception as e:
            # Signalling EOS here as well, but I'm adding error to logs
            logger.error(f"Error in Kokoro audio streaming: {e}")
            if appsrc:
                appsrc.emit("end-of-stream")

    def speak(self, status, text):
        self.make_pipeline()
        
        if KOKORO_AVAILABLE and self._kokoro_ready:
            lang_label = language_config.get_language_display_label(
                self.current_kokoro_voice)
            logger.debug(
                'Using Kokoro TTS: voice=%s lang=%s text=%s',
                self.current_kokoro_voice, lang_label, text)
            self.restart_sound_device()
            self._stream_kokoro_audio(text, self.current_kokoro_voice)
            
        else:
            # Fallback to espeak
            src = self.pipeline.get_by_name('espeak')
            
            pitch = int(status.pitch) - 100
            rate = int(status.rate) - 100

            logger.debug('Using espeak fallback: pitch=%d rate=%d voice=%s text=%s' % (pitch, rate,
                                                                status.voice.name,
                                                                text))

            src.props.pitch = pitch
            src.props.rate = rate
            src.props.voice = status.voice.name
            src.props.track = 1
            src.props.text = text

            self.restart_sound_device()


_speech = None


def get_speech():
    global _speech

    if _speech is None:
        _speech = Speech()

    return _speech
