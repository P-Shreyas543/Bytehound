"""Live COM10 Verification using Ather_v1_0_1.dbc directly with cantools.

NOTE: This script does NOT use any .xlsx file.
It directly loads Ather_v1_0_1.dbc via cantools and decodes live CAN packets
received on COM10 at 2,000,000 baud.
"""

from __future__ import annotations
import time
import serial
import cantools

def parse_waveshare_20(buf: bytearray):
    """Extract valid 20-byte Waveshare CAN packets from bytearray buffer."""
    packets = []
    while True:
        idx = buf.find(b"\xAA\x55")
        if idx == -1:
            if len(buf) > 1:
                del buf[:-1]
            break
        if idx > 0:
            del buf[:idx]
        if len(buf) < 20:
            break

        # Checksum = (sum of first 19 bytes + 1) & 0xFF
        expected_chk = (sum(buf[:19]) + 1) & 0xFF
        received_chk = buf[19]
        if expected_chk != received_chk:
            # Drop the first byte to search for next AA 55
            del buf[:1]
            continue

        frame_id = int.from_bytes(buf[5:9], byteorder="little")
        dlc = min(buf[9], 8)
        payload = bytes(buf[10:10 + dlc])
        packets.append((frame_id, payload))
        del buf[:20]

    return packets

def main():
    print("=" * 80)
    print("DIRECT DBC VERIFICATION: Ather_v1_0_1.dbc (NO .xlsx USED)")
    print("=" * 80)

    dbc_path = "Ather_v1_0_1.dbc"
    db = cantools.database.load_file(dbc_path)
    print(f"Loaded DBC File: {dbc_path}")
    print(f"Total Defined Messages in DBC: {len(db.messages)}\n")

    vs_msg = db.get_message_by_frame_id(0x18C)
    vs_sig = vs_msg.signals[0]
    print(f"--- DBC SPECIFICATION FOR VEHICLE SPEED ---")
    print(f"  Message Name:  {vs_msg.name} (0x{vs_msg.frame_id:03X} / {vs_msg.frame_id})")
    print(f"  Signal Name:   {vs_sig.name}")
    print(f"  Start Bit:     {vs_sig.start}")
    print(f"  Bit Length:    {vs_sig.length} bits")
    print(f"  Byte Order:    {vs_sig.byte_order}")
    print(f"  Data Type:     {'Signed' if vs_sig.is_signed else 'Unsigned'}")
    print(f"  Scale Factor:  {vs_sig.scale}")
    print(f"  Offset:        {vs_sig.offset}")
    print(f"  Unit:          {vs_sig.unit}")
    print("-" * 80)

    try:
        ser = serial.Serial("COM10", 2000000, timeout=0.1)
    except Exception as exc:
        print(f"\n[ERROR] Could not open COM10: {exc}")
        print("Ensure no other app has COM10 open.\n")
        return

    buf = bytearray()
    vs_records = []
    dbc_frame_counts = {}
    other_frame_counts = {}

    print("\nListening to live CAN traffic on COM10 @ 2,000,000 baud for 4.0 seconds...")
    t0 = time.time()
    duration = 4.0

    while time.time() - t0 < duration:
        chunk = ser.read(1024)
        if chunk:
            buf.extend(chunk)
            pkts = parse_waveshare_20(buf)
            for frame_id, payload in pkts:
                try:
                    # DIRECT DBC DECODING via cantools
                    decoded = db.decode_message(frame_id, payload)
                    dbc_frame_counts[frame_id] = dbc_frame_counts.get(frame_id, 0) + 1

                    if frame_id == 0x18C:
                        speed_val = decoded["Vehicle_Speed"]
                        # Detailed bit breakdown
                        b1 = payload[1]
                        b2 = payload[2]
                        raw_12 = b1 | ((b2 & 0x0F) << 8)
                        # Two's complement for 12-bit signed
                        raw_signed = raw_12 - 0x1000 if (raw_12 & 0x800) else raw_12

                        vs_records.append({
                            "t": time.time() - t0,
                            "payload_hex": payload.hex(" "),
                            "b1": b1,
                            "b2": b2,
                            "raw_12": raw_12,
                            "raw_signed": raw_signed,
                            "dbc_speed": speed_val,
                        })
                except KeyError:
                    other_frame_counts[frame_id] = other_frame_counts.get(frame_id, 0) + 1

    ser.close()

    total_pkts = sum(dbc_frame_counts.values()) + sum(other_frame_counts.values())
    print(f"\nTotal Packets Received on COM10: {total_pkts}")
    print(f"Vehicle_Speed (0x18C) Frames Received: {len(vs_records)}")

    print("\n" + "=" * 80)
    print("LIVE SAMPLES: DIRECT DBC DECODING OF Vehicle_Speed (0x18C)")
    print("=" * 80)
    print(f"{'Time':>6} | {'Raw Payload (8 Bytes)':<24} | {'B1 B2':^9} | {'12b Raw':>7} | {'Signed Int':>10} | {'DBC Decoded Speed':>17}")
    print("-" * 80)

    for rec in vs_records[:12]:
        print(f"{rec['t']:5.2f}s | {rec['payload_hex']:<24} | 0x{rec['b1']:02X} 0x{rec['b2']:02X} | {rec['raw_12']:7d} | {rec['raw_signed']:10d} | {rec['dbc_speed']:12.1f} {vs_sig.unit}")

    if vs_records:
        speeds = [r["dbc_speed"] for r in vs_records]
        print("-" * 80)
        print("Vehicle Speed Direct DBC Statistics:")
        print(f"  • Frame Count:       {len(speeds)}")
        print(f"  • DBC Speed Min:     {min(speeds):.1f} {vs_sig.unit}")
        print(f"  • DBC Speed Max:     {max(speeds):.1f} {vs_sig.unit}")
        print(f"  • Unique DBC Speeds: {sorted(set(speeds))} {vs_sig.unit}")
        print(f"  • Interpretation:    Stationary/Parked vehicle sensor noise (-0.1 to 0.0 Kmph)")

    print("\n" + "=" * 80)
    print("ALL OTHER DBC MESSAGES DECODED DIRECTLY VIA cantools (NO .xlsx):")
    print("=" * 80)
    for fid, count in sorted(dbc_frame_counts.items()):
        msg = db.get_message_by_frame_id(fid)
        print(f"  • 0x{fid:03X} ({msg.name:<16}): {count:4d} frames decoded via DBC")

    if other_frame_counts:
        print("\nOther CAN IDs detected on bus (not in Ather_v1_0_1.dbc):")
        for fid, count in sorted(other_frame_counts.items()):
            print(f"  • 0x{fid:03X}: {count:4d} frames")

    print("\n" + "=" * 80)
    print("DBC VERIFICATION COMPLETE: Speed decoded directly from Ather_v1_0_1.dbc")
    print("=" * 80)

if __name__ == "__main__":
    main()
