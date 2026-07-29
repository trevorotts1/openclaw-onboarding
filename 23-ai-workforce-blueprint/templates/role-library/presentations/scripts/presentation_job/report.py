from __future__ import annotations

import datetime
import json
import os
import subprocess
from typing import Any, Dict, Optional

from .state import StateStore, utcnow

PROGRESS_MIN_INTERVAL_MINUTES = 10
BLOCKED_DEDUPE_MINUTES = 10
EVENTS_MAX = 2000

_PROGRESS_MILESTONES = {
    "P4-RENDER",
    "P8-ASSEMBLE",
}


def _parse_minutes(ts: str) -> float:
    try:
        dt = datetime.datetime.fromisoformat(ts)
        return dt.timestamp() / 60.0
    except (ValueError, TypeError):
        return 0.0


def dispatch(chat_id: str, kind: str, message: str) -> bool:
    """Transport boundary. Returns True only on CONFIRMED delivery.

    Standalone for callers without a StateStore (e.g. the watchdog).
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
    def __init__(self, state: Dict[str, Any], store: StateStore) -> None:
        self.state = state
        self.store = store
        self._last_progress_at: Dict[str, float] = {}
        self._blocked_dedupe: Dict[str, float] = {}
        self._first_phase_sent = False

    def event(self, kind: str, message: str, **extra: Any) -> None:
        ev = {"at": utcnow(), "kind": kind, "message": message}
        ev.update(extra)
        events = self.state.setdefault("events", [])
        events.append(ev)
        if len(events) > EVENTS_MAX:
            keep_first = 200
            keep_last = EVENTS_MAX - keep_first
            dropped = len(events) - EVENTS_MAX
            marker = {"at": utcnow(), "kind": "events.pruned",
                      "message": f"{dropped} events dropped (cap {EVENTS_MAX})"}
            self.state["events"] = events[:keep_first] + [marker] + events[-(keep_last):]
        self.store.save(self.state)
        print(f"[{ev['at']}] {kind}: {message}", flush=True)

    def to_requester(self, kind: str, message: str, *,
                     phase_id: Optional[str] = None,
                     reason: Optional[str] = None) -> None:
        """kind in {ack, progress, blocked, done}. BLOCKED and DONE ignore quiet hours."""
        req = self.state.get("requester") or {}
        chat_id = req.get("chat_id")
        self.event(f"report.{kind}", message, requester=bool(chat_id))
        if not chat_id:
            self.event("report.undeliverable",
                       f"no requester chat_id on this job -- {kind} message not sent")
            return

        should_send = self._throttle_decision(kind, message, phase_id, reason)
        if should_send:
            ok = self._dispatch(chat_id, kind, message)
            if ok:
                self._stamp_sent(kind)
            else:
                self.state.setdefault("undeliverable", []).append(
                    {"at": utcnow(), "kind": kind, "message": message,
                     "chat_id_present": True, "attempts": 1})
        else:
            throttled = self.state.setdefault("throttled", 0)
            self.state["throttled"] = throttled + 1
        self.store.save(self.state)

    def _stamp_sent(self, kind: str) -> None:
        sent = self.state.setdefault("sent", {})
        prior = sent.get(kind)
        if not isinstance(prior, dict):
            sent[kind] = {"count": 0, "first_at": prior, "last_at": prior}
        rec = sent[kind]
        rec["count"] = rec.get("count", 0) + 1
        rec["first_at"] = rec["first_at"] or utcnow()
        rec["last_at"] = utcnow()

    def _throttle_decision(self, kind: str, message: str,
                           phase_id: Optional[str],
                           reason: Optional[str]) -> bool:
        if kind in ("ack", "done"):
            return True
        if kind == "blocked":
            if phase_id and reason:
                key = f"{phase_id}\x00{reason}"
                now_min = _parse_minutes(utcnow())
                last = self._blocked_dedupe.get(key)
                if last is not None and (now_min - last) < BLOCKED_DEDUPE_MINUTES:
                    return False
                self._blocked_dedupe[key] = now_min
                return True
            return True
        if kind == "progress":
            if self.state.get("throttle_probe"):
                return False
            now_min = _parse_minutes(utcnow())
            if self._is_milestone(message):
                self._last_progress_at["__milestone__"] = now_min
                return True
            if not self._first_phase_sent:
                self._first_phase_sent = True
                self._last_progress_at["__any__"] = now_min
                return True
            last = self._last_progress_at.get("__any__", 0)
            if (now_min - last) >= PROGRESS_MIN_INTERVAL_MINUTES:
                self._last_progress_at["__any__"] = now_min
                return True
            return False
        return True

    def _is_milestone(self, message: str) -> bool:
        for m in _PROGRESS_MILESTONES:
            if m in message:
                return True
        return False

    def _dispatch(self, chat_id: str, kind: str, message: str) -> bool:
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
