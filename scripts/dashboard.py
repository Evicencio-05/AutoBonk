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
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import blotter  # noqa: E402
import desk  # noqa: E402
import claim_alerts  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dashboard" / "index.html"


def _ledger_data(root: Path) -> tuple[list[dict], dict, dict, str]:
    """Ledger rows, raised alarms, freeze progress, and when the rows were built.

    The hosted desk reads the snapshot `ledger.py sync` stores in the database.
    Without one it reads the committed learning/trades.jsonl.
    """
    import freeze as freeze_mod
    import ledger as ledger_mod

    stamp = ""
    rows: list[dict] = []
    alarms: dict = {}
    snapshot = blotter.load_ledger() if root.resolve() == ROOT.resolve() else None
    if snapshot and isinstance(snapshot.get("rows"), list):
        rows = snapshot["rows"]
        alarms = snapshot.get("alarms") or {}
        stamp = str(snapshot.get("updated_at") or "")
    else:
        rows = ledger_mod.load(root / "learning" / "trades.jsonl")
        try:
            alarms = json.loads((root / "alerts" / "alarms.json").read_text())
        except (OSError, json.JSONDecodeError):
            alarms = {}
    progress = freeze_mod.progress(rows, freeze_mod.config(root / "config" / "freeze.yaml"))
    return rows, alarms, progress, stamp


