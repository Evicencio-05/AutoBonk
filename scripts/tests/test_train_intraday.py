"""The first green or red candle is not automatically the confirmed candle."""

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "train_intraday",
    Path(__file__).resolve().parents[1] / "train_intraday.py",
)
train_intraday = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(train_intraday)


def _bar(close_at: int, open_: float, close: float) -> dict:
    return {"close_at": close_at, "open": open_, "close": close}


def test_score_flags_the_flat_green_and_the_small_red():
    bars = [
        _bar(0, 11.0, 10.6),
        _bar(1, 10.6, 10.0),
        _bar(2, 9.90, 9.93),
        _bar(3, 9.95, 10.40),
        _bar(4, 10.30, 10.10),
        _bar(5, 10.00, 8.50),
    ]

    scored = train_intraday.score_put(bars, level=10.5, buy_at=3, sell_at=5)

    assert scored["naive_buy"]["close_at"] == 2
    assert scored["ideal_buy"]["close_at"] == 3
    assert scored["buy_bars_early"] == 1
    assert scored["naive_sell"]["close_at"] == 4
    assert scored["ideal_sell"]["close_at"] == 5
    assert scored["sell_bars_early"] == 1
    assert scored["sell_price_gap"] == 10.10 - 8.50


def test_a_put_bottom_is_the_green_that_pushed():
    bars = [
        _bar(0, 11.0, 10.6),
        _bar(1, 10.6, 10.0),
        _bar(2, 9.90, 9.93),
        _bar(3, 9.95, 10.40),
        _bar(4, 10.30, 10.10),
        _bar(5, 10.00, 8.50),
    ]

    bottom = train_intraday.score_bottom(bars, "put", 10.5, 3)

    assert bottom["sniped"] is True
    assert bottom["bottom"]["close_at"] == 3
    assert bottom["naive"]["close_at"] == 2
    assert bottom["ideal_left"] == 0
    assert bottom["naive_left"] == 10.40 - 9.93


def test_a_call_bottom_is_the_red_that_dipped():
    bars = [
        _bar(0, 9.4, 9.2),
        _bar(1, 9.6, 10.4),
        _bar(2, 10.50, 10.30),
        _bar(3, 10.20, 10.05),
        _bar(4, 10.10, 10.40),
    ]

    bottom = train_intraday.score_bottom(bars, "call", 10.0, 3)
    scored = train_intraday.score_call(bars, 10.0, 3, 4)

    assert bottom["sniped"] is True
    assert bottom["bottom"]["close_at"] == 3
    assert bottom["naive"]["close_at"] == 2
    assert round(bottom["naive_left"], 2) == 0.25
    assert scored["naive_buy"]["close_at"] == 2
    assert scored["ideal_sell"]["close_at"] == 4
    assert scored["buy_price_gap"] == 10.30 - 10.05


def test_the_first_goal_is_sniping_the_contract_bottom():
    import yaml

    root = Path(__file__).resolve().parents[2]
    goal = train_intraday.first_goal(
        yaml.safe_load((root / "learning" / "goals.yaml").read_text())
    )
    lesson = (root / "learning" / "lessons" / "snipe-bottom.md").read_text()
    training = (root / "learning" / "training.md").read_text()

    assert goal["id"] == "snipe-bottom"
    assert goal["title"] == "Sniping the bottom on contracts"
    assert "Buy calls on a red candle" in goal["says"]

    assert "not an order" in lesson
    assert "0.43 stock points" in lesson
    assert "did not wick within 15 cents of 146.5" in lesson
    assert "The live entry stays the retest." in lesson
    assert "not a priced premium" in lesson
    assert "1 bar early, 0.43 less stock-price strength" in training
    assert "16 bars early, 2.72 of the drop left behind" in training
    assert "did not wick within 15 cents of 146.5" in training


def test_the_live_retest_buys_the_confirmed_spcx_bottom():
    """The 09:10 green did not tag 146.5. The retest buys the 09:20 push."""
    import json
    from datetime import datetime
    from zoneinfo import ZoneInfo

    root = Path(__file__).resolve().parents[2]
    zone = ZoneInfo("America/Los_Angeles")
    claim_spec = importlib.util.spec_from_file_location(
        "claim_alerts",
        root / "scripts" / "claim_alerts.py",
    )
    claim = importlib.util.module_from_spec(claim_spec)
    claim_spec.loader.exec_module(claim)

    raw = json.loads((root / "bench/fixtures/2026-10-16-bars.json").read_text())
    bars = claim.add_indicators(
        [
            {
                "close_at": int(bar["close_at"]),
                "o": float(bar["o"]),
                "h": float(bar["h"]),
                "l": float(bar["l"]),
                "c": float(bar["c"]),
            }
            for bar in raw["tickers"]["SPCX"]
        ]
    )
    nine_ten = datetime(2026, 10, 16, 9, 10, tzinfo=zone).timestamp()
    nine_twenty = datetime(2026, 10, 16, 9, 20, tzinfo=zone).timestamp()
    flat = next(bar for bar in bars if bar["close_at"] == nine_ten)
    pushed = next(bar for bar in bars if bar["close_at"] == nine_twenty)
    assert flat["h"] < 146.5 - 0.15
    assert pushed["h"] >= 146.5 - 0.15
    assert abs((pushed["c"] - flat["c"]) - 0.43) < 0.02

    armed = int(datetime.fromisoformat("2026-10-16T08:27:30-07:00").timestamp())
    events = claim.replay(
        bars,
        [{"ticker": "SPCX", "price": 146.5, "allows": "both", "targets": [142.6]}],
        armed,
        claim.live_settings(),
    )
    entries = [event for event in events if event["kind"] == "entry"]

    assert len(entries) == 1
    assert entries[0]["side"] == "put"
    assert entries[0]["reason"] == "retest"
    assert entries[0]["bar"]["close_at"] == nine_twenty
    # The order goes out once the fill bar after the 09:20 push has closed, at that close.
    assert entries[0]["signal_at"] == int(nine_twenty)
    fill_bar = next(bar for bar in bars if bar["close_at"] == entries[0]["fill_at"])
    assert entries[0]["fill_at"] == int(nine_twenty) + 600 and entries[0]["fill"] == fill_bar["c"]
    assert claim.live_settings()["entry"] == "retest"


