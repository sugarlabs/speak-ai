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

"""The per-language backend circuit breaker.

`_backend_failures` is what stops a broken backend from being retried on every
utterance. It matters most for exactly the failures this branch introduced:
Piper and MMS load from disk or the hub, so a missing model, a truncated
download or an OOM kill fails at synthesis time rather than at import, and
without the breaker every single Speak press pays that cost again.

The three methods that maintain it (`_get_backend_for_lang`,
`_record_backend_failure`, `_record_backend_success`) had no tests. The
failure-count branch inside `_get_backend_for_lang` was reachable only through
a real download failure, so nothing verified that the count is what opens the
breaker, that a success closes it again, or that a failure drops the cached
object instead of handing the same broken backend back.

These drive the real methods, so deleting the accounting fails here.
"""

import os
import sys
import threading
import types
import unittest
from unittest.mock import MagicMock, patch

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


def make_speech():
    """Only the attributes the breaker touches. See test_ram_gate.make_speech
    for why this is __new__ and not the real constructor."""
    s = speech_mod.Speech.__new__(speech_mod.Speech)
    s._neural_allowed = True
    s._model_manager = None
    s._backend_lock = threading.Lock()
    s._backend_failures = {}
    s._alt_backend_cache = {}
    s.kokoro_pipeline = None
    s._tts_cache = None
    s._current_backend_type = 'kokoro'
    s._current_sample_rate = 24000
    s.current_kokoro_voice = 'af_heart'
    return s


class TestBreakerOpensOnRepeatedFailure(unittest.TestCase):
    def test_backend_is_retried_up_to_the_limit(self):
        # Below the threshold the backend must still be attempted; opening the
        # breaker on the first blip would drop a language to espeak for the
        # rest of the session over one transient download error.
        s = make_speech()
        sentinel = object()
        for failures in range(speech_mod._MAX_FAILURES):
            with self.subTest(failures=failures):
                s._backend_failures['ar'] = failures
                s._alt_backend_cache.clear()
                with patch.object(speech_mod, 'ALT_BACKENDS_AVAILABLE', True), \
                        patch.object(speech_mod, 'get_tts_backend',
                                     return_value=sentinel) as get_backend:
                    self.assertIs(s._get_backend_for_lang('ar'), sentinel)
                    get_backend.assert_called_once()

    def test_breaker_opens_exactly_at_the_limit(self):
        s = make_speech()
        s._backend_failures['ar'] = speech_mod._MAX_FAILURES
        with patch.object(speech_mod, 'ALT_BACKENDS_AVAILABLE', True), \
                patch.object(speech_mod, 'get_tts_backend') as get_backend:
            self.assertIsNone(s._get_backend_for_lang('ar'))
            # Must short-circuit before construction, not discard the result:
            # building the backend is the expensive part being avoided.
            get_backend.assert_not_called()

    def test_breaker_stays_open_past_the_limit(self):
        s = make_speech()
        s._backend_failures['sw'] = speech_mod._MAX_FAILURES + 10
        with patch.object(speech_mod, 'ALT_BACKENDS_AVAILABLE', True), \
                patch.object(speech_mod, 'get_tts_backend') as get_backend:
            self.assertIsNone(s._get_backend_for_lang('sw'))
            get_backend.assert_not_called()

    def test_construction_failure_counts_towards_the_limit(self):
        # get_tts_backend raising is the path a missing .onnx.json takes.
        s = make_speech()
        with patch.object(speech_mod, 'ALT_BACKENDS_AVAILABLE', True), \
                patch.object(speech_mod, 'get_tts_backend',
                             side_effect=RuntimeError("no model")):
            for _ in range(speech_mod._MAX_FAILURES):
                self.assertIsNone(s._get_backend_for_lang('rw'))

        self.assertEqual(s._backend_failures['rw'], speech_mod._MAX_FAILURES)

        # ...and the breaker is now open, so it stops calling through.
        with patch.object(speech_mod, 'ALT_BACKENDS_AVAILABLE', True), \
                patch.object(speech_mod, 'get_tts_backend') as get_backend:
            self.assertIsNone(s._get_backend_for_lang('rw'))
            get_backend.assert_not_called()

    def test_a_backend_that_declines_is_not_a_failure(self):
        # get_tts_backend returning None means "no backend for this language",
        # which is a permanent fact about the language table, not an error.
        # Counting it would be harmless but misleading in get_status().
        s = make_speech()
        with patch.object(speech_mod, 'ALT_BACKENDS_AVAILABLE', True), \
                patch.object(speech_mod, 'get_tts_backend', return_value=None):
            self.assertIsNone(s._get_backend_for_lang('en-us'))
        self.assertNotIn('en-us', s._backend_failures)

    def test_failures_are_tracked_per_language(self):
        # Arabic failing must not push Swahili towards its own limit; they are
        # different models and one being absent says nothing about the other.
        s = make_speech()
        for _ in range(speech_mod._MAX_FAILURES):
            s._record_backend_failure('ar')

        sentinel = object()
        with patch.object(speech_mod, 'ALT_BACKENDS_AVAILABLE', True), \
                patch.object(speech_mod, 'get_tts_backend',
                             return_value=sentinel):
            self.assertIsNone(s._get_backend_for_lang('ar'))
            self.assertIs(s._get_backend_for_lang('sw'), sentinel)


