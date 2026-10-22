"""Per-run transactional stage store. Directive sections 22, 24.4, 8.2, 8.5. Stdlib only.

Owns stage states, expected-version compare-and-set, worker leases, events.
Uses SQLite WAL; JSON checkpoints are projections, never authorities here.
Also owns typed saved-state documents (8.5): schema/version-tagged object and
list readers with typed errors, version migration through the canonical
request builder, non-generating remeasurement consumers, replay-safe decision
receipts and the pending continuation queue.

Every mutation validates against a fresh read, then writes with a single
UPDATE predicated on the row version (rowcount 0 = lost race). The write
itself is the atomic compare-and-set; pre-checks only pick error codes.

Never imports artifact_graph. Only state this module ever sets on an
upstream change is STALE (via mark_stale).
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from pathlib import Path

SCHEMA_VERSION = "1.0.0"
DB_SCHEMA_VERSION = 1

STATES = frozenset({
    "NOT_STARTED", "READY", "RUNNING", "WAITING_PROVIDER",
    "WAITING_APPROVAL", "QC", "FAILED_RETRYABLE", "FAILED_BLOCKED",
    "PARKED", "COMPLETE", "STALE",
})

# ponytail: fixed table, no per-campaign override; add when directive names one.
TRANSITIONS = {
    "NOT_STARTED": {"READY"},
    "READY": {"RUNNING", "PARKED"},
    "RUNNING": {"WAITING_PROVIDER", "WAITING_APPROVAL", "QC",
                "FAILED_RETRYABLE", "FAILED_BLOCKED", "PARKED", "COMPLETE"},
    "WAITING_PROVIDER": {"RUNNING", "FAILED_RETRYABLE", "FAILED_BLOCKED", "PARKED"},
    "WAITING_APPROVAL": {"RUNNING", "QC", "FAILED_BLOCKED", "PARKED"},
    "QC": {"COMPLETE", "FAILED_RETRYABLE", "FAILED_BLOCKED", "RUNNING"},
    "FAILED_RETRYABLE": {"READY", "RUNNING", "PARKED"},
    "FAILED_BLOCKED": {"READY", "PARKED"},
    "PARKED": {"READY"},
    "COMPLETE": set(),  # out only via mark_stale
    "STALE": {"READY", "RUNNING"},
}

CLAIMABLE = ("READY", "STALE", "FAILED_RETRYABLE", "RUNNING")
TERMINAL_OWNER_CLEAR = {"READY", "COMPLETE", "FAILED_RETRYABLE",
                        "FAILED_BLOCKED", "PARKED", "STALE"}
REASON_REQUIRED = {"FAILED_BLOCKED", "PARKED"}


class StoreError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _ro_connect(path, timeout=5):
    """Read-only connection that survives a WAL db whose -wal/-shm are gone.

    sqlite3.connect() is lazy: with the sidecars absent it returns a handle and
    only fails on the first statement, which surfaced as a false "corrupt:
    unable to open database file" on a healthy store. Force the real open, then
    retry on a private temp copy; the store's own file is never written here.
    """
    import atexit
    import shutil
    import tempfile

    path = os.path.abspath(str(path))
    try:
        con = sqlite3.connect("file:%s?mode=ro" % path, uri=True,
                              timeout=timeout)
        con.execute("PRAGMA schema_version").fetchone()
        return con
    except sqlite3.Error:
        try:
            con.close()                       # noqa: F821
        except Exception:                     # noqa: BLE001
            pass
    tmp = tempfile.mkdtemp(prefix="state-ro-")
    atexit.register(shutil.rmtree, tmp, True)
    base = os.path.basename(path)
    for name in (base, base + "-wal", base + "-shm"):
        src = os.path.join(os.path.dirname(path), name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(tmp, name))
    con = sqlite3.connect(os.path.join(tmp, base), timeout=timeout)
    con.execute("PRAGMA query_only=ON")
    return con


def needs_recovery(db_path):
    """(bool, str): True when the DB must be reconciled before use."""
    p = Path(db_path)
    if not p.exists():
        return False, "fresh"
    try:
        con = _ro_connect(p, timeout=5)
        try:
            row = con.execute("PRAGMA integrity_check").fetchone()
            if not row or row[0] != "ok":
                return True, "corrupt: integrity_check failed"
            tables = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"meta", "stages", "events"} <= tables:
                return True, "corrupt: missing tables"
            flag = con.execute(
                "SELECT v FROM meta WHERE k='db_version'").fetchone()
            if flag is None or flag[0] != str(DB_SCHEMA_VERSION):
                return True, "incompatible: schema drift, migrate first"
            return False, "clean"
        finally:
            con.close()
    except sqlite3.DatabaseError as e:
        return True, "corrupt: %s" % e


class Store:
    def __init__(self, db_path):
        bad, why = needs_recovery(db_path)
        if bad:
            raise StoreError("NEEDS_RECOVERY", why)
        self.path = Path(db_path)
        self.con = sqlite3.connect(self.path, timeout=30)
        self.con.execute("PRAGMA journal_mode=WAL")
        with self.con:
            self.con.executescript(
                "CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);"
                "CREATE TABLE IF NOT EXISTS stages(run_id TEXT, stage TEXT,"
                " state TEXT, version INTEGER, owner TEXT, lease_expires REAL,"
                " reason TEXT, updated_at REAL,"
                " PRIMARY KEY(run_id, stage));"
                "CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,"
                " run_id TEXT, stage TEXT, kind TEXT, detail TEXT, at REAL);"
                "CREATE TABLE IF NOT EXISTS receipts(cache_key TEXT PRIMARY"
                " KEY, run_id TEXT, stage TEXT, kind TEXT, audio_hash TEXT,"
                " evaluator_version TEXT, policy_version TEXT,"
                " plan_revision TEXT, parent_key TEXT, receipt TEXT,"
                " valid INTEGER, created_at REAL);"
                "CREATE TABLE IF NOT EXISTS decisions(run_id TEXT,"
                " ack_id TEXT, channel TEXT, decision TEXT, receipt TEXT,"
                " at REAL, PRIMARY KEY(run_id, ack_id));"
                "CREATE TABLE IF NOT EXISTS continuations(id TEXT PRIMARY KEY,"
                " run_id TEXT, stage TEXT, op TEXT, identity TEXT,"
                " request_digest TEXT, attempt_id TEXT, state TEXT,"
                " claimed_by TEXT, created_at REAL, updated_at REAL);"
                "CREATE UNIQUE INDEX IF NOT EXISTS cont_open_identity"
                " ON continuations(run_id, identity) WHERE state != 'done';"
                "INSERT OR IGNORE INTO meta(k, v)"
                " VALUES('db_version', '%d');" % DB_SCHEMA_VERSION)
        mode = self.con.execute("PRAGMA journal_mode").fetchone()[0]
        # memory: :memory: DBs report mode=memory and cannot do WAL;
        # nothing to crash-recover there, so accept it.
        if mode.lower() not in ("wal", "memory"):
            raise StoreError("NEEDS_RECOVERY",
                             "WAL unavailable (mode=%s)" % mode)

    def close(self):
        self.con.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- internals --
    def _row(self, run_id, stage):
        r = self.con.execute(
            "SELECT state, version, owner, lease_expires, reason"
            " FROM stages WHERE run_id=? AND stage=?",
            (run_id, stage)).fetchone()
        if r is None:
            raise StoreError("NOT_FOUND", "%s/%s" % (run_id, stage))
        return {"run_id": run_id, "stage": stage, "state": r[0],
                "version": r[1], "owner": r[2], "lease_expires": r[3],
                "reason": r[4]}

    def _event(self, run_id, stage, kind, detail=""):
        self.con.execute(
            "INSERT INTO events(id, run_id, stage, kind, detail, at)"
            " VALUES(?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, run_id, stage, kind, detail, time.time()))

    @staticmethod
    def _lease_live(row, now=None):
        now = time.time() if now is None else now
        return bool(row["owner"]) and row["lease_expires"] \
            and row["lease_expires"] > now

    def _cas(self, run_id, stage, version, set_clause, params):
        """Version-predicated write. Returns fresh row or raises."""
        cur = self.con.execute(
            "UPDATE stages SET %s WHERE run_id=? AND stage=? AND version=?"
            % set_clause, params + (run_id, stage, version))
        if cur.rowcount == 0:
            raise StoreError("VERSION_MISMATCH",
                             "lost race on %s/%s" % (run_id, stage))
        return self._row(run_id, stage)

    # -- API --
    def init_run(self, run_id, stages):
        with self.con:
            for s in stages:
                self.con.execute(
                    "INSERT OR IGNORE INTO stages(run_id, stage, state,"
                    " version, owner, lease_expires, reason, updated_at)"
                    " VALUES(?, ?, 'NOT_STARTED', 1, NULL, NULL, NULL, ?)",
                    (run_id, s, time.time()))
            self._event(run_id, "", "init", ",".join(stages))

    def get(self, run_id, stage):
        return self._row(run_id, stage)

    def claim(self, run_id, stage, owner, lease_s=300, expected_version=None):
        """Claim a stage. Re-claim on an expired lease takes over."""
        now = time.time()
        with self.con:
            row = self._row(run_id, stage)
            if expected_version is not None \
                    and expected_version != row["version"]:
                raise StoreError("VERSION_MISMATCH",
                                 "expected %s have %s"
                                 % (expected_version, row["version"]))
            if row["state"] not in CLAIMABLE:
                raise StoreError("ILLEGAL_TRANSITION",
                                 "claim from %s" % row["state"])
            if self._lease_live(row, now) and row["owner"] != owner:
                raise StoreError("NOT_OWNER",
                                 "lease held by %s" % row["owner"])
            fresh = self._cas(
                run_id, stage, row["version"],
                "state='RUNNING', version=version+1, owner=?,"
                " lease_expires=?, reason=NULL, updated_at=?",
                (owner, now + lease_s, now))
            self._event(run_id, stage, "claim", owner)
        return fresh

    def heartbeat(self, run_id, stage, owner, lease_s=300):
        now = time.time()
        with self.con:
            row = self._row(run_id, stage)
            if row["owner"] != owner:
                raise StoreError("NOT_OWNER",
                                 "lease held by %s" % row["owner"])
            if row["lease_expires"] and row["lease_expires"] <= now:
                raise StoreError("STALE_LEASE", "lease expired; re-claim")
            self.con.execute(
                "UPDATE stages SET lease_expires=? WHERE run_id=? AND stage=?",
                (now + lease_s, run_id, stage))
        return self._row(run_id, stage)

    def transition(self, run_id, stage, to_state, actor,
                   expected_version=None, reason=None):
        """Guarded transition: legal edge + lease held + version CAS."""
        if to_state not in STATES:
            raise StoreError("ILLEGAL_TRANSITION", "unknown %s" % to_state)
        if to_state == "STALE":
            raise StoreError("ILLEGAL_TRANSITION", "use mark_stale")
        if to_state in REASON_REQUIRED and not reason:
            raise StoreError("MISSING_REASON", "%s needs reason" % to_state)
        now = time.time()
        with self.con:
            row = self._row(run_id, stage)
            if expected_version is not None \
                    and expected_version != row["version"]:
                raise StoreError("VERSION_MISMATCH",
                                 "expected %s have %s"
                                 % (expected_version, row["version"]))
            if to_state not in TRANSITIONS[row["state"]]:
                raise StoreError("ILLEGAL_TRANSITION",
                                 "%s -> %s" % (row["state"], to_state))
            if self._lease_live(row, now) and row["owner"] != actor:
                raise StoreError("NOT_OWNER",
                                 "lease held by %s" % row["owner"])
            if row["owner"] == actor and row["lease_expires"] \
                    and row["lease_expires"] <= now:
                raise StoreError("STALE_LEASE", "lease expired; re-claim")
            owner, lease = row["owner"], row["lease_expires"]
            if to_state in TERMINAL_OWNER_CLEAR:
                owner, lease = None, None
            fresh = self._cas(
                run_id, stage, row["version"],
                "state=?, version=version+1, owner=?, lease_expires=?,"
                " reason=?, updated_at=?",
                (to_state, owner, lease, reason, now))
            self._event(run_id, stage, "transition",
                        "%s->%s %s" % (row["state"], to_state, reason or ""))
        return fresh

    def mark_stale(self, run_id, stage, reason):
        """Only STALE this module ever sets on upstream change."""
        if not reason:
            raise StoreError("MISSING_REASON", "stale needs reason")
        with self.con:
            row = self._row(run_id, stage)
            if row["state"] == "STALE":
                return row
            fresh = self._cas(
                run_id, stage, row["version"],
                "state='STALE', version=version+1, owner=NULL,"
                " lease_expires=NULL, reason=?, updated_at=?",
                (reason, time.time()))
            self._event(run_id, stage, "stale", reason)
        return fresh

    def events(self, run_id):
        return self.con.execute(
            "SELECT stage, kind, detail, at FROM events WHERE run_id=?"
            " ORDER BY at", (run_id,)).fetchall()

    # -- saved-state receipts (section 8.5) --
    def save_receipt(self, run_id, stage, kind, audio_hash, evaluator_version,
                     policy_version, plan_revision, receipt, parent_key=None):
        """Idempotent receipt write keyed by the 8.5 cache key. An existing
        row for the same key is returned untouched: replaying a measurement
        never redoes work or buys anything."""
        key = cache_key(kind, audio_hash, evaluator_version, policy_version,
                        plan_revision)
        with self.con:
            row = self.con.execute(
                "SELECT receipt, valid FROM receipts WHERE cache_key=?",
                (key,)).fetchone()
            if row is not None:
                return {"cache_key": key, "receipt": json.loads(row[0]),
                        "created": False, "valid": bool(row[1])}
            self.con.execute(
                "INSERT INTO receipts(cache_key, run_id, stage, kind,"
                " audio_hash, evaluator_version, policy_version,"
                " plan_revision, parent_key, receipt, valid, created_at)"
                " VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
                (key, run_id, stage, kind, audio_hash, evaluator_version,
                 policy_version, plan_revision, parent_key,
                 json.dumps(receipt, sort_keys=True), time.time()))
            self._event(run_id, stage, "receipt-save", "%s %s" % (kind, key))
        return {"cache_key": key, "receipt": receipt, "created": True,
                "valid": True}

    def get_receipt(self, kind, audio_hash, evaluator_version,
                    policy_version, plan_revision):
        """The valid receipt for this cache key, or None. Reuse valid cached
        analysis first (8.5); an invalidated receipt reads as absent."""
        key = cache_key(kind, audio_hash, evaluator_version, policy_version,
                        plan_revision)
        row = self.con.execute(
            "SELECT receipt FROM receipts WHERE cache_key=? AND valid=1",
            (key,)).fetchone()
        return json.loads(row[0]) if row is not None else None

    def invalidate_receipts(self, run_id, audio_hash=None,
                            evaluator_version=None, policy_version=None,
                            plan_revision=None):
        """8.5: invalidate ONLY obsolete receipts and their affected
        descendants. Unrelated approvals and valid media survive. Media is
        recorded audio, so only an audio_hash change can obsolete it -- an
        evaluator, policy or approved-plan revision never does. Decision
        receipts (message/webhook acks) are never touched by this path."""
        if not any((audio_hash, evaluator_version, policy_version,
                    plan_revision)):
            raise MalformedRecordError(
                "invalidate_receipts needs at least one current component:"
                " audio_hash, evaluator_version, policy_version or"
                " approved_plan_revision")
        rows = [_receipt_row(r) for r in self.con.execute(
            "SELECT cache_key, kind, audio_hash, evaluator_version,"
            " policy_version, plan_revision, parent_key, valid FROM receipts"
            " WHERE run_id=?", (run_id,))]
        direct = {r["cache_key"] for r in rows
                  if _receipt_obsolete(r, audio_hash, evaluator_version,
                                       policy_version, plan_revision)}
        kids = {}
        for r in rows:
            if r["parent_key"]:
                kids.setdefault(r["parent_key"], []).append(r["cache_key"])
        descendants, stack = set(), list(direct)
        while stack:
            for child in kids.get(stack.pop(), ()):
                if child not in direct and child not in descendants:
                    descendants.add(child)
                    stack.append(child)
        with self.con:
            for key in direct | descendants:
                self.con.execute(
                    "UPDATE receipts SET valid=0 WHERE cache_key=?", (key,))
            if direct or descendants:
                self._event(run_id, "", "receipt-invalidate",
                            ",".join(sorted(direct | descendants)))
        kept = [r["cache_key"] for r in rows
                if r["valid"] == 1 and r["cache_key"] not in direct
                and r["cache_key"] not in descendants]
        return {"invalidated": sorted(direct),
                "descendants": sorted(descendants), "kept": kept}

    # -- replay-safe decisions and continuation queue (section 8.2) --
    def enqueue_continuation(self, run_id, stage, op, request_digest=None,
                             attempt_id=None):
        """ONE open continuation per (run_id, identity). A replay gets the
        existing row back with its ORIGINAL attempt_id -- never a second
        continuation and never a duplicate paid attempt."""
        identity = request_digest or "op:%s:%s" % (stage, op)
        with self.con:
            return self._enqueue_locked(run_id, stage, op, identity,
                                        request_digest, attempt_id)

    def _enqueue_locked(self, run_id, stage, op, identity, request_digest,
                        attempt_id):
        row = self.con.execute(
            "%s WHERE run_id=? AND identity=? AND state != 'done'"
            % _CONT_SELECT, (run_id, identity)).fetchone()
        if row is not None:
            return {"created": False, "continuation": _cont_dict(row)}
        now = time.time()
        try:
            self.con.execute(
                "INSERT INTO continuations(id, run_id, stage, op, identity,"
                " request_digest, attempt_id, state, claimed_by, created_at,"
                " updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, 'pending', NULL,"
                " ?, ?)",
                (uuid.uuid4().hex, run_id, stage, op, identity,
                 request_digest, attempt_id, now, now))
        except sqlite3.IntegrityError:
            row = self.con.execute(
                "%s WHERE run_id=? AND identity=? AND state != 'done'"
                % _CONT_SELECT, (run_id, identity)).fetchone()
            return {"created": False, "continuation": _cont_dict(row)}
        self._event(run_id, stage, "continuation-enqueue", identity)
        row = self.con.execute(
            "%s WHERE run_id=? AND identity=? AND state != 'done'"
            % _CONT_SELECT, (run_id, identity)).fetchone()
        return {"created": True, "continuation": _cont_dict(row)}

    def _continuation_for(self, run_id, request_digest, stage, op):
        identity = request_digest or "op:%s:%s" % (stage, op)
        row = self.con.execute(
            "%s WHERE run_id=? AND identity=? AND state != 'done'"
            % _CONT_SELECT, (run_id, identity)).fetchone()
        return _cont_dict(row) if row is not None else None

    def scan_pending_continuations(self, run_id=None):
        """Post-restart queue scan (8.2): the pending continuation queue,
        one row per work item, for one run or all runs. Claimed-but-undone
        rows are lease business (claim/transition), not queue business."""
        q = "%s WHERE state='pending'" % _CONT_SELECT
        args = ()
        if run_id is not None:
            q += " AND run_id=?"
            args = (run_id,)
        q += " ORDER BY created_at"
        return [_cont_dict(r) for r in self.con.execute(q, args)]

    def resume_continuations(self, run_id, worker, op=None):
        """Resume the SAME run after a restart: claim each pending
        continuation exactly once (pending -> claimed compare-and-set).
        One continuation per work item; the claimed rows keep their original
        attempt_id, so a restart never duplicates a paid attempt."""
        claimed = []
        with self.con:
            for cont in self.scan_pending_continuations(run_id):
                if op is not None and cont["op"] != op:
                    continue
                cur = self.con.execute(
                    "UPDATE continuations SET state='claimed', claimed_by=?,"
                    " updated_at=? WHERE id=? AND state='pending'",
                    (worker, time.time(), cont["id"]))
                if cur.rowcount == 1:
                    cont["state"] = "claimed"
                    cont["claimed_by"] = worker
                    claimed.append(cont)
                    self._event(run_id, cont["stage"], "continuation-resume",
                                cont["identity"])
        return claimed

    def record_decision(self, run_id, ack_id, decision, channel="message",
                        stage="", op="", request_digest=None,
                        attempt_id=None):
        """Append a user/message decision and enqueue its next action
        atomically (8.2). A REPLAYED message acknowledges the EXISTING
        decision and does no duplicate work: same receipt, the same single
        continuation, the same attempt_id, no second decision row."""
        if not isinstance(ack_id, str) or not ack_id:
            raise MalformedRecordError(
                "record_decision needs a non-empty ack_id", path="ack_id")
        if not isinstance(decision, dict):
            raise MalformedRecordError(
                "record_decision needs a decision object, got %s"
                % type(decision).__name__, path="decision")
        with self.con:
            cur = self.con.execute(
                "INSERT OR IGNORE INTO decisions(run_id, ack_id, channel,"
                " decision, receipt, at) VALUES(?, ?, ?, ?, '', ?)",
                (run_id, ack_id, channel,
                 json.dumps(decision, sort_keys=True), time.time()))
            if cur.rowcount == 0:
                row = self.con.execute(
                    "SELECT receipt FROM decisions WHERE run_id=? AND ack_id=?",
                    (run_id, ack_id)).fetchone()
                self._event(run_id, stage, "decision-ack", ack_id)
                return {"duplicate": True, "receipt": json.loads(row[0]),
                        "continuation": self._continuation_for(
                            run_id, request_digest, stage, op)}
            cont = None
            if stage:
                got = self._enqueue_locked(
                    run_id, stage, op or "resume",
                    request_digest or "op:%s:%s" % (stage, op or "resume"),
                    request_digest, attempt_id)
                cont = got["continuation"]
            receipt = {
                "ack_id": ack_id, "channel": channel, "decision": decision,
                "continuation_id": (cont or {}).get("id"),
                "attempt_id": (cont or {}).get("attempt_id", attempt_id),
                "request_digest": request_digest}
            self.con.execute(
                "UPDATE decisions SET receipt=? WHERE run_id=? AND ack_id=?",
                (json.dumps(receipt, sort_keys=True), run_id, ack_id))
            self._event(run_id, stage, "decision", ack_id)
            return {"duplicate": False, "receipt": receipt,
                    "continuation": cont}

    def acknowledge_webhook(self, run_id, delivery_id, event_kind="",
                            decision=None, stage="", op="",
                            request_digest=None, attempt_id=None):
        """A replayed webhook delivery acknowledges the existing decision and
        does no duplicate work (8.2): idempotent on (run_id, delivery_id)."""
        return self.record_decision(
            run_id, "webhook:%s" % delivery_id,
            decision if decision is not None else {"event_kind": event_kind},
            channel="webhook", stage=stage, op=op,
            request_digest=request_digest, attempt_id=attempt_id)

    # -- non-generating operations (section 8.5) --
    def non_generating_op(self, op, **kw):
        """The state-layer non-generating operations contract: validate,
        migrate, remeasure, rejudge, reconcile. None of these can request
        music generation -- request_generation() refuses outright and the
        measure/judge callables receive saved state only. Any paid analysis
        call is the caller's to authorize and ledger separately."""
        if op not in NON_GENERATING_OPS:
            raise StoreError("UNKNOWN_OP",
                             "%r is not a non-generating op (%s)"
                             % (op, ", ".join(NON_GENERATING_OPS)))
        return getattr(self, "_nongen_" + op)(**kw)

    def _nongen_validate(self, kind, doc):
        out = _read(kind, doc, "list" if kind == DOC_QC_RECORDS else "object")
        return {"ok": True, "kind": kind, "version": out["version"],
                "source_version": out["_source_version"]}

    def _nongen_migrate(self, kind, doc):
        return canonical_request_builder(kind, doc)

    def _nongen_remeasure(self, run_id, stage, audio_hash, evaluator_version,
                          policy_version, plan_revision, measure,
                          provenance=None):
        """Remeasure SAVED audio under SAVED provider provenance (8.5). No
        new music-generation request happens here by construction: `measure`
        analyses existing audio, and request_generation() always refuses."""
        hit = self.get_receipt("measurement", audio_hash, evaluator_version,
                               policy_version, plan_revision)
        if hit is not None:
            return {"cached": True, "receipt": hit}
        data = measure(audio_hash, evaluator_version, provenance or {})
        saved = self.save_receipt(
            run_id, stage, "measurement", audio_hash, evaluator_version,
            policy_version, plan_revision,
            {"measurement": data, "provenance": provenance or {}})
        return {"cached": False, "receipt": saved["receipt"]}

    def _nongen_rejudge(self, run_id, stage, audio_hash, evaluator_version,
                        policy_version, plan_revision, judge):
        """Rejudge from SAVED measurements (8.5): no provider call of any
        kind, no generation. The acceptance receipt descends from the exact
        measurement receipt it judged."""
        key = cache_key("measurement", audio_hash, evaluator_version,
                        policy_version, plan_revision)
        row = self.con.execute(
            "SELECT receipt FROM receipts WHERE cache_key=? AND valid=1",
            (key,)).fetchone()
        if row is None:
            raise StoreError("MISSING_MEASUREMENT",
                             "no valid measurement receipt %s; remeasure "
                             "first" % key)
        verdict = judge(json.loads(row[0]))
        saved = self.save_receipt(
            run_id, stage, "acceptance", audio_hash, evaluator_version,
            policy_version, plan_revision,
            {"verdict": verdict, "measurement_key": key}, parent_key=key)
        return {"cached": not saved["created"], "receipt": saved["receipt"]}

    def _nongen_reconcile(self, run_id, audio_hash=None,
                          evaluator_version=None, policy_version=None,
                          plan_revision=None):
        """Read-only reconcile of this layer's own durable facts (8.2):
        the pending continuation queue, decision count, and which receipts
        the given current components would obsolete. Mutates nothing."""
        pending = self.scan_pending_continuations(run_id)
        rows = [_receipt_row(r) for r in self.con.execute(
            "SELECT cache_key, kind, audio_hash, evaluator_version,"
            " policy_version, plan_revision, parent_key, valid FROM receipts"
            " WHERE run_id=?", (run_id,))]
        would_die = sorted(
            r["cache_key"] for r in rows
            if _receipt_obsolete(r, audio_hash, evaluator_version,
                                 policy_version, plan_revision))
        kept = sorted(r["cache_key"] for r in rows
                      if r["valid"] == 1 and r["cache_key"] not in would_die)
        count = self.con.execute(
            "SELECT COUNT(*) FROM decisions WHERE run_id=?",
            (run_id,)).fetchone()[0]
        return {"run_id": run_id, "pending_continuations": pending,
                "obsolete_receipts": would_die, "kept_receipts": kept,
                "decision_count": count}


