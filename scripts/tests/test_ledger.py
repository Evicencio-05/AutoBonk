"""Every signal becomes a ledger row. Broker fills set the dollars. Alarms fire on a contract that is not getting out."""

import importlib.util
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ledger = _load("ledger")
alarm = _load("alarm")
review = _load("review")
broker_mod = _load("robinhood_mcp")
claim = ledger.claim
claim.SEND_ORDERS = False
PT = ZoneInfo("America/Los_Angeles")


def _at(hour, minute, day=23):
    return int(datetime(2026, 10, day, hour, minute, tzinfo=PT).timestamp())


LIVE = """# Live plans

| Time | Ticker | Action | Side | Level | Fill | Reason | Contract | Premium | Cash | $1 strike | $1 premium | Cash strike | Cash premium | Halfway |
|------|--------|--------|------|-------|------|--------|----------|---------|------|-----------|------------|-------------|--------------|---------|
| 2026-10-23 09:40 PT | AVGO | entry | call | 324.60 | 324.92 | retest | 10/23 327.5C | 0.41 | fits | 10/23 327.5C | 0.41 | 10/23 327.5C | 0.41 | inside |
| 2026-10-23 10:30 PT | AVGO | exit | call | 324.60 | 323.96 | reclaim | 10/23 327.5C | |  | 10/23 327.5C |  | 10/23 327.5C |  |  |
| 2026-10-23 11:20 PT | AVGO | entry | call | 324.60 | 324.80 | retest | 10/23 327.5C | 0.18 | fits | 10/23 325C | 0.88 | 10/23 327.5C | 0.18 | inside |
| 2026-10-23 12:00 PT | AVGO | exit | call | 324.60 | 324.10 | reclaim | 10/23 327.5C | 0.10 |  | 10/23 325C |  | 10/23 327.5C |  |  |
| 2026-10-23 11:00 PT | GOOGL | entry | put | 322.75 | 322.42 | retest | 10/23 320P | 0.09 | fits | 10/23 322.5P | 0.75 | 10/23 320P | 0.09 | inside |
"""


def _order(order_id, effect, fill, at, option_id="opt-avgo", ticker="AVGO", contract=("2026-10-23", "327.5", "call"), placed="agentic"):
    return broker_mod.normal_order(
        {
            "id": order_id,
            "agent_initiated": placed == "agentic",
            "placed_agent": placed,
            "chain_symbol": ticker,
            "state": "filled",
            "direction": "debit" if effect == "open" else "credit",
            "price": f"{fill:.2f}",
            "processed_premium": f"{fill * 100:g}",
            "pending_quantity": "0",
            "created_at": at,
            "legs": [
                {
                    "side": "buy" if effect == "open" else "sell",
                    "position_effect": effect,
                    "option_id": option_id,
                    "expiration_date": contract[0],
                    "strike_price": contract[1],
                    "option_type": contract[2],
                    "executions": [{"price": f"{fill:.2f}", "quantity": "1", "timestamp": at}],
                }
            ],
        }
    )


class _Broker:
    def __init__(self, held=None, bars=None, orders=None):
        self._held = held or {}
        self._bars = bars or []
        self._orders = orders or []

    def held(self, option_id):
        return self._held.get(option_id)

    def option_bars(self, *args):
        return self._bars

    def find(self, *args):
        return "opt-plan"

    def agent_orders(self, since):
        return self._orders

    def late_closes(self):
        return {"AVGO"}

    def index_options(self):
        return set()

    def sellout(self, *args):
        return None


def _root(tmp_path, book=None):
    (tmp_path / "alerts").mkdir()
    (tmp_path / "learning" / "reviews").mkdir(parents=True)
    (tmp_path / "alerts" / "live.md").write_text(LIVE)
    import json

    (tmp_path / "alerts" / "broker.json").write_text(json.dumps(book or {}))
    return tmp_path


def test_contract_labels_match_the_checker():
    assert broker_mod.contract_label("2026-10-23", "327.5000", "call") == "10/23 327.5C"
    assert broker_mod.contract_label("2026-10-30", "377.0000", "put") == "10/30 377P"


