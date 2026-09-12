#!/usr/bin/env python3
"""tests/rescue/RR-022/test_aging_structured.py — ONB-side RR-022 gate.

Proves the O1 legacy-aging defects are fixed in the structured path while the
legacy path keeps its drill-only contract:
  1. incomplete work is included in the structured sweep (legacy omits it),
  2. one naive timestamp does NOT collapse the queue (legacy bridge -> []),
  3. one malformed row quarantines individually with owned reason while valid
     overdue rows stay visible,
  4. bridge error is a monitor failure, never a bare [] zero-overdue claim.

Sanitized fixtures only (temp dirs). English only.
Run: python3 tests/rescue/RR-022/test_aging_structured.py
"""
from __future__ import annotations
import importlib.util
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[3]
SCRIPTS = REPO / "23-ai-workforce-blueprint" / "templates" / "role-library" / "rescue-rangers" / "scripts"

def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

PASS, FAIL = 0, 0
def check(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label} {detail}")

def main():
    global PASS, FAIL
    rl = load("rescue_ledger")
    rb = load("rescue_cc_board")
    os.environ["RR_LEDGER_DRILL"] = "1"
    try:
        with tempfile.TemporaryDirectory() as sd:
            led = rl.Ledger(sd)
            old = (datetime.now(timezone.utc) - timedelta(hours=5)).replace(microsecond=0).isoformat()
            led.open_ticket("good-1", client="c", problem="old", ts_open=old)
            led.open_ticket("inc-1", client="c", problem="partial", incomplete=True, ts_open=old)
            led.open_ticket("bad-1", client="c", problem="bad", ts_open="not-a-date")
            led.open_ticket("naive-1", client="c", problem="naive", ts_open="2020-01-01 00:00:00")
            led.open_ticket("fresh-1", client="c", problem="fresh")
            # 1. structured includes incomplete
            st = led.aging_sweep_structured(120)
            got = {t["ticket_id"] for t in st["due"]}
            check("structured-includes-incomplete", "inc-1" in got, sorted(got))
            # Legacy defect proven inline: with a naive row present, legacy
            # aging() raises TypeError (naive vs aware compare) instead of
            # returning a list — the board wrapper turns that into [].
            try:
                leg = {t["ticket_id"] for t in led.aging(120)}
                check("legacy-omits-incomplete", "inc-1" not in leg, sorted(leg))
            except TypeError as exc:
                check("legacy-raises-on-naive", "can't compare" in str(exc), str(exc)[:120])
            # 2+3. naive due, malformed quarantined, valid visible
            check("naive-due-not-collapsed", "naive-1" in got and "good-1" in got, sorted(got))
            bad = {b["ticket_id"]: b for b in st["invalid"]}
            check("malformed-quarantined-owned", "bad-1" in bad and bad["bad-1"]["owner"] == "operator"
                  and bad["bad-1"]["reason"] == "malformed_timestamp", bad)
            check("fresh-excluded", "fresh-1" not in got, sorted(got))
            check("structured-shape", st["ok"] is True and st["error"] is None and st["scanned"] == 5, st)
            # bridge structured path
            bst = rb.aging_sweep_structured(led, 120)
            bgot = {t["ticket_id"] for t in bst["due"]}
            check("bridge-structured-visible", {"good-1", "inc-1", "naive-1"} <= bgot, sorted(bgot))
            # legacy bridge collapses to [] on the naive row (TypeError -> except -> [])
            collapsed = rb.aging_sweep(led, 120)
            check("legacy-bridge-collapses", collapsed == [], str(collapsed)[:200])
            # error path is monitor failure, not zero overdue
            class Boom:
                def aging_sweep_structured(self, *a, **k): raise RuntimeError("db down")
                def aging(self, *a, **k): raise RuntimeError("db down")
            err = rb.aging_sweep_structured(Boom(), 120)
            check("bridge-error-monitor-failure", err["ok"] is False and err["error"] == "monitor_failure" and err["due"] == [], err)
            led.close()
    finally:
        os.environ.pop("RR_LEDGER_DRILL", None)
    print(f"RR-022 ONB: {PASS} pass, {FAIL} fail")
    return 0 if FAIL == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
