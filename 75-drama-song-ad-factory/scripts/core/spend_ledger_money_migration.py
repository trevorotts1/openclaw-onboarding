#!/usr/bin/env python3
"""One-time migration: legacy ledgers that recorded dollars in cents fields.

Some legacy 999 budget ledgers stored dollar amounts in the ledger's integer
minor-unit columns (``runs.ceiling``, ``runs.qc_allowance``,
``jobs.estimated_cost``, ``jobs.actual_cost``, ``receipts.amount``). New runs
are written correctly; this module repairs old ones and nothing else.

Eligibility is never inferred from the amount. A record is eligible only when
BOTH hold:

1. **Version evidence** -- ``schema_info.schema_version`` is a known legacy
   version (``LEGACY_SCHEMA_VERSIONS``).
2. **Provenance evidence** -- a separate provenance manifest states the
   ledger's recorded ``money_unit`` and binds itself to this ledger by naming
   every ``run_id`` it contains. The manifest's schema must match exactly.

Every monetary record is classified as:

* ``eligible``        -- legacy version + ``money_unit: "usd"`` provenance and
                         an integer value: proposed x100.
* ``already_correct`` -- current schema version, ``money_unit: "cents"``
                         provenance, a NULL (nothing recorded), or a record
                         already verified as cents.
* ``already_migrated``-- a completed migration marker already covers it.
* ``ambiguous``       -- unknown version, missing/invalid/unbound provenance,
                         a non-integer or negative value, or a corrupt
                         ``schema_info``. Ambiguous records are NEVER changed
                         and are listed for manual review.

Default mode is a DRY PLAN: it writes nothing and reports each class with the
proposed before/after and the reason. ``--apply`` is the one-time mutation; it
takes a recoverable backup, runs in one IMMEDIATE transaction, updates only
records whose value still matches the planned before (compare-and-set), writes
a per-record idempotency marker, and records a ledger-level marker. Re-running
never double-applies: a per-record marker short-circuits that record to
``already_migrated``. A ledger-level marker alone does not: records without
their own marker stay ``ambiguous`` and visible in every later plan.

Currency, reservation/state, transaction identity and supporting evidence are
never touched -- only the five monetary columns above are scaled.

Stdlib only. Usage:

    python3 spend_ledger_money_migration.py --db LEDGER.db --provenance P.json
    python3 spend_ledger_money_migration.py --db LEDGER.db --provenance P.json --apply
"""
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import time

TOOL_NAME = "spend_ledger_money_migration"
TOOL_VERSION = "1.0.0"
PROVENANCE_SCHEMA = "blackceo.ledger-money-provenance/v1"
MARKER_KEY = "money_unit_migration"
MARKER_TABLE = "money_migration"

#: Versions whose monetary columns may hold dollars. Anything newer is correct.
LEGACY_SCHEMA_VERSIONS = ("1.0.0",)

#: table -> (key columns, monetary columns)
MONEY_RECORDS = (
    ("runs", ("run_id",), ("ceiling", "qc_allowance")),
    ("jobs", ("logical_key", "attempt_id"), ("estimated_cost", "actual_cost")),
    ("receipts", ("receipt_id",), ("amount",)),
)

ELIGIBLE = "eligible"
CORRECT = "already_correct"
MIGRATED = "already_migrated"
AMBIGUOUS = "ambiguous"

class MigrationError(Exception):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message

def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def _sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def _connect(db_path):
    """Read-write only for --apply; the caller keeps the dry plan read-only."""
    conn = sqlite3.connect(db_path, timeout=10, isolation_level=None)
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def _table_exists(conn, name):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row is not None

def _schema_version(conn):
    if not _table_exists(conn, "schema_info"):
        return None
    row = conn.execute(
        "SELECT value FROM schema_info WHERE key='schema_version'").fetchone()
    return row[0] if row else None

def _ledger_run_ids(conn):
    if not _table_exists(conn, "runs"):
        return None
    return sorted(r[0] for r in conn.execute("SELECT run_id FROM runs"))

def _load_provenance(path, conn):
    """-> (unit, reason). unit is 'usd', 'cents' or None with a reason."""
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as exc:
        return None, "provenance unreadable: %s" % exc
    if not isinstance(doc, dict) or doc.get("schema") != PROVENANCE_SCHEMA:
        return None, "provenance schema is not %s" % PROVENANCE_SCHEMA
    unit = doc.get("money_unit")
    if unit not in ("usd", "cents"):
        return None, "provenance money_unit must be 'usd' or 'cents', got %r" % (unit,)
    claimed = doc.get("run_ids")
    if not isinstance(claimed, list) or not all(isinstance(r, str) for r in claimed):
        return None, "provenance must bind itself with a run_ids list"
    actual = _ledger_run_ids(conn)
    if actual is None:
        return None, "ledger has no runs table to bind provenance to"
    if sorted(claimed) != actual:
        return None, ("provenance names runs %r but the ledger holds %r"
                      % (sorted(claimed), actual))
    return unit, "bound to %d run(s)" % len(actual)

