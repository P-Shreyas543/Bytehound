"""Regression corpus for the protocol configuration work (Plane.md Part C).

Every configuration in the repository is decoded with deterministic payloads
and the results are written to ``tests/fixtures/decode_golden/``.
``tests/test_config_corpus.py`` decodes the same payloads with the current
code and requires identical results, so a change to the configuration
loader, the canonical JSON path or the decoder cannot silently change a
decoded value for an existing customer configuration.

Regenerate ONLY when a decoded value is meant to change, and review the diff:

  python tools/make_decode_golden.py
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
GOLDEN = ROOT / "tests" / "fixtures" / "decode_golden"


def corpus() -> list:
    """(id, path) of every configuration in the repository, sorted."""
    items = [ROOT / "app" / "resources" / "config_template", ROOT / "tests" / "fixtures" / "canonical_config"]
    items += sorted(p for p in ROOT.glob("*.xlsx"))
    items += sorted(ROOT.glob("MultiCellBMSConfig/*/*.xlsx"))
    out = []
    for p in items:
        rel = p.relative_to(ROOT).as_posix()
        out.append((re.sub(r"[^A-Za-z0-9]+", "_", rel).strip("_"), p))
    return out


def payloads(config, fid: int) -> list:
    frame = config.frames.get(fid)
    length = getattr(frame, "payload_length", None) or max(
        (s.start_byte + s.byte_length for s in config.signals_by_frame.get(fid, [])), default=0)
    out = [bytes(length), bytes((i * 37 + 11) & 0xFF for i in range(length)), b"\xFF" * length]
    if length:
        # First byte 6 / 7: the values the Ather 0x101 rules react to (Part C
        # decision 4 replaces that hard-coded branch; this pins its output).
        out += [b"\x06" + bytes(length - 1), b"\x07" + bytes(length - 1)]
    return out


def _num(v):
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return repr(v)
    return v


def decode_snapshot(config) -> dict:
    from app.decoder.frame_decoder import decode_frame
    out = {}
    for fid in sorted(config.signals_by_frame):
        rows = []
        for payload in payloads(config, fid):
            decoded = decode_frame(config, fid, payload, {})
            rows.append({
                "payload": payload.hex(),
                "signals": [[s.signal_name, _num(s.raw_value), _num(s.scaled_value), s.display_value,
                             s.enum_label, sorted(s.bit_values.items()), s.status]
                            for s in decoded.signals],
            })
        out[f"0x{fid:X}"] = rows
    return out


def main() -> int:
    from app.decoder.config_loader import load_config
    GOLDEN.mkdir(parents=True, exist_ok=True)
    for cid, path in corpus():
        snap = {"config": path.relative_to(ROOT).as_posix(), "frames": decode_snapshot(load_config(path))}
        (GOLDEN / f"{cid}.json").write_text(json.dumps(snap, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"{cid}: {sum(len(v) for v in snap['frames'].values())} frame decodes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
