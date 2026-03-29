import requests
import streamlit as st
from datetime import datetime, timedelta, time
from pathlib import Path
import pandas as pd
import pydeck as pdk

st.set_page_config(page_title="AI Flight Optimizer", layout="wide")


@st.cache_data
def load_supported_aircraft() -> list[str]:
    response = requests.get(f"{BACKEND_BASE_URL}/", timeout=30)
    response.raise_for_status()
    data = response.json()
    return data["supported_aircraft"]


OBJECTIVES = ["fuel", "time", "emissions"]
BACKEND_BASE_URL = "http://localhost:8000"


@st.cache_data
def load_airport_options() -> pd.DataFrame:
    airport_file = Path(__file__).resolve().parent.parent / "backend" / "data" / "airports.csv"

    if not airport_file.exists():
        raise FileNotFoundError(
            f"Could not find airports.csv at expected path: {airport_file}"
        )

    df = pd.read_csv(airport_file)

    allowed_types = {"large_airport", "medium_airport", "small_airport"}
    df = df[df["type"].isin(allowed_types)].copy()

    for col in ["name", "municipality", "iso_country", "iata_code"]:
        df[col] = df[col].fillna("").astype(str).str.strip()

    # Keep only rows with IATA code for cleaner dropdown UX
    df = df[df["iata_code"] != ""].copy()

    df["label"] = df.apply(
        lambda row: f"{row['iata_code']} — {row['name']} ({row['municipality']}, {row['iso_country']})",
        axis=1,
    )

    df = df.sort_values(["iata_code", "name"]).drop_duplicates(subset=["iata_code"])
    return df[["iata_code", "label", "latitude_deg", "longitude_deg"]].reset_index(drop=True)


def get_index_for_code(options_df: pd.DataFrame, code: str, fallback: int = 0) -> int:
    matches = options_df.index[options_df["iata_code"] == code].tolist()
    if matches:
        return matches[0]
    return fallback


def call_backend(endpoint: str, payload: dict) -> dict:
    response = requests.post(endpoint, json=payload, timeout=120)
    try:
        response_json = response.json()
    except ValueError:
        response.raise_for_status()
        raise RuntimeError("Backend returned a non-JSON response.")

    if not response.ok:
        detail = response_json.get("detail", response.text)
        raise RuntimeError(str(detail))

    return response_json


def build_route_options_table(result: dict) -> list[dict]:
    best_route_id = result["best_route"]["route_id"]
    rows = []

    for route_perf in result["routes_performance"]:
        route = route_perf["route"]
        rows.append(
            {
                "Best?": "✅" if route["route_id"] == best_route_id else "",
                "Route ID": route["route_id"],
                "Distance (nm)": route_perf["total_distance_nm"],
                "Time (min)": route_perf["total_time_min"],
                "Fuel (kg)": route_perf["total_fuel_kg"],
                "CO2 (kg)": route_perf["total_co2_kg"],
            }
        )
    return rows


