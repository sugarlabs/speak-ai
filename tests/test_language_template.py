"""
Example template for adding pronunciation tests for a new language.

This module demonstrates the recommended pattern for adding language-specific
pronunciation tests to the test framework.

To add a new language:
1. Copy this file and rename to test_[language]_pronunciation.py
2. Update the language code and name
3. Create language_data/[language].json with test cases
4. Add a fixture to conftest.py for the new language
5. Implement test classes following the pattern below
6. Update the main README.md to document the new language

Example: Adding Spanish (language_code='e')
"""

import json
import pytest
from pathlib import Path
from typing import List

from test_multilingual_base import PronunciationTestSuite, PronunciationTest


class SpanishPronunciationSuite(PronunciationTestSuite):
    """Spanish-specific pronunciation test suite.
    
    This template demonstrates how to:
    - Load test data from JSON
    - Implement language-specific phoneme normalization
    - Create test methods for different phonological features
    """
    
    def __init__(self):
        super().__init__(language_code='e', language_name='Spanish')
        self._load_test_data()
    
    def _load_test_data(self):
        """Load test cases from JSON file."""
        json_path = Path(__file__).parent / 'language_data' / 'spanish.json'
        
        # Handle case where JSON file doesn't exist yet
        if not json_path.exists():
            # For now, create minimal test data
            self.add_test(
                text='hola',
                expected_phonemes='/ˈoːla/',
                description='Spanish greeting',
                tags=['basic'],
                notes='Basic test case'
            )
            return
        
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
        """Normalize Spanish phonemes for comparison.
        
        Spanish-specific normalization:
        - Strip IPA slashes (/ /)
        - Normalize whitespace
        - Handle lisp vs. non-lisp variants if needed
        """
        normalized = super().normalize_phonemes(phonemes)
        
        # Remove forward slashes from IPA notation
        normalized = normalized.strip('/')
        
        # Add Spanish-specific normalizations here
        # Example: handling θ (lisp c/z) vs. s normalization
        
        return normalized
    
    def compare_phonemes(self, actual: str, expected: str) -> tuple:
        """Compare Spanish phonemes with language-specific logic.
        
        Returns:
            Tuple of (match_bool, difference_description)
        """
        actual_norm = self.normalize_phonemes(actual)
        expected_norm = self.normalize_phonemes(expected)
        
        if actual_norm == expected_norm:
            return True, ""
        
        return False, f"Expected: /{expected_norm}/, Got: /{actual_norm}/"


# Load the Spanish test suite
_spanish_suite = SpanishPronunciationSuite()


# ============================================================================
# Test Classes
# ============================================================================

class TestSpanishPhonetics:
    """Tests for basic Spanish phonetic features."""
    
    @pytest.fixture
    def spanish_pipeline(self, english_pipeline):  # Note: Using english_pipeline as placeholder
        """Use fixture from conftest.
        
        Note: Update this to use spanish_pipeline once the fixture is added
        to conftest.py:
        
        @pytest.fixture(scope="session")
        def spanish_pipeline():
            try:
                pipeline = KPipeline(lang_code='e', model=False)
                return pipeline
            except Exception as e:
                pytest.skip(f"Spanish pipeline not available: {e}")
        """
        return spanish_pipeline
    
    def test_spanish_greeting_hola(self, spanish_pipeline):
        """Test: hola -> /ˈoːla/
        
        This is a placeholder test. Replace with actual Spanish test cases
        once language_data/spanish.json is created.
        """
        if spanish_pipeline is None:
            pytest.skip("Spanish pipeline not available")
        
        # This is a template - implement based on actual G2P output
        assert True


class TestSpanishVowels:
    """Tests for Spanish vowel pronunciation.
    
    Spanish template for vowel-specific tests:
    - Spanish has 5 vowels: a, e, i, o, u
    - Each vowel has relatively consistent pronunciation
    - Vowel length is generally not contrastive
    """
    pass


class TestSpanishConsonants:
    """Tests for Spanish consonant pronunciation.
    
    Spanish template for consonant-specific tests:
    - Voiceless stops: /p/, /t/, /k/
    - Fricatives: /f/, /s/, /θ/ (or /s/ in non-lisp dialects), /x/
    - Affricates: /tʃ/
    - Nasals: /m/, /n/, /ŋ/
    - Approximants and taps
    """
    pass


class TestSpanishDialects:
    """Tests for dialect variations in Spanish.
    
    Note: The framework can accommodate multiple dialects by:
    - Using different language codes for different dialects
    - Having separate test suites for each dialect
    - Using tags to mark dialect-specific tests
    """
    pass


def test_spanish_suite_loads():
    """Test that Spanish test suite loads correctly."""
    assert _spanish_suite.language_code == 'e'
    assert _spanish_suite.language_name == 'Spanish'
    assert len(_spanish_suite.test_cases) > 0


# ============================================================================
# Template for Adding Another Language
# ============================================================================

"""
To add a new language, follow this pattern:

1. Create JSON test data file:
   tests/language_data/[language_code].json
   
   Structure:
   {
     "language": "Language Name",
     "language_code": "[code]",
     "description": "...",
     "test_categories": {...},
     "test_cases": [...]
   }

2. Create Python test file:
   tests/test_[language]_pronunciation.py
   
   Include:
   - Language-specific PronunciationTestSuite subclass
   - Test classes for different phonological features
   - Proper documentation and notes

3. Add fixture to conftest.py:
   @pytest.fixture(scope="session")
   def [language]_pipeline():
       try:
           pipeline = KPipeline(lang_code='[code]', model=False)
           return pipeline
       except Exception as e:
           pytest.skip(f"[Language] pipeline not available: {e}")

4. Update tests/README.md:
   - Add language to supported list
   - Document key phonological features
   - Provide example test cases with explanations

5. Run tests:
   pytest tests/test_[language]_pronunciation.py -v
"""
