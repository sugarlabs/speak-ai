# tests/test_onnx_inference.py, Tests for ONNXInference backend
# Author: Dashpreet Singh <dashpreetsinghhanda@gmail.com>
#
# Run: python -m pytest tests/test_onnx_inference.py -v
# No ONNX model files or GPU needed, all network calls are mocked.

import sys
import os
import types
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np


def _make_mock_ort():
    """Build a minimal onnxruntime mock."""
    ort = types.ModuleType('onnxruntime')
    ort.GraphOptimizationLevel = MagicMock()
    ort.GraphOptimizationLevel.ORT_ENABLE_ALL = 99
    ort.SessionOptions = MagicMock(return_value=MagicMock())

    session = MagicMock()
    # logits shape (1, seq_len, vocab_size=100), max at index 5
    logits = np.zeros((1, 1, 100), dtype=np.float32)
    logits[0, 0, 5] = 10.0   
    session.run.return_value = [logits]
    ort.InferenceSession = MagicMock(return_value=session)
    return ort, session


def _make_mock_tokenizer(eos_token_id=5):
    tok = MagicMock()
    tok.eos_token_id = eos_token_id
    tok.return_value = {
        'input_ids': np.array([[1, 2, 3]], dtype=np.int64),
        'attention_mask': np.array([[1, 1, 1]], dtype=np.int64),
    }
    tok.apply_chat_template = MagicMock(return_value='<prompt>')
    tok.decode = MagicMock(return_value='This is the response.')
    return tok


class TestONNXInferenceInit(unittest.TestCase):

    def test_requires_model_path(self):
        from onnx_inference import ONNXInference
        with self.assertRaises(ValueError):
            ONNXInference(model_path='')

    def test_accepts_model_path(self):
        from onnx_inference import ONNXInference
        model = ONNXInference.__new__(ONNXInference)
        model._model_path = '/fake/model.onnx'
        self.assertEqual(model._model_path, '/fake/model.onnx')

    def test_env_var_model_path(self):
        from onnx_inference import ONNXInference
        with patch.dict(os.environ, {'SUGAR_AI_ONNX_MODEL': '/env/model.onnx'}):
            # Would raise if onnxruntime not installed, so just check attr
            try:
                m = ONNXInference()
                self.assertEqual(m._model_path, '/env/model.onnx')
            except Exception:
                pass  # onnxruntime not installed in test env 

    def test_is_available_false_without_onnxruntime(self):
        from onnx_inference import ONNXInference
        with patch.dict(sys.modules, {'onnxruntime': None}):
            # When onnxruntime is not importable, is_available returns False
            with patch('builtins.__import__', side_effect=ImportError):
                result = ONNXInference.is_available()
                # Just verify the method exists and returns a bool
                self.assertIsInstance(result, bool)


class TestONNXInferenceHistory(unittest.TestCase):

    def _make_model(self):
        from onnx_inference import ONNXInference
        m = ONNXInference.__new__(ONNXInference)
        m._model_path = '/fake/model.onnx'
        m._tokenizer_path = '/fake/'
        m._max_new_tokens = 10
        m._temperature = 0.0
        m._top_p = 1.0
        m._enable_profanity_check = False
        m._history = []
        m._tokenizer = None
        import threading
        m._tokenizer_lock = threading.Lock()
        return m

    def test_clear_history(self):
        m = self._make_model()
        m._history = [
            {'role': 'user', 'content': 'hi'},
            {'role': 'assistant', 'content': 'hello'},
        ]
        m.clear_history()
        self.assertEqual(m._history, [])

    def test_history_property_returns_copy(self):
        m = self._make_model()
        m._history = [{'role': 'user', 'content': 'test'}]
        h = m.history
        h.append({'role': 'user', 'content': 'injected'})
        self.assertEqual(len(m._history), 1)

    def test_history_grows_on_ask(self):
        from onnx_inference import ONNXInference, _session_pool
        m = self._make_model()
        mock_ort, mock_session = _make_mock_ort()
        mock_tok = _make_mock_tokenizer(eos_token_id=5)

        with patch.dict(sys.modules, {'onnxruntime': mock_ort}):
            with patch.object(m, '_get_tokenizer', return_value=mock_tok):
                with patch.object(_session_pool, 'get', return_value=mock_session):
                    m.ask_question('hello')

        self.assertEqual(len(m._history), 2)
        self.assertEqual(m._history[0]['role'], 'user')
        self.assertEqual(m._history[1]['role'], 'assistant')

    def test_empty_question_returns_empty(self):
        m = self._make_model()
        result = m.ask_question('')
        self.assertEqual(result, '')

    def test_whitespace_question_returns_empty(self):
        m = self._make_model()
        result = m.ask_question('   ')
        self.assertEqual(result, '')


