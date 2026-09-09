#!/usr/bin/env python3
"""tests/unit/rr030-board-selftest-failsonly.test.py

RR-030 — proves rescue_cc_board.py --self-test cannot hide failures:
  1. a BROKEN aging sweep (mutated in a copy) makes the self-test exit nonzero
     with a named assertion (baseline behavior: blanket except -> SKIP -> exit 0);
  2. a MISSING sibling rescue_ledger.py makes the self-test exit nonzero
     (baseline behavior: "SKIP (ledger import unavailable)" -> exit 0);
  3. the healthy tree still exits 0 with the aging-sweep case PASSing;
  4. no SKIP line can appear on a required case at all.

The healthy tree is exercised in-process; mutations run in temp copies via
subprocess (the file under test is never modified).
"""
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent          # tests/unit
REPO = HERE.parent.parent                                # repo root
SCRIPTS = REPO / "23-ai-workforce-blueprint" / "templates" / "role-library" / "rescue-rangers" / "scripts"
BOARD = SCRIPTS / "rescue_cc_board.py"
LEDGER = SCRIPTS / "rescue_ledger.py"

checks = []


def check(name, cond, detail=""):
    checks.append((name, cond))
    print(f"  {'✓' if cond else '✗'} {name}{(' — ' + detail) if detail and not cond else ''}")
    return cond


def run_board(script_path, cwd=None):
    r = subprocess.run([sys.executable, str(script_path), "--self-test"],
                       capture_output=True, text=True, cwd=cwd)
    return r.returncode, r.stdout + r.stderr


# 1. broken aging sweep -> nonzero, named assertion
with tempfile.TemporaryDirectory() as td:
    mut = pathlib.Path(td) / "rescue_cc_board.py"
    src = BOARD.read_text()
    broken = src.replace(
        'aged = {t["ticket_id"] for t in aging_sweep(led, 120)}',
        'aged = set()  # MUTATED: sweep returns nothing')
    check("mutation setup applied", broken != src)
    mut.write_text(broken)
    (pathlib.Path(td) / "rescue_ledger.py").write_text(LEDGER.read_text())
    rc, out = run_board(mut)
    check("broken sweep: self-test nonzero", rc != 0, f"rc={rc}")
    check("broken sweep: named assertion in output",
          "aging_sweep returned" in out, out[-300:])

# 2. missing sibling ledger -> nonzero, explicit FAIL line
with tempfile.TemporaryDirectory() as td:
    solo = pathlib.Path(td) / "rescue_cc_board.py"
    solo.write_text(BOARD.read_text())
    rc, out = run_board(solo)
    check("missing ledger: self-test nonzero", rc != 0, f"rc={rc}")
    check("missing ledger: explicit FAIL (no SKIP)",
          "aging-sweep case: FAIL" in out and "SKIP" not in out, out[-300:])

# 3. healthy tree green + the required case actually runs
rc, out = run_board(BOARD)
check("healthy board self-test green", rc == 0, out[-300:])
check("healthy aging-sweep case PASS present", "aging-sweep case: PASS" in out)
check("no SKIP anywhere on the healthy run", "SKIP" not in out)

# 4. the baseline defect class is structurally gone: no blanket except may
#    sit between the sweep assert and the caller.
src = BOARD.read_text()
between = src[src.index("aged = {t[") : src.index("aging-sweep case: PASS")]
check("no blanket except around the required sweep case",
      "except Exception" not in between)

failed = [n for n, ok in checks if not ok]
print(f"\n[rr030-board-selftest-failsonly] {'PASS' if not failed else 'FAIL'} "
      f"({len(checks) - len(failed)}/{len(checks)})")
sys.exit(1 if failed else 0)