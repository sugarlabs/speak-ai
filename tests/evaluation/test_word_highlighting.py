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

"""Word-span arithmetic behind the highlight-as-it-speaks UI.

`_schedule_word_highlights` emits GLOBAL character offsets so the UI can
highlight into the full text entry, while `_find_words` works in coordinates
local to one chunk. The `base_offset + start` that bridges them is the kind of
off-by-one that produces a highlight sliding one word further out of step with
every chunk, which is invisible to the structural checks in verify_all.py
because the audio is perfectly fine.

The multilingual work made this reachable in a way it wasn't before: the
mixed-script path in `_speak_mixed` feeds segments through per run, so
base_offset is now routinely non-zero where single-language English always left
it at 0. Nothing exercised these two methods at all.

GLib.timeout_add is stubbed, so these assert on what *would* be scheduled
rather than waiting on a main loop that isn't running.
"""

import os
import sys
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


def bare_speech():
    """A Speech with nothing started. __new__ for the same reason
    test_ram_gate.py uses it: the real constructor spawns the Kokoro loader."""
    return speech_mod.Speech.__new__(speech_mod.Speech)


def scheduled_words(segment, base_offset, chunk_duration=1.0):
    """Run _schedule_word_highlights and return the (start, end) pairs it
    scheduled, in order, ignoring the delays."""
    s = bare_speech()
    calls = []

    def fake_timeout_add(delay_ms, cb, *args):
        calls.append((delay_ms, cb, args))
        return 1

    with patch.object(speech_mod, 'GLib') as glib:
        glib.timeout_add.side_effect = fake_timeout_add
        s._schedule_word_highlights(
            segment, base_offset,
            anchor=speech_mod.time.monotonic(),
            chunk_start_offset=0.0,
            chunk_duration=chunk_duration)

    return [args for _delay, _cb, args in calls]


class TestFindWords(unittest.TestCase):
    """_find_words returns half-open [start, end) spans into its own string."""

    def test_spans_index_back_to_the_original_words(self):
        text = "the quick brown fox"
        spans = speech_mod.Speech._find_words(text)
        self.assertEqual([text[a:b] for a, b in spans],
                         ["the", "quick", "brown", "fox"])

    def test_runs_of_whitespace_do_not_produce_empty_words(self):
        # An empty span would schedule a zero-width highlight, which reads as
        # the highlight vanishing mid-sentence.
        text = "hello   world\t\tagain\n\nfriend"
        spans = speech_mod.Speech._find_words(text)
        self.assertEqual([text[a:b] for a, b in spans],
                         ["hello", "world", "again", "friend"])
        for start, end in spans:
            self.assertGreater(end, start)

    def test_leading_and_trailing_whitespace_is_not_a_word(self):
        text = "   padded   "
        self.assertEqual(speech_mod.Speech._find_words(text), [(3, 9)])

    def test_empty_and_whitespace_only_segments_yield_nothing(self):
        for text in ("", "   ", "\t\n "):
            with self.subTest(text=repr(text)):
                self.assertEqual(speech_mod.Speech._find_words(text), [])

    def test_devanagari_words_split_on_spaces_not_characters(self):
        # Hindi is whitespace-separated, so the generic splitter is correct
        # here. It is worth pinning: a codepoint-based splitter would highlight
        # one letter at a time and look broken.
        text = "मेरा नाम राहुल है"
        spans = speech_mod.Speech._find_words(text)
        self.assertEqual([text[a:b] for a, b in spans],
                         ["मेरा", "नाम", "राहुल", "है"])

    def test_mixed_script_segment_keeps_both_runs(self):
        text = "मेरा name है Rahul"
        spans = speech_mod.Speech._find_words(text)
        self.assertEqual([text[a:b] for a, b in spans],
                         ["मेरा", "name", "है", "Rahul"])

    def test_punctuation_stays_attached_to_its_word(self):
        # Spans feed a text highlight, not a tokeniser. Splitting "¿Cómo"
        # into two spans would leave the leading punctuation unhighlighted.
        text = "¿Cómo estás, amigo?"
        spans = speech_mod.Speech._find_words(text)
        self.assertEqual([text[a:b] for a, b in spans],
                         ["¿Cómo", "estás,", "amigo?"])


