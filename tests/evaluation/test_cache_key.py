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

"""The voice slot that the cache get and the cache put have to agree on.

`_cache_voice_key` exists because they once didn't: the lookup keyed on the
voice name and the store keyed on the literal 'kokoro', so the cache never hit
and every utterance was re-synthesized. That is a silent bug — the audio is
correct, only slow — which is why it survived until someone measured it.

Centralising the computation fixes the original mismatch but doesn't protect
the property. Nothing tested this method, so a future caller passing the voice
name straight through, or the three call sites drifting apart again, would
restore a 0% hit rate with every test still green.

test_tts_cache.py covers TTSCache itself. These cover the key handed to it, and
the round-trip property that a put is findable by the matching get.
"""

import os
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock

import numpy

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

gi_mock = types.ModuleType('gi')
gi_repo = types.ModuleType('gi.repository')
gi_repo.Gst = MagicMock()
gi_repo.GLib = MagicMock()
gi_repo.GObject = MagicMock()
gi_mock.repository = gi_repo
sys.modules.setdefault('gi', gi_mock)
sys.modules.setdefault('gi.repository', gi_repo)

sugar3_mock = types.ModuleType('sugar3')
sugar3_speech = types.ModuleType('sugar3.speech')
sugar3_speech.GstSpeechPlayer = type(
    'GstSpeechPlayer', (), {'__init__': lambda s: None})
sugar3_mock.speech = sugar3_speech
sys.modules.setdefault('sugar3', sugar3_mock)
sys.modules.setdefault('sugar3.speech', sugar3_speech)

import speech as speech_mod  # noqa: E402
from tts_cache import TTSCache  # noqa: E402


class FakePiperBackend:
    """Stands in for a real backend: only its class name reaches the key."""


class FakeMMSBackend:
    pass


def make_speech():
    s = speech_mod.Speech.__new__(speech_mod.Speech)
    s.current_kokoro_voice = 'af_heart'
    s._lang_voice_map = {
        'ar': 'hf_alpha', 'sw': 'hf_alpha', 'qu': 'hf_alpha',
        'gn': 'hf_alpha', 'rw': 'hf_alpha', 'ay': 'hf_alpha',
    }
    s._kokoro_lang_map = {
        'en-us': ('a', 'af_heart'), 'en-gb': ('a', 'af_heart'),
        'es': ('e', 'ef_dora'), 'fr': ('f', 'ff_siwis'),
        'hi': ('h', 'hf_alpha'), 'pt-br': ('p', 'pf_dora'),
        'zh': ('z', 'zf_xiaoxiao'), 'ja': ('j', 'jf_alpha'),
        'it': ('i', 'if_sara'),
        'ar': ('r', 'hf_alpha'), 'sw': ('w', 'hf_alpha'),
        'qu': ('q', 'hf_alpha'), 'gn': ('g', 'hf_alpha'),
    }
    return s


class TestAltBackendKeys(unittest.TestCase):
    """An alt backend is one-per-language, so its class name identifies it."""

    def test_backend_wins_over_every_other_input(self):
        # The backend produced the audio, so nothing about the Kokoro voice
        # can be allowed to leak into the key.
        s = make_speech()
        backend = FakePiperBackend()
        key = s._cache_voice_key('ar', 'r', backend)
        self.assertEqual(key, 'FakePiperBackend')

        s.current_kokoro_voice = 'ef_dora'
        self.assertEqual(s._cache_voice_key('ar', 'a', backend), key)

    def test_different_backends_get_different_keys(self):
        # Piper and MMS audio for the same text must not collide, or switching
        # engines serves the previous engine's voice from cache.
        s = make_speech()
        self.assertNotEqual(
            s._cache_voice_key('ar', 'r', FakePiperBackend()),
            s._cache_voice_key('ar', 'r', FakeMMSBackend()))


class TestKokoroKeys(unittest.TestCase):
    def test_english_uses_the_currently_selected_voice(self):
        # pl_code 'a' is the one case where the user can change the voice
        # without the language changing, so the key must follow the selection.
        s = make_speech()
        self.assertEqual(s._cache_voice_key('en-us', 'a', None), 'af_heart')
        s.current_kokoro_voice = 'af_aoede'
        self.assertEqual(s._cache_voice_key('en-us', 'a', None), 'af_aoede')

    def test_changing_voice_changes_the_key(self):
        # Otherwise picking a new voice replays the old one from cache, which
        # looks like the voice selector being broken.
        s = make_speech()
        first = s._cache_voice_key('en-us', 'a', None)
        s.current_kokoro_voice = 'af_alloy'
        self.assertNotEqual(first, s._cache_voice_key('en-us', 'a', None))

    def test_non_english_uses_the_mapped_voice_not_the_selection(self):
        # Selecting an English voice must not change Spanish audio, so it must
        # not change the Spanish key either.
        s = make_speech()
        s.current_kokoro_voice = 'af_aoede'
        self.assertEqual(s._cache_voice_key('es', 'e', None), 'ef_dora')
        self.assertEqual(s._cache_voice_key('hi', 'h', None), 'hf_alpha')

    def test_each_kokoro_language_maps_to_its_own_voice(self):
        s = make_speech()
        for lang, (pl_code, voice) in s._kokoro_lang_map.items():
            if pl_code == 'a':
                continue  # covered by the English cases above
            with self.subTest(lang=lang):
                self.assertEqual(s._cache_voice_key(lang, pl_code, None), voice)

    def test_unknown_language_falls_back_without_raising(self):
        # A language detected but absent from both maps must still produce a
        # usable key rather than a KeyError on the synthesis path.
        s = make_speech()
        self.assertEqual(s._cache_voice_key('xx', 'x', None), 'af_heart')

    def test_lang_voice_map_covers_languages_absent_from_the_kokoro_map(self):
        s = make_speech()
        del s._kokoro_lang_map['ar']
        self.assertEqual(s._cache_voice_key('ar', 'r', None), 'hf_alpha')


