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

"""Shared evaluation utilities."""
import os
import sys

# espeak-ng data path — needed before any phonemizer imports
import espeakng_loader
os.environ["ESPEAK_DATA_PATH"] = espeakng_loader.get_data_path()

# project root for kokoro imports
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

CORPORA_DIR = os.path.join(os.path.dirname(__file__), "corpora")
WAV_DIR = os.path.join(os.path.dirname(__file__), "wav")

TIER_1 = {
    "es": {"pl": "e", "voice": "ef_dora", "name": "Spanish"},
    "fr": {"pl": "f", "voice": "ff_siwis", "name": "French"},
    "hi": {"pl": "h", "voice": "hf_alpha", "name": "Hindi"},
    "pt-br": {"pl": "p", "voice": "pf_dora", "name": "Portuguese BR"},
    "zh": {"pl": "z", "voice": "zf_xiaoxiao", "name": "Mandarin"},
}

TIER_2 = {
    "ar": {"pl": "r", "voice": "hf_alpha", "name": "Arabic"},
    "sw": {"pl": "w", "voice": "hf_alpha", "name": "Swahili"},
    "qu": {"pl": "q", "voice": "hf_alpha", "name": "Quechua"},
    "gn": {"pl": "g", "voice": "hf_alpha", "name": "Guarani"},
}

TIER_3 = {
    "rw": {"pl": None, "voice": None, "name": "Kinyarwanda"},
    "ay": {"pl": None, "voice": None, "name": "Aymara"},
}

ALL_TIER_3 = {"rw": "Kinyarwanda", "ay": "Aymara"}

ALL_VOICES = ["af_heart", "ef_dora", "ff_siwis", "hf_alpha", "pf_dora", "zf_xiaoxiao"]


def load_corpus(lang_code):
    """Read corpus file, return sentences grouped by category."""
    path = os.path.join(CORPORA_DIR, f"{lang_code}.txt")
    grouped = {"common": [], "difficult": [], "child": []}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "|" not in line:
                continue
            cat, text = line.split("|", 1)
            cat = cat.strip()
            if cat in grouped:
                grouped[cat].append(text.strip())
    return grouped
