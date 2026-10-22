#!/usr/bin/env python3
"""Alert a retest entry, an exit, or a skipped fill. Never place an order.

Yahoo has no 10-minute bars. Two finished 5-minute bars are one 10-minute
bar. A claim or a lose is a close beyond the level by half the 14-period ATR.
A close inside that band has not broken the level. That same close flips
the level: a lost support is resistance, and a claimed resistance is support.
A wick within 15 cents only counts as the touch. The fill is the next bar's open.
A 0DTE contract is out at 12:45 PT on expiration. SPX is not cut at 12:45.
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
import urllib.error
from concurrent.futures import ThreadPoolExecutor
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parents[1]
LEVELS_PATH = ROOT / "alerts" / "levels.yaml"
STATE_PATH = ROOT / "alerts" / "state.json"
LOG_PATH = ROOT / "alerts" / "log.md"
PAPER_PATH = ROOT / "alerts" / "paper.md"
CONTEXT_PATH = ROOT / "alerts" / "context.md"
CONTRACTS_PATH = ROOT / "alerts" / "contracts.md"
CONTRACTS_HEADER = (
    "# Contract comparison\n\n"
    "The chosen row is the contract the checker would take. "
    "Same-day expiration is eligible until noon Pacific. "
    "A 0DTE strike past the halfway point between the stock and the far target is not taken. "
    "A name with no listing that day uses the nearest expiration that is listed. "
    "The strike is the closest one at or under $1 that the far target can still reach. "
    "The other rows are that same fill. "
    "Price is the latest print while the row is open, and the exit bar once it closes. "
    "Return is the percent change in the premium. "
    "A rule that picks the same contract as an earlier row is not repeated. "
    "Nothing here is an order.\n\n"
    "- dte: the same strike rule on same-day expiration\n"
    "- first: the first target is the ceiling\n"
    "- cheap: the furthest strike under $1 that is still inside the far target\n"
    "- week: Friday's expiration, the same strike rule as chosen\n"
    "- cash: the nearest strike at or under $0.50 that the far target can still reach. "
    "A live plan shows it and does not switch to it.\n\n"
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
FRESH_SECONDS = 20 * 60
# $100 a contract. The debit compared below is the price of one share of the option.
CONTRACT_CAP = 1.0
# Thursday 2026-10-22 is the first live session. Cash is $50, so one contract.
LIVE_FROM = date(2026, 10, 22)
LIVE_CASH = 50.0
LIVE_DEBIT = LIVE_CASH / 100
LIVE_PATH = ROOT / "alerts" / "live.md"
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
    """Every variable at the live default. None from the caller means this."""
    return {name: _default_of(name, spec) for name, spec in VARIABLES.items()}


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

    settings=None keeps the live defaults. The same bars and settings replay
    to the same events.
    """
    chosen = live_settings() if settings is None else settings
    events = []
    position = None
    pending = None
    prev2 = None
    prev = None
    seen: list[dict] = []
    history: list[dict] = []
    for bar in bars:
        prior = history
        history = history + [bar]
        if bar["close_at"] < armed_at:
            prev2, prev = prev, bar
            continue
        seen.append(bar)
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
    events.append(_event("entry", pending, bar, pending["reason"], fill))
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


def format_live(event: dict) -> str:
    when = datetime.fromtimestamp(event["close_at"], PT).strftime("%Y-%m-%d %H:%M PT")
    price = f"{event['level']:.2f}"
    head = f"{event['ticker']} {event['side']} {event['kind']} {price} at {when}."
    if event["kind"] == "skip" and event["reason"] == "chase":
        extra = f" Next open {event['fill']:.2f} left the level."
    elif event["kind"] == "skip" and event["reason"] == "next":
        extra = " The next number was tagged and did not hold."
    elif event["kind"] == "skip" and event["reason"] == "contract":
        if event.get("last") is None and event.get("next") is None:
            extra = " This level has no further number, so no contract was chosen."
        else:
            extra = " No strike under $1 was still in front of the far target."
    elif event["kind"] == "skip":
        extra = " Fill bar closed back through the level."
    elif event["kind"] == "exit" and event["reason"] == "expiry":
        if _is_spx(event["ticker"]):
            extra = " SPX expiration. Out at 1:15 PT."
        else:
            extra = " 0DTE is out at 12:45 PT."
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
            f"{prefix}Fill {event['fill']:.2f}. {contract} debit at most $100. "
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
    query = urllib.parse.urlencode(
        {"interval": "5m", "range": span, "includePrePost": "true"}
    )
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:180]
        raise SystemExit(f"{ticker} price history {exc.code}: {detail}") from exc
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


