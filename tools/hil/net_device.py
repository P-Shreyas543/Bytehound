"""Network BMS simulator for TCP / UDP hardware-in-the-loop tests.

Runs on a second machine (a Raspberry Pi in the lab setup) with only the
Python standard library. Streams the bundled template protocol
(``AA 55 | id LE | len | payload | CRC16-Modbus LE | EE``): frames 0x1000,
0x2000, 0x3000 and the 0x4000 sequence counter (u32 seq, u32 ms), exactly as
the NUCLEO firmware does, and counts everything it sends and receives.

  python3 net_device.py tcp --port 9100 --rate 2000 --seconds 10 --stats s.json
  python3 net_device.py udp --port 9101 --pc 169.254.205.103 --pc-port 9102 ...

TCP: listens, serves one client at a time. ``--drop-after S`` closes the
connection after S seconds and waits for the client to reconnect (the
sequence continues). ``--close-after-cycles N`` sends exactly N cycles, then
closes (peer-close test). UDP: sends one datagram per tick to
``--pc:--pc-port`` from ``--port``; ``--datagram-bytes`` packs cycles into
datagrams of about that size. Both modes read what the client sends and
count the complete frames with a valid CRC (TX commands). The stats JSON is
written when the run ends.
"""

from __future__ import annotations

import argparse
import json
import select
import socket
import struct
import time


def _crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def frame(fid: int, payload: bytes) -> bytes:
    body = b"\xAA\x55" + struct.pack("<HB", fid, len(payload)) + payload
    return body + struct.pack("<H", _crc16_modbus(body)) + b"\xEE"


class Device:
    def __init__(self, start_seq: int = 0) -> None:
        self.seq = start_seq
        self.t0 = time.monotonic()
        self.frames = {"0x1000": 0, "0x2000": 0, "0x3000": 0, "0x4000": 0}
        self.bytes_sent = 0
        self.cycles = 0
        self.rx_buf = bytearray()
        self.rx_frames_ok = 0
        self.rx_crc_errors = 0
        self.rx_bytes = 0
        self.rx_ids = {}

    def cycle(self) -> bytes:
        n = self.cycles
        parts = [
            (0x1000, struct.pack("<HhBhB", 4800 + n % 200, n % 100 - 50, 70 + n % 10, 250, 0)),
            (0x2000, struct.pack("<8HH", *[3700 + (n + i) % 40 for i in range(8)], 5500)),
            (0x3000, bytes([n & 0xFF, n % 4])),
            (0x4000, struct.pack("<II", self.seq & 0xFFFFFFFF, int((time.monotonic() - self.t0) * 1000))),
        ]
        out = b"".join(frame(fid, p) for fid, p in parts)
        for fid, _ in parts:
            self.frames[f"0x{fid:04X}"] += 1
        self.seq += 1
        self.cycles += 1
        return out

    def received(self, data: bytes) -> None:
        self.rx_bytes += len(data)
        self.rx_buf += data
        while True:
            i = self.rx_buf.find(b"\xAA\x55")
            if i < 0:
                del self.rx_buf[:-1]
                return
            del self.rx_buf[:i]
            if len(self.rx_buf) < 5:
                return
            fid, length = struct.unpack_from("<HB", self.rx_buf, 2)
            total = 5 + length + 3
            if len(self.rx_buf) < total:
                return
            body = bytes(self.rx_buf[:5 + length])
            crc = struct.unpack_from("<H", self.rx_buf, 5 + length)[0]
            if crc == _crc16_modbus(body) and self.rx_buf[total - 1] == 0xEE:
                self.rx_frames_ok += 1
                key = f"0x{fid:04X}"
                self.rx_ids[key] = self.rx_ids.get(key, 0) + 1
                del self.rx_buf[:total]
            else:
                self.rx_crc_errors += 1
                del self.rx_buf[:1]

    def stats(self, **extra) -> dict:
        return {"cycles": self.cycles, "frames": self.frames, "bytes_sent": self.bytes_sent,
                "next_seq": self.seq, "rx_bytes": self.rx_bytes, "rx_frames_ok": self.rx_frames_ok,
                "rx_crc_errors": self.rx_crc_errors, "rx_ids": self.rx_ids, **extra}


