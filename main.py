import sys
import requests

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QLineEdit, QFrame,
)
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QFont
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

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
}

AC_SYSTEMS: dict[str, float] = {
    'Premium Inverter (Daikin, Mitsubishi etc.)': 0.50,
    'Standard Inverter Split-Unit':               0.45,
    'Multi-Split System':                         0.42,
    'Non-Inverter Split-Unit':                    0.35,
    'Portable AC':                                0.25,
}

GAS_ENERGY_CONTENT = 9.77   # kWh/m³  (Gronings/L-gas)
BOILER_EFFICIENCY  = 0.95   # modern HR condensing boiler

# Map extent — longitude/latitude bounds for the Netherlands
MAP_WEST, MAP_EAST   = 3.20, 7.30
MAP_SOUTH, MAP_NORTH = 50.65, 53.75

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
# Background worker
# ---------------------------------------------------------------------------

class TempFetchWorker(QThread):
    finished = pyqtSignal(dict)

    def run(self) -> None:
        temps: dict[str, float | None] = {}
        for city, (lat, lon) in CITIES.items():
            try:
                temps[city] = fetch_temperature(lat, lon)
            except Exception:
                temps[city] = None
        self.finished.emit(temps)

# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("GasOrAirco — Heating Cost Advisor")
        self.setMinimumSize(960, 640)
        self.temperatures: dict[str, float | None] = {}
        self.selected_city = "Amsterdam"
        self._build_ui()
        self._start_fetch()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # ── Left control panel ─────────────────────────────────────────
        left = QWidget()
        left.setFixedWidth(300)
        left.setObjectName("sidebar")
        lv = QVBoxLayout(left)
        lv.setSpacing(12)
        lv.setContentsMargins(20, 20, 20, 20)

        title = QLabel("GasOrAirco")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title.setObjectName("appTitle")
        lv.addWidget(title)

        subtitle = QLabel("Heating Cost Advisor")
        subtitle.setFont(QFont("Segoe UI", 9))
        subtitle.setObjectName("appSubtitle")
        lv.addWidget(subtitle)

        # Divider
        lv.addWidget(self._divider())

        # City display
        self.city_label = QLabel(f"City: {self.selected_city}")
        self.city_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        lv.addWidget(self.city_label)

        hint = QLabel("Click a city on the map")
        hint.setObjectName("hint")
        lv.addWidget(hint)

        self.temp_label = QLabel("Outdoor temp: loading…")
        self.temp_label.setObjectName("tempLabel")
        lv.addWidget(self.temp_label)

        lv.addWidget(self._divider())

        # AC system picker
        lv.addWidget(self._section_label("AC System"))
        self.ac_combo = QComboBox()
        self.ac_combo.addItems(list(AC_SYSTEMS.keys()))
        lv.addWidget(self.ac_combo)

        self.cop_label = QLabel("COP: —")
        self.cop_label.setObjectName("copLabel")
        lv.addWidget(self.cop_label)

        lv.addWidget(self._divider())

        # Energy prices
        lv.addWidget(self._section_label("Energy Prices"))

        gas_row = QHBoxLayout()
        gas_row.addWidget(QLabel("Gas price (€/m³):"))
        self.gas_input = QLineEdit("1.25")
        self.gas_input.setMaximumWidth(80)
        gas_row.addWidget(self.gas_input)
        lv.addLayout(gas_row)

        elec_row = QHBoxLayout()
        elec_row.addWidget(QLabel("Electricity price (€/kWh):"))
        self.elec_input = QLineEdit("0.32")
        self.elec_input.setMaximumWidth(80)
        elec_row.addWidget(self.elec_input)
        lv.addLayout(elec_row)

        lv.addWidget(self._divider())

        # Result labels
        self.gas_cost_label   = QLabel("Gas: —")
        self.airco_cost_label = QLabel("AC: —")
        lv.addWidget(self.gas_cost_label)
        lv.addWidget(self.airco_cost_label)

        self.recommendation_label = QLabel("")
        self.recommendation_label.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.recommendation_label.setWordWrap(True)
        self.recommendation_label.setAlignment(
            self.recommendation_label.alignment()
        )
        lv.addWidget(self.recommendation_label)

        self.savings_label = QLabel("")
        self.savings_label.setObjectName("savingsLabel")
        lv.addWidget(self.savings_label)

        lv.addStretch()
        root.addWidget(left)

        # ── Right map panel ────────────────────────────────────────────
        self.figure = Figure(figsize=(5, 6), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setObjectName("mapCanvas")
        root.addWidget(self.canvas, stretch=1)

        self._draw_map()

        # Signals
        self.canvas.mpl_connect('button_press_event', self._on_map_click)
        self.ac_combo.currentIndexChanged.connect(self._recalculate)
        self.gas_input.textChanged.connect(self._recalculate)
        self.elec_input.textChanged.connect(self._recalculate)

        self._recalculate()

    def _divider(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("divider")
        return sep

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text.upper())
        lbl.setObjectName("sectionLabel")
        return lbl

    # ------------------------------------------------------------------
    # Background fetch
    # ------------------------------------------------------------------

    def _start_fetch(self) -> None:
        self.worker = TempFetchWorker()
        self.worker.finished.connect(self._on_temps_fetched)
        self.worker.start()

    def _on_temps_fetched(self, temps: dict) -> None:
        self.temperatures = temps
        self._update_temp_label(self.selected_city)
        self._recalculate()

    # ------------------------------------------------------------------
    # Map interaction
    # ------------------------------------------------------------------

    def _on_map_click(self, event) -> None:
        if event.inaxes is None or event.xdata is None:
            return
        nearest = min(
            CITIES,
            key=lambda c: (CITIES[c][1] - event.xdata) ** 2 + (CITIES[c][0] - event.ydata) ** 2,
        )
        self._select_city(nearest)

    def _select_city(self, city: str) -> None:
        self.selected_city = city
        self.city_label.setText(f"City: {city}")
        self._update_temp_label(city)
        self._recalculate()

    # ------------------------------------------------------------------
    # Slot helpers
    # ------------------------------------------------------------------

    def _update_temp_label(self, city: str) -> None:
        temp = self.temperatures.get(city)
        if temp is not None:
            self.temp_label.setText(f"Outdoor temp: {temp:.1f}°C")
        else:
            self.temp_label.setText("Outdoor temp: unknown")

    # ------------------------------------------------------------------
    # Calculation
    # ------------------------------------------------------------------

    def _get_cop(self) -> float | None:
        temp = self.temperatures.get(self.selected_city)
        if temp is None:
            return None
        factor = AC_SYSTEMS[self.ac_combo.currentText()]
        return calculate_cop(temp, factor)

    def _city_recommendation(self, city: str, gas_cost_kwh: float, elec_price: float, factor: float) -> str:
        temp = self.temperatures.get(city)
        if temp is None:
            return ''
        cop = calculate_cop(temp, factor)
        if cop is None:
            return '\u2600\ufe0f'           # ☀️  no heating needed
        return '\u2744\ufe0f' if (elec_price / cop) < gas_cost_kwh else '\U0001f525'  # ❄️ or 🔥

    def _recalculate(self) -> None:
        cop = self._get_cop()
        self.cop_label.setText(f"COP: {cop:.2f}" if cop is not None else "COP: —")

        try:
            gas_price  = float(self.gas_input.text().replace(',', '.'))
            elec_price = float(self.elec_input.text().replace(',', '.'))
        except ValueError:
            self._clear_results("Enter valid prices.")
            self._draw_map()
            return

        gas_cost_kwh = gas_price / (GAS_ENERGY_CONTENT * BOILER_EFFICIENCY)
        self.gas_cost_label.setText(f"Gas: €{gas_cost_kwh:.3f}/kWh heat")

        if cop is None:
            self.airco_cost_label.setText("AC: COP N/A")
            self.recommendation_label.setText("No heating needed")
            self.recommendation_label.setStyleSheet(
                "color: #1a7f37; background: #dcfce7; padding: 8px 12px; border-radius: 8px;"
            )
            self.savings_label.setText("")
            self._draw_map()
            return

        airco_cost_kwh = elec_price / cop
        self.airco_cost_label.setText(f"AC: €{airco_cost_kwh:.3f}/kWh heat")

        savings = abs(gas_cost_kwh - airco_cost_kwh)
        self.savings_label.setText(f"Savings: €{savings:.3f}/kWh")

        if airco_cost_kwh < gas_cost_kwh:
            self.recommendation_label.setText("❄️  Use AC")
            self.recommendation_label.setStyleSheet(
                "color: #1d4ed8; background: #dbeafe; padding: 8px 12px; border-radius: 8px;"
            )
        else:
            self.recommendation_label.setText("🔥  Use GAS")
            self.recommendation_label.setStyleSheet(
                "color: #b91c1c; background: #fee2e2; padding: 8px 12px; border-radius: 8px;"
            )

        self._draw_map()

    def _clear_results(self, message: str) -> None:
        self.gas_cost_label.setText("Gas: —")
        self.airco_cost_label.setText("AC: —")
        self.recommendation_label.setText(message)
        self.recommendation_label.setStyleSheet(
            "color: #6b7280; background: #f3f4f6; padding: 8px 12px; border-radius: 8px;"
        )
        self.savings_label.setText("")

    # ------------------------------------------------------------------
    # Temperature map
    # ------------------------------------------------------------------

    def _draw_map(self) -> None:
        self.figure.clear()
        self.figure.patch.set_facecolor('#f8fafc')
        ax = self.figure.add_subplot(111)
        ax.set_facecolor('#e8f4f8')

        ax.set_xlim(MAP_WEST, MAP_EAST)
        ax.set_ylim(MAP_SOUTH, MAP_NORTH)
        ax.set_aspect('equal')
        ax.set_title("Temperature Map — Netherlands", fontsize=10, fontweight='bold', color='#1e293b', pad=8)
        ax.set_xlabel("Longitude (°E)", fontsize=8, color='#64748b')
        ax.set_ylabel("Latitude (°N)", fontsize=8, color='#64748b')
        ax.tick_params(labelsize=7, colors='#64748b')
        for spine in ax.spines.values():
            spine.set_edgecolor('#cbd5e1')

        # ── Grayscale map tile background ─────────────────────────────
        try:
            import contextily as cx
            cx.add_basemap(
                ax,
                crs='EPSG:4326',
                source=cx.providers.CartoDB.PositronNoLabels,
                zoom='auto',
                attribution=False,
            )
            ax.set_xlim(MAP_WEST, MAP_EAST)
            ax.set_ylim(MAP_SOUTH, MAP_NORTH)
        except Exception:
            ax.set_facecolor('#dde8f0')

        # ── Resolve prices for per-city icons ─────────────────────────
        try:
            gas_price    = float(self.gas_input.text().replace(',', '.'))
            elec_price   = float(self.elec_input.text().replace(',', '.'))
            gas_cost_kwh = gas_price / (GAS_ENERGY_CONTENT * BOILER_EFFICIENCY)
            prices_valid = True
        except ValueError:
            gas_cost_kwh, elec_price, prices_valid = 0.0, 0.0, False

        factor = AC_SYSTEMS[self.ac_combo.currentText()]

        # ── Partition cities into known / unknown temps ────────────────
        known:   list[tuple[float, float, float, str]] = []
        unknown: list[tuple[float, float, str]]         = []

        for city, (lat, lon) in CITIES.items():
            temp = self.temperatures.get(city)
            if temp is not None:
                known.append((lon, lat, temp, city))
            else:
                unknown.append((lon, lat, city))

        sc = None
        if known:
            lons, lats, temps, names = zip(*known)
            t_min, t_max = min(temps), max(temps)
            if t_min == t_max:
                t_min -= 1.0
                t_max += 1.0

            sc = ax.scatter(
                lons, lats,
                c=temps, cmap='RdYlBu_r',
                vmin=t_min - 1, vmax=t_max + 1,
                s=60, zorder=4,
                edgecolors='#334155', linewidths=0.6,
            )
            for lon, lat, temp, name in zip(lons, lats, temps, names):
                if prices_valid:
                    icon = self._city_recommendation(name, gas_cost_kwh, elec_price, factor)
                    label = f"{icon} {name}\n{temp:.1f}°C" if icon else f"{name}\n{temp:.1f}°C"
                else:
                    label = f"{name}\n{temp:.1f}°C"
                ax.annotate(
                    label,
                    (lon, lat),
                    textcoords="offset points", xytext=(5, 3),
                    fontsize=5.5, zorder=5,
                    bbox=dict(boxstyle='round,pad=0.15', fc='white', alpha=0.70, lw=0),
                )

        if sc is not None:
            cb = self.figure.colorbar(sc, ax=ax, label="Temperature (°C)", shrink=0.65)
            cb.ax.tick_params(labelsize=7)
            cb.set_label("Temperature (°C)", fontsize=8, color='#475569')

        if unknown:
            u_lons, u_lats, _ = zip(*unknown)
            ax.scatter(u_lons, u_lats, c='#94a3b8', s=40, zorder=4, marker='o',
                       edgecolors='#475569', linewidths=0.4)

        # ── Highlight selected city ────────────────────────────────────
        if self.selected_city in CITIES:
            sel_lat, sel_lon = CITIES[self.selected_city]
            ax.scatter(
                [sel_lon], [sel_lat],
                c='none', marker='o', s=280,
                edgecolors='#1e293b', linewidths=2.5, zorder=6,
            )

        self.figure.tight_layout()
        self.canvas.draw()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

APP_STYLE = """
    QMainWindow {
        background: #f1f5f9;
    }
    QWidget#sidebar {
        background: #ffffff;
        border-right: 1px solid #e2e8f0;
    }
    QLabel {
        color: #1e293b;
        font-family: "Segoe UI", Arial, sans-serif;
        font-size: 13px;
    }
    QLabel#appTitle {
        color: #0f172a;
        font-size: 20px;
        font-weight: bold;
    }
    QLabel#appSubtitle {
        color: #64748b;
        font-size: 11px;
    }
    QLabel#hint {
        color: #94a3b8;
        font-size: 11px;
        font-style: italic;
    }
    QLabel#tempLabel {
        color: #475569;
        font-size: 13px;
    }
    QLabel#copLabel {
        color: #475569;
        font-size: 12px;
    }
    QLabel#sectionLabel {
        color: #94a3b8;
        font-size: 10px;
        font-weight: bold;
        letter-spacing: 1px;
    }
    QLabel#savingsLabel {
        color: #475569;
        font-size: 12px;
    }
    QFrame#divider {
        border: none;
        border-top: 1px solid #e2e8f0;
        margin: 2px 0;
    }
    QLineEdit {
        background: #f8fafc;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        padding: 5px 9px;
        font-size: 13px;
        color: #1e293b;
        font-family: "Segoe UI", Arial, sans-serif;
    }
    QLineEdit:focus {
        border-color: #3b82f6;
        background: #ffffff;
    }
    QComboBox {
        background: #f8fafc;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        padding: 5px 9px;
        font-size: 12px;
        color: #1e293b;
        font-family: "Segoe UI", Arial, sans-serif;
    }
    QComboBox:hover {
        border-color: #3b82f6;
    }
    QComboBox::drop-down {
        border: none;
    }
    QComboBox QAbstractItemView {
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        selection-background-color: #dbeafe;
        selection-color: #1d4ed8;
    }
"""


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLE)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
