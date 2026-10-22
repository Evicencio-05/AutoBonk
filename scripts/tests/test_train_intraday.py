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
