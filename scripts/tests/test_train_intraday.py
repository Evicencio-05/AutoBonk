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
