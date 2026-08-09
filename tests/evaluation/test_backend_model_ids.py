"""Guard the model IDs the alt backends point at.

These tests need no network and no torch, so they run in CI. They exist
because two model-ID bugs shipped and were only caught by running the
backends by hand:

  - alt_tts_backends.py used facebook/mms-tts-que, which does not exist. The
    real Quechua checkpoint is mms-tts-quz (ISO 639-3, Cusco Quechua).
  - the same Quechua row in MANIFEST.json already said quz, so the code and
    the manifest had silently drifted apart.

A wrong model ID doesn't fail until a child actually picks that language and
the download 404s mid lesson, which is the worst possible time to find out.
Checking the IDs statically moves that failure to CI.
"""

import ast
import json
import os
import re
import unittest

HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
BACKENDS_PY = os.path.join(ROOT, 'alt_tts_backends.py')
MANIFEST = os.path.join(ROOT, 'MANIFEST.json')

# ISO 639-3 codes for which facebook/mms-tts-<code> is known to exist. These
# were verified against Hugging Face by hand. `que` is deliberately absent:
# it is the bug this file guards against.
KNOWN_MMS_CODES = {
    'arb', 'swh', 'kin', 'quz', 'quy', 'grn', 'gug', 'ayr',
    'hin', 'spa', 'fra', 'por', 'cmn', 'eng',
}


def _mms_ids_from_backends():
    """Map lang -> mms code as declared in alt_tts_backends.py, via regex.

    Regex rather than import because importing the module here would be fine,
    but keeping the check import-free means it never accidentally depends on
    torch being installed on the runner.
    """
    src = open(BACKENDS_PY, encoding='utf-8').read()
    return dict(re.findall(r"'(\w+)':\s*\{'model':\s*'facebook/mms-tts-(\w+)'", src))


def _mms_ids_from_manifest():
    """Map lang -> mms code as declared in MANIFEST.json."""
    models = json.load(open(MANIFEST, encoding='utf-8'))['models']
    out = {}
    for entry in models.values():
        if entry.get('backend') != 'mms':
            continue
        m = re.search(r'facebook/mms-tts-(\w+)', entry['url'])
        if m:
            out[entry['language']] = m.group(1)
    return out


class TestMMSModelIds(unittest.TestCase):
    def test_backend_ids_are_known_to_exist(self):
        for lang, code in _mms_ids_from_backends().items():
            self.assertIn(
                code, KNOWN_MMS_CODES,
                f"alt_tts_backends.py points {lang} at facebook/mms-tts-{code}, "
                f"which is not a known MMS checkpoint",
            )

    def test_backends_and_manifest_agree(self):
        backends = _mms_ids_from_backends()
        manifest = _mms_ids_from_manifest()
        for lang, code in manifest.items():
            if lang in backends:
                self.assertEqual(
                    backends[lang], code,
                    f"MMS code for {lang} disagrees: alt_tts_backends.py says "
                    f"{backends[lang]}, MANIFEST.json says {code}",
                )

    def test_no_dead_que_code(self):
        # Explicit regression pin for the exact bug that shipped.
        self.assertNotIn(
            'que', _mms_ids_from_backends().values(),
            "facebook/mms-tts-que does not exist; Quechua must use quz",
        )


class TestBackendsParse(unittest.TestCase):
    def test_alt_backends_is_valid_python(self):
        # Cheap smoke test so a syntax error in the backend file trips here
        # rather than only when something imports it under torch.
        with open(BACKENDS_PY, encoding='utf-8') as f:
            ast.parse(f.read())


if __name__ == '__main__':
    unittest.main()
