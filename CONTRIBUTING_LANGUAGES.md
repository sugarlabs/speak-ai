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

### Only register a language espeak-ng can actually pronounce

`LANG_CODES` maps to an espeak-ng language id, so this step only makes sense if
espeak-ng *has* that language. Check before you edit anything:

```bash
espeak-ng --voices | grep -i yoruba
```

No row means no G2P, and an alias pointing at a language espeak cannot load is
worse than no alias: it looks registered, routes, and then emits an empty
phoneme string, which the child hears as silence.

**This is why Kinyarwanda (`rw`) and Aymara (`ay`) are not in `ALIASES`.** The
original plan was to register them here — they were the two languages this
whole table was supposed to complete. They cannot be. `espeak-ng --voices` on
the version this project ships lists `qu` (Quechua) and `gn` (Guarani) but has
no entry for Kinyarwanda or Aymara at all. So Quechua and Guarani are
registered and Kinyarwanda and Aymara are not; both instead route straight to
MMS-TTS via `LANGUAGE_BACKEND_PREFERENCE`, which needs no phoneme stage. The
single letters `w` and `y` that were reserved for them went to Swahili and
stayed free respectively.

A Tier 3 language reached only through MMS skips Step 1 entirely. Go to Step 3.

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

Pin the **companion files** too, in `extra_files`. Neither loader takes a lone
weights file: Piper needs the `.onnx.json` beside the `.onnx`, and transformers
needs `config.json`, `vocab.json` and the tokenizer files beside
`model.safetensors`. A swapped vocabulary changes what the model says just as
surely as swapped weights would, so leaving them unpinned defeats the point.
`test_verified_downloads.py` checks that every entry pins what its backend
needs.

## Step 5 — Add a persona

Every language in the palette needs one, or a child can select it and then have
nobody who answers in it. In `personas.json`:

```json
"Ayo (Yorùbá)": {
  "voice": "hf_alpha",
  "lang": "yo",
  "prompt": "..."
}
```

`voice` is required — `activity.py` subscripts it directly — even for Piper and
MMS languages that have no Kokoro embedding to switch to, where it is only a
nominal value. `lang` pins the language so a reply too short to auto-detect
("Sí.") is still spoken by the right voice. `test_personas.py` fails if a
palette language has no persona.

## Step 6 — Text normalization (measure before you write any)

`speech_utils/normalizer.py` composes to NFC, folds apostrophe variants, and
strips invisible joiners. That is deliberately all it does, and the reason is
worth knowing before you add to it: **espeak-ng already handles more than you
expect.** Measured on the version this project ships —

- Hindi word-final schwa is already deleted correctly; appending an explicit
  halant changes nothing on any of 10 test words.
- Numerals are already read in the target language (`42` → बयालीस in Hindi,
  `٣` and `3` identical in Arabic). Expanding them first with `num2words` makes
  Arabic *worse* and is impossible for Hindi, which `num2words` lacks entirely.
- Ejective apostrophes reach the Quechua and Guarani voices as the same
  phonemes whether composed, decomposed, ASCII, U+2019 or U+02BC.

What normalization genuinely fixes is one layer up: the Latin-script hint
matching in `speech.py`. Decomposed Spanish `¿Cómo está usted?` matches no hint
at all and gets read out in English.

So before adding a step here, prove it is needed:

```python
from phonemizer.backend import EspeakBackend
b = EspeakBackend('yo')
print(b.phonemize([raw])[0], b.phonemize([normalized])[0])
```

If those two agree, espeak already handles it and the step is dead code. Record
the finding as a test in `test_normalizer.py` — the ones there pass today
because espeak is correct today, and fail loudly if that changes.

## Step 7 — Verify end to end

```bash
python tests/evaluation/verify_all.py    # corpora, aliases, G2P, WAVs
python tests/evaluation/eval_per.py      # phoneme error rate vs the snapshot
pytest tests/evaluation -q               # full suite
flake8 .                                 # style (uses extend-ignore in .flake8)
```

`verify_all.py` should report 0 failures and your language should appear in the
G2P and WAV sections.

A new espeak-driven language also needs a PER reference. Add it to
`PER_LANGUAGES` in `eval_per.py`, then snapshot it:

```bash
python tests/evaluation/eval_per.py --lang yo --update-reference
```

Read the generated `reference/yo.ipa` before committing it. It becomes the
baseline every future change is measured against, so a snapshot nobody looked
at is a test that cannot fail.

## Deploying offline

Schools image machines once and then run them on a connection that cannot be
relied on. Pre-download the models during imaging rather than letting a child
trigger a 145 MB fetch mid-lesson:

```bash
python scripts/prefetch_models.py --list              # what is available
python scripts/prefetch_models.py --languages ar,sw   # fetch just those
python scripts/prefetch_models.py --all --model-dir /srv/speak-ai
```

The default path is checksum-verified against `MANIFEST.json`. If the manifest
has not been pinned yet, the script says so and `--via-hub` downloads through
HuggingFace instead — unverified, which it warns about every run.

Per-language disk cost beyond the base install: Tier 1 languages are free
(their voices ship inside Kokoro), Piper languages cost ~60 MB each after a
~30 MB one-time engine, and MMS languages cost ~145 MB each after a ~98 MB
one-time `transformers` layer. `--list` prints the real numbers for the
manifest as it stands.

## Checklist

- [ ] espeak-ng actually has a voice for the language (`espeak-ng --voices`)
- [ ] `ALIASES` + `LANG_CODES` entries added, `test_language_aliases.py` green
      (skip for a Tier 3 language that only reaches MMS)
- [ ] 18-sentence corpus at `corpora/<lang>.txt`, native-speaker vetted
- [ ] Cross-lingual + baseline WAVs generated and scored against the rubric
- [ ] Backend chosen by score (≥ 3/5 gate), persona or preference updated
- [ ] Persona added to `personas.json`, `test_personas.py` green
- [ ] Model + companion files pinned in `MANIFEST.json` with real hashes
- [ ] Normalization added **only** if measurement showed espeak needs it
- [ ] PER reference snapshotted and read before committing
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
