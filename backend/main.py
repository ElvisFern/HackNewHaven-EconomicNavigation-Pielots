from pathlib import Path

from fastapi import FastAPI, HTTPException

from backend.models.schemas import (
    InflightPerformanceResponse,
    InflightRequest,
    PreflightPerformanceResponse,
    PreflightRequest,
    PreflightRoutesResponse,
    PreflightWeatherResponse,
    PreflightWindResponse,
    Waypoint,
)
from backend.services.airport_service import AirportLookupError, AirportLookupService
from backend.services.performance_service import (
    PerformanceService,
    PerformanceServiceError,
)
from backend.services.route_generator import (
    generate_candidate_routes,
    generate_candidate_routes_from_waypoints,
)
from backend.services.segment_builder import build_all_route_segments
from backend.services.weather_service import (
    PressureLevelWeatherService,
    WeatherServiceError,
)
from backend.services.wind_service import WindAnalysisService


BASE_DIR = Path(__file__).resolve().parent
AIRPORT_DATA_FILE = BASE_DIR / "data" / "airports.csv"

app = FastAPI(
    title="Pre-Flight Route Recommendation API",
    version="0.5.0",
    description=(
        "Pre-flight MVP API for input validation, dynamic airport lookup, "
        "candidate route generation, route segmentation, pressure-level weather lookup, "
        "wind component analysis, and OpenAP-based route performance scoring."
    ),
)

startup_error = None
airport_service = None
weather_service = None
wind_service = None
performance_service = None

try:
    airport_service = AirportLookupService(AIRPORT_DATA_FILE)
    weather_service = PressureLevelWeatherService()
    wind_service = WindAnalysisService()
    performance_service = PerformanceService()
except Exception as e:
    startup_error = str(e)


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
        "message": "Pre-flight API is running.",
        "airport_data_source": str(AIRPORT_DATA_FILE.name),
        "supported_aircraft": ["c550", "glf6"],
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
    if airport_service is None:
        raise HTTPException(
            status_code=500,
            detail=f"Airport service failed to initialize: {startup_error}",
        )

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
    if airport_service is None:
        raise HTTPException(
            status_code=500,
            detail=f"Airport service failed to initialize: {startup_error}",
        )

    try:
        origin_airport = airport_service.get_airport_response(request.origin)
        destination_airport = airport_service.get_airport_response(request.destination)

        candidate_routes = generate_candidate_routes(
            origin_airport, destination_airport
        )
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
        raise HTTPException(
            status_code=500, detail=f"Unexpected server error: {str(e)}"
        )


@app.post("/preflight/weather", response_model=PreflightWeatherResponse)
def generate_preflight_weather(request: PreflightRequest):
    if airport_service is None or weather_service is None:
        raise HTTPException(
            status_code=500,
            detail=f"Service failed to initialize: {startup_error}",
        )

    try:
        origin_airport = airport_service.get_airport_response(request.origin)
        destination_airport = airport_service.get_airport_response(request.destination)

        candidate_routes = generate_candidate_routes(
            origin_airport, destination_airport
        )
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
        raise HTTPException(
            status_code=500, detail=f"Unexpected server error: {str(e)}"
        )


@app.post("/preflight/wind", response_model=PreflightWindResponse)
def generate_preflight_wind_analysis(request: PreflightRequest):
    if airport_service is None or weather_service is None or wind_service is None:
        raise HTTPException(
            status_code=500,
            detail=f"Service failed to initialize: {startup_error}",
        )

    try:
        origin_airport = airport_service.get_airport_response(request.origin)
        destination_airport = airport_service.get_airport_response(request.destination)

        candidate_routes = generate_candidate_routes(
            origin_airport, destination_airport
        )
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
        raise HTTPException(
            status_code=500, detail=f"Unexpected server error: {str(e)}"
        )