_CONT_COLS = ("id", "run_id", "stage", "op", "identity", "request_digest",
              "attempt_id", "state", "claimed_by", "created_at")

_CONT_SELECT = ("SELECT id, run_id, stage, op, identity, request_digest,"
                " attempt_id, state, claimed_by, created_at"
                " FROM continuations")

_RECEIPT_COLS = ("cache_key", "kind", "audio_hash", "evaluator_version",
                 "policy_version", "plan_revision", "parent_key", "valid")


def _cont_dict(row):
    return dict(zip(_CONT_COLS, row))


def _receipt_row(row):
    return dict(zip(_RECEIPT_COLS, row))


def _receipt_obsolete(row, audio_hash, evaluator_version, policy_version,
                      plan_revision):
    """True when the current components DIRECTLY obsolete this valid
    receipt (8.5). Only measurement and acceptance receipts age out on
    component drift; approvals die only as affected descendants (unrelated
    approvals survive), and media is recorded audio, obsoleted by an
    audio_hash change alone -- never by evaluator, policy or plan revisions."""
    if row["valid"] != 1:
        return False
    if row["kind"] == "media":
        return audio_hash is not None and row["audio_hash"] != audio_hash
    if row["kind"] not in ("measurement", "acceptance"):
        return False
    return ((audio_hash is not None and row["audio_hash"] != audio_hash)
            or (evaluator_version is not None
                and row["evaluator_version"] != evaluator_version)
            or (policy_version is not None
                and row["policy_version"] != policy_version)
            or (plan_revision is not None
                and row["plan_revision"] != plan_revision))


