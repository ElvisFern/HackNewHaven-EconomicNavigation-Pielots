import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

from config.aircraft_defaults import AIRCRAFT_DEFAULTS
from models.schemas import (
    InFlightPerformanceResponse,
    InFlightStateRequest,
    PreflightAdvisoryResponse,
    PreflightPerformanceResponse,
    PreflightRequest,
    PreflightRoutesResponse,
    PreflightWeatherResponse,
    PreflightWindResponse,
    Waypoint,
)
from services.advisory_service import AdvisoryServiceError, GeminiAdvisoryService
from services.airport_service import AirportLookupError, AirportLookupService
from services.performance_service import PerformanceService, PerformanceServiceError
from services.route_generator import (
    generate_candidate_routes,
    generate_candidate_routes_from_position,
)
from services.runway_service import RunwayFeasibilityService, RunwayServiceError
from services.segment_builder import build_all_route_segments
from services.weather_service import PressureLevelWeatherService, WeatherServiceError
from services.wind_service import WindAnalysisService


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
AIRPORT_DATA_FILE = BASE_DIR / "data" / "airports.csv"
RUNWAY_DATA_FILE = BASE_DIR / "data" / "runways.csv"

app = FastAPI(
    title="Pre-Flight and In-Flight Route Recommendation API",
    version="0.9.0",
    description=(
        "API for pre-flight and in-flight advisory using dynamic airport lookup, "
        "candidate route generation, pressure-level weather lookup, wind analysis, "
        "OpenAP-based route performance scoring, runway feasibility checks, "
        "and Gemini-powered advisory generation."
    ),
)

startup_error = None
airport_service = None
runway_service = None
weather_service = None
wind_service = None
performance_service = None
advisory_service = None

try:
    airport_service = AirportLookupService(AIRPORT_DATA_FILE)
    runway_service = RunwayFeasibilityService(RUNWAY_DATA_FILE)
    weather_service = PressureLevelWeatherService()
    wind_service = WindAnalysisService()
    performance_service = PerformanceService()
    advisory_service = GeminiAdvisoryService()
except Exception as e:
    startup_error = str(e)


def _require_services(*services) -> None:
    if any(service is None for service in services):
        raise HTTPException(
            status_code=500,
            detail=f"Service failed to initialize: {startup_error}",
        )


def _build_runway_feasibility_pair(request: PreflightRequest):
    origin_record = airport_service.get_airport_record(request.origin)
    destination_record = airport_service.get_airport_record(request.destination)

    origin_airport = airport_service.get_airport_response(request.origin)
    destination_airport = airport_service.get_airport_response(request.destination)

    origin_runway = runway_service.evaluate_airport(
        airport_ident=origin_record["ident"],
        airport_code=origin_airport.code,
        airport_name=origin_airport.name,
        aircraft=request.aircraft,
    )

    destination_runway = runway_service.evaluate_airport(
        airport_ident=destination_record["ident"],
        airport_code=destination_airport.code,
        airport_name=destination_airport.name,
        aircraft=request.aircraft,
    )

    return (
        origin_record,
        destination_record,
        origin_airport,
        destination_airport,
        origin_runway,
        destination_runway,
    )


def _raise_if_infeasible(origin_runway: dict, destination_runway: dict) -> None:
    if not origin_runway["feasible"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Origin airport runway feasibility check failed.",
                "runway_feasibility": origin_runway,
            },
        )

    if not destination_runway["feasible"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Destination airport runway feasibility check failed.",
                "runway_feasibility": destination_runway,
            },
        )


@app.get("/")
def root():
    if startup_error:
        return {
            "status": "error",
            "message": "Service started with configuration issues.",
            "detail": startup_error,
        }

    return {
        "status": "ok",
        "message": "Pre-flight and in-flight API is running.",
        "airport_data_source": str(AIRPORT_DATA_FILE.name),
        "runway_data_source": str(RUNWAY_DATA_FILE.name),
        "supported_aircraft": sorted(AIRCRAFT_DEFAULTS.keys()),
        "supported_objectives": ["fuel", "time", "emissions"],
        "gemini_model": os.getenv("GEMINI_MODEL", "gemini-3.1-flash"),
    }


@app.get("/health")
def health():
    if startup_error:
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "message": "Service failed to initialize.",
                "detail": startup_error,
            },
        )

    return {
        "status": "ok",
        "message": "All services are healthy.",
    }


@app.get("/airport/{code}")
def get_airport(code: str):
    _require_services(airport_service)

    try:
        airport = airport_service.get_airport_record(code)
        return {
            "query_code": code.upper(),
            "airport": airport,
        }
    except AirportLookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected server error: {str(e)}",
        )


