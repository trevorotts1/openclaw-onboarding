from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Dict

from .state import StateStore, utcnow


def dispatch(chat_id: str, kind: str, message: str) -> bool:
    """Transport boundary. Returns True only on CONFIRMED delivery.

    Extracted from Reporter._dispatch so that callers without a StateStore
    (specifically the watchdog) can send notifications through the same
    contract: JSON on stdin, 30-second timeout, non-zero exit = not delivered.
    """
    cmd = os.environ.get("PRESENTATION_NOTIFY_CMD")
    if not cmd:
        return False
    try:
        r = subprocess.run(cmd, shell=True, input=json.dumps(
            {"chat_id": chat_id, "kind": kind, "message": message}),
            text=True, capture_output=True, timeout=30)
        return r.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


class Reporter:
    """
    Emits to three places, in this order of reliability:
      1. state.json events   -- always, durable, local
      2. stdout              -- always
      3. the board + Telegram -- best effort, retried, NEVER blocking
    """

    def __init__(self, state: Dict[str, Any], store: StateStore) -> None:
        self.state = state
        self.store = store

    def event(self, kind: str, message: str, **extra: Any) -> None:
        ev = {"at": utcnow(), "kind": kind, "message": message}
        ev.update(extra)
        self.state.setdefault("events", []).append(ev)
        self.store.save(self.state)
        print(f"[{ev['at']}] {kind}: {message}", flush=True)

    def to_requester(self, kind: str, message: str) -> None:
        """
        kind in {ack, progress, blocked, done}.
        BLOCKED and DONE ignore quiet hours.
        """
        req = self.state.get("requester") or {}
        chat_id = req.get("chat_id")
        self.event(f"report.{kind}", message, requester=bool(chat_id))
        if not chat_id:
            self.event("report.undeliverable",
                       f"no requester chat_id on this job -- {kind} message not sent")
            return
        ok = dispatch(chat_id, kind, message)
        if ok:
            self.state.setdefault("sent", {})[kind] = utcnow()
        else:
            self.state.setdefault("undeliverable", []).append(
                {"at": utcnow(), "kind": kind, "message": message, "chat_id_present": True})
        self.store.save(self.state)
