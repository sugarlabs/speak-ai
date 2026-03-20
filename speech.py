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
import logging
import os

from gi.repository import Gst
from gi.repository import GLib
from gi.repository import GObject

from sugar3.speech import GstSpeechPlayer

logger = logging.getLogger('speak')

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

        self.kokoro_pipeline = None
        if KOKORO_AVAILABLE:
            threading.Thread(target=self.setup_kokoro).start()

        self.kokoro_voices = [
            'af_heart', 'af_alloy', 'af_aoede', 'af_bella', 'af_jessica', 'af_kore',
            'af_nicole', 'af_nova', 'af_river', 'af_sarah', 'af_sky',
            'am_adam', 'am_echo', 'am_eric', 'am_fenrir', 'am_liam', 'am_michael',
            'am_onyx', 'am_puck', 'am_santa'
        ]

        self.current_kokoro_voice = 'af_heart'

        self._cb = {'peak': None, 'wave': None, 'idle': None}

    def setup_kokoro(self):
        self.kokoro_pipeline = KPipeline(lang_code='a')

    def make_pipeline(self):
        if self.pipeline is not None:
            self.stop_sound_device()
            del self.pipeline

        if KOKORO_AVAILABLE and self.kokoro_pipeline:
            cmd = (
                'appsrc name=kokoro_src '
                '! audioconvert '
                '! audio/x-raw,channels=(int)1,format=F32LE,rate=24000 '
                '! tee name=me '
                'me.! queue ! autoaudiosink name=ears '
                'me.! queue ! audioconvert ! audioresample '
                '! audio/x-raw,format=S16LE,channels=1,rate=16000 '
                '! fakesink name=sink'
            )
        else:
            cmd = (
                'espeak name=espeak '
                '! capsfilter name=caps '
                '! tee name=me '
                'me.! queue ! autoaudiosink name=ears '
                'me.! queue ! fakesink name=sink'
            )

        self.pipeline = Gst.parse_launch(cmd)

        if not (KOKORO_AVAILABLE and self.kokoro_pipeline):
            caps = self.pipeline.get_by_name('caps')
            caps.set_property('caps', Gst.caps_from_string(
                'audio/x-raw,channels=(int)1,depth=(int)16'
            ))

        sink = self.pipeline.get_by_name('sink')
        sink.props.signal_handoffs = True
        sink.connect('handoff', self._handoff)

        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect('message', self._gst_message_cb)

    def _gst_message_cb(self, bus, message):
        if message.type in (Gst.MessageType.EOS, Gst.MessageType.ERROR):
            self.stop_sound_device()
        return True

    def _handoff(self, element, data, pad):
        return True

    def set_kokoro_voice(self, voice_name):
        if voice_name in self.kokoro_voices:
            self.current_kokoro_voice = voice_name
            logger.debug(f"Kokoro voice set: {voice_name}")
        else:
            logger.warning(f"Invalid Kokoro voice: {voice_name}")

    def _use_espeak(self, status, text):
        src = self.pipeline.get_by_name('espeak')

        pitch = int(status.pitch) - 100
        rate = int(status.rate) - 100

        src.props.pitch = pitch
        src.props.rate = rate
        src.props.voice = status.voice.name
        src.props.track = 1
        src.props.text = text

        self.restart_sound_device()

    def _stream_kokoro_audio(self, text, voice):
        try:
            appsrc = self.pipeline.get_by_name('kokoro_src')
            if not appsrc:
                logger.error("kokoro_src not found")
                return

            caps = Gst.Caps.from_string(
                "audio/x-raw,format=F32LE,rate=24000,channels=1"
            )
            appsrc.set_property("caps", caps)

            generator = self.kokoro_pipeline(text, voice=voice)

            for _, _, audio_chunk in generator:
                data_bytes = audio_chunk.numpy().tobytes()
                buf = Gst.Buffer.new_wrapped(data_bytes)

                ret = appsrc.emit("push-buffer", buf)
                if ret != Gst.FlowReturn.OK:
                    break

            appsrc.emit("end-of-stream")

        except Exception as e:
            logger.error(f"Kokoro streaming error: {e}")
            appsrc.emit("end-of-stream")

    def speak(self, status, text, lang='hi'):
        from gtts import gTTS

        # Optional quick playback
        try:
            tts = gTTS(text=text, lang=lang)
            tts.save("temp.mp3")
            os.system("start temp.mp3")
            return
        except Exception as e:
            logger.debug(f"gTTS failed: {e}")

        self.make_pipeline()

        if KOKORO_AVAILABLE and self.kokoro_pipeline is not None:
            try:
                logger.debug("Using Kokoro TTS")
                self.restart_sound_device()
                self._stream_kokoro_audio(text, self.current_kokoro_voice)

            except Exception as e:
                logger.error(f"Kokoro failed: {e}")
                self._use_espeak(status, text)

        else:
            logger.debug("Kokoro not available, using espeak")
            self._use_espeak(status, text)


_speech = None

def get_speech():
    global _speech
    if _speech is None:
        _speech = Speech()
    return _speech