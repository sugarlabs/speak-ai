# Copyright (C) 2025
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

"""
Centralized language configuration for Speak-AI multilingual TTS support.

This module provides:
- Mapping between Kokoro voice prefixes and language codes
- Language metadata (display names, scripts, G2P requirements)
- Helper utilities for language detection from voice names
- Organized voice registry grouped by language

Kokoro voice naming convention:
    <lang_code><gender>_<name>
    - lang_code: single letter (a=American English, b=British English, etc.)
    - gender: f=female, m=male
    - name: voice identifier

Supported languages and their Kokoro lang_codes:
    a = American English    (misaki[en])
    b = British English     (misaki[en])
    e = Spanish             (espeak-ng)
    f = French              (espeak-ng)
    h = Hindi               (espeak-ng)
    i = Italian             (espeak-ng)
    j = Japanese            (misaki[ja])
    p = Portuguese Brazilian (espeak-ng)
    z = Mandarin Chinese    (misaki[zh])
"""

import logging
logger = logging.getLogger('speak')


# ---------------------------------------------------------------------------
# Language metadata
# ---------------------------------------------------------------------------

LANGUAGE_META = {
    'a': {
        'name': 'American English',
        'native_name': 'English (US)',
        'code': 'en-us',
        'script': 'Latin',
        'g2p_backend': 'misaki[en]',
        'espeak_fallback': True,
    },
    'b': {
        'name': 'British English',
        'native_name': 'English (UK)',
        'code': 'en-gb',
        'script': 'Latin',
        'g2p_backend': 'misaki[en]',
        'espeak_fallback': True,
    },
    'e': {
        'name': 'Spanish',
        'native_name': 'Español',
        'code': 'es',
        'script': 'Latin',
        'g2p_backend': 'espeak-ng',
        'espeak_fallback': False,
    },
    'f': {
        'name': 'French',
        'native_name': 'Français',
        'code': 'fr-fr',
        'script': 'Latin',
        'g2p_backend': 'espeak-ng',
        'espeak_fallback': False,
    },
    'h': {
        'name': 'Hindi',
        'native_name': 'हिन्दी',
        'code': 'hi',
        'script': 'Devanagari',
        'g2p_backend': 'espeak-ng',
        'espeak_fallback': False,
    },
    'i': {
        'name': 'Italian',
        'native_name': 'Italiano',
        'code': 'it',
        'script': 'Latin',
        'g2p_backend': 'espeak-ng',
        'espeak_fallback': False,
    },
    'j': {
        'name': 'Japanese',
        'native_name': '日本語',
        'code': 'ja',
        'script': 'CJK',
        'g2p_backend': 'misaki[ja]',
        'espeak_fallback': False,
    },
    'p': {
        'name': 'Portuguese (Brazil)',
        'native_name': 'Português (Brasil)',
        'code': 'pt-br',
        'script': 'Latin',
        'g2p_backend': 'espeak-ng',
        'espeak_fallback': False,
    },
    'z': {
        'name': 'Mandarin Chinese',
        'native_name': '普通话',
        'code': 'zh',
        'script': 'CJK',
        'g2p_backend': 'misaki[zh]',
        'espeak_fallback': False,
    },
}

# ---------------------------------------------------------------------------
# Voice registry — all known Kokoro voices grouped by language
# ---------------------------------------------------------------------------

VOICE_REGISTRY = {
    'a': [  # American English
        'af_heart', 'af_alloy', 'af_aoede', 'af_bella', 'af_jessica',
        'af_kore', 'af_nicole', 'af_nova', 'af_river', 'af_sarah',
        'af_sky',
        'am_adam', 'am_echo', 'am_eric', 'am_fenrir', 'am_liam',
        'am_michael', 'am_onyx', 'am_puck', 'am_santa',
    ],
    'b': [  # British English
        'bf_alice', 'bf_emma', 'bf_isabella', 'bf_lily',
        'bm_daniel', 'bm_fable', 'bm_george', 'bm_lewis',
    ],
    'e': [  # Spanish
        'ef_dora',
        'em_alex', 'em_santa',
    ],
    'f': [  # French
        'ff_siwis',
    ],
    'h': [  # Hindi
        'hf_alpha', 'hf_beta',
        'hm_omega', 'hm_psi',
    ],
    'i': [  # Italian
        'if_sara',
        'im_nicola',
    ],
    'j': [  # Japanese
        'jf_alpha', 'jf_gongitsune', 'jf_nezumi', 'jf_tebukuro',
        'jm_kumo',
    ],
    'p': [  # Portuguese (Brazil)
        'pf_dora',
        'pm_alex', 'pm_santa',
    ],
    'z': [  # Mandarin Chinese
        'zf_xiaobei', 'zf_xiaoni', 'zf_xiaoxiao', 'zf_xiaoyi',
        'zm_yunjian', 'zm_yunxi', 'zm_yunxia', 'zm_yunyang',
    ],
}


def get_all_voices():
    """Return a flat list of all known Kokoro voice names."""
    voices = []
    for lang_voices in VOICE_REGISTRY.values():
        voices.extend(lang_voices)
    return voices


def get_lang_code_for_voice(voice_name):
    """Derive the Kokoro lang_code from a voice name.

    Kokoro voices follow the pattern <lang><gender>_<name>, so the
    first character is always the language code.

    Args:
        voice_name: Kokoro voice name (e.g. 'af_heart', 'hf_alpha')

    Returns:
        Single-character lang_code string, or 'a' as fallback.
    """
    if not voice_name or len(voice_name) < 2:
        logger.warning(
            "Invalid voice name '%s', falling back to 'a' (American English)",
            voice_name)
        return 'a'

    lang_code = voice_name[0]
    if lang_code not in LANGUAGE_META:
        logger.warning(
            "Unknown language prefix '%s' in voice '%s', "
            "falling back to 'a' (American English)",
            lang_code, voice_name)
        return 'a'

    return lang_code


def get_language_name(lang_code):
    """Return the human-readable English name for a lang_code."""
    meta = LANGUAGE_META.get(lang_code)
    return meta['name'] if meta else 'Unknown'


def get_language_native_name(lang_code):
    """Return the native-script name for a lang_code."""
    meta = LANGUAGE_META.get(lang_code)
    return meta['native_name'] if meta else 'Unknown'


def get_voices_for_language(lang_code):
    """Return the list of known voices for a given lang_code."""
    return list(VOICE_REGISTRY.get(lang_code, []))


def get_supported_language_codes():
    """Return all supported lang_codes."""
    return list(LANGUAGE_META.keys())


def get_language_display_label(voice_name):
    """Return a display string like 'Hindi (हिन्दी)' for a voice."""
    lang_code = get_lang_code_for_voice(voice_name)
    meta = LANGUAGE_META.get(lang_code, {})
    name = meta.get('name', 'Unknown')
    native = meta.get('native_name', '')
    if native and native != name:
        return f'{name} ({native})'
    return name


def get_voice_display_name(voice_name):
    """Return a human-friendly display name for a Kokoro voice.

    Converts e.g. 'hf_alpha' -> 'Hindi Female - Alpha'
    """
    lang_code = get_lang_code_for_voice(voice_name)
    lang_name = get_language_name(lang_code)

    # Parse gender from second character
    gender_char = voice_name[1] if len(voice_name) > 1 else '?'
    gender = 'Female' if gender_char == 'f' else 'Male' if gender_char == 'm' else '?'

    # Parse the actual name part after the underscore
    parts = voice_name.split('_', 1)
    name_part = parts[1].capitalize() if len(parts) > 1 else voice_name

    return f'{lang_name} {gender} - {name_part}'
