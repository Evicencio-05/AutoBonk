"""The hosted desk serves the same page the local server renders."""

import importlib.util
import os
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "hosted",
    Path(__file__).resolve().parents[2] / "app.py",
)
hosted = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(hosted)


def test_the_hosted_desk_serves_the_page_and_a_saved_backtest():
    client = hosted.app.test_client()
    page = client.get("/").get_data(as_text=True)
    assert "Open trades" in page
    assert "Live session" in page
    assert "place order" not in page.lower()
    result = client.post("/api/backtest", json={"bars": "saved", "levels": []})
    assert result.status_code == 200
    assert "report" in result.get_json()


def test_the_hosted_desk_does_not_rewrite_the_github_book():
    os.environ["VERCEL"] = "1"
    try:
        result = hosted.app.test_client().post("/api/book", json={"levels": []})
    finally:
        os.environ.pop("VERCEL", None)
    assert result.status_code == 400
    assert "GitHub" in result.get_json()["error"]
