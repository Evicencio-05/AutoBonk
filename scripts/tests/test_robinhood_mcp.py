"""The trading client parses MCP replies and the Cursor token blob."""

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "robinhood_mcp",
    Path(__file__).resolve().parents[1] / "robinhood_mcp.py",
)
robinhood_mcp = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(robinhood_mcp)


def test_a_stream_and_a_json_body_both_unwrap():
    payload = {"jsonrpc": "2.0", "id": 2, "result": {"content": [{"type": "text", "text": "{\"data\": {\"ok\": true}}"}]}}
    streamed = "event: message\ndata: " + json.dumps(payload) + "\n"
    assert robinhood_mcp.parse_mcp_body(streamed.encode(), "text/event-stream")["id"] == 2
    assert robinhood_mcp.unwrap_tool(payload) == {"data": {"ok": True}}
    assert robinhood_mcp.parse_mcp_body(json.dumps(payload).encode(), "application/json")["id"] == 2


def test_the_cursor_token_blob_decrypts_without_printing_it():
    plain = b'{"access_token":"sample","expires_in":1}'
    pad = 16 - (len(plain) % 16)
    padded = plain + bytes([pad]) * pad
    key = hashlib.pbkdf2_hmac("sha1", b"peanuts", b"saltysalt", 1, 16)
    proc = subprocess.run(
        ["openssl", "enc", "-aes-128-cbc", "-K", key.hex(), "-iv", (b" " * 16).hex(), "-nopad"],
        input=padded,
        capture_output=True,
        check=True,
    )
    raw = b"v10" + proc.stdout
    value = json.dumps({"type": "Buffer", "data": list(raw)})
    assert robinhood_mcp._decrypt_cursor(value)["access_token"] == "sample"


def test_a_contract_label_splits_into_the_strike():
    parsed = robinhood_mcp.contract_parts("10/23 327.5C", 2026)
    assert parsed is not None
    expiration, strike, side = parsed
    assert expiration.isoformat() == "2026-10-23"
    assert strike == 327.5
    assert side == "call"
    assert robinhood_mcp.contract_parts("none", 2026) is None
