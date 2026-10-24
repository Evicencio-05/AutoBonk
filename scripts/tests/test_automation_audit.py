"""The automation audit counts repeated agent work from transcripts, with no model."""

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "automation_audit", Path(__file__).resolve().parents[1] / "automation_audit.py"
)
audit = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(audit)

SINCE = datetime(2026, 10, 1, tzinfo=timezone.utc)


def test_commands_become_steps_and_inline_code_is_one_step():
    assert audit.step_of("cd x && python3 scripts/ledger.py show | head") == ["python3 ledger.py show"]
    assert audit.step_of("python3 - <<'EOF'\nimport x\nfor y in z:\n  print(y)\nEOF\ngit status") == [
        "python3 inline",
        "git status",
    ]
    assert audit.step_of('python3 -c "import a\nfor b in c: pass" && gh pr merge 3 --merge') == [
        "python3 inline",
        "gh pr merge",
    ]
    assert audit.step_of("FOO=1 .venv/bin/python3 scripts/bench.py compare --levels a \\\n --bars b") == [
        "python3 bench.py compare"
    ]


def test_prompts_are_sorted_into_kinds():
    assert audit.kind_of("The charts are in, arm the levels") == "levels"
    assert audit.kind_of("Merge all PRs") == "merge and ship"
    assert audit.kind_of("Why did the GOOGL put show a loss?") == "trade result"
    assert audit.kind_of("hello") == "other"


def _claude(tmp_path):
    rows = [
        {"type": "user", "sessionId": "s1", "timestamp": "2026-10-23T13:00:00Z",
         "message": {"content": "Merge it"}},
        {"type": "assistant", "requestId": "r1", "message": {"id": "m1",
         "usage": {"input_tokens": 10, "cache_creation_input_tokens": 100, "output_tokens": 5,
                   "cache_read_input_tokens": 1000},
         "content": [{"type": "tool_use", "name": "Bash", "input": {"command": "gh pr merge 3 --merge"}}]}},
        # A second content block of the same response repeats its usage. Count it once.
        {"type": "assistant", "requestId": "r1", "message": {"id": "m1",
         "usage": {"input_tokens": 10, "cache_creation_input_tokens": 100, "output_tokens": 5},
         "content": [{"type": "tool_use", "name": "Bash", "input": {"command": "git pull"}}]}},
        {"type": "user", "sessionId": "s1", "timestamp": "2026-10-23T13:01:00Z",
         "message": {"content": [{"type": "tool_result", "content": "ok"}]}},
        {"type": "user", "isMeta": True, "message": {"content": "<system-reminder>x</system-reminder>"}},
        {"type": "user", "sessionId": "s1", "timestamp": "2026-10-23T13:05:00Z",
         "message": {"content": "This session is being continued from a previous conversation"}},
    ]
    path = tmp_path / "claude" / "s1.jsonl"
    path.parent.mkdir()
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    return path.parent


def test_claude_turns_count_each_response_once(tmp_path):
    turns = audit.claude_turns(_claude(tmp_path))
    assert len(turns) == 1
    assert turns[0]["prompt"] == "Merge it"
    assert turns[0]["fresh"] == 115 and turns[0]["cached"] == 1000
    assert turns[0]["steps"] == ["gh pr merge", "git pull"]


def test_cursor_turns_read_the_query_and_its_time(tmp_path):
    rows = [
        {"role": "user", "message": {"content": [{"type": "text", "text":
            "<timestamp>Friday, Oct 23, 2026, 6:49 AM (UTC-7)</timestamp>\n<user_query>\nArm the levels\n</user_query>"}]}},
        {"role": "assistant", "message": {"content": [{"type": "tool_use", "name": "Shell",
            "input": {"command": "python3 scripts/discord_ta.py ingest"}}]}},
    ]
    path = tmp_path / "cursor" / "a" / "a.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    turns = audit.cursor_turns(tmp_path / "cursor")
    assert turns[0]["prompt"] == "Arm the levels"
    assert turns[0]["at"] == "2026-10-23T06:49:00-07:00"
    assert turns[0]["steps"] == ["python3 discord_ta.py ingest"]


def test_the_report_groups_kinds_and_repeated_recipes(tmp_path):
    turn = {"tool": "claude", "session": "s", "prompt": "Merge it", "fresh": 100, "cached": 0,
            "steps": ["gh pr checks", "gh pr merge"], "skills": []}
    turns = [
        {**turn, "at": "2026-10-20T13:00:00Z"},
        {**turn, "at": "2026-10-21T13:00:00Z", "session": "t"},
        {**turn, "at": "2026-10-21T13:00:00Z", "session": "t"},
        {**turn, "at": "2026-09-01T13:00:00Z"},
    ]
    report = audit.build(turns, SINCE)
    assert report["turns"] == 2
    assert report["kinds"][0] == {
        "kind": "merge and ship", "turns": 2, "sessions": 2, "fresh": 200, "per_turn": 100, "cached": 0,
        "cursor_turns": 0, "scripted_by": "", "examples": ["Merge it", "Merge it"],
    }
    assert report["recipes"][0]["steps"] == ["gh pr checks", "gh pr merge"]
    text = audit.markdown(report, "2026-10-23")
    assert "| merge and ship | 2 | 2 | 200 | 100 |" in text
    assert "gh pr checks → gh pr merge" in text
