#!/usr/bin/env python3
"""Score a live 10-minute read against candles the operator confirmed.

Only finished bars are visible. The forming candle is ignored. The score is
how many bars early the first legal candle is, and how much price that costs.
This script never places an order.

  python3 scripts/train_intraday.py score
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parents[1]
DRILLS_PATH = ROOT / "learning" / "drills.yaml"
TRAINING_PATH = ROOT / "learning" / "training.md"
PT = ZoneInfo("America/Los_Angeles")
FIVE_MIN = 300
TEN_MIN = 600
RSI_LENGTH = 14


def ten_minute_bars(
    five_minute: list[tuple[int, float, float]], now: int
) -> list[dict]:
    """Roll finished 5-minute (start, open, close) bars into 10-minute bars."""
    grouped: dict[int, list[tuple[int, float, float]]] = {}
    for start, open_, close in five_minute:
        bucket = start - (start % TEN_MIN)
        grouped.setdefault(bucket, []).append((start, open_, close))
    bars = []
    for bucket in sorted(grouped):
        if bucket + TEN_MIN > now:
            continue
        parts = grouped[bucket]
        opening = [item for item in parts if item[0] < bucket + FIVE_MIN]
        ending = [item for item in parts if item[0] >= bucket + FIVE_MIN]
        if not opening or not ending:
            continue
        bars.append(
            {
                "close_at": bucket + TEN_MIN,
                "open": opening[0][1],
                "close": ending[-1][2],
            }
        )
    return bars


def add_rsi(bars: list[dict]) -> None:
    """Purple is 14 RSI. Yellow is the 14 SMA of that RSI."""
    closes = [bar["close"] for bar in bars]
    gains, losses = [], []
    for index in range(1, len(closes)):
        change = closes[index] - closes[index - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    if len(gains) < RSI_LENGTH:
        return
    avg_gain = sum(gains[:RSI_LENGTH]) / RSI_LENGTH
    avg_loss = sum(losses[:RSI_LENGTH]) / RSI_LENGTH
    values: list[float | None] = [None] * RSI_LENGTH

    def reading(gain: float, loss: float) -> float:
        if loss == 0:
            return 100.0
        return 100 - (100 / (1 + gain / loss))

    values.append(reading(avg_gain, avg_loss))
    for index in range(RSI_LENGTH, len(gains)):
        avg_gain = (avg_gain * (RSI_LENGTH - 1) + gains[index]) / RSI_LENGTH
        avg_loss = (avg_loss * (RSI_LENGTH - 1) + losses[index]) / RSI_LENGTH
        values.append(reading(avg_gain, avg_loss))
    for index, bar in enumerate(bars):
        purple = values[index] if index < len(values) else None
        bar["purple"] = purple
        window = [item for item in values[max(0, index - 13) : index + 1] if item is not None]
        bar["yellow"] = sum(window) / len(window) if len(window) == RSI_LENGTH else None


def _color(bar: dict) -> str:
    if bar["close"] > bar["open"]:
        return "green"
    if bar["close"] < bar["open"]:
        return "red"
    return "flat"


def score_put(bars: list[dict], level: float, buy_at: int, sell_at: int) -> dict:
    """Compare the first green and first red with the confirmed candles.

    A put buy is a green candle after the lose, still under the level.
    A put sell is a red candle after the buy. Later bars are not used to
    pick an earlier candle.
    """
    lose_at = None
    for index in range(1, len(bars)):
        previous, bar = bars[index - 1], bars[index]
        if previous["close"] >= level > bar["close"] and bar["close_at"] <= buy_at:
            lose_at = bar["close_at"]
    if lose_at is None:
        raise ValueError("no lose before the confirmed buy")
    after_lose = [bar for bar in bars if bar["close_at"] > lose_at and bar["close"] < level]
    greens = [bar for bar in after_lose if _color(bar) == "green"]
    if not greens:
        raise ValueError("no green candle after the lose")
    naive_buy = greens[0]
    ideal_buy = next(bar for bar in bars if bar["close_at"] == buy_at)
    after_buy = [bar for bar in bars if bar["close_at"] > buy_at]
    reds = [bar for bar in after_buy if _color(bar) == "red"]
    if not reds:
        raise ValueError("no red candle after the confirmed buy")
    naive_sell = reds[0]
    ideal_sell = next(bar for bar in bars if bar["close_at"] == sell_at)
    return {
        "lose_at": lose_at,
        "naive_buy": naive_buy,
        "ideal_buy": ideal_buy,
        "buy_bars_early": _bars_between(bars, naive_buy["close_at"], buy_at),
        "buy_price_gap": ideal_buy["close"] - naive_buy["close"],
        "naive_sell": naive_sell,
        "ideal_sell": ideal_sell,
        "sell_bars_early": _bars_between(bars, naive_sell["close_at"], sell_at),
        "sell_price_gap": naive_sell["close"] - ideal_sell["close"],
    }


def _bars_between(bars: list[dict], start: int, end: int) -> int:
    times = [bar["close_at"] for bar in bars]
    return times.index(end) - times.index(start)


def _clock(close_at: int, session: str) -> int:
    hour, minute = close_at.split(":")
    when = datetime.fromisoformat(f"{session}T{hour}:{minute}:00").replace(tzinfo=PT)
    return int(when.timestamp())


def fetch_five_minute(ticker: str) -> list[tuple[int, float, float]]:
    query = urllib.parse.urlencode(
        {"interval": "5m", "range": "5d", "includePrePost": "true"}
    )
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode())
    row = payload["chart"]["result"][0]
    quote = row["indicators"]["quote"][0]
    bars = []
    for start, open_, close in zip(row["timestamp"], quote["open"], quote["close"]):
        if open_ is None or close is None:
            continue
        bars.append((start, float(open_), float(close)))
    return bars


def _fmt(bar: dict) -> str:
    when = datetime.fromtimestamp(bar["close_at"], PT).strftime("%H:%M")
    push = bar["close"] - bar["open"]
    purple = f"{bar['purple']:.1f}" if bar.get("purple") is not None else "-"
    return (
        f"{when} {_color(bar)} open {bar['open']:.2f} close {bar['close']:.2f} "
        f"push {push:+.2f} purple {purple}"
    )


def render(drill: dict, scored: dict) -> str:
    buy_gap = scored["buy_price_gap"]
    sell_gap = scored["sell_price_gap"]
    return "\n".join(
        [
            f"## {drill['ticker']} {drill['session']} {drill['side']}",
            "",
            drill["why"],
            f"Contract: {drill['contract']}",
            "",
            f"- Confirmed buy: {_fmt(scored['ideal_buy'])}",
            f"- First green after the lose: {_fmt(scored['naive_buy'])}",
            (
                f"- Buy miss: {scored['buy_bars_early']} bar early, "
                f"{buy_gap:.2f} less stock-price strength"
            ),
            f"- Confirmed sell: {_fmt(scored['ideal_sell'])}",
            f"- First red after the buy: {_fmt(scored['naive_sell'])}",
            (
                f"- Sell miss: {scored['sell_bars_early']} bars early, "
                f"{sell_gap:.2f} of the drop left behind"
            ),
            "",
            "The feed did contain the confirmed candles. The miss is taking the first green or the first red.",
            "",
        ]
    )


def score_drills() -> str:
    spec = yaml.safe_load(DRILLS_PATH.read_text())
    sections = [
        "# Intraday training",
        "",
        "Each drill is a play whose candles the operator confirmed. "
        "A live read uses finished 10-minute bars only. "
        "One drill is an observation, not a pattern and not an order.",
        "",
    ]
    for drill in spec["drills"]:
        if drill["side"] != "put":
            raise SystemExit(f"{drill['id']} is not a put drill yet")
        now = int(datetime.now(PT).timestamp())
        bars = ten_minute_bars(fetch_five_minute(drill["ticker"]), now)
        add_rsi(bars)
        session = [
            bar
            for bar in bars
            if datetime.fromtimestamp(bar["close_at"], PT).date().isoformat()
            == drill["session"]
        ]
        scored = score_put(
            session,
            float(drill["level"]),
            _clock(drill["ideal_buy"], drill["session"]),
            _clock(drill["ideal_sell"], drill["session"]),
        )
        sections.append(render(drill, scored))
    text = "\n".join(sections)
    TRAINING_PATH.write_text(text)
    return text


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Score intraday reads against confirmed candles")
    parser.add_argument("command", choices=("score",))
    args = parser.parse_args()
    if args.command == "score":
        print(score_drills(), end="")


if __name__ == "__main__":
    main()
