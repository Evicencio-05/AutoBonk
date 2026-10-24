#!/usr/bin/env python3
"""Hard limits and task routing for the coding agents (Claude Code and Cursor).

  python3 scripts/agent_guard.py route "move the dashboard legend under the chart"
  python3 scripts/agent_guard.py claude-tool     < hook.json   # PreToolUse
  python3 scripts/agent_guard.py claude-prompt   < hook.json   # UserPromptSubmit
  python3 scripts/agent_guard.py cursor-shell    < hook.json   # beforeShellExecution
  python3 scripts/agent_guard.py cursor-mcp      < hook.json   # beforeMCPExecution
  python3 scripts/agent_guard.py cursor-tool     < hook.json   # preToolUse
  python3 scripts/agent_guard.py cursor-prompt   < hook.json   # beforeSubmitPrompt

AGENTS.md is the policy in words. This file is the part that is enforced.
A prompt that starts with or contains !here skips the routing check. Nothing skips a limit.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import PurePosixPath

OVERRIDE = "!here"

# Files no agent writes. The operator owns these.
NO_WRITE = (
    "config/agentic.yaml",
    "config/accounts.yaml",
    "config/freeze.yaml",
    "rules/ta_rules.md",
    "alerts/state.json",
    "alerts/broker.json",
    # The checker's tapes. A row written by anything else can hide an open position from it:
    # on 2026-10-23 a hand-added GOOGL exit row meant the checker never sent the put's sell (Robinhood's
    # expiring-option close sold it at the cutoff instead).
    "alerts/live.md",
    "alerts/paper.md",
    "alerts/log.md",
    "alerts/context.md",
    "alerts/contracts.md",
    "alerts/events.jsonl",
    "alerts/alarms.json",
    "learning/trades.jsonl",
    "learning/trades.csv",
)
# Directories no agent writes into.
NO_WRITE_UNDER = ("bench/golden/",)
# Files no agent reads. Secrets and account numbers.
NO_READ = ("config/accounts.yaml",)
_ENV_FILE = re.compile(r"(^|/)\.env(\.[\w-]+)?$")

# A script run as a program (python, uv, or the path itself), not named in a message, a grep, or a heredoc.
_RUN = r"(\b(python3?(\.\d+)?|uv\s+run|uvx)\s+(-\S+\s+)*|(^|[;&|(]\s*)(\./)?)[^\s;&|'\"`]*"


def _runs(script: str, command: str) -> re.Pattern:
    return re.compile(
        _RUN + script + r"(\.py)?\b[^|;&\n]*\b" + command + r"\b"
        r"|-m\s+(scripts\.)?" + script + r"\b[^|;&\n]*\b" + command + r"\b"
    )


_SHELL_RULES = (
    (
        _runs("claim_alerts", "check"),
        "claim_alerts.py check sends the live Agentic entry and exit on a live session. "
        "Only the systemd timer runs it. Use pytest or scripts/bench.py instead.",
    ),
    (
        re.compile(r"robinhood_mcp\b.*\b(buy|sell|_place|place_option_order)\b"),
        "Calling the broker's buy, sell, or place from an agent is an order. Orders come from the checker only.",
    ),
    (
        _runs("freeze", "bless"),
        "Blessing new golden decisions lifts the freeze for that change. Only the operator runs it.",
    ),
    (
        re.compile(r"systemctl\b.*\b(start|stop|restart|enable|disable|kill)\b.*autobonk"),
        "The autobonk timer belongs to the operator. Do not start, stop, or change it.",
    ),
    (
        re.compile(r"(^|[\s'\"=/<>])\.env(\.[\w-]+)?(\b|$)"),
        ".env files hold TA_BOT_TOKEN and other secrets. Agents do not read, print, or write them.",
    ),
    (
        re.compile(
            r"\$\{?TA_BOT_TOKEN|\b(printenv|env|set|export)\b[^|;&]*TA_BOT_TOKEN"
            r"|\bos\.environ\b[^|;&]*TA_BOT_TOKEN|config/accounts\.yaml"
        ),
        "Do not print TA_BOT_TOKEN or account numbers.",
    ),
    (
        re.compile(r"config/agentic\.yaml"),
        "config/agentic.yaml is the operator's cap. Agents do not touch it.",
    ),
    (
        re.compile(r"git\s+push\b.*(--force\b|-f\b|\s\+?(master|main)\b)"),
        "Do not push to master or force-push. Open a PR on a branch.",
    ),
)

# Broker MCP tools that move money. Quotes, positions, and review_* stay allowed.
_ORDER_TOOL = re.compile(
    r"(^|_)(place|submit|cancel|replace|modify|send)_?\w*order|(^|_)(buy|sell)(_|$)",
    re.IGNORECASE,
)


def _norm(path: str) -> str:
    text = path.replace("\\", "/")
    marker = "/AutoBonk/"
    if marker in text:
        text = text.split(marker, 1)[1]
    text = str(PurePosixPath(text))
    while text.startswith("./"):
        text = text[2:]
    return text


def path_refusal(path: str, writing: bool) -> str | None:
    rel = _norm(path)
    if _ENV_FILE.search(rel):
        return f"{rel} holds secrets. Agents do not read or write .env files."
    if rel in NO_READ:
        return f"{rel} holds account numbers. Agents do not read or write it."
    if writing and (rel in NO_WRITE or rel.startswith(NO_WRITE_UNDER)):
        return f"{rel} belongs to the operator or the checker. Agents do not write it."
    return None


_HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n.*?\n\s*\1\s*(\n|$)", re.DOTALL)
_SHELL_FED = re.compile(r"\b(ba|z)?sh\s*(-\w+\s*)*<<")


def shell_refusal(command: str) -> str | None:
    # A heredoc body is file content, unless it is fed to a shell.
    text = command if _SHELL_FED.search(command) else _HEREDOC.sub("<<heredoc\n", command)
    for pattern, reason in _SHELL_RULES:
        if pattern.search(text):
            return reason
    return None


def mcp_refusal(tool_name: str) -> str | None:
    name = tool_name.rsplit("__", 1)[-1]
    if _ORDER_TOOL.search(name):
        return (
            f"{name} places or changes a broker order. Agents never send orders; "
            "the checker sends the qualifying Agentic entry and exit."
        )
    return None


_PATH_KEYS = ("file_path", "path", "target_file", "notebook_path", "filePath", "targetFile")
_WRITE_TOOLS = re.compile(r"edit|write|notebook|delete|create|patch|replace", re.IGNORECASE)


def tool_refusal(tool_name: str, tool_input: dict) -> str | None:
    if tool_name.startswith("mcp__") or tool_name.startswith("MCP:"):
        return mcp_refusal(tool_name.removeprefix("MCP:").strip())
    if not isinstance(tool_input, dict):
        return None
    command = tool_input.get("command")
    if isinstance(command, str) and command:
        reason = shell_refusal(command)
        if reason:
            return reason
    writing = bool(_WRITE_TOOLS.search(tool_name))
    for key in _PATH_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            reason = path_refusal(value, writing)
            if reason:
                return reason
    return None


# ---- routing ----------------------------------------------------------------

CLAUDE = "claude"
CURSOR_CLOUD = "cursor-cloud"
CURSOR_EDITOR = "cursor-editor"
NOBODY = "nobody"

_NAMES = {
    CLAUDE: "Claude Code (local)",
    CURSOR_CLOUD: "a Cursor cloud agent",
    CURSOR_EDITOR: "Cursor in the editor (Tab / Cmd-K)",
    NOBODY: "no agent",
}

_ROUTES = (
    (
        NOBODY,
        r"\b(place|send|submit|enter)\s+(an?\s+|the\s+|my\s+)?(live\s+)?(order|trade)\b"
        r"|\b(buy|sell)\s+(an?\s+|the\s+|my\s+|\d+\s+)?(\w+\s+)?(call|put|contract|position)s?\b"
        r"|\brun\s+(the\s+)?(live\s+)?check(er)?\b|claim_alerts\.py\s+check",
        "Orders come from the systemd checker, or from you in the Robinhood app. No agent sends one.",
    ),
    (
        CLAUDE,
        r"claim_alerts|\bchecker\b|\bcutoffs?\b|\bsellout\b|\bretest|\batr\b|\bskip (logic|rule)"
        r"|\bbench\b|backtest|\bregime|\bfade\b|\breplay|profit factor"
        r"|review (the |this |that )?(pr|diff|branch)|code.?review|\bpr #?\d+"
        r"|\bchart image|levels\.yaml|\blevels file|\bingest|\bjournal|daily.?review|\bdrills?\b|\blesson"
        r"|\bwhy (does|did|is)\b|\bdebug|\btraceback|\bfailing test|\brefactor|across (files|the repo)"
        r"|\bpost.?close\b|\bafter the close\b|\bevery (day|weekday|morning|evening)\b|\bschedul",
        "it touches the order logic, needs tests or bench replays, reads charts, "
        "or writes the learning files, so it benefits from a careful agent working with you locally.",
    ),
    (
        CURSOR_EDITOR,
        r"\bdashboard\b|\bcss\b|\bhtml\b|\bstyl(e|ing)\b|\bcolou?rs?\b|\blayout\b|\bbutton\b|\bfont"
        r"|\bpadding|\bmargin|\balign|\btooltip|\blegend\b|\bdark mode\b|\bon the page\b|\bbar widget"
        r"|\btypo\b|\brename\b|\bone.?liner?\b",
        "it is a quick visual or one-file edit you can watch happen.",
    ),
    (
        CURSOR_CLOUD,
        r"\bin the background\b|\bwhile i\b|\bopen a pr\b|\bspec\b|\bcloud agent\b"
        r"|\badd (a |an )?(field|column|flag|option|endpoint|route)\b|\bwrite tests? for\b"
        r"|\bvercel\b|\bneon\b|\bblotter\b|\bdesk\.py\b|\bdiscord_ta\b",
        "it is a well-scoped change with a clear spec that can run unattended and come back as a PR.",
    ),
)
_COMPILED = tuple((agent, re.compile(rx, re.IGNORECASE), why) for agent, rx, why in _ROUTES)


def route(prompt: str) -> tuple[str, str, dict[str, int]] | None:
    """Best agent for a task, its reason, and the hit counts. None when nothing matches."""
    scores = {agent: len(rx.findall(prompt)) for agent, rx, _ in _COMPILED}
    # "Buy the TSLA call" is a trade. "Size the call to the balance in the checker" is code.
    if scores[NOBODY] and not any(scores[a] for a in scores if a != NOBODY):
        agent = NOBODY
    else:
        ranked = sorted((a for a in scores if a != NOBODY), key=lambda a: -scores[a])
        agent = ranked[0]
        if not scores[agent]:
            return None
        # Anything that names the order logic stays with Claude even if it also mentions the page.
        if scores[CLAUDE] and scores[CLAUDE] >= scores[agent] - 1:
            agent = CLAUDE
    why = next(w for a, _, w in _COMPILED if a == agent)
    return agent, why, scores


_LEAD = re.compile(r"^(?:\(?\d+[.)]\s*)?(?:(?:and|also|then|plus)\b[,:]?\s*)*", re.IGNORECASE)
_SPLIT = re.compile(r"(?:\n+|(?<=[.?!;])(?<!\d[.)])\s+|\s+(?=\(?\d+[.)]\s)|\s+also,?\s+)", re.IGNORECASE)


def split_tasks(prompt: str) -> list[str]:
    """The separate asks in one message: lines, sentences, numbered items, and "also ..." clauses."""
    parts = []
    for part in _SPLIT.split(prompt.replace(OVERRIDE, " ")):
        part = _LEAD.sub("", (part or "").strip(" -*\t"))
        if part:
            parts.append(part[0].upper() + part[1:])
    tasks: list[str] = []
    for part in parts:
        if len(part.split()) < 3 and tasks:
            tasks[-1] += " " + part
        elif len(part.split()) >= 2:
            tasks.append(part)
    return tasks


def plan(prompt: str) -> list[tuple[str | None, str]]:
    """(agent, task) per ask. A task with no clear route follows the task before it."""
    out: list[tuple[str | None, str]] = []
    for task in split_tasks(prompt):
        found = route(task)
        agent = found[0] if found else (out[-1][0] if out else None)
        out.append((agent, task))
    return out


def _tool(agent: str | None) -> str | None:
    if agent in (CURSOR_CLOUD, CURSOR_EDITOR):
        return "cursor"
    return agent


# Where a Cursor task most likely lives, so the handoff can name files.
_FILES = (
    (r"dashboard|css|html|styl|colou?r|layout|button|font|padding|margin|align|tooltip|legend|dark mode|page|chart|tab\b",
     ("scripts/dashboard_page.html (styles and page script)", "scripts/overview.py (Overview charts, trades table, proposals)",
      "scripts/dashboard.py (sections and tabs)")),
    (r"blotter|neon|database", ("scripts/blotter.py",)),
    (r"vercel|hosted|deploy", ("app.py", "vercel.json")),
    (r"desk\.py|studio", ("scripts/desk.py",)),
    (r"discord", ("scripts/discord_ta.py",)),
    (r"bar widget|waybar|omarchy bar", ("scripts/bar_status.py",)),
)

TEST_COMMAND = "uvx --with pyyaml --with flask --with 'psycopg[binary]' pytest -q scripts/tests"


def _files(tasks: list[str]) -> list[str]:
    found: list[str] = []
    text = " ".join(tasks)
    for pattern, files in _FILES:
        if re.search(pattern, text, re.IGNORECASE):
            found += [name for name in files if name not in found]
    return found


def handoff(agent: str, tasks: list[str]) -> str:
    """A prompt to paste into the other tool, with what it needs to do the job inside the repo's limits."""
    task = "\n".join(f"- {item}" for item in tasks) if len(tasks) > 1 else tasks[0]
    files = _files(tasks)
    where = ("Files to start with:\n" + "\n".join(f"- {name}" for name in files) + "\n\n") if files else ""
    if agent == CURSOR_EDITOR:
        return (
            f"{task}\n\n{where}"
            "Keep the change to those files. Preview the desk with `python3 scripts/dashboard.py serve` "
            "(http://127.0.0.1:8765). Do not touch alerts/, config/, or bench/golden/."
        )
    if agent == CURSOR_CLOUD:
        return (
            "Read AGENTS.md first and stay inside its limits.\n\n"
            f"Task:\n{task}\n\n{where}"
            "Rules for this change:\n"
            "- Work on a cursor/ branch and open a PR to master.\n"
            "- Do not edit alerts/ tapes, bench/golden/, config/freeze.yaml, config/agentic.yaml, or .env. Never place a broker order.\n"
            f"- Run `{TEST_COMMAND}`; every test must pass, including test_freeze.\n"
            "- If you change scripts/claim_alerts.py or scripts/robinhood_mcp.py, say so at the top of the PR so Claude reviews it before merge.\n\n"
            "Done when: the PR is open, tests pass, and its description says what changed and how you checked it."
        )
    return (
        f"{task}\n\n"
        "(Handed over from Cursor. Follow AGENTS.md. If this changes what the checker decides, write it as a "
        "proposal with the proposal skill instead of changing the code.)"
    )