def test_a_sold_trade_scores_broker_dollars_and_its_path(tmp_path):
    entry_id = claim.event_id("AVGO", {"kind": "entry", "side": "call", "level": 324.6, "close_at": _at(11, 20), "reason": "retest"})
    exit_id = claim.event_id("AVGO", {"kind": "exit", "side": "call", "level": 324.6, "close_at": _at(12, 0), "reason": "reclaim"})
    root = _root(tmp_path, {entry_id: {"order_id": "buy-1"}, exit_id: {"order_id": "sell-1"}})
    orders = [
        _order("buy-1", "open", 0.13, "2026-10-23T18:31:13Z"),
        _order("sell-1", "close", 0.10, "2026-10-23T19:01:00Z"),
    ]
    bars = [{"begins_at": "2026-10-23T18:30:00Z", "o": 0.13, "h": 0.16, "l": 0.10, "c": 0.12}]
    rows = ledger.build(root, orders, _Broker(bars=bars))
    live = [row for row in rows if row["mode"] == "live"]
    assert len(live) == 1
    trade = live[0]
    assert trade["dollars"] == -3.0 and trade["outcome"] == "sold"
    assert trade["mfe_dollars"] == 3.0 and trade["mae_dollars"] == -3.0
    assert trade["entry_slippage"] == -0.05
    assert trade["level_entry_number"] == 2 and trade["prior_stop_at_level"] is True


def test_a_contract_with_no_sell_is_scored_as_expired(tmp_path):
    entry_id = claim.event_id("GOOGL", {"kind": "entry", "side": "put", "level": 322.75, "close_at": _at(11, 0), "reason": "retest"})
    root = _root(tmp_path, {entry_id: {"order_id": "buy-2"}})
    orders = [_order("buy-2", "open", 0.12, "2026-10-22T18:11:00Z", "opt-g", "GOOGL", ("2026-10-22", "320", "put"))]
    rows = ledger.build(root, orders, _Broker())
    trade = next(row for row in rows if row["ticker"] == "GOOGL")
    assert trade["outcome"] == "expired" and trade["dollars"] == -12.0 and trade["exit_assumed"]


def test_a_fill_the_book_missed_still_lands_on_its_signal(tmp_path):
    root = _root(tmp_path)
    orders = [_order("buy-3", "open", 0.41, "2026-10-23T16:45:00Z")]
    rows = ledger.build(root, orders, _Broker())
    first = next(row for row in rows if row["entry_time"].endswith("09:40 PT"))
    assert first["mode"] == "live" and first["order_matched_by"] == "contract and time"
    assert not any(row["id"].startswith("broker|") for row in rows)


def test_a_signal_with_no_order_is_a_plan_with_a_counterfactual(tmp_path):
    root = _root(tmp_path)
    bars = [
        {"begins_at": "2026-10-23T16:40:00Z", "o": 0.41, "h": 0.50, "l": 0.30, "c": 0.35},
        {"begins_at": "2026-10-23T17:20:00Z", "o": 0.20, "h": 0.22, "l": 0.15, "c": 0.18},
    ]
    rows = ledger.build(root, [], _Broker(bars=bars))
    first = next(row for row in rows if row["entry_time"].endswith("09:40 PT"))
    assert first["mode"] == "plan" and first["no_order_reason"] == "not routed"
    assert first["plan_exit_premium"] == 0.18 and first["plan_dollars"] == -23.0
    assert first["plan_mfe_dollars"] == 9.0


def test_operator_answers_flow_back_into_the_ledger(tmp_path):
    root = _root(tmp_path)
    rows = ledger.build(root, [], None)
    ref = rows[0]["ref"]
    (root / "learning" / "reviews" / "2026-10-23.md").write_text(
        f"## Would I take it\n\n| Trade | Ticker | Entry | Mode | Take | Why |\n|---|---|---|---|---|---|\n"
        f"| `{ref}` | AVGO | 09:40 | plan | no | chop at the level |\n"
    )
    labeled = ledger.build(root, [], None)
    assert labeled[0]["operator_take"] == "no" and labeled[0]["operator_note"] == "chop at the level"


def test_summary_is_in_option_dollars():
    rows = [
        {"mode": "live", "dollars": 30.0},
        {"mode": "live", "dollars": -10.0},
        {"mode": "live", "dollars": -10.0},
        {"mode": "plan", "plan_dollars": 5.0},
    ]
    stats = ledger.summary(rows, "live")
    assert stats["trades"] == 3 and stats["net"] == 10.0 and stats["profit_factor"] == 1.5


def test_an_alarm_repeats_on_a_schedule_and_clears(tmp_path):
    path = tmp_path / "alarms.json"
    sent = []
    send = lambda key, text: sent.append(key)  # noqa: E731
    assert alarm.raise_alarm("x", "held", now=0, path=path, send=send)
    assert not alarm.raise_alarm("x", "held", now=60, path=path, send=send)
    assert alarm.raise_alarm("x", "held", now=alarm.REPEAT_SECONDS + 1, path=path, send=send)
    assert sent == ["x", "x"]
    assert alarm.clear_alarm("x", path=path) and not alarm.raised(path)


