#!/usr/bin/env python3
"""Alert a retest entry, an exit, or a skipped fill.

A qualifying live entry is sent on the Agentic account. So is the sell when
that contract is still open. Anything else stays a plan.

Yahoo has no 10-minute bars. Two finished 5-minute bars are one 10-minute
bar. A claim or a lose is a close beyond the level by half the 14-period ATR.
A close inside that band has not broken the level. That same close flips
the level: a lost support is resistance, and a claimed resistance is support.
A wick within 15 cents only counts as the touch. The fill is the next bar's open.
A contract is out at its broker sellout when the instrument has one.
Otherwise a late-close name is out at 12:45 PT, any other equity option at
12:30 PT, and an index at 1:00 PM PT. If that list cannot be read, the equity
cutoff stays 12:45 PT so the checker does not sell early. An open row past
that cutoff is closed on a later check. A contract with no expiration still
leaves on the 12:50 bar. That close does not add an entry from an old book.
RSI is printed and does not block.

  python3 scripts/claim_alerts.py check
  python3 scripts/claim_alerts.py check --notify
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import subprocess
import time
import uuid
import urllib.error
from concurrent.futures import ThreadPoolExecutor
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

import sys

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import alarm  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LEVELS_PATH = ROOT / "alerts" / "levels.yaml"
STATE_PATH = ROOT / "alerts" / "state.json"
LOG_PATH = ROOT / "alerts" / "log.md"
PAPER_PATH = ROOT / "alerts" / "paper.md"
PARAMETERS_PATH = ROOT / "alerts" / "parameters.yaml"
ADOPTED_BUFFERS = ("touch", "sma_band", "chase", "break_atr")
CONTEXT_PATH = ROOT / "alerts" / "context.md"
CONTRACTS_PATH = ROOT / "alerts" / "contracts.md"
CONTRACTS_HEADER = (
    "# Contract comparison\n\n"
    "The chosen row is the strike at or under $1. "
    "On a next-day expiration the live plan names the cash row, "
    "the nearest strike one contract can buy with the account balance, "
    "when the far target can still reach it. "
    "Same-day expiration is eligible until noon Pacific. "
    "A 0DTE strike past the halfway point between the stock and the far target is not taken. "
    "Halfway does not refuse a next-day strike. "
    "A name with no listing that day uses the nearest expiration that is listed. "
    "The other rows are that same fill. "
    "Price is the latest print while the row is open, and the exit bar once it closes. "
    "Return is the percent change in the premium. "
    "A rule that picks the same contract as an earlier row is not repeated. "
    "The cash row is kept either way, so the halfway flag stays. "
    "Nothing here is an order.\n\n"
    "- dte: the same strike rule on same-day expiration\n"
    "- first: the first target is the ceiling\n"
    "- cheap: the furthest strike under $1 that is still inside the far target\n"
    "- week: Friday's expiration, the same strike rule as chosen\n"
    "- cash: the nearest strike the account balance can buy that the far target can still reach. "
    "This is the named live contract on a next-day expiration. "
    "The chosen row stays on the plan as the $1 comparison.\n\n"
    "| Time | Ticker | Level | Role | Contract | Entry | Price | Return | State |\n"
    "|------|--------|-------|------|----------|-------|-------|--------|-------|\n"
)
PT = ZoneInfo("America/Los_Angeles")
FIVE_MIN = 300
TEN_MIN = 600
TOUCH = 0.15
SMA_BAND = 1.0
ATR_LENGTH = 14
# A close has to clear the level by this much of the 10-minute ATR.
BREAK_ATR = 0.5
CHASE = 0.50
# After a reclaim stop at a level, the next entry there needs a fresh retest:
# price must first trade this many 10-minute ATRs away from the level. 0 turns it off.
FRESH_ATR = 1.0
FRESH_SECONDS = 20 * 60
# The cheapest live contract the checker will buy, per share. Below it the bid-ask spread alone
# eats 8-17% of the trade (proposal 2026-10-24-contract-floor). The plan is still written and
# scored as a what-if. 0 turns it off. This gates the order only; no replayed decision moves.
MIN_PREMIUM = 0.20
# $1 comparison. The debit compared below is the price of one share of the option.
CONTRACT_CAP = 1.0
# Thursday 2026-10-22 is the first live session. One contract.
# The live premium ceiling is the Agentic balance read on that check.
LIVE_FROM = date(2026, 10, 22)
LIVE_PATH = ROOT / "alerts" / "live.md"
BROKER_PATH = ROOT / "alerts" / "broker.json"
EVENTS_PATH = ROOT / "alerts" / "events.jsonl"
FREEZE_PATH = ROOT / "config" / "freeze.yaml"
# Tests turn this off. The timer leaves it on.
SEND_ORDERS = True


def balance_amount(value) -> float | None:
    """Dollars, when the figure was read. None when it was not."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    if amount < 0 or amount != amount or amount == float("inf"):
        return None
    return amount


def premium_cap(cash) -> float | None:
    """Premium of one contract the balance can pay. None when the balance was not read."""
    amount = balance_amount(cash)
    if amount is None:
        return None
    return amount / 100


def debit_fits(premium, cash) -> bool:
    """True when one contract at this premium still fits the balance."""
    amount = balance_amount(cash)
    if amount is None or premium is None:
        return False
    return int(round(float(premium) * 10000)) <= int(round(amount * 100))


def _debit_over(debit, cap) -> bool:
    """True when the premium is past the cap. A missing cap does not refuse."""
    if cap is None or debit is None:
        return False
    return int(round(float(debit) * 10000)) > int(round(float(cap) * 10000))
PAPER_HEADER = (
    "| Time | Ticker | Action | Side | Level | Fill | Reason | Contract | Premium |\n"
    "|------|--------|--------|------|-------|------|--------|----------|---------|\n"
)
CONTEXT_HEADER = (
    "# Trade context\n\n"
    "One row per paper entry or exit. The time matches the paper row. "
    "On an entry the candle is the signal bar, the bar before the fill. "
    "On an exit the candle is the exit bar. "
    "SMA 20, 50, and 200 are the 10-minute close averages. "
    "The number in parentheses is the close minus that average. "
    "Nearby is every posted level within $1 of the close. "
    "When none are that close, it is the nearest one. "
    "The number in parentheses is the close minus that level. "
    "Volume is the 10-minute bar, in shares. "
    "This is not an order and it is not a pattern.\n\n"
    "| Time | Ticker | Action | Side | Level | Fill | Candle | Purple | Yellow "
    "| SMA20 | SMA50 | SMA200 | Nearby | Volume |\n"
    "|------|--------|--------|------|-------|------|--------|--------|--------"
    "|-------|-------|--------|--------|--------|\n"
)
# name, type, default, allowed values, and the decision that variable touches.
# A variable with no default is invalid. Live check() uses these defaults.
VARIABLES = {
    "touch": {"type": "float", "default": TOUCH, "allowed": None, "decision": "tag"},
    "sma_band": {"type": "float", "default": SMA_BAND, "allowed": None, "decision": "tag"},
    "chase": {"type": "float", "default": CHASE, "allowed": None, "decision": "fill"},
    "exit": {
        "type": "str",
        "default": "target",
        "allowed": ("target", "stop"),
        "decision": "exit",
    },
    "entry": {
        "type": "str",
        "default": "retest",
        "allowed": ("retest", "fade"),
        "decision": "entry",
    },
    "break_atr": {
        "type": "float",
        "default": BREAK_ATR,
        "allowed": None,
        "decision": "exit",
    },
    "fresh_atr": {
        "type": "float",
        "default": FRESH_ATR,
        "allowed": None,
        "decision": "entry",
    },
    # Where an entry is priced. The checker buys after the fill bar has closed, so "close" is what
    # it can get. "open" is the old bench price, which used the fill bar's open while still knowing
    # how that bar closed. The chase and reclaim checks are the same either way.
    "entry_price": {
        "type": "str",
        "default": "close",
        "allowed": ("close", "open"),
        "decision": "fill",
    },
}


def load_levels(path: Path = LEVELS_PATH) -> dict:
    data = yaml.safe_load(path.read_text())
    armed = datetime.fromisoformat(data["armed_at"])
    if armed.tzinfo is None:
        armed = armed.replace(tzinfo=PT)
    data["armed_at"] = armed
    return data


def ten_minute_closes(
    five_minute: list[tuple[int, float | None]], now: int
) -> list[tuple[int, float]]:
    """Return (bar_start, close) for 10-minute bars that have finished."""
    grouped: dict[int, list[tuple[int, float]]] = {}
    for start, close in five_minute:
        if close is None:
            continue
        bucket = start - (start % TEN_MIN)
        grouped.setdefault(bucket, []).append((start, float(close)))
    closed = []
    for bucket in sorted(grouped):
        if bucket + TEN_MIN > now:
            continue
        ending = [price for start, price in grouped[bucket] if start >= bucket + FIVE_MIN]
        if not ending:
            continue
        closed.append((bucket, ending[-1]))
    return closed


def in_session(close_at: int) -> bool:
    """Premarket through the cash close, weekdays, Pacific time."""
    when = datetime.fromtimestamp(close_at, PT)
    if when.weekday() >= 5:
        return False
    minute = when.hour * 60 + when.minute
    return 4 * 60 <= minute <= 13 * 60


def crosses(
    closes: list[tuple[int, float]],
    price: float,
    side: str,
    armed_at: int,
) -> list[dict]:
    """First finished 10-minute close through the level, after armed_at."""
    found = []
    for index in range(1, len(closes)):
        prev_start, prev_close = closes[index - 1]
        start, close = closes[index]
        del prev_start
        close_at = start + TEN_MIN
        if close_at < armed_at:
            continue
        claimed = side == "claim" and prev_close <= price < close
        lost = side == "lose" and prev_close >= price > close
        if claimed or lost:
            found.append(
                {
                    "bar_start": start,
                    "close_at": close_at,
                    "close": close,
                    "price": price,
                    "side": side,
                }
            )
    return found


def ten_minute_bars(
    five_minute: list[tuple], now: int
) -> list[dict]:
    """Finished 10-minute OHLC. The close is the second 5-minute close."""
    grouped: dict[int, list[tuple]] = {}
    for row in five_minute:
        start, open_, high, low, close = row[:5]
        if None in (open_, high, low, close):
            continue
        bucket = start - (start % TEN_MIN)
        volume = row[5] if len(row) > 5 else None
        grouped.setdefault(bucket, []).append(
            (
                start,
                float(open_),
                float(high),
                float(low),
                float(close),
                None if volume is None else float(volume),
            )
        )
    bars = []
    for bucket in sorted(grouped):
        if bucket + TEN_MIN > now:
            continue
        halves = grouped[bucket]
        opening = [row for row in halves if row[0] < bucket + FIVE_MIN]
        ending = [row for row in halves if row[0] >= bucket + FIVE_MIN]
        if not opening or not ending:
            continue
        volumes = [row[5] for row in halves if len(row) > 5 and row[5] is not None]
        bars.append(
            {
                "start": bucket,
                "close_at": bucket + TEN_MIN,
                "o": opening[0][1],
                "h": max(row[2] for row in halves),
                "l": min(row[3] for row in halves),
                "c": ending[-1][4],
                "v": sum(volumes) if volumes else None,
            }
        )
    return bars


def add_indicators(bars: list[dict]) -> list[dict]:
    """Wilder RSI 14, its 14 SMA, and the 20, 50, and 200 SMAs of the close.

    The 20 SMA stays on ``sma``. The longer averages are recorded with the
    trade. They are not an entry.
    """
    closes = [bar["c"] for bar in bars]
    purple = _rsi(closes, 14)
    yellow = _sma([value if value is not None else None for value in purple], 14)
    average = _sma(closes, 20)
    slow = _sma(closes, 50)
    longest = _sma(closes, 200)
    atr = _atr(bars, ATR_LENGTH)
    for index, bar in enumerate(bars):
        bar["purple"] = purple[index]
        bar["yellow"] = yellow[index]
        bar["sma"] = average[index]
        bar["sma50"] = slow[index]
        bar["sma200"] = longest[index]
        bar["atr"] = atr[index]
    return bars


def _atr(bars: list[dict], length: int) -> list[float | None]:
    """Wilder ATR of the 10-minute bars. The first value is the 14th bar."""
    out: list[float | None] = [None] * len(bars)
    if not bars:
        return out
    prev_close = None
    prev_atr = None
    seeded: list[float] = []
    for index, bar in enumerate(bars):
        if prev_close is None:
            tr = bar["h"] - bar["l"]
        else:
            tr = max(
                bar["h"] - bar["l"],
                abs(bar["h"] - prev_close),
                abs(bar["l"] - prev_close),
            )
        prev_close = bar["c"]
        if index < length:
            seeded.append(tr)
            if index == length - 1:
                prev_atr = sum(seeded) / length
                out[index] = prev_atr
            continue
        prev_atr = (prev_atr * (length - 1) + tr) / length
        out[index] = prev_atr
    return out


def _break_buffer(bar: dict, settings: dict | None = None) -> float:
    """How far a close must clear a level before it is a break or a claim.

    Half the 14-period ATR unless a backtest passes another fraction.
    A bar without an average keeps the old test, so a one-tick close
    through still counts until the average exists.
    """
    atr = bar.get("atr")
    if not atr:
        return 0.0
    fraction = BREAK_ATR
    if settings is not None and settings.get("break_atr") is not None:
        fraction = float(settings["break_atr"])
    return fraction * float(atr)


def _sma(values: list[float | None], length: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    for index in range(length - 1, len(values)):
        window = values[index - length + 1 : index + 1]
        if any(value is None for value in window):
            continue
        out[index] = sum(window) / length
    return out


def _rsi(closes: list[float], length: int) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= length:
        return out
    gains = []
    losses = []
    for index in range(1, len(closes)):
        change = closes[index] - closes[index - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains[:length]) / length
    avg_loss = sum(losses[:length]) / length
    out[length] = _rsi_value(avg_gain, avg_loss)
    for index in range(length, len(gains)):
        avg_gain = (avg_gain * (length - 1) + gains[index]) / length
        avg_loss = (avg_loss * (length - 1) + losses[index]) / length
        out[index + 1] = _rsi_value(avg_gain, avg_loss)
    return out


def _rsi_value(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))


def _allows(level: dict) -> str:
    if level.get("allows") in ("long", "short", "both"):
        return level["allows"]
    return "long" if level.get("side") == "claim" else "short"


def _active_allows(level: dict, history: list[dict], settings: dict | None) -> str:
    """Written side, after each close that claims or loses the level.

    Support (long) becomes resistance after a lose. Resistance (short)
    becomes support after a claim. A later close the other way flips it
    back. A level marked both stays both. A close inside the break band
    does not flip the level.
    """
    allows = _allows(level)
    if allows == "both":
        return "both"
    price = float(level["price"])
    role = allows
    for bar in history:
        band = _break_buffer(bar, settings)
        if bar["c"] > price + band and role == "short":
            role = "long"
        elif bar["c"] < price - band and role == "long":
            role = "short"
    return role


def _can(
    level: dict,
    side: str,
    history: list[dict] | None = None,
    settings: dict | None = None,
) -> bool:
    allows = _allows(level) if history is None else _active_allows(level, history, settings)
    if side == "put":
        return allows in ("short", "both")
    return allows in ("long", "both")


def _played_flip(level: dict, side: str) -> bool:
    """True when this side is the one the note did not write.

    A level marked both already plays both sides, so that is not a flip.
    """
    allows = _allows(level)
    if side == "put":
        return allows == "long"
    return allows == "short"


def _book_targets(level: dict, side: str, levels: list[dict]) -> list[float]:
    """Posted numbers on this ticker in the trade's direction, nearest first."""
    price = float(level["price"])
    ticker = level.get("ticker")
    found: list[float] = []
    seen: set[float] = set()
    for other in levels:
        if other.get("ticker") != ticker:
            continue
        candidates = [float(other["price"])]
        for key in ("targets", "up_targets"):
            candidates.extend(float(item) for item in (other.get(key) or []))
        for candidate in candidates:
            if abs(candidate - price) < 0.001:
                continue
            if side == "put" and candidate >= price:
                continue
            if side == "call" and candidate <= price:
                continue
            marker = round(candidate, 4)
            if marker in seen:
                continue
            seen.add(marker)
            found.append(candidate)
    found.sort(reverse=(side == "put"))
    return found


def _targets(level: dict, side: str) -> list[float]:
    allows = _allows(level)
    if side == "call":
        raw = level.get("up_targets") if allows == "both" else level.get("targets")
        if allows == "short":
            raw = []
    else:
        raw = [] if allows == "long" else level.get("targets")
    return [float(price) for price in (raw or [])]


def _is_clock(close_at: int) -> bool:
    when = datetime.fromtimestamp(close_at, PT)
    return when.hour == 12 and when.minute == 50


def _green(bar: dict) -> bool:
    return bar["c"] > bar["o"]


def _red(bar: dict) -> bool:
    return bar["c"] < bar["o"]


def _default_of(name: str, spec: dict):
    if "default" not in spec or spec["default"] is None:
        raise ValueError(f"{name} has no default")
    return spec["default"]


def live_settings() -> dict:
    """Every variable at the code default. A bare replay uses this."""
    return {name: _default_of(name, spec) for name, spec in VARIABLES.items()}


def frozen(path: Path | None = None) -> bool:
    """True while the operator's rule freeze is on. A missing or broken file is not a freeze."""
    file = FREEZE_PATH if path is None else path
    try:
        data = yaml.safe_load(file.read_text()) or {}
    except (OSError, yaml.YAMLError):
        return False
    return isinstance(data, dict) and data.get("active") is True