def render_route_map(
    origin_code: str,
    destination_code: str,
    origin_lat: float,
    origin_lon: float,
    destination_lat: float,
    destination_lon: float,
) -> None:
    # Build a simple curved arc using a lifted midpoint
    midpoint_lat = (origin_lat + destination_lat) / 2
    midpoint_lon = (origin_lon + destination_lon) / 2

    dx = destination_lon - origin_lon
    dy = destination_lat - origin_lat

    # perpendicular unit vector
    length = (dx**2 + dy**2) ** 0.5
    if length == 0:
        length = 1.0

    px = -dy / length
    py = dx / length

    # arc height scaled by route length
    arc_offset = min(max(length * 0.18, 0.8), 3.0)

    control_lon = midpoint_lon + px * arc_offset
    control_lat = midpoint_lat + py * arc_offset

    # Generate curved path points using quadratic Bezier interpolation
    path_points = []
    for t in [i / 40 for i in range(41)]:
        lon = (
            (1 - t) ** 2 * origin_lon
            + 2 * (1 - t) * t * control_lon
            + t**2 * destination_lon
        )
        lat = (
            (1 - t) ** 2 * origin_lat
            + 2 * (1 - t) * t * control_lat
            + t**2 * destination_lat
        )
        path_points.append([lon, lat])

    # Place plane around the middle of the curve
    plane_idx = len(path_points) // 2
    plane_lon, plane_lat = path_points[plane_idx]

    airport_points = pd.DataFrame(
        [
            {"code": origin_code, "lat": origin_lat, "lon": origin_lon},
            {"code": destination_code, "lat": destination_lat, "lon": destination_lon},
        ]
    )

    route_line = pd.DataFrame(
        [
            {
                "path": path_points,
            }
        ]
    )

    plane_label = pd.DataFrame(
        [
            {
                "lat": plane_lat,
                "lon": plane_lon,
                "label": "✈",
            }
        ]
    )

    view_state = pdk.ViewState(
        latitude=midpoint_lat,
        longitude=midpoint_lon,
        zoom=4,
        pitch=0,
    )

    deck = pdk.Deck(
        layers=[
            pdk.Layer(
                "PathLayer",
                data=route_line,
                get_path="path",
                get_color=[255, 215, 0],
                width_scale=6,
                width_min_pixels=4,
                pickable=True,
            ),
            pdk.Layer(
                "ScatterplotLayer",
                data=airport_points,
                get_position="[lon, lat]",
                get_fill_color=[0, 128, 255],
                get_radius=25000,
                pickable=True,
            ),
            pdk.Layer(
                "TextLayer",
                data=airport_points,
                get_position="[lon, lat]",
                get_text="code",
                get_size=16,
                get_color=[255, 255, 255],
                get_text_anchor="'start'",
                get_alignment_baseline="'bottom'",
            ),
            pdk.Layer(
                "TextLayer",
                data=plane_label,
                get_position="[lon, lat]",
                get_text="label",
                get_size=24,
                get_color=[255, 255, 255],
                get_text_anchor="'middle'",
                get_alignment_baseline="'center'",
            ),
        ],
        initial_view_state=view_state,
        tooltip={"text": "{code}"},
    )

    st.pydeck_chart(deck, use_container_width=True)


st.title("✈️ P!lot")

st.sidebar.header("Flight Inputs")

try:
    airport_options_df = load_airport_options()
except Exception as e:
    st.error(f"Failed to load airport options: {e}")
    st.stop()

airport_labels = airport_options_df["label"].tolist()

departure_label = st.sidebar.selectbox(
    "Departure Airport",
    options=airport_labels,
    index=get_index_for_code(airport_options_df, "HPN", 0),
)

destination_label = st.sidebar.selectbox(
    "Destination Airport",
    options=airport_labels,
    index=get_index_for_code(airport_options_df, "IAD", 1),
)

origin = airport_options_df.loc[
    airport_options_df["label"] == departure_label, "iata_code"
].iloc[0]

destination = airport_options_df.loc[
    airport_options_df["label"] == destination_label, "iata_code"
].iloc[0]

origin_row = airport_options_df.loc[airport_options_df["label"] == departure_label].iloc[0]
destination_row = airport_options_df.loc[airport_options_df["label"] == destination_label].iloc[0]

origin_lat = float(origin_row["latitude_deg"])
origin_lon = float(origin_row["longitude_deg"])
destination_lat = float(destination_row["latitude_deg"])
destination_lon = float(destination_row["longitude_deg"])

min_departure_dt = (datetime.now() + timedelta(hours=1)).replace(
    second=0, microsecond=0
)

selected_date = st.sidebar.date_input(
    "Departure Date",
    value=min_departure_dt.date(),
    min_value=min_departure_dt.date(),
)

selected_time = st.sidebar.time_input(
    "Departure Time",
    value=min_departure_dt.time().replace(second=0, microsecond=0),
)

departure_datetime = datetime.combine(selected_date, selected_time)

if departure_datetime < min_departure_dt:
    st.sidebar.error("Departure must be at least 1 hour from now.")

supported_aircraft = load_supported_aircraft()

aircraft = st.sidebar.selectbox(
    "Aircraft Type",
    options=supported_aircraft,
)

st.sidebar.markdown("---")
st.sidebar.subheader("Optional Aircraft Overrides")
st.sidebar.caption("Leave these unchecked to use the backend fallbacks from aircraft_defaults.py.")

use_tas_override = st.sidebar.checkbox("Override TAS (knots)", value=False)
tas_kt = (
    st.sidebar.number_input(
        "tas_kt",
        min_value=1.0,
        step=1.0,
        format="%.1f",
        help="Optional true airspeed override in knots.",
    )
    if use_tas_override
    else None
)

