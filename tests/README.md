# Pronunciation Test Framework for Multilingual TTS

A comprehensive testing framework for validating pronunciation accuracy across multiple languages in the Speak-AI project. This framework enables automated regression testing of G2P (Grapheme-to-Phoneme) conversion and serves as documentation for correct pronunciation rules.

## Overview

As Speak-AI expands to support 10+ languages, it's critical to verify that Text-to-Speech (TTS) pronunciation is correct—especially for non-Latin scripts like Hindi (Devanagari) and Arabic where small errors in G2P output cause noticeably wrong pronunciation.

**The Problem:** Without test cases, developers adding language support have no way to know if their G2P output is phonemically correct.

**The Solution:** This framework provides language-specific pronunciation test cases that:
- Define expected phoneme output for common words per language
- Run automatically to catch regressions
- Serve as documentation for correct pronunciation rules

## Key Features

### ✅ Language-Specific Test Suites
- Organized tests by linguistic phenomena (schwa deletion, gemination, etc.)
- IPA notation for standardized phonetic representation
- Comprehensive test cases with documentation

### ✅ Extensible Architecture
- Base classes for easy addition of new languages
- JSON-based test data for easy maintenance and collaboration
- Tag-based test organization and filtering

### ✅ Regression Detection
- Automated G2P output validation
- Clear reporting of pronunciation errors
- Helps catch regressions before they reach production

### ✅ Developer Documentation
- Embedded linguistic rules and notes
- Serves as reference material for correct pronunciation
- Example: "Word-final schwa must be deleted in Hindi"

## Project Structure

```
tests/
├── __init__.py                          # Package initialization
├── conftest.py                          # pytest configuration & fixtures
├── test_multilingual_base.py            # Base classes for all language tests
├── test_hindi_pronunciation.py          # Hindi pronunciation tests
├── test_english_pronunciation.py        # English pronunciation tests (template)
├── language_data/
│   ├── hindi.json                       # Hindi test case definitions
│   └── english.json                     # English test case definitions (template)
└── README.md                            # This file
```

## Test Categories by Language

### Hindi (हिंदी) - `tests/test_hindi_pronunciation.py`

**Supported Phonological Rules:**
- **Schwa Deletion**: Word-final and medial schwa deletion (crucial for natural pronunciation)
- **Geminate Consonants**: Doubled consonants are phonemically distinct
- **Vowel Length**: Hindi distinguishes short vs. long vowels
- **Aspiration**: Aspirated vs. unaspirated consonants
- **Retroflex Consonants**: Retroflex sounds like /ʂ/ (sh) and /ʈ/ (t-retroflex)
- **Nasalization**: Anusvara handling and nasal assimilation

**Example Test Cases:**

| Text | Expected Phonemes | Rule | Notes |
|------|-------------------|------|-------|
| काम | /kaːm/ | Word-final schwa deletion | NOT /kaːmə/ |
| रास्ता | /raːstaː/ | Medial schwa deletion | NOT /raːsətaː/ |
| कक्षा | /kəkʂaː/ | Geminate consonants | Double 'k' preserved |
| धन्यवाद | /dʰənjəvaːd/ | Aspirated consonants | Initial /dʰ/ is aspirated |
| कहानी | /kəhaːniː/ | Vowel length | Long vowels marked with ':' |

### English (American) - `tests/language_data/english.json`

**Supported Phonological Rules:**
- **Rhotic R**: American English preserves r in all positions
- **Vowel Reduction**: Unstressed vowels reduce to schwa [ə]
- **Consonant Clusters**: Complex onset and coda clusters
- **Stress Patterns**: Word stress and syllable emphasis
- **Th-Sounds**: /θ/ (voiceless) vs /ð/ (voiced)

**Example Test Cases:**

| Text | Expected Phonemes | Feature | Notes |
|------|-------------------|---------|-------|
| hello | /həˈloʊ/ | Stress + reduction | First vowel reduces, stress on second |
| water | /ˈwɔtɚ/ | Rhotic r | American r preserved at end |
| string | /stɹɪŋ/ | Consonant cluster | Initial /str/ cluster |
| think | /θɪŋk/ | Voiceless theta | /θ/ at word beginning |

## Running Tests

### Prerequisites

```bash
# Install test dependencies
pip install pytest pytest-cov

# Ensure kokoro module is available
cd /path/to/speak-ai
```

### Basic Usage

```bash
# Run all tests
pytest tests/

# Run tests verbosely (shows all test names and results)
pytest tests/ -v

# Run tests with detailed output
pytest tests/ -vv

# Run only Hindi tests
pytest tests/test_hindi_pronunciation.py

# Run tests matching a specific pattern
pytest tests/ -k "hindi"
pytest tests/ -k "schwa_deletion"
```

### Advanced Usage

```bash
# Run tests and show coverage
pytest tests/ --cov=tests --cov-report=html

# Run tests with specific markers
pytest tests/ -m "hindi"

# Stop after first failure
pytest tests/ -x

# Run last failed tests only
pytest tests/ --lf

# Run tests in parallel (requires pytest-xdist)
pytest tests/ -n auto

# Generate JUnit XML for CI/CD integration
pytest tests/ --junit-xml=test-results.xml
```

## Adding Tests for a New Language

### Step 1: Create Test Data File

Create `tests/language_data/[language].json`:

