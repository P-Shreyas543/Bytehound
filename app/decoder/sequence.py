"""Sequence-counter gap detection (Plane.md F12).

Frames can be lost before they reach the PC (USB-serial bridge overflow,
network, device firmware) with no error anywhere. When the protocol carries
a rolling counter, comparing each value with the previous one reveals it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from .types import SequenceCounterSpec


@dataclass
class SequenceEvent:
    frame_id: int
    kind: str            # "gap" (frames missing), "repeat", "reset" (counter went back)
    expected: int
    received: int
    missing: int         # frames missing for a gap, else 0


@dataclass
class CounterStats:
    received: int = 0
    missing: int = 0
    gaps: int = 0
    repeats: int = 0
    resets: int = 0


@dataclass
class SequenceTracker:
    """Per frame ID: the next expected value is ``(last + step) mod 2**bits``.

    * as expected: fine;
    * the same value again: a *repeat*;
    * further ahead by less than half the counter range: a *gap* of
      ``delta // step - 1`` missing frames;
    * anything else (a jump backwards): a *reset* — the device restarted
      or the counter was reset; not counted as loss.

    Half the range is the usual limit for telling "ahead" from "behind"
    on a wrapping counter (as in serial-number arithmetic, RFC 1982).
    """

    specs: Dict[int, SequenceCounterSpec]
    stats: Dict[int, CounterStats] = field(default_factory=dict)
    _last: Dict[int, int] = field(default_factory=dict)

    def observe(self, frame_id: int, value: int) -> Optional[SequenceEvent]:
        spec = self.specs.get(frame_id)
        if spec is None:
            return None
        st = self.stats.setdefault(frame_id, CounterStats())
        st.received += 1
        modulus = 1 << spec.bits
        value = int(value) % modulus
        last = self._last.get(frame_id)
        self._last[frame_id] = value
        if last is None:
            return None
        expected = (last + spec.step) % modulus
        if value == expected:
            return None
        delta = (value - last) % modulus
        if delta == 0:
            st.repeats += 1
            return SequenceEvent(frame_id, "repeat", expected, value, 0)
        if delta < modulus // 2:
            missing = max(1, delta // spec.step - 1)
            st.gaps += 1
            st.missing += missing
            return SequenceEvent(frame_id, "gap", expected, value, missing)
        st.resets += 1
        return SequenceEvent(frame_id, "reset", expected, value, 0)

    def totals(self) -> Dict[str, int]:
        out = {"seq_missing": 0, "seq_gaps": 0, "seq_repeats": 0, "seq_resets": 0}
        for fid, st in self.stats.items():
            out["seq_missing"] += st.missing
            out["seq_gaps"] += st.gaps
            out["seq_repeats"] += st.repeats
            out["seq_resets"] += st.resets
            out[f"seq_missing_0x{fid:X}"] = st.missing
        return out
