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

"""Bulk-download voice models ahead of deployment, for school sysadmins.

The activity downloads a language's model the first time a child selects it.
That is the right behaviour on a laptop with a connection and the wrong one in
a classroom, where the connection is shared, slow, or absent, and where the
download would happen in the middle of a lesson for thirty machines at once.

Run this once while imaging, over whatever connection the school actually has,
and the models are on disk before the first child opens the activity.

    python scripts/prefetch_models.py --list
    python scripts/prefetch_models.py --languages ar,sw
    python scripts/prefetch_models.py --all
    python scripts/prefetch_models.py --languages qu --model-dir /srv/speak-ai

Point --model-dir at the image's model directory, or set SPEAK_AI_MODEL_DIR;
both are read the same way the activity reads them, so what this writes is
what it will later find.

Two paths, and the difference matters:

  * The manifest path is the default and is verified. Every file is checked
    against its pinned sha256 and installed atomically.
  * --via-hub warms the HuggingFace cache instead, by loading each backend
    exactly as the activity would. Use it when the manifest has not been
    pinned yet. It is NOT checksum-verified — it inherits whatever trust you
    place in the hub — so it is opt-in and says so every time it runs.
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from model_manager import ModelManager  # noqa: E402

# Language -> the manifest entries that language needs. A language with no
# entry is served by Kokoro or espeak and costs nothing extra on disk.
LANGUAGE_MODELS = {
    'ar': ['piper_ar'],
    'sw': ['piper_sw'],
    'hi': ['piper_hi'],
    'rw': ['mms_rw'],
    'qu': ['mms_qu'],
    'gn': ['mms_gn'],
    'ay': ['mms_ay'],
}

BUNDLED = {
    'en-us': 'Kokoro (bundled)',
    'es': 'Kokoro (bundled)',
    'fr': 'Kokoro (bundled)',
    'pt-br': 'Kokoro (bundled)',
    'zh': 'Kokoro (bundled)',
}


def entry_size_mb(entry):
    """Declared size of a manifest entry, companions included."""
    total = entry.get('size_mb', 0.0)
    # Companion files are configs and vocabularies — kilobytes against a
    # 145 MB checkpoint — so an unstated size is 0, not a guess.
    for extra in entry.get('extra_files', []):
        total += extra.get('size_mb', 0.0)
    return total


def cmd_list(mm):
    print(f"Model directory: {mm.model_dir}")
    print(f"Detected RAM:    {mm.available_ram_mb} MB "
          f"({'neural TTS enabled' if mm.neural_allowed else 'espeak only'})")
    print()
    print(f"{'lang':6} {'model':10} {'size':>9}  status")
    print("-" * 48)

    for lang, label in sorted(BUNDLED.items()):
        print(f"{lang:6} {'-':10} {'0 MB':>9}  {label}")

    for lang, names in sorted(LANGUAGE_MODELS.items()):
        for name in names:
            entry = mm.manifest.get(name)
            if entry is None:
                print(f"{lang:6} {name:10} {'?':>9}  not in MANIFEST.json")
                continue
            size = f"{entry_size_mb(entry):.0f} MB"
            if mm.is_cached(name):
                status = "cached"
            elif not entry.get('sha256'):
                status = "unpinned — see --via-hub"
            else:
                status = "not downloaded"
            print(f"{lang:6} {name:10} {size:>9}  {status}")
    return 0


def prefetch_verified(mm, names):
    ok, failed = [], []
    for name in names:
        entry = mm.manifest.get(name)
        if entry is None:
            print(f"[skip] {name}: not in MANIFEST.json")
            failed.append(name)
            continue

        if mm.is_cached(name):
            print(f"[have] {name}")
            ok.append(name)
            continue

        if not entry.get('sha256'):
            print(f"[skip] {name}: no pinned sha256 — a maintainer must run "
                  f"scripts/populate_manifest.py first, or use --via-hub")
            failed.append(name)
            continue

        print(f"[get ] {name} ({entry_size_mb(entry):.0f} MB) ...", flush=True)
        if mm.get_dir(name) is not None:
            print(f"[ok  ] {name}")
            ok.append(name)
        else:
            print(f"[FAIL] {name}: see ~/.local/share/speak-ai/download_errors.log")
            failed.append(name)
    return ok, failed


def prefetch_via_hub(languages):
    """Warm the HuggingFace cache by building each backend, as the activity does.

    No checksum verification happens here — this is the same trust model the
    activity runs under today, moved earlier in time. That is the entire
    benefit: the download stops happening during a lesson.
    """
    print("WARNING: --via-hub downloads without checksum verification.")
    print("         Pin the manifest (scripts/populate_manifest.py) to get")
    print("         verified, atomic installs instead.")
    print()

    from alt_tts_backends import get_tts_backend

    ok, failed = [], []
    for lang in languages:
        backend = get_tts_backend(lang)
        if backend is None:
            print(f"[skip] {lang}: served by Kokoro or espeak, nothing to fetch")
            continue
        print(f"[get ] {lang} via {type(backend).__name__} ...", flush=True)
        try:
            backend._ensure_loaded()
            # Synthesize once: loading the weights is not the same as proving
            # the tokenizer and config are usable, and finding that out here
            # is much cheaper than finding it out in a classroom.
            waveform, _sr = backend.synthesize("test")
            if waveform is None or len(waveform) == 0:
                raise RuntimeError("backend produced no audio")
            print(f"[ok  ] {lang}")
            ok.append(lang)
        except Exception as e:
            print(f"[FAIL] {lang}: {e}")
            failed.append(lang)
    return ok, failed


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--languages',
                        help='comma-separated language codes, e.g. ar,sw,qu')
    parser.add_argument('--all', action='store_true',
                        help='every language with a downloadable model')
    parser.add_argument('--list', action='store_true',
                        help='show what is available and what is already cached')
    parser.add_argument('--model-dir',
                        help='where to install (default: $SPEAK_AI_MODEL_DIR '
                             'or ~/.local/share/speak-ai/models)')
    parser.add_argument('--via-hub', action='store_true',
                        help='download through HuggingFace without checksum '
                             'verification, for an unpinned manifest')
    args = parser.parse_args(argv)

    if args.model_dir:
        os.environ['SPEAK_AI_MODEL_DIR'] = args.model_dir
    mm = ModelManager(model_dir=args.model_dir)

    if args.list or not (args.languages or args.all):
        return cmd_list(mm)

    if args.all:
        languages = sorted(LANGUAGE_MODELS)
    else:
        languages = [code.strip() for code in args.languages.split(',')
                     if code.strip()]

    unknown = [c for c in languages if c not in LANGUAGE_MODELS and c not in BUNDLED]
    if unknown:
        parser.error(f"unknown language(s): {', '.join(unknown)}. "
                     f"Known: {', '.join(sorted(LANGUAGE_MODELS) + sorted(BUNDLED))}")

    if not mm.neural_allowed:
        print(f"NOTE: this machine reports {mm.available_ram_mb} MB RAM, below "
              f"the neural threshold.")
        print("      The activity will use espeak-ng here regardless of what "
              "is downloaded.")
        print("      Continuing anyway, since you are probably imaging for "
              "different hardware.")
        print()
        mm.neural_allowed = True

    if args.via_hub:
        ok, failed = prefetch_via_hub(languages)
    else:
        names = [n for lang in languages for n in LANGUAGE_MODELS.get(lang, [])]
        ok, failed = prefetch_verified(mm, names)

    print()
    print(f"Installed: {len(ok)}   Failed: {len(failed)}")
    print(f"Model directory now holds {mm.disk_usage_mb():.0f} MB "
          f"({mm.free_disk_mb():.0f} MB free)")
    if failed:
        print(f"Failed: {', '.join(failed)}")
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