def _block(agent: str, tasks: list[str]) -> str:
    return f"Paste into {_NAMES[agent]}:\n```\n{handoff(agent, tasks)}\n```"


def advice(prompt: str) -> str:
    steps = plan(prompt)
    if not steps or all(agent is None for agent, _ in steps):
        return "No clear route. Default: Claude Code for logic, Cursor for quick edits. See AGENTS.md."
    lines = []
    for agent, task in steps:
        lines.append(f"- {_NAMES.get(agent, 'unclear')}: {task}")
    blocks = []
    for agent in (CLAUDE, CURSOR_CLOUD, CURSOR_EDITOR):
        tasks = [task for who, task in steps if who == agent]
        if tasks:
            blocks.append(_block(agent, tasks))
    nobody = [task for who, task in steps if who == NOBODY]
    if nobody:
        blocks.append(f"No agent for: {'; '.join(nobody)}. {next(w for a, _, w in _COMPILED if a == NOBODY)}")
    return "Split:\n" + "\n".join(lines) + "\n\n" + "\n\n".join(blocks)


def route_prompt(prompt: str, here: str) -> tuple[str, str]:
    """What a prompt hook should do: ("allow", ""), ("block", message), or ("context", note for the agent).

    All of it belongs elsewhere: block, and hand the operator a ready prompt.
    Part of it belongs elsewhere: in Claude Code, let it run and tell Claude to
    hand back a ready Cursor prompt for that part; Cursor cannot be told, so it
    blocks with both prompts split out.
    """
    if OVERRIDE in prompt:
        return "allow", ""
    steps = [(agent, task) for agent, task in plan(prompt) if agent]
    if not steps:
        return "allow", ""
    mine = [task for agent, task in steps if _tool(agent) == here]
    theirs = [(agent, task) for agent, task in steps if _tool(agent) not in (here, NOBODY)]
    nobody = [task for agent, task in steps if agent == NOBODY]
    if nobody and not mine and not theirs:
        why = next(w for a, _, w in _COMPILED if a == NOBODY)
        return "block", f"AutoBonk: {why} Resend with {OVERRIDE} if you meant a code change."
    if not theirs:
        return "allow", ""
    groups: dict[str, list[str]] = {}
    for agent, task in theirs:
        groups.setdefault(agent, []).append(task)
    blocks = "\n\n".join(_block(agent, tasks) for agent, tasks in groups.items())
    if not mine:
        why = next(w for a, _, w in _COMPILED if a == theirs[0][0])
        return "block", (
            f"AutoBonk routing: this is a job for {_NAMES[theirs[0][0]]}, because {why}\n\n{blocks}\n\n"
            f"Or resend with {OVERRIDE} to run it here anyway."
        )
    if here == CLAUDE:
        return "context", (
            "AutoBonk routing: part of this message belongs in Cursor. Do the Claude Code parts. For these parts, do not "
            "do the work; end your reply with the ready-to-paste prompt below, in a code block, so the operator can "
            f"send it:\n\n{blocks}"
        )
    return "block", (
        "AutoBonk routing: this message mixes Claude Code and Cursor work.\n\n"
        f"{_block(CLAUDE, [task for agent, task in steps if _tool(agent) == CLAUDE])}\n\n"
        f"Then resend only this here:\n```\n{chr(10).join(mine)}\n```\n\nOr resend with {OVERRIDE} to do all of it here."
    )