def _markers(conn):
    """-> {(table, record_key, field): row} for completed/verified records."""
    if not _table_exists(conn, MARKER_TABLE):
        return {}
    return {(row[0], row[1], row[2]): {"status": row[3], "before": row[4],
                                       "after": row[5], "reason": row[6]}
            for row in conn.execute(
                "SELECT table_name, record_key, field, status, before_value, "
                "after_value, reason FROM %s" % MARKER_TABLE)}

def _ledger_marker(conn):
    if not _table_exists(conn, "schema_info"):
        return None
    row = conn.execute(
        "SELECT value FROM schema_info WHERE key=?", (MARKER_KEY,)).fetchone()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except ValueError:
        return {"corrupt": True}

def _record_key(row, keys):
    return "|".join(str(row[k]) for k in keys)

def _classify(conn, version, unit, provenance_reason, ledger_marker=None):
    """-> list of dicts: table, record_key, field, before, after, status, reason."""
    markers = _markers(conn)
    rows = []
    for table, keys, fields in MONEY_RECORDS:
        if not _table_exists(conn, table):
            continue
        cols = {r[1] for r in conn.execute("PRAGMA table_info(%s)" % table)}
        fields = [f for f in fields if f in cols]
        if not fields:
            continue
        select = ", ".join(list(keys) + fields)
        for row in conn.execute("SELECT %s FROM %s" % (select, table)):
            rec = dict(zip(list(keys) + fields, row))
            record_key = _record_key(rec, keys)
            states = {f: (markers[(table, record_key, f)]["status"]
                          if (table, record_key, f) in markers else None)
                      for f in fields}
            mixed = any(s is not None for s in states.values()) and any(
                states[f] is None and rec[f] is not None for f in fields)
            for field in fields:
                value = rec[field]
                marker = markers.get((table, record_key, field))
                base = {"table": table, "record_key": record_key, "field": field,
                        "before": value,
                        "after": None if value is None else value}
                if marker:
                    base.update(status=MIGRATED if marker["status"] == "migrated"
                                else CORRECT,
                                after=marker["after"],
                                reason="migration marker: %s" % marker["reason"])
                    rows.append(base)
                    continue
                if ledger_marker is not None:
                    base.update(status=AMBIGUOUS,
                                reason="ledger-level migration marker present but this "
                                       "record has no per-record marker; resolve manually")
                    rows.append(base)
                    continue
                if version not in LEGACY_SCHEMA_VERSIONS:
                    base.update(status=AMBIGUOUS,
                                reason="schema version %r is not a recognised legacy "
                                       "schema; cannot classify" % (version,))
                    rows.append(base)
                    continue
                if value is None:
                    base.update(status=CORRECT, reason="no amount recorded")
                    rows.append(base)
                    continue
                if isinstance(value, bool) or not isinstance(value, int):
                    base.update(status=AMBIGUOUS,
                                reason="amount is not an integer minor-unit count (%r)" % (value,))
                    rows.append(base)
                    continue
                if value < 0:
                    base.update(status=AMBIGUOUS, reason="negative amount cannot be unit-scaled")
                    rows.append(base)
                    continue
                if mixed:
                    base.update(status=AMBIGUOUS,
                                reason="row is partially migrated; an unmarked field "
                                       "cannot be safely classified")
                    rows.append(base)
                    continue
                if unit == "cents":
                    base.update(status=CORRECT,
                                reason="provenance says this ledger already records cents")
                    rows.append(base)
                    continue
                if unit != "usd":
                    base.update(status=AMBIGUOUS,
                                reason="no reliable provenance: %s" % provenance_reason)
                    rows.append(base)
                    continue
                base.update(status=ELIGIBLE, after=value * 100,
                            reason="legacy %s schema + dollar provenance; x100 to minor units"
                                   % version)
                rows.append(base)
    return rows

def plan(db_path, provenance_path):
    """Read-only dry plan. Never writes to the ledger."""
    if not os.path.isfile(db_path):
        raise MigrationError("NO_DB", "ledger not found: %s" % db_path)
    conn = _connect(db_path)
    try:
        version = _schema_version(conn)
        marker = _ledger_marker(conn)
        unit, reason = _load_provenance(provenance_path, conn)
        records = _classify(conn, version, unit, reason, marker)
        summary = {k: 0 for k in (ELIGIBLE, CORRECT, MIGRATED, AMBIGUOUS)}
        for r in records:
            summary[r["status"]] += 1
        out = {"tool": TOOL_NAME, "tool_version": TOOL_VERSION, "mode": "dry-plan",
               "db": db_path, "schema_version": version,
               "provenance": {"money_unit": unit, "reason": reason},
               "summary": summary, "records": records}
        if marker is not None:
            out["ledger_marker"] = marker
            out["note"] = ("ledger-level marker present; per-record validation still "
                           "applied, unresolved records remain visible")
        return out
    finally:
        conn.close()

