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

"""Mixed-script segmentation.

The case that matters is "मेरा name है Rahul": ordinary Hindi-English
classroom writing that a single G2P engine cannot pronounce. The tests below
pin down both halves of the contract — that mixed text splits on the right
boundaries, and just as importantly that single-language text does *not*
split, because a false positive here would chop a Spanish sentence into
fragments and speak it with gaps.
"""

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from speech_utils.codeswitch import (  # noqa: E402
    BOUNDARY_SILENCE_MS, is_mixed_script, script_of_word, segment_by_script,
)


class TestScriptOfWord(unittest.TestCase):

    def test_identifies_each_script(self):
        cases = [
            ('name', 'LATIN'),
            ('मेरा', 'DEVANAGARI'),
            ('طالب', 'ARABIC'),
            ('中文', 'HAN'),
            ('Rahul', 'LATIN'),
            ('está', 'LATIN'),
        ]
        for word, script in cases:
            with self.subTest(word=word):
                self.assertEqual(script_of_word(word), script)

    def test_punctuation_and_digits_have_no_script(self):
        for word in ('42', '...', '?!', '—'):
            with self.subTest(word=word):
                self.assertIsNone(script_of_word(word))

    def test_majority_vote_survives_attached_punctuation(self):
        self.assertEqual(script_of_word('Rahul,'), 'LATIN')
        self.assertEqual(script_of_word('"मेरा"'), 'DEVANAGARI')

    def test_majority_wins_over_first_character(self):
        # One leading Latin character must not carry a Devanagari word.
        self.assertEqual(script_of_word('xमेरा'), 'DEVANAGARI')


class TestSegmentation(unittest.TestCase):

    def test_the_motivating_case(self):
        self.assertEqual(
            segment_by_script('मेरा name है Rahul', 'hi'),
            [('hi', 'मेरा'), ('en-us', 'name'),
             ('hi', 'है'), ('en-us', 'Rahul')])

    def test_consecutive_same_script_words_merge(self):
        self.assertEqual(
            segment_by_script('मेरा नाम Rahul Kumar है', 'hi'),
            [('hi', 'मेरा नाम'), ('en-us', 'Rahul Kumar'), ('hi', 'है')])

    def test_monolingual_text_is_one_segment(self):
        for text, lang in [('Ella ha comido pizza', 'es'),
                           ('hello world', 'en-us'),
                           ('मेरा नाम राहुल है', 'hi'),
                           ('الطالب في الفصل', 'ar')]:
            with self.subTest(text=text):
                segments = segment_by_script(text, lang)
                self.assertEqual(len(segments), 1)
                self.assertFalse(is_mixed_script(text, lang))

    def test_latin_resolves_to_the_base_language(self):
        """A Latin run in Spanish text is Spanish, not English."""
        self.assertEqual(segment_by_script('Ella ha comido', 'es'),
                         [('es', 'Ella ha comido')])
        self.assertEqual(segment_by_script('jambo rafiki', 'sw'),
                         [('sw', 'jambo rafiki')])

    def test_latin_falls_back_to_english_from_a_non_latin_base(self):
        segments = segment_by_script('मेरा name', 'hi')
        self.assertEqual(segments[1][0], 'en-us')

    def test_digits_attach_to_the_run_in_progress(self):
        """"है 42 rupees" must not become three segments."""
        self.assertEqual(
            segment_by_script('है 42 rupees', 'hi'),
            [('hi', 'है 42'), ('en-us', 'rupees')])

    def test_leading_punctuation_starts_a_segment_in_the_base_language(self):
        segments = segment_by_script('... hello', 'en-us')
        self.assertEqual(segments[0][0], 'en-us')

    def test_word_order_is_preserved(self):
        text = 'मेरा name है Rahul और school'
        spoken = ' '.join(seg for _lang, seg in segment_by_script(text, 'hi'))
        self.assertEqual(spoken.split(), text.split())

    def test_empty_input(self):
        for value in ('', '   ', None):
            with self.subTest(value=repr(value)):
                self.assertEqual(segment_by_script(value, 'hi'), [])

    def test_arabic_latin_mix(self):
        self.assertEqual(
            segment_by_script('الطالب Rahul في الفصل', 'ar'),
            [('ar', 'الطالب'), ('en-us', 'Rahul'), ('ar', 'في الفصل')])

    def test_known_limitation_english_in_devanagari(self):
        """Recorded, not fixed: टेबल routes to Hindi.

        Detecting Devanagari-transliterated English would need a lexicon this
        activity cannot ship, and espeak-ng's Hindi voice reads common loan
        words acceptably. The test exists so the behaviour is a decision
        rather than a surprise.
        """
        self.assertEqual(segment_by_script('मेरा टेबल', 'hi'),
                         [('hi', 'मेरा टेबल')])


