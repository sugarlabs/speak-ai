# Copyright (C) 2025, Dashpreet Singh <dashpreetsinghhanda@gmail.com>

"""phrase_cache.py — Thread-safe LRU cache for synthesised audio chunks.

Speak-AI is used heavily in language-learning sessions where the same
phrases ("hello", "repeat after me", numbers, greetings) appear over and
over. Re-synthesising identical text on every call wastes CPU and adds
latency. This module caches raw numpy audio arrays keyed by
(text, voice, lang_code) so repeated phrases are served instantly.

Usage::

    cache = PhraseCache(maxsize=128)
    audio = cache.get("hello", voice="af_heart", lang_code="a")
    if audio is None:
        audio = <synthesise>
        cache.put("hello", voice="af_heart", lang_code="a", audio=audio)
"""

import hashlib
import logging
import threading
from collections import OrderedDict

import numpy

logger = logging.getLogger('speak')

# Default maximum number of entries kept in memory.
# Each entry is a float32 numpy array (~24000 samples/sec * ~3 sec ≈ 288 KB).
# 128 entries ≈ up to ~36 MB worst case, typically much less.
DEFAULT_CACHE_SIZE = 128


class PhraseCache:
    """Thread-safe LRU cache mapping (text, voice, lang_code) → numpy audio array.

    Uses an OrderedDict to maintain LRU order without any extra dependencies.
    All public methods are safe to call from multiple threads.
    """

    def __init__(self, maxsize=DEFAULT_CACHE_SIZE):
        if maxsize < 1:
            raise ValueError('maxsize must be >= 1')
        self._maxsize = maxsize
        self._store = OrderedDict()  
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    # Key construction

    @staticmethod
    def _make_key(text, voice, lang_code):
        """Produce a short, collision-resistant cache key."""
        raw = f'{lang_code}\x00{voice}\x00{text}'
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()

    # Public API

    def get(self, text, voice, lang_code):
        """Return the cached numpy audio array, or None on a miss.

        On a hit the entry is promoted to most-recently-used.
        """
        key = self._make_key(text, voice, lang_code)
        with self._lock:
            if key not in self._store:
                self._misses += 1
                return None
            # Promote to MRU position
            self._store.move_to_end(key)
            self._hits += 1
            return self._store[key]

    def put(self, text, voice, lang_code, audio):
        """Store *audio* (numpy array) for the given key.

        Evicts the least-recently-used entry when the cache is full.
        Overwrites silently if the key already exists.
        """
        if not isinstance(audio, numpy.ndarray):
            raise TypeError('audio must be a numpy.ndarray')
        key = self._make_key(text, voice, lang_code)
        with self._lock:
            if key in self._store:
                # Update in place and re-promote
                self._store[key] = audio
                self._store.move_to_end(key)
                return
            self._store[key] = audio
            self._store.move_to_end(key)
            if len(self._store) > self._maxsize:
                evicted_key, _ = self._store.popitem(last=False)
                logger.debug('PhraseCache: evicted entry %s…', evicted_key[:8])

    def clear(self):
        """Remove all entries and reset statistics."""
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0
        logger.debug('PhraseCache: cleared')

    # Introspection

    def __len__(self):
        with self._lock:
            return len(self._store)

    @property
    def maxsize(self):
        return self._maxsize

    @property
    def hits(self):
        with self._lock:
            return self._hits

    @property
    def misses(self):
        with self._lock:
            return self._misses

    @property
    def hit_rate(self):
        """Return hit rate as a float in [0, 1], or 0.0 if no lookups yet."""
        with self._lock:
            total = self._hits + self._misses
            return self._hits / total if total > 0 else 0.0

    def stats_string(self):
        """Human-readable cache statistics for logging."""
        with self._lock:
            total = self._hits + self._misses
            rate = f'{self.hit_rate:.0%}' if total else 'n/a'
            return (
                f'PhraseCache: {len(self._store)}/{self._maxsize} entries, '
                f'{self._hits} hits, {self._misses} misses, hit rate {rate}'
            )