class TestKeyIsDeterministic(unittest.TestCase):
    def test_repeated_calls_agree(self):
        # The whole point: the get and the put call this separately, so an
        # unstable key is a permanent cache miss.
        s = make_speech()
        for detected, pl_code, backend in [
                ('en-us', 'a', None),
                ('es', 'e', None),
                ('ar', 'r', FakePiperBackend()),
                ('rw', 'w', FakeMMSBackend()),
                ('xx', 'x', None)]:
            with self.subTest(lang=detected):
                keys = {s._cache_voice_key(detected, pl_code, backend)
                        for _ in range(5)}
                self.assertEqual(len(keys), 1)

    def test_key_is_a_non_empty_string(self):
        # It becomes part of a filename hash; None or '' would collapse
        # distinct voices onto one entry.
        s = make_speech()
        for detected, pl_code, backend in [
                ('en-us', 'a', None), ('zh', 'z', None),
                ('ar', 'r', FakePiperBackend()), ('xx', None, None)]:
            with self.subTest(lang=detected):
                key = s._cache_voice_key(detected, pl_code, backend)
                self.assertIsInstance(key, str)
                self.assertTrue(key)


class TestRoundTripThroughTheRealCache(unittest.TestCase):
    """The property that actually matters: a put is found by the matching get.

    These use a real TTSCache on a temp dir, so a key that is unstable or that
    disagrees between the two call sites shows up as a miss here.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='speakai-cachekey-')
        self.cache = TTSCache(cache_dir=self.tmp)
        self.speech = make_speech()
        self.wave = numpy.zeros(2400, dtype=numpy.float32)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def store_then_fetch(self, text, detected, pl_code, backend, speed=1.0):
        """Mirror the real call sites: compute the key once for the put and
        again for the get, exactly as _speak_impl does.

        Returns the waveform only. TTSCache.get answers (waveform, rate) and
        misses as (None, None), so asserting on the tuple itself would pass
        either way -- which is precisely how a cache that never hits stays
        invisible.
        """
        put_key = self.speech._cache_voice_key(detected, pl_code, backend)
        self.cache.put(text, put_key, detected, speed, self.wave, 24000)

        get_key = self.speech._cache_voice_key(detected, pl_code, backend)
        waveform, _rate = self.cache.get(text, get_key, detected, speed)
        return waveform

    def test_kokoro_entry_round_trips(self):
        hit = self.store_then_fetch("hello there", 'en-us', 'a', None)
        self.assertIsNotNone(hit, "cache put was not findable by the matching get")
        self.assertEqual(len(hit), len(self.wave))

    def test_alt_backend_entry_round_trips(self):
        hit = self.store_then_fetch("salam", 'ar', 'r', FakePiperBackend())
        self.assertIsNotNone(hit)

    def test_sample_rate_survives_the_round_trip(self):
        # The rate is stored beside the samples; losing it plays the audio at
        # the wrong pitch rather than not at all.
        key = self.speech._cache_voice_key('ar', 'r', FakeMMSBackend())
        self.cache.put("jambo", key, 'ar', 1.0, self.wave, 16000)
        _waveform, rate = self.cache.get("jambo", key, 'ar', 1.0)
        self.assertEqual(rate, 16000)

    def test_every_kokoro_language_round_trips(self):
        for lang, (pl_code, _voice) in self.speech._kokoro_lang_map.items():
            with self.subTest(lang=lang):
                hit = self.store_then_fetch(f"sample {lang}", lang, pl_code, None)
                self.assertIsNotNone(hit)

    def test_switching_voice_misses_rather_than_serving_the_old_audio(self):
        # A miss here is correct behaviour: the new voice has not been
        # synthesized yet. Serving the previous voice would be the bug.
        self.store_then_fetch("hello there", 'en-us', 'a', None)
        self.speech.current_kokoro_voice = 'af_alloy'
        new_key = self.speech._cache_voice_key('en-us', 'a', None)
        waveform, _rate = self.cache.get("hello there", new_key, 'en-us', 1.0)
        self.assertIsNone(waveform)

    def test_same_text_in_two_languages_does_not_collide(self):
        # "no" is a word in both English and Spanish and must not serve the
        # English audio to a Spanish speaker.
        self.store_then_fetch("no", 'en-us', 'a', None)
        es_key = self.speech._cache_voice_key('es', 'e', None)
        waveform, _rate = self.cache.get("no", es_key, 'es', 1.0)
        self.assertIsNone(waveform)

    def test_backend_audio_does_not_satisfy_a_kokoro_lookup(self):
        # Same language, different engine: Piper Arabic must not be served
        # where the Kokoro cross-lingual fallback was asked for.
        self.store_then_fetch("salam", 'ar', 'r', FakePiperBackend())
        kokoro_key = self.speech._cache_voice_key('ar', 'r', None)
        waveform, _rate = self.cache.get("salam", kokoro_key, 'ar', 1.0)
        self.assertIsNone(waveform)


if __name__ == '__main__':
    unittest.main()
