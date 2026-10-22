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


def test_the_first_lesson_is_sniping_the_contract_bottom():
    root = Path("/tmp/autobonk-dashboard-lesson")
    (root / "alerts").mkdir(parents=True, exist_ok=True)
    (root / "learning" / "lessons").mkdir(parents=True, exist_ok=True)
    (root / "alerts" / "levels.yaml").write_text(
        'armed_at: "2026-10-16T08:27:30-07:00"\nlevels: []\n'
    )
    (root / "learning" / "goals.yaml").write_text(
        """
goals:
  - id: snipe-bottom
    title: Sniping the bottom on contracts
    says: Buy calls on a red candle and puts on a green candle.
"""
    )
    (root / "learning" / "lessons" / "snipe-bottom.md").write_text(
        "# Sniping the bottom on contracts\n\nThis is the first goal. It is not an order.\n"
    )
    (root / "learning" / "drills.yaml").write_text(
        """
drills:
  - ticker: SPCX
    session: "2026-10-16"
    side: put
    level: 146.5
    ideal_buy: "09:20"
    ideal_sell: "12:10"
"""
    )

    page = dashboard.render(root)

    assert "Sniping the bottom on contracts" in page
    assert page.index("Sniping the bottom on contracts") < page.index("<h2>Journal</h2>")
    assert "not an order" in page
    assert "place order" not in page.lower()