def render(root: Path) -> str:
    import overview

    rows, alarms, progress, stamp = _ledger_data(root)
    as_of = f"<p class='sub'>Ledger built {_esc(stamp[:16].replace('T', ' '))} PT.</p>" if stamp else ""
    return _page(
        [
            ("Overview", overview.overview(rows, alarms, progress) + as_of, "overview"),
            ("All trades", overview.trades_table(rows), "ledger"),
            ("Proposals", overview.proposals_panel(root), "proposals"),
            ("Open trades", _paper(root), "trades"),
            ("Live session", _live_session(root), "session"),
            ("Watch", _watches(root), "watch"),
            ("Backtest", _studio(root), "backtest"),
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
    text = path.read_text() if path.is_file() else ""
    if path.parent == ROOT / "alerts":
        text = blotter.merge(path.name, text)
    return text


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


def _paper_label(entry: dict) -> str:
    """Paper only when the paid premium is over the contract cap."""
    premium = _premium(entry.get("premium"))
    book = desk.classify_contract(entry.get("contract"), premium, claim_alerts.CONTRACT_CAP)
    return "paper" if book == "paper" else ""


def _label_cell(entry: dict) -> str:
    label = _paper_label(entry)
    if not label:
        return "<td></td>"
    return "<td class='paper'>paper</td>"


def _watch_rows(text: str) -> list[dict]:
    """The latest watch for each level on the newest session in the log."""
    found = []
    for line in text.splitlines():
        if " watch " not in line or not line.startswith("- "):
            continue
        head, _, rest = line[2:].partition(" at ")
        pieces = head.split()
        if len(pieces) < 4 or pieces[2] != "watch":
            continue
        when, _, note = rest.partition(". ")
        if " PT" not in when:
            continue
        found.append(
            {
                "ticker": pieces[0],
                "side": pieces[1],
                "level": pieces[3],
                "time": when.strip(),
                "note": note.strip(),
            }
        )
    if not found:
        return []
    newest = max(row["time"][:10] for row in found)
    latest: dict[tuple[str, str, str], dict] = {}
    for row in found:
        if row["time"][:10] != newest:
            continue
        latest[(row["ticker"], row["side"], row["level"])] = row
    return list(latest.values())


def _watches(root: Path) -> str:
    rows = _watch_rows(_read(root / "alerts" / "log.md"))
    if not rows:
        return "<p>No watch. A watch is not a fill and it is not an order.</p>"
    body = []
    for row in sorted(rows, key=lambda item: item["time"]):
        side = row["side"]
        side_class = " call" if side == "call" else " put" if side == "put" else ""
        body.append(
            "<tr>"
            f"<td class='num'>{_esc(row['time'])}</td>"
            f"<td class='ticker'>{_esc(row['ticker'])}</td>"
            f"<td class='side{side_class}'>{_esc(side)}</td>"
            f"<td class='num'>{_esc(row['level'])}</td>"
            f"<td>{_esc(row['note'])}</td>"
            "</tr>"
        )
    return (
        "<p>The latest watch on each level for the newest session in the log. "
        "A watch is not a fill and it is not an order.</p>"
        "<table><thead><tr>"
        "<th>Time</th><th>Ticker</th><th>Side</th><th>Level</th><th>Note</th>"
        f"</tr></thead><tbody>{''.join(body)}</tbody></table>"
    )


def _open_table(trades: list[dict]) -> str:
    open_rows = [trade for trade in trades if trade["exit"] is None]
    if not open_rows:
        return "<div id='open-trades'><p>No open trade.</p></div>"
    body = []
    for trade in reversed(open_rows):
        entry = trade["entry"]
        side = entry["side"]
        side_class = " call" if side == "call" else " put" if side == "put" else ""
        mark = trade["mark"]
        mark_text = "" if mark is None else f"{mark['premium']} at {mark['as_of']}"
        body.append(
            "<tr>"
            f"<td class='num'>{_esc(entry['time'])}</td>"
            f"<td class='ticker'>{_esc(entry['ticker'])}</td>"
            f"<td class='side{side_class}'>{_esc(side)}</td>"
            f"<td class='num'>{_esc(entry['level'])}</td>"
            f"<td class='num'>{_esc(entry['fill'])}</td>"
            f"<td>{_esc(entry['contract'])}</td>"
            f"<td class='num'>{_esc(entry['premium'])}</td>"
            f"<td class='num'>{_esc(mark_text)}</td>"
            f"{_label_cell(entry)}"
            "</tr>"
        )
    return (
        "<div id='open-trades'>"
        "<p>These entries have no exit. A mark is the latest print. "
        "A trade is labeled paper when the premium is over $1. This is not an order.</p>"
        "<table><thead><tr>"
        "<th>Time</th><th>Ticker</th><th>Side</th><th>Level</th>"
        "<th>Fill</th><th>Contract</th><th>Paid</th><th>Mark</th><th></th>"
        f"</tr></thead><tbody>{''.join(body)}</tbody></table></div>"
    )


def _live_session(root: Path) -> str:
    """The live tape: every entry and exit the checker wrote on a live session."""
    note = (
        "<p>Agentic account, one contract. The checker sends a qualifying entry and its exit. "
        "A row with no order stays a plan: a balance that cannot pay, a 0DTE strike past halfway, "
        "or an empty ladder. Broker fills and dollars for each row are on the Overview.</p>"
    )
    text = _read(root / "alerts" / "live.md")
    detailed = "$1 strike" in text
    body = []
    for cells in _table_rows(text):
        if cells[0] == "Time":
            continue
        padded = (cells + [""] * (15 if detailed else 12))[: 15 if detailed else 12]
        side = padded[3]
        side_class = " call" if side == "call" else " put" if side == "put" else ""
        cash = padded[9]
        cash_class = " call" if cash == "fits" else " put" if cash == "over" else ""
        if detailed:
            extra = (
                f"<td>{_esc(padded[10])}</td>"
                f"<td class='num'>{_esc(padded[11])}</td>"
                f"<td>{_esc(padded[12])}</td>"
                f"<td class='num'>{_esc(padded[13])}</td>"
                f"<td>{_esc(padded[14])}</td>"
            )
        else:
            extra = f"<td>{_esc(padded[10])}</td><td>{_esc(padded[11])}</td>"
        body.append(
            "<tr>"
            f"<td class='num'>{_esc(padded[0])}</td>"
            f"<td class='ticker'>{_esc(padded[1])}</td>"
            f"<td>{_esc(padded[2])}</td>"
            f"<td class='side{side_class}'>{_esc(side)}</td>"
            f"<td class='num'>{_esc(padded[4])}</td>"
            f"<td class='num'>{_esc(padded[5])}</td>"
            f"<td>{_esc(padded[6])}</td>"
            f"<td>{_esc(padded[7])}</td>"
            f"<td class='num'>{_esc(padded[8])}</td>"
            f"<td class='{cash_class.strip()}'>{_esc(cash)}</td>"
            f"{extra}"
            "</tr>"
        )
    if not body:
        return note + "<p>No live plan yet.</p>"
    if detailed:
        tail = (
            "<th>$1 strike</th><th>$1 premium</th><th>Cash strike</th>"
            "<th>Cash premium</th><th>Halfway</th>"
        )
    else:
        tail = "<th>Under $0.50</th><th>Halfway</th>"
    return (
        note
        + "<table><thead><tr>"
        "<th>Time</th><th>Ticker</th><th>Action</th><th>Side</th><th>Level</th>"
        "<th>Fill</th><th>Reason</th><th>Contract</th><th>Premium</th><th>Cash</th>"
        f"{tail}"
        f"</tr></thead><tbody>{''.join(body)}</tbody></table>"
    )


def _paper(root: Path) -> str:
    text = _read(root / "alerts" / "paper.md")
    rows, marks = _paper_rows(text)
    notes = [
        "<p>A row here is not an order and is not a journal trade. "
        "Profit is one contract, the premium change times 100.</p>"
    ]
    for line in text.split("## Open marks", 1)[0].splitlines():
        if line.startswith("- "):
            notes.append(f"<p>{_esc(line[2:].strip())}</p>")
    if not rows:
        return "<p>No open trade.</p>" + "".join(notes)
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
            f"{_label_cell(entry)}"
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
        _open_table(trades)
        + "<table><thead><tr>"
        "<th>Time</th><th>Ticker</th><th>Side</th><th>Level</th>"
        "<th>Contract</th><th>Paid</th><th>Exit</th><th></th><th>Profit</th>"
        f"</tr></thead><tbody>{''.join(trade_rows)}"
        f"<tr data-stay><td colspan='8'>Day</td><td class='num{total_class}'>{_esc(total_text)}</td></tr>"
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


_CHOICE_LABELS = {
    "retest": "retest",
    "fade": "fade",
    "target": "close through the far target",
    "stop": "named stop",
}


def _select_field(name: str, element_id: str, label: str) -> str:
    spec = claim_alerts.VARIABLES[name]
    current = spec["default"]
    options = "".join(
        f"<option value='{_esc(choice)}'{' selected' if choice == current else ''}>"
        f"{_esc(_CHOICE_LABELS.get(choice, choice))}</option>"
        for choice in spec["allowed"]
    )
    return f'<label>{_esc(label)} <select id="{element_id}">{options}</select></label>'


def _number_field(name: str, element_id: str, label: str) -> str:
    default = claim_alerts.VARIABLES[name]["default"]
    return f'<label>{_esc(label)} <input id="{element_id}" value="{_esc(default)}"></label>'


_RANGE_FIELDS = (
    ("touch", "touch", "Wick touch", "0", "0.50"),
    ("sma_band", "sma-band", "SMA band", "0", "2"),
    ("chase", "chase", "Chase", "0", "1.50"),
    ("break_atr", "break-atr", "ATR fraction", "0", "1.50"),
    ("profit_near", "profit-near", "Near a level", "0", "0.50"),
)
_RANGE_LABELS = {name: label for name, _element, label, _low, _high in _RANGE_FIELDS}


def _range_field(name: str, element_id: str, label: str, low: str, high: str) -> str:
    default = 0.15 if name == "profit_near" else claim_alerts.VARIABLES[name]["default"]
    return (
        f'<div class="range-knob" data-name="{name}" data-low="{element_id}-low" data-high="{element_id}-high">'
        f'<label>{_esc(label)} <input id="{element_id}" value="{_esc(default)}"></label>'
        f'<label class="tick"><input id="range-{name}" type="checkbox"> Range</label>'
        f'<div class="bounds" id="bounds-{name}" hidden>'
        f'<label>Low <input id="{element_id}-low" value="{low}"></label>'
        f'<label>High <input id="{element_id}-high" value="{high}"></label>'
        f"</div></div>"
    )


def _strategy_fields() -> str:
    ranges = "".join(_range_field(*spec) for spec in _RANGE_FIELDS)
    return (
        _select_field("entry", "entry", "Entry")
        + _select_field("exit", "exit-rule", "Exit rule")
        + ranges
        + '<label>Range steps <input id="range-steps" value="10"></label>'
    )


def _as_iso(value) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value or "")


def _clock(text: str) -> str:
    when = datetime.fromisoformat(str(text))
    if when.tzinfo is None:
        when = when.replace(tzinfo=claim_alerts.PT)
    when = when.astimezone(claim_alerts.PT)
    clock = when.strftime("%I:%M %p").lstrip("0")
    return f"{when.strftime('%Y-%m-%d')} {clock} PT"


def _armed_choices(root: Path) -> list[tuple[str, str]]:
    """The live book's armed time, then each saved book's armed time."""
    live = ""
    path = root / "alerts" / "levels.yaml"
    if path.is_file():
        data = yaml.safe_load(path.read_text()) or {}
        live = _as_iso(data.get("armed_at") or "")
    choices: list[tuple[str, str]] = []
    seen: set[str] = set()
    if live:
        choices.append((live, f"This book · {_clock(live)}"))
        seen.add(live)
    folder = root / "bench" / "fixtures"
    if folder.is_dir():
        for levels_path in sorted(folder.glob("*-levels.yaml"), reverse=True):
            day = levels_path.name[: -len("-levels.yaml")]
            data = yaml.safe_load(levels_path.read_text()) or {}
            stamp = _as_iso(data.get("armed_at") or "")
            if not stamp or stamp in seen:
                continue
            seen.add(stamp)
            choices.append((stamp, f"{day} book · {_clock(stamp)}"))
    if not choices:
        choices.append(("", "Not set"))
    return choices


def _armed_field(root: Path) -> str:
    options = []
    for index, (value, label) in enumerate(_armed_choices(root)):
        selected = " selected" if index == 0 else ""
        options.append(f'<option value="{_esc(value)}"{selected}>{_esc(label)}</option>')
    return f'<label>Armed <select id="armed-at">{"".join(options)}</select></label>'


def _calendar_fields() -> str:
    today = datetime.now(claim_alerts.PT).date()
    start = today - timedelta(days=30)
    return (
        f'<label>From <input id="range-from" type="date" value="{start.isoformat()}"></label>'
        f'<label>To <input id="range-to" type="date" value="{today.isoformat()}"></label>'
    )


def _studio(root: Path) -> str:
    path = root / "alerts" / "levels.yaml"
    data = yaml.safe_load(path.read_text()) if path.is_file() else {}
    data = data or {}
    armed = data.get("armed_at") or ""
    if hasattr(armed, "isoformat"):
        armed = armed.isoformat()
    levels = data.get("levels") or []
    level_rows = "".join(_level_inputs(level) for level in levels) or _level_inputs({})
    count = len(levels)
    payload = json.dumps({"armed_at": armed}).replace("<", "\\u003c")
    return f"""
<p>Change the entry, the exit, and the buffers, then run the test.
The report is stock points on finished 10-minute closes: net profit, gross profit,
gross loss, profit factor, max drawdown, win rate, and the average trade.
It also gives each day's profit under these parameters and under the live parameters, and the difference.
The armed menu is when this book started. It applies to recent sessions.
Saved sessions keep each day's own armed time.
The calendar keeps closes on those dates for both.
Check Range on wick touch, the SMA band, chase, the ATR fraction, or near a level.
Set that buffer's low and high. Range steps cuts the span into 10 to 20 values and graphs the net.
Live, Never exit, Near the next level, and Named stop are scored beside this test.
This does not place an order and it does not rewrite the paper tape.</p>
<p class="knobs" id="strategy-fields">
{_armed_field(root)}
<label>Bars <select id="bars-source"><option value="recent">recent sessions</option><option value="saved">saved sessions</option></select></label>
{_calendar_fields()}
{_strategy_fields()}
<label>Exit test <select id="exit-test"><option value="live">use the exit rule</option><option value="never">never exit</option><option value="near">near the next level</option><option value="named">named stop</option><option value="custom">custom</option></select></label>
<label>Stop <select id="stop-mode"><option value="reclaim">reclaim</option><option value="named">named stop</option><option value="none">none</option></select></label>
<label>Take profit <select id="take-mode"><option value="target">close through the far target</option><option value="near">near the next level</option><option value="none">never</option></select></label>
<label>Clock <select id="flatten-mode"><option value="clock">12:50 PT</option><option value="none">do not flatten</option></select></label>
</p>
<p class="actions"><button type="button" id="run-backtest">Run backtest</button>
<button type="button" id="save-book">Save book</button></p>
<details>
<summary>Levels in this test ({count})</summary>
<table class="editor levels" data-nosort><thead><tr><th>Ticker</th><th>Price</th><th>Allows</th><th>Targets</th><th>Up targets</th><th>Stop</th><th>Note</th></tr></thead>
<tbody id="level-rows">{level_rows}</tbody></table>
<p class="actions"><button type="button" id="add-level">Add level</button></p>
</details>
<div id="backtest-out"><p>Run the test to see net profit, drawdown, and win rate for these variables.</p></div>
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


def _day_bounds(payload: dict) -> tuple[date, date] | None:
    start_text = str(payload.get("from") or "").strip()
    end_text = str(payload.get("to") or "").strip()
    if not start_text and not end_text:
        return None
    if not start_text or not end_text:
        raise ValueError("from and to are both required")
    try:
        start = date.fromisoformat(start_text)
        end = date.fromisoformat(end_text)
    except ValueError as exc:
        raise ValueError("from and to must be YYYY-MM-DD") from exc
    if start > end:
        raise ValueError("from must be on or before to")
    return start, end


def _covers(close_at: int, bounds: tuple[date, date] | None) -> bool:
    if bounds is None:
        return True
    start, end = bounds
    day = datetime.fromtimestamp(int(close_at), claim_alerts.PT).date()
    return start <= day <= end


def _clip_bars(bars_by_ticker: dict, bounds: tuple[date, date] | None) -> dict:
    if bounds is None:
        return bars_by_ticker
    return {
        ticker: [bar for bar in bars if _covers(bar["close_at"], bounds)]
        for ticker, bars in bars_by_ticker.items()
    }


def _mark_calendar(window: dict, bounds: tuple[date, date] | None) -> dict:
    if bounds is not None:
        window["from_day"] = bounds[0].isoformat()
        window["to_day"] = bounds[1].isoformat()
    return window


def _yahoo_span(start: date, today: date) -> str:
    if (today - start).days <= 5:
        return "5d"
    return "1mo"


def _calendar_note(bounds: tuple[date, date] | None, today: date) -> str:
    if bounds is None or (today - bounds[0]).days <= 31:
        return ""
    return "Recent prices cover about one month. Older calendar dates have no bars."


def _armed_stamp(text: str) -> int:
    if not text:
        return 0
    when = datetime.fromisoformat(str(text))
    if when.tzinfo is None:
        when = when.replace(tzinfo=claim_alerts.PT)
    return int(when.timestamp())


def _fetch_bars(tickers: list[str], span: str = "1mo") -> dict[str, list[dict]]:
    if span not in ("5d", "1mo"):
        raise ValueError("range must be 5d or 1mo")
    moment = int(datetime.now(claim_alerts.PT).timestamp())
    found = {}
    for ticker in tickers:
        raw = claim_alerts.fetch_five_minute(ticker, span)
        bars = claim_alerts.add_indicators(claim_alerts.ten_minute_bars(raw, moment))
        found[ticker] = [bar for bar in bars if claim_alerts.in_session(bar["close_at"])]
    return found


def _window(bars_by_ticker: dict[str, list[dict]], source: str, note: str = "") -> dict:
    stamps = [bar["close_at"] for bars in bars_by_ticker.values() for bar in bars]
    window = {
        "source": source,
        "bars": len(stamps),
        "tickers": len(bars_by_ticker),
        "missing": [ticker for ticker, bars in bars_by_ticker.items() if not bars],
    }
    if stamps:
        window["from"] = datetime.fromtimestamp(min(stamps), claim_alerts.PT).strftime("%Y-%m-%d %H:%M PT")
        window["to"] = datetime.fromtimestamp(max(stamps), claim_alerts.PT).strftime("%Y-%m-%d %H:%M PT")
    if note:
        window["note"] = note
    return window


def _variable(payload: dict, name: str):
    spec = claim_alerts.VARIABLES[name]
    if name not in payload or payload[name] == "":
        return spec["default"]
    if payload[name] is None:
        raise ValueError(f"{name} must be a number" if spec["type"] == "float" else f"{name} must be set")
    return claim_alerts._coerce(name, payload[name], spec)


def _profit_near(payload: dict) -> float:
    value = payload.get("profit_near", 0.15)
    if value in ("", None):
        if value is None and "profit_near" in payload:
            raise ValueError("profit_near must be a number")
        return 0.15
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("profit_near must be a number") from exc
    if number < 0:
        raise ValueError("profit_near must be zero or more")
    return number


def _one_of(value, allowed: tuple[str, ...], label: str) -> str:
    if value not in allowed:
        raise ValueError(f"{label} must be one of {', '.join(allowed)}")
    return value


def _this_test(payload: dict) -> dict:
    """The form's exit. Live uses the exit rule. The other tests are what-ifs."""
    extra = {"exit": _variable(payload, "exit")}
    mode = _one_of(
        payload.get("exit_test") or "live",
        ("live", "never", "near", "named", "custom"),
        "exit test",
    )
    if mode == "never":
        extra.update(stop_mode="none", take="none", flatten="none")
    elif mode == "near":
        extra.update(stop_mode="none", take="near", flatten="clock")
    elif mode == "named":
        extra.update(stop_mode="named", take="none", flatten="clock")
    elif mode == "custom":
        extra.update(
            stop_mode=_one_of(payload.get("stop_mode") or "reclaim", ("reclaim", "named", "none"), "stop"),
            take=_one_of(payload.get("take") or "target", ("target", "near", "none"), "take profit"),
            flatten=_one_of(payload.get("flatten") or "clock", ("clock", "none"), "clock"),
        )
    return extra


def _range_number(name: str, value, edge: str) -> float:
    label = f"{_RANGE_LABELS[name]} {edge}"
    if value is None or value == "":
        raise ValueError(f"{label} must be a number")
    if name == "profit_near":
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} must be a number") from exc
        if number < 0:
            raise ValueError(f"{label} must be zero or more")
        return number
    try:
        return float(claim_alerts._coerce(name, value, claim_alerts.VARIABLES[name]))
    except ValueError as exc:
        text = str(exc)
        if text.startswith(f"{name} "):
            raise ValueError(f"{label} {text[len(name) + 1:]}") from exc
        raise


