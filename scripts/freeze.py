#!/usr/bin/env python3
"""Hold the checker's decisions still while a live sample builds.

  python3 scripts/freeze.py status    # frozen or not, and closed live trades toward the target
  python3 scripts/freeze.py check     # replay every bench fixture; fail if a decision changed
  python3 scripts/freeze.py bless     # operator only: accept the current decisions as the golden set

config/freeze.yaml is the operator's switch. While it is active:

- the checker ignores alerts/parameters.yaml and keeps the code defaults, and
- scripts/tests/test_freeze.py fails when any replayed entry, exit, or skip differs
  from bench/golden/. A bug fix that changes no decision passes. One that changes a
  decision needs the operator to run `bless`, which is the point.

A fixture with no golden file yet (a new day from `ledger.py snapshot`) is recorded
as it replays now. That is a new observation, not a change.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import bench  # noqa: E402
import claim_alerts as claim  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PT = ZoneInfo("America/Los_Angeles")
FIXTURES = ROOT / "bench" / "fixtures"
GOLDEN = ROOT / "bench" / "golden"
FREEZE_PATH = ROOT / "config" / "freeze.yaml"


def settings() -> dict:
    """What a frozen checker trades on: the code defaults."""
    return claim.live_settings()


def days(fixtures: Path = FIXTURES) -> list[str]:
    return sorted(
        path.name[: -len("-levels.yaml")]
        for path in fixtures.glob("*-levels.yaml")
        if (fixtures / path.name.replace("-levels.yaml", "-bars.json")).is_file()
    )


def replay_day(day: str, fixtures: Path = FIXTURES) -> list[dict]:
    when = datetime.fromisoformat(day).replace(hour=13, minute=10, tzinfo=PT)
    prepared = bench.prepare(
        fixtures / f"{day}-levels.yaml", fixtures / f"{day}-bars.json", int(when.timestamp())
    )
    return bench.execute(prepared, settings())


def _golden(day: str, golden: Path) -> Path:
    return golden / f"{day}.json"


def record_missing(fixtures: Path = FIXTURES, golden: Path = GOLDEN) -> list[str]:
    """Write golden files only for fixture days that have none."""
    added = []
    golden.mkdir(parents=True, exist_ok=True)
    for day in days(fixtures):
        path = _golden(day, golden)
        if path.is_file():
            continue
        path.write_text(json.dumps(replay_day(day, fixtures), indent=1) + "\n")
        added.append(day)
    return added


def differences(fixtures: Path = FIXTURES, golden: Path = GOLDEN) -> dict[str, dict]:
    """day -> {"added": [...], "removed": [...]} for every day whose decisions moved."""
    changed = {}
    for day in days(fixtures):
        path = _golden(day, golden)
        if not path.is_file():
            continue
        want = json.loads(path.read_text())
        got = replay_day(day, fixtures)
        if got == want:
            continue
        keyed = lambda rows: {json.dumps(row, sort_keys=True) for row in rows}  # noqa: E731
        changed[day] = {
            "added": sorted(keyed(got) - keyed(want)),
            "removed": sorted(keyed(want) - keyed(got)),
        }
    return changed


def bless(fixtures: Path = FIXTURES, golden: Path = GOLDEN) -> list[str]:
    golden.mkdir(parents=True, exist_ok=True)
    for day in days(fixtures):
        _golden(day, golden).write_text(json.dumps(replay_day(day, fixtures), indent=1) + "\n")
    return days(fixtures)


def config(path: Path = FREEZE_PATH) -> dict:
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def progress(rows: list[dict], spec: dict) -> dict:
    """Closed live trades on or after the freeze start, toward its target."""
    start = str(spec.get("started") or "")
    closed = [
        row
        for row in rows
        if row.get("mode") == "live" and row.get("dollars") is not None and str(row.get("day") or "") >= start
    ]
    target = int(spec.get("target_trades") or 0)
    return {
        "active": spec.get("active") is True,
        "started": start,
        "target": target,
        "closed": len(closed),
        "net": round(sum(row["dollars"] for row in closed), 2),
        "done": bool(target) and len(closed) >= target,
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    command = args[0] if args else "status"
    if command == "status":
        import ledger

        state = progress(ledger.load(), config())
        word = "on" if state["active"] else "off"
        print(
            f"Freeze {word} since {state['started'] or '-'}: {state['closed']}/{state['target']} "
            f"closed live trades, net ${state['net']:.2f}."
        )
        if state["done"]:
            print("Target reached. Run the weekly review before lifting it.")
        return 0
    if command == "check":
        added = record_missing()
        if added:
            print("Recorded new fixture days:", ", ".join(added))
        changed = differences()
        if not changed:
            print(f"No decision changed across {len(days())} fixture days.")
            return 0
        for day, diff in changed.items():
            print(f"{day}: +{len(diff['added'])} -{len(diff['removed'])}")
            for row in diff["removed"]:
                print("  - " + row)
            for row in diff["added"]:
                print("  + " + row)
        return 1
    if command == "bless":
        blessed = bless()
        print("Golden decisions written for", ", ".join(blessed))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
