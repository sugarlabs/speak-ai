import pytest
from g2p_ext import AdvancedG2P

class TestAdvancedG2P:
    def test_hindi_basic_mapping(self):
        text = "काम"
        expected = "kaːm"
        phonemes, tokens = AdvancedG2P.phonemize(text, 'h')
        assert phonemes == expected
        assert len(tokens) == 1
        
    def test_hindi_schwa_deletion(self):
        # 'कमल' should be 'kəməl', 'करना' should be 'kəɾnaː' (schwa deletion)
        text = "करना"
        expected = "kəɾənaː"
        phonemes, _ = AdvancedG2P.phonemize(text, 'h')
        assert phonemes == expected

    def test_hindi_halant(self):
        text = "क्या"
        expected = "kjaː" # Halant on k removes schwa
        phonemes, _ = AdvancedG2P.phonemize(text, 'h')
        assert phonemes == expected
        
    def test_arabic_basic(self):
        text = "كتاب"
        expected = "ktaːb"
        phonemes, _ = AdvancedG2P.phonemize(text, 'r')
        assert phonemes == expected

    def test_arabic_diacritics(self):
        text = "كِتَابٌ"
        expected = "kitaaːbun"
        phonemes, _ = AdvancedG2P.phonemize(text, 'r')
        assert phonemes == expected

    def test_arabic_shadda(self):
        text = "مُدَرِّس"
        expected = "mudariːs"
        phonemes, _ = AdvancedG2P.phonemize(text, 'r')
        assert phonemes == expected

    def test_swahili_digraphs(self):
        text = "shamba"
        expected = "ʃamɓa"
        phonemes, _ = AdvancedG2P.phonemize(text, 's')
        assert phonemes == expected
        
    def test_swahili_trigraphs(self):
        text = "ng'ombe"
        expected = "ŋɔmɓɛ"
        phonemes, _ = AdvancedG2P.phonemize(text, 's')
        assert phonemes == expected

    def test_fallback(self):
        text = "Hello"
        phonemes, _ = AdvancedG2P.phonemize(text, 'unknown_code')
        assert phonemes == text
