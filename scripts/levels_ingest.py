#!/usr/bin/env python3
"""Arm the live book from the operator's levels note. No model reads it.

The operator posts or forwards the note in #ta and sends ``!levels``.
``autobonk-levels.timer`` runs ``poll`` every minute premarket and in the session,
writes ``alerts/levels.yaml``, and replies in #ta with what it armed.

A note line looks like:

  - AAPL: Res: 349 -> 350.5 -> 353 -> 359.19 / Sup: 345.37 -> 343.8 -> 342.5

Numbers are kept as printed. A ladder out of order, or a number far from the
ticker's others, is armed and flagged in the reply so the operator can resend
that line. A line that cannot be read is not armed.

Commands (from the operator only):

  !levels            arm the note in this message, or the operator's last note
  !levels preview    reply with what would be armed, write nothing
  !levels force      arm a same-day change even if price already crossed it

The first book of a session replaces yesterday's and is armed when written.
A later note the same session replaces only the tickers it names and keeps the
morning's armed_at, so claims and flips already seen stay. A changed number that
price already crossed since then is held back: the checker could act on that
crossing late, and a late entry is still sent live.

  python3 scripts/levels_ingest.py parse < note.txt   # print the book, write nothing
  python3 scripts/levels_ingest.py arm --latest        # an agent arms the newest saved note
  python3 scripts/levels_ingest.py poll                # what the timer runs
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import claim_alerts as claim  # noqa: E402
from discord_ta import normalize_message  # noqa: E402

PT = claim.PT
LEVELS_PATH = claim.LEVELS_PATH
STATE_PATH = ROOT / "alerts" / "levels_ingest.json"
# boingbingbonk. AUTOBONK_OPERATOR_IDS (comma-separated) overrides.
OPERATOR_IDS = {"254654676585152512"}
# A command older than this when first seen is not armed.
STALE_SECONDS = 30 * 60
# A bare !levels looks this far back for the operator's note.
LOOKBACK_SECONDS = 18 * 3600
# A number this far from the ticker's median level is flagged.
FAR = 0.25
SESSION_END = time(13, 10)
DISCORD_EPOCH_MS = 1420070400000

LINE = re.compile(r"^\s*(?:[-•*]\s*)?\$?([A-Za-z]{1,6})\s*:\s*(.*)$")
LABEL = re.compile(r"\b(res(?:istance)?|sup(?:port)?)\s*:", re.I)
ARROW = re.compile(r"\s*(?:-\s*>|→|⟶|➜|➡️?|=>|>|,|\|)\s*")
NUMBER = re.compile(r"^\$?(\d+(?:\.\d+)?)$")
EMPTY = {"", "-", "none", "n/a", "na"}
HEADER = [
    "# allows: long, short, or both. targets are in order. The first does not close the trade.",
    "# A lost support flips to resistance. A claimed resistance flips to support.",
    "# Resistance is long. Support is short.",
]


def parse_note(text: str) -> tuple[dict, list[str], list[str]]:
    """Ladders by ticker, warnings, and errors. A line with an error is left out."""
    books: dict[str, dict] = {}
    warnings: list[str] = []
    errors: list[str] = []
    for raw in text.splitlines():
        line = re.sub(r"[*_~`]", "", raw).strip()
        match = LINE.match(line)
        if not match:
            continue
        ticker, rest = match.group(1).upper(), match.group(2)
        labels = list(LABEL.finditer(rest))
        if not labels:
            continue
        if rest[: labels[0].start()].strip(" /"):
            errors.append(f"{ticker}: could not read `{line}`")
            continue
        ladder = {"res": [], "sup": []}
        bad = None
        for index, label in enumerate(labels):
            end = labels[index + 1].start() if index + 1 < len(labels) else len(rest)
            segment = rest[label.end() : end].strip().rstrip("/").strip()
            side = "res" if label.group(1).lower().startswith("r") else "sup"
            if segment.lower() in EMPTY:
                continue
            for piece in ARROW.split(segment):
                piece = piece.strip()
                if not piece:
                    continue
                number = NUMBER.match(piece)
                if not number:
                    bad = f"{ticker} {side.title()}: `{piece}` is not a number"
                    break
                ladder[side].append(number.group(1))
            if bad:
                break
        if bad:
            errors.append(bad)
            continue
        if ticker in books:
            warnings.append(f"{ticker} is in the note twice. The last line is used.")
        books[ticker] = ladder
        warnings.extend(check_ladder(ticker, ladder))
    return books, warnings, errors


def check_ladder(ticker: str, ladder: dict) -> list[str]:
    found = []
    for side, word, rising in (("res", "Res", True), ("sup", "Sup", False)):
        prices = [float(token) for token in ladder[side]]
        for before, after, token in zip(prices, prices[1:], ladder[side][1:]):
            if (after <= before) if rising else (after >= before):
                way = "lower" if rising else "higher"
                found.append(
                    f"{ticker} {word} {token} is {way} than {_fmt(before)} before it. Kept as printed."
                )
    every = [float(token) for token in ladder["res"] + ladder["sup"]]
    if len(every) >= 3:
        middle = statistics.median(every)
        for side, word in (("res", "Res"), ("sup", "Sup")):
            for token in ladder[side]:
                gap = abs(float(token) - middle) / middle
                if gap > FAR:
                    found.append(
                        f"{ticker} {word} {token} is {gap:.0%} from {ticker}'s other levels. Kept as printed."
                    )
    if ladder["res"] and ladder["sup"]:
        if min(map(float, ladder["res"])) <= max(map(float, ladder["sup"])):
            found.append(f"{ticker} Res and Sup overlap. Kept as printed.")
    return found


def _fmt(value: float) -> str:
    return f"{value:g}"


def _num(token: str) -> int | float:
    return int(token) if "." not in token else float(token)


def build_levels(books: dict) -> list[dict]:
    """The checker's rows: each number targets the ones printed after it."""
    rows = []
    for ticker, ladder in books.items():
        for side, kind, allows, word in (
            ("res", "claim", "long", "Resistance"),
            ("sup", "lose", "short", "Support"),
        ):
            tokens = ladder[side]
            for index, token in enumerate(tokens):
                after = tokens[index + 1 :]
                if index:
                    note = f"Then {token}"
                elif after:
                    note = f"{word} {token}, then {', '.join(after)}"
                else:
                    note = f"{word} {token}"
                rows.append(
                    {
                        "ticker": ticker,
                        "price": _num(token),
                        "side": kind,
                        "allows": allows,
                        "targets": [_num(item) for item in after],
                        "note": note,
                    }
                )
    return rows