# ===========================================================================
# Typed saved-state documents (section 8.5; findings D26, D33).
#
# Five typed OBJECT documents plus a QC-record LIST, each carrying
# schema/version tags validated at the boundary that consumes it. The
# dict-only readers refuse lists and the list-only reader refuses dicts: a
# dict-only helper must never be asked to read a list of QC records (D33).
# Wrong object at a boundary is a typed error -- no silent migration and no
# tag stripping. Version migration goes through canonical_request_builder
# only (D26): it preserves performance tags and approved meaning exactly and
# reports every semantic difference requiring review. An internal recipe that
# lacks provider-envelope fields is NOT obsolete -- each kind is validated
# against its own contract, never another kind's.
# ===========================================================================

DOC_RECIPE_INPUT = "skill75.recipe_input"
DOC_APPROVED_LYRIC_SHEET = "skill75.approved_lyric_sheet"
DOC_PROVIDER_ENVELOPE = "skill75.provider_envelope"
DOC_LANE_PLAN = "skill75.lane_plan"
DOC_EXECUTION_RESULT = "skill75.execution_result"
DOC_QC_RECORDS = "skill75.qc_records"          # LIST document

OBJECT_KINDS = (DOC_RECIPE_INPUT, DOC_APPROVED_LYRIC_SHEET,
                DOC_PROVIDER_ENVELOPE, DOC_LANE_PLAN, DOC_EXECUTION_RESULT)
