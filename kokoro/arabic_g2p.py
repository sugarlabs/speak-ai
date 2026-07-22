"""
Arabic Grapheme-to-Phoneme converter.
Pure Python, strictly adhering to Kokoro-82M's configuration vocabulary.

Assumes fully or partially vocalized text (Tashkeel).
"""

# Map Arabic letters to Kokoro config.json valid IPA tokens
ARABIC_CONSONANTS = {
    'ء': 'ʔ',    # Hamza
    'ب': 'b',    # Ba
    'ت': 't',    # Ta
    'ث': 'θ',    # Tha
    'ج': 'ʤ',    # Jeem
    'ح': 'h',    # Hha (fallback to h since ħ unsupported)
    'خ': 'χ',    # Kha
    'د': 'd',    # Dal
    'ذ': 'ð',    # Dhal
    'ر': 'r',    # Ra
    'ز': 'z',    # Zay
    'س': 's',    # Seen
    'ش': 'ʃ',    # Sheen
    'ص': 's',    # Saad (fallback to s)
    'ض': 'd',    # Daad (fallback to d)
    'ط': 't',    # Taa (fallback to t)
    'ظ': 'z',    # Zaa (fallback to dhal/zay)
    'ع': 'ʔ',    # Ayn (fallback to glottal stop)
    'غ': 'ɣ',    # Ghayn
    'ف': 'f',    # Fa
    'ق': 'q',    # Qaf
    'ك': 'k',    # Kaf
    'ل': 'l',    # Lam
    'م': 'm',    # Meem
    'ن': 'n',    # Noon
    'ه': 'h',    # Ha
    'و': 'w',    # Waw
    'ي': 'j',    # Ya
    'ة': 't',    # Ta marbuta
    'ى': 'a',    # Alif maqsura
    'أ': 'ʔ',    # Alif with hamza
    'إ': 'ʔ',    # Alif with hamza below
    'آ': 'ʔaː',  # Alif madda
    'ؤ': 'ʔ',    # Waw with hamza
    'ئ': 'ʔ',    # Ya with hamza
    'ا': 'aː',   # Bare alif
}

# Vowels & Marks
FATHA = 'َ'
KASRA = 'ِ'
DAMMA = 'ُ'
SUKUN = 'ْ'
SHADDA = 'ّ'
FATHATAN = 'ً'
KASRATAN = 'ٍ'
DAMMATAN = 'ٌ'


def transliterate_arabic(text: str) -> str:
    result = []
    chars = list(text)
    i = 0
    while i < len(chars):
        ch = chars[i]
        nxt = chars[i+1] if i+1 < len(chars) else ''
        
        c_pho = ARABIC_CONSONANTS.get(ch, None)
        if c_pho:
            # Handle shadda (gemination)
            if nxt == SHADDA:
                result.append(c_pho) # double the consonant
                result.append(c_pho)
                i += 2
                # Look for vowel after shadda
                if i < len(chars):
                    v = chars[i]
                    if v == FATHA: result.append('a'); i += 1
                    elif v == KASRA: result.append('i'); i += 1
                    elif v == DAMMA: result.append('u'); i += 1
                    elif v == FATHATAN: result.append('a'); result.append('n'); i += 1
                    elif v == KASRATAN: result.append('i'); result.append('n'); i += 1
                    elif v == DAMMATAN: result.append('u'); result.append('n'); i += 1
            else:
                result.append(c_pho)
                i += 1
        elif ch == FATHA:
            if nxt == 'ا' or nxt == 'ى':
                result.append('aː')
                i += 2
            else:
                result.append('a')
                i += 1
        elif ch == KASRA:
            if nxt == 'ي':
                result.append('iː')
                i += 2
            else:
                result.append('i')
                i += 1
        elif ch == DAMMA:
            if nxt == 'و':
                result.append('uː')
                i += 2
            else:
                result.append('u')
                i += 1
        elif ch == FATHATAN:
            result.append('an')
            i += 1
        elif ch == KASRATAN:
            result.append('in')
            i += 1
        elif ch == DAMMATAN:
            result.append('un')
            i += 1
        elif ch == SUKUN:
            i += 1
        elif ch == ' ':
            result.append(' ')
            i += 1
        elif ch.isascii():
            result.append(ch)
            i += 1
        else:
            i += 1
            
    return ''.join(result).replace('aːaː', 'aː').replace('iːiː', 'iː').replace('uːuː', 'uː')


class ArabicG2P:
    def __call__(self, text: str):
        phonemes = transliterate_arabic(text)
        return phonemes, None
