"""TCP / UDP hardware-in-the-loop tests against a second machine.

The device side is ``tools/hil/net_device.py`` running on a Raspberry Pi (or
any host with Python 3), started over SSH for each test; the application
side is the real PollingWorker, parser and raw capture (``run_hil.AppLink``).
Every test compares the device's own counters with what the application saw.

The SSH password is never written anywhere: it is read from the
environment variable ``BH_PI_PASS`` and handed to OpenSSH through
``SSH_ASKPASS`` (a helper that only echoes the variable).

  set BH_PI_PASS=...   (or export in bash)
  python tools/hil/net_hil.py --pi 169.254.20.2 --pc 169.254.205.103
  python tools/hil/net_hil.py --pi 192.168.1.94 --pc 192.168.1.34 --only tcp_stream

Exit status = number of failed tests; JSON report in artifacts/net_hil/.
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.decoder.config_loader import load_config  # noqa: E402
from app.protocol.packet_builder import build_packet  # noqa: E402
from app.serial_io.serial_worker import PollingWorker, SerialSettings  # noqa: E402
from tools.hil import nucleo as hw  # noqa: E402
from tools.hil.run_hil import TELEMETRY, Result, pump  # noqa: E402

DEVICE = ROOT / "tools" / "hil" / "net_device.py"
REMOTE = "/tmp/bh_net_device.py"


class Pi:
    """Runs commands on the device machine over OpenSSH."""

    def __init__(self, host: str, user: str, scratch: Path) -> None:
        self.target = f"{user}@{host}"
        askpass = scratch / "askpass.cmd" if sys.platform == "win32" else scratch / "askpass.sh"
        if sys.platform == "win32":
            askpass.write_text("@echo off\r\necho %BH_PI_PASS%\r\n", encoding="ascii")
        else:
            askpass.write_text('#!/bin/sh\necho "$BH_PI_PASS"\n', encoding="ascii")
            askpass.chmod(0o700)
        self.env = dict(os.environ, SSH_ASKPASS=str(askpass), SSH_ASKPASS_REQUIRE="force", DISPLAY=":0")
        if not self.env.get("BH_PI_PASS"):
            raise SystemExit("set BH_PI_PASS to the device's SSH password")
        self.opts = ["-o", f"UserKnownHostsFile={scratch / 'known_hosts'}", "-o", "StrictHostKeyChecking=accept-new",
                     "-o", "ConnectTimeout=10", "-o", "LogLevel=ERROR"]

    def run(self, cmd: str, timeout: float = 60) -> str:
        p = subprocess.run(["ssh", *self.opts, self.target, cmd], env=self.env, capture_output=True,
                           text=True, timeout=timeout)
        return p.stdout

    def put(self, local: Path, remote: str) -> None:
        subprocess.run(["scp", *self.opts, str(local), f"{self.target}:{remote}"], env=self.env,
                       capture_output=True, check=True, timeout=60)

    def device(self, args: str) -> None:
        self.run(f"rm -f /tmp/bh_stats.json; nohup python3 {REMOTE} {args} --stats /tmp/bh_stats.json "
                 ">/tmp/bh_dev.log 2>&1 &")

    def stats(self, wait: float = 30.0) -> dict:
        end = time.monotonic() + wait
        while time.monotonic() < end:
            out = self.run("cat /tmp/bh_stats.json 2>/dev/null")
            if out.strip():
                return json.loads(out)
            time.sleep(0.5)
        raise TimeoutError("device wrote no stats: " + self.run("cat /tmp/bh_dev.log"))


class Link:
    """PollingWorker over TCP/UDP with counters."""

    def __init__(self, config, settings: SerialSettings) -> None:
        self.worker = PollingWorker(settings, config.protocol, [], decode_config=config)
        self.good = {}
        self.good_bytes = self.rejected = self.rejected_bytes = 0
        self.seq = []
        self.lost = 0
        self.errors = []
        self.worker.packets_received.connect(self._on)
        self.worker.connection_lost.connect(self._on_lost)
        self.worker.error_occurred.connect(self.errors.append)

    def _on_lost(self) -> None:
        self.lost += 1

    def _on(self, items) -> None:
        for p, _d, _t in items:
            if not p.ok:
                self.rejected += 1
                self.rejected_bytes += len(p.raw)
                continue
            if p.frame_id in TELEMETRY:
                self.good[p.frame_id] = self.good.get(p.frame_id, 0) + 1
                self.good_bytes += len(p.raw)
                if p.frame_id == 0x4000:
                    self.seq.append(struct.unpack_from("<I", p.payload)[0])

    def open(self) -> "Link":
        self.worker.open()
        pump(0.2)
        return self

    def close(self) -> dict:
        snap = self.worker.integrity_snapshot()
        self.worker.close()
        pump(0.1)
        return snap


def _account(r: Result, link: Link, snap: dict, dev: dict, *, exact: bool = True) -> None:
    for fid in TELEMETRY:
        got, sent = link.good.get(fid, 0), dev["frames"][f"0x{fid:04X}"]
        r.check(got == sent if exact else got <= sent, f"0x{fid:04X} frames app {got} {'==' if exact else '<='} device {sent}")
    seq = link.seq
    gaps = sum(1 for a, b in zip(seq, seq[1:], strict=False) if b != a + 1)
    r.check(gaps == 0 if exact else all(b > a for a, b in zip(seq, seq[1:], strict=False)),
            f"0x4000 sequence {'contiguous' if exact else 'increasing'} ({len(seq)} frames, {gaps} gaps)")
    r.check(link.rejected == 0 and snap["discarded_bytes"] == 0,
            f"no rejected frames / discarded bytes ({link.rejected}, {snap['discarded_bytes']})")
    if exact:
        total = link.good_bytes + link.rejected_bytes + snap["discarded_bytes"]
        r.check(total == dev["bytes_sent"], f"bytes app {total} == device {dev['bytes_sent']}")
    r.data.update(device=dev, app_frames={f"0x{k:04X}": v for k, v in link.good.items()},
                  integrity={k: v for k, v in snap.items() if k != "driver_errors"})


def t_tcp_stream(a, config, pi: Pi, rate: float) -> Result:
    r = Result(f"tcp_stream_{int(rate)}")
    pi.device(f"tcp --port {a.port} --rate {rate} --seconds {a.seconds}")
    time.sleep(1.0)
    link = Link(config, SerialSettings(port=a.pi, connection_type="tcp", host=a.pi, port_num=a.port))
    raw = Path(tempfile.mkdtemp(prefix="bh_net_")) / "wire.bhraw"
    link.worker.start_raw_capture(raw, {})     # before connecting: the device streams at once
    link.open()
    pump(a.seconds + 2.5, lambda: link.lost > 0)
    pump(0.5)
    dev = pi.stats()
    link.worker.stop_raw_capture()
    snap = link.close()
    _account(r, link, snap, dev)
    from app.serial_logging.raw_capture import iter_raw_capture
    rx = sum(len(d) for k, _t, d in iter_raw_capture(raw) if k == 0)
    r.check(rx == snap["parser_bytes_in"], f"raw capture {rx} == parser bytes in {snap['parser_bytes_in']}")
    r.data["rate_cycles_per_s"] = rate
    return r


def t_tcp_peer_close(a, config, pi: Pi) -> Result:
    """F15: the device sends exactly N cycles and closes; the application
    must deliver all N before it reports the connection lost."""
    r = Result("tcp_peer_close")
    n = 5000
    pi.device(f"tcp --port {a.port} --rate 5000 --seconds 30 --close-after-cycles {n}")
    time.sleep(1.0)
    link = Link(config, SerialSettings(port=a.pi, connection_type="tcp", host=a.pi, port_num=a.port)).open()
    r.check(pump(20.0, lambda: link.lost > 0), "connection_lost reported after the peer closed")
    pump(0.5)
    dev = pi.stats()
    snap = link.close()
    r.check(dev["cycles"] == n, f"device sent {dev['cycles']} cycles")
    _account(r, link, snap, dev)
    return r


def t_tcp_reconnect(a, config, pi: Pi) -> Result:
    """The device drops the connection mid-stream; a new connection (as the
    application's auto-reconnect makes) continues the sequence."""
    r = Result("tcp_drop_reconnect")
    pi.device(f"tcp --port {a.port} --rate 2000 --seconds 8 --drop-after 3")
    time.sleep(1.0)
    s = SerialSettings(port=a.pi, connection_type="tcp", host=a.pi, port_num=a.port)
    first = Link(config, s).open()
    r.check(pump(10.0, lambda: first.lost > 0), "first connection: connection_lost on drop")
    pump(0.3)
    snap1 = first.close()
    second = Link(config, s).open()
    pump(12.0, lambda: second.lost > 0)
    pump(0.5)
    dev = pi.stats()
    snap2 = second.close()
    seq = first.seq + second.seq
    r.check(dev["connections"] == 2 and dev["drops"] == 1, f"device saw {dev['connections']} connections")
    r.check(seq == list(range(dev["next_seq"])),
            f"sequence 0..{dev['next_seq'] - 1} complete across the reconnect ({len(first.seq)} + {len(second.seq)})")
    r.check(first.rejected + second.rejected == 0 and snap1["discarded_bytes"] + snap2["discarded_bytes"] == 0,
            "no torn frames at the drop")
    r.data.update(device=dev, first=len(first.seq), second=len(second.seq))
    return r


def _commands(config, n: int) -> list:
    return [build_packet(config.protocol, 0x1000 + (i % 3) * 0x1000, bytes([i & 0xFF]) * (2 + i % 16))
            for i in range(n)]


def t_tx(a, config, pi: Pi, mode: str) -> Result:
    """Application → device commands while the device streams: every
    command arrives complete with a valid CRC (F13 partial sends)."""
    r = Result(f"{mode}_tx_commands")
    n = 300
    if mode == "tcp":
        pi.device(f"tcp --port {a.port} --rate 1000 --seconds 8")
        s = SerialSettings(port=a.pi, connection_type="tcp", host=a.pi, port_num=a.port)
    else:
        pi.device(f"udp --port {a.udp_port} --pc {a.pc} --pc-port {a.udp_local} --rate 1000 --seconds 8 --start-delay 0.5")
        s = SerialSettings(port=a.pi, connection_type="udp", host=a.pi, port_num=a.udp_port, local_port=a.udp_local)
    time.sleep(1.0)
    link = Link(config, s)
    warnings = []
    link.worker.warning_occurred.connect(warnings.append)
    # Commands are spaced by the poll TX-gap floor (100 ms by default, i.e.
    # at most 10/s, queue of 256, excess dropped with a warning). Test
    # integrity at speed with a 10 ms gap; the default is documented.
    link.worker.set_pipelining(False, gap_ms=10)
    link.open()
    cmds = _commands(config, n)
    for c in cmds:
        link.worker.enqueue_priority_tx(c)
        pump(0.012)
    pump(11.0, lambda: link.lost > 0)
    dev = pi.stats()
    link.close()
    r.check(not any("queue full" in w for w in warnings), f"no TX queue overflow {warnings[:1]}")
    r.check(dev["rx_frames_ok"] == n, f"device received {dev['rx_frames_ok']} of {n} commands intact")
    r.check(dev["rx_crc_errors"] == 0, f"device CRC errors {dev['rx_crc_errors']}")
    r.check(dev["rx_bytes"] == sum(len(c) for c in cmds), f"device bytes {dev['rx_bytes']} == {sum(len(c) for c in cmds)}")
    r.data["device"] = dev
    return r


def t_udp_stream(a, config, pi: Pi, rate: float, datagram_bytes: int = 0) -> Result:
    name = f"udp_stream_{int(rate)}" + (f"_dgram{datagram_bytes}" if datagram_bytes else "")
    r = Result(name)
    pi.device(f"udp --port {a.udp_port} --pc {a.pc} --pc-port {a.udp_local} --rate {rate} "
              f"--seconds {a.seconds} --start-delay 1.5 --datagram-bytes {datagram_bytes}")
    link = Link(config, SerialSettings(port=a.pi, connection_type="udp", host=a.pi, port_num=a.udp_port,
                                       local_port=a.udp_local)).open()
    pump(a.seconds + 4.5)
    dev = pi.stats()
    snap = link.close()
    got = link.good.get(0x4000, 0)
    lost = dev["frames"]["0x4000"] - got
    r.data.update(lost_cycles=lost, loss_fraction=round(lost / max(1, dev["frames"]["0x4000"]), 6),
                  datagrams=dev.get("datagrams"))
    r.check(got > 0, f"UDP datagrams reach the application ({got} cycles)")
    # UDP may lose datagrams on a real network; on this direct link at
    # this rate none are expected, and any loss must show as a gap.
    _account(r, link, snap, dev, exact=a.udp_exact)
    r.checks.append(f"info UDP: {dev.get('datagrams')} datagrams, {lost} cycles lost")
    return r


def t_udp_unreachable(a, config, pi: Pi) -> Result:
    """F14: the application sends before anything listens on the device
    (ICMP port unreachable → WSAECONNRESET on Windows). The session must go
    on and receive once the device starts."""
    r = Result("udp_port_unreachable")
    pi.device(f"udp --port {a.udp_port} --pc {a.pc} --pc-port {a.udp_local} --rate 500 --seconds 4 --start-delay 3")
    link = Link(config, SerialSettings(port=a.pi, connection_type="udp", host=a.pi, port_num=a.udp_port + 7,
                                       local_port=a.udp_local)).open()
    # Port +7 has no listener: these sends draw ICMP unreachable replies.
    for _ in range(5):
        link.worker.enqueue_priority_tx(build_packet(config.protocol, 0x1000, b""))
        pump(0.2)
    r.check(link.lost == 0, "no connection_lost after ICMP port unreachable")
    link.close()
    link2 = Link(config, SerialSettings(port=a.pi, connection_type="udp", host=a.pi, port_num=a.udp_port,
                                        local_port=a.udp_local)).open()
    for _ in range(3):
        link2.worker.enqueue_priority_tx(build_packet(config.protocol, 0x1000, b""))
        pump(0.2)
    pump(8.0)
    dev = pi.stats()
    link2.close()
    r.check(link2.good.get(0x4000, 0) == dev["frames"]["0x4000"],
            f"frames received after the unreachable period: {link2.good.get(0x4000, 0)} of {dev['frames']['0x4000']}")
    return r


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pi", required=True, help="device machine address (IPv4)")
    ap.add_argument("--pc", required=True, help="this PC's address as seen by the device (for UDP)")
    ap.add_argument("--user", default="shreyas")
    ap.add_argument("--port", type=int, default=9100)
    ap.add_argument("--udp-port", type=int, default=9101)
    ap.add_argument("--udp-local", type=int, default=9102)
    ap.add_argument("--seconds", type=float, default=8.0)
    ap.add_argument("--rates", type=float, nargs="*", default=[1000.0, 5000.0])
    ap.add_argument("--udp-exact", action="store_true", default=True)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--report", type=Path, default=ROOT / "artifacts" / "net_hil")
    a = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication(sys.argv)

    scratch = Path(tempfile.mkdtemp(prefix="bh_net_ssh_"))
    pi = Pi(a.pi, a.user, scratch)
    pi.put(DEVICE, REMOTE)
    cfg_dir = hw.hil_config_dir(scratch / "config")
    config = load_config(cfg_dir)
    tests = {}
    for rate in a.rates:
        tests[f"tcp_stream_{int(rate)}"] = lambda rate=rate: t_tcp_stream(a, config, pi, rate)
    tests["tcp_peer_close"] = lambda: t_tcp_peer_close(a, config, pi)
    tests["tcp_drop_reconnect"] = lambda: t_tcp_reconnect(a, config, pi)
    tests["tcp_tx_commands"] = lambda: t_tx(a, config, pi, "tcp")
    for rate in a.rates:
        tests[f"udp_stream_{int(rate)}"] = lambda rate=rate: t_udp_stream(a, config, pi, rate)
    tests["udp_stream_large_datagrams"] = lambda: t_udp_stream(a, config, pi, 2000, datagram_bytes=60000)
    tests["udp_tx_commands"] = lambda: t_tx(a, config, pi, "udp")
    tests["udp_port_unreachable"] = lambda: t_udp_unreachable(a, config, pi)
    names = [n for n in tests if not a.only or any(n.startswith(o) for o in a.only)]
    print(f"network HIL: app {a.pc} <-> device {a.pi}: {', '.join(names)}")
    results = []
    for name in names:
        t0 = time.monotonic()
        try:
            res = tests[name]()
        except Exception as exc:
            import traceback
            res = Result(name)
            res.check(False, f"raised {type(exc).__name__}: {exc}")
            res.data["traceback"] = traceback.format_exc()
        res.seconds = round(time.monotonic() - t0, 1)
        results.append(res)
        print(f"\n[{'PASS' if res.ok else 'FAIL'}] {name} ({res.seconds}s)")
        for c in res.checks:
            print("   " + c)
        time.sleep(0.5)
    pi.run(f"rm -f {REMOTE} /tmp/bh_stats.json /tmp/bh_dev.log")
    failed = [r.name for r in results if not r.ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed" + (f"; failed: {failed}" if failed else ""))
    a.report.mkdir(parents=True, exist_ok=True)
    path = a.report / f"net_{datetime.now():%Y%m%d_%H%M%S}.json"
    path.write_text(json.dumps({"pi": a.pi, "pc": a.pc, "results": [vars(r) for r in results]}, indent=2,
                               default=str), encoding="utf-8")
    print(f"report: {path}")
    return len(failed)


if __name__ == "__main__":
    sys.exit(main())
