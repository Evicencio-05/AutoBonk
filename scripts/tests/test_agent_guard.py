"""Agents cannot send orders, touch secrets, or write operator files. Tasks route to one tool."""

import importlib.util
import io
import json
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "agent_guard",
    Path(__file__).resolve().parents[1] / "agent_guard.py",
)
guard = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(guard)


def _run(mode, payload, monkeypatch, capsys):
    monkeypatch.setattr(guard.sys, "stdin", io.StringIO(json.dumps(payload)))
    guard.main([mode])
    out = capsys.readouterr().out.strip()
    return json.loads(out) if out else {}


def test_the_live_check_is_refused_and_its_tests_are_not():
    assert guard.shell_refusal("python3 scripts/claim_alerts.py check")
    assert guard.shell_refusal("cd x && /usr/bin/python3 scripts/claim_alerts.py check --notify")
    assert guard.shell_refusal("scripts/claim_alerts.py check")
    assert guard.shell_refusal(".venv/bin/python3 -u scripts/claim_alerts.py check")
    assert guard.shell_refusal("python3 -m pytest scripts/tests/test_claim_alerts.py") is None
    assert guard.shell_refusal("gh pr create --body 'no `claim_alerts.py check` from agents'") is None
    assert guard.shell_refusal("grep -n 'claim_alerts.py check' AGENTS.md") is None
    assert guard.shell_refusal("python3 scripts/bench.py run --levels a --bars b --as-of c --out d") is None


def test_secrets_are_refused_and_the_venv_is_not():
    assert guard.shell_refusal("cat .env")
    assert guard.shell_refusal("grep TOKEN .env.local")
    assert guard.shell_refusal("echo $TA_BOT_TOKEN")
    assert guard.shell_refusal("printenv TA_BOT_TOKEN")
    assert guard.shell_refusal("python3 -c 'import os; print(os.environ[\"TA_BOT_TOKEN\"])'")
    assert guard.shell_refusal("grep -rn TA_BOT_TOKEN scripts/") is None
    assert guard.shell_refusal("cat config/accounts.yaml")
    assert guard.shell_refusal(".venv/bin/python -m pytest") is None
    assert guard.shell_refusal("python3 scripts/discord_ta.py ingest --channel ta") is None


def test_operator_files_cannot_be_written_but_can_be_read():
    assert guard.tool_refusal("Write", {"file_path": "/home/evice/repos/AutoBonk/config/agentic.yaml"})
    assert guard.tool_refusal("Edit", {"file_path": "rules/ta_rules.md"})
    assert guard.tool_refusal("Edit", {"file_path": "./alerts/broker.json"})
    assert guard.tool_refusal("Read", {"file_path": "rules/ta_rules.md"}) is None
    assert guard.tool_refusal("Read", {"file_path": "/home/evice/repos/AutoBonk/.env"})
    assert guard.tool_refusal("Read", {"file_path": "config/accounts.yaml"})
    assert guard.tool_refusal("Edit", {"file_path": "scripts/dashboard.py"}) is None
    assert guard.tool_refusal("Edit", {"file_path": "alerts/live.md"})
    assert guard.tool_refusal("Write", {"file_path": "bench/golden/2026-10-23.json"})
    assert guard.tool_refusal("Edit", {"file_path": "config/freeze.yaml"})
    assert guard.tool_refusal("Edit", {"file_path": "learning/proposals.md"}) is None
    assert guard.shell_refusal("python3 scripts/freeze.py bless")
    assert guard.shell_refusal("python3 scripts/freeze.py check") is None
    assert guard.shell_refusal("cat > x.json <<'EOF'\n\"Bash(python3 scripts/freeze.py bless:*)\"\nEOF") is None
    assert guard.shell_refusal("bash <<'EOF'\npython3 scripts/freeze.py bless\nEOF")
    assert guard.shell_refusal("python3 scripts/ledger.py sync") is None


def test_broker_order_tools_are_refused_and_reads_are_not():
    assert guard.mcp_refusal("mcp__claude_ai_Robinhood_Agentic__place_option_order")
    assert guard.mcp_refusal("place_option_order")
    assert guard.mcp_refusal("cancel_order")
    assert guard.mcp_refusal("review_option_order") is None
    assert guard.mcp_refusal("get_positions") is None
    assert guard.mcp_refusal("mcp__context7__query-docs") is None


def test_force_push_and_master_push_are_refused():
    assert guard.shell_refusal("git push origin master")
    assert guard.shell_refusal("git push --force origin cursor/x")
    assert guard.shell_refusal("git push -u origin claude/agent-limits") is None