@app.post("/preflight/routes", response_model=PreflightRoutesResponse)
def generate_preflight_routes(request: PreflightRequest):
    _require_services(airport_service)

    try:
        origin_airport = airport_service.get_airport_response(request.origin)
        destination_airport = airport_service.get_airport_response(request.destination)

        candidate_routes = generate_candidate_routes(origin_airport, destination_airport)
        routes_with_segments = build_all_route_segments(candidate_routes)

        return PreflightRoutesResponse(
            request=request,
            origin_airport=origin_airport,
            destination_airport=destination_airport,
            candidate_routes=candidate_routes,
            routes_with_segments=routes_with_segments,
        )

    except AirportLookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected server error: {str(e)}")


@app.post("/preflight/weather", response_model=PreflightWeatherResponse)
def generate_preflight_weather(request: PreflightRequest):
    _require_services(airport_service, weather_service)

    try:
        origin_airport = airport_service.get_airport_response(request.origin)
        destination_airport = airport_service.get_airport_response(request.destination)

        candidate_routes = generate_candidate_routes(origin_airport, destination_airport)
        routes_with_segments = build_all_route_segments(candidate_routes)

        routes_with_segment_weather = weather_service.attach_weather_to_routes(
            request=request,
            routes_with_segments=routes_with_segments,
        )

        return PreflightWeatherResponse(
            request=request,
            origin_airport=origin_airport,
            destination_airport=destination_airport,
            routes_with_segment_weather=routes_with_segment_weather,
        )

    except AirportLookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except WeatherServiceError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected server error: {str(e)}")


@app.post("/preflight/wind", response_model=PreflightWindResponse)
def generate_preflight_wind_analysis(request: PreflightRequest):
    _require_services(airport_service, weather_service, wind_service)

    try:
        origin_airport = airport_service.get_airport_response(request.origin)
        destination_airport = airport_service.get_airport_response(request.destination)

        candidate_routes = generate_candidate_routes(origin_airport, destination_airport)
        routes_with_segments = build_all_route_segments(candidate_routes)

        routes_with_segment_weather = weather_service.attach_weather_to_routes(
            request=request,
            routes_with_segments=routes_with_segments,
        )

        tas_used_kt, routes_with_wind_analysis = wind_service.attach_wind_components(
            request=request,
            routes_with_segment_weather=routes_with_segment_weather,
        )

        return PreflightWindResponse(
            request=request,
            origin_airport=origin_airport,
            destination_airport=destination_airport,
            tas_used_kt=tas_used_kt,
            routes_with_wind_analysis=routes_with_wind_analysis,
        )

    except AirportLookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except WeatherServiceError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected server error: {str(e)}")


@app.post("/preflight/performance", response_model=PreflightPerformanceResponse)
def generate_preflight_performance(request: PreflightRequest):
    _require_services(
        airport_service,
        runway_service,
        weather_service,
        wind_service,
        performance_service,
    )

    try:
        (
            origin_record,
            destination_record,
            origin_airport,
            destination_airport,
            origin_runway,
            destination_runway,
        ) = _build_runway_feasibility_pair(request)

        _raise_if_infeasible(origin_runway, destination_runway)

        candidate_routes = generate_candidate_routes(origin_airport, destination_airport)
        routes_with_segments = build_all_route_segments(candidate_routes)

        routes_with_segment_weather = weather_service.attach_weather_to_routes(
            request=request,
            routes_with_segments=routes_with_segments,
        )

        tas_used_kt, routes_with_wind_analysis = wind_service.attach_wind_components(
            request=request,
            routes_with_segment_weather=routes_with_segment_weather,
        )

        (
            aircraft_mass_kg,
            cruise_altitude_ft,
            objective_used,
            routes_performance,
            best_route,
        ) = performance_service.evaluate_routes(
            request=request,
            tas_used_kt=tas_used_kt,
            routes_with_wind_analysis=routes_with_wind_analysis,
        )

        return PreflightPerformanceResponse(
            request=request,
            origin_airport=origin_airport,
            destination_airport=destination_airport,
            origin_runway_feasibility=origin_runway,
            destination_runway_feasibility=destination_runway,
            tas_used_kt=tas_used_kt,
            aircraft_mass_kg=aircraft_mass_kg,
            cruise_altitude_ft=cruise_altitude_ft,
            objective_used=objective_used,
            routes_performance=routes_performance,
            best_route=best_route,
        )

    except AirportLookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RunwayServiceError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except WeatherServiceError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except PerformanceServiceError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected server error: {str(e)}")


