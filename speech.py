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
import os
import sys
import logging
import urllib.request
from sugar3.activity.activity import get_activity_root

try:
    import gi
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst, GLib, GObject
except ImportError:
    print("WARNING: GStreamer not found. Audio will not play.")

    class Gst:
        class Pipeline:
            pass

        class State:
            PLAYING = 1
            NULL = 0

        class Buffer:
            @staticmethod
            def new_wrapped(d):
                return d

        class Caps:
            @staticmethod
            def from_string(s):
                return s

        class FlowReturn:
            OK = 0

    class GObject:
        TYPE_PYOBJECT = object
        SIGNAL_RUN_FIRST = "run-first"


logger = logging.getLogger('speak')

try:
    from sugar3.speech import GstSpeechPlayer
except ImportError:
    logger.warning("sugar3 not found (running in venv?). Using MockSpeechPlayer.")

    class GstSpeechPlayer(GObject.GObject if 'GObject' in sys.modules else object):
        def __init__(self):
            if 'GObject' in sys.modules:
                GObject.GObject.__init__(self)
            self.pipeline = None

        def stop_sound_device(self):
            pass

        def restart_sound_device(self):
            pass


# Kokoro TTS imports
# Check for Kokoro ONNX availability
try:
    from kokoro_onnx import Kokoro
    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False
    logger.warning("kokoro-onnx not available, falling back to espeak")

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
        try:
            GstSpeechPlayer.__init__(self)
        except Exception:
            pass

        self.pipeline = None

        # Initialize Kokoro pipeline if available
        self.kokoro = None
        if KOKORO_AVAILABLE:
            threading.Thread(target=self.setup_kokoro, daemon=True).start()

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
        self.current_kokoro_voice = 'af_heart'

        self._cb = {'peak': None, 'wave': None, 'idle': None}
        self._current_pipeline_type = None  # Track pipeline type to avoid rebuilds

    def setup_kokoro(self):
        activity_root = get_activity_root()
        model_dir = os.path.join(activity_root, "models")
        os.makedirs(model_dir, exist_ok=True)

        model_path = os.path.join(model_dir, "kokoro-v1.0.fp16.onnx")
        voices_path = os.path.join(model_dir, "voices-v1.0.bin")

        # Expected file sizes for validation (prevents corrupted partial downloads)
        EXPECTED_MODEL_SIZE = 177464787  # ~169MB
        EXPECTED_VOICES_SIZE = 28214398  # ~27MB

        def is_valid_download(filepath, expected_size):
            """Check if file exists and has the expected size."""
            if not os.path.exists(filepath):
                return False
            actual_size = os.path.getsize(filepath)
            if actual_size != expected_size:
                logger.warning(f"File {filepath} has invalid size: {actual_size} (expected {expected_size})")
                return False
            return True

        # Created a progress bar function that bypasses Sugar's hidden logs
        def download_progress(block_num, block_size, total_size):
            if total_size > 0:
                percent = min(100, int(block_num * block_size * 100 / total_size))
                sys.stdout.write(f"\r Downloading models... {percent}% complete")
                sys.stdout.flush()

        # Check and download model file
        if not is_valid_download(model_path, EXPECTED_MODEL_SIZE):
            # Remove corrupted/incomplete file if it exists
            if os.path.exists(model_path):
                print("\n Removing incomplete/corrupted model file...")
                os.remove(model_path)
            print("\n Kokoro ONNX model not found. Starting 170MB download...")
            try:
                urllib.request.urlretrieve(
                    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.fp16.onnx",
                    model_path,
                    reporthook=download_progress
                )
                if is_valid_download(model_path, EXPECTED_MODEL_SIZE):
                    print("\n Model downloaded successfully!")
                else:
                    print("\n Model download incomplete! Please check your connection and try again.")
                    if os.path.exists(model_path):
                        os.remove(model_path)
            except Exception as e:
                logger.error(f"Model download failed: {e}")
                if os.path.exists(model_path):
                    os.remove(model_path)

        # Check and download voices file
        if not is_valid_download(voices_path, EXPECTED_VOICES_SIZE):
            # Remove corrupted/incomplete file if it exists
            if os.path.exists(voices_path):
                print("\n Removing incomplete/corrupted voices file...")
                os.remove(voices_path)
            print("\n Voices file not found. Starting 26MB download...")
            try:
                urllib.request.urlretrieve(
                    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
                    voices_path,
                    reporthook=download_progress
                )
                if is_valid_download(voices_path, EXPECTED_VOICES_SIZE):
                    print("\n Voices downloaded successfully!")
                else:
                    print("\n Voices download incomplete! Please check your connection and try again.")
                    if os.path.exists(voices_path):
                        os.remove(voices_path)
            except Exception as e:
                logger.error(f"Voices download failed: {e}")
                if os.path.exists(voices_path):
                    os.remove(voices_path)

        if os.path.exists(model_path) and os.path.exists(voices_path):
            try:
                self.kokoro = Kokoro(model_path, voices_path)
                print("\n Kokoro ONNX Engine Loaded and Ready!")
                # Warm-up inference to eliminate first-call latency
                try:
                    self.kokoro.create("Hi", voice=self.current_kokoro_voice,
                                       speed=1.0, lang='en-us')
                    print(" Kokoro warm-up complete.")
                except Exception as e:
                    logger.warning(f"Kokoro warm-up failed (non-fatal): {e}")
            except Exception as e:
                logger.error(f"Failed to load Kokoro ONNX: {e}")
                self.kokoro = None
        else:
            logger.warning(f"Kokoro model files not found at {model_dir}")
            self.kokoro = None

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
        return [
            v for v in self.kokoro_voices
            if v not in self.get_default_kokoro_voices()
        ]

    def make_pipeline(self, use_kokoro=False):
        # Reuse existing pipeline if the type hasn't changed
        if self.pipeline is not None and self._current_pipeline_type == use_kokoro:
            try:
                self.pipeline.set_state(Gst.State.NULL)
                # For kokoro, need a fresh appsrc, so rebuild
                if use_kokoro:
                    pass  # fall through to rebuild
                else:
                    self.pipeline.set_state(Gst.State.PLAYING)
                    return
            except Exception:
                pass

        if self.pipeline is not None:
            try:
                self.pipeline.set_state(Gst.State.NULL)
            except Exception:
                pass
            del self.pipeline

        self._current_pipeline_type = use_kokoro

        # If kokoro is available build pipeline using kokoro, else use espeak
        # The pipeline has two sinks : `ears` & `fakesink`
        # ears play to the audio device - we hear the sound output from Kokoro / espeak
        # fakesink is used to draw the mouth movements

        if use_kokoro:
            # Build pipeline for Kokoro using appsrc
            # fakesink audio converted to S16LE 16KHz so it's backward compatable with the previous mouth drawing logic
            cmd = (
                'appsrc name=kokoro_src format=time is-live=true '
                'do-timestamp=true ! audio/x-raw,format=F32LE,rate=24000,'
                'channels=1,layout=interleaved ! audioconvert ! audioresample '
                '! tee name=me me. ! queue ! autoaudiosink name=ears '
                'me. ! queue ! audioconvert ! audioresample ! '
                'audio/x-raw,format=S16LE,channels=1,rate=16000 ! '
                'fakesink name=sink'
            )
        else:
            # Fallback to espeak pipeline
            cmd = (
                'espeak name=espeak ! capsfilter name=caps ! tee name=me '
                'me. ! queue ! audioconvert ! audioresample ! autoaudiosink '
                'name=ears me. ! queue ! audioconvert ! audioresample ! '
                'audio/x-raw,format=S16LE,channels=1,rate=16000 ! '
                'fakesink name=sink'
            )

        try:
            self.pipeline = Gst.parse_launch(cmd)
            self.pipeline.set_state(Gst.State.PLAYING)
        except Exception as e:
            logger.error(f"Failed to launch GStreamer pipeline: {e}")
            return

        # Configure caps to ensure compatibility with numpy int16 processing
        if not use_kokoro:
            # force a sample bit width to match our numpy code below
            caps = self.pipeline.get_by_name('caps')
            if caps:
                want = 'audio/x-raw,format=S16LE,channels=1'
                caps.set_property('caps', Gst.caps_from_string(want))

        # grab reference to the output element for scheduling mouth moves
        ears = self.pipeline.get_by_name('ears')

        def handoff(element, data, pad):
            size = data.get_size()
            if size == 0:
                logger.debug("Size is equal to zero, skipping handoff")
                return True

            # Assume 16-bit, 1 channel, 16000 Hz for duration calculation
            samples = size // 2  # 16-bit = 2 bytes per sample
            fallback_duration = samples * Gst.SECOND // 16000
            actual_duration = fallback_duration

            # Handle invalid duration
            if (data.duration == 0 or data.duration == Gst.CLOCK_TIME_NONE or
                    data.duration > Gst.SECOND * 10):
                actual_duration = fallback_duration
            else:
                actual_duration = data.duration

            npc = 50000000  # npc - nanoseconds per chunk; here 50ms audio = 1 chunks
            bpc = size * npc // actual_duration if actual_duration > 0 else 0  # bytes per chunk
            bpc = bpc // 2 * 2  # force alignment for int16

            # Ensuring minimum chunk size
            if bpc == 0:
                # I think 4096 is a reasonable chunk size, if not will change later.
                bpc = min(4096, size // 2 * 2)

            a = []  # list of waveform data
            p = []  # list of peak values, representing absolute amplitude
            w = []  # list of timestamps for corresponding chunk

            here = 0  # offset in bytes
            when = data.pts
            last = data.pts + actual_duration

            logger.debug(
                f"Processing audio chunk: size={size}, "
                f"duration={actual_duration}, bpc={bpc}"
            )

            while True:
                try:
                    # Extract raw bytes from the buffer
                    # `extract_dup` -> Extracts a copy of at most size bytes the data at offset into newly-allocated memory. (from docs)
                    raw_bytes = data.extract_dup(here, bpc)

                    if len(raw_bytes) == 0:
                        # Handling case when chunk is empty - this happens sometimes.
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
                    del a[0], p[0], w[0]
                    if len(a) > 0:
                        GLib.timeout_add(interval_ms, emit_next_chunk)
                    return False
                return False

            # For Kokoro, use time-based emission since position queries will fail while streaming in chunks
            if KOKORO_AVAILABLE and self.kokoro:
                GLib.timeout_add(interval_ms, emit_next_chunk)
            else:
                def poke(pts):
                    success, position = ears.query_position(Gst.Format.TIME)
                    if success and position >= w[0]:
                        self.emit("wave", a[0])
                        self.emit("peak", p[0])
                        del a[0], p[0], w[0]
                    if len(w) > 0:
                        GLib.timeout_add(25, poke, pts)
                        return False
                    return False
                GLib.timeout_add(25, poke, data.pts)

            return True

        sink = self.pipeline.get_by_name('sink')
        if sink:
            sink.props.signal_handoffs = True
            sink.connect('handoff', handoff)

        bus = self.pipeline.get_bus()
        bus.add_signal_watch()

        def gst_message_cb(bus, message):
            if message.type == Gst.MessageType.EOS:
                logger.debug("GStreamer: End of stream")
                self.stop_sound_device()
                self.emit('idle')
            elif message.type == Gst.MessageType.ERROR:
                err, debug = message.parse_error()
                logger.error(f"GStreamer error: {err.message} | dbg: {debug}")
                self.stop_sound_device()
            elif message.type == Gst.MessageType.WARNING:
                err, debug = message.parse_warning()
                logger.warning(f"GStreamer warn: {err.message} | dbg: {debug}")

        bus.connect('message', gst_message_cb)

    def _stream_kokoro_audio(self, text, voice):
        """Stream Kokoro audio chunks to the GStreamer pipeline"""
        try:
            if not self.pipeline:
                return

            # Getting the appsrc element
            appsrc = self.pipeline.get_by_name('kokoro_src')
            if not appsrc:
                return

            lang_map = {
                'a': 'en-us', 'b': 'en-gb', 'e': 'es',
                'f': 'fr-fr', 'h': 'hi', 'j': 'ja',
                'p': 'pt-br', 'z': 'cmn', 'i': 'it'
            }
            prefix_char = voice.split('_')[0][0] if '_' in voice else 'a'
            lang_code = lang_map.get(prefix_char, 'en-us')

            logger.info(f"Generating TTS | Voice: {voice} | Lang: {lang_code}")

            # actual audio generation by kokoro
            samples, sample_rate = self.kokoro.create(
                text, voice=voice, speed=1.0, lang=lang_code
            )

            if samples is None or len(samples) == 0:
                logger.warning("Kokoro generated empty audio")
                appsrc.emit("end-of-stream")
                return

            # Stream audio chunks
            # Convert tensor to numpy array then to bytes
            data_bytes = samples.tobytes()
            
            # Create GStreamer buffer
            buf = Gst.Buffer.new_wrapped(data_bytes)

            # Only set duration, let GStreamer handle PTS
            buf.duration = int((len(samples) / 24000) * Gst.SECOND)

            # Push buffer to appsrc
            appsrc.emit("push-buffer", buf)
            
            # Signal EOS
            appsrc.emit("end-of-stream")
            logger.info(f"Pushed {len(data_bytes)} bytes successfully.")

        except Exception as e:
            # Signalling EOS here as well, but I'm adding error to logs
            logger.error(f"Error in Kokoro ONNX generation: {e}")
            try:
                if appsrc:
                    appsrc.emit("end-of-stream")
            except Exception:
                pass

    def speak(self, status, text):
        use_kokoro = KOKORO_AVAILABLE and (self.kokoro is not None)
        self.make_pipeline(use_kokoro=use_kokoro)

        if use_kokoro:
            logger.debug('Using Kokoro ONNX: voice=%s' % self.current_kokoro_voice)
            # Run TTS generation in a thread to avoid blocking the UI
            threading.Thread(
                target=self._stream_kokoro_audio,
                args=(text, self.current_kokoro_voice),
                daemon=True
            ).start()
        else:
            # Fallback to espeak
            try:
                if self.pipeline:
                    src = self.pipeline.get_by_name('espeak')
                    if src:
                        src.props.pitch = status.pitch
                        src.props.rate = status.rate
                        src.props.voice = status.voice
                        src.props.track = 2
                        src.props.text = text
            except Exception as e:
                logger.error(f"Espeak fallback failed: {e}")


_speech = None


def get_speech():
    global _speech
    if _speech is None:
        _speech = Speech()
    return _speech
