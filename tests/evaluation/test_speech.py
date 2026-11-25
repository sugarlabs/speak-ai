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

import os
import sys
import threading
import types
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Stub out gi and sugar3 before importing speech
gi_mock = types.ModuleType('gi')
gi_repo = types.ModuleType('gi.repository')
gi_repo.Gst = MagicMock()
gi_repo.GLib = MagicMock()
gi_repo.GObject = MagicMock()
gi_mock.repository = gi_repo
sys.modules['gi'] = gi_mock
sys.modules['gi.repository'] = gi_repo

sugar3_mock = types.ModuleType('sugar3')
sugar3_speech = types.ModuleType('sugar3.speech')
sugar3_speech.GstSpeechPlayer = type('GstSpeechPlayer', (), {'__init__': lambda s: None})
sugar3_mock.speech = sugar3_speech
sys.modules['sugar3'] = sugar3_mock
sys.modules['sugar3.speech'] = sugar3_speech

from speech import (
    Speech, _detect_language, _LATIN_HINTS, _NS_PER_CHUNK, _DEFAULT_CHUNK_BYTES,
    _MIN_INTERVAL_MS, _MAX_FAILURES, _KOKORO_SR, _ESPEAK_SR
)


class TestKokoroInitializationFailure(unittest.TestCase):
    def test_failure_wakes_waiting_requests_for_espeak_fallback(self):
        for method in ('_speak_impl', 'speak_multilingual'):
            with self.subTest(method=method):
                s = Speech.__new__(Speech)
                s._language_hint = None
                s._kokoro_lang_map = {'en-us': ('a', 'af_heart')}
                s._tts_cache = None
                s._kokoro_model = None
                s._kokoro_failed = False
                s._kokoro_ready = threading.Event()
                s._get_backend_for_lang = MagicMock(return_value=None)
                s._cache_voice_key = MagicMock(return_value='af_heart')
                s._build_pipeline = MagicMock()
                s.restart_sound_device = MagicMock()
                s.pipeline = MagicMock()
                status = MagicMock(pitch=100, rate=100)
                args = (status, 'hello') if method == '_speak_impl' else ('hello',)
                worker = threading.Thread(target=getattr(s, method), args=args,
                                          daemon=True)
                waiting = threading.Event()
                real_wait = s._kokoro_ready.wait

                def wait_for_kokoro(timeout=None):
                    waiting.set()
                    return real_wait(timeout)

                with patch('speech.KOKORO_AVAILABLE', True), \
                        patch('speech.KPipeline', create=True,
                              side_effect=RuntimeError('initialization failed')), \
                        patch.object(s._kokoro_ready, 'wait',
                                     side_effect=wait_for_kokoro) as wait:
                    try:
                        worker.start()
                        self.assertTrue(waiting.wait(timeout=2))
                        wait.assert_called_once_with(timeout=30)
                        s._setup_kokoro()
                        worker.join(timeout=2)
                        self.assertFalse(worker.is_alive(),
                                         'Request waited for the Kokoro timeout')
                        self.assertTrue(s._kokoro_failed)
                        self.assertTrue(s._kokoro_ready.is_set())
                        s._build_pipeline.assert_called_once_with('espeak', _ESPEAK_SR)
                        s.restart_sound_device.assert_called_once_with()
                        self.assertEqual(s.pipeline.get_by_name('espeak').props.text,
                                         'hello')
                    finally:
                        s._kokoro_ready.set()
                        worker.join(timeout=2)


class TestDetectLanguage(unittest.TestCase):
    def test_explicit_lang_code(self):
        self.assertEqual(_detect_language("hello", "fr"), "fr")

    def test_empty_text(self):
        self.assertEqual(_detect_language("", None), "en-us")

    def test_none_text(self):
        self.assertEqual(_detect_language(None, None), "en-us")

    def test_arabic_script(self):
        self.assertEqual(_detect_language("مرحبا كيف حالك", None), "ar")

    def test_hindi_script(self):
        self.assertEqual(_detect_language("नमस्ते क्या हाल है", None), "hi")

    def test_chinese_script(self):
        self.assertEqual(_detect_language("你好世界", None), "zh")

    def test_spanish_hints(self):
        self.assertEqual(_detect_language("hola gracias por favor", None), "es")

    def test_french_hints(self):
        self.assertEqual(_detect_language("bonjour merci s'il vous plaît", None), "fr")

    def test_english_default(self):
        self.assertEqual(_detect_language("hello world", None), "en-us")

    def test_whitespace_only(self):
        self.assertEqual(_detect_language("   ", None), "en-us")


class TestSpeechConstants(unittest.TestCase):
    def test_ns_per_chunk(self):
        self.assertEqual(_NS_PER_CHUNK, 50_000_000)

    def test_default_chunk_bytes(self):
        self.assertEqual(_DEFAULT_CHUNK_BYTES, 4096)

    def test_min_interval_ms(self):
        self.assertEqual(_MIN_INTERVAL_MS, 10)

    def test_max_failures(self):
        self.assertEqual(_MAX_FAILURES, 3)

    def test_kokoro_sr(self):
        self.assertEqual(_KOKORO_SR, 24000)

    def test_espeak_sr(self):
        self.assertEqual(_ESPEAK_SR, 16000)


class TestLanguageHints(unittest.TestCase):
    def test_swahili_hints(self):
        self.assertIn('sw', _LATIN_HINTS)
        self.assertIn('jambo', _LATIN_HINTS['sw'])

    def test_quechua_hints(self):
        self.assertIn('qu', _LATIN_HINTS)
        self.assertIn('imayna', _LATIN_HINTS['qu'])

    def test_guarani_hints(self):
        self.assertIn('gn', _LATIN_HINTS)
        # Was pinned to 'mba\'echu', which is a misspelling of the greeting
        # and could never match anyway: the tokeniser split on the apostrophe,
        # so no Guarani hint containing one was reachable. Assert the corrected
        # spelling instead. test_language_detection.py checks the general
        # property that every hint survives tokenisation.
        self.assertIn('mba\'éichapa', _LATIN_HINTS['gn'])


if __name__ == '__main__':
    unittest.main()
