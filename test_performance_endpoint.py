import requests

API_URL = "http://127.0.0.1:8000/preflight/performance"

payload = {
    "origin": "HPN",
    "destination": "IAD",
    "aircraft": "glf6",
    "departure_time": "2026-03-28T14:00:00",
    "objective": "time",
    "tas_kt": 500.0,
    "mass_kg": 28500.0,
    "cruise_altitude_ft": 43000,
}

try:
    response = requests.post(API_URL, json=payload, timeout=30)

    print("Status Code:", response.status_code)
    print("Response JSON:")
    print(response.json())

except requests.exceptions.RequestException as e:
    print("Request failed:")
    print(str(e))
except ValueError:
    print("Response was not valid JSON.")
    print("Raw response:")
    print(response.text)
