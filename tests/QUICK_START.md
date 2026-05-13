# Quick Start Guide: Pronunciation Tests

Get started with pronunciation testing in Speak-AI in 5 minutes!

## Installation

```bash
# Navigate to project root
cd speak-ai

# Install test dependencies
pip install pytest pytest-cov

# (Optional) Install parallel test support
pip install pytest-xdist
```

## Running Tests

### Run all tests
```bash
pytest tests/
```

### Run Hindi tests only
```bash
pytest tests/test_hindi_pronunciation.py -v
```

### Run tests for a specific linguistic feature
```bash
pytest tests/ -k "schwa" -v
pytest tests/ -k "geminate" -v
pytest tests/ -k "vowel_length" -v
```

### View coverage report
```bash
pytest tests/ --cov=tests --cov-report=html
# Opens: htmlcov/index.html
```

## Understanding Test Output

### Passing Test
```
tests/test_hindi_pronunciation.py::TestHindiSchwaDeletion::test_word_final_schwa_deletion_kaam PASSED
```
✓ The G2P output matched the expected phonemes.

### Failing Test
```
AssertionError: Test: Word-final schwa deletion
Text: काम
Notes: Should produce /kaːm/ NOT /kaːmə/
Difference: Expected: /kaːm/, Got: /kaːmə/
```
✗ The G2P output doesn't match expected pronunciation.

### Skipped Test
```
SKIPPED [reason]: Hindi pipeline not available
```
⊗ Test was skipped (likely due to missing language dependencies).

## Common Tasks

### Add a new test case for Hindi
1. Edit `tests/language_data/hindi.json`
2. Add a new test object with:
   - `text`: Hindi word
   - `expected_phonemes`: IPA output
   - `description`: What's being tested
   - `tags`: Categories
3. Run: `pytest tests/test_hindi_pronunciation.py -v`

### Run tests with detailed output
```bash
pytest tests/ -vv --tb=long
```

### Generate test report
```bash
pytest tests/ --junit-xml=report.xml
```

### Run tests in parallel (faster!)
```bash
pytest tests/ -n auto
```

## Troubleshooting

### "Pipeline not available"
The Hindi (or other language) G2P pipeline isn't initialized.

**Solution:**
```bash
pip install misaki  # For Hindi and other languages
```

### "ModuleNotFoundError: No module named 'kokoro'"
The kokoro package isn't installed or in path.

**Solution:**
```bash
# From project root
pip install -e .
# or
pip install kokoro
```

### "Cannot find path '.../tests'"
You're not in the project root directory.

**Solution:**
```bash
cd /path/to/speak-ai
pytest tests/
```

## File Structure

```
tests/
├── test_multilingual_base.py          # Base test classes
├── test_hindi_pronunciation.py        # Hindi tests
├── test_language_template.py          # Template for new languages
├── conftest.py                        # pytest configuration
├── pytest.ini                         # pytest settings
├── run_tests.py                       # Test runner script
├── language_data/
│   ├── hindi.json                     # Hindi test data
│   └── english.json                   # English test data
├── README.md                          # Full documentation
├── CONTRIBUTING.md                    # How to add tests
└── QUICK_START.md                     # This file
```

## Key Concepts

### Test Tags
Tests are organized by linguistic feature:
- `schwa_deletion`: Word-final/medial schwa deletion
- `geminate_consonants`: Doubled consonants
- `vowel_length`: Long vs. short vowels
- `aspiration`: Aspirated vs. unaspirated sounds
- `stress_patterns`: Word stress
- `regression`: Known bug fixes

Find tests by tag:
```bash
pytest tests/ -k "tag_name" -v
```

### IPA Notation
Phonemes are written in IPA (International Phonetic Alphabet):
- `/kaːm/` - slashes for broad transcription
- `:` marks long vowels
- `ˈ` marks primary stress
- `ə` is schwa (neutral vowel)

## Learning More

- **Full documentation**: See [README.md](README.md)
- **Contributing guide**: See [CONTRIBUTING.md](CONTRIBUTING.md)
- **Language template**: See [test_language_template.py](test_language_template.py)

## Tips for Success

1. **Start small**: Run a single test file first
   ```bash
   pytest tests/test_hindi_pronunciation.py::TestHindiSchwaDeletion -v
   ```

2. **Use verbose output**: See exactly what's being tested
   ```bash
   pytest tests/ -vv
   ```

3. **Test locally before pushing**: Catch errors early
   ```bash
   pytest tests/ -v --tb=short
   ```

4. **Check test coverage**: See what's not tested
   ```bash
   pytest tests/ --cov=tests --cov-report=term-missing
   ```

5. **Review documentation**: Tests serve as documentation
   - Read test descriptions
   - Check the "Notes" fields for linguistic explanations
   - Look at JSON test data for patterns

## Next Steps

- ✓ Understand the test framework
- ✓ Run tests for existing languages
- → Read [README.md](README.md) for detailed documentation
- → Check [CONTRIBUTING.md](CONTRIBUTING.md) to add new tests
- → Use [test_language_template.py](test_language_template.py) to add a language

---

**Questions?** See [README.md](README.md#troubleshooting) for troubleshooting.
