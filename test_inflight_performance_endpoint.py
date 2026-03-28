import requests

API_URL = "http://127.0.0.1:8000/inflight/performance"

payload = {
    "destination": "IAD",
    "aircraft": "c550",
    "current_time": "2026-03-28T14:00:00",
    "current_lat": 40.8501,
    "current_lon": -73.1515,
    "current_altitude_ft": 35000,
    "current_mass_kg": 9500,
    "remaining_fuel_kg": 1800,
    "current_tas_kt": 380,
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