def arm_time(moment: datetime) -> datetime:
    """Now, or 04:00 PT on the next weekday when the session is over or it is a weekend."""
    local = moment.astimezone(PT).replace(microsecond=0)
    if local.weekday() < 5 and local.time() < SESSION_END:
        return local
    day = local.date() + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return datetime.combine(day, time(4, 0), PT)


def _read_book(path: Path) -> tuple[list[str], dict | None]:
    if not path.is_file():
        return [], None
    text = path.read_text()
    header = []
    for line in text.splitlines():
        if not line.startswith("#"):
            break
        header.append(line)
    return header, yaml.safe_load(text)


def crossed(ticker: str, prices: list[float], since: datetime, now: datetime, fetch=None) -> list[float]:
    """Numbers price already traded through between `since` and `now`."""
    fetch = fetch or claim.fetch_five_minute
    bars = [
        bar
        for bar in claim.ten_minute_bars(fetch(ticker), int(now.timestamp()) + 1)
        if int(since.timestamp()) < bar["close_at"] <= int(now.timestamp())
    ]
    if not bars:
        return []
    low = min(bar["l"] for bar in bars)
    high = max(bar["h"] for bar in bars)
    return [price for price in prices if low <= price <= high]


def arm(
    books: dict,
    now: datetime,
    path: Path = LEVELS_PATH,
    source: str = "",
    force: bool = False,
    fetch=None,
    warnings: list[str] | None = None,
    described: str = "",
) -> dict:
    """Write the book. Returns what changed for the reply."""
    warnings = warnings if warnings is not None else []
    header, old = _read_book(path)
    armed = arm_time(now)
    stamp = armed.strftime("%H:%M PT")
    note_of = f"the operator's {now.astimezone(PT):%Y-%m-%d %H:%M} PT note"
    if source:
        note_of += f" (Discord message {source})"
    if described:
        note_of = described
    old_armed = None
    if old and old.get("armed_at"):
        old_armed = datetime.fromisoformat(str(old["armed_at"]))
        if old_armed.tzinfo is None:
            old_armed = old_armed.replace(tzinfo=PT)
    same_session = old_armed is not None and old_armed.astimezone(PT).date() == armed.date()
    held: dict[str, list[float]] = {}
    if same_session:
        rows = list(old.get("levels") or [])
        if not force and armed > old_armed:
            for ticker, ladder in books.items():
                before = {
                    (row["side"], float(row["price"])) for row in rows if row["ticker"] == ticker
                }
                fresh = [
                    float(token)
                    for side, kind in (("res", "claim"), ("sup", "lose"))
                    for token in ladder[side]
                    if (kind, float(token)) not in before
                ]
                if not fresh:
                    continue
                try:
                    hit = crossed(ticker, fresh, old_armed, armed, fetch)
                except (SystemExit, OSError) as exc:
                    held[ticker] = []
                    warnings.append(
                        f"{ticker} not changed: its bars could not be read ({type(exc).__name__})."
                    )
                    continue
                if hit:
                    held[ticker] = hit
        armed_at = old_armed
        changed = {ticker: ladder for ticker, ladder in books.items() if ticker not in held}
        order = []
        for row in rows:
            if row["ticker"] not in order:
                order.append(row["ticker"])
        order += [ticker for ticker in changed if ticker not in order]
        fresh_rows = build_levels(changed)
        levels = []
        for ticker in order:
            source_rows = fresh_rows if ticker in changed else rows
            levels += [row for row in source_rows if row["ticker"] == ticker]
        names = ", ".join(changed) or "nothing"
        header = header + [f"# {armed:%H:%M} PT: {names} replaced from {note_of}."]
        mode = "merged"
    else:
        changed = books
        armed_at = armed
        levels = build_levels(books)
        header = [
            f"# Levels from {note_of}.",
            f"# Written by scripts/levels_ingest.py and armed at {stamp}. Numbers are as printed.",
            *HEADER,
        ]
        mode = "new"
    header += [f"# {line}" for line in warnings if line.split(" ", 1)[0] in changed]
    if changed:
        body = yaml.safe_dump(
            {"armed_at": armed_at.isoformat(), "levels": levels},
            sort_keys=False,
            allow_unicode=True,
        )
        if path.is_file():
            (path.parent / "levels.prev.yaml").write_text(path.read_text())
        tmp = path.with_suffix(".tmp")
        tmp.write_text("\n".join(header) + "\n" + body)
        os.replace(tmp, path)
    return {
        "mode": mode,
        "armed_at": armed_at,
        "tickers": list(changed),
        "levels": sum(len(books[t]["res"]) + len(books[t]["sup"]) for t in changed),
        "held": held,
        "book": len(levels),
    }