@app.post("/preflight/performance", response_model=PreflightPerformanceResponse)
def generate_preflight_performance(request: PreflightRequest):
    if (
        airport_service is None
        or weather_service is None
        or wind_service is None
        or performance_service is None
    ):
        raise HTTPException(
            status_code=500,
            detail=f"Service failed to initialize: {startup_error}",
        )

    try:
        origin_airport = airport_service.get_airport_response(request.origin)
        destination_airport = airport_service.get_airport_response(request.destination)

        candidate_routes = generate_candidate_routes(
            origin_airport, destination_airport
        )
        routes_with_segments = build_all_route_segments(candidate_routes)

        routes_with_segment_weather = weather_service.attach_weather_to_routes(
            request=request,
            routes_with_segments=routes_with_segments,
        )

        tas_used_kt, routes_with_wind_analysis = wind_service.attach_wind_components(
            request=request,
            routes_with_segment_weather=routes_with_segment_weather,
        )

        aircraft_mass_kg, cruise_altitude_ft, routes_performance, best_route = (
            performance_service.evaluate_routes(
                request=request,
                tas_used_kt=tas_used_kt,
                routes_with_wind_analysis=routes_with_wind_analysis,
            )
        )

        return PreflightPerformanceResponse(
            request=request,
            origin_airport=origin_airport,
            destination_airport=destination_airport,
            tas_used_kt=tas_used_kt,
            aircraft_mass_kg=aircraft_mass_kg,
            cruise_altitude_ft=cruise_altitude_ft,
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
        raise HTTPException(
            status_code=500, detail=f"Unexpected server error: {str(e)}"
        )


@app.post("/inflight/performance", response_model=InflightPerformanceResponse)
def generate_inflight_performance(request: InflightRequest):
    if (
        airport_service is None
        or weather_service is None
        or wind_service is None
        or performance_service is None
    ):
        raise HTTPException(
            status_code=500,
            detail=f"Service failed to initialize: {startup_error}",
        )

    try:
        destination_airport = airport_service.get_airport_response(request.destination)
        current_position = Waypoint(
            name="CURRENT_POSITION",
            lat=request.current_lat,
            lon=request.current_lon,
        )
        destination_waypoint = Waypoint(
            name=destination_airport.code,
            lat=destination_airport.lat,
            lon=destination_airport.lon,
        )

        candidate_routes = generate_candidate_routes_from_waypoints(
            current_position, destination_waypoint
        )
        routes_with_segments = build_all_route_segments(candidate_routes)

        routes_with_segment_weather = weather_service.attach_weather_with_overrides(
            routes_with_segments=routes_with_segments,
            forecast_time=request.current_time,
            target_cruise_altitude_ft=request.current_altitude_ft,
        )

        tas_requested = request.current_tas_kt or wind_service.get_default_tas_kt(
            request.aircraft
        )
        tas_used_kt, routes_with_wind_analysis = (
            wind_service.attach_wind_components_with_tas(
                tas_kt=tas_requested,
                routes_with_segment_weather=routes_with_segment_weather,
            )
        )

        aircraft_mass_kg = (
            request.current_mass_kg
            if request.current_mass_kg is not None
            else performance_service.get_default_mass_kg(request.aircraft)
        )

        (
            aircraft_mass_kg,
            cruise_altitude_ft,
            routes_performance,
            best_route,
        ) = performance_service.evaluate_routes_with_overrides(
            aircraft=request.aircraft,
            tas_used_kt=tas_used_kt,
            routes_with_wind_analysis=routes_with_wind_analysis,
            mass_kg=aircraft_mass_kg,
            cruise_altitude_ft=request.current_altitude_ft,
        )

        return InflightPerformanceResponse(
            request=request,
            current_position=current_position,
            destination_airport=destination_airport,
            tas_used_kt=tas_used_kt,
            aircraft_mass_kg=aircraft_mass_kg,
            cruise_altitude_ft=cruise_altitude_ft,
            remaining_fuel_kg=request.remaining_fuel_kg,
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
        raise HTTPException(
            status_code=500, detail=f"Unexpected server error: {str(e)}"
        )
