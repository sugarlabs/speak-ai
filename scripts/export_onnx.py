#!/usr/bin/env python3
"""Export Kokoro-82M to ONNX, verify it against PyTorch, then quantise to INT8.

Why this script exists
----------------------
Kokoro's iSTFTNet decoder calls ``torch.istft``, which works on complex
tensors. The ONNX tracer cannot follow complex numbers, so a straight export
dies in the decoder. KModel already knows how to dodge this: pass
``disable_complex=True`` and it swaps TorchSTFT for CustomSTFT, which computes
the same transform with conv1d / conv_transpose1d — ops ONNX understands.

So the export path is:

    KModel(disable_complex=True)  ->  KModelForONNX  ->  torch.onnx.export

Exporting is the easy half. The half that actually matters is proving the
exported graph still produces the same audio, which is what --verify does.
A silently-wrong ONNX model is worse than no ONNX model at all: it will
happily emit plausible-sounding garbage and no test will notice.

Usage
-----
    python scripts/export_onnx.py                  # export + verify
    python scripts/export_onnx.py --quantize       # also emit an INT8 build
    python scripts/export_onnx.py --skip-export    # verify/quantise existing
"""

import argparse
import os
import sys
import time

import numpy as np
import torch

# Import kokoro from the repo root regardless of where this is invoked from.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from kokoro.model import KModel, KModelForONNX  # noqa: E402

REPO_ID = 'hexgrad/Kokoro-82M'
STYLE_DIM = 256      # ref_s: first 128 dims drive the decoder, last 128 the predictor
DEFAULT_OPSET = 17

# Acceptance thresholds for "same waveform, not bit-identical". Measured
# torch-vs-ONNX on this model sits at corr ~0.997 / SNR ~22 dB; these are set
# just below that so a genuine regression trips them but the known CustomSTFT
# approximation error does not. Perceptual sign-off is the PER harness's job,
# not this script's — see tests/evaluation/.
MIN_CORR = 0.99
MIN_SNR_DB = 18.0

OUT_FP32 = os.path.join(ROOT, 'kokoro.onnx')
OUT_INT8 = os.path.join(ROOT, 'kokoro_int8.onnx')


def build_dummy_inputs(seq_len=24, seed=0):
    """A synthetic (input_ids, ref_s, speed) triple, for TRACING ONLY.

    Deliberately not used for verification. A random ``ref_s`` is not a valid
    voice embedding, and feeding one in drives the decoder into a numerically
    unstable regime — output lands around 1e8 instead of [-1, 1]. That is fine
    for recording a graph, but comparing two runs of garbage tells you nothing
    about whether the export is faithful. Use build_real_inputs() for that.
    """
    torch.manual_seed(seed)
    body = torch.randint(1, 100, (1, seq_len - 2), dtype=torch.long)
    pad = torch.zeros((1, 1), dtype=torch.long)
    input_ids = torch.cat([pad, body, pad], dim=1)
    ref_s = torch.randn(1, STYLE_DIM, dtype=torch.float32)
    return input_ids, ref_s, 1.0


def build_real_inputs(text, lang_code='a', voice='af_heart'):
    """Real phonemes + a real voice embedding, which is what verification needs.

    Mirrors what KPipeline does at synthesis time: g2p the text, map phonemes
    through the model vocab, bracket with zeros, and index the voice pack by
    token count (each pack row is tuned for a specific length).
    """
    from kokoro.pipeline import KPipeline

    pipe = KPipeline(lang_code=lang_code, model=False)

    g2p_result = pipe.g2p(text)
    ps = g2p_result[0] if isinstance(g2p_result, tuple) else g2p_result

    vocab = _vocab_of(pipe)
    ids = [vocab.get(p) for p in ps]
    ids = [i for i in ids if i is not None]
    input_ids = torch.LongTensor([[0, *ids, 0]])

    pack = pipe.load_single_voice(voice)
    ref_s = pack[len(ids)]
    if ref_s.dim() == 1:
        ref_s = ref_s.unsqueeze(0)

    return input_ids, ref_s.float(), 1.0


def _vocab_of(pipe):
    """Fetch the phoneme->id table without needing a loaded KModel."""
    if getattr(pipe, 'model', None) is not None:
        return pipe.model.vocab
    import json
    from huggingface_hub import hf_hub_download
    with open(hf_hub_download(repo_id=REPO_ID, filename='config.json')) as f:
        return json.load(f)['vocab']


