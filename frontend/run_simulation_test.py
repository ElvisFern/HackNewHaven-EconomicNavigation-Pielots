from datetime import datetime, timedelta
from simulator import SimulationState, InFlightSimulator

state = SimulationState(
    current_lat=41.0670,
    current_lon=-73.7076,
    destination="IAD",
    aircraft="c550",
    simulation_time=(datetime.now() + timedelta(hours=1)).replace(
        second=0, microsecond=0
    ),
    tas_kt=380.0,
    mass_kg=9800.0,
    cruise_altitude_ft=35000,
    objective="fuel",
    current_route_id="A",
    step_minutes=5.0,
)

sim = InFlightSimulator(base_url="http://localhost:8000")

for step in range(5):
    out = sim.advance_one_step(state)
    print(f"\nStep {step + 1}")
    print("Active route:", out["active_route_id"])
    print("Mass kg:", out["state"]["mass_kg"])
    print("Distance remaining nm:", out["distance_to_destination_nm"])
    print("Best route now:", out["backend_result"]["best_route"]["route_id"])
    if out["arrived"]:
        print("Arrived.")
        break