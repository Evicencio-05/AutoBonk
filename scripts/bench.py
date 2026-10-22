#!/usr/bin/env python3
"""Rerun the live replay on a frozen levels file and one settings snapshot.

A replay is an observation. This script does not place an order, and it does
not change the live defaults or rules/ta_rules.md.

  python3 scripts/bench.py run --levels day.yaml --bars day.json --as-of 2026-10-15T13:00:00-07:00 --out bench/runs/day
  python3 scripts/bench.py compare --levels day.yaml --bars day.json --as-of 2026-10-15T13:00:00-07:00 --variable touch --value 0.05 --question "..." --day discovery --out bench/experiments/touch
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CLAIM_PATH = Path(__file__).resolve().parent / "claim_alerts.py"


class BenchError(Exception):
    pass


def _load_claim_alerts():
    spec = importlib.util.spec_from_file_location("claim_alerts", CLAIM_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


claim = _load_claim_alerts()


def _read(path: Path) -> dict:
    text = path.read_text()
    if path.suffix == ".json":
        data = json.loads(text)
    else:
        data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise BenchError(f"{path} must be a mapping")
    return data


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def _parse_time(value) -> int:
    if isinstance(value, bool):
        raise BenchError("a time must be a timestamp or an ISO time")
    if isinstance(value, (int, float)):
        return int(value)
    when = datetime.fromisoformat(str(value))
    if when.tzinfo is None:
        when = when.replace(tzinfo=claim.PT)
    return int(when.timestamp())


def _stamp(close_at: int) -> str:
    return datetime.fromtimestamp(close_at, claim.PT).strftime("%Y-%m-%d %H:%M PT")


def code_identity() -> dict:
    """Git revision when HEAD is clean, otherwise the hash of claim_alerts.py."""
    digest = hashlib.sha256(CLAIM_PATH.read_bytes()).hexdigest()
    try:
        rev = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        status = subprocess.run(
            ["git", "status", "--porcelain", "--", "scripts/claim_alerts.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return {"claim_alerts_sha256": digest}
    if rev.returncode != 0 or status.stdout.strip():
        return {"claim_alerts_sha256": digest}
    return {"git": rev.stdout.strip()}


def level_rows(spec: dict) -> list[dict]:
    rows = []
    for level in spec.get("levels") or []:
        if not level.get("ticker"):
            raise BenchError("a level has no ticker")
        if level.get("price") is None:
            raise BenchError(f"{level['ticker']} has no numbered price")
        row = {
            "ticker": level["ticker"],
            "price": float(level["price"]),
            "allows": claim._allows(level),
            "targets": [float(price) for price in (level.get("targets") or [])],
            "chart": level.get("chart"),
        }
        if level.get("up_targets"):
            row["up_targets"] = [float(price) for price in level["up_targets"]]
        if level.get("stop") is not None:
            row["stop"] = float(level["stop"])
        rows.append(row)
    return rows


def _ohlc(bar: dict) -> dict:
    return {
        "close_at": _parse_time(bar["close_at"]),
        "o": float(bar["o"]),
        "h": float(bar["h"]),
        "l": float(bar["l"]),
        "c": float(bar["c"]),
    }


def bar_book(payload: dict, tickers: list[str], as_of: int) -> dict[str, list[dict]]:
    source = payload.get("tickers") if isinstance(payload.get("tickers"), dict) else payload
    book = {}
    for ticker in tickers:
        rows = []
        for bar in source.get(ticker) or []:
            frozen = _ohlc(bar)
            if frozen["close_at"] <= as_of:
                rows.append(frozen)
        book[ticker] = rows
    return book


def prepare(levels_path: Path, bars_path: Path, as_of: int) -> dict:
    spec = claim.load_levels(levels_path)
    rows = level_rows(spec)
    tickers = []
    for row in rows:
        if row["ticker"] not in tickers:
            tickers.append(row["ticker"])
    bars = bar_book(_read(bars_path), tickers, as_of)
    grouped = {ticker: [] for ticker in tickers}
    for row in rows:
        grouped[row["ticker"]].append(row)
    return {
        "armed_at": spec["armed_at"],
        "armed_stamp": spec["armed_at"].isoformat(),
        "as_of": as_of,
        "as_of_stamp": datetime.fromtimestamp(as_of, claim.PT).isoformat(),
        "tickers": tickers,
        "rows": rows,
        "grouped": grouped,
        "bars": bars,
    }


def _with_indicators(bars: list[dict]) -> list[dict]:
    copied = [dict(bar) for bar in bars]
    return claim.add_indicators(copied)


def decide(prepared: dict, settings: dict) -> list[dict]:
    events = []
    armed_at = int(prepared["armed_at"].timestamp())
    for ticker in prepared["tickers"]:
        bars = _with_indicators(prepared["bars"][ticker])
        events.extend(
            claim.replay(bars, prepared["grouped"][ticker], armed_at, settings)
        )
    return [_public(event) for event in events]


def _public(event: dict) -> dict:
    return {
        "ticker": event["ticker"],
        "side": event["side"],
        "level": event["level"],
        "kind": event["kind"],
        "reason": event["reason"],
        "bar_time": _stamp(event["close_at"]),
        "fill": event["fill"],
    }


def execute(prepared: dict, settings: dict, decide_fn=None) -> list[dict]:
    """Replay twice. A difference is a bench bug, and nothing is published."""
    runner = decide_fn or decide
    try:
        first = runner(prepared, settings)
        second = runner(prepared, settings)
    except ValueError as exc:
        raise BenchError(str(exc)) from exc
    if first != second:
        raise BenchError("repeat differed")
    return first


def settings_snapshot(resolved: dict) -> dict:
    snapshot = {}
    for name, spec in claim.VARIABLES.items():
        allowed = spec.get("allowed")
        snapshot[name] = {
            "value": resolved[name],
            "default": spec["default"],
            "type": spec["type"],
            "decision": spec["decision"],
            "allowed": list(allowed) if allowed else None,
        }
    return snapshot


def score_contracts(events: list[dict], records: list[dict] | None) -> list[dict]:
    """Score a recorded contract. Never invent a debit."""
    by_fill = {}
    for record in records or []:
        by_fill[(record.get("ticker"), record.get("bar_time"))] = record
    scored = []
    for event in events:
        if event["kind"] != "entry":
            continue
        base = {"ticker": event["ticker"], "bar_time": event["bar_time"]}
        record = by_fill.get((event["ticker"], event["bar_time"]))
        if record is None:
            scored.append({**base, "status": "not recorded"})
            continue
        missing = [
            field
            for field in ("strike", "expiration", "debit")
            if record.get(field) in (None, "")
        ]
        if missing:
            scored.append({**base, "status": "not recorded"})
            continue
        debit = float(record["debit"])
        if debit > 100:
            scored.append({**base, "status": "not scored", "reason": "debit over 100"})
            continue
        if record.get("otm") and not record.get("theta_room"):
            scored.append(
                {**base, "status": "not scored", "reason": "otm without room to gain"}
            )
            continue
        scored.append(
            {
                **base,
                "status": "scored",
                "strike": record["strike"],
                "expiration": record["expiration"],
                "debit": debit,
                "otm": bool(record.get("otm")),
            }
        )
    return scored


def _payload(prepared: dict, settings: dict, events: list[dict], contracts: list[dict]) -> dict:
    return {
        "levels": {"armed_at": prepared["armed_stamp"], "levels": prepared["rows"]},
        "bars": {
            "as_of": prepared["as_of_stamp"],
            "tickers": prepared["bars"],
        },
        "settings": settings_snapshot(settings),
        "code": code_identity(),
        "events": {"tickers": prepared["tickers"], "events": events},
        "contracts": contracts,
    }


def write_run(out: Path, payload: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name in ("levels", "bars", "settings", "code", "events", "contracts"):
        _write(out / f"{name}.json", payload[name])


def run(
    levels_path: Path,
    bars_path: Path,
    as_of,
    out: Path,
    settings_path: Path | None = None,
    contracts_path: Path | None = None,
    decide_fn=None,
) -> dict:
    overrides = _read(settings_path) if settings_path else {}
    try:
        settings = claim.resolve_settings(overrides)
    except ValueError as exc:
        raise BenchError(str(exc)) from exc
    prepared = prepare(levels_path, bars_path, _parse_time(as_of))
    events = execute(prepared, settings, decide_fn)
    records = None
    if contracts_path:
        loaded = _read(contracts_path)
        records = loaded.get("contracts") if "contracts" in loaded else loaded.get("entries")
        if not isinstance(records, list):
            raise BenchError("contracts must be a list")
    payload = _payload(prepared, settings, events, score_contracts(events, records))
    write_run(out, payload)
    return payload


def difference(default: list[dict], variant: list[dict]) -> dict:
    def entry_key(event):
        return (event["ticker"], event["side"], event["level"], event["bar_time"])

    def exit_key(event):
        return (event["ticker"], event["side"], event["level"])

    def skip_key(event):
        return (
            event["ticker"],
            event["side"],
            event["level"],
            event["reason"],
            event["bar_time"],
        )

    default_entries = {entry_key(event): event for event in default if event["kind"] == "entry"}
    variant_entries = {entry_key(event): event for event in variant if event["kind"] == "entry"}
    default_exits = {exit_key(event): event for event in default if event["kind"] == "exit"}
    variant_exits = {exit_key(event): event for event in variant if event["kind"] == "exit"}
    default_skips = {skip_key(event) for event in default if event["kind"] == "skip"}
    moved = []
    for key, event in variant_exits.items():
        prior = default_exits.get(key)
        if prior and (
            prior["bar_time"] != event["bar_time"] or prior["reason"] != event["reason"]
        ):
            moved.append({"from": prior, "to": event})
    return {
        "entries_added": [variant_entries[key] for key in variant_entries if key not in default_entries],
        "entries_removed": [default_entries[key] for key in default_entries if key not in variant_entries],
        "exits_moved": moved,
        "skips_appeared": [
            event
            for event in variant
            if event["kind"] == "skip" and skip_key(event) not in default_skips
        ],
    }


def _experiment_text(record: dict) -> str:
    diff = record["difference"]
    lines = [
        f"# {record['question']}",
        "",
        f"- variable: {record['variable']}",
        f"- default: {record['default_value']}",
        f"- variant: {record['variant_value']}",
        f"- day: {record['day']}",
        "",
        "## Default",
        "",
        _event_lines(record["default_events"]),
        "",
        "## Variant",
        "",
        _event_lines(record["variant_events"]),
        "",
        "## Difference",
        "",
    ]
    if not any(diff.values()):
        lines.append("No difference.")
    else:
        lines.append(f"- entries added: {len(diff['entries_added'])}")
        lines.append(f"- entries removed: {len(diff['entries_removed'])}")
        lines.append(f"- exits moved: {len(diff['exits_moved'])}")
        lines.append(f"- skips appeared: {len(diff['skips_appeared'])}")
    lines.append("")
    return "\n".join(lines)


def _event_lines(events: list[dict]) -> str:
    if not events:
        return "No events."
    return "\n".join(
        f"- {event['ticker']} {event['side']} {event['kind']} {event['level']} "
        f"{event['reason']} at {event['bar_time']}"
        for event in events
    )


def compare(
    levels_path: Path,
    bars_path: Path,
    as_of,
    variable: str,
    value,
    question: str,
    day: str,
    out: Path,
    decide_fn=None,
) -> dict:
    if day not in ("discovery", "confirmation"):
        raise BenchError("day must be discovery or confirmation")
    if not str(question).strip():
        raise BenchError("the question is required")
    if variable not in claim.VARIABLES:
        raise BenchError(f"unknown variable: {variable}")
    try:
        variant_settings = claim.resolve_settings({variable: value})
    except ValueError as exc:
        raise BenchError(str(exc)) from exc
    default_settings = claim.live_settings()
    prepared = prepare(levels_path, bars_path, _parse_time(as_of))
    default_events = execute(prepared, default_settings, decide_fn)
    variant_events = execute(prepared, variant_settings, decide_fn)
    record = {
        "question": question.strip(),
        "variable": variable,
        "default_value": default_settings[variable],
        "variant_value": variant_settings[variable],
        "day": day,
        "default_events": default_events,
        "variant_events": variant_events,
        "difference": difference(default_events, variant_events),
    }
    write_run(
        out / "default",
        _payload(prepared, default_settings, default_events, score_contracts(default_events, None)),
    )
    write_run(
        out / "variant",
        _payload(prepared, variant_settings, variant_events, score_contracts(variant_events, None)),
    )
    _write(out / "experiment.json", record)
    (out / "experiment.md").write_text(_experiment_text(record))
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay one frozen day")
    commands = parser.add_subparsers(dest="command", required=True)
    run_cmd = commands.add_parser("run")
    run_cmd.add_argument("--levels", required=True, type=Path)
    run_cmd.add_argument("--bars", required=True, type=Path)
    run_cmd.add_argument("--as-of", required=True)
    run_cmd.add_argument("--settings", type=Path)
    run_cmd.add_argument("--contracts", type=Path)
    run_cmd.add_argument("--out", required=True, type=Path)
    compare_cmd = commands.add_parser("compare")
    compare_cmd.add_argument("--levels", required=True, type=Path)
    compare_cmd.add_argument("--bars", required=True, type=Path)
    compare_cmd.add_argument("--as-of", required=True)
    compare_cmd.add_argument("--variable", required=True)
    compare_cmd.add_argument("--value", required=True)
    compare_cmd.add_argument("--question", required=True)
    compare_cmd.add_argument("--day", required=True, choices=("discovery", "confirmation"))
    compare_cmd.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "run":
            payload = run(
                args.levels,
                args.bars,
                args.as_of,
                args.out,
                args.settings,
                args.contracts,
            )
            print(f"{len(payload['events']['events'])} events")
            return
        record = compare(
            args.levels,
            args.bars,
            args.as_of,
            args.variable,
            args.value,
            args.question,
            args.day,
            args.out,
        )
    except BenchError as exc:
        raise SystemExit(str(exc)) from exc
    diff = record["difference"]
    if not any(diff.values()):
        print("No difference.")
        return
    print(
        f"entries added {len(diff['entries_added'])}, "
        f"removed {len(diff['entries_removed'])}, "
        f"exits moved {len(diff['exits_moved'])}, "
        f"skips appeared {len(diff['skips_appeared'])}"
    )


if __name__ == "__main__":
    main()
