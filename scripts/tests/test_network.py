"""A rate limit or a dropped connection is retried, and an alert failure never stops a check."""

import importlib.util
import io
import json
import urllib.error
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "claim_alerts", Path(__file__).resolve().parents[1] / "claim_alerts.py"
)
claim = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(claim)
claim.SEND_ORDERS = False


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _limited(retry_after="0"):
    return urllib.error.HTTPError("https://x", 429, "Too Many Requests", {"Retry-After": retry_after}, io.BytesIO(b""))


def _opener(script):
    calls = []

    def urlopen(request, timeout=0):
        calls.append(request.full_url)
        step = script[min(len(calls) - 1, len(script) - 1)]
        if isinstance(step, BaseException):
            raise step
        return _Response(json.dumps(step).encode())

    return urlopen, calls


def test_price_history_waits_out_a_rate_limit(monkeypatch):
    chart = {"chart": {"result": [{"timestamp": [1], "indicators": {"quote": [{"open": [1], "high": [1], "low": [1], "close": [1], "volume": [1]}]}}]}}
    urlopen, calls = _opener([_limited(), chart])
    monkeypatch.setattr(claim.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(claim.time, "sleep", lambda seconds: None)
    assert claim.fetch_five_minute("AVGO") == [(1, 1, 1, 1, 1, 1)]
    assert len(calls) == 2


def test_price_history_gives_up_after_three_tries(monkeypatch):
    urlopen, calls = _opener([_limited()])
    monkeypatch.setattr(claim.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(claim.time, "sleep", lambda seconds: None)
    try:
        claim.fetch_five_minute("AVGO")
    except SystemExit as exc:
        assert "429" in str(exc)
    else:
        raise AssertionError("expected SystemExit")
    assert len(calls) == claim.RETRIES


def test_the_ta_channel_is_looked_up_once_per_process(monkeypatch):
    guilds = [{"id": "g"}]
    channels = [{"name": "ta", "type": 0, "id": "c"}]
    urlopen, calls = _opener([guilds, channels, {}, {}, {}])
    monkeypatch.setattr(claim.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(claim, "_token", lambda: "t")
    monkeypatch.setattr(claim, "_CHANNEL", {})
    claim.notify_discord("one")
    claim.notify_discord("two")
    assert sum("/guilds" in url for url in calls) == 2
    assert sum("/messages" in url for url in calls) == 2


def test_no_discord_failure_stops_a_check(monkeypatch):
    for failure in (_limited(), urllib.error.URLError("down"), SystemExit("Discord #ta was not found"), TimeoutError()):
        def boom(text, failure=failure):
            raise failure

        monkeypatch.setattr(claim, "notify_discord", boom)
        claim._send_alert("GOOGL call entry", True)


def test_the_pause_honors_retry_after_but_caps_it(monkeypatch):
    waited = []
    monkeypatch.setattr(claim.time, "sleep", waited.append)
    claim._pause(_limited("3"), 0)
    claim._pause(_limited("120"), 0)
    claim._pause(None, 1)
    assert waited == [3.0, claim.MAX_PAUSE, 2.0]
