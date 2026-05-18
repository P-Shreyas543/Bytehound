"""Bytehound performance harness — measures the headless RX pipeline.

Runs the parser -> decoder -> decoded-logger pipeline against a synthetic byte
stream representing a real session shape (multiple frames, mixed signal
counts). Reports throughput, per-stage latency percentiles, RSS growth, and GC
pause time. Designed to run on a developer laptop without a serial device.

Usage
-----
    python scripts\\perf_harness.py                 # default 30s, 500 Hz
    python scripts\\perf_harness.py --rate 1000     # 1 kHz
    python scripts\\perf_harness.py --duration 10 --no-logger
    python scripts\\perf_harness.py --json out.json # machine-readable

The output is also written to stdout in a human-readable table.

Notes
-----
* This harness deliberately exercises only the non-Qt half of the pipeline.
  flush_ui / plot redraw require a running QApplication and are best measured
  via the live app + a faked /dev/null serial port. The CPU we see here IS
  the CPU the worker thread (and the slot that decodes packets) would burn
  in the real app under the same RX rate, so it's a load-bearing proxy.
* Latency percentiles are reported as microseconds per packet.
"""

from __future__ import annotations

import argparse
import gc
import json
import statistics
import sys
import tempfile
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional

# Make the project root importable when run directly.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.decoder.config_loader import load_config
from app.decoder.frame_decoder import decode_frame
from app.protocol.packet_builder import build_packet
from app.protocol.packet_parser import create_parser
from app.serial_logging.decoded_logger import DecodedLogger
from app.serial_logging.raw_logger import RawLogger

try:
    import psutil  # type: ignore
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


# ---------------------------------------------------------------------------
# Scenario builder — multiple frames with mixed signal shapes
# ---------------------------------------------------------------------------

CANONICAL_CONFIG = ROOT / "tests" / "fixtures" / "canonical_config"


def _build_stream(config, n_packets: int) -> bytes:
    """Build a fully-framed byte stream cycling through every configured frame.

    Mimics a real device's RX pattern: each frame in the config is emitted in
    round-robin order so the decoder hits every signal/bitfield/enum branch.
    The payload bytes are deterministic — we don't care about engineering
    correctness here, only consistent decode work.
    """
    frame_ids = list(config.signals_by_frame.keys())
    if not frame_ids:
        raise RuntimeError("config has no frames; cannot build stream")

    bufs: List[bytes] = []
    for i in range(n_packets):
        fid = frame_ids[i % len(frame_ids)]
        specs = config.signals_by_frame[fid]
        if specs:
            payload_len = max(s.end_byte for s in specs)
        else:
            payload_len = 0
        payload = bytes((i + j) & 0xFF for j in range(payload_len))
        bufs.append(build_packet(config.protocol, fid, payload))
    return b"".join(bufs)


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------

