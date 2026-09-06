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

"""The low-RAM gate is actually consulted by speech.py.

test_model_manager.py already covers ModelManager deciding `neural_allowed`.
What that cannot catch is the gate being computed and then ignored, which is
how it sat for most of this branch: the module existed, its tests passed, and
nothing on the synthesis path ever asked it anything.

These tests drive the real Speech methods rather than reimplementing the
condition, so deleting the check in speech.py fails here.

gi and sugar3 are stubbed the same way test_speech.py does it, so this runs on
a CI box with no GStreamer.
"""

import os
import sys
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

NEURAL_LANGS = ['ar', 'sw', 'rw', 'qu', 'gn', 'ay']


def make_speech(neural_allowed):
    """A Speech with only the attributes the gated methods touch.

    __new__ rather than __init__ on purpose: the real constructor starts the
    Kokoro loader thread and builds a disk cache, none of which this is about.
    """
    import threading

    s = speech_mod.Speech.__new__(speech_mod.Speech)
    s._neural_allowed = neural_allowed
    s._model_manager = None
    s._backend_lock = threading.Lock()
    s._backend_failures = {}
    s._alt_backend_cache = {}
    s.kokoro_pipeline = None
    s._tts_cache = None
    s._current_backend_type = 'kokoro'
    s._current_sample_rate = 24000
    s.current_kokoro_voice = 'af_heart'
    return s


class TestBackendSelectionHonoursGate(unittest.TestCase):
    def test_no_alt_backend_when_ram_is_short(self):
        s = make_speech(neural_allowed=False)
        with patch.object(speech_mod, 'ALT_BACKENDS_AVAILABLE', True), \
                patch.object(speech_mod, 'get_tts_backend') as get_backend:
            for lang in NEURAL_LANGS:
                with self.subTest(lang=lang):
                    self.assertIsNone(s._get_backend_for_lang(lang))
            # The gate must short-circuit before anything tries to build or
            # download a model, not just discard the result afterwards.
            get_backend.assert_not_called()

    def test_alt_backend_is_built_when_ram_is_fine(self):
        s = make_speech(neural_allowed=True)
        sentinel = object()
        with patch.object(speech_mod, 'ALT_BACKENDS_AVAILABLE', True), \
                patch.object(speech_mod, 'get_tts_backend',
                             return_value=sentinel) as get_backend:
            self.assertIs(s._get_backend_for_lang('ar'), sentinel)
            get_backend.assert_called_once_with('ar')


class TestReportedCapabilitiesHonourGate(unittest.TestCase):
    def test_gated_backends_are_not_advertised(self):
        s = make_speech(neural_allowed=False)
        with patch.object(speech_mod, 'ALT_BACKENDS_AVAILABLE', True):
            for lang in ('ar', 'sw'):
                with self.subTest(lang=lang):
                    backends = s.get_available_backends(lang)
                    self.assertNotIn('piper', backends)
                    self.assertNotIn('mms', backends)
                    # espeak is always there; that is the whole point of
                    # refusing the neural backend rather than erroring.
                    self.assertTrue(backends['espeak'])

    def test_backends_are_advertised_when_allowed(self):
        s = make_speech(neural_allowed=True)
        with patch.object(speech_mod, 'ALT_BACKENDS_AVAILABLE', True):
            self.assertTrue(s.get_available_backends('ar').get('piper'))
            self.assertTrue(s.get_available_backends('rw').get('mms'))


class TestStatusReportsGate(unittest.TestCase):
    def test_status_exposes_neural_allowed(self):
        s = make_speech(neural_allowed=False)
        self.assertIs(s.get_status()['neural_allowed'], False)


if __name__ == '__main__':
    unittest.main()
