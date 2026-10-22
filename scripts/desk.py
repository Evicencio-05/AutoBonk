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
    # Live is the checker: retest entry, target exit. The other columns keep the caller's entry.
    ("Live", {"entry": "retest", "exit": "target"}),
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


def _streaks(values: list[float]) -> tuple[int, int]:
    wins = losses = max_wins = max_losses = 0
    for value in values:
        if value > 0:
            wins += 1
            losses = 0
        elif value < 0:
            losses += 1
            wins = 0
        else:
            wins = losses = 0
        max_wins = max(max_wins, wins)
        max_losses = max(max_losses, losses)
    return max_wins, max_losses


def score_points(values: list[float]) -> dict:
    """Closed-trade profit, in the units of `values`.

    Profit factor is gross wins divided by gross losses. Zero losses are not a factor.
    Drawdown walks the running sum. The percent is that drop divided by the peak
    it fell from, and it stays empty when the peak was never above zero.
    """
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    flats = [value for value in values if value == 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    net = gross_win - gross_loss
    count = len(values)
    factor = None if gross_loss == 0 else gross_win / gross_loss
    avg_win = None if not wins else gross_win / len(wins)
    avg_loss = None if not losses else -gross_loss / len(losses)
    payoff = None if avg_win is None or avg_loss in (None, 0) else avg_win / abs(avg_loss)
    equity: list[float] = []
    running = 0.0
    peak = 0.0
    max_drawdown = 0.0
    max_drawdown_percent = None
    for value in values:
        running += value
        equity.append(running)
        if running > peak:
            peak = running
        drop = peak - running
        if drop > max_drawdown:
            max_drawdown = drop
            max_drawdown_percent = None if peak <= 0 else drop / peak
    max_wins, max_losses = _streaks(values)
    return {
        "trades": count,
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(flats),
        "win_rate": None if count == 0 else len(wins) / count,
        "net": net,
        "gross_profit": gross_win,
        "gross_loss": gross_loss,
        "profit_factor": factor,
        "expected": None if count == 0 else net / count,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "payoff_ratio": payoff,
        "largest_win": None if not wins else max(wins),
        "largest_loss": None if not losses else min(losses),
        "max_drawdown": max_drawdown,
        "max_drawdown_percent": max_drawdown_percent,
        "max_win_streak": max_wins,
        "max_loss_streak": max_losses,
        "equity": equity,
    }


def _settings(
    touch: float,
    chase: float,
    break_atr: float,
    profit_near: float,
    sma_band: float,
    entry: str,
    extra: dict | None,
) -> dict:
    chosen = claim.live_settings()
    chosen["touch"] = claim._coerce("touch", touch, claim.VARIABLES["touch"])
    chosen["chase"] = claim._coerce("chase", chase, claim.VARIABLES["chase"])
    chosen["break_atr"] = claim._coerce("break_atr", break_atr, claim.VARIABLES["break_atr"])
    chosen["sma_band"] = claim._coerce("sma_band", sma_band, claim.VARIABLES["sma_band"])
    chosen["entry"] = claim._coerce("entry", entry, claim.VARIABLES["entry"])
    near = float(profit_near)
    if near < 0:
        raise ValueError("profit_near must be zero or more")
    chosen["profit_near"] = near
    if extra:
        chosen.update(extra)
        if "exit" in extra:
            chosen["exit"] = claim._coerce("exit", extra["exit"], claim.VARIABLES["exit"])
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
    visible = {}
    for name in ("entry", "exit", "touch", "chase", "sma_band", "break_atr", "profit_near", "stop_mode", "take", "flatten"):
        if name in chosen:
            visible[name] = chosen[name]
    return {"trades": trades, "settings": visible, **performance(trades, bars_by_ticker)}


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


def _strategy_summary(trades: list[dict]) -> dict:
    """Every round trip, in stock points. A missing contract still counts."""
    stats = score_points([trade["points"] for trade in trades])
    fills = sum(abs(trade["fill"]) for trade in trades)
    stats["return"] = 0.0 if fills == 0 else stats["net"] / fills
    open_rows = [trade for trade in trades if trade["marked"]]
    stats["open_trades"] = len(open_rows)
    stats["open_points"] = sum(trade["points"] for trade in open_rows)
    closed = [trade["points"] for trade in trades if not trade["marked"]]
    stats["closed_net"] = score_points(closed)["net"]
    return stats


def _buy_hold(bars_by_ticker: dict[str, list[dict]]) -> dict:
    points = 0.0
    capital = 0.0
    tickers = 0
    for bars in bars_by_ticker.values():
        if not bars:
            continue
        points += float(bars[-1]["c"]) - float(bars[0]["c"])
        capital += abs(float(bars[0]["c"]))
        tickers += 1
    return {
        "points": points,
        "return": 0.0 if capital == 0 else points / capital,
        "tickers": tickers,
    }


def performance(trades: list[dict], bars_by_ticker: dict[str, list[dict]]) -> dict:
    """Stock-point profit for a list of round trips, plus buy and hold on the bars."""
    return {"summary": _summary(trades), "buy_hold": _buy_hold(bars_by_ticker)}


def _summary(trades: list[dict]) -> dict:
    return {
        "strategy": _strategy_summary(trades),
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
    sma_band: float = 1.0,
    entry: str = "retest",
    this_test: dict | None = None,
) -> list[dict]:
    """The same bars scored under each exit, then under the caller's variables.

    Touch, chase, the ATR fraction, the SMA band, and the entry apply to every
    column. `this_test` is the strategy on the form, including its exit.
    """
    runs = []
    plan = list(PRESETS)
    if custom:
        plan.append(("Custom", custom))
    if this_test:
        plan.append(("This test", this_test))
    for name, extra in plan:
        settings = _settings(touch, chase, break_atr, profit_near, sma_band, entry, extra)
        result = run_backtest(bars_by_ticker, levels, armed_at, settings, premiums, threshold)
        runs.append({"name": name, **result})
    return runs