def load_model():
    """Load Kokoro with the ONNX-safe decoder and wrap it for export."""
    print(f"  loading {REPO_ID} with disable_complex=True ...")
    t0 = time.perf_counter()
    kmodel = KModel(repo_id=REPO_ID, disable_complex=True).eval()
    wrapped = KModelForONNX(kmodel).eval()
    print(f"  loaded in {time.perf_counter() - t0:.2f}s")
    return wrapped


def export(model, out_path, opset=DEFAULT_OPSET):
    """Trace the wrapped model to ONNX with a dynamic sequence length."""
    input_ids, ref_s, speed = build_dummy_inputs()

    print(f"  tracing to {out_path} (opset {opset}) ...")
    t0 = time.perf_counter()
    torch.onnx.export(
        model,
        (input_ids, ref_s, speed),
        out_path,
        opset_version=opset,
        input_names=['input_ids', 'ref_s', 'speed'],
        output_names=['audio', 'duration'],
        # Sequence length varies per utterance and audio length follows from it,
        # so both must stay dynamic or the graph only ever works on 24 tokens.
        dynamic_axes={
            'input_ids': {1: 'seq_len'},
            'audio': {0: 'audio_len'},
            'duration': {0: 'seq_len'},
        },
        do_constant_folding=True,
        dynamo=False,   # legacy tracer; the dynamo path chokes on the LSTM here
    )
    dt = time.perf_counter() - t0
    size_mb = os.path.getsize(out_path) / (1024 ** 2)
    print(f"  exported in {dt:.1f}s -> {size_mb:.2f} MiB")
    return size_mb


VERIFY_SENTENCES = [
    "The quick brown fox jumps over the lazy dog.",
    "Hello.",
    "She sells sea shells by the sea shore on a bright summer morning.",
]


def verify(model, onnx_path, sentences=VERIFY_SENTENCES, tol=1e-3):
    """Compare PyTorch and onnxruntime output on real text and a real voice.

    Varying sentence length on purpose: an export with a baked-in shape matches
    perfectly at the traced length and falls apart everywhere else, which is
    exactly the failure mode that slips through a single-shape check.
    """
    import onnxruntime as ort

    sess = ort.InferenceSession(onnx_path, providers=['CPUExecutionProvider'])
    all_ok = True

    # A bare Python float traces as float64, so the graph's `speed` input may be
    # double or float depending on how it got folded. Read the dtype back off
    # the graph instead of guessing — hardcoding it breaks on re-export.
    ort_dtypes = {
        'tensor(float)': np.float32,
        'tensor(double)': np.float64,
    }
    speed_dtype = next(
        (ort_dtypes.get(i.type, np.float32) for i in sess.get_inputs() if i.name == 'speed'),
        np.float32,
    )

    for text in sentences:
        input_ids, ref_s, speed = build_real_inputs(text)
        seq_len = input_ids.shape[1]

        with torch.no_grad():
            torch_audio, _ = model(input_ids, ref_s, speed)
        torch_audio = torch_audio.cpu().numpy()

        onnx_audio, _ = sess.run(
            None,
            {
                'input_ids': input_ids.numpy(),
                'ref_s': ref_s.numpy(),
                'speed': np.array(speed, dtype=speed_dtype),
            },
        )

        if torch_audio.shape != onnx_audio.shape:
            print(f"  [{seq_len:>3} tok] SHAPE MISMATCH "
                  f"torch={torch_audio.shape} onnx={onnx_audio.shape}")
            all_ok = False
            continue

        diff = torch_audio - onnx_audio
        rms_sig = float(np.sqrt((torch_audio ** 2).mean()))
        rms_err = float(np.sqrt((diff ** 2).mean()))
        snr_db = 20 * np.log10(rms_sig / rms_err) if rms_err > 0 else float('inf')
        corr = float(np.corrcoef(torch_audio, onnx_audio)[0, 1])

        # Max absolute diff is the wrong gate here. CustomSTFT is an
        # *approximation* of TorchSTFT (its own docstring says so: replicate
        # padding standing in for reflect, no DC/Nyquist correction), so the
        # exported graph is not expected to be bit-comparable. What matters is
        # whether it is the same waveform: correlation and SNR catch real
        # breakage, while a single outlying sample does not.
        ok = corr >= MIN_CORR and snr_db >= MIN_SNR_DB
        all_ok &= ok
        print(f"  [{seq_len:>3} tok] corr={corr:.6f}  SNR={snr_db:5.2f} dB  "
              f"max|d|={np.abs(diff).max():.3e}  ({'PASS' if ok else 'FAIL'})")

    return all_ok


