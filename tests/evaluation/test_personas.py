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

"""personas.json agrees with the language table and with activity.py.

Two failures this catches, both of which were live on this branch:

  - A language reachable from the Languages palette with no persona behind it.
    A child could select Quechua, get the palette highlight, and then have
    nothing to talk to, because every persona pinned some other language.
  - A persona missing 'voice'. activity.py subscripts it directly
    (self._personas[name]['voice']), so an absent key is a KeyError at
    persona-selection time rather than a graceful default.

Reads SUPPORTED_LANGUAGES out of speech.py with ast, so no torch import.
"""

import ast
import json
import os
import unittest

ROOT = os.path.join(os.path.dirname(__file__), '..', '..')
SPEECH_PY = os.path.join(ROOT, 'speech.py')
PERSONAS_JSON = os.path.join(ROOT, 'personas.json')

# English is the default and needs no pinned persona: unpinned personas
# already speak it, and pinning it would stop them auto-detecting.
LANGS_NEEDING_A_PERSONA_EXEMPT = {'en-us', 'en-gb'}


def _supported_languages():
    with open(SPEECH_PY, encoding='utf-8') as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == 'SUPPORTED_LANGUAGES':
                    return ast.literal_eval(node.value)
    raise AssertionError("SUPPORTED_LANGUAGES not found in speech.py")


LANGS = _supported_languages()
SUPPORTED_CODES = {code for _tier, code, _name, _endonym in LANGS}

with open(PERSONAS_JSON, encoding='utf-8') as f:
    PERSONAS = json.load(f)


class TestPersonaSchema(unittest.TestCase):

    def test_there_are_personas(self):
        self.assertGreater(len(PERSONAS), 0)

    def test_every_persona_has_the_keys_activity_subscripts(self):
        for name, persona in PERSONAS.items():
            with self.subTest(persona=name):
                # activity.py:1135 does self._personas[name]['voice'].
                self.assertIn('voice', persona,
                              "activity.py subscripts 'voice' directly")
                self.assertIn('prompt', persona)

    def test_voice_and_prompt_are_non_empty_strings(self):
        for name, persona in PERSONAS.items():
            with self.subTest(persona=name):
                for key in ('voice', 'prompt'):
                    value = persona[key]
                    self.assertIsInstance(value, str)
                    self.assertTrue(value.strip(), f"{key} is blank")

    def test_pinned_languages_are_supported(self):
        for name, persona in PERSONAS.items():
            lang = persona.get('lang')
            if lang is None:
                continue
            with self.subTest(persona=name):
                self.assertIn(
                    lang, SUPPORTED_CODES,
                    f"persona pins '{lang}', which is not in "
                    "SUPPORTED_LANGUAGES; set_language_hint would pin a "
                    "language the activity cannot route")


class TestPaletteCoverage(unittest.TestCase):
    """Every language the palette offers has something to talk to."""

    def test_every_non_english_language_has_a_persona(self):
        pinned = {p.get('lang') for p in PERSONAS.values()} - {None}
        missing = sorted(
            SUPPORTED_CODES - pinned - LANGS_NEEDING_A_PERSONA_EXEMPT)
        self.assertEqual(
            missing, [],
            f"languages in the palette with no persona: {missing}. A child "
            "can select these and then has nobody who answers in them.")

    def test_tier_3_languages_are_covered(self):
        """Named explicitly: these are the ones that were missing."""
        pinned = {p.get('lang') for p in PERSONAS.values()}
        for code in ('qu', 'gn', 'rw', 'ay'):
            with self.subTest(lang=code):
                self.assertIn(code, pinned)

    def test_no_two_personas_pin_the_same_language(self):
        """Not fatal, but it makes the palette ambiguous — flag it early."""
        pins = [p['lang'] for p in PERSONAS.values() if p.get('lang')]
        dupes = sorted({c for c in pins if pins.count(c) > 1})
        self.assertEqual(dupes, [], f"more than one persona pins: {dupes}")


if __name__ == '__main__':
    unittest.main()
