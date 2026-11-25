#!/usr/bin/env python3
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

"""Measure Speak-AI's real cost: memory, latency, and cache benefit.

Produces the numbers that go into tests/evaluation/tts_footprint_poc.md. Every
value here is measured on the machine this runs on — nothing is estimated from
another architecture, because an ARM number guessed from an x86 number is not
a number, it is a guess wearing a number's clothes.

Reports p50/p95/p99 rather than a bare mean. A mean hides the pause a child
actually notices; the tail is the user experience.

Usage:
    python scripts/profile_tts.py                    # full run
    python scripts/profile_tts.py --runs 30          # more samples
    python scripts/profile_tts.py --json out.json    # machine-readable
"""

import argparse
import gc
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    import psutil
except ImportError:
    psutil = None

SENTENCE = "The quick brown fox jumps over the lazy dog and keeps on running."
VOICE = 'af_heart'
RATE = 24000


def rss_mb():
    if psutil is None:
        return float('nan')
    return psutil.Process().memory_info().rss / (1024 ** 2)


def pct(values, p):
    """Percentile without pulling in scipy."""
    if not values:
        return float('nan')
    return float(np.percentile(np.array(values), p))


def summarise(name, samples, unit='ms'):
    return {
        'name': name,
        'n': len(samples),
        'unit': unit,
        'p50': round(pct(samples, 50), 4),
        'p95': round(pct(samples, 95), 4),
        'p99': round(pct(samples, 99), 4),
        'mean': round(statistics.fmean(samples), 4) if samples else None,
        'min': round(min(samples), 4) if samples else None,
        'max': round(max(samples), 4) if samples else None,
    }


def print_row(s):
    print(f"  {s['name']:<34} n={s['n']:<4} "
          f"p50={s['p50']:>10.3f} p95={s['p95']:>10.3f} p99={s['p99']:>10.3f} {s['unit']}")


# ----------------------------------------------------------------------
# environment
# ----------------------------------------------------------------------

def environment():
    env = {
        'platform': platform.platform(),
        'machine': platform.machine(),
        'processor': platform.processor() or 'unknown',
        'python': platform.python_version(),
        'cpu_count': os.cpu_count(),
    }
    if psutil is not None:
        vm = psutil.virtual_memory()
        env['total_ram_mb'] = round(vm.total / 1024 ** 2, 1)
        env['available_ram_mb'] = round(vm.available / 1024 ** 2, 1)
    try:
        import torch
        env['torch'] = torch.__version__
    except ImportError:
        pass
    return env


# ----------------------------------------------------------------------
# cold start — measured in a fresh process
# ----------------------------------------------------------------------

COLD_START_SNIPPET = """
import time, sys, json
sys.path.insert(0, {root!r})
t0 = time.perf_counter()
from kokoro.pipeline import KPipeline
pipe = KPipeline(lang_code='a', model=True, device='cpu')
t1 = time.perf_counter()
try:
    import psutil
    rss = psutil.Process().memory_info().rss / (1024**2)
except ImportError:
    rss = float('nan')
print("COLDSTART_JSON" + json.dumps({{'seconds': t1 - t0, 'rss_mb': rss}}))
"""


def measure_cold_start():
    """Import + model load in a brand new interpreter.

    Has to be a subprocess: once anything in this process has touched torch or
    pulled the weights into page cache, 'cold' is no longer measurable here.
    """
    code = COLD_START_SNIPPET.format(root=ROOT)
    t0 = time.perf_counter()
    proc = subprocess.run([sys.executable, '-c', code],
                          capture_output=True, text=True, timeout=1200)
    wall = time.perf_counter() - t0

    for line in proc.stdout.splitlines():
        if line.startswith("COLDSTART_JSON"):
            data = json.loads(line[len("COLDSTART_JSON"):])
            data['process_wall_s'] = round(wall, 3)
            return data
    return {'error': proc.stderr[-400:] if proc.stderr else 'no marker in output',
            'process_wall_s': round(wall, 3)}


# ----------------------------------------------------------------------
# synthesis + cache
# ----------------------------------------------------------------------

def measure_synthesis(runs):
    from kokoro.pipeline import KPipeline

    baseline = rss_mb()
    t0 = time.perf_counter()
    pipe = KPipeline(lang_code='a', model=True, device='cpu')
    warm_load_s = time.perf_counter() - t0
    after_load = rss_mb()

    def synth_once():
        out = None
        for r in pipe(SENTENCE, voice=VOICE):
            if r.audio is None:
                continue
            out = r.audio.cpu().numpy()
            break
        return out

    synth_once()  # discard: first call pays lazy-init costs unrelated to steady state

    wall, cpu, peak = [], [], after_load
    audio = None
    for _ in range(runs):
        gc.collect()
        w0, c0 = time.perf_counter(), time.process_time()
        audio = synth_once()
        wall.append((time.perf_counter() - w0) * 1000)
        cpu.append((time.process_time() - c0) * 1000)
        peak = max(peak, rss_mb())

    audio_seconds = len(audio) / RATE if audio is not None else float('nan')

    return {
        'baseline_rss_mb': round(baseline, 1),
        'after_load_rss_mb': round(after_load, 1),
        'load_delta_mb': round(after_load - baseline, 1),
        'peak_rss_mb': round(peak, 1),
        'warm_load_s': round(warm_load_s, 3),
        'audio_seconds': round(audio_seconds, 3),
        'wall': summarise('warm synthesis (wall)', wall),
        'cpu': summarise('warm synthesis (cpu)', cpu),
        'audio': audio,
    }


