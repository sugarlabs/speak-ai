import pytest
from kokoro.pipeline import KPipeline
import torch

class MockModel:
    def __init__(self):
        self.device = "cpu"
    def __call__(self, *args, **kwargs):
        class MockOutput:
            audio = torch.zeros(10)
            pred_dur = torch.ones(5, dtype=torch.long)
        return MockOutput()
    def eval(self):
        return self

class TestPipelineIntegration:
    def test_hindi_pipeline_initialization(self):
        pipeline = KPipeline(lang_code='h', model=False)
        assert pipeline.lang_code == 'h'
        # The g2p should be our CustomG2PWrapper
        assert hasattr(pipeline.g2p, 'lc')
        assert pipeline.g2p.lc == 'h'

    def test_arabic_pipeline_initialization(self):
        pipeline = KPipeline(lang_code='r', model=False)
        assert pipeline.lang_code == 'r'
        assert hasattr(pipeline.g2p, 'lc')
        assert pipeline.g2p.lc == 'r'

    def test_pipeline_generation_hindi(self):
        pipeline = KPipeline(lang_code='h', model=False)
        generator = pipeline("नमस्ते", voice="hi_voice", model=MockModel())
        results = list(generator)
        assert len(results) > 0
        assert results[0].phonemes == "nəməsteː"

    def test_pipeline_generation_arabic(self):
        pipeline = KPipeline(lang_code='r', model=False)
        generator = pipeline("مرحبا", voice="ar_voice", model=MockModel())
        results = list(generator)
        assert len(results) > 0
        assert "mrħbaː" in results[0].phonemes

    def test_pipeline_generation_swahili(self):
        pipeline = KPipeline(lang_code='s', model=False)
        generator = pipeline("jambo", voice="sw_voice", model=MockModel())
        results = list(generator)
        assert len(results) > 0
        assert results[0].phonemes == "ʄambɔ"
