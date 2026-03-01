from __future__ import annotations

import os

from flask import Flask, jsonify, render_template, request

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

# COP lookup tables per system type: list of (outdoor_temp_°C, COP) pairs.
# Based on EN 14511 manufacturer data for air-to-air heating mode.
# Sorted by temperature ascending.
AC_SYSTEMS: dict[str, list[tuple[float, float]]] = {
    'Premium Inverter (Daikin, Mitsubishi e.d.)': [
        (-15, 1.7), (-10, 2.3), (-7, 2.7), (2, 3.9), (7, 5.2), (10, 5.8), (15, 6.5),
    ],
    'Standaard Inverter split-unit': [
        (-15, 1.5), (-10, 1.9), (-7, 2.3), (2, 3.3), (7, 4.3), (10, 4.8), (15, 5.5),
    ],
    'Multi-split systeem': [
        (-15, 1.4), (-10, 1.8), (-7, 2.1), (2, 3.0), (7, 3.8), (10, 4.2), (15, 4.9),
    ],
    'Niet-inverter split-unit': [
        (-10, 1.4), (-7, 1.8), (2, 2.5), (7, 3.0), (10, 3.3), (15, 3.8),
    ],
    'Mobiele airco': [
        (0, 1.2), (5, 1.4), (7, 1.6), (10, 1.8), (15, 2.0),
    ],
}

GAS_ENERGY_CONTENT = 9.77   # kWh/m³  (Gronings/L-gas)
BOILER_EFFICIENCY  = 0.95   # modern HR condensing boiler

# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def lookup_cop(outdoor_temp_c: float, curve: list[tuple[float, float]]) -> float | None:
    """Interpolate COP from a manufacturer lookup table. Returns None if no heating needed."""
    if outdoor_temp_c >= 21.0:
        return None
    # Clamp to table bounds rather than extrapolating wildly
    if outdoor_temp_c <= curve[0][0]:
        return curve[0][1]
    if outdoor_temp_c >= curve[-1][0]:
        return curve[-1][1]
    # Linear interpolation between surrounding data points
    for i in range(len(curve) - 1):
        t0, cop0 = curve[i]
        t1, cop1 = curve[i + 1]
        if t0 <= outdoor_temp_c <= t1:
            f = (outdoor_temp_c - t0) / (t1 - t0)
            return cop0 + f * (cop1 - cop0)
    return curve[-1][1]



# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return render_template('index.html', cities=CITIES, ac_systems=AC_SYSTEMS)



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

    curve = AC_SYSTEMS[ac_system]
    cop   = lookup_cop(temperature, curve)
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
