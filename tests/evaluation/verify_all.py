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

"""Verify all week 1-4 work in one pass."""
import os
import soundfile as sf
import numpy as np
from common import TIER_1, TIER_2, WAV_DIR, load_corpus
from kokoro.pipeline import KPipeline

RATE = 24000
PASS = 0
FAIL = 0


def check(label, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        msg = f"  FAIL  {label}"
        if detail:
            msg += f" ({detail})"
        print(msg)


def _check_flat_wav_dir(label, lang_dir, expected):
    """Validate a directory of NN.wav files: count, sample rate, no NaNs.

    Shared by both tiers — the only thing that differs between them is how many
    files to expect and where the directory lives.
    """
    if not os.path.isdir(lang_dir):
        check(f"WAV dir {label}", False, "missing")
        return
    wav_files = sorted(f for f in os.listdir(lang_dir) if f.endswith('.wav'))
    check(f"WAV dir {label}: {len(wav_files)} files", len(wav_files) == expected)

    durations = []
    for wf in wav_files:
        path = os.path.join(lang_dir, wf)
        try:
            data, sr = sf.read(path)
            durations.append(len(data) / sr)
            check(f"  {label}/{wf}: {len(data) / sr:.2f}s {sr}Hz",
                  sr == RATE and len(data) > 0 and not np.any(np.isnan(data)))
        except Exception as e:
            check(f"  {label}/{wf}", False, str(e)[:50])

    # No clip should be wildly longer or shorter than its peers — that usually
    # means a truncated or run-on synthesis.
    if durations:
        median = np.median(durations)
        outliers = [d for d in durations if d > median * 3 or d < median / 3]
        check(f"  {label} duration consistency", len(outliers) == 0,
              f"{len(outliers)} outliers" if outliers else "")


def main():
    # No `global PASS, FAIL` here on purpose: main() only reads the counters
    # for the summary. They are mutated by check() further up, which does
    # declare them global.
    print("=" * 60)
    print("WEEK 1-4 VERIFICATION")
    print("=" * 60)

    # 1. Check corpus files exist and have 18 sentences each
    print("\n--- Corpus Files ---")
    all_langs = {**TIER_1, **TIER_2}
    for lang, info in all_langs.items():
        try:
            sents = load_corpus(lang)
            total = sum(len(v) for v in sents.values())
            has_common = len(sents["common"]) == 10
            has_difficult = len(sents["difficult"]) == 5
            has_child = len(sents["child"]) == 3
            check(f"{info['name']} ({lang}): {total} sentences",
                  total == 18 and has_common and has_difficult and has_child,
                  f"c={len(sents['common'])} d={len(sents['difficult'])} ch={len(sents['child'])}")
        except FileNotFoundError:
            check(f"{info['name']} ({lang}): corpus file", False, "missing")

    # 2. Check pipeline aliases resolve
    print("\n--- Pipeline Aliases ---")
    from kokoro.pipeline import ALIASES, LANG_CODES
    for alias, code in ALIASES.items():
        check(f"Alias {alias} -> {code}", code in LANG_CODES)

    # 3. Check G2P works for all languages
    print("\n--- G2P Functionality ---")
    for code, lang_name in LANG_CODES.items():
        if code in ['a', 'b', 'j', 'z']:
            continue
        try:
            pipe = KPipeline(lang_code=code, model=False)
            # misaki's EspeakG2P hands back a bare phoneme string, while the
            # en/ja/zh G2Ps hand back a (phonemes, extra) tuple. Unpacking
            # blindly shreds the string one character at a time.
            g2p_result = pipe.g2p('hello world')
            ps = g2p_result[0] if isinstance(g2p_result, tuple) else g2p_result
            check(f"G2P {code} ({lang_name})", len(ps) > 0, f"{len(ps)} phonemes")
        except Exception as e:
            check(f"G2P {code} ({lang_name})", False, str(e)[:50])

    # 4. Check WAV files exist and are valid.
    #
    # Two layouts, because the two tiers are generated for different purposes:
    #   Tier 1  -> wav/<lang>/NN.wav              (18 flat files, one voice)
    #   Tier 2  -> wav/crosslingual/<lang>/<voice>/NN.wav
    #              (cross-lingual transfer test: every Kokoro voice family x
    #               the first 5 sentences, so we can score which embedding
    #               carries the language best)
    # Checking Tier 2 against the Tier 1 flat-18 assumption was reporting the
    # cross-lingual WAVs as "missing" even though they exist.
    print("\n--- WAV Files (Tier 1: flat, one voice) ---")
    for lang in TIER_1:
        _check_flat_wav_dir(lang, os.path.join(WAV_DIR, lang), expected=18)

    print("\n--- WAV Files (Tier 2: cross-lingual, per voice) ---")
    for lang in TIER_2:
        lang_dir = os.path.join(WAV_DIR, "crosslingual", lang)
        if not os.path.isdir(lang_dir):
            check(f"crosslingual dir {lang}", False, "missing")
            continue
        voices = sorted(d for d in os.listdir(lang_dir)
                        if os.path.isdir(os.path.join(lang_dir, d)))
        check(f"crosslingual {lang}: {len(voices)} voice families", len(voices) > 0)
        for voice in voices:
            _check_flat_wav_dir(f"{lang}/{voice}",
                                os.path.join(lang_dir, voice), expected=5)

    # Summary
    print("\n" + "=" * 60)
    total = PASS + FAIL
    print(f"RESULTS: {PASS}/{total} passed, {FAIL}/{total} failed")
    print("=" * 60)

    return FAIL == 0


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
