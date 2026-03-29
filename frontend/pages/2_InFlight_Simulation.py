import requests
import streamlit as st
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import pydeck as pdk
from PIL import Image

from simulator import SimulationState, InFlightSimulator

st.set_page_config(page_title="In-Flight Simulation", layout="wide")

st.markdown(
    """
<style>
    .stApp {
        background-color: white;
        color: black;
    }

    .main, .block-container {
        background-color: white;
        color: black;
    }

    h1, h2, h3, h4, h5, h6, p, div, label, span {
        color: black !important;
    }

    [data-testid="stSidebar"] {
        background-color: #f7f7f7;
    }

    [data-testid="stSidebar"] * {
        color: black !important;
    }

    .stAlert {
        color: black !important;
    }
</style>
""",
    unsafe_allow_html=True,
)



BACKEND_BASE_URL = "http://localhost:8000"
DEFAULT_STEP_MINUTES = 5.0


@st.cache_data
def load_supported_aircraft() -> list[str]:
    response = requests.get(f"{BACKEND_BASE_URL}/", timeout=30)
    response.raise_for_status()
    data = response.json()
    return data["supported_aircraft"]


@st.cache_data
def load_airport_options() -> pd.DataFrame:
    airport_file = Path(__file__).resolve().parent.parent.parent / "backend" / "data" / "airports.csv"

    if not airport_file.exists():
        raise FileNotFoundError(
            f"Could not find airports.csv at expected path: {airport_file}"
        )

    df = pd.read_csv(airport_file)

    allowed_types = {"large_airport", "medium_airport", "small_airport"}
    df = df[df["type"].isin(allowed_types)].copy()

    for col in ["name", "municipality", "iso_country", "iata_code"]:
        df[col] = df[col].fillna("").astype(str).str.strip()

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


