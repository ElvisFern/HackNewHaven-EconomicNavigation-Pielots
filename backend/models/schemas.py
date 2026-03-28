from datetime import datetime
from typing import List, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


SUPPORTED_AIRCRAFT = {"c550", "glf6"}


class PreflightRequest(BaseModel):
    origin: str = Field(..., min_length=3, max_length=4, description="IATA or ICAO airport code")
    destination: str = Field(..., min_length=3, max_length=4, description="IATA or ICAO airport code")
    aircraft: str = Field(..., description="Supported aircraft code")
    departure_time: datetime = Field(..., description="Planned departure datetime in ISO format")

    @field_validator("origin", "destination")
    @classmethod
    def normalize_airport_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("aircraft")
    @classmethod
    def normalize_aircraft(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in SUPPORTED_AIRCRAFT:
            raise ValueError(
                f"Unsupported aircraft '{value}'. Supported aircraft: {sorted(SUPPORTED_AIRCRAFT)}"
            )
        return value

    @model_validator(mode="after")
    def validate_route(self) -> "PreflightRequest":
        if self.origin == self.destination:
            raise ValueError("Origin and destination cannot be the same.")
        return self


class AirportResponse(BaseModel):
    code: str = Field(..., description="Airport code used in the request")
    name: str = Field(..., description="Airport name")
    lat: float = Field(..., description="Latitude in decimal degrees")
    lon: float = Field(..., description="Longitude in decimal degrees")


class Waypoint(BaseModel):
    name: str = Field(..., description="Waypoint label")
    lat: float = Field(..., ge=-90, le=90, description="Latitude in decimal degrees")
    lon: float = Field(..., ge=-180, le=180, description="Longitude in decimal degrees")


class CandidateRoute(BaseModel):
    route_id: str = Field(..., description="Unique route identifier")
    type: Literal["direct", "offset_left", "offset_right"] = Field(..., description="Route type")
    waypoints: List[Waypoint] = Field(..., min_length=2, description="Ordered waypoint list")


class RouteSegment(BaseModel):
    segment_id: str = Field(..., description="Unique segment identifier")
    start_waypoint: Waypoint
    end_waypoint: Waypoint
    distance_nm: float = Field(..., description="Segment distance in nautical miles")
    bearing_deg: float = Field(..., ge=0, lt=360, description="Initial bearing in degrees")
    midpoint_lat: float = Field(..., ge=-90, le=90, description="Midpoint latitude")
    midpoint_lon: float = Field(..., ge=-180, le=180, description="Midpoint longitude")


class RouteWithSegments(BaseModel):
    route: CandidateRoute
    segments: List[RouteSegment] = Field(..., description="Segments derived from the route")


class PreflightRoutesResponse(BaseModel):
    request: PreflightRequest
    origin_airport: AirportResponse
    destination_airport: AirportResponse
    candidate_routes: List[CandidateRoute]
    routes_with_segments: List[RouteWithSegments]
