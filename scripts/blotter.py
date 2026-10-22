"""Trade rows the website reads without a git push.

The checker still writes the markdown files. When POSTGRES_URL or DATABASE_URL
is set, a new line is also stored here. The site adds those lines to the copy
of the file that was deployed.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env.local"
KINDS = {
    "live.md": "live",
    "paper.md": "paper",
    "log.md": "log",
    "context.md": "context",
}


def connection_string() -> str:
    _load_local()
    for key in ("POSTGRES_URL", "DATABASE_URL"):
        value = os.environ.get(key, "").strip().strip('"').strip("'")
        if value:
            return value
    return ""


def _load_local() -> None:
    if not ENV_FILE.is_file():
        return
    for line in ENV_FILE.read_text().splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if os.environ.get(key, "").strip():
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


def store(kind: str, lines: list[str]) -> None:
    rows = [line.strip() for line in lines if line and line.strip()]
    if not rows or not connection_string():
        return
    try:
        _insert(kind, rows)
    except Exception:
        return


def merge(filename: str, text: str) -> str:
    kind = KINDS.get(filename)
    if kind is None or not connection_string():
        return text
    try:
        rows = _select(kind)
    except Exception:
        return text
    return append_missing(kind, text, rows)


def append_missing(kind: str, text: str, rows: list[str]) -> str:
    fresh = []
    for row in rows:
        row = row.strip()
        if row and row not in fresh:
            fresh.append(row)
    if not fresh:
        return text
    if kind == "log":
        existing = {line[2:].strip() for line in text.splitlines() if line.startswith("- ")}
        added = [row for row in fresh if row not in existing]
        if not added:
            return text
        extra = "\n".join(f"- {row}" for row in added)
        return text.rstrip() + "\n" + extra + "\n"
    existing = {line.strip() for line in text.splitlines() if line.startswith("|")}
    added = [row for row in fresh if row not in existing]
    if not added:
        return text
    addition = "\n".join(added) + "\n"
    head, separator, marks = text.partition("\n## Open marks\n")
    if separator:
        return head.rstrip() + "\n" + addition + "\n## Open marks\n" + marks
    return text.rstrip() + "\n" + addition


def _connect():
    import psycopg

    return psycopg.connect(connection_string(), connect_timeout=5, prepare_threshold=None)


def _insert(kind: str, rows: list[str]) -> None:
    with _connect() as conn:
        conn.execute(
            """
            create table if not exists trade_rows (
                kind text not null,
                line text not null,
                primary key (kind, line)
            )
            """
        )
        with conn.cursor() as cur:
            cur.executemany(
                "insert into trade_rows (kind, line) values (%s, %s) on conflict do nothing",
                [(kind, row) for row in rows],
            )
        conn.commit()


def _select(kind: str) -> list[str]:
    with _connect() as conn:
        conn.execute(
            """
            create table if not exists trade_rows (
                kind text not null,
                line text not null,
                primary key (kind, line)
            )
            """
        )
        found = conn.execute(
            "select line from trade_rows where kind = %s order by line",
            (kind,),
        ).fetchall()
    return [row[0] for row in found]
