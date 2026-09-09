#!/usr/bin/env python3
"""tests/unit/rr030-staging-ledger-concurrency.test.py

RR-030 — staging persistence concurrency gate for the Rescue ledger.

The captured n8n Code-node tests + the board self-tests exercise single-writer
flows. RR-030 also requires "actual staging persistence concurrency": real
parallel writers against the durable store, where a lost/double write must
FAIL the gate. rescue_ledger.Ledger pins journal_mode=WAL and
busy_timeout=30000 — this gate proves those settings actually hold up under
concurrent processes, using EXPLICIT state dirs (never HOME).

Cases:
  1. N parallel PROCESSES open distinct tickets — every write survives, no
     process errors, row count exact.
  2. N parallel processes re-deliver the SAME ticket id (transport replay) —
     exactly one row wins (INSERT OR IGNORE idempotency holds).
  3. WAL mode is actually on for the surviving db.
"""
import concurrent.futures
import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
LEDGER = REPO / "23-ai-workforce-blueprint" / "templates" / "role-library" / "rescue-rangers" / "scripts" / "rescue_ledger.py"

checks = []


def check(name, cond, detail=""):
    checks.append((name, cond))
    print(f"  {'✓' if cond else '✗'} {name}{(' — ' + detail) if detail and not cond else ''}")


OPEN_ONE = """
import json
import importlib.util
import sys
spec = importlib.util.spec_from_file_location(
    "rescue_ledger", %(ledger_path)s)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
led = mod.Ledger(%(state)r)
created = led.open_ticket(%(tid)r, client=%(client)r, problem="staging concurrency probe")
led.close()
print(json.dumps({"tid": %(tid)r, "created": created}))
"""


def open_one(state, tid, client):
    src = OPEN_ONE % {
        "ledger_path": json.dumps(str(LEDGER)),
        "state": str(state), "tid": tid, "client": client,
    }
    # RR-006: the legacy Python writer is RETIRED — production-style runs
    # exit 78. This gate is an explicit offline drill against an isolated
    # tempdir state dir, so it opts into drill mode (same pattern as the
    # board/migrate self-tests). Production refusal without the env is
    # unchanged and pinned by tests/rescue/RR-006/test_legacy_writer_retired.py.
    env = dict(os.environ, RR_LEDGER_DRILL="1")
    return subprocess.run([sys.executable, "-c", src],
                          capture_output=True, text=True, env=env)


def rows(state):
    db = sqlite3.connect(str(pathlib.Path(state) / "tickets.db"))
    db.row_factory = sqlite3.Row
    out = [dict(r) for r in db.execute("SELECT ticket_id,status FROM tickets")]
    db.close()
    return out


def wal_mode(state):
    db = sqlite3.connect(str(pathlib.Path(state) / "tickets.db"))
    mode = db.execute("PRAGMA journal_mode").fetchone()[0]
    db.close()
    return str(mode)


with tempfile.TemporaryDirectory() as td:
    # --- 1. distinct tickets, parallel processes ----------------------------
    state1 = pathlib.Path(td) / "s1"
    state1.mkdir(parents=True)
    tids = [(f"tkt-p{i:02d}", f"client{i % 3}") for i in range(12)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        results = list(ex.map(lambda a: open_one(state1, *a), tids))
    oks = [r for r in results if r.returncode == 0]
    check("12 parallel distinct-ticket writers all succeeded", len(oks) == 12,
          f"{len(oks)}/12 ok; first error: {next((r.stderr for r in results if r.returncode), 'none')[:200]}")
    got = {r["ticket_id"] for r in rows(state1)}
    want = {t for t, _ in tids}
    check("every parallel write survived (no lost rows)", got == want,
          f"missing={want - got} extra={got - want}")

    # --- 2. same ticket id replayed in parallel -----------------------------
    state2 = pathlib.Path(td) / "s2"
    state2.mkdir(parents=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        results2 = list(ex.map(lambda i: open_one(state2, "tkt-replay", "acme"), range(12)))
    oks2 = [r for r in results2 if r.returncode == 0]
    check("12 parallel SAME-id writers all completed without error", len(oks2) == 12,
          f"{len(oks2)}/12 ok; first error: {next((r.stderr for r in results2 if r.returncode), 'none')[:200]}")
    created_flags = []
    for r in oks2:
        created_flags.append(json.loads(r.stdout.strip().splitlines()[-1])["created"])
    survivors = rows(state2)
    check("replayed id collapsed to exactly ONE row", len(survivors) == 1,
          f"{len(survivors)} rows: {survivors}")
    check("exactly one writer reported created=True", created_flags.count(True) == 1,
          f"created counts: True={created_flags.count(True)} False={created_flags.count(False)}")

    # --- 3. WAL actually on --------------------------------------------------
    check("surviving db is in WAL mode", wal_mode(state2).lower() == "wal",
          f"journal_mode={wal_mode(state2)}")

failed = [n for n, ok in checks if not ok]
print(f"\n[rr030-staging-ledger-concurrency] {'PASS' if not failed else 'FAIL'} "
      f"({len(checks) - len(failed)}/{len(checks)})")
sys.exit(1 if failed else 0)