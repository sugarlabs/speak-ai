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

"""Text normalization applied before language detection and G2P.

What this module does is narrower than it first looks, and the reason is worth
writing down, because the obvious version of it is mostly unnecessary.

espeak-ng already handles more than expected. Measured against the espeak-ng
shipped with this project (see tests/evaluation/test_normalizer.py, which
asserts each of these so a future espeak-ng regression is caught rather than
assumed away):

  * Hindi word-final schwa is already correct. कमल -> kʌməl, राम -> ɾaːm,
    and कृष्ण -> kɾɪʂɳə keeps the schwa where Hindi keeps it. Appending an
    explicit halant (U+094D) changes nothing at all: 10 of 10 test words
    phonemize identically with and without it. The preprocessing step this
    module was expected to carry does not exist because it is not needed.
  * Numerals are already read in the target language. The Hindi voice reads
    "42" as bəɪaːlis and "2026" as doː hʌɟaːɾ cʰəbbis; the Arabic voice reads
    "٣" and "3" identically. Expanding them first with num2words makes Arabic
    actively worse (ثلاثة -> θlaːθt, against espeak's own θalaːθa) and is
    impossible for Hindi, which num2words does not support at all.
  * Ejective apostrophes, decomposed or composed, ASCII or U+2019 or U+02BC,
    all reach the Quechua and Guarani voices as the same phonemes.
  * A stray ZWNJ inside a Devanagari cluster does not change its phonemes.

So none of that is done here. What *is* done is the layer above: the language
detector in speech.py matches hint words against typed text, and that matching
is not Unicode-robust on its own. Decomposed Spanish "¿Cómo está usted?"
scores zero hints and falls through to English, where the composed form scores
two and routes correctly. A child who pastes text out of a word processor gets
the wrong language for the whole utterance.

That is the bug this module fixes. NFC composition and apostrophe folding are
cheap, they make detection deterministic regardless of how the text was
produced, and they protect the two backends that do *not* go through
espeak-ng — Piper and MMS both tokenise against a fixed vocabulary, where a
decomposed character is an unknown token rather than a differently-spelled
known one.

Every step degrades to a no-op rather than raising. normalize_text sits
between the child pressing enter and any sound coming out, so the worst thing
it may do is hand back the text it was given.
"""

import logging
import re
import unicodedata

logger = logging.getLogger('speak')


# --------------------------------------------------------------------------
# character classes
# --------------------------------------------------------------------------

# Every apostrophe that carries meaning in the orthographies here, folded to
# ASCII: ejective marker in Quechua and Guarani, elision in French. Kept in
# sync with _APOSTROPHES in speech.py — the tokeniser and the normalizer
# disagreeing about what an apostrophe is was how "mba'echu" became
# unmatchable in the first place.
_APOSTROPHES = str.maketrans({'’': "'", 'ʼ': "'", '՚': "'", '‘': "'"})

# Invisible characters that survive copy-paste and split tokens. They do not
# change espeak-ng's phonemes (asserted in the tests), but they do split a
# hint word in two and so break detection.
_JOINERS = dict.fromkeys([0x200b, 0x200c, 0x200d, 0xfeff])

_WHITESPACE_RE = re.compile(r'\s+')


# --------------------------------------------------------------------------
# Hindi schwa — retained as a diagnostic, not applied
# --------------------------------------------------------------------------

_DEV_CONSONANTS = set(
    [chr(c) for c in range(0x0915, 0x093a)] +      # क .. ह
    [chr(c) for c in range(0x0958, 0x0960)]        # क़ .. य़ (nukta forms)
)
_DEV_HALANT = '्'
_DEV_NUKTA = '़'
_DEV_WORD_RE = re.compile(r'[ऀ-ॿ]+')

# Words whose final schwa is pronounced, mostly Sanskrit-derived (tatsama)
# vocabulary and conjunct-final stems. Never modified, in either mode.
_HI_SCHWA_KEEP = {
    'कृष्ण', 'ब्रह्म', 'मित्र', 'चन्द्र', 'रुद्र', 'शुक्र', 'वज्र',
    'अन्य', 'सत्य', 'नृत्य', 'कार्य', 'सूर्य', 'धैर्य', 'वाक्य',
}


def ends_in_bare_consonant(word):
    """True when `word` ends in a consonant carrying its inherent vowel.

    False for a word ending in a matra, an anusvara, an explicit halant, or as
    the tail of a conjunct — a conjunct-final consonant (मित्र) keeps its
    schwa, so suppressing it there would produce a different word rather than
    a slightly stilted one.
    """
    if not word:
        return False
    last = word[-1]
    if last == _DEV_NUKTA and len(word) >= 2:
        word = word[:-1]
        last = word[-1]
    if last not in _DEV_CONSONANTS:
        return False
    if len(word) >= 2 and word[-2] == _DEV_HALANT:
        return False
    return True


def delete_final_schwa(text):
    """Append an explicit halant where Hindi drops the word-final schwa.

    Not called by normalize_text, and deliberately so: measured against the
    espeak-ng shipped here this is a no-op, because espeak-ng already applies
    Hindi schwa deletion correctly. It is kept because that is a property of
    one espeak-ng version rather than a guarantee, and
    test_normalizer.py::test_espeak_still_handles_hindi_schwa asserts the
    equivalence. If that test ever fails, this function is the fix that is
    already written and already tested — wire it into normalize_text for
    lang_code 'hi' and the corpus will tell you whether it helped.
    """
    def repl(match):
        word = match.group(0)
        if word in _HI_SCHWA_KEEP or not ends_in_bare_consonant(word):
            return word
        return word + _DEV_HALANT

    return _DEV_WORD_RE.sub(repl, text)


# --------------------------------------------------------------------------
# public entry point
# --------------------------------------------------------------------------

def normalize_text(text, lang_code='en-us'):
    """Return `text` in the canonical form the detector and backends expect.

    `lang_code` is accepted for callers that want per-language handling later;
    nothing currently branches on it, because every measured difference turned
    out to be handled upstream by espeak-ng. Keeping the parameter means
    adding a language-specific step does not change any call site.

    Never raises. A normalizer that throws would take the whole utterance with
    it and the child would get silence for one stray character.
    """
    if not text or not text.strip():
        return text

    try:
        out = unicodedata.normalize('NFC', text)
        out = out.translate(_APOSTROPHES)
        out = out.translate(_JOINERS)
        return _WHITESPACE_RE.sub(' ', out).strip()
    except Exception:
        logger.exception("normalize_text failed for lang=%s; using raw text",
                         lang_code)
        return text
