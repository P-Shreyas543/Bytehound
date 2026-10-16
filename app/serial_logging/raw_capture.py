"""Lossless raw wire capture (``.bhraw``).

Every RX read and TX write is appended exactly as it crossed the wire, with
the ``time.perf_counter()`` stamp the capture worker took for it. This file is
the ground truth for a logging session: the decoded log can always be rebuilt
from it (:func:`rebuild_decoded_log`), so a GUI stall, a full decoded-log
queue, or a crash during the xlsx compile never loses data.

File layout
-----------
``MAGIC`` (8 bytes), then a ``uint32`` length + UTF-8 JSON metadata block,
then records until EOF::

    <B direction> <d t_perf> <I length> <length bytes>

``direction`` is 0 for RX and 1 for TX. A crash can leave a truncated last
record; :func:`iter_raw_capture` stops cleanly at it.

Threading
---------
:meth:`RawCapture.write` is called on the capture thread (or capture process)
right after each read. It only appends to an in-memory buffer under a lock.
A writer thread swaps the buffer out and writes it every ``flush_interval``
seconds, so a slow disk never stalls serial reads. Nothing is ever dropped:
if the disk stalls, the buffer grows (raw rates are small — 2 Mbaud is
~200 KB/s) until the writer catches up or :meth:`close` drains it.
"""

from __future__ import annotations

import json
import logging
import struct
import threading
import time
from pathlib import Path
from typing import Iterator, Mapping, Optional, Tuple

_LOG = logging.getLogger("bytehound.serial_logging.raw_capture")

MAGIC = b"BHRAW\x00\x01\n"
RX = 0
TX = 1
_RECORD = struct.Struct("<BdI")
_META_LEN = struct.Struct("<I")


class RawCapture:
    """Append-only writer for one ``.bhraw`` file."""

    def __init__(
        self,
        path: str | Path,
        metadata: Optional[Mapping[str, object]] = None,
        *,
        flush_interval: float = 0.1,
    ) -> None:
        self.path = Path(path)
        self._metadata = dict(metadata or {})
        self._flush_interval = flush_interval
        self._lock = threading.Lock()
        self._buf = bytearray()
        self._closed = False
        self._error: Optional[str] = None
        self._bytes_written = 0
        self._wake = threading.Event()

        self.path.parent.mkdir(parents=True, exist_ok=True)
        meta = json.dumps(self._metadata, default=str).encode("utf-8")
        self._fp = self.path.open("wb")
        self._fp.write(MAGIC + _META_LEN.pack(len(meta)) + meta)
        self._fp.flush()
        self._thread = threading.Thread(
            target=self._writer_loop, name=f"RawCapture[{self.path.name}]", daemon=False
        )
        self._thread.start()

    # -- capture side ------------------------------------------------------

    def write(self, direction: int, t_perf: float, data: bytes) -> None:
        if not data:
            return
        rec = _RECORD.pack(direction, t_perf, len(data))
        with self._lock:
            if self._closed:
                return
            self._buf += rec
            self._buf += data

    # -- lifecycle ---------------------------------------------------------

    @property
    def error(self) -> Optional[str]:
        return self._error

    @property
    def bytes_written(self) -> int:
        return self._bytes_written

    def close(self, timeout: float = 10.0) -> None:
        """Drain everything buffered to disk and close the file."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._wake.set()
        self._thread.join(timeout)
        if self._thread.is_alive():
            _LOG.warning("RawCapture writer for %s still draining after %.1fs", self.path, timeout)

    def _take(self) -> bytes:
        with self._lock:
            if not self._buf:
                return b""
            out = bytes(self._buf)
            self._buf.clear()
            return out

    def _writer_loop(self) -> None:
        try:
            while True:
                self._wake.wait(self._flush_interval)
                closing = self._closed
                chunk = self._take()
                if chunk:
                    try:
                        self._fp.write(chunk)
                        self._fp.flush()
                        self._bytes_written += len(chunk)
                    except OSError as exc:
                        # Keep the bytes in memory and retry next cycle rather
                        # than drop them; surface the error once.
                        with self._lock:
                            self._buf[:0] = chunk
                        if self._error is None:
                            self._error = f"Raw capture write error for {self.path.name}: {exc}"
                            _LOG.error(self._error)
                        if closing:
                            break
                        time.sleep(0.5)
                        continue
                if closing:
                    break
        finally:
            try:
                self._fp.close()
            except OSError:
                pass


def read_metadata(path: str | Path) -> dict:
    with Path(path).open("rb") as fp:
        return _read_header(fp)


def _read_header(fp) -> dict:
    magic = fp.read(len(MAGIC))
    if magic != MAGIC:
        raise ValueError(f"{getattr(fp, 'name', 'file')} is not a Bytehound raw capture")
    (n,) = _META_LEN.unpack(fp.read(_META_LEN.size))
    return json.loads(fp.read(n).decode("utf-8")) if n else {}


def iter_raw_capture(path: str | Path) -> Iterator[Tuple[int, float, bytes]]:
    """Yield ``(direction, t_perf, data)`` records; stops at a truncated tail."""
    with Path(path).open("rb") as fp:
        _read_header(fp)
        while True:
            head = fp.read(_RECORD.size)
            if len(head) < _RECORD.size:
                return
            direction, t_perf, length = _RECORD.unpack(head)
            data = fp.read(length)
            if len(data) < length:
                return
            yield direction, t_perf, data


def rebuild_decoded_log(
    raw_path: str | Path,
    config,
    out_path: str | Path,
    *,
    polling_mode: Optional[bool] = None,
) -> int:
    """Re-run parse + decode over a raw capture and write a decoded log.

    Uses the same parser, decoder and :class:`DecodedLogger` as a live session,
    with ``elapsed_ms`` measured from the session's recorded log start, so the
    result matches what the live logger would have written had it kept up.
    Returns the number of frames decoded.
    """
    from ..decoder.frame_decoder import decode_frame
    from ..protocol.packet_parser import create_parser
    from .decoded_logger import DecodedLogger

    meta = read_metadata(raw_path)
    log_start = float(meta.get("log_started_perf", 0.0))
    if polling_mode is None:
        polling_mode = bool(meta.get("polling_mode", False))
    log_meta = {k: str(v) for k, v in (meta.get("log_metadata") or {}).items()}
    log_meta["rebuilt_from"] = str(raw_path)

    parser = create_parser(config.protocol)
    signal_state: dict = {}
    frames = 0
    logger = DecodedLogger(out_path, config, metadata=log_meta, polling_mode=polling_mode)
    logger.open()
    try:
        for direction, t_perf, data in iter_raw_capture(raw_path):
            if direction != RX:
                continue
            parser.feed(data)
            elapsed_ms = int((t_perf - log_start) * 1000)
            for packet in parser.extract_all():
                if not packet.ok or packet.frame_id is None:
                    continue
                decoded = decode_frame(config, packet.frame_id, packet.payload, signal_state)
                # Never drop on rebuild: wait for room instead.
                while logger.pending_rows() >= 50_000:
                    time.sleep(0.01)
                logger.log_frame(decoded, elapsed_ms)
                frames += 1
    finally:
        logger.close(timeout=600.0)
    return frames
