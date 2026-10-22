#!/usr/bin/env python3
"""Pick buffer sizes for the daily recap. The last session is the forward test.

  python3 scripts/recap.py

Train on every saved session except the last. Score the train winner on that
last session against the buffers the checker is using. The write-up states
that day's profit with the new parameters, that day's profit with the old
parameters, and the difference. Entry stays the retest. Near a level is
reported and not applied. A pass writes alerts/parameters.yaml. A miss
leaves the buffers already in force. Nothing here places an order.
"""

from __future__ import annotations

import itertools
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import claim_alerts as claim  # noqa: E402
import dashboard  # noqa: E402
import desk  # noqa: E402

SEARCH_PATH = ROOT / "learning" / "parameter_search.md"
STEPS = 10
MIN_TRAIN = 4
MIN_FORWARD = 2
LIVE = claim.ADOPTED_BUFFERS
RANGES = {
    "touch": (0.0, 0.50),
    "sma_band": (0.0, 2.0),
    "chase": (0.0, 1.50),
    "break_atr": (0.0, 1.50),
    "profit_near": (0.0, 0.50),
}


def old_buffers() -> dict:
    """The four buffer sizes the checker is using before this search."""
    current = claim.checker_settings()
    return {name: float(current[name]) for name in LIVE}


def code_buffers() -> dict:
    return {
        "touch": float(claim.VARIABLES["touch"]["default"]),
        "sma_band": float(claim.VARIABLES["sma_band"]["default"]),
        "chase": float(claim.VARIABLES["chase"]["default"]),
        "break_atr": float(claim.VARIABLES["break_atr"]["default"]),
        "profit_near": 0.15,
    }


def settings_from(combo: dict) -> dict:
    base = code_buffers()
    base.update(combo)
    return desk._settings(
        base["touch"],
        base["chase"],
        base["break_atr"],
        base["profit_near"],
        base["sma_band"],
        "retest",
        {"exit": "target"},
    )


def score(days: list[dict], settings: dict) -> dict:
    trades = []
    stitched: dict[str, list[dict]] = {}
    for day in days:
        result = desk.run_backtest(day["bars"], day["levels"], day["armed_at"], settings)
        trades.extend(result["trades"])
        for ticker, bars in day["bars"].items():
            stitched.setdefault(ticker, []).extend(bars)
    ordered = {
        ticker: sorted(bars, key=lambda bar: bar["close_at"])
        for ticker, bars in stitched.items()
    }
    stats = desk.performance(trades, ordered)["summary"]["strategy"]
    return {
        "net": stats["net"],
        "trades": stats["trades"],
        "profit_factor": stats["profit_factor"],
        "max_drawdown": stats["max_drawdown"],
        "win_rate": stats["win_rate"],
    }


def shortlist(points: list[dict], default: float, limit: int = 3) -> list[float]:
    """Up to three train values near the best net. The live value stays in the list."""
    default = round(float(default), 4)
    if not points:
        return [default]
    best = max(point["net"] for point in points)
    if all(point["net"] == best for point in points):
        return [default]
    band = max(0.5, abs(best) * 0.2)
    ranked = sorted(points, key=lambda point: (-point["net"], abs(point["value"] - default)))
    chosen: list[float] = []
    for point in ranked:
        if len(chosen) >= limit:
            break
        if point["value"] in chosen:
            continue
        if point["net"] < best - band and point["value"] != default:
            continue
        chosen.append(point["value"])
    if default not in chosen:
        if len(chosen) >= limit:
            chosen[-1] = default
        else:
            chosen.append(default)
    unique: list[float] = []
    for value in chosen:
        if value not in unique:
            unique.append(value)
    return unique


def _rank(row: dict) -> tuple:
    factor = row["train"]["profit_factor"]
    if factor is None:
        factor = 999.0 if row["train"]["net"] > 0 else 0.0
    draw = row["train"]["max_drawdown"] or 0.0
    return (row["train"]["net"], factor, -abs(draw))


def _same(combo: dict, defaults: dict) -> bool:
    return all(round(float(combo[name]), 4) == round(float(defaults[name]), 4) for name in LIVE)


def is_stable(winner: dict, rows: list[dict], defaults: dict) -> bool:
    """A peak with no neighbor in range is a spike. A one-cell grid may only keep the live buffers."""
    gap = max(1.0, abs(winner["train"]["net"]) * 0.5)
    neighbors = []
    for row in rows:
        diffs = [name for name in LIVE if row["combo"][name] != winner["combo"][name]]
        if len(diffs) == 1:
            neighbors.append(row)
    if not neighbors:
        return _same(winner["combo"], defaults)
    return any(row["train"]["net"] >= winner["train"]["net"] - gap for row in neighbors)


