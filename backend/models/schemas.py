from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from config.aircraft_defaults import AIRCRAFT_DEFAULTS


SUPPORTED_AIRCRAFT = set(AIRCRAFT_DEFAULTS.keys())
SUPPORTED_OBJECTIVES = {"fuel", "time", "emissions"}


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
    objective: str = Field(
        default="fuel",
        description="Optimization objective: fuel, time, or emissions",
    )

    # Optional operating-state overrides
    tas_kt: Optional[float] = Field(
        default=None,
        gt=0,
        description="Optional true airspeed override in knots",
    )
    mass_kg: Optional[float] = Field(
        default=None,
        gt=0,
        description="Optional aircraft mass override in kilograms",
    )
    cruise_altitude_ft: Optional[int] = Field(
        default=None,
        gt=0,
        description="Optional cruise altitude override in feet",
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

    @field_validator("objective")
    @classmethod
    def normalize_objective(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in SUPPORTED_OBJECTIVES:
            raise ValueError(
                f"Unsupported objective '{value}'. Supported objectives: {sorted(SUPPORTED_OBJECTIVES)}"
            )
        return value

    @model_validator(mode="after")
    def validate_route(self) -> "PreflightRequest":
        if self.origin == self.destination:
            raise ValueError("Origin and destination cannot be the same.")
        return self


class AirportResponse(BaseModel):
    code: str
    name: str
    lat: float
    lon: float


class Waypoint(BaseModel):
    name: str
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


class CandidateRoute(BaseModel):
    route_id: str
    type: Literal["direct", "offset_left", "offset_right"]
    waypoints: List[Waypoint] = Field(..., min_length=2)


class RouteSegment(BaseModel):
    segment_id: str
    start_waypoint: Waypoint
    end_waypoint: Waypoint
    distance_nm: float
    bearing_deg: float = Field(..., ge=0, lt=360)
    midpoint_lat: float = Field(..., ge=-90, le=90)
    midpoint_lon: float = Field(..., ge=-180, le=180)


class RouteWithSegments(BaseModel):
    route: CandidateRoute
    segments: List[RouteSegment]


class PreflightRoutesResponse(BaseModel):
    request: PreflightRequest
    origin_airport: AirportResponse
    destination_airport: AirportResponse
    candidate_routes: List[CandidateRoute]
    routes_with_segments: List[RouteWithSegments]


class SegmentWeather(BaseModel):
    selected_pressure_level_hpa: int
    selected_geopotential_height_m: float
    target_cruise_altitude_ft: int
    target_cruise_altitude_m: float
    wind_speed_kt: float
    wind_direction_deg: float = Field(..., ge=0, lt=360)
    temperature_c: Optional[float] = None
    forecast_time: str
    source: str


class RouteSegmentWithWeather(BaseModel):
    segment: RouteSegment
    weather: SegmentWeather


class RouteWithSegmentWeather(BaseModel):
    route: CandidateRoute
    segments_with_weather: List[RouteSegmentWithWeather]


class PreflightWeatherResponse(BaseModel):
    request: PreflightRequest
    origin_airport: AirportResponse
    destination_airport: AirportResponse
    routes_with_segment_weather: List[RouteWithSegmentWeather]


class SegmentWindComponents(BaseModel):
    headwind_component_kt: float
    tailwind_component_kt: float
    crosswind_component_kt: float
    crosswind_abs_kt: float
    wind_relative_angle_deg: float
    estimated_groundspeed_kt: Optional[float] = None


class RouteSegmentWithWind(BaseModel):
    segment: RouteSegment
    weather: SegmentWeather
    wind_components: SegmentWindComponents


class RouteWithWindAnalysis(BaseModel):
    route: CandidateRoute
    segments_with_wind: List[RouteSegmentWithWind]


class PreflightWindResponse(BaseModel):
    request: PreflightRequest
    origin_airport: AirportResponse
    destination_airport: AirportResponse
    tas_used_kt: float
    routes_with_wind_analysis: List[RouteWithWindAnalysis]


class SegmentPerformance(BaseModel):
    segment: RouteSegment
    weather: SegmentWeather
    wind_components: SegmentWindComponents
    tas_used_kt: float
    fuel_flow_kg_s: float
    segment_time_hr: float
    segment_time_min: float
    segment_fuel_kg: float
    segment_co2_kg: float


class RoutePerformance(BaseModel):
    route: CandidateRoute
    segments_performance: List[SegmentPerformance]
    total_distance_nm: float
    total_time_hr: float
    total_time_min: float
    total_fuel_kg: float
    total_co2_kg: float


class BestRouteSummary(BaseModel):
    route_id: str
    route_type: str
    objective_used: str
    total_distance_nm: float
    total_time_min: float
    total_fuel_kg: float
    total_co2_kg: float


class RunwayMatchSummary(BaseModel):
    airport_ident: str
    length_ft: Optional[float] = None
    width_ft: Optional[float] = None
    surface: str
    surface_category: str
    lighted: bool
    le_ident: str
    he_ident: str


class AirportRunwayFeasibility(BaseModel):
    airport_ident: str
    airport_code: str
    airport_name: str
    aircraft: str
    aircraft_display_name: str
    feasible: bool
    reason: str
    required_min_runway_length_ft: int
    required_min_runway_width_ft: int
    allowed_surface_categories: List[str]
    total_runway_records: int
    usable_runway_count: int
    longest_usable_runway_ft: Optional[float] = None
    matched_runway: Optional[RunwayMatchSummary] = None


class PreflightPerformanceResponse(BaseModel):
    request: PreflightRequest
    origin_airport: AirportResponse
    destination_airport: AirportResponse
    origin_runway_feasibility: AirportRunwayFeasibility
    destination_runway_feasibility: AirportRunwayFeasibility
    tas_used_kt: float
    aircraft_mass_kg: float
    cruise_altitude_ft: int
    objective_used: str
    routes_performance: List[RoutePerformance]
    best_route: BestRouteSummary


class PreflightAdvisoryResponse(BaseModel):
    request: PreflightRequest
    objective_used: str
    origin_runway_feasibility: AirportRunwayFeasibility
    destination_runway_feasibility: AirportRunwayFeasibility
    advisory_selected_route_id: str
    advisory_reasoning: str
    advisory_text: str
    routes_performance: List[RoutePerformance]


class InFlightStateRequest(BaseModel):
    current_lat: float = Field(..., ge=-90, le=90)
    current_lon: float = Field(..., ge=-180, le=180)
    destination: str = Field(
        ..., min_length=3, max_length=4, description="IATA or ICAO airport code"
    )
    aircraft: str = Field(..., description="Supported aircraft code")
    simulation_time: datetime = Field(
        ..., description="Current simulated datetime in ISO format"
    )
    objective: str = Field(
        default="fuel",
        description="Optimization objective: fuel, time, or emissions",
    )

    tas_kt: Optional[float] = Field(
        default=None,
        gt=0,
        description="Current true airspeed in knots",
    )
    mass_kg: Optional[float] = Field(
        default=None,
        gt=0,
        description="Current aircraft mass in kilograms",
    )
    cruise_altitude_ft: Optional[int] = Field(
        default=None,
        gt=0,
        description="Current cruise altitude in feet",
    )
    current_route_id: Optional[str] = Field(
        default=None,
        description="Currently active route identifier, if any",
    )

    @field_validator("aircraft")
    @classmethod
    def normalize_aircraft_inflight(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in SUPPORTED_AIRCRAFT:
            raise ValueError(
                f"Unsupported aircraft '{value}'. Supported aircraft: {sorted(SUPPORTED_AIRCRAFT)}"
            )
        return value

    @field_validator("destination")
    @classmethod
    def normalize_destination_airport_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("objective")
    @classmethod
    def normalize_objective_inflight(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in SUPPORTED_OBJECTIVES:
            raise ValueError(
                f"Unsupported objective '{value}'. Supported objectives: {sorted(SUPPORTED_OBJECTIVES)}"
            )
        return value


class InFlightPerformanceResponse(BaseModel):
    request: InFlightStateRequest
    destination_airport: AirportResponse
    current_position: Waypoint
    tas_used_kt: float
    aircraft_mass_kg: float
    cruise_altitude_ft: int
    objective_used: str
    candidate_routes: List[CandidateRoute]
    routes_performance: List[RoutePerformance]
    best_route: BestRouteSummary