class TestGlobalOffsets(unittest.TestCase):
    """base_offset turns chunk-local spans into entry-global ones."""

    def test_zero_base_offset_matches_local_spans(self):
        self.assertEqual(scheduled_words("one two", base_offset=0),
                         [(0, 3), (4, 7)])

    def test_base_offset_shifts_every_span_by_the_same_amount(self):
        local = scheduled_words("one two", base_offset=0)
        shifted = scheduled_words("one two", base_offset=100)
        self.assertEqual([(a + 100, b + 100) for a, b in local], shifted)

    def test_offsets_slice_the_full_text_back_to_the_spoken_words(self):
        # The end-to-end property the UI actually depends on: for a segment
        # taken out of a larger entry at a known position, every scheduled span
        # must slice that entry back to the word being spoken.
        full = "Hello there. मेरा नाम राहुल है. Goodbye."
        segment = "मेरा नाम राहुल है."
        base = full.index(segment)

        spans = scheduled_words(segment, base_offset=base)
        self.assertEqual([full[a:b] for a, b in spans],
                         ["मेरा", "नाम", "राहुल", "है."])

    def test_consecutive_chunks_do_not_drift(self):
        # Two chunks scheduled with their real offsets must between them cover
        # each word exactly once, which is what fails if base_offset is ever
        # computed from the wrong chunk.
        full = "first chunk here second chunk there"
        a, b = "first chunk here", " second chunk there"
        spans = (scheduled_words(a, base_offset=0)
                 + scheduled_words(b, base_offset=len(a)))
        self.assertEqual([full[s:e] for s, e in spans], full.split())


class TestTimingDistribution(unittest.TestCase):
    """Word timings are proportional to length and bounded by the chunk."""

    def test_no_words_schedules_nothing(self):
        with patch.object(speech_mod, 'GLib') as glib:
            bare_speech()._schedule_word_highlights(
                "   ", 0, anchor=speech_mod.time.monotonic(),
                chunk_start_offset=0.0, chunk_duration=1.0)
            glib.timeout_add.assert_not_called()

    def test_one_emission_per_word(self):
        self.assertEqual(len(scheduled_words("a b c d e", base_offset=0)), 5)

    def test_zero_duration_chunk_still_emits_every_word(self):
        # A backend can return a chunk whose duration rounds to 0. The words
        # should all fire immediately rather than the highlight being skipped.
        spans = scheduled_words("one two three", base_offset=0,
                                chunk_duration=0.0)
        self.assertEqual(len(spans), 3)

    def test_delays_are_non_negative_and_monotonic(self):
        s = bare_speech()
        calls = []
        with patch.object(speech_mod, 'GLib') as glib:
            glib.timeout_add.side_effect = (
                lambda delay, cb, *a: calls.append(delay) or 1)
            s._schedule_word_highlights(
                "alpha beta gamma delta", 0,
                anchor=speech_mod.time.monotonic(),
                chunk_start_offset=0.0, chunk_duration=4.0)

        self.assertTrue(all(d >= 0 for d in calls), calls)
        self.assertEqual(calls, sorted(calls),
                         "words must be scheduled in reading order")

    def test_longer_words_are_given_more_time(self):
        # Proportional-to-length is the documented estimate. A long word
        # getting the same slot as a short one means the highlight runs ahead
        # of the voice on any sentence with uneven word lengths.
        s = bare_speech()
        calls = []
        with patch.object(speech_mod, 'GLib') as glib:
            glib.timeout_add.side_effect = (
                lambda delay, cb, *a: calls.append(delay) or 1)
            s._schedule_word_highlights(
                "a extraordinarily b", 0,
                anchor=speech_mod.time.monotonic(),
                chunk_start_offset=0.0, chunk_duration=10.0)

        # Gap after the 15-char word must exceed the gap after the 1-char one.
        self.assertGreater(calls[2] - calls[1], calls[1] - calls[0])

    def test_words_stay_within_the_chunk_duration(self):
        # The last word may start near the end but must not be scheduled past
        # it, or the highlight outlives the audio.
        s = bare_speech()
        calls = []
        anchor = speech_mod.time.monotonic()
        with patch.object(speech_mod, 'GLib') as glib:
            glib.timeout_add.side_effect = (
                lambda delay, cb, *a: calls.append(delay) or 1)
            s._schedule_word_highlights(
                "one two three four five", 0, anchor=anchor,
                chunk_start_offset=0.0, chunk_duration=2.0)

        self.assertLessEqual(max(calls), 2000)

    def test_chunk_start_offset_pushes_the_whole_chunk_later(self):
        s = bare_speech()
        anchor = speech_mod.time.monotonic()

        def run(offset):
            calls = []
            with patch.object(speech_mod, 'GLib') as glib:
                glib.timeout_add.side_effect = (
                    lambda delay, cb, *a: calls.append(delay) or 1)
                s._schedule_word_highlights(
                    "one two", 0, anchor=anchor,
                    chunk_start_offset=offset, chunk_duration=1.0)
            return calls

        early, late = run(0.0), run(5.0)
        for e, li in zip(early, late):
            self.assertAlmostEqual(li - e, 5000, delta=50)


if __name__ == '__main__':
    unittest.main()
