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
    from kokoro import KPipeline
    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False
    logger.warning("Kokoro not available, falling back to espeak")

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
        
        # Initialize Kokoro pipeline if available
        self.kokoro_pipeline = None
        if KOKORO_AVAILABLE:
            threading.Thread(target=self.setup_kokoro).start()
        
        # Predefined Kokoro voices for future GUI selection - TODO
        self.kokoro_voices = [
            'af_heart', 'af_alloy', 'af_aoede', 'af_bella', 'af_jessica', 'af_kore', 'af_nicole',
            'af_nova', 'af_river', 'af_sarah', 'af_sky','am_adam', 'am_echo', 'am_eric', 'am_fenrir',
            'am_adam', 'am_echo', 'am_eric', 'am_fenrir', 'am_liam', 'am_michael', 'am_onyx',
            'am_puck', 'am_santa', 'bf_alice', 'bf_emma', 'bf_isabella', 'bf_lily', 'bm_daniel',
            'bm_fable', 'bm_george', 'bm_lewis', 'jf_alpha', 'jf_gongitsune', 'jf_nezumi', 'jf_tebukuro',
            'jm_kumo', 'zf_xiaobei', 'zf_xiaoni', 'zf_xiaoxiao', 'zf_xiaoyi', 'zm_yunjian',
            'zm_yunxi', 'zm_yunxia', 'zm_yunyang', 'ef_dora', 'em_alex', 'em_santa',
            'ff_siwis', 'hf_alpha', 'hf_beta', 'hm_omega', 'hm_psi',
            'if_sara', 'im_nicola', 'pf_dora', 'pm_alex', 'pm_santa'
        ]
        self.current_kokoro_voice = 'af_heart'

        self._cb = {}
        for cb in ['peak', 'wave', 'idle']:
            self._cb[cb] = None

    def setup_kokoro(self):
        self.kokoro_pipeline = KPipeline(lang_code='a')

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
            logger.debug(f"Kokoro voice set to: {voice_name}")
        else:
            logger.warning(f"Invalid Kokoro voice: {voice_name}.")

    def get_available_kokoro_voices(self):
        return self.kokoro_voices.copy()

    def get_default_kokoro_voices(self):
        """Return the default Kokoro voices for UI display."""
        return ['af_heart', 'af_alloy', 'af_aoede']

    def get_addon_kokoro_voices(self):
        """Return the add-on Kokoro voices for UI display."""
        return [v for v in self.kokoro_voices if v not in self.get_default_kokoro_voices()]

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
        """Stream Kokoro audio chunks to the GStreamer pipeline"""
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

            audio_generator = self.kokoro_pipeline(text, voice=voice) # actual audio generation by kokoro

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
        
        if KOKORO_AVAILABLE and self.kokoro_pipeline:
            logger.debug('Using Kokoro TTS: voice=%s text=%s' % (self.current_kokoro_voice, text))
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
