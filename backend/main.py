from pathlib import Path

from fastapi import FastAPI, HTTPException

from backend.models.schemas import PreflightRequest, Step1To3Response
from backend.services.airport_service import AirportLookupError, AirportLookupService
from backend.services.route_generator import generate_candidate_routes
from backend.services.weather_service import get_metar, WeatherServiceError


BASE_DIR = Path(__file__).resolve().parent
AIRPORT_DATA_FILE = BASE_DIR / "data" / "airports.csv"

app = FastAPI(
    title="Pre-Flight Route Recommendation API",
    version="0.1.0",
    description=(
        "Pre-flight MVP API for input validation, dynamic airport lookup from CSV, "
        "and candidate route generation."
    ),
)

startup_error = None
airport_service = None

try:
    airport_service = AirportLookupService(AIRPORT_DATA_FILE)
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
                "message": "Airport service failed to initialize.",
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


@app.get("/weather/{code}")
def weather_for_airport(code: str):
    if startup_error:
        raise HTTPException(status_code=500, detail=f"Service startup error: {startup_error}")

    try:
        lookup_code = code.strip().upper()

        # If we have the airport service, try to resolve IATA (3-letter) to ICAO
        if airport_service is not None:
            try:
                record = airport_service.get_airport_record(lookup_code)
                icao_code = record.get("icao_code") or lookup_code
            except AirportLookupError:
                # Not found in dataset; fall back to using the provided code.
                icao_code = lookup_code
        else:
            icao_code = lookup_code

        metar = get_metar(icao_code)
        return {"query_code": lookup_code, "resolved_icao": icao_code, "metar": metar}
    except WeatherServiceError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected server error: {str(e)}")


@app.post("/preflight/step1-3", response_model=Step1To3Response)
def preflight_step1_3(request: PreflightRequest):
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

        return Step1To3Response(
            request=request,
            origin_airport=origin_airport,
            destination_airport=destination_airport,
            candidate_routes=candidate_routes,
        )

    except AirportLookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected server error: {str(e)}",
        )