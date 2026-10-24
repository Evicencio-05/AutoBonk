"""The !levels command arms the book from the operator's note with no model."""

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
_SPEC = importlib.util.spec_from_file_location("levels_ingest", SCRIPTS / "levels_ingest.py")
ingest = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ingest)

PT = ZoneInfo("America/Los_Angeles")
OPERATOR = "254654676585152512"

# The operator's 2026-10-23 06:24 PT note, as forwarded.
FRIDAY = """PM Levels:
- AAPL: Res:  349 → 350.5 → 353 → 359.19 / Sup: 345.37 → 343.8 → 342.5 → 241.37
- AMD: Res: 524 → 551 → 556.75 → 562.42 / Sup: 500 → 485.25 -> 453.65
- META: Res: 645 -> 573 -> 680 -> 712 / Sup: 636.75 -> 600 -> 554
- MU: RES: 895 -> 900 -> 920 -> 930 / Sup: 844 -> 800 -> 783 -> 737 -> 670
- NVDA: Res: 217.5 -> 222 -> 226 - > 228 / Sup: 211.18 -> 208.9 -> 204 -> 202
- TSLA: Res: 380 -> 382.75 -> 388 / Sup: 372.75 -> 367.75 -> 365.3 -> 360.45 -> 352 -> 342.5"""


def _at(hour, minute, day=23):
    return datetime(2026, 10, day, hour, minute, tzinfo=PT)


def test_friday_note_reads_every_arrow_and_label():
    books, warnings, errors = ingest.parse_note(FRIDAY)
    assert errors == []
    assert list(books) == ["AAPL", "AMD", "META", "MU", "NVDA", "TSLA"]
    assert books["NVDA"]["res"] == ["217.5", "222", "226", "228"]
    assert books["MU"]["res"] == ["895", "900", "920", "930"]
    assert books["AMD"]["sup"] == ["500", "485.25", "453.65"]
    assert any("META Res 573 is lower than 645" in line for line in warnings)
    assert any("AAPL Sup 241.37 is 30%" in line for line in warnings)


def test_rows_match_the_book_armed_by_hand_on_friday():
    books, _, _ = ingest.parse_note(FRIDAY)
    rows = ingest.build_levels(books)
    aapl = [row for row in rows if row["ticker"] == "AAPL"]
    assert aapl[0] == {
        "ticker": "AAPL",
        "price": 349,
        "side": "claim",
        "allows": "long",
        "targets": [350.5, 353, 359.19],
        "note": "Resistance 349, then 350.5, 353, 359.19",
    }
    assert aapl[-1] == {
        "ticker": "AAPL",
        "price": 241.37,
        "side": "lose",
        "allows": "short",
        "targets": [],
        "note": "Then 241.37",
    }
    assert len(rows) == 8 + 7 + 7 + 9 + 8 + 9


def test_an_unreadable_line_is_left_out():
    books, _, errors = ingest.parse_note(
        "- AAPL: Res: 349 -> 35O / Sup: 345\n- AMD: Res: 524 / Sup: 500\n"
    )
    assert list(books) == ["AMD"]
    assert errors == ["AAPL Res: `35O` is not a number"]


def test_markdown_and_missing_sides():
    books, _, errors = ingest.parse_note("**SPY**: Resistance: 600 → 605 / Support: none")
    assert errors == []
    assert books == {"SPY": {"res": ["600", "605"], "sup": []}}


def test_arm_time_moves_after_the_close_to_the_next_weekday():
    assert ingest.arm_time(_at(6, 24)) == _at(6, 24)
    assert ingest.arm_time(_at(14, 0)) == _at(4, 0, day=26)
    assert ingest.arm_time(_at(20, 0, day=25)) == _at(4, 0, day=26)


def test_a_new_session_replaces_the_book_and_the_checker_reads_it(tmp_path):
    path = tmp_path / "levels.yaml"
    path.write_text('armed_at: "2026-10-22T06:20:00-07:00"\nlevels:\n- ticker: OLD\n  price: 1\n'
                    "  side: claim\n  allows: long\n  targets: []\n  note: x\n")
    books, warnings, _ = ingest.parse_note(FRIDAY)
    result = ingest.arm(books, _at(6, 25), path=path, source="1", warnings=warnings)
    assert result["mode"] == "new"
    spec = ingest.claim.load_levels(path)
    assert spec["armed_at"] == _at(6, 25)
    assert {row["ticker"] for row in spec["levels"]} == set(books)
    text = path.read_text()
    assert "# META Res 573 is lower than 645" in text
    assert (tmp_path / "levels.prev.yaml").read_text().count("OLD") == 1


def _bars(low, high):
    """Two finished 10-minute bars after 06:30 PT that trade from low to high."""

    def fetch(ticker):
        start = int(_at(6, 30).timestamp())
        return [
            (start + step * 300, low, high, low, high) for step in range(4)
        ]

    return fetch


