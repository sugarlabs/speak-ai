"""
Pronunciation Test Framework for Multilingual TTS Validation.

This package provides a comprehensive testing framework for validating
pronunciation accuracy across multiple languages in the Speak-AI project.

Key Components:
    - test_multilingual_base: Base classes for building language-specific tests
    - test_hindi_pronunciation: Hindi pronunciation validation tests
    - conftest: pytest configuration and fixtures
    - language_data/: JSON files with test case definitions per language

The framework enables:
    1. Automated regression testing of G2P (Grapheme-to-Phoneme) conversion
    2. Documentation of correct pronunciation rules per language
    3. Easy extensibility to add new languages
    4. Organized test grouping by linguistic phenomenon (e.g., schwa deletion)

Usage:
    pytest tests/                          # Run all tests
    pytest tests/test_hindi_pronunciation.py  # Run Hindi tests only
    pytest tests/ -k "schwa_deletion"     # Run tests with specific tag
    pytest tests/ -v                       # Verbose output with test details
"""

__version__ = '0.1.0'