DOC_KINDS = OBJECT_KINDS + (DOC_QC_RECORDS,)

CURRENT_VERSION = 2
SUPPORTED_VERSIONS = (1, CURRENT_VERSION)

NON_GENERATING_OPS = ("validate", "migrate", "remeasure", "rejudge",
                      "reconcile")

_GENERATION_CALLS = 0


def request_generation(*_args, **_kw):
    """The state layer NEVER generates music (8.5). Any non-generating
    operation that reaches for generation hits this wall and fails typed,
    so remeasure/rejudge paths provably make zero generation calls."""
    global _GENERATION_CALLS
    _GENERATION_CALLS += 1
    raise GenerationForbiddenError(
        "state_store is a non-generating layer: remeasure/rejudge use saved "
        "audio and saved measurements only; music generation is never "
        "requested here")


def generation_calls():
    """Refused generation attempts seen by this module. The remeasure and
    rejudge paths must leave this at 0."""
    return _GENERATION_CALLS


class StateShapeError(StoreError):
    """Typed saved-state error. `kind` names the boundary, `path` the field."""

    def __init__(self, code, message, kind=None, path=None):
        super().__init__(code, message)
        self.kind = kind
        self.path = path


class WrongShapeError(StateShapeError):
    def __init__(self, message, kind=None, path=None):
        super().__init__("WRONG_SHAPE", message, kind, path)


