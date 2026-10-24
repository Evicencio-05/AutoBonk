#!/usr/bin/env python3
"""Read-only Discord access for forwarded TA posts.

Forwards store the chart text and images on message_snapshots, not on the
outer message. This reader keeps both. It never sends, edits, or deletes.

Token: TA_BOT_TOKEN in the repo-root .env (never printed).

  uv run python3 scripts/discord_ta.py channels
  uv run python3 scripts/discord_ta.py read --channel ta
  uv run python3 scripts/discord_ta.py --mcp
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://discord.com/api/v10"
SERVER_NAME = "discord-ta"
PROTOCOL = "2024-11-05"


def load_token() -> str:
    env_path = ROOT / ".env"
    token = ""
    if env_path.is_file():
        for line in env_path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            if key.strip() == "TA_BOT_TOKEN":
                token = value.strip().strip('"').strip("'")
    token = os.environ.get("TA_BOT_TOKEN", token).strip()
    if not token:
        raise SystemExit("TA_BOT_TOKEN is missing from .env")
    return token


def _attachment(raw: dict) -> dict:
    return {
        "filename": raw.get("filename"),
        "url": raw.get("url"),
        "content_type": raw.get("content_type"),
        "size": raw.get("size"),
    }


def normalize_message(raw: dict) -> dict:
    """Flatten a Discord message, preferring forwarded snapshot text and files."""
    snapshots = raw.get("message_snapshots") or []
    content_parts = []
    attachments = []
    forwarded = bool(snapshots)
    outer = (raw.get("content") or "").strip()
    if outer:
        content_parts.append(outer)
    if not forwarded:
        attachments.extend(_attachment(item) for item in raw.get("attachments") or [])
    for snap in snapshots:
        message = snap.get("message") or {}
        text = (message.get("content") or "").strip()
        if text:
            content_parts.append(text)
        attachments.extend(_attachment(item) for item in message.get("attachments") or [])
    author = raw.get("author") or {}
    return {
        "id": raw.get("id"),
        "channel_id": raw.get("channel_id"),
        "author": author.get("username"),
        "author_id": author.get("id"),
        "bot": bool(author.get("bot")),
        "timestamp": raw.get("timestamp"),
        "forwarded": forwarded,
        "content": "\n".join(content_parts),
        "attachments": attachments,
    }


class DiscordRead:
    def __init__(self, token: str):
        self._token = token

    def _get(self, path: str):
        request = urllib.request.Request(
            API + path,
            headers={
                "Authorization": f"Bot {self._token}",
                "User-Agent": "claude-trading-skills discord-ta",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:300]
            raise SystemExit(f"Discord API {exc.code}: {detail}") from exc

    def guilds(self) -> list:
        return self._get("/users/@me/guilds")

    def channels(self, guild_id: str) -> list:
        rows = self._get(f"/guilds/{guild_id}/channels")
        text = [row for row in rows if row.get("type") in (0, 5, 15, 16)]
        return [
            {"id": row["id"], "name": row.get("name"), "type": row.get("type")}
            for row in sorted(text, key=lambda row: row.get("position", 0))
        ]

    def find_channel(self, name_or_id: str, guild_id: str | None = None) -> dict:
        matches = []
        for guild in self.guilds():
            if guild_id and guild["id"] != guild_id and guild.get("name") != guild_id:
                continue
            for channel in self.channels(guild["id"]):
                if channel["id"] == name_or_id or channel["name"].lower() == name_or_id.lower():
                    matches.append({**channel, "guild_id": guild["id"], "guild": guild.get("name")})
        if not matches:
            raise SystemExit(f"No text channel matching {name_or_id}")
        if len(matches) > 1:
            names = ", ".join(f"{item['guild']}#{item['name']}" for item in matches)
            raise SystemExit(f"Channel name is ambiguous: {names}")
        return matches[0]

    def read_messages(self, name_or_id: str, limit: int = 20, guild_id: str | None = None) -> dict:
        channel = self.find_channel(name_or_id, guild_id)
        safe_limit = max(1, min(int(limit), 50))
        query = urllib.parse.urlencode({"limit": safe_limit})
        rows = self._get(f"/channels/{channel['id']}/messages?{query}")
        messages = [normalize_message(row) for row in reversed(rows)]
        return {
            "guild": channel["guild"],
            "channel": channel["name"],
            "channel_id": channel["id"],
            "count": len(messages),
            "messages": messages,
        }

    def ingest(self, name_or_id: str = "ta", limit: int = 20) -> dict:
        """Save forwarded text and images under charts/inbox. Drops expiring CDN URLs."""
        data = self.read_messages(name_or_id, limit=limit)
        inbox = ROOT / "charts" / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        saved = []
        for msg in data["messages"]:
            local = []
            for index, att in enumerate(msg.get("attachments") or []):
                url = att.get("url")
                if not url:
                    continue
                kind = att.get("content_type") or ""
                if "webp" in kind:
                    ext = "webp"
                elif "png" in kind:
                    ext = "png"
                else:
                    ext = "bin"
                rel = Path("charts") / "inbox" / f"{msg['id']}_{index}.{ext}"
                request = urllib.request.Request(
                    url,
                    headers={"User-Agent": "AutoBonk discord-ta"},
                )
                with urllib.request.urlopen(request, timeout=30) as response:
                    (ROOT / rel).write_bytes(response.read())
                local.append(
                    {
                        "filename": att.get("filename"),
                        "content_type": att.get("content_type"),
                        "size": att.get("size"),
                        "file": str(rel),
                    }
                )
            record = {
                "id": msg.get("id"),
                "author": msg.get("author"),
                "author_id": msg.get("author_id"),
                "bot": msg.get("bot"),
                "timestamp": msg.get("timestamp"),
                "forwarded": msg.get("forwarded"),
                "content": msg.get("content"),
                "channel": data.get("channel"),
                "guild": data.get("guild"),
                "attachments": local,
            }
            out = inbox / f"{msg['id']}.json"
            out.write_text(json.dumps(record, indent=2) + "\n")
            saved.append(
                {
                    "id": record["id"],
                    "file": str(out.relative_to(ROOT)),
                    "images": [item["file"] for item in local],
                    "chars": len(record.get("content") or ""),
                }
            )
        return {"channel": data.get("channel"), "saved": saved}


def _tool_result(payload: dict, is_error: bool = False) -> dict:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
        "isError": is_error,
    }


def handle_rpc(message: dict, client: DiscordRead) -> dict | None:
    method = message.get("method")
    msg_id = message.get("id")
    if method == "notifications/initialized" or msg_id is None and method != "initialize":
        if method and method.startswith("notifications/"):
            return None
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": PROTOCOL,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": "0.1.0"},
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": [
                    {
                        "name": "list_channels",
                        "description": "List text channels the TA bot can read.",
                        "inputSchema": {"type": "object", "properties": {}},
                    },
                    {
                        "name": "ingest_ta",
                        "description": (
                            "Download #ta forwards into charts/inbox so image URLs cannot expire."
                        ),
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "channel": {"type": "string"},
                                "limit": {"type": "integer"},
                            },
                        },
                    },
                    {
                        "name": "read_messages",
                        "description": (
                            "Read a channel, including forwarded posts. "
                            "Forwarded chart text and images are included."
                        ),
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "channel": {
                                    "type": "string",
                                    "description": "Channel name or ID. Use ta for forwarded charts.",
                                },
                                "limit": {
                                    "type": "integer",
                                    "description": "How many messages (1-50, default 20).",
                                },
                            },
                            "required": ["channel"],
                        },
                    },
                ]
            },
        }
    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            if name == "list_channels":
                listed = []
                for guild in client.guilds():
                    for channel in client.channels(guild["id"]):
                        listed.append(
                            {
                                "guild": guild.get("name"),
                                "guild_id": guild["id"],
                                "name": channel["name"],
                                "id": channel["id"],
                            }
                        )
                payload = {"channels": listed}
            elif name == "ingest_ta":
                payload = client.ingest(
                    args.get("channel") or "ta",
                    limit=args.get("limit") or 20,
                )
            elif name == "read_messages":
                payload = client.read_messages(
                    args.get("channel") or "ta",
                    limit=args.get("limit") or 20,
                )
            else:
                payload = {"error": f"Unknown tool {name}"}
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": _tool_result(payload, is_error=True),
                }
            return {"jsonrpc": "2.0", "id": msg_id, "result": _tool_result(payload)}
        except SystemExit as exc:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": _tool_result({"error": str(exc)}, is_error=True),
            }
    if msg_id is not None:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }
    return None


def _read_frame(stream) -> dict | None:
    headers = {}
    while True:
        line = stream.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        decoded = line.decode("utf-8")
        if ":" not in decoded:
            continue
        key, value = decoded.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    return json.loads(stream.read(length).decode("utf-8"))


def _write_frame(payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    sys.stdout.buffer.write(header)
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def serve_mcp() -> None:
    client = DiscordRead(load_token())
    while True:
        message = _read_frame(sys.stdin.buffer)
        if message is None:
            return
        response = handle_rpc(message, client)
        if response is not None:
            _write_frame(response)


def main() -> None:
    parser = argparse.ArgumentParser(description="Read forwarded TA from Discord")
    parser.add_argument("--mcp", action="store_true", help="Speak MCP on stdio")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("channels")
    read = sub.add_parser("read")
    read.add_argument("--channel", default="ta")
    read.add_argument("--limit", type=int, default=20)
    ingest_cmd = sub.add_parser("ingest")
    ingest_cmd.add_argument("--channel", default="ta")
    ingest_cmd.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    if args.mcp:
        serve_mcp()
        return
    client = DiscordRead(load_token())
    if args.command == "channels":
        listed = []
        for guild in client.guilds():
            for channel in client.channels(guild["id"]):
                listed.append({"guild": guild.get("name"), **channel})
        json.dump(listed, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return
    if args.command == "read":
        json.dump(
            client.read_messages(args.channel, limit=args.limit),
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
        return
    if args.command == "ingest":
        json.dump(
            client.ingest(args.channel, limit=args.limit),
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
        return
    parser.print_help()
    raise SystemExit(2)


if __name__ == "__main__":
    main()
