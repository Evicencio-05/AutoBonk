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
claim_alerts.SEND_ORDERS = False


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
    assert "fit the account balance" in text
    assert text.endswith("Not an order.")


def test_a_claimed_resistance_flips_to_a_call():
    levels = [
        {"ticker": "NVDA", "price": 213.50, "allows": "short", "targets": [209]},
        {"ticker": "NVDA", "price": 219.80, "allows": "long", "targets": [225]},
    ]
    bars = [
        _bar(0, 212.80, 213.20, 212.20, 212.60),
        _bar(600, 212.80, 214.40, 212.60, 214.10),
        _bar(1200, 214.00, 214.20, 213.40, 213.70),
        _bar(1800, 213.65, 213.90, 213.40, 213.70),
    ]

    events = claim_alerts.replay(bars, levels)

    assert events[0]["kind"] == "entry"
    assert events[0]["side"] == "call"
    assert events[0]["reason"] == "retest"
    assert events[0]["level"] == 213.50
    assert events[0]["flip"] == "Resistance flipped to support."
    assert "Resistance flipped to support." in claim_alerts.format_live(events[0])
    assert claim_alerts._book_targets(levels[0], "call", levels) == [219.8, 225.0]


def test_a_lost_support_flips_to_a_put_and_exits_at_the_lower_number():
    levels = [
        {"ticker": "AAPL", "price": 340, "allows": "long", "targets": [345.4]},
        {"ticker": "AAPL", "price": 333.25, "allows": "long", "targets": [340, 345.4]},
    ]
    bars = [
        _bar(0, 341.00, 341.20, 340.20, 340.60),
        _bar(600, 340.40, 340.50, 339.10, 339.30),
        _bar(1200, 339.20, 340.05, 339.00, 339.40),
        _bar(1800, 339.60, 339.80, 339.20, 339.40),
        _bar(2400, 339.20, 339.30, 332.50, 332.80),
    ]
    for bar in bars:
        bar["atr"] = 0.70

    events = claim_alerts.replay(bars, levels)

    assert [event["kind"] for event in events] == ["entry", "exit"]
    assert events[0]["side"] == "put"
    assert events[0]["reason"] == "retest"
    assert events[0]["flip"] == "Support flipped to resistance."
    assert events[1]["reason"] == "target"
    assert events[1]["close_at"] == 3000
    assert "Support flipped to resistance." in claim_alerts.format_live(events[0])


def test_a_close_inside_half_an_atr_does_not_flip_support():
    level = {"ticker": "AAPL", "price": 340, "allows": "long", "targets": [345]}
    bars = [
        _bar(0, 340.80, 341.00, 340.40, 340.70),
        _bar(600, 340.50, 340.55, 339.70, 339.80),
        _bar(1200, 339.70, 340.05, 339.50, 339.75),
        _bar(1800, 339.70, 339.90, 339.40, 339.60),
    ]
    for bar in bars:
        bar["atr"] = 0.70

    assert claim_alerts.replay(bars, [level]) == []


def test_a_reclaim_flips_a_lost_support_back_to_a_call():
    level = {"ticker": "AAPL", "price": 340, "allows": "long", "targets": [345]}
    bars = [
        _bar(0, 341.00, 341.20, 339.00, 339.20),
        _bar(600, 339.40, 341.00, 339.30, 340.80),
        _bar(1200, 340.70, 340.80, 340.00, 340.20),
        _bar(1800, 340.15, 340.40, 340.00, 340.20),
    ]
    for bar in bars:
        bar["atr"] = 0.70

    events = claim_alerts.replay(bars, [level])

    assert events[0]["kind"] == "entry"
    assert events[0]["side"] == "call"
    assert events[0]["reason"] == "retest"
    assert events[0]["flip"] == ""


def test_a_level_marked_both_plays_either_side_without_a_flip():
    level = {
        "ticker": "AAPL",
        "price": 333.25,
        "allows": "both",
        "targets": [330.7],
        "up_targets": [340],
    }
    bars = [
        _bar(0, 334.20, 334.40, 333.80, 334.00),
        _bar(600, 333.90, 334.00, 333.20, 333.50),
        _bar(1200, 333.45, 333.70, 333.30, 333.55),
    ]

    events = claim_alerts.replay(bars, [level])

    assert events[0]["kind"] == "entry"
    assert events[0]["side"] == "call"
    assert events[0]["flip"] == ""


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
    assert "no further number" in claim_alerts.format_live(events[0])


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