class WrongKindError(StateShapeError):
    def __init__(self, message, kind=None, path=None):
        super().__init__("WRONG_KIND", message, kind, path)


class MalformedRecordError(StateShapeError):
    def __init__(self, message, kind=None, path=None):
        super().__init__("MALFORMED_RECORD", message, kind, path)


class UnknownFieldError(StateShapeError):
    def __init__(self, message, kind=None, path=None):
        super().__init__("UNKNOWN_FIELD", message, kind, path)


class UnsupportedVersionError(StateShapeError):
    def __init__(self, message, kind=None, path=None):
        super().__init__("UNSUPPORTED_VERSION", message, kind, path)


class SemanticLossError(StateShapeError):
    def __init__(self, message, kind=None, path=None):
        super().__init__("SEMANTIC_LOSS", message, kind, path)


class GenerationForbiddenError(StoreError):
    def __init__(self, message):
        super().__init__("GENERATION_FORBIDDEN", message)


def _is_str(v):
    return isinstance(v, str)


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _is_strlist(v):
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def _is_list(v):
    return isinstance(v, list)


def _is_opt_str(v):
    return v is None or isinstance(v, str)


def _is_dict(v):
    return isinstance(v, dict)


def _is_counts(v):
    return (isinstance(v, dict)
            and all(isinstance(k, str) and _is_int(x)
                    for k, x in v.items()))


