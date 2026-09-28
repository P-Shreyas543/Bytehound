"""Headless live hardware smoke test against BMS on COM15."""

import os
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from single_cell_cycler.ui.main_window import MainWindow


def run_com15_smoke_test(port: str = "COM15", baud: int = 115200):
    print(f"============================================================")
    print(f"   STARTING HEADLESS BMS HARDWARE SMOKE TEST ON {port}")
    print(f"============================================================")

    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    # 1. Select COM15 in combo box
    port_found = False
    for i in range(window.combo_port.count()):
        p_val = window.combo_port.itemData(i)
        p_txt = window.combo_port.itemText(i)
        if p_val == port or port in p_txt:
            window.combo_port.setCurrentIndex(i)
            port_found = True
            print(f"[OK] Found port in dropdown: {p_txt} (data={p_val})")
            break

    if not port_found:
        print(f"[WARN] {port} not in autodetected list. Forcing port selection...")
        window.combo_port.addItem(port, port)
        window.combo_port.setCurrentIndex(window.combo_port.count() - 1)

    # 2. Connect to COM15
    print(f"[ACTION] Connecting to {port} @ {baud} baud...")
    window._toggle_connection()

    # Wait up to 3 seconds for initial connection and telemetry
    start_t = time.time()
    rx_received = False
    while time.time() - start_t < 3.5:
        app.processEvents()
        if window.transceiver._rx_count > 0:
            rx_received = True
            break
        time.sleep(0.05)

    if not rx_received:
        print(f"[ERROR] No telemetry received from {port} within 3.5s! Check power and TX/RX wiring.")
        window.close()
        return False

    print(f"[SUCCESS] Telemetry link online! Received {window.transceiver._rx_count} packets.")

    # 3. Read and verify live KPI telemetry values
    # Process for 1 more second to gather all frames
    t_gather = time.time()
    while time.time() - t_gather < 1.0:
        app.processEvents()
        time.sleep(0.05)

    v_str = window.dashboard.card_voltage.lbl_value.text()
    i_str = window.dashboard.card_current.lbl_value.text()
    temp_val = window.dashboard.card_temp.lbl_value.text()
    temp_sub = window.dashboard.card_temp.lbl_sub.text()
    soc_str = window.dashboard.card_soc.lbl_value.text()
    soc_sub = window.dashboard.card_soc.lbl_sub.text()
    bus_str = window.dashboard.card_bus.lbl_value.text()
    bus_sub = window.dashboard.card_bus.lbl_sub.text()

    print(f"\n--- LIVE TELEMETRY READOUT FROM {port} ---")
    print(f"  Cell Voltage : {v_str} V")
    print(f"  Cell Current : {i_str} A")
    print(f"  Cell Temp    : {temp_val} °C ({temp_sub})")
    print(f"  State of Chg : {soc_str} % ({soc_sub})")
    print(f"  Bus Voltages : {bus_str} V ({bus_sub})")
    print(f"  Live Plot Pts: {len(window.live_plots.voltages)} samples")
    print(f"----------------------------------------------\n")

    # 4. Verify Active Cell Switching (Cell 1 vs Cell 2)
    print(f"[ACTION] Testing Cell 1 Relay Control (0x6000 -> 0x01)...")
    window.combo_active_cell.setCurrentIndex(0)  # Cell 1
    app.processEvents()
    time.sleep(0.3)

    print(f"[ACTION] Testing Cell 2 Relay Control (0x6000 -> 0x03)...")
    window.combo_active_cell.setCurrentIndex(1)  # Cell 2
    app.processEvents()
    time.sleep(0.3)

    # 5. Brief Discharge Load Bank Pulse (0.2A Load 1) to verify response
    print(f"[ACTION] Testing brief 0.2A Load Pulse (0x6004=0x01, 0x6003=0x01)...")
    window.transceiver.send_command(0x6004, 0x01, priority=1)
    window.transceiver.send_command(0x6003, 0x01, priority=1)
    t_load = time.time()
    while time.time() - t_load < 1.0:
        app.processEvents()
        time.sleep(0.05)

    print(f"[ACTION] Turning off load pulse (0x6003=0x00, 0x6004=0x00)...")
    window.transceiver.send_command(0x6003, 0x00, priority=1)
    window.transceiver.send_command(0x6004, 0x00, priority=1)
    app.processEvents()

    # 6. Test Emergency Stop & Safe Disconnect
    print(f"[ACTION] Testing Emergency Stop...")
    window._emergency_stop()
    assert window.engine.state.value == "Safety Stop"
    print(f"[OK] Emergency Stop verified: Engine state = Safety Stop")

    # Clean close
    print(f"[ACTION] Disconnecting and closing cleanly...")
    window.close()
    app.processEvents()
    time.sleep(0.2)

    print(f"\n============================================================")
    print(f"   HEADLESS COM15 SMOKE TEST COMPLETED SUCCESSFULLY!")
    print(f"============================================================")
    return True


if __name__ == "__main__":
    success = run_com15_smoke_test("COM15", 115200)
    sys.exit(0 if success else 1)
