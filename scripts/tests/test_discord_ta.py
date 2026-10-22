"""Forwarded Discord messages keep chart text and attachments."""

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "discord_ta",
    Path(__file__).resolve().parents[1] / "discord_ta.py",
)
discord_ta = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(discord_ta)


def test_plain_message_uses_top_level_content():
    raw = {
        "id": "1",
        "content": "SPY holding 560",
        "author": {"username": "boingbingbonk"},
        "timestamp": "2026-10-10T00:00:00.000Z",
        "attachments": [
            {
                "filename": "chart.png",
                "url": "https://cdn.example/chart.png",
                "content_type": "image/png",
                "size": 10,
            }
        ],
    }

    parsed = discord_ta.normalize_message(raw)

    assert parsed["forwarded"] is False
    assert parsed["content"] == "SPY holding 560"
    assert parsed["attachments"][0]["filename"] == "chart.png"
    assert parsed["author"] == "boingbingbonk"


def test_forward_reads_snapshot_text_and_images():
    raw = {
        "id": "2",
        "content": "",
        "flags": 16384,
        "author": {"username": "boingbingbonk"},
        "timestamp": "2026-10-10T01:00:00.000Z",
        "attachments": [],
        "message_snapshots": [
            {
                "message": {
                    "content": "NVDA daily, 50 SMA support",
                    "attachments": [
                        {
                            "filename": "image.png",
                            "url": "https://cdn.example/a.webp",
                            "content_type": "image/webp",
                            "size": 100,
                        },
                        {
                            "filename": "image.png",
                            "url": "https://cdn.example/b.png",
                            "content_type": "image/png",
                            "size": 200,
                        },
                    ],
                }
            }
        ],
    }

    parsed = discord_ta.normalize_message(raw)

    assert parsed["forwarded"] is True
    assert parsed["content"] == "NVDA daily, 50 SMA support"
    assert len(parsed["attachments"]) == 2
    assert parsed["attachments"][1]["content_type"] == "image/png"
