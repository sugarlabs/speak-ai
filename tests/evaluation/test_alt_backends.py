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

"""Tests for alt_tts_backends.py — unit tests with mocked dependencies."""

import os
import sys
import threading
import unittest

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from alt_tts_backends import (
    FallbackTTSBackend,
    MMSTTSBackend,
    PiperBackend,
    LANGUAGE_BACKEND_PREFERENCE,
    get_tts_backend,
    _EMPTY_WAVEFORM,
)


class TestFallbackTTSBackend(unittest.TestCase):
    def test_synthesize_raises(self):
        b = FallbackTTSBackend()
        with self.assertRaises(NotImplementedError):
            b.synthesize("hello")

    def test_sample_rate_raises(self):
        b = FallbackTTSBackend()
        with self.assertRaises(NotImplementedError):
            _ = b.sample_rate

    def test_language_name_raises(self):
        b = FallbackTTSBackend()
        with self.assertRaises(NotImplementedError):
            _ = b.language_name

    def test_repr(self):
        b = FallbackTTSBackend()
        b.lang_code = 'es'
        self.assertEqual(repr(b), "<FallbackTTSBackend lang=es>")


class TestMMSTTSBackend(unittest.TestCase):
    def test_supported_languages_keys(self):
        expected = {'qu', 'gn', 'ay', 'sw', 'rw', 'ar'}
        self.assertEqual(set(MMSTTSBackend.SUPPORTED_LANGUAGES.keys()), expected)

    def test_supported_languages_values(self):
        for lang, cfg in MMSTTSBackend.SUPPORTED_LANGUAGES.items():
            self.assertIn('model', cfg)
            self.assertIn('name', cfg)
            self.assertIn('sr', cfg)
            self.assertEqual(cfg['sr'], 16000)

    def test_unsupported_language_raises(self):
        with self.assertRaises(ValueError) as ctx:
            MMSTTSBackend('xx')
        self.assertIn('xx', str(ctx.exception))

    def test_sample_rate(self):
        self.assertEqual(MMSTTSBackend('qu').sample_rate, 16000)

    def test_language_name(self):
        self.assertEqual(MMSTTSBackend('qu').language_name, 'Quechua')

    def test_repr(self):
        self.assertEqual(repr(MMSTTSBackend('ar')), "<MMSTTSBackend lang=ar>")

    def test_empty_text_returns_empty(self):
        waveform, sr = MMSTTSBackend('qu').synthesize("")
        self.assertEqual(len(waveform), 0)
        self.assertEqual(sr, 16000)

    def test_whitespace_text_returns_empty(self):
        waveform, sr = MMSTTSBackend('qu').synthesize("   ")
        self.assertEqual(len(waveform), 0)
        self.assertEqual(sr, 16000)


class TestPiperBackend(unittest.TestCase):
    def test_supported_languages_keys(self):
        expected = {'ar', 'es', 'fr', 'pt', 'hi', 'sw', 'zh'}
        self.assertEqual(set(PiperBackend.SUPPORTED_LANGUAGES.keys()), expected)

    def test_supported_languages_values(self):
        for lang, cfg in PiperBackend.SUPPORTED_LANGUAGES.items():
            self.assertIn('model', cfg)
            self.assertIn('name', cfg)
            self.assertIn('sr', cfg)
            self.assertEqual(cfg['sr'], 22050)

    def test_unsupported_language_raises(self):
        with self.assertRaises(ValueError) as ctx:
            PiperBackend('xx')
        self.assertIn('xx', str(ctx.exception))

    def test_sample_rate(self):
        self.assertEqual(PiperBackend('es').sample_rate, 22050)

    def test_language_name(self):
        self.assertEqual(PiperBackend('es').language_name, 'Spanish')

    def test_repr(self):
        self.assertEqual(repr(PiperBackend('hi')), "<PiperBackend lang=hi>")

    def test_empty_text_returns_empty(self):
        waveform, sr = PiperBackend('es').synthesize("")
        self.assertEqual(len(waveform), 0)
        self.assertEqual(sr, 22050)

    def test_whitespace_text_returns_empty(self):
        waveform, sr = PiperBackend('es').synthesize("   ")
        self.assertEqual(len(waveform), 0)
        self.assertEqual(sr, 22050)


class TestLanguageBackendPreference(unittest.TestCase):
    def test_all_languages_have_preference(self):
        all_langs = (
            set(MMSTTSBackend.SUPPORTED_LANGUAGES.keys())
            | set(PiperBackend.SUPPORTED_LANGUAGES.keys())
            | {'en-us', 'en-gb', 'es', 'fr', 'hi', 'it', 'pt-br', 'ja', 'zh'}
        )
        for lang in all_langs:
            if lang == 'pt':
                continue  # Piper uses 'pt' internally, preference dict uses 'pt-br'
            self.assertIn(lang, LANGUAGE_BACKEND_PREFERENCE,
                          f"{lang} missing from preference dict")

    def test_primary_in_all_entries(self):
        for lang, prefs in LANGUAGE_BACKEND_PREFERENCE.items():
            self.assertIn('primary', prefs, f"{lang} has no 'primary' fallback")


class TestGetTTSBackend(unittest.TestCase):
    def test_primary_returns_none(self):
        self.assertIsNone(get_tts_backend('es', 'primary'))

    def test_unknown_language_returns_none(self):
        self.assertIsNone(get_tts_backend('xx'))

    def test_en_us_returns_none(self):
        self.assertIsNone(get_tts_backend('en-us'))

    def test_en_gb_returns_none(self):
        self.assertIsNone(get_tts_backend('en-gb'))

    def test_it_returns_none(self):
        self.assertIsNone(get_tts_backend('it'))

    def test_ja_returns_none(self):
        self.assertIsNone(get_tts_backend('ja'))

    def test_preferred_engine_overrides(self):
        self.assertIsNone(get_tts_backend('es', preferred_engine='primary'))


class TestThreadSafety(unittest.TestCase):
    def test_mms_concurrent_init(self):
        results = [None, None]
        errors = [None, None]

        def create(idx):
            try:
                results[idx] = MMSTTSBackend('qu')
            except Exception as e:
                errors[idx] = e

        threads = [threading.Thread(target=create, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertIsNone(errors[0])
        self.assertIsNone(errors[1])
        self.assertIsNotNone(results[0])
        self.assertIsNotNone(results[1])

    def test_piper_concurrent_init(self):
        results = [None, None]
        errors = [None, None]

        def create(idx):
            try:
                results[idx] = PiperBackend('es')
            except Exception as e:
                errors[idx] = e

        threads = [threading.Thread(target=create, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertIsNone(errors[0])
        self.assertIsNone(errors[1])
        self.assertIsNotNone(results[0])
        self.assertIsNotNone(results[1])


class TestEmptyWaveform(unittest.TestCase):
    def test_is_float32(self):
        self.assertEqual(_EMPTY_WAVEFORM.dtype, np.float32)

    def test_is_empty(self):
        self.assertEqual(len(_EMPTY_WAVEFORM), 0)


if __name__ == "__main__":
    unittest.main()
