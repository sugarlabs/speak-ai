"""Check G2P phoneme coverage for Tier 1 and Tier 2 languages."""
import json
import os
from collections import Counter
from common import TIER_1, TIER_2, load_corpus
from kokoro.pipeline import KPipeline

# what phonemes espeak-ng should produce for each language
EXPECTED = {
    "es": {"ʎ": "ll", "ɲ": "ñ", "ɾ": "r", "ʧ": "ch", "ɣ": "g", "β": "b", "ð": "d"},
    "fr": {"ʁ": "r", "ø": "eu", "œ": "eu", "ə": "e", "ɛ": "è", "ʒ": "j"},
    "hi": {"ʰ": "asp", "ʈ": "ṭ", "ɟ": "j", "ʋ": "v", "ː": "long", "ɡ": "g"},
    "pt-br": {"ɲ": "nh", "ɾ": "r", "ʃ": "ch", "ʒ": "j", "æ": "ã", "ʊ": "u"},
    "zh": {"ʂ": "sh", "ɻ": "r", "ɕ": "x", "ʨ": "j", "ʦ": "z", "↘": "tone4"},
    "ar": {"ʔ": "hamza", "ð": "eth", "ˈ": "stress", "ː": "long"},
    "sw": {"θ": "theta", "ˈ": "stress"},
    "qu": {"q": "uvular", "ʎ": "palatal lateral", "ˈ": "stress"},
    "gn": {"ɾ": "tap", "β": "bilabial", "ˈ": "stress", "ː": "long"},
}

COMBINING = (
    (0x0300, 0x036F), (0x1AB0, 0x1AFF), (0x1DC0, 0x1DFF),
    (0x20D0, 0x20FF), (0xFE20, 0xFE2F),
)


def chars(phonemes):
    """Extract base IPA chars, skipping combining marks."""
    return [c for c in phonemes if c != " "
            and not any(lo <= ord(c) <= hi for lo, hi in COMBINING)]


def main():
    report = {}
    all_tiers = {**TIER_1, **TIER_2}

    for lang, info in all_tiers.items():
        print(f"{info['name']} ({lang})...")
        try:
            pipe = KPipeline(lang_code=info["pl"], model=False)
        except Exception as e:
            print(f"  skip: {e}")
            continue

        try:
            sents = load_corpus(lang)
        except FileNotFoundError:
            print(f"  skip: no corpus")
            continue

        freq = Counter()
        cat_freq = {c: Counter() for c in ["common", "difficult", "child"]}
        results = []
        fails = 0

        for cat in ["common", "difficult", "child"]:
            for i, sent in enumerate(sents[cat]):
                try:
                    ps, _ = pipe.g2p(sent)
                    if ps:
                        cs = chars(ps)
                        for c in cs:
                            freq[c] += 1
                            cat_freq[cat][c] += 1
                        results.append({"i": i+1, "cat": cat, "text": sent,
                                        "phonemes": ps, "n": len(cs)})
                    else:
                        fails += 1
                        results.append({"i": i+1, "cat": cat, "text": sent,
                                        "phonemes": "", "err": "empty"})
                except Exception as e:
                    fails += 1
                    results.append({"i": i+1, "cat": cat, "text": sent,
                                    "phonemes": "", "err": str(e)})

        # check expected phonemes
        found = set(freq.keys())
        exp = EXPECTED.get(lang, {})
        coverage = {}
        for sym, label in exp.items():
            ok = sym in found if len(sym) == 1 else all(c in found for c in sym)
            coverage[sym] = {"label": label, "ok": ok}

        report[lang] = {
            "name": info["name"], "total": sum(len(v) for v in sents.values()),
            "fails": fails, "unique": len(freq),
            "sorted": sorted(freq.keys()),
            "freq": dict(freq.most_common()),
            "coverage": coverage,
            "by_cat": {c: {"n": len(sents[c]), "unique": len(cat_freq[c])}
                       for c in ["common", "difficult", "child"]},
            "details": results,
        }

    # write json
    jp = os.path.join(os.path.dirname(__file__), "g2p_coverage_report.json")
    with open(jp, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # write summary
    sp = os.path.join(os.path.dirname(__file__), "g2p_coverage_summary.txt")
    with open(sp, "w", encoding="utf-8") as f:
        for lang, r in report.items():
            cov = r["coverage"]
            n_ok = sum(1 for v in cov.values() if v["ok"])
            f.write(f"\n=== {r['name']} ({lang}) ===\n")
            f.write(f"  {r['total']} sentences, {r['fails']} failures, {r['unique']} phonemes\n")
            f.write(f"  Expected: {n_ok}/{len(cov)}\n")
            for sym, v in cov.items():
                f.write(f"    {sym} ({v['label']}): {'OK' if v['ok'] else 'MISSING'}\n")
            for cat in ["common", "difficult", "child"]:
                cs = r["by_cat"][cat]
                f.write(f"  {cat}: {cs['n']} sents, {cs['unique']} phonemes\n")
            f.write(f"  Top 10: {', '.join(f'{p}:{c}' for p, c in list(r['freq'].items())[:10])}\n")

    print(f"Report: {jp}")
    print(f"Summary: {sp}")
    for lang, r in report.items():
        cov = r["coverage"]
        n_ok = sum(1 for v in cov.values() if v["ok"])
        print(f"  {r['name']}: {r['unique']} phonemes, expected {n_ok}/{len(cov)}, {r['fails']} fails")


if __name__ == "__main__":
    main()
