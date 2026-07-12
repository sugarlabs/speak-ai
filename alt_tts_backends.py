"""
Alternative TTS backends: MMS-TTS (VITS) and Piper (ONNX).

Provides on-device synthesis for languages not covered by Kokoro.
Each backend lazy-loads models on first use with thread-safe caching.
"""

import logging
import threading

import numpy as np

logger = logging.getLogger('speak')

_EMPTY_WAVEFORM = np.array([], dtype=np.float32)


class FallbackTTSBackend:
    """Base class for alternative TTS synthesizers."""

    def synthesize(self, text):
        """Return (float32_waveform, sample_rate) for the given text."""
        raise NotImplementedError

    @property
    def sample_rate(self):
        raise NotImplementedError

    @property
    def language_name(self):
        raise NotImplementedError

    def __repr__(self):
        return f"<{self.__class__.__name__} lang={getattr(self, 'lang_code', '?')}>"


class MMSTTSBackend(FallbackTTSBackend):
    """Meta MMS-TTS backend using VITS architecture.

    Covers low-resource languages with ~30 MB per language model at 16 kHz.
    """

    SUPPORTED_LANGUAGES = {
        'qu': {'model': 'facebook/mms-tts-que', 'name': 'Quechua', 'sr': 16000},
        'gn': {'model': 'facebook/mms-tts-grn', 'name': 'Guarani', 'sr': 16000},
        'ay': {'model': 'facebook/mms-tts-ayr', 'name': 'Aymara', 'sr': 16000},
        'sw': {'model': 'facebook/mms-tts-swh', 'name': 'Swahili', 'sr': 16000},
        'rw': {'model': 'facebook/mms-tts-kin', 'name': 'Kinyarwanda', 'sr': 16000},
        'ar': {'model': 'facebook/mms-tts-arb', 'name': 'Arabic', 'sr': 16000},
    }

    def __init__(self, lang_code):
        if lang_code not in self.SUPPORTED_LANGUAGES:
            raise ValueError(f"MMS does not support '{lang_code}'.")
        self.lang_code = lang_code
        self.config = self.SUPPORTED_LANGUAGES[lang_code]
        self._model = None
        self._tokenizer = None
        self._lock = threading.Lock()

    def _ensure_loaded(self):
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            try:
                from transformers import AutoTokenizer, VitsModel
            except ImportError as e:
                raise ImportError(f"MMS requires 'transformers': {e}") from e
            name = self.config['model']
            logger.debug("Loading MMS model: %s", name)
            self._tokenizer = AutoTokenizer.from_pretrained(name)
            self._model = VitsModel.from_pretrained(name)
            self._model.eval()

    def synthesize(self, text):
        if not text or not text.strip():
            return _EMPTY_WAVEFORM, self.config['sr']
        self._ensure_loaded()
        import torch
        inputs = self._tokenizer(text, return_tensors="pt")
        with torch.no_grad():
            output = self._model(**inputs)
        waveform = output.waveform.squeeze().cpu().numpy().astype(np.float32)
        return waveform, self.config['sr']

    @property
    def sample_rate(self):
        return self.config['sr']

    @property
    def language_name(self):
        return self.config['name']


