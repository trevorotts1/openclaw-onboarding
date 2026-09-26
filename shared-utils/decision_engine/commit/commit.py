#!/usr/bin/env python3
"""D23 single-writer compare-and-swap commit (JEV spec 1.1, ss 10.3/10.4/5.5).

Extends the existing D02 envelope / D07 ladder seams; replaces nothing.
One decision head per store. ``cas_commit`` writes the decision plus its
board-facing mirrors under one lock hold: exactly one winner per revision.

Stdlib only (copy, threading, time). No network, no disk, no environment
reads. The store is caller-supplied (in-memory dict from ``fresh_state``);
no SQLite handle is ever opened here, so no transaction can span a call.
"""

from __future__ import annotations

import copy
import threading
import time

# Late-result producer kinds (spec 10.3: selector, backfill, producer
# report, audience rescore). Closed set: unknown kinds are caller defects.
LATE_KINDS = ("selector", "backfill", "producer_report", "audience_rescore")

# Pending-selection state machine (spec 10.4). preparing is the only live
# state; committed|held are explicit terminal states. No other statuses
# exist, so no new board columns are needed.
PENDING = "preparing"
TERMINAL = ("committed", "held")

__all__ = [
    "LATE_KINDS",
    "PENDING",
    "TERMINAL",
    "BadTransitionError",
    "FencedError",
    "LateResultError",
    "ObsoleteInputError",
    "ObsoleteRevisionError",
    "PendingSelection",
    "cas_commit",
    "check_fence",
    "check_late_result",
    "consume_retry",
    "fresh_state",
    "issue_fence_token",
    "on_wait_tick",
    "recommit_scope",
    "selfheal_sweep",
    "start_execution",
    "start_pending",
]


class ObsoleteRevisionError(Exception):
    """CAS loser: head moved since ``expected``. Clean retry signal."""

    def __init__(self, expected, actual):
        self.expected = expected
        self.actual = actual
        super().__init__(
            "obsolete revision: expected %r, head is %r" % (expected, actual))


class ObsoleteInputError(Exception):
    """Decision built on a stale input hash. Fails even at head revision."""

    def __init__(self, decision_hash, current_hash):
        self.decision_hash = decision_hash
        self.current_hash = current_hash
        super().__init__(
            "stale input hash: decision %r, current %r"
            % (decision_hash, current_hash))


class FencedError(Exception):
    """Uncommitted work invalidated by root expiry or mode/policy change."""

    def __init__(self, reason, detail=""):
        self.reason = reason
        self.detail = detail
        super().__init__("fenced: %s%s" % (
            reason, (" (%s)" % detail) if detail else ""))


class LateResultError(Exception):
    """Late producer result against an obsolete decision revision."""

    def __init__(self, kind, result_revision, head_revision):
        self.kind = kind
        self.result_revision = result_revision
        self.head_revision = head_revision
        super().__init__(
            "late %s result: revision %r is obsolete, head is %r"
            % (kind, result_revision, head_revision))


class BadTransitionError(Exception):
    """Illegal state-machine or scope-path transition."""

    def __init__(self, from_state, to_state):
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            "bad transition: %r -> %r" % (from_state, to_state))


def fresh_state(*, input_hash=None, retry_budget=3, clock=None,
                mode_revision=0, policy_revision=0, root_budget_s=None):
    """New in-memory store. One root deadline; deliberately no extend API."""
    clk = clock or time.monotonic
    now = float(clk())
    return {
        "_lock": threading.RLock(),
        "_clock": clk,
        "decision_revision": 0,
        "input_hash": input_hash,
        "decision": None,
        "mirrors": {},
        "fence": {
            "mode_revision": int(mode_revision),
            "policy_revision": int(policy_revision),
            "deadline_s": (now + float(root_budget_s)
                           if root_budget_s is not None else None),
        },
        "pending": None,
        "retry": {"remaining": int(retry_budget), "consumed": 0},
        "wait_ticks": 0,
        "selfheal_spawns": 0,
        "execution_started": False,
        "running_snapshot": None,
        "running_revision": None,
        "dispatched": [],
    }


def issue_fence_token(store):
    """Snapshot current fence generations for an uncommitted recommendation."""
    with store["_lock"]:
        return dict(store["fence"])


def check_fence(store, token):
    """Validate an uncommitted recommendation. Never touches committed state.

    Raises FencedError on root expiry or mode/policy revision change.
    """
    with store["_lock"]:
        fence = store["fence"]
        deadline = fence["deadline_s"]
        if deadline is not None and float(store["_clock"]()) > deadline:
            raise FencedError("root_expired")
        if token.get("mode_revision") != fence["mode_revision"]:
            raise FencedError("mode_changed")
        if token.get("policy_revision") != fence["policy_revision"]:
            raise FencedError("policy_changed")
    return True


