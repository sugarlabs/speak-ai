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

"""Regression tests for Latin-script language detection.

speech.py cannot be imported here (it pulls in gi/GStreamer, which CI does not
have), so the detector and its tables are lifted out with ast and executed on
their own. Same approach as test_language_aliases.py.

Every case below is a bug that was live in this branch, not a hypothetical:

  - "s'il" (French) and "mba'echu" (Guarani) were listed as hints but could
    never match, because the tokeniser split on the apostrophe. Two languages
    were carrying dead hints.
  - "ha" was a Guarani hint and is also the Spanish auxiliary verb, so "Ella ha
    comido" detected as Guarani and a Spanish child got routed to Guarani MMS.
  - English had no hints at all, so English text was not positively identified,
    only left undetected. That is fine while the default is English, but a
    pinned persona language fills exactly the undetected case, so English text
    under a Spanish persona would have been spoken in Spanish.
"""

import ast
import os
import re
import unittest

SPEECH_PY = os.path.join(os.path.dirname(__file__), '..', '..', 'speech.py')

_WANTED = {
    '_LANG_DETECT_RANGES', '_LATIN_HINTS', '_TOKEN_RE', '_APOSTROPHES',
}
_FUNCS = {'_detect_language', '_detect_language_or_none'}


def _load_detector():
    """Execute just the detection machinery out of speech.py."""
    with open(SPEECH_PY, encoding='utf-8') as f:
        tree = ast.parse(f.read())

    keep = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in _WANTED:
                    keep.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in _FUNCS:
            keep.append(node)

    ns = {'re': re, 'Optional': __import__('typing').Optional}
    module = ast.Module(body=keep, type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), '<speech>', 'exec'), ns)
    return ns


NS = _load_detector()
detect = NS['_detect_language']
detect_or_none = NS['_detect_language_or_none']
HINTS = NS['_LATIN_HINTS']
TOKEN_RE = NS['_TOKEN_RE']
APOSTROPHES = NS['_APOSTROPHES']


def tokens(text):
    return set(TOKEN_RE.findall(text.lower().translate(APOSTROPHES)))


class TestHintsAreReachable(unittest.TestCase):
    """Every hint must be able to match under the real tokeniser."""

    def test_all_hints_survive_tokenisation(self):
        for lang, words in HINTS.items():
            for word in words:
                with self.subTest(lang=lang, word=word):
                    self.assertIn(
                        word, tokens(word),
                        f"hint {word!r} for {lang} cannot match: the tokeniser "
                        f"splits it into {sorted(tokens(word))}",
                    )

    def test_apostrophe_hints_match_in_a_sentence(self):
        self.assertIn("s'il", tokens("S'il vous plaît, aidez-moi"))
        self.assertIn("mba'éichapa", tokens("Mba'éichapa nde rera"))

    def test_typographic_apostrophe_is_folded(self):
        # Text pasted from a word processor uses U+2019, not U+0027.
        self.assertIn("s'il", tokens('S’il vous plaît'))


class TestNoCrossLanguageCollisions(unittest.TestCase):
    """A hint must not be a hint for, or a common word of, another language."""

    def test_hints_are_not_shared_across_languages(self):
        seen = {}
        for lang, words in HINTS.items():
            for word in words:
                if word in seen and seen[word] != lang:
                    # 'por'/'favor' are genuinely shared by es and pt-br and
                    # score for both, which is harmless; anything else is not.
                    self.assertIn(
                        word, {'por', 'favor', 'está', 'como'},
                        f"{word!r} is a hint for both {seen[word]} and {lang}",
                    )
                seen[word] = lang

    def test_spanish_auxiliary_ha_is_not_guarani(self):
        # The exact regression: 'ha' used to be a Guarani hint.
        for sentence in ('Ella ha comido.', 'Ha llegado el tren.'):
            with self.subTest(sentence=sentence):
                self.assertNotEqual(detect(sentence), 'gn')


class TestPositiveDetection(unittest.TestCase):
    def test_english_is_positively_detected(self):
        # Not merely "undetected and defaulted" — must be a real match, or a
        # pinned persona language would claim it.
        self.assertEqual(detect_or_none('Hello, how are you today?'), 'en-us')

    def test_each_latin_language_detects_from_its_own_hints(self):
        samples = {
            'es': 'Hola, gracias por favor',
            'fr': 'Bonjour, comment allez vous',
            'pt-br': 'Olá, obrigado, bom dia você',
            'sw': 'Jambo, asante, habari, karibu',
            'qu': 'Rimaykullayki, imayna, allin, pachamama',
            'gn': "Mba'éichapa, aguyje, rohayhu, porã",
            'rw': 'Muraho, amakuru, ubuntu, isoko',
            'ay': 'Kamisaraki, waliki, sumawa, jilata',
        }
        for lang, text in samples.items():
            with self.subTest(lang=lang):
                self.assertEqual(detect(text), lang)

    def test_scripts_still_win_over_hints(self):
        for text, want in [
            ('नमस्ते, आप कैसे हैं?', 'hi'),
            ('你好，你今天好吗？', 'zh'),
            ('مرحبا، كيف حالك اليوم؟', 'ar'),
        ]:
            with self.subTest(want=want):
                self.assertEqual(detect(text), want)


class TestUndetectedIsDistinguishable(unittest.TestCase):
    """The whole point of splitting _detect_language_or_none out."""

    def test_short_ambiguous_text_is_undetected(self):
        for text in ('Sí.', 'Oui.', 'Ok', ''):
            with self.subTest(text=text):
                self.assertIsNone(detect_or_none(text))

    def test_detect_language_still_defaults_to_english(self):
        # The public wrapper keeps its old contract for existing callers.
        self.assertEqual(detect('Sí.'), 'en-us')
        self.assertEqual(detect(''), 'en-us')

    def test_explicit_lang_code_overrides(self):
        self.assertEqual(detect('anything at all', 'fr'), 'fr')


if __name__ == '__main__':
    unittest.main()
