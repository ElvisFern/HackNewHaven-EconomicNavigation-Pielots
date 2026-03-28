from typing import Any, Dict, List, Tuple

from backend.models.schemas import (
    BestRouteSummary,
    PreflightRequest,
    RoutePerformance,
    RouteWithWindAnalysis,
    SegmentPerformance,
)


class PerformanceServiceError(Exception):
    """Raised when route performance cannot be computed."""


class PerformanceService:
    """
    Uses OpenAP to estimate fuel flow, fuel burn, and CO2 for each segment,
    then aggregates results per route.
    """

    DEFAULT_MASS_KG: Dict[str, float] = {
        "c550": 10000.0,
        "glf6": 30000.0,
    }

    DEFAULT_CRUISE_ALTITUDE_FT: Dict[str, int] = {
        "c550": 35000,
        "glf6": 41000,
    }

    def get_default_mass_kg(self, aircraft: str) -> float:
        return self.DEFAULT_MASS_KG.get(aircraft.lower(), 10000.0)

    def get_default_cruise_altitude_ft(self, aircraft: str) -> int:
        return self.DEFAULT_CRUISE_ALTITUDE_FT.get(aircraft.lower(), 35000)

    def _get_openap_models(self, aircraft: str) -> Tuple[Any, Any]:
        try:
            from openap import Emission, FuelFlow

            ff_model = FuelFlow(ac=aircraft)
            em_model = Emission(ac=aircraft)
            return ff_model, em_model
        except ModuleNotFoundError as e:
            raise PerformanceServiceError(
                "The 'openap' package is not installed. Install dependencies before using performance endpoints."
            ) from e
        except Exception as e:
            raise PerformanceServiceError(
                f"Failed to initialize OpenAP models for '{aircraft}': {e}"
            ) from e

    def evaluate_routes(
        self,
        request: PreflightRequest,
        tas_used_kt: float,
        routes_with_wind_analysis: List[RouteWithWindAnalysis],
    ) -> tuple[float, int, List[RoutePerformance], BestRouteSummary]:
        aircraft = request.aircraft.lower()
        mass_kg = self.get_default_mass_kg(aircraft)
        cruise_altitude_ft = self.get_default_cruise_altitude_ft(aircraft)
        return self.evaluate_routes_with_overrides(
            aircraft=aircraft,
            tas_used_kt=tas_used_kt,
            routes_with_wind_analysis=routes_with_wind_analysis,
            mass_kg=mass_kg,
            cruise_altitude_ft=cruise_altitude_ft,
        )

    def evaluate_routes_with_overrides(
        self,
        aircraft: str,
        tas_used_kt: float,
        routes_with_wind_analysis: List[RouteWithWindAnalysis],
        mass_kg: float,
        cruise_altitude_ft: int,
    ) -> tuple[float, int, List[RoutePerformance], BestRouteSummary]:
        if mass_kg <= 0:
            raise PerformanceServiceError("mass_kg must be greater than zero.")
        if cruise_altitude_ft < 0:
            raise PerformanceServiceError(
                "cruise_altitude_ft must be zero or greater."
            )

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

        best = min(routes_performance, key=lambda r: r.total_fuel_kg)

        best_route = BestRouteSummary(
            route_id=best.route.route_id,
            route_type=best.route.type,
            total_distance_nm=best.total_distance_nm,
            total_time_min=best.total_time_min,
            total_fuel_kg=best.total_fuel_kg,
            total_co2_kg=best.total_co2_kg,
        )

        return mass_kg, cruise_altitude_ft, routes_performance, best_route
