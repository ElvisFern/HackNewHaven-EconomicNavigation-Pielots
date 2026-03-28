import requests
from typing import Any, Dict

BASE_URL = "https://aviationweather.gov/api/data/metar"


class WeatherServiceError(RuntimeError):
    pass


def get_metar(airport_code: str, timeout: int = 10) -> Dict[str, Any]:
    """Fetch METAR data for a given airport ICAO code.

    Returns raw JSON from aviationweather.gov. Raises WeatherServiceError on failure.
    """
    params = {"ids": airport_code.upper(), "format": "json"}
    try:
        resp = requests.get(BASE_URL, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        raise WeatherServiceError(f"Failed to fetch METAR for {airport_code}: {e}")
