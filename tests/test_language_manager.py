# Copyright (C) 2025 Sugar Labs
# SPDX-License-Identifier: GPL-3.0-or-later
#
# test_language_manager.py — Tests for : multilingual language support
#
# Run as:
#   python -m pytest test_language_manager.py -v -p no:randomly

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from language_manager import (
    LanguageManager,
    LANGUAGE_REGISTRY,
    LANGUAGE_NAMES,
    detect_language_from_text,
)


# ── LanguageManager tests ──

class TestLanguageManager(unittest.TestCase):

    def test_default_language_is_english(self):
        lm = LanguageManager()
        self.assertEqual(lm.language, 'English (US)')
        self.assertEqual(lm.kokoro_lang_code, 'a')
        self.assertTrue(lm.uses_kokoro)

    def test_set_known_kokoro_language(self):
        lm = LanguageManager()
        lm.set_language('Hindi')
        self.assertEqual(lm.language, 'Hindi')
        self.assertEqual(lm.kokoro_lang_code, 'h')
        self.assertEqual(lm.kokoro_voice, 'hf_alpha')
        self.assertEqual(lm.espeak_lang, 'hi')
        self.assertTrue(lm.uses_kokoro)

    def test_set_espeak_fallback_language(self):
        lm = LanguageManager()
        lm.set_language('Arabic')
        self.assertIsNone(lm.kokoro_lang_code)
        self.assertIsNone(lm.kokoro_voice)
        self.assertFalse(lm.uses_kokoro)
        self.assertEqual(lm.espeak_lang, 'ar')

    def test_set_unknown_language_falls_back_to_english(self):
        lm = LanguageManager()
        lm.set_language('Klingon')
        self.assertEqual(lm.language, 'English (US)')

    def test_all_languages_returns_full_list(self):
        langs = LanguageManager.all_languages()
        self.assertIn('Spanish', langs)
        self.assertIn('Arabic', langs)
        self.assertIn('Kinyarwanda', langs)
        self.assertIn('Chinese (Mandarin)', langs)
        self.assertGreaterEqual(len(langs), 14)

    def test_kokoro_languages_subset(self):
        kokoro = LanguageManager.kokoro_languages()
        self.assertIn('Spanish', kokoro)
        self.assertIn('Hindi', kokoro)
        self.assertNotIn('Arabic', kokoro)
        self.assertNotIn('Swahili', kokoro)

    def test_fallback_languages_subset(self):
        fallback = LanguageManager.fallback_languages()
        self.assertIn('Arabic', fallback)
        self.assertIn('Swahili', fallback)
        self.assertNotIn('Spanish', fallback)

    def test_display_name_matches_language(self):
        lm = LanguageManager('French')
        self.assertEqual(lm.display_name, 'French')

    def test_set_language_from_text_devanagari(self):
        lm = LanguageManager('English (US)')
        changed = lm.set_language_from_text('नमस्ते दुनिया')
        self.assertTrue(changed)
        self.assertEqual(lm.language, 'Hindi')

    def test_set_language_from_text_no_change_on_latin(self):
        lm = LanguageManager('English (US)')
        changed = lm.set_language_from_text('Hello world')
        self.assertFalse(changed)
        self.assertEqual(lm.language, 'English (US)')


# ── Registry integrity tests ──

class TestLanguageRegistry(unittest.TestCase):

    REQUIRED_LANGUAGES = [
        'Spanish',
        'Portuguese (Brazilian)',
        'Hindi',
        'French',
        'Arabic',
        'Swahili',
        'Quechua',
        'Chinese (Mandarin)',
        'Kinyarwanda',
        'Guaraní',
    ]

    def test_all_required_languages_present(self):
        for lang in self.REQUIRED_LANGUAGES:
            self.assertIn(lang, LANGUAGE_REGISTRY, f'Missing: {lang}')

    def test_every_entry_has_espeak_lang(self):
        for name, entry in LANGUAGE_REGISTRY.items():
            self.assertIn('espeak_lang', entry, f'{name}: missing espeak_lang')
            self.assertTrue(entry['espeak_lang'],
                            f'{name}: espeak_lang is empty')

    def test_every_entry_has_script(self):
        for name, entry in LANGUAGE_REGISTRY.items():
            self.assertIn('script', entry, f'{name}: missing script field')

    def test_kokoro_entries_have_voice(self):
        for name, entry in LANGUAGE_REGISTRY.items():
            if entry['kokoro_lang_code'] is not None:
                self.assertIsNotNone(
                    entry['kokoro_voice'],
                    f'{name}: has kokoro_lang_code but missing kokoro_voice'
                )

    def test_language_names_list_matches_registry(self):
        self.assertEqual(LANGUAGE_NAMES, list(LANGUAGE_REGISTRY.keys()))

    def test_espeak_codes_correct(self):
        expected = {
            'English (US)': 'en-us',
            'English (UK)': 'en-gb',
            'Spanish': 'es',
            'French': 'fr',
            'Hindi': 'hi',
            'Italian': 'it',
            'Japanese': 'ja',
            'Portuguese (Brazilian)': 'pt-br',
            'Chinese (Mandarin)': 'zh',
            'Arabic': 'ar',
            'Swahili': 'sw',
            'Kinyarwanda': 'rw',
            'Quechua': 'qu',
            'Guaraní': 'gn',
        }
        for lang, code in expected.items():
            with self.subTest(lang=lang):
                entry = LANGUAGE_REGISTRY.get(lang)
                self.assertIsNotNone(entry, f'{lang} not in registry')
                self.assertEqual(entry['espeak_lang'], code)

    def test_kokoro_lang_codes_correct(self):
        expected_kokoro = {
            'English (US)': 'a',
            'English (UK)': 'b',
            'Spanish': 'e',
            'French': 'f',
            'Hindi': 'h',
            'Italian': 'i',
            'Japanese': 'j',
            'Portuguese (Brazilian)': 'p',
            'Chinese (Mandarin)': 'z',
        }
        for lang, code in expected_kokoro.items():
            with self.subTest(lang=lang):
                self.assertEqual(LANGUAGE_REGISTRY[lang]['kokoro_lang_code'], code)


# ── Script auto-detection tests ──

class TestDetectLanguageFromText(unittest.TestCase):

    def test_detect_hindi(self):
        self.assertEqual(detect_language_from_text('नमस्ते दुनिया'), 'Hindi')

    def test_detect_arabic(self):
        self.assertEqual(detect_language_from_text('مرحبا بالعالم'), 'Arabic')

    def test_detect_chinese(self):
        self.assertEqual(detect_language_from_text('你好世界'), 'Chinese (Mandarin)')

    def test_detect_japanese_hiragana(self):
        self.assertEqual(detect_language_from_text('こんにちは'), 'Japanese')

    def test_latin_returns_none(self):
        self.assertIsNone(detect_language_from_text('Hello world'))

    def test_empty_string_returns_none(self):
        self.assertIsNone(detect_language_from_text(''))

    def test_whitespace_only_returns_none(self):
        self.assertIsNone(detect_language_from_text('   '))

    def test_numbers_only_returns_none(self):
        self.assertIsNone(detect_language_from_text('12345'))

    def test_mixed_arabic_and_latin_detects_arabic(self):
        result = detect_language_from_text('مرحبا hello')
        self.assertEqual(result, 'Arabic')


if __name__ == '__main__':
    unittest.main()