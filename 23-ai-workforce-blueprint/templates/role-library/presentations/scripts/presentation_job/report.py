from __future__ import annotations

import datetime
import json
import os
import shlex
import subprocess
from typing import Any, Dict, List, Optional

from .result import CheckResult
from .state import StateStore, utcnow

PROGRESS_MIN_INTERVAL_MINUTES = 10
BLOCKED_DEDUPE_MINUTES = 10
EVENTS_MAX = 2000

# ---------------------------------------------------------------------------
# NOTIFY RETRY SEMANTICS (transport-down vs poisoned).
#
# WHAT EVIDENCE ACTUALLY EXISTS at the dispatch site (dispatch3() below):
# PRESENTATION_NOTIFY_CMD is an arbitrary external command. The only things
# report.py can ever observe about a failed send are: cmd unset (FAIL),
# OSError starting it (couldn't even launch -- unambiguously transport),
# subprocess.TimeoutExpired (unambiguously transport: a hang/unreachable
# network), or a non-zero exit code (CheckResult.UNDETERMINED -- and this one
# is NOT distinguishable from here. A non-zero exit is produced identically
# by "network down" and by "the API rejected this exact message." There is no
# stderr taxonomy report.py can trust: PRESENTATION_NOTIFY_CMD can point at
# ANY script, and hard-coding a parse of one particular script's stderr text
# into the generic dispatch path would be exactly the kind of guessed signal
# this module refuses to invent -- see result.py's doctrine.
#
# So: a non-zero exit, by itself, is NOT evidence of poisoning. Per the
# explicit instruction this module follows -- "if no signal distinguishes the
# two cases, default to retry-with-backoff forever, never discarding" -- every
# UNDETERMINED and every FAIL retries forever on a capped backoff. NOTHING is
# ever discarded on attempt-count alone (that was the first failed attempt at
# this fix: a terminal cap that silently lost an alert an outage-then-recovery
# would otherwise have delivered).
#
# The ONE piece of real, non-guessed evidence this module DOES have for
# "poisoned" is cross-message correlation: state["transport"]["last_ok_at"] is
# stamped every time ANY dispatch, for ANY message, is CONFIRMED delivered
# (CheckResult.PASS) -- whether that was a live send or a queued retry. If a
# specific queued message keeps failing on repeated retries made AFTER the
# transport has been independently proven to work (something else got
# through), that message's own content -- not the transport -- is what's
# rejecting it. POISON_CONFIRM_THRESHOLD such confirmations park it: retries
# stop, but the content is preserved and surfaced (state["parked"]), never
# silently dropped. A message with no such corroborating evidence (transport
# never independently proven up since it started failing) just keeps
# retrying forever on backoff -- a nuisance, never a loss.
POISON_CONFIRM_THRESHOLD = 3

# Capped exponential backoff for automatic retry. Never grows past the cap,
# so no caller -- however often it invokes the retry path, human or cron --
# can turn this into a hot loop. This delay is the ONLY thing that is ever
# bounded here; the number of attempts is not (see flush_undeliverable()).
RETRY_BACKOFF_BASE_SECONDS = 30
RETRY_BACKOFF_CAP_SECONDS = 900  # 15 minutes

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


def _parse_iso(ts: Any) -> Optional[datetime.datetime]:
    if not ts or not isinstance(ts, str):
        return None
    try:
        return datetime.datetime.fromisoformat(ts)
    except ValueError:
        return None


def _add_seconds(ts: str, seconds: float) -> str:
    dt = _parse_iso(ts) or datetime.datetime.now(datetime.timezone.utc)
    return (dt + datetime.timedelta(seconds=seconds)).isoformat(timespec="seconds")


def _backoff_seconds(attempts: int) -> float:
    """Capped exponential backoff. `attempts` is the attempt number just made
    (>=1). 30s, 60s, 120s, ... capped at RETRY_BACKOFF_CAP_SECONDS (15min),
    where it stays forever -- retried, never dropped, never faster than every
    15 minutes no matter how long the outage runs."""
    return min(RETRY_BACKOFF_BASE_SECONDS * (2 ** max(0, attempts - 1)),
               RETRY_BACKOFF_CAP_SECONDS)