def edge_count(combo: dict, defaults: dict) -> int:
    count = 0
    for name in LIVE:
        low, high = RANGES[name]
        value = round(float(combo[name]), 4)
        if value != round(float(defaults[name]), 4) and (value == low or value == high):
            count += 1
    return count


def decide(
    combo: dict,
    defaults: dict,
    train: dict,
    forward: dict,
    baseline_forward: dict,
    stable: bool,
) -> tuple[bool, str]:
    if _same(combo, defaults):
        return False, "kept the live buffers"
    if train["trades"] < MIN_TRAIN:
        return False, "the train has fewer than 4 closes"
    if forward["trades"] < MIN_FORWARD:
        return False, "the forward day has fewer than 2 closes"
    if not stable:
        return False, "the train peak is a spike"
    if edge_count(combo, defaults) > 1:
        return False, "more than one buffer sits on a range edge"
    if forward["net"] <= baseline_forward["net"]:
        return False, "the forward day did not beat the live buffers"
    hole = (forward["max_drawdown"] or 0) < (baseline_forward["max_drawdown"] or 0) - 1
    paid = forward["net"] >= baseline_forward["net"] + 1
    if hole and not paid:
        return False, "the forward day buys the net with a deeper hole"
    return True, "the forward day beat the live buffers"


def _sweep(train: list[dict], name: str, default: float) -> dict:
    low, high = RANGES[name]
    points = []
    for value in dashboard._range_steps(low, high, STEPS):
        stats = score(train, settings_from({name: value}))
        points.append({"value": value, **stats})
    return {
        "low": low,
        "high": high,
        "points": points,
        "candidates": shortlist(points, default),
    }


def search(days: list[dict]) -> dict:
    if len(days) < 2:
        raise ValueError("a forward test needs an earlier session and a last session")
    train = days[:-1]
    forward = days[-1]
    defaults = code_buffers()
    previous = old_buffers()
    sweeps = {name: _sweep(train, name, defaults[name]) for name in (*LIVE, "profit_near")}
    scored = []
    grids = [sweeps[name]["candidates"] for name in LIVE]
    for values in itertools.product(*grids):
        combo = {name: value for name, value in zip(LIVE, values)}
        scored.append({"combo": combo, "train": score(train, settings_from(combo))})
    winner = max(scored, key=_rank)
    winner_settings = settings_from(winner["combo"])
    previous_settings = settings_from(previous)
    forward_stats = score([forward], winner_settings)
    baseline_forward = score([forward], previous_settings)
    folds = []
    for day in days:
        winner_day = score([day], winner_settings)
        previous_day = score([day], previous_settings)
        folds.append(
            {
                "day": day["day"],
                "role": "forward" if day is forward else "train",
                "winner": winner_day,
                "baseline": previous_day,
                "difference": _gap(winner_day["net"], previous_day["net"]),
            }
        )
    stable = is_stable(winner, scored, defaults)
    apply, reason = decide(
        winner["combo"],
        defaults,
        winner["train"],
        forward_stats,
        baseline_forward,
        stable,
    )
    return {
        "train_days": [day["day"] for day in train],
        "forward_day": forward["day"],
        "defaults": {name: defaults[name] for name in LIVE},
        "sweeps": sweeps,
        "winner": winner["combo"],
        "train": winner["train"],
        "old": previous,
        "forward": forward_stats,
        "baseline_forward": baseline_forward,
        "forward_difference": _gap(forward_stats["net"], baseline_forward["net"]),
        "folds": folds,
        "apply": apply,
        "reason": reason,
    }


def _num(value: float) -> str:
    return f"{float(value):.4f}".rstrip("0").rstrip(".")


def _closes(count: int) -> str:
    return "1 close" if count == 1 else f"{count} closes"


def _gap(new: float, old: float) -> float:
    """Difference of the stock-point profits as the recap prints them."""
    return round(float(new), 2) - round(float(old), 2)


def _points(value: float) -> str:
    rounded = round(float(value), 2)
    text = f"{abs(rounded):.2f}"
    if rounded > 0:
        return f"+{text}"
    if rounded < 0:
        return f"-{text}"
    return "0.00"


def _best(points: list[dict]) -> dict:
    return max(points, key=lambda point: point["net"])


