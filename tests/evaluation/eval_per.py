# Speak.activity
# This file is part of Speak.activity
#
# Copyright (C) 2026  NSA Raiyyan <f20241312@pilani.bits-pilani.ac.in>
#
#     Speak.activity is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     Speak.activity is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with Speak.activity.  If not, see <http://www.gnu.org/licenses/>.

"""Phoneme Error Rate over the evaluation corpora.

What this measures, stated precisely, because PER is easy to overclaim.

The reference is a committed snapshot of this project's own G2P output
(reference/<lang>.ipa), not a gold-standard transcription from a linguist. So
a PER of 0% means "the phonemes have not changed since the snapshot was
reviewed", not "the phonemes are correct". That is still the check worth
having on every pull request: the rubric answers whether a language sounds
right, a human answers it slowly, and this answers whether anything moved
underneath that judgement — a phonemizer upgrade, a normalization change, an
edited corpus line — in about a second, with no model weights involved.

Read the two together. Neither replaces the other.

Scope is the eight languages whose G2P actually goes through espeak-ng.
English and Mandarin are excluded because they use misaki's own G2P rather
than espeak, and Kinyarwanda and Aymara because espeak-ng has no voice for
them at all — they reach MMS-TTS with no phoneme stage to measure. That last
one is not an omission; see CONTRIBUTING_LANGUAGES.md on why rw and ay are
not registered as espeak languages.

Usage:

    python tests/evaluation/eval_per.py                    # score everything
    python tests/evaluation/eval_per.py --lang hi          # one language
    python tests/evaluation/eval_per.py --update-reference # re-snapshot
    python tests/evaluation/eval_per.py --json per.json    # machine readable

Re-snapshotting is a deliberate act that belongs in its own reviewed commit,
with the diff of the .ipa files read by someone who can tell an improvement
from a regression. It is not something to run to make a red test go green.
"""

import argparse
import json
import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(__file__))

import espeakng_loader  # noqa: E402
os.environ.setdefault("ESPEAK_DATA_PATH", espeakng_loader.get_data_path())

from common import load_corpus  # noqa: E402

REFERENCE_DIR = os.path.join(os.path.dirname(__file__), "reference")

# BCP-47 code -> the espeak-ng language string misaki's G2P wants. Mirrors
# LANG_CODES in kokoro/pipeline.py; if the two ever disagree this harness is
# measuring a different pipeline than the activity runs.
PER_LANGUAGES = {
    "es": "es",
    "fr": "fr-fr",
    "hi": "hi",
    "pt-br": "pt-br",
    "ar": "ar",
    "sw": "sw",
    "qu": "qu",
    "gn": "gn",
}

CATEGORIES = ("common", "difficult", "child")

# The engineering target from the proposal. A regression check would justify
# 0%, but a little tolerance absorbs an espeak-ng point release retouching a
# handful of allophones without anyone having broken anything.
DEFAULT_THRESHOLD = 0.15


# ---------------------------------------------------------------------------
# phoneme tokenisation
# ---------------------------------------------------------------------------

def phoneme_tokens(ipa):
    """Split an IPA string into phonemes rather than characters.

    Character-level edit distance overcounts: aspiration in /kʰ/ and length in
    /aː/ are modifiers on one phoneme, and treating them as separate symbols
    makes every Hindi aspirate look like two errors instead of one. Combining
    marks (tone, nasalisation) and spacing modifier letters (ʰ ʲ ː ˈ) attach to
    the base symbol they modify.
    """
    tokens = []
    for char in ipa:
        if char.isspace():
            continue
        combining = unicodedata.combining(char) != 0
        modifier = unicodedata.category(char) == 'Lm'
        if tokens and (combining or modifier):
            tokens[-1] += char
        else:
            tokens.append(char)
    return tokens


def levenshtein(a, b):
    """Edit distance between two token sequences.

    Two rolling rows rather than the full matrix: the corpora are short, but
    this also runs per sentence per language on every pull request.
    """
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    previous = list(range(len(b) + 1))
    for i, token_a in enumerate(a, start=1):
        current = [i]
        for j, token_b in enumerate(b, start=1):
            current.append(min(
                previous[j] + 1,                                  # deletion
                current[j - 1] + 1,                               # insertion
                previous[j - 1] + (token_a != token_b),           # substitution
            ))
        previous = current
    return previous[-1]


def phoneme_error_rate(reference_ipa, hypothesis_ipa):
    """PER as edits per reference phoneme.

    An empty reference with a non-empty hypothesis is 1.0 rather than a
    division by zero: everything produced is an error against nothing.
    """
    ref = phoneme_tokens(reference_ipa)
    hyp = phoneme_tokens(hypothesis_ipa)
    if not ref:
        return 0.0 if not hyp else 1.0
    return levenshtein(ref, hyp) / len(ref)


