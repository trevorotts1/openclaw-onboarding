#!/usr/bin/env python3
"""BATCH-5 redesign #10: factory runs the continuity stage's OWN reconciler.

PR #2414 carried an inline `_proven_continuity` copy in factory.py. The stage
already owns that predicate (`character_continuity.stage.proven`) and its
`register()` was tested -- but nothing ever CALLED it, so factory's
`_RECONCILIERS` had no continuity-bible entry and a run that finished music
could never leave continuity-bible, however complete its records.

Pinned here:
  * factory's registry carries the stage's own predicate (identity, not a copy);
  * _reconcile_stages advances continuity-bible from PROVEN records;
  * missing records prove nothing and move nothing (fail closed).

stdlib only, zero paid calls.

Run from the skill root: python3 scripts/core/intake_preflight/test_continuity_reconciler_b5.py
"""
import importlib
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for _p in (CORE, os.path.join(CORE, "character_continuity")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

F = importlib.import_module("intake_preflight.factory")
ST = importlib.import_module("character_continuity.stage")
SS = importlib.import_module("state_store")

FAILS = []


def check(name, got, want):
    if got == want:
        print("ok %s" % name)
    else:
        print("FAIL %s: got %r want %r" % (name, got, want))
        FAILS.append(name)


REC = {"schema_version": "1.0.0", "check_id": "continuity-dna-1",
       "run_id": "run-b5", "stage": "continuity-bible", "check": "continuity",
       "verdict": "PASS",
       "evidence": {"summary": "Character DNA, product DNA and style bible "
                               "agree across every planned shot."},
       "checker_version": "1.0.0",
       "reviewer": {"identity": "qc-reviewer-1", "session": "s1",
                    "authority": "qc"}}


def _run(with_records=True):
    run = tempfile.mkdtemp(prefix="b5-cont-")
    os.makedirs(os.path.join(run, "continuity"))
    os.makedirs(os.path.join(run, "control"))
    if with_records:
        with open(os.path.join(run, "continuity", "qc-records.json"), "w") as f:
            json.dump([REC], f)
        with open(os.path.join(run, "continuity", "makers.json"), "w") as f:
            json.dump({"continuity-dna-1": "agent-writer-1"}, f)
    db = os.path.join(run, "control", "state.sqlite3")
    ids = list(F.CANONICAL_STAGES)
    with SS.Store(db) as st:
        st.init_run("run-b5", ids)
    return run


def main():
    check("1: continuity-bible is in the reconciler registry",
          "continuity-bible" in F._RECONCILIERS, True)
    check("2: it is the stage's own predicate, not a factory copy",
          F._RECONCILIERS.get("continuity-bible"), ST.proven)

    run = _run()
    got = {"continuity-bible": "NOT_STARTED"}
    rows, fresh = F._reconcile_stages(run, got)
    moved = [r for r in rows if r.get("stage") == "continuity-bible"]
    check("2b: no inline _proven_continuity copy survives in factory",
          hasattr(F, "_proven_continuity"), False)

    check("3: proven records reconcile the row",
          bool(moved) and moved[0].get("to_state"), "COMPLETE")
    check("4: the fresh state map says COMPLETE",
          fresh.get("continuity-bible"), "COMPLETE")

    run2 = _run(with_records=False)
    rows2, fresh2 = F._reconcile_stages(run2, {"continuity-bible": "NOT_STARTED"})
    check("5: no records -> no continuity move",
          [r for r in rows2 if r.get("stage") == "continuity-bible"], [])
    check("6: the row is untouched",
          fresh2.get("continuity-bible"), "NOT_STARTED")

    print()
    if FAILS:
        print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