def render_route_map(
    current_code: str,
    destination_code: str,
    current_lat: float,
    current_lon: float,
    destination_lat: float,
    destination_lon: float,
) -> None:
    midpoint_lat = (current_lat + destination_lat) / 2
    midpoint_lon = (current_lon + destination_lon) / 2

    dx = destination_lon - current_lon
    dy = destination_lat - current_lat

    length = (dx**2 + dy**2) ** 0.5
    if length == 0:
        length = 1.0

    px = -dy / length
    py = dx / length

    arc_offset = min(max(length * 0.18, 0.8), 3.0)

    control_lon = midpoint_lon + px * arc_offset
    control_lat = midpoint_lat + py * arc_offset

    path_points = []
    for t in [i / 40 for i in range(41)]:
        lon = (
            (1 - t) ** 2 * current_lon
            + 2 * (1 - t) * t * control_lon
            + t**2 * destination_lon
        )
        lat = (
            (1 - t) ** 2 * current_lat
            + 2 * (1 - t) * t * control_lat
            + t**2 * destination_lat
        )
        path_points.append([lon, lat])

    plane_idx = min(len(path_points) // 4, len(path_points) - 1)
    plane_lon, plane_lat = path_points[plane_idx]

    airport_points = pd.DataFrame(
        [
            {"code": current_code, "lat": current_lat, "lon": current_lon, "color": [0, 200, 255]},
            {"code": destination_code, "lat": destination_lat, "lon": destination_lon, "color": [255, 120, 0]},
        ]
    )

    route_line = pd.DataFrame([{"path": path_points}])

    plane_label = pd.DataFrame(
        [{"lat": plane_lat, "lon": plane_lon, "label": "✈"}]
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
                get_fill_color="color",
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


def init_simulation_session() -> None:
    if "simulator" not in st.session_state:
        st.session_state.simulator = InFlightSimulator(base_url=BACKEND_BASE_URL)

    if "simulation_state" not in st.session_state:
        st.session_state.simulation_state = None

    if "simulation_history" not in st.session_state:
        st.session_state.simulation_history = []

    if "latest_simulation_result" not in st.session_state:
        st.session_state.latest_simulation_result = None


def reset_simulation_session() -> None:
    st.session_state.simulation_state = None
    st.session_state.simulation_history = []
    st.session_state.latest_simulation_result = None


logo_path = Path(__file__).resolve().parent.parent / "logo.png"

if logo_path.exists():
    logo = Image.open(logo_path)
    title_col1, title_col2 = st.columns([1, 6])

    with title_col1:
        st.image(logo, width=90)

    with title_col2:
        st.markdown(
            "<h1 style='margin-top: 10px;'>In-Flight Advisory Simulation</h1>",
            unsafe_allow_html=True,
        )
else:
    st.title("🛫 In-Flight Advisory Simulation")

st.caption("Simulate real-time rerouting from the current aircraft position to the destination.")

init_simulation_session()

try:
    airport_options_df = load_airport_options()
    supported_aircraft = load_supported_aircraft()
except Exception as e:
    st.error(f"Initialization failed: {e}")
    st.stop()

airport_labels = airport_options_df["label"].tolist()

st.sidebar.header("Simulation Inputs")

destination_label = st.sidebar.selectbox(
    "Destination Airport",
    options=airport_labels,
    index=get_index_for_code(airport_options_df, "IAD", 1),
)

destination = airport_options_df.loc[
    airport_options_df["label"] == destination_label, "iata_code"
].iloc[0]
destination_row = airport_options_df.loc[airport_options_df["label"] == destination_label].iloc[0]
destination_lat = float(destination_row["latitude_deg"])
destination_lon = float(destination_row["longitude_deg"])

start_position_mode = st.sidebar.radio(
    "Start Position",
    options=["Use Airport", "Use Coordinates"],
)

if start_position_mode == "Use Airport":
    current_label = st.sidebar.selectbox(
        "Current Position Airport",
        options=airport_labels,
        index=get_index_for_code(airport_options_df, "HPN", 0),
    )
    current_row = airport_options_df.loc[airport_options_df["label"] == current_label].iloc[0]
    current_lat = float(current_row["latitude_deg"])
    current_lon = float(current_row["longitude_deg"])
    current_position_label = current_row["iata_code"]
else:
    current_lat = st.sidebar.number_input("Current Latitude", min_value=-90.0, max_value=90.0, value=41.0670, format="%.6f")
    current_lon = st.sidebar.number_input("Current Longitude", min_value=-180.0, max_value=180.0, value=-73.7076, format="%.6f")
    current_position_label = "CURR"

aircraft = st.sidebar.selectbox("Aircraft Type", options=supported_aircraft)

min_sim_dt = (datetime.now() + timedelta(hours=1)).replace(second=0, microsecond=0)

selected_date = st.sidebar.date_input(
    "Simulation Start Date",
    value=min_sim_dt.date(),
    min_value=min_sim_dt.date(),
)
selected_time = st.sidebar.time_input(
    "Simulation Start Time",
    value=min_sim_dt.time(),
)
simulation_datetime = datetime.combine(selected_date, selected_time)

tas_kt = st.sidebar.number_input(
    "Current TAS (kt)",
    min_value=1.0,
    value=380.0,
    step=1.0,
    format="%.1f",
)

mass_kg = st.sidebar.number_input(
    "Current Mass (kg)",
    min_value=1000.0,
    value=9800.0,
    step=100.0,
    format="%.1f",
)

cruise_altitude_ft = st.sidebar.number_input(
    "Current Cruise Altitude (ft)",
    min_value=1000,
    value=35000,
    step=1000,
)

objective = st.sidebar.selectbox("Optimization Objective", options=["fuel", "time", "emissions"])
step_minutes = st.sidebar.slider("Step Size (minutes)", min_value=1, max_value=30, value=5, step=1)

invalid_start_time = simulation_datetime < min_sim_dt
if invalid_start_time:
    st.sidebar.error("Simulation start time must be at least 1 hour from now.")

same_position_as_destination = (
    abs(current_lat - destination_lat) < 1e-6 and abs(current_lon - destination_lon) < 1e-6
)
if same_position_as_destination:
    st.sidebar.error("Current position and destination cannot be the same.")

sim_col1, sim_col2, sim_col3 = st.columns(3)
with sim_col1:
    start_sim = st.button("Start Simulation", type="primary", disabled=invalid_start_time or same_position_as_destination)
with sim_col2:
    step_sim = st.button("Advance One Step")
with sim_col3:
    reset_sim = st.button("Reset Simulation")

run_steps = st.number_input("Batch Run Steps", min_value=1, max_value=50, value=5, step=1)
run_batch = st.button("Run Batch Steps")

if reset_sim:
    reset_simulation_session()
    st.success("Simulation reset.")

if start_sim:
    try:
        st.session_state.simulation_state = SimulationState(
            current_lat=current_lat,
            current_lon=current_lon,
            destination=destination,
            aircraft=aircraft,
            simulation_time=simulation_datetime,
            tas_kt=float(tas_kt),
            mass_kg=float(mass_kg),
            cruise_altitude_ft=int(cruise_altitude_ft),
            objective=objective,
            current_route_id="A",
            step_minutes=float(step_minutes),
        )
        st.session_state.simulation_history = []
        st.session_state.latest_simulation_result = None
        st.success("Simulation initialized.")
    except Exception as e:
        st.error(f"Failed to initialize simulation: {e}")

if step_sim:
    if st.session_state.simulation_state is None:
        st.warning("Start the simulation first.")
    else:
        try:
            st.session_state.simulation_state.step_minutes = float(step_minutes)
            result = st.session_state.simulator.advance_one_step(
                st.session_state.simulation_state
            )
            st.session_state.latest_simulation_result = result
            st.session_state.simulation_history.append(result)
            if result["arrived"]:
                st.success("Aircraft has reached the destination area.")
            else:
                st.success("Advanced simulation by one step.")
        except Exception as e:
            st.error(f"Simulation step failed: {e}")

if run_batch:
    if st.session_state.simulation_state is None:
        st.warning("Start the simulation first.")
    else:
        try:
            st.session_state.simulation_state.step_minutes = float(step_minutes)
            for _ in range(int(run_steps)):
                result = st.session_state.simulator.advance_one_step(
                    st.session_state.simulation_state
                )
                st.session_state.latest_simulation_result = result
                st.session_state.simulation_history.append(result)
                if result["arrived"]:
                    break
            if st.session_state.latest_simulation_result and st.session_state.latest_simulation_result["arrived"]:
                st.success("Aircraft has reached the destination area.")
            else:
                st.success("Batch simulation completed.")
        except Exception as e:
            st.error(f"Simulation batch failed: {e}")

if st.session_state.simulation_state is None:
    st.info("Configure the in-flight scenario and click Start Simulation.")
else:
    sim_state = st.session_state.simulation_state

    st.subheader("Current Simulated State")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Latitude", round(sim_state.current_lat, 4))
    c2.metric("Longitude", round(sim_state.current_lon, 4))
    c3.metric("Mass (kg)", round(sim_state.mass_kg, 2))
    c4.metric("TAS (kt)", round(sim_state.tas_kt, 2))
    c5.metric("Altitude (ft)", sim_state.cruise_altitude_ft)
    st.caption(f"Simulation time: {sim_state.simulation_time.isoformat()}")

    st.subheader("Route Map")
    render_route_map(
        current_code=current_position_label if not st.session_state.simulation_history else "CURR",
        destination_code=destination,
        current_lat=sim_state.current_lat,
        current_lon=sim_state.current_lon,
        destination_lat=destination_lat,
        destination_lon=destination_lon,
    )

    if st.session_state.latest_simulation_result is not None:
        latest = st.session_state.latest_simulation_result
        backend_result = latest["backend_result"]
        best_route = backend_result["best_route"]

        st.subheader("Latest In-Flight Evaluation")
        e1, e2, e3, e4 = st.columns(4)
        e1.metric("Active Route", latest["active_route_id"])
        e2.metric("Best Route Now", best_route["route_id"])
        e3.metric("Fuel Burn This Step (kg)", latest["fuel_burn_kg_step"])
        e4.metric("Distance Remaining (nm)", latest["distance_to_destination_nm"])

        st.dataframe(
            build_route_options_table(backend_result),
            use_container_width=True,
            hide_index=True,
        )

        with st.expander("Full backend response", expanded=False):
            st.json(backend_result)

    if st.session_state.simulation_history:
        st.subheader("Simulation History")

        history_rows = []
        for idx, item in enumerate(st.session_state.simulation_history, start=1):
            state_row = item["state"]
            best_route = item["backend_result"]["best_route"]
            history_rows.append(
                {
                    "Step": idx,
                    "Time": state_row["simulation_time"],
                    "Lat": round(state_row["current_lat"], 4),
                    "Lon": round(state_row["current_lon"], 4),
                    "Mass (kg)": state_row["mass_kg"],
                    "Active Route": item["active_route_id"],
                    "Best Route": best_route["route_id"],
                    "Distance Remaining (nm)": item["distance_to_destination_nm"],
                }
            )

        st.dataframe(history_rows, use_container_width=True, hide_index=True)