def applied_buffers(path: Path | None = None) -> dict:
    """Buffer sizes the forward test wrote. Entry and exit in that file are ignored.

    While config/freeze.yaml is active the checker keeps the code defaults, so
    the frozen sample is scored on one set of rules.
    """
    if path is None and frozen():
        return {}
    file = PARAMETERS_PATH if path is None else path
    if not file.is_file():
        return {}
    data = yaml.safe_load(file.read_text()) or {}
    if not isinstance(data, dict) or not data.get("apply"):
        return {}
    adopted = data.get("adopted") or {}
    if not isinstance(adopted, dict):
        raise ValueError("adopted buffers must be a map")
    found = {}
    for name in ADOPTED_BUFFERS:
        if name not in adopted:
            continue
        found[name] = _coerce(name, adopted[name], VARIABLES[name])
    return found


def checker_settings(path: Path | None = None) -> dict:
    """Code defaults, then any buffers the forward test applied."""
    resolved = live_settings()
    resolved.update(applied_buffers(path))
    return resolved


def resolve_settings(overrides: dict | None) -> dict:
    """Fill defaults, reject an unknown name, a null, or two changes at once."""
    overrides = dict(overrides or {})
    unknown = sorted(set(overrides) - set(VARIABLES))
    if unknown:
        raise ValueError(f"unknown variable: {', '.join(unknown)}")
    resolved = live_settings()
    changed = []
    for name, spec in VARIABLES.items():
        if name not in overrides:
            continue
        value = _coerce(name, overrides[name], spec)
        resolved[name] = value
        if value != spec["default"]:
            changed.append(name)
    if len(changed) > 1:
        raise ValueError("a run can change one variable")
    return resolved


def _coerce(name: str, value, spec: dict):
    if value is None:
        raise ValueError(f"{name} has no default")
    kind = spec["type"]
    if kind == "float":
        try:
            value = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be a number") from exc
        if value < 0:
            raise ValueError(f"{name} must be zero or more")
    elif kind == "str":
        value = str(value)
    allowed = spec.get("allowed")
    if allowed is not None and value not in allowed:
        raise ValueError(f"{name} must be one of {', '.join(allowed)}")
    return value


def _signal(
    prev: dict | None,
    bar: dict,
    levels: list[dict],
    settings: dict,
    history: list[dict] | None = None,
) -> dict | None:
    """Level retest. Fade is the failed claim or the failed break.

    A fade put is a claim level that tags and closes back under. A fade call
    is a break level that tags and closes back above. A close back through
    that level invalidates it. A close beyond the signal wick is the stop.
    The furthest other level in that direction is the target. The live
    default is the retest, so check() does not take the fade. An SMA hold
    is a watch, not an entry.

    history is every finished bar before this one. A lose flips support to
    resistance, and a claim flips resistance to support. The fade still uses
    the side written in the note.
    """
    if prev is None:
        return None
    touch = settings["touch"]
    prior = history or []
    fade = settings.get("entry") == "fade"
    for level in levels:
        price = float(level["price"])
        if fade:
            put_tag = (
                _can(level, "call")
                and prev["c"] < price
                and _green(bar)
                and bar["h"] >= price - touch
                and bar["c"] < price
            )
            call_tag = (
                _can(level, "put")
                and prev["c"] > price
                and _red(bar)
                and bar["l"] <= price + touch
                and bar["c"] > price
            )
            reason = "fade"
        else:
            put_tag = (
                _can(level, "put", prior, settings)
                and prev["c"] < price
                and _green(bar)
                and bar["h"] >= price - touch
                and bar["c"] < price
            )
            call_tag = (
                _can(level, "call", prior, settings)
                and prev["c"] > price
                and _red(bar)
                and bar["l"] <= price + touch
                and bar["c"] > price
            )
            reason = "retest"
        if put_tag or call_tag:
            return _intent(level, "put" if put_tag else "call", bar, reason, levels)
    return None


def _fresh_sma_hold(
    prev2: dict | None,
    prev: dict | None,
    bar: dict,
    level: dict,
    side: str,
    settings: dict,
    history: list[dict],
) -> bool:
    """The first bar of an SMA hold. A hold that is still true does not repeat."""
    if prev is None or not _sma_hold(prev, bar, level, side, settings, history):
        return False
    if prev2 is None:
        return True
    earlier = history[:-1]
    return not _sma_hold(prev2, prev, level, side, settings, earlier)


def _sma_watches(
    prev2: dict | None,
    prev: dict | None,
    bar: dict,
    levels: list[dict],
    settings: dict,
    history: list[dict] | None = None,
) -> list[dict]:
    found = []
    prior = history or []
    for level in levels:
        for side in ("put", "call"):
            if not _fresh_sma_hold(prev2, prev, bar, level, side, settings, prior):
                continue
            intent = _intent(level, side, bar, "sma")
            intent["note"] = "The 20 SMA is on the level."
            found.append(intent)
            break
    return found


def _rsi_cross(prev: dict | None, bar: dict) -> str:
    """Purple crossing 50, or crossing its yellow average. Empty when neither flips."""
    if prev is None:
        return ""
    before_p = prev.get("purple")
    before_y = prev.get("yellow")
    after_p = bar.get("purple")
    after_y = bar.get("yellow")
    if None in (before_p, before_y, after_p, after_y):
        return ""
    if (before_p >= 50) != (after_p >= 50):
        return "Purple crossed under 50." if after_p < 50 else "Purple crossed above 50."
    if (before_p >= before_y) != (after_p >= after_y):
        return "Purple crossed under yellow." if after_p < after_y else "Purple crossed above yellow."
    return ""


def _rsi_watch(position: dict, prev: dict | None, bar: dict) -> dict | None:
    note = _rsi_cross(prev, bar)
    if not note:
        return None
    return {
        "ticker": position["ticker"],
        "side": position["side"],
        "level": position["level"],
        "last": position.get("last"),
        "stop": position.get("stop"),
        "reason": "rsi",
        "bar": bar,
        "note": note,
    }


def _sma_hold(
    prev: dict,
    bar: dict,
    level: dict,
    side: str,
    settings: dict,
    history: list[dict] | None = None,
) -> bool:
    average = bar.get("sma")
    price = float(level["price"])
    if average is None or not _can(level, side, history, settings):
        return False
    if abs(average - price) > settings["sma_band"]:
        return False
    if side == "put":
        return prev["c"] < price and bar["c"] < price and bar["c"] < average and _green(bar)
    return prev["c"] > price and bar["c"] > price and bar["c"] > average and _red(bar)


def _fade_last(level: dict, side: str, levels: list[dict]) -> float | None:
    """Furthest number on this ticker in the direction of the fade.

    Level prices and the target lists both count. The first number does not
    close the trade. The far one does.
    """
    price = float(level["price"])
    ticker = level.get("ticker")
    chosen = []
    for other in levels:
        if other.get("ticker") != ticker:
            continue
        numbers = [float(other["price"])]
        for key in ("targets", "up_targets"):
            numbers.extend(float(item) for item in (other.get(key) or []))
        for other_price in numbers:
            if side == "put" and other_price < price:
                chosen.append(other_price)
            elif side == "call" and other_price > price:
                chosen.append(other_price)
    if not chosen:
        return None
    return min(chosen) if side == "put" else max(chosen)


def _intent(level: dict, side: str, bar: dict, reason: str, levels: list[dict] | None = None) -> dict:
    flipped = reason != "fade" and _played_flip(level, side)
    if flipped:
        targets = _book_targets(level, side, levels or [])
        flip = (
            "Support flipped to resistance."
            if side == "put"
            else "Resistance flipped to support."
        )
    else:
        targets = _targets(level, side)
        flip = ""
    stop = level.get("stop")
    last = targets[-1] if targets else None
    nxt = targets[0] if targets else None
    if reason == "fade":
        # The wick is the hard stop. The other levels in the note are the target.
        last = _fade_last(level, side, levels or [])
        stop = bar["h"] if side == "put" else bar["l"]
    return {
        "ticker": level.get("ticker") or "",
        "side": side,
        "level": float(level["price"]),
        "last": last,
        "next": nxt,
        "stop": None if stop is None else float(stop),
        "reason": reason,
        "bar": bar,
        "note": level.get("note") or "",
        "flip": flip,
    }


def _through_last(position: dict, bar: dict, settings: dict | None = None) -> bool:
    last = position["last"]
    if last is None:
        return False
    band = _break_buffer(bar, settings)
    if position["side"] == "put":
        return bar["c"] < last - band
    return bar["c"] > last + band


def _reclaimed(position: dict, bar: dict, settings: dict | None = None) -> bool:
    band = _break_buffer(bar, settings)
    if position["side"] == "put":
        return bar["c"] > position["level"] + band
    return bar["c"] < position["level"] - band


def _event(kind: str, pending: dict, bar: dict, reason: str, fill: float | None) -> dict:
    return {
        "kind": kind,
        "ticker": pending["ticker"],
        "side": pending["side"],
        "level": pending["level"],
        "reason": reason,
        "close_at": bar["close_at"],
        "signal_at": pending["bar"]["close_at"],
        "bar": pending["bar"] if kind == "entry" else bar,
        "fill": fill,
        "note": pending.get("note") or "",
        "flip": pending.get("flip") or "",
        "last": pending.get("last"),
        "next": pending.get("next"),
    }


def _next_failed(
    seen: list[dict], pending: dict, touch: float, settings: dict | None = None
) -> bool:
    """The next number was tagged and closed back. A later close through clears it.

    Fade keeps its own entry. A level with no next number is free.
    """
    if pending.get("reason") == "fade":
        return False
    nxt = pending.get("next")
    if nxt is None:
        return False
    failed = False
    for bar in seen:
        if bar["close_at"] > pending["bar"]["close_at"]:
            break
        band = _break_buffer(bar, settings)
        if pending["side"] == "call":
            if bar["c"] > nxt + band:
                failed = False
            elif bar["h"] >= nxt - touch and bar["c"] < nxt:
                failed = True
        elif bar["c"] < nxt - band:
            failed = False
        elif bar["l"] <= nxt + touch and bar["c"] > nxt:
            failed = True
    return failed


def replay(
    bars: list[dict],
    levels: list[dict],
    armed_at: int = 0,
    settings: dict | None = None,
    accept=None,
) -> list[dict]:
    """Walk finished bars. One position per call. The next open is the fill.

    settings=None uses the code defaults. The checker passes
    checker_settings(), which adds alerts/parameters.yaml when that file
    says to apply the buffers. The same bars and settings replay to the
    same events.
    """
    chosen = live_settings() if settings is None else settings
    events = []
    position = None
    pending = None
    prev2 = None
    prev = None
    seen: list[dict] = []
    history: list[dict] = []
    # Levels stopped out by a reclaim this session, still waiting for price to leave.
    stale: set[float] = set()
    session = None
    for bar in bars:
        prior = history
        history = history + [bar]
        if bar["close_at"] < armed_at:
            prev2, prev = prev, bar
            continue
        seen.append(bar)
        day = datetime.fromtimestamp(bar["close_at"], PT).date()
        if day != session:
            session, stale = day, set()
        stale = {level for level in stale if not _left_level(bar, level, chosen)}
        if pending:
            opened = _resolve_fill(pending, bar, events, chosen, accept)
            pending = None
            if opened and _finish(opened, bar, events, include_reclaim=False, settings=chosen):
                position = None
            else:
                position = opened
            prev2, prev = prev, bar
            continue
        if position:
            if _finish(position, bar, events, include_reclaim=True, settings=chosen):
                if events[-1]["reason"] == "reclaim" and float(chosen.get("fresh_atr") or 0) > 0:
                    stale.add(round(float(position["level"]), 4))
                position = None
            else:
                watch = _rsi_watch(position, prev, bar)
                if watch:
                    events.append(_event("watch", watch, bar, "rsi", None))
            prev2, prev = prev, bar
            continue
        if not _is_clock(bar["close_at"]):
            pending = _signal(prev, bar, levels, chosen, prior)
            if pending and _next_failed(seen, pending, chosen["touch"], chosen):
                events.append(_event("skip", pending, bar, "next", None))
                pending = None
            if pending and round(float(pending["level"]), 4) in stale:
                events.append(_event("skip", pending, bar, "fresh", None))
                pending = None
            for watch in _sma_watches(prev2, prev, bar, levels, chosen, prior):
                if (
                    pending
                    and watch["side"] == pending["side"]
                    and abs(watch["level"] - pending["level"]) < 0.001
                ):
                    continue
                events.append(_event("watch", watch, bar, "sma", None))
        prev2, prev = prev, bar
    return events


def _left_level(bar: dict, level: float, settings: dict) -> bool:
    """This bar traded fresh_atr ATRs away from the level, on either side. No ATR yet is not away."""
    atr = bar.get("atr")
    if not atr:
        return False
    distance = float(settings.get("fresh_atr") or 0) * float(atr)
    return bar["h"] - level >= distance or level - bar["l"] >= distance


def _resolve_fill(
    pending: dict,
    bar: dict,
    events: list[dict],
    settings: dict,
    accept=None,
) -> dict | None:
    fill = bar["o"]
    # A retest is judged from the printed level. An SMA hold never tagged that
    # level, so the chase is measured from the signal close instead.
    anchor = pending["bar"]["c"] if pending["reason"] == "sma" else pending["level"]
    if abs(fill - anchor) > settings["chase"]:
        events.append(_event("skip", pending, bar, "chase", fill))
        return None
    if _reclaimed(pending, bar, settings):
        events.append(_event("skip", pending, bar, "reclaim", fill))
        return None
    if settings["exit"] == "stop" and pending.get("stop") is None:
        raise ValueError(
            f"{pending['ticker']} {pending['level']} was taken and has no stop price"
        )
    if accept is not None and not accept(pending, bar):
        events.append(_event("skip", pending, bar, "contract", fill))
        return None
    at_close = (settings.get("entry_price") or "close") == "close"
    entry = _event("entry", pending, bar, pending["reason"], bar["c"] if at_close else fill)
    entry["fill_at"] = bar["close_at"] if at_close else bar["close_at"] - TEN_MIN
    events.append(entry)
    return pending


def _through_stop(position: dict, bar: dict) -> bool:
    stop = position.get("stop")
    if stop is None:
        return False
    if position["side"] == "put":
        return bar["c"] > stop
    return bar["c"] < stop


def _near_level(position: dict, bar: dict, distance: float) -> bool:
    """Price has come within `distance` of the next target. The far one is the fallback."""
    target = position.get("next")
    if target is None:
        target = position.get("last")
    if target is None:
        return False
    if position["side"] == "put":
        return bar["l"] <= float(target) + distance
    return bar["h"] >= float(target) - distance


def _custom_exit(
    position: dict, bar: dict, include_reclaim: bool, settings: dict
) -> str | None:
    """A what-if exit. The live checker does not set these keys."""
    stop_mode = settings.get("stop_mode") or "reclaim"
    take = settings.get("take") or "target"
    flatten = settings.get("flatten") or "clock"
    if stop_mode == "reclaim" and include_reclaim and _reclaimed(position, bar, settings):
        return "reclaim"
    if stop_mode == "named" and _through_stop(position, bar):
        return "stop"
    if take == "target" and _through_last(position, bar, settings):
        return "target"
    if take == "near" and _near_level(position, bar, float(settings.get("profit_near") or 0)):
        return "near"
    if flatten == "clock" and _is_clock(bar["close_at"]):
        return "clock"
    return None


def _finish(
    position: dict,
    bar: dict,
    events: list[dict],
    include_reclaim: bool,
    settings: dict,
) -> bool:
    if any(key in settings for key in ("stop_mode", "take", "flatten")):
        reason = _custom_exit(position, bar, include_reclaim, settings)
        if reason is None:
            return False
        events.append(_event("exit", position, bar, reason, None))
        return True
    if position.get("reason") == "fade" and settings["exit"] == "target":
        # Invalidation is a close back through the level. The wick stop is
        # outside that, so it only fires when the level close has not.
        if include_reclaim and _reclaimed(position, bar, settings):
            reason = "reclaim"
        elif _through_stop(position, bar):
            reason = "stop"
        elif _through_last(position, bar, settings):
            reason = "target"
        elif _is_clock(bar["close_at"]):
            reason = "clock"
        else:
            return False
    elif settings["exit"] == "stop":
        if _through_stop(position, bar):
            reason = "stop"
        elif _is_clock(bar["close_at"]):
            reason = "clock"
        else:
            return False
    elif include_reclaim and _reclaimed(position, bar, settings):
        reason = "reclaim"
    elif _through_last(position, bar, settings):
        reason = "target"
    elif _is_clock(bar["close_at"]):
        reason = "clock"
    else:
        return False
    events.append(_event("exit", position, bar, reason, None))
    return True


