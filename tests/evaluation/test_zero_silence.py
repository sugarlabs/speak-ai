# Speak.activity
# This file is part of Speak.activity
#
# Copyright (C) 2026  NSA Raiyyan <f20241312@pilani.bits-pilani.ac.in>
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

"""Pressing Speak always produces sound, immediately.

Kokoro's measured cold start is 44 seconds on the hardware this targets. The
synthesis path used to open with `self._kokoro_ready.wait(timeout=30)`, so
for the first three quarters of a minute after launch the child pressed Speak
and got nothing at all, then a robotic voice anyway. Silence reads as a broken
activity; espeak reads as a cheap voice that gets better once the model lands.

These tests drive the real _speak_impl with the model still loading, so
reintroducing a blocking wait fails here rather than in a classroom.
"""

import os
import sys
import threading
import time
import types
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

gi_mock = types.ModuleType('gi')
gi_repo = types.ModuleType('gi.repository')
gi_repo.Gst = MagicMock()
gi_repo.GLib = MagicMock()
gi_repo.GObject = MagicMock()
gi_mock.repository = gi_repo
sys.modules.setdefault('gi', gi_mock)
sys.modules.setdefault('gi.repository', gi_repo)

sugar3_mock = types.ModuleType('sugar3')
sugar3_speech = types.ModuleType('sugar3.speech')
sugar3_speech.GstSpeechPlayer = type(
    'GstSpeechPlayer', (), {'__init__': lambda s: None})
sugar3_mock.speech = sugar3_speech
sys.modules.setdefault('sugar3', sugar3_mock)
sys.modules.setdefault('sugar3.speech', sugar3_speech)

import speech as speech_mod  # noqa: E402

SPEECH_PY = os.path.join(os.path.dirname(__file__), '..', '..', 'speech.py')

# A blocking wait long enough to matter would show up as seconds. Anything
# under this is "did not wait".
NON_BLOCKING_SECONDS = 1.0


class FakeVoice:
    name = 'en-us'


class FakeStatus:
    pitch = 100
    rate = 100
    voice = FakeVoice()


def make_speech(kokoro_ready, kokoro_failed=False):
    """A Speech wired for _speak_impl with nothing real behind it.

    __new__ rather than __init__: the real constructor starts the Kokoro
    loader thread and opens a disk cache, neither of which this is about.
    """
    s = speech_mod.Speech.__new__(speech_mod.Speech)
    s._neural_allowed = True
    s._model_manager = None
    s._backend_lock = threading.Lock()
    s._speak_lock = threading.Lock()
    s._backend_failures = {}
    s._alt_backend_cache = {}
    s._tts_cache = None
    s._language_hint = None
    s._current_backend_type = 'kokoro'
    s._current_sample_rate = 24000
    s.current_kokoro_voice = 'af_heart'
    s.kokoro_pipeline = None
    s._kokoro_failed = kokoro_failed
    s._kokoro_model = MagicMock() if kokoro_ready else None
    s._kokoro_ready = threading.Event()
    if kokoro_ready:
        s._kokoro_ready.set()
    s._kokoro_lang_map = {'en-us': ('a', 'af_heart'), 'hi': ('h', 'hf_alpha')}
    s._lang_voice_map = {}
    s.pipeline = MagicMock()
    s._build_pipeline = MagicMock()
    s.restart_sound_device = MagicMock()
    s._stream_kokoro_audio = MagicMock(return_value=[])
    return s


class TestKokoroUsable(unittest.TestCase):

    def test_not_usable_while_still_loading(self):
        self.assertFalse(make_speech(kokoro_ready=False)._kokoro_usable())

    def test_usable_once_ready(self):
        with patch.object(speech_mod, 'KOKORO_AVAILABLE', True):
            self.assertTrue(make_speech(kokoro_ready=True)._kokoro_usable())

    def test_not_usable_after_a_failed_load(self):
        with patch.object(speech_mod, 'KOKORO_AVAILABLE', True):
            s = make_speech(kokoro_ready=True, kokoro_failed=True)
            self.assertFalse(s._kokoro_usable())

    def test_does_not_block(self):
        """The whole point: asking must be free, not a 30 second wait."""
        s = make_speech(kokoro_ready=False)
        start = time.monotonic()
        for _ in range(50):
            s._kokoro_usable()
        self.assertLess(time.monotonic() - start, NON_BLOCKING_SECONDS)


