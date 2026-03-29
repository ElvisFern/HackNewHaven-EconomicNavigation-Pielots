from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Tuple

import requests

from config.aircraft_defaults import AIRCRAFT_DEFAULTS
from models.schemas import (
    PreflightRequest,
    RouteSegmentWithWeather,
    RouteWithSegmentWeather,
    RouteWithSegments,
    SegmentWeather,
)


class WeatherServiceError(Exception):
    """Raised when weather data cannot be fetched or parsed."""


@dataclass(frozen=True)
class PressureLevelConfig:
    hpa: int
    wind_speed_var: str
    wind_direction_var: str
    geopotential_height_var: str
    temperature_var: str


class PressureLevelWeatherService:
    """
    Pressure-level winds aloft lookup using Open-Meteo ECMWF forecast data.

    The service chooses the pressure level whose geopotential height is closest
    to the target cruise altitude.
    """

    BASE_URL = "https://api.open-meteo.com/v1/ecmwf"

    LEVELS: List[PressureLevelConfig] = [
        PressureLevelConfig(
            700,
            "wind_speed_700hPa",
            "wind_direction_700hPa",
            "geopotential_height_700hPa",
            "temperature_700hPa",
        ),
        PressureLevelConfig(
            600,
            "wind_speed_600hPa",
            "wind_direction_600hPa",
            "geopotential_height_600hPa",
            "temperature_600hPa",
        ),
        PressureLevelConfig(
            500,
            "wind_speed_500hPa",
            "wind_direction_500hPa",
            "geopotential_height_500hPa",
            "temperature_500hPa",
        ),
        PressureLevelConfig(
            400,
            "wind_speed_400hPa",
            "wind_direction_400hPa",
            "geopotential_height_400hPa",
            "temperature_400hPa",
        ),
        PressureLevelConfig(
            300,
            "wind_speed_300hPa",
            "wind_direction_300hPa",
            "geopotential_height_300hPa",
            "temperature_300hPa",
        ),
        PressureLevelConfig(
            250,
            "wind_speed_250hPa",
            "wind_direction_250hPa",
            "geopotential_height_250hPa",
            "temperature_250hPa",
        ),
        PressureLevelConfig(
            200,
            "wind_speed_200hPa",
            "wind_direction_200hPa",
            "geopotential_height_200hPa",
            "temperature_200hPa",
        ),
    ]

    def __init__(self, timeout_seconds: int = 30) -> None:
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def feet_to_meters(feet: int) -> float:
        return feet * 0.3048

    def get_default_cruise_altitude_ft(self, aircraft: str) -> int:
        aircraft_key = aircraft.lower()
        if aircraft_key not in AIRCRAFT_DEFAULTS:
            raise WeatherServiceError(f"Missing aircraft defaults for '{aircraft_key}'")
        return int(AIRCRAFT_DEFAULTS[aircraft_key]["cruise_altitude_ft"])

    def _build_hourly_vars(self) -> List[str]:
        variables: List[str] = []
        for level in self.LEVELS:
            variables.extend(
                [
                    level.wind_speed_var,
                    level.wind_direction_var,
                    level.geopotential_height_var,
                    level.temperature_var,
                ]
            )
        return variables

    def _fetch_hourly_forecast(
        self,
        latitude: float,
        longitude: float,
        target_time: datetime,
    ) -> Dict:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(self._build_hourly_vars()),
            "wind_speed_unit": "kn",
            "temperature_unit": "celsius",
            "timezone": "UTC",
            "forecast_days": 10,
        }

        try:
            response = requests.get(
                self.BASE_URL, params=params, timeout=self.timeout_seconds
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise WeatherServiceError(f"Weather API request failed: {e}") from e

        try:
            data = response.json()
        except ValueError as e:
            raise WeatherServiceError("Weather API returned invalid JSON.") from e

        if "hourly" not in data or "time" not in data["hourly"]:
            raise WeatherServiceError(
                "Weather API response is missing hourly forecast data."
            )

        return data

    @staticmethod
    def _nearest_time_index(times: List[str], target_time: datetime) -> int:
        target_time_utc = target_time.astimezone().replace(tzinfo=None)

        best_idx = 0
        best_delta = None

        for idx, time_str in enumerate(times):
            candidate = datetime.fromisoformat(time_str)
            delta = abs((candidate - target_time_utc).total_seconds())

            if best_delta is None or delta < best_delta:
                best_idx = idx
                best_delta = delta

        return best_idx

    def _select_best_pressure_level(
        self,
        hourly: Dict,
        time_index: int,
        target_altitude_m: float,
    ) -> Tuple[PressureLevelConfig, float, float, float, float | None]:
        best_level = None
        best_height = None
        best_diff = None
        best_wind_speed = None
        best_wind_direction = None
        best_temperature = None

        for level in self.LEVELS:
            try:
                geopotential_height = hourly[level.geopotential_height_var][time_index]
                wind_speed = hourly[level.wind_speed_var][time_index]
                wind_direction = hourly[level.wind_direction_var][time_index]
                temperature = hourly[level.temperature_var][time_index]
            except KeyError as e:
                raise WeatherServiceError(
                    f"Missing expected pressure-level variable in weather response: {e}"
                ) from e

            if (
                geopotential_height is None
                or wind_speed is None
                or wind_direction is None
            ):
                continue

            diff = abs(geopotential_height - target_altitude_m)

            if best_diff is None or diff < best_diff:
                best_diff = diff
                best_level = level
                best_height = float(geopotential_height)
                best_wind_speed = float(wind_speed)
                best_wind_direction = float(wind_direction)
                best_temperature = (
                    float(temperature) if temperature is not None else None
                )

        if best_level is None:
            raise WeatherServiceError(
                "Could not match a pressure level to the target cruise altitude."
            )

        return (
            best_level,
            best_height,
            best_wind_speed,
            best_wind_direction,
            best_temperature,
        )

    def get_segment_weather(
        self,
        latitude: float,
        longitude: float,
        departure_time: datetime,
        target_cruise_altitude_ft: int,
    ) -> SegmentWeather:
        forecast = self._fetch_hourly_forecast(latitude, longitude, departure_time)
        hourly = forecast["hourly"]
        times = hourly["time"]

        time_index = self._nearest_time_index(times, departure_time)
        target_altitude_m = self.feet_to_meters(target_cruise_altitude_ft)

        (
            selected_level,
            selected_height_m,
            wind_speed_kt,
            wind_direction_deg,
            temperature_c,
        ) = self._select_best_pressure_level(hourly, time_index, target_altitude_m)

        return SegmentWeather(
            selected_pressure_level_hpa=selected_level.hpa,
            selected_geopotential_height_m=round(selected_height_m, 2),
            target_cruise_altitude_ft=target_cruise_altitude_ft,
            target_cruise_altitude_m=round(target_altitude_m, 2),
            wind_speed_kt=round(wind_speed_kt, 2),
            wind_direction_deg=round(wind_direction_deg % 360, 2),
            temperature_c=(
                round(temperature_c, 2) if temperature_c is not None else None
            ),
            forecast_time=times[time_index],
            source="open-meteo-ecmwf-pressure-level",
        )

    def attach_weather_to_routes(
        self,
        request: PreflightRequest,
        routes_with_segments: List[RouteWithSegments],
    ) -> List[RouteWithSegmentWeather]:
        target_cruise_altitude_ft = self.get_default_cruise_altitude_ft(
            request.aircraft
        )

        results: List[RouteWithSegmentWeather] = []

        for route_with_segments in routes_with_segments:
            segments_with_weather: List[RouteSegmentWithWeather] = []

            for segment in route_with_segments.segments:
                weather = self.get_segment_weather(
                    latitude=segment.midpoint_lat,
                    longitude=segment.midpoint_lon,
                    departure_time=request.departure_time,
                    target_cruise_altitude_ft=target_cruise_altitude_ft,
                )

                segments_with_weather.append(
                    RouteSegmentWithWeather(
                        segment=segment,
                        weather=weather,
                    )
                )

            results.append(
                RouteWithSegmentWeather(
                    route=route_with_segments.route,
                    segments_with_weather=segments_with_weather,
                )
            )

        return results