def test_thursday_is_live_and_wednesday_stays_on_the_paper_tape():
    wednesday = int(datetime(2026, 10, 21, 7, 30, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())
    thursday = int(datetime(2026, 10, 22, 7, 30, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())
    event = {
        "kind": "entry",
        "ticker": "AAPL",
        "side": "call",
        "level": 340.0,
        "reason": "retest",
        "close_at": thursday,
        "fill": 340.35,
        "contract": "10/22 342.5C",
        "premium": 0.38,
        "cash": 40,
        "bar": {
            "o": 340.42,
            "h": 340.74,
            "l": 340.07,
            "c": 340.35,
            "purple": 70.6,
            "yellow": 63.51,
        },
    }
    over = {
        **event,
        "ticker": "AMZN",
        "side": "put",
        "level": 260.5,
        "contract": "10/22 257.5P",
        "premium": 0.80,
    }
    missing = {**event, "contract": "none", "premium": None}
    paper = Path("/tmp/autobonk-paper-untouched.md")
    live = Path("/tmp/autobonk-live.md")
    paper.write_text("# Paper trades\n\n| Time | Ticker |\n|---|---|\n")
    if live.exists():
        live.unlink()

    assert claim_alerts.session_kind(wednesday) == "paper"
    assert claim_alerts.session_kind(thursday) == "live"
    assert claim_alerts.cash_fit(event) == "fits"
    assert claim_alerts.cash_fit(over) == "over"
    assert claim_alerts.cash_fit(missing) == "none"
    notice = claim_alerts.live_notice(event)
    assert "Waiting for confirm." in notice
    assert "The debit fits the account balance." in notice
    assert notice.endswith("Not an order.")
    claim_alerts.append_live([event, over], live)

    text = live.read_text()
    assert "10/22 342.5C" in text
    assert text.count("fits") == 1
    assert "| over |" in text
    assert "AAPL" not in paper.read_text()
    claim_alerts.append_live([event], live)
    assert live.read_text().count("10/22 342.5C") == 1


def test_the_ladder_keeps_walking_past_the_one_dollar_strike():
    assert claim_alerts._has_cash_strike([{"debit": 0.90}], claim_alerts.premium_cap(40)) is False
    assert (
        claim_alerts._has_cash_strike([{"debit": 0.90}, {"debit": 0.49}], claim_alerts.premium_cap(49))
        is True
    )
    assert claim_alerts._has_cash_strike([{"debit": 0.90}], claim_alerts.premium_cap(100)) is True


def test_next_day_names_the_cash_strike_and_keeps_the_dollar_strike():
    session = date(2026, 10, 22)
    friday = date(2026, 10, 23)
    quotes = [
        {"strike": 150, "debit": 2.38},
        {"strike": 146, "debit": 0.90},
        {"strike": 144, "debit": 0.49},
        {"strike": 139, "debit": 0.11},
    ]

    rows = claim_alerts.assemble_contracts(
        session, {friday: quotes}, "put", 149.80, 146.6, 138.6, cash=49
    )

    by_role = {row["role"]: row for row in rows}
    assert by_role["chosen"]["contract"] == "10/23 146P"
    assert by_role["cash"]["contract"] == "10/23 144P"
    assert by_role["cash"]["premium"] == 0.49
    assert by_role["cash"]["halfway"] == "past"
    assert by_role["cheap"]["contract"] == "10/23 139P"
    close_at = int(datetime(2026, 10, 22, 8, 30, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())
    contract, premium = claim_alerts.named_live_contract(rows, close_at)
    assert contract == "10/23 144P"
    assert premium == 0.49
    assert claim_alerts.halfway_blocks(rows, close_at) == "past"
    event = {
        "kind": "entry",
        "ticker": "SPCX",
        "side": "put",
        "level": 150.0,
        "reason": "retest",
        "close_at": close_at,
        "fill": 149.80,
        "contract": contract,
        "premium": premium,
        "cash": 49,
        "contracts": rows,
        "bar": {"o": 148.81, "h": 149.91, "l": 148.28, "c": 149.80, "purple": 26.75, "yellow": 26.89},
    }
    notice = claim_alerts.live_notice(event)
    assert "The live contract is 10/23 144P at $0.49." in notice
    assert "The $1 strike 10/23 146P at $0.90 stays on the row." in notice
    assert "does not refuse a next-day strike" in notice
    line = claim_alerts.live_line(event)
    assert "| 10/23 144P | 0.49 | fits | 10/23 146P | 0.90 | 10/23 144P | 0.49 | past |" in line
    blank = {**event, "contract": "", "premium": None, "contracts": []}
    assert claim_alerts.cash_fit(blank) == "quote"
    assert "quote failed" in claim_alerts.live_notice(blank)


def test_zero_dte_halfway_blocks_the_cash_strike():
    session = date(2026, 10, 22)
    quotes = [
        {"strike": 150, "debit": 2.38},
        {"strike": 146, "debit": 0.90},
        {"strike": 144, "debit": 0.49},
        {"strike": 139, "debit": 0.11},
    ]
    rows = claim_alerts.assemble_contracts(
        session, {session: quotes}, "put", 149.80, 146.6, 138.6, cash=49
    )
    close_at = int(datetime(2026, 10, 22, 8, 30, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())
    by_role = {row["role"]: row for row in rows}
    assert by_role["cash"]["contract"] == "10/22 144P"
    assert by_role["cash"]["halfway"] == "past"
    contract, _premium = claim_alerts.named_live_contract(rows, close_at)
    assert contract == "10/22 146P"
    assert claim_alerts.halfway_blocks(rows, close_at) == "blocks"


def test_the_balance_picks_the_nearest_strike_it_can_still_pay():
    session = date(2026, 10, 22)
    friday = date(2026, 10, 23)
    quotes = [
        {"strike": 150, "debit": 2.38},
        {"strike": 146, "debit": 0.90},
        {"strike": 144, "debit": 0.49},
        {"strike": 139, "debit": 0.11},
    ]

    wide = claim_alerts.assemble_contracts(
        session, {friday: quotes}, "put", 149.80, 146.6, 138.6, cash=100
    )
    tight = claim_alerts.assemble_contracts(
        session, {friday: quotes}, "put", 149.80, 146.6, 138.6, cash=20
    )
    unread = claim_alerts.assemble_contracts(
        session, {friday: quotes}, "put", 149.80, 146.6, 138.6
    )

    assert {row["role"]: row for row in wide}["cash"]["contract"] == "10/23 146P"
    assert {row["role"]: row for row in tight}["cash"]["contract"] == "10/23 139P"
    assert {row["role"]: row for row in unread}["cash"]["contract"] == "none"


def test_a_blank_live_contract_is_quoted_again():
    live = Path("/tmp/autobonk-live-blank.md")
    contracts = Path("/tmp/autobonk-live-contracts.md")
    contracts.unlink(missing_ok=True)
    live.write_text(
        "# Live plans\n\n"
        "Thursday 2026-10-22 is the first live session.\n\n"
        "| Time | Ticker | Action | Side | Level | Fill | Reason | Contract | Premium | Cash |\n"
        "|------|--------|--------|------|-------|------|--------|----------|---------|------|\n"
        "| 2026-10-22 08:30 PT | SPCX | entry | put | 150.00 | 149.80 | retest |  | | none |\n"
    )

    def fake(ticker, side, stock, start, first, far, cash=None):
        return [
            {"role": "chosen", "contract": "10/23 146P", "premium": 0.90, "book": "fits"},
            {
                "role": "cash",
                "contract": "10/23 144P",
                "premium": 0.49,
                "book": "fits",
                "halfway": "past",
            },
        ]

    original = claim_alerts.quote_contracts
    claim_alerts.quote_contracts = fake
    try:
        filled = claim_alerts.fill_missing_contracts(
            [{"ticker": "SPCX", "price": 150, "side": "lose", "allows": "short", "targets": [146.6, 138.6]}],
            live,
            contracts,
            cash=49,
        )
    finally:
        claim_alerts.quote_contracts = original

    text = live.read_text()
    assert filled
    assert "$1 strike" in text
    assert "| 10/23 144P | 0.49 | fits | 10/23 146P | 0.90 | 10/23 144P | 0.49 | past |" in text
    assert "| none |" not in text
    saved = contracts.read_text()
    assert "10/23 146P" in saved
    assert "10/23 144P" in saved
    assert "cash" in saved


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
    chosen = next(row for row in rows if row["role"] == "chosen")
    assert chosen["why"] == "no-target"


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
    live_claim = claim_alerts.replay(claim_bars, [claim_level])
    assert live_claim[0]["kind"] == "entry"
    assert live_claim[0]["side"] == "put"
    assert live_claim[0]["reason"] == "retest"
    assert live_claim[0]["flip"] == "Support flipped to resistance."

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
    live_break = claim_alerts.replay(break_bars, [break_level])
    assert live_break[0]["kind"] == "entry"
    assert live_break[0]["side"] == "call"
    assert live_break[0]["reason"] == "retest"
    assert live_break[0]["flip"] == "Resistance flipped to support."
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
    live = claim_alerts.replay(held, levels)
    assert live[0]["kind"] == "entry"
    assert live[0]["side"] == "put"
    assert live[0]["reason"] == "retest"
    assert live[0]["flip"] == "Support flipped to resistance."
    assert live[1]["reason"] == "target"


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

    def fake(ticker, side, stock, start, first, far, cash=None):
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

    def fake(ticker, side, stock, start, first, far, cash=None):
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


def _open_contract(**overrides):
    row = {
        "time": "2026-10-21 07:30 PT",
        "ticker": "AAPL",
        "action": "entry",
        "side": "call",
        "level": "340.00",
        "fill": "340.35",
        "contract": "10/21 342.5C",
        "premium": 0.38,
    }
    row.update(overrides)
    return row


def _priced_bar(moment):
    def stock_bar(ticker, at):
        del ticker, at
        return {"o": 340.1, "h": 340.4, "l": 339.2, "c": 339.5, "close_at": moment}

    return stock_bar


def test_contract_expiration_uses_the_entry_year_and_rolls_forward():
    assert claim_alerts.contract_expiration(_open_contract()) == date(2026, 10, 21)
    assert claim_alerts.contract_expiration(_open_contract(contract="none")) is None
    january = _open_contract(time="2026-12-30 07:30 PT", contract="1/2 100C")

    assert claim_alerts.contract_expiration(january) == date(2027, 1, 2)


def test_a_zero_dte_stays_open_until_twelve_forty_five():
    entry = _open_contract()
    before = int(datetime(2026, 10, 21, 12, 44, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())
    cutoff = int(datetime(2026, 10, 21, 12, 45, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())

    assert claim_alerts.apply_contract_exits([], [entry], before) == []
    exits = claim_alerts.apply_contract_exits(
        [],
        [entry],
        cutoff,
        stock_bar=_priced_bar(cutoff),
        option_mark=lambda symbol, moment: 0.11,
    )

    assert len(exits) == 1
    assert exits[0]["reason"] == "expiry"
    assert exits[0]["close_at"] == cutoff
    assert exits[0]["contract"] == "10/21 342.5C"
    assert exits[0]["premium"] == 0.11
    assert exits[0]["fill"] == 339.5
    assert "12:45" in claim_alerts.format_live(exits[0])


def test_a_passed_expiration_exits_at_the_cutoff_not_the_next_morning():
    entry = _open_contract()
    morning = int(datetime(2026, 10, 22, 8, 14, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())
    cutoff = int(datetime(2026, 10, 21, 12, 45, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())

    exits = claim_alerts.apply_contract_exits(
        [],
        [entry],
        morning,
        marks={"AAPL 10/21 342.5C": "0.18"},
    )

    assert exits[0]["close_at"] == cutoff
    assert exits[0]["premium"] == 0.18
    assert exits[0]["reason"] == "expiry"


def test_a_later_expiration_is_not_cut_on_the_entry_day():
    entry = _open_contract(contract="10/23 345C")
    moment = int(datetime(2026, 10, 21, 12, 50, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())

    assert claim_alerts.apply_contract_exits([], [entry], moment) == []


def test_a_clock_exit_after_the_cutoff_moves_to_twelve_forty_five():
    entry = _open_contract()
    clock = int(datetime(2026, 10, 21, 12, 50, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())
    cutoff = int(datetime(2026, 10, 21, 12, 45, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())
    event = {
        "kind": "exit",
        "ticker": "AAPL",
        "side": "call",
        "level": 340.0,
        "reason": "clock",
        "close_at": clock,
        "bar": _bar(clock - 600, 340.2, 340.8, 339.4, 339.9),
        "fill": None,
    }

    exits = claim_alerts.apply_contract_exits(
        [event],
        [entry],
        clock + 60,
        stock_bar=_priced_bar(cutoff),
        option_mark=lambda symbol, moment: 0.09,
    )

    assert len(exits) == 1
    assert exits[0]["reason"] == "expiry"
    assert exits[0]["close_at"] == cutoff
    assert exits[0]["premium"] == 0.09


def test_an_earlier_reclaim_stays_the_exit():
    entry = _open_contract()
    reclaim = int(datetime(2026, 10, 21, 10, 0, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())
    moment = int(datetime(2026, 10, 21, 12, 46, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())
    event = {
        "kind": "exit",
        "ticker": "AAPL",
        "side": "call",
        "level": 340.0,
        "reason": "reclaim",
        "close_at": reclaim,
        "bar": _bar(reclaim - 600, 341.0, 341.2, 339.4, 339.6),
        "fill": None,
    }

    exits = claim_alerts.apply_contract_exits([event], [entry], moment)

    assert len(exits) == 1
    assert exits[0]["reason"] == "reclaim"
    assert exits[0]["close_at"] == reclaim


def test_spx_is_not_cut_at_twelve_forty_five():
    entry = _open_contract(ticker="SPX", contract="10/21 6000C", fill="6001.00")
    at_cutoff = int(datetime(2026, 10, 21, 12, 45, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())
    clock = int(datetime(2026, 10, 21, 12, 50, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())
    session_end = int(datetime(2026, 10, 21, 13, 15, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())
    clock_event = {
        "kind": "exit",
        "ticker": "SPX",
        "side": "call",
        "level": 340.0,
        "reason": "clock",
        "close_at": clock,
        "bar": _bar(clock - 600, 6000, 6002, 5990, 5994),
        "fill": None,
    }

    assert claim_alerts.apply_contract_exits([], [entry], at_cutoff) == []
    kept = claim_alerts.apply_contract_exits([clock_event], [entry], clock + 60)
    assert kept[0]["reason"] == "clock"
    assert kept[0]["close_at"] == clock

    expired = claim_alerts.apply_contract_exits(
        [],
        [entry],
        session_end,
        option_mark=lambda symbol, moment: 1.25,
    )
    assert expired[0]["reason"] == "expiry"
    assert expired[0]["close_at"] == session_end
    assert "1:15" in claim_alerts.format_live(expired[0])


def test_a_closed_contract_is_not_exited_again():
    entry = _open_contract()
    closed = {
        "time": "2026-10-21 10:00 PT",
        "ticker": "AAPL",
        "action": "exit",
        "side": "call",
        "level": "340.00",
        "fill": "339.00",
        "contract": "10/21 342.5C",
        "premium": 0.20,
    }
    morning = int(datetime(2026, 10, 22, 8, 14, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())
    clock = int(datetime(2026, 10, 21, 12, 50, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())
    event = {
        "kind": "exit",
        "ticker": "AAPL",
        "side": "call",
        "level": 340.0,
        "reason": "clock",
        "close_at": clock,
        "bar": _bar(clock - 600, 340, 341, 339, 339.2),
        "fill": None,
    }

    assert claim_alerts.apply_contract_exits([], [entry, closed], morning) == []
    assert claim_alerts.apply_contract_exits([event], [entry, closed], morning) == []


def test_an_open_comparison_row_exits_when_the_contract_expires():
    path = Path("/tmp/autobonk-expired-contracts.md")
    path.write_text(
        claim_alerts.CONTRACTS_HEADER
        + "| 2026-10-21 07:30 PT | AAPL | 340.00 | chosen | 10/21 342.5C | 0.38 | 0.20 | -47.4% | open |\n"
        + "| 2026-10-21 07:30 PT | SPX | 6000.00 | chosen | 10/21 6000C | 1.00 | 1.10 | +10.0% | open |\n"
    )
    moment = int(datetime(2026, 10, 21, 12, 45, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())

    assert claim_alerts.close_expired_contracts(
        moment,
        path,
        option_mark=lambda symbol, at: 0.05,
    )

    rows = {row["ticker"]: row for row in claim_alerts.contract_rows(path.read_text())}
    assert rows["AAPL"]["state"] == "exit"
    assert rows["AAPL"]["price"] == "0.05"
    assert rows["SPX"]["state"] == "open"


def test_a_closed_contract_drops_its_open_mark():
    path = Path("/tmp/autobonk-marks.md")
    path.write_text(
        """
| Time | Ticker | Action | Side | Level | Fill | Reason | Contract | Premium |
|------|--------|--------|------|-------|------|--------|----------|---------|
| 2026-10-21 07:30 PT | AAPL | entry | call | 340.00 | 340.35 | retest | 10/21 342.5C | 0.38 |
| 2026-10-21 12:45 PT | AAPL | exit | call | 340.00 | 343.88 | expiry | 10/21 342.5C | 1.82 |

## Open marks

| Contract | Premium | As of | Source |
|----------|---------|-------|--------|
| AAPL 10/21 342.5C | 1.40 | 2026-10-21 13:51 PT | Yahoo |
"""
    )

    assert claim_alerts.refresh_open_marks(path, now=0)

    marks = path.read_text().split("## Open marks", 1)[1]
    assert "342.5C" not in marks
    assert "1.40" not in marks


def _pt(year, month, day, hour, minute):
    return int(
        datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp()
    )


def _stamp(close_at, close, atr=None):
    bar = _bar(close_at - 600, close, close + 0.2, close - 0.2, close)
    if atr is not None:
        bar["atr"] = atr
    return bar


def _open_row(**overrides):
    row = {
        "time": "2026-10-19 09:40 PT",
        "ticker": "AMZN",
        "action": "entry",
        "side": "call",
        "level": "261.00",
        "fill": "263.03",
        "reason": "sma",
        "contract": "none",
        "premium": None,
    }
    row.update(overrides)
    return row


def test_spcx_is_not_cut_at_twelve_forty_five():
    entry = _open_contract(
        ticker="SPCX",
        contract="10/22 146P",
        time="2026-10-22 08:30 PT",
        fill="149.80",
    )

    deadline = claim_alerts.contract_deadline(entry)

    assert deadline == datetime(2026, 10, 22, 13, 15, tzinfo=ZoneInfo("America/Los_Angeles"))


def test_a_none_contract_closes_on_the_twelve_fifty_bar():
    entry_at = _pt(2026, 10, 19, 9, 40)
    clock = _pt(2026, 10, 19, 12, 50)
    bars = [
        _stamp(entry_at, 263.03),
        _stamp(clock, 263.32),
    ]

    exits = claim_alerts.settle_open_entries(
        [_open_row()],
        [],
        clock,
        lambda ticker, at: bars,
    )

    assert len(exits) == 1
    assert exits[0]["reason"] == "clock"
    assert exits[0]["close_at"] == clock
    assert exits[0]["fill"] == 263.32
    assert exits[0]["kept"] is True
    assert "12:50" in claim_alerts.format_live(exits[0])


def test_a_reclaim_closes_before_the_clock():
    entry_at = _pt(2026, 10, 19, 9, 40)
    reclaim = _pt(2026, 10, 19, 10, 10)
    clock = _pt(2026, 10, 19, 12, 50)
    bars = [
        _stamp(entry_at, 263.03),
        _stamp(reclaim, 260.40),
        _stamp(clock, 263.32),
    ]

    exits = claim_alerts.settle_open_entries(
        [_open_row()],
        [],
        clock + 60,
        lambda ticker, at: bars,
    )

    assert len(exits) == 1
    assert exits[0]["reason"] == "reclaim"
    assert exits[0]["close_at"] == reclaim


def test_the_last_target_closes_and_the_first_does_not():
    entry_at = _pt(2026, 10, 19, 9, 40)
    tagged = _pt(2026, 10, 19, 10, 0)
    clock = _pt(2026, 10, 19, 12, 50)
    levels = [{"ticker": "AMZN", "price": 261, "allows": "long", "targets": [263.15, 265]}]
    held = [
        _stamp(entry_at, 263.03),
        _stamp(tagged, 264.00),
        _stamp(clock, 264.20),
    ]
    lost = [
        _stamp(entry_at, 263.03),
        _stamp(tagged, 265.40),
        _stamp(clock, 266.00),
    ]

    still_open = claim_alerts.settle_open_entries(
        [_open_row()], levels, clock, lambda ticker, at: held
    )
    closed = claim_alerts.settle_open_entries(
        [_open_row()], levels, clock, lambda ticker, at: lost
    )

    assert still_open[0]["reason"] == "clock"
    assert closed[0]["reason"] == "target"
    assert closed[0]["close_at"] == tagged


def test_a_close_inside_the_band_has_not_reclaimed():
    entry_at = _pt(2026, 10, 19, 9, 40)
    inside = _pt(2026, 10, 19, 10, 10)
    clock = _pt(2026, 10, 19, 12, 50)
    bars = [
        _stamp(entry_at, 263.03, atr=2),
        _stamp(inside, 260.10, atr=2),
        _stamp(clock, 262.00, atr=2),
    ]

    exits = claim_alerts.settle_open_entries(
        [_open_row()],
        [],
        clock,
        lambda ticker, at: bars,
    )

    assert exits[0]["reason"] == "clock"
    assert exits[0]["close_at"] == clock


def test_an_open_trade_stays_open_before_the_twelve_fifty_bar():
    moment = _pt(2026, 10, 19, 12, 40)

    assert (
        claim_alerts.settle_open_entries(
            [_open_row()],
            [],
            moment,
            lambda ticker, at: [_stamp(moment, 263)],
        )
        == []
    )


def test_a_closed_row_is_not_exited_again():
    rows = [
        _open_row(),
        {
            "time": "2026-10-19 10:10 PT",
            "ticker": "AMZN",
            "action": "exit",
            "side": "call",
            "level": "261.00",
            "fill": "260.40",
            "reason": "reclaim",
            "contract": "none",
            "premium": None,
        },
    ]

    assert (
        claim_alerts.settle_open_entries(
            rows,
            [],
            _pt(2026, 10, 19, 13, 0),
            lambda ticker, at: [],
        )
        == []
    )


def test_a_same_day_expiration_stays_with_the_cutoff():
    row = _open_row(contract="10/19 265C")

    assert (
        claim_alerts.settle_open_entries(
            [row],
            [],
            _pt(2026, 10, 19, 13, 0),
            lambda ticker, at: [_stamp(_pt(2026, 10, 19, 12, 50), 263)],
        )
        == []
    )


def test_a_later_expiration_still_leaves_at_the_clock():
    row = _open_row(contract="10/20 265C", ticker="SPCX", side="put", level="150.00")
    clock = _pt(2026, 10, 19, 12, 50)
    bars = [
        _stamp(_pt(2026, 10, 19, 9, 40), 149.80),
        _stamp(clock, 144.92),
    ]

    exits = claim_alerts.settle_open_entries(
        [row],
        [{"ticker": "SPCX", "price": 150, "allows": "short", "targets": [146.6, 138.6]}],
        clock,
        lambda ticker, at: bars,
    )

    assert exits[0]["reason"] == "clock"
    assert exits[0]["ticker"] == "SPCX"
    assert "Waiting for confirm" not in claim_alerts.live_notice(exits[0])
    assert "12:50" in claim_alerts.live_notice(exits[0])


def test_a_repeated_paper_exit_is_not_written_twice():
    path = Path("/tmp/autobonk-paper-dedupe.md")
    path.write_text(
        "# Paper trades\n\n"
        + claim_alerts.PAPER_HEADER
        + "| 2026-10-19 09:40 PT | AMZN | entry | call | 261.00 | 263.03 | sma | none | |\n"
    )
    event = {
        "kind": "exit",
        "ticker": "AMZN",
        "side": "call",
        "level": 261.0,
        "reason": "clock",
        "close_at": _pt(2026, 10, 19, 12, 50),
        "bar": _stamp(_pt(2026, 10, 19, 12, 50), 263.32),
        "fill": 263.32,
        "contract": "none",
        "premium": None,
    }

    claim_alerts.append_paper([event], path)
    claim_alerts.append_paper([event], path)

    text = path.read_text()
    assert text.count("| 2026-10-19 12:50 PT | AMZN | exit | call | 261.00 |") == 1


def test_a_missed_exit_premium_is_filled_on_the_next_check():
    path = Path("/tmp/autobonk-exit-premium.md")
    contracts = Path("/tmp/autobonk-exit-premium-contracts.md")
    path.write_text(
        "# Live\n\n"
        "| Time | Ticker | Action | Side | Level | Fill | Reason | Contract | Premium | Cash | Under $0.50 | Halfway |\n"
        "|------|--------|--------|------|-------|------|--------|----------|---------|------|-------------|---------|\n"
        "| 2026-10-22 08:30 PT | SPCX | entry | put | 150.00 | 149.80 | retest | 10/23 146P | 0.90 | over | 10/23 144P | past |\n"
        "| 2026-10-22 12:50 PT | SPCX | exit | put | 150.00 | 144.92 | clock | 10/23 146P | |  |  |  |\n"
    )
    contracts.write_text(
        claim_alerts.CONTRACTS_HEADER
        + "| 2026-10-22 08:30 PT | SPCX | 150.00 | chosen | 10/23 146P | 0.90 |  |  | exit |\n"
        + "| 2026-10-22 08:30 PT | SPCX | 150.00 | cash | 10/23 144P | 0.49 |  |  | exit |\n"
    )
    symbol = claim_alerts.option_symbol("SPCX", date(2026, 10, 23), 146, "put")
    cash = claim_alerts.option_symbol("SPCX", date(2026, 10, 23), 144, "put")

    def marker(name, moment):
        del moment
        return {symbol: 3.03, cash: 1.99}.get(name)

    assert claim_alerts.repair_exit_premiums(path, contracts, marker)
    assert not claim_alerts.repair_exit_premiums(path, contracts, marker)

    text = path.read_text()
    assert "| 10/23 146P | 3.03 |" in text
    assert "over" in text
    rows = {row["role"]: row for row in claim_alerts.contract_rows(contracts.read_text())}
    assert rows["chosen"]["price"] == "3.03"
    assert rows["chosen"]["return"] == "+236.7%"
    assert rows["cash"]["price"] == "1.99"


def test_an_exit_marks_the_dollar_strike_and_the_cash_strike():
    event = {
        "kind": "exit",
        "ticker": "SPCX",
        "side": "put",
        "level": 150.0,
        "reason": "clock",
        "close_at": int(datetime(2026, 10, 22, 12, 50, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp()),
        "fill": 144.92,
        "contract": "10/23 144P",
        "premium": 1.99,
        "dollar_contract": "10/23 146P",
        "dollar_premium": 3.03,
        "cash_contract": "10/23 144P",
        "cash_premium": 1.99,
        "bar": {"o": 145.10, "h": 145.20, "l": 144.80, "c": 144.92},
    }
    line = claim_alerts.live_line(event)
    assert "| 10/23 144P | 1.99 |  | 10/23 146P | 3.03 | 10/23 144P | 1.99 |  |" in line


def _atr_bar(start, open_, high, low, close, atr=1.0):
    bar = _bar(start, open_, high, low, close)
    bar["atr"] = atr
    return bar


def test_bounce_and_trend_are_paper_timings():
    level = {
        "ticker": "AAA",
        "price": 100,
        "allows": "both",
        "targets": [99],
        "up_targets": [102],
    }
    bounce_bars = [
        _atr_bar(0, 100.40, 100.50, 100.20, 100.30),
        _atr_bar(600, 100.30, 100.40, 99.90, 100.20),
        _atr_bar(1200, 100.20, 100.70, 100.10, 100.55),
        _atr_bar(1800, 100.55, 103.20, 100.50, 103.00),
    ]
    bounce = claim_alerts.regime_trades(bounce_bars, [level], kind="bounce")
    assert len(bounce) == 1
    assert bounce[0]["side"] == "call"
    assert bounce[0]["fill"] == 100.20
    assert bounce[0]["reason"] == "target"
    assert claim_alerts.bounce_side(bounce_bars[3], 100) is None

    trend_bars = [
        _atr_bar(0, 100.00, 100.20, 99.80, 100.00),
        _atr_bar(600, 100.00, 101.40, 99.90, 101.20),
        _atr_bar(1200, 100.40, 101.80, 100.30, 101.60),
        _atr_bar(1800, 101.60, 103.00, 101.40, 102.80),
    ]
    trend = claim_alerts.regime_trades(trend_bars, [level], kind="trend")
    assert len(trend) == 1
    assert trend[0]["retested"] is False
    assert trend[0]["reason"] == "target"
    assert trend[0]["fill"] == 100.40

    chased = [
        _atr_bar(0, 100.00, 100.20, 99.80, 100.00),
        _atr_bar(600, 100.00, 101.40, 99.90, 101.20),
        _atr_bar(1200, 101.20, 101.80, 101.00, 101.60),
    ]
    assert claim_alerts.regime_trades(chased, [level], kind="trend") == []

    clock = int(datetime(2026, 10, 22, 12, 40, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())
    returned = [
        _atr_bar(clock - 1800, 100.00, 100.20, 99.80, 100.00),
        _atr_bar(clock - 1200, 100.00, 101.40, 99.90, 101.20),
        _atr_bar(clock - 600, 100.40, 101.20, 100.30, 101.00),
        _atr_bar(clock, 101.00, 101.10, 99.90, 100.40),
        _atr_bar(clock + 600, 100.40, 100.50, 100.20, 100.30),
    ]
    back = claim_alerts.regime_trades(returned, [level], kind="trend")
    assert len(back) == 1
    assert back[0]["retested"] is True
    assert back[0]["reason"] == "clock"


def test_a_rate_limit_is_asked_again_and_a_blank_open_still_counts():
    import io
    import json
    import urllib.error

    calls = {"n": 0}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                {
                    "chart": {
                        "result": [
                            {
                                "timestamp": [100],
                                "indicators": {
                                    "quote": [
                                        {
                                            "open": [None],
                                            "high": [0.2],
                                            "low": [0.2],
                                            "close": [0.2],
                                        }
                                    ]
                                },
                            }
                        ]
                    }
                }
            ).encode()

    def urlopen(request, timeout=8):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(
                request.full_url, 429, "Too Many Requests", {}, io.BytesIO(b"")
            )
        return Response()

    original = claim_alerts.urllib.request.urlopen
    slept = claim_alerts.time.sleep
    claim_alerts.urllib.request.urlopen = urlopen
    claim_alerts.time.sleep = lambda seconds: None
    try:
        bars = claim_alerts.fetch_option_minutes("GOOGL261023C00327500")
    finally:
        claim_alerts.urllib.request.urlopen = original
        claim_alerts.time.sleep = slept

    assert calls["n"] == 2
    assert bars == [(100, 0.2, 0.2, 0.2, 0.2)]


def test_a_discord_refusal_does_not_stop_the_check():
    import io
    import urllib.error

    def boom(text):
        raise urllib.error.HTTPError(
            "https://discord.com", 429, "Too Many Requests", {}, io.BytesIO(b"")
        )

    original = claim_alerts.notify_discord
    claim_alerts.notify_discord = boom
    try:
        claim_alerts._send_alert("GOOGL call entry", True)
    finally:
        claim_alerts.notify_discord = original


def _cash_entry(contract="10/23 655C", premium=0.32, halfway="inside", close=None):
    when = close or datetime(2026, 10, 23, 9, 10, tzinfo=ZoneInfo("America/Los_Angeles"))
    rows = [
        {"role": "chosen", "contract": "10/23 650C", "premium": 1.00},
        {"role": "cash", "contract": contract, "premium": premium, "halfway": halfway},
    ]
    return {
        "kind": "entry",
        "ticker": "META",
        "side": "call",
        "level": 645.0,
        "reason": "retest",
        "close_at": int(when.timestamp()),
        "fill": 645.41,
        "contract": contract,
        "premium": premium,
        "contracts": rows,
        "cash": 40,
        "bar": {"o": 646.06, "h": 646.08, "l": 644.73, "c": 645.43, "purple": 52.09, "yellow": 54.07},
    }


class _Broker:
    def __init__(self, sell_result=None):
        self.buys = []
        self.sells = []
        self.sell_result = sell_result or {
            "sent": True,
            "order_id": "sell-1",
            "price": "0.02",
            "state": "filled",
        }

    def buy(self, ticker, label, year, ref_id, cash=None):
        self.buys.append((ticker, label, year, ref_id))
        return {"sent": True, "order_id": "buy-1", "price": "0.32", "state": "filled"}

    def sell(self, ticker, label, year, ref_id):
        self.sells.append((ticker, label, year, ref_id))
        return self.sell_result


def test_a_qualifying_live_entry_is_sent_once():
    book = Path("/tmp/autobonk-broker-once.json")
    book.unlink(missing_ok=True)
    broker = _Broker()
    event = _cash_entry()
    claim_alerts.route_live_order(event, broker, book)
    assert event["order_id"] == "buy-1"
    assert event["order_price"] == "0.32"
    assert len(broker.buys) == 1
    claim_alerts.route_live_order(dict(event), broker, book)
    assert len(broker.buys) == 1
    notice = claim_alerts.live_notice(event)
    assert "Order buy-1 at 0.32." in notice
    assert "Waiting for confirm" not in notice


def test_a_plan_is_not_sent_when_the_cash_strike_cannot_be_bought():
    book = Path("/tmp/autobonk-broker-skip.json")
    book.unlink(missing_ok=True)
    broker = _Broker()
    none = _cash_entry(contract="none", premium=None, halfway="")
    none["contracts"] = [
        {"role": "chosen", "contract": "10/23 650C", "premium": 1.00},
        {"role": "cash", "contract": "none", "premium": None},
    ]
    empty = _cash_entry()
    empty["contracts"] = []
    empty["contract"] = ""
    over = _cash_entry(premium=0.80)
    same_day = datetime(2026, 10, 23, 9, 10, tzinfo=ZoneInfo("America/Los_Angeles"))
    blocked = _cash_entry(contract="10/23 327.5C", halfway="past", close=same_day)
    assert claim_alerts.entry_order_block(none) == "none"
    assert claim_alerts.entry_order_block(empty) == "empty"
    assert claim_alerts.entry_order_block(over) == "over"
    assert claim_alerts.entry_order_block(blocked) == "halfway"
    for event in (none, empty, over, blocked):
        claim_alerts.route_live_order(event, broker, book)
    assert broker.buys == []
    wednesday = _cash_entry(
        close=datetime(2026, 10, 21, 9, 10, tzinfo=ZoneInfo("America/Los_Angeles"))
    )
    assert claim_alerts.entry_order_block(wednesday) == "paper"
    missed = _cash_entry()
    missed["cash"] = None
    assert claim_alerts.entry_order_block(missed) == "unread"
    claim_alerts.route_live_order(missed, broker, book)
    assert broker.buys == []
    assert "could not be read" in claim_alerts.live_notice(missed)


def test_an_exit_sells_an_open_contract_and_a_working_sell_is_not_repeated():
    book = Path("/tmp/autobonk-broker-sell.json")
    book.unlink(missing_ok=True)
    working = _Broker(sell_result={"sent": False, "reason": "working"})
    event = {
        "kind": "exit",
        "ticker": "GOOGL",
        "side": "call",
        "level": 322.75,
        "reason": "reclaim",
        "close_at": int(datetime(2026, 10, 23, 10, 30, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp()),
        "contract": "10/23 327.5C",
        "fill": 322.14,
        "bar": {"o": 322.45, "h": 322.54, "l": 322.08, "c": 322.14, "purple": 39.52, "yellow": 49.21},
    }
    claim_alerts.route_live_order(event, working, book)
    claim_alerts.route_live_order(dict(event), working, book)
    assert len(working.sells) == 1
    assert "order_id" not in event

    flat_book = Path("/tmp/autobonk-broker-flat.json")
    flat_book.unlink(missing_ok=True)
    flat = _Broker(sell_result={"sent": False, "reason": "flat"})
    claim_alerts.route_live_order(dict(event), flat, flat_book)
    assert len(flat.sells) == 1
    assert "order_id" not in event

    filled_book = Path("/tmp/autobonk-broker-filled.json")
    filled_book.unlink(missing_ok=True)
    filled = _Broker()
    sold = dict(event)
    claim_alerts.route_live_order(sold, filled, filled_book)
    assert sold["order_id"] == "sell-1"
    assert sold["order_price"] == "0.02"
    assert "Sold at 0.02." in claim_alerts.live_notice(sold)
