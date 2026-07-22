# -*- coding: utf-8 -*-
"""
Test Hindi G2P: validates phoneme output AND Kokoro model compatibility.
Writes results to test_results.txt.

Run: python test_g2p_hindi.py
"""

import importlib.util
import os
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    "hindi_g2p", os.path.join(script_dir, "kokoro", "hindi_g2p.py")
)
hindi_g2p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hindi_g2p)
HindiG2P = hindi_g2p.HindiG2P
transliterate = hindi_g2p.transliterate

OUTPUT_FILE = os.path.join(script_dir, "test_results.txt")

# Exact vocab from Kokoro-82M config.json
KOKORO_VOCAB = set(';:,.!?\u2014\u2026"()\u201c\u201d \u0303\u02a3\u02a5\u02a6\u02a8\u1d5d\uab67AIoQSTWY\u1d4aabcdefhijklmnopqrstuvwxyz\u0251\u0250\u0252\xe6\u03b2\u0254\u0255\xe7\u0256\xf0\u02a4\u0259\u025a\u025b\u025c\u025f\u0261\u0265\u0268\u026a\u029d\u026f\u0270\u014b\u0273\u0272\u0274\xf8\u0278\u03b8\u0153\u0279\u027e\u027b\u0281\u027d\u0282\u0283\u0288\u02a7\u028a\u028b\u028c\u0263\u0264\u03c7\u028e\u0292\u0294\u02c8\u02cc\u02d0\u02b0\u02b2\u2193\u2192\u2197\u2198\u1d7b')

HINDI_SENTENCES = [
    ("\u0928\u092e\u0938\u094d\u0924\u0947", "namaste"),
    ("\u0906\u092a \u0915\u0948\u0938\u0947 \u0939\u0948\u0902?", "aap kaise hain?"),
    ("\u092e\u0947\u0930\u093e \u0928\u093e\u092e \u0930\u093e\u0939\u0941\u0932 \u0939\u0948\u0964", "mera naam Rahul hai"),
    ("\u092d\u093e\u0930\u0924 \u090f\u0915 \u092e\u0939\u093e\u0928 \u0926\u0947\u0936 \u0939\u0948\u0964", "Bharat ek mahan desh hai"),
    ("\u0906\u091c \u092e\u094c\u0938\u092e \u092c\u0939\u0941\u0924 \u0905\u091a\u094d\u091b\u093e \u0939\u0948\u0964", "aaj mausam bahut achha hai"),
    ("\u0915\u0943\u092a\u092f\u093e \u092e\u0941\u091d\u0947 \u092a\u093e\u0928\u0940 \u0926\u0940\u091c\u093f\u090f\u0964", "kripaya mujhe paani dijie"),
]


def run_tests(out):
    out.write("Hindi G2P Test Suite\n")
    out.write("=" * 60 + "\n\n")

    g2p = HindiG2P()
    all_ok = True

    # TEST 1: Sentence transliteration
    out.write("TEST 1: Sentence transliteration\n")
    out.write("-" * 40 + "\n")
    for sentence, roman in HINDI_SENTENCES:
        phonemes, _ = g2p(sentence)
        out.write(f"  [{roman}]\n")
        out.write(f"  Input:    {sentence}\n")
        out.write(f"  Phonemes: {phonemes}\n")
        out.write(f"  Length:   {len(phonemes)}\n\n")

    # TEST 2: Kokoro vocab compatibility (THE KEY TEST)
    out.write("=" * 60 + "\n")
    out.write("TEST 2: Kokoro model vocab compatibility\n")
    out.write("-" * 40 + "\n")
    for sentence, roman in HINDI_SENTENCES:
        phonemes, _ = g2p(sentence)
        bad_chars = []
        for ch in phonemes:
            if ch not in KOKORO_VOCAB:
                bad_chars.append((ch, hex(ord(ch))))
        if bad_chars:
            out.write(f"  FAIL  [{roman}]\n")
            for ch, code in bad_chars:
                out.write(f"         Unknown char: '{ch}' ({code})\n")
            all_ok = False
        else:
            out.write(f"  PASS  [{roman}] - all {len(phonemes)} chars in vocab\n")

    out.write("\n")

    # TEST 3: Halant handling
    out.write("=" * 60 + "\n")
    out.write("TEST 3: Halant (virama) and matra handling\n")
    out.write("-" * 40 + "\n")
    cases = [
        ("\u0915\u094d\u0924", "kt cluster"),
        ("\u0915\u093e", "kaa matra"),
        ("\u0915\u093f", "ki matra"),
        ("\u0915\u0942", "kuu matra"),
        ("\u0915\u0947", "ke matra"),
        ("\u0915\u094b", "ko matra"),
    ]
    for text, desc in cases:
        result = transliterate(text)
        bad = [ch for ch in result if ch not in KOKORO_VOCAB]
        status = "PASS" if not bad else "FAIL"
        if bad:
            all_ok = False
        out.write(f"  {status}  '{text}' -> '{result}' [{desc}]\n")

    # SUMMARY
    out.write("\n" + "=" * 60 + "\n")
    if all_ok:
        out.write("ALL TESTS PASSED - Output is Kokoro TTS compatible!\n")
    else:
        out.write("SOME TESTS FAILED - Output contains chars not in Kokoro vocab\n")
    out.write("=" * 60 + "\n")
    return all_ok


if __name__ == "__main__":
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        success = run_tests(f)
    try:
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            print(f.read())
    except UnicodeEncodeError:
        print(f"Results written to {OUTPUT_FILE}")
    sys.exit(0 if success else 1)