```json
{
  "language": "Language Name",
  "language_code": "xx",
  "description": "Description of language and phonology",
  "notes": "Key linguistic features tested",
  "test_categories": {
    "category_name": {
      "description": "Description of category",
      "notes": "Notes about this phonological feature"
    }
  },
  "test_cases": [
    {
      "text": "word",
      "expected_phonemes": "/ɪ.pæ/",
      "description": "What this tests",
      "tags": ["category_name", "other_tags"],
      "notes": "Additional notes about the test"
    }
  ]
}
```

### Step 2: Create Test Module

Create `tests/test_[language]_pronunciation.py`:

```python
import json
import pytest
from pathlib import Path
from test_multilingual_base import PronunciationTestSuite

class LanguagePronunciationSuite(PronunciationTestSuite):
    """Language-specific pronunciation test suite."""
    
    def __init__(self):
        super().__init__(language_code='xx', language_name='Language Name')
        self._load_test_data()
    
    def _load_test_data(self):
        """Load test cases from JSON file."""
        json_path = Path(__file__).parent / 'language_data' / '[language].json'
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

_language_suite = LanguagePronunciationSuite()

class TestLanguagePronunciation:
    """Language pronunciation test class."""
    
    @pytest.fixture
    def language_pipeline(self, language_pipeline):
        return language_pipeline
    
    # Add specific test methods here
```

### Step 3: Add Fixture to conftest.py

Add a fixture in `tests/conftest.py`:

```python
@pytest.fixture(scope="session")
def language_pipeline():
    """Create a KPipeline instance for your language."""
    try:
        pipeline = KPipeline(lang_code='xx', model=False)
        return pipeline
    except Exception as e:
        pytest.skip(f"Language pipeline not available: {e}")
```

## Test Structure & Best Practices

### PronunciationTest Class
Represents a single test case with:
- `text`: Input text in target language
- `expected_phonemes`: Expected IPA output
- `description`: Human-readable description
- `tags`: Linguistic phenomenon tags for organization
- `notes`: Additional documentation

### PronunciationTestSuite Class
Base class for language-specific test suites providing:
- `add_test()`: Add test cases
- `normalize_phonemes()`: Language-specific phoneme normalization
- `compare_phonemes()`: Compare actual vs. expected with detailed reporting
- `get_tests_by_tag()`: Filter tests by linguistic category
- `get_summary()`: Generate test statistics

### Best Practices

1. **Use IPA Notation**: Standardize on International Phonetic Alphabet
2. **Tag Everything**: Organize tests by linguistic phenomenon
3. **Include Notes**: Document why a test exists and what rule it validates
4. **Test Regression Cases**: Include known problem cases
5. **Keep Tests Simple**: One linguistic feature per test
6. **Document Edge Cases**: Explain unusual phonological behavior

## Integration with CI/CD

### GitHub Actions Example

Create `.github/workflows/test-pronunciation.yml`:

```yaml
name: Pronunciation Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.8', '3.9', '3.10']
    
    steps:
    - uses: actions/checkout@v2
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install pytest pytest-cov
    
    - name: Run pronunciation tests
      run: |
        pytest tests/ -v --cov=tests --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v2
```

## Understanding Test Output

### Successful Test
```
tests/test_hindi_pronunciation.py::TestHindiSchwaDeletion::test_word_final_schwa_deletion_kaam PASSED
```

### Failed Test
```
AssertionError: Test: Word-final schwa deletion
Text: काम
Notes: Should produce /kaːm/ NOT /kaːmə/
Difference: Expected: /kaːm/, Got: /kaːmə/
```

## Troubleshooting

### G2P Pipeline Not Available
```
pytest.skip("Hindi pipeline not available")
```
**Solution**: Ensure the required language dependencies are installed:
```bash
pip install misaki[hi]  # For Hindi
```

### Phoneme Comparison Failures
- Check if the G2P output format matches IPA expectations
- Verify that language-specific phoneme normalization is correct
- Update `normalize_phonemes()` if needed for your language

### Tests Running Too Slowly
- Use session-scoped fixtures to avoid recreating pipelines
- Run specific test categories: `pytest tests/ -k "hindi"`
- Consider using pytest-xdist for parallel execution

## Contributing New Tests

When adding new test cases:

1. **Research the phonology**: Understand the linguistic rules
2. **Find minimal pairs**: Test cases that show contrasts
3. **Document thoroughly**: Explain why the test matters
4. **Include edge cases**: Don't just test happy paths
5. **Cross-reference standards**: Link to linguistic references

## References

### Linguistic Resources
- **Hindi Phonology**: 
  - Schwa deletion rules: Essential for natural speech
  - IPA Chart: https://www.internationalphoneticsassociation.org/content/ipa-chart
  
- **English Phonology**:
  - American English r-coloring
  - Vowel reduction patterns

### Tools & Standards
- **IPA (International Phonetic Alphabet)**: Standard phonetic notation
- **pytest**: Python testing framework
- **Kokoro**: TTS model used in Speak-AI

## License

These tests are part of the Speak-AI project and follow the same license.

## Support

For issues or questions about the test framework:
1. Check existing test cases for examples
2. Review the base test classes in `test_multilingual_base.py`
3. Consult the linguistic documentation in test case notes
4. Open an issue on the project repository

---

**Last Updated**: 2026-05-13
**Maintainers**: Speak-AI Development Team
