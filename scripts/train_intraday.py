#!/usr/bin/env python3
"""Score a live 10-minute read against candles the operator confirmed.

Only finished bars are visible. The forming candle is ignored. The score is
how many bars early the first legal candle is, and how much price that costs.
The bars come from the frozen session file. A session that has no file is
fetched once and written, and later scores read that file. This script never
places an order and does not change the live checker.

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
GOALS_PATH = ROOT / "learning" / "goals.yaml"
TRAINING_PATH = ROOT / "learning" / "training.md"
LESSONS_DIR = ROOT / "learning" / "lessons"
FIXTURES = ROOT / "bench" / "fixtures"
PT = ZoneInfo("America/Los_Angeles")
FIVE_MIN = 300
TEN_MIN = 600
RSI_LENGTH = 14
# The checker's wick. The lesson names it. Chase and the half-ATR flip stay on the checker.
WICK = 0.15


def ten_minute_bars(
    five_minute: list[tuple[int, float, float, float, float]], now: int
) -> list[dict]:
    """Roll finished 5-minute bars into 10-minute bars, once, for a new freeze.

    Each item is (start, open, high, low, close). A later score reads the file
    this writes. It does not roll the file again.
    """
    grouped: dict[int, list[tuple[int, float, float, float, float]]] = {}
    for start, open_, high, low, close in five_minute:
        bucket = start - (start % TEN_MIN)
        grouped.setdefault(bucket, []).append((start, open_, high, low, close))
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
                "high": max(item[2] for item in parts),
                "low": min(item[3] for item in parts),
                "close": ending[-1][4],
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


def _cross_at(bars: list[dict], side: str, level: float, buy_at: int) -> int | None:
    """Last close through the level at or before the confirmed buy."""
    found = None
    for index in range(1, len(bars)):
        previous, bar = bars[index - 1], bars[index]
        if bar["close_at"] > buy_at:
            break
        if side == "put" and previous["close"] >= level > bar["close"]:
            found = bar["close_at"]
        if side == "call" and previous["close"] <= level < bar["close"]:
            found = bar["close_at"]
    return found


def _entry_bars(bars: list[dict], side: str, level: float, trigger_at: int, buy_at: int) -> list[dict]:
    """Candles that buy the contract, through the confirmed buy.

    A put is bought on a green candle still under the level.
    A call is bought on a red candle still above the level.
    """
    color = "green" if side == "put" else "red"
    picked = []
    for bar in bars:
        if bar["close_at"] <= trigger_at or bar["close_at"] > buy_at:
            continue
        if _color(bar) != color:
            continue
        if side == "put" and bar["close"] < level:
            picked.append(bar)
        if side == "call" and bar["close"] > level:
            picked.append(bar)
    return picked


def _bottom_bar(side: str, legal: list[dict]) -> dict:
    """The cheap contract. A put bottom is the high close. A call bottom is the low close."""
    if side == "put":
        return max(legal, key=lambda bar: (bar["close"], -bar["close_at"]))
    return min(legal, key=lambda bar: (bar["close"], bar["close_at"]))


def _premium_left(side: str, bottom_close: float, close: float) -> float:
    """Stock points that made the contract more expensive than the bottom."""
    if side == "put":
        return bottom_close - close
    return close - bottom_close


def score_bottom(bars: list[dict], side: str, level: float, buy_at: int) -> dict:
    """How far the entry sits from the bottom of the contract.

    The score is stock points on the entry candle. That is where the
    contract is bought. It is not a priced premium. Later bars are not
    used to pick an earlier candle.
    """
    if side not in ("call", "put"):
        raise ValueError(f"unknown side {side}")
    trigger_at = _cross_at(bars, side, level, buy_at)
    if trigger_at is None:
        raise ValueError("no claim or lose before the confirmed buy")
    legal = _entry_bars(bars, side, level, trigger_at, buy_at)
    if not legal:
        raise ValueError("no entry candle through the confirmed buy")
    ideal = next(bar for bar in bars if bar["close_at"] == buy_at)
    if ideal["close_at"] not in {bar["close_at"] for bar in legal}:
        raise ValueError("confirmed buy is not an entry candle")
    bottom = _bottom_bar(side, legal)
    naive = legal[0]
    return {
        "trigger_at": trigger_at,
        "naive": naive,
        "ideal": ideal,
        "bottom": bottom,
        "naive_left": _premium_left(side, bottom["close"], naive["close"]),
        "ideal_left": _premium_left(side, bottom["close"], ideal["close"]),
        "sniped": bottom["close_at"] == buy_at,
    }


def score_put(bars: list[dict], level: float, buy_at: int, sell_at: int) -> dict:
    """Compare the first green and first red with the confirmed candles.

    A put buy is a green candle after the lose, still under the level.
    A put sell is a red candle after the buy. Later bars are not used to
    pick an earlier candle.
    """
    lose_at = _cross_at(bars, "put", level, buy_at)
    if lose_at is None:
        raise ValueError("no lose before the confirmed buy")
    greens = _entry_bars(bars, "put", level, lose_at, buy_at)
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


def score_call(bars: list[dict], level: float, buy_at: int, sell_at: int) -> dict:
    """Compare the first red and first green with the confirmed candles.

    A call buy is a red candle after the claim, still above the level.
    A call sell is a green candle after the buy. Later bars are not used
    to pick an earlier candle.
    """
    claim_at = _cross_at(bars, "call", level, buy_at)
    if claim_at is None:
        raise ValueError("no claim before the confirmed buy")
    reds = _entry_bars(bars, "call", level, claim_at, buy_at)
    if not reds:
        raise ValueError("no red candle after the claim")
    naive_buy = reds[0]
    ideal_buy = next(bar for bar in bars if bar["close_at"] == buy_at)
    after_buy = [bar for bar in bars if bar["close_at"] > buy_at]
    greens = [bar for bar in after_buy if _color(bar) == "green"]
    if not greens:
        raise ValueError("no green candle after the confirmed buy")
    naive_sell = greens[0]
    ideal_sell = next(bar for bar in bars if bar["close_at"] == sell_at)
    return {
        "claim_at": claim_at,
        "naive_buy": naive_buy,
        "ideal_buy": ideal_buy,
        "buy_bars_early": _bars_between(bars, naive_buy["close_at"], buy_at),
        "buy_price_gap": naive_buy["close"] - ideal_buy["close"],
        "naive_sell": naive_sell,
        "ideal_sell": ideal_sell,
        "sell_bars_early": _bars_between(bars, naive_sell["close_at"], sell_at),
        "sell_price_gap": ideal_sell["close"] - naive_sell["close"],
    }


def _bars_between(bars: list[dict], start: int, end: int) -> int:
    times = [bar["close_at"] for bar in bars]
    return times.index(end) - times.index(start)


def _clock(close_at: int, session: str) -> int:
    hour, minute = close_at.split(":")
    when = datetime.fromisoformat(f"{session}T{hour}:{minute}:00").replace(tzinfo=PT)
    return int(when.timestamp())


def fetch_five_minute(ticker: str) -> list[tuple[int, float, float, float, float]]:
    """One fetch, used only when the session file does not exist yet.

    A score that already has the ticker in bench/fixtures/{session}-bars.json
    does not call this. The written file is the later source.
    """
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
    for start, open_, high, low, close in zip(
        row["timestamp"], quote["open"], quote["high"], quote["low"], quote["close"]
    ):
        if None in (open_, high, low, close):
            continue
        bars.append((start, float(open_), float(high), float(low), float(close)))
    return bars


def _fixture_path(session: str, fixtures: Path) -> Path:
    return fixtures / f"{session}-bars.json"


def _read_frozen(path: Path, ticker: str, session: str) -> list[dict] | None:
    """Finished 10-minute bars already stored for this ticker and session."""
    if not path.is_file():
        return None
    payload = json.loads(path.read_text())
    rows = (payload.get("tickers") or {}).get(ticker)
    if not rows:
        return None
    bars = []
    for row in rows:
        bar = {
            "close_at": int(row["close_at"]),
            "open": float(row["o"]),
            "high": float(row["h"]),
            "low": float(row["l"]),
            "close": float(row["c"]),
        }
        when = datetime.fromtimestamp(bar["close_at"], PT).date().isoformat()
        if when == session:
            bars.append(bar)
    return bars or None


def _freeze_once(path: Path, ticker: str, session: str, fetch) -> None:
    """Write the session's finished 10-minute bars. Do not replace a file."""
    if path.is_file():
        raise SystemExit(f"{path.name} is already frozen. The score does not refetch it.")
    now = int(datetime.now(PT).timestamp())
    rolled = ten_minute_bars(fetch(ticker), now)
    chosen = [
        bar
        for bar in rolled
        if datetime.fromtimestamp(bar["close_at"], PT).date().isoformat() == session
    ]
    if not chosen:
        raise SystemExit(f"no finished 10-minute bars for {ticker} {session}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "tickers": {
            ticker: [
                {
                    "close_at": bar["close_at"],
                    "o": bar["open"],
                    "h": bar["high"],
                    "l": bar["low"],
                    "c": bar["close"],
                }
                for bar in chosen
            ]
        }
    }
    path.write_text(json.dumps(payload))


