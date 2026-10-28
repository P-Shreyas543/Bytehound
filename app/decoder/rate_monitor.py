"""Expected frame rate (Frames sheet ``expected_period_ms``).

``FrameRateMonitor`` watches the receive times of frames that have an
expected period and reports *changes* only — one line when a frame stops
or slows down, one when it is back — so a long outage is one warning, not
one per second.

- **late**: nothing for ``LATE_FACTOR`` × the expected period (at least
  ``LATE_MIN_S``).
- **slow**: still arriving, but the average period over the last
  ``WINDOW_S`` is more than ``SLOW_FACTOR`` × expected.

A frame is watched from its first arrival on, so a frame that never comes
(a send-only frame, an unused option) is not reported.
"""

from __future__ import annotations

from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

LATE_FACTOR = 3.0
LATE_MIN_S = 0.5
SLOW_FACTOR = 1.5
WINDOW_S = 10.0


class FrameRateMonitor:
    def __init__(self, expected_s: Dict[int, float], names: Optional[Dict[int, str]] = None) -> None:
        self._expected = {fid: p for fid, p in expected_s.items() if p and p > 0}
        self._names = names or {}
        self._times: Dict[int, Deque[float]] = {}
        self._first: Dict[int, float] = {}
        self._state: Dict[int, str] = {}

    @classmethod
    def from_config(cls, config) -> "FrameRateMonitor":
        frames = getattr(config, "frames", {}) or {}
        expected = {fid: f.expected_period_ms / 1000.0 for fid, f in frames.items()
                    if getattr(f, "expected_period_ms", None)}
        return cls(expected, {fid: f.frame_name for fid, f in frames.items()})

    def __bool__(self) -> bool:
        return bool(self._expected)

    def expected_s(self, frame_id) -> Optional[float]:
        return self._expected.get(frame_id)

    def late_after_s(self, frame_id) -> Optional[float]:
        p = self._expected.get(frame_id)
        return None if p is None else max(LATE_MIN_S, LATE_FACTOR * p)

    def note(self, frame_id, t: float) -> None:
        if frame_id not in self._expected:
            return
        times = self._times.get(frame_id)
        if times is None:
            times = self._times[frame_id] = deque()
            self._first[frame_id] = t
            self._state[frame_id] = "ok"
        times.append(t)
        while times and times[0] < t - WINDOW_S:
            times.popleft()

    def reset(self) -> None:
        """Forget every frame (disconnect, new configuration)."""
        self._times.clear()
        self._first.clear()
        self._state.clear()

    def measured_period_s(self, frame_id) -> Optional[float]:
        times = self._times.get(frame_id)
        if not times or len(times) < 2:
            return None
        return (times[-1] - times[0]) / (len(times) - 1)

    def check(self, now: float) -> List[Tuple[int, str, str]]:
        """``(frame_id, new_state, message)`` for every frame whose state
        changed since the last call; states are ok | slow | late."""
        out = []
        for fid, times in self._times.items():
            expected = self._expected[fid]
            age = now - times[-1]
            measured = self.measured_period_s(fid)
            if age > self.late_after_s(fid):
                state = "late"
            elif (measured is not None and now - self._first[fid] >= WINDOW_S
                  and measured > SLOW_FACTOR * expected):
                state = "slow"
            else:
                state = "ok"
            old = self._state[fid]
            if state == old:
                continue
            self._state[fid] = state
            label = self._label(fid)
            exp = _ms(expected)
            if state == "late":
                msg = f"{label}: no frame for {age:.1f} s (expected every {exp})"
            elif state == "slow":
                msg = f"{label}: arriving every {_ms(measured)} (expected every {exp})"
            elif old == "late":
                msg = f"{label}: arriving again"
            else:
                msg = f"{label}: back to the expected rate ({_ms(measured) if measured else exp})"
            out.append((fid, state, msg))
        return out

    def _label(self, fid) -> str:
        name = self._names.get(fid, "")
        head = f"0x{fid:X}" if isinstance(fid, int) else str(fid)
        return f"{head} {name}".strip()


def _ms(seconds: float) -> str:
    return f"{seconds * 1000:.0f} ms" if seconds < 10 else f"{seconds:.1f} s"
