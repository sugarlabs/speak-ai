import requests
import json
import socket
import logging
from typing import Optional

# TODO: Don't hard code these, need to see how Sugar as a whole
# manages API Keys
API_URL = "https://ai.sugarlabs.org/ask-llm-prompted"

try:
    with open("API_KEY.txt", "r") as f:
        API_KEY = f.read().strip()
except OSError:
    logging.error("Missing API_KEY.txt file.")
    API_KEY = None

DEFAULT_PROMPT = (
    "You are a friendly teacher named Jane who is 28 years old. "
    "You teach 10 year old children. Always give helpful, educational "
    "responses in simple words that children can understand. Keep your "
    "answers between 20-40 words. Be encouraging and enthusiastic but "
    "never use emojis(ever). If you notice spelling mistakes, gently "
    "correct them. Stay focused on the topic and give relevant answers."
)


def is_connected() -> bool:
    """Check if the device has an active internet connection."""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=5)
        logging.debug("Connection to 8.8.8.8 successful")
        return True
    except OSError:
        logging.error(
            "Error: No internet connection. Please check your network."
        )
        return False


def ask_llm_prompted(
    question: str,
    custom_prompt: str = DEFAULT_PROMPT,
    timeout: int = 120,
    max_length: int = 200
) -> Optional[str]:
    """Send a question to the Sugar Labs LLM API and return the response.

    Args:
        question: The user's question to send to the LLM.
        custom_prompt: System prompt for the LLM persona.
        timeout: Maximum seconds to wait for a response.
        max_length: Maximum length of the generated response.

    Returns:
        The LLM's answer as a string, or None if the request failed.
    """
    if API_KEY is None:
        logging.error("Missing API key file: API_KEY.txt")
        return None

    if not is_connected():
        return None

    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "question": question,
        "custom_prompt": custom_prompt,
        "max_length": max_length,
        "truncation": True,
        "repetition_penalty": 1.2,
        "temperature": 0.3,
        "top_p": 0.8,
        "top_k": 20
    }

    try:
        response = requests.post(
            API_URL,
            headers=headers,
            data=json.dumps(payload),
            timeout=(10, timeout),
        )

        if 500 <= response.status_code < 600:
            logging.error("Server error: %d", response.status_code)
            return None
        response.raise_for_status()

        data = response.json()

        if isinstance(data, dict) and "answer" in data:
            return data['answer']

        logging.warning("Unexpected response format: %s", type(data))
        return None

    except requests.exceptions.Timeout:
        logging.error(
            "The request timed out after %d seconds. "
            "The server might be slow.", timeout
        )
    except requests.exceptions.RequestException as e:
        logging.error("An error occurred: %s", e)
        try:
            logging.error("Response content: %s", response.text)
        except Exception:
            pass
    return None


if __name__ == "__main__":
    while True:
        answer = ask_llm_prompted(
            question=input("Enter question to LLM: "),
            custom_prompt=DEFAULT_PROMPT
        )
        if answer:
            print(f'LLM ANS: {answer}')
        else:
            print("Error, LLM did not respond")
