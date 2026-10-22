"""A claim is a finished 10-minute close, not a wick."""

import importlib.util
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_SPEC = importlib.util.spec_from_file_location(
    "claim_alerts",
    Path(__file__).resolve().parents[1] / "claim_alerts.py",
)
claim_alerts = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(claim_alerts)


def test_ten_minute_close_uses_the_second_five_minute_bar():
    # 1_000_200 is a 10-minute boundary. The 10:05 bar supplies the close.
    start = 1_000_200
    bars = [
        (start, 10.0),
        (start + 300, 11.0),
        (start + 600, 12.0),
    ]
    closed = claim_alerts.ten_minute_closes(bars, now=start + 600 + 120)

    assert closed == [(start, 11.0)]


def test_wick_above_the_level_is_not_a_claim():
    # High is not stored. Only the close can claim. 10.4 stays under 10.5.
    closes = [(0, 10.0), (600, 10.4)]

    assert claim_alerts.crosses(closes, 10.5, "claim", armed_at=600) == []


def test_claim_is_the_first_close_above_the_level():
    closes = [(0, 10.0), (600, 10.6), (1200, 10.8)]

    found = claim_alerts.crosses(closes, 10.5, "claim", armed_at=600)

    assert len(found) == 1
    assert found[0]["close"] == 10.6
    assert found[0]["close_at"] == 1200


def test_lose_is_the_first_close_below_the_level():
    closes = [(0, 10.0), (600, 9.4)]

    found = claim_alerts.crosses(closes, 9.5, "lose", armed_at=0)

    assert len(found) == 1
    assert found[0]["side"] == "lose"
    assert found[0]["close"] == 9.4