def mismatch(prompt: str, here: str) -> str | None:
    """A block message when all of the task belongs to a different tool than `here`."""
    action, message = route_prompt(prompt, here)
    return message if action == "block" else None


# ---- hook adapters ----------------------------------------------------------


def _stdin() -> dict:
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return {}


def _claude_deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"AutoBonk limit: {reason}",
                }
            }
        )
    )


def _cursor_permission(reason: str | None) -> None:
    if reason:
        message = f"AutoBonk limit: {reason}"
        print(json.dumps({"permission": "deny", "user_message": message, "agent_message": message}))
    else:
        print(json.dumps({"permission": "allow"}))


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print(__doc__)
        return 1
    mode = args[0]
    if mode == "route":
        print(advice(" ".join(args[1:]) or sys.stdin.read()))
        return 0
    data = _stdin()
    if mode == "claude-tool":
        reason = tool_refusal(data.get("tool_name", ""), data.get("tool_input") or {})
        if reason:
            _claude_deny(reason)
        return 0
    if mode == "claude-prompt":
        action, message = route_prompt(data.get("prompt", ""), CLAUDE)
        if action == "block":
            print(json.dumps({"decision": "block", "reason": message}))
        elif action == "context":
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": message}}))
        return 0
    if mode == "cursor-shell":
        _cursor_permission(shell_refusal(data.get("command", "")))
        return 0
    if mode == "cursor-mcp":
        _cursor_permission(mcp_refusal(data.get("tool_name", "")))
        return 0
    if mode == "cursor-tool":
        tool_input = data.get("tool_input") or {}
        if isinstance(tool_input, str):
            try:
                tool_input = json.loads(tool_input)
            except json.JSONDecodeError:
                tool_input = {}
        _cursor_permission(tool_refusal(data.get("tool_name", ""), tool_input))
        return 0
    if mode == "cursor-prompt":
        message = mismatch(data.get("prompt", ""), "cursor")
        if message:
            print(json.dumps({"continue": False, "user_message": message}))
        else:
            print(json.dumps({"continue": True}))
        return 0
    print(f"unknown mode {mode}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