@dataclass
class StageStats:
    label: str
    n: int
    total_s: float
    samples_us: List[float] = field(default_factory=list)

    def summary(self) -> dict:
        if not self.samples_us:
            return {"label": self.label, "n": self.n, "total_s": round(self.total_s, 4)}
        s = sorted(self.samples_us)
        return {
            "label": self.label,
            "n": self.n,
            "total_s": round(self.total_s, 4),
            "throughput_per_s": round(self.n / self.total_s, 1) if self.total_s > 0 else None,
            "mean_us": round(statistics.fmean(s), 2),
            "p50_us": round(s[len(s) // 2], 2),
            "p95_us": round(s[int(len(s) * 0.95)], 2),
            "p99_us": round(s[int(len(s) * 0.99)], 2),
            "max_us": round(s[-1], 2),
        }


@dataclass
class RunReport:
    rate_hz: int
    duration_s: float
    packets_planned: int
    packets_processed: int
    decoded_logger_enabled: bool
    raw_logger_enabled: bool
    rss_start_mb: Optional[float]
    rss_end_mb: Optional[float]
    gc_count_delta: List[int]
    stages: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _rss_mb() -> Optional[float]:
    if not _HAS_PSUTIL:
        return None
    return psutil.Process().memory_info().rss / (1024 * 1024)


def run(
    rate_hz: int,
    duration_s: float,
    *,
    use_decoded_logger: bool,
    use_raw_logger: bool,
    sample_every: int = 10,
) -> RunReport:
    """Run the headless pipeline at *rate_hz* for *duration_s* seconds.

    sample_every controls how often per-stage latency is recorded. At 1 kHz a
    full per-packet sample list would hold 30k floats — keep it sparse to
    avoid the measurement itself thrashing the GC.
    """
    config = load_config(CANONICAL_CONFIG)
    n_packets = int(rate_hz * duration_s)

    # Pre-build the byte stream so the inner loop only times the work under
    # study (parse + decode + log). This isolates the measurement from the
    # builder's contribution.
    stream = _build_stream(config, n_packets)

    # The parser is fed in chunks sized like the real worker would (in_waiting
    # bytes ~ a few packets at a time). Picking 4 packets per chunk keeps the
    # parser exercised across the chunk-boundary code paths.
    bytes_per_packet = len(stream) // n_packets
    chunk_size = max(bytes_per_packet * 4, 1)

    parser = create_parser(config.protocol)

    decoded_logger = None
    raw_logger = None
    tmpdir: Optional[tempfile.TemporaryDirectory] = None
    if use_decoded_logger or use_raw_logger:
        tmpdir = tempfile.TemporaryDirectory(prefix="bh_perf_")
        if use_decoded_logger:
            decoded_logger = DecodedLogger(Path(tmpdir.name) / "decoded.xlsx", config)
            decoded_logger.open()
        if use_raw_logger:
            raw_logger = RawLogger(Path(tmpdir.name) / "raw.csv")
            raw_logger.open()

    parse_stats = StageStats(label="parse", n=0, total_s=0.0)
    decode_stats = StageStats(label="decode", n=0, total_s=0.0)
    log_stats = StageStats(label="logger", n=0, total_s=0.0)

    rss_start = _rss_mb()
    gc_start = list(gc.get_count())

    # Pace at the requested rate by tracking when each chunk was meant to be
    # produced. If we fall behind, we keep going (no sleeping) so the report
    # captures the actual throughput ceiling.
    offset = 0
    iteration = 0
    packet_idx = 0
    elapsed_ms = 0
    start_perf = time.perf_counter()
    next_chunk_at = start_perf
    chunk_interval = chunk_size / max(bytes_per_packet, 1) / rate_hz

    overall_start = time.perf_counter()
    while offset < len(stream):
        chunk = stream[offset : offset + chunk_size]
        offset += chunk_size

        # ── parse stage ───────────────────────────────────────────────
        t0 = time.perf_counter()
        parser.feed(chunk)
        packets = parser.extract_all()
        t1 = time.perf_counter()
        parse_stats.n += len(packets)
        parse_stats.total_s += t1 - t0
        if packets and iteration % sample_every == 0:
            parse_stats.samples_us.append((t1 - t0) * 1e6 / max(len(packets), 1))

        # ── decode stage ──────────────────────────────────────────────
        for p in packets:
            if not p.ok:
                continue
            t2 = time.perf_counter()
            decoded = decode_frame(config, p.frame_id, p.payload)
            t3 = time.perf_counter()
            decode_stats.n += 1
            decode_stats.total_s += t3 - t2
            if iteration % sample_every == 0:
                decode_stats.samples_us.append((t3 - t2) * 1e6)

            # ── logger stage ──────────────────────────────────────────
            if decoded_logger is not None or raw_logger is not None:
                t4 = time.perf_counter()
                if raw_logger is not None:
                    raw_logger.log("RX", p.raw)
                if decoded_logger is not None:
                    decoded_logger.log_frame(decoded, elapsed_ms)
                t5 = time.perf_counter()
                log_stats.n += 1
                log_stats.total_s += t5 - t4
                if iteration % sample_every == 0:
                    log_stats.samples_us.append((t5 - t4) * 1e6)

            packet_idx += 1
            elapsed_ms = int((time.perf_counter() - overall_start) * 1000)

        iteration += 1

        # Pace: if running ahead of schedule, idle until the next chunk slot.
        next_chunk_at += chunk_interval
        now = time.perf_counter()
        if now < next_chunk_at:
            # Use a tight spin only for sub-millisecond waits — sleep on longer
            # ones so we don't burn CPU pretending to be a 1 kHz device.
            wait = next_chunk_at - now
            if wait > 0.001:
                time.sleep(wait)

    overall_end = time.perf_counter()
    gc_end = list(gc.get_count())

    if decoded_logger is not None:
        decoded_logger.close()
    if raw_logger is not None:
        raw_logger.close()
    if tmpdir is not None:
        try:
            tmpdir.cleanup()
        except Exception:
            pass

    rss_end = _rss_mb()

    report = RunReport(
        rate_hz=rate_hz,
        duration_s=round(overall_end - overall_start, 3),
        packets_planned=n_packets,
        packets_processed=packet_idx,
        decoded_logger_enabled=use_decoded_logger,
        raw_logger_enabled=use_raw_logger,
        rss_start_mb=round(rss_start, 1) if rss_start is not None else None,
        rss_end_mb=round(rss_end, 1) if rss_end is not None else None,
        gc_count_delta=[gc_end[i] - gc_start[i] for i in range(3)],
        stages=[parse_stats.summary(), decode_stats.summary(), log_stats.summary()],
    )
    return report


# ---------------------------------------------------------------------------
# Pretty-printing
# ---------------------------------------------------------------------------

def _print_report(report: RunReport) -> None:
    print("=" * 72)
    print(f"  Rate: {report.rate_hz} Hz   Duration: {report.duration_s} s")
    print(
        f"  Packets: {report.packets_processed}/{report.packets_planned}"
        f"  Loggers: decoded={report.decoded_logger_enabled} "
        f"raw={report.raw_logger_enabled}"
    )
    if report.rss_start_mb is not None:
        delta = report.rss_end_mb - report.rss_start_mb if report.rss_end_mb else 0.0
        print(
            f"  RSS: {report.rss_start_mb:.1f} MB -> {report.rss_end_mb:.1f} MB"
            f"  (delta {delta:+.1f} MB)"
        )
    print(f"  GC count delta: {report.gc_count_delta}")
    print("-" * 72)
    print(f"  {'stage':<10} {'n':>8} {'ops/s':>10} {'mean us':>10} {'p95 us':>10} {'p99 us':>10}")
    for stage in report.stages:
        if "throughput_per_s" not in stage:
            print(f"  {stage['label']:<10} {stage['n']:>8} {'-':>10} {'-':>10} {'-':>10} {'-':>10}")
            continue
        print(
            f"  {stage['label']:<10} {stage['n']:>8} {stage['throughput_per_s']:>10.0f}"
            f" {stage['mean_us']:>10.2f} {stage['p95_us']:>10.2f} {stage['p99_us']:>10.2f}"
        )
    print("=" * 72)


def main() -> int:
    ap = argparse.ArgumentParser(description="Bytehound headless perf harness")
    ap.add_argument("--rate", type=int, default=500, help="packets per second (default 500)")
    ap.add_argument("--duration", type=float, default=10.0, help="seconds (default 10)")
    ap.add_argument(
        "--scenarios",
        type=str,
        default=None,
        help="comma-separated list of rates to sweep (overrides --rate)",
    )
    ap.add_argument("--no-decoded-logger", action="store_true")
    ap.add_argument("--no-raw-logger", action="store_true")
    ap.add_argument("--json", type=Path, help="write machine-readable report to this path")
    args = ap.parse_args()

    rates = (
        [int(x) for x in args.scenarios.split(",")]
        if args.scenarios
        else [args.rate]
    )

    reports: List[RunReport] = []
    for rate in rates:
        report = run(
            rate_hz=rate,
            duration_s=args.duration,
            use_decoded_logger=not args.no_decoded_logger,
            use_raw_logger=not args.no_raw_logger,
        )
        _print_report(report)
        reports.append(report)

    if args.json:
        args.json.write_text(json.dumps([r.to_dict() for r in reports], indent=2))
        print(f"\nWrote {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