def _backup(db_path, backup_dir):
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    target = os.path.join(backup_dir or os.path.dirname(os.path.abspath(db_path)),
                          "%s.pre-money-migration-%s" % (os.path.basename(db_path), stamp))
    if os.path.exists(target):
        raise MigrationError("BACKUP_EXISTS", "refusing to overwrite %s" % target)
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)          # consistent copy, WAL included
    finally:
        dst.close()
        src.close()
    return target, _sha_file(target)

def apply(db_path, provenance_path, backup_dir=None):
    """One-time mutation. Atomic; idempotent through markers."""
    dry = plan(db_path, provenance_path)
    eligible = [r for r in dry["records"] if r["status"] == ELIGIBLE]
    if not eligible:
        return dict(dry, mode="apply", applied=0,
                    note="no eligible records; nothing written")
    backup_path, backup_sha = _backup(db_path, backup_dir)
    marker = {"schema": "blackceo.ledger-money-migration/v1",
              "tool": TOOL_NAME, "tool_version": TOOL_VERSION,
              "from_schema": dry["schema_version"], "to_unit": "cents",
              "provenance_unit": dry["provenance"]["money_unit"],
              "at": _now(), "backup_path": backup_path,
              "backup_sha256": backup_sha, "records": len(eligible)}
    conn = _connect(db_path)
    applied = 0
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS %s("
            "table_name TEXT NOT NULL, record_key TEXT NOT NULL, field TEXT NOT NULL,"
            "status TEXT NOT NULL, before_value INTEGER, after_value INTEGER,"
            "reason TEXT NOT NULL, at_utc TEXT NOT NULL,"
            "PRIMARY KEY(table_name, record_key, field))" % MARKER_TABLE)
        for r in eligible:
            keys = ("receipt_id",) if r["table"] == "receipts" else (
                ("run_id",) if r["table"] == "runs" else ("logical_key", "attempt_id"))
            key_parts = r["record_key"].split("|")
            where = " AND ".join("%s=?" % k for k in keys)
            cur = conn.execute(
                "UPDATE %s SET %s=?" % (r["table"], r["field"]) +
                " WHERE %s AND %s=?" % (where, r["field"]),
                [r["after"]] + key_parts + [r["before"]])
            if cur.rowcount != 1:
                raise MigrationError(
                    "CAS_FAILED", "%s %s.%s changed under the plan; rolled back"
                    % (r["table"], r["record_key"], r["field"]))
            conn.execute(
                "INSERT OR REPLACE INTO %s(table_name, record_key, field, status,"
                " before_value, after_value, reason, at_utc) VALUES(?,?,?,?,?,?,?,?)"
                % MARKER_TABLE,
                (r["table"], r["record_key"], r["field"], "migrated",
                 r["before"], r["after"], r["reason"], _now()))
            applied += 1
        conn.execute(
            "INSERT OR REPLACE INTO schema_info(key, value) VALUES(?, ?)",
            (MARKER_KEY, json.dumps(marker, sort_keys=True)))
        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()
    return dict(dry, mode="apply", applied=applied, backup_path=backup_path,
                backup_sha256=backup_sha, ledger_marker=marker)

def _print_human(result):
    print("mode:", result["mode"])
    print("db:", result["db"])
    print("schema_version:", result.get("schema_version"))
    if "provenance" in result:
        print("provenance:", result["provenance"])
    print("summary:", json.dumps(result["summary"], sort_keys=True))
    for r in result["records"]:
        print("  %-10s %-8s %-22s %-16s %r -> %r | %s"
              % (r["status"], r["table"], r["record_key"], r["field"],
                 r["before"], r["after"], r["reason"]))
    if result["mode"] == "apply":
        print("applied:", result.get("applied"))
        print("backup:", result.get("backup_path"), result.get("backup_sha256"))
    if result.get("note"):
        print("note:", result["note"])

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--db", required=True)
    p.add_argument("--provenance", required=True)
    p.add_argument("--apply", action="store_true",
                   help="perform the one-time migration (default: dry plan)")
    p.add_argument("--backup-dir", default=None)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    try:
        result = (apply(args.db, args.provenance, args.backup_dir) if args.apply
                  else plan(args.db, args.provenance))
    except MigrationError as exc:
        print(json.dumps({"tool": TOOL_NAME, "outcome": "error",
                          "reason_code": exc.code, "message": exc.message}))
        return 1
    if args.json:
        print(json.dumps(result, indent=1, sort_keys=True))
    else:
        _print_human(result)
    return 0

if __name__ == "__main__":
    sys.exit(main())
