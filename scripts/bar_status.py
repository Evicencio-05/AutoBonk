#!/usr/bin/env python3
"""Compact JSON status for Omarchy bar widgets.

  python3 scripts/bar_status.py
  python3 scripts/bar_status.py --pretty

Watches come from alerts/log.md (latest session).
Open trades come from unpaired paper entries plus live plans awaiting exit.
Nothing here places an order.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import dashboard  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _live_open(root: Path) -> list[dict]:
    """Unpaired live.md entries. A row waits for confirm; it is not an order."""
    text = dashboard._read(root / "alerts" / "live.md")
    open_entries: list[dict] = []
    for cells in dashboard._table_rows(text):
        if cells[0] == "Time":
            continue
        padded = (cells + [""] * 10)[:10]
        row = {
            "time": padded[0],
            "ticker": padded[1],
            "action": padded[2],
            "side": padded[3],
            "level": padded[4],
            "fill": padded[5],
            "reason": padded[6],
            "contract": padded[7],
            "premium": padded[8],
            "cash": padded[9],
            "book": "live",
        }
        if row["action"] == "entry":
            open_entries.append(row)
            continue
        if row["action"] != "exit":
            continue
        for index, entry in enumerate(open_entries):
            if (
                entry["ticker"] == row["ticker"]
                and entry["side"] == row["side"]
                and entry["level"] == row["level"]
            ):
                open_entries.pop(index)
                break
    return open_entries


def _paper_open(root: Path) -> list[dict]:
    rows, marks = dashboard._paper_rows(dashboard._read(root / "alerts" / "paper.md"))
    opens = []
    for trade in dashboard._paired_trades(rows, marks):
        if trade["exit"] is not None:
            continue
        entry = dict(trade["entry"])
        entry["book"] = "paper"
        mark = trade["mark"]
        entry["mark"] = "" if mark is None else f"{mark.get('premium', '')} at {mark.get('as_of', '')}".strip()
        opens.append(entry)
    return opens


def _watch_items(root: Path) -> list[dict]:
    rows = dashboard._watch_rows(dashboard._read(root / "alerts" / "log.md"))
    return sorted(rows, key=lambda row: row["time"], reverse=True)


def status(root: Path | None = None) -> dict:
    root = ROOT if root is None else root
    watches = _watch_items(root)
    live = _live_open(root)
    paper = _paper_open(root)
    opens = live + paper
    return {
        "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "root": str(root),
        "watches": watches,
        "opens": opens,
        "counts": {
            "watches": len(watches),
            "opens": len(opens),
            "live": len(live),
            "paper": len(paper),
        },
    }


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    pretty = "--pretty" in args or "-p" in args
    payload = status()
    if pretty:
        print(json.dumps(payload, indent=2))
    else:
        print(json.dumps(payload, separators=(",", ":")))


if __name__ == "__main__":
    main()
