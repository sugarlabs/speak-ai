# Copyright (C) 2026, Adarsh Kumar <adarsh23072005@gmail.com>
# This file is part of Speak.activity
#
#     Speak.activity is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     Speak.activity is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with Speak.activity.  If not, see <http://www.gnu.org/licenses/>.

"""
Voice AI Assistant for Sugar Speak Activity.

Enables kids to talk to the AI assistant using their voice instead
of typing. Supports speech-to-text via multiple backends:
1. Google Speech Recognition (online, higher accuracy)
2. Vosk (offline, works without internet)

Architecture:
  Microphone → STT → LLM/SLM → TTS (Kokoro/espeak) → Speaker

This module provides the speech-to-text layer. The existing
LLM.py and GenAI/ modules handle the AI response, and the
existing Kokoro/espeak TTS handles speaking the response back.
"""

import logging
import os
import wave
import tempfile
import threading
from typing import Optional, Callable

logger = logging.getLogger('voice-assistant')

# Try importing speech recognition backends
try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False
    logger.info("speech_recognition not available. "
                "Install with: pip install SpeechRecognition")

try:
    import gi
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst, GLib
    Gst.init(None)
    GST_AVAILABLE = True
except (ImportError, ValueError):
    GST_AVAILABLE = False
    logger.info("GStreamer not available.")


class VoiceListener:
    """Captures audio from the microphone using GStreamer.

    Uses GStreamer pipeline to record audio from the default
    microphone and saves it as a WAV file for speech recognition.
    """

    def __init__(self):
        if not GST_AVAILABLE:
            raise RuntimeError("GStreamer is required for voice input")
        self._pipeline = None
        self._temp_file = None
        self._is_recording = False

    def start_recording(self) -> None:
        """Start recording audio from the microphone."""
        if self._is_recording:
            return

        self._temp_file = tempfile.mktemp(suffix='.wav')

        pipeline_str = (
            'autoaudiosrc ! '
            'audioconvert ! '
            'audioresample ! '
            'audio/x-raw,rate=16000,channels=1,format=S16LE ! '
            'wavenc ! '
            'filesink location={}'.format(self._temp_file)
        )

        self._pipeline = Gst.parse_launch(pipeline_str)
        self._pipeline.set_state(Gst.State.PLAYING)
        self._is_recording = True
        logger.debug("Recording started: %s", self._temp_file)

    def stop_recording(self) -> Optional[str]:
        """Stop recording and return the path to the WAV file."""
        if not self._is_recording:
            return None

        self._pipeline.set_state(Gst.State.NULL)
        self._is_recording = False
        logger.debug("Recording stopped: %s", self._temp_file)
        return self._temp_file

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    def cleanup(self) -> None:
        """Remove temporary audio file."""
        if self._temp_file and os.path.exists(self._temp_file):
            os.remove(self._temp_file)
            self._temp_file = None


class SpeechToText:
    """Converts speech audio to text using available backends.

    Supports two backends:
    - Google Speech Recognition (online, better accuracy)
    - Vosk (offline, works without internet on low-resource devices)

    Falls back automatically: Google first, then Vosk if offline.
    """

    def __init__(self, language: str = "en-US"):
        self._language = language
        self._recognizer = sr.Recognizer() if SR_AVAILABLE else None

        # Configure for noisy classroom environments
        if self._recognizer:
            self._recognizer.energy_threshold = 300
            self._recognizer.dynamic_energy_threshold = True
            self._recognizer.pause_threshold = 1.0

    def transcribe(self, audio_path: str) -> Optional[str]:
        """Transcribe a WAV audio file to text.

        Tries Google Speech Recognition first (better accuracy).
        Falls back to offline recognition if no internet.

        Args:
            audio_path: Path to WAV file recorded by VoiceListener.

        Returns:
            Transcribed text, or None if recognition failed.
        """
        if not SR_AVAILABLE:
            logger.error("speech_recognition library not installed")
            return None

        if not os.path.exists(audio_path):
            logger.error("Audio file not found: %s", audio_path)
            return None

        try:
            with sr.AudioFile(audio_path) as source:
                audio_data = self._recognizer.record(source)

            # Try Google first (online, higher accuracy)
            try:
                text = self._recognizer.recognize_google(
                    audio_data, language=self._language
                )
                logger.debug("Google STT result: %s", text)
                return text
            except sr.RequestError:
                logger.info("Google STT unavailable, trying offline")
            except sr.UnknownValueError:
                logger.info("Google STT could not understand audio")
                return None

            # Fallback: try Sphinx (offline)
            try:
                text = self._recognizer.recognize_sphinx(audio_data)
                logger.debug("Sphinx STT result: %s", text)
                return text
            except sr.RequestError:
                logger.error("No STT backend available")
            except sr.UnknownValueError:
                logger.info("Sphinx could not understand audio")

        except Exception as e:
            logger.error("STT error: %s", e)

        return None


class VoiceAssistant:
    """Main voice assistant that ties together listening, STT, and response.

    Usage in Speak Activity:
        assistant = VoiceAssistant(on_text=handle_user_speech,
                                   on_response=handle_ai_response)
        assistant.start_listening()  # Kid presses mic button
        assistant.stop_listening()   # Kid releases mic button
    """

    def __init__(
        self,
        on_text: Optional[Callable[[str], None]] = None,
        on_response: Optional[Callable[[str], None]] = None,
        language: str = "en-US"
    ):
        """
        Args:
            on_text: Callback when user's speech is transcribed.
            on_response: Callback when AI response is ready.
            language: Language code for speech recognition.
        """
        self._listener = VoiceListener()
        self._stt = SpeechToText(language=language)
        self._on_text = on_text
        self._on_response = on_response
        self._processing = False

    def start_listening(self) -> None:
        """Start recording from microphone (call on mic button press)."""
        if not self._processing:
            self._listener.start_recording()

    def stop_listening(self) -> None:
        """Stop recording and process speech (call on mic button release).

        Runs transcription in a background thread to avoid blocking
        the GTK main loop.
        """
        audio_path = self._listener.stop_recording()
        if audio_path:
            self._processing = True
            thread = threading.Thread(
                target=self._process_audio,
                args=(audio_path,),
                daemon=True
            )
            thread.start()

    def _process_audio(self, audio_path: str) -> None:
        """Process recorded audio: transcribe and get AI response."""
        try:
            # Step 1: Speech to Text
            text = self._stt.transcribe(audio_path)

            if text and self._on_text:
                # Notify UI with transcribed text
                GLib.idle_add(self._on_text, text)

            if text and self._on_response:
                # Step 2: Get AI response (uses existing LLM/SLM)
                # The callback should call _try_llm_response or
                # _try_slm_response from activity.py
                GLib.idle_add(self._on_response, text)

        except Exception as e:
            logger.error("Voice processing error: %s", e)
        finally:
            self._listener.cleanup()
            self._processing = False

    @property
    def is_listening(self) -> bool:
        return self._listener.is_recording

    @property
    def is_processing(self) -> bool:
        return self._processing
