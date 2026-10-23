#!/usr/bin/env python3
"""Draft the daily and weekly reviews from the trade ledger. You write only the judgment.

  python3 scripts/review.py day [--day YYYY-MM-DD]     # learning/reviews/YYYY-MM-DD.md
  python3 scripts/review.py week [--end YYYY-MM-DD]    # learning/reviews/week-YYYY-MM-DD.md

The numbers come from learning/trades.jsonl (run `ledger.py sync` first). A
redraft keeps every answer already written in "Would I take it" and in the
operator sections, so it is safe to run again. Nothing here changes the
checker, the rules, or an order.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import freeze  # noqa: E402
import ledger  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PT = ZoneInfo("America/Los_Angeles")
REVIEWS = ROOT / "learning" / "reviews"
PROPOSALS = ROOT / "learning" / "proposals.md"
ALARMS = ROOT / "alerts" / "alarms.json"
MARK = "Drafted by `scripts/review.py day`"
KEEP = ("## Would I take it", "## What I saw that the checker did not", "## Lessons", "## Proposals")


def _money(value) -> str:
    return "-" if value is None else f"{value:+.2f}"


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _kept(path: Path) -> dict[str, str]:
    """Operator sections already written in an earlier draft."""
    if not path.is_file():
        return {}
    text = path.read_text()
    found = {}
    for header in KEEP:
        if header in text:
            found[header] = header + text.split(header, 1)[1].split("\n## ", 1)[0].rstrip("\n")
    return found


def _answers(section: str) -> dict[str, list[str]]:
    rows = {}
    for line in section.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and cells[0].startswith("`"):
            rows[cells[0]] = cells
    return rows


def _stats_line(stats: dict) -> str:
    if not stats["trades"]:
        return f"- {stats['mode']}: no scored trades."
    return (
        f"- {stats['mode']}: {stats['trades']} trades, net ${stats['net']:+.2f}, "
        f"win rate {stats['win_rate']}%, avg win {_money(stats['avg_win'])}, "
        f"avg loss {_money(stats['avg_loss'])}, expectancy {_money(stats['expectancy'])}, "
        f"profit factor {stats['profit_factor'] if stats['profit_factor'] is not None else '-'}"
    )


def _skips(day: str) -> dict[str, int]:
    try:
        fired = json.loads((ROOT / "alerts" / "state.json").read_text()).get("fired") or []
    except (OSError, json.JSONDecodeError):
        return {}
    counts: dict[str, int] = defaultdict(int)
    for identity in fired:
        parts = identity.split("|")
        if len(parts) != 6 or parts[1] != "skip":
            continue
        try:
            when = datetime.fromtimestamp(int(parts[4]), PT).date().isoformat()
        except ValueError:
            continue
        if when == day:
            counts[parts[5]] += 1
    return dict(sorted(counts.items(), key=lambda item: -item[1]))


def _alarms() -> dict:
    try:
        return json.loads(ALARMS.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def day_review(day: str, rows: list[dict]) -> str:
    path = REVIEWS / f"{day}.md"
    kept = _kept(path)
    today = [row for row in rows if row.get("day") == day]
    taken = [row for row in today if row.get("mode") == "live"]
    plans = [row for row in today if row.get("mode") in ("plan", "paper")]
    spec = freeze.config()
    state = freeze.progress(rows, spec)
    out = [
        f"# Review {day}",
        "",
        f"{MARK}. Numbers are from `learning/trades.jsonl`. "
        "Fill the four operator sections at the bottom. A review is an observation: it does not "
        "change `rules/ta_rules.md`, the checker, or an order.",
        "",
        "## Numbers",
        "",
        _stats_line(ledger.summary(today, "live")),
        _stats_line(ledger.summary(today, "plan")),
        _stats_line(ledger.summary(today, "paper")),
        f"- Freeze {'on' if state['active'] else 'off'} since {state['started'] or '-'}: "
        f"{state['closed']}/{state['target']} closed live trades, net ${state['net']:+.2f}.",
        "",
        "## Taken (broker fills, one contract)",
        "",
    ]
    if taken:
        out += [
            "| Entry | Ticker | Side | Level | # at level | Contract | DTE | Fill | Exit | Outcome | $ | Best $ | Worst $ | Fill lag (min) | Exit reason |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for row in taken:
            lag = row.get("entry_latency_s")
            out.append(
                f"| {row['entry_time'][11:16]} | {row['ticker']} | {row['side']} | {_cell(row.get('level'))} "
                f"| {_cell(row.get('level_entry_number'))} | {row.get('contract') or ''} | {_cell(row.get('dte'))} "
                f"| {_cell(row.get('entry_fill'))} | {_cell(row.get('exit_fill'))}{'*' if row.get('exit_assumed') else ''} "
                f"| {row.get('outcome') or ''} | {_money(row.get('dollars'))} | {_money(row.get('mfe_dollars'))} "
                f"| {_money(row.get('mae_dollars'))} | {'' if lag is None else round(lag / 60, 1)} | {row.get('exit_reason') or ''} |"
            )
        if any(row.get("exit_assumed") for row in taken):
            out.append("")
            out.append("`*` No sell filled. The contract expired and its value is taken from the last stock print.")
    else:
        out.append("No Agentic fills.")
    out += ["", "## Signals with no order", ""]
    if plans:
        out += [
            "| Entry | Ticker | Side | Level | # at level | Contract | Why no order | Plan in | Plan out | Plan $ | Exit reason |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for row in plans:
            out.append(
                f"| {row['entry_time'][11:16]} | {row['ticker']} | {row['side']} | {_cell(row.get('level'))} "
                f"| {_cell(row.get('level_entry_number'))} | {row.get('contract') or ''} "
                f"| {row.get('no_order_reason') or row.get('mode')} | {_cell(row.get('plan_entry_premium'))} "
                f"| {_cell(row.get('plan_exit_premium'))} | {_money(row.get('plan_dollars'))} | {row.get('exit_reason') or ''} |"
            )
    else:
        out.append("None.")
    reentries = [row for row in today if (row.get("level_entry_number") or 1) > 1]
    out += ["", "## Re-entries at a level", ""]
    if reentries:
        for row in reentries:
            out.append(
                f"- {row['ticker']} {row['side']} {_cell(row.get('level'))} at {row['entry_time'][11:16]}: "
                f"entry #{row['level_entry_number']}, "
                f"{'after a stop' if row.get('prior_stop_at_level') else 'no stop before'}, "
                f"{_cell(row.get('minutes_since_level_exit'))} min since the last exit there, "
                f"{row.get('level_flips_before')} flips before it. "
                f"Result {_money(row.get('dollars') if row.get('mode') == 'live' else row.get('plan_dollars'))}."
            )
    else:
        out.append("None.")
    skips = _skips(day)
    out += ["", "## Skips", ""]
    out.append(", ".join(f"{reason} {count}" for reason, count in skips.items()) or "None.")
    out += ["", "## Alarms still raised", ""]
    alarms = _alarms()
    out += [f"- {item['text']}" for item in alarms.values()] or ["None."]
    out += ["", "## Fade and backtest", ""]
    out.append(
        "Append the day's fade closes to `alerts/fade_forward.md`. Run `python3 scripts/recap.py` and "
        "paste `learning/parameter_search.md` here. During the freeze a pass is reported and not applied."
    )
    labels = _answers(kept.get(KEEP[0], ""))
    out += [
        "",
        KEEP[0],
        "",
        "One row per signal. Answer yes, no, or unsure, and why, from your own read of the chart at that "
        "candle. This is the check that the checker trades your TA. The answers go back into the ledger "
        "as `operator_take`.",
        "",
        "| Trade | Ticker | Entry | Mode | Take | Why |",
        "|---|---|---|---|---|---|",
    ]
    for row in today:
        key = f"`{row['ref']}`"
        prior = labels.get(key)
        take = prior[-2] if prior else ""
        note = prior[-1] if prior else ""
        out.append(f"| {key} | {row['ticker']} {row['side']} {_cell(row.get('level'))} | {row['entry_time'][11:16]} | {row['mode']} | {take} | {note} |")
    for header, prompt in (
        (KEEP[1], "Anything you would have done that no rule covers: a level you would have skipped, an exit you would have taken earlier."),
        (KEEP[2], "What repeated, and on which earlier day. A pattern needs more than one taken trade."),
        (KEEP[3], "A rule change you want. It goes to `learning/proposals.md` for the weekly review, not into the checker."),
    ):
        out += ["", kept.get(header) or f"{header}\n\n{prompt}"]
    return "\n".join(out).rstrip() + "\n"


def _bucket(rows: list[dict], key, value="dollars") -> list[tuple[str, dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[str(key(row))].append(row)
    out = []
    for name, members in sorted(groups.items()):
        scored = [row[value] for row in members if row.get(value) is not None]
        out.append(
            (
                name,
                {
                    "n": len(scored),
                    "net": round(sum(scored), 2),
                    "win": round(100 * len([v for v in scored if v > 0]) / len(scored)) if scored else None,
                },
            )
        )
    return out


def _hour(row: dict) -> str:
    minutes = row.get("minutes_after_open")
    if minutes is None:
        return "?"
    return f"{6 + (30 + minutes) // 60:02d}h PT"


def _premium(row: dict) -> str:
    price = row.get("entry_fill") or row.get("plan_entry_premium")
    if price is None:
        return "?"
    return "<0.20" if price < 0.20 else "0.20-0.50" if price < 0.50 else "0.50-1.00" if price < 1 else ">=1.00"


def week_review(end: str, rows: list[dict]) -> str:
    last = date.fromisoformat(end)
    first = (last - timedelta(days=6)).isoformat()
    week = [row for row in rows if first <= str(row.get("day") or "") <= end]
    spec = freeze.config()
    state = freeze.progress(rows, spec)
    out = [
        f"# Week ending {end}",
        "",
        "Drafted by `scripts/review.py week`. Read this once a week. A rule changes only here, "
        "only from `learning/proposals.md`, and only when the sample supports it.",
        "",
        "## Totals",
        "",
        _stats_line(ledger.summary(week, "live")),
        _stats_line(ledger.summary(week, "plan")),
        _stats_line(ledger.summary(week, "paper")),
        f"- All-time live: {_stats_line(ledger.summary(rows, 'live'))[2:]}",
        f"- Freeze: {state['closed']}/{state['target']} closed live trades since {state['started'] or '-'}.",
        "",
        "Groups below are live dollars, then plan dollars for signals with no order. Fewer than 10 in a "
        "group is an anecdote.",
    ]
    cuts = (
        ("Entry number at the level", lambda row: row.get("level_entry_number")),
        ("After a stop at the same level", lambda row: row.get("prior_stop_at_level")),
        ("Hour", _hour),
        ("Ticker", lambda row: row.get("ticker")),
        ("Side", lambda row: row.get("side")),
        ("Days to expiration", lambda row: row.get("dte")),
        ("Premium", _premium),
        ("Exit reason", lambda row: row.get("exit_reason")),
        ("Candle", lambda row: row.get("candle")),
        ("You would take it", lambda row: row.get("operator_take") or "unlabeled"),
    )
    live = [row for row in week if row.get("mode") == "live"]
    plan = [row for row in week if row.get("mode") == "plan"]
    for title, key in cuts:
        out += ["", f"## {title}", "", "| Group | Live n | Live $ | Live win % | Plan n | Plan $ |", "|---|---|---|---|---|---|"]
        plan_groups = dict(_bucket(plan, key, "plan_dollars"))
        names = sorted({name for name, _ in _bucket(live, key)} | set(plan_groups))
        live_groups = dict(_bucket(live, key))
        for name in names:
            got = live_groups.get(name, {"n": 0, "net": 0, "win": None})
            pl = plan_groups.get(name, {"n": 0, "net": 0})
            out.append(
                f"| {name} | {got['n']} | {got['net']:+.2f} | {'' if got['win'] is None else got['win']} "
                f"| {pl['n']} | {pl['net']:+.2f} |"
            )
    taken = [row for row in live if row.get("operator_take")]
    if taken:
        agree = [row for row in taken if row["operator_take"] == "yes"]
        out += [
            "",
            "## Does the checker trade your TA?",
            "",
            f"You would have taken {len(agree)} of {len(taken)} labeled live trades. "
            f"Those made {sum(row.get('dollars') or 0 for row in agree):+.2f}; the rest made "
            f"{sum(row.get('dollars') or 0 for row in taken if row not in agree):+.2f}.",
        ]
    proposals = PROPOSALS.read_text() if PROPOSALS.is_file() else ""
    out += ["", "## Proposals waiting", "", proposals.split("## Open", 1)[-1].split("\n## ", 1)[0].strip() or "None."]
    out += ["", "## Decisions", "", "For each proposal: accept, reject, or wait for more trades, and why."]
    return "\n".join(out).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    sub = parser.add_subparsers(dest="command", required=True)
    day_cmd = sub.add_parser("day")
    day_cmd.add_argument("--day", default=datetime.now(PT).date().isoformat())
    day_cmd.add_argument("--force", action="store_true")
    week_cmd = sub.add_parser("week")
    week_cmd.add_argument("--end", default=datetime.now(PT).date().isoformat())
    args = parser.parse_args(argv)
    rows = ledger.load()
    REVIEWS.mkdir(parents=True, exist_ok=True)
    if args.command == "day":
        path = REVIEWS / f"{args.day}.md"
        if path.is_file() and MARK not in path.read_text() and not args.force:
            print(f"{path.relative_to(ROOT)} was written by hand. Left as is; pass --force to replace it.")
            return 1
        path.write_text(day_review(args.day, rows))
    else:
        path = REVIEWS / f"week-{args.end}.md"
        path.write_text(week_review(args.end, rows))
    print(path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