def _range_steps(low: float, high: float, count: int) -> list[float]:
    if count < 10 or count > 20:
        raise ValueError("steps must be a whole number from 10 to 20")
    if low > high:
        raise ValueError("the range low must be at or below the high")
    if count == 1:
        return [round(float(low), 6)]
    values = []
    for index in range(count):
        if index == count - 1:
            values.append(round(float(high), 4))
        else:
            values.append(round(float(low) + (float(high) - float(low)) * index / (count - 1), 4))
    return values


def _parse_ranges(payload: dict) -> list[dict]:
    raw = payload.get("ranges") or []
    if raw in ([], None, ""):
        return []
    if not isinstance(raw, list):
        raise ValueError("ranges must be a list")
    steps = payload.get("steps", 10)
    if steps in (None, ""):
        steps = 10
    try:
        number = float(steps)
    except (TypeError, ValueError) as exc:
        raise ValueError("steps must be a whole number from 10 to 20") from exc
    if number != int(number):
        raise ValueError("steps must be a whole number from 10 to 20")
    count = int(number)
    parsed = []
    seen: set[str] = set()
    for row in raw:
        if not isinstance(row, dict):
            raise ValueError("a range needs a name, a low, and a high")
        name = str(row.get("name") or "")
        if name not in _RANGE_LABELS:
            raise ValueError("range must be wick touch, SMA band, chase, ATR fraction, or near a level")
        if name in seen:
            continue
        seen.add(name)
        low = _range_number(name, row.get("low"), "low")
        high = _range_number(name, row.get("high"), "high")
        if low > high:
            raise ValueError(f"{_RANGE_LABELS[name]} low must be at or below the high")
        parsed.append(
            {
                "name": name,
                "label": _RANGE_LABELS[name],
                "low": low,
                "high": high,
                "values": _range_steps(low, high, count),
            }
        )
    return parsed


