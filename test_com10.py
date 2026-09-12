import time
import serial
from collections import Counter
from pathlib import Path
from app.decoder.config_loader import load_config
from app.protocol.packet_parser import create_parser
from app.decoder.frame_decoder import decode_frame

def test_port(port="COM10", baud=None, duration_sec=3):
    cfg_path = Path("Ather_v1_0_1.xlsx")
    cfg = load_config(cfg_path)
    if baud is None:
        baud = cfg.serial_defaults.baud_rate or 2000000

    print(f"Loaded config: {cfg.protocol.profile_name} ({cfg.protocol.parser_type})")
    print(f"Connecting to {port} at {baud} baud (listening for {duration_sec}s)...")
    
    try:
        ser = serial.Serial(port, baud, timeout=0.1)
    except Exception as e:
        print(f"\n[NOTE] Could not open {port}: {e}")
        print("If Bytehound GUI is currently connected to COM10, disconnect in Bytehound first or view live data inside Bytehound!")
        return

    parser = create_parser(cfg.protocol)
    state_dict = {}
    known_frames_rx = Counter()
    unknown_frames_rx = Counter()
    total_bytes = 0
    t0 = time.time()
    last_print = 0

    while time.time() - t0 < duration_sec:
        chunk = ser.read(512)
        if chunk:
            total_bytes += len(chunk)
            parser.feed(chunk)
            for p in parser.extract_all():
                if not p.ok:
                    continue
                if p.frame_id in cfg.frames:
                    known_frames_rx[p.frame_id] += 1
                    decode_frame(cfg, p.frame_id, p.payload, state_dict)
                else:
                    unknown_frames_rx[p.frame_id] += 1

        now = time.time()
        if now - last_print >= 0.5:
            last_print = now
            pack_state = state_dict.get("Pack Parameters", state_dict.get("Pack", {}))
            cv_state = state_dict.get("Cell Voltages", {})
            v_live = pack_state.get("Pack_Voltage", 0.0)
            i_live = pack_state.get("Pack_Current", pack_state.get("Pack_Current_Standby", pack_state.get("Battery_Current", 0.0)))
            soc_live = pack_state.get("Battery_SOC", pack_state.get("Pack_SOC_Live", 0.0))
            voltages = [
                cv_state.get(f"Cell_Voltage_{i}", cv_state.get(f"Vol{i}"))
                for i in range(1, 15)
                if cv_state.get(f"Cell_Voltage_{i}", cv_state.get(f"Vol{i}")) is not None
            ]
            vdiff = (max(voltages) - min(voltages))*1000 if voltages else 0.0
            print(f"[{now - t0:4.1f}s] Pack: {v_live:5.2f}V | Current: {i_live:+.2f}A | SOC: {soc_live:3.0f}% | Imbalance: {vdiff:4.1f}mV")

    ser.close()

    print("\n" + "=" * 72)
    print("                 LIVE ATHER TELEMETRY DASHBOARD")
    print("=" * 72)
    
    # 1. Pack & Vehicle Summary
    pack_state = state_dict.get("Pack Parameters", state_dict.get("Pack", {}))
    veh_state = state_dict.get("Vehicle Parameters", state_dict.get("Vehicle", {}))
    
    print("\n--- BATTERY PACK & VEHICLE STATUS ---")
    v_live = pack_state.get("Pack_Voltage")
    if v_live is not None:
        print(f"  • Total Pack Voltage (0x141):     {v_live:.2f} V")
    v_curr = pack_state.get("Pack_Current", pack_state.get("Pack_Current_Standby"))
    if v_curr is not None:
        print(f"  • Live / Standby Current (0x141): {v_curr:+.2f} A")
    soc_live = pack_state.get("Battery_SOC", pack_state.get("Pack_SOC_Live"))
    if soc_live is not None:
        print(f"  • Battery State of Charge (SOC):  {soc_live:.0f} %")
    d_limit = pack_state.get("Discharge_Power_Limit")
    if d_limit is not None:
        print(f"  • Discharge Power Limit (0x147):  {d_limit:.0f} W")
    c_limit = pack_state.get("Charge_Power_Limit")
    if c_limit is not None:
        print(f"  • Charge Power Limit (0x148):     {c_limit:.0f} W")
    i_limit = pack_state.get("Pack_Current_Limit")
    if i_limit is not None:
        print(f"  • Current Limit (0x148):          {i_limit:.0f} A")
    aux_v = veh_state.get("Auxiliary_12V_Voltage", veh_state.get("Aux_12V_Voltage"))
    if aux_v is not None:
        print(f"  • Auxiliary 12V Rail (0x153):     {aux_v:.2f} V")
    speed = veh_state.get("Vehicle_Speed")
    if speed is not None:
        print(f"  • Vehicle Speed (0x18C):          {speed:.1f} km/h")
    throttle = veh_state.get("Throttle_Position", veh_state.get("Throttle_2"))
    if throttle is not None:
        print(f"  • Throttle Position (0x28C):      {throttle:.1f} %")
    dm = veh_state.get("Drive_Mode")
    if dm is not None:
        print(f"  • Drive Mode State (0x101):       {'ACTIVE' if dm else 'STANDBY'}")
    ks = veh_state.get("Key_Switch")
    if ks is not None:
        print(f"  • Key Switch State (0x205):       {'ON' if ks else 'OFF'}")

    # 2. 14S Cell Voltages
    cv_state = state_dict.get("Cell Voltages", {})
    if cv_state:
        print("\n--- 14S CELL VOLTAGES ---")
        voltages = []
        for i in range(1, 15):
            val = cv_state.get(f"Cell_Voltage_{i}", cv_state.get(f"Vol{i}"))
            if val is not None:
                voltages.append(val)

        for i in range(1, 15, 2):
            v1_name = f"Cell_{i:02d}"
            v2_name = f"Cell_{i+1:02d}"
            v1_val = cv_state.get(f"Cell_Voltage_{i}", cv_state.get(f"Vol{i}", 0.0))
            v2_val = cv_state.get(f"Cell_Voltage_{i+1}", cv_state.get(f"Vol{i+1}", 0.0)) if i+1 <= 14 else None
            line = f"  {v1_name}: {v1_val:.4f} V"
            if v2_val is not None:
                line += f"   |   {v2_name}: {v2_val:.4f} V"
            print(line)

        if voltages:
            v_sum = sum(voltages)
            v_min = min(voltages)
            v_max = max(voltages)
            v_diff = (v_max - v_min) * 1000
            v_avg = v_sum / len(voltages)
            print(f"\n  • Cell Sum:        {v_sum:.3f} V (Pack reading: {v_live if v_live else v_sum:.2f} V)")
            print(f"  • Min Cell:        {v_min:.4f} V")
            print(f"  • Max Cell:        {v_max:.4f} V")
            print(f"  • Average Cell:    {v_avg:.4f} V")
            print(f"  • Cell Imbalance:  {v_diff:.1f} mV")

    # 3. Active Battery Temperatures
    temp_state = state_dict.get("Battery Temperatures", {})
    if temp_state:
        print("\n--- ACTIVE BATTERY TEMPERATURE SENSORS ---")
        for k, v in sorted(temp_state.items()):
            print(f"  • {k:<25}: {v:.2f} °C")
        t_vals = list(temp_state.values())
        if t_vals:
            print(f"  • Min Temp: {min(t_vals):.2f} °C | Max Temp: {max(t_vals):.2f} °C | Delta: {max(t_vals)-min(t_vals):.2f} °C")

    # 4. Internal Module Temperatures
    mod_state = state_dict.get("Module Temperatures", {})
    if mod_state:
        print("\n--- BMS MODULE & POWER STAGE TEMPERATURES (0x170) ---")
        for k, v in sorted(mod_state.items()):
            print(f"  • {k:<25}: {v:.2f} °C")

    # 5. Cell Internal Resistances
    res_state = state_dict.get("Cell Internal Resistances", {})
    if res_state:
        print("\n--- CELL INTERNAL RESISTANCES (0.1 mOhm) ---")
        r_vals = [res_state.get(f"Cell_{i}_Resistance") for i in range(1, 15) if res_state.get(f"Cell_{i}_Resistance") is not None]
        if r_vals:
            print(f"  • Cells 1-14 IR Range: {min(r_vals):.1f} - {max(r_vals):.1f} mOhm (Avg: {sum(r_vals)/len(r_vals):.1f} mOhm)")

    # 6. Cell Open Circuit Voltages
    ocv_state = state_dict.get("Cell Open Circuit Voltages", {})
    if ocv_state:
        print("\n--- CELL OPEN CIRCUIT VOLTAGES (OCV) ---")
        ocv_vals = [ocv_state.get(f"Cell_{i}_OCV") for i in range(1, 15) if ocv_state.get(f"Cell_{i}_OCV") is not None]
        if ocv_vals:
            print(f"  • Cells 1-14 OCV: {min(ocv_vals):.3f} V - {max(ocv_vals):.3f} V (Sum: {sum(ocv_vals):.2f} V)")

    # 7. Cell State of Charge
    csoc_state = state_dict.get("Cell State of Charge", {})
    if csoc_state:
        print("\n--- CELL INDIVIDUAL STATE OF CHARGE (%) ---")
        csoc_vals = [csoc_state.get(f"Cell_{i}_SOC") for i in range(1, 15) if csoc_state.get(f"Cell_{i}_SOC") is not None]
        if csoc_vals:
            print(f"  • Cells 1-14 SOC: {min(csoc_vals):.0f}% - {max(csoc_vals):.0f}%")

    print("\n--- FRAMES RECEIVED SUMMARY ---")
    for fid, cnt in sorted(known_frames_rx.items()):
        fname = cfg.frame_names.get(fid, "Unknown")
        print(f"  ID 0x{fid:03X} ({fname:<28}): {cnt:4d} frames")

    print(f"\n  Total raw bytes received on COM10: {total_bytes}")
    print("=" * 72)

if __name__ == "__main__":
    test_port()