class PiperBackend(FallbackTTSBackend):
    """Piper TTS backend using ONNX-optimized VITS models.

    Covers Tier 1/2 languages with ~60 MB per medium-quality voice at 22.05 kHz.
    """

    SUPPORTED_LANGUAGES = {
        'ar': {'model': 'ar_JO-kareem-medium', 'name': 'Arabic', 'sr': 22050},
        'es': {'model': 'es_ES-davefx-medium', 'name': 'Spanish', 'sr': 22050},
        'fr': {'model': 'fr_FR-siwis-medium', 'name': 'French', 'sr': 22050},
        'pt': {'model': 'pt_BR-faber-medium', 'name': 'Portuguese (BR)', 'sr': 22050},
        'hi': {'model': 'hi_IN-priyamvada-medium', 'name': 'Hindi', 'sr': 22050},
        'sw': {'model': 'sw_CD-lanfrica-medium', 'name': 'Swahili', 'sr': 22050},
        'zh': {'model': 'zh_CN-huayan-medium', 'name': 'Chinese (Mandarin)', 'sr': 22050},
    }

    def __init__(self, lang_code):
        if lang_code not in self.SUPPORTED_LANGUAGES:
            raise ValueError(f"Piper does not support '{lang_code}'.")
        self.lang_code = lang_code
        self.config = self.SUPPORTED_LANGUAGES[lang_code]
        self._engine = None
        self._lock = threading.Lock()

    def _ensure_loaded(self):
        if self._engine is not None:
            return
        with self._lock:
            if self._engine is not None:
                return
            try:
                from piper import PiperVoice
            except ImportError as e:
                raise ImportError(f"Piper requires 'piper-tts': {e}") from e
            try:
                from huggingface_hub import hf_hub_download
            except ImportError as e:
                raise ImportError(
                    "Piper requires 'huggingface_hub': pip install huggingface_hub"
                ) from e
            model_name = self.config['model']
            logger.debug("Loading Piper model: %s", model_name)
            parts = model_name.replace('-', '_').split('_')
            base = f"{parts[0]}/{parts[0]}_{parts[1]}/{parts[2]}/{parts[3]}/{model_name}"
            onnx = hf_hub_download("rhasspy/piper-voices", f"{base}.onnx")
            cfg = hf_hub_download("rhasspy/piper-voices", f"{base}.onnx.json")
            self._engine = PiperVoice.load(onnx, config_path=cfg)

    def synthesize(self, text):
        if not text or not text.strip():
            return _EMPTY_WAVEFORM, self.config['sr']
        self._ensure_loaded()
        raw = b"".join(self._engine.synthesize_stream_raw(text))
        waveform = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        return waveform, self.config['sr']

    @property
    def sample_rate(self):
        return self.config['sr']

    @property
    def language_name(self):
        return self.config['name']


LANGUAGE_BACKEND_PREFERENCE = {
    'en-us': ['primary'], 'en-gb': ['primary'],
    'es': ['primary', 'piper'], 'fr': ['primary', 'piper'],
    'hi': ['primary', 'piper'], 'it': ['primary'],
    'pt-br': ['primary', 'piper'], 'ja': ['primary'],
    'zh': ['primary', 'piper'],
    'ar': ['piper', 'primary', 'mms'],
    'sw': ['piper', 'primary', 'mms'],
    'rw': ['mms', 'primary'], 'gn': ['mms', 'primary'],
    'qu': ['mms', 'primary'], 'ay': ['mms', 'primary'],
}


def get_tts_backend(lang_code, preferred_engine=None):
    """Pick the best available backend for the given language.

    Returns None when 'primary' (Kokoro/espeak) should be used.
    """
    prefs = (
        [preferred_engine]
        if preferred_engine
        else LANGUAGE_BACKEND_PREFERENCE.get(lang_code, ['primary'])
    )
    for engine in prefs:
        if engine == 'primary':
            return None
        if engine == 'mms' and lang_code in MMSTTSBackend.SUPPORTED_LANGUAGES:
            try:
                import torch  # noqa: F401
                from transformers import AutoTokenizer, VitsModel  # noqa: F401
                return MMSTTSBackend(lang_code)
            except ImportError as e:
                logger.warning("MMS unavailable for %s: %s", lang_code, e)
                continue
        if engine == 'piper' and lang_code in PiperBackend.SUPPORTED_LANGUAGES:
            try:
                from piper import PiperVoice  # noqa: F401
                return PiperBackend(lang_code)
            except ImportError as e:
                logger.warning("Piper unavailable for %s: %s", lang_code, e)
                continue
    return None
