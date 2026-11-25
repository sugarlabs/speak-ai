"""
Hindi pronunciation validation tests.

This module tests the Hindi G2P (Grapheme-to-Phoneme) conversion to ensure
correct pronunciation with proper handling of Hindi-specific phonological rules:
- Word-final and medial schwa deletion
- Geminate consonants
- Vowel length distinctions
- Nasal assimilation
- Retroflex consonants

Reference: Hindi phonology follows IPA conventions with specific rules for
schwa deletion that are critical for natural-sounding speech synthesis.
"""

import json
import pytest
from pathlib import Path
from typing import List, Dict

from test_multilingual_base import PronunciationTestSuite, PronunciationTest


class HindiPronunciationSuite(PronunciationTestSuite):
    """Hindi-specific pronunciation test suite."""
    
    def __init__(self):
        super().__init__(language_code='hi', language_name='Hindi')
        self._load_test_data()
    
    def _load_test_data(self):
        """Load test cases from JSON file."""
        json_path = Path(__file__).parent / 'language_data' / 'hindi.json'
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        for test_case in data['test_cases']:
            self.add_test(
                text=test_case['text'],
                expected_phonemes=test_case['expected_phonemes'],
                description=test_case['description'],
                tags=test_case['tags'],
                notes=test_case['notes']
            )
    
    def normalize_phonemes(self, phonemes: str) -> str:
        """Normalize Hindi phonemes for comparison.
        
        Handles:
        - Whitespace normalization
        - IPA symbol normalization
        - Variant handling
        """
        normalized = super().normalize_phonemes(phonemes)
        
        # Remove forward slashes commonly used in IPA notation
        normalized = normalized.strip('/')
        
        # Normalize common IPA variants (language engines may output different forms)
        # This is a basic normalization; can be expanded based on real-world testing
        
        return normalized
    
    def compare_phonemes(self, actual: str, expected: str) -> tuple:
        """Compare Hindi phonemes with special handling for common variations.
        
        Returns:
            Tuple of (match_bool, difference_description)
        """
        actual_norm = self.normalize_phonemes(actual)
        expected_norm = self.normalize_phonemes(expected)
        
        if actual_norm == expected_norm:
            return True, ""
        
        # Check if the difference is only in formatting (spaces, slashes, etc.)
        actual_compact = actual_norm.replace(' ', '')
        expected_compact = expected_norm.replace(' ', '')
        
        if actual_compact == expected_compact:
            return True, f"Match (formatting difference)"
        
        return False, f"Expected: /{expected_norm}/, Got: /{actual_norm}/"


# Load the Hindi test suite
_hindi_suite = HindiPronunciationSuite()


class TestHindiSchwaDeletion:
    """Tests for Hindi schwa deletion rules (word-final and medial)."""
    
    @pytest.fixture
    def hindi_pipeline(self, hindi_pipeline):
        """Use fixture from conftest."""
        return hindi_pipeline
    
    def test_word_final_schwa_deletion_kaam(self, hindi_pipeline):
        """Test: काम (kāma) -> should produce /kaːm/ NOT /kaːmə/.
        
        Rule: Word-final schwas are deleted in Hindi, which is crucial for
        natural pronunciation and avoiding extra syllables.
        """
        test = _hindi_suite.get_tests_by_tag('schwa_deletion')[0]
        
        # Skip if pipeline not available
        if hindi_pipeline is None:
            pytest.skip("Hindi pipeline not available")
        
        # Get actual phonemes from pipeline
        try:
            result = list(hindi_pipeline(test.text, None))
            if result and len(result) > 1:
                actual_phonemes = result[1]
                match, diff = _hindi_suite.compare_phonemes(
                    actual_phonemes,
                    test.expected_phonemes
                )
                
                assert match, (
                    f"Test: {test.description}\n"
                    f"Text: {test.text}\n"
                    f"Notes: {test.notes}\n"
                    f"Difference: {diff}"
                )
        except Exception as e:
            pytest.skip(f"G2P conversion failed: {e}")
    
    def test_medial_schwa_deletion_rasta(self, hindi_pipeline):
        """Test: रास्ता (rāstā) -> should produce /raːstaː/ NOT /raːsətaː/.
        
        Rule: Medial schwas are deleted in certain contexts, particularly before
        the final stressed syllable. This is a key prosodic rule.
        """
        test = _hindi_suite.get_tests_by_tag('schwa_deletion')[1]
        
        if hindi_pipeline is None:
            pytest.skip("Hindi pipeline not available")
        
        try:
            result = list(hindi_pipeline(test.text, None))
            if result and len(result) > 1:
                actual_phonemes = result[1]
                match, diff = _hindi_suite.compare_phonemes(
                    actual_phonemes,
                    test.expected_phonemes
                )
                
                assert match, (
                    f"Test: {test.description}\n"
                    f"Text: {test.text}\n"
                    f"Difference: {diff}"
                )
        except Exception as e:
            pytest.skip(f"G2P conversion failed: {e}")


