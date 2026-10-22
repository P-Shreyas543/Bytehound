"""Merge a logging session's hourly segments into one workbook or one per day.

Command-line front end for ``app/serial_logging/session_merge.py`` (the same
code as Tools → Merge Session… in the application). The session folder is
never modified.

  python tools/merge_session.py <session folder>                    # one workbook
  python tools/merge_session.py <session folder> --split day        # one per day
  python tools/merge_session.py <session folder> --kind fixed       # fixed-step log
  python tools/merge_session.py <session folder> --csv              # also keep the merged CSV

Output goes to ``--out`` (default ``<session folder>/merged``), named
``<session>_<kind>[_<YYYY-MM-DD>][_partN].xlsx``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.serial_logging.session_merge import MergeError, merge  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session", type=Path, help="session folder (contains session.json)")
    ap.add_argument("--kind", choices=("event", "fixed"), default="event")
    ap.add_argument("--split", choices=("none", "day"), default="none",
                    help="none = one workbook; day = one workbook per calendar day (local time)")
    ap.add_argument("--out", type=Path, default=None, help="output folder (default: <session>/merged)")
    ap.add_argument("--csv", action="store_true", help="also keep the merged CSV next to each workbook")
    args = ap.parse_args(argv)
    try:
        results = merge(args.session, args.kind, args.split, args.out, args.csv)
    except MergeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    for w in results:
        size = Path(w["xlsx"]).stat().st_size / 1e6
        print(f"{w['xlsx']}  rows={w['rows']}  {w['first']} .. {w['last']}  "
              f"segments {w['segments'][0]}..{w['segments'][-1]}  {size:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
