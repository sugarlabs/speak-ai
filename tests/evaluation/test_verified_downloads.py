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

"""Multi-file verified downloads, and that the backends actually use them.

test_model_manager.py covers a single verified file. Neither backend loads a
single file: Piper wants its .onnx.json beside the .onnx, and transformers
wants config.json, vocab.json and the tokenizer files beside
model.safetensors. Verifying only the weights leaves the rest unpinned, and a
swapped vocab.json changes what the model says just as surely as swapped
weights would.

The second half is the part that was missing before: ModelManager existed and
its own tests passed while nothing on the synthesis path ever called it. These
drive the real _ensure_loaded, so unwiring it fails here.

Fixtures come from test_model_manager so the localhost server and manifest
helpers are defined once.
"""

import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from test_model_manager import (  # noqa: E402
    ModelManagerTestBase, ServedDirectory, sha256_of,
)

MANIFEST_JSON = os.path.join(
    os.path.dirname(__file__), '..', '..', 'MANIFEST.json')

WEIGHTS = b"pretend safetensors" * 500
CONFIG = b'{"model_type": "vits"}'
VOCAB = b'{"a": 0, "b": 1}'


class TestGetDir(ModelManagerTestBase):

    def _manifest(self, srv, primary_hash=None, extra_hash=None):
        weights_url = srv.publish("model.safetensors", WEIGHTS)
        config_url = srv.publish("config.json", CONFIG)
        vocab_url = srv.publish("vocab.json", VOCAB)
        self.write_manifest({"m": {
            "filename": "mms/model.safetensors",
            "url": weights_url,
            "sha256": sha256_of(WEIGHTS) if primary_hash is None else primary_hash,
            "extra_files": [
                {"filename": "config.json", "url": config_url,
                 "sha256": sha256_of(CONFIG) if extra_hash is None else extra_hash},
                {"filename": "vocab.json", "url": vocab_url,
                 "sha256": sha256_of(VOCAB)},
            ],
        }})

    def test_assembles_a_complete_directory(self):
        with ServedDirectory() as srv:
            self._manifest(srv)
            directory = self.manager().get_dir("m")

        self.assertIsNotNone(directory)
        self.assertTrue((directory / "model.safetensors").is_file())
        self.assertTrue((directory / "config.json").is_file())
        self.assertTrue((directory / "vocab.json").is_file())
        self.assertEqual((directory / "config.json").read_bytes(), CONFIG)

    def test_companions_land_beside_the_weights(self):
        """from_pretrained resolves siblings, so the layout is load-bearing."""
        with ServedDirectory() as srv:
            self._manifest(srv)
            directory = self.manager().get_dir("m")
        weights = directory / "model.safetensors"
        self.assertEqual(weights.parent, directory)

    def test_a_corrupt_companion_fails_the_whole_directory(self):
        with ServedDirectory() as srv:
            self._manifest(srv, extra_hash=sha256_of(b"something else"))
            directory = self.manager().get_dir("m")
        self.assertIsNone(
            directory,
            "a directory with an unverified companion must not be handed to "
            "a loader")

    def test_an_unpinned_companion_is_refused(self):
        with ServedDirectory() as srv:
            self._manifest(srv, extra_hash="")
            self.assertIsNone(self.manager().get_dir("m"))

    def test_a_corrupt_primary_fails_before_any_companion(self):
        with ServedDirectory() as srv:
            self._manifest(srv, primary_hash=sha256_of(b"wrong"))
            directory = self.manager().get_dir("m")
        self.assertIsNone(directory)

    def test_unknown_model_is_none(self):
        self.write_manifest({})
        self.assertIsNone(self.manager().get_dir("nope"))

    def test_cached_files_are_not_refetched(self):
        with ServedDirectory() as srv:
            self._manifest(srv)
            mm = self.manager()
            first = mm.get_dir("m")
            self.assertIsNotNone(first)
            # Server goes away; a second call must be satisfied from disk.
        second = self.manager().get_dir("m")
        self.assertEqual(second, first)

    def test_low_ram_devices_get_nothing(self):
        with ServedDirectory() as srv:
            self._manifest(srv)
            mm = self.manager(force_neural=False)
            mm.neural_allowed = False
            self.assertIsNone(mm.get_dir("m"))