# kind -> version -> (required, optional) field predicates. The QC list spec
# describes ONE record; the wrapper is checked at the boundary.
_SPECS = {
    DOC_RECIPE_INPUT: {
        1: ({"run_id": _is_str, "style": _is_str, "seconds": _is_num,
             "tags": _is_strlist, "lyrics": _is_str},
            {"digest": _is_str}),
        2: ({"run_id": _is_str, "style_id": _is_str, "length_s": _is_num,
             "performance_tags": _is_strlist, "approved_lyrics": _is_str},
            {"request_digest": _is_str}),
    },
    DOC_APPROVED_LYRIC_SHEET: {
        1: ({"run_id": _is_str, "approval_id": _is_str,
             "approved_at": _is_str, "text": _is_str},
            {"meaning_digest": _is_str}),
        2: ({"run_id": _is_str, "approval_id": _is_str,
             "approved_at": _is_str, "lines": _is_strlist},
            {"meaning_digest": _is_str}),
    },
    DOC_PROVIDER_ENVELOPE: {
        1: ({"run_id": _is_str, "provider": _is_str, "task_id": _is_str,
             "status": _is_str, "takes": _is_list},
            {"usage": _is_dict}),
        2: ({"run_id": _is_str, "provider": _is_str, "task_id": _is_str,
             "status": _is_str, "takes": _is_list},
            {"usage": _is_dict}),
    },
    DOC_LANE_PLAN: {
        1: ({"run_id": _is_str, "song_length_s": _is_num, "lanes": _is_int,
             "lanes_detail": _is_list},
            {"lane_share_per_10s": _is_num}),
        2: ({"run_id": _is_str, "song_length_s": _is_num, "lanes": _is_int,
             "lanes_detail": _is_list},
            {"lane_share_per_10s": _is_num,
             "shared_steps_before": _is_strlist,
             "shared_steps_after": _is_strlist}),
    },
    DOC_EXECUTION_RESULT: {
        1: ({"run_id": _is_str, "stage": _is_str, "outcome": _is_str,
             "attempt": _is_str},
            {"reason_code": _is_str, "receipt_id": _is_str}),
        2: ({"run_id": _is_str, "stage": _is_str, "outcome": _is_str,
             "attempt_id": _is_str},
            {"reason_code": _is_str, "receipt_id": _is_str,
             "counts": _is_counts}),
    },
    DOC_QC_RECORDS: {
        1: ({"check_id": _is_str, "category": _is_str,
             "artifact_hash": _is_str, "evaluator_version": _is_str,
             "result": _is_str, "severity": _is_str},
            {"confidence": _is_num}),
        2: ({"check_id": _is_str, "category": _is_str,
             "artifact_hash": _is_str, "plan_revision": _is_opt_str,
             "evaluator_version": _is_str, "evidence_source": _is_opt_str,
             "applicability": _is_opt_str, "measured": _is_str,
             "severity": _is_str},
            {"confidence": _is_num}),
    },
}

_TAKE_SPECS = {
    1: ({"take_id": _is_str, "path": _is_str}, {"audio_hash": _is_opt_str}),
    2: ({"take_id": _is_str, "audio_path": _is_str},
        {"audio_hash": _is_opt_str}),
}

_LANE_SPECS = {
    1: ({"lane_index": _is_int, "song_start": _is_num, "song_end": _is_num,
         "shots": _is_strlist}, {}),
    2: ({"lane_index": _is_int, "song_start": _is_num, "song_end": _is_num,
         "shot_ids": _is_strlist}, {}),
}

# kind -> (nested field, version -> (required, optional) per record)
_NESTED = {
    DOC_PROVIDER_ENVELOPE: ("takes", _TAKE_SPECS),
    DOC_LANE_PLAN: ("lanes_detail", _LANE_SPECS),
}


def _check_fields(kind, payload, req, opt, path=""):
    if not isinstance(payload, dict):
        raise MalformedRecordError(
            "%s: record must be an object, got %s"
            % (kind, type(payload).__name__), kind, path)
    allowed = set(req) | set(opt)
    for name in payload:
        if name not in allowed:
            raise UnknownFieldError(
                "%s: unknown field %r (allowed: %s)"
                % (kind, name, ", ".join(sorted(allowed))), kind, path + name)
    for name, ok in req.items():
        if name not in payload:
            raise MalformedRecordError(
                "%s: missing required field %r" % (kind, name), kind,
                path + name)
        if not ok(payload[name]):
            raise MalformedRecordError(
                "%s: field %r has the wrong shape: %r"
                % (kind, name, payload[name]), kind, path + name)
    for name, ok in opt.items():
        if name in payload and not ok(payload[name]):
            raise MalformedRecordError(
                "%s: field %r has the wrong shape: %r"
                % (kind, name, payload[name]), kind, path + name)


def _check_nested(kind, payload, version):
    entry = _NESTED.get(kind)
    if entry is None:
        return
    field, specs = entry
    req, opt = specs[version]
    for i, rec in enumerate(payload.get(field) or []):
        _check_fields(kind, rec, req, opt, "%s[%d]." % (field, i))


def _tag_version(kind, doc):
    if "version" not in doc:
        raise MalformedRecordError(
            "%s document carries no version tag" % kind, kind, "version")
    v = doc["version"]
    if not isinstance(v, int) or isinstance(v, bool):
        raise MalformedRecordError(
            "%s version tag must be an int, got %r" % (kind, v), kind,
            "version")
    if v not in SUPPORTED_VERSIONS:
        raise UnsupportedVersionError(
            "%s version %d is not supported (supported: %s); saved state "
            "this new needs a matching skill version"
            % (kind, v, ", ".join(str(x) for x in SUPPORTED_VERSIONS)),
            kind, "version")
    return v


