from pathlib import Path

from fastapi import FastAPI, HTTPException

from models.schemas import PreflightRequest, PreflightRoutesResponse
from services.airport_service import AirportLookupError, AirportLookupService
from services.route_generator import generate_candidate_routes
from services.segment_builder import build_all_route_segments


BASE_DIR = Path(__file__).resolve().parent
AIRPORT_DATA_FILE = BASE_DIR / "data" / "airports.csv"

app = FastAPI(
    title="Pre-Flight Route Recommendation API",
    version="0.2.0",
    description=(
        "Pre-flight MVP API for input validation, dynamic airport lookup, "
        "candidate route generation, and route segmentation."
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
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected server error: {str(e)}",
        )
