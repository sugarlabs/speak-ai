#!/usr/bin/env python
import argparse
import json
import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from multilingual import detect_text_script, normalize_text_for_tts, select_kokoro_voice_for_text


DEFAULT_VOICES = [
    'af_heart', 'af_alloy', 'bf_emma', 'ff_siwis',
    'hf_alpha', 'hf_beta', 'hm_omega', 'zf_xiaoxiao', 'jf_alpha'
]


def main():
    parser = argparse.ArgumentParser(description='Validate multilingual routing decisions.')
    parser.add_argument(
        '--dataset',
        default=os.path.join(ROOT_DIR, 'tests', 'data', 'multilingual_phrases.json'),
        help='Path to multilingual phrase dataset JSON',
    )
    parser.add_argument('--current-voice', default='af_heart', help='Current selected Kokoro voice')
    args = parser.parse_args()

    with open(args.dataset, 'r', encoding='utf-8') as fp:
        dataset = json.load(fp)
    rows = dataset.get('phrases', [])
    if not rows:
        raise ValueError('Dataset has no phrases')

    failures = []
    for idx, row in enumerate(rows):
        text = normalize_text_for_tts(row['text'])
        expected_script = row['expected_script']
        detected_script = detect_text_script(text)
        selected_voice, reason = select_kokoro_voice_for_text(
            text, args.current_voice, DEFAULT_VOICES
        )
        if detected_script != expected_script:
            failures.append(
                f'[{idx}] script mismatch: expected={expected_script} detected={detected_script}'
            )
        print(
            f"[{idx}] {row['language']}: script={detected_script} "
            f"voice={selected_voice} reason={reason}"
        )

    if failures:
        print('\nValidation failures:')
        for item in failures:
            print(f' - {item}')
        raise SystemExit(1)

    print('\nRouting validation passed.')


if __name__ == '__main__':
    main()
