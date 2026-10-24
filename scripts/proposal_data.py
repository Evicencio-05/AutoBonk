#!/usr/bin/env python3
"""The data pack every proposal starts from.

  python3 scripts/proposal_data.py              # sync the ledger with the broker, then write the pack
  python3 scripts/proposal_data.py --offline    # use the ledger as it is

Writes learning/proposals/data/YYYY-MM-DD.json and .md: ledger totals, cuts by
group, execution leaks (fill lag, slippage, failed exits), freeze progress,
skips, alarms, the operator's answers and notes, and every proposal with its
status. Nothing here changes the checker or places an order.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import freeze  # noqa: E402
import ledger  # noqa: E402
import review  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PT = ZoneInfo("America/Los_Angeles")
PROPOSALS = ROOT / "learning" / "proposals"
OUT = PROPOSALS / "data"


def front_matter(text: str) -> dict:
    """The key: value lines between the leading --- fences."""
    if not text.startswith("---\n"):
        return {}
    block = text[4:].split("\n---", 1)[0]
    found = {}
    for line in block.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            found[key.strip()] = value.strip()
    return found


def proposals(folder: Path = PROPOSALS) -> list[dict]:
    rows = []
    for path in sorted(folder.glob("*.md")):
        text = path.read_text()
        meta = front_matter(text)
        decision = re.search(r"^Decision:\s*(accept|reject|wait)\b", text, re.MULTILINE | re.IGNORECASE)
        rows.append(
            {
                "file": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
                "title": meta.get("title") or path.stem,
                "kind": meta.get("kind") or "decision",
                "status": meta.get("status") or "open",
                "created": meta.get("created") or "",
                "recommendation": meta.get("recommendation") or "",
                "operator_decision": decision.group(1).lower() if decision else "",
            }
        )
    return rows


def _cut(rows: list[dict], key) -> dict:
    live = dict(review._bucket([r for r in rows if r.get("mode") == "live"], key))
    plan = dict(review._bucket([r for r in rows if r.get("mode") == "plan"], key, "plan_dollars"))
    return {name: {"live": live.get(name), "what_if": plan.get(name)} for name in sorted(set(live) | set(plan))}


def execution(rows: list[dict], book: dict) -> dict:
    live = [r for r in rows if r.get("mode") == "live"]
    lags = [r["entry_latency_s"] / 60 for r in live if r.get("entry_latency_s") is not None]
    slips = [r["entry_slippage"] for r in live if r.get("entry_slippage") is not None]
    exits = [rec for rec in book.values() if rec.get("kind") == "exit"]
    return {
        "live_trades": len(live),
        "fill_lag_minutes": {"n": len(lags), "median": sorted(lags)[len(lags) // 2] if lags else None, "max": max(lags) if lags else None},
        "entry_slippage_per_share": {"n": len(slips), "mean": round(sum(slips) / len(slips), 4) if slips else None},
        "expired_without_a_sell": [r["ref"] for r in live if r.get("outcome") == "expired"],
        "exit_routing": dict(Counter(rec.get("status") for rec in exits)),
        "exit_retries_over_one": [key for key, rec in book.items() if rec.get("kind") == "exit" and int(rec.get("attempts") or 0) > 1],
        "gave_back": [
            {"ref": r["ref"], "best": r.get("mfe_dollars"), "result": r.get("dollars")}
            for r in live
            if r.get("mfe_dollars") is not None and r.get("dollars") is not None and r["mfe_dollars"] - r["dollars"] >= 20
        ],
    }


def skips(fired: list[str]) -> dict:
    by_day: dict[str, Counter] = {}
    for identity in fired:
        parts = identity.split("|")
        if len(parts) != 6 or parts[1] != "skip":
            continue
        try:
            day = datetime.fromtimestamp(int(parts[4]), PT).date().isoformat()
        except ValueError:
            continue
        by_day.setdefault(day, Counter())[parts[5]] += 1
    return {day: dict(count) for day, count in sorted(by_day.items())}


def build(rows: list[dict], root: Path = ROOT) -> dict:
    try:
        fired = json.loads((root / "alerts" / "state.json").read_text()).get("fired") or []
    except (OSError, json.JSONDecodeError):
        fired = []
    try:
        alarms = json.loads((root / "alerts" / "alarms.json").read_text())
    except (OSError, json.JSONDecodeError):
        alarms = {}
    book = ledger.claim._broker_book(root / "alerts" / "broker.json")
    cuts = {
        "entry_number_at_level": lambda r: r.get("level_entry_number"),
        "after_a_stop_at_the_level": lambda r: r.get("prior_stop_at_level"),
        "hour": review._hour,
        "ticker": lambda r: r.get("ticker"),
        "side": lambda r: r.get("side"),
        "days_to_expiration": lambda r: r.get("dte"),
        "premium": review._premium,
        "exit_reason": lambda r: r.get("exit_reason"),
        "candle": lambda r: r.get("candle"),
        "operator_take": lambda r: r.get("operator_take") or "unlabeled",
    }
    return {
        "built": datetime.now(PT).isoformat(timespec="minutes"),
        "totals": {mode: ledger.summary(rows, mode) for mode in ("live", "plan", "paper")},
        "freeze": freeze.progress(rows, freeze.config(root / "config" / "freeze.yaml")),
        "cuts": {name: _cut(rows, key) for name, key in cuts.items()},
        "execution": execution(rows, book),
        "skips_by_day": skips(fired),
        "alarms_raised": alarms,
        "operator_notes": [
            {"ref": r["ref"], "take": r.get("operator_take"), "note": r.get("operator_note")}
            for r in rows
            if r.get("operator_take") or r.get("operator_note")
        ],
        "proposals": proposals(root / "learning" / "proposals"),
    }


def markdown(pack: dict) -> str:
    out = [f"# Proposal data, {pack['built']}", ""]
    for stats in pack["totals"].values():
        out.append(review._stats_line(stats))
    state = pack["freeze"]
    out += ["", f"Freeze: {state['closed']}/{state['target']} closed live trades since {state['started'] or '-'}.", "", "## Execution", ""]
    out += [f"- {key}: {value}" for key, value in pack["execution"].items()]
    out += ["", "## Cuts (n, net $, win %)", ""]
    for name, groups in pack["cuts"].items():
        cells = []
        for group, data in groups.items():
            live, plan = data["live"], data["what_if"]
            text = f"{group}: live {live['n']}/{live['net']:+.2f}" if live else f"{group}: live 0"
            if plan:
                text += f", what-if {plan['n']}/{plan['net']:+.2f}"
            cells.append(text)
        out.append(f"- **{name}**: " + "; ".join(cells))
    out += ["", "## Skips by day", ""] + [f"- {day}: {counts}" for day, counts in pack["skips_by_day"].items()]
    out += ["", "## Alarms still raised", ""] + ([f"- {item['text']}" for item in pack["alarms_raised"].values()] or ["None."])
    out += ["", "## Operator answers and notes", ""] + ([f"- {n['ref']}: {n['take'] or ''} {n['note'] or ''}" for n in pack["operator_notes"]] or ["None yet."])
    out += ["", "## Proposals", ""] + (
        [f"- [{p['status']}] {p['kind']}: {p['title']} ({p['file']})" for p in pack["proposals"]] or ["None."]
    )
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args(argv)
    if not args.offline:
        ledger.main(["sync"])
    pack = build(ledger.load())
    OUT.mkdir(parents=True, exist_ok=True)
    day = datetime.now(PT).date().isoformat()
    (OUT / f"{day}.json").write_text(json.dumps(pack, indent=1, default=str) + "\n")
    (OUT / f"{day}.md").write_text(markdown(pack))
    print(OUT.relative_to(ROOT) / f"{day}.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