@app.post("/preflight/advisory", response_model=PreflightAdvisoryResponse)
def generate_preflight_advisory(request: PreflightRequest):
    _require_services(
        airport_service,
        runway_service,
        weather_service,
        wind_service,
        performance_service,
        advisory_service,
    )

    try:
        (
            origin_record,
            destination_record,
            origin_airport,
            destination_airport,
            origin_runway,
            destination_runway,
        ) = _build_runway_feasibility_pair(request)

        _raise_if_infeasible(origin_runway, destination_runway)

        candidate_routes = generate_candidate_routes(origin_airport, destination_airport)
        routes_with_segments = build_all_route_segments(candidate_routes)

        routes_with_segment_weather = weather_service.attach_weather_to_routes(
            request=request,
            routes_with_segments=routes_with_segments,
        )

        tas_used_kt, routes_with_wind_analysis = wind_service.attach_wind_components(
            request=request,
            routes_with_segment_weather=routes_with_segment_weather,
        )

        (
            aircraft_mass_kg,
            cruise_altitude_ft,
            objective_used,
            routes_performance,
            best_route,
        ) = performance_service.evaluate_routes(
            request=request,
            tas_used_kt=tas_used_kt,
            routes_with_wind_analysis=routes_with_wind_analysis,
        )

        perf_response = PreflightPerformanceResponse(
            request=request,
            origin_airport=origin_airport,
            destination_airport=destination_airport,
            origin_runway_feasibility=origin_runway,
            destination_runway_feasibility=destination_runway,
            tas_used_kt=tas_used_kt,
            aircraft_mass_kg=aircraft_mass_kg,
            cruise_altitude_ft=cruise_altitude_ft,
            objective_used=objective_used,
            routes_performance=routes_performance,
            best_route=best_route,
        )

        advisory = advisory_service.generate_advisory(perf_response)

        return PreflightAdvisoryResponse(
            request=request,
            objective_used=objective_used,
            origin_runway_feasibility=origin_runway,
            destination_runway_feasibility=destination_runway,
            advisory_selected_route_id=advisory["selected_route_id"],
            advisory_reasoning=advisory["reasoning"],
            advisory_text=advisory["advisory_text"],
            routes_performance=routes_performance,
        )

    except AirportLookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RunwayServiceError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except WeatherServiceError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except PerformanceServiceError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except AdvisoryServiceError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected server error: {str(e)}")


@app.post("/inflight/performance", response_model=InFlightPerformanceResponse)
def generate_inflight_performance(request: InFlightStateRequest):
    _require_services(
        airport_service,
        weather_service,
        wind_service,
        performance_service,
    )

    try:
        destination_airport = airport_service.get_airport_response(request.destination)

        candidate_routes = generate_candidate_routes_from_position(
            current_lat=request.current_lat,
            current_lon=request.current_lon,
            destination=destination_airport,
        )

        routes_with_segments = build_all_route_segments(candidate_routes)

        bridge_request = PreflightRequest(
            origin="HPN",
            destination=request.destination,
            aircraft=request.aircraft,
            departure_time=request.simulation_time,
            objective=request.objective,
            tas_kt=request.tas_kt,
            mass_kg=request.mass_kg,
            cruise_altitude_ft=request.cruise_altitude_ft,
        )

        routes_with_segment_weather = weather_service.attach_weather_to_routes(
            request=bridge_request,
            routes_with_segments=routes_with_segments,
        )

        tas_used_kt, routes_with_wind_analysis = wind_service.attach_wind_components(
            request=bridge_request,
            routes_with_segment_weather=routes_with_segment_weather,
        )

        (
            aircraft_mass_kg,
            cruise_altitude_ft,
            objective_used,
            routes_performance,
            best_route,
        ) = performance_service.evaluate_routes(
            request=bridge_request,
            tas_used_kt=tas_used_kt,
            routes_with_wind_analysis=routes_with_wind_analysis,
        )

        return InFlightPerformanceResponse(
            request=request,
            destination_airport=destination_airport,
            current_position=Waypoint(
                name="CURRENT_POS",
                lat=request.current_lat,
                lon=request.current_lon,
            ),
            tas_used_kt=tas_used_kt,
            aircraft_mass_kg=aircraft_mass_kg,
            cruise_altitude_ft=cruise_altitude_ft,
            objective_used=objective_used,
            candidate_routes=candidate_routes,
            routes_performance=routes_performance,
            best_route=best_route,
        )

    except AirportLookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except WeatherServiceError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except PerformanceServiceError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected server error: {str(e)}")
