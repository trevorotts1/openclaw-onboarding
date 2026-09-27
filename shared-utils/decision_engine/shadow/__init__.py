#!/usr/bin/env python3
"""Shadow evaluation sampler (JEV 1.1, spec 3.6/3.9; A61).

Consumes the D34 shadow predicates (modes.py: ``shadow_sample_allowed``,
``shadow_dedup_key``, ``refuse_shadow_commit``) and gives them the missing
half: a PERSISTED evaluation-state store, so sampling/quota/dedup/in-flight/
deadline enforcement survives restart and failover.

State lives in SQLite beside the task state (``<state_dir>/shadow_evaluation.db``),
never in memory: every instance rehydrates from the tables on the next call,
and two processes sharing one state_dir are serialized by the primary key
(dedup key) plus a short transaction — a losing racer is told "duplicate
sample", never admitted twice. This module owns no task/persona/weight/
confirmation/execution state and never writes to any of them: results are
diagnostic only, and ``refuse_shadow_commit`` is exercised on every
evaluation path so a shadow result can never become an assignment.

Deadline: spec 3.6's ``evaluation_deadline_ms`` (default 6000) is persisted
per sample as an absolute deadline; the gate's optional ``deadline_ms``
parameter denies with the typed reason ``deadline_expired`` when the
evaluation's own remaining allowance is exhausted, and expired in-flight
samples are swept to ``expired`` on every evaluation so they cannot hold the
in-flight slot past their deadline (failover reconciliation). The deadline is
bounded to the evaluation's own context: this module never extends a
production deadline and never touches foreground budgets.

Stdlib only (sqlite3, hashlib, time, importlib, copy, pathlib). No network.
No process-environment reads. Paths resolve from the caller-supplied
``state_dir``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sqlite3
import time
from pathlib import Path

_MODES_PY = Path(__file__).resolve().parent.parent / "modes" / "modes.py"

# Spec 3.6 shadow config block defaults (evaluation context only).
SHADOW_DEFAULTS = {
    "sample_rate": 0.01,
    "max_evaluations_per_company_hour": 20,
    "max_external_attempts_per_company_hour": 40,
    "max_in_flight_per_company": 1,
    "evaluation_deadline_ms": 6000,
}

# One shared window for both hourly budgets (evaluations, external attempts).
WINDOW_S = 3600.0

# Sample statuses. ``skipped`` carries the typed denial reason; ``expired``
# is a deadline sweep result.
STATUS_IN_FLIGHT = "in_flight"
STATUS_COMPLETE = "complete"
STATUS_SKIPPED = "skipped"
STATUS_EXPIRED = "expired"

REASON_DEADLINE_EXPIRED = "deadline_expired"
REASON_DUPLICATE_SAMPLE = "duplicate_sample"
REASON_DUPLICATE_IN_FLIGHT = "duplicate_in_flight"
REASON_EXTERNAL_QUOTA_EXHAUSTED = "external_quota_exhausted"

_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS shadow_samples (
  key        TEXT PRIMARY KEY,
  company    TEXT NOT NULL,
  task_key   TEXT NOT NULL,
  epoch      TEXT NOT NULL,
  status     TEXT NOT NULL,
  reason     TEXT NOT NULL DEFAULT '',
  deadline_s REAL,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_shadow_samples_company
  ON shadow_samples(company, status, created_at);
CREATE TABLE IF NOT EXISTS shadow_external_attempts (
  company TEXT NOT NULL,
  ts      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_shadow_attempts_company
  ON shadow_external_attempts(company, ts);
"""

__all__ = [
    "REASON_DEADLINE_EXPIRED",
    "REASON_DUPLICATE_IN_FLIGHT",
    "REASON_DUPLICATE_SAMPLE",
    "REASON_EXTERNAL_QUOTA_EXHAUSTED",
    "SHADOW_DEFAULTS",
    "STATUS_COMPLETE",
    "STATUS_EXPIRED",
    "STATUS_IN_FLIGHT",
    "STATUS_SKIPPED",
    "ShadowEvaluator",
    "parse_shadow_config",
    "shadow_state_dir",
]


