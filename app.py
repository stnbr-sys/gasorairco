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
    # Additional cities for broader coverage
    'Alphen a/d Rijn':  (52.1296, 4.6559),
    'Assen':            (52.9929, 6.5642),
    'Bergen op Zoom':   (51.4940, 4.2887),
    'Capelle a/d IJssel':(51.9278, 4.5669),
    'Coevorden':        (52.6606, 6.7428),
    'Delfzijl':         (53.3290, 6.9211),
    'Doetinchem':       (51.9628, 6.2953),
    'Drachten':         (53.1111, 6.0964),
    'Franeker':         (53.1854, 5.5432),
    'Hardenberg':       (52.5752, 6.6179),
    'Harderwijk':       (52.3444, 5.6239),
    'Heerhugowaard':    (52.6702, 4.8437),
    'Hengelo':          (52.2659, 6.7933),
    'Hilversum':        (52.2292, 5.1787),
    'Hoorn':            (52.6440, 5.0604),
    'Kampen':           (52.5553, 5.9097),
    'Kerkrade':         (50.8655, 6.0602),
    'Meppel':           (52.6963, 6.1936),
    'Nieuwegein':       (52.0309, 5.0978),
    'Purmerend':        (52.5030, 4.9599),
    'Ridderkerk':       (51.8680, 4.5980),
    'Schiedam':         (51.9175, 4.3980),
    'Sittard':          (50.9983, 5.8696),
    'Spijkenisse':      (51.8476, 4.3254),
    'Stadskanaal':      (53.0000, 6.9500),
    'Tiel':             (51.8874, 5.4305),
    'Veenendaal':       (52.0265, 5.5568),
    'Veldhoven':        (51.4163, 5.4065),
    'Venray':           (51.5240, 5.9738),
    'Vlaardingen':      (51.9126, 4.3429),
    'Weert':            (51.2499, 5.7063),
    'Westland':         (51.9971, 4.2009),
    'Woerden':          (52.0875, 4.8878),
    'Zeist':            (52.0878, 5.2352),
    'Zutphen':          (52.1380, 6.1986),
    'Barendrecht':      (51.8594, 4.5386),
    'Wijk bij Duurstede':(51.9743, 5.3379),
    'Dokkum':           (53.3255, 5.9990),
    'Winschoten':       (53.1432, 7.0384),
    'Sluis':            (51.3088, 3.3882),
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

WOOD_STOVE_EFFICIENCY = 0.75   # modern houtkachel (EN13229 avg)
WOOD_TYPES: dict[str, int] = {  # kWh per m³ gestapeld hout, ~20% vochtgehalte
    'Beuk':     1950,   # Beech
    'Eiken':    1850,   # Oak
    'Es':       1900,   # Ash
    'Berk':     1750,   # Birch
    'Den/Spar': 1350,   # Pine / Spruce
    'Populier': 1150,   # Poplar
}

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


def _to_rd(lat: float, lon: float) -> tuple[float, float]:
    """Transform WGS84 (lat, lon) to Dutch RD New (EPSG:28992) (x, y) in metres."""
    x0, y0 = 155000.0, 463000.0
    f0, l0 = 52.15517440, 5.38720621
    Rp  = [0, 1, 2, 0, 1, 3, 1, 0, 2]
    Rq  = [1, 1, 1, 3, 0, 1, 3, 2, 3]
    Rpq = [190094.945, -11832.228, -114.221, -32.391, -0.705, -2.34, -0.608, -0.008, 0.148]
    Sp  = [1, 0, 2, 1, 3, 0, 2, 1, 0, 1]
    Sq  = [0, 2, 0, 2, 0, 1, 2, 1, 4, 4]
    Spq = [309056.544, 3638.893, 73.077, -157.984, 59.788, 0.433, -6.439, -0.032, 0.092, -0.054]
    df = 0.36 * (lat - f0)
    dl = 0.36 * (lon - l0)
    x = x0 + sum(Rpq[i] * (df ** Rp[i]) * (dl ** Rq[i]) for i in range(9))
    y = y0 + sum(Spq[i] * (df ** Sp[i]) * (dl ** Sq[i]) for i in range(10))
    return x, y


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
    return render_template('index.html', cities=CITIES, ac_systems=AC_SYSTEMS, ac_meta=AC_META,
                           wood_types=WOOD_TYPES, wood_stove_efficiency=WOOD_STOVE_EFFICIENCY)



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


@app.route('/api/stookwijzer')
def stookwijzer():
    """Return current Stookwijzer advice for a coordinate (RIVM / Atlas Leefomgeving WMS)."""
    try:
        lat = float(request.args['lat'])
        lon = float(request.args['lon'])
    except (KeyError, ValueError):
        return jsonify({'error': 'lat and lon required'}), 400

    x_rd, y_rd = _to_rd(lat, lon)
    # 5 km bounding box; point placed at pixel (128,128) = centre of 256×256 image
    buf = 2500
    bbox = f'{x_rd - buf},{y_rd - buf},{x_rd + buf},{y_rd + buf}'
    url = (
        'https://data.rivm.nl/geo/alo/wms'
        '?service=WMS&VERSION=1.3.0&REQUEST=GetFeatureInfo'
        '&FORMAT=image/png&TRANSPARENT=true'
        '&QUERY_LAYERS=stookwijzer_v2&LAYERS=stookwijzer_v2'
        '&servicekey=82b124ad-834d-4c10-8bd0-ee730d5c1cc8'
        '&STYLES=&BUFFER=1&EXCEPTIONS=INIMAGE'
        '&info_format=application/json&feature_count=1'
        '&I=128&J=128&WIDTH=256&HEIGHT=256&CRS=EPSG:28992&BBOX=' + bbox
    )
    try:
        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        features = data.get('features', [])
        if not features:
            return jsonify({'advice': None, 'stookalarm': False})

        props = features[0]['properties']
        now_hour = datetime.now(timezone.utc).hour
        if now_hour < 6:
            raw = props.get('advies_0')
        elif now_hour < 12:
            raw = props.get('advies_6')
        elif now_hour < 18:
            raw = props.get('advies_12')
        else:
            raw = props.get('advies_18')

        # 0 = code_yellow (ok), 1 = code_orange (ongunstig), 2 = code_red (stookalarm)
        color_map = {'0': 'code_yellow', '1': 'code_orange', '2': 'code_red'}
        advice = color_map.get(str(raw), 'code_yellow')
        return jsonify({
            'advice':    advice,
            'lki':       props.get('lki'),
            'wind_bft':  props.get('wind_bft'),
            'stookalarm': advice == 'code_red',
        })
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