def test_after_hours_close_is_outside_the_session():
    close_at = int(datetime(2026, 10, 16, 15, 0, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())
    cash_close = int(datetime(2026, 10, 16, 13, 0, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())

    assert claim_alerts.in_session(close_at) is False
    assert claim_alerts.in_session(cash_close) is True


def test_close_before_the_note_does_not_alert():
    closes = [(0, 10.0), (600, 11.0)]

    assert claim_alerts.crosses(closes, 10.5, "claim", armed_at=2000) == []


def _bar(start, open_, high, low, close, sma=None, purple=None, yellow=None):
    return {
        "start": start,
        "close_at": start + 600,
        "o": open_,
        "h": high,
        "l": low,
        "c": close,
        "sma": sma,
        "purple": purple,
        "yellow": yellow,
    }


def test_ten_minute_bar_keeps_the_wick():
    start = 1_000_200
    bars = [
        (start, 10.0, 10.2, 9.8, 10.1),
        (start + 300, 10.1, 11.5, 10.0, 11.0),
    ]

    closed = claim_alerts.ten_minute_bars(bars, now=start + 720)

    assert closed[0]["o"] == 10.0
    assert closed[0]["h"] == 11.5
    assert closed[0]["l"] == 9.8
    assert closed[0]["c"] == 11.0


def test_a_tighter_touch_rejects_the_two_cent_miss():
    level = {"ticker": "AAPL", "price": 342.85, "allows": "long", "targets": []}
    bars = [
        _bar(0, 344.20, 344.80, 343.40, 344.10),
        _bar(600, 343.80, 344.06, 342.87, 343.40),
        _bar(1200, 343.20, 343.60, 342.95, 343.35),
    ]

    tight = claim_alerts.resolve_settings({"touch": 0.0})

    assert claim_alerts.replay(bars, [level], settings=tight) == []
    assert claim_alerts.TOUCH == 0.15
    assert claim_alerts.replay(bars, [level])[0]["kind"] == "entry"


def test_two_cent_miss_still_tags():
    # Thursday AAPL 08:30 low was 342.87, two cents above 342.85.
    level = {"ticker": "AAPL", "price": 342.85, "allows": "long", "targets": []}
    bars = [
        _bar(0, 344.20, 344.80, 343.40, 344.10),
        _bar(600, 343.80, 344.06, 342.87, 343.40),
        _bar(1200, 343.20, 343.60, 342.95, 343.35),
    ]

    events = claim_alerts.replay(bars, [level])

    assert events[0]["kind"] == "entry"
    assert events[0]["side"] == "call"
    assert events[0]["reason"] == "retest"
    assert events[0]["signal_at"] == 1200


def test_green_retest_after_a_break_signals_a_put():
    level = {
        "ticker": "SPCX",
        "price": 146,
        "allows": "short",
        "targets": [142.5, 138.5],
    }
    bars = [
        _bar(0, 147.20, 147.80, 146.40, 147.00),
        _bar(600, 147.00, 147.10, 145.40, 145.70),
        _bar(1200, 145.60, 146.06, 145.30, 145.85, purple=62.0, yellow=55.0),
        _bar(1800, 145.84, 146.00, 145.40, 145.70),
        _bar(2400, 145.20, 145.40, 142.20, 142.40),
        _bar(3000, 142.10, 142.30, 138.00, 138.20),
    ]

    events = claim_alerts.replay(bars, [level])

    assert events[0]["kind"] == "entry"
    assert events[0]["side"] == "put"
    assert events[0]["signal_at"] == 1800
    assert [event["kind"] for event in events] == ["entry", "exit"]
    assert events[1]["reason"] == "target"
    assert events[1]["close_at"] == 3600
    text = claim_alerts.format_live(events[0])
    assert "SPCX put entry 146.00" in text
    assert "RSI purple 62.00 yellow 55.00" in text
    assert "debit at most $100" in text
    assert text.endswith("Not an order.")


def test_red_hold_of_a_short_only_level_is_not_a_call():
    level = {"ticker": "NVDA", "price": 213.50, "allows": "short", "targets": [209]}
    bars = [
        _bar(0, 216.40, 217.00, 215.20, 216.10),
        _bar(600, 215.80, 216.20, 213.40, 214.60),
        _bar(1200, 214.40, 215.10, 213.80, 214.90),
    ]

    assert claim_alerts.replay(bars, [level]) == []


def test_next_open_two_dollars_away_is_a_skip():
    level = {"ticker": "TSLA", "price": 358, "allows": "long", "targets": [367, 371]}
    bars = [
        _bar(0, 360.20, 361.00, 359.40, 360.00),
        _bar(600, 359.80, 360.10, 357.60, 358.40),
        _bar(1200, 360.00, 361.20, 359.40, 360.40),
    ]

    events = claim_alerts.replay(bars, [level])

    assert len(events) == 1
    assert events[0]["kind"] == "skip"
    assert events[0]["reason"] == "chase"
    assert "left the level" in claim_alerts.format_live(events[0])


def test_same_bar_reclaim_is_a_skip():
    level = {"ticker": "SPCX", "price": 146, "allows": "short", "targets": [142.5, 138.5]}
    bars = [
        _bar(0, 147.00, 147.40, 146.20, 146.80),
        _bar(600, 146.70, 146.90, 145.20, 145.50),
        _bar(1200, 145.40, 146.06, 145.20, 145.85),
        _bar(1800, 145.84, 146.20, 145.70, 146.10),
    ]

    events = claim_alerts.replay(bars, [level])

    assert len(events) == 1
    assert events[0]["kind"] == "skip"
    assert events[0]["reason"] == "reclaim"


def test_a_close_inside_half_an_atr_is_not_a_break():
    level = {"ticker": "AAPL", "price": 340, "allows": "long", "targets": [345.4]}
    bars = [
        _bar(0, 340.80, 341.00, 340.40, 340.70),
        _bar(600, 340.60, 340.74, 340.07, 340.35),
        _bar(1200, 340.35, 340.44, 339.90, 340.40),
        _bar(1800, 340.40, 340.41, 339.71, 339.74),
        _bar(2400, 339.74, 339.80, 339.50, 339.60),
    ]
    for bar in bars:
        bar["atr"] = 0.70

    events = claim_alerts.replay(bars, [level])

    assert events[0]["kind"] == "entry"
    assert events[-1]["kind"] == "exit"
    assert events[-1]["reason"] == "reclaim"
    assert events[-1]["bar"]["c"] == 339.60


def test_the_atr_is_ready_on_the_fourteenth_bar():
    start = 1_000_200
    rows = []
    for index in range(40):
        price = 100 + (index % 2) * 0.4
        rows.append((start + index * 300, price, price + 0.5, price - 0.2, price, 1))

    bars = claim_alerts.add_indicators(
        claim_alerts.ten_minute_bars(rows, now=start + 40 * 300)
    )

    assert bars[12]["atr"] is None
    assert bars[13]["atr"] is not None


def test_twenty_sma_hold_near_a_level_is_a_watch():
    # High is 75 cents under 344, so the wick does not tag. The average does.
    level = {"ticker": "AAPL", "price": 344, "allows": "short", "targets": [340]}
    bars = [
        _bar(0, 343.80, 344.20, 343.20, 343.50),
        _bar(600, 342.80, 343.25, 342.40, 343.10, sma=343.80, purple=48.79, yellow=48.55),
        _bar(1200, 342.40, 343.00, 342.10, 342.90, sma=343.70, purple=47.00, yellow=48.00),
    ]

    events = claim_alerts.replay(bars, [level])

    assert [event["kind"] for event in events] == ["watch"]
    assert events[0]["side"] == "put"
    assert events[0]["reason"] == "sma"
    text = claim_alerts.format_live(events[0])
    assert "watch" in text
    assert "20 SMA" in text
    assert text.endswith("Not an order.")


def test_a_failed_next_number_blocks_the_lower_level():
    level = {"ticker": "AAPL", "price": 340, "allows": "long", "targets": [342.25, 350]}
    bars = [
        _bar(0, 341.50, 341.80, 340.80, 341.20),
        _bar(600, 341.20, 342.64, 341.00, 342.10),
        _bar(1200, 341.50, 341.60, 340.05, 340.40),
        _bar(1800, 340.30, 340.50, 340.10, 340.40),
    ]

    events = claim_alerts.replay(bars, [level])

    assert [event["kind"] for event in events] == ["skip"]
    assert events[0]["reason"] == "next"
    assert "did not hold" in claim_alerts.format_live(events[0])


def test_a_close_through_the_next_number_clears_the_block():
    level = {"ticker": "AAPL", "price": 340, "allows": "long", "targets": [342.25]}
    bars = [
        _bar(0, 341.50, 341.80, 340.80, 341.20),
        _bar(600, 341.20, 342.64, 341.00, 342.10),
        _bar(1200, 341.80, 341.90, 340.00, 340.40),
        _bar(1800, 340.40, 340.50, 340.20, 340.45),
        _bar(2400, 340.50, 342.80, 340.40, 342.50),
        _bar(3000, 342.00, 342.05, 341.30, 341.50),
        _bar(3600, 341.40, 341.40, 340.00, 340.30),
        _bar(4200, 340.20, 340.60, 340.10, 340.50),
    ]

    events = claim_alerts.replay(bars, [level])

    assert events[0]["kind"] == "skip"
    assert events[0]["reason"] == "next"
    assert events[1]["kind"] == "entry"
    assert events[1]["reason"] == "retest"


def test_fade_keeps_its_entry_when_the_next_number_failed():
    pending = {
        "reason": "fade",
        "side": "call",
        "next": 342.25,
        "bar": {"close_at": 1800},
    }
    seen = [
        {"close_at": 1200, "h": 342.64, "l": 341.0, "c": 342.10},
        {"close_at": 1800, "h": 341.60, "l": 340.05, "c": 340.40},
    ]

    assert claim_alerts._next_failed(seen, pending, 0.15) is False


def test_a_rejected_contract_does_not_open_the_trade():
    level = {"ticker": "AAPL", "price": 342.85, "allows": "long", "targets": []}
    bars = [
        _bar(0, 344.20, 344.80, 343.40, 344.10),
        _bar(600, 343.80, 344.06, 342.87, 343.40),
        _bar(1200, 343.20, 343.60, 342.95, 343.35),
    ]

    events = claim_alerts.replay(bars, [level], accept=lambda pending, bar: False)

    assert [event["kind"] for event in events] == ["skip"]
    assert events[0]["reason"] == "contract"
    assert "far target" in claim_alerts.format_live(events[0])


def test_a_late_exit_is_kept_and_a_late_watch_is_dropped():
    moment = int(datetime(2026, 10, 20, 15, 0, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())
    same_day = int(datetime(2026, 10, 20, 10, 0, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())
    prior_day = int(datetime(2026, 10, 19, 10, 0, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())
    fresh = int(datetime(2026, 10, 20, 14, 40, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())

    assert claim_alerts.route_event({"kind": "exit", "close_at": same_day}, moment) == "quiet"
    assert claim_alerts.route_event({"kind": "watch", "close_at": same_day}, moment) == "drop"
    assert claim_alerts.route_event({"kind": "exit", "close_at": prior_day}, moment) == "drop"
    assert claim_alerts.route_event({"kind": "entry", "close_at": fresh}, moment) == "alert"


def test_an_rsi_cross_on_an_open_trade_is_a_watch():
    level = {"ticker": "SPCX", "price": 146, "allows": "short", "targets": [100]}
    bars = [
        _bar(0, 147.20, 147.80, 146.40, 147.00, purple=58, yellow=54),
        _bar(600, 147.00, 147.10, 145.40, 145.70, purple=56, yellow=54),
        _bar(1200, 145.60, 146.06, 145.30, 145.85, purple=55, yellow=54),
        _bar(1800, 145.84, 146.00, 145.40, 145.70, purple=52, yellow=54),
        _bar(2400, 145.70, 145.90, 145.20, 145.40, purple=48, yellow=53),
    ]

    events = claim_alerts.replay(bars, [level])

    assert events[0]["kind"] == "entry"
    assert events[0]["reason"] == "retest"
    assert events[1]["kind"] == "watch"
    assert events[1]["reason"] == "rsi"
    assert "under 50" in events[1]["note"]
    assert all(event["kind"] != "exit" for event in events)


def test_twelve_fifty_bar_closes_the_trade():
    cut = int(datetime(2026, 10, 15, 12, 50, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())
    start = cut - 600
    level = {"ticker": "SPCX", "price": 146, "allows": "short", "targets": [138.5]}
    bars = [
        _bar(start - 1800, 147.00, 147.20, 146.10, 146.80),
        _bar(start - 1200, 146.60, 146.70, 145.20, 145.40),
        _bar(start - 600, 145.30, 146.05, 145.10, 145.80),
        _bar(start, 145.70, 145.90, 145.20, 145.40),
    ]

    events = claim_alerts.replay(bars, [level])

    assert events[-1]["kind"] == "exit"
    assert events[-1]["reason"] == "clock"
    assert events[-1]["close_at"] == cut


def test_paper_line_is_an_entry_and_not_a_skip():
    close_at = int(datetime(2026, 10, 19, 5, 40, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())
    event = {
        "kind": "entry",
        "ticker": "SPCX",
        "side": "call",
        "level": 146.5,
        "reason": "sma",
        "close_at": close_at,
        "fill": 147.30,
        "bar": {"c": 147.24},
    }

    line = claim_alerts.paper_line(event)

    assert line is not None
    assert "SPCX" in line
    assert "entry" in line
    assert "147.30" in line
    assert claim_alerts.paper_line({**event, "kind": "skip"}) is None


def test_the_nearest_otm_call_under_the_cap_is_taken_when_the_target_can_reach_it():
    quotes = [
        {"strike": 345, "debit": 1.25},
        {"strike": 347.5, "debit": 0.32},
        {"strike": 350, "debit": 0.07},
    ]

    chosen = claim_alerts.choose_contract(345.18, "call", quotes, 350)

    assert chosen["strike"] == 347.5
    assert chosen["otm"] is True


def test_an_over_cap_strike_the_target_can_reach_is_paper():
    quotes = [
        {"strike": 262.5, "debit": 1.17},
        {"strike": 265, "debit": 0.27},
    ]

    chosen = claim_alerts.choose_contract(262.98, "call", quotes, 263.15)

    assert chosen["strike"] == 262.5
    assert chosen["book"] == "paper"
    assert claim_alerts.choose_contract(262.98, "call", quotes[1:], 263.15) is None


def test_same_day_is_chosen_when_the_strike_stays_inside_the_far_target():
    session = date(2026, 10, 20)
    quotes = [
        {"strike": 345, "debit": 1.25},
        {"strike": 347.5, "debit": 0.32},
        {"strike": 350, "debit": 0.07},
    ]
    ladders = {
        session: quotes,
        date(2026, 10, 21): quotes,
        date(2026, 10, 23): [{"strike": 347.5, "debit": 0.55}],
    }

    rows = claim_alerts.assemble_contracts(
        session, ladders, "call", 345.18, 345.4, 350
    )

    by_role = {row["role"]: row["contract"] for row in rows}
    assert by_role["chosen"] == "10/20 347.5C"
    assert "dte" not in by_role
    assert by_role["first"] == "10/20 345C"
    first = next(row for row in rows if row["role"] == "first")
    assert first["book"] == "paper"
    assert by_role["cheap"] == "10/20 350C"
    assert by_role["week"] == "10/23 347.5C"
    assert claim_alerts.format_return("0.52", "5.65") == "+986.5%"
    assert claim_alerts.format_return("0.32", "0.04") == "-87.5%"


def test_without_a_target_the_chosen_contract_is_none():
    session = date(2026, 10, 20)
    ladders = {session: [{"strike": 150, "debit": 0.60}]}

    rows = claim_alerts.assemble_contracts(
        session, ladders, "call", 149.11, None, None
    )

    by_role = {row["role"]: row["contract"] for row in rows}
    assert by_role["chosen"] == "none"
    assert by_role["dte"] == "10/20 150C"


def test_an_entry_records_each_contract_rule():
    path = Path("/tmp/autobonk-contracts.md")
    path.unlink(missing_ok=True)
    close_at = int(datetime(2026, 10, 20, 7, 40, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())

    claim_alerts.record_contracts(
        [
            {
                "kind": "entry",
                "ticker": "AAPL",
                "level": 343.5,
                "close_at": close_at,
                "contracts": [
                    {"role": "chosen", "contract": "10/21 347.5C", "premium": 0.40},
                    {"role": "dte", "contract": "10/20 347.5C", "premium": 0.22},
                ],
            }
        ],
        path,
    )

    text = path.read_text()
    assert "10/21 347.5C" in text
    assert "10/20 347.5C" in text
    assert "| 0.40 |" in text
    assert text.count("| open |") == 2


def test_a_put_takes_the_nearest_strike_under_the_cap():
    quotes = [
        {"strike": 100, "debit": 1.40},
        {"strike": 97.5, "debit": 0.40},
        {"strike": 95, "debit": 0.10},
    ]

    chosen = claim_alerts.choose_contract(99.2, "put", quotes, 95)

    assert chosen["strike"] == 97.5


def test_a_failed_claim_is_a_put_and_a_failed_break_is_a_call():
    fade = claim_alerts.resolve_settings({"entry": "fade"})
    claim_level = {"ticker": "AAPL", "price": 100, "allows": "long", "targets": [110]}
    claim_bars = [
        _bar(0, 99.2, 99.6, 98.8, 99.4),
        _bar(600, 99.3, 100.1, 99.1, 99.6),
        _bar(1200, 99.5, 99.8, 99.2, 99.4),
    ]

    faded = claim_alerts.replay(claim_bars, [claim_level], settings=fade)

    assert faded[0]["kind"] == "entry"
    assert faded[0]["side"] == "put"
    assert faded[0]["reason"] == "fade"
    assert claim_alerts.replay(claim_bars, [claim_level]) == []

    break_level = {"ticker": "NVDA", "price": 100, "allows": "short", "targets": [90]}
    break_bars = [
        _bar(0, 100.8, 101.2, 100.4, 100.6),
        _bar(600, 100.7, 100.9, 99.9, 100.3),
        _bar(1200, 100.4, 100.6, 100.1, 100.2),
    ]

    faded_break = claim_alerts.replay(break_bars, [break_level], settings=fade)

    assert faded_break[0]["kind"] == "entry"
    assert faded_break[0]["side"] == "call"
    assert faded_break[0]["reason"] == "fade"
    assert claim_alerts.replay(break_bars, [break_level]) == []
    assert claim_alerts.live_settings()["entry"] == "retest"


def test_a_fade_exits_at_the_far_level_or_back_through_the_entry():
    fade = claim_alerts.resolve_settings({"entry": "fade"})
    levels = [
        {"ticker": "AMZN", "price": 100, "allows": "long", "targets": []},
        {"ticker": "AMZN", "price": 95, "allows": "short", "targets": [90]},
    ]
    held = [
        _bar(0, 99.0, 99.4, 98.5, 99.2),
        _bar(600, 99.2, 100.4, 99.0, 99.6),
        _bar(1200, 99.5, 99.7, 94.0, 94.5),
        _bar(1800, 94.4, 94.6, 89.0, 89.5),
    ]

    events = claim_alerts.replay(held, levels, settings=fade)

    assert events[0]["side"] == "put"
    assert events[0]["reason"] == "fade"
    assert events[1]["kind"] == "exit"
    assert events[1]["reason"] == "target"
    assert events[1]["close_at"] == 2400

    failed = [
        _bar(0, 99.0, 99.4, 98.5, 99.2),
        _bar(600, 99.2, 100.4, 99.0, 99.6),
        _bar(1200, 99.5, 99.8, 99.2, 99.6),
        _bar(1800, 99.7, 101.0, 99.5, 100.6),
    ]

    invalidated = claim_alerts.replay(failed, levels, settings=fade)

    assert invalidated[1]["reason"] == "reclaim"
    assert claim_alerts.replay(held, levels) == []


def test_a_premarket_fill_uses_the_first_print_after_the_option_open():
    start = int(datetime(2026, 10, 20, 5, 20, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())
    first = int(datetime(2026, 10, 20, 6, 31, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())
    bars = [(first, 1.20, 1.40, 1.10, 1.30)]

    assert claim_alerts.option_price(bars, start, "open") == 1.20


def test_a_missing_same_day_ladder_is_recorded_as_none():
    rows = claim_alerts.assemble_contracts(
        date(2026, 10, 20),
        {date(2026, 10, 21): [{"strike": 222.5, "debit": 0.44}]},
        "call",
        217.7,
        219.8,
        225.35,
    )

    by_role = {row["role"]: row["contract"] for row in rows}
    assert by_role["chosen"] == "10/21 222.5C"
    assert by_role["dte"] == "none"


def test_a_zero_dte_in_the_last_hour_uses_the_next_expiration():
    session = date(2026, 10, 21)
    noon = int(datetime(2026, 10, 21, 11, 50, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())
    morning = int(datetime(2026, 10, 21, 7, 20, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())
    ladders = {
        session: [{"strike": 342.5, "debit": 0.35}],
        date(2026, 10, 22): [{"strike": 342.5, "debit": 0.80}],
    }

    late = claim_alerts.assemble_contracts(
        session, ladders, "call", 340.35, 343.0, 345.4, noon
    )
    early = claim_alerts.assemble_contracts(
        session, ladders, "call", 340.35, 343.0, 345.4, morning
    )

    assert {row["role"]: row["contract"] for row in late}["chosen"] == "10/22 342.5C"
    assert {row["role"]: row["contract"] for row in late}["dte"] == "10/21 342.5C"
    assert {row["role"]: row["contract"] for row in early}["chosen"] == "10/21 342.5C"


def test_a_zero_dte_strike_past_the_midpoint_uses_the_next_expiration():
    session = date(2026, 10, 21)
    ladders = {
        session: [{"strike": 345.0, "debit": 0.07}, {"strike": 342.5, "debit": 1.40}],
        date(2026, 10, 22): [{"strike": 342.5, "debit": 0.80}],
    }

    rows = claim_alerts.assemble_contracts(
        session, ladders, "call", 340.35, 343.0, 345.4
    )

    by_role = {row["role"]: row["contract"] for row in rows}
    assert by_role["chosen"] == "10/22 342.5C"
    assert by_role["dte"] == "10/21 345C"
    assert claim_alerts._too_far_otm(340.35, "call", 342.5, 345.4) is False
    assert claim_alerts._too_far_otm(340.35, "call", 345.0, 345.4) is True


def test_the_expiration_search_starts_on_the_session_date():
    days = claim_alerts._quote_days(date(2026, 10, 20))

    assert days[0] == date(2026, 10, 20)
    assert date(2026, 10, 23) in days


def test_a_missing_wednesday_uses_the_nearest_later_expiration():
    session = date(2026, 10, 21)
    days = claim_alerts._quote_days(session)
    friday = date(2026, 10, 23)
    ladder = [{"strike": 190.0, "debit": 0.40, "expiration": friday}]
    rows = claim_alerts.assemble_contracts(
        session,
        {friday: ladder},
        "call",
        193.0,
        197.0,
        210.0,
    )

    assert days[0] == session
    assert friday in days
    assert rows[0]["role"] == "chosen"
    assert rows[0]["contract"] == "10/23 190C"
    assert rows[1]["role"] == "dte"
    assert rows[1]["contract"] == "none"


def test_a_blank_contract_is_quoted_again():
    paper = Path("/tmp/autobonk-paper-blank.md")
    contracts = Path("/tmp/autobonk-contracts-blank.md")
    contracts.unlink(missing_ok=True)
    paper.write_text(
        "| Time | Ticker | Action | Side | Level | Fill | Reason | Contract | Premium |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
        "| 2026-10-20 07:50 PT | NVDA | entry | call | 217.50 | 217.70 | retest |  |  |\n"
        "| 2026-10-20 08:00 PT | AAPL | entry | call | 340.00 | 341.88 | sma | none |  |\n"
    )

    def fake(ticker, side, stock, start, first, far):
        return [{"role": "chosen", "contract": "10/21 222.5C", "premium": 0.44}]

    original = claim_alerts.quote_contracts
    claim_alerts.quote_contracts = fake
    try:
        filled = claim_alerts.fill_missing_contracts(
            [{"ticker": "NVDA", "price": 217.5, "allows": "long", "targets": [219.8, 225.35]}],
            paper,
            contracts,
        )
    finally:
        claim_alerts.quote_contracts = original

    text = paper.read_text()
    assert filled
    assert "10/21 222.5C" in text
    assert "| 0.44 |" in text
    assert "| none |" in text
    saved = contracts.read_text()
    assert "| chosen |" in saved
    assert "10/21 222.5C" in saved


def test_an_empty_ladder_stays_blank():
    paper = Path("/tmp/autobonk-paper-empty.md")
    contracts = Path("/tmp/autobonk-contracts-empty.md")
    contracts.unlink(missing_ok=True)
    paper.write_text(
        "| Time | Ticker | Action | Side | Level | Fill | Reason | Contract | Premium |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
        "| 2026-10-20 07:50 PT | NVDA | entry | call | 217.50 | 217.70 | retest |  |  |\n"
    )

    def fake(ticker, side, stock, start, first, far):
        return []

    original = claim_alerts.quote_contracts
    claim_alerts.quote_contracts = fake
    try:
        filled = claim_alerts.fill_missing_contracts(
            [{"ticker": "NVDA", "price": 217.5, "allows": "long", "targets": [225.35]}],
            paper,
            contracts,
        )
    finally:
        claim_alerts.quote_contracts = original

    assert not filled
    assert "|  |  |" in paper.read_text()
    assert not contracts.is_file()


def test_a_ten_minute_bar_sums_the_two_volumes():
    start = 1_000_200
    bars = [
        (start, 10.0, 10.2, 9.8, 10.1, 100),
        (start + 300, 10.1, 11.5, 10.0, 11.0, 250),
    ]

    closed = claim_alerts.ten_minute_bars(bars, now=start + 720)

    assert closed[0]["v"] == 350
    assert closed[0]["c"] == 11.0


def test_the_longer_averages_stay_off_the_entry():
    start = 1_000_200
    rows = []
    for index in range(120):
        price = 100 + index * 0.01
        rows.append((start + index * 300, price, price + 0.2, price - 0.2, price, 5))

    bars = claim_alerts.add_indicators(
        claim_alerts.ten_minute_bars(rows, now=start + 120 * 300)
    )

    assert bars[-1]["sma"] is not None
    assert bars[-1]["sma50"] is not None
    assert bars[-1]["sma200"] is None
    assert bars[-1]["v"] == 10


def test_context_line_records_the_signal_candle_and_not_a_skip():
    close_at = int(datetime(2026, 10, 21, 7, 30, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())
    event = {
        "kind": "entry",
        "ticker": "AAPL",
        "side": "call",
        "level": 340.0,
        "reason": "retest",
        "close_at": close_at,
        "fill": 340.35,
        "bar": {
            "o": 340.42,
            "h": 340.74,
            "l": 340.07,
            "c": 340.35,
            "purple": 70.60,
            "yellow": 63.51,
            "sma": 338.93,
            "sma50": 338.24,
            "sma200": 340.53,
            "v": 12500,
        },
    }
    levels = [
        {"ticker": "AAPL", "price": 340},
        {"ticker": "AAPL", "price": 343},
        {"ticker": "AMZN", "price": 260.5},
    ]

    line = claim_alerts.context_line(event, levels)

    assert line is not None
    assert "70.60" in line
    assert "63.51" in line
    assert "338.93 (+1.42)" in line
    assert "340.53 (-0.18)" in line
    assert "340.00 (+0.35)" in line
    assert "343.00" not in line
    assert "12,500" in line
    assert claim_alerts.context_line({**event, "kind": "skip"}, levels) is None


def test_context_is_written_once():
    path = Path("/tmp/autobonk-context.md")
    path.unlink(missing_ok=True)
    close_at = int(datetime(2026, 10, 21, 7, 30, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())
    event = {
        "kind": "entry",
        "ticker": "AAPL",
        "side": "call",
        "level": 340.0,
        "close_at": close_at,
        "fill": 340.35,
        "bar": {
            "o": 340.42,
            "h": 340.74,
            "l": 340.07,
            "c": 340.35,
            "purple": 70.6,
            "yellow": 63.51,
            "sma": 338.93,
            "sma50": None,
            "sma200": None,
            "v": 100,
        },
    }

    claim_alerts.append_context([event], [{"ticker": "AAPL", "price": 340}], path)
    claim_alerts.append_context([event], [{"ticker": "AAPL", "price": 340}], path)

    text = path.read_text()
    assert text.count("| 2026-10-21 07:30 PT | AAPL | entry |") == 1
    assert "Trade context" in text
