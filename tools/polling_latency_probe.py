"""Probe Bytehound poll latency on a real serial port.

Example:
    python tools/polling_latency_probe.py --port COM13 --config MultiCell-BMS-OverAllFrame.xlsx

The probe uses the same config loader, packet builder, and parser as the app,
then sends one poll at a time. That makes it useful for checking whether the
hardware itself is answering reliably before enabling faster pipelined polling.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import serial

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.decoder.config_loader import load_config
from app.decoder.types import PollingScheduleSpec, ProtocolConfig
from app.protocol.packet_builder import build_packet
from app.protocol.packet_parser import ParsedPacket, create_parser


@dataclass
class ProbeResult:
    timeout_ms: int
    target_id: int
    attempt: int
    ok: bool
    latency_ms: float | None
    rx_frame_id: int | None
    rx_hex: str
    error: str
    stale_before_tx: int


@dataclass
class WireEvent:
    elapsed_ms: float
    direction: str
    active_target: int | None
    frame_id: int | None
    status: str
    hex: str


def _hex(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def _read_matching_response(
    ser: serial.Serial,
    parser,
    target_id: int,
    protocol: ProtocolConfig,
    timeout_ms: int,
    events: list[WireEvent] | None = None,
    trace_start: float | None = None,
) -> tuple[ParsedPacket | None, list[ParsedPacket], float | None]:
    start = time.monotonic()
    deadline = start + timeout_ms / 1000.0
    seen: list[ParsedPacket] = []
    while time.monotonic() < deadline:
        waiting = ser.in_waiting
        if waiting:
            parser.feed(ser.read(waiting))
            packets = parser.extract_all()
            seen.extend(packets)
            for packet in packets:
                if events is not None and trace_start is not None:
                    events.append(
                        WireEvent(
                            elapsed_ms=(time.monotonic() - trace_start) * 1000.0,
                            direction="RX",
                            active_target=target_id,
                            frame_id=packet.frame_id,
                            status="OK" if packet.ok else packet.error or "ERR",
                            hex=_hex(packet.raw),
                        )
                    )
                if packet.ok and packet.frame_id == target_id:
                    return packet, seen, (time.monotonic() - start) * 1000.0
        time.sleep(0.002)
    return None, seen, None


def _drain_stale(ser: serial.Serial, parser, drain_ms: int) -> list[ParsedPacket]:
    deadline = time.monotonic() + drain_ms / 1000.0
    stale: list[ParsedPacket] = []
    while time.monotonic() < deadline:
        waiting = ser.in_waiting
        if waiting:
            parser.feed(ser.read(waiting))
            stale.extend(parser.extract_all())
        time.sleep(0.002)
    return stale


def _poll_once(
    ser: serial.Serial,
    parser,
    protocol: ProtocolConfig,
    sched: PollingScheduleSpec,
    timeout_ms: int,
    attempt: int,
    gap_ms: int,
    drain_before_tx_ms: int,
    events: list[WireEvent] | None = None,
    trace_start: float | None = None,
) -> ProbeResult:
    if gap_ms > 0:
        time.sleep(gap_ms / 1000.0)
    stale = _drain_stale(ser, parser, drain_before_tx_ms) if drain_before_tx_ms > 0 else []
    req = build_packet(protocol, sched.target_id, b"")
    ser.write(req)
    ser.flush()
    if events is not None and trace_start is not None:
        events.append(
            WireEvent(
                elapsed_ms=(time.monotonic() - trace_start) * 1000.0,
                direction="TX",
                active_target=sched.target_id,
                frame_id=sched.target_id,
                status="",
                hex=_hex(req),
            )
        )
    packet, seen, latency_ms = _read_matching_response(
        ser, parser, sched.target_id, protocol, timeout_ms, events, trace_start
    )
    if packet is not None:
        return ProbeResult(
            timeout_ms=timeout_ms,
            target_id=sched.target_id,
            attempt=attempt,
            ok=True,
            latency_ms=latency_ms,
            rx_frame_id=packet.frame_id,
            rx_hex=_hex(packet.raw),
            error="",
            stale_before_tx=len(stale),
        )
    last = seen[-1] if seen else None
    return ProbeResult(
        timeout_ms=timeout_ms,
        target_id=sched.target_id,
        attempt=attempt,
        ok=False,
        latency_ms=None,
        rx_frame_id=last.frame_id if last else None,
        rx_hex=_hex(last.raw) if last else "",
        error=last.error if last and last.error else "timeout/no matching response",
        stale_before_tx=len(stale),
    )


def _summary(results: list[ProbeResult]) -> str:
    lines: list[str] = []
    by_timeout = sorted({r.timeout_ms for r in results})
    for timeout_ms in by_timeout:
        group = [r for r in results if r.timeout_ms == timeout_ms]
        ok = [r for r in group if r.ok and r.latency_ms is not None]
        success = len(ok)
        total = len(group)
        if ok:
            latencies = [r.latency_ms for r in ok if r.latency_ms is not None]
            median = statistics.median(latencies)
            p95 = sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)]
            lines.append(
                f"{timeout_ms:4d} ms timeout: {success:2d}/{total:2d} OK, "
                f"median {median:6.1f} ms, p95 {p95:6.1f} ms, max {max(latencies):6.1f} ms"
            )
        else:
            lines.append(f"{timeout_ms:4d} ms timeout:  0/{total:2d} OK")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Measure Bytehound polling latency on real hardware.")
    ap.add_argument("--port", default="COM13")
    ap.add_argument("--config", default="MultiCell-BMS-OverAllFrame.xlsx")
    ap.add_argument("--timeouts", default="250,500,750,1000")
    ap.add_argument("--cycles", type=int, default=1)
    ap.add_argument("--gap-ms", type=int, default=25, help="Delay before each TX in sequential probing.")
    ap.add_argument("--drain-ms", type=int, default=250, help="Input drain window before each timeout group.")
    ap.add_argument(
        "--drain-before-tx-ms",
        type=int,
        default=50,
        help="Drain stale RX for this long before every poll request.",
    )
    ap.add_argument("--limit-targets", type=int, default=0, help="Use only the first N enabled targets.")
    ap.add_argument("--csv", default="")
    ap.add_argument("--events-csv", default="", help="Write ordered TX/RX trace events to CSV.")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    schedules = [s for s in cfg.polling_schedules if s.enabled]
    if args.limit_targets > 0:
        schedules = schedules[: args.limit_targets]
    if not schedules:
        print("No enabled polling targets in config.", file=sys.stderr)
        return 2

    timeouts = [int(part.strip()) for part in args.timeouts.split(",") if part.strip()]
    parser = create_parser(cfg.protocol)
    results: list[ProbeResult] = []
    events: list[WireEvent] = []
    trace_start = time.monotonic()

    with serial.Serial(
        port=args.port,
        baudrate=cfg.serial_defaults.baud_rate,
        bytesize=cfg.serial_defaults.data_bits,
        stopbits=cfg.serial_defaults.stop_bits,
        parity=cfg.serial_defaults.parity,
        timeout=0,
        write_timeout=max(timeouts) / 1000.0,
    ) as ser:
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        print(
            f"Opened {args.port} at {cfg.serial_defaults.baud_rate} baud; "
            f"{len(schedules)} target(s), {args.cycles} cycle(s)."
        )
        for timeout_ms in timeouts:
            stale = _drain_stale(ser, parser, args.drain_ms)
            if stale:
                print(f"Drained {len(stale)} stale frame(s) before {timeout_ms} ms run.")
            for attempt in range(1, args.cycles + 1):
                for sched in schedules:
                    result = _poll_once(
                        ser,
                        parser,
                        cfg.protocol,
                        sched,
                        timeout_ms,
                        attempt,
                        args.gap_ms,
                        args.drain_before_tx_ms,
                        events if args.events_csv else None,
                        trace_start,
                    )
                    results.append(result)
                    status = "OK" if result.ok else "MISS"
                    latency = f"{result.latency_ms:.1f} ms" if result.latency_ms is not None else "-"
                    stale_note = f" stale={result.stale_before_tx}" if result.stale_before_tx else ""
                    print(
                        f"{timeout_ms:4d} ms  try {attempt:02d}  "
                        f"0x{sched.target_id:04X}  {status:4s}  {latency}{stale_note}"
                    )

    print("\nSummary:")
    print(_summary(results))

    if args.csv:
        out = Path(args.csv)
        with out.open("w", newline="", encoding="utf-8") as fp:
            writer = csv.DictWriter(fp, fieldnames=list(ProbeResult.__annotations__))
            writer.writeheader()
            for r in results:
                writer.writerow(r.__dict__)
        print(f"Wrote {out}")

    if args.events_csv:
        out = Path(args.events_csv)
        with out.open("w", newline="", encoding="utf-8") as fp:
            writer = csv.DictWriter(fp, fieldnames=list(WireEvent.__annotations__))
            writer.writeheader()
            for event in events:
                writer.writerow(event.__dict__)
        print(f"Wrote {out}")

    failures = [r for r in results if not r.ok]
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
