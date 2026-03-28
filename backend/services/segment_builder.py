import math
from typing import List, Tuple

from backend.models.schemas import (
    CandidateRoute,
    RouteSegment,
    RouteWithSegments,
    Waypoint,
)


EARTH_RADIUS_NM = 3440.065  # nautical miles


def _to_radians(deg: float) -> float:
    return math.radians(deg)


def _to_degrees(rad: float) -> float:
    return math.degrees(rad)


def haversine_distance_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Great-circle distance between two lat/lon points in nautical miles.
    """
    lat1_rad, lon1_rad = _to_radians(lat1), _to_radians(lon1)
    lat2_rad, lon2_rad = _to_radians(lat2), _to_radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return EARTH_RADIUS_NM * c


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Initial great-circle bearing from point 1 to point 2 in degrees [0, 360).
    """
    lat1_rad, lon1_rad = _to_radians(lat1), _to_radians(lon1)
    lat2_rad, lon2_rad = _to_radians(lat2), _to_radians(lon2)

    dlon = lon2_rad - lon1_rad

    x = math.sin(dlon) * math.cos(lat2_rad)
    y = (
        math.cos(lat1_rad) * math.sin(lat2_rad)
        - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlon)
    )

    bearing_rad = math.atan2(x, y)
    bearing_deg = (_to_degrees(bearing_rad) + 360) % 360
    return bearing_deg


def midpoint(lat1: float, lon1: float, lat2: float, lon2: float) -> Tuple[float, float]:
    """
    Geographic midpoint between two coordinates.
    """
    lat1_rad, lon1_rad = _to_radians(lat1), _to_radians(lon1)
    lat2_rad, lon2_rad = _to_radians(lat2), _to_radians(lon2)

    dlon = lon2_rad - lon1_rad

    bx = math.cos(lat2_rad) * math.cos(dlon)
    by = math.cos(lat2_rad) * math.sin(dlon)

    mid_lat_rad = math.atan2(
        math.sin(lat1_rad) + math.sin(lat2_rad),
        math.sqrt((math.cos(lat1_rad) + bx) ** 2 + by**2),
    )
    mid_lon_rad = lon1_rad + math.atan2(by, math.cos(lat1_rad) + bx)

    return _to_degrees(mid_lat_rad), _to_degrees(mid_lon_rad)


def build_route_segments(route: CandidateRoute) -> List[RouteSegment]:
    """
    Build segments from consecutive waypoint pairs in a route.
    """
    waypoints = route.waypoints
    if len(waypoints) < 2:
        raise ValueError(f"Route {route.route_id} must contain at least 2 waypoints.")

    segments: List[RouteSegment] = []

    for idx in range(len(waypoints) - 1):
        start_wp: Waypoint = waypoints[idx]
        end_wp: Waypoint = waypoints[idx + 1]

        distance_nm = haversine_distance_nm(
            start_wp.lat, start_wp.lon, end_wp.lat, end_wp.lon
        )
        bearing_deg = initial_bearing_deg(
            start_wp.lat, start_wp.lon, end_wp.lat, end_wp.lon
        )
        midpoint_lat, midpoint_lon = midpoint(
            start_wp.lat, start_wp.lon, end_wp.lat, end_wp.lon
        )

        segment = RouteSegment(
            segment_id=f"{route.route_id}_{idx + 1}",
            start_waypoint=start_wp,
            end_waypoint=end_wp,
            distance_nm=round(distance_nm, 3),
            bearing_deg=round(bearing_deg, 3),
            midpoint_lat=round(midpoint_lat, 6),
            midpoint_lon=round(midpoint_lon, 6),
        )
        segments.append(segment)

    return segments


def build_all_route_segments(routes: List[CandidateRoute]) -> List[RouteWithSegments]:
    """
    Build segments for every route in the candidate route list.
    """
    results: List[RouteWithSegments] = []

    for route in routes:
        route_segments = build_route_segments(route)
        results.append(
            RouteWithSegments(
                route=route,
                segments=route_segments,
            )
        )

    return results