def _discord_get(token: str, path: str):
    request = urllib.request.Request(
        "https://discord.com/api/v10" + path,
        headers={
            "Authorization": f"Bot {token}",
            "User-Agent": "AutoBonk claim-alerts",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode())


def notify_discord(text: str) -> None:
    """Post one alert to #ta. The token is never printed."""
    token = _token()
    channel_id = None
    for guild in _discord_get(token, "/users/@me/guilds"):
        for channel in _discord_get(token, f"/guilds/{guild['id']}/channels"):
            if channel.get("name") == "ta" and channel.get("type") == 0:
                channel_id = channel["id"]
                break
        if channel_id:
            break
    if not channel_id:
        raise SystemExit("Discord #ta was not found")
    body = json.dumps({"content": text}).encode()
    request = urllib.request.Request(
        f"https://discord.com/api/v10/channels/{channel_id}/messages",
        data=body,
        headers={
            "Authorization": f"Bot {token}",
            "User-Agent": "AutoBonk claim-alerts",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        response.read()


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
        if cap is not None and row["debit"] > cap:
            continue
        return {**row, "otm": False}
    for row in out_the_money:
        if cap is not None and row["debit"] > cap:
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
        limit = chosen_day == session
        picked = _pick_contract(stock, side, ladders[chosen_day], far, limit, LIVE_DEBIT)
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
    """One-minute option bars from Yahoo. The checker cannot call Robinhood."""
    query = urllib.parse.urlencode(
        {"interval": "1m", "range": span, "includePrePost": "true"}
    )
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
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
    return [
        (stamp, open_, high, low, close)
        for stamp, open_, high, low, close in zip(stamps, opens, highs, lows, closes)
        if None not in (open_, high, low, close)
    ]


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


def _has_cash_strike(quotes: list[dict]) -> bool:
    """True once the ladder holds a strike the $50 cash can buy."""
    return any(row["debit"] <= LIVE_DEBIT for row in quotes)


def _priced_strikes(
    ticker: str,
    side: str,
    stock: float,
    expiration: date,
    start: int,
    ceiling: float | None = None,
) -> list[dict]:
    """Price enough of the ladder to pick the chosen strike and the cheap one.

    The walk stops once a strike at or under $1 is in hand, then prices the
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
        # The first strike under $1 is often over the $50 cash. Keep walking
        # until a strike at or under $0.50 is in hand, so the cash row is the
        # nearest one and not the far tail.
        if _has_cash_strike(quotes):
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
) -> list[dict]:
    """Price the chosen contract and the comparison rules at the fill."""
    session = datetime.fromtimestamp(start, PT).date()
    ladders: dict[date, list[dict]] = {}
    tried: set[date] = set()
    for day in _quote_days(session):
        tried.add(day)
        quotes = _priced_strikes(ticker, side, stock, day, start, far)
        if not quotes:
            continue
        ladders[day] = quotes
        if day >= session:
            break
    week = weekly_expiration(session)
    if week not in tried and week.weekday() < 5:
        quotes = _priced_strikes(ticker, side, stock, week, start, far)
        if quotes:
            ladders[week] = quotes
    return assemble_contracts(session, ladders, side, stock, first, far, start)


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


def quote_paper(events: list[dict], levels: list[dict], path: Path = PAPER_PATH) -> list[dict]:
    """Attach the contract and its print. A failure leaves the row without a premium."""
    text = path.read_text() if path.is_file() else ""
    known = paper_rows(text)
    quoted = []
    for event in events:
        if event.get("kind") not in ("entry", "exit"):
            quoted.append(event)
            continue
        try:
            if event["kind"] == "entry":
                start = event["close_at"] - TEN_MIN
                first, far = _target_pair(levels, event)
                found = quote_contracts(
                    event["ticker"],
                    event["side"],
                    float(event["fill"]),
                    start,
                    first,
                    far,
                )
                chosen = next((row for row in found if row["role"] == "chosen"), None)
                contract = "" if chosen is None else chosen["contract"]
                premium = None if chosen is None else chosen["premium"]
                event = {**event, "contracts": found}
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
                    price = option_price(fetch_option_minutes(symbol), start, "close")
                    if price is not None:
                        premium = round(price, 2)
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
                if label not in ("", "none"):
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
                price = option_price(fetch_option_minutes(symbol), start, "close")
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
    """A live contract has to fit the $50 cash. A missing quote is not a refusal."""
    contract = event.get("contract")
    premium = event.get("premium")
    if contract in (None, ""):
        return "quote"
    if contract == "none" or premium is None:
        return "none"
    if float(premium) > LIVE_DEBIT:
        return "over"
    return "fits"


def _cash_alternative(event: dict) -> tuple[str, str]:
    """The $0.50 strike and whether it sits past halfway. Blank when the ladder has none."""
    rows = event.get("contracts") or []
    cash = next((row for row in rows if row.get("role") == "cash"), None)
    if cash is None:
        return "", ""
    label = cash.get("contract") or ""
    if label in ("", "none"):
        return "none", ""
    return label, cash.get("halfway") or ""


def _live_cash_sentence(event: dict) -> str:
    """Say which strike the $1 rule chose, and which strike the $50 cash can buy."""
    fit = cash_fit(event)
    alternative, halfway = _cash_alternative(event)
    if fit == "fits":
        sentence = "The debit fits $50."
        if halfway == "past":
            sentence += " The strike is past halfway to the far target."
        return sentence
    if fit == "over":
        sentence = "The debit is over $50, so it is not the live contract."
        if alternative not in ("", "none"):
            where = "past halfway" if halfway == "past" else "in front of halfway"
            premium = next(
                (
                    row.get("premium")
                    for row in (event.get("contracts") or [])
                    if row.get("role") == "cash"
                ),
                None,
            )
            price = "" if premium is None else f" at ${float(premium):.2f}"
            sentence += (
                f" The nearest strike at or under $0.50 is {alternative}{price}, {where}."
                " The plan keeps the $1 strike."
            )
        else:
            sentence += " No strike at or under $0.50 was still in front of the far target."
        return sentence
    if fit == "quote":
        return "The quote failed. The next check will price it again."
    chosen = next(
        (row for row in (event.get("contracts") or []) if row.get("role") == "chosen"),
        None,
    )
    if chosen and chosen.get("why") == "no-target":
        return "This level has no further number, so no contract was chosen."
    return "No strike under $1 was still in front of the far target."


def live_notice(event: dict) -> str:
    """The checker text for a live plan. It still is not an order."""
    text = format_live(event)
    if text.endswith(" Not an order."):
        text = text[: -len(" Not an order.")]
    return (
        text
        + f" Live session. {_live_cash_sentence(event)} Waiting for confirm. Not an order."
    )


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


def live_line(event: dict) -> str | None:
    """One plan row. The contract is the $1 strike. The $0.50 strike is beside it."""
    line = paper_line(event)
    if line is None:
        return None
    if event.get("kind") != "entry":
        return line.rstrip()[:-1].rstrip() + " |  |  |  |"
    alternative, halfway = _cash_alternative(event)
    return (
        line.rstrip()[:-1].rstrip()
        + f" | {cash_fit(event)} | {alternative} | {halfway} |"
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
            "Cash is $50, so one contract at or under $0.50. "
            "A row waits for confirm. It is not an order and it is not a paper row. "
            "The fade checker stays off. "
            "The contract column is the strike at or under $1. "
            "Under $0.50 is the nearest strike the cash can buy. The plan does not switch to it. "
            "Halfway says whether that strike is past the point between the stock and the far target. "
            "A cash cell of quote means the chain was not priced, and the next check tries again.\n\n"
            "| Time | Ticker | Action | Side | Level | Fill | Reason | Contract | Premium | Cash | Under $0.50 | Halfway |\n"
            "|------|--------|--------|------|-------|------|--------|----------|---------|------|-------------|---------|\n"
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
    addition = "\n".join(lines) + "\n"
    blotter, separator, marks = text.partition("\n## Open marks\n")
    if separator:
        path.write_text(blotter.rstrip() + "\n" + addition + "\n## Open marks\n" + marks)
    else:
        with path.open("a") as handle:
            handle.write(addition)
    _store_rows("paper", lines, path, PAPER_PATH)


def refresh_dashboard() -> None:
    path = Path(__file__).resolve().parent / "dashboard.py"
    spec = importlib.util.spec_from_file_location("dashboard", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main()


def notify_live(event: dict) -> None:
    """Desktop toast for a live plan. The toast is not an order."""
    headline = f"{event['ticker']} live {event['kind']}"
    price = event["fill"] if event.get("fill") is not None else event["bar"]["c"]
    body = f"{event['side']} {event['level']:.2f} at {price:.2f}. Waiting for confirm. Not an order."
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


def _paint_live_contract(
    line: str,
    contract: str,
    premium: float | None,
    cash: str,
    alternative: str,
    halfway: str,
) -> str:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    cells = (cells + [""] * 12)[:12]
    cells[7] = contract
    cells[8] = "" if premium is None else f"{float(premium):.2f}"
    cells[9] = cash
    cells[10] = alternative
    cells[11] = halfway
    return "| " + " | ".join(cells) + " |"


def _upgrade_live_header(lines: list[str]) -> bool:
    """Give an older live table the $0.50 and halfway columns."""
    for index, line in enumerate(lines):
        if not line.startswith("| Time |") or "Cash" not in line or "Under $0.50" in line:
            continue
        lines[index] = (
            "| Time | Ticker | Action | Side | Level | Fill | Reason | Contract | Premium "
            "| Cash | Under $0.50 | Halfway |"
        )
        rule = index + 1
        if rule < len(lines) and set(lines[rule].replace("|", "").replace(" ", "")) <= {"-"}:
            lines[rule] = (
                "|------|--------|--------|------|-------|------|--------|----------|---------"
                "|------|-------------|---------|"
            )
        return True
    return False


def fill_missing_contracts(
    levels: list[dict],
    path: Path = PAPER_PATH,
    contracts_path: Path = CONTRACTS_PATH,
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
            )
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            continue
        if not found:
            continue
        chosen = next((item for item in found if item["role"] == "chosen"), None)
        contract = "" if chosen is None else chosen["contract"]
        if not contract:
            continue
        premium = None if chosen is None else chosen.get("premium")
        if live_table:
            priced = {**event, "contract": contract, "premium": premium, "contracts": found}
            alternative, halfway = _cash_alternative(priced)
            lines[index] = _paint_live_contract(
                lines[index],
                contract,
                premium,
                cash_fit(priced),
                alternative,
                halfway,
            )
        else:
            lines[index] = _paint_contract(lines[index], contract, premium)
        changed = True
        events.append({**event, "contracts": found})
        paired = exit_for.get(index)
        if paired is None or paired[1]["contract"]:
            continue
        exit_index, exit_row = paired
        exit_premium = None
        symbol = _contract_symbol({**row, "contract": contract})
        if symbol and contract != "none":
            exit_at = int(_row_clock(exit_row["time"]).timestamp())
            price = option_price(fetch_option_minutes(symbol), exit_at - TEN_MIN, "close")
            if price is not None:
                exit_premium = round(price, 2)
        if live_table:
            lines[exit_index] = _paint_live_contract(
                lines[exit_index], contract, exit_premium, "", "", ""
            )
        else:
            lines[exit_index] = _paint_contract(lines[exit_index], contract, exit_premium)
        events.append(
            {
                "kind": "exit",
                "ticker": row["ticker"],
                "side": row["side"],
                "level": float(row["level"]),
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
    return name in {"SPX", "SPXW"}


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


def contract_deadline(row: dict) -> datetime | None:
    """When this contract has to be out.

    Equity 0DTE is out at 12:45 PT on the expiration date. SPX is not cut then.
    SPX keeps the session and is out at 1:15 PT.
    """
    expiration = contract_expiration(row)
    if expiration is None:
        return None
    if _is_spx(row.get("ticker") or ""):
        return datetime(expiration.year, expiration.month, expiration.day, 13, 15, tzinfo=PT)
    return datetime(expiration.year, expiration.month, expiration.day, 12, 45, tzinfo=PT)


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
    return {
        "time": when,
        "ticker": event["ticker"],
        "action": "entry",
        "side": event["side"],
        "level": f"{float(event['level']):.2f}",
        "fill": "" if fill is None else f"{float(fill):.2f}",
        "contract": event.get("contract") or "",
        "premium": event.get("premium"),
    }


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


def apply_contract_exits(
    events: list[dict],
    rows: list[dict],
    moment: int,
    marks: dict | None = None,
    stock_bar=None,
    option_mark=None,
) -> list[dict]:
    """Close a contract once its expiration cutoff has passed.

    A replay exit at or after that cutoff moves to the cutoff. A contract that
    is still open gets an exit there. An equity 0DTE is out at 12:45 PT. SPX
    is not cut at 12:45.
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


def check(now: int | None = None, notify: bool = False) -> list[str]:
    spec = load_levels()
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
        bars = add_indicators(ten_minute_bars(fetch_five_minute(ticker), moment))
        usable = [
            bar
            for bar in bars
            if bar["close_at"] < armed_at or in_session(bar["close_at"])
        ]
        for event in replay(usable, levels, armed_at, accept=accept):
            identity = event_id(ticker, event)
            if identity in fired:
                continue
            fired.add(identity)
            if route_event(event, moment) == "drop":
                continue
            originals.append(event)
    save_state(fired, no_contract=blocked, taken=taken)
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
    final_paper = apply_contract_exits(
        quote_paper(paper_src, spec["levels"]) if paper_src else [],
        paper_rows(paper_text),
        moment,
        marks=_mark_premiums(paper_text),
        stock_bar=_stock_bar_at,
        option_mark=_option_mark_at,
    )
    final_live = apply_contract_exits(
        quote_paper(live_src, spec["levels"], path=LIVE_PATH) if live_src else [],
        paper_rows(live_text),
        moment,
        marks=_mark_premiums(live_text),
        stock_bar=_stock_bar_at,
        option_mark=_option_mark_at,
    )
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
        if routed == "drop" and event.get("reason") != "expiry":
            return
        if routed != "drop":
            line = live_notice(event) if live_row else format_live(event)
            if routed == "alert":
                if notify:
                    notify_discord(line)
                messages.append(line)
                if live_row:
                    notify_live(event)
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
    logged = messages + quiet
    if logged:
        append_log(logged)
    if live:
        append_live(live)
        append_context(live, spec["levels"])
        record_contracts(live)
    if paper:
        append_paper(paper)
        append_context(paper, spec["levels"])
        record_contracts(paper)
        for event in paper:
            if route_event(event, moment) == "alert":
                notify_paper(event)
    repaired = fill_missing_contracts(spec["levels"])
    repaired_live = fill_missing_contracts(spec["levels"], LIVE_PATH)
    comparison = close_expired_contracts(moment)
    if (
        paper
        or live
        or repaired
        or repaired_live
        or comparison
        or refresh_open_marks(now=moment)
        or refresh_contract_marks(now=moment)
    ):
        refresh_dashboard()
    return logged


def main() -> None:
    parser = argparse.ArgumentParser(description="10-minute retest alerts")
    parser.add_argument("command", choices=("check",))
    parser.add_argument(
        "--notify",
        action="store_true",
        help="Post new alerts to Discord #ta",
    )
    args = parser.parse_args()
    messages = check(notify=args.notify)
    if not messages:
        print("No new 10-minute entries, exits, or skips.")
        return
    for message in messages:
        print(message)


if __name__ == "__main__":
    main()
