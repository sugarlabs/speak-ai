"""Checks on the SUPPORTED_LANGUAGES table that drives the language palette.

Read out of speech.py with ast rather than imported, because importing speech
pulls in gi/GStreamer, which a CI runner does not have. Same trick as
test_language_aliases.py.

What this guards:
  - no duplicate language codes (a dup would make one entry unreachable in the
    palette selection dict, since it is keyed by code)
  - every row is well formed (tier, code, name, endonym all present and non
    empty) so the palette never renders a blank label
  - the tiers are the expected three, so a typo like "Neural(Kokoro)" doesn't
    silently create a fourth group
"""

import ast
import os
import unittest

SPEECH_PY = os.path.join(os.path.dirname(__file__), '..', '..', 'speech.py')

EXPECTED_TIERS = {'Neural (Kokoro)', 'Neural (Piper)', 'Basic (MMS)'}


def _supported_languages():
    """Pull the SUPPORTED_LANGUAGES literal out of speech.py without importing."""
    with open(SPEECH_PY, encoding='utf-8') as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == 'SUPPORTED_LANGUAGES':
                    return ast.literal_eval(node.value)
    raise AssertionError("SUPPORTED_LANGUAGES not found in speech.py")


LANGS = _supported_languages()


class TestSupportedLanguages(unittest.TestCase):
    def test_table_is_non_empty(self):
        self.assertGreater(len(LANGS), 0)

    def test_rows_are_well_formed(self):
        for row in LANGS:
            self.assertEqual(len(row), 4, f"row is not (tier, code, name, endonym): {row}")
            tier, code, name, endonym = row
            for field in row:
                self.assertTrue(
                    isinstance(field, str) and field.strip(),
                    f"empty or non-string field in {row}",
                )

    def test_no_duplicate_codes(self):
        codes = [code for _tier, code, _name, _endonym in LANGS]
        dupes = {c for c in codes if codes.count(c) > 1}
        self.assertEqual(dupes, set(), f"duplicate language codes: {dupes}")

    def test_tiers_are_expected(self):
        tiers = {row[0] for row in LANGS}
        self.assertEqual(
            tiers, EXPECTED_TIERS,
            f"unexpected tier labels (a typo makes a stray palette group): {tiers}",
        )

    def test_covers_the_eleven_target_languages_plus_english(self):
        codes = {code for _tier, code, _name, _endonym in LANGS}
        expected = {'en-us', 'hi', 'es', 'fr', 'pt-br', 'zh',
                    'ar', 'sw', 'rw', 'qu', 'gn', 'ay'}
        self.assertEqual(codes, expected, "language coverage drifted from the target set")


if __name__ == '__main__':
    unittest.main()