def test_a_contract_held_past_its_cutoff_raises_an_alarm(tmp_path):
    raised, cleared = [], []
    orders = [_order("buy-1", "open", 0.12, "2026-10-23T18:00:00Z", "opt-g", "GOOGL", ("2026-10-23", "320", "put"))]
    broker = _Broker(held={"opt-g": {"quantity": 1, "pending_sell": 0}}, orders=orders)
    texts = claim.audit_positions(
        _at(12, 51),
        broker=broker,
        book_path=tmp_path / "broker.json",
        raise_fn=lambda key, text, now=None: raised.append(key),
        clear_fn=cleared.append,
    )
    assert raised == ["open|opt-g"] and "still held" in texts[0]
    flat = _Broker(held={}, orders=orders)
    claim.audit_positions(
        _at(12, 51), broker=flat, book_path=tmp_path / "broker.json",
        raise_fn=lambda key, text, now=None: raised.append(key), clear_fn=cleared.append,
    )
    assert "open|opt-g" in cleared and raised == ["open|opt-g"]


def test_an_exit_that_keeps_failing_is_retried_and_raises_an_alarm(tmp_path):
    book = tmp_path / "broker.json"

    class Boom:
        def sell(self, *args):
            raise RuntimeError("down")

    event = {
        "kind": "exit", "ticker": "AVGO", "side": "call", "level": 324.6,
        "close_at": _at(12, 0), "reason": "reclaim", "contract": "10/23 327.5C",
    }
    for _ in range(4):
        claim.route_live_order(dict(event), broker=Boom(), book_path=book)
    record = next(iter(claim._broker_book(book).values()))
    assert record["status"] == "error" and record["attempts"] == 4
    raised = []
    claim.audit_positions(
        _at(12, 10), broker=_Broker(), book_path=book,
        raise_fn=lambda key, text, now=None: raised.append(key), clear_fn=lambda key: None,
    )
    assert raised and raised[0].startswith("exit|")


def test_a_redraft_keeps_the_operator_answers(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "REVIEWS", tmp_path)
    rows = [{"id": "a", "ref": "1023-0940-AVGO-call", "day": "2026-10-23", "mode": "plan", "ticker": "AVGO",
             "side": "call", "level": 324.6, "entry_time": "2026-10-23 09:40 PT", "close_at": _at(9, 40)}]
    first = review.day_review("2026-10-23", rows)
    filled = first.replace("| plan |  |  |", "| plan | no | chop |").replace(
        "## Lessons\n\nWhat repeated", "## Lessons\n\nRe-entries lost.\n\nWhat repeated"
    )
    (tmp_path / "2026-10-23.md").write_text(filled)
    again = review.day_review("2026-10-23", rows)
    assert "| plan | no | chop |" in again and "Re-entries lost." in again


def test_proposals_are_read_with_their_status_and_decision(tmp_path):
    data = _load("proposal_data")
    (tmp_path / "2026-10-30-x.md").write_text(
        "---\ntitle: Do a thing\nkind: decision\nstatus: open\ncreated: 2026-10-30\nrecommendation: wait\n---\n\n"
        "# Do a thing\n\n## Summary\nWhy.\n\n## Operator decision\nDecision: accept\nNotes: fine\n"
    )
    (tmp_path / "2026-10-31-y.md").write_text("---\ntitle: Undecided\nkind: safety\nstatus: open\n---\n\n## Operator decision\nDecision: <!-- accept / reject / wait -->\n")
    found = {p["title"]: p for p in data.proposals(tmp_path)}
    assert found["Do a thing"]["operator_decision"] == "accept" and found["Do a thing"]["recommendation"] == "wait"
    assert found["Undecided"]["operator_decision"] == "" and found["Undecided"]["kind"] == "safety"


def test_the_daily_safety_run_only_fires_on_a_day_an_alarm_was_sent(tmp_path):
    auto = _load("proposals_auto")
    log = tmp_path / "alarm_log.jsonl"
    friday = datetime(2026, 10, 23, 12, 51, tzinfo=PT)
    log.write_text(
        '{"key": "open|x", "text": "held past cutoff", "at": %d}\n{"key": "old", "text": "old", "at": %d}\n'
        % (friday.timestamp(), friday.timestamp() - 86400)
    )
    today = auto.alarms_today(friday, log)
    assert [item["key"] for item in today] == ["open|x"]
    assert auto.alarms_today(datetime(2026, 10, 26, 9, 0, tzinfo=PT), log) == []
    command = auto.command("hi")
    assert "dontAsk" in command and "Bash(git push:*)" in command


def test_proposal_markdown_renders_headings_lists_and_tables():
    page = review.ledger  # keep the import used
    from overview import markdown

    html = markdown("---\ntitle: t\n---\n\n# T\n\n## Summary\nOne **bold** line.\n\n- a\n- b\n\n| A | B |\n|---|---|\n| 1 | 2 |\n")
    assert "<h3>T</h3>" in html and "<strong>bold</strong>" in html
    assert html.count("<li>") == 2 and "<td>1</td>" in html and "title: t" not in html


