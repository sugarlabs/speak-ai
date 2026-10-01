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

"""Text normalization: what it fixes, and what espeak-ng already handles.

Two kinds of test live here and they are doing different jobs.

The first kind checks normalize_text itself — that composition, apostrophe
folding and joiner stripping happen, and that the function never raises.

The second kind is unusual and worth explaining. Several normalization steps
that the design called for turned out to be unnecessary, because espeak-ng
already does them. Rather than delete that finding into a commit message,
each one is asserted here against the live espeak-ng. They pass today because
espeak-ng is correct today. If a future espeak-ng stops deleting the Hindi
word-final schwa, or stops reading numerals in the target language, the
corresponding test fails and points at the already-written, already-reviewed
function in normalizer.py that becomes the fix.

That is the only honest way to ship "we did not need to do this": prove it,
and leave a tripwire.
"""

import os
import sys
import unicodedata
import unittest

sys.path.insert(0, os.path.dirname(__file__))

import espeakng_loader  # noqa: E402
os.environ.setdefault("ESPEAK_DATA_PATH", espeakng_loader.get_data_path())

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from speech_utils.normalizer import (  # noqa: E402
    normalize_text, delete_final_schwa, ends_in_bare_consonant,
)

# Written as escapes on purpose: three of these are invisible in an editor,
# and a literal one has already been mangled into a null byte once.
ZWNJ = '‌'
CURLY = '’'
MODIFIER = 'ʼ'
LEFT_SINGLE = '‘'
ARMENIAN_APOS = '՚'
HALANT = '्'


def phonemize(text, lang):
    """One string through espeak-ng, or skip the test if it is unavailable."""
    from phonemizer.backend import EspeakBackend
    return EspeakBackend(lang).phonemize([text])[0].strip()


class TestNormalizeText(unittest.TestCase):

    def test_composes_to_nfc(self):
        decomposed = unicodedata.normalize('NFD', 'está')
        self.assertNotEqual(decomposed, 'está')
        self.assertEqual(normalize_text(decomposed, 'es'), 'está')

    def test_folds_every_apostrophe_to_ascii(self):
        for variant in (CURLY, MODIFIER, LEFT_SINGLE, ARMENIAN_APOS):
            with self.subTest(apostrophe=hex(ord(variant))):
                self.assertEqual(
                    normalize_text(f"mba{variant}echu", 'gn'),
                    "mba'echu")

    def test_strips_invisible_joiners(self):
        self.assertEqual(normalize_text(f'अनु{ZWNJ}च्छेद', 'hi'), 'अनुच्छेद')

    def test_collapses_whitespace(self):
        self.assertEqual(normalize_text('  hello   world  ', 'en-us'),
                         'hello world')

    def test_is_idempotent(self):
        once = normalize_text('¿Cómo está usted?', 'es')
        self.assertEqual(normalize_text(once, 'es'), once)

    def test_empty_and_whitespace_pass_through(self):
        for value in ('', '   ', None):
            with self.subTest(value=repr(value)):
                self.assertEqual(normalize_text(value, 'en-us'), value)

    def test_never_raises_on_odd_input(self):
        for value in ('\U0001f600 \ufffd', 'a' * 10000, '\\', '\U0001f1ee\U0001f1f3'):
            with self.subTest(value=value[:12]):
                self.assertIsInstance(normalize_text(value, 'hi'), str)


class TestDetectionIsWhyThisExists(unittest.TestCase):
    """The bug normalization actually fixes, reproduced end to end.

    Decomposed text scores zero language hints and falls through to English,
    so a Spanish child who pastes from a word processor is read to in English.
    """

    @staticmethod
    def _detect(text):
        import ast
        import re
        speech_py = os.path.join(ROOT, 'speech.py')
        with open(speech_py, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
        hints = None
        for node in ast.walk(tree):
            if (isinstance(node, ast.Assign)
                    and getattr(node.targets[0], 'id', None) == '_LATIN_HINTS'):
                hints = ast.literal_eval(node.value)
        assert hints is not None, "_LATIN_HINTS not found in speech.py"

        token_re = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)*", re.UNICODE)
        folded = text.lower().translate(
            str.maketrans({CURLY: "'", MODIFIER: "'"}))
        tokens = set(token_re.findall(folded))
        best, best_score = None, 0
        for lang, words in hints.items():
            score = sum(1 for w in words if w in tokens)
            if score > best_score:
                best, best_score = lang, score
        return best

    def test_decomposed_spanish_is_undetectable_without_normalization(self):
        decomposed = unicodedata.normalize('NFD', '¿Cómo está usted?')
        self.assertIsNone(
            self._detect(decomposed),
            "if this now detects, the detector became Unicode-robust on its "
            "own and normalize_text's main justification needs revisiting")

    def test_normalization_restores_detection(self):
        decomposed = unicodedata.normalize('NFD', '¿Cómo está usted?')
        self.assertEqual(self._detect(normalize_text(decomposed, 'es')), 'es')


