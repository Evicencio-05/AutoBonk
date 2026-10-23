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
    # on 2026-10-23 a hand-added GOOGL exit row meant the real put was never sold.
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


def advice(prompt: str) -> str:
    found = route(prompt)
    if not found:
        return "No clear route. Default: Claude Code for logic, Cursor for quick edits. See AGENTS.md."
    agent, why, _ = found
    if agent == NOBODY:
        return f"Best fit: no agent. {why}"
    return f"Best fit: {_NAMES[agent]}, because {why}"


def mismatch(prompt: str, here: str) -> str | None:
    """A block message when the task belongs to a different tool than `here`."""
    if OVERRIDE in prompt:
        return None
    found = route(prompt)
    if not found:
        return None
    agent, why, scores = found
    if agent == NOBODY:
        return f"AutoBonk: {why} Resend with {OVERRIDE} if you meant something else (say, a code change)."
    tool = CLAUDE if agent == CLAUDE else "cursor"
    if tool == here:
        return None
    # Only block on a clear signal: the current tool scored nothing.
    mine = scores[CLAUDE] if here == CLAUDE else scores[CURSOR_CLOUD] + scores[CURSOR_EDITOR]
    if mine:
        return None
    return (
        f"AutoBonk routing: this looks like a job for {_NAMES[agent]}, because {why} "
        f"Open it there, or resend with {OVERRIDE} to run it here anyway."
    )


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
        message = mismatch(data.get("prompt", ""), CLAUDE)
        if message:
            print(json.dumps({"decision": "block", "reason": message}))
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
