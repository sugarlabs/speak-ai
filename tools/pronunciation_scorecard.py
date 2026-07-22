#!/usr/bin/env python
import argparse
import csv
import os
from collections import defaultdict


def _to_float(value):
    try:
        return float(value)
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description='Aggregate native-speaker pronunciation ratings.')
    parser.add_argument('--input', required=True, help='CSV file with pronunciation ratings')
    parser.add_argument(
        '--output',
        default='pronunciation_scorecard_summary.csv',
        help='Output CSV summary path',
    )
    args = parser.parse_args()

    if not os.path.exists(args.input):
        raise FileNotFoundError(f'Input file not found: {args.input}')

    # Expected columns:
    # reviewer,language,text,voice,pronunciation,naturalness,notes
    grouped = defaultdict(lambda: {'pronunciation': [], 'naturalness': [], 'samples': 0})

    with open(args.input, 'r', encoding='utf-8') as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            language = (row.get('language') or '').strip()
            voice = (row.get('voice') or '').strip()
            key = (language, voice)
            p = _to_float(row.get('pronunciation'))
            n = _to_float(row.get('naturalness'))
            if p is not None:
                grouped[key]['pronunciation'].append(p)
            if n is not None:
                grouped[key]['naturalness'].append(n)
            grouped[key]['samples'] += 1

    with open(args.output, 'w', encoding='utf-8', newline='') as fp:
        writer = csv.writer(fp)
        writer.writerow([
            'language',
            'voice',
            'samples',
            'avg_pronunciation',
            'avg_naturalness',
            'overall',
        ])

        for (language, voice), values in sorted(grouped.items()):
            pronunciation = values['pronunciation']
            naturalness = values['naturalness']
            p_avg = sum(pronunciation) / len(pronunciation) if pronunciation else 0.0
            n_avg = sum(naturalness) / len(naturalness) if naturalness else 0.0
            overall = (p_avg * 0.65) + (n_avg * 0.35)
            writer.writerow([
                language,
                voice,
                values['samples'],
                f'{p_avg:.3f}',
                f'{n_avg:.3f}',
                f'{overall:.3f}',
            ])

    print(f'Wrote summary to {args.output}')


if __name__ == '__main__':
    main()