def cas_commit(store, expected_revision, decision, mirrors):
    """Single compare-and-swap: decision + mirrors written atomically.

    Hash check runs first, so a stale input hash fails cleanly even at the
    current revision. A revision mismatch raises ObsoleteRevisionError and
    writes nothing (no torn mirrors). Returns the new head revision.
    """
    if not isinstance(decision, dict) or not isinstance(mirrors, dict):
        raise ValueError("decision and mirrors must both be dicts")
    with store["_lock"]:
        if decision.get("inputHash") != store["input_hash"]:
            raise ObsoleteInputError(
                decision.get("inputHash"), store["input_hash"])
        if expected_revision != store["decision_revision"]:
            raise ObsoleteRevisionError(
                expected_revision, store["decision_revision"])
        token = decision.get("fence_token")
        if token is not None:
            check_fence(store, token)
        store["decision"] = copy.deepcopy(decision)
        store["mirrors"] = copy.deepcopy(mirrors)
        store["decision_revision"] = expected_revision + 1
        return store["decision_revision"]


class PendingSelection:
    """Explicit preparation record: preparing -> committed|held, then done."""

    STATUSES = (PENDING,) + tuple(TERMINAL)

    def __init__(self, preparation_id, generation=0):
        self.preparation_id = preparation_id
        self.generation = int(generation)
        self.status = PENDING

    @property
    def terminal(self):
        return self.status in TERMINAL

    def _move(self, target):
        if self.status != PENDING:
            raise BadTransitionError(self.status, target)
        self.status = target
        return self.status

    def commit(self):
        return self._move("committed")

    def hold(self, reason=""):
        self.reason = reason
        return self._move("held")


def start_pending(store, preparation_id, generation=0):
    """Record a new in-flight selection. Refuses a second live one."""
    with store["_lock"]:
        cur = store["pending"]
        if cur is not None and not cur.terminal:
            raise BadTransitionError(cur.status, PENDING)
        sel = PendingSelection(preparation_id, generation)
        store["pending"] = sel
        return sel


def check_late_result(store, kind, result_revision):
    """Gate a producer result against the head revision. Typed failure."""
    if kind not in LATE_KINDS:
        raise ValueError("unknown late-result kind: %r" % (kind,))
    with store["_lock"]:
        head = store["decision_revision"]
        if result_revision != head:
            raise LateResultError(kind, result_revision, head)
    return True


def on_wait_tick(store):
    """Record a pending-wait tick. Never consumes retry budget."""
    with store["_lock"]:
        store["wait_ticks"] += 1
        return store["wait_ticks"]


def consume_retry(store):
    """Spend one retry attempt. Refused while a selection is in flight."""
    with store["_lock"]:
        cur = store["pending"]
        if cur is not None and not cur.terminal:
            raise BadTransitionError(cur.status, "retry_consumed")
        retry = store["retry"]
        if retry["remaining"] <= 0:
            raise BadTransitionError("retry_exhausted", "retry_consumed")
        retry["remaining"] -= 1
        retry["consumed"] += 1
        return retry["remaining"]


def selfheal_sweep(store, reason=""):
    """Sweep entry. Spawns only when no selection record exists at all.

    A live preparing selection — even past some old wait timeout — never
    triggers a parallel selector. Terminal records are settled, not swept.
    """
    with store["_lock"]:
        if store["pending"] is not None:
            return {"spawned": False, "reason": reason,
                    "pending": store["pending"].status}
        store["selfheal_spawns"] += 1
        return {"spawned": True, "reason": reason,
                "spawns": store["selfheal_spawns"]}


def recommit_scope(store, expected_revision, new_scope, recompute_fn):
    """Pre-dispatch scope change: recompute, CAS-commit, dispatch snapshot.

    Refused once execution started (post-start path is amendment, not
    recompute). Returns ``(new_revision, snapshot)`` where the snapshot is
    the dispatched copy matching the post-change scope.
    """
    with store["_lock"]:
        if store["execution_started"]:
            raise BadTransitionError("execution_started", "recompute")
        base = copy.deepcopy(store["decision"])
    # Caller compute runs outside the lock: the head can move meanwhile,
    # which is exactly what expected_revision guards in cas_commit below.
    decision, mirrors = recompute_fn(base, new_scope)
    new_rev = cas_commit(store, expected_revision, decision, mirrors)
    snapshot = copy.deepcopy(decision)
    with store["_lock"]:
        store["dispatched"].append(snapshot)
    return new_rev, copy.deepcopy(snapshot)


def start_execution(store):
    """Freeze the running snapshot. Later commits never rewrite it."""
    with store["_lock"]:
        if store["decision"] is None:
            raise BadTransitionError("no_decision", "start")
        if store["execution_started"]:
            raise BadTransitionError("execution_started", "start")
        store["execution_started"] = True
        store["running_snapshot"] = copy.deepcopy(store["decision"])
        store["running_revision"] = store["decision_revision"]
        return copy.deepcopy(store["running_snapshot"])
