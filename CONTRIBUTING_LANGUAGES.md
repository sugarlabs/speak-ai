# Adding a Language to Speak-AI

This guide is for adding a new language to the multilingual TTS pipeline. It
exists so that adding the *next* language — Yoruba, Amharic, Bengali, whatever
a classroom needs — does not require reverse-engineering the whole system
first.

The guiding rule of this pipeline: **quality of pronunciation is the priority,
and every backend decision is made by measurement, not assumption.** A language
that sounds worse than the existing espeak fallback should not ship until it
sounds better.

## The three tiers

A language falls into one of three tiers by how much support already exists.
The tier decides the backend, and the backend decides the work.

| Tier | Support | Backend | Example languages |
|---|---|---|---|
| 1 | Full Kokoro voice + G2P | Kokoro (neural) | Spanish, French, Hindi, Mandarin, Portuguese |
| 2 | espeak G2P, no Kokoro voice | Kokoro cross-lingual *or* Piper | Arabic, Swahili, Kinyarwanda |
| 3 | No Kokoro coverage at all | MMS-TTS (VITS) | Quechua, Guarani, Aymara |

You find out which tier a *new* language is in by testing, below — you do not
assume it.

## Step 1 — Register the language

In `kokoro/pipeline.py`, add the language to both `ALIASES` and `LANG_CODES`.
`ALIASES` maps a BCP-47 tag to Kokoro's single-letter code; `LANG_CODES` maps
that letter back to the espeak language id.

```python
ALIASES = {
    # ...
    'yo': 'y',   # Yoruba  (pick an unused single letter)
}
LANG_CODES = dict(
    # ...
    y='yo',      # Yoruba -> espeak-ng G2P
)
```

The single-letter code must be unused. `test_language_aliases.py` enforces this
— it fails if two languages collide on one code, or if an alias has no matching
`LANG_CODES` entry. Run it after editing:

```bash
pytest tests/evaluation/test_language_aliases.py -q
```

This test imports **no** torch, so it is the same check CI runs on every PR.

## Step 2 — Write a test corpus

Create `tests/evaluation/corpora/<lang>.txt` with 18 sentences:

- 10 common classroom phrases
- 5 sentences loaded with the language's difficult phonemes (the sounds a
  cross-lingual backend is most likely to mangle)
- 3 sentences in the register a 10-year-old actually uses

A native speaker should write or at least vet these. They are the ground truth
everything downstream is scored against.

## Step 3 — Decide the backend by measurement

This is the step that matters. Do **not** guess whether Kokoro cross-lingual
transfer will work — generate audio and score it.

```bash
# generate cross-lingual candidates across every Kokoro voice family
python tests/evaluation/test_crosslingual.py

# generate the espeak baseline to beat
python tests/evaluation/test_pronunciation.py
```

Score the output against `tests/evaluation/rubric.md` (1–5 on intelligibility,
naturalness, phoneme accuracy, prosody), ideally with a native speaker.

Decision logic:

- **Any Kokoro voice family scores ≥ 3/5** → Tier 1/2, use Kokoro with that
  voice. Add a persona in `personas.json` pointing at the winning voice.
- **Every Kokoro family scores < 3/5** → the language needs a dedicated
  backend. Register a Piper voice (Tier 2) or an MMS-TTS checkpoint (Tier 3)
  in `alt_tts_backends.py`, and flip the preference order for that language:

  ```python
  # in alt_tts_backends.py — configuration, not logic
  'yo': ['piper', 'primary'],   # or ['mms', 'primary']
  ```

The preference arrays are deliberately data, not code: a backend choice is a
one-line change plus a re-score, never a rewrite.

## Step 4 — Pin the model (Tier 2 / Tier 3 only)

If the language needs a downloaded model, add it to `MANIFEST.json` with a real
SHA-256. Do not hand-write the hash — generate it:

```bash
python scripts/populate_manifest.py   # downloads, hashes, rewrites MANIFEST.json
```

`ModelManager` refuses to install any entry whose `sha256` is not a valid
64-char hex digest, so an unverified model cannot ship by accident. Updating a
model later is a reviewed PR that changes `url`, `sha256`, and
`upstream_version` together — there is no auto-update, because a surprise
download mid-lesson on a school connection is not acceptable.

## Step 5 — Text normalization (if the script needs it)

If the language uses a script with special handling — numerals that must be
spelled out, combining characters that need NFC normalization, ejective
apostrophes — add it to the normalizer before it reaches G2P. Extended-Latin
languages (Quechua, Guarani, Aymara) in particular need NFC normalization or
the tokenizer splits ejectives incorrectly and the G2P output is garbage.

## Step 6 — Verify end to end

```bash
python tests/evaluation/verify_all.py    # corpora, aliases, G2P, WAVs
pytest tests/evaluation -q               # full suite
flake8 .                                 # style (uses extend-ignore in .flake8)
```

`verify_all.py` should report 0 failures and your language should appear in the
G2P and WAV sections.

## Checklist

- [ ] `ALIASES` + `LANG_CODES` entries added, `test_language_aliases.py` green
- [ ] 18-sentence corpus at `corpora/<lang>.txt`, native-speaker vetted
- [ ] Cross-lingual + baseline WAVs generated and scored against the rubric
- [ ] Backend chosen by score (≥ 3/5 gate), persona or preference updated
- [ ] Model pinned in `MANIFEST.json` with a real hash (if downloaded)
- [ ] Normalization added if the script needs it
- [ ] `verify_all.py` clean, full suite green, flake8 clean
- [ ] One small, reviewable PR — not a mega-commit

## Why the fallback chain matters

Kokoro is language-agnostic at the acoustic level: it turns IPA phonemes plus a
voice embedding into audio. Feed it Arabic phonemes with a Spanish voice
embedding and it does not produce Arabic-with-an-accent — it produces sound
that does not resemble a language, because the embedding, not the phonemes,
carries what the language is supposed to sound like. That is why Tier 2 and
Tier 3 languages genuinely need Piper / MMS, and why the fallback chain is not
optional decoration. When in doubt, measure, and let the score decide.
