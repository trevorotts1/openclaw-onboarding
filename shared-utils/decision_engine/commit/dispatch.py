#!/usr/bin/env python3
"""CAS-backed re-dispatch adapter (JEV 1.1, ss 8.12/10.3/10.4; A35/A36).

Thin persistence seam over the EXISTING D23 single-writer module
(``commit.py``: cas_commit / recommit_scope / check_late_result). No CAS
logic restated here: every mutation goes through the D23 functions, and the
store is hydrated from a real SQLite handle (never a bare in-memory dict in
production paths).

Revision auditability: each committed decision appends one row to the
``decision_revisions`` table beside the task row (decisionId, revision,
envelope, reason, evidence). Readers (board/report-back) consume the chain
via :func:`revision_history`.

Scope-change detection (spec 8.12): :func:`detect_scope_change` diffs the
8.12 invalidation dimensions (title/description/audience/voice/SOP/catalog/
policy/model/owner/persona). Unchanged re-dispatch reuses the committed
selection; a changed scope goes through ``recompute_fn`` + ``recommit_scope``
with reason + evidence recorded.

Stdlib only. No network, no provider access.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import time
from pathlib import Path

_COMMIT_PY = Path(__file__).resolve().parent / "commit.py"


def _load_commit():
    """Import the existing D23 module by path (never restated, never copied).

    Registered under its file path in sys.modules so ``check_late_result``
    failures raise the SAME class object every caller (and test) imports —
    distinct ``spec_from_file_location`` loads would otherwise mint distinct
    ``LateResultError`` identities that ``assertRaises`` cannot catch.
    """
    import sys as _sys  # noqa: PLC0415 (stdlib, deferred for import cost)

    key = "jev_d23_commit:" + str(_COMMIT_PY)
    cached = _sys.modules.get(key)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(key, str(_COMMIT_PY))
    mod = importlib.util.module_from_spec(spec)
    _sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


# Spec 8.12 reuse-invalidation dimensions, as scope-dict keys.
SCOPE_FIELDS = (
    "title", "description", "audience", "voice", "sop", "catalog",
    "policy", "model", "owner", "persona",
)

# Audience-update detector watches the audience/voice/SOP triple (A36).
AUDIENCE_FIELDS = ("audience", "voice", "sop")

REVISION_DDL = """
CREATE TABLE IF NOT EXISTS decision_revisions (
  decision_id  TEXT PRIMARY KEY,
  task_key     TEXT NOT NULL,
  revision     INTEGER NOT NULL,
  envelope     TEXT NOT NULL,
  mirrors      TEXT NOT NULL DEFAULT '{}',
  reason       TEXT NOT NULL DEFAULT '',
  evidence     TEXT NOT NULL DEFAULT '{}',
  created_at   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_decision_revisions_task
  ON decision_revisions(task_key, revision);
"""


def _canon(value) -> str:
    """JSON-canonical form for stable compare + hashing (None-safe)."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      default=str)


def scope_hash(scope: dict) -> str:
    """Stable input hash over the 8.12 scope dimensions."""
    scoped = {k: (scope or {}).get(k) for k in SCOPE_FIELDS}
    return hashlib.sha256(_canon(scoped).encode("utf-8")).hexdigest()[:32]


def detect_scope_change(old_scope: dict, new_scope: dict) -> list:
    """Return the 8.12 dimensions that changed (empty = reuse, no recompute)."""
    old, new = old_scope or {}, new_scope or {}
    return [k for k in SCOPE_FIELDS if _canon(old.get(k)) != _canon(new.get(k))]


def audience_scope_changed(old_bundle: dict, new_spec: dict) -> list:
    """Audience-update change detector (A36): audience/voice/SOP diff fires."""
    old, new = old_bundle or {}, new_spec or {}
    return [k for k in AUDIENCE_FIELDS
            if _canon(old.get(k)) != _canon(new.get(k))]


def ensure_revision_table(con: sqlite3.Connection) -> None:
    """Create the audit sidecar if absent. No schema-version bump: additive."""
    con.executescript(REVISION_DDL)


def latest_revision(con: sqlite3.Connection, task_key: str):
    """Newest revision row for a task, or None (first dispatch)."""
    ensure_revision_table(con)
    return con.execute(
        "SELECT decision_id, task_key, revision, envelope, mirrors, reason,"
        " evidence, created_at FROM decision_revisions"
        " WHERE task_key=? ORDER BY revision DESC LIMIT 1",
        (task_key,)).fetchone()


def revision_history(con: sqlite3.Connection, task_key: str) -> list:
    """Full version chain, oldest first (board/report-back surface)."""
    ensure_revision_table(con)
    rows = con.execute(
        "SELECT decision_id, revision, envelope, reason, evidence, created_at"
        " FROM decision_revisions WHERE task_key=? ORDER BY revision ASC",
        (task_key,)).fetchall()
    return [dict(r) for r in rows]


def load_cas_store(con: sqlite3.Connection, task_key: str,
                   input_hash=None):
    """Hydrate a D23 store from the persisted chain (real DB handle, WAL-safe).

    Returns ``(commit_module, store)``. First dispatch yields revision 0 with
    no decision; otherwise head revision + committed envelope.
    """
    commit = _load_commit()
    row = latest_revision(con, task_key)
    if row is None:
        return commit, commit.fresh_state(input_hash=input_hash)
    store = commit.fresh_state(input_hash=row["envelope"] and input_hash)
    store["decision_revision"] = int(row["revision"])
    store["decision"] = json.loads(row["envelope"])
    store["mirrors"] = json.loads(row["mirrors"] or "{}")
    return commit, store


def append_revision(con: sqlite3.Connection, task_key: str, revision: int,
                    decision: dict, mirrors: dict, reason: str,
                    evidence: dict) -> str:
    """Persist one envelope/decisionId/version-chain row beside the task row.

    Row key is the task+revision pair, so a recomputed decision that reuses
    its own decisionId under a new revision never collides.
    """
    revision = int(revision)
    row_key = "%s#r%d" % (task_key, revision)
    decision = dict(decision or {})
    decision.setdefault("decisionId", row_key)
    con.execute(
        "INSERT INTO decision_revisions(decision_id, task_key, revision,"
        " envelope, mirrors, reason, evidence, created_at)"
        " VALUES(?,?,?,?,?,?,?,?)",
        (row_key, task_key, int(revision), _canon(decision),
         _canon(mirrors or {}), reason or "",
         _canon(evidence or {}), time.time()))
    return row_key


def guard_late_result(store, kind: str, result_revision: int) -> bool:
    """Fail-closed late gate through the existing D23 ``check_late_result``."""
    commit = _load_commit()
    return commit.check_late_result(store, kind, result_revision)


def redispatch(con: sqlite3.Connection, task_key: str, new_scope: dict,
               recompute_fn, reason: str, evidence=None,
               commit_in: bool = True):
    """Reuse-vs-revision (A35) against real persistence.

    * No committed decision yet -> commit the recomputed selection as rev 1.
    * Scope unchanged -> reuse: ``("reuse", revision, committed_envelope)``.
    * Scope changed -> ``recompute_fn(base, new_scope)`` through the existing
      ``recommit_scope`` (head-guarded), then persist the new revision row
      with reason + evidence: ``("recommitted", new_rev, snapshot)``.

    Stale callers lose with ``ObsoleteRevisionError``/``ObsoleteInputError``
    and write nothing (no torn mirrors, no clobbered head).
    """
    commit = _load_commit()
    evidence = dict(evidence or {})
    new_hash = scope_hash(new_scope)
    row = latest_revision(con, task_key)
    if row is None:
        store = commit.fresh_state(input_hash=new_hash)
        decision, mirrors = recompute_fn(None, dict(new_scope or {}))
        decision = dict(decision or {})
        decision.setdefault("decisionId", "%s#r1" % task_key)
        decision["inputHash"] = new_hash
        new_rev = commit.cas_commit(store, 0, decision, dict(mirrors or {}))
        decision_id = append_revision(con, task_key, new_rev, decision,
                                      dict(mirrors or {}), reason, evidence)
        if commit_in:
            con.commit()
        return ("committed", new_rev,
                {"decision_id": decision_id, "revision": new_rev,
                 "decision": decision})
    old_envelope = json.loads(row["envelope"])
    old_scope = old_envelope.get("scope") or {}
    changed = detect_scope_change(old_scope, new_scope)
    if not changed:
        return ("reuse", int(row["revision"]), dict(old_envelope))
    store = commit.fresh_state(input_hash=old_envelope.get("inputHash"))
    store["decision_revision"] = int(row["revision"])
    store["decision"] = old_envelope
    store["mirrors"] = json.loads(row["mirrors"] or "{}")
    # Scope moved: the recomputed decision carries the NEW input hash, so the
    # head guard compares against it (existing cas_commit semantics).
    store["input_hash"] = new_hash

    def _recompute(base, scope):
        decision, mirrors = recompute_fn(base, dict(scope or {}))
        decision = dict(decision or {})
        decision["inputHash"] = new_hash
        decision["scope"] = dict(scope or {})
        return decision, dict(mirrors or {})

    new_rev, snapshot = commit.recommit_scope(
        store, int(row["revision"]), dict(new_scope or {}), _recompute)
    snapshot = dict(snapshot)
    # Recomputed decisions keep their own decisionId (recompute_fn owns it);
    # the audit row keys on task+revision, so a reused id never collides.
    snapshot.setdefault("decisionId", "%s#r%d" % (task_key, new_rev))
    evidence = dict(evidence)
    evidence.setdefault("changed_fields", changed)
    evidence.setdefault("prior_revision", int(row["revision"]))
    decision_id = append_revision(con, task_key, new_rev, snapshot,
                                  store["mirrors"], reason, evidence)
    if commit_in:
        con.commit()
    return ("recommitted", new_rev,
            {"decision_id": decision_id, "revision": new_rev,
             "decision": snapshot})
