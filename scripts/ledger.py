#!/usr/bin/env python3
"""One row per trade, built from what the checker saw and what the broker filled.

  python3 scripts/ledger.py sync              # rebuild learning/trades.jsonl and .csv
  python3 scripts/ledger.py sync --offline    # same, without asking the broker
  python3 scripts/ledger.py snapshot          # save today's bars and book as a bench fixture
  python3 scripts/ledger.py show              # totals in option dollars

Every checker entry becomes a row, whether or not an order went out:

  mode live   an Agentic order was sent. Fills, dollars, and the option's path come from the broker.
  mode plan   a live session, but no order (balance, halfway, ladder). Plan premiums are the counterfactual.
  mode paper  a paper session. Plan premiums only.

A broker order with no checker entry still gets a row, so a manual fill is never lost.
The operator's "would I take it" answers in learning/reviews/*.md are read back
onto each row. Nothing here places an order or changes the checker.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import claim_alerts as claim  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PT = ZoneInfo("America/Los_Angeles")
UTC = timezone.utc
TRADES_PATH = ROOT / "learning" / "trades.jsonl"
CSV_PATH = ROOT / "learning" / "trades.csv"
REVIEWS = ROOT / "learning" / "reviews"
FIXTURES = ROOT / "bench" / "fixtures"
OPEN_AT = (6, 30)
FIRST_LIVE = "2026-10-22T00:00:00Z"

CSV_COLUMNS = (
    "id", "mode", "day", "entry_time", "ticker", "side", "level", "reason", "contract", "dte",
    "moneyness_pct", "stock_fill", "candle", "purple", "yellow", "rsi_gap", "sma20_gap",
    "level_entry_number", "prior_stop_at_level", "minutes_since_level_exit", "level_flips_before",
    "minutes_after_open", "cash", "cash_fit", "halfway", "no_order_reason",
    "plan_entry_premium", "plan_exit_premium", "plan_dollars",
    "entry_fill", "exit_fill", "dollars", "return_pct", "entry_slippage", "entry_latency_s",
    "mfe_dollars", "mae_dollars", "exit_time", "exit_reason", "stock_exit", "stock_points",
    "hold_minutes", "outcome", "operator_take", "operator_note",
)


# ---- reading the tapes ------------------------------------------------------


def table_rows(text: str) -> list[dict]:
    """Every markdown table row in text, keyed by its header. The Open marks block is skipped."""
    rows: list[dict] = []
    header: list[str] | None = None
    for line in text.split("\n## Open marks\n", 1)[0].splitlines():
        if not line.startswith("|"):
            header = None if not line.strip() else header
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and cells[0] == "Time":
            header = cells
            continue
        if header is None or not cells or set(cells[0]) <= {"-", ":"}:
            continue
        rows.append(dict(zip(header, cells + [""] * (len(header) - len(cells)))))
    return rows


def _read(path: Path) -> str:
    return path.read_text() if path.is_file() else ""


def _float(text) -> float | None:
    if text in (None, ""):
        return None
    try:
        return float(str(text).replace(",", "").split()[0])
    except (TypeError, ValueError, IndexError):
        return None


def _clock(text: str) -> int | None:
    try:
        return int(claim._row_clock(text).timestamp())
    except (ValueError, AttributeError):
        return None


def _gap(cell: str) -> float | None:
    """'324.94 (-0.84)' -> -0.84, the stock minus the average."""
    found = re.search(r"\(([-+]?\d+(\.\d+)?)\)", cell or "")
    return float(found.group(1)) if found else None


def _trade_id(ticker: str, kind: str, side: str, level: float, close_at: int, reason: str) -> str:
    return claim.event_id(
        ticker, {"kind": kind, "side": side, "level": level, "close_at": close_at, "reason": reason}
    )


def _events(path: Path) -> dict[str, dict]:
    found = {}
    for line in _read(path).splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        found[record.get("id") or ""] = record
    return found


def _flips(fired: list[str]) -> dict[tuple[str, float, str], list[int]]:
    """Claim and lose closes per ticker, level, and PT day, from the checker's state."""
    found: dict[tuple[str, float, str], list[int]] = {}
    for identity in fired:
        parts = identity.split("|")
        if len(parts) != 4 or parts[1] not in ("claim", "lose"):
            continue
        try:
            level, at = float(parts[2]), int(parts[3])
        except ValueError:
            continue
        day = datetime.fromtimestamp(at, PT).date().isoformat()
        found.setdefault((parts[0], level, day), []).append(at)
    return found


