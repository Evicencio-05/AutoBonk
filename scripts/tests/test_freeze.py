"""While the freeze is on, a replayed decision cannot change without the operator's bless."""

import importlib.util
import json
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "freeze",
    Path(__file__).resolve().parents[1] / "freeze.py",
)
freeze = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(freeze)


def test_no_frozen_decision_changed():
    if not freeze.config().get("active"):
        return
    changed = freeze.differences()
    assert not changed, (
        "A replayed decision changed during the freeze. Put the change in learning/proposals.md "
        f"for the weekly review, or have the operator run `python3 scripts/freeze.py bless`. {changed}"
    )


def test_a_moved_decision_is_reported(tmp_path):
    day = freeze.days()[0]
    golden = tmp_path / "golden"
    golden.mkdir()
    rows = freeze.replay_day(day)
    (golden / f"{day}.json").write_text(json.dumps(rows[1:]))
    changed = freeze.differences(golden=golden)
    assert day in changed
    assert changed[day]["added"] and not changed[day]["removed"]


def test_progress_counts_closed_live_trades_since_the_start():
    rows = [
        {"mode": "live", "day": "2026-10-23", "dollars": -3.0},
        {"mode": "live", "day": "2026-10-26", "dollars": 12.0},
        {"mode": "live", "day": "2026-10-27", "dollars": None},
        {"mode": "plan", "day": "2026-10-27", "plan_dollars": 50.0},
    ]
    state = freeze.progress(rows, {"active": True, "started": "2026-10-26", "target_trades": 2})
    assert state["closed"] == 1 and state["net"] == 12.0 and not state["done"]
