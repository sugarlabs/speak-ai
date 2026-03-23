import requests
import json
import socket
import logging

import os

CACHE_FILE = "llm_cache.json"
CACHE_LIMIT = 50

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Error loading cache: {e}")
    return {}

def save_cache(cache):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f)
    except Exception as e:
        logging.error(f"Error saving cache: {e}")

def get_cached_response(cache, question):
    return cache.get(question)

def add_to_cache(cache, question, response):
    if len(cache) >= CACHE_LIMIT:
        cache.pop(next(iter(cache)))
    cache[question] = response
    save_cache(cache)
    logging.info(f"Cache size: {len(cache)}")

# Load cache when program starts
cache = load_cache()

#TODO: Dont hard code these, need to see how sugar as a whole manages API Keys
API_URL = "https://ai.sugarlabs.org/ask-llm-prompted"
try:
    with open("API_KEY.txt", "r") as f:
        API_KEY = f.read().strip()
except OSError:
    logging.error("Missing API_KEY.txt file.")
    API_KEY = None

DEFAULT_PROMPT = "You are a friendly teacher named Jane who is 28 years old. You teach 10 year old children. Always give helpful, educational responses in simple words that children can understand. Keep your answers between 20-40 words. Be encouraging and enthusiastic but never use emojis(ever). If you notice spelling mistakes, gently correct them. Stay focused on the topic and give relevant answers."

def is_connected():
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=5)
        logging.debug("Connection to 8.8.8.8 successful")
        return True
    except OSError:
        logging.error("Error: No internet connection. Please check your network.")
        return False

def ask_llm_prompted(question, custom_prompt = DEFAULT_PROMPT, timeout=120, max_length=200):
    if API_KEY is None:
        logging.error("Missing API key file: API_KEY.txt")
        return False

    # Normalize cache key to avoid duplicates due to case or extra spaces
    # Include prompt to ensure different prompts generate different cached responses
    cache_key = (question.strip().lower() + custom_prompt.strip().lower())    
    # Check cache first
    cached_response = get_cached_response(cache, cache_key)
    if cached_response:
        logging.info("Cache hit - returning stored response")
        return cached_response
    
    logging.info("Cache miss - calling API")

    if not is_connected():
        return False

    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "question": question,
        "custom_prompt": custom_prompt,
        "max_length": max_length,
        "truncation": True,
        "repetition_penalty": 1.2,  # Slightly higher to avoid repetition
        "temperature": 0.3,         # Lower for more consistent responses
        "top_p": 0.8,              # Slightly lower for better focus
        "top_k": 20                # Much lower for more predictable responses
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

        # Parse the JSON response.
        data = response.json()

        # Check if the 'answer' key is in the response and return it.
        if isinstance(data, dict) and "answer" in data:
            answer = data['answer']
            if answer:
                add_to_cache(cache, cache_key, answer)
                logging.info("Response saved to cache")
            return answer
        else:
            if data:
                add_to_cache(cache, cache_key, data)
                logging.info("Response saved to cache")
            return data

    except requests.exceptions.Timeout:
        logging.error(f"The request timed out after {timeout} seconds. The server might be slow.")
    except requests.exceptions.RequestException as e:
        logging.error(f"An error occurred: {e}")
        try:
            logging.error(f"Response content: {response.text}")
        except Exception:
            pass
    return False

if __name__ == "__main__":
    
    while True:
        answer = ask_llm_prompted(question=input("Enter question to LLM"),custom_prompt=DEFAULT_PROMPT)
        if answer:
            print(f'LLM ANS: {answer}')
        
        else:
            print("Error, LLM did not respond")