def render(result: dict) -> str:
    lines = [
        "# Parameter search",
        "",
        "Generated by `python3 scripts/recap.py`. Paste this into the day's Backtest section. "
        "This is not a pattern and it does not place an order.",
        "",
        "## Backtest",
        "",
        "Train sessions: " + ", ".join(result["train_days"]) + ". "
        f"Forward session: {result['forward_day']}. "
        "Entry stays the retest. The exit stays a close through the far target. "
        "Near a level is scored and not applied.",
        "",
        "| Buffer | Low | High | Train best | Train net | Values kept |",
        "|--------|-----|------|------------|-----------|-------------|",
    ]
    labels = {
        "touch": "Wick touch",
        "sma_band": "SMA band",
        "chase": "Chase",
        "break_atr": "ATR fraction",
        "profit_near": "Near a level",
    }
    for name in (*LIVE, "profit_near"):
        sweep = result["sweeps"][name]
        best = _best(sweep["points"])
        flat = all(point["net"] == best["net"] for point in sweep["points"])
        kept = ", ".join(_num(value) for value in sweep["candidates"])
        lines.append(
            f"| {labels[name]} | {_num(sweep['low'])} | {_num(sweep['high'])} | "
            f"{'flat' if flat else _num(best['value'])} | {_points(best['net'])} | {kept} |"
        )
    winner = result["winner"]
    lines.extend(
        [
            "",
            "Train winner: "
            + ", ".join(f"{labels[name]} {_num(winner[name])}" for name in LIVE)
            + f". Train net {_points(result['train']['net'])} on {_closes(result['train']['trades'])}.",
            "",
            "Old parameters: "
            + ", ".join(f"{labels[name]} {_num(result['old'][name])}" for name in LIVE)
            + ".",
            "",
            f"On {result['forward_day']}, new parameters made {_points(result['forward']['net'])} "
            f"on {_closes(result['forward']['trades'])}. "
            f"Old parameters made {_points(result['baseline_forward']['net'])} "
            f"on {_closes(result['baseline_forward']['trades'])}. "
            f"Difference {_points(result['forward_difference'])} stock points.",
            "",
            "| Session | Role | New parameters | Old parameters | Difference |",
            "|---------|------|----------------|----------------|------------|",
        ]
    )
    for fold in result["folds"]:
        lines.append(
            f"| {fold['day']} | {fold['role']} | "
            f"{_points(fold['winner']['net'])} on {_closes(fold['winner']['trades'])} | "
            f"{_points(fold['baseline']['net'])} on {_closes(fold['baseline']['trades'])} | "
            f"{_points(fold['difference'])} |"
        )
    lines.extend(
        [
            "",
            ("Applied. The next check uses these buffer sizes. " if result["apply"] else "Not applied. ")
            + result["reason"][:1].upper()
            + result["reason"][1:]
            + ". Entry stays the retest.",
            "",
        ]
    )
    return "\n".join(lines)


def parameters_document(result: dict) -> str:
    adopted = {name: result["winner"][name] for name in LIVE}
    body = {
        "apply": bool(result["apply"]),
        "reason": result["reason"],
        "forward_day": result["forward_day"],
        "train_days": result["train_days"],
        "adopted": adopted,
        "train_net": round(float(result["train"]["net"]), 4),
        "train_trades": result["train"]["trades"],
        "forward_net": round(float(result["forward"]["net"]), 4),
        "forward_trades": result["forward"]["trades"],
        "baseline_forward_net": round(float(result["baseline_forward"]["net"]), 4),
        "forward_difference": round(float(result["forward_difference"]), 4),
    }
    import yaml

    dumped = yaml.safe_dump(body, sort_keys=False)
    return (
        "# Buffer sizes from scripts/recap.py.\n"
        "# The checker reads apply and the four buffers. Entry in this file is ignored.\n"
        "# This file does not place an order.\n"
        + dumped
    )


def write(result: dict, search_path: Path = SEARCH_PATH, parameters_path: Path = claim.PARAMETERS_PATH) -> None:
    search_path.parent.mkdir(parents=True, exist_ok=True)
    search_path.write_text(render(result))
    parameters_path.parent.mkdir(parents=True, exist_ok=True)
    parameters_path.write_text(parameters_document(result))


def main() -> None:
    days = dashboard._saved_days(ROOT)
    result = search(days)
    write(result)
    print(render(result))


if __name__ == "__main__":
    main()
