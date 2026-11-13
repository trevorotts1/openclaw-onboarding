#!/usr/bin/env python3
"""Tests for spend_ledger_money_migration: unknown schema and marker scope.

Proves the two defects fixed after review:
  1. an unrecognised or missing schema version is AMBIGUOUS, never "correct";
  2. a ledger-level marker does not prove every record migrated -- validation is
     per record, and unresolved records stay visible on every later plan.

Run: python3 -m pytest -q scripts/core/test_spend_ledger_money_migration.py
"""
import hashlib
import json
import os
import sqlite3
import tempfile

import spend_ledger_money_migration as M

PROV = {"schema": M.PROVENANCE_SCHEMA, "money_unit": "usd",
        "run_ids": ["r1"], "recorded_by": "test", "at": "2026-10-01T00:00:00Z"}
T = "2026-10-01T00:00:00Z"

def _db(tmp, version="1.0.0", ledger_marker=None, markers=()):
    db = os.path.join(tmp, "ledger.db")
    conn = sqlite3.connect(db)
    conn.executescript("""
    CREATE TABLE schema_info(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE runs(run_id TEXT PRIMARY KEY, ceiling INTEGER NOT NULL,
      currency TEXT NOT NULL DEFAULT 'USD', qc_allowance INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE jobs(logical_key TEXT NOT NULL, attempt_id TEXT NOT NULL,
      estimated_cost INTEGER, actual_cost INTEGER, PRIMARY KEY(logical_key, attempt_id));
    CREATE TABLE receipts(receipt_id INTEGER PRIMARY KEY AUTOINCREMENT,
      amount INTEGER NOT NULL);
    CREATE TABLE money_migration(table_name TEXT NOT NULL, record_key TEXT NOT NULL,
      field TEXT NOT NULL, status TEXT NOT NULL, before_value INTEGER,
      after_value INTEGER, reason TEXT NOT NULL, at_utc TEXT NOT NULL,
      PRIMARY KEY(table_name, record_key, field));
    """)
    if version is not None:
        conn.execute("INSERT INTO schema_info VALUES('schema_version',?)", (version,))
    if ledger_marker is not None:
        conn.execute("INSERT INTO schema_info VALUES(?,?)",
                     (M.MARKER_KEY, json.dumps(ledger_marker)))
    conn.execute("INSERT INTO runs VALUES('r1',250,'USD',10)")
    conn.execute("INSERT INTO jobs VALUES('k1','a1',250,200)")
    conn.execute("INSERT INTO receipts(amount) VALUES(199)")
    for table, key, field in markers:
        conn.execute("INSERT INTO money_migration VALUES(?,?,?,'migrated',0,0,?,?)",
                     (table, key, field, "prior migration", T))
    conn.commit()
    conn.close()
    prov = os.path.join(tmp, "prov.json")
    with open(prov, "w", encoding="utf-8") as f:
        json.dump(PROV, f)
    return db, prov

def _by_field(result):
    return {(r["table"], r["record_key"], r["field"]): r for r in result["records"]}

def test_unknown_schema_is_ambiguous_and_names_the_version():
    with tempfile.TemporaryDirectory() as tmp:
        db, prov = _db(tmp, version="9.9.9")
        out = M.plan(db, prov)
        assert out["summary"]["eligible"] == 0, out["summary"]
        assert out["summary"]["already_correct"] == 0, out["summary"]
        assert out["summary"]["ambiguous"] == len(out["records"]) > 0
        assert all(r["status"] == "ambiguous" for r in out["records"])
        assert all("9.9.9" in r["reason"] for r in out["records"]), out["records"]

def test_missing_schema_is_ambiguous():
    with tempfile.TemporaryDirectory() as tmp:
        db, prov = _db(tmp, version=None)
        out = M.plan(db, prov)
        assert out["summary"]["ambiguous"] == len(out["records"]) > 0
        assert all(r["status"] == "ambiguous" for r in out["records"])

def test_ledger_marker_does_not_collapse_unresolved_records():
    with tempfile.TemporaryDirectory() as tmp:
        db, prov = _db(tmp, ledger_marker={"schema": "blackceo.ledger-money-migration/v1"},
                       markers=[("runs", "r1", "ceiling")])
        for _ in range(2):                       # visible on every later plan
            out = M.plan(db, prov)
            assert out["records"], "unresolved records must stay visible"
            got = _by_field(out)
            assert got[("runs", "r1", "ceiling")]["status"] == "already_migrated"
            unresolved = got[("runs", "r1", "qc_allowance")]
            assert unresolved["status"] == "ambiguous", unresolved
            assert "no per-record marker" in unresolved["reason"], unresolved
            assert out["summary"]["already_migrated"] == 1, out["summary"]
            assert out["summary"]["ambiguous"] >= 1, out["summary"]

def test_all_records_individually_proven_are_migrated():
    with tempfile.TemporaryDirectory() as tmp:
        fields = [("runs", "r1", "ceiling"), ("runs", "r1", "qc_allowance"),
                  ("jobs", "k1|a1", "estimated_cost"),
                  ("jobs", "k1|a1", "actual_cost"), ("receipts", "1", "amount")]
        db, prov = _db(tmp, markers=fields)
        out = M.plan(db, prov)
        assert out["summary"]["already_migrated"] == len(fields), out["summary"]
        assert out["summary"]["eligible"] == 0
        assert out["summary"]["ambiguous"] == 0
        assert all(r["status"] == "already_migrated" for r in out["records"])

def test_dry_plan_never_writes():
    with tempfile.TemporaryDirectory() as tmp:
        db, prov = _db(tmp)
        before = hashlib.sha256(open(db, "rb").read()).hexdigest()
        M.plan(db, prov)
        after = hashlib.sha256(open(db, "rb").read()).hexdigest()
        assert before == after
