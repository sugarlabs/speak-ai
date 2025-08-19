import requests
import json
import socket
import logging

#TODO: Dont hard code these, need to see how sugar as a whole manages API Keys
API_URL = "https://ai.sugarlabs.org/ask-llm-prompted"
with open("API_KEY.txt", "r") as f:
    API_KEY = f.read().strip()

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
            return data['answer']

        else:
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
