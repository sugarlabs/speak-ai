# Copyright (C) 2025, Dashpreet Singh <dashpreetsinghhanda@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# tests/test_phrase_cache.py — Unit tests for : PhraseCache
#
# Only depends on phrase_cache.py and numpy.
# No audio hardware, Sugar environment, or Kokoro model files required.
#
# Run from repo root:
#   python -m pytest tests/test_phrase_cache.py -v

import os
import sys
import threading
import unittest

import numpy

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from phrase_cache import PhraseCache, DEFAULT_CACHE_SIZE


def _make_audio(length=100):
    """Return a small float32 numpy array to use as fake audio."""
    return numpy.zeros(length, dtype=numpy.float32)


class TestPhraseCacheBasic(unittest.TestCase):

    def setUp(self):
        self.cache = PhraseCache(maxsize=4)

    # ─ get / put ─

    def test_miss_returns_none(self):
        self.assertIsNone(self.cache.get('hello', voice='af_heart', lang_code='a'))

    def test_put_then_get(self):
        audio = _make_audio()
        self.cache.put('hello', voice='af_heart', lang_code='a', audio=audio)
        result = self.cache.get('hello', voice='af_heart', lang_code='a')
        self.assertIsNotNone(result)
        numpy.testing.assert_array_equal(result, audio)

    def test_different_text_is_miss(self):
        self.cache.put('hello', voice='af_heart', lang_code='a', audio=_make_audio())
        self.assertIsNone(self.cache.get('world', voice='af_heart', lang_code='a'))

    def test_different_voice_is_miss(self):
        self.cache.put('hello', voice='af_heart', lang_code='a', audio=_make_audio())
        self.assertIsNone(self.cache.get('hello', voice='af_sky', lang_code='a'))

    def test_different_lang_code_is_miss(self):
        self.cache.put('hola', voice='ef_dora', lang_code='e', audio=_make_audio())
        self.assertIsNone(self.cache.get('hola', voice='ef_dora', lang_code='a'))

    def test_same_text_different_lang_no_collision(self):
        audio_es = _make_audio(50)
        audio_en = _make_audio(80)
        self.cache.put('hola', voice='ef_dora', lang_code='e', audio=audio_es)
        self.cache.put('hola', voice='af_heart', lang_code='a', audio=audio_en)
        numpy.testing.assert_array_equal(
            self.cache.get('hola', voice='ef_dora', lang_code='e'), audio_es)
        numpy.testing.assert_array_equal(
            self.cache.get('hola', voice='af_heart', lang_code='a'), audio_en)

    # ─ overwrite ─

    def test_put_overwrites_existing(self):
        old = _make_audio(10)
        new = _make_audio(20)
        self.cache.put('hi', voice='af_heart', lang_code='a', audio=old)
        self.cache.put('hi', voice='af_heart', lang_code='a', audio=new)
        result = self.cache.get('hi', voice='af_heart', lang_code='a')
        numpy.testing.assert_array_equal(result, new)

    def test_overwrite_does_not_grow_len(self):
        self.cache.put('hi', voice='af_heart', lang_code='a', audio=_make_audio())
        self.cache.put('hi', voice='af_heart', lang_code='a', audio=_make_audio())
        self.assertEqual(len(self.cache), 1)

    # ─ type check ─

    def test_put_non_numpy_raises(self):
        with self.assertRaises(TypeError):
            self.cache.put('hi', voice='af_heart', lang_code='a', audio=[1, 2, 3])


class TestPhraseCacheLRU(unittest.TestCase):

    def test_evicts_lru_when_full(self):
        cache = PhraseCache(maxsize=3)
        cache.put('p0', voice='v', lang_code='a', audio=_make_audio())
        cache.put('p1', voice='v', lang_code='a', audio=_make_audio())
        cache.put('p2', voice='v', lang_code='a', audio=_make_audio())
        # Adding p3 should evict p0 (least recently used)
        cache.put('p3', voice='v', lang_code='a', audio=_make_audio())
        self.assertIsNone(cache.get('p0', voice='v', lang_code='a'))
        self.assertIsNotNone(cache.get('p3', voice='v', lang_code='a'))

    def test_get_promotes_to_mru(self):
        cache = PhraseCache(maxsize=3)
        cache.put('p0', voice='v', lang_code='a', audio=_make_audio())
        cache.put('p1', voice='v', lang_code='a', audio=_make_audio())
        cache.put('p2', voice='v', lang_code='a', audio=_make_audio())
        # Access p0 — it should be promoted, so p1 gets evicted next
        cache.get('p0', voice='v', lang_code='a')
        cache.put('p3', voice='v', lang_code='a', audio=_make_audio())
        self.assertIsNotNone(cache.get('p0', voice='v', lang_code='a'), 'p0 should survive')
        self.assertIsNone(cache.get('p1', voice='v', lang_code='a'), 'p1 should be evicted')

    def test_never_exceeds_maxsize(self):
        maxsize = 5
        cache = PhraseCache(maxsize=maxsize)
        for i in range(30):
            cache.put(f'phrase{i}', voice='v', lang_code='a', audio=_make_audio())
        self.assertLessEqual(len(cache), maxsize)

    def test_maxsize_one(self):
        cache = PhraseCache(maxsize=1)
        cache.put('a', voice='v', lang_code='a', audio=_make_audio())
        cache.put('b', voice='v', lang_code='a', audio=_make_audio())
        self.assertIsNone(cache.get('a', voice='v', lang_code='a'))
        self.assertIsNotNone(cache.get('b', voice='v', lang_code='a'))


