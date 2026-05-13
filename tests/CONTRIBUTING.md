# Contributing to Pronunciation Tests

Thank you for helping improve pronunciation accuracy in Speak-AI! This document explains how to contribute pronunciation tests.

## When to Add Tests

Add pronunciation tests when you:
- Add support for a new language
- Find a pronunciation bug that needs to be caught by regression tests
- Identify underrepresented phonological features
- Want to document important pronunciation rules

## How to Contribute

### 1. Adding Tests to an Existing Language

If you want to add test cases for an existing language (e.g., Hindi):

1. **Edit the JSON file**: Update `tests/language_data/[language].json`
   ```json
   {
     "text": "नया",
     "expected_phonemes": "/naːjaː/",
     "description": "Testing vowel length and approximant",
     "tags": ["vowel_length", "approximant"],
     "notes": "Transliteration: nayā. Shows /j/ approximant."
   }
   ```

2. **Run tests locally**:
   ```bash
   pytest tests/test_[language]_pronunciation.py -v
   ```

3. **Document your test**: Include clear descriptions and linguistic notes

### 2. Adding a New Language

If you want to add pronunciation tests for a new language:

1. **Create test data**: `tests/language_data/[language].json`
   - Start with 10-15 representative test cases
   - Cover key phonological features
   - Include documentation for each feature

2. **Create test module**: `tests/test_[language]_pronunciation.py`
   - Use the template in `test_language_template.py`
   - Implement language-specific phoneme comparison if needed
   - Create test classes organized by phonological feature

3. **Add fixture**: Update `tests/conftest.py`
   ```python
   @pytest.fixture(scope="session")
   def [language]_pipeline():
       try:
           pipeline = KPipeline(lang_code='[code]', model=False)
           return pipeline
       except Exception as e:
           pytest.skip(f"[Language] pipeline not available: {e}")
   ```

4. **Update documentation**: Add to `tests/README.md`
   - Language overview
   - Key phonological rules
   - Example test cases in a table
   - How to run language-specific tests

### 3. Reporting a Pronunciation Bug

Found a pronunciation error? Create a regression test:

1. **Identify the problem**: What text produces wrong pronunciation?

2. **Create a test case**:
   ```json
   {
     "text": "problem_word",
     "expected_phonemes": "/correct_phonemes/",
     "description": "Bug fix: [Issue #123]",
     "tags": ["regression", "bug_fix"],
     "notes": "This word was producing /wrong/ instead of /correct/"
   }
   ```

3. **Mark as regression**:
   ```bash
   pytest tests/ -m "regression" -v
   ```

## Best Practices

### Documentation

Every test case should include:
- **text**: The word/phrase being tested
- **expected_phonemes**: Correct IPA output
- **description**: What linguistic feature is being tested
- **tags**: Categories for organization
- **notes**: Explanation of the rule and why it matters

Example:
```json
{
  "text": "काम",
  "expected_phonemes": "/kaːm/",
  "description": "Word-final schwa deletion",
  "tags": ["schwa_deletion", "word_final"],
  "notes": "Word-final schwas must be deleted in Hindi for natural pronunciation. Schwa-final would produce incorrect /kaːmə/"
}
```

### Test Selection

- **Minimal pairs**: Include tests that show phonemic contrasts
- **Edge cases**: Test boundaries and unusual cases
- **Frequency words**: Include common words first
- **Progressive complexity**: Build from simple to complex

### Phoneme Accuracy

- Use **IPA notation** consistently: https://www.internationalphoneticsassociation.org/
- Mark **long vowels** with `:` (e.g., `/kaːm/`)
- Include **stress marks** when relevant (e.g., `/ˈtɪɡər/`)
- Use **diacritics** for non-standard sounds

## Code Style

### Python Code

```python
class MyLanguagePronunciationSuite(PronunciationTestSuite):
    """Language-specific test suite with clear docstrings."""
    
    def __init__(self):
        super().__init__(language_code='xx', language_name='My Language')
        self._load_test_data()
    
    def normalize_phonemes(self, phonemes: str) -> str:
        """Language-specific phoneme normalization."""
        normalized = super().normalize_phonemes(phonemes)
        # Add language-specific logic
        return normalized
```

### Test Methods

```python
def test_my_linguistic_feature(self, language_pipeline):
    """Test: Input text -> Expected output.
    
    Linguistic Rule: Brief explanation of what's being tested.
    """
    if language_pipeline is None:
        pytest.skip("Pipeline not available")
    
    test = _suite.get_tests_by_tag('tag_name')[0]
    # Test implementation
```

## Testing Locally

### Before Submitting PR

```bash
# Run all tests
pytest tests/ -v

# Run language-specific tests
pytest tests/test_hindi_pronunciation.py -v

# Run tests with specific tag
pytest tests/ -k "schwa_deletion" -v

# Run with coverage
pytest tests/ --cov=tests --cov-report=term-missing

# Check for pytest issues
pytest tests/ --collect-only
```

### Quick Validation

```bash
# Test suite loads correctly
pytest tests/test_[language]_pronunciation.py::test_[language]_suite_loads -v

# JSON is valid
python -m json.tool tests/language_data/[language].json
```

## Submitting Changes

1. **Fork and branch**: Create a feature branch
   ```bash
   git checkout -b add-hindi-tests
   ```

2. **Make changes**: Add or update test files

3. **Test locally**: Ensure all tests pass
   ```bash
   pytest tests/ -v
   ```

4. **Commit with clear messages**:
   ```bash
   git commit -m "feat: Add Hindi schwa deletion tests (#120)"
   ```

5. **Create Pull Request**: Include:
   - Description of what tests were added
   - Which linguistic features are covered
   - Any related issues (#123)

## Common Issues

### "Pipeline not available"
- Ensure language dependencies are installed
- Check `conftest.py` fixture configuration
- Run `pip install kokoro` and language-specific packages

### Phoneme mismatches
- Verify IPA notation is correct
- Check if normalization is needed for your language
- Compare with linguistic references

### JSON parsing errors
- Validate JSON: `python -m json.tool [file].json`
- Ensure UTF-8 encoding for non-Latin scripts
- Check quote characters and escaped characters

## Resources

### Linguistic References
- **IPA Chart**: https://www.internationalphoneticsassociation.org/content/ipa-chart
- **Language-specific resources**: Document in test JSON files
- **Phonology references**: Link in README.md

### Project Resources
- **Issue #120**: Pronunciation test framework feature
- **kokoro repository**: TTS model documentation
- **misaki library**: G2P implementations

## Questions?

- Check existing test cases for examples
- Review test documentation in test files
- Ask in project discussions/issues
- Refer to linguistic references linked in tests

## Code of Conduct

Please adhere to the project's code of conduct. We're building tools for children's education, so accuracy and quality are paramount.

---

**Thank you for contributing to better pronunciation in Speak-AI!**
