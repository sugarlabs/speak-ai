"""Test cross-lingual voice transfer for Tier 2 languages (ar, sw, qu, gn)."""
import json
import os
import soundfile as sf
from common import TIER_2, ALL_VOICES, WAV_DIR, load_corpus
from kokoro.pipeline import KPipeline

RATE = 24000


def main():
    report = {}
    model = None
    pipe = None

    for lang, info in TIER_2.items():
        print(f"\n=== {info['name']} ({lang}) ===")
        lang_out = os.path.join(WAV_DIR, "crosslingual", lang)
        os.makedirs(lang_out, exist_ok=True)

        try:
            sents = load_corpus(lang)
        except FileNotFoundError:
            print(f"  SKIP: no corpus for {lang}")
            continue

        flat = []
        cat_of = {}
        for cat in ["common", "difficult", "child"]:
            for s in sents[cat]:
                cat_of[len(flat)] = cat
                flat.append(s)

        test_sents = flat[:5]
        test_cats = [cat_of[i] for i in range(5)]

        lang_report = {
            "name": info["name"], "voices": {},
            "by_cat": {c: {"n": len(sents[c])} for c in ["common", "difficult", "child"]},
        }

        for voice in ALL_VOICES:
            print(f"\n  Voice: {voice}")
            voice_out = os.path.join(lang_out, voice)
            os.makedirs(voice_out, exist_ok=True)

            if model is None:
                pipe = KPipeline(lang_code=info["pl"], model=True, device="cpu")
                model = pipe.model
            elif pipe is None or pipe.lang_code != info["pl"]:
                pipe = KPipeline(lang_code=info["pl"], model=model, device="cpu")

            voice_res = {"ok": 0, "fail": 0, "details": []}

            for i, sent in enumerate(test_sents):
                cat = test_cats[i]
                wav = os.path.join(voice_out, f"{i+1:02d}.wav")
                try:
                    for r in pipe(sent, voice=voice):
                        if r.audio is None:
                            continue
                        audio = r.audio.cpu().numpy()
                        if len(audio) == 0:
                            break
                        sf.write(wav, audio, RATE)
                        dur = round(len(audio) / RATE, 3)
                        voice_res["ok"] += 1
                        voice_res["details"].append({
                            "i": i+1, "cat": cat, "text": sent,
                            "phonemes": r.phonemes, "dur": dur,
                        })
                        print(f"    [{i+1}] {dur:.2f}s OK")
                        break
                    else:
                        voice_res["fail"] += 1
                        voice_res["details"].append({"i": i+1, "cat": cat, "text": sent, "err": "no_audio"})
                        print(f"    [{i+1}] FAIL")
                except Exception as e:
                    voice_res["fail"] += 1
                    voice_res["details"].append({"i": i+1, "cat": cat, "text": sent, "err": str(e)})
                    print(f"    [{i+1}] ERR: {e}")

            lang_report["voices"][voice] = voice_res
            total = voice_res["ok"] + voice_res["fail"]
            print(f"  {voice}: {voice_res['ok']}/{total}")

        report[lang] = lang_report

    out_path = os.path.join(os.path.dirname(__file__), "crosslingual_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nReport: {out_path}\n")
    for lang, r in report.items():
        print(f"  {r['name']}:")
        for voice, res in r["voices"].items():
            total = res["ok"] + res["fail"]
            print(f"    {voice}: {res['ok']}/{total}")


if __name__ == "__main__":
    main()