def _boundary(kind, doc, want):
    """Shape + schema/version tag validation at the consuming boundary.
    Returns (payload, source_version). Never migrates across kinds."""
    if kind not in DOC_KINDS:
        raise StoreError("UNKNOWN_KIND", "unknown saved-state kind %r"
                         % (kind,))
    if want == "list":
        if isinstance(doc, list):
            return {"records": list(doc)}, CURRENT_VERSION
        if not isinstance(doc, dict):
            raise WrongShapeError(
                "%s records must be a list or a tagged wrapper, got %s"
                % (kind, type(doc).__name__), kind)
        if "schema" not in doc:
            raise WrongShapeError(
                "dict-only document handed where a %s record list is "
                "required: a dict-only helper must never be asked to read a "
                "list of QC records" % kind, kind)
        if doc["schema"] != kind:
            raise WrongKindError(
                "expected %s at this boundary, got %r: wrong object at the "
                "boundary (no silent migration, no tag stripping)"
                % (kind, doc["schema"]), kind, "schema")
        for name in doc:
            if name not in ("schema", "version", "records"):
                raise UnknownFieldError(
                    "%s wrapper: unknown field %r" % (kind, name), kind,
                    name)
        return {"records": doc.get("records")}, _tag_version(kind, doc)
    if isinstance(doc, list):
        raise WrongShapeError(
            "a list was handed to the dict-only %s reader: a dict-only "
            "helper must never be asked to read a list of QC records"
            % kind, kind)
    if not isinstance(doc, dict):
        raise WrongShapeError(
            "%s document must be an object, got %s"
            % (kind, type(doc).__name__), kind)
    if "schema" not in doc:
        raise MalformedRecordError(
            "%s document carries no schema tag" % kind, kind, "schema")
    if doc["schema"] != kind:
        raise WrongKindError(
            "expected %s at this boundary, got %r: wrong object at the "
            "boundary (no silent migration, no tag stripping)"
            % (kind, doc["schema"]), kind, "schema")
    version = _tag_version(kind, doc)
    payload = {k: v for k, v in doc.items() if k not in ("schema", "version")}
    return payload, version


def _read(kind, doc, want):
    payload, src = _boundary(kind, doc, want)
    req, opt = _SPECS[kind][src]
    if want == "list":
        records = payload.get("records")
        if not isinstance(records, list):
            raise WrongShapeError(
                "%s: 'records' must be a list of QC records, got %s"
                % (kind, type(records).__name__), kind, "records")
        for i, rec in enumerate(records):
            _check_fields(kind, rec, req, opt, "records[%d]." % i)
    else:
        _check_fields(kind, payload, req, opt)
        _check_nested(kind, payload, src)
    diffs = []
    if src != CURRENT_VERSION:
        before = payload if want == "object" else dict(payload)
        payload, diffs = _UPGRADES[(kind, src)](payload)
        verify_preserved(kind, before, payload)
        req2, opt2 = _SPECS[kind][CURRENT_VERSION]
        if want == "object":
            _check_fields(kind, payload, req2, opt2)
        else:
            for i, rec in enumerate(payload["records"]):
                _check_fields(kind, rec, req2, opt2, "records[%d]." % i)
        _check_nested(kind, payload, CURRENT_VERSION)
    if want == "list":
        out = {"schema": kind, "version": CURRENT_VERSION,
               "records": [dict(r) for r in payload["records"]]}
    else:
        out = {"schema": kind, "version": CURRENT_VERSION}
        out.update(payload)
    out["_source_version"] = src
    out["_migrated"] = src != CURRENT_VERSION
    out["_semantic_differences"] = diffs
    return out


def read_object(kind, doc):
    """Dict-only saved-state reader boundary (D33). Refuses the QC-record
    LIST kind outright: a dict-only helper must never be asked to read a
    list of QC records."""
    if kind == DOC_QC_RECORDS:
        raise WrongShapeError(
            "read_object() is the dict-only helper and must never be asked "
            "to read a list of QC records; use read_qc_records()", kind)
    return _read(kind, doc, "object")


def read_list(kind, doc):
    """List-only saved-state reader boundary (D33). Refuses the object
    kinds outright."""
    if kind != DOC_QC_RECORDS:
        raise WrongShapeError(
            "read_list() is the list-only helper and never reads a single "
            "%s object; use the kind reader" % kind, kind)
    return _read(kind, doc, "list")


def read_recipe_input(doc):
    """Typed recipe-input reader (8.5). Validated here, at the boundary
    that consumes a recipe -- never against provider-envelope fields."""
    return read_object(DOC_RECIPE_INPUT, doc)


def read_approved_lyric_sheet(doc):
    """Typed approved-lyric-sheet reader (8.5): the approved meaning."""
    return read_object(DOC_APPROVED_LYRIC_SHEET, doc)


def read_provider_envelope(doc):
    """Typed provider-envelope reader (8.5): provider task provenance."""
    return read_object(DOC_PROVIDER_ENVELOPE, doc)


def read_lane_plan(doc):
    """Typed lane-plan reader (8.5)."""
    return read_object(DOC_LANE_PLAN, doc)


def read_execution_result(doc):
    """Typed execution-result reader (8.5)."""
    return read_object(DOC_EXECUTION_RESULT, doc)


def read_qc_records(doc):
    """Typed QC-record LIST reader (8.5): valid lists, empty lists and
    every malformed member fail or pass with explicit typed errors."""
    return read_list(DOC_QC_RECORDS, doc)


# -- version migration through the canonical request builder (D26) --

def _upgrade_recipe_v1(p):
    out = {"run_id": p["run_id"], "style_id": p["style"],
           "length_s": p["seconds"], "performance_tags": list(p["tags"]),
           "approved_lyrics": p["lyrics"]}
    diffs = []
    if "digest" in p:
        out["request_digest"] = p["digest"]
    else:
        diffs.append({
            "code": "REQUEST_DIGEST_DERIVED", "path": "request_digest",
            "detail": "v1 recipe input carries no request_digest; the "
                      "canonical builder derives it and a reviewer must "
                      "confirm it identifies the same approved request"})
    if p["style"] != p["style"].strip().lower():
        diffs.append({
            "code": "STYLE_HINT_NOT_CANONICAL", "path": "style_id",
            "detail": "v1 free-text style %r carried verbatim into style_id; "
                      "confirm it names the intended canonical style"
                      % (p["style"],)})
    return out, diffs


def _upgrade_sheet_v1(p):
    out = {"run_id": p["run_id"], "approval_id": p["approval_id"],
           "approved_at": p["approved_at"], "lines": p["text"].split("\n")}
    if "meaning_digest" in p:
        out["meaning_digest"] = p["meaning_digest"]
    return out, []


def _upgrade_envelope_v1(p):
    takes, missing = [], []
    for t in p["takes"]:
        rec = {"take_id": t["take_id"], "audio_path": t["path"],
               "audio_hash": t.get("audio_hash")}
        if rec["audio_hash"] is None:
            missing.append(t["take_id"])
        takes.append(rec)
    out = dict(p)
    out["takes"] = takes
    diffs = []
    if missing:
        diffs.append({
            "code": "AUDIO_HASH_UNKNOWN", "path": "takes",
            "detail": "v1 provider envelope takes %s carry no audio_hash; it "
                      "remains unknown until recomputed from saved audio "
                      "before remeasurement" % ", ".join(missing)})
    return out, diffs


