import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import Flask, jsonify, render_template, request
import requests

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

CITIES: dict[str, tuple[float, float]] = {
    'Amsterdam':        (52.3676, 4.9041),
    'Rotterdam':        (51.9244, 4.4777),
    'Den Haag':         (52.0705, 4.3007),
    'Utrecht':          (52.0907, 5.1214),
    'Eindhoven':        (51.4416, 5.4697),
    'Groningen':        (53.2194, 6.5665),
    'Tilburg':          (51.5555, 5.0913),
    'Almere':           (52.3508, 5.2647),
    'Breda':            (51.5719, 4.7683),
    'Nijmegen':         (51.8126, 5.8372),
    'Enschede':         (52.2215, 6.8937),
    'Haarlem':          (52.3874, 4.6462),
    'Arnhem':           (51.9851, 5.8987),
    'Amersfoort':       (52.1561, 5.3878),
    'Apeldoorn':        (52.2112, 5.9699),
    "'s-Hertogenbosch": (51.6978, 5.3037),
    'Maastricht':       (50.8514, 5.6910),
    'Leiden':           (52.1601, 4.4970),
    'Dordrecht':        (51.8133, 4.6901),
    'Zwolle':           (52.5168, 6.0830),
}

AC_SYSTEMS: dict[str, float] = {
    'Premium Inverter (Daikin, Mitsubishi e.d.)': 0.50,
    'Standaard Inverter split-unit':               0.45,
    'Multi-split systeem':                         0.42,
    'Niet-inverter split-unit':                    0.35,
    'Mobiele airco':                               0.25,
}

GAS_ENERGY_CONTENT = 9.77   # kWh/m³  (Gronings/L-gas)
BOILER_EFFICIENCY  = 0.95   # modern HR condensing boiler

# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def calculate_cop(outdoor_temp_c: float, efficiency_factor: float) -> float | None:
    """Return practical COP for heating, or None if no heating is needed."""
    T_hot  = 21.0 + 273.15
    T_cold = outdoor_temp_c + 273.15
    if T_cold >= T_hot:
        return None
    cop_carnot = T_hot / (T_hot - T_cold)
    return max(1.0, efficiency_factor * cop_carnot)


def fetch_temperature(lat: float, lon: float) -> float:
    """Fetch current outdoor temperature from Open-Meteo (no API key needed)."""
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}&current_weather=true"
    )
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()["current_weather"]["temperature"]

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return render_template('index.html', cities=CITIES, ac_systems=AC_SYSTEMS)


@app.route('/api/temperatures')
def get_temperatures():
    """Fetch all city temperatures in parallel and return as JSON."""
    def _fetch(city: str, lat: float, lon: float) -> tuple[str, float | None]:
        try:
            return city, fetch_temperature(lat, lon)
        except Exception as e:
            print(f"[temp fetch] {city}: {e}", flush=True)
            return city, None

    results: dict[str, float | None] = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(_fetch, city, lat, lon): city
            for city, (lat, lon) in CITIES.items()
        }
        for future in as_completed(futures):
            city, temp = future.result()
            results[city] = temp

    return jsonify(results)


@app.route('/api/calculate', methods=['POST'])
def calculate():
    """Calculate gas vs airco cost and return a recommendation."""
    data = request.get_json(silent=True) or {}

    city       = data.get('city')
    ac_system  = data.get('ac_system')
    temperature = data.get('temperature')
    gas_price  = data.get('gas_price')
    elec_price = data.get('elec_price')

    if city not in CITIES:
        return jsonify({'error': 'Unknown city'}), 400
    if ac_system not in AC_SYSTEMS:
        return jsonify({'error': 'Unknown AC system'}), 400

    try:
        temperature = float(temperature)
        gas_price   = float(str(gas_price).replace(',', '.'))
        elec_price  = float(str(elec_price).replace(',', '.'))
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid price or temperature'}), 400

    factor   = AC_SYSTEMS[ac_system]
    cop      = calculate_cop(temperature, factor)
    gas_cost = gas_price / (GAS_ENERGY_CONTENT * BOILER_EFFICIENCY)

    if cop is None:
        return jsonify({
            'recommendation': 'none',
            'temperature': temperature,
            'cop': None,
            'gas_cost_kwh': round(gas_cost, 4),
            'airco_cost_kwh': None,
            'savings': None,
        })

    airco_cost = elec_price / cop
    savings    = abs(gas_cost - airco_cost)

    return jsonify({
        'recommendation': 'airco' if airco_cost < gas_cost else 'gas',
        'temperature': temperature,
        'cop': round(cop, 2),
        'gas_cost_kwh': round(gas_cost, 4),
        'airco_cost_kwh': round(airco_cost, 4),
        'savings': round(savings, 4),
    })


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
