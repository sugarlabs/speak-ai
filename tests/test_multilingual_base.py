"""
Base test framework for multilingual TTS pronunciation validation.

This module provides a PronunciationTestCase base class that standardizes
how pronunciation tests are written across different languages.
"""

import re
from typing import List, Dict, Tuple, Optional
from abc import ABC, abstractmethod


class PronunciationTest:
    """Represents a single pronunciation test case.
    
    Attributes:
        text: Input text in the target language
        expected_phonemes: Expected phoneme output (IPA notation)
        description: Human-readable description of the test (e.g., "Hindi Schwa Deletion")
        tags: List of tags for organizing tests (e.g., "schwa_deletion", "word_final")
        notes: Additional notes about the test case or linguistic rule
    """
    
    def __init__(
        self,
        text: str,
        expected_phonemes: str,
        description: str = "",
        tags: List[str] = None,
        notes: str = ""
    ):
        self.text = text
        self.expected_phonemes = expected_phonemes
        self.description = description
        self.tags = tags or []
        self.notes = notes
    
    def __repr__(self):
        return f"PronunciationTest({self.text!r}, {self.expected_phonemes!r}, {self.description!r})"


class PronunciationTestSuite:
    """Base class for language-specific pronunciation test suites.
    
    This class provides a framework for organizing and validating pronunciation
    tests for a specific language. Subclasses should define test cases and
    implement phoneme comparison logic if needed.
    """
    
    def __init__(self, language_code: str, language_name: str):
        """Initialize a test suite for a specific language.
        
        Args:
            language_code: Language code (e.g., 'hi' for Hindi, 'a' for English)
            language_name: Human-readable language name (e.g., 'Hindi')
        """
        self.language_code = language_code
        self.language_name = language_name
        self.test_cases: List[PronunciationTest] = []
    
    def add_test(
        self,
        text: str,
        expected_phonemes: str,
        description: str = "",
        tags: List[str] = None,
        notes: str = ""
    ) -> None:
        """Add a test case to the suite.
        
        Args:
            text: Input text in the target language
            expected_phonemes: Expected phoneme output
            description: Description of the test
            tags: Tags for organizing tests
            notes: Additional notes
        """
        test = PronunciationTest(text, expected_phonemes, description, tags, notes)
        self.test_cases.append(test)
    
    def get_tests_by_tag(self, tag: str) -> List[PronunciationTest]:
        """Get all test cases with a specific tag.
        
        Args:
            tag: Tag to filter by
            
        Returns:
            List of test cases with the given tag
        """
        return [test for test in self.test_cases if tag in test.tags]
    
    def normalize_phonemes(self, phonemes: str) -> str:
        """Normalize phoneme string for comparison.
        
        This method can be overridden by subclasses to implement language-specific
        phoneme normalization (e.g., handling variants, optional markers).
        
        Args:
            phonemes: Raw phoneme string
            
        Returns:
            Normalized phoneme string
        """
        # Default: minimal normalization - strip whitespace and normalize slashes
        normalized = phonemes.strip()
        normalized = re.sub(r'\s+', ' ', normalized)  # collapse multiple spaces
        return normalized
    
    def compare_phonemes(self, actual: str, expected: str) -> Tuple[bool, str]:
        """Compare actual phonemes with expected phonemes.
        
        This method can be overridden by subclasses to implement language-specific
        comparison logic (e.g., fuzzy matching, variant handling).
        
        Args:
            actual: Actual phoneme output from G2P
            expected: Expected phoneme output
            
        Returns:
            Tuple of (match_bool, difference_description)
        """
        actual_normalized = self.normalize_phonemes(actual)
        expected_normalized = self.normalize_phonemes(expected)
        
        if actual_normalized == expected_normalized:
            return True, ""
        else:
            return False, f"Expected: {expected_normalized}, Got: {actual_normalized}"
    
    def get_summary(self) -> Dict[str, any]:
        """Get summary statistics about the test suite.
        
        Returns:
            Dictionary with test count and tag breakdown
        """
        tag_counts = {}
        for test in self.test_cases:
            for tag in test.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        
        return {
            'language': self.language_name,
            'language_code': self.language_code,
            'total_tests': len(self.test_cases),
            'tags': tag_counts,
        }


class MultilingualPronunciationValidator:
    """Validates pronunciation across multiple languages.
    
    This class manages multiple language-specific test suites and provides
    unified validation and reporting.
    """
    
    def __init__(self):
        """Initialize the multilingual validator."""
        self.suites: Dict[str, PronunciationTestSuite] = {}
    
    def register_suite(self, suite: PronunciationTestSuite) -> None:
        """Register a language-specific test suite.
        
        Args:
            suite: PronunciationTestSuite instance to register
        """
        self.suites[suite.language_code] = suite
    
    def get_suite(self, language_code: str) -> Optional[PronunciationTestSuite]:
        """Get a registered test suite by language code.
        
        Args:
            language_code: Language code to look up
            
        Returns:
            PronunciationTestSuite if found, None otherwise
        """
        return self.suites.get(language_code)
    
    def get_all_suites(self) -> Dict[str, PronunciationTestSuite]:
        """Get all registered test suites.
        
        Returns:
            Dictionary of language_code -> PronunciationTestSuite
        """
        return self.suites
