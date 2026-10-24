#!/usr/bin/env python3
"""Run Claude Code headless to draft proposals. The systemd timers call this.

  python3 scripts/proposals_auto.py weekly          # Friday after the close: up to two decision proposals
  python3 scripts/proposals_auto.py daily           # after the close: a safety note, only if something broke today
  python3 scripts/proposals_auto.py daily --dry-run # say what would run, run nothing

The headless session follows the `proposal` skill. It can read, write files,
and run python. The project hooks still apply: no orders, no live check, no
secrets, no bless, no tape edits. It does not commit or push. A desktop toast
says when a draft is ready.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import alarm  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PT = ZoneInfo("America/Los_Angeles")
# systemd runs without the login shell's PATH, so look in the usual install places too.
CLAUDE = shutil.which("claude") or next(
    (str(path) for path in (
        Path.home() / ".local" / "share" / "mise" / "installs" / "claude" / "latest" / "claude",
        Path.home() / ".local" / "bin" / "claude",
        Path.home() / ".claude" / "local" / "claude",
    ) if path.exists()),
    "claude",
)
TOOLS = ["Read", "Write", "Edit", "Glob", "Grep", "Skill", "Bash(python3:*)", "Bash(uvx:*)", "Bash(ls:*)", "Bash(git log:*)", "Bash(git diff:*)"]
DENY = ["Bash(git push:*)", "Bash(git commit:*)", "WebFetch", "WebSearch"]

WEEKLY = (
    "!here Use the proposal skill for the weekly AutoBonk proposal run. Run "
    "python3 scripts/proposal_data.py first. Write at most two decision proposals in "
    "learning/proposals/, each with a recommendation, and list them under Open in "
    "learning/proposals.md. If the evidence does not support any change yet, write one "
    "short proposal that says so and what data would settle it. Do not implement anything, "
    "do not commit, and do not fill the Operator decision section. End with the file paths."
)
DAILY = (
    "!here Use the proposal skill to write a safety proposal for what broke in today's "
    "AutoBonk session. Today's alarms are below. Read the checker journal with "
    "journalctl --user -u autobonk-claims.service --since today if it helps, and the code "
    "involved. Propose fixes that change no replayed decision; if the fix would change a "
    "decision, write it as a decision proposal for the weekly review instead. Do not "
    "implement anything, do not commit. End with the file path.\n\nToday's alarms:\n"
)


def alarms_today(now: datetime | None = None, path: Path | None = None) -> list[dict]:
    file = path or alarm.HISTORY_PATH
    day = (now or datetime.now(PT)).date()
    found = []
    try:
        lines = file.read_text().splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if datetime.fromtimestamp(float(item.get("at") or 0), PT).date() == day:
            found.append(item)
    return found


def command(prompt: str) -> list[str]:
    return [
        CLAUDE, "-p", prompt,
        # Unattended: anything not on the allowed list is refused instead of waiting on a prompt.
        "--permission-mode", "dontAsk",
        "--allowedTools", *TOOLS,
        "--disallowedTools", *DENY,
        "--output-format", "text",
    ]


def run(prompt: str, label: str) -> int:
    done = subprocess.run(command(prompt), cwd=ROOT, capture_output=True, text=True, timeout=3600)
    log = ROOT / "learning" / "proposals" / "data" / f"{datetime.now(PT):%Y-%m-%d}-{label}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(done.stdout + ("\n--- stderr ---\n" + done.stderr if done.stderr else ""))
    tail = (done.stdout.strip().splitlines() or ["(no output)"])[-1][:200]
    if done.returncode == 0:
        alarm.toast("AutoBonk proposal ready", f"{label}: {tail}", "normal")
    else:
        alarm.toast("AutoBonk proposal run failed", f"{label}: see {log.relative_to(ROOT)}", "normal")
    print(log.relative_to(ROOT))
    return done.returncode


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args or args[0] not in ("weekly", "daily"):
        print(__doc__)
        return 1
    dry = "--dry-run" in args
    if args[0] == "weekly":
        if dry:
            print("would run the weekly proposal session")
            return 0
        return run(WEEKLY, "weekly")
    today = alarms_today()
    if not today:
        print("No alarms today. No safety note.")
        return 0
    listed = "\n".join(f"- {datetime.fromtimestamp(item['at'], PT):%H:%M} {item['text']}" for item in today)
    if dry:
        print(f"would write a safety note for {len(today)} alarms:\n{listed}")
        return 0
    return run(DAILY + listed, "safety")


if __name__ == "__main__":
    sys.exit(main())