def signal_trades(root: Path = ROOT) -> list[dict]:
    """Entries paired with their exits from the live and paper tapes, with the candle context."""
    context = {}
    for row in table_rows(_read(root / "alerts" / "context.md")):
        key = (row.get("Time"), row.get("Ticker"), row.get("Action"), row.get("Side"), row.get("Level"))
        context[key] = row
    trades = []
    for name in ("live", "paper"):
        opens: list[dict] = []
        for row in table_rows(_read(root / "alerts" / f"{name}.md")):
            close_at = _clock(row.get("Time", ""))
            level = _float(row.get("Level"))
            if close_at is None or level is None:
                continue
            ctx = context.get((row["Time"], row.get("Ticker"), row.get("Action"), row.get("Side"), row.get("Level"))) or {}
            if row.get("Action") == "entry":
                opens.append(
                    {
                        "id": _trade_id(row["Ticker"], "entry", row["Side"], level, close_at, row.get("Reason", "")),
                        "tape": name,
                        "ticker": row["Ticker"],
                        "side": row["Side"],
                        "level": level,
                        "reason": row.get("Reason", ""),
                        "close_at": close_at,
                        "entry_time": row["Time"],
                        "stock_fill": _float(row.get("Fill")),
                        "contract": row.get("Contract") or "",
                        "plan_entry_premium": _float(row.get("Premium")),
                        "cash_fit": row.get("Cash", ""),
                        "halfway": row.get("Halfway", ""),
                        "context": ctx,
                    }
                )
                continue
            if row.get("Action") != "exit":
                continue
            match = next(
                (
                    open_row
                    for open_row in opens
                    if open_row["ticker"] == row.get("Ticker")
                    and open_row["side"] == row.get("Side")
                    and open_row["level"] == level
                    and open_row["close_at"] <= close_at
                ),
                None,
            )
            if match is None:
                continue
            opens.remove(match)
            match.update(
                {
                    "exit_close_at": close_at,
                    "exit_time": row["Time"],
                    "exit_reason": row.get("Reason", ""),
                    "stock_exit": _float(row.get("Fill")),
                    "plan_exit_premium": _float(row.get("Premium")),
                    "exit_id": _trade_id(row["Ticker"], "exit", row["Side"], level, close_at, row.get("Reason", "")),
                }
            )
            trades.append(match)
        trades.extend(opens)
    return trades


# ---- features ---------------------------------------------------------------


def _expiration(contract: str, entry_time: str) -> date | None:
    return claim.contract_expiration({"contract": contract, "time": entry_time})


def _strike(contract: str) -> float | None:
    parts = (contract or "").split()
    if len(parts) != 2 or not parts[1] or parts[1][-1] not in "CP":
        return None
    return _float(parts[1][:-1])