# Dynamic INT8 quantisation does NOT work on this model. Measured per op type
# on kokoro.onnx, against fp32 torch output for "The quick brown fox ...":
#
#   ops quantised        size        corr      SNR dB
#   Conv                 154.4 MiB   0.10351    -2.06   audio destroyed
#   MatMul               296.4 MiB   0.64907     1.97   audio destroyed
#   Gemm                 310.8 MiB   0.99674    22.29   clean, but no shrink
#   MatMul,Gemm          296.4 MiB   0.64907     1.97   audio destroyed
#   Conv,MatMul,Gemm,LSTM 109.3 MiB  -           -      audio length changed
#
# Two separate failure modes. (1) Conv and MatMul carry the decoder and text
# encoder; INT8 weights there put the output below 2 dB SNR — it is noise.
# (2) Anything touching the duration path (LSTM, and the Gemm/MatMul inside
# predictor.duration_proj) shifts predicted durations, because those feed
# torch.round(...).clamp(min=1) — one flipped rounding boundary re-times every
# phoneme and the emitted audio comes out a different length entirely.
#
# Gemm-only is the sole configuration that preserves the waveform, and it
# saves nothing (310.8 MiB vs 310.4 MiB fp32 — marginally larger, since the
# quantise/dequantise nodes cost more than the weights saved).
#
# Conclusion: shipping INT8 needs static quantisation with a calibration set,
# per-channel weights, and the duration predictor held at fp32 — not a
# one-line quantize_dynamic call. Left as documented follow-up.
SAFE_QUANT_OPS = ['Gemm']


def quantize(fp32_path, int8_path, op_types=None):
    """Dynamic INT8 quantisation of the weights.

    Dynamic (not static) because it needs no calibration dataset: weights are
    quantised ahead of time, activations on the fly. For an 82M-param model
    that is the difference between a ~310 MiB and a ~110 MiB artefact, which is
    what decides whether this runs on a 1 GB classroom laptop at all.
    """
    from onnxruntime.quantization import quantize_dynamic, QuantType

    op_types = op_types or SAFE_QUANT_OPS
    print(f"  quantising -> {int8_path}  (ops: {', '.join(op_types)}) ...")
    t0 = time.perf_counter()
    quantize_dynamic(
        model_input=fp32_path,
        model_output=int8_path,
        weight_type=QuantType.QInt8,
        op_types_to_quantize=op_types,
    )
    dt = time.perf_counter() - t0

    fp32_mb = os.path.getsize(fp32_path) / (1024 ** 2)
    int8_mb = os.path.getsize(int8_path) / (1024 ** 2)
    print(f"  quantised in {dt:.1f}s")
    print(f"  {fp32_mb:.2f} MiB -> {int8_mb:.2f} MiB "
          f"({fp32_mb / int8_mb:.2f}x smaller)")
    return fp32_mb, int8_mb


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--quantize', action='store_true', help='also emit INT8 build')
    ap.add_argument('--skip-export', action='store_true', help='reuse existing kokoro.onnx')
    ap.add_argument('--opset', type=int, default=DEFAULT_OPSET)
    ap.add_argument('--tol', type=float, default=1e-3)
    ap.add_argument('--quant-ops', default=None,
                    help=f"comma-separated op types to quantise "
                         f"(default: {','.join(SAFE_QUANT_OPS)}; adding LSTM breaks the model)")
    args = ap.parse_args()

    print("=" * 62)
    print("Kokoro ONNX export")
    print("=" * 62)

    model = load_model()

    if not args.skip_export:
        print("\n[1] Export")
        export(model, OUT_FP32, opset=args.opset)
    else:
        print(f"\n[1] Export skipped, reusing {OUT_FP32}")

    print("\n[2] Numerical verification (torch vs onnxruntime)")
    ok = verify(model, OUT_FP32, tol=args.tol)

    if args.quantize:
        print("\n[3] INT8 dynamic quantisation")
        quantize(OUT_FP32, OUT_INT8, op_types=args.quant_ops.split(',') if args.quant_ops else None)
        print("\n[4] Verifying INT8 build")
        # INT8 is lossy by construction. This catches gross breakage only —
        # the number that decides whether INT8 actually ships is phoneme error
        # rate on real audio, measured by tests/evaluation/.
        int8_ok = verify(model, OUT_INT8)
        print(f"  INT8 verdict: {'usable' if int8_ok else 'NOT usable as-is'}")

    print("\n" + "=" * 62)
    print("RESULT:", "export verified" if ok else "VERIFICATION FAILED")
    print("=" * 62)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
