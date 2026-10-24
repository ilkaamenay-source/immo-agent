"""Appels Gemini (API REST, clé gratuite AI Studio). Retry + backoff sur les 429."""
import json, os, re, time, requests

def generate_json(prompt, model, max_retries=4):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}}
    delay = 8
    for attempt in range(max_retries):
        try:
            r = requests.post(url, headers={"x-goog-api-key": key}, json=body, timeout=60)
            if r.status_code in (429, 500, 503):
                time.sleep(delay); delay *= 2; continue
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
            return json.loads(text)
        except (requests.RequestException, KeyError, IndexError, json.JSONDecodeError) as e:
            print(f"  [gemini] erreur: {e}")
            time.sleep(delay); delay *= 2
    return None
