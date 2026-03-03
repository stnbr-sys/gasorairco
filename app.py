from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

CITIES: dict[str, tuple[float, float]] = {
    'Amsterdam':        (52.3676, 4.9041),
    'Rotterdam':        (51.9244, 4.4777),
    'The Hague':        (52.0705, 4.3007),
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
    # Added for broader coverage
    'Alkmaar':          (52.6324, 4.7534),
    'Delft':            (52.0116, 4.3571),
    'Deventer':         (52.2550, 6.1583),
    'Emmen':            (52.7792, 6.9008),
    'Gouda':            (52.0167, 4.7000),
    'Heerlen':          (50.8878, 5.9806),
    'Helmond':          (51.4818, 5.6575),
    'Hoogeveen':        (52.7269, 6.4775),
    'Leeuwarden':       (53.2012, 5.7999),
    'Lelystad':         (52.5185, 5.4714),
    'Middelburg':       (51.4988, 3.6136),
    'Oss':              (51.7654, 5.5188),
    'Roosendaal':       (51.5308, 4.4636),
    'Roermond':         (51.1940, 5.9875),
    'Sneek':            (53.0323, 5.6600),
    'Terneuzen':        (51.3352, 3.8278),
    'Venlo':            (51.3704, 6.1724),
    'Vlissingen':       (51.4425, 3.5756),
    'Zaandam':          (52.4389, 4.8136),
    'Zoetermeer':       (52.0574, 4.4938),
}

def _load_cop_data() -> dict:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cop-data.json')
    with open(path) as f:
        return json.load(f)

_RAW = _load_cop_data()

def _load_ac_systems() -> dict[str, list[tuple[float, float]]]:
    """Load COP-vs-temperature curves from cop-data.json (EN14511 manufacturer data)."""
    return {
        s['name']: sorted((float(t), c) for t, c in s['cop_by_temp'].items())
        for s in _RAW['systems']
    }

def _load_ac_meta() -> dict:
    """Load rich product metadata (brand, series, label, image, datasheet) per system."""
    return {
        s['name']: {
            'id':            s['id'],
            'brand':         s['brand'],
            'series':        s['series'],
            'energy_label':  s['energy_label'],
            'scop':          s['scop'],
            'seer':          s.get('seer'),
            'color':         s['color'],
            'image_url':     s.get('image_url'),
            'product_page':  s.get('product_page'),
            'datasheet_url': s.get('datasheet_url'),
        }
        for s in _RAW['systems']
    }

# Keys: system display name → sorted [(outdoor_°C, COP), …]
AC_SYSTEMS: dict[str, list[tuple[float, float]]] = _load_ac_systems()
AC_META: dict = _load_ac_meta()

GAS_ENERGY_CONTENT = 9.77   # kWh/m³  (Gronings/L-gas)
BOILER_EFFICIENCY  = 0.95   # modern HR condensing boiler
GAS_CO2_G_PER_M3   = 1880  # g CO₂/m³ natural gas (combustion, IPCC AR6)
NL_GRID_CO2_FALLBACK = 300  # g CO₂/kWh — Dutch grid average estimate (no live token)

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


def find_break_even(curve: list[tuple[float, float]], gas_cost_kwh: float, elec_price: float) -> tuple[str, float | None]:
    """Return ('break_even', temp_°C), ('ac_always', None), or ('gas_always', None)."""
    if gas_cost_kwh <= 0 or elec_price <= 0:
        return ('unknown', None)
    required_cop = elec_price / gas_cost_kwh
    # AC cheaper even at the lowest COP in the table
    if required_cop <= curve[0][1]:
        return ('ac_always', None)
    # Gas always wins; AC never reaches the required COP
    if required_cop > curve[-1][1]:
        return ('gas_always', None)
    for i in range(len(curve) - 1):
        t0, cop0 = curve[i]
        t1, cop1 = curve[i + 1]
        if cop0 <= required_cop <= cop1:
            f = (required_cop - cop0) / (cop1 - cop0)
            return ('break_even', round(t0 + f * (t1 - t0), 1))
    return ('gas_always', None)



# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return render_template('index.html', cities=CITIES, ac_systems=AC_SYSTEMS, ac_meta=AC_META)



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

    curve    = AC_SYSTEMS[ac_system]
    cop      = lookup_cop(temperature, curve)
    gas_cost = gas_price / (GAS_ENERGY_CONTENT * BOILER_EFFICIENCY)
    be_kind, be_temp = find_break_even(curve, gas_cost, elec_price)
    be = {'type': be_kind, 'temp': be_temp}

    if cop is None:
        return jsonify({
            'recommendation': 'none',
            'temperature': temperature,
            'cop': None,
            'gas_cost_kwh': round(gas_cost, 4),
            'airco_cost_kwh': None,
            'savings': None,
            'break_even': be,
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
        'break_even': be,
    })


# Dutch energy taxes 2025 (excl. BTW) — source: Belastingdienst
# Schijf 1: electricity 0–10,000 kWh/yr, gas 0–170,000 m³/yr
ELECTRICITY_TAX_KWH = 0.12599  # energiebelasting €/kWh
GAS_TAX_M3          = 0.49459  # energiebelasting €/m³
BTW                 = 1.21     # 21% VAT


