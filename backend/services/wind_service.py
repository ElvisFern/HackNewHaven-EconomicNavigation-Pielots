import math
from typing import List

from config.aircraft_defaults import AIRCRAFT_DEFAULTS
from models.schemas import (
    PreflightRequest,
    RouteSegmentWithWind,
    RouteWithSegmentWeather,
    RouteWithWindAnalysis,
    SegmentWindComponents,
)


class WindAnalysisService:
    def get_default_tas_kt(self, aircraft: str) -> float:
        aircraft_key = aircraft.lower()
        if aircraft_key not in AIRCRAFT_DEFAULTS:
            raise ValueError(f"Missing aircraft defaults for '{aircraft_key}'")
        return float(AIRCRAFT_DEFAULTS[aircraft_key]["tas_kt"])

    def resolve_tas_kt(self, request: PreflightRequest) -> float:
        if request.tas_kt is not None:
            return float(request.tas_kt)
        return self.get_default_tas_kt(request.aircraft)

    @staticmethod
    def _normalize_angle_deg(angle: float) -> float:
        return angle % 360.0

    def compute_wind_components(
        self,
        course_bearing_deg: float,
        wind_speed_kt: float,
        wind_direction_deg: float,
        tas_kt: float | None = None,
    ) -> SegmentWindComponents:
        relative_angle_deg = self._normalize_angle_deg(
            wind_direction_deg - course_bearing_deg
        )
        theta_rad = math.radians(relative_angle_deg)

        headwind_component = wind_speed_kt * math.cos(theta_rad)
        crosswind_component = wind_speed_kt * math.sin(theta_rad)

        tailwind_component = 0.0
        if headwind_component < 0:
            tailwind_component = abs(headwind_component)

        estimated_groundspeed = None
        if tas_kt is not None:
            estimated_groundspeed = tas_kt - headwind_component

        return SegmentWindComponents(
            headwind_component_kt=round(headwind_component, 2),
            tailwind_component_kt=round(tailwind_component, 2),
            crosswind_component_kt=round(crosswind_component, 2),
            crosswind_abs_kt=round(abs(crosswind_component), 2),
            wind_relative_angle_deg=round(relative_angle_deg, 2),
            estimated_groundspeed_kt=(
                round(estimated_groundspeed, 2)
                if estimated_groundspeed is not None
                else None
            ),
        )

    def attach_wind_components(
        self,
        request: PreflightRequest,
        routes_with_segment_weather: List[RouteWithSegmentWeather],
    ) -> tuple[float, List[RouteWithWindAnalysis]]:
        tas_kt = self.resolve_tas_kt(request)

        results: List[RouteWithWindAnalysis] = []

        for route_with_weather in routes_with_segment_weather:
            segments_with_wind: List[RouteSegmentWithWind] = []

            for segment_with_weather in route_with_weather.segments_with_weather:
                segment = segment_with_weather.segment
                weather = segment_with_weather.weather

                wind_components = self.compute_wind_components(
                    course_bearing_deg=segment.bearing_deg,
                    wind_speed_kt=weather.wind_speed_kt,
                    wind_direction_deg=weather.wind_direction_deg,
                    tas_kt=tas_kt,
                )

                segments_with_wind.append(
                    RouteSegmentWithWind(
                        segment=segment,
                        weather=weather,
                        wind_components=wind_components,
                    )
                )

            results.append(
                RouteWithWindAnalysis(
                    route=route_with_weather.route,
                    segments_with_wind=segments_with_wind,
                )
            )

        return tas_kt, results