def test_the_spcx_drill_scores_the_frozen_file_without_a_refetch():
    import yaml

    root = Path(__file__).resolve().parents[2]
    drills = yaml.safe_load((root / "learning" / "drills.yaml").read_text())
    drill = drills["drills"][0]

    def refetch(ticker):
        raise AssertionError(ticker)

    bars = train_intraday.bars_for_drill(drill, fetch=refetch)
    train_intraday.add_rsi(bars)
    buy_at = train_intraday._clock(drill["ideal_buy"], drill["session"])
    sell_at = train_intraday._clock(drill["ideal_sell"], drill["session"])
    scored = train_intraday.score_put(bars, float(drill["level"]), buy_at, sell_at)
    sentence = train_intraday.wick_sentence(drill["side"], float(drill["level"]), scored["naive_buy"])

    assert drill["id"] == "spcx-2026-10-16-put"
    assert scored["buy_bars_early"] == 1
    assert round(scored["buy_price_gap"], 2) == 0.43
    assert scored["sell_bars_early"] == 16
    assert round(scored["sell_price_gap"], 2) == 2.72
    assert "09:10 PT green did not wick within 15 cents of 146.5" in sentence
    assert "skip" not in sentence.lower()
    assert train_intraday.WICK == 0.15


def test_a_missing_session_is_frozen_once_and_then_read():
    import json
    from datetime import datetime
    from zoneinfo import ZoneInfo

    zone = ZoneInfo("America/Los_Angeles")
    start = int(datetime(2026, 10, 16, 9, 0, tzinfo=zone).timestamp())
    calls = {"n": 0}

    def fetch(ticker):
        calls["n"] += 1
        assert ticker == "QQQ"
        return [
            (start, 10.0, 10.2, 9.8, 10.1),
            (start + 300, 10.1, 10.4, 10.0, 10.3),
        ]

    root = Path(__file__).resolve().parents[2]
    fixtures = root / "bench" / "fixtures"
    # Keep the freeze off the real bench files.
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        drill = {"ticker": "QQQ", "session": "2026-10-16"}
        first = train_intraday.bars_for_drill(drill, fixtures=Path(tmp), fetch=fetch)
        second = train_intraday.bars_for_drill(
            drill,
            fixtures=Path(tmp),
            fetch=lambda ticker: (_ for _ in ()).throw(AssertionError(ticker)),
        )
        stored = json.loads((Path(tmp) / "2026-10-16-bars.json").read_text())

    assert calls["n"] == 1
    assert first[0]["open"] == 10.0
    assert first[0]["high"] == 10.4
    assert first[0]["low"] == 9.8
    assert first[0]["close"] == 10.3
    assert second == first
    assert stored["tickers"]["QQQ"][0]["h"] == 10.4
    assert fixtures == train_intraday.FIXTURES


def test_a_frozen_file_without_the_ticker_is_not_refetched():
    import json
    import tempfile

    def refetch(ticker):
        raise AssertionError(ticker)

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "2026-10-23-bars.json"
        path.write_text(json.dumps({"tickers": {"AAPL": []}}))
        before = path.read_text()
        try:
            train_intraday.bars_for_drill(
                {"ticker": "QQQ", "session": "2026-10-23"},
                fixtures=Path(tmp),
                fetch=refetch,
            )
        except SystemExit as stopped:
            message = str(stopped)
        else:
            raise AssertionError("expected the frozen file to stop the refetch")
        assert path.read_text() == before

    assert "no QQQ bars" in message
    assert "does not refetch" in message


def test_a_tagged_call_wick_does_not_change_the_entry():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    close_at = int(datetime(2026, 10, 16, 10, 0, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())
    tagged = {"close_at": close_at, "low": 10.10, "high": 10.50}
    short = {"close_at": close_at, "low": 10.20, "high": 10.50}
    text = train_intraday.wick_sentence("call", 10.0, tagged)

    assert train_intraday.wick_tagged("call", 10.0, tagged) is True
    assert train_intraday.wick_tagged("call", 10.0, short) is False
    assert "10:00 PT red wicked within 15 cents of 10" in text
    assert "The checker could take that candle." in text
    assert "The live entry stays the retest." in text
    assert "skip" not in text.lower()
