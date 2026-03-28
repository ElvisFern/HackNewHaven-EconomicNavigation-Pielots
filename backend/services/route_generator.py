import math
from typing import List

from models.schemas import AirportResponse, CandidateRoute, Waypoint


def _euclidean_degree_distance(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """
    Lightweight degree-space distance used only to scale the synthetic midpoint offset.
    This is not the flight distance and should not be used for navigation math.
    """
    dx = lon2 - lon1
    dy = lat2 - lat1
    return math.sqrt(dx * dx + dy * dy)


def _compute_perpendicular_offset(
    origin: AirportResponse,
    destination: AirportResponse,
) -> tuple[Waypoint, Waypoint]:
    """
    Generate left/right synthetic midpoint waypoints by offsetting perpendicular
    to the origin-destination direction vector.

    This is intentionally simple and suitable for MVP candidate-route generation.
    """
    lat1, lon1 = origin.lat, origin.lon
    lat2, lon2 = destination.lat, destination.lon

    # Midpoint of origin-destination
    mid_lat = (lat1 + lat2) / 2.0
    mid_lon = (lon1 + lon2) / 2.0

    # Direction vector in degree-space
    dx = lon2 - lon1
    dy = lat2 - lat1

    if dx == 0 and dy == 0:
        raise ValueError("Origin and destination coordinates are identical.")

    # Perpendicular vector
    px = -dy
    py = dx

    norm = math.sqrt(px * px + py * py)
    px /= norm
    py /= norm

    # Offset scaling in degrees
    # Small enough for short flights, capped for long flights
    route_length = _euclidean_degree_distance(lat1, lon1, lat2, lon2)
    offset = min(max(route_length * 0.15, 0.30), 1.20)

    left_mid = Waypoint(
        name="MID_LEFT",
        lat=mid_lat + py * offset,
        lon=mid_lon + px * offset,
    )

    right_mid = Waypoint(
        name="MID_RIGHT",
        lat=mid_lat - py * offset,
        lon=mid_lon - px * offset,
    )

    return left_mid, right_mid


def generate_candidate_routes(
    origin: AirportResponse,
    destination: AirportResponse,
) -> List[CandidateRoute]:
    """
    Generate three simple candidate pre-flight routes:
    - Direct route
    - Left-offset midpoint route
    - Right-offset midpoint route

    Returns Pydantic CandidateRoute objects ready for API response usage.
    """
    if origin.code == destination.code:
        raise ValueError("Origin and destination cannot be the same.")

    origin_wp = Waypoint(name=origin.code, lat=origin.lat, lon=origin.lon)
    destination_wp = Waypoint(
        name=destination.code, lat=destination.lat, lon=destination.lon
    )

    left_mid, right_mid = _compute_perpendicular_offset(origin, destination)

    routes = [
        CandidateRoute(
            route_id="A",
            type="direct",
            waypoints=[origin_wp, destination_wp],
        ),
        CandidateRoute(
            route_id="B",
            type="offset_left",
            waypoints=[origin_wp, left_mid, destination_wp],
        ),
        CandidateRoute(
            route_id="C",
            type="offset_right",
            waypoints=[origin_wp, right_mid, destination_wp],
        ),
    ]

    return routes