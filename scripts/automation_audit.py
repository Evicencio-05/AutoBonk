#!/usr/bin/env python3
"""Find repeated agent work that a script could do for no tokens.

Reads the Claude Code and Cursor transcripts for this repo, splits them into
turns (one operator prompt and the work after it), and counts by kind of task:
how often it came up, in how many sessions, and what it cost. It also finds
command recipes that repeat across turns. No model reads anything.

The report goes to learning/automation/ (gitignored: it quotes prompts). The
weekly proposal run reads it and judges each candidate with the `proposal`
skill's automation rules: keep the agent when its judgment is worth much more
than the tokens, else script the mechanical part.

  python3 scripts/automation_audit.py              # last 14 days
  python3 scripts/automation_audit.py --days 30 --print
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "learning" / "automation"
CLAUDE_DIR = Path.home() / ".claude" / "projects" / "-home-evice-repos-AutoBonk"
CURSOR_DIR = Path.home() / ".cursor" / "projects" / "home-evice-repos-AutoBonk" / "agent-transcripts"
# Cursor transcripts carry no token counts. About four characters a token.
CHARS_PER_TOKEN = 4

# First match wins. The script column names what already does the job, if anything.
KINDS = [
    ("levels", r"\blevels?\b|\bcharts? (are )?(in|up)\b|\bpm note\b|ingest", "levels_ingest.py arm (charts still read by the agent)"),
    ("merge and ship", r"\bmerge\b|\bpush\b|\bpr\b|\bprs\b|pull request", ""),
    ("bless and freeze", r"\bbless(ed)?\b|\bfreeze\b", "freeze.py"),
    ("proposal", r"\bproposals?\b", "proposals_auto.py weekly|daily"),
    ("review and recap", r"\breview\b|\brecap\b|how did (today|the day|it go)|\bjournal\b", "review.py day|week, recap.py"),
    ("trade result", r"p&l|\bpnl\b|\bloss\b|\bprofit\b|auto.?clos|\bfill(ed)?\b|\bexits?\b", "ledger.py show"),
    ("status", r"\bstatus\b|is it (running|working)|did (it|the checker) (run|fire)|\btimer\b|\bunits?\b", "freeze.py status, alarm.py list"),
    ("desk and bar", r"dashboard|\bdesk\b|top bar|widget|\bbar\b", ""),
    ("agents and routing", r"\bcursor\b|\bagents?\b|\brout(e|er|ing)\b|\bplugin\b", "agent_guard.py route"),
    ("fix", r"\bfix\b|\bbug\b|\berror\b|failed|broke|wrong", ""),
]
_KINDS = [(name, re.compile(pattern, re.I), script) for name, pattern, script in KINDS]
# Programs whose subcommand says what the step did.
_SUB = {"git", "gh", "systemctl", "uv", "npm", "omarchy", "journalctl"}
# Plumbing that says nothing about the task.
_SKIP = {"cd", "echo", "printf", "cat", "head", "tail", "sed", "grep", "ls", "wc", "sort", "true", "sleep", "cut", "awk", "tr", "uniq", "xargs", "find", "HEREDOC"}


def kind_of(prompt: str) -> str:
    for name, pattern, _ in _KINDS:
        if pattern.search(prompt):
            return name
    return "other"


_HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n.*?\n\s*\1\s*(?:\n|$)", re.S)


def _segments(command: str) -> list[list[str]]:
    """Words of each simple command. Newlines inside quotes stay inside their word."""
    command = _HEREDOC.sub(" HEREDOC\n", command.replace("\\\n", " "))
    out, quote = [], ""
    for char in command:
        if quote:
            quote = "" if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char == "\n":
            char = ";"
        out.append(char)
    lexer = shlex.shlex("".join(out), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = "#"
    segments, words = [], []
    try:
        for token in lexer:
            if set(token) <= set(";&|()"):
                segments.append(words)
                words = []
            else:
                words.append(token)
    except ValueError:
        return [part.split() for part in re.split(r"&&|\|\||;|\||\n", command)]
    return segments + [words]


def step_of(command: str) -> list[str]:
    """`cd x && python3 scripts/ledger.py show | head` -> ['python3 ledger.py show'].

    A heredoc body or a `-c` string is not a command: either is one `python3 inline` step.
    """
    steps = []
    for words in _segments(command):
        while words and "=" in words[0] and not words[0].startswith("-"):
            words = words[1:]
        if not words or words[0] in _SKIP:
            continue
        program = Path(words[0]).name
        rest = [word for word in words[1:] if not word.startswith("-")]
        if program.startswith("python"):
            scripts = [word for word in rest if word.endswith(".py") and "\n" not in word]
            if not scripts:
                steps.append("python3 inline")
                continue
            after = rest[rest.index(scripts[0]) + 1 :]
            sub = next((word for word in after if re.fullmatch(r"[a-z][a-z-]*", word)), "")
            steps.append(f"python3 {Path(scripts[0]).name} {sub}".strip())
        elif program in _SUB:
            depth = 2 if program in ("gh", "systemctl") else 1
            subs = [word for word in rest if re.fullmatch(r"[a-z][a-z-]*", word)][:depth]
            steps.append(" ".join([program, *subs]))
        elif re.fullmatch(r"[\w.-]+", program):
            steps.append(program)
    return steps


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


def _real_prompt(text: str) -> str:
    """The operator's words, or '' for tool results, hook notes, and command echoes."""
    text = text.strip()
    if not text or text.startswith(
        ("<local-command", "<system-reminder", "[Request interrupted", "Caveat:", "This session is being continued")
    ):
        return ""
    command = re.search(r"<command-name>/?([\w:-]+)</command-name>", text)
    if command:
        return f"/{command.group(1)}"
    query = re.search(r"<user_query>\s*(.*?)\s*</user_query>", text, re.S)
    if query:
        return query.group(1)
    return re.sub(r"<[^>]+>.*?</[^>]+>", "", text, flags=re.S).strip()


