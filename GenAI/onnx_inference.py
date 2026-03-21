# Copyright (C) 2026, Srishti Jain
# This file is part of Speak.activity
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

import os
import warnings
from typing import Dict, List
from . import profainity_check

try:
    from optimum.onnxruntime import ORTModelForCausalLM
    from transformers import AutoTokenizer
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False

# Suppress warnings for cleaner output
warnings.filterwarnings("ignore")


class ONNXInference:
    def __init__(self, model_path: str, max_context_tokens: int = 1500,
                 generation_mode: int = 1, verbose: bool = False):
        """
        ONNX Runtime based inference backend.
        Mirrors the GGUFInference interface so it can be used as a
        drop-in replacement in activity.py's _try_slm_response().

        Args:
            model_path: Path to local directory containing the ONNX model
                        and tokenizer files (e.g. ./GenAI/phi3-onnx/)
            max_context_tokens: Approximate token limit for context window
            generation_mode: 1 = default (temp=0.7), 2 = low temp (0.3),
                             3 = deterministic (greedy)
            verbose: Whether to print debug info
        """
        if not ONNX_AVAILABLE:
            raise ImportError(
                "optimum and transformers are required for ONNX inference. "
                "Install via: pip install optimum[onnxruntime] transformers"
            )
        if not os.path.isdir(model_path):
            raise FileNotFoundError(
                f"ONNX model directory not found: {model_path}"
            )

        self.model_path: str = model_path
        self.max_context_tokens: int = max_context_tokens
        self.conversation_history: List[Dict[str, str]] = []
        self.generation_settings: dict = self._get_generation_settings(
            generation_mode
        )
        self.blacklisted_words = profainity_check.bad_word_list()
        self.verbose = verbose

        if self.verbose:
            print(f"Loading ONNX model from {model_path}...")

        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = ORTModelForCausalLM.from_pretrained(model_path)

        if self.verbose:
            print("ONNX model loaded successfully.")

    def _get_generation_settings(self, mode: int) -> Dict:
        """Get generation settings based on mode.
        Mirrors GGUFInference._get_generation_settings() exactly.
        """
        base_settings = {
            "max_new_tokens": 200,
            "top_p": 0.9,
            "top_k": 50,
            "repetition_penalty": 1.1,
        }

        if mode == 1:   # Default
            base_settings["temperature"] = 0.7
            base_settings["do_sample"] = True
        elif mode == 2:  # Low temp
            base_settings["temperature"] = 0.3
            base_settings["do_sample"] = True
        elif mode == 3:  # Deterministic / greedy
            base_settings["do_sample"] = False
        else:
            raise ValueError(f"Invalid mode: {mode}. Must be 1, 2, or 3.")

        return base_settings

    def set_generation_mode(self, mode: int):
        self.generation_settings = self._get_generation_settings(mode)

    def _contains_profanity(self, text: str) -> bool:
        """
        Check if text contains blacklisted words (whole word match only).
        Mirrors GGUFInference._contains_profanity() exactly.
        """
        words = [w.strip(".,!?;:()[]{}\"'").lower() for w in text.split()]
        blacklist = set(word.lower() for word in self.blacklisted_words)
        for w in words:
            if w in blacklist:
                return True
        return False

    def _format_conversation_history(self) -> str:
        """
        Format conversation history for model input.
        Uses same Student/Teacher format as GGUFInference.
        """
        formatted = ""
        for entry in self.conversation_history:
            formatted += f"Student: {entry['student']}\n"
            formatted += f"Teacher: {entry['teacher']}\n"
        return formatted

    def _truncate_history_if_needed(self, new_student_input: str) -> str:
        """
        Truncate conversation history if context would exceed max tokens.
        Mirrors GGUFInference._truncate_history_if_needed() logic exactly.
        """
        history_str = self._format_conversation_history()
        potential_instruction = (
            f"{history_str}Student: {new_student_input}\nTeacher:"
        )

        # Approximate token count
        token_count = len(potential_instruction.split()) * 1.3

        if token_count <= self.max_context_tokens:
            return potential_instruction

        # Remove oldest entries one by one until we fit
        for i in range(len(self.conversation_history) - 1, -1, -1):
            temp_history = self.conversation_history[i:]
            temp_str = ""
            for entry in temp_history:
                temp_str += (
                    f"Student: {entry['student']}\n"
                    f"Teacher: {entry['teacher']}\n"
                )
            test_instruction = (
                f"{temp_str}Student: {new_student_input}\nTeacher:"
            )
            test_token_count = len(test_instruction.split()) * 1.3

            if test_token_count <= self.max_context_tokens:
                self.conversation_history = temp_history
                return test_instruction

        # If even a single exchange is too long, reset history
        self.conversation_history = []
        return f"Student: {new_student_input}\nTeacher:"

    def _extract_teacher_response(self, generated_text: str,
                                  instruction: str) -> str:
        """
        Extract the teacher's response from the full generated text.
        Mirrors GGUFInference._extract_teacher_response() exactly.
        """
        if instruction in generated_text:
            response_part = generated_text[len(instruction):].strip()
        else:
            response_part = generated_text.strip()

        lines = response_part.split('\n')
        teacher_response = ""

        for line in lines:
            line = line.strip()
            if line and not line.startswith("Student:"):
                teacher_response = line
                break

        if not teacher_response:
            teacher_response = response_part.split('\n')[0].strip()
        if not teacher_response:
            teacher_response = "I'm not sure how to respond to that."

        return teacher_response

    def ask_question(self, question: str,
                     maintain_conversation: bool = True) -> str:
        """
        Ask the model a question and return a response.
        Mirrors GGUFInference.ask_question() exactly so this class
        can be used as a drop-in replacement in activity.py.

        Args:
            question: The student's input text
            maintain_conversation: Whether to store this Q&A in history

        Returns:
            The teacher's response string
        """
        # Check student input for profanity
        if self._contains_profanity(question):
            blocked = "Looks like you have typed in a blacklisted word"
            if maintain_conversation:
                self.conversation_history.append({
                    "student": question,
                    "teacher": blocked
                })
            return blocked

        if maintain_conversation:
            instruction = self._truncate_history_if_needed(question)
        else:
            instruction = f"Student: {question}\nTeacher:"

        try:
            inputs = self.tokenizer(instruction, return_tensors="pt")

            outputs = self.model.generate(
                **inputs,
                **self.generation_settings,
                pad_token_id=self.tokenizer.eos_token_id
            )

            generated_text = self.tokenizer.decode(
                outputs[0], skip_special_tokens=True
            )

            teacher_response = self._extract_teacher_response(
                generated_text, instruction
            )

            # Check model output for profanity
            if self._contains_profanity(teacher_response):
                teacher_response = (
                    "Sorry, I cant answer this, can we talk about something else"
                )

            if maintain_conversation:
                self.conversation_history.append({
                    "student": question,
                    "teacher": teacher_response
                })

            return teacher_response

        except Exception as e:
            if self.verbose:
                print(f"ONNX inference error: {e}")
            return "I'm not sure how to respond to that. There has been some kind of error."


def load_onnx_model(model_path: str, **kwargs) -> ONNXInference:
    """
    Convenience function mirroring load_gguf_model() from gguf_inference.py.
    Usage in activity.py:
        from GenAI import load_onnx_model
        model = load_onnx_model("./GenAI/phi3-onnx/")
    """
    return ONNXInference(model_path, **kwargs)