from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


SUPPORTED_AIRCRAFT = {"c550", "glf6"}


class PreflightRequest(BaseModel):
    origin: str = Field(
        ..., min_length=3, max_length=4, description="IATA or ICAO airport code"
    )
    destination: str = Field(
        ..., min_length=3, max_length=4, description="IATA or ICAO airport code"
    )
    aircraft: str = Field(..., description="Supported aircraft code")
    departure_time: datetime = Field(
        ..., description="Planned departure datetime in ISO format"
    )

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


class AirportRecord(BaseModel):
    iata: Optional[str] = Field(default=None, description="IATA airport code")
    icao: Optional[str] = Field(default=None, description="ICAO airport code")
    name: str = Field(..., description="Airport name")
    lat: float = Field(..., ge=-90, le=90, description="Latitude in decimal degrees")
    lon: float = Field(..., ge=-180, le=180, description="Longitude in decimal degrees")

    @field_validator("iata")
    @classmethod
    def normalize_iata(cls, value: Optional[str]) -> Optional[str]:
        return value.strip().upper() if value else value

    @field_validator("icao")
    @classmethod
    def normalize_icao(cls, value: Optional[str]) -> Optional[str]:
        return value.strip().upper() if value else value


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
    type: Literal["direct", "offset_left", "offset_right"] = Field(
        ..., description="Route type"
    )
    waypoints: List[Waypoint] = Field(
        ..., min_length=2, description="Ordered waypoint list"
    )


class Step1To3Response(BaseModel):
    request: PreflightRequest
    origin_airport: AirportResponse
    destination_airport: AirportResponse
    candidate_routes: List[CandidateRoute]