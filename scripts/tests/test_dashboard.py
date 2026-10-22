"""The dashboard renders files it is given and does not open the network."""

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "dashboard",
    Path(__file__).resolve().parents[1] / "dashboard.py",
)
dashboard = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(dashboard)


def test_fixture_levels_and_an_empty_journal_render():
    root = Path("/tmp/autobonk-dashboard")
    (root / "alerts").mkdir(parents=True, exist_ok=True)
    (root / "learning").mkdir(parents=True, exist_ok=True)
    (root / "alerts" / "levels.yaml").write_text(
        """
armed_at: "2026-10-16T08:27:30-07:00"
levels:
  - ticker: AAPL
    price: 350
    allows: long
    targets: [360]
    note: "Claim 350 toward 360"
"""
    )
    (root / "learning" / "journal.md").write_text(
        """
## Observations

| Date | Ticker | Posted setup | Trade | Result |
|------|--------|--------------|-------|--------|

## Patterns

None.
"""
    )

    page = dashboard.render(root)

    assert "AAPL" in page
    assert "350" in page
    assert "charts/inbox is not the live book." in page
    assert "None." in page
    assert "No paper trades yet." in page
    assert "not an order" in page
    assert page.index("<h2>Paper</h2>") < page.index("<h2>Live book</h2>")
    assert 'id="loaded"' in page
    assert "place order" not in page.lower()
    assert "<h2>Lessons</h2>" in page
    assert "<h2>Rules</h2>" in page


def test_a_paper_row_renders_above_the_live_book():
    root = Path("/tmp/autobonk-dashboard-paper")
    (root / "alerts").mkdir(parents=True, exist_ok=True)
    (root / "alerts" / "levels.yaml").write_text(
        """
armed_at: "2026-10-19T06:05:48-07:00"
levels: []
"""
    )
    (root / "alerts" / "paper.md").write_text(
        """
| Time | Ticker | Action | Side | Level | Fill | Reason |
|------|--------|--------|------|-------|------|--------|
| 2026-10-19 05:40 PT | SPCX | entry | call | 146.50 | 147.30 | sma |
"""
    )

    page = dashboard.render(root)

    assert "SPCX" in page
    assert "146.50" in page
    assert "Paper" in page
    assert "class='side call'" in page
    assert page.index("<h2>Paper</h2>") < page.index("<h2>Live book</h2>")
    assert "place order" not in page.lower()


def test_a_closed_trade_shows_its_profit_and_the_day():
    root = Path("/tmp/autobonk-dashboard-profit")
    (root / "alerts").mkdir(parents=True, exist_ok=True)
    (root / "alerts" / "levels.yaml").write_text(
        'armed_at: "2026-10-19T06:05:48-07:00"\nlevels: []\n'
    )
    (root / "alerts" / "paper.md").write_text(
        """
| Time | Ticker | Action | Side | Level | Fill | Reason | Contract | Premium |
|------|--------|--------|------|-------|------|--------|----------|---------|
| 2026-10-19 07:40 PT | AAPL | entry | call | 343.50 | 345.18 | sma | 10/19 347.5C | 0.32 |
| 2026-10-19 08:10 PT | AAPL | exit | call | 343.50 | 343.09 | reclaim | 10/19 347.5C | 0.04 |
| 2026-10-19 08:30 PT | GOOGL | entry | call | 344.55 | 345.60 | sma | 10/19 347.5C | 0.37 |

## Open marks

| Contract | Premium | As of | Source |
|----------|---------|-------|--------|
| GOOGL 10/19 347.5C | 0.23 | 2026-10-19 09:34 PT | Robinhood |
"""
    )

    page = dashboard.render(root)

    assert "10/19 347.5C" in page
    assert "-$28" in page
    assert "-$14" in page
    assert "Day" in page
    assert "-$42" in page
    assert "<h2>Contracts</h2>" in page
    assert "No contract comparison yet." in page
    assert "data-stay" in page
    assert "autobonk-sort:" in page
    assert "place order" not in page.lower()
    assert "profit factor" in page