class TestRecordFailure(unittest.TestCase):
    def test_failure_increments_from_absent(self):
        s = make_speech()
        s._record_backend_failure('gn')
        self.assertEqual(s._backend_failures['gn'], 1)

    def test_failures_accumulate(self):
        s = make_speech()
        for expected in range(1, 6):
            s._record_backend_failure('gn')
            self.assertEqual(s._backend_failures['gn'], expected)

    def test_failure_evicts_the_cached_backend(self):
        # The bug this prevents: a backend that has started failing at
        # synthesis time stays in _alt_backend_cache, so _get_backend_for_lang
        # keeps returning that same broken object and the breaker never sees a
        # construction attempt to count.
        s = make_speech()
        broken = object()
        s._alt_backend_cache['ar'] = broken

        s._record_backend_failure('ar')

        self.assertNotIn('ar', s._alt_backend_cache)
        fresh = object()
        with patch.object(speech_mod, 'ALT_BACKENDS_AVAILABLE', True), \
                patch.object(speech_mod, 'get_tts_backend',
                             return_value=fresh):
            self.assertIs(s._get_backend_for_lang('ar'), fresh)

    def test_evicting_an_uncached_language_is_not_an_error(self):
        s = make_speech()
        s._record_backend_failure('ay')  # nothing cached
        self.assertEqual(s._backend_failures['ay'], 1)


class TestRecordSuccess(unittest.TestCase):
    def test_success_clears_the_failure_count(self):
        s = make_speech()
        s._backend_failures['ar'] = 2
        s._record_backend_success('ar')
        self.assertNotIn('ar', s._backend_failures)

    def test_success_closes_a_breaker_that_was_about_to_open(self):
        # Two transient failures then a success must fully reset, otherwise
        # three transient failures spread across a whole session are enough to
        # disable a language permanently.
        s = make_speech()
        s._record_backend_failure('sw')
        s._record_backend_failure('sw')
        s._record_backend_success('sw')

        s._record_backend_failure('sw')
        self.assertEqual(s._backend_failures['sw'], 1)

        sentinel = object()
        with patch.object(speech_mod, 'ALT_BACKENDS_AVAILABLE', True), \
                patch.object(speech_mod, 'get_tts_backend',
                             return_value=sentinel):
            self.assertIs(s._get_backend_for_lang('sw'), sentinel)

    def test_success_for_a_clean_language_is_a_no_op(self):
        s = make_speech()
        s._record_backend_success('qu')
        self.assertEqual(s._backend_failures, {})


class TestBackendCaching(unittest.TestCase):
    def test_backend_is_built_once_and_reused(self):
        # Rebuilding per utterance would reload the model from disk each time.
        s = make_speech()
        sentinel = object()
        with patch.object(speech_mod, 'ALT_BACKENDS_AVAILABLE', True), \
                patch.object(speech_mod, 'get_tts_backend',
                             return_value=sentinel) as get_backend:
            first = s._get_backend_for_lang('ar')
            second = s._get_backend_for_lang('ar')

        self.assertIs(first, second)
        get_backend.assert_called_once()

    def test_nothing_is_cached_when_alt_backends_are_missing(self):
        s = make_speech()
        with patch.object(speech_mod, 'ALT_BACKENDS_AVAILABLE', False):
            self.assertIsNone(s._get_backend_for_lang('ar'))
        self.assertEqual(s._alt_backend_cache, {})


class TestStatusReportsBreakerState(unittest.TestCase):
    def test_status_lists_loaded_and_failed_backends(self):
        # get_status feeds the about box; the two dicts it exposes are the only
        # way to see from outside that a language has been disabled.
        s = make_speech()
        s._alt_backend_cache['ar'] = object()
        s._record_backend_failure('sw')

        status = s.get_status()
        self.assertIn('ar', status['loaded_backends'])
        self.assertEqual(status['failed_backends']['sw'], 1)

    def test_status_failure_dict_is_a_copy(self):
        # Handing out the live dict would let a caller mutate the breaker.
        s = make_speech()
        s._record_backend_failure('ar')
        s.get_status()['failed_backends']['ar'] = 99
        self.assertEqual(s._backend_failures['ar'], 1)


class TestThreadSafety(unittest.TestCase):
    def test_concurrent_failures_are_all_counted(self):
        # _backend_lock exists because the preload worker and the speak thread
        # both touch this. A lost update here would under-count failures and
        # leave the breaker closed on a backend that is reliably broken.
        s = make_speech()
        per_thread = 50
        threads = [
            threading.Thread(
                target=lambda: [s._record_backend_failure('ar')
                                for _ in range(per_thread)])
            for _ in range(8)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(s._backend_failures['ar'], per_thread * len(threads))


if __name__ == '__main__':
    unittest.main()
