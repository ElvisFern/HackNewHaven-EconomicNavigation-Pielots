import math
from typing import Dict, List

from models.schemas import (
    PreflightRequest,
    RouteSegmentWithWeather,
    RouteSegmentWithWind,
    RouteWithSegmentWeather,
    RouteWithWindAnalysis,
    SegmentWindComponents,
)


class WindAnalysisService:
    """
    Converts weather wind direction/speed into headwind/tailwind/crosswind
    relative to the route segment bearing.
    """

    DEFAULT_TAS_KT: Dict[str, float] = {
        "c550": 380.0,
        "glf6": 488.0,
    }

    def get_default_tas_kt(self, aircraft: str) -> float:
        return self.DEFAULT_TAS_KT.get(aircraft.lower(), 400.0)

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
        """
        wind_direction_deg is the meteorological 'from' direction.

        headwind_component_kt:
            positive -> headwind
            negative -> tailwind

        crosswind_component_kt:
            signed crosswind based on sin(theta)
        """
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
        tas_kt = self.get_default_tas_kt(request.aircraft)

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