def _this_settings(kwargs: dict, overrides: dict) -> dict:
    return desk._settings(
        overrides.get("touch", kwargs["touch"]),
        overrides.get("chase", kwargs["chase"]),
        overrides.get("break_atr", kwargs["break_atr"]),
        overrides.get("profit_near", kwargs["profit_near"]),
        overrides.get("sma_band", kwargs["sma_band"]),
        kwargs["entry"],
        kwargs.get("this_test"),
    )


def _sweep_points(days: list[dict], kwargs: dict, name: str, values: list[float]) -> list[dict]:
    points = []
    for value in values:
        settings = _this_settings(kwargs, {name: value})
        trades = []
        stitched: dict[str, list[dict]] = {}
        for day in days:
            result = desk.run_backtest(
                day["bars"],
                day["levels"],
                day["armed_at"],
                settings,
                kwargs.get("premiums"),
                kwargs.get("threshold") or 1,
            )
            trades.extend(result["trades"])
            for ticker, bars in day["bars"].items():
                stitched.setdefault(ticker, []).extend(bars)
        ordered = {
            ticker: sorted(bars, key=lambda bar: bar["close_at"])
            for ticker, bars in stitched.items()
        }
        stats = desk.performance(trades, ordered)["summary"]["strategy"]
        points.append(
            {
                "value": value,
                "net": stats["net"],
                "trades": stats["trades"],
                "win_rate": stats["win_rate"],
                "profit_factor": stats["profit_factor"],
                "max_drawdown": stats["max_drawdown"],
                "expected": stats["expected"],
            }
        )
    return points


