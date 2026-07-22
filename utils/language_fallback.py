"""
Language fallback handler for Speak-AI Kokoro TTS pipeline.

When a requested language is not supported by Kokoro, this module
handles graceful fallback with user-friendly logging.

Author: Uday Kumar Reddy
GSoC 2026 - Speak-AI Multilingual Support
"""

import logging

logger = logging.getLogger(__name__)

# Kokoro's officially supported lang_codes as of v0.9.4
KOKORO_SUPPORTED = {
    'a': 'English (American)',
    'b': 'English (British)',
    'e': 'Spanish',
    'f': 'French',
    'h': 'Hindi',
    'i': 'Italian',
    'j': 'Japanese',
    'p': 'Portuguese (Brazilian)',
    'z': 'Chinese (Mandarin)',
}

# ISO 639-1 codes → Kokoro lang_codes
ISO_TO_KOKORO = {
    'en': 'a',
    'en-gb': 'b',
    'es': 'e',
    'fr': 'f',
    'hi': 'h',
    'it': 'i',
    'ja': 'j',
    'pt': 'p',
    'pt-br': 'p',
    'zh': 'z',
    'zh-cn': 'z',
}

DEFAULT_LANG = 'a'  # English fallback


def resolve_lang_code(requested: str) -> tuple[str, bool]:
    """
    Resolve a language code to a Kokoro-supported lang_code.

    Args:
        requested: ISO 639-1 code (e.g. 'hi', 'fr') or
                   Kokoro code (e.g. 'h', 'f') or
                   language name (e.g. 'hindi', 'french')

    Returns:
        Tuple of (resolved_lang_code, is_native_support)
        is_native_support is False when falling back to English
    """
    req = requested.lower().strip()

    # Already a valid Kokoro code
    if req in KOKORO_SUPPORTED:
        return req, True

    # ISO 639-1 code
    if req in ISO_TO_KOKORO:
        return ISO_TO_KOKORO[req], True

    # Language name fallback
    name_map = {v.lower().split(' ')[0]: k
                for k, v in KOKORO_SUPPORTED.items()}
    if req in name_map:
        return name_map[req], True

    # Not supported — fallback to English
    logger.warning(
        f"Language '{requested}' is not supported by Kokoro TTS. "
        f"Falling back to English. "
        f"Supported languages: {list(KOKORO_SUPPORTED.values())}"
    )
    return DEFAULT_LANG, False


def get_supported_languages() -> dict:
    """
    Return all languages supported by Kokoro TTS.

    Returns:
        Dict mapping Kokoro lang_code to language name
    """
    return KOKORO_SUPPORTED.copy()


def is_non_latin_script(lang_code: str) -> bool:
    """
    Check if a language uses a non-Latin script.
    These languages need G2P preprocessing before Kokoro.

    Args:
        lang_code: Kokoro lang_code

    Returns:
        True if language needs special script handling
    """
    NON_LATIN = {'h', 'j', 'z'}  # Hindi, Japanese, Chinese
    return lang_code in NON_LATIN