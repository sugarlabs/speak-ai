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

"""Generate 18-sentence WAVs for Tier 3 (rw, ay) using MMS-TTS."""
import json
import os
import soundfile as sf
from common import ALL_TIER_3, WAV_DIR, load_corpus
from alt_tts_backends import MMSTTSBackend


def main():
    report = {}

    for lang, name in ALL_TIER_3.items():
        print(f"\n=== {name} ({lang}) ===", flush=True)
        out = os.path.join(WAV_DIR, f"Tier 3 - {name}")
        os.makedirs(out, exist_ok=True)

        try:
            backend = MMSTTSBackend(lang)
        except Exception as e:
            print(f"  SKIP: MMS-TTS unavailable for {lang}: {e}", flush=True)
            continue

        try:
            sents = load_corpus(lang)
        except FileNotFoundError:
            print(f"  SKIP: no corpus for {lang}", flush=True)
            continue

        flat = []
        cat_of = {}
        for cat in ["common", "difficult", "child"]:
            for s in sents[cat]:
                cat_of[len(flat)] = cat
                flat.append(s)

        res = {
            "engine": "mms-tts", "name": name,
            "count": len(flat), "ok": 0, "fail": 0,
            "by_cat": {c: {"n": len(sents[c]), "ok": 0, "fail": 0, "dur": []}
                       for c in ["common", "difficult", "child"]},
            "details": [],
        }

        for i, sent in enumerate(flat):
            cat = cat_of[i]
            wav = os.path.join(out, f"{i + 1:02d}.wav")
            try:
                waveform, sr = backend.synthesize(sent)
                if waveform is None or len(waveform) == 0:
                    res["fail"] += 1
                    res["by_cat"][cat]["fail"] += 1
                    res["details"].append({"i": i + 1, "cat": cat, "text": sent, "err": "empty"})
                    print(f"  [{i + 1:02d}] FAIL: empty audio", flush=True)
                    continue

                sf.write(wav, waveform, sr)
                dur = round(len(waveform) / sr, 3)
                res["ok"] += 1
                res["by_cat"][cat]["ok"] += 1
                res["by_cat"][cat]["dur"].append(dur)
                res["details"].append({
                    "i": i + 1, "cat": cat, "text": sent,
                    "dur": dur, "sr": sr, "wav": f"{i + 1:02d}.wav",
                })
                print(f"  [{i + 1:02d}] {dur:.2f}s @{sr}Hz", flush=True)
            except Exception as e:
                res["fail"] += 1
                res["by_cat"][cat]["fail"] += 1
                res["details"].append({"i": i + 1, "cat": cat, "text": sent, "err": str(e)})
                print(f"  [{i + 1:02d}] ERR: {e}", flush=True)

        for c in res["by_cat"].values():
            d = c.pop("dur")
            if d:
                c["avg"] = round(sum(d) / len(d), 3)

        report[lang] = res
        cats = res["by_cat"]
        print(f"  {res['name']}: {res['ok']}/{res['count']} "
              f"(common={cats['common']['ok']}/{cats['common']['n']} "
              f"difficult={cats['difficult']['ok']}/{cats['difficult']['n']} "
              f"child={cats['child']['ok']}/{cats['child']['n']})", flush=True)

    out_path = os.path.join(os.path.dirname(__file__), "tier3_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    total_ok = sum(r["ok"] for r in report.values())
    total = sum(r["count"] for r in report.values())
    print(f"\nTotal: {total_ok}/{total} WAVs generated")
    print(f"Report: {out_path}")


if __name__ == "__main__":
    main()