def _session_days(days: list[dict]) -> list[dict]:
    """One row per cash session. A recent fetch that spans dates is split on the PT date."""
    sessions = []
    for day in days:
        if day.get("day"):
            sessions.append(day)
            continue
        by_date: dict[str, dict[str, list[dict]]] = {}
        for ticker, bars in day["bars"].items():
            for bar in bars:
                stamp = datetime.fromtimestamp(bar["close_at"], claim_alerts.PT).date().isoformat()
                by_date.setdefault(stamp, {}).setdefault(ticker, []).append(bar)
        for stamp, bars in sorted(by_date.items()):
            sessions.append(
                {
                    "day": stamp,
                    "bars": bars,
                    "levels": day["levels"],
                    "armed_at": day["armed_at"],
                }
            )
    return sessions


def _day_net(day: dict, settings: dict, kwargs: dict) -> float:
    result = desk.run_backtest(
        day["bars"],
        day["levels"],
        day["armed_at"],
        settings,
        kwargs.get("premiums"),
        kwargs.get("threshold") or 1,
    )
    return desk.performance(result["trades"], day["bars"])["summary"]["strategy"]["net"]


def _live_run_settings() -> dict:
    defaults = claim_alerts.live_settings()
    return desk._settings(
        defaults["touch"],
        defaults["chase"],
        defaults["break_atr"],
        0.15,
        defaults["sma_band"],
        defaults["entry"],
        None,
    )