def _stamp_sent_kind(state: Dict[str, Any], kind: str) -> None:
    """Record a CONFIRMED delivery. Shared by Reporter._stamp_sent (a live
    send) and flush_undeliverable (a retried send) -- one implementation, not
    two independently-maintained copies. See dispatch3()'s docstring for why
    a second copy of shared dispatch/record logic is exactly the shape this
    codebase's worst bugs have shipped as before (U069)."""
    sent = state.setdefault("sent", {})
    prior = sent.get(kind)
    if not isinstance(prior, dict):
        sent[kind] = {"count": 0, "first_at": prior, "last_at": prior}
    rec = sent[kind]
    rec["count"] = rec.get("count", 0) + 1
    now = utcnow()
    rec["first_at"] = rec["first_at"] or now
    rec["last_at"] = now


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


def flush_undeliverable(state: Dict[str, Any], store: StateStore) -> Dict[str, int]:
    """Retry every DUE queued message. THIS is the only retry driver in the
    system -- everything that ever recovers a notify outage goes through this
    one function:

      - Reporter.to_requester() calls it automatically, unconditionally, on
        every ack/progress/blocked/done -- i.e. on every normal thing a live
        job already does. An active job heals its own backlog with zero
        additional action from anyone.
      - cmd_status() calls it opportunistically (best-effort, non-blocking)
        so that even a job that has already gone terminal heals the next time
        anyone runs the ordinary, pre-existing --status command -- not a
        special recovery flag, not a cron entry invented for this fix.
      - cmd_sweep_undeliverable() (--sweep-undeliverable) also calls it, kept
        for an operator who wants to force an immediate check -- but it is no
        longer LOAD-BEARING for recovery, and, critically, it is not a
        DIFFERENT code path: because it shares this exact function, it obeys
        the exact same next_attempt_at backoff gate and the exact same
        poisoned/transport split as the automatic callers. A cron entry
        calling --sweep-undeliverable on a tight schedule cannot hot-loop the
        transport (due-check throttles every caller identically) and cannot
        un-park a poisoned message (this function only ever reads
        state["undeliverable"]; state["parked"] is never touched by it) --
        this is what closes the second failed attempt's hole ("putting the
        flag in a cron line recreated unbounded retry").

    Never discards. A message leaves state["undeliverable"] only by being
    CONFIRMED delivered (state["sent"]) or by being independently proven
    poisoned (state["parked"], content preserved -- see the module docstring
    above for what evidence justifies that move). Everything else -- however
    long the outage runs, however many times this is invoked -- stays queued,
    retried on capped backoff, forever.

    Returns {"delivered": N, "still_queued": N, "parked": N}.
    """
    undeliverable = state.get("undeliverable") or []
    if not undeliverable:
        return {"delivered": 0, "still_queued": 0, "parked": 0}

    now = utcnow()
    now_dt = _parse_iso(now)
    due: List[Dict[str, Any]] = []
    not_due: List[Dict[str, Any]] = []
    for msg in undeliverable:
        nat = _parse_iso(msg.get("next_attempt_at"))
        # Missing/unparseable next_attempt_at (e.g. a pre-fix state.json, or a
        # record with no chat_id/kind at all) is treated as "due" -- never as
        # a reason to skip forever.
        if nat is None or now_dt is None or nat <= now_dt:
            due.append(msg)
        else:
            not_due.append(msg)
    if not due:
        return {"delivered": 0, "still_queued": len(undeliverable), "parked": 0}

    transport = state.setdefault("transport", {})
    delivered = 0
    remaining: List[Dict[str, Any]] = list(not_due)
    parked_now: List[Dict[str, Any]] = []

    for msg in due:
        chat_id = msg.get("chat_id", "")
        kind = msg.get("kind", "")
        message = msg.get("message", "")
        if not (chat_id and kind):
            # Nothing to attempt (malformed record) -- keep it queued as-is
            # rather than silently dropping it; do not spin on it.
            remaining.append(msg)
            continue

        result = dispatch3(chat_id, kind, message)
        if result is CheckResult.PASS:
            delivered += 1
            _stamp_sent_kind(state, kind)
            transport["last_ok_at"] = now
            continue

        attempts = msg.get("attempts", 0) + 1
        msg["attempts"] = attempts
        msg["last_attempt_at"] = now
        msg["outcome"] = result.value

        # Poisoning evidence: transport independently confirmed working
        # (state["transport"]["last_ok_at"]) AT OR AFTER this exact
        # message first started failing (msg["at"]), yet it failed again just
        # now. That is real, observed evidence the content -- not the
        # transport -- is the problem. `>=` (not strict `>`): a sibling
        # success timestamped in the SAME second (state.py's utcnow() has
        # second resolution) is still a real, independent confirmation the
        # transport answered for someone -- it is not weaker evidence for
        # being contemporaneous. No such evidence at all -> leave the counter
        # alone; it just backs off and stays queued (see module docstring).
        last_ok = _parse_iso(transport.get("last_ok_at"))
        queued_at = _parse_iso(msg.get("at"))
        if last_ok is not None and queued_at is not None and last_ok >= queued_at:
            msg["confirmed_up_failures"] = msg.get("confirmed_up_failures", 0) + 1

        if msg.get("confirmed_up_failures", 0) >= POISON_CONFIRM_THRESHOLD:
            msg["parked_at"] = now
            msg["parked_reason"] = (
                f"failed {msg['confirmed_up_failures']} time(s) AFTER the transport "
                "was independently confirmed working (another queued message got "
                "through since this one first failed) -- retrying is pointless; "
                "content preserved below, never re-attempted automatically")
            parked_now.append(msg)
            continue

        msg["next_attempt_at"] = _add_seconds(now, _backoff_seconds(attempts))
        remaining.append(msg)

    state["undeliverable"] = remaining
    if parked_now:
        parked_list = state.setdefault("parked", [])
        parked_list.extend(parked_now)
        events = state.setdefault("events", [])
        for m in parked_now:
            events.append({"at": now, "kind": "report.parked",
                           "message": f"poisoned {m.get('kind','?')} message parked "
                                      f"after {m.get('confirmed_up_failures')} confirmed-up "
                                      f"failures -- content preserved, never told to the "
                                      f"requester"})
    store.save(state)
    return {"delivered": delivered, "still_queued": len(remaining), "parked": len(parked_now)}


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
        # Automatic, unconditional retry drain BEFORE handling this new
        # message. This is what makes recovery from a notify outage require
        # NO human action: every ack/progress/blocked/done a live job already
        # sends also opportunistically clears whatever is due in the backlog.
        # See flush_undeliverable()'s docstring.
        flush_undeliverable(self.state, self.store)

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
            # Stamp the transport heartbeat -- this live confirmed send is
            # exactly the same kind of evidence a flush-retried send is (see
            # flush_undeliverable()'s poisoning check), so it must update the
            # same field.
            self.state.setdefault("transport", {})["last_ok_at"] = utcnow()
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
            # exit / could not start): never discard. Queue with a backoff
            # schedule -- flush_undeliverable() (called automatically, see
            # above) retries it forever until either CONFIRMED delivered or
            # independently proven poisoned. Do NOT stamp the blocked dedupe
            # timer -- see above.
            now = utcnow()
            self.state.setdefault("undeliverable", []).append(
                {"at": now, "kind": kind, "message": message,
                 "chat_id": chat_id, "attempts": 1, "outcome": result.value,
                 "next_attempt_at": _add_seconds(now, _backoff_seconds(1)),
                 "confirmed_up_failures": 0})
        self.store.save(self.state)

    @staticmethod
    def _blocked_key(phase_id: str, reason: str) -> str:
        return f"{phase_id}\x00{reason}"

    def _stamp_sent(self, kind: str) -> None:
        _stamp_sent_kind(self.state, kind)

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
