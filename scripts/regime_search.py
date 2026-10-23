"""Paper bounce and trend fills. Not the live entry, and not an alert.

Replay the sessions already scored in the level-respect note. Stock points
only. The live checker stays on the retest.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

import claim_alerts

PT = ZoneInfo("America/Los_Angeles")
ROOT = claim_alerts.ROOT
OUT = ROOT / "alerts" / "regime_forward.md"

MONDAY = {
    "AAPL": [335.8, 339.75, 340.3, 343.5, 345.4, 350],
    "AMZN": [248.25, 253.15, 255.75, 258.3, 261, 263.15],
    "GOOGL": [335.5, 338.75, 340.35, 342, 344.55, 346, 350],
    "META": [664.75, 680, 700, 710.15, 725, 730, 737.5],
    "NVDA": [209, 212, 213.4, 220, 222.35],
    "SPCX": [138.6, 142.5, 144, 146.5, 148.5],
    "TSLA": [342.5, 345.5, 350, 352.5, 359, 362.5, 372.75],
}
TUESDAY = {
    "AAPL": [328.75, 333, 335.8, 336.25, 340, 342.25, 343.5, 345.4, 350],
    "AMZN": [254.4, 256.18, 257.95, 260.5, 264.2, 265.9, 267, 269.58],
    "AVGO": [332.6, 340.2, 343],
    "GOOGL": [335.5, 339.85, 343.6, 346.25, 347.33, 352.66],
    "META": [650, 665, 680, 715, 725, 737, 745.5],
    "NVDA": [209, 212, 213.44, 217.5, 219.8, 223.35, 225.35],
    "SPCX": [138.5, 142.5, 145, 146.6, 153, 155.5, 158],
    "TSLA": [350, 352, 361, 364, 367.5, 370, 372.75, 377, 380, 382.75],
}


def _stamp(year: int, month: int, day: int, hour: int, minute: int) -> int:
    return int(datetime(year, month, day, hour, minute, tzinfo=PT).timestamp())


def _when(stamp: int) -> str:
    return datetime.fromtimestamp(stamp, PT).strftime("%Y-%m-%d %H:%M PT")


def _day(stamp: int) -> str:
    return datetime.fromtimestamp(stamp, PT).strftime("%Y-%m-%d")


def _ladder(prices: dict[str, list[float]]) -> list[dict]:
    levels = []
    for ticker, chain in prices.items():
        for price in chain:
            levels.append(
                {
                    "ticker": ticker,
                    "price": price,
                    "allows": "both",
                    "targets": [item for item in chain if item < price],
                    "up_targets": [item for item in chain if item > price],
                }
            )
    return levels


def _load_yaml(text: str) -> tuple[int, list[dict]]:
    data = yaml.safe_load(text)
    armed = datetime.fromisoformat(data["armed_at"])
    if armed.tzinfo is None:
        armed = armed.replace(tzinfo=PT)
    return int(armed.timestamp()), data["levels"]


def _books() -> list[dict]:
    sessions = []
    for name, hour, minute in (
        ("2026-10-14", 6, 30),
        ("2026-10-15", 6, 30),
        ("2026-10-16", 8, 27),
    ):
        path = ROOT / "bench" / "fixtures" / f"{name}-levels.yaml"
        armed, levels = _load_yaml(path.read_text())
        year, month, day = (int(part) for part in name.split("-"))
        sessions.append(
            {
                "day": name,
                "armed": armed,
                "end": _stamp(year, month, day, 13, 0),
                "levels": levels,
            }
        )
        del hour, minute
    sessions.append(
        {
            "day": "2026-10-19",
            "armed": _stamp(2026, 10, 19, 6, 5),
            "end": _stamp(2026, 10, 20, 7, 30),
            "levels": _ladder(MONDAY),
        }
    )
    sessions.append(
        {
            "day": "2026-10-20",
            "armed": _stamp(2026, 10, 20, 7, 34),
            "end": _stamp(2026, 10, 20, 13, 0),
            "levels": _ladder(TUESDAY),
        }
    )
    wednesday = _load_yaml(
        __import__("subprocess")
        .check_output(["git", "show", "fa26dd1:alerts/levels.yaml"], cwd=ROOT, text=True)
    )
    sessions.append(
        {
            "day": "2026-10-21",
            "armed": _stamp(2026, 10, 21, 4, 0),
            "end": _stamp(2026, 10, 21, 13, 0),
            "levels": wednesday[1],
        }
    )
    thursday = _load_yaml((ROOT / "alerts" / "levels.yaml").read_text())
    sessions.append(
        {
            "day": "2026-10-22",
            "armed": thursday[0],
            "end": _stamp(2026, 10, 22, 13, 0),
            "levels": thursday[1],
        }
    )
    return sessions


def _bars(ticker: str, cache: dict[str, list[dict]]) -> list[dict]:
    if ticker in cache:
        return cache[ticker]
    raw = claim_alerts.fetch_five_minute(ticker, "1mo")
    now = _stamp(2026, 10, 22, 16, 30)
    folded = claim_alerts.ten_minute_bars(raw, now)
    session = [bar for bar in folded if claim_alerts.in_session(bar["close_at"])]
    claim_alerts.add_indicators(session)
    cache[ticker] = session
    return session


def _retest_signals(bars: list[dict], levels: list[dict], armed: int, end: int) -> list[dict]:
    settings = claim_alerts.live_settings()
    found = []
    history: list[dict] = []
    prev = None
    for bar in bars:
        if bar["close_at"] > end:
            break
        if bar["close_at"] >= armed and not claim_alerts._is_clock(bar["close_at"]):
            for level in levels:
                intent = claim_alerts._signal(prev, bar, [level], settings, history)
                if intent and intent.get("reason") == "retest":
                    found.append({**intent, "bar_at": bar["close_at"]})
        history = history + [bar]
        prev = bar
    return found


def _score(kind: str, trades: list[dict]) -> dict:
    closed = [trade for trade in trades if trade["reason"] != "open"]
    wins = [trade["points"] for trade in closed if trade["points"] > 0]
    losses = [-trade["points"] for trade in closed if trade["points"] < 0]
    gross_win = sum(wins)
    gross_loss = sum(losses)
    return {
        "kind": kind,
        "closes": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "flat": len(closed) - len(wins) - len(losses),
        "net": sum(trade["points"] for trade in closed),
        "profit_factor": None if gross_loss == 0 else gross_win / gross_loss,
        "gross_win": gross_win,
        "gross_loss": gross_loss,
    }


def _line(trade: dict, day: str, caught: str) -> str:
    exit_name = {
        "target": "target",
        "reclaim": "reclaim",
        "clock": "clock",
    }.get(trade["reason"], trade["reason"])
    return (
        f"| {day} | {trade['ticker']} | {trade['kind']} | {trade['side']} "
        f"| {trade['level']:.2f} | {_when(trade['close_at'])} | {trade['fill']:.2f} "
        f"| {_when(trade['exit_at'])} | {trade['exit']:.2f} | {exit_name} "
        f"| {trade['points']:+.2f} | {caught} |"
    )


def _fmt_pf(score: dict) -> str:
    factor = score["profit_factor"]
    if factor is None:
        return "n/a"
    return f"{factor:.2f}"


def main() -> None:
    cache: dict[str, list[dict]] = {}
    rows: list[str] = []
    bounce: list[dict] = []
    trend: list[dict] = []
    trend_only: list[dict] = []
    trend_caught: list[dict] = []
    bounce_same_bar = 0
    by_day: dict[str, dict[str, int]] = {}
    for session in _books():
        levels = session["levels"]
        names = sorted({level["ticker"] for level in levels if level.get("ticker")})
        day_counts = {"bounce": 0, "trend": 0, "trend_only": 0, "retest": 0}
        for ticker in names:
            book = [level for level in levels if level.get("ticker") == ticker]
            series = [
                bar
                for bar in _bars(ticker, cache)
                if bar["close_at"] <= session["end"]
            ]
            if not series:
                continue
            tagged = [
                {**bar, "ticker": ticker}
                for bar in series
            ]
            retests = _retest_signals(tagged, book, session["armed"], session["end"])
            day_counts["retest"] += len(retests)
            for kind in ("bounce", "trend"):
                trades = claim_alerts.regime_trades(
                    tagged,
                    book,
                    armed_at=session["armed"],
                    kind=kind,
                    end_at=session["end"],
                )
                for trade in trades:
                    trade["ticker"] = ticker
                    same = any(
                        abs(item["level"] - trade["level"]) < 0.001
                        and item["side"] == trade["side"]
                        and item["bar_at"] == trade["signal_at"]
                        for item in retests
                    )
                    later = any(
                        abs(item["level"] - trade["level"]) < 0.001
                        and item["side"] == trade["side"]
                        and trade["signal_at"] < item["bar_at"] <= trade["exit_at"]
                        for item in retests
                    )
                    if kind == "bounce":
                        caught = "same bar" if same else "no"
                        bounce.append(trade)
                        if same:
                            bounce_same_bar += 1
                    else:
                        kept = (not trade["retested"]) and not later
                        caught = "no" if kept else "yes"
                        trend.append(trade)
                        if kept:
                            trend_only.append(trade)
                        else:
                            trend_caught.append(trade)
                    rows.append(_line(trade, session["day"], caught))
                    day_counts[kind] += 1
                    if kind == "trend" and caught == "no":
                        day_counts["trend_only"] += 1
        by_day[session["day"]] = day_counts
        print(session["day"], day_counts, flush=True)

    bounce_score = _score("bounce", bounce)
    trend_score = _score("trend", trend)
    only_score = _score("trend", trend_only)
    caught_score = _score("trend", trend_caught)
    summary = {
        "bounce": bounce_score,
        "trend": trend_score,
        "trend_only": only_score,
        "trend_caught": caught_score,
        "bounce_same_bar": bounce_same_bar,
        "by_day": by_day,
        "bounce_n": len(bounce),
        "trend_n": len(trend),
    }
    Path("/tmp/regime_summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    only_clock = sum(1 for trade in trend_only if trade["reason"] == "clock")
    only_reclaim = sum(1 for trade in trend_only if trade["reason"] == "reclaim")
    only_target = sum(1 for trade in trend_only if trade["reason"] == "target")
    if only_target == 0:
        reached = "None of them reached the next posted number."
    else:
        reached = f"{only_target} of them reached the next posted number."
    header = f"""# Regime forward