def _parameter_days(days: list[dict], kwargs: dict) -> list[dict]:
    """Stock points for the day under the live parameters and under this test."""
    new = _this_settings(kwargs, {})
    old = _live_run_settings()
    rows = []
    for day in _session_days(days):
        old_net = _day_net(day, old, kwargs)
        new_net = _day_net(day, new, kwargs)
        rows.append(
            {
                "day": day["day"],
                "old": old_net,
                "new": new_net,
                "difference": new_net - old_net,
            }
        )
    return rows


def _attach_sweeps(packed: dict, days: list[dict], kwargs: dict, payload: dict) -> dict:
    packed["parameter_days"] = _parameter_days(days, kwargs)
    ranges = _parse_ranges(payload)
    if not ranges:
        return packed
    packed["sweeps"] = [
        {
            "name": row["name"],
            "label": row["label"],
            "low": row["low"],
            "high": row["high"],
            "steps": len(row["values"]),
            "points": _sweep_points(days, kwargs, row["name"], row["values"]),
        }
        for row in ranges
    ]
    return packed


def _preset_kwargs(payload: dict) -> dict:
    threshold = payload.get("threshold", 1)
    if threshold in (None, ""):
        threshold = 1
    return {
        "touch": _variable(payload, "touch"),
        "chase": _variable(payload, "chase"),
        "break_atr": _variable(payload, "break_atr"),
        "profit_near": _profit_near(payload),
        "sma_band": _variable(payload, "sma_band"),
        "entry": _variable(payload, "entry"),
        "threshold": float(threshold),
        "premiums": _premium_map(payload.get("premiums") or {}),
        "this_test": _this_test(payload),
    }


