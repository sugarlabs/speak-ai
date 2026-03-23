#!/usr/bin/env python
import argparse
import json
import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from multilingual import detect_text_script, normalize_text_for_tts, select_kokoro_voice_for_text


DEFAULT_PHRASES = [
    "Hello, how are you?",
    "Hola, como estas?",
    "Bonjour tout le monde",
    "Namaste dosto",
    "नमस्ते, आप कैसे हैं?",
    "مرحبا كيف حالك",
    "Habari yako rafiki yangu",
    "你好，今天怎么样？",
    "こんにちは、元気ですか？",
]

DEFAULT_VOICES = [
    'af_heart', 'af_alloy', 'bf_emma', 'ff_siwis',
    'hf_alpha', 'hm_omega', 'zf_xiaoxiao', 'jf_alpha'
]


def _load_phrases(path):
    if not path:
        return DEFAULT_PHRASES
    with open(path, 'r', encoding='utf-8') as fp:
        data = json.load(fp)
    if isinstance(data, dict) and 'phrases' in data:
        return data['phrases']
    if isinstance(data, list):
        return data
    raise ValueError('Invalid input file format. Use list or {"phrases": [...]}')


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    parser = argparse.ArgumentParser(description='Evaluate multilingual Kokoro voice routing.')
    parser.add_argument('--phrases-file', default=None, help='JSON file with phrases')
    parser.add_argument('--current-voice', default='af_heart', help='Current selected Kokoro voice')
    parser.add_argument('--voices-file', default=None, help='JSON file with available Kokoro voices')
    args = parser.parse_args()

    if args.voices_file:
        with open(args.voices_file, 'r', encoding='utf-8') as fp:
            available_voices = json.load(fp)
    else:
        available_voices = DEFAULT_VOICES

    phrases = _load_phrases(args.phrases_file)

    for phrase in phrases:
        normalized = normalize_text_for_tts(phrase)
        script = detect_text_script(normalized)
        voice, reason = select_kokoro_voice_for_text(
            normalized, args.current_voice, available_voices
        )
        print(f'text={normalized}')
        print(f'  script={script}')
        print(f'  selected_voice={voice}')
        print(f'  reason={reason}')


if __name__ == '__main__':
    main()
