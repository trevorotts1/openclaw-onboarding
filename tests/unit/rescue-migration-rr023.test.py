#!/usr/bin/env python3
# tests/unit/rescue-migration-rr023.test.py
#
# RR-023 — ONB legacy importer: preserve incident history across migration.
# Every case below is a CONTROL with a known-bad input: the guard must FIRE
# (loud named refusal, exact exit code, nothing written). Exact counts are
# asserted, never exit-0 alone.
#
# Run: python3 tests/unit/rescue-migration-rr023.test.py
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
SCRIPT = os.path.join(
    REPO, "23-ai-workforce-blueprint", "templates", "role-library",
    "rescue-rangers", "scripts", "migrate-rescue-staticdata.py")

PASS = 0
FAIL = 0

HIST_DAY = "2026-06-01"


def ok(name):
    global PASS
    PASS += 1
    print(f"  ok {name}")


def fail(name, detail=""):
    global FAIL
    FAIL += 1
    print(f"  FAIL {name}" + (f"\n       {detail}" if detail else ""))


def check(cond, name, detail=""):
    if cond:
        ok(name)
    else:
        fail(name, detail)


def run_importer(export_obj, state_dir, *extra, raw_text=None, env_extra=None):
    """Run the importer as a subprocess (real CLI, real exit codes)."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        f.write(raw_text if raw_text is not None else json.dumps(export_obj))
        exp = f.name
    env = dict(os.environ)
    env["RR_LEDGER_DRILL"] = "1"
    if env_extra:
        env.update(env_extra)
    try:
        p = subprocess.run(
            [sys.executable, SCRIPT, "--export", exp, "--state-dir", state_dir, *extra],
            capture_output=True, text=True, env=env, timeout=60)
        return p
    finally:
        os.unlink(exp)


def load_ledger():
    # The retired writer opens ONLY as an explicit offline drill: the env var
    # AND an isolated state dir are both required (RR-006). Set the var here
    # so the in-process verification reads use the same drill contract as the
    # subprocess importer runs.
    os.environ["RR_LEDGER_DRILL"] = "1"
    spec = importlib.util.spec_from_file_location(
        "rescue_ledger_rr023",
        os.path.join(os.path.dirname(SCRIPT), "rescue_ledger.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rescue_ledger_rr023"] = mod
    spec.loader.exec_module(mod)
    return mod


def dated_export(day=HIST_DAY, n_acme=4, n_beta=2):
    return {
        "pending": [
            {"ticketId": "h-1", "clientName": "acme", "problem": "gateway down",
             "status": "open", "ts_open": f"{day}T03:04:05+00:00"},
            {"ticketId": "h-2", "clientName": "beta", "problem": "MCP timeout",
             "answer": "restart the job", "status": "resolved",
             "ts_open": f"{day}T04:05:06+00:00"},
        ],
        "counters": {"acme": {day: n_acme}, "beta": {day: n_beta}},
    }


print("== RR-023 ONB: historical import preserves counts, ids, timestamps ==")
with tempfile.TemporaryDirectory() as td:
    sd = os.path.join(td, "rescue")
    p = run_importer(dated_export(), sd)
    check(p.returncode == 0, "dated export imports with exit 0", p.stderr[-500:])
    rl = load_ledger()
    led = rl.Ledger(Path(sd))
    t1 = led.get_ticket("h-1")
    t2 = led.get_ticket("h-2")
    check(t1 is not None and t2 is not None, "both ticket ids present verbatim")
    check(t1 and t1["ts_open"] == f"{HIST_DAY}T03:04:05+00:00",
          "historical ts_open preserved verbatim, never rewritten",
          str(t1.get("ts_open")) if t1 else "missing")
    check(t2 and t2["status"] == "resolved", "resolved status applied")
    check(led.count_exchanges_today("acme", day=HIST_DAY) == 4,
          "acme export-day counter holds exactly 4",
          str(led.count_exchanges_today("acme", day=HIST_DAY)))
    check(led.count_exchanges_today("beta", day=HIST_DAY) == 2,
          "beta export-day counter holds exactly 2")
    led.close()

print("== RR-023 ONB CONTROL: unsupported nonempty (top-level array) fails, writes nothing ==")
with tempfile.TemporaryDirectory() as td:
    sd = os.path.join(td, "rescue")
    p = run_importer([{"ticketId": "x-1", "clientName": "acme"}], sd)
    check(p.returncode == 2, "top-level array exits 2", f"rc={p.returncode} {p.stderr[-300:]}")
    check("unsupported_nonempty_schema_refused" in p.stderr,
          "refusal names unsupported_nonempty_schema_refused", p.stderr[-300:])
    check(not os.path.exists(sd), "refused run wrote NO state dir")

print("== RR-023 ONB CONTROL: unsupported nonempty (workflow nodes shape) fails ==")
with tempfile.TemporaryDirectory() as td:
    sd = os.path.join(td, "rescue")
    wf = {"name": "Rescue Rangers Relay",
          "nodes": [{"name": "Webhook"}],
          "workflowStaticData": [{"ticketId": "wf-1"}],
          "connections": {}}
    p = run_importer(wf, sd)
    check(p.returncode == 2, "workflow-shaped export exits 2", f"rc={p.returncode} {p.stderr[-300:]}")
    check("unsupported_nonempty_schema_refused" in p.stderr,
          "refusal names unsupported_nonempty_schema_refused", p.stderr[-300:])
    check(not os.path.exists(sd), "refused run wrote NO state dir")

print("== RR-023 ONB CONTROL: undated counter refuses without --counter-day (never bills today) ==")
with tempfile.TemporaryDirectory() as td:
    sd = os.path.join(td, "rescue")
    p = run_importer({"pending": [], "counters": {"acme": 4}}, sd)
    check(p.returncode == 2, "undated counter exits 2", f"rc={p.returncode} {p.stderr[-300:]}")
    check("undated_counter_refused" in p.stderr,
          "refusal names undated_counter_refused", p.stderr[-300:])
    check(not os.path.exists(sd), "refused run wrote NO state dir")

print("== RR-023 ONB: undated counter imports under --counter-day onto that day ==")
with tempfile.TemporaryDirectory() as td:
    sd = os.path.join(td, "rescue")
    p = run_importer({"pending": [], "counters": {"acme": 4}}, sd,
                     "--counter-day", HIST_DAY)
    check(p.returncode == 0, "undated counter with --counter-day exits 0", p.stderr[-500:])
    rl = load_ledger()
    led = rl.Ledger(Path(sd))
    check(led.count_exchanges_today("acme", day=HIST_DAY) == 4,
          "undated count landed on the named day, exactly 4")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if today != HIST_DAY:
        check(led.count_exchanges_today("acme", day=today) == 0,
              "today holds 0 seeded rows (history never bills today)",
              str(led.count_exchanges_today("acme", day=today)))
    else:
        print("  SKIP today-zero check (today IS the historical fixture day)")
    led.close()

print("== RR-023 ONB CONTROL: multi-day counters are ambiguous, refuse ==")
with tempfile.TemporaryDirectory() as td:
    sd = os.path.join(td, "rescue")
    p = run_importer({"pending": [], "counters": {"acme": {"2026-06-01": 4, "2026-06-02": 2}}}, sd)
    check(p.returncode == 2, "multi-day export exits 2", f"rc={p.returncode} {p.stderr[-300:]}")
    check("ambiguous_counter_days" in p.stderr,
          "refusal names ambiguous_counter_days", p.stderr[-300:])
    check(not os.path.exists(sd), "refused run wrote NO state dir")

print("== RR-023 ONB CONTROL: duplicate import folds, no duplicate resolved ==")
with tempfile.TemporaryDirectory() as td:
    sd = os.path.join(td, "rescue")
    p1 = run_importer(dated_export(), sd)
    check(p1.returncode == 0, "first import exits 0", p1.stderr[-300:])
    rl = load_ledger()
    led = rl.Ledger(Path(sd))
    resolved_1 = led.conn.execute(
        "SELECT COUNT(*) AS n FROM exchanges WHERE ticket_id='h-2' AND kind='resolved'"
    ).fetchone()["n"]
    acme_1 = led.count_exchanges_today("acme", day=HIST_DAY)
    led.close()
    p2 = run_importer(dated_export(), sd)
    check(p2.returncode == 0, "second import exits 0", p2.stderr[-300:])
    check("folded 1 already-resolved" in p2.stdout,
          "second run reports the resolved fold", p2.stdout[-300:])
    led2 = rl.Ledger(Path(sd))
    resolved_2 = led2.conn.execute(
        "SELECT COUNT(*) AS n FROM exchanges WHERE ticket_id='h-2' AND kind='resolved'"
    ).fetchone()["n"]
    acme_2 = led2.count_exchanges_today("acme", day=HIST_DAY)
    led2.close()
    check(resolved_1 == 1 and resolved_2 == 1,
          f"exactly one resolved exchange after two runs (was {resolved_1}, now {resolved_2})")
    check(acme_1 == 4 and acme_2 == 4,
          f"export-day counter still exactly 4 after re-run (was {acme_1}, now {acme_2})")

print("== RR-023 ONB CONTROL: empty export needs --allow-empty-retirement ==")
with tempfile.TemporaryDirectory() as td:
    sd = os.path.join(td, "rescue")
    p = run_importer({"pending": [], "counters": {}}, sd)
    check(p.returncode == 3, "empty export exits 3", f"rc={p.returncode} {p.stderr[-300:]}")
    check("empty_retirement_unacknowledged" in p.stderr,
          "refusal names empty_retirement_unacknowledged", p.stderr[-300:])
    p2 = run_importer({"pending": [], "counters": {}}, sd, "--allow-empty-retirement")
    check(p2.returncode == 0, "acknowledged empty export exits 0", p2.stderr[-300:])
    check("RETIREMENT-NOTE" in p2.stdout, "acknowledged run prints the retirement note",
          p2.stdout[-300:])

print("== RR-023 ONB CONTROL: ownership mismatch aborts, writes nothing new ==")
with tempfile.TemporaryDirectory() as td:
    sd = os.path.join(td, "rescue")
    p1 = run_importer(dated_export(), sd)
    check(p1.returncode == 0, "first import exits 0", p1.stderr[-300:])
    rl = load_ledger()
    led = rl.Ledger(Path(sd))
    n_before = led.conn.execute("SELECT COUNT(*) AS n FROM tickets").fetchone()["n"]
    led.close()
    hostile = dated_export()
    hostile["pending"][0]["clientName"] = "mallory"
    p2 = run_importer(hostile, sd, "--verify-ownership", "acme")
    check(p2.returncode == 3, "ownership mismatch exits 3", f"rc={p2.returncode} {p2.stderr[-300:]}")
    check("ownership_mismatch" in p2.stderr,
          "refusal names ownership_mismatch", p2.stderr[-300:])
    led3 = rl.Ledger(Path(sd))
    n_after = led3.conn.execute("SELECT COUNT(*) AS n FROM tickets").fetchone()["n"]
    t1 = led3.get_ticket("h-1")
    led3.close()
    check(n_after == n_before, f"ticket count unchanged ({n_before} -> {n_after})")
    check(t1 and t1["client"] == "acme", "original ownership row untouched")

print("== RR-023 ONB CONTROL: malformed JSON fails, writes nothing ==")
with tempfile.TemporaryDirectory() as td:
    sd = os.path.join(td, "rescue")
    p = run_importer(None, sd, raw_text="{not json")
    check(p.returncode == 2, "malformed JSON exits 2", f"rc={p.returncode} {p.stderr[-300:]}")
    check(not os.path.exists(sd), "malformed run wrote NO state dir")

print("")
print(f"RESULT: {PASS} passed, {FAIL} failed")
sys.exit(0 if FAIL == 0 else 1)