def _pack(runs: list[dict], window: dict) -> dict:
    report = next(run for run in runs if run["name"] == "This test")
    return {"runs": runs, "report": report, "window": window}


def _bars_for_tickers(source: dict, tickers: list[str]) -> dict[str, list[dict]]:
    found = {ticker: {} for ticker in tickers}
    for ticker in tickers:
        for bar in source.get(ticker) or []:
            if not isinstance(bar, dict):
                continue
            if any(bar.get(name) is None for name in ("close_at", "o", "h", "l", "c")):
                continue
            close_at = int(bar["close_at"])
            if not claim_alerts.in_session(close_at):
                continue
            found[ticker][close_at] = {
                "start": close_at - claim_alerts.TEN_MIN,
                "close_at": close_at,
                "o": float(bar["o"]),
                "h": float(bar["h"]),
                "l": float(bar["l"]),
                "c": float(bar["c"]),
                "v": bar.get("v"),
            }
    return {
        ticker: claim_alerts.add_indicators([by_time[stamp] for stamp in sorted(by_time)])
        for ticker, by_time in found.items()
    }


def _saved_days(root: Path) -> list[dict]:
    """Each frozen session keeps that day's levels and its armed time."""
    folder = root / "bench" / "fixtures"
    if not folder.is_dir():
        return []
    days = []
    for bars_path in sorted(folder.glob("*-bars.json")):
        day = bars_path.name[: -len("-bars.json")]
        levels_path = folder / f"{day}-levels.yaml"
        if not levels_path.is_file():
            continue
        data = yaml.safe_load(levels_path.read_text()) or {}
        armed = data.get("armed_at") or ""
        if hasattr(armed, "isoformat"):
            armed = armed.isoformat()
        levels = _parse_levels(data.get("levels") or [])
        raw = json.loads(bars_path.read_text())
        source = raw.get("tickers") if isinstance(raw.get("tickers"), dict) else raw
        if not isinstance(source, dict):
            continue
        tickers = sorted({level["ticker"] for level in levels})
        days.append(
            {
                "day": day,
                "levels": levels,
                "armed_at": _armed_stamp(str(armed)),
                "bars": _bars_for_tickers(source, tickers),
            }
        )
    return days


def _saved_payload(
    payload: dict,
    kwargs: dict,
    note: str = "",
    bounds: tuple[date, date] | None = None,
) -> dict:
    days = _saved_days(ROOT)
    if bounds is not None:
        start, end = bounds
        days = [day for day in days if start <= date.fromisoformat(day["day"]) <= end]
    if not days:
        message = note or ("No saved sessions in that calendar." if bounds else "No saved sessions.")
        window = _mark_calendar(_window({}, "saved", message), bounds)
        runs = desk.run_presets({}, [], 0, **kwargs)
        return _attach_sweeps(_pack(runs, window), [], kwargs, payload)
    day_runs = [
        desk.run_presets(day["bars"], day["levels"], day["armed_at"], **kwargs)
        for day in days
    ]
    stitched: dict[str, list[dict]] = {}
    for day in days:
        for ticker, bars in day["bars"].items():
            stitched.setdefault(ticker, []).extend(bars)
    ordered = {
        ticker: sorted(bars, key=lambda bar: bar["close_at"])
        for ticker, bars in stitched.items()
    }
    runs = []
    for index, first in enumerate(day_runs[0]):
        trades = []
        for scored in day_runs:
            trades.extend(scored[index]["trades"])
        runs.append(
            {
                "name": first["name"],
                "trades": trades,
                "settings": first["settings"],
                **desk.performance(trades, ordered),
            }
        )
    window = _mark_calendar(_window(ordered, "saved", note), bounds)
    window["days"] = [day["day"] for day in days]
    return _attach_sweeps(_pack(runs, window), days, kwargs, payload)


