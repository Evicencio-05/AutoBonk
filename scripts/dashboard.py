#!/usr/bin/env python3
"""Write a read-only dashboard from the files already in the repo.

  python3 scripts/dashboard.py

Opens nothing, places no order, and does not call the network.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dashboard" / "index.html"


def render(root: Path) -> str:
    return _page(
        _paper(root),
        _contracts(root),
        _live_book(root),
        _alerts(root),
        _journal(root),
        _training(root),
        _bench(root),
        _archives(root),
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
        + "".join(notes)
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
            for label in ("Confirmed buy", "Confirmed sell", "Buy miss", "Sell miss")
        )
    ]
    blocks = ["<p>One observation. Not a live alert.</p>"]
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


def _page(*sections: str) -> str:
    titles = (
        "Paper",
        "Contracts",
        "Live book",
        "Alerts",
        "Journal",
        "Training",
        "Bench",
        "Archives",
    )
    body = "".join(
        f"<section><h2>{title}</h2>{html_part}</section>"
        for title, html_part in zip(titles, sections)
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="60">
<title>AutoBonk</title>
<style>
  body {{ margin: 0; background: #101218; color: #e7e4dc;
    font: 15px/1.45 "Segoe UI", system-ui, sans-serif; }}
  main {{ max-width: 1180px; margin: 0 auto; padding: 28px 24px 48px; }}
  header {{ margin: 0 0 18px; }}
  h1 {{ font-size: 1.5rem; font-weight: 650; letter-spacing: -0.02em; margin: 0; }}
  .status {{ margin: 6px 0 0; color: #9aa3b2; }}
  h2 {{ font-size: 0.78rem; font-weight: 650; letter-spacing: 0.08em;
    text-transform: uppercase; margin: 0 0 12px; color: #9aa3b2; }}
  h3 {{ font-size: 0.95rem; margin: 14px 0 6px; color: #f3efe6; }}
  section {{ background: #181b22; border: 1px solid #2a3040; border-radius: 12px;
    padding: 16px 18px 8px; margin: 0 0 14px; }}
  p, li {{ color: #c9c3b8; }}
  table {{ width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }}
  th, td {{ text-align: left; padding: 8px 10px; vertical-align: top;
    border-bottom: 1px solid #2a3040; }}
  th {{ color: #8b95a8; font-size: 0.75rem; font-weight: 650;
    letter-spacing: 0.04em; text-transform: uppercase; cursor: pointer; }}
  th[aria-sort="ascending"]::after {{ content: " \\2191"; color: #e7e4dc; }}
  th[aria-sort="descending"]::after {{ content: " \\2193"; color: #e7e4dc; }}
  td.ticker {{ font-weight: 700; color: #f7f4ee; }}
  td.call, td.up {{ color: #8fbf9f; }}
  td.put, td.down {{ color: #d7a0a0; }}
  a {{ color: #9ecbff; }}
</style>
</head>
<body>
<main>
<header>
<h1>AutoBonk</h1>
<p class="status">Paper session. A row on this page is not an order.</p>
<p class="status" id="loaded">Loaded</p>
</header>
{body}
</main>
<script>
document.getElementById("loaded").textContent = "Loaded " + new Intl.DateTimeFormat("en-US", {{
  timeZone: "America/Los_Angeles",
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
  timeZoneName: "short"
}}).format(new Date());

function sortKey(text) {{
  const raw = text.replace(/\\s+mark$/i, "").trim();
  if (raw === "" || raw.toLowerCase() === "open" || raw.toLowerCase() === "none") {{
    return {{ empty: true, n: 0, t: "" }};
  }}
  const numeric = raw.replace(/[$,%]/g, "");
  if (/^[+-]?\\d+(?:\\.\\d+)?$/.test(numeric)) {{
    return {{ empty: false, n: Number(numeric), t: raw.toLowerCase() }};
  }}
  return {{ empty: false, n: NaN, t: raw.toLowerCase() }};
}}

function compareKeys(a, b) {{
  if (a.empty && b.empty) return 0;
  if (a.empty) return 1;
  if (b.empty) return -1;
  if (!Number.isNaN(a.n) && !Number.isNaN(b.n)) return a.n - b.n;
  if (a.t < b.t) return -1;
  if (a.t > b.t) return 1;
  return 0;
}}

function applySort(table, col, dir) {{
  const body = table.tBodies[0];
  if (!body) return;
  const pinned = [];
  const rows = [];
  Array.from(body.rows).forEach((row) => {{
    if (row.hasAttribute("data-stay")) pinned.push(row);
    else rows.push(row);
  }});
  rows.sort((left, right) => {{
    const a = sortKey(left.cells[col] ? left.cells[col].textContent : "");
    const b = sortKey(right.cells[col] ? right.cells[col].textContent : "");
    if (a.empty || b.empty) return compareKeys(a, b);
    return compareKeys(a, b) * dir;
  }});
  rows.concat(pinned).forEach((row) => body.appendChild(row));
  Array.from(table.tHead.rows[0].cells).forEach((th, index) => {{
    th.setAttribute("aria-sort", index === col ? (dir > 0 ? "ascending" : "descending") : "none");
  }});
}}

document.querySelectorAll("section").forEach((section) => {{
  const name = section.querySelector("h2").textContent;
  section.querySelectorAll("table").forEach((table, index) => {{
    if (!table.tHead) return;
    const key = "autobonk-sort:" + name + ":" + index;
    Array.from(table.tHead.rows[0].cells).forEach((th, col) => {{
      th.tabIndex = 0;
      const sort = () => {{
        const dir = th.getAttribute("aria-sort") === "ascending" ? -1 : 1;
        applySort(table, col, dir);
        sessionStorage.setItem(key, JSON.stringify({{ col: col, dir: dir }}));
      }};
      th.addEventListener("click", sort);
      th.addEventListener("keydown", (event) => {{
        if (event.key === "Enter" || event.key === " ") {{
          event.preventDefault();
          sort();
        }}
      }});
    }});
    let saved = null;
    try {{
      saved = JSON.parse(sessionStorage.getItem(key) || "null");
    }} catch (error) {{
      saved = null;
    }}
    if (saved && Number.isInteger(saved.col)) {{
      applySort(table, saved.col, saved.dir === -1 ? -1 : 1);
    }}
  }});
}});
</script>
</body>
</html>
"""


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(ROOT))
    print(OUT)


if __name__ == "__main__":
    main()
