import os
import requests
import json
import time

api_key = os.environ.get("GOOGLE_API_KEY")

models_to_test = [
    "gemini-flash-latest",
    "gemini-2.5-flash",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite"
]

for model in models_to_test:
    print(f"\nTesting {model} generateContent...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": "Hello"}]}]
    }
    resp = requests.post(url, json=payload)
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        print("SUCCESS! (Response skipped for brevity)")
    else:
        try:
            print(json.dumps(resp.json().get('error', {}), indent=2))
        except:
            print(resp.text)
    time.sleep(1)
