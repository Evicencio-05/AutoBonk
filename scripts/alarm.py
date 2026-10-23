#!/usr/bin/env python3
"""Loud failures. An alarm is a desktop toast that stays up, a Discord post, and a failed heartbeat.

  python3 scripts/alarm.py test                  # one toast and one post, to check the wiring
  python3 scripts/alarm.py systemd autobonk-claims.service   # systemd OnFailure= calls this
  python3 scripts/alarm.py list                  # alarms still raised

An alarm repeats every REPEAT_SECONDS while it stays raised, and stops when the
checker clears it. Nothing here places or cancels an order.

AUTOBONK_HEARTBEAT_URL in .env, when set, is pinged after every finished check
and pinged at /fail on an alarm. Point it at a dead-man's switch such as
healthchecks.io so a laptop that is asleep, offline, or crashed still reaches you.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALARMS_PATH = ROOT / "alerts" / "alarms.json"
REPEAT_SECONDS = 30 * 60


def _env(name: str) -> str:
    """One value from the environment or .env. The value is never printed."""
    if os.environ.get(name):
        return os.environ[name]
    env_path = ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text().splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def toast(headline: str, body: str, urgency: str = "critical") -> None:
    for command in (
        ["omarchy", "notification", "send", "--app-name", "AutoBonk", "-u", urgency, headline, body],
        ["notify-send", "--app-name=AutoBonk", "-u", urgency, headline, body],
    ):
        try:
            done = subprocess.run(command, check=False, timeout=10, capture_output=True)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if done.returncode == 0:
            return


def _discord(text: str) -> None:
    try:
        import claim_alerts

        claim_alerts.notify_discord(text)
    except BaseException:  # noqa: BLE001 - an alarm must not crash the caller
        return


def heartbeat(fail: bool = False, body: str = "") -> None:
    url = _env("AUTOBONK_HEARTBEAT_URL")
    if not url:
        return
    target = url.rstrip("/") + ("/fail" if fail else "")
    request = urllib.request.Request(target, data=body.encode()[:10000] or None, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()
    except Exception:  # noqa: BLE001
        return


def raise_alarm(
    key: str,
    text: str,
    now: float | None = None,
    path: Path = ALARMS_PATH,
    send=None,
) -> bool:
    """Raise or repeat one alarm. True when it was sent on this call."""
    moment = time.time() if now is None else now
    book = _load(path)
    prior = book.get(key) or {}
    due = not prior or moment - float(prior.get("sent_at") or 0) >= REPEAT_SECONDS
    book[key] = {
        "text": text,
        "first_at": prior.get("first_at") or moment,
        "sent_at": moment if due else prior.get("sent_at"),
        "count": int(prior.get("count") or 0) + (1 if due else 0),
    }
    _save(path, book)
    if not due:
        return False
    if send is not None:
        send(key, text)
        return True
    toast("AutoBonk ALARM", text)
    _discord(f"**AutoBonk alarm** {text}")
    heartbeat(fail=True, body=text)
    return True


def clear_alarm(key: str, path: Path = ALARMS_PATH) -> bool:
    book = _load(path)
    if key not in book:
        return False
    book.pop(key)
    _save(path, book)
    return True


def raised(path: Path = ALARMS_PATH) -> dict:
    return _load(path)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    if not args or args[0] == "list":
        for key, item in sorted(raised().items()):
            print(f"{key}: {item['text']} (sent {item['count']}x)")
        return 0
    if args[0] == "test":
        toast("AutoBonk alarm test", "If you can read this, alarms reach the desktop.", "normal")
        _discord("AutoBonk alarm test. Alarms reach #ta. Not an order.")
        print("Sent one toast and one #ta post.")
        return 0
    if args[0] == "systemd":
        unit = args[1] if len(args) > 1 else "autobonk"
        raise_alarm(
            f"systemd|{unit}",
            f"{unit} failed. Open positions are not being watched. "
            f"Run: journalctl --user -u {unit} -n 50",
        )
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
