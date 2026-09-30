# TTS Footprint & Performance POC

Reproducible measurements of what Speak-AI actually costs to run: memory,
latency, and the benefit of the audio cache. Regenerate any time with:

```bash
python scripts/profile_tts.py --runs 20 --json profile.json
```

Every number below is **measured on the machine named in the table**, not
estimated from another architecture. Cells for hardware not yet profiled say
TBD rather than carrying a guess across from x86.

## Measurement method

| Quantity | How |
|---|---|
| Cold start | Fresh interpreter (subprocess), time from launch to model-loaded |
| Warm synthesis | `time.perf_counter()`, N runs, first run discarded |
| CPU time | `time.process_time()` alongside wall clock |
| Peak RSS | `psutil.Process().memory_info().rss`, sampled around synthesis |
| Cache hit | `np.load` round-trip through `TTSCache`, N runs |
| Percentiles | `numpy.percentile`, p50 / p95 / p99 reported (not just mean) |

Tail percentiles are reported on purpose: a child notices the slow call, not
the average one, so p99 is the honest latency to plan around.

## Baseline — x86_64 Linux (dev machine)

Environment: Linux 6.12 x86_64 · 16 cores · 15.8 GB RAM · Python 3.13.5 ·
**torch 2.13.0+cpu** · Kokoro-82M already in HF cache.

| Measurement | x86_64 Linux (measured) | ARM / RPi 4 |
|---|---|---|
| Peak RSS during synthesis | **1305.2 MB** | TBD |
| RSS after Kokoro load | **1123.4 MB** | TBD |
| Kokoro load RSS delta | **722.9 MB** | TBD |
| Baseline RSS before load | **400.5 MB** | TBD |
| Warm synthesis p50 (13-word sentence) | **1073.2 ms** | TBD |
| Warm synthesis p95 | **1172.5 ms** | TBD |
| Warm synthesis p99 | **1185.3 ms** | TBD |
| Audio produced | 4.42 s | — |
| Real-time factor (p50) | **0.243×** | TBD |
| CPU/wall ratio (p50) | **7.51** | TBD |
| Cache key generation (p50, 1000 iters) | **0.003 ms** | TBD |
| Cache hit p50 (load from disk) | **0.127 ms** | TBD |
| Cache hit p99 | **0.260 ms** | TBD |
| Cache speedup on repeated phrase | **~8,457×** | TBD |
| Cold start (fresh process, import + load) | 5.71 s (measured on CUDA build) | TBD |

### CPU-only torch vs the default CUDA wheel

The default `torch` wheel on PyPI is the CUDA build. On Linux it installs
~3.4 GB of `nvidia` and `triton` libraries that never load on hardware without
a GPU, which is every machine this project targets. Both builds measured on
the same box, 20 runs each:

| | torch 2.13.0+cu130 | torch 2.13.0+cpu | change |
|---|---|---|---|
| venv on disk | 5.4 GB | **1.7 GB** | **−69%** |
| Baseline RSS | 734.6 MB | **400.5 MB** | **−45%** |
| Peak RSS during synthesis | 1636.9 MB | **1305.2 MB** | **−20%** |
| Warm synthesis p50 | 1009.5 ms | 1073.2 ms | +6.3% |
| Real-time factor | 0.228× | 0.243× | +6.6% |
| Cache hit p50 | 0.119 ms | 0.127 ms | ~same |

Synthesis is about 6% slower, and in exchange the install drops by 3.7 GB and
peak memory by 332 MB. On classroom hardware that is a clearly good trade:
disk and RAM are the binding constraints, not a 60 ms difference per sentence
that the audio cache removes on any repeat anyway.

The 332 MB memory saving also matters for the RAM gate in `model_manager.py`.
`MIN_RAM_FOR_NEURAL_MB` is 1536, derived from the CUDA-build peak of 1637 MB.
With the CPU build peaking at 1305 MB there is now real headroom under that
threshold, so it is worth re-checking on actual 1-2 GB hardware whether the
cutoff can come down and let more machines run neural TTS.

### What these numbers say

**Real-time factor 0.228×.** The system generates 4.42 s of audio in ~1.01 s
of wall clock — synthesis is ~4× faster than playback on x86_64. Comfortable
here; the open question is entirely ARM, where it will be far slower.

**CPU/wall ratio 7.58.** Warm synthesis burns ~7.66 s of CPU time in ~1.01 s
of wall time, i.e. it fans out across ~7.6 of the 16 cores. This is the single
most important number for the ARM port: a Raspberry Pi 4 has **4** cores, so
this workload cannot parallelise the same way and per-sentence latency will
rise by more than the raw clock-speed difference suggests. Any ARM estimate
that ignores this would be optimistic. Measure, don't extrapolate.

**Peak RSS 1636.9 MB.** This is why `model_manager.py` refuses to load neural
backends below 1536 MB of RAM: a 1 GB XO laptop cannot hold this, and an OOM
kill mid-lesson is worse than espeak. On such devices the activity stays on
espeak-ng and never attempts the load.

