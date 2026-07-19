"""Language registration + G2P reachability checks.

This is the CI gate. It deliberately does NOT import kokoro, because importing
kokoro pulls in torch, and a ~1.5 GB model runtime has no business running on
every pull request. Instead the ALIASES / LANG_CODES tables are read straight
out of kokoro/pipeline.py with `ast`, which needs nothing but the standard
library, and the phoneme checks go through misaki's espeak backend directly.

What this protects against, concretely:

  - a language alias silently colliding with another one (two languages
    mapping to the same single-letter code, so one of them stops working)
  - a language registered in ALIASES but missing from LANG_CODES, or the
    reverse — the pairing is what makes a language actually reachable
  - espeak-ng producing nothing for a language we claim to support

The last one is the important one. A language can look registered, route
correctly, and still emit an empty phoneme string, at which point the child
presses Speak and hears silence.
"""

import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))

PIPELINE_PY = os.path.join(
    os.path.dirname(__file__), '..', '..', 'kokoro', 'pipeline.py'
)


def _literal_dicts_from(path, *names):
    """Pull top-level dict assignments out of a module without importing it.

    Handles both `X = {...}` and `X = dict(a='b', ...)`, since pipeline.py
    happens to use one of each.
    """
    with open(path, 'r', encoding='utf-8') as f:
        tree = ast.parse(f.read())

    found = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name) or target.id not in names:
                continue

            value = node.value
            if isinstance(value, ast.Dict):
                found[target.id] = ast.literal_eval(value)
            elif isinstance(value, ast.Call) and getattr(value.func, 'id', None) == 'dict':
                found[target.id] = {
                    kw.arg: ast.literal_eval(kw.value) for kw in value.keywords
                }
    return found


_TABLES = _literal_dicts_from(PIPELINE_PY, 'ALIASES', 'LANG_CODES')
ALIASES = _TABLES.get('ALIASES', {})
LANG_CODES = _TABLES.get('LANG_CODES', {})

# Languages routed through espeak-ng, keyed by the BCP-47 tag espeak expects.
# English/Japanese/Mandarin are excluded on purpose: they use misaki's own
# G2P (en / ja / zh), not espeak, so they are not this gate's business.
ESPEAK_LANGS = {
    'es': 'Spanish',
    'fr-fr': 'French',
    'hi': 'Hindi',
    'it': 'Italian',
    'pt-br': 'Portuguese (BR)',
    'ar': 'Arabic',
    'sw': 'Swahili',
    'qu': 'Quechua',
    'gn': 'Guarani',
}


class TestTablesParsed(unittest.TestCase):
    def test_tables_were_found(self):
        self.assertTrue(ALIASES, "ALIASES could not be read from kokoro/pipeline.py")
        self.assertTrue(LANG_CODES, "LANG_CODES could not be read from kokoro/pipeline.py")


class TestAliasIntegrity(unittest.TestCase):
    def test_no_duplicate_single_letter_codes(self):
        """Two languages sharing a code means one of them is unreachable."""
        seen = {}
        for lang, code in ALIASES.items():
            self.assertNotIn(
                code, seen,
                f"alias collision: '{lang}' and '{seen.get(code)}' both map to '{code}'",
            )
            seen[code] = lang

    def test_every_alias_has_a_lang_code_entry(self):
        for lang, code in ALIASES.items():
            self.assertIn(
                code, LANG_CODES,
                f"'{lang}' -> '{code}' is in ALIASES but '{code}' is missing "
                f"from LANG_CODES, so the language never resolves",
            )

    def test_codes_are_single_characters(self):
        for lang, code in ALIASES.items():
            self.assertEqual(len(code), 1, f"'{lang}' maps to non-single-char code {code!r}")

    def test_expected_languages_are_registered(self):
        """The set this project committed to supporting via Kokoro's G2P."""
        for lang in ['es', 'fr-fr', 'hi', 'pt-br', 'zh', 'ar', 'sw', 'qu', 'gn']:
            self.assertIn(lang, ALIASES, f"'{lang}' is not registered in ALIASES")


class TestEspeakCoverage(unittest.TestCase):
    """espeak-ng must actually emit phonemes for every language we route to it."""

    @classmethod
    def setUpClass(cls):
        try:
            import espeakng_loader
            os.environ.setdefault("ESPEAK_DATA_PATH", espeakng_loader.get_data_path())
            from misaki import espeak            # noqa: F401
        except ImportError as e:                 # pragma: no cover
            raise unittest.SkipTest(f"espeak/misaki unavailable: {e}")

    def _phonemize(self, lang, text):
        from misaki import espeak
        g2p = espeak.EspeakG2P(language=lang)
        result = g2p(text)
        # EspeakG2P returns a bare string; en/ja/zh G2Ps return a tuple.
        # Unpacking blindly here shreds the string character by character —
        # this is the exact bug that was live in verify_all.py.
        return result[0] if isinstance(result, tuple) else result

    def test_every_espeak_language_produces_phonemes(self):
        for lang, name in ESPEAK_LANGS.items():
            with self.subTest(language=name):
                ps = self._phonemize(lang, "hello world")
                self.assertTrue(
                    ps and ps.strip(),
                    f"{name} ({lang}) produced no phonemes — a child would hear silence",
                )

    def test_no_unknown_token_markers(self):
        """espeak emits '(en)' style markers when it falls back to another voice."""
        for lang, name in ESPEAK_LANGS.items():
            with self.subTest(language=name):
                ps = self._phonemize(lang, "hello world")
                self.assertNotIn(
                    '(en)', ps,
                    f"{name} ({lang}) fell back to English phonemisation: {ps!r}",
                )

    def test_phonemes_are_not_pass_through_text(self):
        """A G2P that hands back the input unchanged has not done anything."""
        for lang, name in ESPEAK_LANGS.items():
            with self.subTest(language=name):
                text = "hello world"
                self.assertNotEqual(
                    self._phonemize(lang, text).strip(), text,
                    f"{name} ({lang}) returned the input verbatim",
                )


if __name__ == '__main__':
    unittest.main()