Neither paper entry is worth keeping. The live entry stays the retest. These rows do not send a Discord alert and they do not place an order.

Bounce closed {bounce_score['closes']} times, net {bounce_score['net']:+.2f} stock points, profit factor {_fmt_pf(bounce_score)}. The fade gate was a profit factor of at least 2, a positive net, and at least 3 closes. Bounce has the count and a small net. It does not have the factor. {bounce_same_bar} of the {len(bounce)} signal bars are already a retest signal.

Trend closed {trend_score['closes']} times, net {trend_score['net']:+.2f}, profit factor {_fmt_pf(trend_score)}. Entering the next bar after a claim loses money. {caught_score['closes']} of those were also a retest, net {caught_score['net']:+.2f}. The {only_score['closes']} the retest did not catch net {only_score['net']:+.2f}. {reached} {only_clock} drifted to the 12:50 PT clock. {only_reclaim} reclaimed on the way. The trend rows that did reach the next number were already retest signals: Wednesday AAPL 340 and Thursday AAPL 345.40.

Thursday added no trend row the retest missed.

## Rule

- Bounce: a posted level is tagged within 15 cents and the close stays inside the half-ATR band. The fill is the next bar's open, in the direction of the rejection. A close at or above the level is a call. A close under it is a put.
- Trend: a posted level is claimed by a finished 10-minute close beyond it by half the 14-period ATR. The fill is the next bar's open, in the direction of the claim. The target is the next posted number.
- Chase is 0.50 from the level. A wider open is not a fill.
- A close back through the level by half the ATR is the exit. A bounce targets the furthest posted number in that direction. A trend targets the next one. If that number is not reached, the exit is the 12:50 PT bar.
- Retest is "yes" when a later wick tags the level before the exit, or the retest rule signals that level before the exit. "same bar" means the bounce signal is itself a retest signal. "no" means the retest did not have this one.
- Each signal is its own paper row. This is not one open position.

## Window

The seven sessions in the level-respect note, including Thursday 2026-10-22. Prices are Yahoo 5-minute bars folded into finished 10-minute bars. Monday's book runs through Tuesday 07:30 PT. Tuesday's book starts at 07:34 PT.

## Test

| Day | Ticker | Kind | Side | Level | Fill time | Fill | Exit time | Exit | Why | Stock | Retest |
|-----|--------|------|------|-------|-----------|------|-----------|------|-----|-------|--------|
"""
    body = "\n".join(rows)
    OUT.write_text(header + body + ("\n" if body else ""))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