class TestShippedManifest(unittest.TestCase):
    """The real MANIFEST.json is well formed and complete."""

    @classmethod
    def setUpClass(cls):
        with open(MANIFEST_JSON, encoding='utf-8') as f:
            cls.data = json.load(f)
        cls.models = cls.data['models']

    def test_every_entry_has_the_required_fields(self):
        for name, entry in self.models.items():
            with self.subTest(model=name):
                for field in ('filename', 'url', 'sha256', 'language', 'backend'):
                    self.assertIn(field, entry)

    def test_extra_files_are_well_formed(self):
        for name, entry in self.models.items():
            for extra in entry.get('extra_files', []):
                with self.subTest(model=name, extra=extra.get('filename')):
                    for field in ('filename', 'url', 'sha256'):
                        self.assertIn(field, extra)
                    self.assertNotIn(
                        '/', extra['filename'],
                        "companions resolve relative to the primary's "
                        "directory, so a path separator would escape it")

    def test_piper_entries_pin_their_config(self):
        """PiperVoice.load fails without the .onnx.json beside the .onnx."""
        for name, entry in self.models.items():
            if entry['backend'] != 'piper':
                continue
            with self.subTest(model=name):
                names = [e['filename'] for e in entry.get('extra_files', [])]
                self.assertTrue(
                    any(n.endswith('.onnx.json') for n in names),
                    f"{name} has no .onnx.json companion pinned")

    def test_mms_entries_pin_the_tokenizer_files(self):
        """from_pretrained needs all of these next to the weights."""
        required = {'config.json', 'vocab.json', 'tokenizer_config.json'}
        for name, entry in self.models.items():
            if entry['backend'] != 'mms':
                continue
            with self.subTest(model=name):
                names = {e['filename'] for e in entry.get('extra_files', [])}
                self.assertTrue(
                    required.issubset(names),
                    f"{name} is missing {sorted(required - names)}")

    def test_mms_weights_live_in_their_own_directory(self):
        """from_pretrained takes a directory, so models cannot share one."""
        directories = []
        for name, entry in self.models.items():
            if entry['backend'] != 'mms':
                continue
            directories.append(str(Path(entry['filename']).parent))
        self.assertEqual(len(directories), len(set(directories)),
                         "two MMS models share a directory; their config.json "
                         "files would overwrite each other")

    def test_hashes_are_empty_or_valid(self):
        """Empty is the shipped state; anything present must be a real digest."""
        def check(label, value):
            if value == '':
                return
            self.assertRegex(value, r'^[0-9a-f]{64}$',
                             f"{label} is neither empty nor a sha256")

        for name, entry in self.models.items():
            check(name, entry['sha256'])
            for extra in entry.get('extra_files', []):
                check(f"{name}:{extra['filename']}", extra['sha256'])


class TestBackendsConsultModelManager(unittest.TestCase):
    """The wiring. ModelManager being correct is not the same as it being used."""

    def setUp(self):
        import alt_tts_backends
        self.backends = alt_tts_backends

    def test_unknown_model_falls_back_quietly(self):
        """Most Piper voices are not pinned; that must not be an error path."""
        self.assertIsNone(self.backends._verified_model_dir('piper_nonexistent'))

    def test_mms_loads_from_the_verified_directory(self):
        transformers = types.ModuleType('transformers')
        transformers.AutoTokenizer = MagicMock()
        transformers.VitsModel = MagicMock()
        local = Path('/models/mms/mms-tts-kin')

        with patch.dict(sys.modules, {'transformers': transformers}), \
                patch.object(self.backends, '_verified_model_dir',
                             return_value=local) as resolve:
            backend = self.backends.MMSTTSBackend('rw')
            backend._ensure_loaded()

        resolve.assert_called_once_with('mms_rw')
        transformers.VitsModel.from_pretrained.assert_called_once_with(str(local))
        transformers.AutoTokenizer.from_pretrained.assert_called_once_with(str(local))

    def test_mms_falls_back_to_the_hub_when_unpinned(self):
        transformers = types.ModuleType('transformers')
        transformers.AutoTokenizer = MagicMock()
        transformers.VitsModel = MagicMock()

        with patch.dict(sys.modules, {'transformers': transformers}), \
                patch.object(self.backends, '_verified_model_dir',
                             return_value=None):
            backend = self.backends.MMSTTSBackend('rw')
            backend._ensure_loaded()

        transformers.VitsModel.from_pretrained.assert_called_once_with(
            'facebook/mms-tts-kin')

    def test_piper_loads_from_the_verified_directory(self):
        piper = types.ModuleType('piper')
        piper.PiperVoice = MagicMock()
        local = Path('/models/piper')

        with patch.dict(sys.modules, {'piper': piper}), \
                patch.object(self.backends, '_verified_model_dir',
                             return_value=local) as resolve:
            backend = self.backends.PiperBackend('ar')
            backend._ensure_loaded()

        resolve.assert_called_once_with('piper_ar')
        piper.PiperVoice.load.assert_called_once_with(
            str(local / 'ar_JO-kareem-medium.onnx'),
            config_path=str(local / 'ar_JO-kareem-medium.onnx.json'))

    def test_piper_falls_back_to_the_hub_when_unpinned(self):
        piper = types.ModuleType('piper')
        piper.PiperVoice = MagicMock()
        hub = types.ModuleType('huggingface_hub')
        hub.hf_hub_download = MagicMock(side_effect=lambda repo, path: f'/hub/{path}')

        with patch.dict(sys.modules, {'piper': piper, 'huggingface_hub': hub}), \
                patch.object(self.backends, '_verified_model_dir',
                             return_value=None):
            backend = self.backends.PiperBackend('ar')
            backend._ensure_loaded()

        self.assertEqual(hub.hf_hub_download.call_count, 2)
        piper.PiperVoice.load.assert_called_once()


if __name__ == '__main__':
    unittest.main()
