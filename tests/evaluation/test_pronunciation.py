"""Generate WAV files for Tier 1 languages using Kokoro TTS."""
import json
import os
import soundfile as sf
from common import TIER_1, WAV_DIR, load_corpus
from kokoro.pipeline import KPipeline

RATE = 24000


def main():
    report = {}
    model = None
    total = 18 * len(TIER_1)
    done = 0

    for lang, info in TIER_1.items():
        print(f"\n=== {info['name']} ({lang}) ===")
        out = os.path.join(WAV_DIR, lang)
        os.makedirs(out, exist_ok=True)

        if model is None:
            pipe = KPipeline(lang_code=info["pl"], model=True, device="cpu")
            model = pipe.model
        else:
            pipe = KPipeline(lang_code=info["pl"], model=model, device="cpu")

        try:
            sents = load_corpus(lang)
        except FileNotFoundError:
            print(f"  SKIP: no corpus for {lang}")
            continue

        # flatten sentences and track which category each belongs to
        flat = []
        cat_of = {}
        for cat in ["common", "difficult", "child"]:
            for s in sents[cat]:
                cat_of[len(flat)] = cat
                flat.append(s)

        res = {
            "voice": info["voice"], "name": info["name"],
            "count": len(flat), "ok": 0, "fail": 0,
            "by_cat": {c: {"n": len(sents[c]), "ok": 0, "fail": 0, "dur": []}
                       for c in ["common", "difficult", "child"]},
            "details": [],
        }

        for i, sent in enumerate(flat):
            cat = cat_of[i]
            wav = os.path.join(out, f"{i+1:02d}.wav")
            try:
                for r in pipe(sent, voice=info["voice"]):
                    if r.audio is None:
                        continue
                    audio = r.audio.cpu().numpy()
                    if len(audio) == 0:
                        break
                    sf.write(wav, audio, RATE)
                    dur = round(len(audio) / RATE, 3)
                    res["ok"] += 1
                    res["by_cat"][cat]["ok"] += 1
                    res["by_cat"][cat]["dur"].append(dur)
                    res["details"].append({
                        "i": i+1, "cat": cat, "text": sent,
                        "phonemes": r.phonemes, "dur": dur,
                        "wav": f"{i+1:02d}.wav",
                    })
                    done += 1
                    print(f"  [{i+1:02d}] {dur:.2f}s ({done*100//total}%)")
                    break
                else:
                    res["fail"] += 1
                    res["by_cat"][cat]["fail"] += 1
                    res["details"].append({"i": i+1, "cat": cat, "text": sent, "err": "no_audio"})
                    print(f"  [{i+1:02d}] FAIL")
            except Exception as e:
                res["fail"] += 1
                res["by_cat"][cat]["fail"] += 1
                res["details"].append({"i": i+1, "cat": cat, "text": sent, "err": str(e)})
                print(f"  [{i+1:02d}] ERR: {e}")

        # avg durations
        for c in res["by_cat"].values():
            d = c.pop("dur")
            if d:
                c["avg"] = round(sum(d)/len(d), 3)

        report[lang] = res

    out_path = os.path.join(os.path.dirname(__file__), "pronunciation_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nReport: {out_path}\n")
    for lang, r in report.items():
        cats = r["by_cat"]
        print(f"  {r['name']}: {r['ok']}/{r['count']} "
              f"(common={cats['common']['ok']}/{cats['common']['n']} "
              f"difficult={cats['difficult']['ok']}/{cats['difficult']['n']} "
              f"child={cats['child']['ok']}/{cats['child']['n']})")


if __name__ == "__main__":
    main()