def _energyzero_current_price(usage_type: int) -> dict:
    """Fetch raw spot price from EnergyZero and compute all-in consumer price.
    usage_type: 1 = electricity (€/kWh), 3 = gas (€/m³)."""
    now = datetime.now(timezone.utc)
    day_start = now.strftime('%Y-%m-%dT00:00:00.000Z')
    day_end   = now.strftime('%Y-%m-%dT23:59:59.999Z')
    url = (
        'https://api.energyzero.nl/v1/energyprices'
        f'?fromDate={day_start}&tillDate={day_end}'
        f'&interval=4&usageType={usage_type}&inclBtw=false'
    )
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    prices = resp.json().get('Prices', [])
    if not prices:
        raise ValueError('No prices available')

    current_entry = prices[-1]
    for entry in prices:
        try:
            dt = datetime.fromisoformat(entry['readingDate']).astimezone(timezone.utc)
            if dt.hour == now.hour:
                current_entry = entry
                break
        except (ValueError, KeyError):
            pass

    spot = current_entry['price']
    tax  = ELECTRICITY_TAX_KWH if usage_type == 1 else GAS_TAX_M3
    all_in = (spot + tax) * BTW

    return {
        'price':  round(all_in, 4),
        'spot':   round(spot, 4),
        'tax':    round(tax, 4),
        'source': 'EnergyZero',
        'time':   now.strftime('%H:%M UTC'),
    }


def _easyenergy_current_price(usage_type: int) -> dict:
    """Fetch spot price from Easyenergy and compute all-in consumer price.
    usage_type: 1 = electricity, 3 = gas."""
    now = datetime.now(timezone.utc)
    # Easyenergy accepts UTC timestamps in ISO format without timezone suffix
    day_start = now.strftime('%Y-%m-%dT00:00:00')
    day_end   = now.strftime('%Y-%m-%dT23:59:59')
    if usage_type == 1:
        url = (f'https://mijn.easyenergy.com/nl/api/tariff/getapxtariffs'
               f'?startTimestamp={day_start}&endTimestamp={day_end}')
    else:
        url = (f'https://mijn.easyenergy.com/nl/api/tariff/getlebatariffs'
               f'?startTimestamp={day_start}&endTimestamp={day_end}')
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    prices = resp.json()
    if not prices:
        raise ValueError('No prices available')

    current_entry = prices[-1]
    for entry in prices:
        try:
            ts = entry.get('Timestamp', '')
            dt = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
            if dt.hour == now.hour:
                current_entry = entry
                break
        except (ValueError, KeyError):
            pass

    spot = current_entry.get('TariffUsage', 0.0)
    tax  = ELECTRICITY_TAX_KWH if usage_type == 1 else GAS_TAX_M3
    all_in = (spot + tax) * BTW

    return {
        'price':  round(all_in, 4),
        'spot':   round(spot, 4),
        'tax':    round(tax, 4),
        'source': 'Easyenergy',
        'time':   now.strftime('%H:%M UTC'),
    }


_PRICE_FETCHERS = {
    'energyzero': _energyzero_current_price,
    'easyenergy': _easyenergy_current_price,
}


@app.route('/api/electricity-price')
def electricity_price():
    source = request.args.get('source', 'energyzero')
    fetcher = _PRICE_FETCHERS.get(source, _energyzero_current_price)
    try:
        return jsonify(fetcher(usage_type=1))
    except Exception as e:
        return jsonify({'error': str(e)}), 502


@app.route('/api/gas-price')
def gas_price():
    source = request.args.get('source', 'energyzero')
    fetcher = _PRICE_FETCHERS.get(source, _energyzero_current_price)
    try:
        return jsonify(fetcher(usage_type=3))
    except Exception as e:
        return jsonify({'error': str(e)}), 502


@app.route('/api/carbon-intensity')
def carbon_intensity():
    """Live Dutch grid CO₂ intensity via ElectricityMaps API.
    Falls back to a static NL average when ELECTRICITY_MAPS_TOKEN is not set."""
    gas_co2_kwh = round(GAS_CO2_G_PER_M3 / (GAS_ENERGY_CONTENT * BOILER_EFFICIENCY), 1)
    token = os.environ.get('ELECTRICITY_MAPS_TOKEN', '').strip()
    if not token:
        return jsonify({
            'carbon_intensity': NL_GRID_CO2_FALLBACK,
            'gas_co2_kwh_heat': gas_co2_kwh,
            'live': False,
        })
    try:
        resp = requests.get(
            'https://api.electricitymap.org/v3/carbon-intensity/latest?zone=NL',
            headers={'auth-token': token},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        return jsonify({
            'carbon_intensity': data['carbonIntensity'],
            'gas_co2_kwh_heat': gas_co2_kwh,
            'live': True,
            'updated_at': data.get('datetime', ''),
        })
    except Exception:
        return jsonify({
            'carbon_intensity': NL_GRID_CO2_FALLBACK,
            'gas_co2_kwh_heat': gas_co2_kwh,
            'live': False,
        })


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