def bars_for_drill(drill: dict, fixtures: Path = FIXTURES, fetch=None) -> list[dict]:
    """The frozen 10-minute bars for one drill.

    An existing ticker in the session file is the answer key. A missing file
    is fetched once and then read back. A file that does not contain the
    ticker is left as it is.
    """
    ticker = drill["ticker"]
    session = drill["session"]
    path = _fixture_path(session, fixtures)
    frozen = _read_frozen(path, ticker, session)
    if frozen is not None:
        return frozen
    if path.is_file():
        raise SystemExit(
            f"{path.name} has no {ticker} bars. The score does not refetch over a frozen file."
        )
    _freeze_once(path, ticker, session, fetch_five_minute if fetch is None else fetch)
    frozen = _read_frozen(path, ticker, session)
    if not frozen:
        raise SystemExit(f"{path.name} did not keep {ticker} {session}")
    return frozen


def wick_tagged(side: str, level: float, bar: dict) -> bool:
    """Whether the candle's wick reached within 15 cents of the level.

    A put approaches from below, so the high is the wick. A call approaches
    from above, so the low is the wick. This does not choose an entry.
    """
    if side == "put":
        return float(bar["high"]) >= level - WICK
    if side == "call":
        return float(bar["low"]) <= level + WICK
    raise ValueError(f"unknown side {side}")


