import requests
import json
import logging
import os

API_URL = "https://ai.sugarlabs.org/ask-llm-prompted"


def load_api_key():
    """Fetch API key from environment variable or fallback to local file."""
    # Prioritize environment variables for production security standards
    key = os.environ.get("SUGAR_LLM_API_KEY")
    if key:
        return key.strip()

    try:
        with open("API_KEY.txt", "r") as f:
            return f.read().strip()
    except OSError:
        logging.error("Missing API_KEY.txt file and SUGAR_LLM_API_KEY env variable.")
        return None


API_KEY = load_api_key()

# Dictionary to store successful LLM responses to save battery and API costs
_llm_cache = {}
MAX_CACHE_SIZE = 50

DEFAULT_PROMPT = (
    "You are a friendly teacher named Jane who is 28 years old. "
    "You teach 10 year old children. Always give helpful, educational responses "
    "in simple words that children can understand. Keep your answers between 20-40 words. "
    "Be encouraging and enthusiastic but never use emojis(ever). If you notice spelling mistakes, "
    "gently correct them. Stay focused on the topic and give relevant answers."
)


def ask_llm_prompted(
    question, custom_prompt=DEFAULT_PROMPT, timeout=120, max_length=200
):
    """Sends a question to the LLM with optional caching for battery/cost efficiency."""
    if API_KEY is None:
        logging.error("Missing API key: Ensure SUGAR_LLM_API_KEY is set.")
        return False

    # Check cache to prevent redundant network requests and save battery
    cache_key = f"{question}_{custom_prompt}_{max_length}"
    if cache_key in _llm_cache:
        logging.debug("Returning cached LLM response.")
        answer = _llm_cache.pop(cache_key)
        _llm_cache[cache_key] = answer
        return answer
    headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

    payload = {
        "question": question,
        "custom_prompt": custom_prompt,
        "max_length": max_length,
        "truncation": True,
        "repetition_penalty": 1.2,
        "temperature": 0.3,
        "top_p": 0.8,
        "top_k": 20,
    }

    try:
        response = requests.post(
            API_URL,
            headers=headers,
            data=json.dumps(payload),
            timeout=(10, timeout),
        )

        if 500 <= response.status_code < 600:
            logging.error(f"Server error: {response.status_code}")
            return False
        response.raise_for_status()

        data = response.json()

        # Extract answer and update cache only on successful data retrieval
        if isinstance(data, dict) and "answer" in data:
            answer = data["answer"]

            # Manage cache size (LRU) to remain memory-efficient on low-RAM hardware
            if len(_llm_cache) >= MAX_CACHE_SIZE:
                # Remove the oldest item in the dictionary
                _llm_cache.pop(next(iter(_llm_cache)))

            _llm_cache[cache_key] = answer
            return answer

        else:
            return data

    except requests.exceptions.Timeout:
        logging.error(f"The request timed out after {timeout} seconds.")
    except requests.exceptions.RequestException as e:
        logging.error(f"An error occurred: {e}")

    return False


if __name__ == "__main__":
    while True:
        user_input = input("Enter question to LLM (or 'exit' to quit): ")
        if user_input.lower() == "exit":
            break
        answer = ask_llm_prompted(question=user_input, custom_prompt=DEFAULT_PROMPT)
        if answer:
            print(f"LLM ANS: {answer}")
        else:
            print("Error: LLM did not respond.")
