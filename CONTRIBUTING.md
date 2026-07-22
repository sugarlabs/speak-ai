# Contributing to Speak-AI

Thank you for your interest in contributing to Speak-AI!
This guide will help you get started quickly.

## Setting Up the Development Environment

1. Fork and clone the repository
```
   git clone https://github.com/YOUR_USERNAME/speak-ai.git
   cd speak-ai
```

2. Create a virtual environment
```
   python -m venv venv
```

3. Activate it
   - Windows: `venv\Scripts\activate`
   - Linux/Mac: `source venv/bin/activate`

4. Install dependencies
```
   pip install -r requirements.txt
```

5. Connect to the upstream repository
```
   git remote add upstream https://github.com/sugarlabs/speak-ai.git
```

## Making Changes

Always create a new branch for your changes:
```
git checkout -b your-branch-name
```

Branch naming conventions:
- `feat/` — new features
- `fix/` — bug fixes
- `docs/` — documentation changes
- `refactor/` — code improvements

## Commit Message Format

Follow this format for commit messages:
```
type: short description

Longer explanation if needed.
```

Examples:
- `feat: add Spanish language support`
- `fix: handle missing voice model gracefully`
- `docs: update README with setup instructions`

## Submitting a Pull Request

1. Sync with upstream before opening a PR
```
   git fetch upstream
   git rebase upstream/main
```

2. Push your branch
```
   git push origin your-branch-name
```

3. Open a Pull Request against `sugarlabs/speak-ai:main`

4. Fill in the PR title and description clearly —
   explain what problem your change solves

## Adding a New TTS Language

To add support for a new language in the Kokoro pipeline:

1. Add the language mapping in `speech.py`:
```python
   SUGAR_TO_KOKORO = {
       'en': 'a',   # English
       'hi': 'h',   # Hindi
       'es': 'e',   # Spanish  ← add new entries here
   }
```

2. Verify the language is supported by the Kokoro model

3. Add the language to `LANG_CODES` in
   `kokoro/pipeline.py`

4. Test audio output quality for the new language

5. Update this guide with the new language entry

## Communication Channels

- **Matrix**: #sugar on matrix.org
- **Mailing list**: sugar-devel@lists.sugarlabs.org
- **GitHub Issues**: for bug reports and feature requests

## Code Style

- Follow PEP 8 for Python code
- Add docstrings to new functions and methods
- Write clear commit messages
- Include comments for complex logic

## Getting Help

If you are stuck, ask in the Matrix channel or open
a GitHub issue. The community is friendly and happy
to help new contributors.
```

---

🔴 **Step 5 — Commit**

Commit message:
```
docs: add CONTRIBUTING.md with setup and language guide
```

Description:
```
Speak-AI lacked a contributor guide, making it harder 
for new contributors to get started.

This PR adds CONTRIBUTING.md covering:
- Development environment setup
- Branch naming and commit message conventions
- PR submission process
- Step-by-step guide for adding a new TTS language
- Communication channels and code style guidelines

No functional changes. Documentation only.
