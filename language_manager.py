# Copyright (C) 2025 Sugar Labs
# SPDX-License-Identifier: GPL-3.0-or-later
#
# language_manager.py — Multilingual TTS support for Speak-AI
#
# Handles language selection, Kokoro lang_code mapping, and espeak-ng
# fallback for languages not natively supported by Kokoro v1.0.

import logging
import unicodedata

log = logging.getLogger('speak-ai')

# Each entry maps a human-readable language name to:
#   kokoro_lang_code : str | None  — Kokoro KPipeline lang_code, or None
#   kokoro_voice     : str | None  — a default voice token for that language
#   espeak_lang      : str         — espeak-ng language code (always set,
#                                    used as fallback when kokoro_lang_code
#                                    is None, or if Kokoro synthesis fails)
#   script           : str         — Unicode script name used for auto-detect

LANGUAGE_REGISTRY = {
    'English (US)': {
        'kokoro_lang_code': 'a',
        'kokoro_voice': 'af_heart',
        'espeak_lang': 'en-us',
        'script': 'Latin',
    },
    'English (UK)': {
        'kokoro_lang_code': 'b',
        'kokoro_voice': 'bf_emma',
        'espeak_lang': 'en-gb',
        'script': 'Latin',
    },
    'Spanish': {
        'kokoro_lang_code': 'e',
        'kokoro_voice': 'ef_dora',
        'espeak_lang': 'es',
        'script': 'Latin',
    },
    'French': {
        'kokoro_lang_code': 'f',
        'kokoro_voice': 'ff_siwis',
        'espeak_lang': 'fr',
        'script': 'Latin',
    },
    'Hindi': {
        'kokoro_lang_code': 'h',
        'kokoro_voice': 'hf_alpha',
        'espeak_lang': 'hi',
        'script': 'Devanagari',
    },
    'Italian': {
        'kokoro_lang_code': 'i',
        'kokoro_voice': 'if_sara',
        'espeak_lang': 'it',
        'script': 'Latin',
    },
    'Japanese': {
        'kokoro_lang_code': 'j',
        'kokoro_voice': 'jf_alpha',
        'espeak_lang': 'ja',
        'script': 'Hiragana',
    },
    'Portuguese (Brazilian)': {
        'kokoro_lang_code': 'p',
        'kokoro_voice': 'pf_dora',
        'espeak_lang': 'pt-br',
        'script': 'Latin',
    },
    'Chinese (Mandarin)': {
        'kokoro_lang_code': 'z',
        'kokoro_voice': 'zf_xiaobei',
        'espeak_lang': 'zh',
        'script': 'Han',
    },

    # ── espeak-ng fallback languages (not yet in Kokoro v1.0) ──
    # These use espeak-ng directly. When Kokoro adds support, only
    # kokoro_lang_code / kokoro_voice need to be filled in here.
    'Arabic': {
        'kokoro_lang_code': None,
        'kokoro_voice': None,
        'espeak_lang': 'ar',
        'script': 'Arabic',
    },
    'Swahili': {
        'kokoro_lang_code': None,
        'kokoro_voice': None,
        'espeak_lang': 'sw',
        'script': 'Latin',
    },
    'Kinyarwanda': {
        'kokoro_lang_code': None,
        'kokoro_voice': None,
        'espeak_lang': 'rw',
        'script': 'Latin',
    },
    'Quechua': {
        'kokoro_lang_code': None,
        'kokoro_voice': None,
        'espeak_lang': 'qu',
        'script': 'Latin',
    },
    'Guaraní': {
        'kokoro_lang_code': None,
        'kokoro_voice': None,
        'espeak_lang': 'gn',
        'script': 'Latin',
    },
}

LANGUAGE_NAMES = list(LANGUAGE_REGISTRY.keys())

_SCRIPT_TO_LANG = {
    'Devanagari': 'Hindi',
    'Arabic': 'Arabic',
    'Han': 'Chinese (Mandarin)',
    'Cjk': 'Chinese (Mandarin)',   
    'Hiragana': 'Japanese',
    'Katakana': 'Japanese',
    'Hangul': 'Japanese',   # fallback — Korean not yet in registry
}


def detect_language_from_text(text: str) -> str | None:
    """Heuristically detect language from Unicode script of input text.

    Returns a LANGUAGE_REGISTRY key, or None if detection is inconclusive
    (e.g. Latin-script text could be many languages).
    """
    if not text:
        return None
    script_votes: dict[str, int] = {}
    for ch in text:
        if ch.isspace() or not ch.isalpha():
            continue
        try:
            name = unicodedata.name(ch, '')
            script = name.split()[0] if name else 'LATIN'
        except Exception:
            script = 'LATIN'
        script_votes[script] = script_votes.get(script, 0) + 1

    if not script_votes:
        return None
    dominant = max(script_votes, key=script_votes.__getitem__)
    dominant = dominant.capitalize()
    return _SCRIPT_TO_LANG.get(dominant)


class LanguageManager:
    """Central manager for TTS language state.

    Usage::

        lm = LanguageManager()
        lm.set_language('Hindi')
        lang_code = lm.kokoro_lang_code   # 'h'
        voice     = lm.kokoro_voice       # 'hf_alpha'
        espeak    = lm.espeak_lang        # 'hi'
        lm.uses_kokoro                    # True
    """

    def __init__(self, default_language: str = 'English (US)'):
        self._language = None
        self.set_language(default_language)

    def set_language(self, name: str) -> None:
        if name not in LANGUAGE_REGISTRY:
            log.warning('Unknown language %r, falling back to English (US)', name)
            name = 'English (US)'
        self._language = name
        log.info('Language set to: %s', name)

    def set_language_from_text(self, text: str) -> bool:
        """Try to auto-detect and set language from text.

        Returns True if a language was detected and changed.
        """
        detected = detect_language_from_text(text)
        if detected and detected != self._language:
            log.info('Auto-detected language: %s', detected)
            self.set_language(detected)
            return True
        return False

    @property
    def language(self) -> str:
        return self._language

    @property
    def _entry(self) -> dict:
        return LANGUAGE_REGISTRY[self._language]

    @property
    def kokoro_lang_code(self) -> str | None:
        return self._entry['kokoro_lang_code']

    @property
    def kokoro_voice(self) -> str | None:
        return self._entry['kokoro_voice']

    @property
    def espeak_lang(self) -> str:
        return self._entry['espeak_lang']

    @property
    def uses_kokoro(self) -> bool:
        """True when Kokoro natively supports this language."""
        return self._entry['kokoro_lang_code'] is not None

    @property
    def display_name(self) -> str:
        return self._language

    @staticmethod
    def all_languages() -> list[str]:
        return LANGUAGE_NAMES

    @staticmethod
    def kokoro_languages() -> list[str]:
        return [k for k, v in LANGUAGE_REGISTRY.items()
                if v['kokoro_lang_code'] is not None]

    @staticmethod
    def fallback_languages() -> list[str]:
        return [k for k, v in LANGUAGE_REGISTRY.items()
                if v['kokoro_lang_code'] is None]