def _due(t_start: float, rate: float, sent: int) -> int:
    return int((time.monotonic() - t_start) * rate) - sent


def run_tcp(a) -> dict:
    dev = Device(a.start_seq)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", a.port))
    srv.listen(1)
    srv.settimeout(a.accept_timeout)
    connections = 0
    drops = 0
    end_at = None
    while True:
        try:
            conn, _ = srv.accept()
        except socket.timeout:
            break
        connections += 1
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        t_start = time.monotonic()
        if end_at is None:
            end_at = t_start + a.seconds
        sent_here = 0
        dropped = False
        try:
            while time.monotonic() < end_at:
                if a.close_after_cycles and dev.cycles >= a.close_after_cycles:
                    break
                n = _due(t_start, a.rate, sent_here)
                if a.close_after_cycles:
                    n = min(n, a.close_after_cycles - dev.cycles)
                if n > 0:
                    blob = b"".join(dev.cycle() for _ in range(n))
                    conn.sendall(blob)
                    dev.bytes_sent += len(blob)
                    sent_here += n
                r, _, _ = select.select([conn], [], [], 0.002)
                if r:
                    data = conn.recv(65536)
                    if not data:
                        break
                    dev.received(data)
                if a.drop_after and drops == 0 and time.monotonic() - t_start >= a.drop_after:
                    drops += 1
                    dropped = True
                    break
        except OSError:
            pass
        # Linger briefly so the client's last commands are read.
        try:
            conn.shutdown(socket.SHUT_WR)
            conn.settimeout(0.5)
            while True:
                data = conn.recv(65536)
                if not data:
                    break
                dev.received(data)
        except OSError:
            pass
        conn.close()
        if not dropped:
            break
    srv.close()
    return dev.stats(connections=connections, drops=drops)


def run_udp(a) -> dict:
    dev = Device(a.start_seq)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)
    sock.bind(("0.0.0.0", a.port))
    peer = (a.pc, a.pc_port)
    datagrams = 0
    time.sleep(a.start_delay)
    t_start = time.monotonic()
    sent = 0
    pending = b""
    per_dgram = max(1, a.datagram_bytes // 68) if a.datagram_bytes else 0
    while time.monotonic() - t_start < a.seconds:
        n = _due(t_start, a.rate, sent)
        if n > 0:
            if per_dgram:
                for _ in range(n):
                    pending += dev.cycle()
                    if len(pending) >= per_dgram * 68:
                        sock.sendto(pending, peer)
                        dev.bytes_sent += len(pending)
                        datagrams += 1
                        pending = b""
            else:
                blob = b"".join(dev.cycle() for _ in range(n))
                sock.sendto(blob, peer)
                dev.bytes_sent += len(blob)
                datagrams += 1
            sent += n
        r, _, _ = select.select([sock], [], [], 0.002)
        if r:
            try:
                data, _ = sock.recvfrom(65536)
                dev.received(data)
            except OSError:
                pass
    if pending:
        sock.sendto(pending, peer)
        dev.bytes_sent += len(pending)
        datagrams += 1
    end = time.monotonic() + a.linger
    while time.monotonic() < end:
        r, _, _ = select.select([sock], [], [], 0.05)
        if r:
            try:
                data, _ = sock.recvfrom(65536)
                dev.received(data)
            except OSError:
                pass
    sock.close()
    return dev.stats(datagrams=datagrams)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["tcp", "udp"])
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--rate", type=float, default=1000.0, help="cycles per second (4 frames each)")
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--start-seq", type=int, default=0)
    ap.add_argument("--stats", required=True)
    ap.add_argument("--accept-timeout", type=float, default=30.0)
    ap.add_argument("--drop-after", type=float, default=0.0)
    ap.add_argument("--close-after-cycles", type=int, default=0)
    ap.add_argument("--pc", default="")
    ap.add_argument("--pc-port", type=int, default=0)
    ap.add_argument("--start-delay", type=float, default=1.0)
    ap.add_argument("--datagram-bytes", type=int, default=0)
    ap.add_argument("--linger", type=float, default=2.0)
    a = ap.parse_args()
    stats = run_tcp(a) if a.mode == "tcp" else run_udp(a)
    with open(a.stats, "w") as fp:
        json.dump(stats, fp)


if __name__ == "__main__":
    main()
