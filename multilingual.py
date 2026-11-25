import re
import unicodedata


_SCRIPT_PATTERNS = {
    'arabic': re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]'),
    'devanagari': re.compile(r'[\u0900-\u097F]'),
    'han': re.compile(r'[\u4E00-\u9FFF]'),
    'hiragana_katakana': re.compile(r'[\u3040-\u30FF]'),
    'latin': re.compile(r'[A-Za-z]'),
}

_SCRIPT_TO_PREFERRED_VOICES = {
    'arabic': ['af_alloy', 'af_heart'],
    'devanagari': ['hf_alpha', 'hf_beta', 'hm_omega'],
    'han': ['zf_xiaoxiao', 'zf_xiaobei', 'zm_yunjian'],
    'hiragana_katakana': ['jf_alpha', 'jf_gongitsune', 'jm_kumo'],
    'latin': ['af_heart', 'bf_emma', 'ff_siwis'],
}

_VOICE_PREFIX_TO_SCRIPT = {
    'z': 'han',
    'j': 'hiragana_katakana',
    'h': 'devanagari',
    # Most other voice families are currently Latin-script focused.
    'a': 'latin',
    'b': 'latin',
    'e': 'latin',
    'f': 'latin',
    'i': 'latin',
    'p': 'latin',
}


def normalize_text_for_tts(text):
    """Apply light normalization to improve consistency before TTS."""
    if not text:
        return text
    text = unicodedata.normalize('NFKC', text)
    text = text.replace('\u0640', '')  # Arabic tatweel
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def detect_text_script(text):
    """Detect dominant script based on character counts."""
    if not text:
        return 'latin'
    counts = {}
    for script, pattern in _SCRIPT_PATTERNS.items():
        counts[script] = len(pattern.findall(text))
    dominant = max(counts, key=counts.get)
    if counts[dominant] == 0:
        return 'latin'
    return dominant


def infer_script_from_voice(voice_name):
    """Infer script family from Kokoro voice prefix."""
    if not voice_name:
        return 'latin'
    prefix = voice_name.split('_', 1)[0]
    if not prefix:
        return 'latin'
    return _VOICE_PREFIX_TO_SCRIPT.get(prefix[0], 'latin')


def select_kokoro_voice_for_text(text, current_voice, available_voices):
    """
    Select a voice that best matches the input script.
    Returns (voice_name, reason_string).
    """
    script = detect_text_script(text)
    if current_voice in available_voices:
        current_script = infer_script_from_voice(current_voice)
        if current_script == script:
            return current_voice, f'kept_current_script_match:{script}'

    preferred = _SCRIPT_TO_PREFERRED_VOICES.get(script, [])
    for candidate in preferred:
        if candidate in available_voices:
            return candidate, f'auto_selected_by_script:{script}'

    if current_voice in available_voices:
        return current_voice, f'fallback_current_voice:{script}'

    if available_voices:
        return available_voices[0], f'fallback_first_available:{script}'

    return current_voice, f'fallback_no_available:{script}'
