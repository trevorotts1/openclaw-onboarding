#!/usr/bin/env python3
"""Batch-8c proof 1: the B7 Gate-4 recap hold sits in front of BOTH handout paths.

Re-runnable at the batch head. Stdlib only, no network, no provider call.

For each of two handout variants of the SAME run shape at `video-generation`
with the storyboard approved:
  * Agnes path  - the run carries an `agnes.answer = yes` receipt, so `next`
                  would hand out the Agnes segment jobs (and the KIE Kling row
                  for the lip-sync windows);
  * KIE path    - no Agnes receipt, so `next` hands out the KIE runbook row.

Step 1: with `control/production-go.json` present, `next` returns ok and a command.
Step 2: delete ONLY that file (the recap record itself stays), run `next` again.
        Expected: outcome=rejected, reason_code=PRODUCTION_GO_MISSING, and NO
        command on either path. That refusal comes from `final_recap.hold`
        via `_recap_hold`, so it proves the hold executes before the handout.

Correction history, kept because a receipt should show what was asserted first:
the first version of this proof expected a reason_code starting with
`FINAL_RECAP`. No such code exists on this path - the hold's missing-Go code is
`PRODUCTION_GO_MISSING`. The assertion was corrected to the real code after the
probe returned it; the behaviour was right and the expectation was wrong.

Run from the repo root:
    python3 tests/w10-canary/evidence/B8C/proof_recap_hold.py
Exit 0 = both paths hold; 1 = at least one assertion failed.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[4]
CORE = REPO / "75-drama-song-ad-factory" / "scripts" / "core"
FACTORY = CORE / "intake_preflight" / "factory.py"
sys.path.insert(0, str(CORE / "intake_preflight"))

import test_factory_method_agnes as T  # noqa: E402  (fixture builder of the shipped tests)

FAILS = []

def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (" :: " + detail if detail else ""))
    if not cond:
        FAILS.append(name)

def case(td, label, agnes):
    run = T.make_run(td, "video-generation", method=T.method(), agnes=agnes,
                     storyboard="approved")
    cmd = "%s %s next --run-dir %s" % (Path(sys.executable).name, FACTORY, run)
    print("\n== %s\n   $ %s" % (label, cmd))
    p, doc = T.next_env(run)
    data = doc.get("data") or {}
    hands_out = bool(data.get("command")) or bool(
        ((data.get("agnes") or {}).get("segment_jobs")))
    print("   rc=%d outcome=%r reason=%r command=%r"
          % (p.returncode, doc.get("outcome"), doc.get("reason_code"),
             data.get("command")))
    check(label + ": with the Go, the stage hands out a command",
          p.returncode == 0 and hands_out)

    go = run / "control" / "production-go.json"
    check(label + ": control/production-go.json existed", go.is_file())
    go.unlink()

    print("   %s" % cmd.replace(str(run), str(run)) + "   # after deleting control/production-go.json")
    p2, doc2 = T.next_env(run)
    d2 = doc2.get("data") or {}
    reason = str(doc2.get("reason_code") or "")
    still = bool(d2.get("command")) or bool(((d2.get("agnes") or {}).get("segment_jobs")))
    print("   rc=%d outcome=%r reason=%r command=%r"
          % (p2.returncode, doc2.get("outcome"), reason, d2.get("command")))
    check(label + ": without the Go the recap hold refuses the stage",
          doc2.get("outcome") == "rejected" and reason == "PRODUCTION_GO_MISSING",
          reason)
    check(label + ": without the Go NO command is handed out", not still,
          json.dumps({"command": d2.get("command")}))

def main():
    with tempfile.TemporaryDirectory(prefix="b8c-recap-hold-") as td:
        case(td, "AGNES-yes handout path", {"answer": "yes"})
        case(td, "KIE runbook-row handout path", None)
    print("\nproof_recap_hold: %d check(s) failed" % len(FAILS))
    return 1 if FAILS else 0

if __name__ == "__main__":
    sys.exit(main())
