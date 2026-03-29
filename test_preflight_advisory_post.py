import json
import requests

API_URL = "http://127.0.0.1:8000/preflight/advisory"

payload = {
    "origin": "HPN",
    "destination": "IAD",
    "aircraft": "c550",
    "departure_time": "2026-03-28T14:00:00",
}

try:
    response = requests.post(API_URL, json=payload, timeout=120)
    print("Status Code:", response.status_code)

    try:
        data = response.json()
        print(json.dumps(data, indent=2))
    except ValueError:
        print("Response was not valid JSON.")
        print(response.text)
        raise SystemExit

    if response.status_code == 200:
        print("\n--- Parsed Summary ---")
        print("LLM Selected Route:", data.get("advisory_selected_route_id"))
        print("Reasoning:", data.get("advisory_reasoning"))
        print("Advisory Text:", data.get("advisory_text"))

except requests.exceptions.RequestException as e:
    print("Request failed:")
    print(str(e))