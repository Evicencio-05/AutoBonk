#!/usr/bin/env python3
"""Score exit what-ifs from the checker's own bars. No orders, no invented premiums."""

from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "claim_alerts", Path(__file__).resolve().parent / "claim_alerts.py"
)
claim = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(claim)

PRESETS = (
    ("Live", None),
    ("Never exit", {"stop_mode": "none", "take": "none", "flatten": "none"}),
    ("Near the next level", {"stop_mode": "none", "take": "near", "flatten": "clock"}),
    ("Named stop", {"stop_mode": "named", "take": "none", "flatten": "clock"}),
)


def classify_contract(contract: str | None, premium: float | None, threshold: float) -> str | None:
    """A trade needs a contract. A premium over the threshold is paper."""
    if contract is None or str(contract).strip() in ("", "none"):
        return None
    if premium is None:
        return None
    if float(premium) > float(threshold):
        return "paper"
    return "fits"


def score_points(values: list[float]) -> dict:
    """Profit factor is gross wins divided by gross losses. Zero losses are not a factor."""
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    factor = None if gross_loss == 0 else gross_win / gross_loss
    return {
        "trades": len(values),
        "wins": len(wins),
        "losses": len(losses),
        "net": gross_win - gross_loss,
        "profit_factor": factor,
    }


def _settings(touch: float, chase: float, break_atr: float, profit_near: float, extra: dict | None) -> dict:
    chosen = claim.live_settings()
    chosen["touch"] = float(touch)
    chosen["chase"] = float(chase)
    chosen["break_atr"] = float(break_atr)
    chosen["profit_near"] = float(profit_near)
    if extra:
        chosen.update(extra)
    return chosen


def _key(ticker: str, side: str, level: float) -> str:
    return f"{ticker}|{side}|{level:.2f}"


def _snapshot(bar: dict, levels: list[dict], ticker: str, settings: dict) -> dict:
    def cell(name: str):
        value = bar.get(name)
        if value is None:
            return None
        return {"value": value, "distance": bar["c"] - value}

    purple = bar.get("purple")
    yellow = bar.get("yellow")
    volume = bar.get("v")
    return {
        "candle": {
            "color": "green" if bar["c"] > bar["o"] else "red" if bar["c"] < bar["o"] else "flat",
            "o": bar["o"],
            "h": bar["h"],
            "l": bar["l"],
            "c": bar["c"],
        },
        "purple": purple,
        "yellow": yellow,
        "sma20": cell("sma"),
        "sma50": cell("sma50"),
        "sma200": cell("sma200"),
        "atr": bar.get("atr"),
        "band": claim._break_buffer(bar, settings),
        "nearby": claim._nearby_levels(levels, ticker, bar["c"]),
        "volume": None if volume is None else int(round(volume)),
    }


def _round_trips(events: list[dict], bars: list[dict]) -> list[dict]:
    trips = []
    open_entry = None
    for event in events:
        if event["kind"] == "entry":
            open_entry = event
            continue
        if event["kind"] == "exit" and open_entry is not None:
            trips.append((open_entry, event, False))
            open_entry = None
    if open_entry is not None and bars:
        last = bars[-1]
        trips.append(
            (open_entry, {"kind": "exit", "reason": "mark", "bar": last, "close_at": last["close_at"]}, True)
        )
    return trips


def run_backtest(
    bars_by_ticker: dict[str, list[dict]],
    levels: list[dict],
    armed_at: int = 0,
    settings: dict | None = None,
    premiums: dict | None = None,
    threshold: float = 1.0,
) -> dict:
    """One position per ticker. An open trade is marked at the last bar. Premiums are the caller's."""
    chosen = settings or claim.live_settings()
    premiums = premiums or {}
    grouped: dict[str, list[dict]] = {}
    for level in levels:
        grouped.setdefault(level.get("ticker") or "", []).append(level)
    trades = []
    for ticker, bars in bars_by_ticker.items():
        if not bars:
            continue
        events = claim.replay(bars, grouped.get(ticker, []), armed_at, chosen)
        for entry, exit_event, marked in _round_trips(events, bars):
            fill = float(entry["fill"])
            exit_close = float(exit_event["bar"]["c"])
            points = (fill - exit_close) if entry["side"] == "put" else (exit_close - fill)
            quote = premiums.get(_key(entry["ticker"], entry["side"], float(entry["level"]))) or {}
            contract = quote.get("contract") or ""
            entry_premium = quote.get("entry")
            exit_premium = quote.get("exit")
            book = classify_contract(contract, entry_premium, threshold)
            option_dollars = None
            option_return = None
            if book and entry_premium is not None and exit_premium is not None:
                option_dollars = (float(exit_premium) - float(entry_premium)) * 100
                if float(entry_premium) != 0:
                    option_return = (float(exit_premium) - float(entry_premium)) / float(entry_premium)
            when = datetime.fromtimestamp(entry["close_at"], claim.PT).strftime("%Y-%m-%d %H:%M PT")
            trades.append(
                {
                    "time": when,
                    "ticker": entry["ticker"],
                    "side": entry["side"],
                    "level": float(entry["level"]),
                    "fill": fill,
                    "exit_close": exit_close,
                    "exit_reason": exit_event["reason"],
                    "marked": marked,
                    "points": points,
                    "return": 0.0 if fill == 0 else points / fill,
                    "contract": contract,
                    "entry_premium": entry_premium,
                    "exit_premium": exit_premium,
                    "book": book,
                    "option_dollars": option_dollars,
                    "option_return": option_return,
                    "inputs": _snapshot(entry["bar"], levels, entry["ticker"], chosen),
                    "note": entry.get("note") or "",
                }
            )
    return {"trades": trades, "summary": _summary(trades)}


def _book_summary(trades: list[dict], book: str) -> dict:
    rows = [trade for trade in trades if trade["book"] == book]
    stock = score_points([trade["points"] for trade in rows])
    priced = [trade for trade in rows if trade["option_dollars"] is not None]
    option = score_points([trade["option_dollars"] for trade in priced])
    fills = sum(abs(trade["fill"]) for trade in rows)
    stock["return"] = 0.0 if fills == 0 else stock["net"] / fills
    entry_premiums = sum(float(trade["entry_premium"]) for trade in priced)
    option["return"] = None if entry_premiums == 0 else option["net"] / (entry_premiums * 100)
    return {"stock": stock, "option": option}


def _summary(trades: list[dict]) -> dict:
    return {
        "fits": _book_summary(trades, "fits"),
        "paper": _book_summary(trades, "paper"),
        "no_contract": sum(1 for trade in trades if trade["book"] is None),
    }


def run_presets(
    bars_by_ticker: dict[str, list[dict]],
    levels: list[dict],
    armed_at: int = 0,
    touch: float = 0.15,
    chase: float = 0.50,
    break_atr: float = 0.5,
    profit_near: float = 0.15,
    threshold: float = 1.0,
    premiums: dict | None = None,
    custom: dict | None = None,
) -> list[dict]:
    """The same bars scored under each exit. The numbers come from the closes and the premiums given."""
    runs = []
    plan = list(PRESETS)
    if custom:
        plan.append(("Custom", custom))
    for name, extra in plan:
        settings = _settings(touch, chase, break_atr, profit_near, extra)
        result = run_backtest(bars_by_ticker, levels, armed_at, settings, premiums, threshold)
        runs.append({"name": name, **result})
    return runs
