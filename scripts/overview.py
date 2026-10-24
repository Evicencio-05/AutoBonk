"""The desk's Overview tab and Trades table, drawn from the trade ledger.

Everything is server-rendered HTML and inline SVG, so the hosted desk needs no
chart library. Dollars are one contract: broker fills for live rows, the plan
contract's premiums for signals that sent no order ("what-if"). Nothing here
places an order.
"""

from __future__ import annotations

import html
from collections import defaultdict

W, H = 720, 220
PAD_L, PAD_R, PAD_T, PAD_B = 52, 86, 14, 28
BAR_MAX = 24
MODES = {"live": "Live", "plan": "What-if", "paper": "Paper"}


def _esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _money(value, signed: bool = True) -> str:
    if value is None:
        return "–"
    sign = "+" if signed and value > 0 else "−" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def _dollars(row: dict) -> float | None:
    return row.get("dollars") if row.get("mode") == "live" else row.get("plan_dollars")


def _stats(rows: list[dict], mode: str) -> dict:
    values = [_dollars(row) for row in rows if row.get("mode") == mode and _dollars(row) is not None]
    wins = [v for v in values if v > 0]
    losses = [v for v in values if v <= 0]
    return {
        "n": len(values),
        "net": round(sum(values), 2),
        "win_rate": round(100 * len(wins) / len(values)) if values else None,
        "expectancy": round(sum(values) / len(values), 2) if values else None,
        "avg_win": round(sum(wins) / len(wins), 2) if wins else None,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else None,
        "profit_factor": round(sum(wins) / -sum(losses), 2) if losses and sum(losses) else None,
    }


