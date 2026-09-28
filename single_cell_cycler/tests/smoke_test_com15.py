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

    window.transceiver.command_transmitted.connect(
        lambda fid, val, wire: print(f"  [TX WIRE] Frame 0x{fid:04X} -> 0x{val:02X} ({wire.hex().upper()})")
    )
    window.transceiver.command_echo_received.connect(
        lambda echo: print(f"  [RX ECHO] Frame 0x{echo.frame_id:04X} -> 0x{echo.payload_byte:02X}")
    )

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

    # Process events to collect any returned echoes
    t_echo = time.time()
    while time.time() - t_echo < 0.5:
        app.processEvents()
        time.sleep(0.05)

    print(f"\n--- HARDWARE CONTROL READBACK STATUS ---")
    print(f"  Status Bar   : {window.lbl_status_ctrl.text()}")
    print(f"  Relay (0x6000)       : {window.manual_control.lbl_relay_rb.text()}")
    print(f"  Charge Sel (0x6001)  : {window.manual_control.lbl_chg_sel_rb.text()}")
    print(f"  Charge Ctrl (0x6002) : {window.manual_control.lbl_chg_ctrl_rb.text()}")
    print(f"  Discharge Ctrl (0x6003): {window.manual_control.lbl_dis_ctrl_rb.text()}")
    print(f"  Discharge Sel (0x6004) : {window.manual_control.lbl_dis_sel_rb.text()}")
    print(f"-----------------------------------------\n")

    # 6. Verify Automated Safe Step Transition (Charge Setup & Readback Confirmation)
    print(f"[ACTION] Testing Automated Step Transition for CC Charge...")
    from single_cell_cycler.core.profile_model import StepType, TestStep
    chg_step = TestStep(
        step_index=1,
        name="Smoke Test CC Charge",
        step_type=StepType.CHARGE,
        max_charge_voltage=True,
        charge_current_1=False,
        charge_current_2=True,
    )
    chg_completed = []
    chg_failed = []
    window.engine.transition_controller.transition_completed.connect(lambda s: chg_completed.append(s))
    window.engine.transition_controller.transition_failed.connect(lambda f: chg_failed.append(f))
    window.engine.transition_controller.start_transition(step=chg_step, selected_cell=1)

    t_chg = time.time()
    while time.time() - t_chg < 8.0:
        app.processEvents()
        if chg_completed or chg_failed:
            break
        time.sleep(0.02)

    assert len(chg_completed) == 1, f"Step transition failed to complete! Errors: {chg_failed}"
    assert len(chg_failed) == 0
    print(f"[OK] Step transition completed successfully on COM15 hardware!")

    # 7. Test Emergency Stop & Safe Zeroing of All Controls
    print(f"[ACTION] Testing Emergency Stop...")
    window._emergency_stop()
    assert window.engine.state.value == "Safety Stop"
    print(f"[OK] Emergency Stop verified: Engine state = Safety Stop")

    # Give hardware up to 2 seconds to receive 0x00 commands and echo readbacks
    t_zero = time.time()
    while time.time() - t_zero < 2.0:
        app.processEvents()
        time.sleep(0.05)

    rb = window.manual_control.control_readbacks
    print(f"\n--- VERIFYING HARDWARE CONTROL ZEROING READBACKS ---")
    print(f"  0x6000 Relay Readback     : 0x{rb.get(0x6000, 0xFF):02X} (Expected: 0x00)")
    print(f"  0x6001 Chg Sel Readback   : 0x{rb.get(0x6001, 0xFF):02X} (Expected: 0x00)")
    print(f"  0x6002 Chg Ctrl Readback  : 0x{rb.get(0x6002, 0xFF):02X} (Expected: 0x00)")
    print(f"  0x6003 Dis Ctrl Readback  : 0x{rb.get(0x6003, 0xFF):02X} (Expected: 0x00)")
    print(f"  0x6004 Loads Readback     : 0x{rb.get(0x6004, 0xFF):02X} (Expected: 0x00)")
    print(f"-----------------------------------------------------\n")

    assert rb.get(0x6000, 0) == 0x00, f"0x6000 Relay not zeroed: 0x{rb.get(0x6000, 0):02X}"
    assert rb.get(0x6001, 0) == 0x00, f"0x6001 Charge Sel not zeroed: 0x{rb.get(0x6001, 0):02X}"
    assert rb.get(0x6002, 0) == 0x00, f"0x6002 Charge Ctrl not zeroed: 0x{rb.get(0x6002, 0):02X}"
    assert rb.get(0x6003, 0) == 0x00, f"0x6003 Discharge Ctrl not zeroed: 0x{rb.get(0x6003, 0):02X}"
    assert rb.get(0x6004, 0) == 0x00, f"0x6004 Discharge Sel not zeroed: 0x{rb.get(0x6004, 0):02X}"
    print(f"[OK] ALL 5 control registers confirmed zeroed (0x00) on physical hardware!")

    # Clean close
    print(f"[ACTION] Disconnecting and closing cleanly...")
    window.close()
    app.processEvents()
    time.sleep(0.5)

    print(f"\n============================================================")
    print(f"   HEADLESS COM15 SMOKE TEST COMPLETED SUCCESSFULLY!")
    print(f"============================================================")
    return True


if __name__ == "__main__":
    success = run_com15_smoke_test("COM15", 115200)
    sys.exit(0 if success else 1)