def wick_sentence(side: str, level: float, bar: dict) -> str:
    """One lesson line. The distance stays the score. The entry stays the retest."""
    color = "green" if side == "put" else "red"
    when = datetime.fromtimestamp(bar["close_at"], PT).strftime("%H:%M")
    price = f"{level:g}"
    if wick_tagged(side, level, bar):
        fact = (
            f"The {when} PT {color} wicked within 15 cents of {price}. "
            "The checker could take that candle."
        )
    else:
        fact = f"The {when} PT {color} did not wick within 15 cents of {price}."
    return (
        f"{fact} The bars-and-points score is unchanged. "
        "The live entry stays the retest."
    )


def _fmt(bar: dict) -> str:
    when = datetime.fromtimestamp(bar["close_at"], PT).strftime("%H:%M")
    push = bar["close"] - bar["open"]
    purple = f"{bar['purple']:.1f}" if bar.get("purple") is not None else "-"
    return (
        f"{when} {_color(bar)} open {bar['open']:.2f} close {bar['close']:.2f} "
        f"push {push:+.2f} purple {purple}"
    )


def _snipe_line(side: str, bottom: dict) -> str:
    kind = "put" if side == "put" else "call"
    if bottom["sniped"] and bottom["naive"]["close_at"] == bottom["ideal"]["close_at"]:
        return (
            "The confirmed buy is the bottom of the contract. "
            "The first entry candle is that buy."
        )
    if bottom["sniped"]:
        return (
            "The confirmed buy is the bottom of the contract. "
            f"The first color left {bottom['naive_left']:.2f} stock points, "
            f"which is the {kind} more expensive."
        )
    if bottom["ideal_left"] == 0:
        return (
            "The confirmed buy matched the bottom price. "
            "An earlier candle already printed it."
        )
    if bottom["naive"]["close_at"] == bottom["bottom"]["close_at"]:
        return (
            "The first entry candle is the bottom. "
            f"The confirmed buy is {bottom['ideal_left']:.2f} stock points off it."
        )
    return (
        f"The confirmed buy is {bottom['ideal_left']:.2f} stock points off the bottom. "
        f"The first color left {bottom['naive_left']:.2f} stock points, "
        f"which is the {kind} more expensive."
    )