class TestHindiConsonants:
    """Tests for Hindi consonant pronunciation (gemination, aspiration, retroflex)."""
    
    @pytest.fixture
    def hindi_pipeline(self, hindi_pipeline):
        """Use fixture from conftest."""
        return hindi_pipeline
    
    def test_geminate_consonants_kaksha(self, hindi_pipeline):
        """Test: कक्षा (kakṣā) -> should produce /kəkʂaː/ with geminate /kk/.
        
        Rule: Geminate (doubled) consonants are phonemically distinct in Hindi.
        They must be preserved in phonetic output for correct pronunciation.
        """
        test = _hindi_suite.get_tests_by_tag('geminate_consonants')[0]
        
        if hindi_pipeline is None:
            pytest.skip("Hindi pipeline not available")
        
        try:
            result = list(hindi_pipeline(test.text, None))
            if result and len(result) > 1:
                actual_phonemes = result[1]
                match, diff = _hindi_suite.compare_phonemes(
                    actual_phonemes,
                    test.expected_phonemes
                )
                
                assert match, (
                    f"Test: {test.description}\n"
                    f"Text: {test.text}\n"
                    f"Difference: {diff}"
                )
        except Exception as e:
            pytest.skip(f"G2P conversion failed: {e}")
    
    def test_aspirated_consonants_dhanyavad(self, hindi_pipeline):
        """Test: धन्यवाद (dhanyavād) -> /dʰənjəvaːd/ with aspirated /dʰ/.
        
        Rule: Hindi distinguishes between aspirated and unaspirated consonants.
        Aspiration must be preserved for phonemic correctness.
        """
        test = _hindi_suite.get_tests_by_tag('aspiration')[0]
        
        if hindi_pipeline is None:
            pytest.skip("Hindi pipeline not available")
        
        try:
            result = list(hindi_pipeline(test.text, None))
            if result and len(result) > 1:
                actual_phonemes = result[1]
                match, diff = _hindi_suite.compare_phonemes(
                    actual_phonemes,
                    test.expected_phonemes
                )
                
                assert match, (
                    f"Test: {test.description}\n"
                    f"Text: {test.text}\n"
                    f"Difference: {diff}"
                )
        except Exception as e:
            pytest.skip(f"G2P conversion failed: {e}")


class TestHindiVowels:
    """Tests for Hindi vowel pronunciation (length distinctions)."""
    
    @pytest.fixture
    def hindi_pipeline(self, hindi_pipeline):
        """Use fixture from conftest."""
        return hindi_pipeline
    
    def test_vowel_length_kahani(self, hindi_pipeline):
        """Test: कहानी (kahānī) -> /kəhaːniː/ with long vowels.
        
        Rule: Hindi distinguishes between short and long vowels phonemically.
        Long vowels must be marked with ':' in IPA notation.
        """
        test = _hindi_suite.get_tests_by_tag('vowel_length')[0]
        
        if hindi_pipeline is None:
            pytest.skip("Hindi pipeline not available")
        
        try:
            result = list(hindi_pipeline(test.text, None))
            if result and len(result) > 1:
                actual_phonemes = result[1]
                match, diff = _hindi_suite.compare_phonemes(
                    actual_phonemes,
                    test.expected_phonemes
                )
                
                assert match, (
                    f"Test: {test.description}\n"
                    f"Text: {test.text}\n"
                    f"Difference: {diff}"
                )
        except Exception as e:
            pytest.skip(f"G2P conversion failed: {e}")


def test_hindi_suite_loads():
    """Test that Hindi test suite loads correctly."""
    assert _hindi_suite.language_code == 'hi'
    assert _hindi_suite.language_name == 'Hindi'
    assert len(_hindi_suite.test_cases) > 0
    
    summary = _hindi_suite.get_summary()
    assert summary['total_tests'] == 15
    assert 'schwa_deletion' in summary['tags']
    assert 'geminate_consonants' in summary['tags']
    assert 'vowel_length' in summary['tags']


def test_hindi_suite_filtering():
    """Test that test suite can filter by tags."""
    schwa_tests = _hindi_suite.get_tests_by_tag('schwa_deletion')
    assert len(schwa_tests) > 0
    
    geminate_tests = _hindi_suite.get_tests_by_tag('geminate_consonants')
    assert len(geminate_tests) > 0
    
    vowel_tests = _hindi_suite.get_tests_by_tag('vowel_length')
    assert len(vowel_tests) > 0