def _load_modes():
    """Import the REAL D34 modes module by path (never restated, never copied).

    Same pattern as commit/dispatch.py::_load_commit: registered in
    sys.modules under a path key so every caller and test share one class
    object (ShadowCommitError identity survives distinct loads).
    """
    import sys as _sys  # stdlib, deferred (import cost only)

    key = "jev_d34_modes:" + str(_MODES_PY)
    cached = _sys.modules.get(key)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(key, str(_MODES_PY))
    mod = importlib.util.module_from_spec(spec)
    _sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


def shadow_state_dir(state_dir):
    """The state directory the SAMPLER owns for this deployment.

    Callers hand us their task state dir; we keep one shadow db beside it.
    Returned as a resolved Path for stable cross-process agreement.
    """
    if state_dir is None:
        raise ValueError("state_dir required")
    return Path(state_dir) / "shadow_evaluation.db"


def parse_shadow_config(raw=None):
    """The 3.6 shadow block resolved over the defaults.

    Returns ``{"enabled": bool, "shadow": {...resolved fields...}}``. A
    company with no shadow block is disabled (shadow is opt-in) unless it
    says ``"shadow_enabled": true``. Unknown keys are ignored
    (forward-compatible); values are coerced to their default's type and a
    malformed value falls back to the default — a broken config must never
    crash the foreground path.
    """
    out = {"enabled": False, "shadow": dict(SHADOW_DEFAULTS)}
    if not isinstance(raw, dict):
        return out
    block = raw.get("shadow")
    if not isinstance(block, dict):
        out["enabled"] = raw.get("shadow_enabled") is True
        return out
    resolved = dict(SHADOW_DEFAULTS)
    for key in SHADOW_DEFAULTS:
        if key not in block:
            continue
        try:
            resolved[key] = type(SHADOW_DEFAULTS[key])(block[key])
        except (TypeError, ValueError):
            resolved[key] = SHADOW_DEFAULTS[key]
    out["shadow"] = resolved
    enabled = block.get("enabled")
    if enabled is None:
        enabled = raw.get("shadow_enabled")
    out["enabled"] = True if enabled is None else bool(enabled)
    return out