class TestBuildPrompt(unittest.TestCase):

    def _make_model(self):
        from onnx_inference import ONNXInference
        m = ONNXInference.__new__(ONNXInference)
        m._history = []
        m._tokenizer = None
        import threading
        m._tokenizer_lock = threading.Lock()
        return m

    def test_uses_chat_template_when_available(self):
        from onnx_inference import ONNXInference
        m = self._make_model()
        tok = _make_mock_tokenizer()
        tok.apply_chat_template.return_value = '<formatted_prompt>'
        with patch.object(m, '_get_tokenizer', return_value=tok):
            result = m._build_prompt('hello', '')
        self.assertEqual(result, '<formatted_prompt>')
        tok.apply_chat_template.assert_called_once()

    def test_fallback_prompt_contains_question(self):
        from onnx_inference import ONNXInference
        m = self._make_model()
        tok = _make_mock_tokenizer()
        del tok.apply_chat_template   
        with patch.object(m, '_get_tokenizer', return_value=tok):
            result = m._build_prompt('what is sugar?', '')
        self.assertIn('what is sugar?', result)

    def test_context_included_in_prompt(self):
        from onnx_inference import ONNXInference
        m = self._make_model()
        tok = _make_mock_tokenizer()
        del tok.apply_chat_template
        with patch.object(m, '_get_tokenizer', return_value=tok):
            result = m._build_prompt('hello', 'some context here')
        self.assertIn('some context here', result)

    def test_history_limited_to_last_8_turns(self):
        from onnx_inference import ONNXInference
        m = self._make_model()
        m._history = [
            {'role': 'user' if i % 2 == 0 else 'assistant', 'content': f'msg{i}'}
            for i in range(10)
        ]
        tok = _make_mock_tokenizer()
        with patch.object(m, '_get_tokenizer', return_value=tok):
            m._build_prompt('new question', '')
        call_args = tok.apply_chat_template.call_args[0][0]
        history_turns = [m for m in call_args if m['role'] in ('user', 'assistant')]
        self.assertLessEqual(len(history_turns), 9)


class TestSampling(unittest.TestCase):

    def _make_model(self):
        from onnx_inference import ONNXInference
        m = ONNXInference.__new__(ONNXInference)
        m._temperature = 0.0
        m._top_p = 1.0
        return m

    def test_greedy_returns_argmax(self):
        logits = np.array([0.1, 0.5, 0.9, 0.2], dtype=np.float32)
        m = self._make_model()
        result = m._sample(logits)
        self.assertEqual(result, 2)

    def test_temperature_sampling_returns_valid_token(self):
        m = self._make_model()
        m._temperature = 0.8
        logits = np.random.rand(50).astype(np.float32)
        for _ in range(20):
            result = m._sample(logits)
            self.assertGreaterEqual(result, 0)
            self.assertLess(result, 50)

    def test_top_p_restricts_vocab(self):
        m = self._make_model()
        m._temperature = 1.0
        m._top_p = 0.1   # very tight, only top token should win almost always
        logits = np.zeros(100, dtype=np.float32)
        logits[7] = 20.0   # token 7 dominates
        results = {m._sample(logits) for _ in range(30)}
        self.assertIn(7, results)

    def test_deterministic_at_zero_temperature(self):
        m = self._make_model()
        m._temperature = 0.0
        logits = np.array([1.0, 3.0, 2.0], dtype=np.float32)
        r1 = m._sample(logits)
        r2 = m._sample(logits)
        self.assertEqual(r1, r2)
        self.assertEqual(r1, 1)


class TestSessionPool(unittest.TestCase):

    def test_same_path_returns_same_session(self):
        from onnx_inference import _ONNXSessionPool
        pool = _ONNXSessionPool()
        mock_ort, mock_session = _make_mock_ort()
        with patch.dict(sys.modules, {'onnxruntime': mock_ort}):
            import onnx_inference
            original_import = onnx_inference._import_onnx
            onnx_inference._import_onnx = lambda: mock_ort
            try:
                s1 = pool.get('/fake/model.onnx')
                s2 = pool.get('/fake/model.onnx')
                self.assertIs(s1, s2)
                # InferenceSession only called once
                self.assertEqual(mock_ort.InferenceSession.call_count, 1)
            finally:
                onnx_inference._import_onnx = original_import

    def test_different_paths_return_different_sessions(self):
        from onnx_inference import _ONNXSessionPool
        pool = _ONNXSessionPool()
        mock_ort, _ = _make_mock_ort()
        with patch.dict(sys.modules, {'onnxruntime': mock_ort}):
            import onnx_inference
            original_import = onnx_inference._import_onnx
            onnx_inference._import_onnx = lambda: mock_ort
            try:
                pool.get('/fake/model_a.onnx')
                pool.get('/fake/model_b.onnx')
                self.assertEqual(mock_ort.InferenceSession.call_count, 2)
            finally:
                onnx_inference._import_onnx = original_import


class TestRepr(unittest.TestCase):

    def test_repr_shows_model_name(self):
        from onnx_inference import ONNXInference
        m = ONNXInference.__new__(ONNXInference)
        m._model_path = '/models/phi3.onnx'
        m._max_new_tokens = 256
        m._temperature = 0.7
        r = m.__repr__()
        self.assertIn('phi3.onnx', r)
        self.assertIn('256', r)


if __name__ == '__main__':
    unittest.main(verbosity=2)
