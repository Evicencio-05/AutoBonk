"""After a reclaim stop at a level, the next entry there waits until price has left it by one ATR."""

import importlib.util
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPTS = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("bench", SCRIPTS / "bench.py")
bench = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bench)
claim = bench.claim
FIXTURES = SCRIPTS.parent / "bench" / "fixtures"
PT = ZoneInfo("America/Los_Angeles")


def _friday(fresh_atr):
    as_of = int(datetime(2026, 10, 23, 13, 10, tzinfo=PT).timestamp())
    prepared = bench.prepare(FIXTURES / "2026-10-23-levels.yaml", FIXTURES / "2026-10-23-bars.json", as_of)
    settings = claim.live_settings()
    settings["fresh_atr"] = fresh_atr
    return bench.decide(prepared, settings)


def _entries(events, ticker, level):
    return [e for e in events if e["ticker"] == ticker and e["level"] == level and e["kind"] == "entry"]


def test_chop_at_a_level_after_a_stop_is_not_re_entered():
    events = _friday(claim.FRESH_ATR)
    avgo = _entries(events, "AVGO", 324.6)
    # 07:00 and 09:40 each came after price had left the level. 10:50 and 11:20 were chop after a stop.
    assert [e["bar_time"][11:16] for e in avgo] == ["07:00", "09:40"]
    skipped = [e for e in events if e["ticker"] == "AVGO" and e["reason"] == "fresh"]
    assert skipped and all(e["kind"] == "skip" for e in skipped)


def test_without_the_rule_the_chop_is_traded():
    avgo = _entries(_friday(0.0), "AVGO", 324.6)
    assert len(avgo) == 4


def test_a_level_price_left_and_came_back_to_is_a_fresh_retest():
    # GOOGL lost 322.75 at 10:30, traded more than an ATR under it at 10:40, and retested it at 11:00.
    googl = _entries(_friday(claim.FRESH_ATR), "GOOGL", 322.75)
    assert [(e["bar_time"][11:16], e["side"]) for e in googl] == [("07:40", "call"), ("11:00", "put")]


def test_leaving_is_measured_in_atr_on_either_side():
    settings = {"fresh_atr": 1.0}
    assert claim._left_level({"h": 101.0, "l": 100.2, "atr": 0.9}, 100.0, settings)
    assert claim._left_level({"h": 99.8, "l": 98.9, "atr": 1.0}, 100.0, settings)
    assert not claim._left_level({"h": 100.5, "l": 99.5, "atr": 1.0}, 100.0, settings)
    assert not claim._left_level({"h": 105.0, "l": 95.0}, 100.0, settings)


def test_the_skip_says_why():
    event = {
        "kind": "skip", "ticker": "AVGO", "side": "call", "level": 324.6, "reason": "fresh",
        "close_at": int(datetime(2026, 10, 23, 11, 10, tzinfo=PT).timestamp()), "fill": None,
        "bar": {"o": 324.5, "h": 324.9, "l": 324.4, "c": 324.8},
    }
    assert "has not left it" in claim.format_live(event)
