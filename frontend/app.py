import requests
import streamlit as st
from datetime import datetime, time
from pathlib import Path
import pandas as pd

st.set_page_config(page_title="AI Flight Optimizer", layout="wide")

SUPPORTED_AIRCRAFT = {
    "c550": "Cessna Citation 550",
    "glf6": "Gulfstream G650",
}
OBJECTIVES = ["fuel", "time", "emissions"]
BACKEND_BASE_URL = "http://localhost:8000"


@st.cache_data
def load_airport_options() -> pd.DataFrame:

    airport_file = (
        Path(__file__).resolve().parent.parent / "backend" / "data" / "airports.csv"
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
    return df[["iata_code", "label"]].reset_index(drop=True)


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
                "Route Type": route["type"],
                "Distance (nm)": route_perf["total_distance_nm"],
                "Time (min)": route_perf["total_time_min"],
                "Fuel (kg)": route_perf["total_fuel_kg"],
                "CO2 (kg)": route_perf["total_co2_kg"],
            }
        )
    return rows


st.title("✈️ AI-Powered Flight Route Optimizer")
st.caption(
    "Compare all backend optimization objectives and view the LLM advisory in one run."
)

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

selected_date = st.sidebar.date_input("Departure Date")
selected_time = st.sidebar.time_input("Departure Time", value=time(14, 0))
departure_datetime = datetime.combine(selected_date, selected_time)

aircraft = st.sidebar.selectbox(
    "Aircraft Type",
    options=list(SUPPORTED_AIRCRAFT.keys()),
    format_func=lambda code: f"{SUPPORTED_AIRCRAFT[code]} ({code})",
)

st.sidebar.markdown("---")
st.sidebar.subheader("Optional Aircraft Overrides")
st.sidebar.caption(
    "Leave these unchecked to use the backend fallbacks from aircraft_defaults.py."
)

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

use_altitude_override = st.sidebar.checkbox(
    "Override Cruise Altitude (ft)", value=False
)
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

optimize = st.sidebar.button("Optimize Route", type="primary", disabled=same_airport)


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


with st.expander("Request preview", expanded=False):
    st.json(build_base_payload())

if optimize:
    base_payload = build_base_payload()

    performance_results = {}
    advisory_result = None

    try:
        with st.spinner(
            "Running all objective comparisons and fetching LLM advisory..."
        ):
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
                c2.metric("Route Type", best_route["route_type"])
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
                    "Route Type": best_route["route_type"],
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
            st.metric(
                "Recommended Route", advisory_result["advisory_selected_route_id"]
            )
        with right:
            st.markdown("**Reasoning**")
            st.write(advisory_result["advisory_reasoning"])
            st.markdown("**Advisory**")
            st.write(advisory_result["advisory_text"])
else:
    st.info(
        "Enter flight details and click Optimize Route to compare fuel, time, and emissions together."
    )
