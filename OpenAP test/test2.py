from openap import FuelFlow, Emission


def evaluate_option(ac, mass, tas, alt, hours):
    fuelflow = FuelFlow(ac=ac)
    emission = Emission(ac=ac)

    ff = fuelflow.enroute(mass=mass, tas=tas, alt=alt, vs=0)  # kg/s
    fuel_total = ff * hours * 3600  # kg
    co2_rate = emission.co2(ff)  # g/s
    co2_total = co2_rate * hours * 3600 / 1000  # kg

    return {
        "aircraft": ac,
        "altitude_ft": alt,
        "fuel_flow_kg_s": ff,
        "trip_fuel_kg": fuel_total,
        "trip_co2_kg": co2_total,
    }


options = [
    evaluate_option("c550", mass=10000, tas=350, alt=25000, hours=1.5),
    evaluate_option("c550", mass=10000, tas=350, alt=30000, hours=1.5),
    evaluate_option("c550", mass=10000, tas=350, alt=35000, hours=1.5),
]

for opt in options:
    print(opt)