class TestEspeakAlreadyHandlesIt(unittest.TestCase):
    """Tripwires for the normalization steps that turned out unnecessary."""

    # 10 words covering final stops, nasals, laterals, flaps and a nukta form.
    HINDI_WORDS = ['कमल', 'सूरज', 'नमक', 'दिल', 'शहर',
                   'मकान', 'कागज', 'सड़क', 'बचपन', 'जंगल']

    def test_espeak_still_handles_hindi_schwa(self):
        """An explicit halant changes nothing, so we do not insert one.

        If this fails, espeak-ng has changed its Hindi schwa handling and
        normalizer.delete_final_schwa is the fix that is already written.
        """
        for word in self.HINDI_WORDS:
            with self.subTest(word=word):
                self.assertEqual(
                    phonemize(word, 'hi'),
                    phonemize(word + HALANT, 'hi'),
                    f"espeak-ng now distinguishes {word} from {word}{HALANT}; "
                    "wire delete_final_schwa into normalize_text for 'hi'")

    def test_espeak_keeps_the_schwa_where_hindi_keeps_it(self):
        """कृष्ण and मित्र are conjunct-final and keep their schwa."""
        for word in ('कृष्ण', 'मित्र'):
            with self.subTest(word=word):
                self.assertTrue(
                    phonemize(word, 'hi').endswith('ə'),
                    f"{word} should retain its final schwa")

    def test_espeak_reads_hindi_numerals_in_hindi(self):
        """"42" is read बयालीस, not "forty-two"; no expansion needed.

        num2words has no Hindi at all, so the alternative to relying on this
        is hand-writing 100 irregular number words. espeak already has them.
        """
        ipa = phonemize('42', 'hi')
        self.assertTrue(ipa and not ipa.isspace())
        self.assertNotEqual(ipa, phonemize('42', 'en-us'))

    def test_espeak_reads_arabic_indic_digits_natively(self):
        """٣ and 3 are the same to the Arabic voice, so no digit mapping."""
        self.assertEqual(phonemize('٣ طلاب', 'ar'), phonemize('3 طلاب', 'ar'))

    def test_num2words_arabic_would_be_worse(self):
        """Expanding first produces different phonemes than espeak's own.

        Recorded because the design called for num2words here and it is the
        wrong call: espeak reads ٣ as θalaːθa, and feeding it the spelled-out
        ثلاثة instead yields θlaːθt.
        """
        self.assertNotEqual(phonemize('٣ طلاب', 'ar'),
                            phonemize('ثلاثة طلاب', 'ar'))

    def test_espeak_accepts_any_ejective_form(self):
        """Composed, decomposed, ASCII, U+2019 and U+02BC all agree."""
        base = "qhali q'umir"
        forms = [base,
                 unicodedata.normalize('NFD', base),
                 base.replace("'", CURLY),
                 base.replace("'", MODIFIER)]
        results = {phonemize(f, 'qu') for f in forms}
        self.assertEqual(len(results), 1, f"ejective forms diverged: {results}")

    def test_espeak_ignores_a_stray_joiner(self):
        self.assertEqual(phonemize('अनुच्छेद', 'hi'),
                         phonemize(f'अनु{ZWNJ}च्छेद', 'hi'))


class TestSchwaHelpers(unittest.TestCase):
    """delete_final_schwa is unused at runtime but must stay correct."""

    def test_detects_bare_final_consonant(self):
        self.assertTrue(ends_in_bare_consonant('राम'))
        self.assertTrue(ends_in_bare_consonant('कमल'))

    def test_rejects_matra_and_conjunct_endings(self):
        self.assertFalse(ends_in_bare_consonant('कमरा'))    # ends in matra
        self.assertFalse(ends_in_bare_consonant('मित्र'))   # conjunct tail
        self.assertFalse(ends_in_bare_consonant(''))

    def test_leaves_the_keep_list_alone(self):
        self.assertEqual(delete_final_schwa('कृष्ण'), 'कृष्ण')
        self.assertEqual(delete_final_schwa('मित्र'), 'मित्र')

    def test_appends_halant_to_bare_consonant_words(self):
        self.assertEqual(delete_final_schwa('राम'), 'राम' + HALANT)

    def test_leaves_non_devanagari_untouched(self):
        self.assertEqual(delete_final_schwa('hello world'), 'hello world')


if __name__ == '__main__':
    unittest.main()
