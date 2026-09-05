# Pronunciation Scoring Rubric

Every backend decision in this project is justified by a number, not by "it
sounds better to me." This rubric is how the subjective part — how the audio
actually lands on a native speaker's ear — gets turned into something
comparable across languages and across backends.

## Test corpus

Per language, 18 sentences (`tests/evaluation/corpora/<lang>.txt`):

- **10 common phrases** — everyday classroom language
- **5 difficult-phoneme sentences** — the sounds a cross-lingual or low-resource
  backend is most likely to get wrong (retroflexes for Hindi, ejectives for
  Quechua, emphatic consonants for Arabic, and so on)
- **3 child-targeted sentences** — the register this activity is actually used in

## Scoring rubric

Each generated clip is scored 1–5 on four independent criteria.

| Criterion | 1 — Poor | 3 — Acceptable | 5 — Excellent |
|---|---|---|---|
| **Intelligibility** | Hard to understand | Understandable with effort | Clear and easy |
| **Naturalness** | Robotic / broken | Slightly unnatural rhythm | Near-native flow |
| **Phoneme accuracy** | Multiple errors | 1–2 minor errors | All phonemes correct |
| **Prosody** | Flat monotone | Mostly correct contours | Natural rise/fall |

A clip's score is the mean of the four criteria.

## Decision logic

Backend selection per language follows the mean rubric score:

- **≥ 3.0** — acceptable. The highest-scoring available backend for that
  language wins.
- **< 3.0 on every Kokoro voice family** — Kokoro cross-lingual transfer has
  failed for that language; fall back to Piper (Tier 2) or MMS-TTS (Tier 3).

This is why the preference array in `alt_tts_backends.py` is *configuration*,
not logic: the ordering is set by measured scores, and changing a backend
choice is a one-line data change plus a re-score, not a code change.

## Review checkpoints

Native-speaker review happens at three points (proposal Weeks 2, 6, 11):

| Language | Reviewer source |
|---|---|
| Hindi | Author (native speaker) |
| Arabic | OpenStreetMap Arabic contributors |
| Swahili, Kinyarwanda | Sugar Labs mailing list, Kinyarwanda Wikimedians |
| Quechua, Guarani, Aymara | Community follow-up (documented low-resource limitation) |

## Objective companion metric

Human scoring covers naturalness, which no automated metric captures well. It
is paired with an automated **Phoneme Error Rate** check
(`tests/evaluation/eval_per.py`, gated in CI by `test_per.py`) so that a
phonetic regression trips a test even between native-speaker rounds. The
rubric answers "does it sound right"; PER answers "did the phonemes change".
Both are needed.

```bash
python tests/evaluation/eval_per.py                     # score every language
python tests/evaluation/eval_per.py --lang hi           # one language
python tests/evaluation/eval_per.py --update-reference  # re-snapshot
```

Read the threshold honestly. The reference is a committed snapshot of this
project's own G2P output (`tests/evaluation/reference/<lang>.ipa`), reviewed
when it was taken — not a gold-standard transcription. 0% PER therefore means
"nothing moved since that review", not "the phonemes are correct". Correctness
is what the native-speaker rounds above are for.

Covers the eight languages whose G2P goes through espeak-ng. English and
Mandarin use misaki's own G2P; Kinyarwanda and Aymara have no espeak-ng voice
at all and reach MMS-TTS with no phoneme stage to measure.