def ladder_lines(books: dict) -> list[str]:
    lines = []
    for ticker, ladder in books.items():
        res = " › ".join(ladder["res"]) or "—"
        sup = " › ".join(ladder["sup"]) or "—"
        lines.append(f"`{ticker}` R {res} | S {sup}")
    return lines


def reply_text(books, warnings, errors, result=None, preview=False) -> str:
    lines = []
    if preview:
        lines.append(f"Preview: {len(books)} tickers read. Nothing armed.")
    elif result:
        when = result["armed_at"].astimezone(PT)
        if result["mode"] == "new":
            lines.append(
                f"Armed a new book for {when:%a %m/%d}: {len(result['tickers'])} tickers, "
                f"{result['levels']} levels, armed {when:%H:%M} PT."
            )
        elif result["tickers"]:
            lines.append(
                f"Replaced {', '.join(result['tickers'])} in today's book "
                f"(still armed {when:%H:%M} PT, {result['book']} levels)."
            )
        else:
            lines.append("Nothing changed.")
        for ticker, hit in result["held"].items():
            if hit:
                lines.append(
                    f"✋ {ticker} not changed: price already crossed "
                    f"{', '.join(_fmt(p) for p in hit)} since {when:%H:%M} PT, so the checker could "
                    "act on it late. Send `!levels force` with the line to arm it anyway."
                )
    shown = set(result["tickers"]) if result and not preview else set(books)
    lines += [line for line in ladder_lines(books) if line.split("`")[1] in shown]
    lines += [f"⚠️ {line}" for line in warnings]
    lines += [f"❌ {line} Not armed." for line in errors]
    lines.append("Not an order.")
    text = "\n".join(lines)
    return text if len(text) <= 1900 else text[:1880] + "\n…"


