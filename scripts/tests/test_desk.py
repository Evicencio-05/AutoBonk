"""Exit what-ifs are scored from the bars. A missing contract is not a trade."""

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "desk", Path(__file__).resolve().parents[1] / "desk.py"
)
desk = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(desk)


def _bar(start, open_, high, low, close, **extra):
    row = {
        "start": start,
        "close_at": start + 600,
        "o": open_,
        "h": high,
        "l": low,
        "c": close,
        "atr": 0.70,
        "purple": 70.6,
        "yellow": 63.5,
        "sma": 338.9,
        "v": 1000,
    }
    row.update(extra)
    return row


def _bars():
    return [
        _bar(0, 340.80, 341.00, 340.40, 340.70),
        _bar(600, 340.60, 340.74, 340.07, 340.35),
        _bar(1200, 340.35, 340.44, 339.90, 340.40),
        _bar(1800, 340.40, 340.41, 339.71, 339.74),
        _bar(2400, 339.74, 339.80, 339.50, 339.60),
        _bar(3000, 339.60, 345.50, 339.55, 345.10),
        _bar(3600, 345.10, 346.20, 345.00, 345.90),
    ]


def _levels():
    return [{"ticker": "AAPL", "price": 340, "allows": "long", "targets": [345.4], "note": "Claim 340"}]


def test_profit_factor_is_gross_wins_over_gross_losses():
    stats = desk.score_points([4.0, -2.0, 1.0])

    assert stats["net"] == 3.0
    assert stats["wins"] == 2
    assert stats["losses"] == 1
    assert stats["breakeven"] == 0
    assert stats["profit_factor"] == 2.5
    assert stats["gross_profit"] == 5.0
    assert stats["gross_loss"] == 2.0
    assert stats["win_rate"] == 2 / 3
    assert stats["expected"] == 1.0
    assert stats["avg_win"] == 2.5
    assert stats["avg_loss"] == -2.0
    assert stats["payoff_ratio"] == 1.25
    assert stats["largest_win"] == 4.0
    assert stats["largest_loss"] == -2.0
    assert stats["max_drawdown"] == 2.0
    assert stats["max_drawdown_percent"] == 0.5
    assert stats["max_win_streak"] == 1
    assert stats["max_loss_streak"] == 1
    assert stats["equity"] == [4.0, 2.0, 3.0]


def test_drawdown_before_a_peak_has_no_percent():
    stats = desk.score_points([-1.0, -1.0, 3.0])

    assert stats["max_drawdown"] == 2.0
    assert stats["max_drawdown_percent"] is None
    assert stats["max_loss_streak"] == 2
    assert stats["max_win_streak"] == 1
    assert stats["breakeven"] == 0


def test_a_premium_over_the_threshold_is_paper_and_a_blank_contract_is_not_a_trade():
    assert desk.classify_contract("10/21 342.5C", 1.20, 1.0) == "paper"
    assert desk.classify_contract("10/21 342.5C", 0.38, 1.0) == "fits"
    assert desk.classify_contract("none", 0.38, 1.0) is None
    assert desk.classify_contract("10/21 342.5C", None, 1.0) is None


def test_never_exit_and_a_near_target_are_scored_from_the_closes():
    premiums = {"AAPL|call|340.00": {"contract": "10/21 342.5C", "entry": 0.38, "exit": 0.90}}
    runs = {
        run["name"]: run
        for run in desk.run_presets({"AAPL": _bars()}, _levels(), premiums=premiums, profit_near=0.15)
    }

    live = runs["Live"]["trades"][0]
    never = runs["Never exit"]["trades"][0]
    near = runs["Near the next level"]["trades"][0]

    assert live["exit_reason"] == "reclaim"
    # Priced at the fill bar's close, where the checker actually buys (entry_price), not its open.
    assert round(live["points"], 2) == -0.80
    assert live["book"] == "fits"
    assert round(live["option_dollars"], 2) == 52.0
    assert live["inputs"]["purple"] == 70.6
    assert live["inputs"]["volume"] == 1000
    assert "340.00" in live["inputs"]["nearby"]

    assert never["marked"] is True
    assert never["exit_reason"] == "mark"
    assert round(never["points"], 2) == 5.50  # priced at the fill bar close (entry_price)
    assert runs["Never exit"]["summary"]["fits"]["stock"]["profit_factor"] is None
    assert runs["Never exit"]["summary"]["fits"]["stock"]["net"] == never["points"]

    assert near["exit_reason"] == "near"
    assert round(near["points"], 2) == 4.70  # priced at the fill bar close (entry_price)
    assert near["exit_close"] == 345.10


def test_a_trade_without_a_contract_stays_out_of_the_factor():
    runs = desk.run_presets({"AAPL": _bars()}, _levels())
    live = runs[0]

    assert live["trades"][0]["book"] is None
    assert live["summary"]["no_contract"] == 1
    assert live["summary"]["fits"]["stock"]["trades"] == 0
    assert live["summary"]["paper"]["stock"]["trades"] == 0
    assert live["summary"]["strategy"]["trades"] == 1
    assert live["summary"]["strategy"]["net"] == live["trades"][0]["points"]
    assert "max_drawdown" in live["summary"]["strategy"]
    assert live["buy_hold"]["tickers"] == 1


def test_this_test_uses_the_callers_exit():
    runs = {
        run["name"]: run
        for run in desk.run_presets(
            {"AAPL": _bars()},
            _levels(),
            this_test={"stop_mode": "none", "take": "none", "flatten": "none"},
        )
    }

    assert runs["This test"]["trades"][0]["marked"] is True
    assert runs["This test"]["summary"]["strategy"]["net"] == runs["Never exit"]["summary"]["strategy"]["net"]
    assert runs["This test"]["settings"]["entry"] == "retest"
    assert runs["Live"]["settings"]["entry"] == "retest"
    assert runs["Live"]["settings"]["exit"] == "target"


def test_live_stays_on_the_retest_when_the_test_fades():
    runs = {
        run["name"]: run
        for run in desk.run_presets(
            {"AAPL": _bars()},
            _levels(),
            entry="fade",
            this_test={"exit": "target"},
        )
    }

    assert runs["Live"]["settings"]["entry"] == "retest"
    assert runs["This test"]["settings"]["entry"] == "fade"
    assert runs["Never exit"]["settings"]["entry"] == "fade"
