"""No view of a parser's buffer may outlive the parse call (task.md Phase 1).

Found while diagnosing GUI stalls: a frame object retained after it
returned (here by a stack sampler; equally by an exception reference cycle,
a debugger or a profiler) kept ``_try_parse_one``'s memoryview of the
bytearray alive. The bytearray could then not be resized, every following
``feed()`` raised ``BufferError``, and the worker discarded the bytes it had
just read — silently, for as long as the frame lived (seconds, measured).

Each test keeps every parser frame alive after it returns and checks that
parsing carries on with nothing lost.
"""

from __future__ import annotations

import sys

import pytest

from app.protocol.packet_builder import build_packet
from app.protocol.packet_parser import FramedParser, WaveshareCanParser
from tests.conftest import dummy_protocol_config


class _RetainParserFrames:
    """sys.setprofile hook that keeps every packet_parser frame referenced
    after it returns, the way a retained traceback or sampler would."""

    def __init__(self) -> None:
        self.frames: list = []

    def __call__(self, frame, event, _arg):
        if event == "return" and frame.f_code.co_filename.endswith("packet_parser.py"):
            self.frames.append(frame)

    def __enter__(self):
        sys.setprofile(self)
        return self

    def __exit__(self, *exc):
        sys.setprofile(None)


def _feed_all(parser, blob: bytes, chunk: int) -> list:
    out = []
    for i in range(0, len(blob), chunk):
        parser.feed(blob[i:i + chunk])
        out.extend(parser.extract_all())
    return out


def test_framed_parser_keeps_working_when_its_frames_are_retained():
    pc = dummy_protocol_config(header=b"\xAA\x55")
    frames = [build_packet(pc, 0x100 + (i % 7), bytes([i % 256]) * 6) for i in range(3000)]
    blob = b"".join(frames)
    parser = FramedParser(pc)
    with _RetainParserFrames() as keeper:
        got = _feed_all(parser, blob, 61)       # forces compaction (clear / del) repeatedly
    assert keeper.frames                        # the hook really kept frames alive
    assert [p.raw for p in got] == frames
    assert parser.stats.bytes_in == len(blob) and parser.stats.frames_ok == 3000


@pytest.mark.parametrize("fixed", [True, False])
def test_waveshare_parser_keeps_working_when_its_frames_are_retained(fixed):
    if fixed:
        pc = dummy_protocol_config(header=b"\xAA", footer=b"\x55", parser_type="waveshare_can_20_bytes",
                                   waveshare_fixed_20_bytes=True)
        frames = []
        for i in range(3000):
            f = bytearray(20)
            f[0], f[1] = 0xAA, 0x55
            f[5], f[6] = i & 0xFF, (i >> 8) & 0xFF
            f[9] = 4
            f[10:14] = b"TEST"
            f[19] = (sum(f[:19]) + 1) & 0xFF
            frames.append(bytes(f))
    else:
        pc = dummy_protocol_config(header=b"\xAA", footer=b"\x55", parser_type="waveshare_can")
        frames = [bytes([0xAA, 0xC0 | 4, i & 0xFF, (i >> 8) & 0x07]) + b"DATA" + b"\x55" for i in range(3000)]
    blob = b"".join(frames)
    parser = WaveshareCanParser(pc)
    with _RetainParserFrames() as keeper:
        got = _feed_all(parser, blob, 61)
    assert keeper.frames
    assert [p.raw for p in got if p.ok] == frames


def test_worker_counts_parser_failures_in_integrity():
    """A parser exception used to cost the bytes just read with no trace in
    the integrity record; it is now counted."""
    from app.serial_io.serial_worker import PollingWorker, SerialSettings

    class Port:
        is_open = True
        in_waiting = 8

        def read(self, n):
            return b"\xAA\x55" * (n // 2)

    class Broken:
        stats = FramedParser(dummy_protocol_config()).stats
        buffered_bytes = 0

        def feed(self, data):
            raise BufferError("Existing exports of data: object cannot be re-sized")

    worker = PollingWorker(SerialSettings(port="x"), dummy_protocol_config(), [])
    worker._serial, worker._parser = Port(), Broken()
    with pytest.raises(BufferError):
        worker._service_rx()
    assert worker.integrity_snapshot()["parse_errors"] == 1
    worker._serial = None