def render(drill: dict, scored: dict, bottom: dict, wick: str) -> str:
    buy_gap = scored["buy_price_gap"]
    sell_gap = scored["sell_price_gap"]
    side = drill["side"]
    if side == "put":
        buy_name = "First green after the lose"
        sell_name = "First red after the buy"
        buy_miss = (
            f"- Buy miss: {scored['buy_bars_early']} bar early, "
            f"{buy_gap:.2f} less stock-price strength"
        )
        sell_miss = (
            f"- Sell miss: {scored['sell_bars_early']} bars early, "
            f"{sell_gap:.2f} of the drop left behind"
        )
        color_line = "The miss is taking the first green or the first red."
    else:
        buy_name = "First red after the claim"
        sell_name = "First green after the buy"
        buy_miss = (
            f"- Buy miss: {scored['buy_bars_early']} bar early, "
            f"{buy_gap:.2f} more stock-price paid"
        )
        sell_miss = (
            f"- Sell miss: {scored['sell_bars_early']} bars early, "
            f"{sell_gap:.2f} of the rally left behind"
        )
        color_line = "The miss is taking the first red or the first green."
    return "\n".join(
        [
            f"## {drill['ticker']} {drill['session']} {drill['side']}",
            "",
            drill["why"],
            f"Contract: {drill['contract']}",
            "",
            f"- Confirmed buy: {_fmt(scored['ideal_buy'])}",
            f"- {buy_name}: {_fmt(scored['naive_buy'])}",
            buy_miss,
            f"- Confirmed sell: {_fmt(scored['ideal_sell'])}",
            f"- {sell_name}: {_fmt(scored['naive_sell'])}",
            sell_miss,
            f"- Contract bottom: {_fmt(bottom['bottom'])}",
            f"- Confirmed buy versus the bottom: {bottom['ideal_left']:.2f} stock points",
            f"- First color versus the bottom: {bottom['naive_left']:.2f} stock points",
            "",
            wick,
            "",
            "The feed did contain the confirmed candles. " + color_line,
            _snipe_line(side, bottom),
            "",
        ]
    )


def render_lesson(goal: dict, blocks: list[str]) -> str:
    body = [
        f"# {goal['title']}",
        "",
        "This is the first goal. A goal is a lesson. It is not a pattern and it is not an order.",
        "",
        " ".join(goal["says"].split()),
        "",
        "The number is stock points on the entry candle. That is where the contract is bought. It is not a priced premium.",
        "",
    ]
    body.extend(blocks)
    return "\n".join(body)


def render_snipe_block(drill: dict, bottom: dict, wick: str) -> str:
    return "\n".join(
        [
            f"## {drill['ticker']} {drill['session']} {drill['side']}",
            "",
            drill["why"],
            f"Contract: {drill['contract']}",
            "",
            f"- Bottom: {_fmt(bottom['bottom'])}",
            f"- Confirmed buy: {_fmt(bottom['ideal'])}",
            f"- First entry candle: {_fmt(bottom['naive'])}",
            f"- First candle off the bottom: {bottom['naive_left']:.2f} stock points",
            "",
            wick,
            "",
            _snipe_line(drill["side"], bottom),
            "One drill is an observation.",
            "",
        ]
    )


def first_goal(spec: dict) -> dict:
    goals = spec.get("goals") or []
    if not goals:
        raise SystemExit("learning/goals.yaml has no goal")
    return goals[0]


def _score_side(drill: dict, session: list[dict], buy_at: int, sell_at: int) -> dict:
    level = float(drill["level"])
    if drill["side"] == "put":
        return score_put(session, level, buy_at, sell_at)
    if drill["side"] == "call":
        return score_call(session, level, buy_at, sell_at)
    raise SystemExit(f"{drill['id']} has no entry color")


def score_drills() -> str:
    spec = yaml.safe_load(DRILLS_PATH.read_text())
    goal = first_goal(yaml.safe_load(GOALS_PATH.read_text()))
    if goal["id"] != "snipe-bottom":
        raise SystemExit(f"{goal['id']} is not the snipe-bottom goal")
    sections = [
        "# Intraday training",
        "",
        f"The first goal is {goal['title']}.",
        "Each drill is a play whose candles the operator confirmed. "
        "A live read uses finished 10-minute bars only. "
        "One drill is an observation, not a pattern and not an order.",
        "",
    ]
    lesson_blocks = []
    for drill in spec["drills"]:
        session = bars_for_drill(drill)
        add_rsi(session)
        buy_at = _clock(drill["ideal_buy"], drill["session"])
        sell_at = _clock(drill["ideal_sell"], drill["session"])
        level = float(drill["level"])
        bottom = score_bottom(session, drill["side"], level, buy_at)
        scored = _score_side(drill, session, buy_at, sell_at)
        wick = wick_sentence(drill["side"], level, scored["naive_buy"])
        sections.append(render(drill, scored, bottom, wick))
        if drill.get("goal", goal["id"]) == goal["id"]:
            lesson_blocks.append(render_snipe_block(drill, bottom, wick))
    text = "\n".join(sections)
    TRAINING_PATH.write_text(text)
    LESSONS_DIR.mkdir(parents=True, exist_ok=True)
    (LESSONS_DIR / f"{goal['id']}.md").write_text(render_lesson(goal, lesson_blocks))
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