class TestSpeakWhileLoading(unittest.TestCase):

    def test_speaking_does_not_wait_for_the_model(self):
        s = make_speech(kokoro_ready=False)
        with patch.object(speech_mod, 'KOKORO_AVAILABLE', True), \
                patch.object(speech_mod, 'ALT_BACKENDS_AVAILABLE', False):
            start = time.monotonic()
            s._speak_impl(FakeStatus(), 'hello there')
            elapsed = time.monotonic() - start
        self.assertLess(
            elapsed, NON_BLOCKING_SECONDS,
            f"_speak_impl blocked for {elapsed:.1f}s while Kokoro was loading; "
            "the espeak placeholder must be immediate")

    def test_espeak_pipeline_is_built_while_loading(self):
        s = make_speech(kokoro_ready=False)
        with patch.object(speech_mod, 'KOKORO_AVAILABLE', True), \
                patch.object(speech_mod, 'ALT_BACKENDS_AVAILABLE', False):
            s._speak_impl(FakeStatus(), 'hello there')
        s._build_pipeline.assert_called_once()
        self.assertEqual(s._build_pipeline.call_args[0][0], 'espeak')

    def test_kokoro_is_not_invoked_while_loading(self):
        s = make_speech(kokoro_ready=False)
        with patch.object(speech_mod, 'KOKORO_AVAILABLE', True), \
                patch.object(speech_mod, 'ALT_BACKENDS_AVAILABLE', False):
            s._speak_impl(FakeStatus(), 'hello there')
        s._stream_kokoro_audio.assert_not_called()

    def test_kokoro_is_used_once_it_is_ready(self):
        s = make_speech(kokoro_ready=True)
        s._stream_kokoro_audio = MagicMock(return_value=[MagicMock()])
        with patch.object(speech_mod, 'KOKORO_AVAILABLE', True), \
                patch.object(speech_mod, 'ALT_BACKENDS_AVAILABLE', False):
            s._speak_impl(FakeStatus(), 'hello there')
        s._stream_kokoro_audio.assert_called_once()
        s._build_pipeline.assert_not_called()

    def test_the_loading_flag_flips_between_utterances(self):
        """Speak, then the model lands, then speak again: espeak then Kokoro.

        This is the transition the design promises and the one most likely to
        be broken by a cached decision.
        """
        s = make_speech(kokoro_ready=False)
        with patch.object(speech_mod, 'KOKORO_AVAILABLE', True), \
                patch.object(speech_mod, 'ALT_BACKENDS_AVAILABLE', False):
            s._speak_impl(FakeStatus(), 'first sentence')
            self.assertEqual(s._build_pipeline.call_args[0][0], 'espeak')

            s._kokoro_model = MagicMock()
            s._kokoro_ready.set()
            s._stream_kokoro_audio = MagicMock(return_value=[MagicMock()])

            s._speak_impl(FakeStatus(), 'second sentence')
            s._stream_kokoro_audio.assert_called_once()


class TestNoBlockingWaitInSource(unittest.TestCase):
    """Belt and braces: the call itself must not come back.

    The behavioural tests above only catch a wait on the paths they exercise.
    This catches one reintroduced anywhere in the file, including in
    speak_multilingual, which has its own copy of the same logic.
    """

    def test_kokoro_ready_is_never_waited_on(self):
        """Parsed, not grepped — the prose explaining this says the words."""
        import ast

        with open(SPEECH_PY, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())

        offenders = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if (isinstance(func, ast.Attribute) and func.attr == 'wait'
                    and isinstance(func.value, ast.Attribute)
                    and func.value.attr == '_kokoro_ready'):
                offenders.append(node.lineno)

        self.assertEqual(
            offenders, [],
            f"speech.py:{offenders} blocks on _kokoro_ready, which "
            "reintroduces the startup silence; use _kokoro_usable() and let "
            "espeak cover the gap")


if __name__ == '__main__':
    unittest.main()
