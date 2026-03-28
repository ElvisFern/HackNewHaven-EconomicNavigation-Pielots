from openap import prop, FuelFlow, Emission

# 1) Verify supported aircraft
aircraft = prop.available_aircraft()
print("Supported aircraft count:", len(aircraft))
print("Supported aircraft:", aircraft)

# 2) Inspect the two business/private-jet-class aircraft
for ac in ["c550", "glf6"]:
    print(f"\n--- {ac} ---")
    info = prop.aircraft(ac)
    print("Name:", info.get("aircraft"))
    print("Ceiling:", info.get("ceiling"))
    print("Cruise:", info.get("cruise"))
    print("Limits:", info.get("limits"))
    print("Engine:", info.get("engine"))

# 3) Smoke test fuel flow and emissions
for ac in ["c550", "glf6"]:
    print(f"\nTesting fuel/emission model for {ac}")
    fuelflow = FuelFlow(ac=ac)
    emission = Emission(ac=ac)

    # Placeholder values for an enroute test
    mass = 10000  # kg
    tas = 350  # knots
    alt = 30000  # ft
    vs = 0  # ft/min

    ff = fuelflow.enroute(mass=mass, tas=tas, alt=alt, vs=vs)  # kg/s
    co2 = emission.co2(ff)  # g/s

    print("Fuel flow (kg/s):", ff)
    print("CO2 (g/s):", co2)