#!/usr/bin/env python3
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

"""Fill in the sha256 fields in MANIFEST.json by actually downloading each model.

Hashes in MANIFEST.json are intentionally never hand-written. A hash typed by a
human is a hash nobody verified — it looks authoritative while proving nothing.
This script is the only supported way to populate them: it streams each model
from its pinned URL, computes the digest over exactly the bytes received, and
writes that back. If you didn't run this, the hash isn't real.

By default it only fills entries whose sha256 is currently empty; pass --force
to re-hash everything (e.g. after bumping a model's URL to a new version).

    python scripts/populate_manifest.py
    python scripts/populate_manifest.py --force
    python scripts/populate_manifest.py --only piper_ar,mms_rw

This talks to the network and downloads real, large (60-145 MB) files. It is a
maintainer tool run during community bonding, not something CI or the activity
ever invokes.
"""

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

MANIFEST_PATH = Path(__file__).resolve().parent.parent / "MANIFEST.json"
_CHUNK = 1024 * 1024


def hash_url(url: str) -> str:
    """Stream a URL and return its sha256, without holding it all in memory."""
    digest = hashlib.sha256()
    downloaded = 0
    with urllib.request.urlopen(url, timeout=60) as resp:
        total = int(resp.headers.get('Content-Length') or 0)
        while True:
            chunk = resp.read(_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
            downloaded += len(chunk)
            if total:
                pct = 100 * downloaded / total
                print(f"\r    {downloaded / 1024**2:7.1f} / {total / 1024**2:.1f} MiB "
                      f"({pct:5.1f}%)", end='', flush=True)
    print()
    return digest.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--force', action='store_true',
                    help='re-hash entries that already have a sha256')
    ap.add_argument('--only', default=None,
                    help='comma-separated model names to process')
    ap.add_argument('--manifest', default=str(MANIFEST_PATH))
    args = ap.parse_args()

    with open(args.manifest, 'r', encoding='utf-8') as f:
        data = json.load(f)

    models = data.get('models', {})
    wanted = set(args.only.split(',')) if args.only else None

    changed = 0
    for name, entry in models.items():
        if wanted is not None and name not in wanted:
            continue

        # The primary artefact and every companion file. Hashing only the
        # weights would leave config.json and vocab.json unpinned, and a
        # swapped vocab changes what the model says just as surely as swapped
        # weights would.
        targets = [(name, entry)] + [
            (f"{name}:{extra['filename']}", extra)
            for extra in entry.get('extra_files', [])
        ]

        for label, target in targets:
            if target.get('sha256') and not args.force:
                print(f"[skip] {label} already hashed")
                continue

            print(f"[hash] {label}: {target['url']}")
            try:
                target['sha256'] = hash_url(target['url'])
                print(f"    -> {target['sha256']}")
                changed += 1
            except Exception as e:
                print(f"    FAILED: {e}", file=sys.stderr)

    if changed:
        # Write via a temp file + rename so an interrupted run never leaves a
        # half-written manifest behind.
        tmp = args.manifest + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write('\n')
        os.replace(tmp, args.manifest)
        print(f"\nUpdated {changed} entr{'y' if changed == 1 else 'ies'} in {args.manifest}")
    else:
        print("\nNothing to update.")

    return 0


if __name__ == '__main__':
    sys.exit(main())