def backtest_payload(payload: dict, bars_by_ticker: dict | None = None) -> dict:
    kwargs = _preset_kwargs(payload)
    bounds = _day_bounds(payload)
    source = payload.get("bars") or "recent"
    if bars_by_ticker is not None:
        bars_by_ticker = _clip_bars(bars_by_ticker, bounds)
        levels = _parse_levels(payload.get("levels") or [])
        armed = _armed_stamp(payload.get("armed_at") or "")
        window = _mark_calendar(_window(bars_by_ticker, "given"), bounds)
        days = [{"bars": bars_by_ticker, "levels": levels, "armed_at": armed}]
        runs = desk.run_presets(bars_by_ticker, levels, armed, **kwargs)
        return _attach_sweeps(_pack(runs, window), days, kwargs, payload)
    if source == "saved":
        return _saved_payload(payload, kwargs, bounds=bounds)
    if source != "recent":
        raise ValueError("bars must be recent or saved")
    levels = _parse_levels(payload.get("levels") or [])
    tickers = sorted({level["ticker"] for level in levels})
    today = datetime.now(claim_alerts.PT).date()
    span = "1mo" if bounds is None else _yahoo_span(bounds[0], today)
    try:
        bars = _clip_bars(_fetch_bars(tickers, span), bounds)
    except (SystemExit, OSError, urllib.error.URLError) as exc:
        note = f"Recent prices were unavailable ({exc}). Saved sessions were used."
        return _saved_payload(payload, kwargs, note, bounds)
    armed = _armed_stamp(payload.get("armed_at") or "")
    window = _mark_calendar(_window(bars, "recent", _calendar_note(bounds, today)), bounds)
    days = [{"bars": bars, "levels": levels, "armed_at": armed}]
    runs = desk.run_presets(bars, levels, armed, **kwargs)
    return _attach_sweeps(_pack(runs, window), days, kwargs, payload)


def save_book(root: Path, payload: dict) -> None:
    levels = _parse_levels(payload.get("levels") or [])
    armed = str(payload.get("armed_at") or "")
    path = root / "alerts" / "levels.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"armed_at": armed, "levels": levels}, sort_keys=False))


def _contain_tables(part: str) -> str:
    return part.replace("<table", "<div class='sheet-scroll'><table").replace("</table>", "</table></div>")


def _page(sections: list[tuple[str, str, str]]) -> str:

    by_anchor = {anchor: (title, part) for title, part, anchor in sections}
    used = {anchor for _label, _tab, anchors in TABS for anchor in anchors}
    tabs = [
        (label, tab, [anchor for anchor in anchors if anchor in by_anchor]) for label, tab, anchors in TABS
    ]
    leftover = [anchor for _title, _part, anchor in sections if anchor not in used]
    if leftover:
        tabs.append(("More", "more", leftover))
    nav = []
    panels = []
    for label, tab, anchors in tabs:
        if not anchors:
            continue
        nav.append(f"<a href='#{tab}' data-tab='{tab}' role='tab' aria-controls='{tab}'>{html.escape(label)}</a>")
        inside = "".join(
            f"<section id='{anchor}'><h2>{html.escape(by_anchor[anchor][0])}</h2>"
            f"{_contain_tables(by_anchor[anchor][1])}</section>"
            for anchor in anchors
        )
        jump = ""
        if len(anchors) > 1:
            jump = "<p class='jump'>" + " · ".join(
                f"<a href='#{anchor}'>{html.escape(by_anchor[anchor][0])}</a>" for anchor in anchors
            ) + "</p>"
        panels.append(f"<div class='panel' id='{tab}' role='tabpanel' data-panel='{tab}'>{jump}{inside}</div>")
    template = Path(__file__).with_name("dashboard_page.html").read_text()
    return template.replace("__NAV__", "".join(nav)).replace("__BODY__", "".join(panels))


# Tabs on the desk, in order. Every section anchor lives in one tab.
TABS = (
    ("Overview", "home", ("overview", "ledger")),
    ("Proposals", "decide", ("proposals",)),
    ("Today", "today", ("session", "trades", "watch", "contracts")),
    ("Backtest", "test", ("backtest", "bench")),
    ("Learning", "learn", ("lessons", "journal", "training", "fade")),
    ("Reference", "reference", ("rules", "book", "alerts", "archives")),
)


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
