import streamlit as st

st.set_page_config(page_title="AI Flight Optimizer", layout="wide")

st.title("✈️ AI-Powered Flight Route Optimizer")

# Sidebar inputs
st.sidebar.header("Flight Inputs")
st.markdown("""
    <style>
    .card {
        padding: 20px;
        border-radius: 15px;
        background-color: #1C1F26;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        margin-bottom: 20px;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="card">', unsafe_allow_html=True)

st.subheader("Flight Details")

departure = st.sidebar.text_input("Departure Airport", "JFK")
destination = st.sidebar.text_input("Destination Airport", "LHR")
departure_time = st.sidebar.text_input("Departure Time", "2026-04-01 12:00")
departure = departure.upper()
destination = destination.upper()

aircraft = st.sidebar.selectbox(
    "Aircraft Type",
    ["Boeing 737", "Airbus A320", "Boeing 787"]
)

st.markdown('</div>', unsafe_allow_html=True)

optimize = st.sidebar.button("Optimize Route")

# Main screen
col1, col2 = st.columns([3, 1])

with col1:
    st.subheader("Route Map")
    st.map()  # placeholder 

with col2:
    st.subheader("Impact Metrics")
    st.metric("Fuel Saved", "0", "0%")
    st.metric("CO₂ Reduced", "0kg", "0%")
    st.metric("Time Change", "0")