use_mass_override = st.sidebar.checkbox("Override Mass (kg)", value=False)
mass_kg = (
    st.sidebar.number_input(
        "mass_kg",
        min_value=1.0,
        step=100.0,
        format="%.1f",
        help="Optional aircraft mass override in kilograms.",
    )
    if use_mass_override
    else None
)

use_altitude_override = st.sidebar.checkbox("Override Cruise Altitude (ft)", value=False)
cruise_altitude_ft = (
    st.sidebar.number_input(
        "cruise_altitude_ft",
        min_value=1,
        step=1000,
        help="Optional cruise altitude override in feet.",
    )
    if use_altitude_override
    else None
)

same_airport = origin == destination
if same_airport:
    st.sidebar.error("Departure and destination airports must be different.")

invalid_departure = departure_datetime < min_departure_dt
optimize = st.sidebar.button(
    "Optimize Route",
    type="primary",
    disabled=same_airport or invalid_departure,
)


def build_base_payload() -> dict:
    payload = {
        "origin": origin,
        "destination": destination,
        "aircraft": aircraft,
        "departure_time": departure_datetime.isoformat(),
    }
    if tas_kt is not None:
        payload["tas_kt"] = float(tas_kt)
    if mass_kg is not None:
        payload["mass_kg"] = float(mass_kg)
    if cruise_altitude_ft is not None:
        payload["cruise_altitude_ft"] = int(cruise_altitude_ft)
    return payload


if optimize:
    base_payload = build_base_payload()

    performance_results = {}
    advisory_result = None

    try:
        with st.spinner("Running all objective comparisons and fetching LLM advisory..."):
            for objective in OBJECTIVES:
                payload = {**base_payload, "objective": objective}
                performance_results[objective] = call_backend(
                    f"{BACKEND_BASE_URL}/preflight/performance", payload
                )

            advisory_result = call_backend(
                f"{BACKEND_BASE_URL}/preflight/advisory",
                base_payload,
            )

        st.success("Optimization complete.")

        st.subheader("Route Map")
        render_route_map(
            origin_code=origin,
            destination_code=destination,
            origin_lat=origin_lat,
            origin_lon=origin_lon,
            destination_lat=destination_lat,
            destination_lon=destination_lon,
        )

    except Exception as e:
        st.error(f"Request failed: {e}")

    if performance_results:
        st.subheader("All Route Options")

        route_tabs = st.tabs([obj.title() for obj in OBJECTIVES])

        for tab, objective in zip(route_tabs, OBJECTIVES):
            with tab:
                result = performance_results[objective]
                best_route = result["best_route"]

                st.markdown(f"### Objective: {objective.title()}")

                route_rows = build_route_options_table(result)
                st.dataframe(route_rows, use_container_width=True, hide_index=True)

                st.markdown("### Best Route for This Objective")
                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("Best Route", best_route["route_id"])
                c3.metric("Time", f"{best_route['total_time_min']} min")
                c4.metric("Fuel", f"{best_route['total_fuel_kg']} kg")
                c5.metric("CO₂", f"{best_route['total_co2_kg']} kg")

        st.subheader("Best Routes Summary")

        summary_rows = []
        for objective, result in performance_results.items():
            best_route = result["best_route"]
            summary_rows.append(
                {
                    "Objective": objective.title(),
                    "Best Route": best_route["route_id"],
                    "Distance (nm)": best_route["total_distance_nm"],
                    "Time (min)": best_route["total_time_min"],
                    "Fuel (kg)": best_route["total_fuel_kg"],
                    "CO2 (kg)": best_route["total_co2_kg"],
                }
            )

        st.dataframe(summary_rows, use_container_width=True, hide_index=True)

    if advisory_result:
        st.subheader("LLM Advisory Across All Route Options")
        left, right = st.columns([1, 2])
        with left:
            st.metric("Recommended Route", advisory_result["advisory_selected_route_id"])
        with right:
            st.markdown("**Reasoning**")
            st.write(advisory_result["advisory_reasoning"])
            st.markdown("**Advisory**")
            st.write(advisory_result["advisory_text"])
else:
    st.info("Enter flight details and click Optimize Route to compare fuel, time, and emissions together.")