class TestBoundarySilence(unittest.TestCase):

    def test_is_a_sane_gap(self):
        # Long enough to separate two voices, short enough not to read as a
        # pause in the sentence.
        self.assertGreaterEqual(BOUNDARY_SILENCE_MS, 20)
        self.assertLessEqual(BOUNDARY_SILENCE_MS, 200)


# ---------------------------------------------------------------------------
# Wiring: that speech.py actually uses the segmentation above.
#
# Segmenting correctly and then never calling it is the exact failure this
# branch already had once with alt_tts_backends.py, so these drive the real
# Speech methods. gi and sugar3 are stubbed as in test_ram_gate.py.
# ---------------------------------------------------------------------------

import threading  # noqa: E402
import types  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402

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

import numpy  # noqa: E402
import speech as speech_mod  # noqa: E402


class FakeVoice:
    name = 'en-us'


class FakeStatus:
    pitch = 100
    rate = 100
    voice = FakeVoice()


def make_speech():
    s = speech_mod.Speech.__new__(speech_mod.Speech)
    s._neural_allowed = True
    s._model_manager = None
    s._backend_lock = threading.Lock()
    s._speak_lock = threading.Lock()
    s._backend_failures = {}
    s._alt_backend_cache = {}
    s._tts_cache = None
    s._language_hint = None
    s._current_backend_type = 'kokoro'
    s._current_sample_rate = 24000
    s.current_kokoro_voice = 'af_heart'
    s.kokoro_pipeline = None
    s._kokoro_failed = True          # keep Kokoro out of these tests
    s._kokoro_model = None
    s._kokoro_ready = threading.Event()
    s._kokoro_ready.set()
    s._kokoro_lang_map = {'en-us': ('a', 'af_heart'), 'hi': ('h', 'hf_alpha')}
    s._lang_voice_map = {}
    s.pipeline = MagicMock()
    s._build_pipeline = MagicMock()
    s.restart_sound_device = MagicMock()
    s._push_waveform_to_appsrc = MagicMock()
    s._stream_kokoro_audio = MagicMock(return_value=[])
    return s