def _read_state(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_state(path: Path = STATE_PATH) -> set[str]:
    return set(_read_state(path).get("fired") or [])


def load_marked(name: str, path: Path = STATE_PATH) -> set[str]:
    return set(_read_state(path).get(name) or [])


def save_state(fired: set[str], path: Path = STATE_PATH, **marks: set[str]) -> None:
    payload = _read_state(path)
    payload["fired"] = sorted(fired)
    for name, values in marks.items():
        payload[name] = sorted(values)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def route_event(event: dict, moment: int) -> str:
    """A fresh event is alerted. A late entry or exit from the same session is still written."""
    stale = moment - event["close_at"] > FRESH_SECONDS
    if not stale:
        return "alert"
    event_day = datetime.fromtimestamp(event["close_at"], PT).date()
    moment_day = datetime.fromtimestamp(moment, PT).date()
    if event.get("kind") in ("entry", "exit") and event_day == moment_day:
        return "quiet"
    return "drop"


def _entry_key(pending: dict) -> str:
    return (
        f"{pending['ticker']}|{pending['side']}|{pending['level']}"
        f"|{pending['bar']['close_at']}"
    )


def event_id(ticker: str, event: dict) -> str:
    if "kind" in event:
        return (
            f"{ticker}|{event['kind']}|{event['side']}|{event['level']}"
            f"|{event['close_at']}|{event['reason']}"
        )
    return f"{ticker}|{event['side']}|{event['price']}|{event['close_at']}"


def format_event(ticker: str, event: dict, note: str) -> str:
    when = datetime.fromtimestamp(event["close_at"], PT).strftime("%Y-%m-%d %H:%M PT")
    relation = "above" if event["side"] == "claim" else "below"
    text = (
        f"{ticker} {event['side']}: 10-minute close {event['close']:.2f} "
        f"{relation} {event['price']} at {when}."
    )
    if note:
        text = f"{text} {note}."
    return text + " Not an order."


def _clock_label(close_at: int) -> str:
    when = datetime.fromtimestamp(close_at, PT)
    hour = when.hour % 12 or 12
    return f"{hour}:{when.minute:02d} PT"


def format_live(event: dict) -> str:
    when = datetime.fromtimestamp(event["close_at"], PT).strftime("%Y-%m-%d %H:%M PT")
    price = f"{event['level']:.2f}"
    head = f"{event['ticker']} {event['side']} {event['kind']} {price} at {when}."
    if event["kind"] == "skip" and event["reason"] == "chase":
        extra = f" Next open {event['fill']:.2f} left the level."
    elif event["kind"] == "skip" and event["reason"] == "next":
        extra = " The next number was tagged and did not hold."
    elif event["kind"] == "skip" and event["reason"] == "fresh":
        extra = " Stopped at this level earlier and price has not left it since."
    elif event["kind"] == "skip" and event["reason"] == "contract":
        if event.get("last") is None and event.get("next") is None:
            extra = " This level has no further number, so no contract was chosen."
        else:
            extra = " No strike under $1 was still in front of the far target."
    elif event["kind"] == "skip":
        extra = " Fill bar closed back through the level."
    elif event["kind"] == "exit" and event["reason"] == "expiry":
        extra = f" Out at {_clock_label(event['close_at'])}."
    elif event["kind"] == "exit" and event["reason"] == "target":
        extra = " Close through the last target."
    elif event["kind"] == "exit" and event["reason"] == "reclaim":
        extra = " Close back through the entry level."
    elif event["kind"] == "exit":
        extra = " 12:50 bar, cut before the cash close."
    elif event["kind"] == "watch":
        extra = f" {event['note']} Not a fill."
    else:
        contract = "call" if event["side"] == "call" else "put"
        flip = event.get("flip") or ""
        prefix = f" {flip} " if flip else " "
        extra = (
            f"{prefix}Fill {event['fill']:.2f}. {contract} debit has to fit the account balance. "
            "OTM is allowed when theta and the target still leave room to gain."
        )
    return f"{head} {_candle(event['bar'])} {_rsi_text(event['bar'])}{extra} Not an order."


def _candle(bar: dict) -> str:
    color = "green" if _green(bar) else "red" if _red(bar) else "flat"
    return (
        f"Candle {color} O {bar['o']:.2f} H {bar['h']:.2f} "
        f"L {bar['l']:.2f} C {bar['c']:.2f}."
    )


def _rsi_text(bar: dict) -> str:
    purple = bar.get("purple")
    yellow = bar.get("yellow")
    left = "n/a" if purple is None else f"{purple:.2f}"
    right = "n/a" if yellow is None else f"{yellow:.2f}"
    return f"RSI purple {left} yellow {right}."


def fetch_five_minute(ticker: str, span: str = "5d") -> list[tuple]:
    _CLOCK.requests["stock"] += 1
    query = urllib.parse.urlencode(
        {"interval": "5m", "range": span, "includePrePost": "true"}
    )
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?{query}"
    payload = None
    for attempt in range(RETRIES):
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode())
            break
        except urllib.error.HTTPError as exc:
            if exc.code in RETRY_CODES and attempt < RETRIES - 1:
                _pause(exc, attempt)
                continue
            detail = exc.read().decode(errors="replace")[:180]
            raise SystemExit(f"{ticker} price history {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt < RETRIES - 1:
                _pause(None, attempt)
                continue
            raise SystemExit(f"{ticker} price history unreachable: {exc}") from exc
    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        raise SystemExit(f"{ticker} price history was empty")
    row = result[0]
    stamps = row.get("timestamp") or []
    quote = (row.get("indicators") or {}).get("quote", [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    if len(volumes) < len(stamps):
        volumes = list(volumes) + [None] * (len(stamps) - len(volumes))
    return list(zip(stamps, opens, highs, lows, closes, volumes))


def _token() -> str:
    token = ""
    env_path = ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text().splitlines():
            if line.startswith("TA_BOT_TOKEN="):
                token = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not token:
        raise SystemExit("TA_BOT_TOKEN is missing from .env")
    return token


RETRIES = 3
RETRY_CODES = (429, 500, 502, 503, 504)
# A Retry-After longer than this is not waited out inside a 10-minute check.
MAX_PAUSE = 10.0


def _pause(exc: urllib.error.HTTPError | None, attempt: int) -> None:
    """Wait what the server asked for (Retry-After), else 1s then 2s."""
    wait = float(attempt + 1)
    if exc is not None:
        header = (exc.headers or {}).get("Retry-After") if exc.headers else None
        try:
            wait = float(header) if header else wait
        except ValueError:
            pass
    time.sleep(min(max(wait, 0.0), MAX_PAUSE))


def _discord_call(token: str, path: str, body: dict | None = None):
    """One Discord API call, retried on a rate limit or a server error."""
    for attempt in range(RETRIES):
        request = urllib.request.Request(
            "https://discord.com/api/v10" + path,
            data=None if body is None else json.dumps(body).encode(),
            headers={
                "Authorization": f"Bot {token}",
                "User-Agent": "AutoBonk claim-alerts",
                "Content-Type": "application/json",
            },
            method="GET" if body is None else "POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read()
            return json.loads(raw.decode()) if raw else {}
        except urllib.error.HTTPError as exc:
            if exc.code in RETRY_CODES and attempt < RETRIES - 1:
                _pause(exc, attempt)
                continue
            raise


def _discord_get(token: str, path: str):
    return _discord_call(token, path)


def _send_alert(text: str, notify: bool) -> None:
    """Post one alert. Nothing Discord does can stop the rest of the check."""
    if not notify:
        return
    try:
        notify_discord(text)
    except Exception:  # noqa: BLE001
        return
    except SystemExit:
        return


# The #ta channel id, found once per process. Every alert used to list every guild and channel.
_CHANNEL: dict[str, str] = {}


def _ta_channel(token: str) -> str:
    if "ta" in _CHANNEL:
        return _CHANNEL["ta"]
    for guild in _discord_get(token, "/users/@me/guilds"):
        for channel in _discord_get(token, f"/guilds/{guild['id']}/channels"):
            if channel.get("name") == "ta" and channel.get("type") == 0:
                _CHANNEL["ta"] = channel["id"]
                return channel["id"]
    raise SystemExit("Discord #ta was not found")


def notify_discord(text: str) -> None:
    """Post one alert to #ta. The token is never printed."""
    token = _token()
    _discord_call(token, f"/channels/{_ta_channel(token)}/messages", {"content": text})


def _store_rows(kind: str, lines: list[str], path: Path, real: Path) -> None:
    """Remember a row for the website. A temp path used by a test stays a file."""
    if path.resolve() != real.resolve():
        return
    import blotter as trade_rows

    trade_rows.store(kind, lines)


def append_log(lines: list[str]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not LOG_PATH.is_file():
        LOG_PATH.write_text("# 10-minute claim alerts\n\n")
    with LOG_PATH.open("a") as handle:
        for line in lines:
            handle.write(f"- {line}\n")
    _store_rows("log", lines, LOG_PATH, LOG_PATH)


def _too_far_otm(stock: float, side: str, strike: float, far: float | None) -> bool:
    """A 0DTE strike past the halfway point from the stock to the far target.

    The target then has less room beyond the strike than the stock still has
    to travel, so theta takes the contract before the target can add value.
    """
    if far is None:
        return False
    midpoint = (stock + far) / 2
    if side == "call":
        return strike > stock and strike > midpoint
    return strike < stock and strike < midpoint


def _last_hour(start: int) -> bool:
    """The 10-minute window closes at noon or later. Cash close is 13:00 PT."""
    close = datetime.fromtimestamp(start + TEN_MIN, PT)
    return close.hour * 60 + close.minute >= 12 * 60


def _ordered_quotes(stock: float, side: str, quotes: list[dict]) -> tuple[list[dict], list[dict]]:
    if side == "call":
        in_the_money = sorted(
            (row for row in quotes if row["strike"] <= stock),
            key=lambda row: row["strike"],
            reverse=True,
        )
        out_the_money = sorted(
            (row for row in quotes if row["strike"] > stock),
            key=lambda row: row["strike"],
        )
    else:
        in_the_money = sorted(
            (row for row in quotes if row["strike"] >= stock),
            key=lambda row: row["strike"],
        )
        out_the_money = sorted(
            (row for row in quotes if row["strike"] < stock),
            key=lambda row: row["strike"],
            reverse=True,
        )
    return in_the_money, out_the_money


def _pick_contract(
    stock: float,
    side: str,
    quotes: list[dict],
    far_target: float | None,
    limit_otm: bool,
    cap: float | None,
) -> dict | None:
    in_the_money, out_the_money = _ordered_quotes(stock, side, quotes)
    for row in in_the_money:
        if _debit_over(row["debit"], cap):
            continue
        return {**row, "otm": False}
    for row in out_the_money:
        if _debit_over(row["debit"], cap):
            continue
        if far_target is not None and side == "call" and row["strike"] > far_target:
            continue
        if far_target is not None and side == "put" and row["strike"] < far_target:
            continue
        if limit_otm and _too_far_otm(stock, side, row["strike"], far_target):
            continue
        return {**row, "otm": True}
    return None


def choose_contract(
    stock: float,
    side: str,
    quotes: list[dict],
    far_target: float | None,
    limit_otm: bool = False,
) -> dict | None:
    """The contract for this fill. Over the $100 cap, it is still the contract and it is paper.

    ATM or ITM at or under the cap comes first, then the nearest OTM the target
    can still reach. When nothing is under the cap, the same search ignores the
    cap and the trade is paper.
    """
    picked = _pick_contract(stock, side, quotes, far_target, limit_otm, CONTRACT_CAP)
    if picked is not None:
        return {**picked, "book": "fits"}
    picked = _pick_contract(stock, side, quotes, far_target, limit_otm, None)
    if picked is not None:
        return {**picked, "book": "paper"}
    return None


def choose_cheap(
    stock: float,
    side: str,
    quotes: list[dict],
    ceiling: float | None,
) -> dict | None:
    """The furthest strike under the cap that the target can still reach."""
    legal = []
    for row in quotes:
        if row["debit"] > CONTRACT_CAP:
            continue
        strike = row["strike"]
        if ceiling is not None and side == "call" and strike > ceiling:
            continue
        if ceiling is not None and side == "put" and strike < ceiling:
            continue
        legal.append(row)
    if not legal:
        return None
    if side == "call":
        return max(legal, key=lambda row: row["strike"])
    return min(legal, key=lambda row: row["strike"])


def pick_expiration(days: list[date], session: date) -> date | None:
    """The nearest listed expiration, including the session date."""
    ordered = [day for day in sorted(days) if day >= session]
    return ordered[0] if ordered else None


def weekly_expiration(session: date) -> date:
    """Friday of this week."""
    return session + timedelta(days=(4 - session.weekday()) % 7)


def assemble_contracts(
    session: date,
    ladders: dict[date, list[dict]],
    side: str,
    stock: float,
    first: float | None,
    far: float | None,
    start: int | None = None,
    cash: float | None = None,
) -> list[dict]:
    """The chosen contract, plus the other rules priced at the same fill.

    A repeated contract is kept once, on the earlier rule. A rule that finds
    nothing is recorded as none so the miss stays visible.
    """
    if not ladders:
        return []
    late = start is not None and _last_hour(start)
    rows: list[dict] = []

    def add(role: str, day: date | None, ceiling: float | None, picker) -> None:
        if day is None or day not in ladders:
            rows.append({"role": role, "contract": "none", "premium": None})
            return
        picked = picker(stock, side, ladders[day], ceiling)
        if picked is None:
            rows.append({"role": role, "contract": "none", "premium": None})
            return
        label = contract_label(day, picked["strike"], side)
        if any(row["contract"] == label for row in rows):
            return
        rows.append(
            {
                "role": role,
                "contract": label,
                "premium": round(float(picked["debit"]), 2),
                "book": picked.get("book") or "fits",
            }
        )

    chosen_day = None
    paper_day = None
    if far is not None:
        for day in sorted(ladders):
            if day < session or (late and day == session):
                continue
            limit = day == session

            def pick(price, direction, quotes, ceiling, limit=limit):
                return choose_contract(price, direction, quotes, ceiling, limit_otm=limit)

            picked = pick(stock, side, ladders[day], far)
            if picked is None:
                continue
            if picked.get("book") == "paper":
                if paper_day is None:
                    paper_day = day
                continue
            before = len(rows)
            add("chosen", day, far, pick)
            if any(row["role"] == "chosen" and row["contract"] != "none" for row in rows[before:]):
                chosen_day = day
                break
            del rows[before:]
    if chosen_day is None and paper_day is not None:
        limit = paper_day == session

        def pick_paper(price, direction, quotes, ceiling, limit=limit):
            return choose_contract(price, direction, quotes, ceiling, limit_otm=limit)

        add("chosen", paper_day, far, pick_paper)
        if any(row["role"] == "chosen" and row["contract"] != "none" for row in rows):
            chosen_day = paper_day
    if chosen_day is None:
        rows.insert(
            0,
            {
                "role": "chosen",
                "contract": "none",
                "premium": None,
                "why": "no-target" if far is None else "no-strike",
            },
        )
    chosen_is_none = rows[0]["contract"] == "none"
    if session != chosen_day or chosen_is_none:
        if session in ladders:
            add("dte", session, far, choose_contract)
        else:
            rows.append({"role": "dte", "contract": "none", "premium": None})
    if (
        chosen_day is not None
        and first is not None
        and far is not None
        and abs(first - far) > 0.001
    ):
        add("first", chosen_day, first, choose_contract)
    if chosen_day is not None and far is not None:
        add("cheap", chosen_day, far, choose_cheap)
    week = weekly_expiration(session)
    if chosen_day is not None and week != chosen_day:
        add("week", week, far, choose_contract)
    if chosen_day is not None and far is not None and chosen_day in ladders:
        # Record the cash strike even when 0DTE halfway would refuse it.
        # The refusal is applied when the live row is named, not by dropping the strike.
        # A balance that was not read leaves the cash strike unnamed, so nothing is sent.
        cap = premium_cap(cash)
        if cap is None:
            picked = None
        else:
            picked = _pick_contract(stock, side, ladders[chosen_day], far, False, cap)
        if picked is None:
            rows.append({"role": "cash", "contract": "none", "premium": None, "halfway": ""})
        else:
            rows.append(
                {
                    "role": "cash",
                    "contract": contract_label(chosen_day, picked["strike"], side),
                    "premium": round(float(picked["debit"]), 2),
                    "book": "fits",
                    "halfway": (
                        "past"
                        if _too_far_otm(stock, side, float(picked["strike"]), far)
                        else "inside"
                    ),
                }
            )
    return rows


def _label_expiration(label: str, close_at: int) -> date | None:
    """Expiration date from a contract label, using the fill's year."""
    when = datetime.fromtimestamp(close_at, PT).strftime("%Y-%m-%d %H:%M PT")
    return contract_expiration({"contract": label, "time": when})


def _role_row(rows: list[dict] | None, role: str) -> dict | None:
    return next((row for row in (rows or []) if row.get("role") == role), None)


def halfway_blocks(rows: list[dict] | None, close_at: int) -> str:
    """Whether halfway refuses the cash strike.

    ``blocks`` is a 0DTE refusal. ``past`` is the same geometry on a later
    expiration, and it does not refuse. ``inside`` is in front of halfway.
    """
    cash = _role_row(rows, "cash")
    if cash is None:
        return ""
    label = cash.get("contract") or ""
    if label in ("", "none"):
        return ""
    where = cash.get("halfway") or ""
    if where != "past":
        return where
    expiration = _label_expiration(label, close_at)
    session = datetime.fromtimestamp(close_at, PT).date()
    if expiration is not None and expiration == session:
        return "blocks"
    return "past"


def named_live_contract(rows: list[dict] | None, close_at: int) -> tuple[str, float | None]:
    """The contract a live plan names.

    The cash strike is named when the far target can reach it, except a 0DTE
    strike past halfway. Otherwise the name stays the $1 strike.
    """
    chosen = _role_row(rows, "chosen")
    cash = _role_row(rows, "cash")
    session = datetime.fromtimestamp(close_at, PT).date()
    label = "" if cash is None else (cash.get("contract") or "")
    if label not in ("", "none"):
        expiration = _label_expiration(label, close_at)
        blocked = expiration == session and (cash or {}).get("halfway") == "past"
        if expiration is not None and not blocked:
            return label, cash.get("premium")
    if chosen is None:
        return "", None
    chosen_label = chosen.get("contract") or ""
    if chosen_label in ("",):
        return "", None
    return chosen_label, chosen.get("premium")


def _candidate_fields(rows: list[dict] | None) -> dict:
    dollar = _role_row(rows, "chosen") or {}
    cash = _role_row(rows, "cash") or {}
    return {
        "dollar_contract": dollar.get("contract") or "",
        "dollar_premium": dollar.get("premium"),
        "cash_contract": cash.get("contract") or "",
        "cash_premium": cash.get("premium"),
    }


def _mark_label(ticker: str, label: str, when: str, start: int) -> float | None:
    """The option close on ``start``. A missed tape stays blank."""
    if not label or label == "none":
        return None
    symbol = _contract_symbol({"contract": label, "ticker": ticker, "time": when})
    if not symbol:
        return None
    try:
        price = option_price(fetch_option_minutes(symbol, span="10d"), start, "close")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    if price is None:
        return None
    return round(float(price), 2)


def _live_candidate_book(text: str) -> dict[tuple[str, str, str], dict]:
    """The $1 strike and the cash strike already written on a live entry."""
    book: dict[tuple[str, str, str], dict] = {}
    if "$1 strike" not in text:
        return book
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 14 or cells[0] in ("Time", "") or set(cells[0]) <= {"-"}:
            continue
        if cells[2] != "entry":
            continue
        book[(cells[1], cells[3], cells[4])] = {
            "dollar_contract": cells[10],
            "cash_contract": cells[12],
        }
    return book


def format_return(entry: str, price: str) -> str:
    try:
        start = float(entry)
        mark = float(price)
    except (TypeError, ValueError):
        return ""
    if start == 0:
        return ""
    return f"{(mark - start) / start * 100:+.1f}%"


def _strike_text(strike: float) -> str:
    text = f"{strike:.2f}"
    if text.endswith("0"):
        text = text[:-1]
    if text.endswith(".0"):
        text = text[:-2]
    return text


def contract_label(expiration: date, strike: float, side: str) -> str:
    kind = "C" if side == "call" else "P"
    return f"{expiration.month}/{expiration.day} {_strike_text(strike)}{kind}"


def option_symbol(ticker: str, expiration: date, strike: float, side: str) -> str:
    kind = "C" if side == "call" else "P"
    mills = int(round(strike * 1000))
    return f"{ticker.upper()}{expiration.strftime('%y%m%d')}{kind}{mills:08d}"


def candidate_strikes(stock: float, side: str) -> list[float]:
    if side == "call":
        low, high = stock - 2.5, stock + 8
    else:
        low, high = stock - 8, stock + 2.5
    return _strike_span(low, high)


def ladder_strikes(stock: float, side: str, ceiling: float | None) -> list[float]:
    """Strikes from just in the money through the far target."""
    if side == "call":
        low = stock - 2.5
        high = stock + 8 if ceiling is None else max(stock + 1, ceiling)
    else:
        high = stock + 2.5
        low = stock - 8 if ceiling is None else min(stock - 1, ceiling)
    return _strike_span(low, high)


def _strike_span(low: float, high: float) -> list[float]:
    found = set()
    for step in (1.0, 2.5):
        point = math.floor(max(low, step) / step) * step
        while point <= high + 1e-6:
            if point > 0:
                found.add(round(point, 2))
            point = round(point + step, 2)
    return sorted(found)


def fetch_option_minutes(symbol: str, span: str = "1d") -> list[tuple]:
    """One-minute option bars from Yahoo. The checker cannot call Robinhood.

    An unlisted strike is an empty list. A rate limit is asked again. Treating
    that limit as a missing strike empties the ladder and leaves no status.
    A minute that printed a close still counts when the open is blank.
    """
    _CLOCK.requests["option"] += 1
    query = urllib.parse.urlencode(
        {"interval": "1m", "range": span, "includePrePost": "true"}
    )
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{query}"
    payload = None
    for attempt in range(3):
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                payload = json.loads(response.read().decode())
            break
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 503) and attempt < 2:
                time.sleep(0.4 * (attempt + 1))
                continue
            return []
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            return []
    if not payload:
        return []
    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        return []
    row = result[0]
    stamps = row.get("timestamp") or []
    quote = (row.get("indicators") or {}).get("quote", [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    bars = []
    for stamp, open_, high, low, close in zip(stamps, opens, highs, lows, closes):
        if stamp is None or close is None:
            continue
        if open_ is None:
            open_ = close
        if high is None:
            high = close
        if low is None:
            low = close
        bars.append((stamp, open_, high, low, close))
    return bars


def option_price(bars: list[tuple], start: int, which: str) -> float | None:
    """Open or close of the 10-minute window. The first later print covers a premarket fill."""
    window = [bar for bar in bars if start <= bar[0] < start + TEN_MIN]
    if not window and which == "open":
        horizon = start + 40 * 60
        # Equity options open at 6:30 PT. A fill before that uses the first print after the open.
        opened = datetime.fromtimestamp(start, PT).replace(hour=6, minute=30, second=0, microsecond=0)
        if datetime.fromtimestamp(start, PT) < opened:
            horizon = max(horizon, int(opened.timestamp()) + 40 * 60)
        window = [bar for bar in bars if start <= bar[0] < horizon]
        if window:
            return float(window[0][1])
        return None
    if not window:
        return None
    if which == "open":
        return float(window[0][1])
    return float(window[-1][4])


def _expiration_days(moment: int) -> list[date]:
    day = datetime.fromtimestamp(moment, PT).date()
    days = []
    for offset in range(8):
        candidate = day + timedelta(days=offset)
        if candidate.weekday() < 5:
            days.append(candidate)
    return days


def _ordered_strikes(strikes: list[float], stock: float, side: str) -> list[float]:
    """Nearest in-the-money strike first, then out toward the far target."""
    if side == "call":
        nearer = sorted((strike for strike in strikes if strike <= stock), reverse=True)
        farther = sorted(strike for strike in strikes if strike > stock)
    else:
        nearer = sorted(strike for strike in strikes if strike >= stock)
        farther = sorted((strike for strike in strikes if strike < stock), reverse=True)
    return nearer + farther


def _quote_days(session: date) -> list[date]:
    """Weekdays from the session date, nearest first.

    A name that does not list that day is tried on each later weekday until
    one is listed. Friday stays in the list so the comparison row can still
    be priced.
    """
    days: list[date] = []
    cursor = session
    while cursor <= session + timedelta(days=21):
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    week = weekly_expiration(session)
    if week not in days and week.weekday() < 5:
        days.append(week)
    return days


def _debit_at(
    ticker: str,
    side: str,
    expiration: date,
    strike: float,
    start: int,
) -> dict | None:
    bars = fetch_option_minutes(option_symbol(ticker, expiration, strike, side))
    debit = option_price(bars, start, "open")
    if debit is None:
        return None
    return {"strike": strike, "debit": debit, "expiration": expiration}


def _has_cash_strike(quotes: list[dict], cap: float | None) -> bool:
    """True once the ladder holds a strike this premium cap can buy."""
    if cap is None:
        return False
    return any(not _debit_over(row["debit"], cap) for row in quotes)


def _ladder_ready(quotes: list[dict], cash_cap: float | None) -> bool:
    """True once the walk can name the $1 strike and, when known, the cash strike."""
    has_dollar = any(row["debit"] <= CONTRACT_CAP for row in quotes)
    if cash_cap is None:
        return has_dollar
    return has_dollar and _has_cash_strike(quotes, cash_cap)


def _priced_strikes(
    ticker: str,
    side: str,
    stock: float,
    expiration: date,
    start: int,
    ceiling: float | None = None,
    cash_cap: float | None = None,
) -> list[dict]:
    """Price enough of the ladder to pick the chosen strike and the cash one.

    The walk stops once a strike at or under $1 is in hand and, when the
    balance was read, a strike that debit can still pay. Then it prices the
    far end of the target. A miss on the whole ladder is an empty list, which
    the checker treats as "ask again," not as a decision.
    """
    ordered = _ordered_strikes(ladder_strikes(stock, side, ceiling), stock, side)
    if not ordered:
        return []

    def price(strikes: list[float]) -> list[dict]:
        def one(strike: float) -> dict | None:
            return _debit_at(ticker, side, expiration, strike, start)

        with ThreadPoolExecutor(max_workers=4) as pool:
            found = [row for row in pool.map(one, strikes) if row]
        if found or not strikes:
            return found
        time.sleep(0.4)
        with ThreadPoolExecutor(max_workers=4) as pool:
            return [row for row in pool.map(one, strikes) if row]

    quotes: list[dict] = []
    seen: set[float] = set()
    for offset in range(0, len(ordered), 4):
        chunk = [strike for strike in ordered[offset : offset + 4] if strike not in seen]
        rows = price(chunk)
        for row in rows:
            seen.add(row["strike"])
            quotes.append(row)
        # The first strike under $1 can still be more than the account can pay.
        # Keep walking until a strike that fits the balance is in hand, so the
        # cash row is the nearest one and not the far tail.
        if _ladder_ready(quotes, cash_cap):
            break
    tail = [strike for strike in ordered[-4:] if strike not in seen]
    for row in price(tail):
        if row["strike"] in seen:
            continue
        seen.add(row["strike"])
        quotes.append(row)
    return quotes


def quote_contracts(
    ticker: str,
    side: str,
    stock: float,
    start: int,
    first: float | None,
    far: float | None,
    cash: float | None = None,
) -> list[dict]:
    """Price the chosen contract and the comparison rules at the fill."""
    session = datetime.fromtimestamp(start, PT).date()
    cap = premium_cap(cash)
    ladders: dict[date, list[dict]] = {}
    tried: set[date] = set()
    for day in _quote_days(session):
        tried.add(day)
        quotes = _priced_strikes(ticker, side, stock, day, start, far, cap)
        if not quotes:
            continue
        ladders[day] = quotes
        if day >= session:
            break
    week = weekly_expiration(session)
    if week not in tried and week.weekday() < 5:
        quotes = _priced_strikes(ticker, side, stock, week, start, far, cap)
        if quotes:
            ladders[week] = quotes
    return assemble_contracts(session, ladders, side, stock, first, far, start, cash)


def quote_contract(ticker: str, side: str, stock: float, start: int, far_target: float | None) -> dict | None:
    rows = quote_contracts(ticker, side, stock, start, far_target, far_target)
    chosen = next((row for row in rows if row["role"] == "chosen"), None)
    if chosen is None:
        return None
    return {"contract": chosen["contract"], "premium": chosen["premium"]}


def paper_rows(text: str) -> list[dict]:
    blotter = text.split("\n## Open marks\n", 1)[0]
    rows = []
    for line in blotter.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or cells[0] in ("Time", "") or set(cells[0]) <= {"-"}:
            continue
        padded = (cells + [""] * 9)[:9]
        premium = padded[8]
        rows.append(
            {
                "time": padded[0],
                "ticker": padded[1],
                "action": padded[2],
                "side": padded[3],
                "level": padded[4],
                "fill": padded[5],
                "reason": padded[6],
                "contract": padded[7],
                "premium": float(premium) if premium else None,
            }
        )
    return rows


def _open_entries(rows: list[dict]) -> list[dict]:
    open_entries = []
    for row in rows:
        if row["action"] == "entry":
            open_entries.append(row)
            continue
        for index, entry in enumerate(open_entries):
            if (
                entry["ticker"] == row["ticker"]
                and entry["side"] == row["side"]
                and entry["level"] == row["level"]
            ):
                open_entries.pop(index)
                break
    return open_entries


def _contract_symbol(row: dict) -> str | None:
    label = row.get("contract") or ""
    parts = label.split()
    if len(parts) != 2 or "/" not in parts[0] or parts[1][-1] not in ("C", "P"):
        return None
    month, day = parts[0].split("/")
    year = int(row["time"][:4])
    strike = float(parts[1][:-1])
    side = "call" if parts[1][-1] == "C" else "put"
    return option_symbol(row["ticker"], date(year, int(month), int(day)), strike, side)


def _target_pair(levels: list[dict], event: dict) -> tuple[float | None, float | None]:
    """The first posted number and the far one. Both are None when the note has neither."""
    for level in levels:
        if level.get("ticker") != event["ticker"]:
            continue
        if abs(float(level["price"]) - float(event["level"])) > 0.001:
            continue
        if _played_flip(level, event["side"]):
            targets = _book_targets(level, event["side"], levels)
        else:
            targets = _targets(level, event["side"])
        if not targets:
            return None, None
        return targets[0], targets[-1]
    return None, None


def quote_paper(
    events: list[dict],
    levels: list[dict],
    path: Path = PAPER_PATH,
    cash: float | None = None,
) -> list[dict]:
    """Attach the contract and its print. A failure leaves the row without a premium."""
    text = path.read_text() if path.is_file() else ""
    known = paper_rows(text)
    live_book = path.resolve() == LIVE_PATH.resolve()
    candidates = _live_candidate_book(text) if live_book else {}
    quoted = []
    for event in events:
        if event.get("kind") not in ("entry", "exit"):
            quoted.append(event)
            continue
        try:
            if event["kind"] == "entry":
                # Price the contract when the order goes out: the fill bar's close.
                start = int(event.get("fill_at") or event["close_at"] - TEN_MIN)
                first, far = _target_pair(levels, event)
                found = quote_contracts(
                    event["ticker"],
                    event["side"],
                    float(event["fill"]),
                    start,
                    first,
                    far,
                    cash,
                )
                if live_book:
                    contract, premium = named_live_contract(found, event["close_at"])
                else:
                    chosen = next((row for row in found if row["role"] == "chosen"), None)
                    contract = "" if chosen is None else chosen["contract"]
                    premium = None if chosen is None else chosen["premium"]
                fields = _candidate_fields(found)
                event = {
                    **event,
                    "contracts": found,
                    "cash": cash,
                    **fields,
                    "halfway": halfway_blocks(found, event["close_at"]),
                }
                candidates[(event["ticker"], event["side"], f"{float(event['level']):.2f}")] = fields
            else:
                match = next(
                    (
                        row
                        for row in reversed(_open_entries(known))
                        if row["ticker"] == event["ticker"]
                        and row["side"] == event["side"]
                        and abs(float(row["level"]) - float(event["level"])) < 0.001
                    ),
                    None,
                )
                contract = "" if match is None else match["contract"]
                premium = None
                symbol = None if match is None else _contract_symbol(match)
                if symbol and contract != "none":
                    start = event["close_at"] - TEN_MIN
                    price = option_price(fetch_option_minutes(symbol, span="10d"), start, "close")
                    if price is not None:
                        premium = round(price, 2)
                key = (event["ticker"], event["side"], f"{float(event['level']):.2f}")
                saved = candidates.get(key) or {}
                when = datetime.fromtimestamp(event["close_at"], PT).strftime("%Y-%m-%d %H:%M PT")
                start = event["close_at"] - TEN_MIN
                event = {
                    **event,
                    "dollar_contract": saved.get("dollar_contract") or "",
                    "cash_contract": saved.get("cash_contract") or "",
                    "dollar_premium": _mark_label(
                        event["ticker"], saved.get("dollar_contract") or "", when, start
                    ),
                    "cash_premium": _mark_label(
                        event["ticker"], saved.get("cash_contract") or "", when, start
                    ),
                }
            event = {**event, "contract": contract, "premium": premium}
            when = datetime.fromtimestamp(event["close_at"], PT).strftime("%Y-%m-%d %H:%M PT")
            known.append(
                {
                    "time": when,
                    "ticker": event["ticker"],
                    "action": event["kind"],
                    "side": event["side"],
                    "level": f"{event['level']:.2f}",
                    "contract": contract,
                    "premium": premium,
                }
            )
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            pass
        quoted.append(event)
    return quoted


def refresh_open_marks(path: Path = PAPER_PATH, now: int | None = None) -> bool:
    """Rewrite the open-mark table from the latest option print."""
    if not path.is_file():
        return False
    text = path.read_text()
    rows = _open_entries(paper_rows(text))
    previous = {}
    marks_text = text.split("\n## Open marks\n", 1)[1] if "\n## Open marks\n" in text else ""
    for line in marks_text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and cells[0] not in ("Contract", "") and not set(cells[0]) <= {"-"}:
            previous[cells[0]] = line
    moment = int(datetime.now(PT).timestamp()) if now is None else now
    when = datetime.fromtimestamp(moment, PT).strftime("%Y-%m-%d %H:%M PT")
    lines = [
        "| Contract | Premium | As of | Source |",
        "|----------|---------|-------|--------|",
    ]
    for row in rows:
        key = f"{row['ticker']} {row['contract']}"
        symbol = _contract_symbol(row)
        bars = fetch_option_minutes(symbol) if symbol else []
        usable = [bar for bar in bars if bar[4] is not None and bar[0] <= moment]
        if usable:
            lines.append(
                f"| {key} | {float(usable[-1][4]):.2f} | {when} | Yahoo |"
            )
        elif key in previous:
            lines.append(previous[key])
    blotter = text.split("\n## Open marks\n", 1)[0].rstrip()
    if len(lines) == 2 and not previous:
        return False
    path.write_text(blotter + "\n\n## Open marks\n\n" + "\n".join(lines) + "\n")
    return len(lines) != 2 or bool(previous)


def contract_rows(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or cells[0] in ("Time", "") or set(cells[0]) <= {"-"}:
            continue
        padded = (cells + [""] * 9)[:9]
        rows.append(
            {
                "time": padded[0],
                "ticker": padded[1],
                "level": padded[2],
                "role": padded[3],
                "contract": padded[4],
                "entry": padded[5],
                "price": padded[6],
                "return": padded[7],
                "state": padded[8],
            }
        )
    return rows


def _contracts_text(rows: list[dict]) -> str:
    lines = [
        (
            f"| {row['time']} | {row['ticker']} | {row['level']} | {row['role']} "
            f"| {row['contract']} | {row['entry']} | {row['price']} | {row['return']} "
            f"| {row['state']} |"
        )
        for row in rows
    ]
    return CONTRACTS_HEADER + "\n".join(lines) + ("\n" if lines else "")


def _row_symbol(row: dict) -> str | None:
    return _contract_symbol(
        {"contract": row["contract"], "ticker": row["ticker"], "time": row["time"]}
    )


def record_contracts(events: list[dict], path: Path = CONTRACTS_PATH) -> None:
    """Append the fill's candidates, and close them when that trade exits."""
    rows = contract_rows(path.read_text()) if path.is_file() else []
    changed = False
    for event in events:
        if event.get("kind") == "entry":
            when = datetime.fromtimestamp(event["close_at"], PT).strftime("%Y-%m-%d %H:%M PT")
            level = f"{float(event['level']):.2f}"
            known = {(row["time"], row["ticker"], row["level"], row["role"]) for row in rows}
            seen_labels: set[str] = set()
            for item in event.get("contracts") or []:
                label = item.get("contract") or "none"
                if label not in ("", "none") and item.get("role") != "cash":
                    if label in seen_labels:
                        continue
                    seen_labels.add(label)
                key = (when, event["ticker"], level, item["role"])
                if key in known:
                    continue
                premium = item.get("premium")
                rows.append(
                    {
                        "time": when,
                        "ticker": event["ticker"],
                        "level": level,
                        "role": item["role"],
                        "contract": item.get("contract") or "none",
                        "entry": "" if premium is None else f"{float(premium):.2f}",
                        "price": "",
                        "return": "",
                        "state": "open",
                    }
                )
                changed = True
            continue
        if event.get("kind") != "exit":
            continue
        level = f"{float(event['level']):.2f}"
        start = event["close_at"] - TEN_MIN
        for row in rows:
            if row["state"] != "open" or row["ticker"] != event["ticker"] or row["level"] != level:
                continue
            symbol = _row_symbol(row)
            if symbol:
                price = option_price(fetch_option_minutes(symbol, span="10d"), start, "close")
                if price is not None:
                    row["price"] = f"{price:.2f}"
                    row["return"] = format_return(row["entry"], row["price"])
            row["state"] = "exit"
            changed = True
    if not changed:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_contracts_text(rows))


def refresh_contract_marks(path: Path = CONTRACTS_PATH, now: int | None = None) -> bool:
    """Rewrite the open comparison rows from the latest option print."""
    if not path.is_file():
        return False
    rows = contract_rows(path.read_text())
    moment = int(datetime.now(PT).timestamp()) if now is None else now
    changed = False
    for row in rows:
        if row["state"] != "open":
            continue
        symbol = _row_symbol(row)
        if not symbol:
            continue
        usable = [
            bar
            for bar in fetch_option_minutes(symbol)
            if bar[4] is not None and bar[0] <= moment
        ]
        if not usable:
            continue
        price = f"{float(usable[-1][4]):.2f}"
        returned = format_return(row["entry"], price)
        if price != row["price"] or returned != row["return"]:
            row["price"] = price
            row["return"] = returned
            changed = True
    if changed:
        path.write_text(_contracts_text(rows))
    return changed


def session_kind(close_at: int) -> str:
    """Paper through Wednesday 2026-10-21. Thursday is the first live session."""
    when = datetime.fromtimestamp(close_at, PT).date()
    return "live" if when >= LIVE_FROM else "paper"


def cash_fit(event: dict) -> str:
    """A live contract has to fit the account balance. A missing quote is not a refusal."""
    contract = event.get("contract")
    premium = event.get("premium")
    if contract in (None, ""):
        return "quote"
    if balance_amount(event.get("cash")) is None:
        return "unread"
    if contract == "none" or premium is None:
        return "none"
    if not debit_fits(premium, event.get("cash")):
        return "over"
    return "fits"


def _cash_alternative(event: dict) -> tuple[str, str]:
    """The strike the balance can buy, and whether it sits past halfway."""
    rows = event.get("contracts") or []
    cash = next((row for row in rows if row.get("role") == "cash"), None)
    if cash is None:
        return "", ""
    label = cash.get("contract") or ""
    if label in ("", "none"):
        return "none", ""
    return label, cash.get("halfway") or ""


def _premium_text(premium) -> str:
    if premium is None or premium == "":
        return ""
    return f" at ${float(premium):.2f}"


def _live_cash_sentence(event: dict) -> str:
    """Say which strike the plan names, and keep the other strike on the row."""
    fit = cash_fit(event)
    if fit == "quote":
        return "The quote failed. The next check will price it again."
    if fit == "unread":
        return "The account balance could not be read, so this stays a plan."
    rows = event.get("contracts") or []
    cash = _role_row(rows, "cash") or {}
    dollar = _role_row(rows, "chosen") or {}
    cash_label = cash.get("contract") or ""
    dollar_label = dollar.get("contract") or ""
    named = event.get("contract") or ""
    blocks = halfway_blocks(rows, event.get("close_at") or 0)
    if named and cash_label and named == cash_label and named != "none":
        sentence = f"The live contract is {named}{_premium_text(cash.get('premium'))}."
        if dollar_label not in ("", "none") and dollar_label != named:
            sentence += (
                f" The $1 strike {dollar_label}{_premium_text(dollar.get('premium'))}"
                " stays on the row."
            )
        if blocks == "past":
            sentence += " Halfway does not refuse a next-day strike."
        elif blocks == "inside":
            sentence += " The strike is in front of halfway."
        return sentence
    if fit == "fits":
        return "The debit fits the account balance."
    if fit == "over":
        sentence = "The debit is over the account balance, so it is not the live contract."
        if cash_label not in ("", "none"):
            if blocks == "blocks":
                sentence += (
                    f" The nearest strike the account can buy is {cash_label}"
                    f"{_premium_text(cash.get('premium'))}, and halfway blocks it on 0DTE."
                )
            else:
                where = "past halfway" if blocks == "past" else "in front of halfway"
                sentence += (
                    f" The nearest strike the account can buy is {cash_label}"
                    f"{_premium_text(cash.get('premium'))}, {where}."
                )
        else:
            sentence += " No strike the account can buy was still in front of the far target."
        return sentence
    if dollar and dollar.get("why") == "no-target":
        return "This level has no further number, so no contract was chosen."
    return "No strike under $1 was still in front of the far target."


def live_notice(event: dict) -> str:
    """The checker text for a live plan. A sent order replaces the confirm line."""
    text = format_live(event)
    if text.endswith(" Not an order."):
        text = text[: -len(" Not an order.")]
    order = event.get("order_id")
    if event.get("kind") == "exit":
        if order:
            return text + f" Live session. Sold at {event.get('order_price')}. Order {order}."
        return text + " Live session. Not an order."
    if order:
        return text + f" Live session. Order {order} at {event.get('order_price')}."
    return (
        text
        + f" Live session. {_live_cash_sentence(event)} Waiting for confirm. Not an order."
    )


def entry_order_block(event: dict) -> str:
    """Why this live entry is not sent. Empty means one qualifying contract."""
    if event.get("kind") != "entry":
        return "exit"
    close_at = int(event.get("close_at") or 0)
    if session_kind(close_at) != "live":
        return "paper"
    rows = event.get("contracts") or []
    if not rows:
        return "empty"
    if balance_amount(event.get("cash")) is None:
        return "unread"
    cash = _role_row(rows, "cash") or {}
    label = cash.get("contract") or ""
    if label in ("", "none"):
        return "none"
    if halfway_blocks(rows, close_at) == "blocks":
        return "halfway"
    named, premium = named_live_contract(rows, close_at)
    if named != label or premium is None:
        return "none"
    if MIN_PREMIUM and float(premium) < MIN_PREMIUM:
        return "floor"
    if not debit_fits(premium, event.get("cash")):
        return "over"
    return ""


def _broker_book(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _remember_order(path: Path, key: str, record: dict) -> None:
    book = _broker_book(path)
    book[key] = record
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(book, indent=2) + "\n")


def route_live_order(
    event: dict, broker=None, book_path: Path | None = None, cash: float | None = None
) -> dict:
    """Buy a qualifying entry, or sell the open Agentic contract on its exit.

    A balance that was not read, a cash strike of none, an empty ladder, a
    0DTE halfway block, or a debit the balance cannot pay writes nothing to
    the broker. A sell that is already working is not sent again.
    """
    if event.get("cash") is None and cash is not None:
        event["cash"] = cash
    if event.get("kind") == "entry" and balance_amount(event.get("cash")) is None:
        return event
    if event.get("kind") not in ("entry", "exit"):
        return event
    close_at = int(event.get("close_at") or 0)
    if session_kind(close_at) != "live":
        return event
    path = book_path or BROKER_PATH
    key = event_id(event.get("ticker") or "", event)
    book = _broker_book(path)
    prior = book.get(key) or {}
    if prior.get("status") in ("sent", "working", "skip"):
        if prior.get("order_id"):
            event["order_id"] = prior["order_id"]
            event["order_price"] = prior.get("price") or ""
        return event
    retry = prior.get("status") == "error" and prior.get("qualified") is True
    label = event.get("contract") or prior.get("contract") or ""
    if event.get("kind") == "entry":
        if event.get("open") is False:
            return event
        blocked = "" if retry else entry_order_block(event)
        if blocked:
            event["order_block"] = blocked
            return event
        if not label:
            label = ((_role_row(event.get("contracts"), "cash") or {}).get("contract")) or ""
    elif label in ("", "none"):
        return event
    if not label:
        return event
    if broker is None:
        if not SEND_ORDERS:
            return event
        from robinhood_mcp import RobinhoodBroker

        broker = RobinhoodBroker()
    year = datetime.fromtimestamp(close_at, PT).year
    ref = str(uuid.uuid5(uuid.NAMESPACE_URL, "autobonk:" + key))
    try:
        if event["kind"] == "entry":
            result = broker.buy(event["ticker"], label, year, ref, cash=event.get("cash"))
        else:
            result = broker.sell(event["ticker"], label, year, ref)
    except Exception:
        attempts = int(prior.get("attempts") or 0) + 1
        # An entry gives up after three tries. An exit keeps trying: a contract left open is the worse failure.
        gave_up = attempts > 2 and event["kind"] == "entry"
        _remember_order(
            path,
            key,
            {
                "status": "skip" if gave_up else "error",
                "qualified": event.get("kind") == "entry",
                "attempts": attempts,
                "kind": event["kind"],
                "ticker": event.get("ticker") or "",
                "contract": label,
                "side": event.get("side") or "",
                "level": event.get("level"),
                "close_at": close_at,
                "reason": event.get("reason") or "",
            },
        )
        return event
    reason = "" if result.get("sent") else (result.get("reason") or "skip")
    if result.get("sent"):
        status = "sent"
    elif reason == "working":
        status = "working"
    elif reason in ("quote", "broker"):
        status = "error"
    else:
        status = "skip"
    attempts = int(prior.get("attempts") or 0) + 1
    if status == "error" and attempts > 2 and event["kind"] == "entry":
        status = "skip"
    price = ""
    if result.get("price") not in (None, ""):
        try:
            price = f"{float(result['price']):.2f}"
        except (TypeError, ValueError):
            price = str(result.get("price") or "")
    _remember_order(
        path,
        key,
        {
            "status": status,
            "qualified": event.get("kind") == "entry",
            "attempts": attempts,
            "order_id": result.get("order_id") or "",
            "price": price,
            "kind": event["kind"],
            "ticker": event.get("ticker") or "",
            "contract": label,
            "side": event.get("side") or "",
            "level": event.get("level"),
            "close_at": close_at,
            "reason": event.get("reason") or "",
            "broker_reason": reason,
        },
    )
    if result.get("sent"):
        event["order_id"] = result.get("order_id") or ""
        event["order_price"] = price
    return event


def retry_live_orders(
    book_path: Path | None = None, broker=None, cash: float | None = None
) -> None:
    """Try once more when the last send failed. A sent or working order stays put."""
    path = book_path or BROKER_PATH
    book = _broker_book(path)
    for key, record in list(book.items()):
        if record.get("status") != "error":
            continue
        event = {
            "kind": record.get("kind") or "",
            "ticker": record.get("ticker") or "",
            "side": record.get("side") or "",
            "level": record.get("level"),
            "close_at": record.get("close_at") or 0,
            "reason": record.get("reason") or "",
            "contract": record.get("contract") or "",
            "cash": cash,
        }
        route_live_order(event, broker=broker, book_path=path, cash=cash)


def paper_line(event: dict) -> str | None:
    """One blotter row for an entry or an exit. A skip is not a trade."""
    if event.get("kind") not in ("entry", "exit"):
        return None
    when = datetime.fromtimestamp(event["close_at"], PT).strftime("%Y-%m-%d %H:%M PT")
    price = event["fill"] if event.get("fill") is not None else event["bar"]["c"]
    premium = event.get("premium")
    premium_text = "" if premium is None else f"{float(premium):.2f}"
    return (
        f"| {when} | {event['ticker']} | {event['kind']} | {event['side']} "
        f"| {event['level']:.2f} | {price:.2f} | {event['reason']} "
        f"| {event.get('contract') or ''} | {premium_text} |"
    )


def _average_cell(bar: dict, key: str) -> str:
    value = bar.get(key)
    if value is None:
        return ""
    return f"{value:.2f} ({bar['c'] - value:+.2f})"


def _nearby_levels(levels: list[dict], ticker: str, close: float) -> str:
    """Posted prices within $1 of the close. The nearest one, when none are."""
    same = []
    for level in levels:
        if level.get("ticker") != ticker:
            continue
        try:
            same.append(float(level["price"]))
        except (TypeError, ValueError, KeyError):
            continue
    if not same:
        return ""
    close_ones = [price for price in same if abs(close - price) <= 1]
    chosen = close_ones or [min(same, key=lambda price: abs(close - price))]
    ordered = sorted(chosen, key=lambda price: (abs(close - price), price))
    return ", ".join(f"{price:.2f} ({close - price:+.2f})" for price in ordered)


def context_line(event: dict, levels: list[dict] | None = None) -> str | None:
    """The signal candle on an entry, the exit candle on an exit. A skip is not a row."""
    if event.get("kind") not in ("entry", "exit"):
        return None
    bar = event.get("bar") or {}
    if "c" not in bar:
        return None
    when = datetime.fromtimestamp(event["close_at"], PT).strftime("%Y-%m-%d %H:%M PT")
    price = event["fill"] if event.get("fill") is not None else bar["c"]
    color = "green" if _green(bar) else "red" if _red(bar) else "flat"
    candle = f"{color} O{bar['o']:.2f} H{bar['h']:.2f} L{bar['l']:.2f} C{bar['c']:.2f}"
    purple = bar.get("purple")
    yellow = bar.get("yellow")
    volume = bar.get("v")
    volume_text = "" if volume is None else f"{int(round(volume)):,}"
    return (
        f"| {when} | {event['ticker']} | {event['kind']} | {event['side']} "
        f"| {event['level']:.2f} | {price:.2f} | {candle} "
        f"| {'' if purple is None else f'{purple:.2f}'} "
        f"| {'' if yellow is None else f'{yellow:.2f}'} "
        f"| {_average_cell(bar, 'sma')} | {_average_cell(bar, 'sma50')} "
        f"| {_average_cell(bar, 'sma200')} "
        f"| {_nearby_levels(levels or [], event['ticker'], bar['c'])} | {volume_text} |"
    )


def append_context(
    events: list[dict], levels: list[dict] | None = None, path: Path = CONTEXT_PATH
) -> None:
    lines = [line for line in (context_line(event, levels) for event in events) if line]
    if not lines:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text() if path.is_file() else ""
    if not existing:
        existing = CONTEXT_HEADER
    known = set()
    for line in existing.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 5 and cells[0] not in ("Time", ""):
            known.add((cells[0], cells[1], cells[2], cells[4]))
    fresh = []
    for line in lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        key = (cells[0], cells[1], cells[2], cells[4])
        if key in known:
            continue
        known.add(key)
        fresh.append(line)
    if not fresh:
        return
    path.write_text(existing.rstrip() + "\n" + "\n".join(fresh) + "\n")
    _store_rows("context", fresh, path, CONTEXT_PATH)


def _cell_premium(value) -> str:
    if value is None or value == "":
        return ""
    return f"{float(value):.2f}"


def live_line(event: dict) -> str | None:
    """One plan row. The contract is the named live strike. Both candidates are recorded."""
    line = paper_line(event)
    if line is None:
        return None
    if event.get("kind") != "entry":
        return (
            line.rstrip()[:-1].rstrip()
            + " |  | "
            + f"{event.get('dollar_contract') or ''} | {_cell_premium(event.get('dollar_premium'))} | "
            + f"{event.get('cash_contract') or ''} | {_cell_premium(event.get('cash_premium'))} |  |"
        )
    rows = event.get("contracts") or []
    dollar = _role_row(rows, "chosen") or {}
    cash = _role_row(rows, "cash") or {}
    halfway = event.get("halfway") or halfway_blocks(rows, event.get("close_at") or 0)
    return (
        line.rstrip()[:-1].rstrip()
        + f" | {cash_fit(event)} | {dollar.get('contract') or ''} | "
        + f"{_cell_premium(dollar.get('premium'))} | {cash.get('contract') or ''} | "
        + f"{_cell_premium(cash.get('premium'))} | {halfway} |"
    )


def append_live(events: list[dict], path: Path = LIVE_PATH) -> None:
    """A live plan. This does not write the paper tape and it does not send an order."""
    lines = [line for line in (live_line(event) for event in events) if line]
    if not lines:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        path.write_text(
            "# Live plans\n\n"
            "Thursday 2026-10-22 is the first live session. Agentic only. "
            "One contract. The live debit has to fit the account balance. "
            "A row is the plan. It is not a paper row. "
            "The fade checker stays off. "
            "On a next-day expiration the contract column is the nearest strike the balance can buy "
            "that the far target can still reach. Halfway does not refuse that expiration. "
            "On 0DTE, halfway still refuses that strike. "
            "The $1 strike and the cash strike are both recorded, with the entry premium, "
            "and both are marked at the exit. "
            "A cash cell of quote means the chain was not priced, and the next check tries again.\n\n"
            "| Time | Ticker | Action | Side | Level | Fill | Reason | Contract | Premium | Cash | $1 strike | $1 premium | Cash strike | Cash premium | Halfway |\n"
            "|------|--------|--------|------|-------|------|--------|----------|---------|------|-----------|------------|-------------|--------------|---------|\n"
        )
    text = path.read_text()
    upgraded = text.splitlines()
    if _upgrade_live_header(upgraded):
        text = "\n".join(upgraded) + ("\n" if text.endswith("\n") else "")
        path.write_text(text)
    known = set()
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 5 and cells[0] not in ("Time", ""):
            known.add((cells[0], cells[1], cells[2], cells[4]))
    fresh = []
    for line in lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        key = (cells[0], cells[1], cells[2], cells[4])
        if key in known:
            continue
        known.add(key)
        fresh.append(line)
    if not fresh:
        return
    path.write_text(text.rstrip() + "\n" + "\n".join(fresh) + "\n")
    _store_rows("live", fresh, path, LIVE_PATH)


def append_paper(events: list[dict], path: Path = PAPER_PATH) -> None:
    lines = [line for line in (paper_line(event) for event in events) if line]
    if not lines:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        path.write_text(
            "# Paper trades\n\n"
            "Each row is a checker entry or exit. Nothing here was sent to Robinhood. "
            "A row does not fill the journal Trade column and is not a pattern.\n\n"
            + PAPER_HEADER
        )
    text = path.read_text()
    blotter, separator, marks = text.partition("\n## Open marks\n")
    known = set()
    for line in blotter.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 5 and cells[0] not in ("Time", ""):
            known.add((cells[0], cells[1], cells[2], cells[4]))
    fresh = []
    for line in lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        key = (cells[0], cells[1], cells[2], cells[4])
        if key in known:
            continue
        known.add(key)
        fresh.append(line)
    if not fresh:
        return
    addition = "\n".join(fresh) + "\n"
    if separator:
        path.write_text(blotter.rstrip() + "\n" + addition + "\n## Open marks\n" + marks)
    else:
        with path.open("a") as handle:
            handle.write(addition)
    _store_rows("paper", fresh, path, PAPER_PATH)


def refresh_dashboard() -> None:
    path = Path(__file__).resolve().parent / "dashboard.py"
    spec = importlib.util.spec_from_file_location("dashboard", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main()


def notify_live(event: dict) -> None:
    """Desktop toast for a live entry or exit. The order, when one went out, is in alerts/broker.json."""
    headline = f"{event['ticker']} live {event['kind']}"
    price = event["fill"] if event.get("fill") is not None else event["bar"]["c"]
    if event.get("order_id"):
        sent = f"Order sent at {event.get('order_price') or '?'}."
    else:
        sent = "No order sent. The plan stays in alerts/live.md."
    body = f"{event['side']} {event['level']:.2f} at {price:.2f}. {sent}"
    try:
        subprocess.run(
            [
                "omarchy",
                "notification",
                "send",
                "--app-name",
                "AutoBonk",
                "-u",
                "normal",
                headline,
                body,
            ],
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return


def notify_paper(event: dict) -> None:
    """Desktop toast. A failure leaves the paper row and the Discord alert in place."""
    headline = f"{event['ticker']} paper {event['kind']}"
    price = event["fill"] if event.get("fill") is not None else event["bar"]["c"]
    body = f"{event['side']} {event['level']:.2f} at {price:.2f}. Not an order."
    try:
        subprocess.run(
            [
                "omarchy",
                "notification",
                "send",
                "--app-name",
                "AutoBonk",
                "-u",
                "normal",
                headline,
                body,
            ],
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return


def _row_clock(text: str) -> datetime:
    return datetime.strptime(text.replace(" PT", ""), "%Y-%m-%d %H:%M").replace(tzinfo=PT)


def _level_known(levels: list[dict], event: dict) -> bool:
    for level in levels:
        if level.get("ticker") != event["ticker"]:
            continue
        if abs(float(level["price"]) - float(event["level"])) <= 0.001:
            return True
    return False


def _paint_contract(line: str, contract: str, premium: float | None) -> str:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    cells = (cells + [""] * 9)[:9]
    cells[7] = contract
    cells[8] = "" if premium is None else f"{float(premium):.2f}"
    return "| " + " | ".join(cells) + " |"


LIVE_HEADER_ROW = (
    "| Time | Ticker | Action | Side | Level | Fill | Reason | Contract | Premium "
    "| Cash | $1 strike | $1 premium | Cash strike | Cash premium | Halfway |"
)
LIVE_RULE_ROW = (
    "|------|--------|--------|------|-------|------|--------|----------|---------"
    "|------|-----------|------------|-------------|--------------|---------|"
)


def _paint_live_contract(
    line: str,
    contract: str,
    premium: float | None,
    cash: str,
    dollar: str,
    dollar_premium,
    cash_strike: str,
    cash_premium,
    halfway: str,
) -> str:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    cells = (cells + [""] * 15)[:15]
    cells[7] = contract
    cells[8] = "" if premium is None else f"{float(premium):.2f}"
    cells[9] = cash
    cells[10] = dollar
    cells[11] = _cell_premium(dollar_premium)
    cells[12] = cash_strike
    cells[13] = _cell_premium(cash_premium)
    cells[14] = halfway
    return "| " + " | ".join(cells) + " |"


def _migrate_live_row(cells: list[str]) -> str:
    """Keep an older plan row readable after the candidate columns are added."""
    width = len(cells)
    base = (cells + [""] * 7)[:7]
    contract = cells[7] if width > 7 else ""
    premium = cells[8] if width > 8 else ""
    cash = cells[9] if width > 9 else ""
    if width >= 12:
        dollar = contract
        dollar_premium = premium
        cash_strike = cells[10]
        halfway = cells[11]
    else:
        dollar = ""
        dollar_premium = ""
        cash_strike = ""
        halfway = ""
    merged = base + [
        contract,
        premium,
        cash,
        dollar,
        dollar_premium,
        cash_strike,
        "",
        halfway,
    ]
    return "| " + " | ".join(merged) + " |"


def _upgrade_live_header(lines: list[str]) -> bool:
    """Give an older live table the $1 strike, the cash strike, and halfway."""
    for index, line in enumerate(lines):
        if not line.startswith("| Time |") or "Cash" not in line or "$1 strike" in line:
            continue
        lines[index] = LIVE_HEADER_ROW
        rule = index + 1
        if rule < len(lines) and set(lines[rule].replace("|", "").replace(" ", "")) <= {"-"}:
            lines[rule] = LIVE_RULE_ROW
            rule += 1
        while rule < len(lines) and lines[rule].startswith("|"):
            cells = [cell.strip() for cell in lines[rule].strip().strip("|").split("|")]
            if cells and cells[0] not in ("Time", "") and not set(cells[0]) <= {"-"}:
                lines[rule] = _migrate_live_row(cells)
            rule += 1
        return True
    return False


def fill_missing_contracts(
    levels: list[dict],
    path: Path = PAPER_PATH,
    contracts_path: Path = CONTRACTS_PATH,
    cash: float | None = None,
) -> bool:
    """Price paper rows whose contract cell is still blank.

    A blank is a quote that returned nothing. "none" is a finished decision
    and stays put. The comparison file is written from the same quote.
    """
    if not path.is_file():
        return False
    text = path.read_text()
    blotter, separator, marks = text.partition("\n## Open marks\n")
    lines = blotter.splitlines()
    live_table = "| Cash |" in blotter
    changed = _upgrade_live_header(lines)
    parsed: list[tuple[int, dict]] = []
    for index, line in enumerate(lines):
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or cells[0] in ("Time", "") or set(cells[0]) <= {"-"}:
            continue
        padded = (cells + [""] * 9)[:9]
        premium = padded[8]
        parsed.append(
            (
                index,
                {
                    "time": padded[0],
                    "ticker": padded[1],
                    "action": padded[2],
                    "side": padded[3],
                    "level": padded[4],
                    "fill": padded[5],
                    "reason": padded[6],
                    "contract": padded[7],
                    "premium": float(premium) if premium else None,
                },
            )
        )
    exit_for: dict[int, tuple[int, dict]] = {}
    open_entries: list[tuple[int, dict]] = []
    for index, row in parsed:
        if row["action"] == "entry":
            open_entries.append((index, row))
            continue
        for cursor, (entry_index, entry) in enumerate(open_entries):
            if (
                entry["ticker"] == row["ticker"]
                and entry["side"] == row["side"]
                and entry["level"] == row["level"]
            ):
                exit_for[entry_index] = (index, row)
                open_entries.pop(cursor)
                break
    events = []
    for index, row in parsed:
        if row["action"] != "entry" or row["contract"] or not row["fill"]:
            continue
        close_at = int(_row_clock(row["time"]).timestamp())
        event = {
            "kind": "entry",
            "ticker": row["ticker"],
            "side": row["side"],
            "level": float(row["level"]),
            "fill": float(row["fill"]),
            "close_at": close_at,
        }
        if not _level_known(levels, event):
            continue
        try:
            first, far = _target_pair(levels, event)
            found = quote_contracts(
                event["ticker"],
                event["side"],
                float(event["fill"]),
                close_at - TEN_MIN,
                first,
                far,
                cash,
            )
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            continue
        if not found:
            continue
        if live_table:
            contract, premium = named_live_contract(found, close_at)
        else:
            chosen = next((item for item in found if item["role"] == "chosen"), None)
            contract = "" if chosen is None else chosen["contract"]
            premium = None if chosen is None else chosen.get("premium")
        if not contract:
            continue
        fields = _candidate_fields(found)
        if live_table:
            priced = {
                **event,
                "contract": contract,
                "premium": premium,
                "contracts": found,
                "cash": cash,
            }
            lines[index] = _paint_live_contract(
                lines[index],
                contract,
                premium,
                cash_fit(priced),
                fields["dollar_contract"],
                fields["dollar_premium"],
                fields["cash_contract"],
                fields["cash_premium"],
                halfway_blocks(found, close_at),
            )
        else:
            lines[index] = _paint_contract(lines[index], contract, premium)
        changed = True
        events.append(
            {
                **event,
                "contracts": found,
                "contract": contract,
                "premium": premium,
                "reason": row.get("reason") or "retest",
                "open": index not in exit_for,
                "cash": cash,
            }
        )
        paired = exit_for.get(index)
        if paired is None or paired[1]["contract"]:
            continue
        exit_index, exit_row = paired
        exit_premium = None
        symbol = _contract_symbol({**row, "contract": contract})
        exit_at = int(_row_clock(exit_row["time"]).timestamp())
        when = exit_row["time"]
        if symbol and contract != "none":
            price = option_price(
                fetch_option_minutes(symbol, span="10d"), exit_at - TEN_MIN, "close"
            )
            if price is not None:
                exit_premium = round(price, 2)
        if live_table:
            lines[exit_index] = _paint_live_contract(
                lines[exit_index],
                contract,
                exit_premium,
                "",
                fields["dollar_contract"],
                _mark_label(row["ticker"], fields["dollar_contract"], when, exit_at - TEN_MIN),
                fields["cash_contract"],
                _mark_label(row["ticker"], fields["cash_contract"], when, exit_at - TEN_MIN),
                "",
            )
        else:
            lines[exit_index] = _paint_contract(lines[exit_index], contract, exit_premium)
        events.append(
            {
                "kind": "exit",
                "ticker": row["ticker"],
                "side": row["side"],
                "level": float(row["level"]),
                "reason": exit_row.get("reason") or "reclaim",
                "contract": contract,
                "close_at": int(_row_clock(exit_row["time"]).timestamp()),
            }
        )
    if not changed:
        return False
    rewritten = "\n".join(lines)
    if blotter.endswith("\n"):
        rewritten += "\n"
    path.write_text(rewritten + separator + marks)
    record_contracts(events, contracts_path)
    for item in events:
        if item.get("kind") == "entry" and item.get("open") is False:
            continue
        try:
            route_live_order(item, cash=cash)
        except Exception:
            pass
    return True


def _window_close(symbol: str, moment: int) -> float | None:
    """The option print on the exit bar. A missed tape is left for the next check."""
    try:
        price = option_price(fetch_option_minutes(symbol, span="10d"), moment - TEN_MIN, "close")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    if price is None:
        return None
    return round(float(price), 2)


def repair_exit_premiums(
    path: Path = PAPER_PATH,
    contracts_path: Path = CONTRACTS_PATH,
    option_mark=None,
) -> bool:
    """Fill an exit premium the first quote missed. A priced cell stays put."""
    if not path.is_file():
        return False
    marker = _window_close if option_mark is None else option_mark
    text = path.read_text()
    blotter, separator, marks = text.partition("\n## Open marks\n")
    lines = blotter.splitlines()
    width = 15 if "$1 strike" in blotter else 12 if "| Cash |" in blotter else 9
    parsed = paper_rows(blotter)
    opens: list[dict] = []
    pairs = []
    table_lines = [index for index, line in enumerate(lines) if line.startswith("|")]
    row_index = 0
    for index in table_lines:
        cells = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
        if not cells or cells[0] in ("Time", "") or set(cells[0]) <= {"-"}:
            continue
        if row_index >= len(parsed):
            break
        row = parsed[row_index]
        row_index += 1
        if row["action"] == "entry":
            opens.append(row)
            continue
        for spot, entry in enumerate(opens):
            if (
                entry["ticker"] == row["ticker"]
                and entry["side"] == row["side"]
                and entry["level"] == row["level"]
            ):
                pairs.append((entry, row, index))
                opens.pop(spot)
                break
    changed = False
    priced: list[tuple[dict, dict, float]] = []
    for entry, exit_row, index in pairs:
        if exit_row.get("premium") is not None:
            continue
        contract = exit_row.get("contract") or ""
        if contract in ("", "none"):
            continue
        symbol = _contract_symbol(exit_row)
        if not symbol:
            continue
        try:
            moment = int(_row_clock(exit_row["time"]).timestamp())
            price = marker(symbol, moment)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            continue
        if price is None:
            continue
        premium = round(float(price), 2)
        cells = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
        cells = (cells + [""] * width)[:width]
        cells[8] = f"{premium:.2f}"
        lines[index] = "| " + " | ".join(cells) + " |"
        exit_row["premium"] = premium
        priced.append((entry, exit_row, premium))
        changed = True
    if priced and contracts_path.is_file():
        rows = contract_rows(contracts_path.read_text())
        contracts_changed = False
        for entry, exit_row, _premium in priced:
            moment = int(_row_clock(exit_row["time"]).timestamp())
            for row in rows:
                if row["state"] not in ("open", "exit") or row["price"]:
                    continue
                if (
                    row["time"] != entry["time"]
                    or row["ticker"] != entry["ticker"]
                    or row["level"] != entry["level"]
                ):
                    continue
                symbol = _row_symbol(row)
                if not symbol:
                    continue
                try:
                    price = marker(symbol, moment)
                except (urllib.error.URLError, TimeoutError, OSError, ValueError):
                    continue
                if price is None:
                    continue
                row["price"] = f"{round(float(price), 2):.2f}"
                row["return"] = format_return(row["entry"], row["price"])
                contracts_changed = True
        if contracts_changed:
            contracts_path.write_text(_contracts_text(rows))
            changed = True
    if not changed:
        return False
    rewritten = "\n".join(lines)
    if blotter.endswith("\n"):
        rewritten += "\n"
    path.write_text(rewritten + separator + marks)
    return True


def _contract_ok(pending: dict, bar: dict, levels: list[dict], taken: set[str], blocked: set[str]) -> bool:
    """False when the ladder was priced and no strike fit. A missed quote is left for the next check."""
    key = _entry_key(pending)
    if key in blocked:
        return False
    if key in taken:
        return True
    try:
        first, far = _target_pair(
            levels,
            {"ticker": pending["ticker"], "side": pending["side"], "level": pending["level"]},
        )
        found = quote_contracts(
            pending["ticker"],
            pending["side"],
            float(bar["o"]),
            bar["close_at"] - TEN_MIN,
            first,
            far,
        )
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return True
    if not found:
        return True
    chosen = next((row for row in found if row["role"] == "chosen"), None)
    if chosen is None or chosen.get("contract") in (None, "", "none"):
        blocked.add(key)
        return False
    taken.add(key)
    return True


def _is_spx(ticker: str) -> bool:
    name = (ticker or "").upper().strip().lstrip("^$")
    return name in {"SPX", "SPXW", "SPCX"}


def contract_expiration(row: dict) -> date | None:
    """Expiration from a label such as '10/21 342.5C'. The year comes from the entry."""
    label = (row.get("contract") or "").strip()
    if not label or label == "none":
        return None
    parts = label.split()
    if len(parts) != 2 or "/" not in parts[0]:
        return None
    tail = parts[1]
    if not tail or tail[-1] not in ("C", "P"):
        return None
    try:
        month_text, day_text = parts[0].split("/", 1)
        month, day = int(month_text), int(day_text)
        float(tail[:-1])
        entry = _row_clock(row["time"])
        expiration = date(entry.year, month, day)
    except (ValueError, KeyError, IndexError, AttributeError):
        return None
    if expiration < entry.date():
        try:
            expiration = date(entry.year + 1, month, day)
        except ValueError:
            return None
    return expiration


def _known_sellout(row: dict) -> datetime | None:
    """A broker sellout already on the row. None when this contract has no time."""
    raw = row.get("sellout")
    if isinstance(raw, datetime):
        when = raw if raw.tzinfo is not None else raw.replace(tzinfo=PT)
        return when.astimezone(PT)
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        when = datetime.fromisoformat(text)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=PT)
    return when.astimezone(PT)


def _is_index(row: dict) -> bool:
    if row.get("index_option") is True:
        return True
    return _is_spx(row.get("ticker") or "")


def fallback_cutoff(ticker: str, day: date, late_close=None) -> datetime:
    """The cutoff when the broker did not name a sellout.

    An index is out at 1:00 PM PT. A name Robinhood does not list as late
    close is out at 12:30 PT. A late-close name, or a name whose list was
    not read, stays at 12:45 PT.
    """
    if _is_spx(ticker):
        hour, minute = 13, 0
    elif late_close is False:
        hour, minute = 12, 30
    else:
        hour, minute = 12, 45
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=PT)


def contract_deadline(row: dict) -> datetime | None:
    """When this contract has to be out.

    The broker sellout is the cutoff when the instrument has one. It is not
    moved earlier or later to match another name. When that time is unknown,
    an index is out at 1:00 PM PT. A late-close equity option is out at
    12:45 PT, and any other equity option at 12:30 PT. If the late-close
    list was not read, the equity cutoff stays 12:45 PT. A blank or none
    contract has no option cutoff.
    """
    known = _known_sellout(row)
    if known is not None:
        return known
    expiration = contract_expiration(row)
    if expiration is None:
        return None
    if _is_index(row):
        return datetime(expiration.year, expiration.month, expiration.day, 13, 0, tzinfo=PT)
    return fallback_cutoff(row.get("ticker") or "", expiration, row.get("late_close"))


def _clock_before_cutoff(event: dict, deadline: datetime | None) -> bool:
    """A 12:50 clock that would sell this contract before its own cutoff."""
    if deadline is None or event.get("reason") != "clock":
        return False
    try:
        close_at = int(event["close_at"])
    except (TypeError, ValueError, KeyError):
        return False
    if close_at >= int(deadline.timestamp()):
        return False
    return datetime.fromtimestamp(close_at, PT).date() == deadline.date()


def _same_position(row: dict, event: dict) -> bool:
    try:
        level = float(row["level"])
        other = float(event["level"])
    except (TypeError, ValueError, KeyError):
        return False
    return (
        row.get("ticker") == event.get("ticker")
        and row.get("side") == event.get("side")
        and abs(level - other) < 0.001
    )


def _pop_open(opens: list[dict], event: dict) -> dict | None:
    for index, entry in enumerate(opens):
        if _same_position(entry, event):
            return opens.pop(index)
    return None


def _position_row(event: dict) -> dict:
    when = event.get("time")
    if not when:
        when = datetime.fromtimestamp(event["close_at"], PT).strftime("%Y-%m-%d %H:%M PT")
    fill = event.get("fill")
    row = {
        "time": when,
        "ticker": event["ticker"],
        "action": "entry",
        "side": event["side"],
        "level": f"{float(event['level']):.2f}",
        "fill": "" if fill is None else f"{float(fill):.2f}",
        "reason": event.get("reason") or "",
        "contract": event.get("contract") or "",
        "premium": event.get("premium"),
    }
    if "last" in event:
        row["last"] = event.get("last")
    if "next" in event:
        row["next"] = event.get("next")
    return row


def _mark_premiums(text: str) -> dict[str, str]:
    marks_text = text.split("\n## Open marks\n", 1)[1] if "\n## Open marks\n" in text else ""
    marks = {}
    for line in marks_text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or cells[0] in ("Contract", "") or set(cells[0]) <= {"-"}:
            continue
        marks[cells[0]] = cells[1] if len(cells) > 1 else ""
    return marks


def _print_at(bars: list[tuple], moment: int) -> float | None:
    usable = [bar for bar in bars if len(bar) > 4 and bar[4] is not None and bar[0] <= moment]
    if not usable:
        return None
    return float(usable[-1][4])


def _option_mark_at(symbol: str | None, moment: int) -> float | None:
    if not symbol:
        return None
    price = _print_at(fetch_option_minutes(symbol, span="5d"), moment)
    if price is None:
        return None
    return round(price, 2)


def _stock_bar_at(ticker: str, moment: int) -> dict | None:
    try:
        fetched = fetch_five_minute(ticker)
    except (SystemExit, OSError, urllib.error.URLError):
        return None
    usable = [
        bar
        for bar in add_indicators(ten_minute_bars(fetched, moment + 1))
        if bar["close_at"] <= moment and in_session(bar["close_at"])
    ]
    if not usable:
        return None
    return usable[-1]


def _premium_for(entry: dict, moment: int, marks: dict, option_mark) -> float | None:
    symbol = _contract_symbol(entry)
    if option_mark is not None and symbol:
        try:
            price = option_mark(symbol, moment)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            price = None
        if price is not None:
            return round(float(price), 2)
    raw = marks.get(f"{entry['ticker']} {entry.get('contract') or ''}")
    if raw in (None, ""):
        return None
    try:
        return round(float(raw), 2)
    except (TypeError, ValueError):
        return None


def _bar_at(entry: dict, moment: int, stock_bar) -> dict | None:
    if stock_bar is None:
        return None
    try:
        return stock_bar(entry["ticker"], moment)
    except (SystemExit, OSError, urllib.error.URLError, ValueError):
        return None


def _expiry_event(entry: dict, deadline: datetime, marks: dict, stock_bar, option_mark) -> dict:
    moment = int(deadline.timestamp())
    bar = _bar_at(entry, moment, stock_bar)
    if bar is None:
        try:
            fill = float(entry["fill"])
        except (TypeError, ValueError):
            fill = 0.0
        bar = {"o": fill, "h": fill, "l": fill, "c": fill, "close_at": moment}
    return {
        "kind": "exit",
        "ticker": entry["ticker"],
        "side": entry["side"],
        "level": float(entry["level"]),
        "reason": "expiry",
        "close_at": moment,
        "signal_at": moment,
        "bar": bar,
        "fill": bar["c"],
        "note": "",
        "contract": entry.get("contract") or "",
        "premium": _premium_for(entry, moment, marks, option_mark),
    }


def session_flat(when: datetime) -> datetime:
    """The 12:50 PT bar that cuts a trade still open into the cash close."""
    return when.replace(hour=12, minute=50, second=0, microsecond=0)


def _target_key(entry: dict) -> str:
    return (
        f"{entry['ticker']}|{entry['side']}|{float(entry['level']):.2f}|{entry['time']}"
    )


def _remember_targets(events: list[dict], path: Path = STATE_PATH) -> None:
    """Keep the posted targets with the entry. A later book must not move them."""
    book = _read_state(path).get("targets")
    if not isinstance(book, dict):
        book = {}
    changed = False
    for event in events:
        if event.get("kind") != "entry" or (
            "last" not in event and "next" not in event
        ):
            continue
        when = datetime.fromtimestamp(event["close_at"], PT).strftime("%Y-%m-%d %H:%M PT")
        key = f"{event['ticker']}|{event['side']}|{float(event['level']):.2f}|{when}"
        book[key] = {"last": event.get("last"), "next": event.get("next")}
        changed = True
    if not changed:
        return
    payload = _read_state(path)
    payload["targets"] = book
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def _recall_targets(entry: dict, path: Path = STATE_PATH) -> dict | None:
    book = _read_state(path).get("targets")
    if not isinstance(book, dict):
        return None
    found = book.get(_target_key(entry))
    return found if isinstance(found, dict) else None


def _targets_for(entry: dict, levels: list[dict], path: Path = STATE_PATH) -> tuple:
    """Last target, then the next number. Remembered targets win over today's book."""
    if "last" in entry or "next" in entry:
        return entry.get("last"), entry.get("next")
    remembered = _recall_targets(entry, path)
    if remembered is not None:
        return remembered.get("last"), remembered.get("next")
    first, far = _target_pair(
        levels,
        {
            "ticker": entry["ticker"],
            "side": entry["side"],
            "level": float(entry["level"]),
        },
    )
    return far, first


def _still_open(rows: list[dict], events: list[dict]) -> list[dict]:
    """Rows that this run has not already closed."""
    opens = _open_entries(rows)
    for event in events:
        if event.get("kind") == "entry":
            opens.append(_position_row(event))
        elif event.get("kind") == "exit":
            _pop_open(opens, event)
    return opens


def session_bars(ticker: str, moment: int) -> list[dict]:
    """Finished 10-minute bars through `moment`. Empty when the tape cannot be read."""
    try:
        fetched = fetch_five_minute(ticker, span="10d")
    except (SystemExit, OSError, urllib.error.URLError):
        return []
    return [
        bar
        for bar in add_indicators(ten_minute_bars(fetched, moment + 1))
        if bar["close_at"] <= moment and in_session(bar["close_at"])
    ]


def _walk_exit(position: dict, entry_at: int, bars: list[dict], settings: dict) -> dict | None:
    """The first reclaim, last target, or 12:50 bar after the fill."""
    flat_at = int(session_flat(datetime.fromtimestamp(entry_at, PT)).timestamp())
    day = datetime.fromtimestamp(entry_at, PT).date()
    for bar in bars:
        if bar["close_at"] < entry_at or bar["close_at"] > flat_at:
            continue
        if not in_session(bar["close_at"]):
            continue
        if datetime.fromtimestamp(bar["close_at"], PT).date() != day:
            continue
        found: list[dict] = []
        if _finish(position, bar, found, bar["close_at"] != entry_at, settings):
            event = found[0]
            event["fill"] = bar["c"]
            return event
    return None


def settle_open_entries(
    rows: list[dict],
    levels: list[dict],
    moment: int,
    stock_bars=None,
    settings: dict | None = None,
    path: Path = STATE_PATH,
) -> list[dict]:
    """Close an entry the current book no longer replays, once its session is over.

    A contract whose cutoff has passed stays with that expiration close.
    The cutoff is the broker sellout when the row has one. Otherwise a
    late-close name is out at 12:45 PT, any other equity option at 12:30 PT,
    and an index at 1:00 PM PT. A clock before that cutoff is not an exit.
    A `none` contract and a later
    expiration still leave at 12:50, or earlier when the level is reclaimed
    or the last target is lost. The first target does not close the trade.
    This does not add an entry.
    """
    settings = live_settings() if settings is None else settings
    bars_for = session_bars if stock_bars is None else stock_bars
    events = []
    for entry in _open_entries(rows):
        try:
            opened = _row_clock(entry["time"])
        except (ValueError, KeyError):
            continue
        flat = session_flat(opened)
        flat_at = int(flat.timestamp())
        if moment < flat_at:
            continue
        deadline = contract_deadline(entry)
        if deadline is not None and moment >= int(deadline.timestamp()):
            continue
        last, nxt = _targets_for(entry, levels, path)
        position = {
            "ticker": entry["ticker"],
            "side": entry["side"],
            "level": float(entry["level"]),
            "last": last,
            "next": nxt,
            "stop": None,
            "reason": entry.get("reason") or "retest",
            "bar": {"close_at": int(opened.timestamp())},
            "note": "",
            "flip": "",
        }
        try:
            bars = bars_for(entry["ticker"], flat_at)
        except (SystemExit, OSError, urllib.error.URLError, ValueError):
            continue
        event = _walk_exit(position, int(opened.timestamp()), bars or [], settings)
        if event is None or _clock_before_cutoff(event, deadline):
            continue
        event["contract"] = entry.get("contract") or ""
        event["premium"] = None
        event["kept"] = True
        events.append(event)
    return events


def _context_for(events: list[dict], levels: list[dict], armed_at: datetime) -> None:
    """Nearby levels come from the book that was armed that day."""
    armed_day = armed_at.date()
    same = []
    older = []
    for event in events:
        day = datetime.fromtimestamp(event["close_at"], PT).date()
        if day == armed_day:
            same.append(event)
        else:
            older.append(event)
    if same:
        append_context(same, levels)
    if older:
        append_context(older, [])


def apply_contract_exits(
    events: list[dict],
    rows: list[dict],
    moment: int,
    marks: dict | None = None,
    stock_bar=None,
    option_mark=None,
) -> list[dict]:
    """Close a contract once its own cutoff has passed.

    The cutoff is the broker sellout when the row has one. Otherwise a
    late-close name is out at 12:45 PT, any other equity option at 12:30 PT,
    and an index at 1:00 PM PT. A replay exit at or after that cutoff moves
    to the cutoff. A clock before it is left open. A contract that is still
    open gets an exit at the cutoff.
    """
    marks = marks or {}
    opens = _open_entries(rows)
    file_open = list(opens)
    adjusted = []
    for event in events:
        if event.get("kind") == "entry":
            adjusted.append(event)
            opens.append(_position_row(event))
            continue
        if event.get("kind") != "exit":
            adjusted.append(event)
            continue
        entry = _pop_open(opens, event)
        if entry is None:
            matched = any(
                row.get("action") == "entry" and _same_position(row, event) for row in rows
            )
            still_open = any(_same_position(row, event) for row in file_open)
            if matched and not still_open:
                continue
            adjusted.append(event)
            continue
        deadline = contract_deadline(entry)
        if _clock_before_cutoff(event, deadline):
            opens.append(entry)
            continue
        cutoff = None if deadline is None else int(deadline.timestamp())
        if cutoff is not None and moment >= cutoff and event["close_at"] >= cutoff:
            bar = _bar_at(entry, cutoff, stock_bar)
            premium = _premium_for(entry, cutoff, marks, option_mark)
            event = {
                **event,
                "reason": "expiry",
                "close_at": cutoff,
                "contract": entry.get("contract") or event.get("contract") or "",
                "premium": event.get("premium") if premium is None else premium,
            }
            if bar is not None:
                event["bar"] = bar
                event["fill"] = bar["c"]
        adjusted.append(event)
    for entry in opens:
        deadline = contract_deadline(entry)
        if deadline is None or moment < int(deadline.timestamp()):
            continue
        adjusted.append(_expiry_event(entry, deadline, marks, stock_bar, option_mark))
    return adjusted


def close_expired_contracts(
    moment: int | None = None,
    path: Path = CONTRACTS_PATH,
    option_mark=None,
) -> bool:
    """Mark an open comparison row exited once its contract cutoff has passed."""
    if not path.is_file():
        return False
    moment = int(datetime.now(PT).timestamp()) if moment is None else moment
    marker = _option_mark_at if option_mark is None else option_mark
    rows = contract_rows(path.read_text())
    changed = False
    for row in rows:
        if row["state"] != "open":
            continue
        deadline = contract_deadline(row)
        if deadline is None or moment < int(deadline.timestamp()):
            continue
        symbol = _row_symbol(row)
        price = None
        if symbol:
            try:
                price = marker(symbol, int(deadline.timestamp()))
            except (urllib.error.URLError, TimeoutError, OSError, ValueError):
                price = None
        if price is not None:
            row["price"] = f"{float(price):.2f}"
            row["return"] = format_return(row["entry"], row["price"])
        row["state"] = "exit"
        changed = True
    if not changed:
        return False
    path.write_text(_contracts_text(rows))
    return True


def stamp_sellouts(rows: list[dict], broker=None) -> None:
    """Copy each open contract's broker sellout, and whether it closes late.

    A missing sellout leaves that field unset. A late-close list that cannot
    be read leaves the row unclassified, so the equity cutoff stays 12:45 PT.
    """
    if broker is None and not SEND_ORDERS:
        return
    if broker is None:
        try:
            from robinhood_mcp import RobinhoodBroker

            broker = RobinhoodBroker()
        except Exception:
            return
    try:
        late = broker.late_closes()
    except Exception:
        late = None
    try:
        indexes = broker.index_options()
    except Exception:
        indexes = None
    cache: dict[tuple, datetime | None] = {}
    for row in rows:
        ticker = (row.get("ticker") or "").upper()
        on_index = _is_spx(ticker) or (isinstance(indexes, set) and ticker in indexes)
        if on_index:
            row["index_option"] = True
        elif isinstance(late, set) and isinstance(indexes, set):
            row["late_close"] = ticker in late
        elif isinstance(late, set) and ticker in late:
            row["late_close"] = True
        if row.get("action") not in (None, "entry"):
            continue
        label = (row.get("contract") or "").strip()
        if not label or label == "none" or row.get("sellout"):
            continue
        try:
            year = _row_clock(row["time"]).year
        except (ValueError, KeyError, AttributeError):
            continue
        key = (row.get("ticker") or "", label, year)
        if key not in cache:
            try:
                cache[key] = broker.sellout(key[0], label, year)
            except Exception:
                cache[key] = None
        if cache[key] is not None:
            row["sellout"] = cache[key]


def read_agentic_cash(broker=None) -> float | None:
    """Dollars one contract can debit on the Agentic account.

    None when the read fails. The plan is still written, and no order is sent.
    """
    if broker is None and not SEND_ORDERS:
        return None
    try:
        if broker is None:
            from robinhood_mcp import RobinhoodBroker

            broker = RobinhoodBroker()
        amount = broker.spendable()
    except Exception:
        return None
    return balance_amount(amount)


def _plain(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return str(value)


def record_events(events: list[dict], mode: str, path: Path | None = None) -> None:
    """Every field of each entry and exit, one JSON line each, for the trade ledger.

    The markdown tapes are for reading. This file keeps the candle, indicators,
    targets, ladder, balance, and order the checker saw, so nothing has to be
    parsed back out of a table later. Writing it changes no decision.
    """
    rows = [event for event in events if event.get("kind") in ("entry", "exit")]
    if not rows:
        return
    file = path or EVENTS_PATH
    file.parent.mkdir(parents=True, exist_ok=True)
    with file.open("a") as handle:
        for event in rows:
            record = {"id": event_id(event.get("ticker") or "", event), "mode": mode, **event}
            handle.write(json.dumps(record, default=_plain, sort_keys=True) + "\n")


def _since_session(moment: int) -> str:
    day = datetime.fromtimestamp(moment, PT).date()
    start = datetime(day.year, day.month, day.day, 0, 0, tzinfo=PT)
    return start.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc(text: str) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


# Minutes past a contract's cutoff before a held position raises an alarm.
LATE_EXIT_MINUTES = 5
# Minutes a working sell may sit unfilled before it raises an alarm.
STUCK_SELL_MINUTES = 20


def audit_positions(moment: int, broker=None, book_path: Path | None = None, raise_fn=None, clear_fn=None) -> list[str]:
    """Alarm on any Agentic contract the checker opened that is not getting out.

    The broker is the truth: today's agent buys, minus their filled sells, that
    the account still holds. A held contract past its cutoff, a sell that sits
    unfilled, or an exit that keeps failing to route raises an alarm. A clean
    position clears it. Nothing here sends or cancels an order.
    """
    raise_fn = raise_fn or alarm.raise_alarm
    clear_fn = clear_fn or alarm.clear_alarm
    if broker is None:
        from robinhood_mcp import RobinhoodBroker

        broker = RobinhoodBroker()
    orders = broker.agent_orders(_since_session(moment))
    now = datetime.fromtimestamp(moment, PT)
    opened: dict[str, dict] = {}
    for order in sorted(orders, key=lambda row: row.get("created_at") or ""):
        if order.get("effect") == "open" and (order.get("filled_quantity") or 0) > 0:
            opened[order["option_id"]] = order
    raised = []
    for option_id, buy in opened.items():
        key = f"open|{option_id}"
        held = broker.held(option_id)
        if not held or held["quantity"] <= 0:
            for name in (key, f"stuck|{option_id}"):
                clear_fn(name)
            continue
        label = buy.get("contract") or ""
        row = {
            "ticker": buy.get("ticker") or "",
            "contract": label,
            "time": now.strftime("%Y-%m-%d %H:%M PT"),
            "action": "entry",
        }
        stamp_sellouts([row], broker)
        deadline = contract_deadline(row)
        if deadline is not None and now > deadline + timedelta(minutes=LATE_EXIT_MINUTES):
            text = (
                f"{row['ticker']} {label} is still held {int((now - deadline).total_seconds() // 60)} "
                f"minutes past its {deadline.strftime('%H:%M')} PT cutoff. Sell it by hand."
            )
            raise_fn(key, text, now=moment)
            raised.append(text)
        else:
            clear_fn(key)
        sells = [
            order
            for order in orders
            if order.get("option_id") == option_id
            and order.get("effect") == "close"
            and order.get("state") in ("queued", "confirmed", "unconfirmed", "partially_filled")
        ]
        stuck = [
            order
            for order in sells
            if (_utc(order.get("created_at")) or now) < now - timedelta(minutes=STUCK_SELL_MINUTES)
        ]
        if held.get("pending_sell") and stuck:
            text = (
                f"{row['ticker']} {label} sell at {stuck[0].get('limit')} has not filled in "
                f"{STUCK_SELL_MINUTES} minutes. Reprice it by hand."
            )
            raise_fn(f"stuck|{option_id}", text, now=moment)
            raised.append(text)
        else:
            clear_fn(f"stuck|{option_id}")
    for key, record in _broker_book(book_path or BROKER_PATH).items():
        if record.get("kind") != "exit":
            continue
        name = f"exit|{key}"
        if record.get("status") == "error" and int(record.get("attempts") or 0) >= 2:
            text = (
                f"{record.get('ticker')} {record.get('contract')} exit failed "
                f"{record.get('attempts')} times. The checker keeps retrying; sell by hand if it is still open."
            )
            raise_fn(name, text, now=moment)
            raised.append(text)
        else:
            clear_fn(name)
    return raised


CHECK_TIMES_PATH = ROOT / "alerts" / "check_times.jsonl"


class _StepClock:
    """Seconds per step of one check, and how long until its first order went out.

    Accepted proposal 2026-10-23-time-the-check: entry checks took 2.5 to 6
    minutes and nobody knew where. Timing never changes a decision, and a
    timing failure is ignored.
    """

    def __init__(self) -> None:
        self.start = time.monotonic()
        self.last = self.start
        self.steps: dict[str, float] = {}
        self.first_order: float | None = None
        self.requests: dict[str, int] = {"stock": 0, "option": 0}

    def lap(self, name: str) -> None:
        now = time.monotonic()
        self.steps[name] = round(self.steps.get(name, 0.0) + now - self.last, 2)
        self.last = now

    def add(self, name: str, seconds: float) -> None:
        self.steps[name] = round(self.steps.get(name, 0.0) + seconds, 2)

    def ordered(self) -> None:
        if self.first_order is None:
            self.first_order = round(time.monotonic() - self.start, 2)

    def record(self, moment: int, live: list[dict], path: Path | None = None) -> None:
        try:
            broker = sys.modules.get("robinhood_mcp")
            line = {
                "at": datetime.fromtimestamp(moment, PT).isoformat(timespec="minutes"),
                "total": round(time.monotonic() - self.start, 2),
                "first_order_s": self.first_order,
                "entries": sum(1 for event in live if event.get("kind") == "entry"),
                "exits": sum(1 for event in live if event.get("kind") == "exit"),
                "steps": self.steps,
                "requests": {**self.requests, "broker": getattr(broker, "CALLS", 0) if broker else 0},
            }
            with (path or CHECK_TIMES_PATH).open("a") as handle:
                handle.write(json.dumps(line) + "\n")
        except Exception:  # noqa: BLE001
            return


_CLOCK = _StepClock()


def check(now: int | None = None, notify: bool = False) -> list[str]:
    global _CLOCK
    clock = _CLOCK = _StepClock()
    spec = load_levels()
    cash = read_agentic_cash()
    clock.lap("balance")
    armed_at = int(spec["armed_at"].timestamp())
    moment = int(datetime.now(PT).timestamp()) if now is None else now
    fired = load_state()
    taken = load_marked("taken")
    blocked = load_marked("no_contract")
    grouped: dict[str, list[dict]] = {}
    for level in spec["levels"]:
        grouped.setdefault(level["ticker"], []).append(level)

    def accept(pending: dict, bar: dict) -> bool:
        return _contract_ok(pending, bar, spec["levels"], taken, blocked)

    originals = []
    for ticker, levels in grouped.items():
        fetch_started = time.monotonic()
        try:
            fetched = fetch_five_minute(ticker)
            clock.add("bars_fetch", time.monotonic() - fetch_started)
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            # One ticker's bars failing skips that ticker this check. It does not stop the others.
            if SEND_ORDERS:
                alarm.raise_alarm(
                    f"data|{ticker}",
                    f"{ticker} price history failed ({str(exc)[:120]}). Its entries and exits wait for the next check.",
                    now=moment,
                )
            continue
        if SEND_ORDERS:
            alarm.clear_alarm(f"data|{ticker}")
        bars = add_indicators(ten_minute_bars(fetched, moment))
        usable = [
            bar
            for bar in bars
            if bar["close_at"] < armed_at or in_session(bar["close_at"])
        ]
        for event in replay(usable, levels, armed_at, checker_settings(), accept=accept):
            identity = event_id(ticker, event)
            if identity in fired:
                continue
            fired.add(identity)
            if route_event(event, moment) == "drop":
                continue
            originals.append(event)
    save_state(fired, no_contract=blocked, taken=taken)
    clock.lap("bars_and_replay")
    paper_src = []
    live_src = []
    other = []
    for event in originals:
        if event.get("kind") in ("entry", "exit") and session_kind(event["close_at"]) == "live":
            live_src.append(event)
        elif event.get("kind") in ("entry", "exit"):
            paper_src.append(event)
        else:
            other.append(event)
    paper_text = PAPER_PATH.read_text() if PAPER_PATH.is_file() else ""
    live_text = LIVE_PATH.read_text() if LIVE_PATH.is_file() else ""
    paper_open = paper_rows(paper_text)
    live_open = paper_rows(live_text)
    stamp_sellouts(live_open)
    clock.lap("sellouts")
    quoted_paper = quote_paper(paper_src, spec["levels"]) if paper_src else []
    quoted_live = quote_paper(live_src, spec["levels"], path=LIVE_PATH, cash=cash) if live_src else []
    clock.lap("pricing")
    final_paper = apply_contract_exits(
        quoted_paper,
        paper_open,
        moment,
        marks=_mark_premiums(paper_text),
        stock_bar=_stock_bar_at,
        option_mark=_option_mark_at,
    )
    final_live = apply_contract_exits(
        quoted_live,
        live_open,
        moment,
        marks=_mark_premiums(live_text),
        stock_bar=_stock_bar_at,
        option_mark=_option_mark_at,
    )
    clock.lap("exits")
    cached: dict[str, list[dict]] = {}

    def bars_for(ticker: str, at: int) -> list[dict]:
        if ticker not in cached:
            cached[ticker] = session_bars(ticker, moment)
        return [bar for bar in cached[ticker] if bar["close_at"] <= at]

    settled_paper = settle_open_entries(
        _still_open(paper_open, final_paper),
        spec["levels"],
        moment,
        bars_for,
    )
    settled_live = settle_open_entries(
        _still_open(live_open, final_live),
        spec["levels"],
        moment,
        bars_for,
    )
    if settled_paper:
        final_paper.extend(quote_paper(settled_paper, spec["levels"]))
    if settled_live:
        final_live.extend(quote_paper(settled_live, spec["levels"], path=LIVE_PATH, cash=cash))
    clock.lap("settle")
    messages = []
    quiet = []
    paper = []
    live = []

    def publish(event: dict, live_row: bool) -> None:
        identity = event_id(event["ticker"], event)
        if identity not in fired:
            fired.add(identity)
        routed = route_event(event, moment)
        save_state(fired, no_contract=blocked, taken=taken)
        kept = event.get("kept") is True
        if routed == "drop" and event.get("reason") != "expiry" and not kept:
            return
        if live_row and event.get("kind") in ("entry", "exit"):
            routing_started = time.monotonic()
            try:
                route_live_order(event, cash=cash)
                if event.get("order_id"):
                    clock.ordered()
            except Exception as exc:
                alarm.raise_alarm(
                    f"route|{identity}",
                    f"{event['ticker']} live {event['kind']} could not be routed "
                    f"({type(exc).__name__}). Check the Agentic account by hand.",
                )
            clock.add("routing", time.monotonic() - routing_started)
        if routed != "drop" or kept:
            line = live_notice(event) if live_row else format_live(event)
            if routed == "alert":
                alert_started = time.monotonic()
                _send_alert(line, notify)
                messages.append(line)
                if live_row:
                    notify_live(event)
                clock.add("alerts", time.monotonic() - alert_started)
            else:
                quiet.append(line)
        if event.get("kind") in ("entry", "exit"):
            if live_row:
                live.append(event)
            else:
                paper.append(event)

    for event in other:
        publish(event, False)
    for event in final_paper:
        publish(event, False)
    for event in final_live:
        publish(event, True)
    save_state(fired, no_contract=blocked, taken=taken)
    clock.lap("publish")
    logged = messages + quiet
    if logged:
        append_log(logged)
    if live:
        append_live(live)
        _context_for(live, spec["levels"], spec["armed_at"])
        record_contracts(live)
    if paper:
        append_paper(paper)
        _context_for(paper, spec["levels"], spec["armed_at"])
        record_contracts(paper)
    _remember_targets(live + paper)
    for event in paper:
        if route_event(event, moment) == "alert":
            notify_paper(event)
    clock.lap("tapes")
    repaired = fill_missing_contracts(spec["levels"])
    repaired_live = fill_missing_contracts(spec["levels"], LIVE_PATH, cash=cash)
    repaired_premium = repair_exit_premiums(PAPER_PATH)
    repaired_premium_live = repair_exit_premiums(LIVE_PATH)
    comparison = close_expired_contracts(moment)
    changed = (
        paper
        or live
        or repaired
        or repaired_live
        or repaired_premium
        or repaired_premium_live
        or comparison
        or refresh_open_marks(now=moment)
        or refresh_contract_marks(now=moment)
    )
    clock.lap("repairs_and_marks")
    if changed:
        refresh_dashboard()
    clock.lap("dashboard")
    try:
        retry_live_orders(cash=cash)
    except Exception as exc:
        alarm.raise_alarm("retry", f"Retrying failed live orders broke ({type(exc).__name__}).")
    clock.lap("retry")
    record_events(live, "live")
    record_events(paper, "paper")
    if not SEND_ORDERS:
        return logged
    if session_kind(moment) == "live" and in_session(moment) and cash is None:
        alarm.raise_alarm(
            "cash",
            "The Agentic balance could not be read, so no live entry can be sent. "
            "The Robinhood login may have lapsed.",
            now=moment,
        )
    else:
        alarm.clear_alarm("cash")
    if session_kind(moment) == "live":
        try:
            audit_positions(moment)
        except Exception as exc:
            alarm.raise_alarm(
                "audit",
                f"Open Agentic positions could not be checked ({type(exc).__name__}). Check them by hand.",
                now=moment,
            )
    clock.lap("audit")
    clock.record(moment, live)
    return logged


def _wick_reaches(bar: dict, price: float, touch: float) -> bool:
    """The 15-cent figure is the wick. A close is not a tag."""
    return bar["l"] <= price + touch and bar["h"] >= price - touch


def bounce_side(bar: dict, price: float, settings: dict | None = None) -> str | None:
    """The rejection when a wick tags the level and the close stays inside the band.

    A close at or above the level is a call. A close under it is a put.
    A close outside the half-ATR band is a claim, not a bounce.
    """
    chosen = live_settings() if settings is None else settings
    level = float(price)
    if not _wick_reaches(bar, level, chosen["touch"]):
        return None
    if abs(bar["c"] - level) > _break_buffer(bar, chosen) + 1e-9:
        return None
    if bar["c"] >= level and bar["l"] <= level + chosen["touch"]:
        return "call"
    if bar["c"] < level and bar["h"] >= level - chosen["touch"]:
        return "put"
    return None


def fresh_claim(
    prev: dict | None, bar: dict, price: float, settings: dict | None = None
) -> str | None:
    """A finished close beyond the level by half the 14-period ATR, the first one."""
    chosen = live_settings() if settings is None else settings
    level = float(price)
    band = _break_buffer(bar, chosen)
    if bar["c"] > level + band and (prev is None or prev["c"] <= level + band):
        return "call"
    if bar["c"] < level - band and (prev is None or prev["c"] >= level - band):
        return "put"
    return None


def _direction_targets(level: dict, side: str, levels: list[dict]) -> list[float]:
    targets = _book_targets(level, side, levels)
    if targets:
        return targets
    return _targets(level, side)


def regime_trades(
    bars: list[dict],
    levels: list[dict],
    armed_at: int = 0,
    kind: str = "bounce",
    end_at: int | None = None,
) -> list[dict]:
    """Paper bounce or trend fills. Each signal is scored on its own.

    This is not the live entry. It does not send an alert.
    """
    if kind not in ("bounce", "trend"):
        raise ValueError(f"regime must be bounce or trend, not {kind}")
    settings = live_settings()
    usable = [bar for bar in bars if end_at is None or bar["close_at"] <= end_at]
    trades = []
    for index in range(1, len(usable)):
        bar = usable[index]
        prev = usable[index - 1]
        if bar["close_at"] < armed_at or _is_clock(bar["close_at"]):
            continue
        for level in levels:
            price = float(level["price"])
            if kind == "bounce":
                side = bounce_side(bar, price, settings)
            else:
                side = fresh_claim(prev, bar, price, settings)
            if side is None:
                continue
            if index + 1 >= len(usable):
                continue
            entry = usable[index + 1]
            fill = float(entry["o"])
            if abs(fill - price) > settings["chase"]:
                continue
            targets = _direction_targets(level, side, levels)
            nxt = targets[0] if targets else None
            far = targets[-1] if targets else None
            target = far if kind == "bounce" else nxt
            exit_bar = None
            reason = "open"
            retested = False
            for offset, later in enumerate(usable[index + 1 :]):
                # The entry bar is still the fill. A retest is a later wick back.
                tagged = offset > 0 and _wick_reaches(later, price, settings["touch"])
                hit = target is not None and _through_last(
                    {"side": side, "level": price, "last": target}, later, settings
                )
                if kind == "trend" and tagged and not hit:
                    retested = True
                if _reclaimed({"side": side, "level": price}, later, settings):
                    exit_bar = later
                    reason = "reclaim"
                    break
                if hit:
                    exit_bar = later
                    reason = "target"
                    if tagged:
                        retested = True
                    break
                if _is_clock(later["close_at"]):
                    exit_bar = later
                    reason = "clock"
                    break
            if exit_bar is None:
                continue
            points = exit_bar["c"] - fill if side == "call" else fill - exit_bar["c"]
            trades.append(
                {
                    "kind": kind,
                    "ticker": level.get("ticker") or "",
                    "side": side,
                    "level": price,
                    "signal_at": bar["close_at"],
                    "close_at": entry["close_at"],
                    "fill": fill,
                    "exit_at": exit_bar["close_at"],
                    "exit": exit_bar["c"],
                    "reason": reason,
                    "points": points,
                    "retested": retested,
                    "target": target,
                }
            )
    return trades


def main() -> None:
    parser = argparse.ArgumentParser(description="10-minute retest alerts")
    parser.add_argument("command", choices=("check",))
    parser.add_argument(
        "--notify",
        action="store_true",
        help="Post new alerts to Discord #ta",
    )
    args = parser.parse_args()
    try:
        messages = check(notify=args.notify)
    except KeyboardInterrupt:
        raise
    except BaseException as exc:
        if SEND_ORDERS:
            alarm.raise_alarm(
                "crash",
                f"The 10-minute check crashed ({type(exc).__name__}: {str(exc)[:160]}). "
                "Open positions are not being watched until it runs clean.",
            )
        raise
    alarm.clear_alarm("crash")
    alarm.heartbeat()
    if not messages:
        print("No new 10-minute entries, exits, or skips.")
        return
    for message in messages:
        print(message)


if __name__ == "__main__":
    main()