def test_a_check_records_its_steps_and_first_order(tmp_path):
    clock = claim._StepClock()
    clock.lap("balance")
    clock.add("routing", 1.5)
    clock.ordered()
    clock.requests["option"] += 3
    path = tmp_path / "times.jsonl"
    clock.record(_at(11, 1), [{"kind": "entry"}, {"kind": "exit"}], path)
    line = __import__("json").loads(path.read_text())
    assert line["entries"] == 1 and line["exits"] == 1 and line["steps"]["routing"] == 1.5
    assert line["first_order_s"] is not None and line["requests"]["option"] == 3
    clock.record(_at(11, 1), [], tmp_path / "missing" / "times.jsonl")


def test_the_review_says_where_entry_checks_spend_their_time(tmp_path):
    import json

    path = tmp_path / "times.jsonl"
    path.write_text("\n".join(json.dumps(run) for run in (
        {"at": "2026-10-26T09:01", "total": 300.0, "first_order_s": 280.0, "entries": 1, "steps": {"pricing": 1.0, "sellouts": 250.0}},
        {"at": "2026-10-26T09:11", "total": 5.0, "first_order_s": None, "entries": 0, "steps": {"pricing": 0.0, "sellouts": 2.0}},
        {"at": "2026-10-25T09:11", "total": 99.0, "entries": 0, "steps": {"x": 99.0}},
    )))
    text = review.check_speed("2026-10-26", path)
    assert text.startswith("2 checks") and "first order after a median 280s" in text and "sellouts 250s" in text
    assert review.check_speed("2026-10-27", path) == "No timings recorded."


def test_robinhood_closing_an_expiring_contract_counts_as_the_exit(tmp_path):
    # 2026-10-23: the GOOGL 320P was bought at 0.12 and Robinhood's expiring-option close sold it at 0.24.
    entry_id = claim.event_id("GOOGL", {"kind": "entry", "side": "put", "level": 322.75, "close_at": _at(11, 0), "reason": "retest"})
    root = _root(tmp_path, {entry_id: {"order_id": "buy-2"}})
    contract = ("2026-10-23", "320", "put")
    orders = [
        _order("buy-2", "open", 0.12, "2026-10-23T18:11:11Z", "opt-g", "GOOGL", contract),
        _order("auto-1", "close", 0.24, "2026-10-23T19:30:58Z", "opt-g", "GOOGL", contract, placed="expiring_option"),
    ]
    rows = ledger.build(root, orders, _Broker())
    trade = next(row for row in rows if row["ticker"] == "GOOGL")
    assert trade["dollars"] == 12.0 and trade["outcome"] == "auto-closed"
    assert trade["exit_by"] == "Robinhood auto-close" and not trade.get("exit_assumed")


def test_a_sell_placed_by_hand_is_the_exit_too(tmp_path):
    entry_id = claim.event_id("GOOGL", {"kind": "entry", "side": "put", "level": 322.75, "close_at": _at(11, 0), "reason": "retest"})
    root = _root(tmp_path, {entry_id: {"order_id": "buy-2"}})
    contract = ("2026-10-23", "320", "put")
    orders = [
        _order("buy-2", "open", 0.12, "2026-10-23T18:11:11Z", "opt-g", "GOOGL", contract),
        _order("hand-1", "close", 0.30, "2026-10-23T19:00:00Z", "opt-g", "GOOGL", contract, placed="manual"),
    ]
    trade = next(row for row in ledger.build(root, orders, _Broker()) if row["ticker"] == "GOOGL")
    assert trade["dollars"] == 18.0 and trade["outcome"] == "sold by hand"


def test_the_bar_counts_only_todays_watches(tmp_path):
    bar = _load("bar_status")
    (tmp_path / "alerts").mkdir()
    (tmp_path / "alerts" / "log.md").write_text(
        "# Alert log\n"
        "- PLTR put watch 200.00 at 2026-10-23 09:10 PT. Candle green O 1 H 1 L 1 C 1. Not a fill. Not an order.\n"
    )
    friday = bar.status(tmp_path, datetime(2026, 10, 23, 12, 0, tzinfo=PT))
    monday = bar.status(tmp_path, datetime(2026, 10, 26, 6, 0, tzinfo=PT))
    assert friday["counts"]["watches"] == 1 and monday["counts"]["watches"] == 0


def test_the_close_run_pings_its_own_check(monkeypatch):
    seen = []
    monkeypatch.setattr(alarm, "heartbeat", lambda fail=False, body="", name="": seen.append(name))
    alarm.main(["ping", "AUTOBONK_CLOSE_HEARTBEAT_URL"])
    assert seen == ["AUTOBONK_CLOSE_HEARTBEAT_URL"]