# ---------------------------------------------------------------------------
# corpus plumbing
# ---------------------------------------------------------------------------

def corpus_sentences(lang):
    """Corpus lines in a fixed order, so line N always means the same line."""
    grouped = load_corpus(lang)
    return [(cat, text) for cat in CATEGORIES for text in grouped[cat]]


def phonemize_corpus(lang):
    from misaki.espeak import EspeakG2P
    g2p = EspeakG2P(language=PER_LANGUAGES[lang])
    # EspeakG2P returns a plain string, not the (phonemes, tokens) tuple the
    # kokoro pipeline's g2p returns. Unpacking it silently iterates the string
    # instead, which is what made verify_all.py report failures that were not
    # real for all nine espeak languages.
    return [g2p(text) for _cat, text in corpus_sentences(lang)]


def reference_path(lang):
    return os.path.join(REFERENCE_DIR, f"{lang}.ipa")


def load_reference(lang):
    with open(reference_path(lang), encoding="utf-8") as f:
        return [line.rstrip("\n") for line in f]


def write_reference(lang, phonemes):
    os.makedirs(REFERENCE_DIR, exist_ok=True)
    with open(reference_path(lang), "w", encoding="utf-8") as f:
        for line in phonemes:
            f.write(line + "\n")


# ---------------------------------------------------------------------------
# evaluation
# ---------------------------------------------------------------------------

def evaluate(lang):
    """Per-sentence and aggregate PER for one language.

    The aggregate is total edits over total reference phonemes, not the mean
    of the per-sentence rates. Averaging rates lets one short sentence with
    two errors outweigh a long one that is perfect.
    """
    hypotheses = phonemize_corpus(lang)
    references = load_reference(lang)

    if len(hypotheses) != len(references):
        raise AssertionError(
            f"{lang}: corpus has {len(hypotheses)} sentences but the reference "
            f"has {len(references)}. Re-run with --update-reference and review "
            "the diff before committing it.")

    sentences = []
    total_edits = 0
    total_reference = 0
    for index, (reference, hypothesis) in enumerate(zip(references, hypotheses)):
        ref_tokens = phoneme_tokens(reference)
        edits = levenshtein(ref_tokens, phoneme_tokens(hypothesis))
        total_edits += edits
        total_reference += len(ref_tokens)
        sentences.append({
            "index": index,
            "per": phoneme_error_rate(reference, hypothesis),
            "edits": edits,
            "reference_phonemes": len(ref_tokens),
            "changed": reference != hypothesis,
        })

    return {
        "lang": lang,
        "sentences": sentences,
        "per": (total_edits / total_reference) if total_reference else 0.0,
        "edits": total_edits,
        "reference_phonemes": total_reference,
        "changed_sentences": sum(1 for s in sentences if s["changed"]),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--lang", action="append", choices=sorted(PER_LANGUAGES),
                        help="limit to one language (repeatable)")
    parser.add_argument("--update-reference", action="store_true",
                        help="re-snapshot the reference IPA and exit")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help=f"failing PER (default {DEFAULT_THRESHOLD:.0%})")
    parser.add_argument("--json", metavar="PATH", help="write the full report")
    args = parser.parse_args(argv)

    languages = args.lang or sorted(PER_LANGUAGES)

    if args.update_reference:
        for lang in languages:
            phonemes = phonemize_corpus(lang)
            write_reference(lang, phonemes)
            print(f"{lang:6} wrote {len(phonemes)} lines to "
                  f"{os.path.relpath(reference_path(lang))}")
        print("\nReview the diff before committing. A reference nobody read "
              "is a test that cannot fail.")
        return 0

    report = {}
    failures = []
    print(f"{'lang':6} {'PER':>8} {'edits':>7} {'phonemes':>9}  changed")
    print("-" * 46)
    for lang in languages:
        try:
            result = evaluate(lang)
        except FileNotFoundError:
            print(f"{lang:6} {'no reference':>8} — run --update-reference")
            failures.append(lang)
            continue
        report[lang] = result
        flag = "" if result["per"] <= args.threshold else "  FAIL"
        print(f"{lang:6} {result['per']:>7.2%} {result['edits']:>7} "
              f"{result['reference_phonemes']:>9}  "
              f"{result['changed_sentences']}/{len(result['sentences'])}{flag}")
        if result["per"] > args.threshold:
            failures.append(lang)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\nwrote {args.json}")

    print()
    if failures:
        print(f"FAIL: {', '.join(failures)} above {args.threshold:.0%} PER")
        return 1
    print(f"OK: {len(report)} languages within {args.threshold:.0%} PER")
    return 0


if __name__ == "__main__":
    sys.exit(main())
