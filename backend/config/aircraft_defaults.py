from __future__ import annotations

from typing import Any, Dict

# Small safe fallback so the backend can still boot even if OpenAP is unavailable
FALLBACK_AIRCRAFT_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "c550": {
        "display_name": "Cessna Citation 550",
        "tas_kt": 380.0,
        "mass_kg": 10000.0,
        "cruise_altitude_ft": 35000,
    },
    "glf6": {
        "display_name": "Gulfstream G650",
        "tas_kt": 488.0,
        "mass_kg": 30000.0,
        "cruise_altitude_ft": 41000,
    },
}


def _first_number(*values: Any) -> float | None:
    for value in values:
        if value is None:
            continue
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _safe_int(value: Any, default: int) -> int:
    try:
        if value is None:
            return default
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _estimate_tas_kt(aircraft_data: dict[str, Any]) -> float:
    # Try common cruise / max-speed style fields first
    tas = _first_number(
        aircraft_data.get("cruise", {}).get("tas"),
        aircraft_data.get("cruise", {}).get("mach"),
        aircraft_data.get("v_cruise"),
        aircraft_data.get("vmo"),
        aircraft_data.get("max_speed"),
    )

    if tas is None:
        mtow = _first_number(aircraft_data.get("mtow"), aircraft_data.get("limits", {}).get("MTOW"))
        if mtow is not None:
            # Very rough generic estimate based on aircraft class by weight
            if mtow < 12000:
                return 320.0
            if mtow < 30000:
                return 380.0
            if mtow < 80000:
                return 450.0
            return 470.0
        return 400.0

    # If the value looks like a Mach number, convert to a reasonable TAS proxy
    if 0.3 <= tas <= 0.92:
        return round(tas * 570.0, 1)

    # Clamp extreme junk values into a defensible operating range
    return round(min(max(tas, 180.0), 520.0), 1)


def _estimate_mass_kg(aircraft_data: dict[str, Any]) -> float:
    mtow = _first_number(
        aircraft_data.get("mtow"),
        aircraft_data.get("limits", {}).get("MTOW"),
        aircraft_data.get("weight", {}).get("mtow"),
    )
    oew = _first_number(
        aircraft_data.get("oew"),
        aircraft_data.get("limits", {}).get("OEW"),
        aircraft_data.get("weight", {}).get("oew"),
    )

    if oew is not None:
        return round(oew, 1)
    if mtow is not None:
        return round(mtow * 0.78, 1)

    return 20000.0


def _estimate_cruise_altitude_ft(aircraft_data: dict[str, Any]) -> int:
    alt = _first_number(
        aircraft_data.get("cruise", {}).get("alt"),
        aircraft_data.get("cruise_alt"),
        aircraft_data.get("ceiling"),
        aircraft_data.get("service_ceiling"),
    )

    if alt is not None:
        if alt < 1000:
            # If someone stored km or other unexpected units, ignore it
            return 35000
        return _safe_int(min(max(alt, 10000), 45000), 35000)

    mtow = _first_number(aircraft_data.get("mtow"), aircraft_data.get("limits", {}).get("MTOW"))
    if mtow is not None:
        if mtow < 12000:
            return 31000
        if mtow < 30000:
            return 35000
        if mtow < 80000:
            return 39000
        return 41000

    return 35000


def _build_from_openap() -> Dict[str, Dict[str, Any]]:
    """
    Build defaults dynamically from the aircraft types that OpenAP reports.

    OpenAP docs show:
    - `openap.prop.available_aircraft()` returns supported aircraft type codes
    - `openap.prop.aircraft(typecode)` returns aircraft parameters

    We use those parameters to derive reasonable defaults for:
    - display_name
    - tas_kt
    - mass_kg
    - cruise_altitude_ft
    """
    from openap import prop

    aircraft_defaults: Dict[str, Dict[str, Any]] = {}

    for typecode in prop.available_aircraft():
        code = str(typecode).strip().lower()
        try:
            data = prop.aircraft(typecode)
        except Exception:
            continue

        if not isinstance(data, dict):
            continue

        display_name = (
            data.get("name")
            or data.get("aircraft")
            or data.get("model")
            or data.get("type")
            or code.upper()
        )

        aircraft_defaults[code] = {
            "display_name": str(display_name),
            "tas_kt": _estimate_tas_kt(data),
            "mass_kg": _estimate_mass_kg(data),
            "cruise_altitude_ft": _estimate_cruise_altitude_ft(data),
        }

    if not aircraft_defaults:
        raise RuntimeError("OpenAP returned no aircraft types.")

    return aircraft_defaults


try:
    AIRCRAFT_DEFAULTS = _build_from_openap()
except Exception:
    AIRCRAFT_DEFAULTS = FALLBACK_AIRCRAFT_DEFAULTS