def _upgrade_lane_v1(p):
    out = dict(p)
    out["lanes_detail"] = [
        {"lane_index": ln["lane_index"], "song_start": ln["song_start"],
         "song_end": ln["song_end"], "shot_ids": list(ln["shots"])}
        for ln in p["lanes_detail"]]
    return out, []


def _upgrade_execution_v1(p):
    out = {"run_id": p["run_id"], "stage": p["stage"],
           "outcome": p["outcome"], "attempt_id": p["attempt"]}
    for k in ("reason_code", "receipt_id"):
        if k in p:
            out[k] = p[k]
    diffs = [{
        "code": "COUNTS_RESERVED_UNKNOWN", "path": "counts",
        "detail": "v1 execution result carries no attempt counts; "
                  "planned/submitted/acknowledged/billed counts remain "
                  "reserved-unknown, never asserted"}]
    return out, diffs


def _upgrade_qc_v1(p):
    out = []
    for r in p["records"]:
        rec = {"check_id": r["check_id"], "category": r["category"],
               "artifact_hash": r["artifact_hash"], "plan_revision": None,
               "evaluator_version": r["evaluator_version"],
               "evidence_source": None, "applicability": None,
               "measured": r["result"], "severity": r["severity"]}
        if "confidence" in r:
            rec["confidence"] = r["confidence"]
        out.append(rec)
    diffs = []
    if out:
        diffs.append({
            "code": "QC_FIELDS_REMAIN_UNKNOWN", "path": "records",
            "detail": "v1 QC records carry no plan_revision, evidence_source "
                      "or applicability; those fields remain explicitly "
                      "unknown until remeasurement, never invented"})
    return {"records": out}, diffs


_UPGRADES = {
    (DOC_RECIPE_INPUT, 1): _upgrade_recipe_v1,
    (DOC_APPROVED_LYRIC_SHEET, 1): _upgrade_sheet_v1,
    (DOC_PROVIDER_ENVELOPE, 1): _upgrade_envelope_v1,
    (DOC_LANE_PLAN, 1): _upgrade_lane_v1,
    (DOC_EXECUTION_RESULT, 1): _upgrade_execution_v1,
    (DOC_QC_RECORDS, 1): _upgrade_qc_v1,
}


def verify_preserved(kind, before, after):
    """Migration preservation proof (D26): performance tags and approved
    meaning survive a version migration EXACTLY. Raises SemanticLossError
    the moment a migration would strip a tag or change approved meaning."""
    if kind == DOC_RECIPE_INPUT:
        src_tags = before.get("performance_tags", before.get("tags"))
        if list(src_tags or []) != list(after.get("performance_tags") or []):
            raise SemanticLossError(
                "migration would strip performance tags", kind,
                "performance_tags")
        src_lyrics = before.get("approved_lyrics", before.get("lyrics"))
        if src_lyrics != after.get("approved_lyrics"):
            raise SemanticLossError(
                "migration would change approved meaning", kind,
                "approved_lyrics")
    elif kind == DOC_APPROVED_LYRIC_SHEET:
        src = before.get("text", "\n".join(before.get("lines") or []))
        if src != "\n".join(after.get("lines") or []):
            raise SemanticLossError(
                "migration would change approved lyric meaning", kind,
                "lines")
    elif kind == DOC_PROVIDER_ENVELOPE:
        if ([t.get("take_id") for t in before.get("takes") or []]
                != [t.get("take_id") for t in after.get("takes") or []]):
            raise SemanticLossError(
                "migration would drop provider takes", kind, "takes")
    elif kind == DOC_LANE_PLAN:
        before_shots = [s for ln in before.get("lanes_detail") or []
                        for s in (ln.get("shot_ids") or ln.get("shots") or [])]
        after_shots = [s for ln in after.get("lanes_detail") or []
                       for s in ln.get("shot_ids") or []]
        if before_shots != after_shots:
            raise SemanticLossError(
                "migration would drop planned shots", kind, "lanes_detail")
    elif kind == DOC_EXECUTION_RESULT:
        if ((before.get("stage"), before.get("outcome"))
                != (after.get("stage"), after.get("outcome"))):
            raise SemanticLossError(
                "migration would change the recorded outcome", kind,
                "outcome")
    elif kind == DOC_QC_RECORDS:
        if ([r.get("check_id") for r in before.get("records") or []]
                != [r.get("check_id") for r in after.get("records") or []]):
            raise SemanticLossError(
                "migration would drop QC records", kind, "records")


def canonical_request_builder(kind, doc):
    """The canonical request builder: the ONLY supported version migration
    for saved state (D26). It never hand-rewrites a saved request contract.
    Performance tags and approved meaning are preserved exactly
    (SemanticLossError otherwise) and every semantic difference that needs
    human review is reported. It never migrates across kinds -- a wrong
    object at this boundary is WrongKindError, not a silent migration -- and
    an internal recipe lacking provider-envelope fields is not obsolete."""
    out = _read(kind, doc, "list" if kind == DOC_QC_RECORDS else "object")
    return {
        "kind": kind,
        "from_version": out["_source_version"],
        "to_version": CURRENT_VERSION,
        "migrated": out,
        "semantic_differences": list(out["_semantic_differences"]),
        "requires_review": bool(out["_semantic_differences"]),
    }


def migrate_document(kind, doc):
    """Version migration for saved state, through the canonical request
    builder (D26). See canonical_request_builder."""
    return canonical_request_builder(kind, doc)


def cache_key(kind, audio_hash, evaluator_version, policy_version,
              approved_plan_revision):
    """The 8.5 cache key: audio hash + evaluator version + policy version +
    approved-plan revision (plus the receipt kind so measurement and
    acceptance receipts of the same audio never collide)."""
    for name, v in (("audio_hash", audio_hash),
                    ("evaluator_version", evaluator_version),
                    ("policy_version", policy_version),
                    ("approved_plan_revision", approved_plan_revision)):
        if not isinstance(v, str) or not v:
            raise MalformedRecordError(
                "cache key component %s must be a non-empty string, got %r"
                % (name, v), path=name)
    return "%s|%s|%s|%s|%s" % (kind, audio_hash, evaluator_version,
                               policy_version, approved_plan_revision)
