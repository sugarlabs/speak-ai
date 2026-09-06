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

"""Splitting mixed-script text so each run reaches the right G2P engine.

"मेरा name है Rahul" is ordinary Indian-classroom writing, not an edge case,
and it is one of the most common things a Hindi-speaking child will type into
this activity. Pushed through a single G2P engine it comes out wrong in one
direction or the other: the Hindi voice spells its way through "Rahul" as
Devanagari-transliterated nonsense, or the English voice does the same to
मेरा.

The split is per word, by Unicode block majority vote, because a word is the
smallest unit that reliably belongs to one language. Punctuation, digits and
whitespace carry no script, so they attach to the run in progress rather than
starting a new one — otherwise "है 42 rupees" would break into five segments
and get spoken with gaps in it.

Known limitation, inherited from the approach and worth stating plainly:
English written in Devanagari ("टेबल") routes to the Hindi backend. That is
acceptable — espeak-ng's Hindi voice reads common English loanwords in
Devanagari about as well as anything else would, and detecting them would need
a lexicon this activity has no way to ship.
"""

import re

# Silence inserted at each language boundary when the segments are stitched
# back together. Long enough to stop the two voices running into each other,
# short enough not to read as a pause in the sentence.
BOUNDARY_SILENCE_MS = 50

_SCRIPT_RANGES = [
    ('DEVANAGARI', 0x0900, 0x097f),
    ('ARABIC', 0x0600, 0x06ff),
    ('ARABIC', 0x0750, 0x077f),
    ('HAN', 0x3400, 0x4dbf),
    ('HAN', 0x4e00, 0x9fff),
    ('LATIN', 0x0041, 0x005a),
    ('LATIN', 0x0061, 0x007a),
    ('LATIN', 0x00c0, 0x024f),
    ('LATIN', 0x1e00, 0x1eff),
]

# Which language a run of each script should be spoken as. LATIN is resolved
# against the surrounding text instead — see _latin_lang.
_SCRIPT_TO_LANG = {
    'DEVANAGARI': 'hi',
    'ARABIC': 'ar',
    'HAN': 'zh',
}

# Languages written in Latin script that this activity supports. When the
# base language is one of these, a Latin run belongs to it rather than to
# English: in "Ella ha comido pizza" every word is Latin and every word is
# Spanish.
_LATIN_LANGS = {
    'en-us', 'en-gb', 'es', 'fr', 'pt-br', 'it',
    'sw', 'qu', 'gn', 'rw', 'ay',
}

# A "word" for voting purposes. Split on whitespace and on anything that is
# not a letter, so punctuation never joins two scripts into one token.
_WORD_RE = re.compile(r'\S+')


def _script_of_char(ch):
    cp = ord(ch)
    for name, lo, hi in _SCRIPT_RANGES:
        if lo <= cp <= hi:
            return name
    return None


def script_of_word(word):
    """Dominant script of `word`, or None when it has no letters in it.

    Majority vote rather than first-character: "Rahul," and "42kg" and a word
    with one stray accented character all need to land somewhere sensible, and
    the first character is not reliably representative of any of them.
    """
    counts = {}
    for ch in word:
        script = _script_of_char(ch)
        if script is not None:
            counts[script] = counts.get(script, 0) + 1
    if not counts:
        return None
    return max(counts, key=counts.get)


def _latin_lang(base_lang):
    return base_lang if base_lang in _LATIN_LANGS else 'en-us'


def _lang_of_script(script, base_lang):
    if script == 'LATIN':
        return _latin_lang(base_lang)
    return _SCRIPT_TO_LANG.get(script, base_lang)


def segment_by_script(text, base_lang='en-us'):
    """Split `text` into [(lang_code, segment_text), ...] runs.

    Always returns at least one segment for non-empty input, and the segments
    concatenate back to the original text with single spaces between words —
    so a caller that does not care about code-switching can ignore the split
    entirely and speak segment[0] without losing anything.
    """
    if not text or not text.strip():
        return []

    words = _WORD_RE.findall(text)
    if not words:
        return []

    segments = []
    current_lang = None
    current_words = []

    for word in words:
        script = script_of_word(word)
        if script is None:
            # Pure punctuation or digits: stays with the run in progress.
            if current_words:
                current_words.append(word)
                continue
            lang = base_lang
        else:
            lang = _lang_of_script(script, base_lang)

        if current_lang is None:
            current_lang = lang
            current_words = [word]
        elif lang == current_lang:
            current_words.append(word)
        else:
            segments.append((current_lang, ' '.join(current_words)))
            current_lang = lang
            current_words = [word]

    if current_words:
        segments.append((current_lang, ' '.join(current_words)))

    return segments


def is_mixed_script(text, base_lang='en-us'):
    """True when `text` needs more than one backend to be spoken correctly."""
    return len(segment_by_script(text, base_lang)) > 1