**Cache hit 0.119 ms vs 1009.5 ms synthesis — ~8,480×.** A child changing one
letter and re-pressing Speak hits the cache instead of re-running the network.
The p99 cache hit (0.229 ms) is still ~4,400× faster than a synthesis, so even
the tail is effectively free. This is measured on SSD; SD-card `np.load` will
be slower and is part of the ARM TODO.

> **On the cold-start difference from the proposal.** The proposal records a
> 44 s cold start on a Windows dev machine; this run measured 5.71 s. The gap
> is environment, not a fix: here the 312 MB weight blob is already in the HF
> cache and OS page cache, and the disk is a fast SSD. The 44 s figure includes
> a cold disk read of the model on slower storage. Both are real; they measure
> different starting states. The ARM/SD-card number — the one that actually
> governs the classroom — is still TBD and is exactly why the async background
> load with an espeak placeholder is non-negotiable.

## ARM / classroom hardware — TODO

Planned on a Raspberry Pi 4 (4 GB) per the proposal. To be measured with the
same script, same sentence, same 20-run protocol:

1. Kokoro cold-start time (SD-card storage, 4 cores)
2. Peak RSS during synthesis
3. Warm synthesis p50/p95/p99 — expected well above 1 s given the 4-core limit
4. Cache hit latency on SD card (`np.load` is slower there than on SSD)
5. MMS + Kokoro co-residency: does `ModelManager` have to unload one to fit 1 GB?

If physical hardware is unavailable during community bonding, QEMU ARM64
emulation will be used as a stopgap and **clearly marked `[QEMU emulated]`**,
with real-hardware numbers to follow.

## ONNX export findings

See `scripts/export_onnx.py`. Summary of what was measured:

- **FP32 ONNX export succeeds.** `disable_complex=True` swaps TorchSTFT for
  CustomSTFT (conv1d / conv_transpose1d), which ONNX can trace. Verified
  against PyTorch on real text + real voice: **corr 0.996–0.997, SNR
  21–23 dB**. Not bit-identical — CustomSTFT is a documented approximation —
  but the same waveform.
- **Naive INT8 dynamic quantisation does NOT work on this model.** Measured
  per op type:

  | ops quantised | size | corr vs fp32 | SNR |
  |---|---|---|---|
  | Conv | 154.4 MiB | 0.104 | −2.06 dB (noise) |
  | MatMul | 296.4 MiB | 0.649 | 1.97 dB (noise) |
  | Gemm | 310.8 MiB | 0.997 | 22.29 dB (clean, no shrink) |
  | Conv+MatMul+Gemm+LSTM | 109.3 MiB | — | audio length changed |

  Two failure modes: (1) INT8 on the Conv/MatMul decoder weights drops output
  below 2 dB SNR; (2) anything touching the duration predictor (LSTM, and the
  Gemm inside `duration_proj`) shifts predicted durations through the
  `round().clamp()` step and changes the audio length. The only clean config
  (Gemm-only) saves no space.

  **Conclusion:** shipping INT8 needs static, per-channel quantisation with a
  calibration set and the duration predictor pinned at fp32 — not a one-line
  `quantize_dynamic`. Documented as follow-up rather than shipped half-working.

- **FP16 half-precision was also investigated and does not convert cleanly**
  with the available CPU tooling. `onnxconverter_common.float16` reduces the
  model to **156.0 MiB (1.99× smaller)** in ~4 s, but every resulting graph
  fails to load in onnxruntime:

  | strategy | result |
  |---|---|
  | `convert_float_to_float16(keep_io_types=True)` | invalid graph: internal `/Cast_3` node output declared float, produces float16 |
  | `keep_io_types=False` | same `/Cast_3` type error |
  | strip `value_info` + re-infer shapes | clears Cast error, next node fails: `Div` with mixed fp16/fp32 operands |
  | `auto_mixed_precision` (node-by-node validator) | inherits the base `/Cast_3` failure before it can bisect |

  Root cause is a converter bug: it does not consistently update the declared
  types of the model's own internal Cast/Div nodes, so the graph is
  structurally invalid regardless of strategy. The one path that sidesteps the
  converter — exporting fp16 **directly from a half-precision PyTorch model** —
  needs fp16 CPU kernels during tracing (this box has none) or a GPU (none
  available), so it could not be validated here.

  **Conclusion:** fp16 is the most promising compression route (2× smaller,
  and float precision loss is far gentler than INT8), but it must be produced
  where a GPU is available — trace `KModel(...).half().cuda()` and export
  natively, bypassing the buggy CPU converter entirely. This is the
  recommended next step and is a clean ~2× win once run on the right hardware.

### Compression study — bottom line

Neither post-training path ships as-is from this environment. This is a
**documented negative result, not a shipped feature** — do not claim a size
reduction that has not been validated end-to-end. The value delivered is the
rigorous characterisation: INT8's two failure modes are identified precisely,
fp16's blocker is isolated to a specific converter bug, and the concrete path
to a clean 2× fp16 build (native GPU export) is written down for whoever has
the hardware.
