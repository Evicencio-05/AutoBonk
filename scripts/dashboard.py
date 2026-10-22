#!/usr/bin/env python3
"""The AutoBonk desk. The page reads the repo. The server scores exits from bars.

  python3 scripts/dashboard.py
  python3 scripts/dashboard.py serve

Nothing here places an order. A backtest does not rewrite the paper tape.
"""

from __future__ import annotations

import html
import json
import sys
import urllib.error
from datetime import datetime
from pathlib import Path

import yaml

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import desk  # noqa: E402
import claim_alerts  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dashboard" / "index.html"


def render(root: Path) -> str:
    return _page(
        [
            ("Backtest", _studio(root), "backtest"),
            ("Paper", _paper(root), "trades"),
            ("Contracts", _contracts(root), "contracts"),
            ("Live book", _live_book(root), "book"),
            ("Lessons", _lessons(root), "lessons"),
            ("Rules", _rules(root), "rules"),
            ("Journal", _journal(root), "journal"),
            ("Training", _training(root), "training"),
            ("Fade", _fade(root), "fade"),
            ("Alerts", _alerts(root), "alerts"),
            ("Bench", _bench(root), "bench"),
            ("Archives", _archives(root), "archives"),
        ]
    )


def _read(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text()


def _esc(value) -> str:
    return html.escape("" if value is None else str(value))


def _dollars(amount: float | None) -> str:
    if amount is None:
        return ""
    rounded = round(amount, 2)
    if abs(rounded - round(rounded)) < 0.001:
        text = f"{abs(round(rounded)):.0f}"
    else:
        text = f"{abs(rounded):.2f}"
    if rounded > 0:
        return f"+${text}"
    if rounded < 0:
        return f"-${text}"
    return "$0"


def _premium(text: str) -> float | None:
    if text in ("", "none"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _paper_rows(text: str) -> tuple[list[dict], dict[str, dict]]:
    blotter, _, marks_text = text.partition("## Open marks")
    rows = []
    for cells in _table_rows(blotter):
        if cells[0] == "Time":
            continue
        padded = (cells + [""] * 9)[:9]
        rows.append(
            {
                "time": padded[0],
                "ticker": padded[1],
                "action": padded[2],
                "side": padded[3],
                "level": padded[4],
                "fill": padded[5],
                "reason": padded[6],
                "contract": padded[7],
                "premium": padded[8],
            }
        )
    marks = {}
    for cells in _table_rows(marks_text):
        if cells[0] == "Contract":
            continue
        padded = (cells + [""] * 4)[:4]
        marks[padded[0]] = {"premium": padded[1], "as_of": padded[2], "source": padded[3]}
    return rows, marks


def _paired_trades(rows: list[dict], marks: dict[str, dict]) -> list[dict]:
    open_entries = []
    trades = []
    for row in rows:
        if row["action"] == "entry":
            open_entries.append(row)
            continue
        match = None
        for index, entry in enumerate(open_entries):
            if (
                entry["ticker"] == row["ticker"]
                and entry["side"] == row["side"]
                and entry["level"] == row["level"]
            ):
                match = open_entries.pop(index)
                break
        if match is not None:
            trades.append({"entry": match, "exit": row, "mark": None})
    for entry in open_entries:
        mark = marks.get(f"{entry['ticker']} {entry['contract']}")
        trades.append({"entry": entry, "exit": None, "mark": mark})
    return trades


def _profit(trade: dict) -> float | None:
    entry = _premium(trade["entry"]["premium"])
    if trade["exit"] is not None:
        exit_premium = _premium(trade["exit"]["premium"])
    elif trade["mark"] is not None:
        exit_premium = _premium(trade["mark"]["premium"])
    else:
        exit_premium = None
    if entry is None or exit_premium is None:
        return None
    return (exit_premium - entry) * 100


def _paper(root: Path) -> str:
    text = _read(root / "alerts" / "paper.md")
    rows, marks = _paper_rows(text)
    notes = [
        "<p>A paper row is not an order and is not a journal trade. "
        "Profit is one contract, the premium change times 100.</p>"
    ]
    for line in text.split("## Open marks", 1)[0].splitlines():
        if line.startswith("- "):
            notes.append(f"<p>{_esc(line[2:].strip())}</p>")
    if not rows:
        return "<p>No paper trades yet.</p>" + "".join(notes)
    trades = _paired_trades(rows, marks)
    trade_rows = []
    total = 0.0
    counted = 0
    for trade in trades:
        entry = trade["entry"]
        profit = _profit(trade)
        if profit is not None:
            total += profit
            counted += 1
        if trade["exit"] is not None:
            exit_text = trade["exit"]["premium"]
        elif trade["mark"] is not None:
            exit_text = f"{trade['mark']['premium']} mark"
        else:
            exit_text = "open"
        side = entry["side"]
        side_class = " call" if side == "call" else " put" if side == "put" else ""
        profit_class = ""
        if profit is not None and profit > 0:
            profit_class = " up"
        elif profit is not None and profit < 0:
            profit_class = " down"
        trade_rows.append(
            "<tr>"
            f"<td class='num'>{_esc(entry['time'])}</td>"
            f"<td class='ticker'>{_esc(entry['ticker'])}</td>"
            f"<td class='side{side_class}'>{_esc(side)}</td>"
            f"<td class='num'>{_esc(entry['level'])}</td>"
            f"<td>{_esc(entry['contract'])}</td>"
            f"<td class='num'>{_esc(entry['premium'])}</td>"
            f"<td class='num'>{_esc(exit_text)}</td>"
            f"<td class='num{profit_class}'>{_esc(_dollars(profit))}</td>"
            "</tr>"
        )
    total_class = " up" if total > 0 else " down" if total < 0 else ""
    total_text = _dollars(total) if counted else ""
    blotter = []
    for row in rows:
        side = row["side"]
        side_class = " call" if side == "call" else " put" if side == "put" else ""
        blotter.append(
            "<tr>"
            f"<td class='num'>{_esc(row['time'])}</td>"
            f"<td class='ticker'>{_esc(row['ticker'])}</td>"
            f"<td>{_esc(row['action'])}</td>"
            f"<td class='side{side_class}'>{_esc(side)}</td>"
            f"<td class='num'>{_esc(row['level'])}</td>"
            f"<td class='num'>{_esc(row['fill'])}</td>"
            f"<td>{_esc(row['reason'])}</td>"
            f"<td>{_esc(row['contract'])}</td>"
            f"<td class='num'>{_esc(row['premium'])}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>Time</th><th>Ticker</th><th>Side</th><th>Level</th>"
        "<th>Contract</th><th>Paid</th><th>Exit</th><th>Profit</th>"
        f"</tr></thead><tbody>{''.join(trade_rows)}"
        f"<tr data-stay><td colspan='7'>Day</td><td class='num{total_class}'>{_esc(total_text)}</td></tr>"
        "</tbody></table>"
        + _tape_books(trades)
        + "".join(notes)
        + _context(root)
        + "<table><thead><tr>"
        "<th>Time</th><th>Ticker</th><th>Action</th><th>Side</th>"
        "<th>Level</th><th>Fill</th><th>Reason</th><th>Contract</th><th>Premium</th>"
        f"</tr></thead><tbody>{''.join(blotter)}</tbody></table>"
    )


def _contracts(root: Path) -> str:
    text = _read(root / "alerts" / "contracts.md")
    note = (
        "<p>The chosen row is the contract the checker would take. "
        "Same-day expiration is eligible until noon Pacific. "
        "A 0DTE strike past the halfway point between the stock and the far target is not taken. "
        "The strike is the closest one at or under $1 that the far target can still reach. "
        "The other rows use that same fill. Return is the percent change in the premium. "
        "Nothing here is an order.</p>"
    )
    body = []
    for cells in _table_rows(text):
        if cells[0] == "Time":
            continue
        padded = (cells + [""] * 9)[:9]
        returned = padded[7]
        tone = " up" if returned.startswith("+") else " down" if returned.startswith("-") else ""
        body.append(
            "<tr>"
            f"<td class='num'>{_esc(padded[0])}</td>"
            f"<td class='ticker'>{_esc(padded[1])}</td>"
            f"<td class='num'>{_esc(padded[2])}</td>"
            f"<td>{_esc(padded[3])}</td>"
            f"<td>{_esc(padded[4])}</td>"
            f"<td class='num'>{_esc(padded[5])}</td>"
            f"<td class='num'>{_esc(padded[6])}</td>"
            f"<td class='num{tone}'>{_esc(returned)}</td>"
            f"<td>{_esc(padded[8])}</td>"
            "</tr>"
        )
    if not body:
        return note + "<p>No contract comparison yet.</p>"
    return (
        note
        + "<table><thead><tr>"
        "<th>Time</th><th>Ticker</th><th>Level</th><th>Role</th><th>Contract</th>"
        "<th>Entry</th><th>Price</th><th>Return</th><th>State</th>"
        f"</tr></thead><tbody>{''.join(body)}</tbody></table>"
    )


def _live_book(root: Path) -> str:
    path = root / "alerts" / "levels.yaml"
    if not path.is_file():
        return "<p>No live book.</p>"
    data = yaml.safe_load(path.read_text()) or {}
    rows = []
    for level in data.get("levels") or []:
        targets = [str(price) for price in (level.get("targets") or [])]
        if level.get("up_targets"):
            ups = ", ".join(str(price) for price in level["up_targets"])
            targets.append(f"up {ups}")
        stop = level.get("stop")
        rows.append(
            "<tr>"
            f"<td class='ticker'>{_esc(level.get('ticker'))}</td>"
            f"<td>{_esc(level.get('price'))}</td>"
            f"<td>{_esc(level.get('allows'))}</td>"
            f"<td>{_esc(', '.join(targets))}</td>"
            f"<td>{_esc('' if stop is None else stop)}</td>"
            f"<td>{_esc(level.get('note') or '')}</td>"
            "</tr>"
        )
    body = "".join(rows) or "<tr><td colspan='6'>No levels.</td></tr>"
    return (
        f"<p>Armed {_esc(data.get('armed_at'))}. "
        "charts/inbox is not the live book.</p>"
        "<table><thead><tr>"
        "<th>Ticker</th><th>Price</th><th>Allows</th>"
        "<th>Targets</th><th>Stop</th><th>Note</th>"
        f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _alerts(root: Path) -> str:
    text = _read(root / "alerts" / "log.md")
    lines = [
        line[2:].strip()
        for line in text.splitlines()
        if line.startswith("- ")
    ]
    if not lines:
        return "<p>No alerts. An alert is not an order.</p>"
    items = "".join(f"<li>{_esc(line)}</li>" for line in lines)
    return f"<p>An alert is not an order.</p><ul>{items}</ul>"


def _table_rows(text: str) -> list[list[str]]:
    rows = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or cells[0] in ("Date", "") or set(cells[0]) <= {"-"}:
            continue
        rows.append(cells)
    return rows


def _journal(root: Path) -> str:
    text = _read(root / "learning" / "journal.md")
    if not text:
        return "<p>No journal.</p><p class='patterns'>Patterns: none.</p>"
    observations, _, rest = text.partition("## Patterns")
    rows = []
    for cells in _table_rows(observations):
        padded = (cells + [""] * 5)[:5]
        rows.append(
            "<tr>"
            + "".join(
                f"<td class='ticker'>{_esc(cell)}</td>" if index == 1 else f"<td>{_esc(cell)}</td>"
                for index, cell in enumerate(padded)
            )
            + "</tr>"
        )
    body = "".join(rows) or "<tr><td colspan='5'>No observations.</td></tr>"
    patterns = rest.strip() or "none"
    return (
        "<table><thead><tr>"
        "<th>Date</th><th>Ticker</th><th>Posted setup</th><th>Trade</th><th>Result</th>"
        f"</tr></thead><tbody>{body}</tbody></table>"
        f"<h3>Patterns</h3><p class='patterns'>{_esc(patterns)}</p>"
    )


def _training(root: Path) -> str:
    drills_path = root / "learning" / "drills.yaml"
    if not drills_path.is_file():
        return "<p>No drill. This section is not a live alert.</p>"
    data = yaml.safe_load(drills_path.read_text()) or {}
    drills = data.get("drills") or []
    if not drills:
        return "<p>No drill. This section is not a live alert.</p>"
    training = _read(root / "learning" / "training.md")
    notes = [
        line[2:].strip()
        for line in training.splitlines()
        if line.startswith("- ")
        and any(
            label in line
            for label in (
                "Confirmed buy",
                "Confirmed sell",
                "Buy miss",
                "Sell miss",
                "Contract bottom",
                "versus the bottom",
            )
        )
    ]
    blocks = []
    goal = _first_goal(root)
    if goal:
        blocks.append(
            f"<p><b>{_esc(goal.get('title'))}</b> {_esc(' '.join(str(goal.get('says') or '').split()))}</p>"
        )
    blocks.append("<p>One observation. Not a live alert.</p>")
    for drill in drills:
        blocks.append(
            "<table><thead><tr>"
            "<th>Ticker</th><th>Session</th><th>Side</th><th>Level</th>"
            "<th>Confirmed buy</th><th>Confirmed sell</th>"
            "</tr></thead><tbody><tr>"
            f"<td class='ticker'>{_esc(drill.get('ticker'))}</td>"
            f"<td>{_esc(drill.get('session'))}</td>"
            f"<td>{_esc(drill.get('side'))}</td>"
            f"<td>{_esc(drill.get('level'))}</td>"
            f"<td>{_esc(drill.get('ideal_buy'))}</td>"
            f"<td>{_esc(drill.get('ideal_sell'))}</td>"
            "</tr></tbody></table>"
        )
    if notes:
        blocks.append("<ul>" + "".join(f"<li>{_esc(note)}</li>" for note in notes) + "</ul>")
    return "".join(blocks)


def _changed(difference: dict) -> bool:
    return any(
        difference.get(key)
        for key in ("entries_added", "entries_removed", "exits_moved", "skips_appeared")
    )


def _bench(root: Path) -> str:
    experiments = root / "bench" / "experiments"
    runs = root / "bench" / "runs"
    if not experiments.is_dir() and not runs.is_dir():
        return "<p>No experiments.</p>"
    records = sorted(experiments.glob("**/experiment.json")) if experiments.is_dir() else []
    if not records:
        return "<p>No experiments.</p>"
    rows = []
    for path in records:
        record = json.loads(path.read_text())
        changed = "yes" if _changed(record.get("difference") or {}) else "no"
        rows.append(
            "<tr>"
            f"<td>{_esc(record.get('question'))}</td>"
            f"<td>{_esc(record.get('variable'))}</td>"
            f"<td>{_esc(record.get('day'))}</td>"
            f"<td>{changed}</td>"
            "</tr>"
        )
    body = "".join(rows)
    return (
        "<table><thead><tr>"
        "<th>Question</th><th>Variable</th><th>Day</th><th>Events changed</th>"
        f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _archives(root: Path) -> str:
    text = _read(root / "charts" / "pm_levels_index.md")
    if not text:
        return "<p>No archives.</p>"
    rows = []
    section = ""
    for line in text.splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        if not line.startswith("|") or not section:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3 or cells[0] in ("Ticker", "") or set(cells[0]) <= {"-"}:
            continue
        ticker, last, file_name = cells[0], cells[1], cells[2].strip("`")
        href = "../charts/" + file_name
        rows.append(
            "<tr>"
            f"<td class='ticker'>{_esc(ticker)}</td>"
            f"<td>{_esc(section)}</td>"
            f"<td>{_esc(last)}</td>"
            f"<td><a href='{_esc(href)}'>{_esc(file_name)}</a></td>"
            "</tr>"
        )
    body = "".join(rows) or "<tr><td colspan='4'>No archives.</td></tr>"
    return (
        "<p>Dated packs are archives.</p>"
        "<table><thead><tr>"
        "<th>Ticker</th><th>Pack</th><th>Last</th><th>File</th>"
        f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _factor_text(values: list[float]) -> str:
    stats = desk.score_points(values)
    if stats["trades"] == 0:
        return "—"
    if stats["profit_factor"] is None:
        return "no losses" if stats["net"] > 0 else "0.00"
    return f"{stats['profit_factor']:.2f}"


def _tape_books(trades: list[dict]) -> str:
    """Profit factor of the tape, split by the $1 threshold. Computed from the rows."""
    fits_points = []
    paper_points = []
    fits_option = []
    paper_option = []
    missing = 0
    for trade in trades:
        entry = trade["entry"]
        premium = _premium(entry.get("premium"))
        book = desk.classify_contract(entry.get("contract"), premium, claim_alerts.CONTRACT_CAP)
        if book is None:
            missing += 1
            continue
        points = None
        if trade["exit"] is not None:
            try:
                fill = float(entry["fill"])
                close = float(trade["exit"]["fill"])
            except (TypeError, ValueError):
                fill = None
            if fill is not None:
                points = (fill - close) if entry["side"] == "put" else (close - fill)
        option = _profit(trade)
        if book == "paper":
            if points is not None:
                paper_points.append(points)
            if option is not None:
                paper_option.append(option)
        else:
            if points is not None:
                fits_points.append(points)
            if option is not None:
                fits_option.append(option)
    return (
        "<p>A trade needs a contract. A premium over $1 is paper. "
        f"Fits stock profit factor {_factor_text(fits_points)}. "
        f"Fits option profit factor {_factor_text(fits_option)}. "
        f"Paper stock profit factor {_factor_text(paper_points)}. "
        f"Paper option profit factor {_factor_text(paper_option)}. "
        f"{missing} rows have no contract and are not in either factor. "
        "These factors are computed from the tape.</p>"
    )


def _context(root: Path) -> str:
    text = _read(root / "alerts" / "context.md")
    body = []
    for cells in _table_rows(text):
        if cells[0] == "Time":
            continue
        padded = (cells + [""] * 14)[:14]
        body.append("<tr>" + "".join(f"<td>{_esc(cell)}</td>" for cell in padded) + "</tr>")
    if not body:
        return ""
    return (
        "<h3>What went into each row</h3>"
        "<p>The signal candle on an entry, the exit candle on an exit. "
        "Purple is the 14 RSI. Yellow is its 14 SMA. "
        "The number after an average or a level is the close minus that price.</p>"
        "<table><thead><tr>"
        "<th>Time</th><th>Ticker</th><th>Action</th><th>Side</th><th>Level</th><th>Fill</th>"
        "<th>Candle</th><th>Purple</th><th>Yellow</th><th>SMA20</th><th>SMA50</th>"
        "<th>SMA200</th><th>Nearby</th><th>Volume</th>"
        f"</tr></thead><tbody>{''.join(body)}</tbody></table>"
    )


def _sheet(text: str, empty: str) -> str:
    body = text.strip()
    if not body:
        return f"<p>{_esc(empty)}</p>"
    return f"<pre class='sheet'>{_esc(body)}</pre>"


def _first_goal(root: Path) -> dict | None:
    path = root / "learning" / "goals.yaml"
    if not path.is_file():
        return None
    goals = (yaml.safe_load(path.read_text()) or {}).get("goals") or []
    return goals[0] if goals else None


def _lessons(root: Path) -> str:
    lessons_dir = root / "learning" / "lessons"
    lessons = sorted(lessons_dir.glob("*.md")) if lessons_dir.is_dir() else []
    reviews = sorted((root / "learning" / "reviews").glob("*.md")) if (root / "learning" / "reviews").is_dir() else []
    if not lessons and not reviews:
        goal = _first_goal(root)
        if goal is None:
            return "<p>No written lesson yet.</p>"
        return (
            f"<h3>{_esc(goal.get('title'))}</h3>"
            f"<p>{_esc(' '.join(str(goal.get('says') or '').split()))}</p>"
            "<p>This is the first goal. It is not a pattern and it is not an order.</p>"
        )
    blocks = []
    for path in lessons:
        blocks.append(_sheet(path.read_text(), ""))
    for path in reversed(reviews):
        blocks.append(f"<h3>{_esc(path.stem)}</h3>" + _sheet(path.read_text(), ""))
    return "".join(blocks)


def _rules(root: Path) -> str:
    return (
        "<p>The live checker still enters on a retest. A close has to clear a level by half "
        "the 14-period ATR. The other exits on the backtest desk are scores, not a new live rule.</p>"
        + _sheet(_read(root / "rules" / "ta_rules.md"), "No rules in this copy.")
    )


def _fade(root: Path) -> str:
    return _sheet(
        _read(root / "alerts" / "fade_forward.md"),
        "No fade record. The live checker stays on the retest.",
    )


def _level_inputs(level: dict) -> str:
    targets = ", ".join(str(price) for price in (level.get("targets") or []))
    ups = ", ".join(str(price) for price in (level.get("up_targets") or []))
    stop = "" if level.get("stop") is None else level.get("stop")
    allows = level.get("allows") or "long"
    options = "".join(
        f"<option value='{name}'{' selected' if name == allows else ''}>{name}</option>"
        for name in ("long", "short", "both")
    )
    return (
        "<tr>"
        f"<td><input name='ticker' value='{_esc(level.get('ticker') or '')}'></td>"
        f"<td><input name='price' value='{_esc(level.get('price') or '')}'></td>"
        f"<td><select name='allows'>{options}</select></td>"
        f"<td><input name='targets' value='{_esc(targets)}'></td>"
        f"<td><input name='up_targets' value='{_esc(ups)}'></td>"
        f"<td><input name='stop' value='{_esc(stop)}'></td>"
        f"<td><input name='note' value='{_esc(level.get('note') or '')}'></td>"
        "</tr>"
    )


def _premium_inputs(row: dict) -> str:
    side = row.get("side") or "call"
    options = "".join(
        f"<option value='{name}'{' selected' if name == side else ''}>{name}</option>"
        for name in ("call", "put")
    )
    return (
        "<tr>"
        f"<td><input name='ticker' value='{_esc(row.get('ticker') or '')}'></td>"
        f"<td><select name='side'>{options}</select></td>"
        f"<td><input name='level' value='{_esc(row.get('level') or '')}'></td>"
        f"<td><input name='contract' value='{_esc(row.get('contract') or '')}'></td>"
        f"<td><input name='entry' value='{_esc(row.get('entry') or '')}'></td>"
        f"<td><input name='exit' value='{_esc(row.get('exit') or '')}'></td>"
        "</tr>"
    )


def _known_premiums(root: Path) -> list[dict]:
    rows = []
    for cells in _table_rows(_read(root / "alerts" / "contracts.md")):
        if cells[0] == "Time" or len(cells) < 9 or cells[3] != "chosen":
            continue
        if cells[4] in ("", "none"):
            continue
        side = "call" if cells[4].endswith("C") else "put" if cells[4].endswith("P") else "call"
        exit_premium = cells[6] if cells[8] == "exit" else ""
        rows.append(
            {
                "ticker": cells[1],
                "side": side,
                "level": cells[2],
                "contract": cells[4],
                "entry": cells[5],
                "exit": exit_premium,
            }
        )
    return rows


def _studio(root: Path) -> str:
    path = root / "alerts" / "levels.yaml"
    data = yaml.safe_load(path.read_text()) if path.is_file() else {}
    data = data or {}
    armed = data.get("armed_at") or ""
    if hasattr(armed, "isoformat"):
        armed = armed.isoformat()
    levels = data.get("levels") or []
    level_rows = "".join(_level_inputs(level) for level in levels) or _level_inputs({})
    premium_rows = "".join(_premium_inputs(row) for row in _known_premiums(root)) or _premium_inputs({})
    payload = json.dumps({"armed_at": armed}).replace("<", "\\u003c")
    return f"""
<p>Change the levels, the buffers, the exit, and the contract premiums, then run the backtest.
Stock points, returns, and profit factor are computed from the 10-minute closes.
Option dollars use the premiums in the form, and they are not a quote at a new exit.
A premium over the threshold is paper. A row with no contract is left out of both factors.
This does not place an order and it does not rewrite the paper tape.</p>
<p class="knobs">
<label>Armed <input id="armed-at" value="{_esc(armed)}"></label>
<label>Touch <input id="touch" value="0.15"></label>
<label>Chase <input id="chase" value="0.50"></label>
<label>ATR fraction <input id="break-atr" value="0.5"></label>
<label>Near a level <input id="profit-near" value="0.15"></label>
<label>Premium threshold <input id="threshold" value="1"></label>
<label>Stop <select id="stop-mode"><option value="reclaim">reclaim</option><option value="named">named stop</option><option value="none">none</option></select></label>
<label>Take profit <select id="take-mode"><option value="target">close through the far target</option><option value="near">near the next level</option><option value="none">never</option></select></label>
<label>Clock <select id="flatten-mode"><option value="clock">12:50 PT</option><option value="none">do not flatten</option></select></label>
</p>
<table data-nosort><thead><tr><th>Ticker</th><th>Price</th><th>Allows</th><th>Targets</th><th>Up targets</th><th>Stop</th><th>Note</th></tr></thead>
<tbody id="level-rows">{level_rows}</tbody></table>
<p><button type="button" id="add-level">Add level</button></p>
<table data-nosort><thead><tr><th>Ticker</th><th>Side</th><th>Level</th><th>Contract</th><th>Entry premium</th><th>Exit premium</th></tr></thead>
<tbody id="premium-rows">{premium_rows}</tbody></table>
<p><button type="button" id="add-premium">Add contract</button>
<button type="button" id="run-backtest">Run backtest</button>
<button type="button" id="save-book">Save book</button></p>
<div id="backtest-out"><p>The four presets are Live, Never exit, Near the next level, and Named stop. Custom uses the menus above.</p></div>
<script id="desk-data" type="application/json">{payload}</script>
"""


def _parse_levels(rows: list[dict]) -> list[dict]:
    levels = []
    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker or row.get("price") in (None, ""):
            continue
        allows = row.get("allows") or "long"
        if allows not in ("long", "short", "both"):
            raise ValueError("allows must be long, short, or both")
        level = {
            "ticker": ticker,
            "price": float(row["price"]),
            "allows": allows,
            "targets": [float(price) for price in (row.get("targets") or [])],
            "note": row.get("note") or "",
        }
        if row.get("up_targets"):
            level["up_targets"] = [float(price) for price in row["up_targets"]]
        if row.get("stop") not in (None, ""):
            level["stop"] = float(row["stop"])
        levels.append(level)
    return levels


def _premium_map(rows: dict) -> dict:
    cleaned = {}
    for key, row in (rows or {}).items():
        if not isinstance(row, dict):
            continue
        entry = row.get("entry")
        exit_premium = row.get("exit")
        cleaned[key] = {
            "contract": row.get("contract") or "",
            "entry": None if entry in (None, "") else float(entry),
            "exit": None if exit_premium in (None, "") else float(exit_premium),
        }
    return cleaned


def _armed_stamp(text: str) -> int:
    if not text:
        return 0
    when = datetime.fromisoformat(str(text))
    if when.tzinfo is None:
        when = when.replace(tzinfo=claim_alerts.PT)
    return int(when.timestamp())


def _fetch_bars(tickers: list[str]) -> dict[str, list[dict]]:
    moment = int(datetime.now(claim_alerts.PT).timestamp())
    found = {}
    for ticker in tickers:
        raw = claim_alerts.fetch_five_minute(ticker, "1mo")
        bars = claim_alerts.add_indicators(claim_alerts.ten_minute_bars(raw, moment))
        found[ticker] = [bar for bar in bars if claim_alerts.in_session(bar["close_at"])]
    return found


def backtest_payload(payload: dict, bars_by_ticker: dict | None = None) -> dict:
    levels = _parse_levels(payload.get("levels") or [])
    if bars_by_ticker is None:
        bars_by_ticker = _fetch_bars(sorted({level["ticker"] for level in levels}))
    custom = payload.get("custom") or {}
    runs = desk.run_presets(
        bars_by_ticker,
        levels,
        _armed_stamp(payload.get("armed_at") or ""),
        touch=float(payload.get("touch", 0.15)),
        chase=float(payload.get("chase", 0.50)),
        break_atr=float(payload.get("break_atr", 0.5)),
        profit_near=float(payload.get("profit_near", 0.15)),
        threshold=float(payload.get("threshold", 1)),
        premiums=_premium_map(payload.get("premiums") or {}),
        custom={
            "stop_mode": custom.get("stop_mode") or "reclaim",
            "take": custom.get("take") or "target",
            "flatten": custom.get("flatten") or "clock",
        },
    )
    return {"runs": runs}


def save_book(root: Path, payload: dict) -> None:
    levels = _parse_levels(payload.get("levels") or [])
    armed = str(payload.get("armed_at") or "")
    path = root / "alerts" / "levels.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"armed_at": armed, "levels": levels}, sort_keys=False))


def _page(sections: list[tuple[str, str, str]]) -> str:

    body = "".join(
        f"<section id='{anchor}'><h2>{html.escape(title)}</h2>{part}</section>"
        for title, part, anchor in sections
    )
    by_anchor = {anchor: title for title, _part, anchor in sections}
    groups = (
        ("Trades", ("trades", "contracts")),
        ("Lessons", ("lessons", "journal", "training")),
        ("Rules", ("rules",)),
        ("Backtest", ("backtest",)),
        ("Rest", ("book", "fade", "alerts", "bench", "archives")),
    )
    used = {anchor for _label, anchors in groups for anchor in anchors}
    nav_groups = []
    for label, anchors in groups:
        links = "".join(
            f"<a href='#{anchor}'>{html.escape(by_anchor[anchor])}</a>"
            for anchor in anchors
            if anchor in by_anchor
        )
        if links:
            nav_groups.append(f"<div class='nav-group'><span>{html.escape(label)}</span>{links}</div>")
    leftover = "".join(
        f"<a href='#{anchor}'>{html.escape(title)}</a>"
        for title, _part, anchor in sections
        if anchor not in used
    )
    if leftover:
        nav_groups.append(f"<div class='nav-group'><span>Rest</span>{leftover}</div>")
    nav = "".join(nav_groups)
    template = Path(__file__).with_name("dashboard_page.html").read_text()
    return template.replace("__NAV__", nav).replace("__BODY__", body)


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, kind: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path.split("?", 1)[0] != "/":
                self.send_error(404)
                return
            self._send(200, "text/html; charset=utf-8", render(ROOT).encode())

        def do_POST(self) -> None:
            path = self.path.split("?", 1)[0]
            length = int(self.headers.get("Content-Length") or 0)
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
                if path == "/api/backtest":
                    result = backtest_payload(payload)
                elif path == "/api/book":
                    save_book(ROOT, payload)
                    result = {"saved": True}
                else:
                    self.send_error(404)
                    return
                status = 200
            except (ValueError, KeyError, TypeError, SystemExit, OSError, urllib.error.URLError) as exc:
                result = {"error": str(exc)}
                status = 400
            self._send(status, "application/json", json.dumps(result).encode())

        def log_message(self, fmt: str, *args) -> None:
            return

    print(f"http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if args[:1] == ["serve"]:
        port = int(args[1]) if len(args) > 1 else 8765
        serve(port=port)
        return
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(ROOT))
    print(OUT)


if __name__ == "__main__":
    main()
