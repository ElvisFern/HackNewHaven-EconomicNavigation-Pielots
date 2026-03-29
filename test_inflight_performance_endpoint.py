import argparse
import json
import sys
from datetime import datetime, timedelta
from typing import Any

import requests


def pretty(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


def build_payload(args: argparse.Namespace) -> dict:
    if args.simulation_time:
        simulation_time = args.simulation_time
    else:
        simulation_time = (datetime.now() + timedelta(hours=1)).replace(
            second=0, microsecond=0
        ).isoformat()

    payload = {
        "current_lat": args.current_lat,
        "current_lon": args.current_lon,
        "destination": args.destination,
        "aircraft": args.aircraft,
        "simulation_time": simulation_time,
        "objective": args.objective,
    }

    if args.tas_kt is not None:
        payload["tas_kt"] = args.tas_kt
    if args.mass_kg is not None:
        payload["mass_kg"] = args.mass_kg
    if args.cruise_altitude_ft is not None:
        payload["cruise_altitude_ft"] = args.cruise_altitude_ft
    if args.current_route_id is not None:
        payload["current_route_id"] = args.current_route_id

    return payload


def print_summary(data: dict) -> None:
    best = data["best_route"]
    print("\n=== In-Flight Performance Summary ===")
    print(f"Objective used : {data['objective_used']}")
    print(f"Best route     : {best['route_id']} ({best['route_type']})")
    print(f"TAS used (kt)  : {data['tas_used_kt']}")
    print(f"Mass (kg)      : {data['aircraft_mass_kg']}")
    print(f"Cruise alt (ft): {data['cruise_altitude_ft']}")

    print("\n=== Route Options ===")
    for route_perf in data["routes_performance"]:
        route = route_perf["route"]
        print(
            f"- {route['route_id']} [{route['type']}] | "
            f"Distance: {route_perf['total_distance_nm']} nm | "
            f"Time: {route_perf['total_time_min']} min | "
            f"Fuel: {route_perf['total_fuel_kg']} kg | "
            f"CO2: {route_perf['total_co2_kg']} kg"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test the /inflight/performance endpoint."
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Backend base URL. Default: http://localhost:8000",
    )
    parser.add_argument(
        "--current-lat",
        type=float,
        default=41.0670,
        help="Current aircraft latitude.",
    )
    parser.add_argument(
        "--current-lon",
        type=float,
        default=-73.7076,
        help="Current aircraft longitude.",
    )
    parser.add_argument(
        "--destination",
        default="IAD",
        help="Destination airport code.",
    )
    parser.add_argument(
        "--aircraft",
        default="c550",
        help="Aircraft code supported by the backend.",
    )
    parser.add_argument(
        "--simulation-time",
        default=None,
        help="ISO datetime for the simulated current time. Default: now + 1 hour.",
    )
    parser.add_argument(
        "--objective",
        default="fuel",
        choices=["fuel", "time", "emissions"],
        help="Optimization objective.",
    )
    parser.add_argument(
        "--tas-kt",
        type=float,
        default=380.0,
        help="Optional TAS override in knots.",
    )
    parser.add_argument(
        "--mass-kg",
        type=float,
        default=9800.0,
        help="Optional mass override in kilograms.",
    )
    parser.add_argument(
        "--cruise-altitude-ft",
        type=int,
        default=35000,
        help="Optional cruise altitude override in feet.",
    )
    parser.add_argument(
        "--current-route-id",
        default="A",
        help="Optional current active route id.",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print full JSON response.",
    )

    args = parser.parse_args()
    payload = build_payload(args)
    endpoint = f"{args.base_url.rstrip('/')}/inflight/performance"

    print(f"POST {endpoint}")
    print("\nPayload:")
    print(pretty(payload))

    try:
        response = requests.post(endpoint, json=payload, timeout=180)
    except requests.RequestException as e:
        print(f"\nRequest failed before receiving a response:\n{e}", file=sys.stderr)
        return 1

    print(f"\nHTTP {response.status_code}")

    try:
        data = response.json()
    except ValueError:
        print("\nResponse was not valid JSON.")
        print(response.text)
        return 1

    if not response.ok:
        print("\nEndpoint returned an error:")
        print(pretty(data))
        return 1

    if args.raw:
        print("\nFull response:")
        print(pretty(data))
    else:
        print_summary(data)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
