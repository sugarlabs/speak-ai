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

import os
import sys
import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from tts_cache import TTSCache


class TestTTSCacheInit(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cache = TTSCache(cache_dir=self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_creates_cache_dir(self):
        self.assertTrue(self.tmp.is_dir())

    def test_creates_index_on_first_put(self):
        self.assertFalse((self.tmp / "index.json").is_file())
        self.cache.put("a", "v", "en", 1.0, np.array([0.1], dtype=np.float32))
        self.assertTrue((self.tmp / "index.json").is_file())

    def test_default_cache_dir(self):
        from tts_cache import DEFAULT_CACHE_DIR
        c = TTSCache()
        self.assertEqual(c.cache_dir, DEFAULT_CACHE_DIR)

    def test_custom_max_entries(self):
        c = TTSCache(cache_dir=self.tmp, max_entries=10)
        self.assertEqual(c.max_entries, 10)

    def test_custom_max_disk_bytes(self):
        c = TTSCache(cache_dir=self.tmp, max_disk_bytes=1024)
        self.assertEqual(c.max_disk_bytes, 1024)

    def test_empty_cache(self):
        self.assertEqual(len(self.cache), 0)
        self.assertEqual(self.cache.stats['entries'], 0)


class TestComputeHash(unittest.TestCase):
    def test_same_params_same_hash(self):
        h1 = TTSCache._compute_hash("hello", "af_heart", "en-us", 1.0)
        h2 = TTSCache._compute_hash("hello", "af_heart", "en-us", 1.0)
        self.assertEqual(h1, h2)

    def test_different_text_different_hash(self):
        h1 = TTSCache._compute_hash("hello", "af_heart", "en-us", 1.0)
        h2 = TTSCache._compute_hash("world", "af_heart", "en-us", 1.0)
        self.assertNotEqual(h1, h2)

    def test_different_voice_different_hash(self):
        h1 = TTSCache._compute_hash("hello", "af_heart", "en-us", 1.0)
        h2 = TTSCache._compute_hash("hello", "af_alloy", "en-us", 1.0)
        self.assertNotEqual(h1, h2)

    def test_different_speed_different_hash(self):
        h1 = TTSCache._compute_hash("hello", "af_heart", "en-us", 1.0)
        h2 = TTSCache._compute_hash("hello", "af_heart", "en-us", 1.5)
        self.assertNotEqual(h1, h2)

    def test_hash_is_hex_string(self):
        h = TTSCache._compute_hash("test", "v", "en", 1.0)
        self.assertEqual(len(h), 64)
        int(h, 16)  # should not raise


class TestPutAndGet(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cache = TTSCache(cache_dir=self.tmp)
        self.waveform = np.array([0.1, 0.2, 0.3], dtype=np.float32)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_put_and_get(self):
        self.cache.put("hello", "af_heart", "en-us", 1.0, self.waveform, 24000)
        result, sr = self.cache.get("hello", "af_heart", "en-us", 1.0)
        np.testing.assert_array_equal(result, self.waveform)
        self.assertEqual(sr, 24000)

    def test_get_miss(self):
        result, sr = self.cache.get("missing", "v", "en", 1.0)
        self.assertIsNone(result)
        self.assertIsNone(sr)

    def test_get_updates_atime(self):
        self.cache.put("hello", "v", "en", 1.0, self.waveform)
        before = time.time() - 1
        self.cache.get("hello", "v", "en", 1.0)
        key = TTSCache._compute_hash("hello", "v", "en", 1.0)
        self.assertGreater(self.cache._index[key]['atime'], before)

    def test_overwrite_same_key(self):
        wave2 = np.array([0.4, 0.5], dtype=np.float32)
        self.cache.put("hello", "v", "en", 1.0, self.waveform)
        self.cache.put("hello", "v", "en", 1.0, wave2)
        result, _ = self.cache.get("hello", "v", "en", 1.0)
        np.testing.assert_array_equal(result, wave2)

    def test_npy_file_exists(self):
        self.cache.put("hello", "v", "en", 1.0, self.waveform)
        key = TTSCache._compute_hash("hello", "v", "en", 1.0)
        path = self.tmp / self.cache._index[key]['path']
        self.assertTrue(path.is_file())

    def test_put_invalid_array_skipped(self):
        self.cache.put("hello", "v", "en", 1.0, None)
        self.assertEqual(len(self.cache), 0)

    def test_put_empty_array_skipped(self):
        self.cache.put("hello", "v", "en", 1.0, np.array([], dtype=np.float32))
        self.assertEqual(len(self.cache), 0)

    def test_put_non_ndarray_skipped(self):
        self.cache.put("hello", "v", "en", 1.0, [0.1, 0.2])
        self.assertEqual(len(self.cache), 0)


class TestEviction(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cache = TTSCache(cache_dir=self.tmp, max_entries=3)
        self.wave = np.array([0.1], dtype=np.float32)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_evicts_oldest_by_count(self):
        for i in range(5):
            self.cache.put(f"t{i}", "v", "en", 1.0, self.wave)
        self.assertEqual(len(self.cache), 3)
        self.assertIsNone(self.cache.get("t0", "v", "en", 1.0)[0])
        self.assertIsNone(self.cache.get("t1", "v", "en", 1.0)[0])

    def test_evicts_oldest_by_disk_size(self):
        small_cache = TTSCache(cache_dir=self.tmp, max_disk_bytes=500)
        for i in range(5):
            small_cache.put(f"t{i}", "v", "en", 1.0, self.wave)
        self.assertLessEqual(len(small_cache), 5)

    def test_recent_access_survives(self):
        for i in range(3):
            self.cache.put(f"t{i}", "v", "en", 1.0, self.wave)
        self.cache.get("t0", "v", "en", 1.0)
        self.cache.put("t3", "v", "en", 1.0, self.wave)
        self.assertIsNotNone(self.cache.get("t0", "v", "en", 1.0)[0])


class TestClear(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cache = TTSCache(cache_dir=self.tmp)
        self.wave = np.array([0.1], dtype=np.float32)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_clear_removes_all(self):
        self.cache.put("a", "v", "en", 1.0, self.wave)
        self.cache.put("b", "v", "en", 1.0, self.wave)
        self.cache.clear()
        self.assertEqual(len(self.cache), 0)

    def test_clear_removes_npy_files(self):
        self.cache.put("a", "v", "en", 1.0, self.wave)
        npy_files = list(self.tmp.glob("*.npy"))
        self.cache.clear()
        for f in npy_files:
            self.assertFalse(f.is_file())


class TestIndexPersistence(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.wave = np.array([0.1], dtype=np.float32)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_index_survives_restart(self):
        c1 = TTSCache(cache_dir=self.tmp)
        c1.put("hello", "v", "en", 1.0, self.wave)
        del c1

        c2 = TTSCache(cache_dir=self.tmp)
        result, sr = c2.get("hello", "v", "en", 1.0)
        np.testing.assert_array_equal(result, self.wave)

    def test_corrupted_index_resets(self):
        (self.tmp / "index.json").write_text("NOT JSON", encoding='utf-8')
        c = TTSCache(cache_dir=self.tmp)
        self.assertEqual(len(c), 0)

    def test_missing_entry_keys_skipped(self):
        idx = {"bad": {"path": "x.npy"}}
        (self.tmp / "index.json").write_text(json.dumps(idx), encoding='utf-8')
        c = TTSCache(cache_dir=self.tmp)
        self.assertEqual(len(c), 0)


class TestStats(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cache = TTSCache(cache_dir=self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stats_empty(self):
        s = self.cache.stats
        self.assertEqual(s['entries'], 0)
        self.assertEqual(s['disk_bytes'], 0)
        self.assertEqual(s['disk_mb'], 0)

    def test_stats_after_put(self):
        wave = np.array([0.1, 0.2, 0.3], dtype=np.float32)
        self.cache.put("a", "v", "en", 1.0, wave)
        s = self.cache.stats
        self.assertEqual(s['entries'], 1)
        self.assertGreater(s['disk_bytes'], 0)


class TestRepr(unittest.TestCase):
    def test_repr(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            c = TTSCache(cache_dir=tmp)
            r = repr(c)
            self.assertIn("TTSCache", r)
            self.assertIn("entries=0", r)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestFlush(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cache = TTSCache(cache_dir=self.tmp)
        self.wave = np.array([0.1], dtype=np.float32)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_flush_writes_index(self):
        self.cache.put("a", "v", "en", 1.0, self.wave)
        self.cache.flush()
        with open(self.tmp / "index.json", 'r') as f:
            data = json.load(f)
        self.assertEqual(len(data), 1)


if __name__ == '__main__':
    unittest.main()
