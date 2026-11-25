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

"""Disk accounting and the diagnostic summary on ModelManager.

test_model_manager.py covers the RAM gate and resolution; the three disk
methods were left untested. They matter on the hardware this activity targets:
an XO or a low-end Chromebook has a few GB of SD-card storage, and the models
this branch adds are 145MB for Piper plus the MMS checkpoints. `summary()` is
what a deployer reads to find out whether a machine can actually hold them.

`free_disk_mb` has the one non-obvious behaviour worth pinning: it walks up to
an existing ancestor, because it is called before the model directory has been
created and `shutil.disk_usage` on a missing path raises. That walk is a loop
with a root guard, and nothing exercised it.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from model_manager import ModelManager  # noqa: E402


def write_manifest(path, models):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'models': models}, f)


def write_file(path: Path, size_bytes: int):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'wb') as f:
        f.write(b'\0' * size_bytes)


class DiskTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='speakai-disk-'))
        self.model_dir = self.tmp / 'models'
        self.manifest_path = self.tmp / 'MANIFEST.json'
        write_manifest(self.manifest_path, {
            'piper_ar': {'filename': 'ar_JO-kareem.onnx'},
            'mms_rw': {'filename': 'mms-rw/model.safetensors'},
        })

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def manager(self):
        return ModelManager(model_dir=self.model_dir,
                            manifest_path=self.manifest_path)


class TestDiskUsage(DiskTestBase):
    def test_missing_model_dir_is_zero_not_an_error(self):
        # Called on first launch, before anything has been downloaded.
        self.assertEqual(self.manager().disk_usage_mb(), 0.0)

    def test_empty_model_dir_is_zero(self):
        self.model_dir.mkdir(parents=True)
        self.assertEqual(self.manager().disk_usage_mb(), 0.0)

    def test_usage_reflects_file_size(self):
        write_file(self.model_dir / 'ar_JO-kareem.onnx', 4 * 1024 ** 2)
        self.assertAlmostEqual(self.manager().disk_usage_mb(), 4.0, places=2)

    def test_usage_sums_across_files(self):
        write_file(self.model_dir / 'a.onnx', 2 * 1024 ** 2)
        write_file(self.model_dir / 'b.onnx', 3 * 1024 ** 2)
        self.assertAlmostEqual(self.manager().disk_usage_mb(), 5.0, places=2)

    def test_usage_recurses_into_subdirectories(self):
        # MMS checkpoints are directories, not single files. rglob rather than
        # glob is what makes them counted at all -- an accounting that reports
        # 0MB for the checkpoints is worse than none.
        write_file(self.model_dir / 'mms-rw' / 'model.safetensors', 2 * 1024 ** 2)
        write_file(self.model_dir / 'mms-rw' / 'config.json', 1024)
        write_file(self.model_dir / 'mms-rw' / 'nested' / 'vocab.json', 1024)
        usage = self.manager().disk_usage_mb()
        self.assertGreater(usage, 2.0)
        self.assertLess(usage, 2.1)

    def test_directories_do_not_contribute_their_own_size(self):
        # Only is_file() entries count, so an empty tree stays at zero however
        # many directories it contains.
        (self.model_dir / 'a' / 'b' / 'c').mkdir(parents=True)
        self.assertEqual(self.manager().disk_usage_mb(), 0.0)

    def test_usage_grows_as_models_arrive(self):
        mm = self.manager()
        write_file(self.model_dir / 'one.onnx', 1024 ** 2)
        first = mm.disk_usage_mb()
        write_file(self.model_dir / 'two.onnx', 1024 ** 2)
        self.assertGreater(mm.disk_usage_mb(), first)


class TestFreeDisk(DiskTestBase):
    def test_reports_a_positive_figure_for_an_existing_dir(self):
        self.model_dir.mkdir(parents=True)
        self.assertGreater(self.manager().free_disk_mb(), 0.0)

    def test_missing_model_dir_falls_back_to_an_existing_ancestor(self):
        # The common case: asked before the directory exists.
        self.assertGreater(self.manager().free_disk_mb(), 0.0)

    def test_walks_up_several_missing_levels(self):
        # The loop, not just the single-parent fallback. A deployer pointing
        # --model-dir at a path several levels below anything real must still
        # get a number rather than a FileNotFoundError.
        deep = self.tmp / 'a' / 'b' / 'c' / 'd' / 'models'
        mm = ModelManager(model_dir=deep, manifest_path=self.manifest_path)
        self.assertGreater(mm.free_disk_mb(), 0.0)

    def test_agrees_with_the_filesystem(self):
        self.model_dir.mkdir(parents=True)
        expected = shutil.disk_usage(self.model_dir).free / (1024 ** 2)
        self.assertAlmostEqual(self.manager().free_disk_mb(), expected, delta=50)

    def test_terminates_at_the_root(self):
        # The `target != target.parent` guard. Without it an absolute path
        # whose ancestors are all missing spins forever, hanging startup.
        mm = ModelManager(model_dir=Path('/nonexistent-speakai/x/y/z'),
                          manifest_path=self.manifest_path)
        self.assertGreater(mm.free_disk_mb(), 0.0)


class TestSummary(DiskTestBase):
    def test_summary_has_the_documented_keys(self):
        summary = self.manager().summary()
        for key in ('ram_mb', 'neural_allowed', 'model_dir',
                    'cached_models', 'disk_used_mb', 'disk_free_mb'):
            with self.subTest(key=key):
                self.assertIn(key, summary)

    def test_cached_models_lists_only_what_is_on_disk(self):
        write_file(self.model_dir / 'ar_JO-kareem.onnx', 1024)
        summary = self.manager().summary()
        self.assertEqual(summary['cached_models'], ['piper_ar'])

    def test_cached_models_is_empty_before_any_download(self):
        self.assertEqual(self.manager().summary()['cached_models'], [])

    def test_cached_models_is_sorted(self):
        write_file(self.model_dir / 'ar_JO-kareem.onnx', 1024)
        write_file(self.model_dir / 'mms-rw' / 'model.safetensors', 1024)
        summary = self.manager().summary()
        self.assertEqual(summary['cached_models'], sorted(summary['cached_models']))

    def test_unmanifested_files_are_not_reported_as_cached_models(self):
        # A stray file in the model dir counts towards disk usage but is not a
        # model the manifest knows how to serve.
        # A megabyte rather than a token few bytes: disk_used_mb is rounded to
        # two places, so a 1KB file reports as 0.0 and proves nothing.
        write_file(self.model_dir / 'stray.bin', 1024 ** 2)
        summary = self.manager().summary()
        self.assertEqual(summary['cached_models'], [])
        self.assertGreater(summary['disk_used_mb'], 0.0)

    def test_summary_is_json_serialisable(self):
        # It goes into logs and the about box; a Path in there raises at the
        # point of logging rather than here.
        json.dumps(self.manager().summary())

    def test_model_dir_is_a_string(self):
        self.assertIsInstance(self.manager().summary()['model_dir'], str)

    def test_disk_figures_are_rounded(self):
        write_file(self.model_dir / 'ar_JO-kareem.onnx', 1234567)
        summary = self.manager().summary()
        for key in ('disk_used_mb', 'disk_free_mb'):
            with self.subTest(key=key):
                self.assertEqual(summary[key], round(summary[key], 2))

    def test_summary_reports_the_gate_it_was_constructed_with(self):
        with patch.object(ModelManager, '_detect_ram_mb', staticmethod(lambda: 256)):
            summary = self.manager().summary()
        self.assertEqual(summary['ram_mb'], 256)
        self.assertFalse(summary['neural_allowed'])

    def test_summary_survives_a_missing_manifest(self):
        # Nothing downloadable is a supported state, not a crash.
        mm = ModelManager(model_dir=self.model_dir,
                          manifest_path=self.tmp / 'absent.json')
        self.assertEqual(mm.summary()['cached_models'], [])


if __name__ == '__main__':
    unittest.main()