def measure_cache(audio, runs):
    """Round-trip an audio array through TTSCache, the way speech.py does."""
    from tts_cache import TTSCache

    tmp = Path(tempfile.mkdtemp())
    try:
        cache = TTSCache(cache_dir=tmp)

        key_times = []
        for i in range(1000):
            t0 = time.perf_counter()
            cache._compute_hash(f"sentence number {i}", VOICE, 'en', 1.0)
            key_times.append((time.perf_counter() - t0) * 1000)

        cache.put(SENTENCE, VOICE, 'en', 1.0, audio)

        hit_times = []
        for _ in range(runs):
            t0 = time.perf_counter()
            got, _sr = cache.get(SENTENCE, VOICE, 'en', 1.0)
            hit_times.append((time.perf_counter() - t0) * 1000)
            assert got is not None, "cache round-trip lost the entry"

        return {
            'key_gen': summarise('cache key generation', key_times),
            'hit': summarise('cache hit (load from disk)', hit_times),
            'entry_kb': round(audio.nbytes / 1024, 1),
        }
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--runs', type=int, default=20, help='synthesis/cache samples')
    ap.add_argument('--json', default=None, help='write raw results here')
    ap.add_argument('--skip-cold', action='store_true', help='skip subprocess cold start')
    args = ap.parse_args()

    print("=" * 78)
    print("Speak-AI TTS profile")
    print("=" * 78)

    env = environment()
    print("\n[env]")
    for k, v in env.items():
        print(f"  {k:<20} {v}")

    results = {'environment': env, 'runs': args.runs}

    if not args.skip_cold:
        print("\n[cold start]  fresh interpreter, imports + model load")
        cold = measure_cold_start()
        results['cold_start'] = cold
        if 'error' in cold:
            print(f"  FAILED: {cold['error']}")
        else:
            print(f"  load           {cold['seconds']:.2f} s")
            print(f"  process wall   {cold['process_wall_s']:.2f} s")
            print(f"  rss after load {cold['rss_mb']:.1f} MB")

    print(f"\n[synthesis]  {args.runs} runs, {len(SENTENCE.split())}-word sentence")
    syn = measure_synthesis(args.runs)
    audio = syn.pop('audio')
    results['synthesis'] = syn
    print(f"  baseline rss   {syn['baseline_rss_mb']:.1f} MB")
    print(f"  after load     {syn['after_load_rss_mb']:.1f} MB  (delta {syn['load_delta_mb']:.1f} MB)")
    print(f"  peak rss       {syn['peak_rss_mb']:.1f} MB")
    print(f"  audio produced {syn['audio_seconds']:.2f} s")
    print_row(syn['wall'])
    print_row(syn['cpu'])

    rtf = (syn['wall']['p50'] / 1000) / syn['audio_seconds']
    results['rtf_p50'] = round(rtf, 4)
    print(f"  real-time factor (p50)  {rtf:.3f}x  "
          f"({'faster' if rtf < 1 else 'SLOWER'} than playback)")

    # process_time vs wall tells you whether you are compute- or IO-bound.
    cpu_ratio = syn['cpu']['p50'] / syn['wall']['p50'] if syn['wall']['p50'] else float('nan')
    results['cpu_wall_ratio_p50'] = round(cpu_ratio, 3)
    print(f"  cpu/wall ratio (p50)    {cpu_ratio:.2f}  "
          f"({'compute-bound' if cpu_ratio > 0.9 else 'partly IO/contention-bound'})")

    print(f"\n[cache]  {args.runs} hits, 1000 key generations")
    cache = measure_cache(audio, args.runs)
    results['cache'] = cache
    print(f"  entry size     {cache['entry_kb']:.1f} KB")
    print_row(cache['key_gen'])
    print_row(cache['hit'])

    speedup = syn['wall']['p50'] / cache['hit']['p50']
    results['cache_speedup_p50'] = round(speedup, 1)
    print(f"\n  cache speedup on a repeated phrase: {speedup:,.0f}x "
          f"({syn['wall']['p50']:.1f} ms -> {cache['hit']['p50']:.3f} ms)")

    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2))
        print(f"\nwrote {args.json}")

    print("\n" + "=" * 78)
    return 0


if __name__ == '__main__':
    sys.exit(main())
