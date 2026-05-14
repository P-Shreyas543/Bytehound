"""Tests for pure helpers in app.serial_io.serial_worker.

We target the response-matching predicate (and a few other static helpers)
without standing up an actual serial connection or QThread — the predicate
captures the correctness fix for the polling mis-attribution bug.
"""
from __future__ import annotations

import pytest

from app.protocol.packet_parser import ParsedPacket
from app.serial_io.serial_worker import PollingWorker


def _pkt(frame_id, ok=True, payload=b"", err=None) -> ParsedPacket:
    return ParsedPacket(raw=b"", frame_id=frame_id, payload=payload,
                        ok=ok, error=err)


# ──────────────────────────────────────────────────────────────────
# _is_response_match — correctness predicate
# ──────────────────────────────────────────────────────────────────

def test_match_target_none_accepts_any_ok_packet():
    """No-addressing path (priority TX) — any valid frame wins."""
    assert PollingWorker._is_response_match(_pkt(frame_id=42), target_id=None)
    assert PollingWorker._is_response_match(_pkt(frame_id=None), target_id=None)


def test_match_target_none_rejects_bad_crc():
    """Even with no addressing, a bad-CRC frame is never the response."""
    assert not PollingWorker._is_response_match(
        _pkt(frame_id=42, ok=False), target_id=None)


def test_match_requires_frame_id_when_target_set():
    """Strict matching: response frame_id must equal target_id."""
    assert PollingWorker._is_response_match(_pkt(frame_id=5), target_id=5)
    assert not PollingWorker._is_response_match(_pkt(frame_id=6), target_id=5)


def test_match_bad_crc_never_matches_targeted_response():
    assert not PollingWorker._is_response_match(
        _pkt(frame_id=5, ok=False), target_id=5)


def test_match_none_frame_id_doesnt_match_specific_target():
    """A frame with frame_id=None can't be the response to a targeted poll."""
    assert not PollingWorker._is_response_match(
        _pkt(frame_id=None), target_id=5)


# ──────────────────────────────────────────────────────────────────
# Bug regression — a streaming frame during a poll wait MUST NOT
# short-circuit the wait when we're polling a different target.
# ──────────────────────────────────────────────────────────────────

def test_streaming_frame_does_not_satisfy_polled_target():
    """Before the fix, ANY packet during the wait was treated as 'the
    response'. After the fix, a streaming frame with frame_id=99 must not
    satisfy a wait for target_id=5."""
    streaming = _pkt(frame_id=99)
    targeted_response = _pkt(frame_id=5)

    assert not PollingWorker._is_response_match(streaming, target_id=5)
    assert PollingWorker._is_response_match(targeted_response, target_id=5)


@pytest.mark.parametrize("target_id, frame_id, ok, expected", [
    (None, 1, True, True),
    (None, 1, False, False),
    (None, None, True, True),
    (5, 5, True, True),
    (5, 5, False, False),
    (5, 4, True, False),
    (5, None, True, False),
])
def test_response_match_table(target_id, frame_id, ok, expected):
    assert PollingWorker._is_response_match(
        _pkt(frame_id=frame_id, ok=ok), target_id=target_id) is expected
