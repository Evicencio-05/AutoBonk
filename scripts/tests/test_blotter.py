"""Database rows are added to the deployed tape. A missing database changes nothing."""

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "blotter",
    Path(__file__).resolve().parents[1] / "blotter.py",
)
blotter = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(blotter)


def test_a_new_log_line_is_appended_once():
    text = "- AAPL call watch 340. Already there.\n"
    row = "AAPL call watch 340. Already there."
    added = "TSLA put watch 382.75. Not a fill."
    merged = blotter.append_missing("log", text, [row, added, added])
    assert merged.count(added) == 1
    assert merged.count("Already there") == 1


def test_a_live_row_lands_above_the_open_marks():
    text = (
        "| Time | Ticker |\n"
        "|------|--------|\n"
        "| 2026-10-22 08:30 PT | SPCX |\n"
        "\n## Open marks\n"
        "| Contract | Mark |\n"
    )
    fresh = "| 2026-10-22 10:00 PT | TSLA |"
    merged = blotter.append_missing("live", text, [fresh])
    assert merged.index(fresh) < merged.index("## Open marks")
    assert merged.index("## Open marks") < merged.index("| Contract | Mark |")


def test_store_does_nothing_without_a_database():
    saved = {key: blotter.os.environ.pop(key, None) for key in ("POSTGRES_URL", "DATABASE_URL")}
    try:
        blotter.store("live", ["| 2026-10-22 10:00 PT | TSLA |"])
    finally:
        for key, value in saved.items():
            if value is not None:
                blotter.os.environ[key] = value
