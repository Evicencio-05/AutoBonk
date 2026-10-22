"""A frozen day reprints the same events. One variable moves at a time."""

import importlib.util
import json
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "bench",
    Path(__file__).resolve().parents[1] / "bench.py",
)
bench = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bench)


def _bar(close_at, open_, high, low, close):
    return {"close_at": close_at, "o": open_, "h": high, "l": low, "c": close}


def _write_day(root: Path, levels: str, bars: dict) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    levels_path = root / "levels.yaml"
    bars_path = root / "bars.json"
    levels_path.write_text(levels)
    bars_path.write_text(json.dumps(bars))
    return levels_path, bars_path


def _put_day(root: Path) -> tuple[Path, Path]:
    levels = """
armed_at: "1970-01-01T00:00:00+00:00"
levels:
  - ticker: SPCX
    price: 146
    allows: short
    targets: [142.5, 138.5]
    stop: 146.5
    chart: charts/inbox/spcx.webp
  - ticker: NVDA
    price: 1000
    allows: long
    targets: []
    chart: charts/inbox/nvda.webp
"""
    bars = {
        "SPCX": [
            _bar(600, 147.2, 147.8, 146.4, 147.0),
            _bar(1200, 147.0, 147.1, 145.4, 145.7),
            _bar(1800, 145.6, 146.06, 145.3, 145.85),
            _bar(2400, 145.84, 146.0, 145.4, 145.7),
            _bar(3000, 145.2, 145.4, 142.2, 142.4),
            _bar(3600, 142.1, 142.3, 138.0, 138.2),
            _bar(4200, 146.8, 147.2, 146.6, 147.0),
        ]
    }
    return _write_day(root, levels, bars)


def test_two_identical_runs_match(tmp_path=None):
    root = Path(tmp_path or "/tmp/autobonk-bench-same")
    levels, bars = _put_day(root / "day")
    first = bench.run(levels, bars, 4200, root / "a")
    second = bench.run(levels, bars, 4200, root / "b")

    assert first["events"] == second["events"]
    assert "touch" in first["settings"]
    assert first["settings"]["touch"]["value"] == 0.15
    assert first["settings"]["exit"]["value"] == "target"
    assert first["events"]["tickers"] == ["SPCX", "NVDA"]
    assert not any(event["ticker"] == "NVDA" for event in first["events"]["events"])
    code = json.loads((root / "a" / "code.json").read_text())
    assert "git" in code or "claim_alerts_sha256" in code
    saved = json.loads((root / "a" / "events.json").read_text())
    assert saved == first["events"]
    assert (root / "a" / "levels.json").is_file()
    assert (root / "a" / "bars.json").is_file()
    assert (root / "a" / "code.json").is_file()


def test_a_second_differing_run_fails_and_writes_nothing(tmp_path=None):
    root = Path(tmp_path or "/tmp/autobonk-bench-diff")
    levels, bars = _put_day(root / "day")
    state = {"n": 0}

    def flip(prepared, settings):
        del prepared, settings
        state["n"] += 1
        if state["n"] % 2 == 0:
            return [{"ticker": "SPCX", "kind": "entry"}]
        return []

    out = root / "out"
    try:
        bench.run(levels, bars, 4200, out, decide_fn=flip)
    except bench.BenchError as exc:
        assert "repeat differed" in str(exc)
    else:
        raise AssertionError("the differing repeat was published")
    assert not out.exists()


def test_two_variables_are_rejected(tmp_path=None):
    root = Path(tmp_path or "/tmp/autobonk-bench-two")
    levels, bars = _put_day(root / "day")
    settings = root / "settings.yaml"
    settings.write_text("touch: 0.05\nchase: 1\n")
    out = root / "out"
    try:
        bench.run(levels, bars, 4200, out, settings)
    except bench.BenchError as exc:
        assert "one variable" in str(exc)
    else:
        raise AssertionError("two variables were accepted")
    assert not out.exists()


def test_a_variable_with_no_default_is_rejected(tmp_path=None):
    root = Path(tmp_path or "/tmp/autobonk-bench-default")
    levels, bars = _put_day(root / "day")
    settings = root / "settings.yaml"
    settings.write_text("touch:\n")
    try:
        bench.run(levels, bars, 4200, root / "out", settings)
    except bench.BenchError as exc:
        assert "no default" in str(exc)
    else:
        raise AssertionError("a null variable was accepted")
    try:
        bench.claim._default_of("touch", {"type": "float"})
    except ValueError as exc:
        assert "no default" in str(exc)
    else:
        raise AssertionError("a registry entry without a default was accepted")


