"""The first green or red candle is not automatically the confirmed candle."""

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "train_intraday",
    Path(__file__).resolve().parents[1] / "train_intraday.py",
)
train_intraday = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(train_intraday)


def _bar(close_at: int, open_: float, close: float) -> dict:
    return {"close_at": close_at, "open": open_, "close": close}


def test_score_flags_the_flat_green_and_the_small_red():
    bars = [
        _bar(0, 11.0, 10.6),
        _bar(1, 10.6, 10.0),
        _bar(2, 9.90, 9.93),
        _bar(3, 9.95, 10.40),
        _bar(4, 10.30, 10.10),
        _bar(5, 10.00, 8.50),
    ]

    scored = train_intraday.score_put(bars, level=10.5, buy_at=3, sell_at=5)

    assert scored["naive_buy"]["close_at"] == 2
    assert scored["ideal_buy"]["close_at"] == 3
    assert scored["buy_bars_early"] == 1
    assert scored["naive_sell"]["close_at"] == 4
    assert scored["ideal_sell"]["close_at"] == 5
    assert scored["sell_bars_early"] == 1
    assert scored["sell_price_gap"] == 10.10 - 8.50


def test_a_put_bottom_is_the_green_that_pushed():
    bars = [
        _bar(0, 11.0, 10.6),
        _bar(1, 10.6, 10.0),
        _bar(2, 9.90, 9.93),
        _bar(3, 9.95, 10.40),
        _bar(4, 10.30, 10.10),
        _bar(5, 10.00, 8.50),
    ]

    bottom = train_intraday.score_bottom(bars, "put", 10.5, 3)

    assert bottom["sniped"] is True
    assert bottom["bottom"]["close_at"] == 3
    assert bottom["naive"]["close_at"] == 2
    assert bottom["ideal_left"] == 0
    assert bottom["naive_left"] == 10.40 - 9.93


def test_a_call_bottom_is_the_red_that_dipped():
    bars = [
        _bar(0, 9.4, 9.2),
        _bar(1, 9.6, 10.4),
        _bar(2, 10.50, 10.30),
        _bar(3, 10.20, 10.05),
        _bar(4, 10.10, 10.40),
    ]

    bottom = train_intraday.score_bottom(bars, "call", 10.0, 3)
    scored = train_intraday.score_call(bars, 10.0, 3, 4)

    assert bottom["sniped"] is True
    assert bottom["bottom"]["close_at"] == 3
    assert bottom["naive"]["close_at"] == 2
    assert round(bottom["naive_left"], 2) == 0.25
    assert scored["naive_buy"]["close_at"] == 2
    assert scored["ideal_sell"]["close_at"] == 4
    assert scored["buy_price_gap"] == 10.30 - 10.05


def test_the_first_goal_is_sniping_the_contract_bottom():
    import yaml

    root = Path(__file__).resolve().parents[2]
    goal = train_intraday.first_goal(
        yaml.safe_load((root / "learning" / "goals.yaml").read_text())
    )
    lesson = (root / "learning" / "lessons" / "snipe-bottom.md").read_text()

    assert goal["id"] == "snipe-bottom"
    assert goal["title"] == "Sniping the bottom on contracts"
    assert "Buy calls on a red candle" in goal["says"]
    assert "not an order" in lesson
    assert "0.43 stock points" in lesson
    assert "not a priced premium" in lesson


def test_the_live_retest_buys_the_confirmed_spcx_bottom():
    """The 09:10 green did not tag 146.5. The retest buys the 09:20 push."""
    import json
    from datetime import datetime
    from zoneinfo import ZoneInfo

    root = Path(__file__).resolve().parents[2]
    zone = ZoneInfo("America/Los_Angeles")
    claim_spec = importlib.util.spec_from_file_location(
        "claim_alerts",
        root / "scripts" / "claim_alerts.py",
    )
    claim = importlib.util.module_from_spec(claim_spec)
    claim_spec.loader.exec_module(claim)

    raw = json.loads((root / "bench/fixtures/2026-10-16-bars.json").read_text())
    bars = claim.add_indicators(
        [
            {
                "close_at": int(bar["close_at"]),
                "o": float(bar["o"]),
                "h": float(bar["h"]),
                "l": float(bar["l"]),
                "c": float(bar["c"]),
            }
            for bar in raw["tickers"]["SPCX"]
        ]
    )
    nine_ten = datetime(2026, 10, 16, 9, 10, tzinfo=zone).timestamp()
    nine_twenty = datetime(2026, 10, 16, 9, 20, tzinfo=zone).timestamp()
    flat = next(bar for bar in bars if bar["close_at"] == nine_ten)
    pushed = next(bar for bar in bars if bar["close_at"] == nine_twenty)
    assert flat["h"] < 146.5 - 0.15
    assert pushed["h"] >= 146.5 - 0.15
    assert abs((pushed["c"] - flat["c"]) - 0.43) < 0.02

    armed = int(datetime.fromisoformat("2026-10-16T08:27:30-07:00").timestamp())
    events = claim.replay(
        bars,
        [{"ticker": "SPCX", "price": 146.5, "allows": "both", "targets": [142.6]}],
        armed,
        claim.live_settings(),
    )
    entries = [event for event in events if event["kind"] == "entry"]

    assert len(entries) == 1
    assert entries[0]["side"] == "put"
    assert entries[0]["reason"] == "retest"
    assert entries[0]["bar"]["close_at"] == nine_twenty
    assert abs(entries[0]["fill"] - pushed["c"]) < 0.02
    assert claim.live_settings()["entry"] == "retest"
