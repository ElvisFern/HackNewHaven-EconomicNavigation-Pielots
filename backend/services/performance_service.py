from typing import List, Tuple

from openap import Emission, FuelFlow

from config.aircraft_defaults import AIRCRAFT_DEFAULTS
from models.schemas import (
    BestRouteSummary,
    PreflightRequest,
    RoutePerformance,
    RouteWithWindAnalysis,
    SegmentPerformance,
)


class PerformanceServiceError(Exception):
    """Raised when route performance cannot be computed."""


class PerformanceService:
    def get_default_mass_kg(self, aircraft: str) -> float:
        aircraft_key = aircraft.lower()
        if aircraft_key not in AIRCRAFT_DEFAULTS:
            raise PerformanceServiceError(
                f"Missing aircraft defaults for '{aircraft_key}'"
            )
        return float(AIRCRAFT_DEFAULTS[aircraft_key]["mass_kg"])

    def get_default_cruise_altitude_ft(self, aircraft: str) -> int:
        aircraft_key = aircraft.lower()
        if aircraft_key not in AIRCRAFT_DEFAULTS:
            raise PerformanceServiceError(
                f"Missing aircraft defaults for '{aircraft_key}'"
            )
        return int(AIRCRAFT_DEFAULTS[aircraft_key]["cruise_altitude_ft"])

    def resolve_mass_kg(self, request: PreflightRequest) -> float:
        if request.mass_kg is not None:
            return float(request.mass_kg)
        return self.get_default_mass_kg(request.aircraft)

    def resolve_cruise_altitude_ft(self, request: PreflightRequest) -> int:
        if request.cruise_altitude_ft is not None:
            return int(request.cruise_altitude_ft)
        return self.get_default_cruise_altitude_ft(request.aircraft)

    def _get_openap_models(self, aircraft: str) -> Tuple[FuelFlow, Emission]:
        try:
            ff_model = FuelFlow(ac=aircraft, use_synonym=True)
            em_model = Emission(ac=aircraft, use_synonym=True)
            return ff_model, em_model
        except Exception as e:
            raise PerformanceServiceError(
                f"Failed to initialize OpenAP models for '{aircraft}': {e}"
            ) from e

    def _select_best_route(
        self,
        routes_performance: List[RoutePerformance],
        objective: str,
    ) -> RoutePerformance:
        if objective == "fuel":
            return min(routes_performance, key=lambda r: r.total_fuel_kg)
        if objective == "time":
            return min(routes_performance, key=lambda r: r.total_time_min)
        if objective == "emissions":
            return min(routes_performance, key=lambda r: r.total_co2_kg)

        raise PerformanceServiceError(f"Unsupported objective selection: {objective}")

    def evaluate_routes(
        self,
        request: PreflightRequest,
        tas_used_kt: float,
        routes_with_wind_analysis: List[RouteWithWindAnalysis],
    ) -> tuple[float, int, str, List[RoutePerformance], BestRouteSummary]:
        aircraft = request.aircraft.lower()
        objective = request.objective.lower()
        mass_kg = self.resolve_mass_kg(request)
        cruise_altitude_ft = self.resolve_cruise_altitude_ft(request)

        ff_model, em_model = self._get_openap_models(aircraft)

        routes_performance: List[RoutePerformance] = []

        for route_with_wind in routes_with_wind_analysis:
            segment_results: List[SegmentPerformance] = []
            total_distance_nm = 0.0
            total_time_hr = 0.0
            total_fuel_kg = 0.0
            total_co2_kg = 0.0

            for segment_with_wind in route_with_wind.segments_with_wind:
                segment = segment_with_wind.segment
                weather = segment_with_wind.weather
                wind = segment_with_wind.wind_components

                groundspeed_kt = wind.estimated_groundspeed_kt
                if groundspeed_kt is None or groundspeed_kt <= 0:
                    raise PerformanceServiceError(
                        f"Invalid groundspeed for segment {segment.segment_id}: {groundspeed_kt}"
                    )

                segment_time_hr = segment.distance_nm / groundspeed_kt
                segment_time_sec = segment_time_hr * 3600.0

                try:
                    fuel_flow_kg_s = float(
                        ff_model.enroute(
                            mass=mass_kg,
                            tas=tas_used_kt,
                            alt=cruise_altitude_ft,
                            vs=0,
                        )
                    )
                except Exception as e:
                    raise PerformanceServiceError(
                        f"Failed OpenAP fuel flow calculation for segment {segment.segment_id}: {e}"
                    ) from e

                try:
                    co2_g_s = float(em_model.co2(fuel_flow_kg_s))
                except Exception as e:
                    raise PerformanceServiceError(
                        f"Failed OpenAP CO2 calculation for segment {segment.segment_id}: {e}"
                    ) from e

                segment_fuel_kg = fuel_flow_kg_s * segment_time_sec
                segment_co2_kg = (co2_g_s * segment_time_sec) / 1000.0

                segment_results.append(
                    SegmentPerformance(
                        segment=segment,
                        weather=weather,
                        wind_components=wind,
                        tas_used_kt=round(tas_used_kt, 2),
                        fuel_flow_kg_s=round(fuel_flow_kg_s, 4),
                        segment_time_hr=round(segment_time_hr, 4),
                        segment_time_min=round(segment_time_hr * 60.0, 2),
                        segment_fuel_kg=round(segment_fuel_kg, 2),
                        segment_co2_kg=round(segment_co2_kg, 2),
                    )
                )

                total_distance_nm += segment.distance_nm
                total_time_hr += segment_time_hr
                total_fuel_kg += segment_fuel_kg
                total_co2_kg += segment_co2_kg

            routes_performance.append(
                RoutePerformance(
                    route=route_with_wind.route,
                    segments_performance=segment_results,
                    total_distance_nm=round(total_distance_nm, 3),
                    total_time_hr=round(total_time_hr, 4),
                    total_time_min=round(total_time_hr * 60.0, 2),
                    total_fuel_kg=round(total_fuel_kg, 2),
                    total_co2_kg=round(total_co2_kg, 2),
                )
            )

        if not routes_performance:
            raise PerformanceServiceError(
                "No route performance results were generated."
            )

        best = self._select_best_route(routes_performance, objective)

        best_route = BestRouteSummary(
            route_id=best.route.route_id,
            route_type=best.route.type,
            objective_used=objective,
            total_distance_nm=best.total_distance_nm,
            total_time_min=best.total_time_min,
            total_fuel_kg=best.total_fuel_kg,
            total_co2_kg=best.total_co2_kg,
        )

        return mass_kg, cruise_altitude_ft, objective, routes_performance, best_route