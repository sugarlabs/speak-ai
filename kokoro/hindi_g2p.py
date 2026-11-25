"""
Hindi (Devanagari) Grapheme-to-Phoneme converter.
Pure Python, zero external dependencies.

Produces phoneme strings compatible with Kokoro TTS model's vocabulary.
Each output character must exist in the model's config.json vocab mapping.

Devanagari is a largely phonemic script — each character consistently maps to
a specific phoneme, making rule-based G2P viable and accurate for Hindi.
"""

# --- Kokoro-compatible phoneme mappings ---
# Only uses characters present in the Kokoro-82M config.json vocab.
# Key remappings from standard IPA:
#   t̪ (dental) → t     (model has no combining dental diacritic)
#   d̪ (dental) → d     (same)
#   ʱ (voiced asp.) → ʰ  (model only has voiceless aspiration marker)
#   ɦ (voiced h) → h     (model has no ɦ)

# Vowels (independent forms)
VOWELS = {
    'अ': 'ə',  'आ': 'aː', 'इ': 'ɪ',  'ई': 'iː',
    'उ': 'ʊ',  'ऊ': 'uː', 'ऋ': 'ɾɪ', 'ए': 'eː',
    'ऐ': 'ɛː', 'ओ': 'oː', 'औ': 'ɔː', 'ऑ': 'ɔ',
}

# Vowel signs (dependent forms / matras)
MATRAS = {
    'ा': 'aː', 'ि': 'ɪ',  'ी': 'iː', 'ु': 'ʊ',
    'ू': 'uː', 'ृ': 'ɾɪ', 'े': 'eː', 'ै': 'ɛː',
    'ो': 'oː', 'ौ': 'ɔː', 'ॉ': 'ɔ',
}

# Consonants — using only Kokoro-vocab-safe phonemes
CONSONANTS = {
    'क': 'k',   'ख': 'kʰ',  'ग': 'ɡ',   'घ': 'ɡʰ',  'ङ': 'ŋ',
    'च': 'ʧ',   'छ': 'ʧʰ',  'ज': 'ʤ',   'झ': 'ʤʰ',  'ञ': 'ɲ',
    'ट': 'ʈ',   'ठ': 'ʈʰ',  'ड': 'ɖ',   'ढ': 'ɖʰ',  'ण': 'ɳ',
    'त': 't',   'थ': 'tʰ',  'द': 'd',   'ध': 'dʰ',  'न': 'n',
    'प': 'p',   'फ': 'pʰ',  'ब': 'b',   'भ': 'bʰ',  'म': 'm',
    'य': 'j',   'र': 'ɾ',   'ल': 'l',   'व': 'ʋ',
    'श': 'ʃ',   'ष': 'ʂ',   'स': 's',   'ह': 'h',
    'क़': 'q',   'ख़': 'x',   'ग़': 'ɣ',   'ज़': 'z',
    'ड़': 'ɽ',   'ढ़': 'ɽʰ',  'फ़': 'f',   'झ़': 'ʒ',
}

HALANT = '्'
ANUSVARA = 'ं'
VISARGA = 'ः'
CHANDRABINDU = 'ँ'
NUKTA = '़'
NASALIZE = '\u0303'  # combining tilde — token 17 in Kokoro vocab

SCHWA = 'ə'


def transliterate(text: str) -> str:
    """Convert Hindi Devanagari text to Kokoro-compatible phoneme string."""
    result = []
    chars = list(text)
    i = 0

    while i < len(chars):
        ch = chars[i]

        # Two-char consonants with nukta (e.g., क़)
        if i + 1 < len(chars) and chars[i + 1] == NUKTA:
            combo = ch + NUKTA
            if combo in CONSONANTS:
                result.append(CONSONANTS[combo])
                i += 2
                if i < len(chars) and chars[i] == HALANT:
                    i += 1
                elif i < len(chars) and chars[i] in MATRAS:
                    result.append(MATRAS[chars[i]])
                    i += 1
                elif combo in CONSONANTS:
                    result.append(SCHWA)
                continue

        if ch in CONSONANTS:
            result.append(CONSONANTS[ch])
            if i + 1 < len(chars) and chars[i + 1] == HALANT:
                i += 2
            elif i + 1 < len(chars) and chars[i + 1] in MATRAS:
                result.append(MATRAS[chars[i + 1]])
                i += 2
            else:
                result.append(SCHWA)
                i += 1

        elif ch in VOWELS:
            result.append(VOWELS[ch])
            i += 1

        elif ch in MATRAS:
            result.append(MATRAS[ch])
            i += 1

        elif ch == ANUSVARA:
            result.append(NASALIZE)
            i += 1

        elif ch == CHANDRABINDU:
            result.append(NASALIZE)
            i += 1

        elif ch == VISARGA:
            result.append('h')
            i += 1

        elif ch == HALANT:
            i += 1

        elif ch == ' ':
            result.append(' ')
            i += 1

        elif ch in '।॥':
            result.append('.')
            i += 1

        elif ch.isascii():
            result.append(ch)
            i += 1

        else:
            i += 1

    return ''.join(result)


class HindiG2P:
    """G2P interface compatible with the Kokoro pipeline's (phonemes, tokens) convention."""

    def __call__(self, text: str):
        phonemes = transliterate(text)
        return phonemes, None
