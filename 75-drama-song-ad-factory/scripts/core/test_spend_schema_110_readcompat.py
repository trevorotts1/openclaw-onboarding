#!/usr/bin/env python3
"""Read canonical 1.1.0 spend ledgers; keep refusing unknown versions.

The canonical Skill 75 build writes SCHEMA_VERSION 1.1.0, which only widens
1.0.0 (columns, two tables, one index -- nothing removed or reshaped). This
build must read such a ledger without losing the 1.1.0-only fields, must write
the canonical 1.1.0 itself, and must still refuse a genuinely unsupported version.

Run: python3 core/test_spend_schema_110_readcompat.py
"""
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import spend_ledger as L                     # noqa: E402  (module under test)

FAILS = []

# Canonical's additive 1.0.0 -> 1.1.0 widening, reproduced here so the fixture
# needs no copy of the canonical build.
ADDITIVE_JOBS = (
    ("retry_category", "TEXT NOT NULL DEFAULT ''"),
    ("auth_ref", "TEXT NOT NULL DEFAULT ''"),
    ("provider_lookup_ref", "TEXT NOT NULL DEFAULT ''"),
    ("outcome_class", "TEXT NOT NULL DEFAULT ''"),
    ("est_credits_micro", "INTEGER"),
    ("actual_credits_micro", "INTEGER"))
ADDITIVE_RUNS = (("credit_to_subunit_num", "INTEGER NOT NULL DEFAULT 1"),
                 ("credit_to_subunit_den", "INTEGER NOT NULL DEFAULT 1"))

def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)

def tmp_db():
    d = tempfile.mkdtemp(prefix="schema110-")
    return os.path.join(d, "spend.db")

def make_110(db):
    """A 1.1.0 ledger shaped exactly as canonical writes it."""
    L.init_run(db, "run1", 10000)
    conn = sqlite3.connect(db)
    try:
        for table, cols in (("jobs", ADDITIVE_JOBS), ("runs", ADDITIVE_RUNS)):
            have = {r[1] for r in conn.execute(
                "PRAGMA table_info(%s)" % table)}
            for col, decl in cols:
                if col not in have:
                    conn.execute("ALTER TABLE %s ADD COLUMN %s %s"
                                 % (table, col, decl))
        conn.execute("UPDATE schema_info SET value='1.1.0' "
                     "WHERE key='schema_version'")
        conn.execute(
            "INSERT INTO jobs(logical_key,attempt_id,run_id,request_digest,"
            "state,retry_category,auth_ref,est_credits_micro,created_at,"
            "updated_at) VALUES('song1','a1','run1','d1','planned',"
            "'initial','auth-xyz',2000000,'2026-01-01T00:00:00+00:00',"
            "'2026-01-01T00:00:00+00:00')")
        conn.commit()
    finally:
        conn.close()

def schema_version(db):
    conn = sqlite3.connect(db)
    try:
        return conn.execute("SELECT value FROM schema_info "
                            "WHERE key='schema_version'").fetchone()[0]
    finally:
        conn.close()

def seed_fields(db):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(
            "SELECT retry_category,auth_ref,est_credits_micro FROM jobs "
            "WHERE logical_key='song1'").fetchone()
    finally:
        conn.close()

def test_reads_canonical_110():
    db = tmp_db()
    make_110(db)
    s = L.summary(db, "run1")
    check("1.1.0 summary accepted", s["outcome"] == "ok", s.get("reason_code"))
    check("1.1.0-only fields intact", seed_fields(db)
          == ("initial", "auth-xyz", 2000000), seed_fields(db))
    check("file still declares 1.1.0", schema_version(db) == "1.1.0",
          schema_version(db))

def test_own_new_ledger_writes_110():
    db = tmp_db()
    L.init_run(db, "run1", 1000)
    check("new ledger writes 1.1.0 (the canonical version)", schema_version(db) == "1.1.0",
          schema_version(db))

def test_write_into_110_preserves_fields():
    db = tmp_db()
    make_110(db)
    r = L.plan(db, "run1", "song2", "a2", "d2", estimated_cost=100)
    check("plan into 1.1.0 accepted", r["outcome"] == "ok", r.get("reason_code"))
    check("existing 1.1.0 fields survive the write", seed_fields(db)
          == ("initial", "auth-xyz", 2000000), seed_fields(db))
    check("write does not downgrade the file", schema_version(db) == "1.1.0",
          schema_version(db))

def test_unknown_version_still_refused():
    db = tmp_db()
    make_110(db)
    conn = sqlite3.connect(db)
    try:
        conn.execute("UPDATE schema_info SET value='9.9.9' "
                     "WHERE key='schema_version'")
        conn.commit()
    finally:
        conn.close()
    s = L.summary(db, "run1")  # summary reports refusal as an envelope
    check("9.9.9 refused", s["outcome"] == "error"
          and s["reason_code"] == "INCOMPATIBLE_STATE",
          (s["outcome"], s["reason_code"]))
    try:
        L._open(db)
        check("9.9.9 refused at open", False, "open succeeded")
    except L.IncompatibleStateError as e:
        check("9.9.9 refused at open", "INCOMPATIBLE_STATE" in str(e), str(e))

TESTS = [
    test_reads_canonical_110,
    test_own_new_ledger_writes_110,
    test_write_into_110_preserves_fields,
    test_unknown_version_still_refused,
]

def main():
    for t in TESTS:
        try:
            t()
        except Exception as e:                              # noqa: BLE001
            check("%s raised" % t.__name__, False, "%s: %s"
                  % (type(e).__name__, e))
    print("\n%d checks failed" % len(FAILS))
    if FAILS:
        for f in FAILS:
            print("  FAILED: %s" % f)
        return 1
    print("all schema-1.1.0 read-compat checks passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