# --- Discord ---------------------------------------------------------------


def _operators() -> set[str]:
    raw = os.environ.get("AUTOBONK_OPERATOR_IDS", "")
    found = {item.strip() for item in raw.split(",") if item.strip()}
    return found or OPERATOR_IDS


def _snowflake(moment: float) -> int:
    return (int(moment * 1000) - DISCORD_EPOCH_MS) << 22


def _posted(message: dict) -> datetime:
    return datetime.fromisoformat(message["timestamp"].replace("Z", "+00:00"))


def command_of(message: dict, operators: set[str]) -> tuple[set[str], str] | None:
    """The flags and note text of an operator's !levels, else None."""
    if message.get("bot") or str(message.get("author_id")) not in operators:
        return None
    content = (message.get("content") or "").strip()
    first, _, rest = content.partition("\n")
    words = first.split()
    if not words or words[0].lower() != "!levels":
        return None
    flags = set()
    tail = words[1:]
    while tail and tail[0].lower() in ("preview", "force"):
        flags.add(tail.pop(0).lower())
    return flags, "\n".join(part for part in (" ".join(tail), rest) if part)


def _load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def poll(
    now: datetime | None = None,
    get=None,
    post=None,
    path: Path = LEVELS_PATH,
    state_path: Path = STATE_PATH,
    fetch=None,
) -> list[str]:
    """Handle new !levels commands in #ta. Returns the replies sent."""
    now = now or datetime.now(PT)
    if get is None or post is None:
        token = claim._token()
        get = get or (lambda route: claim._discord_get(token, route))
        post = post or (lambda route, body: claim._discord_call(token, route, body))
    state = _load_state(state_path)
    channel = state.get("channel") or claim._ta_channel(claim._token())
    floor = _snowflake(now.timestamp() - STALE_SECONDS)
    after = max(int(state.get("last_id") or 0), floor)
    rows = get(f"/channels/{channel}/messages?after={after}&limit=100") or []
    messages = sorted((normalize_message(row) for row in rows), key=lambda m: int(m["id"]))
    operators = _operators()
    replies = []
    for message in messages:
        found = command_of(message, operators)
        if found is None:
            continue
        flags, text = found
        books, warnings, errors = parse_note(text)
        if not books and not errors:
            books, warnings, errors = _last_note(get, channel, message, operators)
        if not books:
            reply = "❌ No levels found. Put the note in the same message, or forward it first.\nNot an order."
            if errors:
                reply = reply_text(books, warnings, errors)
        elif "preview" in flags:
            reply = reply_text(books, warnings, errors, preview=True)
        else:
            result = arm(
                books,
                _posted(message),
                path=path,
                source=message["id"],
                force="force" in flags,
                fetch=fetch,
                warnings=warnings,
            )
            reply = reply_text(books, warnings, errors, result)
        post(
            f"/channels/{channel}/messages",
            {"content": reply, "message_reference": {"message_id": message["id"]}},
        )
        replies.append(reply)
    if messages:
        state["last_id"] = str(max(int(m["id"]) for m in messages))
    state["channel"] = channel
    state_path.write_text(json.dumps(state) + "\n")
    return replies


