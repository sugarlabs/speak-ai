# test_voice.py
import unittest
import sys
import os
import unittest.mock

# ── Stub out every Sugar / GStreamer / GI dependency ──────────────────────────
for mod in [
    'gi', 'gi.repository', 'gi.repository.Gst', 'gi.repository.GLib',
    'gi.repository.GObject', 'gi.repository.Gdk', 'gi.repository.GdkPixbuf',
    'gi.repository.Gtk',
    'sugar3', 'sugar3.speech', 'sugar3.graphics', 'sugar3.graphics.style',
    'sugar3.activity', 'sugar3.activity.activity',
    'numpy', 'kokoro', 'speech',
]:
    sys.modules[mod] = unittest.mock.MagicMock()

# Now we can safely import voice.py
import voice


# ─────────────────────────────────────────────────────────────────────────────
# Tests for _friendly_name()
# ─────────────────────────────────────────────────────────────────────────────
class TestFriendlyName(unittest.TestCase):

    def test_simple_english(self):
        self.assertEqual(voice._friendly_name('english'), 'English')

    def test_hindi(self):
        self.assertEqual(voice._friendly_name('hindi'), 'Hindi')

    def test_french(self):
        self.assertEqual(voice._friendly_name('french'), 'French')

    def test_hyphenated(self):
        # Should capitalize first word only
        result = voice._friendly_name('portuguese-brazil')
        self.assertTrue(result.startswith('Portuguese'))


# ─────────────────────────────────────────────────────────────────────────────
# Tests for Voice class
# ─────────────────────────────────────────────────────────────────────────────
class TestVoiceClass(unittest.TestCase):

    def test_friendly_name_rp(self):
        v = voice.Voice('en', 'english_rp')
        self.assertEqual(v.friendlyname, 'English (Received Pronunciation)')

    def test_friendly_name_us(self):
        v = voice.Voice('en', 'english-us')
        self.assertEqual(v.friendlyname, 'English (USA)')

    def test_friendly_name_wmids(self):
        v = voice.Voice('en', 'english_wmids')
        self.assertEqual(v.friendlyname, 'English (West Midlands)')

    def test_sorting(self):
        # English (E) comes before Hindi (H) alphabetically
        v_en = voice.Voice('en', 'english')
        v_hi = voice.Voice('hi', 'hindi')
        self.assertTrue(v_en < v_hi)

    def test_language_stored(self):
        v = voice.Voice('hi', 'hindi')
        self.assertEqual(v.language, 'hi')


# ─────────────────────────────────────────────────────────────────────────────
# Tests for KOKORO_LANG_MAP (defined in speech.py)
# ─────────────────────────────────────────────────────────────────────────────
class TestKokoroLangMap(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Load KOKORO_LANG_MAP once for all tests in this class."""
        import importlib.util

        # Stub every dependency speech.py needs
        for m in [
            'gi', 'gi.repository',
            'gi.repository.Gst', 'gi.repository.GLib',
            'gi.repository.GObject',
            'sugar3', 'sugar3.speech',
            'numpy', 'kokoro',
        ]:
            sys.modules[m] = unittest.mock.MagicMock()

        speech_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'speech.py'
        )
        spec = importlib.util.spec_from_file_location('speech_real', speech_path)
        mod = importlib.util.module_from_spec(spec)

        try:
            spec.loader.exec_module(mod)
        except Exception:
            pass  # GStreamer calls fail on Windows — that's fine

        cls.lang_map = mod.KOKORO_LANG_MAP

    def test_all_expected_languages_present(self):
        expected = {'a', 'b', 'j', 'z', 'e', 'f', 'h', 'i', 'p'}
        self.assertEqual(set(self.lang_map.keys()), expected)

    def test_hindi_prefix_maps_to_h(self):
        self.assertIn('hf_', self.lang_map['h'])
        self.assertIn('hm_', self.lang_map['h'])

    def test_japanese_prefix_maps_to_j(self):
        self.assertIn('jf_', self.lang_map['j'])
        self.assertIn('jm_', self.lang_map['j'])

    def test_chinese_prefix_maps_to_z(self):
        self.assertIn('zf_', self.lang_map['z'])
        self.assertIn('zm_', self.lang_map['z'])

    def test_hindi_voice_detected_correctly(self):
        """hf_alpha should resolve to lang_code 'h' (Hindi)"""
        detected = 'a'
        for lang_code, prefixes in self.lang_map.items():
            if any('hf_alpha'.startswith(p) for p in prefixes):
                detected = lang_code
                break
        self.assertEqual(detected, 'h')

    def test_japanese_voice_detected_correctly(self):
        """jf_alpha should resolve to lang_code 'j' (Japanese)"""
        detected = 'a'
        for lang_code, prefixes in self.lang_map.items():
            if any('jf_alpha'.startswith(p) for p in prefixes):
                detected = lang_code
                break
        self.assertEqual(detected, 'j')

    def test_english_voice_detected_correctly(self):
        """af_heart should resolve to lang_code 'a' (American English)"""
        detected = 'a'
        for lang_code, prefixes in self.lang_map.items():
            if any('af_heart'.startswith(p) for p in prefixes):
                detected = lang_code
                break
        self.assertEqual(detected, 'a')

# ─────────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    unittest.main(verbosity=2)