def claude_turns(folder: Path = CLAUDE_DIR) -> list[dict]:
    turns: list[dict] = []
    for path in sorted(folder.glob("**/*.jsonl")):
        seen: set[str] = set()
        current = None
        for line in path.open(errors="replace"):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            kind = row.get("type")
            message = row.get("message") or {}
            if kind == "user" and not row.get("isMeta") and not row.get("isSidechain"):
                prompt = _real_prompt(_text(message.get("content")))
                if prompt:
                    current = {
                        "tool": "claude",
                        "session": row.get("sessionId") or path.stem,
                        "at": row.get("timestamp"),
                        "prompt": prompt,
                        "fresh": 0,
                        "cached": 0,
                        "steps": [],
                        "skills": [],
                    }
                    turns.append(current)
                continue
            if kind != "assistant" or current is None:
                continue
            usage = message.get("usage") or {}
            key = message.get("id") or row.get("requestId") or row.get("uuid")
            if usage and key not in seen:
                seen.add(key)
                current["fresh"] += sum(
                    int(usage.get(name) or 0)
                    for name in ("input_tokens", "cache_creation_input_tokens", "output_tokens")
                )
                current["cached"] += int(usage.get("cache_read_input_tokens") or 0)
            for block in message.get("content") or []:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                tool_input = block.get("input") or {}
                if block.get("name") == "Bash":
                    current["steps"] += step_of(str(tool_input.get("command") or ""))
                elif block.get("name") == "Skill":
                    current["skills"].append(str(tool_input.get("skill") or ""))
    return turns


def cursor_turns(folder: Path = CURSOR_DIR) -> list[dict]:
    turns: list[dict] = []
    for path in sorted(folder.glob("**/*.jsonl")):
        current = None
        for line in path.open(errors="replace"):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            content = (row.get("message") or {}).get("content")
            if row.get("role") == "user":
                raw = _text(content)
                prompt = _real_prompt(raw)
                if prompt:
                    stamp = re.search(r"<timestamp>(.*?)</timestamp>", raw)
                    current = {
                        "tool": "cursor",
                        "session": path.stem,
                        "at": _cursor_time(stamp.group(1)) if stamp else None,
                        "prompt": prompt,
                        "fresh": 0,
                        "cached": 0,
                        "steps": [],
                        "skills": [],
                    }
                    turns.append(current)
                continue
            if current is None:
                continue
            current["fresh"] += len(json.dumps(content)) // CHARS_PER_TOKEN
            for block in content or []:
                if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Shell":
                    current["steps"] += step_of(str((block.get("input") or {}).get("command") or ""))
    return turns


def _cursor_time(text: str) -> str | None:
    """'Friday, Oct 16, 2026, 6:49 AM (UTC-7)' -> ISO."""
    match = re.match(r"\w+, (\w+ \d+, \d+), (\d+:\d+ [AP]M) \(UTC([+-]\d+)\)", text)
    if not match:
        return None
    moment = datetime.strptime(f"{match.group(1)} {match.group(2)}", "%b %d, %Y %I:%M %p")
    return moment.replace(tzinfo=timezone(timedelta(hours=int(match.group(3))))).isoformat()


def _when(turn: dict) -> datetime | None:
    if not turn.get("at"):
        return None
    try:
        return datetime.fromisoformat(str(turn["at"]).replace("Z", "+00:00"))
    except ValueError:
        return None


