import re
from typing import List, Dict, Tuple

class AdvancedG2P:
    """
    Advanced Grapheme-to-Phoneme (G2P) converter for non-Latin scripts.
    Designed for the Speak-AI project to bypass brittle espeak-ng dependencies
    and generate highly accurate Kokoro-compatible IPA phonemes natively in Python.
    """
    
    DEVANAGARI_MAP = {
        'अ': 'ə', 'आ': 'aː', 'इ': 'i', 'ई': 'iː', 'उ': 'u', 'ऊ': 'uː',
        'ऋ': 'r̩', 'ए': 'eː', 'ऐ': 'ɛː', 'ओ': 'oː', 'औ': 'ɔː',
        'क': 'k', 'ख': 'kʰ', 'ग': 'ɡ', 'घ': 'ɡʱ', 'ङ': 'ŋ',
        'च': 'c', 'छ': 'cʰ', 'ज': 'ɟ', 'झ': 'ɟʱ', 'ञ': 'ɲ',
        'ट': 'ʈ', 'ठ': 'ʈʰ', 'ड': 'ɖ', 'ढ': 'ɖʱ', 'ण': 'ɳ',
        'त': 't', 'थ': 'tʰ', 'द': 'd', 'ध': 'dʱ', 'न': 'n',
        'प': 'p', 'फ': 'pʰ', 'ब': 'b', 'भ': 'bʱ', 'म': 'm',
        'य': 'j', 'र': 'ɾ', 'ल': 'l', 'व': 'ʋ', 'श': 'ʃ',
        'ष': 'ʂ', 'स': 's', 'ह': 'ɦ',
        'क़': 'q', 'ख़': 'x', 'ग़': 'ɣ', 'ज़': 'z', 'ड़': 'ɽ', 'ढ़': 'ɽʱ', 'फ़': 'f',
        'ा': 'aː', 'ि': 'i', 'ी': 'iː', 'ु': 'u', 'ू': 'uː', 'ृ': 'r̩',
        'े': 'eː', 'ै': 'ɛː', 'ो': 'oː', 'ौ': 'ɔː',
        'ं': 'n', 'ः': 'h', 'ँ': '̃', '्': '',
    }
    
    ARABIC_MAP = {
        'ا': 'aː', 'ب': 'b', 'ت': 't', 'ث': 'θ', 'ج': 'dʒ', 'ح': 'ħ', 'خ': 'x',
        'د': 'd', 'ذ': 'ð', 'ر': 'r', 'ز': 'z', 'س': 's', 'ش': 'ʃ', 'ص': 'sˤ',
        'ض': 'dˤ', 'ط': 'tˤ', 'ظ': 'ðˤ', 'ع': 'ʕ', 'غ': 'ɣ', 'ف': 'f', 'ق': 'q',
        'ك': 'k', 'ل': 'l', 'م': 'm', 'ن': 'n', 'ه': 'h', 'و': 'w', 'ي': 'j',
        'ء': 'ʔ', 'أ': 'ʔ', 'إ': 'ʔ', 'ؤ': 'ʔ', 'ئ': 'ʔ', 'آ': 'ʔaː',
        'ة': 'a', 'ى': 'aː',
        'َ': 'a', 'ِ': 'i', 'ُ': 'u', 'ً': 'an', 'ٍ': 'in', 'ٌ': 'un', 'ْ': '',
        'ّ': 'ː'
    }

    SWAHILI_MAP = {
        'a': 'a', 'e': 'ɛ', 'i': 'i', 'o': 'ɔ', 'u': 'u',
        'b': 'ɓ', 'ch': 'tʃ', 'd': 'ɗ', 'dh': 'ð', 'f': 'f',
        'g': 'g', 'gh': 'ɣ', 'h': 'h', 'j': 'ʄ', 'k': 'k',
        'l': 'l', 'm': 'm', 'n': 'n', 'ng': 'ŋg', 'ng\'': 'ŋ',
        'ny': 'ɲ', 'p': 'p', 'r': 'r', 's': 's', 'sh': 'ʃ',
        't': 't', 'th': 'θ', 'v': 'v', 'w': 'w', 'y': 'j', 'z': 'z'
    }

    @classmethod
    def hindi_g2p(cls, text: str) -> str:
        """
        Advanced Hindi Schwa Deletion and Phoneme mapping algorithm.
        Identifies word boundaries and dynamically computes inherent schwa retention.
        """
        phonemes = []
        words = text.split()
        for word in words:
            word_phonemes = []
            for i, char in enumerate(word):
                if char in cls.DEVANAGARI_MAP:
                    if char in ['ा', 'ि', 'ी', 'ु', 'ू', 'ृ', 'े', 'ै', 'ो', 'ौ']:
                        if len(word_phonemes) > 0 and word_phonemes[-1] == 'ə':
                            word_phonemes.pop()
                        word_phonemes.append(cls.DEVANAGARI_MAP[char])
                    elif char == '्': # Halant
                        if len(word_phonemes) > 0 and word_phonemes[-1] == 'ə':
                            word_phonemes.pop()
                    else:
                        word_phonemes.append(cls.DEVANAGARI_MAP[char])
                        # Schwa retention logic
                        if char in 'कखगघचछजझटठडढणतथदधनपफबभमयरलवशषसह':
                            if i < len(word) - 1:
                                next_char = word[i+1]
                                if next_char not in ['ा', 'ि', 'ी', 'ु', 'ू', 'ृ', 'े', 'ै', 'ो', 'ौ', '्']:
                                    word_phonemes.append('ə')
                else:
                    word_phonemes.append(char)
            phonemes.append("".join(word_phonemes))
        return " ".join(phonemes)

    @classmethod
    def arabic_g2p(cls, text: str) -> str:
        """
        Advanced Arabic phonemization.
        Processes Shadda (gemination), Tanween, and long vowels contextually.
        """
        phonemes = []
        for i, char in enumerate(text):
            if char in cls.ARABIC_MAP:
                if char == 'ّ': # Shadda (duplicate previous consonant)
                    if i > 0 and text[i-1] in cls.ARABIC_MAP and text[i-1] not in ['َ', 'ِ', 'ُ', 'ً', 'ٍ', 'ٌ']:
                        phonemes.append(cls.ARABIC_MAP[text[i-1]])
                    else:
                        phonemes.append(cls.ARABIC_MAP[char])
                else:
                    phonemes.append(cls.ARABIC_MAP[char])
            elif char.isspace():
                phonemes.append(' ')
            else:
                phonemes.append(char)
        return "".join(phonemes).strip()

    @classmethod
    def swahili_g2p(cls, text: str) -> str:
        """
        Swahili G2P algorithm handling digraphs and trigraphs natively.
        """
        text = text.lower()
        
        # Replace trigraphs first
        text = text.replace("ng'", cls.SWAHILI_MAP["ng'"])
        
        # Replace digraphs
        digraphs = ['ch', 'dh', 'gh', 'ng', 'ny', 'sh', 'th']
        for dg in digraphs:
            text = text.replace(dg, cls.SWAHILI_MAP[dg])
            
        # Replace monographs
        phonemes = []
        for char in text:
            if char in cls.SWAHILI_MAP:
                phonemes.append(cls.SWAHILI_MAP[char])
            else:
                phonemes.append(char)
        return "".join(phonemes)

    @classmethod
    def phonemize(cls, text: str, lang_code: str) -> Tuple[str, List[str]]:
        """
        Main entrypoint. Returns phonemes and pseudo-tokens for Kokoro pipeline compatibility.
        """
        if lang_code == 'h': # Hindi
            ps = cls.hindi_g2p(text)
        elif lang_code == 'r': # Arabic
            ps = cls.arabic_g2p(text)
        elif lang_code == 's': # Swahili
            ps = cls.swahili_g2p(text)
        else:
            ps = text # Fallback
            
        # Mock MToken return structure to interface smoothly with Kokoro
        class PseudoMToken:
            def __init__(self, t, p, w):
                self.text = t
                self.phonemes = p
                self.whitespace = w
        
        tokens = [PseudoMToken(text, ps, False)]
        return ps, tokens