def features(trade: dict, everyone: list[dict], flips: dict, event: dict | None) -> dict:
    """What was knowable at the entry close. Nothing after the entry is used here."""
    when = datetime.fromtimestamp(trade["close_at"], PT)
    day = when.date().isoformat()
    ctx = trade.get("context") or {}
    bar = (event or {}).get("bar") or {}
    purple = bar.get("purple", _float(ctx.get("Purple")))
    yellow = bar.get("yellow", _float(ctx.get("Yellow")))
    candle = (ctx.get("Candle") or "").split(" ")[0] or None
    if bar.get("o") is not None and bar.get("c") is not None:
        candle = "green" if bar["c"] > bar["o"] else "red" if bar["c"] < bar["o"] else "flat"
    same_level = [
        other
        for other in everyone
        if other["ticker"] == trade["ticker"]
        and other["level"] == trade["level"]
        and datetime.fromtimestamp(other["close_at"], PT).date().isoformat() == day
        and other["close_at"] < trade["close_at"]
    ]
    exits = [other["exit_close_at"] for other in same_level if other.get("exit_close_at") and other["exit_close_at"] <= trade["close_at"]]
    stopped = [other for other in same_level if other.get("exit_reason") == "reclaim" and (other.get("exit_close_at") or 0) <= trade["close_at"]]
    expiration = _expiration(trade.get("contract", ""), trade.get("entry_time", ""))
    strike = _strike(trade.get("contract", ""))
    fill = trade.get("stock_fill")
    moneyness = None
    if strike and fill:
        signed = (strike - fill) if trade["side"] == "call" else (fill - strike)
        moneyness = round(100 * signed / fill, 3)
    open_at = when.replace(hour=OPEN_AT[0], minute=OPEN_AT[1], second=0)
    return {
        "day": day,
        "weekday": when.strftime("%a"),
        "minutes_after_open": int((when - open_at).total_seconds() // 60),
        "candle": candle,
        "purple": purple,
        "yellow": yellow,
        "rsi_gap": round(purple - yellow, 2) if purple is not None and yellow is not None else None,
        "sma20_gap": _gap(ctx.get("SMA20", "")),
        "sma50_gap": _gap(ctx.get("SMA50", "")),
        "sma200_gap": _gap(ctx.get("SMA200", "")),
        "volume": _float(ctx.get("Volume")),
        "nearby": ctx.get("Nearby") or None,
        "targets": (event or {}).get("targets"),
        "cash": (event or {}).get("cash"),
        "dte": (expiration - when.date()).days if expiration else None,
        "moneyness_pct": moneyness,
        "level_entry_number": len(same_level) + 1,
        "prior_stop_at_level": bool(stopped),
        "minutes_since_level_exit": int((trade["close_at"] - max(exits)) // 60) if exits else None,
        "level_flips_before": len(
            [at for at in flips.get((trade["ticker"], trade["level"], day), []) if at <= trade["close_at"]]
        ),
    }


# ---- broker -----------------------------------------------------------------


def _at(text: str) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _path_extremes(bars: list[dict]) -> tuple[float | None, float | None]:
    if not bars:
        return None, None
    return max(bar["h"] for bar in bars), min(bar["l"] for bar in bars)


def attach_orders(trades: list[dict], orders: list[dict], book: dict, broker=None) -> list[dict]:
    """Put each broker fill on its checker entry. Unclaimed fills become their own rows."""
    by_id = {order["id"]: order for order in orders}
    claimed: set[str] = set()
    reserved = {record.get("order_id") for record in book.values() if record.get("order_id")}
    for trade in trades:
        entry_record = book.get(trade["id"]) or {}
        exit_record = book.get(trade.get("exit_id") or "") or {}
        buy = by_id.get(entry_record.get("order_id") or "")
        if trade["tape"] == "paper":
            trade["mode"] = "paper"
            continue
        if not buy:
            # An order the broker book did not keep: same name, side, and contract, placed within 45 minutes.
            nearby = [
                order
                for order in orders
                if order["id"] not in claimed
                and order["id"] not in reserved
                and order["effect"] == "open"
                and order["filled_quantity"]
                and order["ticker"] == trade["ticker"]
                and order["option_type"] == trade["side"]
                and (not trade.get("contract") or order["contract"] == trade["contract"])
                and 0 <= ((_at(order["created_at"]) or datetime.min.replace(tzinfo=UTC)).timestamp() - trade["close_at"]) <= 2700
            ]
            buy = nearby[0] if nearby else None
            if buy:
                trade["order_matched_by"] = "contract and time"
        if not buy:
            trade["mode"] = "plan"
            _counterfactual(trade, broker)
            trade["no_order_reason"] = (
                entry_record.get("broker_reason")
                or entry_record.get("status")
                or ("over balance" if trade.get("cash_fit") == "over" else "")
                or ("past halfway" if trade.get("halfway") == "past" else "")
                or "not routed"
            )
            continue
        trade["mode"] = "live"
        claimed.add(buy["id"])
        sell = by_id.get(exit_record.get("order_id") or "")
        if sell is None:
            sell = next(
                (
                    order
                    for order in orders
                    if order["option_id"] == buy["option_id"]
                    and order["effect"] == "close"
                    and order["filled_quantity"]
                    and (order["created_at"] or "") >= (buy["created_at"] or "")
                ),
                None,
            )
        if sell:
            claimed.add(sell["id"])
        _fill_trade(trade, buy, sell, broker)
    for order in orders:
        if order["id"] in claimed or order["effect"] != "open" or not order["filled_quantity"]:
            continue
        opened = _at(order["filled_at"] or order["created_at"]) or datetime.now(UTC)
        sell = next(
            (
                other
                for other in orders
                if other["option_id"] == order["option_id"]
                and other["effect"] == "close"
                and other["id"] not in claimed
                and other["filled_quantity"]
            ),
            None,
        )
        if sell:
            claimed.add(sell["id"])
        when = opened.astimezone(PT)
        orphan = {
            "id": f"broker|{order['id']}",
            "tape": "broker",
            "mode": "live",
            "ticker": order["ticker"],
            "side": order["option_type"],
            "level": None,
            "reason": "manual" if order.get("initiator", "agent") != "agent" else "unmatched",
            "close_at": int(when.timestamp()),
            "entry_time": when.strftime("%Y-%m-%d %H:%M PT"),
            "contract": order["contract"],
            "context": {},
        }
        _fill_trade(orphan, order, sell, broker)
        trades.append(orphan)
    return trades


def _bar_close_at(bars: list[dict], moment: int) -> float | None:
    """The close of the last 5-minute option bar that ended by moment."""
    best = None
    for bar in bars:
        start = _at(bar["begins_at"])
        if start and start.timestamp() + 300 <= moment:
            best = bar["c"]
    return best


def _counterfactual(trade: dict, broker) -> None:
    """What the plan contract did, from the broker's option bars. Nothing is bought."""
    if broker is None or not trade.get("contract") or trade.get("contract") == "none":
        return
    if trade.get("plan_exit_premium") is not None and trade.get("plan_mfe_dollars") is not None:
        return
    year = datetime.fromtimestamp(trade["close_at"], PT).year
    try:
        option_id = broker.find(trade["ticker"], trade["contract"], year)
    except Exception:  # noqa: BLE001
        return
    if not option_id:
        return
    end = trade.get("exit_close_at") or trade["close_at"] + 6 * 3600
    try:
        bars = broker.option_bars(
            option_id,
            datetime.fromtimestamp(trade["close_at"] - 300, UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            datetime.fromtimestamp(end + 600, UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
    except Exception:  # noqa: BLE001
        return
    held = [bar for bar in bars if (_at(bar["begins_at"]) or datetime.max.replace(tzinfo=UTC)).timestamp() < end]
    entry = trade.get("plan_entry_premium")
    if trade.get("plan_exit_premium") is None and trade.get("exit_close_at"):
        price = _bar_close_at(bars, trade["exit_close_at"])
        if price is not None:
            trade["plan_exit_premium"] = price
            trade["plan_exit_from"] = "option bars"
    high, low = _path_extremes(held)
    if entry is not None and high is not None:
        trade["plan_mfe_dollars"] = round((high - entry) * 100, 2)
        trade["plan_mae_dollars"] = round((low - entry) * 100, 2)


def _fill_trade(trade: dict, buy: dict, sell: dict | None, broker) -> None:
    trade["entry_order"] = buy["id"]
    trade["entry_fill"] = buy["fill"]
    trade["entry_dollars"] = buy["premium"]
    trade["contract"] = buy["contract"] or trade.get("contract")
    filled_at = _at(buy["filled_at"])
    if filled_at:
        trade["entry_latency_s"] = int(filled_at.timestamp() - trade["close_at"])
    if trade.get("plan_entry_premium") is not None and buy["fill"] is not None:
        trade["entry_slippage"] = round(buy["fill"] - trade["plan_entry_premium"], 4)
    end = None
    if sell and sell["filled_quantity"]:
        trade["exit_order"] = sell["id"]
        trade["exit_fill"] = sell["fill"]
        trade["exit_dollars"] = sell["premium"]
        # Who sold it matters for the review: the checker, Robinhood's expiring-option close, or you.
        initiator = sell.get("initiator") or "agent"
        trade["exit_by"] = {"agent": "checker", "expiring_option": "Robinhood auto-close"}.get(initiator, "by hand")
        trade["outcome"] = "sold" if initiator == "agent" else "auto-closed" if initiator == "expiring_option" else "sold by hand"
        end = _at(sell["filled_at"])
    else:
        expiration = date.fromisoformat(buy["expiration"]) if buy["expiration"] else None
        held = None
        if broker is not None:
            try:
                held = broker.held(buy["option_id"])
            except Exception:  # noqa: BLE001
                held = None
        if held and held["quantity"] > 0:
            trade["outcome"] = "open"
        elif expiration and expiration < datetime.now(PT).date() or (
            expiration == datetime.now(PT).date() and datetime.now(PT).hour >= 13
        ):
            # Flat with no sell: it expired. Worthless unless the last stock print was past the strike.
            stock = trade.get("stock_exit")
            strike = buy["strike"]
            intrinsic = 0.0
            if stock is not None and strike is not None:
                intrinsic = max(0.0, (stock - strike) if buy["option_type"] == "call" else (strike - stock))
            trade["outcome"] = "expired"
            trade["exit_fill"] = round(intrinsic, 2)
            trade["exit_dollars"] = round(intrinsic * 100, 2)
            trade["exit_assumed"] = True
            end = datetime(expiration.year, expiration.month, expiration.day, 13, 0, tzinfo=PT)
        else:
            trade["outcome"] = "unknown"
    if trade.get("entry_dollars") is not None and trade.get("exit_dollars") is not None:
        trade["dollars"] = round(trade["exit_dollars"] - trade["entry_dollars"], 2)
        if trade["entry_dollars"]:
            trade["return_pct"] = round(100 * trade["dollars"] / trade["entry_dollars"], 1)
    if broker is not None and filled_at and buy["fill"] is not None and not trade.get("mfe_dollars"):
        stop = end or datetime.now(UTC)
        try:
            bars = broker.option_bars(
                buy["option_id"],
                (filled_at - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                stop.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
        except Exception:  # noqa: BLE001
            bars = []
        high, low = _path_extremes(bars)
        if high is not None:
            trade["mfe_dollars"] = round((high - buy["fill"]) * 100, 2)
            trade["mae_dollars"] = round((low - buy["fill"]) * 100, 2)
            trade["option_bars"] = len(bars)


# ---- operator labels --------------------------------------------------------

_LABEL_HEADER = "## Would I take it"


def operator_labels(reviews: Path = REVIEWS) -> dict[str, dict]:
    """trade id -> {take, note} from each review's "Would I take it" table."""
    found: dict[str, dict] = {}
    for path in sorted(reviews.glob("*.md")):
        text = path.read_text()
        if _LABEL_HEADER not in text:
            continue
        block = text.split(_LABEL_HEADER, 1)[1].split("\n## ", 1)[0]
        for line in block.splitlines():
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) < 3 or not cells[0].startswith("`"):
                continue
            take = cells[-2].lower()
            if take not in ("yes", "no", "unsure"):
                continue
            found[cells[0].strip("`")] = {"take": take, "note": cells[-1].replace("\\|", "|")}
    return found


# ---- build ------------------------------------------------------------------


def _clean(trade: dict) -> dict:
    trade = dict(trade)
    trade.pop("context", None)
    trade.pop("tape", None)
    when = datetime.fromtimestamp(trade["close_at"], PT)
    # A short handle with no pipes, for review tables. The id stays the checker's event id.
    trade["ref"] = f"{when:%m%d}-{when:%H%M}-{trade['ticker']}-{trade.get('side') or ''}"
    if trade.get("plan_entry_premium") is not None and trade.get("plan_exit_premium") is not None:
        trade["plan_dollars"] = round((trade["plan_exit_premium"] - trade["plan_entry_premium"]) * 100, 2)
    if trade.get("stock_fill") is not None and trade.get("stock_exit") is not None:
        move = trade["stock_exit"] - trade["stock_fill"]
        trade["stock_points"] = round(move if trade["side"] == "call" else -move, 2)
    if trade.get("exit_close_at"):
        trade["hold_minutes"] = int((trade["exit_close_at"] - trade["close_at"]) // 60)
    trade.setdefault("outcome", "closed" if trade.get("exit_time") else "open")
    return trade


def build(root: Path = ROOT, orders: list[dict] | None = None, broker=None) -> list[dict]:
    trades = signal_trades(root)
    events = _events(root / "alerts" / "events.jsonl")
    try:
        fired = json.loads(_read(root / "alerts" / "state.json") or "{}").get("fired") or []
    except json.JSONDecodeError:
        fired = []
    flips = _flips(fired)
    for trade in trades:
        trade.update(features(trade, trades, flips, events.get(trade["id"])))
    book = claim._broker_book(root / "alerts" / "broker.json")
    trades = attach_orders(trades, orders or [], book, broker)
    labels = operator_labels(root / "learning" / "reviews")
    previous = {row["id"]: row for row in load(root / "learning" / "trades.jsonl")}
    out = []
    for trade in trades:
        if "day" not in trade:
            trade.update(features(trade, [], {}, None))
        row = _clean(trade)
        kept = previous.get(row["id"]) or {}
        for name in ("mfe_dollars", "mae_dollars", "option_bars"):
            if row.get(name) is None and kept.get(name) is not None:
                row[name] = kept[name]
        for name in ("plan_exit_premium", "plan_exit_from", "plan_mfe_dollars", "plan_mae_dollars"):
            if row.get(name) is None and kept.get(name) is not None:
                row[name] = kept[name]
        if row.get("plan_dollars") is None and row.get("plan_entry_premium") is not None and row.get("plan_exit_premium") is not None:
            row["plan_dollars"] = round((row["plan_exit_premium"] - row["plan_entry_premium"]) * 100, 2)
        label = labels.get(row["ref"]) or labels.get(row["id"])
        if label:
            row["operator_take"] = label["take"]
            row["operator_note"] = label["note"]
        out.append(row)
    out.sort(key=lambda row: (row["close_at"], row["id"]))
    return out


def load(path: Path = TRADES_PATH) -> list[dict]:
    rows = []
    for line in _read(path).splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def write(rows: list[dict], path: Path = TRADES_PATH, csv_path: Path = CSV_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True, default=str) + "\n" for row in rows))
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in CSV_COLUMNS})


def summary(rows: list[dict], mode: str = "live") -> dict:
    """Option-dollar totals for one mode. Plan and paper use plan premiums."""
    key = "dollars" if mode == "live" else "plan_dollars"
    scored = [row[key] for row in rows if row.get("mode") == mode and row.get(key) is not None]
    wins = [value for value in scored if value > 0]
    losses = [value for value in scored if value <= 0]
    gross_loss = -sum(losses)
    return {
        "mode": mode,
        "trades": len(scored),
        "net": round(sum(scored), 2),
        "win_rate": round(100 * len(wins) / len(scored), 1) if scored else None,
        "avg_win": round(sum(wins) / len(wins), 2) if wins else None,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else None,
        "expectancy": round(sum(scored) / len(scored), 2) if scored else None,
        "profit_factor": round(sum(wins) / gross_loss, 2) if gross_loss else None,
    }


# ---- fixtures ---------------------------------------------------------------


def snapshot(day: date, root: Path = ROOT, fetch=None) -> list[Path]:
    """Freeze one live day's 10-minute bars and its armed book under bench/fixtures.

    The replay set grows by a day each session, and the freeze check covers it.
    A day whose book was not armed that morning is not saved.
    """
    levels_path = root / "alerts" / "levels.yaml"
    spec = claim.load_levels(levels_path)
    if spec["armed_at"].astimezone(PT).date() != day:
        return []
    fetch = fetch or claim.fetch_five_minute
    end = int(datetime(day.year, day.month, day.day, 13, 10, tzinfo=PT).timestamp())
    start = int(datetime(day.year, day.month, day.day, 0, 0, tzinfo=PT).timestamp())
    tickers = []
    for level in spec["levels"]:
        if level["ticker"] not in tickers:
            tickers.append(level["ticker"])
    book = {}
    for ticker in tickers:
        bars = claim.ten_minute_bars(fetch(ticker), end)
        book[ticker] = [
            {key: bar[key] for key in ("close_at", "o", "h", "l", "c")}
            for bar in bars
            if start - 3 * 86400 <= bar["close_at"] <= end
        ]
    target = root / "bench" / "fixtures"
    target.mkdir(parents=True, exist_ok=True)
    levels_out = target / f"{day.isoformat()}-levels.yaml"
    bars_out = target / f"{day.isoformat()}-bars.json"
    levels_out.write_text(levels_path.read_text())
    bars_out.write_text(json.dumps({"tickers": book}) + "\n")
    return [levels_out, bars_out]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sync_cmd = sub.add_parser("sync")
    sync_cmd.add_argument("--offline", action="store_true")
    snap = sub.add_parser("snapshot")
    snap.add_argument("--day", default=datetime.now(PT).date().isoformat())
    sub.add_parser("show")
    args = parser.parse_args(argv)
    if args.command == "sync":
        broker = None
        orders: list[dict] = []
        if not args.offline:
            from robinhood_mcp import RobinhoodBroker

            broker = RobinhoodBroker()
            orders = broker.account_orders(FIRST_LIVE)
        rows = build(orders=orders, broker=broker)
        write(rows)
        print(f"{len(rows)} trades -> {TRADES_PATH.relative_to(ROOT)} and {CSV_PATH.relative_to(ROOT)}")
        import alarm
        import blotter

        snapshot_payload = {"rows": rows, "alarms": alarm.raised(), "updated_at": datetime.now(PT).isoformat()}
        if blotter.store_ledger(snapshot_payload):
            print("Snapshot stored for the hosted desk.")
        for mode in ("live", "plan", "paper"):
            print(summary(rows, mode))
        return 0
    if args.command == "snapshot":
        saved = snapshot(date.fromisoformat(args.day))
        print("\n".join(str(path.relative_to(ROOT)) for path in saved) or "No book armed that day.")
        return 0
    rows = load()
    for mode in ("live", "plan", "paper"):
        print(summary(rows, mode))
    return 0


if __name__ == "__main__":
    sys.exit(main())
