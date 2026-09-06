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

"""The PER gate, plus tests for the metric itself.

Testing the measuring instrument matters as much as running it here. A PER
implementation that silently returns 0.0 passes every regression check
forever and nobody notices, which is a worse outcome than having no gate at
all — so the arithmetic is pinned down separately from the corpus run.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))

from eval_per import (  # noqa: E402
    DEFAULT_THRESHOLD, PER_LANGUAGES, corpus_sentences, evaluate,
    levenshtein, phoneme_error_rate, phoneme_tokens, reference_path,
)


class TestPhonemeTokens(unittest.TestCase):

    def test_modifiers_attach_to_their_base(self):
        """/kʰ/ is one phoneme; counting it as two doubles every aspirate."""
        self.assertEqual(phoneme_tokens('kʰ'), ['kʰ'])
        self.assertEqual(phoneme_tokens('aː'), ['aː'])
        self.assertEqual(phoneme_tokens('kʰaːnə'), ['kʰ', 'aː', 'n', 'ə'])

    def test_combining_marks_attach_to_their_base(self):
        self.assertEqual(phoneme_tokens('ẽ'), ['ẽ'])       # composed
        self.assertEqual(phoneme_tokens('ẽ'), ['ẽ'])   # combining

    def test_whitespace_is_dropped(self):
        self.assertEqual(phoneme_tokens('a b'), ['a', 'b'])

    def test_empty(self):
        self.assertEqual(phoneme_tokens(''), [])


class TestLevenshtein(unittest.TestCase):

    def test_identical_is_zero(self):
        self.assertEqual(levenshtein(['a', 'b'], ['a', 'b']), 0)

    def test_counts_each_edit_once(self):
        self.assertEqual(levenshtein(['a', 'b'], ['a', 'c']), 1)      # sub
        self.assertEqual(levenshtein(['a', 'b'], ['a']), 1)           # del
        self.assertEqual(levenshtein(['a'], ['a', 'b']), 1)           # ins

    def test_empty_operands(self):
        self.assertEqual(levenshtein([], ['a', 'b']), 2)
        self.assertEqual(levenshtein(['a', 'b'], []), 2)
        self.assertEqual(levenshtein([], []), 0)

    def test_is_symmetric(self):
        a, b = list('kitten'), list('sitting')
        self.assertEqual(levenshtein(a, b), levenshtein(b, a))
        self.assertEqual(levenshtein(a, b), 3)


class TestPhonemeErrorRate(unittest.TestCase):

    def test_identical_is_zero(self):
        self.assertEqual(phoneme_error_rate('kʰaːnə', 'kʰaːnə'), 0.0)

    def test_one_error_in_four_phonemes(self):
        self.assertAlmostEqual(phoneme_error_rate('kʰaːnə', 'kʰaːnɪ'), 0.25)

    def test_does_not_silently_return_zero(self):
        """The failure mode that would disable this gate permanently."""
        self.assertGreater(phoneme_error_rate('abcdef', 'uvwxyz'), 0.5)

    def test_empty_reference_with_output_is_total_error(self):
        self.assertEqual(phoneme_error_rate('', 'abc'), 1.0)

    def test_empty_both_is_no_error(self):
        self.assertEqual(phoneme_error_rate('', ''), 0.0)


class TestReferencesExist(unittest.TestCase):

    def test_every_language_has_a_reference(self):
        for lang in PER_LANGUAGES:
            with self.subTest(lang=lang):
                self.assertTrue(
                    os.path.isfile(reference_path(lang)),
                    f"missing reference for {lang}; run "
                    "`python tests/evaluation/eval_per.py --update-reference`")

    def test_reference_length_matches_the_corpus(self):
        for lang in PER_LANGUAGES:
            with self.subTest(lang=lang):
                with open(reference_path(lang), encoding='utf-8') as f:
                    lines = [line.rstrip('\n') for line in f]
                self.assertEqual(len(lines), len(corpus_sentences(lang)))

    def test_no_reference_line_is_empty(self):
        """An empty phoneme line is silence, and must never be the baseline."""
        for lang in PER_LANGUAGES:
            with open(reference_path(lang), encoding='utf-8') as f:
                for number, line in enumerate(f, start=1):
                    with self.subTest(lang=lang, line=number):
                        self.assertTrue(line.strip())


class TestCorpusPER(unittest.TestCase):
    """The gate itself: G2P output still matches the reviewed snapshot."""

    def test_every_language_is_within_threshold(self):
        for lang in PER_LANGUAGES:
            with self.subTest(lang=lang):
                result = evaluate(lang)
                self.assertLessEqual(
                    result['per'], DEFAULT_THRESHOLD,
                    f"{lang} PER {result['per']:.2%} exceeds "
                    f"{DEFAULT_THRESHOLD:.0%} over "
                    f"{result['reference_phonemes']} phonemes "
                    f"({result['changed_sentences']} sentences changed). "
                    "Run eval_per.py to see which, and only re-snapshot once "
                    "someone has read the diff.")


if __name__ == '__main__':
    unittest.main()
