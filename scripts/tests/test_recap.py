"""The recap may apply buffer sizes only when the forward day agrees."""

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "recap",
    Path(__file__).resolve().parents[1] / "recap.py",
)
recap = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(recap)

_CLAIM = importlib.util.spec_from_file_location(
    "claim_alerts_for_recap",
    Path(__file__).resolve().parents[1] / "claim_alerts.py",
)
claim = importlib.util.module_from_spec(_CLAIM)
_CLAIM.loader.exec_module(claim)


def _stats(net, trades, drawdown=0.0):
    return {"net": net, "trades": trades, "profit_factor": None, "max_drawdown": drawdown, "win_rate": None}


def _combo(**overrides):
    combo = dict(recap.code_buffers())
    combo.update(overrides)
    return {name: combo[name] for name in recap.LIVE}


def test_a_flat_sweep_keeps_the_live_value():
    points = [{"value": value, "net": 1.0} for value in (0, 0.25, 0.5)]
    assert recap.shortlist(points, 0.15) == [0.15]


def test_the_gate_rejects_a_train_winner_that_loses_the_forward_day():
    defaults = recap.code_buffers()
    combo = _combo(touch=0.05)
    apply, reason = recap.decide(
        combo,
        defaults,
        _stats(4, 6),
        _stats(-1, 3),
        _stats(1, 3),
        True,
    )
    assert apply is False
    assert "forward day" in reason


def test_the_gate_rejects_a_spike_and_two_edges():
    defaults = recap.code_buffers()
    spike, spike_reason = recap.decide(
        _combo(chase=0.8),
        defaults,
        _stats(5, 6),
        _stats(2, 3),
        _stats(0, 3),
        False,
    )
    assert spike is False
    assert "spike" in spike_reason

    edges, edge_reason = recap.decide(
        _combo(touch=0.0, sma_band=2.0),
        defaults,
        _stats(5, 6),
        _stats(2, 3),
        _stats(0, 3),
        True,
    )
    assert edges is False
    assert "range edge" in edge_reason


def test_the_gate_keeps_a_winner_the_forward_day_beats():
    defaults = recap.code_buffers()
    apply, reason = recap.decide(
        _combo(chase=0.8),
        defaults,
        _stats(5, 6, -1),
        _stats(2, 3, -0.4),
        _stats(0.2, 3, -0.5),
        True,
    )
    assert apply is True
    assert "beat the live buffers" in reason


def test_the_checker_applies_buffers_and_ignores_a_fade_entry(tmp_path):
    path = tmp_path / "parameters.yaml"
    path.write_text("apply: true\nadopted:\n  touch: 0.05\n  entry: fade\n")
    settings = claim.checker_settings(path)
    assert settings["touch"] == 0.05
    assert settings["entry"] == "retest"
    assert settings["exit"] == "target"

    skipped = tmp_path / "off.yaml"
    skipped.write_text("apply: false\nadopted:\n  touch: 0\n")
    assert claim.checker_settings(skipped)["touch"] == claim.VARIABLES["touch"]["default"]
    assert claim.live_settings()["entry"] == "retest"


def _rendered(**overrides):
    sweep = {"low": 0, "high": 1, "points": [{"value": 0.15, "net": 1.0}], "candidates": [0.15]}
    result = {
        "train_days": ["2026-10-14"],
        "forward_day": "2026-10-16",
        "sweeps": {name: sweep for name in (*recap.LIVE, "profit_near")},
        "winner": _combo(touch=0.05),
        "old": _combo(),
        "train": _stats(4, 6),
        "forward": _stats(3.5, 2),
        "baseline_forward": _stats(1.25, 2),
        "forward_difference": 2.25,
        "folds": [
            {
                "day": "2026-10-16",
                "role": "forward",
                "winner": _stats(3.5, 2),
                "baseline": _stats(1.25, 2),
                "difference": 2.25,
            }
        ],
        "apply": False,
        "reason": "the forward day has fewer than 2 closes",
    }
    result.update(overrides)
    return recap.render(result)


def test_the_recap_states_the_day_profit_difference():
    text = _rendered()
    assert "On 2026-10-16, new parameters made +3.50 on 2 closes." in text
    assert "Old parameters made +1.25 on 2 closes." in text
    assert "Difference +2.25 stock points." in text
    assert "| 2026-10-16 | forward | +3.50 on 2 closes | +1.25 on 2 closes | +2.25 |" in text

    lost = _rendered(
        forward=_stats(-1, 2),
        baseline_forward=_stats(1.5, 2),
        forward_difference=-2.5,
        folds=[
            {
                "day": "2026-10-16",
                "role": "forward",
                "winner": _stats(-1, 2),
                "baseline": _stats(1.5, 2),
                "difference": -2.5,
            }
        ],
    )
    assert "Difference -2.50 stock points." in lost


def test_saved_sessions_forward_test_the_last_day():
    days = recap.dashboard._saved_days(recap.ROOT)
    result = recap.search(days)

    assert result["train_days"] == ["2026-10-14", "2026-10-15"]
    assert result["forward_day"] == "2026-10-16"
    assert set(result["winner"]) == set(recap.LIVE)
    text = recap.render(result)
    difference = recap._gap(result["forward"]["net"], result["baseline_forward"]["net"])
    assert result["forward_difference"] == difference
    assert f"Difference {recap._points(difference)} stock points." in text
    assert "Old parameters:" in text
    document = recap.parameters_document(result)
    assert f"forward_difference: {round(difference, 4)}" in document
    assert "Entry stays the retest" in text
    assert "does not place an order" in text
    assert "Near a level is scored and not applied" in text
    if result["apply"]:
        assert result["forward"]["net"] > result["baseline_forward"]["net"]
        assert result["forward"]["trades"] >= 2
        assert result["train"]["trades"] >= 4
    else:
        assert result["reason"]
