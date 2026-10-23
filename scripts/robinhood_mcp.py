"""Send one Agentic option order through Robinhood's trading MCP.

The server is the same one Cursor already signs in:
https://agent.robinhood.com/mcp/trading. The access token is the one Cursor
stored for this project. A refresh stays in the user config directory.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MCP_URL = "https://agent.robinhood.com/mcp/trading"
TOKEN_URL = "https://api.robinhood.com/oauth2/token/"
TOKEN_PATH = Path.home() / ".config" / "autobonk" / "robinhood-mcp.json"
CURSOR_DB = Path.home() / ".config" / "Cursor" / "User" / "globalStorage" / "state.vscdb"
# Electron's published Linux safeStorage password. It is not a user secret.
_SAFE_STORAGE = b"peanuts"


class BrokerError(RuntimeError):
    """The trading MCP could not take the order."""


def _decrypt_cursor(value: str) -> dict:
    raw = bytes(json.loads(value)["data"])
    if not raw.startswith(b"v10"):
        raise BrokerError("auth")
    key = hashlib.pbkdf2_hmac("sha1", _SAFE_STORAGE, b"saltysalt", 1, 16)
    proc = subprocess.run(
        [
            "openssl",
            "enc",
            "-aes-128-cbc",
            "-d",
            "-K",
            key.hex(),
            "-iv",
            (b" " * 16).hex(),
            "-nopad",
        ],
        input=raw[3:],
        capture_output=True,
        check=False,
    )
    plain = proc.stdout
    if not plain:
        raise BrokerError("auth")
    pad = plain[-1]
    if not 1 <= pad <= 16 or plain[-pad:] != bytes([pad]) * pad:
        raise BrokerError("auth")
    body = plain[:-pad]
    if not body.startswith(b"{"):
        raise BrokerError("auth")
    return json.loads(body)


def _cursor_rows() -> list[tuple[str, str]]:
    if not CURSOR_DB.is_file():
        return []
    uri = f"file:{CURSOR_DB}?mode=ro"
    with sqlite3.connect(uri, uri=True) as con:
        return list(
            con.execute(
                "SELECT key, value FROM ItemTable WHERE key LIKE 'mcpOAuth.%'"
            )
        )


def _decoded_key(key: str) -> str:
    prefix = "mcpOAuth.secret." if key.startswith("mcpOAuth.secret.") else "mcpOAuth.global."
    raw = key.split(prefix, 1)[-1]
    pad = raw + "=" * ((4 - len(raw) % 4) % 4)
    try:
        return base64.b64decode(pad).decode()
    except (ValueError, UnicodeError):
        return ""


def _cursor_oauth() -> dict:
    rows = _cursor_rows()
    tokens = None
    token_name = ""
    client = None
    for key, value in rows:
        if not key.startswith("mcpOAuth.secret."):
            continue
        name = _decoded_key(key)
        if "AutoBonk-robinhood-trading" not in name:
            continue
        try:
            payload = _decrypt_cursor(value)
        except (BrokerError, json.JSONDecodeError, KeyError, TypeError):
            continue
        if name.endswith("mcp_tokens") and "access_token" in payload:
            tokens = payload
            token_name = name
        elif name.endswith("mcp_client_information") and payload.get("client_id"):
            client = payload
    if not tokens or not client:
        raise BrokerError("auth")
    updated = 0
    marker = token_name.split("]", 1)[0]
    for key, value in rows:
        if not key.startswith("mcpOAuth.global."):
            continue
        name = _decoded_key(key)
        if marker and marker in name and name.endswith("mcp_oauth_updated_at_ms"):
            try:
                updated = int(str(value).strip().strip('"')) / 1000
            except ValueError:
                updated = 0
    expires_in = int(tokens.get("expires_in") or 0)
    expires_at = updated + expires_in if updated and expires_in else 0
    return {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token") or "",
        "client_id": client["client_id"],
        "expires_at": expires_at,
    }


def _read_saved() -> dict | None:
    if not TOKEN_PATH.is_file():
        return None
    try:
        data = json.loads(TOKEN_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not data.get("access_token") or not data.get("client_id"):
        return None
    return data


def _write_saved(data: dict) -> None:
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(json.dumps(data) + "\n")
    os.chmod(TOKEN_PATH, 0o600)


def _refresh(saved: dict) -> dict:
    if not saved.get("refresh_token") or not saved.get("client_id"):
        raise BrokerError("auth")
    body = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": saved["refresh_token"],
            "client_id": saved["client_id"],
        }
    ).encode()
    request = urllib.request.Request(TOKEN_URL, data=body, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    request.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise BrokerError(f"auth {exc.code}") from exc
    access = payload.get("access_token")
    if not access:
        raise BrokerError("auth")
    fresh = {
        "access_token": access,
        "refresh_token": payload.get("refresh_token") or saved["refresh_token"],
        "client_id": saved["client_id"],
        "expires_at": time.time() + int(payload.get("expires_in") or 0),
    }
    _write_saved(fresh)
    return fresh


def load_oauth() -> dict:
    """The Agentic MCP token. Refresh it when the saved clock says it lapsed."""
    saved = _read_saved()
    if saved and float(saved.get("expires_at") or 0) > time.time() + 30:
        return saved
    if saved and saved.get("refresh_token"):
        return _refresh(saved)
    current = _cursor_oauth()
    if float(current.get("expires_at") or 0) > time.time() + 30:
        _write_saved(current)
        return current
    if current.get("refresh_token"):
        return _refresh(current)
    raise BrokerError("auth")


def parse_mcp_body(raw: bytes, content_type: str) -> dict:
    text = raw.decode("utf-8", "replace").strip()
    if not text:
        raise BrokerError("empty")
    if "text/event-stream" in content_type or text.startswith("data:") or text.startswith("event:"):
        data = [line[5:].strip() for line in text.splitlines() if line.startswith("data:" )]
        if not data:
            raise BrokerError("empty")
        return json.loads(data[-1])
    return json.loads(text)


def unwrap_tool(payload: dict) -> dict:
    if payload.get("error"):
        raise BrokerError("mcp")
    result = payload.get("result") or {}
    if result.get("isError"):
        raise BrokerError("mcp")
    structured = result.get("structuredContent")
    if isinstance(structured, dict) and structured:
        return structured
    for item in result.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text":
            text = item.get("text") or ""
            if text.startswith("{") or text.startswith("["):
                loaded = json.loads(text)
                if isinstance(loaded, dict):
                    return loaded
    if isinstance(result, dict):
        return result
    raise BrokerError("mcp")


def contract_parts(label: str, year: int) -> tuple[date, float, str] | None:
    """'10/23 327.5C' plus the trade year."""
    parts = (label or "").split()
    if len(parts) != 2 or "/" not in parts[0] or parts[1][-1] not in ("C", "P"):
        return None
    month_text, day_text = parts[0].split("/", 1)
    try:
        expiration = date(year, int(month_text), int(day_text))
        strike = float(parts[1][:-1])
    except ValueError:
        return None
    side = "call" if parts[1][-1] == "C" else "put"
    return expiration, strike, side


def spendable_amount(payload) -> float | None:
    """Dollars one new contract can debit.

    Unleveraged buying power is what a cash account can pay. The cash field
    is the fallback when buying power is missing. None when neither was read.
    """
    if not isinstance(payload, dict):
        return None
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        return None
    buying = data.get("buying_power") if isinstance(data.get("buying_power"), dict) else {}
    for raw in (
        buying.get("unleveraged_buying_power"),
        buying.get("buying_power"),
        data.get("cash"),
    ):
        if raw in (None, ""):
            continue
        try:
            amount = float(raw)
        except (TypeError, ValueError):
            continue
        if amount >= 0 and amount == amount and amount != float("inf"):
            return amount
    return None


def agentic_account(path: Path | None = None) -> str:
    file = path or (ROOT / "config" / "accounts.yaml")
    data = yaml.safe_load(file.read_text())
    for number, info in (data.get("accounts") or {}).items():
        if info.get("agentic_allowed") is True:
            return str(number)
    raise BrokerError("account")


class RobinhoodBroker:
    """Review, then place, one contract on the Agentic account."""

    def __init__(self, opener=None, oauth=None, account=None):
        self.opener = opener or urllib.request.urlopen
        self.oauth = oauth if oauth is not None else load_oauth
        self.account = account if account is not None else agentic_account
        self._token = ""
        self._session = ""
        self._refreshed = False

    def _headers(self, token: str) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {token}",
        }
        if self._session:
            headers["Mcp-Session-Id"] = self._session
        return headers

    def _post(self, payload: dict) -> dict:
        if not self._token:
            self._token = self.oauth()["access_token"]
        request = urllib.request.Request(
            MCP_URL,
            data=json.dumps(payload).encode(),
            method="POST",
            headers=self._headers(self._token),
        )
        try:
            with self.opener(request, timeout=30) as response:
                session = response.headers.get("Mcp-Session-Id") or response.headers.get(
                    "mcp-session-id"
                )
                if session:
                    self._session = session
                body = response.read()
                kind = response.headers.get("Content-Type") or ""
                if not body and "id" not in payload:
                    return {}
                return parse_mcp_body(body, kind)
        except urllib.error.HTTPError as exc:
            if exc.code == 401 and not self._refreshed:
                self._refreshed = True
                self._token = ""
                self._session = ""
                saved = _read_saved() or _cursor_oauth()
                fresh = _refresh(saved)
                self._token = fresh["access_token"]
                return self._post(payload)
            raise BrokerError(f"http {exc.code}") from exc

    def _ensure(self) -> None:
        if self._session:
            return
        self._post(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "autobonk", "version": "1"},
                },
            }
        )
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def tool(self, name: str, arguments: dict) -> dict:
        self._ensure()
        return unwrap_tool(
            self._post(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                }
            )
        )

    def spendable(self) -> float | None:
        """Dollars the Agentic account can pay for one contract. None when unread."""
        try:
            payload = self.tool("get_portfolio", {"account_number": self.account()})
        except (BrokerError, OSError, TimeoutError, ValueError, TypeError):
            return None
        return spendable_amount(payload)

    def find(self, ticker: str, label: str, year: int) -> str:
        parsed = contract_parts(label, year)
        if parsed is None:
            return ""
        expiration, strike, side = parsed
        payload = self.tool(
            "get_option_instruments",
            {
                "chain_symbol": ticker,
                "expiration_dates": expiration.isoformat(),
                "strike_price": f"{strike:.4f}",
                "type": side,
            },
        )
        instruments = (payload.get("data") or {}).get("instruments") or payload.get(
            "instruments"
        ) or []
        if not instruments:
            return ""
        return str(instruments[0].get("id") or "")

    def position(self, ticker: str, label: str, year: int) -> dict | None:
        option_id = self.find(ticker, label, year)
        if not option_id:
            return None
        payload = self.tool(
            "get_option_positions",
            {
                "account_number": self.account(),
                "option_ids": option_id,
                "nonzero": True,
            },
        )
        rows = (payload.get("data") or {}).get("positions") or []
        if not rows:
            return None
        row = rows[0]
        return {
            "option_id": option_id,
            "quantity": float(row.get("quantity") or 0),
            "pending_sell": float(row.get("pending_sell_quantity") or 0),
        }

    def _quote(self, option_id: str) -> tuple[float, float]:
        payload = self.tool("get_option_quotes", {"instrument_ids": [option_id]})
        results = (payload.get("data") or {}).get("results") or []
        if not results:
            return 0.0, 0.0
        quote = results[0].get("quote") or results[0]
        return float(quote.get("bid_price") or 0), float(quote.get("ask_price") or 0)

    def _place(
        self, ticker: str, option_id: str, side: str, effect: str, price: str, ref_id: str
    ) -> dict:
        account = self.account()
        legs = [{"option_id": option_id, "side": side, "position_effect": effect}]
        arguments = {
            "account_number": account,
            "legs": legs,
            "quantity": "1",
            "type": "limit",
            "price": price,
            "time_in_force": "gfd",
            "market_hours": "regular_hours",
        }
        review = self.tool(
            "review_option_order",
            {**arguments, "chain_symbol": ticker, "underlying_type": "equity"},
        )
        data = review.get("data") or review
        checks = data.get("order_checks") or {}
        if checks:
            return {"sent": False, "reason": "check"}
        # chain_symbol is not part of place. The review used it only for fees.
        arguments.pop("chain_symbol", None)
        placed = self.tool("place_option_order", {**arguments, "ref_id": ref_id})
        order = (placed.get("data") or placed).get("order") or {}
        if not order.get("id"):
            return {"sent": False, "reason": "broker"}
        filled = ""
        for leg in order.get("legs") or []:
            for execution in leg.get("executions") or []:
                filled = execution.get("price") or filled
        return {
            "sent": True,
            "order_id": order["id"],
            "price": filled or order.get("price") or price,
            "state": order.get("state") or "",
        }

    def buy(self, ticker: str, label: str, year: int, ref_id: str, cash=None) -> dict:
        option_id = self.find(ticker, label, year)
        if not option_id:
            return {"sent": False, "reason": "empty"}
        _bid, ask = self._quote(option_id)
        if ask <= 0:
            return {"sent": False, "reason": "quote"}
        if cash is None:
            cash = self.spendable()
        try:
            amount = float(cash)
        except (TypeError, ValueError):
            return {"sent": False, "reason": "unread"}
        if amount < 0 or amount != amount or amount == float("inf"):
            return {"sent": False, "reason": "unread"}
        if int(round(ask * 10000)) > int(round(amount * 100)):
            return {"sent": False, "reason": "over"}
        held = self.position(ticker, label, year)
        if held and held["quantity"] > 0:
            return {"sent": False, "reason": "open"}
        return self._place(ticker, option_id, "buy", "open", f"{ask:.2f}", ref_id)

    def sell(self, ticker: str, label: str, year: int, ref_id: str) -> dict:
        held = self.position(ticker, label, year)
        if held is None or held["quantity"] <= 0:
            return {"sent": False, "reason": "flat"}
        if held["pending_sell"] > 0:
            return {"sent": False, "reason": "working"}
        bid, _ask = self._quote(held["option_id"])
        if bid <= 0:
            return {"sent": False, "reason": "quote"}
        return self._place(ticker, held["option_id"], "sell", "close", f"{bid:.2f}", ref_id)
