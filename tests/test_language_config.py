# Copyright (C) 2025
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

"""
Tests for the language_config module.

Run with:
    python -m pytest tests/test_language_config.py -v
or:
    python tests/test_language_config.py
"""

import json
import os
import sys
import unittest

# Ensure the project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import language_config


class TestVoiceToLanguageMapping(unittest.TestCase):
    """Verify that voice names are correctly mapped to language codes."""

    def test_american_english_voices(self):
        for voice in ['af_heart', 'af_bella', 'am_adam', 'am_liam']:
            self.assertEqual(
                language_config.get_lang_code_for_voice(voice), 'a',
                f'{voice} should map to lang_code "a"')

    def test_british_english_voices(self):
        for voice in ['bf_alice', 'bm_george']:
            self.assertEqual(
                language_config.get_lang_code_for_voice(voice), 'b',
                f'{voice} should map to lang_code "b"')

    def test_spanish_voices(self):
        for voice in ['ef_dora', 'em_alex']:
            self.assertEqual(
                language_config.get_lang_code_for_voice(voice), 'e',
                f'{voice} should map to lang_code "e"')

    def test_french_voices(self):
        self.assertEqual(
            language_config.get_lang_code_for_voice('ff_siwis'), 'f')

    def test_hindi_voices(self):
        for voice in ['hf_alpha', 'hf_beta', 'hm_omega', 'hm_psi']:
            self.assertEqual(
                language_config.get_lang_code_for_voice(voice), 'h',
                f'{voice} should map to lang_code "h"')

    def test_italian_voices(self):
        for voice in ['if_sara', 'im_nicola']:
            self.assertEqual(
                language_config.get_lang_code_for_voice(voice), 'i')

    def test_japanese_voices(self):
        for voice in ['jf_alpha', 'jm_kumo']:
            self.assertEqual(
                language_config.get_lang_code_for_voice(voice), 'j')

    def test_portuguese_voices(self):
        for voice in ['pf_dora', 'pm_alex']:
            self.assertEqual(
                language_config.get_lang_code_for_voice(voice), 'p')

    def test_chinese_voices(self):
        for voice in ['zf_xiaobei', 'zm_yunjian']:
            self.assertEqual(
                language_config.get_lang_code_for_voice(voice), 'z')

    def test_invalid_voice_falls_back(self):
        """Unknown prefixes should fall back to 'a' (American English)."""
        self.assertEqual(
            language_config.get_lang_code_for_voice('xf_unknown'), 'a')

    def test_empty_voice_falls_back(self):
        self.assertEqual(
            language_config.get_lang_code_for_voice(''), 'a')

    def test_none_voice_falls_back(self):
        self.assertEqual(
            language_config.get_lang_code_for_voice(None), 'a')


class TestLanguageMetadata(unittest.TestCase):
    """Verify metadata lookup helpers."""

    def test_all_lang_codes_have_metadata(self):
        for code in language_config.get_supported_language_codes():
            self.assertIn(code, language_config.LANGUAGE_META)

    def test_language_name(self):
        self.assertEqual(
            language_config.get_language_name('a'), 'American English')
        self.assertEqual(
            language_config.get_language_name('h'), 'Hindi')
        self.assertEqual(
            language_config.get_language_name('z'), 'Mandarin Chinese')

    def test_unknown_language_name(self):
        self.assertEqual(
            language_config.get_language_name('x'), 'Unknown')

    def test_language_display_label(self):
        label = language_config.get_language_display_label('hf_alpha')
        self.assertIn('Hindi', label)

    def test_voice_display_name(self):
        name = language_config.get_voice_display_name('hf_alpha')
        self.assertIn('Hindi', name)
        self.assertIn('Female', name)
        self.assertIn('Alpha', name)


class TestVoiceRegistry(unittest.TestCase):
    """Verify the voice registry is consistent."""

    def test_all_voices_returns_flat_list(self):
        all_v = language_config.get_all_voices()
        self.assertIsInstance(all_v, list)
        self.assertGreater(len(all_v), 0)

    def test_no_duplicate_voices(self):
        all_v = language_config.get_all_voices()
        self.assertEqual(len(all_v), len(set(all_v)),
                         'Duplicate voices found in registry')

    def test_all_voices_map_to_valid_lang_code(self):
        for voice in language_config.get_all_voices():
            lang = language_config.get_lang_code_for_voice(voice)
            self.assertIn(lang, language_config.LANGUAGE_META,
                          f'{voice} mapped to unknown lang_code {lang}')

    def test_get_voices_for_language(self):
        hindi_voices = language_config.get_voices_for_language('h')
        self.assertIn('hf_alpha', hindi_voices)
        self.assertIn('hm_omega', hindi_voices)

    def test_voices_for_unknown_language(self):
        self.assertEqual(
            language_config.get_voices_for_language('x'), [])


class TestPersonasConfig(unittest.TestCase):
    """Verify personas.json is well-formed and consistent."""

    @classmethod
    def setUpClass(cls):
        personas_path = os.path.join(
            os.path.dirname(__file__), '..', 'personas.json')
        with open(personas_path, 'r', encoding='utf-8') as f:
            cls.personas = json.load(f)

    def test_every_persona_has_required_keys(self):
        for name, data in self.personas.items():
            self.assertIn('voice', data,
                          f'Persona "{name}" missing "voice" key')
            self.assertIn('language', data,
                          f'Persona "{name}" missing "language" key')
            self.assertIn('prompt', data,
                          f'Persona "{name}" missing "prompt" key')

    def test_persona_voices_exist_in_registry(self):
        all_voices = language_config.get_all_voices()
        for name, data in self.personas.items():
            self.assertIn(data['voice'], all_voices,
                          f'Persona "{name}" uses unknown voice "{data["voice"]}"')

    def test_persona_language_matches_voice(self):
        """The language field must match the voice prefix."""
        for name, data in self.personas.items():
            expected_lang = language_config.get_lang_code_for_voice(
                data['voice'])
            self.assertEqual(
                data['language'], expected_lang,
                f'Persona "{name}": language "{data["language"]}" does not '
                f'match voice "{data["voice"]}" (expected "{expected_lang}")')

    def test_has_multilingual_personas(self):
        """There should be at least one non-English persona."""
        languages = {d['language'] for d in self.personas.values()}
        non_english = languages - {'a', 'b'}
        self.assertGreater(
            len(non_english), 0,
            'Expected at least one non-English persona')


if __name__ == '__main__':
    unittest.main()
