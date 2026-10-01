"""Real-time KPI metric card dashboard widget."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QVBoxLayout,
    QSizePolicy,
    QWidget,
)

from ...comm.packet_codec import BoardParamsTelemetry, CellDataTelemetry, FaultSoCTelemetry
from .elided_label import ElidedLabel
from ..theme import (
    set_style,
    BG_CARD,
    BORDER_COLOR,
    COLOR_ACCENT,
    COLOR_CHARGE,
    COLOR_DANGER,
    COLOR_DISCHARGE,
    COLOR_REST,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class KPICard(QFrame):
    """Reusable card with title, large numeric value, unit, and subtitle."""

    def __init__(
        self,
        title: str,
        initial_value: str = "--",
        unit: str = "",
        subtitle: str = "",
        accent_color: str = COLOR_ACCENT,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.accent_color = accent_color
        self.setStyleSheet(f"""
            KPICard {{
                background-color: {BG_CARD};
                border: 1px solid {BORDER_COLOR};
                border-radius: 8px;
            }}
            KPICard QLabel {{
                background-color: transparent;
            }}
        """)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)

        # Title
        self.lbl_title = ElidedLabel(title.upper())
        self.lbl_title.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 0.5px;")
        layout.addWidget(self.lbl_title)

        # Main Value + Unit row
        val_row = QHBoxLayout()
        val_row.setSpacing(6)
        self.lbl_value = QLabel(initial_value)
        self.lbl_value.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.lbl_value.setStyleSheet(f"color: {accent_color}; font-size: 24px; font-weight: 800; font-family: 'Consolas', monospace;")
        val_row.addWidget(self.lbl_value)

        self.lbl_unit = QLabel(unit)
        self.lbl_unit.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 14px; font-weight: 600; padding-bottom: 2px;")
        self.lbl_unit.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft)
        val_row.addWidget(self.lbl_unit)
        val_row.addStretch()
        layout.addLayout(val_row)

        # Subtitle / Status
        # Single line, elided: a changing subtitle never re-wraps and resizes the card
        self.lbl_sub = ElidedLabel(subtitle)
        self.lbl_sub.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        layout.addWidget(self.lbl_sub)

        # Empty while telemetry is fresh; shows a red warning only when data is stale
        self.lbl_age = ElidedLabel("")
        self.lbl_age.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px;")
        layout.addWidget(self.lbl_age)

    def set_title(self, title: str) -> None:
        self.lbl_title.setText(title.upper())

    def set_value(
        self,
        val_str: str,
        sub_str: str | None = None,
        color: str | None = None,
        unit_str: str | None = None,
    ) -> None:
        self.lbl_value.setText(val_str)
        if unit_str is not None:
            self.lbl_unit.setText(unit_str)
        if sub_str is not None:
            self.lbl_sub.setText(sub_str)
        if color is not None:
            set_style(self.lbl_value, f"color: {color}; font-size: 24px; font-weight: 800; font-family: 'Consolas', monospace;")

    def set_age(self, age_s: float | None) -> None:
        if age_s is not None and age_s > 5.0:
            text, color = f"Telemetry stale · {age_s:.0f}s", COLOR_DANGER
        else:
            text, color = "", TEXT_MUTED
        self.lbl_age.setText(text)
        set_style(self.lbl_age, f"color: {color}; font-size: 10px;")


class KPIDashboard(QWidget):
    """Grid of digital cards showing live cell, cycler, and board parameters."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)

        # Internal operational states for dynamic card presentation
        self._is_charging: bool = False
        self._is_discharging: bool = False
        self._last_params: BoardParamsTelemetry | None = None

        # Card 1: Cell Voltage
        self.card_voltage = KPICard("Cell Voltage", "0.000", "V", "Limit: 2.80 - 4.20 V", COLOR_ACCENT)
        layout.addWidget(self.card_voltage, 0, 0)

        # Card 2: Cell Current
        self.card_current = KPICard("Cell Current", "0.000", "A", "REST (0.00 W)", COLOR_REST)
        layout.addWidget(self.card_current, 0, 1)

        # Card 3: Cell Temperatures
        self.card_temp = KPICard("Cell Temp", "25.0", "°C", "Term: 25.0 °C | Amb: 25.0 °C", "#f97316")
        layout.addWidget(self.card_temp, 0, 2)

        # Card 4: SoC (Displays all three SoCs: EKF, CC, OCV; diagnostics logged)
        self.card_soc = KPICard("State of Charge", "--", "%", "CC: --%  │  OCV: --%", "#10b981")
        layout.addWidget(self.card_soc, 0, 3)

        # Card 5: Step Capacity
        self.card_step_cap = KPICard("Step Capacity", "0.0", "mAh", "Step Energy: 0.0 mWh", "#a855f7")
        layout.addWidget(self.card_step_cap, 1, 0)

        # Card 6: Total Cumulative Capacity
        self.card_tot_cap = KPICard("Total Capacity", "0.000", "Ah", "Total Energy: 0.00 Wh", "#ec4899")
        layout.addWidget(self.card_tot_cap, 1, 1)

        # Card 7: Board Bus Voltages (User Requirement: Load with Chg and Chg with Load; dynamic primary)
        self.card_bus = KPICard("Bus Voltages", "0.00", "V", "Chg Bus: 0.00 V | Load Bus: 0.00 V", "#64748b")
        layout.addWidget(self.card_bus, 1, 2)

        # Card 8: Cycle & Step Status
        self.card_cycle_kpi = KPICard("Cycle / Step", "Cycle 1", "", "Step: Idle", COLOR_ACCENT)
        layout.addWidget(self.card_cycle_kpi, 1, 3)
        self._grid_layout = layout
        self._cards = [
            self.card_voltage, self.card_current, self.card_temp, self.card_soc,
            self.card_step_cap, self.card_tot_cap, self.card_bus, self.card_cycle_kpi,
        ]
        self._last_columns = 4
        self.card_soc.setToolTip("SoC sources: displayed OCV and coulomb-counting values from the BMS.")
        self.card_current.setToolTip("Positive current is charging; negative current is discharging.")
        self.card_step_cap.setToolTip("Capacity and energy accumulated since the current step began.")
        self.card_tot_cap.setToolTip("Cumulative charge/discharge throughput for this test session.")

    def set_cell_number(self, cell_num: int) -> None:
        """Make the live KPI identity explicit when the active relay changes."""
        cell = 2 if int(cell_num) == 2 else 1
        self.card_voltage.set_title(f"Cell {cell} Voltage")
        self.card_current.set_title(f"Cell {cell} Current")
        self.card_temp.set_title(f"Cell {cell} Temp")
        self.card_cycle_kpi.set_title(f"Cell {cell} · Cycle / Step")

    def set_telemetry_age(self, age_s: float | None) -> None:
        """Show freshness without overwriting the metric-specific subtitle."""
        for card in self._cards:
            card.set_age(age_s)

    def set_run_context(
        self,
        cell_num: int,
        recipe: str,
        step_name: str,
        elapsed_s: float,
        cycle_idx: int | None = None,
    ) -> None:
        cell = 2 if int(cell_num) == 2 else 1
        self.card_cycle_kpi.set_title(f"Cell {cell} · Cycle / Step")
        val_str = f"Cycle {cycle_idx}" if cycle_idx is not None else self.card_cycle_kpi.lbl_value.text()
        st_text = f"Step: {step_name}" if step_name else "Step: Idle"
        self.card_cycle_kpi.set_value(val_str, st_text)
        minutes, seconds = divmod(int(max(0.0, elapsed_s)), 60)
        self.card_cycle_kpi.setToolTip(
            f"Recipe: {recipe}\nStep: {step_name}\nElapsed: {minutes:02d}:{seconds:02d}"
        )

    def resizeEvent(self, event) -> None:
        """Reflow KPI cards for wide, medium, and compact window widths."""
        width = self.width()
        # Keep 4 columns down to small laptop widths: fewer columns doubles the dashboard height
        columns = 4 if width >= 880 else 2 if width >= 480 else 1
        if columns != self._last_columns:
            for card in self._cards:
                self._grid_layout.removeWidget(card)
            for index, card in enumerate(self._cards):
                self._grid_layout.addWidget(card, index // columns, index % columns)
            self._last_columns = columns
        super().resizeEvent(event)

    def update_cell_data(self, data: CellDataTelemetry) -> None:
        # Voltage
        # One steady colour; red only when the reading is outside the safe window
        v_color = COLOR_ACCENT
        if data.voltage <= 2.85 or data.voltage >= 4.25:
            v_color = COLOR_DANGER
        self.card_voltage.set_value(f"{data.voltage:.3f}", color=v_color)

        # Current & Power
        power = data.voltage * data.current
        if data.current > 0.05:
            status_text = f"CHARGING (+{power:.2f} W)"
            c_color = COLOR_CHARGE
            self._is_charging = True
            self._is_discharging = False
        elif data.current < -0.05:
            status_text = f"DISCHARGING ({power:.2f} W)"
            c_color = COLOR_DISCHARGE
            self._is_charging = False
            self._is_discharging = True
        else:
            status_text = "RESTING (0.00 W)"
            c_color = COLOR_REST
            self._is_charging = False
            self._is_discharging = False

        self.card_current.set_value(f"{data.current:+.3f}", status_text, color=c_color)

        # Temperature
        max_t = max(data.body_temp, data.terminal_temp)
        t_color = "#f97316" if max_t < 45.0 else COLOR_DANGER
        self.card_temp.set_value(
            f"{max_t:.1f}",
            f"Term: {data.terminal_temp:.1f} °C | Body: {data.body_temp:.1f} °C",
            color=t_color,
        )

        # Refresh bus card with live charging/discharging state
        if self._last_params:
            self._refresh_bus_card()

    def update_board_params(self, params: BoardParamsTelemetry) -> None:
        self._last_params = params
        self._refresh_bus_card()

    def _refresh_bus_card(self) -> None:
        if not self._last_params:
            return
        params = self._last_params

        # Requirement: "Load with Chg and Chg with load.
        # And it should show Chg voltage while charging and Load while discharging"
        if self._is_charging:
            primary_v = params.charge_voltage
            bus_color = COLOR_CHARGE
            self.card_bus.set_title("Bus Voltage (Chg)")
            sub = f"Chg Bus: {params.charge_voltage:.2f} V | Load Bus: {params.load_voltage:.2f} V"
        elif self._is_discharging:
            primary_v = params.load_voltage
            bus_color = COLOR_DISCHARGE
            self.card_bus.set_title("Bus Voltage (Load)")
            sub = f"Load Bus: {params.load_voltage:.2f} V | Chg Bus: {params.charge_voltage:.2f} V"
        else:
            primary_v = params.charge_voltage if params.charge_voltage > 0.05 else params.load_voltage
            bus_color = "#64748b"
            self.card_bus.set_title("Bus Voltages")
            sub = f"Chg Bus: {params.charge_voltage:.2f} V | Load Bus: {params.load_voltage:.2f} V"

        self.card_bus.set_value(f"{primary_v:.2f}", sub, color=bus_color)

    def update_fault_soc(self, fault_soc: FaultSoCTelemetry) -> None:
        # Check if 17-byte EKF frame is present (indicated by non-zero soc_ekf or vr1/vr2/p_diag)
        if fault_soc.soc_ekf > 0.0 or fault_soc.vr1 != 0.0 or fault_soc.vr2 != 0.0:
            self.card_soc.set_title("State of Charge (EKF · CC · OCV)")
            self.card_soc.set_value(
                val_str=f"{fault_soc.soc_ekf:.1f}",
                sub_str=f"CC: {fault_soc.soc_cc:.1f}%  │  OCV: {fault_soc.soc_ocv:.1f}%",
                unit_str="% EKF",
            )
            self.card_soc.setToolTip(
                f"State of Charge Sources:\n"
                f"  • EKF (Main / Recipe Cutoff): {fault_soc.soc_ekf:.2f}%\n"
                f"  • Coulomb Counting (CC): {fault_soc.soc_cc:.2f}%\n"
                f"  • Open-Circuit Voltage (OCV): {fault_soc.soc_ocv:.2f}%\n\n"
                f"Logged Diagnostics:\n"
                f"  • Polarization VR1: {fault_soc.vr1:.4f} V\n"
                f"  • Polarization VR2: {fault_soc.vr2:.4f} V\n"
                f"  • Covariance P_diag: ({fault_soc.p_diag[0]:.4f}, {fault_soc.p_diag[1]:.4f}, {fault_soc.p_diag[2]:.4f})"
            )
        else:
            # Legacy 5-byte payload (swapped labels: OCV value displayed under CC, CC under OCV)
            self.card_soc.set_title("State of Charge (CC · OCV)")
            self.card_soc.set_value(
                val_str=f"{fault_soc.soc_ocv:.1f}",
                sub_str=f"CC: {fault_soc.soc_ocv:.1f}%  │  OCV: {fault_soc.soc_cc:.1f}%",
                unit_str="%",
            )
            self.card_soc.setToolTip(
                f"State of Charge Sources:\n"
                f"  • Coulomb Counting (CC): {fault_soc.soc_ocv:.2f}%\n"
                f"  • Open-Circuit Voltage (OCV): {fault_soc.soc_cc:.2f}%"
            )

    def update_metrics(
        self,
        step_mah: float,
        step_mwh: float,
        tot_chg_mah: float,
        tot_dis_mah: float,
        tot_chg_mwh: float,
        tot_dis_mwh: float,
        cycle_idx: int,
        step_name: str,
    ) -> None:
        self.card_step_cap.set_value(f"{abs(step_mah):.1f}", f"Step Energy: {abs(step_mwh):.1f} mWh")
        net_ah = (tot_chg_mah + tot_dis_mah) / 1000.0
        net_wh = (tot_chg_mwh + tot_dis_mwh) / 1000.0
        self.card_tot_cap.set_value(f"{net_ah:.3f}", f"Total Energy: {net_wh:.2f} Wh")
        st_text = f"Step: {step_name}" if step_name else "Step: Idle"
        self.card_cycle_kpi.set_value(f"Cycle {cycle_idx}", st_text)
