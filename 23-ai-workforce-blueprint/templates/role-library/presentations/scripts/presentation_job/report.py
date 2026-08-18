from __future__ import annotations

import datetime
import json
import os
import shlex
import subprocess
from typing import Any, Dict, Optional

from .result import CheckResult
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


def dispatch3(chat_id: str, kind: str, message: str) -> CheckResult:
    """Transport boundary, three-valued. This is the ONLY implementation of the
    PRESENTATION_NOTIFY_CMD dispatch path anywhere in this package -- dispatch()
    below and Reporter._dispatch3 both delegate here instead of re-running their
    own subprocess.run. A second, independently-maintained copy of this logic is
    exactly how U069 shipped with a live shell-injection hole: the class method
    got the tokenise-first fix and a module-level twin did not, so watchdog.py
    (which imports the dispatch path directly) stayed exploitable.

    CheckResult.PASS         -- the notify command ran and exited 0. CONFIRMED delivery.
    CheckResult.FAIL         -- PRESENTATION_NOTIFY_CMD is unset. A known, stable fact
                                 about this environment, not an unknown -- there is no
                                 transport to retry against until the env var is set.
    CheckResult.UNDETERMINED -- the command ran and exited non-zero, OR timed out, OR
                                 could not be started (OSError). We do NOT know whether
                                 the message actually reached anyone: a non-zero exit
                                 could mean a transient network blip just as easily as a
                                 permanent rejection. Per the transport rule (see
                                 result.py): unknown means keep trying, never discard.
    """
    cmd = os.environ.get("PRESENTATION_NOTIFY_CMD")
    if not cmd:
        return CheckResult.FAIL
    # U069: tokenise, refuse on unparseable, shell=False.
    try:
        argv = shlex.split(cmd)
    except ValueError as exc:
        raise ValueError(
            f"PRESENTATION_NOTIFY_CMD is not a valid argument vector ({exc}). "
            "Fix the environment variable; this is not sanitised for you."
        ) from exc
    try:
        r = subprocess.run(argv, shell=False, input=json.dumps(
            {"chat_id": chat_id, "kind": kind, "message": message}),
            text=True, capture_output=True, timeout=30)
        return CheckResult.PASS if r.returncode == 0 else CheckResult.UNDETERMINED
    except (subprocess.TimeoutExpired, OSError):
        return CheckResult.UNDETERMINED


def dispatch(chat_id: str, kind: str, message: str) -> bool:
    """Back-compat bool wrapper over dispatch3(), for callers that only ever had
    a binary decision to make (watchdog.py's fire-and-forget stall notice,
    __main__.cmd_sweep_undeliverable's per-message retry loop). True ONLY on
    CheckResult.PASS -- both FAIL and UNDETERMINED collapse to False here,
    which is the correct, unchanged behaviour for those two callers: they
    already queue/re-attempt on any False, so nothing about their retry
    semantics changes. Standalone (module-level, not a Reporter method) for
    callers without a StateStore. Do not re-derive the subprocess.run call
    anywhere else -- see dispatch3()'s docstring for why that's exactly the
    U069 bypass shape.
    """
    return dispatch3(chat_id, kind, message) is CheckResult.PASS


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
        if not should_send:
            throttled = self.state.setdefault("throttled", 0)
            self.state["throttled"] = throttled + 1
            self.store.save(self.state)
            return

        result = self._dispatch3(chat_id, kind, message)
        if result is CheckResult.PASS:
            self._stamp_sent(kind)
            if kind == "blocked" and phase_id and reason:
                # B6-1 fix: stamp the dedupe timer ONLY on a CONFIRMED delivery, and
                # only here -- never in _throttle_decision, and never before this
                # point. The old code stamped the timer the moment a blocked event
                # was ALLOWED to attempt dispatch, before the outcome was known. If
                # that first attempt then failed to reach the transport (FAIL or
                # UNDETERMINED), the timer was already set, so the very next
                # identical (phase_id, reason) blocked event -- typically seconds
                # later, from heal.py's own retry loop -- was silently throttled:
                # never dispatched, never queued to `undeliverable`, an alert about
                # a real failure just... suppressed for BLOCKED_DEDUPE_MINUTES. A
                # transport's unknown must keep trying, never be treated as if it
                # had already gotten through (see result.py).
                self._blocked_dedupe[self._blocked_key(phase_id, reason)] = _parse_minutes(utcnow())
        else:
            # FAIL (no transport configured) or UNDETERMINED (timeout / non-zero
            # exit / could not start): never discard. Queue for the sweeper
            # (--sweep-undeliverable / cmd_sweep_undeliverable) and do NOT stamp
            # the dedupe timer -- see above.
            self.state.setdefault("undeliverable", []).append(
                {"at": utcnow(), "kind": kind, "message": message,
                 "chat_id": chat_id, "attempts": 1, "outcome": result.value})
        self.store.save(self.state)

    @staticmethod
    def _blocked_key(phase_id: str, reason: str) -> str:
        return f"{phase_id}\x00{reason}"

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
                key = self._blocked_key(phase_id, reason)
                now_min = _parse_minutes(utcnow())
                last = self._blocked_dedupe.get(key)
                if last is not None and (now_min - last) < BLOCKED_DEDUPE_MINUTES:
                    return False
                # NOTE: the timer is deliberately NOT stamped here -- only
                # to_requester() stamps it, and only on a CONFIRMED PASS. See the
                # B6-1 comment in to_requester() for why "allowed to attempt" and
                # "actually delivered" must not be conflated.
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

    def _dispatch3(self, chat_id: str, kind: str, message: str) -> CheckResult:
        # U069: delegates to the module-level dispatch3() -- do not re-derive
        # the tokenise-first / shell=False logic here. See dispatch3()'s
        # docstring: a second copy of this is precisely the bypass U069
        # closure exists to prevent.
        return dispatch3(chat_id, kind, message)