class TestSpeakMixed(unittest.TestCase):

    def test_joins_segments_with_silence_at_the_target_rate(self):
        s = make_speech()
        # 16 kHz MMS-style and 24 kHz Kokoro-style, deliberately different.
        s._synthesize_segment = MagicMock(side_effect=[
            (numpy.ones(16000, dtype=numpy.float32), 16000),
            (numpy.ones(24000, dtype=numpy.float32), 24000),
        ])

        self.assertTrue(
            s._speak_mixed('मेरा name', [('hi', 'मेरा'), ('en-us', 'name')]))

        s._build_pipeline.assert_called_once_with('audio_src', 24000)
        pushed, sr = s._push_waveform_to_appsrc.call_args[0][:2]
        self.assertEqual(sr, 24000)
        # 1s upsampled to 24k + 50ms gap + 1s at 24k.
        expected = 24000 + int(24000 * BOUNDARY_SILENCE_MS / 1000.0) + 24000
        self.assertEqual(len(pushed), expected)
        self.assertEqual(pushed.dtype, numpy.float32)

    def test_gap_is_actually_silent(self):
        s = make_speech()
        s._synthesize_segment = MagicMock(side_effect=[
            (numpy.ones(1000, dtype=numpy.float32), 16000),
            (numpy.ones(1000, dtype=numpy.float32), 16000),
        ])
        s._speak_mixed('a b', [('hi', 'a'), ('en-us', 'b')])
        pushed = s._push_waveform_to_appsrc.call_args[0][0]
        gap_len = int(16000 * BOUNDARY_SILENCE_MS / 1000.0)
        self.assertTrue(numpy.all(pushed[1000:1000 + gap_len] == 0))

    def test_gives_up_when_a_segment_fails(self):
        """Half a sentence is worse than the whole one in one wrong voice."""
        s = make_speech()
        s._synthesize_segment = MagicMock(side_effect=[
            (numpy.ones(100, dtype=numpy.float32), 16000),
            (None, None),
        ])
        self.assertFalse(
            s._speak_mixed('मेरा name', [('hi', 'मेरा'), ('en-us', 'name')]))
        s._push_waveform_to_appsrc.assert_not_called()
        s._build_pipeline.assert_not_called()


class TestSpeakImplRoutesMixedText(unittest.TestCase):

    def test_mixed_text_goes_through_the_mixed_path(self):
        s = make_speech()
        s._speak_mixed = MagicMock(return_value=True)
        with patch.object(speech_mod, 'ALT_BACKENDS_AVAILABLE', False):
            s._speak_impl(FakeStatus(), 'मेरा name है Rahul')
        s._speak_mixed.assert_called_once()
        segments = s._speak_mixed.call_args[0][1]
        self.assertGreater(len(segments), 1)

    def test_monolingual_text_does_not(self):
        s = make_speech()
        s._speak_mixed = MagicMock(return_value=True)
        with patch.object(speech_mod, 'ALT_BACKENDS_AVAILABLE', False):
            s._speak_impl(FakeStatus(), 'hello there friends')
        s._speak_mixed.assert_not_called()

    def test_falls_through_to_espeak_when_the_mixed_path_declines(self):
        s = make_speech()
        s._speak_mixed = MagicMock(return_value=False)
        with patch.object(speech_mod, 'ALT_BACKENDS_AVAILABLE', False):
            s._speak_impl(FakeStatus(), 'मेरा name है Rahul')
        s._speak_mixed.assert_called_once()
        s._build_pipeline.assert_called_once()
        self.assertEqual(s._build_pipeline.call_args[0][0], 'espeak')


class TestResampling(unittest.TestCase):

    def test_upsampling_preserves_length_ratio_and_dtype(self):
        wave = numpy.ones(16000, dtype=numpy.float32)
        out = speech_mod._resample_linear(wave, 16000, 24000)
        self.assertEqual(len(out), 24000)
        self.assertEqual(out.dtype, numpy.float32)

    def test_same_rate_is_a_no_op(self):
        wave = numpy.ones(100, dtype=numpy.float32)
        self.assertIs(speech_mod._resample_linear(wave, 16000, 16000), wave)

    def test_empty_input(self):
        wave = numpy.zeros(0, dtype=numpy.float32)
        self.assertEqual(len(speech_mod._resample_linear(wave, 16000, 24000)), 0)

    def test_a_constant_signal_stays_constant(self):
        """Interpolation must not ring or clip on the flat parts."""
        wave = numpy.full(1000, 0.5, dtype=numpy.float32)
        out = speech_mod._resample_linear(wave, 16000, 24000)
        self.assertTrue(numpy.allclose(out, 0.5, atol=1e-6))


if __name__ == '__main__':
    unittest.main()
