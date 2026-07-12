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


def main():
    global PASS, FAIL
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
            ps, _ = pipe.g2p('hello world')
            check(f"G2P {code} ({lang_name})", len(ps) > 0, f"{len(ps)} phonemes")
        except Exception as e:
            check(f"G2P {code} ({lang_name})", False, str(e)[:50])

    # 4. Check WAV files exist and are valid
    print("\n--- WAV Files ---")
    for lang, info in all_langs.items():
        lang_dir = os.path.join(WAV_DIR, lang)
        if not os.path.isdir(lang_dir):
            check(f"WAV dir {lang}", False, "missing")
            continue
        wav_files = sorted([f for f in os.listdir(lang_dir) if f.endswith('.wav')])
        check(f"WAV dir {lang}: {len(wav_files)} files", len(wav_files) == 18)

        # Check each WAV
        durations = []
        for wf in wav_files:
            path = os.path.join(lang_dir, wf)
            try:
                data, sr = sf.read(path)
                dur = len(data) / sr
                durations.append(dur)
                check(f"  {lang}/{wf}: {dur:.2f}s {sr}Hz",
                      sr == RATE and len(data) > 0 and not np.any(np.isnan(data)))
            except Exception as e:
                check(f"  {lang}/{wf}", False, str(e)[:50])

        # Check duration consistency (no outliers > 3x median)
        if durations:
            median = np.median(durations)
            outliers = [d for d in durations if d > median * 3 or d < median / 3]
            check(f"  {lang} duration consistency", len(outliers) == 0,
                  f"{len(outliers)} outliers" if outliers else "")

    # Summary
    print("\n" + "=" * 60)
    total = PASS + FAIL
    print(f"RESULTS: {PASS}/{total} passed, {FAIL}/{total} failed")
    print("=" * 60)

    return FAIL == 0


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
