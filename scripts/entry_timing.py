#!/usr/bin/env python3
"""Entry timing study: confirm (today's live process) vs asap (send on the signal), in stock points and option dollars.

model   fill at the fill-bar open, and drop entries the fill bar reclaimed (what the bench scores; not achievable)
confirm wait for the fill bar to finish, then buy near its close (the live checker; ~T+11 to T+16 minutes)
asap    buy at the fill-bar open (~T+1); a fill bar that reclaims becomes an exit at its close
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import bench  # noqa: E402
import claim_alerts as claim  # noqa: E402
import freeze  # noqa: E402

PT = ZoneInfo("America/Los_Angeles")


def sign(side):
    return 1 if side == "call" else -1


def day_rows(day):
    when = datetime.fromisoformat(day).replace(hour=13, minute=10, tzinfo=PT)
    prepared = bench.prepare(
        ROOT / "bench" / "fixtures" / f"{day}-levels.yaml",
        ROOT / "bench" / "fixtures" / f"{day}-bars.json",
        int(when.timestamp()),
    )
    settings = claim.live_settings()
    armed = int(prepared["armed_at"].timestamp())
    rows = []
    for ticker in prepared["tickers"]:
        bars = claim.add_indicators([dict(b) for b in prepared["bars"][ticker]])
        by_close = {b["close_at"]: b for b in bars}
        events = claim.replay(bars, prepared["grouped"][ticker], armed, settings)
        open_entry = None
        for event in events:
            fill_bar = by_close.get(event["close_at"])
            if event["kind"] == "entry":
                open_entry = (event, fill_bar)
            elif event["kind"] == "exit" and open_entry:
                entry, fbar = open_entry
                exit_close = by_close[event["close_at"]]["c"]
                s = sign(entry["side"])
                rows.append({
                    "day": day, "ticker": ticker, "side": entry["side"], "level": entry["level"],
                    "signal_at": entry["signal_at"], "fill_at": entry["close_at"], "exit_at": event["close_at"],
                    "kind": "trade", "exit_reason": event["reason"],
                    "model": s * (exit_close - entry["fill"]),
                    "confirm": s * (exit_close - fbar["c"]) if event["close_at"] != entry["close_at"] else 0.0,
                    "asap": s * (exit_close - entry["fill"]),
                })
                open_entry = None
            elif event["kind"] == "skip" and event["reason"] == "reclaim":
                # The fill bar closed back through: asap would already hold it, and sells at that close.
                s = sign(event["side"])
                rows.append({
                    "day": day, "ticker": ticker, "side": event["side"], "level": event["level"],
                    "signal_at": event["signal_at"], "fill_at": event["close_at"], "exit_at": event["close_at"],
                    "kind": "reclaimed fill bar", "exit_reason": "reclaim",
                    "model": 0.0, "confirm": 0.0, "asap": s * (fill_bar["c"] - event["fill"]),
                })
    return rows


def option_dollars(rows):
    """For 10-23 rows, price the cash contract the live checker named, from broker option bars."""
    from robinhood_mcp import RobinhoodBroker

    broker = RobinhoodBroker()
    ledger = {}
    for line in (ROOT / "learning" / "trades.jsonl").read_text().splitlines():
        r = json.loads(line)
        ledger[(r["ticker"], r["side"], r.get("level"), r["close_at"])] = r
    out = []
    for row in rows:
        if row["day"] < "2026-10-22":
            continue
        match = ledger.get((row["ticker"], row["side"], row["level"], row["fill_at"]))
        contract = (match or {}).get("contract")
        if not contract or contract == "none":
            # A reclaimed fill bar has no plan contract. Use the same strike the checker picked for that level today.
            same = [r for r in ledger.values() if r["ticker"] == row["ticker"] and r["side"] == row["side"] and r.get("level") == row["level"] and r.get("contract")]
            contract = same[0]["contract"] if same else None
        if not contract:
            continue
        option_id = broker.find(row["ticker"], contract, 2026)
        if not option_id:
            continue
        iso = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
        bars = broker.option_bars(option_id, iso(row["signal_at"] - 600), iso(row["exit_at"] + 900))

        def at(moment, field):
            for bar in bars:
                start = datetime.fromisoformat(bar["begins_at"].replace("Z", "+00:00")).timestamp()
                if start <= moment < start + 300:
                    return bar[field]
            return None

        # asap fills ~1 min after the signal close: the 5-minute bar starting then, its open.
        asap_in = at(row["signal_at"] + 60, "o")
        # confirm fills after the fill bar and a ~5 minute pricing pass: the bar after the fill-bar close.
        confirm_in = at(row["fill_at"] + 60, "o")
        confirm_slow = at(row["fill_at"] + 360, "o")
        out_px = at(row["exit_at"] + 60, "o")
        if None in (asap_in, confirm_in, out_px):
            continue
        out.append({
            **row, "contract": contract,
            "asap_$": round((out_px - asap_in) * 100, 2),
            "confirm_$": 0.0 if row["kind"] != "trade" else round((out_px - confirm_in) * 100, 2),
            "confirm_slow_$": 0.0 if row["kind"] != "trade" or confirm_slow is None else round((out_px - confirm_slow) * 100, 2),
        })
    return out


if __name__ != "__main__":
    raise SystemExit("run as a script: python3 scripts/entry_timing.py [--options]")
rows = [row for day in freeze.days() for row in day_rows(day)]
print("STOCK POINTS by day (model / confirm / asap)")
for day in freeze.days():
    d = [r for r in rows if r["day"] == day]
    print(f"  {day}: n={len([r for r in d if r['kind']=='trade'])} trades +{len([r for r in d if r['kind']!='trade'])} reclaimed fill bars | "
          f"model {sum(r['model'] for r in d):+.2f}  confirm {sum(r['confirm'] for r in d):+.2f}  asap {sum(r['asap'] for r in d):+.2f}")
print(f"  ALL: model {sum(r['model'] for r in rows):+.2f}  confirm {sum(r['confirm'] for r in rows):+.2f}  asap {sum(r['asap'] for r in rows):+.2f}")
trades = [r for r in rows if r["kind"] == "trade"]
print(f"  per trade, confirm minus asap: {sum(r['confirm'] - r['asap'] for r in trades) / len(trades):+.3f} pts over {len(trades)} trades")
print(f"  reclaimed fill bars asap would have eaten: {sum(r['asap'] for r in rows if r['kind'] != 'trade'):+.2f} pts over {len(rows) - len(trades)}")
if "--options" in sys.argv:
    priced = option_dollars(rows)
    print("\nOPTION DOLLARS, 2026-10-23 (one contract, broker option bars)")
    for r in priced:
        t = datetime.fromtimestamp(r["signal_at"], PT).strftime("%H:%M")
        print(f"  {t} {r['ticker']} {r['side']} {r['contract']:<14} {r['kind']:<18} asap {r['asap_$']:+7.2f}  confirm {r['confirm_$']:+7.2f}  confirm+5min {r['confirm_slow_$']:+7.2f}")
    for key in ("asap_$", "confirm_$", "confirm_slow_$"):
        print(f"  total {key}: {sum(r[key] for r in priced):+.2f} over {len(priced)}")
