import os
import sys
import types
import unittest
from unittest.mock import MagicMock

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
    _detect_language, _LATIN_HINTS, _NS_PER_CHUNK, _DEFAULT_CHUNK_BYTES,
    _MIN_INTERVAL_MS, _MAX_FAILURES, _KOKORO_SR, _ESPEAK_SR
)


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
        self.assertIn('mba\'echu', _LATIN_HINTS['gn'])


if __name__ == '__main__':
    unittest.main()