def build(turns: list[dict], since: datetime) -> dict:
    kept, seen = [], set()
    for turn in turns:
        key = (turn["tool"], turn["prompt"], turn.get("at"))
        if key in seen or (_when(turn) or since) < since:
            continue
        seen.add(key)
        kept.append(turn)
    kinds: dict[str, dict] = {}
    for turn in kept:
        name = kind_of(turn["prompt"])
        row = kinds.setdefault(
            name, {"turns": 0, "sessions": set(), "fresh": 0, "cached": 0, "cursor": 0, "examples": []}
        )
        row["turns"] += 1
        row["sessions"].add(turn["session"])
        row["fresh"] += turn["fresh"]
        row["cached"] += turn["cached"]
        row["cursor"] += turn["tool"] == "cursor"
        if len(row["examples"]) < 3:
            row["examples"].append(_short(turn["prompt"]))
    recipes: dict[tuple, dict] = defaultdict(lambda: {"turns": 0, "fresh": 0, "kinds": set()})
    steps: dict[str, int] = defaultdict(int)
    for turn in kept:
        unique = tuple(dict.fromkeys(turn["steps"]))
        for step in unique:
            steps[step] += 1
        if len(unique) >= 2:
            recipe = recipes[unique]
            recipe["turns"] += 1
            recipe["fresh"] += turn["fresh"]
            recipe["kinds"].add(kind_of(turn["prompt"]))
    scripts = {name: script for name, _, script in KINDS}
    return {
        "since": since.isoformat(),
        "turns": len(kept),
        "fresh": sum(turn["fresh"] for turn in kept),
        "kinds": sorted(
            (
                {
                    "kind": name,
                    "turns": row["turns"],
                    "sessions": len(row["sessions"]),
                    "fresh": row["fresh"],
                    "per_turn": row["fresh"] // max(row["turns"], 1),
                    "cached": row["cached"],
                    "cursor_turns": row["cursor"],
                    "scripted_by": scripts.get(name, ""),
                    "examples": row["examples"],
                }
                for name, row in kinds.items()
            ),
            key=lambda item: -item["fresh"],
        ),
        "recipes": sorted(
            (
                {"steps": list(key), "turns": row["turns"], "fresh": row["fresh"], "kinds": sorted(row["kinds"])}
                for key, row in recipes.items()
                if row["turns"] >= 2
            ),
            key=lambda item: (-item["turns"], -item["fresh"]),
        )[:10],
        "steps": sorted(({"step": step, "turns": count} for step, count in steps.items() if count >= 3), key=lambda item: -item["turns"])[:15],
    }


def _short(text: str, width: int = 90) -> str:
    one = " ".join(text.split())
    return one if len(one) <= width else one[: width - 1] + "…"


def _k(value: int) -> str:
    return f"{value / 1000:,.0f}k" if value >= 1000 else str(value)


def markdown(report: dict, today: str) -> str:
    lines = [
        f"# Automation audit {today}",
        "",
        f"Since {report['since'][:10]}: {report['turns']} operator prompts, {_k(report['fresh'])} fresh tokens "
        "(input, cache writes, and output; cache reads are listed apart because they cost far less). "
        "Cursor turns count only the text written, so their tokens are a floor, not a total.",
        "",
        "Judge each candidate with the automation rules in `.claude/skills/proposal/SKILL.md`.",
        "",
        "## By kind of task",
        "",
        "| Kind | Prompts | Sessions | Fresh tokens | Per prompt | Cursor prompts | Already scripted by | Examples |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in report["kinds"]:
        examples = "<br>".join(row["examples"]).replace("|", "/")
        lines.append(
            f"| {row['kind']} | {row['turns']} | {row['sessions']} | {_k(row['fresh'])} | {_k(row['per_turn'])} "
            f"| {row['cursor_turns']} | {row['scripted_by'] or '—'} | {examples} |"
        )
    lines += ["", "## Command recipes that repeat", ""]
    if report["recipes"]:
        lines += ["| Steps | Prompts | Fresh tokens | Kinds |", "|---|---|---|---|"]
        for row in report["recipes"]:
            lines.append(
                f"| {' → '.join(row['steps'])} | {row['turns']} | {_k(row['fresh'])} | {', '.join(row['kinds'])} |"
            )
    else:
        lines.append("None repeated yet.")
    lines += ["", "## Commands run in 3 or more prompts", ""]
    lines += [f"- `{row['step']}`: {row['turns']}" for row in report["steps"]] or ["None yet."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--print", action="store_true", help="Also print the report")
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    report = build(claude_turns() + cursor_turns(), now - timedelta(days=args.days))
    today = now.astimezone().date().isoformat()
    OUT.mkdir(parents=True, exist_ok=True)
    text = markdown(report, today)
    for name in (f"{today}.md", "latest.md"):
        (OUT / name).write_text(text)
    (OUT / "latest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(text if args.print else f"Wrote {OUT.relative_to(ROOT)}/{today}.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
