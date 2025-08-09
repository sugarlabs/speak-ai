# Copyright (C) 2025, Mebin J Thattil <mail@mebin.in>
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
    from llama_cpp import Llama
    GGUF_AVAILABLE = True
except ImportError:
    GGUF_AVAILABLE = False
    raise ImportError("llama-cpp-python is required for GGUF models. Please install via pip")

# Suppress warnings for cleaner output
warnings.filterwarnings("ignore")


class GGUFInference:
    def __init__(self, model_path: str, max_context_tokens: int = 1500,
                 generation_mode: int = 1, n_threads: int = 1,
                 verbose: bool = False):
        """ARGS:
        max_context_tokens: For the model used the actual max context window
                           is 2048, but reducing cause we use an approximation
                           while calculating the token count (*1.3)
        generation_mode: 1 = default, sets temp = 0.7
        """
        if not GGUF_AVAILABLE:
            raise ImportError("llama-cpp-python is not available. Install using pip")
        if not os.path.isfile(model_path):
            raise FileNotFoundError(f"GGUF model file not found: {model_path}")
        if not model_path.lower().endswith('.gguf'):
            raise ValueError(f"File must have .gguf extension: {model_path}")

        self.model_path: str = model_path
        self.max_context_tokens: int = max_context_tokens
        self.conversation_history: List[Dict[str, str]] = []
        self.generation_settings: dict = self._get_generation_settings(generation_mode)
        self.blacklisted_words = profainity_check.bad_word_list()

        self.model = Llama(
            model_path=model_path,
            n_ctx=max_context_tokens,
            n_threads=n_threads,
            verbose=verbose
        )

        self.generation_params = {
            "max_tokens": self.generation_settings["max_tokens"],
            "temperature": self.generation_settings["temperature"],
            "top_p": self.generation_settings["top_p"],
            "top_k": self.generation_settings["top_k"],
            "repeat_penalty": self.generation_settings["repetition_penalty"],
            "stop": ["Student:", "\nStudent:"]
        }
    
    def _get_generation_settings(self, mode: int) -> Dict:
        """Get generation settings based on mode."""
        base_settings = {
            "max_tokens": 3000,
            "top_p": 0.9,
            "top_k": 50,
            "repetition_penalty": 1.1,
        }

        if mode == 1:  # Default (temp=0.7)
            base_settings["temperature"] = 0.7

        elif mode == 2:  # Low temp (0.3)
            base_settings["temperature"] = 0.3

        elif mode == 3:  # Deterministic
            base_settings["top_p"] = 1
            base_settings["top_k"] = 0
            base_settings["repetition_penalty"] = 1
            base_settings["temperature"] = 0
        else:
            raise ValueError(f"Invalid mode: {mode}. Must be 1, 2, or 3.")

        return base_settings
    
    def set_generation_mode(self, mode: int):
        self.generation_settings = self._get_generation_settings(mode)
    
    def _contains_profanity(self, text: str) -> bool:
        """
        Check if the given text contains any profanity from the blacklist (whole word match only).
        """
        words = [w.strip(".,!?;:()[]{}\"'").lower() for w in text.split()]
        blacklist = set(word.lower() for word in self.blacklisted_words)
        for w in words:
            if w in blacklist:
                return True
        return False
    
    def _format_conversation_history(self) -> str:
        """
        Format the conversation history for model input.
        Output string of format: "Student: question\nTeacher: answer\nStudent: question2\nTeacher: answer2\n"
        """
        
        formatted_history = ""

        if not self.conversation_history:
            return formatted_history

        for entry in self.conversation_history:
            formatted_history += f"Student: {entry['student']}\n"
            formatted_history += f"Teacher: {entry['teacher']}\n"

        return formatted_history
    
    def _truncate_history_if_needed(self, new_student_input: str) -> str:
        """
        Truncate conversation history if context would exceed max tokens.
        Logic is:
        -> First try to return everything - if below limit
        -> else, remove the oldest conversation entry then check again
           if limit hit...
        -> until you reach a part where along with the current new question
           we are below limit - once that is found - return that
        """
        history_str = self._format_conversation_history()
        potential_instruction = (f"{history_str}Student: {new_student_input}"
                                f"\nTeacher:")

        # this is an approximation
        token_count = len(potential_instruction.split()) * 1.3
        
        # within limits, return as is
        if token_count <= self.max_context_tokens:
            return potential_instruction

        # Start with whole history, then if above, remove one by one
        for i in range((len(self.conversation_history) - 1), -1, -1):
            temp_history = self.conversation_history[i:]
            temp_str = ""
            for entry in temp_history:
                temp_str += (f"Student: {entry['student']}\n"
                            f"Teacher: {entry['teacher']}\n")
            # temp_str now looks like: Student: question\nTeacher: answer\n
            # Student: question2\nTeacher: answer2\n ... till
            # conversation_history[i:]

            test_instruction = (f"{temp_str}Student: {new_student_input}"
                               f"\nTeacher:")  # to check if after the new
            # student question will we cross context limit
            test_token_count = len(test_instruction.split()) * 1.3

            if test_token_count <= self.max_context_tokens:
                # Update conversation history to truncated version
                self.conversation_history = temp_history
                final_instruction = test_instruction
                return final_instruction
        
        # If even one exchange is too long, just use the current question
        final_instruction = f"Student: {new_student_input}\nTeacher:"
        self.conversation_history = []
        return final_instruction
    
    def _extract_teacher_response(self, generated_text: str, instruction: str) -> str:
        """Extract the teacher's response from generated text."""
        # Remove the instruction part from the generated text
        if instruction in generated_text:
            response_part = generated_text[len(instruction):].strip()
        else:
            response_part = generated_text.strip()
        
        # Clean up the response
        # Split by newlines and take the first meaningful line
        lines = response_part.split('\n')
        teacher_response = ""

        for line in lines:
            line = line.strip()
            if line and not line.startswith("Student:"):
                teacher_response = line
                break

        # Fallback if no good response found
        if not teacher_response:
            teacher_response = response_part.split('\n')[0].strip()
            if not teacher_response:
                teacher_response = "I'm not sure how to respond to that."

        return teacher_response
    
    def ask_question(self, question: str, maintain_conversation: bool = True) -> str:
        """
        Ask the model a single question and get a response.
        
        Args:
            question: The question to ask
            maintain_conversation: Whether to add this Q&A to conversation history
            
        Returns:
            The model's response
        """
        # Check for profanity in student input
        if self._contains_profanity(question):
            blocked_response = "Looks like you have typed in a blacklisted word"
            if maintain_conversation:
                self.conversation_history.append({"student": question, "teacher": blocked_response})
            return blocked_response

        if maintain_conversation:
            instruction = self._truncate_history_if_needed(new_student_input=question)
        else:
            instruction = f"Student: {question}\nTeacher:"
        
        try:
            # Generate response
            response = self.model(instruction, **self.generation_params)
            generated_text = response['choices'][0]['text']

            # Extract clean teacher response
            full_text = instruction + generated_text
            teacher_response = self._extract_teacher_response(full_text, instruction)

            # Check for profanity in model output
            if self._contains_profanity(teacher_response):
                blocked_response = "Sorry, I cant answer this, can we talk about something else"
                if maintain_conversation:
                    self.conversation_history.append({"student": question, "teacher": blocked_response})
                return blocked_response

            # Add to conversation history if requested
            if maintain_conversation:
                self.conversation_history.append({"student": question, "teacher": teacher_response})

            return teacher_response

        except Exception as e:
            error_msg = f"Error generating response: {e}"
            print(error_msg)
            return "I'm not sure how to respond to that. There has been some kind of error."


def load_gguf_model(model_path: str, **kwargs) -> GGUFInference:
    return GGUFInference(model_path, **kwargs)