def test_tasks_route_to_one_tool():
    assert guard.route("Exit each contract at its own broker cutoff")[0] == guard.CLAUDE
    assert guard.route("review PR #17 before I merge")[0] == guard.CLAUDE
    assert guard.route("make the dashboard legend dark mode friendly")[0] == guard.CURSOR_EDITOR
    assert guard.route("add a column to the blotter and open a PR")[0] == guard.CURSOR_CLOUD
    assert guard.route("buy the TSLA call now")[0] == guard.NOBODY
    assert guard.route("hello") is None


def test_order_logic_stays_with_claude_even_when_the_page_is_named():
    assert guard.route("show the checker cutoff on the dashboard")[0] == guard.CLAUDE


def test_a_wrong_tool_is_blocked_until_overridden(monkeypatch, capsys):
    css = {"prompt": "change the dashboard button color"}
    assert _run("claude-prompt", css, monkeypatch, capsys)["decision"] == "block"
    css_here = {"prompt": "!here change the dashboard button color"}
    assert _run("claude-prompt", css_here, monkeypatch, capsys) == {}
    logic = {"prompt": "why did the checker skip the 345.40 retest"}
    assert _run("cursor-prompt", logic, monkeypatch, capsys)["continue"] is False
    assert _run("cursor-prompt", css, monkeypatch, capsys)["continue"] is True
    assert _run("claude-prompt", logic, monkeypatch, capsys) == {}


def test_hook_adapters_speak_each_tools_format(monkeypatch, capsys):
    out = _run("claude-tool", {"tool_name": "Bash", "tool_input": {"command": "python3 scripts/claim_alerts.py check"}}, monkeypatch, capsys)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert _run("claude-tool", {"tool_name": "Bash", "tool_input": {"command": "ls"}}, monkeypatch, capsys) == {}
    assert _run("cursor-shell", {"command": "cat .env"}, monkeypatch, capsys)["permission"] == "deny"
    assert _run("cursor-mcp", {"tool_name": "place_option_order"}, monkeypatch, capsys)["permission"] == "deny"
    assert _run("cursor-tool", {"tool_name": "Write", "tool_input": {"file_path": "config/agentic.yaml"}}, monkeypatch, capsys)["permission"] == "deny"
    assert _run("cursor-tool", {"tool_name": "Write", "tool_input": {"file_path": "scripts/x.py"}}, monkeypatch, capsys)["permission"] == "allow"


def test_a_message_is_split_into_its_tasks():
    tasks = guard.split_tasks("Make the dashboard legend bigger. Also why did the checker skip the retest?\n2. add a column to the blotter")
    assert tasks == ["Make the dashboard legend bigger.", "Why did the checker skip the retest?", "Add a column to the blotter"]
    agents = [agent for agent, _ in guard.plan("Make the dashboard legend bigger. Also why did the checker skip the retest?")]
    assert agents == [guard.CURSOR_EDITOR, guard.CLAUDE]


def test_a_redirect_hands_over_a_ready_prompt():
    action, message = guard.route_prompt("add a column to the blotter and open a PR", guard.CLAUDE)
    assert action == "block"
    assert "Paste into a Cursor cloud agent" in message and "Read AGENTS.md first" in message
    assert "scripts/blotter.py" in message and "cursor/ branch" in message and "test_freeze" in message


def test_a_mixed_message_runs_here_and_hands_back_the_cursor_part(monkeypatch, capsys):
    mixed = {"prompt": "why did the checker skip the retest? also make the dashboard legend bigger"}
    out = _run("claude-prompt", mixed, monkeypatch, capsys)
    note = out["hookSpecificOutput"]["additionalContext"]
    assert "Do the Claude Code parts" in note and "Make the dashboard legend bigger" in note
    assert "scripts/dashboard_page.html" in note and "Why did the checker" not in note.split("```")[1]
    in_cursor = _run("cursor-prompt", mixed, monkeypatch, capsys)
    assert in_cursor["continue"] is False
    assert "Paste into Claude Code" in in_cursor["user_message"] and "Then resend only this here" in in_cursor["user_message"]


def test_the_cli_shows_every_part_with_its_prompt():
    text = guard.advice("Make the dashboard legend bigger. Also why did the checker skip the retest?")
    assert text.startswith("Split:") and "Paste into Claude Code" in text and "Paste into Cursor in the editor" in text