def _nice_ticks(low: float, high: float, count: int = 4) -> list[float]:
    span = max(high - low, 1e-9)
    raw = span / count
    magnitude = 10 ** len(str(int(raw))) / 10 if raw >= 1 else 1
    for step in (1, 2, 2.5, 5, 10):
        if raw <= step * magnitude:
            step *= magnitude
            break
    start = (low // step) * step
    ticks = []
    value = start
    while value <= high + step * 0.5:
        ticks.append(round(value, 2))
        value += step
    return ticks


def _axis(ticks: list[float], y, w: int) -> str:
    lines = []
    for tick in ticks:
        lines.append(
            f"<line class='grid{' zero' if tick == 0 else ''}' x1='{PAD_L}' x2='{w - PAD_R}' y1='{y(tick):.1f}' y2='{y(tick):.1f}'/>"
            f"<text class='tick' x='{PAD_L - 8}' y='{y(tick) + 4:.1f}' text-anchor='end'>{_esc(_short(tick))}</text>"
        )
    return "".join(lines)


def _short(value: float) -> str:
    sign = "−" if value < 0 else ""
    value = abs(value)
    if value >= 1000:
        return f"{sign}${value / 1000:g}K"
    return f"{sign}${value:g}"


def _scale(values: list[float], h: int):
    low = min(values + [0.0])
    high = max(values + [0.0])
    if high == low:
        high = low + 1
    ticks = _nice_ticks(low, high)
    low, high = min(ticks + [low]), max(ticks + [high])

    def y(value: float) -> float:
        return PAD_T + (high - value) / (high - low) * (h - PAD_T - PAD_B)

    return y, ticks


def _series(rows: list[dict], mode: str) -> list[tuple[dict, float]]:
    running = 0.0
    out = []
    for row in sorted((r for r in rows if r.get("mode") == mode and _dollars(r) is not None), key=lambda r: r["close_at"]):
        running += _dollars(row)
        out.append((row, round(running, 2)))
    return out


def _sized(draw, label: str, wide: tuple[int, int], narrow: tuple[int, int]) -> str:
    """The same chart drawn at two widths, so its text stays near true size. CSS shows one."""
    return "".join(
        f"<svg class='chart {size}' viewBox='0 0 {w} {h}' role='img' aria-label='{_esc(label)}'>{draw(w, h)}</svg>"
        for size, (w, h) in (("wide-only", wide), ("narrow-only", narrow))
    )


def equity_chart(rows: list[dict]) -> str:
    """Cumulative dollars by signal order, live and what-if, on one dollar axis."""
    lines = {mode: _series(rows, mode) for mode in ("live", "plan")}
    if not any(lines.values()):
        return "<p class='empty'>No scored trades yet.</p>"
    legend = "".join(
        f"<span class='key'><i class='swatch s{slot}'></i>{_esc(MODES[mode])}</span>"
        for slot, (mode, series) in enumerate(lines.items(), start=1)
        if series
    )
    table = _table(
        ["Signal", "Mode", "$", "Running total"],
        [[row["ref"], MODES[mode], _money(_dollars(row)), _money(value)] for mode, series in lines.items() for row, value in series],
    )
    return (
        f"<div class='legend'>{legend}</div>"
        + _sized(lambda w, h: _equity_svg(lines, w, h), "Running dollars by signal, live and what-if", (1080, 260), (420, 300))
        + f"<details><summary>Show as table</summary>{table}</details>"
    )


def _equity_svg(lines: dict, w: int, h: int) -> str:
    every = sorted({row["close_at"] for series in lines.values() for row, _ in series})
    x_of = {stamp: index for index, stamp in enumerate(every)}
    span = max(len(every) - 1, 1)

    def x(stamp: int) -> float:
        return PAD_L + x_of[stamp] / span * (w - PAD_L - PAD_R)

    y, ticks = _scale([value for series in lines.values() for _, value in series], h)
    parts = [_axis(ticks, y, w)]
    for slot, (mode, series) in enumerate(lines.items(), start=1):
        if not series:
            continue
        points = " ".join(f"{x(row['close_at']):.1f},{y(value):.1f}" for row, value in series)
        parts.append(f"<polyline class='line s{slot}' points='{points}'/>")
        for row, value in series:
            tip = f"{MODES[mode]} · {row['ref']} · {_money(_dollars(row))} · total {_money(value)}"
            parts.append(
                f"<circle class='dot s{slot}' cx='{x(row['close_at']):.1f}' cy='{y(value):.1f}' r='4'/>"
                f"<circle class='hit' cx='{x(row['close_at']):.1f}' cy='{y(value):.1f}' r='12' tabindex='0' data-tip='{_esc(tip)}'/>"
            )
        last_row, last = series[-1]
        parts.append(
            f"<text class='end-label' x='{x(last_row['close_at']) + 10:.1f}' y='{y(last) + 4:.1f}'>"
            f"{_esc(MODES[mode])} {_esc(_money(last))}</text>"
        )
    return "".join(parts)


def _bucket_key(row: dict, cut: str) -> str:
    if cut == "entry":
        number = row.get("level_entry_number") or 1
        return "1st at level" if number == 1 else "2nd at level" if number == 2 else "3rd+ at level"
    if cut == "hour":
        minutes = row.get("minutes_after_open")
        if minutes is None:
            return "?"
        hour = 6 + (30 + minutes) // 60
        return f"{hour % 12 or 12}{'am' if hour < 12 else 'pm'}"
    if cut == "premium":
        price = row.get("entry_fill") if row.get("mode") == "live" else row.get("plan_entry_premium")
        if price is None:
            return "?"
        return "under $0.20" if price < 0.2 else "$0.20–0.50" if price < 0.5 else "$0.50–1" if price < 1 else "$1+"
    return str(row.get(cut) or "?")


def group_chart(rows: list[dict], cut: str, title: str, order: list[str] | None = None) -> str:
    """Live and what-if net dollars per group, as columns from a zero baseline."""
    sums: dict[str, dict[str, list[float]]] = defaultdict(lambda: {"live": [], "plan": []})
    for row in rows:
        if row.get("mode") in ("live", "plan") and _dollars(row) is not None:
            sums[_bucket_key(row, cut)][row["mode"]].append(_dollars(row))
    if not sums:
        return ""
    names = [name for name in (order or sorted(sums)) if name in sums]
    values = [sum(v) for group in sums.values() for v in group.values() if v]
    legend = (
        "<div class='legend'><span class='key'><i class='swatch s1'></i>Live</span>"
        "<span class='key'><i class='swatch s2'></i>What-if</span></div>"
    )
    table = _table(
        ["Group", "Live n", "Live $", "What-if n", "What-if $"],
        [
            [name, len(sums[name]["live"]), _money(sum(sums[name]["live"])) if sums[name]["live"] else "–",
             len(sums[name]["plan"]), _money(sum(sums[name]["plan"])) if sums[name]["plan"] else "–"]
            for name in names
        ],
    )
    return (
        f"<div class='chart-card'><h3>{_esc(title)}</h3>{legend}"
        + _sized(lambda w, h: _group_svg(sums, names, values, w, h), title, (520, 230), (380, 250))
        + f"<details><summary>Show as table</summary>{table}</details></div>"
    )


def _group_svg(sums: dict, names: list[str], values: list[float], w: int, h: int) -> str:
    y, ticks = _scale(values, h)
    band = (w - PAD_L - 16) / len(names)
    bar = min(BAR_MAX, band / 3)
    # _axis ends at w - PAD_R; group charts have no end labels, so their plot runs to 16px from the edge.
    parts = [_axis(ticks, y, w - 16 + PAD_R)]
    for index, name in enumerate(names):
        center = PAD_L + band * (index + 0.5)
        for slot, mode in enumerate(("live", "plan"), start=1):
            got = sums[name][mode]
            if not got:
                continue
            total = round(sum(got), 2)
            left = center + (-bar - 1 if slot == 1 else 1)
            top, bottom = sorted((y(total), y(0)))
            height = max(bottom - top, 1)
            radius = min(4, height / 2)
            parts.append(_column(left, top, bar, height, radius, total >= 0, slot))
            tip = f"{name} · {MODES[mode]} · {len(got)} trades · {_money(total)}"
            parts.append(
                f"<rect class='hit' x='{left - 4:.1f}' y='{PAD_T}' width='{bar + 8:.1f}' height='{h - PAD_T - PAD_B}' tabindex='0' data-tip='{_esc(tip)}'/>"
            )
            label_y = top - 6 if total >= 0 else bottom + 14
            parts.append(f"<text class='value' x='{left + bar / 2:.1f}' y='{label_y:.1f}' text-anchor='middle'>{_esc(_short(total))}</text>")
        parts.append(f"<text class='tick' x='{center:.1f}' y='{h - 8}' text-anchor='middle'>{_esc(name)}</text>")
    return "".join(parts)


def _column(x: float, top: float, width: float, height: float, radius: float, up: bool, slot: int) -> str:
    """A column with a 4px rounded data end and a square baseline end."""
    r = radius
    if up:
        path = (
            f"M{x:.1f},{top + height:.1f} V{top + r:.1f} Q{x:.1f},{top:.1f} {x + r:.1f},{top:.1f} "
            f"H{x + width - r:.1f} Q{x + width:.1f},{top:.1f} {x + width:.1f},{top + r:.1f} V{top + height:.1f} Z"
        )
    else:
        bottom = top + height
        path = (
            f"M{x:.1f},{top:.1f} V{bottom - r:.1f} Q{x:.1f},{bottom:.1f} {x + r:.1f},{bottom:.1f} "
            f"H{x + width - r:.1f} Q{x + width:.1f},{bottom:.1f} {x + width:.1f},{bottom - r:.1f} V{top:.1f} Z"
        )
    return f"<path class='bar s{slot}' d='{path}'/>"


def _table(head: list[str], body: list[list]) -> str:
    rows = "".join("<tr>" + "".join(f"<td>{_esc(cell)}</td>" for cell in row) + "</tr>" for row in body)
    return f"<table><thead><tr>{''.join(f'<th>{_esc(h)}</th>' for h in head)}</tr></thead><tbody>{rows}</tbody></table>"


def _tile(label: str, value: str, note: str = "", tone: str = "") -> str:
    return (
        f"<div class='tile{(' ' + tone) if tone else ''}'><span>{_esc(label)}</span>"
        f"<strong>{_esc(value)}</strong>{f'<small>{_esc(note)}</small>' if note else ''}</div>"
    )


def overview(rows: list[dict], alarms: dict, freeze: dict) -> str:
    live = _stats(rows, "live")
    plan = _stats(rows, "plan")
    closed, target = freeze.get("closed", 0), freeze.get("target") or 0
    share = min(100, round(100 * closed / target)) if target else 0
    if alarms:
        alarm_tile = (
            "<div class='tile alert' role='status'><span>Alarms</span>"
            f"<strong><b aria-hidden='true'>!</b> {len(alarms)} raised</strong>"
            + "".join(f"<small>{_esc(item.get('text'))}</small>" for item in list(alarms.values())[:3])
            + "</div>"
        )
    else:
        alarm_tile = "<div class='tile ok' role='status'><span>Alarms</span><strong><b aria-hidden='true'>✓</b> None raised</strong></div>"
    hero = (
        "<div class='hero'>"
        "<div><span class='hero-label'>Live result, all time, one contract</span>"
        f"<strong class='hero-value'>{_esc(_money(live['net']))}</strong>"
        f"<p class='hero-note'>{live['n']} closed live trade{'s' if live['n'] != 1 else ''}. "
        f"Signals that sent no order would have made {_esc(_money(plan['net']))} over {plan['n']}.</p></div>"
        "<div class='freeze'>"
        f"<span class='hero-label'>Rule freeze {'on' if freeze.get('active') else 'off'}"
        f"{' since ' + _esc(freeze.get('started')) if freeze.get('started') else ''}</span>"
        f"<div class='meter' role='meter' aria-valuemin='0' aria-valuemax='{target}' aria-valuenow='{closed}' "
        f"aria-label='Closed live trades toward the freeze target'><i style='width:{share}%'></i></div>"
        f"<small>{closed} of {target} closed live trades. Net since the start {_esc(_money(freeze.get('net')))}.</small>"
        "</div></div>"
    )
    tiles = (
        "<div class='tiles'>"
        + _tile("Win rate", "–" if live["win_rate"] is None else f"{live['win_rate']}%", f"{live['n']} live trades")
        + _tile("Per trade", _money(live["expectancy"]), "average live result")
        + _tile("Average win / loss", f"{_money(live['avg_win'])} / {_money(live['avg_loss'])}")
        + _tile("Profit factor", "–" if live["profit_factor"] is None else f"{live['profit_factor']}", "gains ÷ losses")
        + _tile("What-if per signal", _money(plan["expectancy"]), f"{plan['n']} signals with no order")
        + alarm_tile
        + "</div>"
    )
    charts = (
        "<div class='chart-card wide'><h3>Running dollars by signal</h3>"
        "<p class='sub'>Each point is one closed signal, in time order. Live is what the broker filled; what-if is the plan contract for signals that sent no order.</p>"
        f"{equity_chart(rows)}</div>"
        "<div class='chart-grid'>"
        + group_chart(rows, "entry", "Entry number at a level", ["1st at level", "2nd at level", "3rd+ at level"])
        + group_chart(rows, "hour", "Entry hour (PT)", ["6am", "7am", "8am", "9am", "10am", "11am", "12pm"])
        + group_chart(rows, "premium", "Contract price at entry", ["under $0.20", "$0.20–0.50", "$0.50–1", "$1+"])
        + group_chart(rows, "exit_reason", "Exit reason")
        + "</div>"
        "<p class='sub'>Fewer than 10 trades in a group is an anecdote. Decide rule changes in the weekly review.</p>"
    )
    return hero + tiles + charts


def trades_table(rows: list[dict]) -> str:
    if not rows:
        return "<p class='empty'>The ledger is empty. Run <code>python3 scripts/ledger.py sync</code>.</p>"
    chips = "".join(
        f"<button type='button' class='chip' data-mode='{mode}' aria-pressed='{'true' if mode == 'all' else 'false'}'>{label}</button>"
        for mode, label in (("all", "All"), ("live", "Live"), ("plan", "What-if"), ("paper", "Paper"))
    )
    head = ["Day", "Time", "Ticker", "Side", "Level", "# at level", "Contract", "Mode", "In", "Out", "$", "Best $", "Worst $", "Exit", "You'd take", "Note"]
    body = []
    for row in sorted(rows, key=lambda r: r["close_at"], reverse=True):
        live = row.get("mode") == "live"
        dollars = _dollars(row)
        best = row.get("mfe_dollars") if live else row.get("plan_mfe_dollars")
        worst = row.get("mae_dollars") if live else row.get("plan_mae_dollars")
        tone = "up" if (dollars or 0) > 0 else "down" if (dollars or 0) < 0 else ""
        cells = [
            row.get("day"), (row.get("entry_time") or "")[11:16], row.get("ticker"), row.get("side"),
            row.get("level"), row.get("level_entry_number"), row.get("contract"), MODES.get(row.get("mode"), row.get("mode")),
            row.get("entry_fill") if live else row.get("plan_entry_premium"),
            row.get("exit_fill") if live else row.get("plan_exit_premium"),
            _money(dollars), _money(best), _money(worst),
            row.get("exit_reason") or row.get("outcome"), row.get("operator_take") or "", row.get("operator_note") or "",
        ]
        tds = []
        for index, cell in enumerate(cells):
            klass = ""
            if index == 2:
                klass = " class='ticker'"
            elif index == 3:
                klass = f" class='{_esc(row.get('side'))}'"
            elif index == 10 and tone:
                klass = f" class='{tone}'"
            tds.append(f"<td{klass}>{_esc('' if cell is None else cell)}</td>")
        body.append(f"<tr data-mode='{_esc(row.get('mode'))}' title='{_esc(row.get('ref'))}'>{''.join(tds)}</tr>")
    return (
        f"<div class='chips' role='group' aria-label='Show trades'>{chips}</div>"
        f"<p class='sub'>Newest first. Click a column to sort. Dollars are one contract.</p>"
        f"<table id='ledger-table'><thead><tr>{''.join(f'<th>{_esc(h)}</th>' for h in head)}</tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table>"
    )


# ---- proposals ---------------------------------------------------------------

def _inline(text: str) -> str:
    """**bold** and `code` inside one escaped line."""
    import re

    text = _esc(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", text)


def markdown(text: str) -> str:
    """Enough Markdown for a proposal: headings, paragraphs, lists, tables, code blocks."""
    if text.startswith("---\n"):
        text = text[4:].split("\n---", 1)[-1].lstrip("-\n")
    out: list[str] = []
    para: list[str] = []
    listing = ""
    table: list[list[str]] = []
    code: list[str] | None = None

    def flush() -> None:
        nonlocal listing, table
        if para:
            out.append(f"<p>{_inline(' '.join(para))}</p>")
            para.clear()
        if listing:
            out.append(f"</{listing}>")
            listing = ""
        if table:
            head, *rest = [row for row in table if not set("".join(row)) <= set("-: ")]
            out.append(
                "<table data-nosort><thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in head) + "</tr></thead><tbody>"
                + "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in row) + "</tr>" for row in rest)
                + "</tbody></table>"
            )
            table = []

    for line in text.splitlines():
        if code is not None:
            if line.startswith("```"):
                out.append(f"<pre class='sheet'>{_esc(chr(10).join(code))}</pre>")
                code = None
            else:
                code.append(line)
            continue
        stripped = line.strip()
        if stripped.startswith("```"):
            flush()
            code = []
        elif stripped.startswith("<!--"):
            continue
        elif stripped.startswith("#"):
            flush()
            level = min(len(stripped) - len(stripped.lstrip("#")) + 2, 5)
            out.append(f"<h{level}>{_inline(stripped.lstrip('#').strip())}</h{level}>")
        elif stripped.startswith("|"):
            if para or listing:
                flush()
            table.append([cell.strip() for cell in stripped.strip("|").split("|")])
        elif stripped[:2] in ("- ", "* ") or (stripped[:1].isdigit() and ". " in stripped[:4]):
            kind = "ul" if stripped[:2] in ("- ", "* ") else "ol"
            if para or table or (listing and listing != kind):
                flush()
            if not listing:
                out.append(f"<{kind}>")
                listing = kind
            out.append(f"<li>{_inline(stripped.split(' ', 1)[1] if ' ' in stripped else '')}</li>")
        elif not stripped:
            flush()
        else:
            if listing or table:
                flush()
            para.append(stripped)
    flush()
    return "".join(out)


def proposals_panel(root) -> str:
    import proposal_data

    rows = proposal_data.proposals(root / "learning" / "proposals")
    if not rows:
        return "<p class='empty'>No proposals yet. The weekly run drafts them Friday after the close.</p>"
    order = {"open": 0, "accepted": 1, "waiting": 2, "rejected": 3}
    rows.sort(key=lambda p: (order.get(p["status"], 4), p["created"]))
    cards = []
    for item in rows:
        text = (root / item["file"]).read_text()
        summary = ""
        if "## Summary" in text:
            summary = text.split("## Summary", 1)[1].split("\n## ", 1)[0].strip()
        decided = item["operator_decision"] or ("–" if item["status"] == "open" else item["status"])
        cards.append(
            f"<article class='proposal {_esc(item['status'])}'>"
            f"<div class='proposal-head'><span class='pill'>{_esc(item['kind'])}</span>"
            f"<span class='pill status'>{_esc(item['status'])}</span>"
            f"<small>{_esc(item['created'])} · recommends <b>{_esc(item['recommendation'] or '–')}</b> · you: <b>{_esc(decided)}</b></small></div>"
            f"<h3>{_esc(item['title'])}</h3><p>{_inline(' '.join(summary.split()))}</p>"
            f"<details><summary>Read the proposal</summary><div class='doc'>{markdown(text)}</div>"
            f"<p class='sub'>File: <code>{_esc(item['file'])}</code>. Write your decision under Operator decision, or tell Claude.</p></details>"
            "</article>"
        )
    return "<p class='sub'>Open first. Decision proposals are decided at the weekly review; safety notes any day.</p>" + "".join(cards)
