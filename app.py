#!/usr/bin/env python3
"""Hosted desk. Vercel runs this file. The local desk is still scripts/dashboard.py serve.

Nothing here places an order. A backtest does not rewrite the paper tape.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
from pathlib import Path

from flask import Flask, Response, request

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))

import dashboard  # noqa: E402

app = Flask(__name__)


def _json(payload: dict, status: int = 200) -> Response:
    return Response(json.dumps(payload), status=status, mimetype="application/json")


@app.get("/")
def home() -> Response:
    return Response(dashboard.render(dashboard.ROOT), mimetype="text/html")


@app.post("/api/backtest")
def backtest() -> Response:
    try:
        body = request.get_json(silent=True) or {}
        return _json(dashboard.backtest_payload(body))
    except (ValueError, KeyError, TypeError, SystemExit, OSError, urllib.error.URLError) as exc:
        return _json({"error": str(exc)}, 400)


@app.post("/api/book")
def book() -> Response:
    if os.environ.get("VERCEL"):
        return _json(
            {
                "error": "The hosted desk reads the book from GitHub. A save here does not change it."
            },
            400,
        )
    try:
        dashboard.save_book(dashboard.ROOT, request.get_json(silent=True) or {})
        return _json({"saved": True})
    except (ValueError, KeyError, TypeError, OSError) as exc:
        return _json({"error": str(exc)}, 400)