def test_a_same_session_note_replaces_only_its_tickers(tmp_path):
    path = tmp_path / "levels.yaml"
    books, _, _ = ingest.parse_note(FRIDAY)
    ingest.arm(books, _at(6, 24), path=path)
    fix, _, _ = ingest.parse_note("- TSLA: Res: 380 -> 382.75 -> 388 / Sup: 372.77 -> 367.75")
    result = ingest.arm(fix, _at(6, 51), path=path, fetch=_bars(375, 379))
    assert result["mode"] == "merged" and result["tickers"] == ["TSLA"]
    spec = ingest.claim.load_levels(path)
    assert spec["armed_at"] == _at(6, 24)
    tsla = [row["price"] for row in spec["levels"] if row["ticker"] == "TSLA"]
    assert tsla == [380, 382.75, 388, 372.77, 367.75]
    assert [row["ticker"] for row in spec["levels"]][0] == "AAPL"
    assert "# 06:51 PT: TSLA replaced" in path.read_text()


def test_a_new_number_price_already_crossed_is_held(tmp_path):
    path = tmp_path / "levels.yaml"
    books, _, _ = ingest.parse_note(FRIDAY)
    ingest.arm(books, _at(6, 24), path=path)
    before = path.read_text()
    fix, _, _ = ingest.parse_note("- TSLA: Res: 376 / Sup: 372.75")
    result = ingest.arm(fix, _at(7, 0), path=path, fetch=_bars(374, 378))
    assert result["held"] == {"TSLA": [376.0]} and result["tickers"] == []
    assert path.read_text() == before
    forced = ingest.arm(fix, _at(7, 0), path=path, fetch=_bars(374, 378), force=True)
    assert forced["tickers"] == ["TSLA"]


def _message(mid, content, author=OPERATOR, bot=False, forward=None, minute=25):
    row = {
        "id": str(mid),
        "channel_id": "9",
        "author": {"id": author, "username": "x", "bot": bot},
        "timestamp": _at(6, minute).isoformat(),
        "content": content,
    }
    if forward:
        row["content"] = ""
        row["message_snapshots"] = [{"message": {"content": forward}}]
    return row


def _discord(rows):
    sent = []

    def get(route):
        if "before=" in route:
            before = int(route.split("before=")[1].split("&")[0])
            return [row for row in rows if int(row["id"]) < before]
        after = int(route.split("after=")[1].split("&")[0])
        return [row for row in rows if int(row["id"]) > after]

    def post(route, body):
        sent.append(body)

    return get, post, sent


def test_poll_arms_a_forwarded_note_on_a_bare_command(tmp_path):
    base = ingest._snowflake(_at(6, 20).timestamp())
    rows = [
        _message(base + 1, "", forward=FRIDAY, minute=24),
        _message(base + 2, "!levels", author="111"),
        _message(base + 3, "AAPL call entry 349", author="222", bot=True),
        _message(base + 4, "!levels", minute=25),
    ]
    get, post, sent = _discord(rows)
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"channel": "9"}))
    path = tmp_path / "levels.yaml"
    ingest.poll(_at(6, 26), get=get, post=post, path=path, state_path=state)
    assert len(sent) == 1
    assert sent[0]["message_reference"] == {"message_id": str(base + 4)}
    assert sent[0]["content"].startswith("Armed a new book for Fri 10/23: 6 tickers")
    assert "Not an order." in sent[0]["content"]
    assert ingest.claim.load_levels(path)["armed_at"] == _at(6, 25)
    assert json.loads(state.read_text())["last_id"] == str(base + 4)
    ingest.poll(_at(6, 27), get=get, post=post, path=path, state_path=state)
    assert len(sent) == 1


def test_preview_writes_nothing(tmp_path):
    base = ingest._snowflake(_at(6, 20).timestamp())
    get, post, sent = _discord([_message(base + 1, "!levels preview\n" + FRIDAY)])
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"channel": "9"}))
    path = tmp_path / "levels.yaml"
    ingest.poll(_at(6, 26), get=get, post=post, path=path, state_path=state)
    assert sent[0]["content"].startswith("Preview: 6 tickers read. Nothing armed.")
    assert "`NVDA` R 217.5 › 222 › 226 › 228 | S 211.18 › 208.9 › 204 › 202" in sent[0]["content"]
    assert not path.exists()


def test_a_command_older_than_half_an_hour_is_ignored(tmp_path):
    base = ingest._snowflake(_at(6, 20).timestamp())
    get, post, sent = _discord([_message(base + 1, "!levels\n" + FRIDAY)])
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"channel": "9"}))
    ingest.poll(_at(7, 30), get=get, post=post, path=tmp_path / "l.yaml", state_path=state)
    assert sent == []