def test_a_bar_after_as_of_cannot_fill(tmp_path=None):
    root = Path(tmp_path or "/tmp/autobonk-bench-asof")
    levels, bars = _put_day(root / "day")

    early = bench.run(levels, bars, 1800, root / "early")
    late = bench.run(levels, bars, 4200, root / "late")

    assert early["events"]["events"] == []
    assert any(event["kind"] == "entry" for event in late["events"]["events"])
    saved = json.loads((root / "early" / "bars.json").read_text())
    assert all(bar["close_at"] <= 1800 for bar in saved["tickers"]["SPCX"])


def test_stop_does_not_emit_a_target_exit(tmp_path=None):
    root = Path(tmp_path or "/tmp/autobonk-bench-stop")
    levels, bars = _put_day(root / "day")
    record = bench.compare(
        levels,
        bars,
        4200,
        "exit",
        "stop",
        "Does a named stop replace the target exit on this frozen day?",
        "discovery",
        root / "experiment",
    )

    assert record["day"] == "discovery"
    assert record["default_value"] == "target"
    assert record["variant_value"] == "stop"
    assert any(event["reason"] == "target" for event in record["default_events"])
    assert not any(event["reason"] == "target" for event in record["variant_events"])
    assert any(event["reason"] == "stop" for event in record["variant_events"])
    assert record["difference"]["exits_moved"]
    text = (root / "experiment" / "experiment.md").read_text()
    assert "discovery" in text
    assert "rules/ta_rules.md" not in text


def test_a_level_without_a_price_is_rejected(tmp_path=None):
    root = Path(tmp_path or "/tmp/autobonk-bench-price")
    levels = """
armed_at: "1970-01-01T00:00:00+00:00"
levels:
  - ticker: MSFT
    allows: long
    note: high watch
"""
    bars = {"MSFT": []}
    levels_path, bars_path = _write_day(root / "day", levels, bars)
    try:
        bench.run(levels_path, bars_path, 4200, root / "out")
    except bench.BenchError as exc:
        assert "no numbered price" in str(exc)
    else:
        raise AssertionError("a level without a price was scored")


def test_an_unrecorded_contract_is_not_priced(tmp_path=None):
    root = Path(tmp_path or "/tmp/autobonk-bench-contract")
    levels, bars = _put_day(root / "day")
    payload = bench.run(levels, bars, 4200, root / "out")

    assert payload["contracts"]
    assert all(row["status"] == "not recorded" for row in payload["contracts"])
    assert "debit" not in payload["contracts"][0]


def test_a_taken_level_without_a_stop_is_rejected(tmp_path=None):
    root = Path(tmp_path or "/tmp/autobonk-bench-nostop")
    levels, bars = _put_day(root / "day")
    text = (root / "day" / "levels.yaml").read_text().replace("    stop: 146.5\n", "")
    (root / "day" / "levels.yaml").write_text(text)
    settings = root / "settings.yaml"
    settings.write_text("exit: stop\n")
    out = root / "out"
    try:
        bench.run(levels, bars, 4200, out, settings)
    except bench.BenchError as exc:
        assert "no stop price" in str(exc)
    else:
        raise AssertionError("a stop run without a stop price was published")
    assert not out.exists()


def test_an_otm_contract_without_room_is_not_scored():
    events = [
        {
            "ticker": "SPCX",
            "side": "put",
            "level": 146,
            "kind": "entry",
            "reason": "retest",
            "bar_time": "1970-01-01 00:40 PT",
            "fill": 145.84,
        }
    ]
    scored = bench.score_contracts(
        events,
        [
            {
                "ticker": "SPCX",
                "bar_time": "1970-01-01 00:40 PT",
                "strike": 140,
                "expiration": "1970-01-02",
                "debit": 1.2,
                "otm": True,
                "theta_room": False,
            }
        ],
    )

    assert scored[0]["status"] == "not scored"
    assert "debit" not in scored[0]


def test_a_day_with_no_difference_is_published(tmp_path=None):
    root = Path(tmp_path or "/tmp/autobonk-bench-same-setting")
    levels, bars = _put_day(root / "day")
    record = bench.compare(
        levels,
        bars,
        4200,
        "touch",
        0.15,
        "Does touch 0.15 change the event list versus touch 0.15 on this frozen day?",
        "confirmation",
        root / "experiment",
    )

    assert record["day"] == "confirmation"
    assert record["difference"]["entries_added"] == []
    assert "No difference." in (root / "experiment" / "experiment.md").read_text()