def _last_note(get, channel: str, command: dict, operators: set[str]):
    rows = get(f"/channels/{channel}/messages?before={command['id']}&limit=50") or []
    oldest = _posted(command).timestamp() - LOOKBACK_SECONDS
    for row in sorted(rows, key=lambda r: int(r["id"]), reverse=True):
        message = normalize_message(row)
        if message.get("bot") or str(message.get("author_id")) not in operators:
            continue
        if _posted(message).timestamp() < oldest:
            break
        books, warnings, errors = parse_note(message.get("content") or "")
        if books or errors:
            return books, warnings, errors
    return {}, [], []


def _latest_note(inbox: Path) -> Path | None:
    """The newest saved #ta post from a person whose text has a ladder."""
    for path in sorted(inbox.glob("*.json"), key=lambda p: int(p.stem), reverse=True):
        record = json.loads(path.read_text())
        if record.get("bot") or record.get("author") == "ta-bot":
            continue
        if parse_note(record.get("content") or "")[0]:
            return path
    return None


def arm_command(args) -> int:
    """Arm from a saved #ta post or note text. Prints the summary and the charts to read."""
    images: list[str] = []
    source = ""
    if args.latest:
        found = _latest_note(Path(args.inbox))
        if found is None:
            print("No saved note with levels in charts/inbox. Run discord_ta.py ingest first.")
            return 1
        args.file = str(found)
    if not args.file or args.file == "-":
        text = sys.stdin.read()
    elif args.file.endswith(".json"):
        record = json.loads(Path(args.file).read_text())
        text = record.get("content") or ""
        source = str(record.get("id") or "")
        images = [item["file"] for item in record.get("attachments") or [] if item.get("file")]
    else:
        text = Path(args.file).read_text()
    books, warnings, errors = parse_note(text)
    if not books:
        print(reply_text(books, warnings, errors) if errors else "No levels found in that note.")
        return 1
    result = arm(
        books,
        datetime.now(PT),
        path=Path(args.book),
        source=source,
        force=args.force,
        warnings=warnings,
        described=args.described or "",
    )
    print(reply_text(books, warnings, errors, result))
    if images:
        print("Charts: " + " ".join(images))
    return 0 if result["tickers"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Arm alerts/levels.yaml from the operator's note")
    sub = parser.add_subparsers(dest="command", required=True)
    parse_cmd = sub.add_parser("parse", help="Print the book a note makes. Writes nothing.")
    parse_cmd.add_argument("file", nargs="?", help="Note text (default: stdin)")
    arm_cmd = sub.add_parser("arm", help="Arm a saved #ta post (.json), a text file, or stdin")
    arm_cmd.add_argument("file", nargs="?", help="charts/inbox/<id>.json, a text file, or - for stdin")
    arm_cmd.add_argument("--latest", action="store_true", help="The newest saved note in charts/inbox")
    arm_cmd.add_argument("--force", action="store_true", help="Arm numbers price already crossed")
    arm_cmd.add_argument("--from", dest="described", help="Where the numbers came from, for the header")
    arm_cmd.add_argument("--book", default=str(LEVELS_PATH), help=argparse.SUPPRESS)
    arm_cmd.add_argument("--inbox", default=str(ROOT / "charts" / "inbox"), help=argparse.SUPPRESS)
    sub.add_parser("poll", help="Handle !levels commands in #ta")
    args = parser.parse_args(argv)
    if args.command == "parse":
        text = Path(args.file).read_text() if args.file else sys.stdin.read()
        books, warnings, errors = parse_note(text)
        print(yaml.safe_dump({"levels": build_levels(books)}, sort_keys=False, allow_unicode=True))
        for line in warnings:
            print(f"warning: {line}", file=sys.stderr)
        for line in errors:
            print(f"error: {line}", file=sys.stderr)
        return 1 if errors else 0
    if args.command == "arm":
        return arm_command(args)
    for reply in poll():
        print(reply)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
