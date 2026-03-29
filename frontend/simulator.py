from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
import math
import requests


EARTH_RADIUS_NM = 3440.065  # nautical miles


def haversine_distance_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_NM * c


def destination_point(
    lat: float, lon: float, bearing_deg: float, distance_nm: float
) -> tuple[float, float]:
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    bearing = math.radians(bearing_deg)
    angular_distance = distance_nm / EARTH_RADIUS_NM

    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular_distance)
        + math.cos(lat1) * math.sin(angular_distance) * math.cos(bearing)
    )

    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(angular_distance) * math.cos(lat1),
        math.cos(angular_distance) - math.sin(lat1) * math.sin(lat2),
    )

    return math.degrees(lat2), ((math.degrees(lon2) + 540) % 360) - 180


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    dlon = lon2_rad - lon1_rad
    x = math.sin(dlon) * math.cos(lat2_rad)
    y = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(
        lat2_rad
    ) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


@dataclass
class SimulationState:
    current_lat: float
    current_lon: float
    destination: str
    aircraft: str
    simulation_time: datetime
    tas_kt: float
    mass_kg: float
    cruise_altitude_ft: int
    objective: str = "fuel"
    current_route_id: Optional[str] = None
    step_minutes: float = 5.0

    def to_payload(self) -> Dict[str, Any]:
        payload = {
            "current_lat": self.current_lat,
            "current_lon": self.current_lon,
            "destination": self.destination,
            "aircraft": self.aircraft,
            "simulation_time": self.simulation_time.isoformat(),
            "objective": self.objective,
            "tas_kt": self.tas_kt,
            "mass_kg": self.mass_kg,
            "cruise_altitude_ft": self.cruise_altitude_ft,
        }
        if self.current_route_id:
            payload["current_route_id"] = self.current_route_id
        return payload


class InFlightSimulationError(Exception):
    pass


class InFlightSimulator:
    def __init__(
        self, base_url: str = "http://localhost:8000", timeout: int = 180
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def call_inflight_performance(self, state: SimulationState) -> Dict[str, Any]:
        endpoint = f"{self.base_url}/inflight/performance"
        response = requests.post(
            endpoint, json=state.to_payload(), timeout=self.timeout
        )

        try:
            data = response.json()
        except ValueError:
            response.raise_for_status()
            raise InFlightSimulationError("Backend returned a non-JSON response.")

        if not response.ok:
            detail = data.get("detail", response.text)
            raise InFlightSimulationError(str(detail))

        return data

    def _select_active_route(
        self, result: Dict[str, Any], state: SimulationState
    ) -> Dict[str, Any]:
        target_route_id = state.current_route_id or result["best_route"]["route_id"]

        for route_perf in result["routes_performance"]:
            if route_perf["route"]["route_id"] == target_route_id:
                return route_perf

        return next(
            rp
            for rp in result["routes_performance"]
            if rp["route"]["route_id"] == result["best_route"]["route_id"]
        )

    def _choose_next_waypoint(
        self, active_route_perf: Dict[str, Any]
    ) -> tuple[float, float, float]:
        route = active_route_perf["route"]
        waypoints = route["waypoints"]

        if len(waypoints) < 2:
            raise InFlightSimulationError("Active route has fewer than 2 waypoints.")

        # For this MVP, move toward the first downstream waypoint after CURRENT_POS.
        # Since routes are regenerated from the current position each step, waypoint[1] is enough.
        next_wp = waypoints[1]
        return float(next_wp["lat"]), float(next_wp["lon"]), 0.0

    def _estimate_step_distance_nm(
        self, active_route_perf: Dict[str, Any], step_minutes: float
    ) -> float:
        # Prefer groundspeed from first segment if available
        segments = active_route_perf.get("segments_performance", [])
        if segments:
            seg0 = segments[0]
            wind = seg0.get("wind_components", {})
            gs = wind.get("estimated_groundspeed_kt")
            if gs is not None and gs > 0:
                return gs * (step_minutes / 60.0)

        tas = active_route_perf["segments_performance"][0]["tas_used_kt"]
        return tas * (step_minutes / 60.0)

    def _estimate_fuel_burn_kg(
        self, active_route_perf: Dict[str, Any], step_minutes: float
    ) -> float:
        segments = active_route_perf.get("segments_performance", [])
        if not segments:
            return 0.0

        fuel_flow_kg_s = float(segments[0]["fuel_flow_kg_s"])
        return fuel_flow_kg_s * step_minutes * 60.0

    def advance_one_step(self, state: SimulationState) -> Dict[str, Any]:
        result = self.call_inflight_performance(state)

        active_route_perf = self._select_active_route(result, state)
        state.current_route_id = active_route_perf["route"]["route_id"]

        next_lat, next_lon, _ = self._choose_next_waypoint(active_route_perf)

        distance_to_next_nm = haversine_distance_nm(
            state.current_lat,
            state.current_lon,
            next_lat,
            next_lon,
        )

        step_distance_nm = self._estimate_step_distance_nm(
            active_route_perf, state.step_minutes
        )
        move_distance_nm = min(step_distance_nm, distance_to_next_nm)

        bearing_deg = initial_bearing_deg(
            state.current_lat,
            state.current_lon,
            next_lat,
            next_lon,
        )

        new_lat, new_lon = destination_point(
            state.current_lat,
            state.current_lon,
            bearing_deg,
            move_distance_nm,
        )

        fuel_burn_kg = self._estimate_fuel_burn_kg(
            active_route_perf, state.step_minutes
        )
        new_mass = max(state.mass_kg - fuel_burn_kg, 1000.0)

        state.current_lat = new_lat
        state.current_lon = new_lon
        state.mass_kg = round(new_mass, 2)
        state.simulation_time = state.simulation_time + timedelta(
            minutes=state.step_minutes
        )

        distance_to_destination_nm = haversine_distance_nm(
            state.current_lat,
            state.current_lon,
            result["destination_airport"]["lat"],
            result["destination_airport"]["lon"],
        )

        return {
            "state": asdict(state),
            "backend_result": result,
            "active_route_id": state.current_route_id,
            "fuel_burn_kg_step": round(fuel_burn_kg, 2),
            "distance_to_destination_nm": round(distance_to_destination_nm, 2),
            "arrived": distance_to_destination_nm < 5.0,
        }