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
import sys
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


_EP_PY = (Path(__file__).resolve().parent.parent.parent
          / "execution_policy" / "__init__.py")


def _load_execution_policy():
    """Import the D11 execution-policy module by path (validator reused).

    Never re-implements owner-confirmation validation: the D11
    ``validate_record`` is the single authorizing gate for the A56
    linked-amendment clause.
    """
    key = "jev_d11_execution_policy:" + str(_EP_PY)
    cached = sys.modules.get(key)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(key, str(_EP_PY))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
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

# Persisted preparation-generation ledger (spec 3.5.3/3.5.4, A56). One row
# per (task, generation): the deadline, cumulative consumed time, attempt
# count, exhausted state, and the amendment link survive a process restart.
# `deadline_s` is the persisted equivalent of the D23 fence `deadline_s`;
# nothing here ever recomputes it for the same (task, generation).
GENERATION_DDL = """
CREATE TABLE IF NOT EXISTS preparation_generations (
  task_key        TEXT NOT NULL,
  generation      INTEGER NOT NULL,
  preparation_id  TEXT NOT NULL,
  deadline_s      REAL,
  consumed_ms     REAL NOT NULL DEFAULT 0,
  attempts        INTEGER NOT NULL DEFAULT 0,
  status          TEXT NOT NULL DEFAULT 'preparing',
  retry_remaining INTEGER NOT NULL DEFAULT 0,
  retry_consumed  INTEGER NOT NULL DEFAULT 0,
  amended_from    INTEGER,
  confirmed_by    TEXT,
  policy_revision INTEGER,
  attempts_json   TEXT NOT NULL DEFAULT '{}',
  created_at      REAL NOT NULL,
  updated_at      REAL NOT NULL,
  PRIMARY KEY (task_key, generation)
);
CREATE INDEX IF NOT EXISTS ix_prep_generations_task
  ON preparation_generations(task_key, generation);
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
    con.executescript(GENERATION_DDL)


def _row_dict(cur, row):
    """Mapping view of a fetched row, whatever the connection's row_factory is.

    Production callers hand us a plain ``sqlite3.Connection`` (tuples); only
    tests set ``sqlite3.Row``. Reading by column name must not depend on that.
    """
    if row is None:
        return None
    if isinstance(row, sqlite3.Row):
        return row
    return dict(zip([d[0] for d in cur.description], row))


def latest_revision(con: sqlite3.Connection, task_key: str):
    """Newest revision row for a task, or None (first dispatch)."""
    ensure_revision_table(con)
    cur = con.execute(
        "SELECT decision_id, task_key, revision, envelope, mirrors, reason,"
        " evidence, created_at FROM decision_revisions"
        " WHERE task_key=? ORDER BY revision DESC LIMIT 1",
        (task_key,))
    return _row_dict(cur, cur.fetchone())


def head_revision(state_dir, task_key: str) -> int:
    """Head revision for ``task_key`` from the persisted chain beside the task.

    The read-side convenience the production callers need before building a
    result: a caller reads the head, computes, then hands that number to its
    ``gate_*_result`` late gate, so a head that moved during the compute is
    refused. 0 means "no committed decision yet" (the same value a fresh store
    carries, so a first-time caller's gate passes). An absent or unreadable
    chain also yields 0 here: the gate itself stays the fail-closed point.
    """
    if not state_dir:
        return 0
    db = Path(state_dir) / "decision_revisions.db"
    if not db.exists():
        return 0
    con = None
    try:
        con = sqlite3.connect(str(db), timeout=30)
        con.row_factory = sqlite3.Row
        row = latest_revision(con, task_key)
        return int(row["revision"]) if row is not None else 0
    except sqlite3.Error:
        return 0
    finally:
        if con is not None:
            con.close()


def revision_history(con: sqlite3.Connection, task_key: str) -> list:
    """Full version chain, oldest first (board/report-back surface)."""
    ensure_revision_table(con)
    cur = con.execute(
        "SELECT decision_id, revision, envelope, reason, evidence, created_at"
        " FROM decision_revisions WHERE task_key=? ORDER BY revision ASC",
        (task_key,))
    return [_row_dict(cur, r) for r in cur.fetchall()]


def load_cas_store(con: sqlite3.Connection, task_key: str,
                   input_hash=None):
    """Hydrate a D23 store from the persisted chain (real DB handle, WAL-safe).

    Returns ``(commit_module, store)``. First dispatch yields revision 0 with
    no decision; otherwise head revision + committed envelope.

    Restart/failover survival (A56): when a preparation-generation row is
    persisted for this task, it is adopted onto the store (deadline, retry,
    pending selection), so a restart or failover reconstructs the SAME
    generation's deadline instead of a fresh one. Adoption stays within the
    latest generation's chain: amending an earlier generation makes the
    later one unreachable by design.
    """
    commit = _load_commit()
    row = latest_revision(con, task_key)
    if row is None:
        store0 = commit.fresh_state(input_hash=input_hash)
    else:
        store0 = commit.fresh_state(input_hash=row["envelope"] and input_hash)
        store0["decision_revision"] = int(row["revision"])
        store0["decision"] = json.loads(row["envelope"])
        store0["mirrors"] = json.loads(row["mirrors"] or "{}")
    gens = generation_rows(con, task_key)
    if gens:
        tail = gens[-1]
        children = [g for g in gens if g["amended_from"] == tail["generation"]]
        latest = children[-1] if children else tail
        commit.adopt_generation(store0, latest)
    return commit, store0


# ── persisted preparation-generation ledger (A56) ──────────────────────
_GEN_FIELDS = ("task_key", "generation", "preparation_id", "deadline_s",
               "consumed_ms", "attempts", "status", "retry_remaining",
               "retry_consumed", "amended_from", "confirmed_by",
               "policy_revision", "attempts_json")


def generation_rows(con: sqlite3.Connection, task_key: str) -> list:
    """Every generation row for a task, oldest first (raw, undecoded)."""
    ensure_revision_table(con)
    cur = con.execute(
        "SELECT " + ", ".join(_GEN_FIELDS) + " FROM preparation_generations"
        " WHERE task_key=? ORDER BY generation", (task_key,))
    return [_row_dict(cur, r) for r in cur.fetchall()]


def load_generation(con: sqlite3.Connection, task_key: str,
                    generation: int | None = None):
    """Decoded generation record for a task (latest when ``generation`` None).

    The row's ``deadline_s`` is the authoritative persisted deadline for that
    generation; readers must never recompute it (spec 3.5.5).
    """
    ensure_revision_table(con)
    if generation is None:
        rows = generation_rows(con, task_key)
        return _decode_gen(rows[-1]) if rows else None
    cur = con.execute(
        "SELECT " + ", ".join(_GEN_FIELDS) + " FROM preparation_generations"
        " WHERE task_key=? AND generation=?", (task_key, int(generation)))
    row = _row_dict(cur, cur.fetchone())
    return _decode_gen(row) if row is not None else None


def _decode_gen(row):
    rec = dict(row)
    rec["attempts_json"] = json.loads(rec.get("attempts_json") or "{}")
    return rec


def begin_generation(con: sqlite3.Connection, task_key: str,
                     preparation_id: str, generation: int, deadline_s,
                     *, attempts=0, retry_budget=3, commit_in: bool = True):
    """Persist a NEW preparation generation with its one fixed deadline.

    Re-beginning an existing generation is refused rather than silently
    re-stamping its deadline: the deadline belongs to the generation, not to
    whoever restarts (spec 3.5.3). An amendment goes through
    :func:`amend_generation` instead, which is owner-gated and linked.
    """
    ensure_revision_table(con)
    generation = int(generation)
    row = load_generation(con, task_key, generation)
    if row is not None:
        raise ValueError(
            "generation %d already persisted for %r; deadline fixed at %r"
            % (generation, task_key, row["deadline_s"]))
    now = time.time()
    con.execute(
        "INSERT INTO preparation_generations(task_key, generation,"
        " preparation_id, deadline_s, consumed_ms, attempts, status,"
        " retry_remaining, retry_consumed, amended_from, confirmed_by,"
        " policy_revision, attempts_json, created_at, updated_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (task_key, generation, str(preparation_id),
         None if deadline_s is None else float(deadline_s), 0.0, int(attempts),
         "preparing", int(retry_budget) - int(attempts), int(attempts),
         None, None, None, "{}", now, now))
    if commit_in:
        con.commit()
    return load_generation(con, task_key, generation)


def update_generation(con: sqlite3.Connection, task_key: str, generation: int,
                      *, consumed_ms=None, attempts=None, status=None,
                      attempts_json=None, commit_in: bool = True):
    """Record usage/attempts/exhaustion on an EXISTING generation only.

    Never touches ``deadline_s``. Missing generation is caller defect.
    """
    ensure_revision_table(con)
    generation = int(generation)
    sets, params = [], []
    if consumed_ms is not None:
        sets.append("consumed_ms=?")
        params.append(float(consumed_ms))
    if attempts is not None:
        sets.append("attempts=?")
        params.append(int(attempts))
        sets.append("retry_consumed=?")
        params.append(int(attempts))
        row = load_generation(con, task_key, generation)
        budget = (row["retry_remaining"] + row["retry_consumed"]
                  if row is not None else int(attempts))
        sets.append("retry_remaining=?")
        params.append(max(0, budget - int(attempts)))
    if status is not None:
        sets.append("status=?")
        params.append(str(status))
    if attempts_json is not None:
        sets.append("attempts_json=?")
        params.append(_canon(attempts_json))
    if not sets:
        return load_generation(con, task_key, generation)
    sets.append("updated_at=?")
    params.append(time.time())
    cur = con.execute(
        "UPDATE preparation_generations SET " + ", ".join(sets)
        + " WHERE task_key=? AND generation=?",
        params + [task_key, generation])
    if cur.rowcount == 0:
        raise ValueError("no persisted generation %d for %r"
                         % (generation, task_key))
    if commit_in:
        con.commit()
    return load_generation(con, task_key, generation)


def exhaust_generation(con: sqlite3.Connection, task_key: str, generation: int,
                       *, status="exhausted", commit_in: bool = True):
    """Mark a generation settled/exhausted in the persisted ledger.

    After this, ``load_cas_store`` restores the exhausted state, so a sweep
    or a retry spend after a restart finds settled work — never a fresh
    budget (the no-self-retry half of A56).
    """
    return update_generation(con, task_key, generation, status=status,
                             commit_in=commit_in)


def sync_usage(store, con: sqlite3.Connection, task_key: str,
               generation: int, *, commit_in: bool = True):
    """Flush cross-process-visible usage from a live D23 store to the ledger.

    ``retry`` is authoritative in the store (the in-process guard lives
    there); the ledger mirrors it for the next hydrate. Fence ``deadline_s``
    is written only when THIS generation has none yet — restarts after a
    hydrate carry the persisted stamp and never replace it.
    """
    ensure_revision_table(con)
    generation = int(generation)
    retry = store["retry"]
    consumed = int(retry["consumed"])
    sets = ["retry_remaining=?", "retry_consumed=?", "attempts=?",
            "updated_at=?"]
    params = [int(retry["remaining"]), consumed, consumed, time.time()]
    row = load_generation(con, task_key, generation)
    if row is not None and row["deadline_s"] is None:
        fence_deadline = store["fence"].get("deadline_s")
        if fence_deadline is not None:
            sets.append("deadline_s=?")
            params.append(float(fence_deadline))
    params += [task_key, generation]
    cur = con.execute(
        "UPDATE preparation_generations SET " + ", ".join(sets)
        + " WHERE task_key=? AND generation=?", params)
    if cur.rowcount == 0:
        raise ValueError("no persisted generation %d for %r"
                         % (generation, task_key))
    if commit_in:
        con.commit()
    return load_generation(con, task_key, generation)


def append_revision(con: sqlite3.Connection, task_key: str, revision: int,
                    decision: dict, mirrors: dict, reason: str,
                    evidence: dict) -> str:
    """Persist one envelope/decisionId/version-chain row beside the task row.

    Row key is the task+revision pair, so a recomputed decision that reuses
    its own decisionId under a new revision never collides.

    The primary key IS the cross-process compare-and-swap point (the in-memory
    store's RLock cannot span two SQLite connections): a losing racer's INSERT
    hits the unique constraint and is re-raised as the typed
    ``ObsoleteRevisionError`` this module's contract already documents. Found
    by the A36 real-DB test (GAP 3); the dict+RLock test could never reach it.
    """
    revision = int(revision)
    row_key = "%s#r%d" % (task_key, revision)
    decision = dict(decision or {})
    decision.setdefault("decisionId", row_key)
    try:
        con.execute(
            "INSERT INTO decision_revisions(decision_id, task_key, revision,"
            " envelope, mirrors, reason, evidence, created_at)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (row_key, task_key, int(revision), _canon(decision),
             _canon(mirrors or {}), reason or "",
             _canon(evidence or {}), time.time()))
    except sqlite3.IntegrityError:
        commit = _load_commit()
        try:
            con.rollback()
        except sqlite3.Error:
            pass
        head = latest_revision(con, task_key)
        actual = int(head["revision"]) if head is not None else revision
        # The loser CAS'd from revision-1 to revision; report that basis so the
        # typed message reads like a lost race (never "expected 2, head is 2").
        raise commit.ObsoleteRevisionError(
            max(revision - 1, 0), max(actual, revision))
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
        # Stamp the scope the reuse diff runs against (mirrors _recompute
        # below): an honest recompute that does not echo the scope dict must
        # still REUSE on an unchanged re-dispatch, per A35's first property.
        decision.setdefault("scope", dict(new_scope or {}))
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


def amend_generation(con: sqlite3.Connection, task_key: str, new_scope: dict,
                     recompute_fn, confirmation, reason: str, evidence=None,
                     generation: int | None = None, deadline_s=None,
                     commit_in: bool = True):
    """Owner-confirmed linked amendment (spec 3.5.4/3.5.5; A56 clause 3).

    A REAL owner confirmation — a D11 :class:`ExecutionPolicyRecord` that
    is ``owner_direct``, authenticated, and sourced from trusted context —
    is the only thing that opens a new generation. The new generation is
    LINKED to the prior one (``amended_from``) and the prior row keeps its
    usage/attempts (``consumed_ms``, ``attempts``, retry counters) exactly
    as they were: the amendment never erases what already happened.

    The new generation never inherits the prior generation's deadline (an
    exhausted prior generation would be born expired): the caller passes
    ``deadline_s`` for the new clock, or leaves it NULL until the new
    generation's start stamps it.

    Without a valid confirmation the call refuses with
    ``UnauthorizedAmendmentError`` and writes nothing. An amendment of an
    otherwise unchanged scope still requires the confirmation (it is the
    authorized explicit retry of settled work), while the decision chain
    keeps reusing the committed selection under the existing A35 semantics.
    """
    commit = _load_commit()
    ep = _load_execution_policy()
    ok, why = ep.validate_record(confirmation)
    if not ok:
        raise UnauthorizedAmendmentError(why)
    ensure_revision_table(con)
    prior = load_generation(con, task_key, generation) if generation is not None \
        else load_generation(con, task_key)
    if prior is None:
        raise ValueError("no prior generation to amend for %r" % (task_key,))
    confirmed_by = "%s:%s" % (confirmation.source_message_id,
                              confirmation.evidence_span)
    new_generation = int(prior["generation"]) + 1
    if load_generation(con, task_key, new_generation) is not None:
        raise ValueError("generation %d already exists for %r"
                         % (new_generation, task_key))
    # The decision chain first (CAS refused => nothing linked, nothing
    # amended): unchanged scope reuses the committed selection, changed
    # scope recommits with reason + evidence — both via the existing A35
    # ``redispatch``, never restated here.
    mode, revision, payload = redispatch(
        con, task_key, new_scope, recompute_fn, reason,
        dict(evidence or {}, amended_from_prior=True,
             confirmed_by=confirmed_by), commit_in=False)
    now = time.time()
    con.execute(
        "INSERT INTO preparation_generations(task_key, generation,"
        " preparation_id, deadline_s, consumed_ms, attempts, status,"
        " retry_remaining, retry_consumed, amended_from, confirmed_by,"
        " policy_revision, attempts_json, created_at, updated_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (task_key, new_generation, str(prior["preparation_id"]),
         None if deadline_s is None else float(deadline_s),
         0.0, 0, "preparing", int(prior["retry_remaining"]), 0,
         int(prior["generation"]), confirmed_by,
         int(confirmation.policy_revision), "{}", now, now))
    if commit_in:
        con.commit()
    return {
        "action": mode, "revision": revision,
        "generation": new_generation,
        "amended_from": int(prior["generation"]),
        "confirmed_by": confirmed_by,
        "prior_usage": {"consumed_ms": prior["consumed_ms"],
                        "attempts": prior["attempts"],
                        "retry_remaining": prior["retry_remaining"],
                        "retry_consumed": prior["retry_consumed"],
                        "status": prior["status"]},
        "decision": payload.get("decision"),
    }


class UnauthorizedAmendmentError(Exception):
    """No real owner confirmation: amendment refused, nothing written."""

    def __init__(self, reason):
        self.reason = reason
        super().__init__("unauthorized amendment: %s" % (reason,))