class ShadowEvaluator:
    """Persisted shadow evaluation sampler for one (state_dir, task_key).

    One short SQLite transaction per operation. No in-memory counters: every
    decision reads the tables, so a process restart or a failover to a second
    process sees exactly the state the first one left. The dedup-key primary
    key is the cross-process compare-and-swap point.
    """

    def __init__(self, state_dir, task_key):
        if not task_key:
            raise ValueError("task_key required")
        self.state_dir = str(state_dir)
        self.task_key = str(task_key)
        self.db_path = str(shadow_state_dir(state_dir))
        self.modes = _load_modes()

    # -- plumbing ----------------------------------------------------------
    def _connect(self):
        con = sqlite3.connect(self.db_path, timeout=30)
        con.executescript(_SCHEMA_DDL)
        return con

    @staticmethod
    def _now(now_s):
        return float(now_s) if now_s is not None else time.time()

    def _sweep_expired(self, con, company, now_s):
        """Failover reconciliation: deadline-passed in-flight -> expired."""
        cur = con.execute(
            "UPDATE shadow_samples SET status=?, reason=?, updated_at=?"
            " WHERE company=? AND status=? AND deadline_s IS NOT NULL"
            " AND deadline_s <= ?",
            (STATUS_EXPIRED, REASON_DEADLINE_EXPIRED, now_s, company,
             STATUS_IN_FLIGHT, now_s))
        return cur.rowcount

    def _open_in_flight(self, con, company, now_s):
        cur = con.execute(
            "SELECT COUNT(*) FROM shadow_samples WHERE company=?"
            " AND status=? AND (deadline_s IS NULL OR deadline_s > ?)",
            (company, STATUS_IN_FLIGHT, now_s))
        return int(cur.fetchone()[0])

    def _evaluations_used_hour(self, con, company, now_s):
        cur = con.execute(
            "SELECT COUNT(*) FROM shadow_samples WHERE company=?"
            " AND status IN (?, ?, ?) AND created_at > ?",
            (company, STATUS_IN_FLIGHT, STATUS_COMPLETE, STATUS_EXPIRED,
             now_s - WINDOW_S))
        return int(cur.fetchone()[0])

    def _external_used_hour(self, con, company, now_s):
        con.execute("DELETE FROM shadow_external_attempts WHERE ts <= ?",
                    (now_s - WINDOW_S,))
        cur = con.execute(
            "SELECT COUNT(*) FROM shadow_external_attempts"
            " WHERE company=? AND ts > ?", (company, now_s - WINDOW_S))
        return int(cur.fetchone()[0])

    @staticmethod
    def _derived_draw(dedup_key):
        """Deterministic [0,1) draw from the sample identity.

        A repeated sweep of the same identity draws the same value; identity
        changes (epoch, input hash, versions) draw independently. Callers
        may still pass their own ``draw``.
        """
        digest = hashlib.sha256(str(dedup_key).encode("utf-8")).hexdigest()
        return int(digest[:16], 16) / float(1 << 64)

    # -- evaluation --------------------------------------------------------
    def evaluate(self, *, company, scope, input_hash, stage,
                 candidate_version, policy_version, model_version, epoch,
                 config, now_s=None, draw=None, permission_ok=True,
                 deadline_remaining_ms=None):
        """Admit (or refuse) one shadow evaluation against persisted state.

        Gate order (all persisted): dedup -> sampling/permission -> hourly
        evaluation quota -> in-flight cap -> deadline. Every admission lands
        as one ``in_flight`` row before any result exists; every denial
        lands as a ``skipped`` row with the typed reason. Returns a dict;
        never raises for a denial.
        """
        resolved = parse_shadow_config(config)
        if not resolved["enabled"]:
            return {"run": False, "reason": "shadow_disabled",
                    "persisted": False, "task_key": self.task_key}
        cfg = resolved["shadow"]
        key = self.modes.shadow_dedup_key(
            company=company, scope=scope, input_hash=input_hash, stage=stage,
            candidate_version=candidate_version,
            policy_version=policy_version, model_version=model_version,
            epoch=epoch)
        # A shadow result can never be committed; exercising the refusal on
        # every evaluation path is the contract, not an afterthought.
        try:
            self.modes.refuse_shadow_commit({"shadow_key": key})
        except self.modes.ShadowCommitError as refusal:
            refusal_reason = str(refusal)
        now = self._now(now_s)
        con = self._connect()
        try:
            self._sweep_expired(con, company, now)
            row = con.execute(
                "SELECT status, reason, deadline_s FROM shadow_samples"
                " WHERE key=?", (key,)).fetchone()
            if row is not None:
                status = row[0]
                reason = (REASON_DUPLICATE_IN_FLIGHT
                          if status == STATUS_IN_FLIGHT
                          else REASON_DUPLICATE_SAMPLE)
                con.commit()
                return {"run": False, "reason": reason, "persisted": True,
                        "prior_status": status, "key": key,
                        "task_key": self.task_key}
            evals_used = self._evaluations_used_hour(con, company, now)
            in_flight = self._open_in_flight(con, company, now)
            allowance_ms = cfg["evaluation_deadline_ms"]
            if deadline_remaining_ms is not None:
                allowance_ms = min(float(deadline_remaining_ms),
                                   float(cfg["evaluation_deadline_ms"]))
            allowed, reason = self.modes.shadow_sample_allowed(
                sample_rate=cfg["sample_rate"],
                draw=self._derived_draw(key) if draw is None else draw,
                quota_remaining=(cfg["max_evaluations_per_company_hour"]
                                 - evals_used),
                in_flight=in_flight,
                max_in_flight=cfg["max_in_flight_per_company"],
                permission_ok=permission_ok,
                deadline_ms=allowance_ms)
            if not allowed:
                con.execute(
                    "INSERT INTO shadow_samples(key, company, task_key,"
                    " epoch, status, reason, deadline_s, created_at,"
                    " updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (key, company, self.task_key, str(epoch), STATUS_SKIPPED,
                     reason, None, now, now))
                con.commit()
                return {"run": False, "reason": reason, "persisted": True,
                        "key": key, "task_key": self.task_key,
                        "evals_used_hour": evals_used,
                        "in_flight": in_flight}
            deadline_s = now + float(cfg["evaluation_deadline_ms"]) / 1000.0
            con.execute(
                "INSERT INTO shadow_samples(key, company, task_key, epoch,"
                " status, reason, deadline_s, created_at, updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (key, company, self.task_key, str(epoch), STATUS_IN_FLIGHT,
                 "sampled", deadline_s, now, now))
            con.commit()
            return {"run": True, "reason": "sampled", "persisted": True,
                    "key": key, "task_key": self.task_key,
                    "deadline_s": deadline_s,
                    "evals_used_hour": evals_used + 1,
                    "in_flight": in_flight + 1,
                    "refused_commit": refusal_reason}
        finally:
            con.close()

    def finish(self, *, key, outcome="complete", reason="", now_s=None):
        """Record the evaluation outcome for an in-flight sample.

        ``complete`` closes it; a sample already swept to ``expired`` cannot
        be finished (its deadline ruled) and reports that instead.
        """
        if outcome not in (STATUS_COMPLETE, STATUS_SKIPPED):
            raise ValueError("outcome must be %r or %r"
                             % (STATUS_COMPLETE, STATUS_SKIPPED))
        now = self._now(now_s)
        con = self._connect()
        try:
            cur = con.execute(
                "UPDATE shadow_samples SET status=?, reason=?, updated_at=?"
                " WHERE key=? AND status=?",
                (outcome, reason or "evaluated", now, key, STATUS_IN_FLIGHT))
            if cur.rowcount:
                con.commit()
                return {"recorded": True, "outcome": outcome, "key": key}
            row = con.execute(
                "SELECT status, reason FROM shadow_samples WHERE key=?",
                (key,)).fetchone()
            con.commit()
            if row is None:
                return {"recorded": False, "reason": "unknown_sample",
                        "key": key}
            return {"recorded": False, "reason": "already_%s" % row[0],
                    "prior_reason": row[1], "key": key}
        finally:
            con.close()

    def reserve_external(self, *, company, config, now_s=None):
        """Reserve one external attempt against the persisted hourly budget.

        Failover retries call this again and consume the SAME quota: the
        reservations live in the table, not the process.
        """
        cfg = parse_shadow_config(config)["shadow"]
        now = self._now(now_s)
        con = self._connect()
        try:
            used = self._external_used_hour(con, company, now)
            cap = int(cfg["max_external_attempts_per_company_hour"])
            if used >= cap:
                con.commit()
                return {"reserved": False,
                        "reason": REASON_EXTERNAL_QUOTA_EXHAUSTED,
                        "used_hour": used, "cap": cap}
            con.execute(
                "INSERT INTO shadow_external_attempts(company, ts)"
                " VALUES(?,?)", (company, now))
            con.commit()
            return {"reserved": True, "used_hour": used + 1, "cap": cap}
        finally:
            con.close()

    # -- reads -------------------------------------------------------------
    def status(self, *, key):
        """Persisted row for one sample key, or None."""
        con = self._connect()
        try:
            cur = con.execute(
                "SELECT key, company, task_key, epoch, status, reason,"
                " deadline_s, created_at, updated_at FROM shadow_samples"
                " WHERE key=?", (key,))
            row = cur.fetchone()
            if row is None:
                return None
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))
        finally:
            con.close()

    def company_state(self, *, company, now_s=None):
        """Rehydrated enforcement numbers for a company (restart-proof)."""
        now = self._now(now_s)
        con = self._connect()
        try:
            self._sweep_expired(con, company, now)
            con.commit()
            return {
                "evaluations_used_hour":
                    self._evaluations_used_hour(con, company, now),
                "external_used_hour": self._external_used_hour(con, company,
                                                               now),
                "in_flight": self._open_in_flight(con, company, now),
            }
        finally:
            con.close()