class TestPhraseCacheStats(unittest.TestCase):

    def setUp(self):
        self.cache = PhraseCache(maxsize=10)

    def test_initial_hit_rate_zero(self):
        self.assertEqual(self.cache.hit_rate, 0.0)

    def test_hits_and_misses_counted(self):
        self.cache.put('hi', voice='v', lang_code='a', audio=_make_audio())
        self.cache.get('hi', voice='v', lang_code='a')   # hit
        self.cache.get('bye', voice='v', lang_code='a')  # miss
        self.assertEqual(self.cache.hits, 1)
        self.assertEqual(self.cache.misses, 1)

    def test_hit_rate_calculation(self):
        self.cache.put('hi', voice='v', lang_code='a', audio=_make_audio())
        self.cache.get('hi', voice='v', lang_code='a')   # hit
        self.cache.get('hi', voice='v', lang_code='a')   # hit
        self.cache.get('bye', voice='v', lang_code='a')  # miss
        self.assertAlmostEqual(self.cache.hit_rate, 2 / 3)

    def test_stats_string_contains_key_info(self):
        s = self.cache.stats_string()
        self.assertIn('PhraseCache', s)
        self.assertIn('hits', s)
        self.assertIn('misses', s)

    def test_clear_resets_stats(self):
        self.cache.put('hi', voice='v', lang_code='a', audio=_make_audio())
        self.cache.get('hi', voice='v', lang_code='a')
        self.cache.clear()
        self.assertEqual(self.cache.hits, 0)
        self.assertEqual(self.cache.misses, 0)
        self.assertEqual(len(self.cache), 0)


class TestPhraseCacheLen(unittest.TestCase):

    def test_empty_len_zero(self):
        cache = PhraseCache()
        self.assertEqual(len(cache), 0)

    def test_len_increments_on_put(self):
        cache = PhraseCache()
        cache.put('a', voice='v', lang_code='a', audio=_make_audio())
        self.assertEqual(len(cache), 1)
        cache.put('b', voice='v', lang_code='a', audio=_make_audio())
        self.assertEqual(len(cache), 2)

    def test_maxsize_property(self):
        cache = PhraseCache(maxsize=42)
        self.assertEqual(cache.maxsize, 42)

    def test_invalid_maxsize_raises(self):
        with self.assertRaises(ValueError):
            PhraseCache(maxsize=0)


class TestPhraseCacheThreadSafety(unittest.TestCase):

    def test_concurrent_puts_and_gets(self):
        cache = PhraseCache(maxsize=64)
        errors = []

        def worker(i):
            try:
                text = f'phrase{i % 10}'  # intentional overlap to stress LRU
                cache.put(text, voice='v', lang_code='a', audio=_make_audio())
                cache.get(text, voice='v', lang_code='a')
            except Exception as e:
                errors.append(repr(e))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(60)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f'Thread errors: {errors}')

    def test_concurrent_clear_and_put(self):
        cache = PhraseCache(maxsize=16)
        errors = []

        def putter():
            for i in range(20):
                try:
                    cache.put(f'p{i}', voice='v', lang_code='a', audio=_make_audio())
                except Exception as e:
                    errors.append(repr(e))

        def clearer():
            for _ in range(5):
                try:
                    cache.clear()
                except Exception as e:
                    errors.append(repr(e))

        threads = [threading.Thread(target=putter) for _ in range(3)]
        threads += [threading.Thread(target=clearer) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f'Thread errors: {errors}')


class TestDefaultCacheSize(unittest.TestCase):

    def test_default_maxsize_matches_constant(self):
        cache = PhraseCache()
        self.assertEqual(cache.maxsize, DEFAULT_CACHE_SIZE)

    def test_default_never_exceeds_maxsize(self):
        cache = PhraseCache()
        for i in range(DEFAULT_CACHE_SIZE + 20):
            cache.put(f'phrase{i}', voice='v', lang_code='a', audio=_make_audio())
        self.assertLessEqual(len(cache), DEFAULT_CACHE_SIZE)


if __name__ == '__main__':
    unittest.main()