def test_a_contract_comparison_shows_the_percent_return():
    root = Path("/tmp/autobonk-dashboard-contracts")
    (root / "alerts").mkdir(parents=True, exist_ok=True)
    (root / "alerts" / "levels.yaml").write_text(
        'armed_at: "2026-10-20T06:05:48-07:00"\nlevels: []\n'
    )
    (root / "alerts" / "contracts.md").write_text(
        """
| Time | Ticker | Level | Role | Contract | Entry | Price | Return | State |
|------|--------|-------|------|----------|-------|-------|--------|-------|
| 2026-10-20 07:40 PT | AAPL | 343.50 | chosen | 10/21 347.5C | 0.40 | 0.55 | +37.5% | open |
| 2026-10-20 07:40 PT | AAPL | 343.50 | dte | 10/20 347.5C | 0.22 | 0.10 | -54.5% | open |
"""
    )

    page = dashboard.render(root)

    assert "10/21 347.5C" in page
    assert "+37.5%" in page
    assert "-54.5%" in page
    assert page.index("<h2>Paper</h2>") < page.index("<h2>Contracts</h2>")
    assert page.index("<h2>Contracts</h2>") < page.index("<h2>Live book</h2>")


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


def _replay_bars():
    return [
        _bar(0, 340.80, 341.00, 340.40, 340.70),
        _bar(600, 340.60, 340.74, 340.07, 340.35),
        _bar(1200, 340.35, 340.44, 339.90, 340.40),
        _bar(1800, 340.40, 340.41, 339.71, 339.74),
        _bar(2400, 339.74, 339.80, 339.50, 339.60),
        _bar(3000, 339.60, 345.50, 339.55, 345.10),
        _bar(3600, 345.10, 346.20, 345.00, 345.90),
    ]


def _strategy_payload(**extra):
    payload = {
        "armed_at": "",
        "levels": [{"ticker": "AAPL", "price": 340, "allows": "long", "targets": [345.4], "note": "Claim 340"}],
        "touch": 0.15,
        "chase": 0.50,
        "sma_band": 1,
        "break_atr": 0.5,
        "profit_near": 0.15,
        "entry": "retest",
        "exit": "target",
        "exit_test": "live",
    }
    payload.update(extra)
    return payload


def test_the_strategy_desk_edits_variables_and_hides_contracts():
    root = Path("/tmp/autobonk-dashboard-strategy")
    (root / "alerts").mkdir(parents=True, exist_ok=True)
    (root / "alerts" / "levels.yaml").write_text(
        'armed_at: "2026-10-16T08:27:30-07:00"\nlevels:\n'
        "  - ticker: AAPL\n    price: 350\n    allows: long\n    targets: [360]\n    note: Claim\n"
    )

    page = dashboard.render(root)
    backtest = page.split("id='backtest'", 1)[1].split("<section", 1)[0]

    assert 'id="strategy-fields"' in backtest
    assert 'id="entry"' in backtest
    assert 'id="exit-rule"' in backtest
    assert 'id="sma-band"' in backtest
    assert 'id="bars-source"' in backtest
    assert "max drawdown" in backtest
    assert "win rate" in backtest
    assert "premium-rows" not in backtest
    assert "Add contract" not in backtest
    assert "place order" not in page.lower()


def test_a_backtest_reports_profit_and_follows_the_exit_variable():
    bars = {"AAPL": _replay_bars()}
    live = dashboard.backtest_payload(_strategy_payload(), bars)
    held = dashboard.backtest_payload(_strategy_payload(exit_test="never"), bars)

    report = live["report"]
    stats = report["summary"]["strategy"]
    assert report["name"] == "This test"
    assert stats["trades"] == 1
    assert round(stats["net"], 2) == -0.75
    assert stats["gross_loss"] == stats["max_drawdown"]
    assert stats["profit_factor"] == 0
    assert stats["wins"] == 0
    assert stats["losses"] == 1
    assert "equity" in stats
    assert report["settings"]["entry"] == "retest"
    assert report["settings"]["exit"] == "target"
    assert "stop_mode" not in report["settings"]
    assert round(held["report"]["summary"]["strategy"]["net"], 2) == 5.55
    assert held["report"]["settings"]["flatten"] == "none"
    assert live["window"]["bars"] == 7


def test_saved_sessions_score_each_posted_book():
    result = dashboard.backtest_payload({"bars": "saved", "levels": [], "exit_test": "live"})
    stats = result["report"]["summary"]["strategy"]

    assert result["window"]["source"] == "saved"
    assert result["window"]["days"] == ["2026-10-14", "2026-10-15", "2026-10-16"]
    assert stats["trades"] > 0
    assert stats["gross_profit"] >= 0
    assert stats["gross_loss"] >= 0
    assert "profit_factor" in stats
    assert "max_drawdown" in stats
    assert "win_rate" in stats
    assert "expected" in stats
    assert "equity" in stats
    assert len(stats["equity"]) == stats["trades"]
    assert result["report"]["trades"][0]["contract"] in ("", None)
