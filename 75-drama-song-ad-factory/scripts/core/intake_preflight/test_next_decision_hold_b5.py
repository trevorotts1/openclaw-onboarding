#!/usr/bin/env python3
"""BATCH-5 redesign #8/#9: ONE acceptance hold, and `next` honours the decision.

`factory.py music --action complete` records operator-decision.json and opens
the WW-21 acceptance hold through `_song_hold`. `factory.py next` kept its own
copy of the gate (`song_choices.refusal(...) or constituent_hold(...)`) and so
re-read the hold closed: a run the operator had accepted advanced from
`music --action complete` and then refused forever at `next` with
ACCEPTANCE_NOT_PROVEN. Two gates, one artifact.

This suite pins the single implementation:
  * a recorded, well-formed operator-decision.json opens the hold in `next`;
  * a MALFORMED decision opens nothing (fail closed);
  * the measured gate is still measured-not-proven in the take record -- the
    decision never writes a PASS (WW-21 L2), so nothing here re-labels.

stdlib only, zero paid calls.

Run from the skill root: python3 scripts/core/intake_preflight/test_next_decision_hold_b5.py
"""
import importlib
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for _p in (CORE, os.path.join(CORE, "song_dispatch")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

T = importlib.import_module("test_operator_decision_v2973")
F = T.F
SD = T.SD

FAILS = []


def check(name, got, want):
    if got == want:
        print("ok %s" % name)
    else:
        print("FAIL %s: got %r want %r" % (name, got, want))
        FAILS.append(name)


def _next_env(run):
    return F.cmd_next(type("A", (), {"run_dir": run, "method": None,
                                    "run_id": T.RID})())


def _accepted_run(tmp):
    """music COMPLETE through the recorded acceptance path."""
    run = T.new_run(tmp)
    F.music_stage(run, T.OWNER, "start")
    T._decfile(run, T._decision(run))
    r = F.music_stage(run, T.OWNER, "complete", qc=T._qc(),
                      operator_decision=T._decision(run))
    assert r["outcome"] == "ok", r
    return run


def main():
    tmp = tempfile.mkdtemp(prefix="b5-next-hold-")

    # 1. the decision opens the hold in `next`, not only in music --complete
    run = _accepted_run(tmp)
    env = _next_env(run)
    check("1: next advances a run whose acceptance hold was decided",
          env["reason_code"] == "ACCEPTANCE_NOT_PROVEN", False)
    check("2: next still hands out the next stage", env["outcome"], "ok")

    # 3. the measured gate was never relabelled PASS (WW-21 L2)
    rec = json.load(open(os.path.join(run, "music", "acceptance", "v1.json")))
    check("3: D5 stays measured-not-proven in the take record",
          rec["results"]["D5"]["verdict"], "UNMEASURED")

    # 4. a MALFORMED decision opens nothing: the same run without a readable
    #    decision is refused exactly as before the change.
    run2 = T.new_run(tmp)
    F.music_stage(run2, T.OWNER, "start")
    r2 = F.music_stage(run2, T.OWNER, "complete", qc=T._qc())   # holds
    check("4: without a decision the music stage holds",
          r2["outcome"] != "ok"
          and (T._row(run2) or {}).get("state") in
          ("FAILED_BLOCKED", "WAITING_APPROVAL"), True)

    run3 = _accepted_run(tmp)
    p = SD.operator_decision_path(run3)
    with open(p, "w", encoding="utf-8") as f:
        f.write("{not json")
    env3 = _next_env(run3)
    check("5: a malformed decision never opens the hold",
          env3["reason_code"], "ACCEPTANCE_NOT_PROVEN")

    # 6. a decision that names a gate the run cannot claim is not a decision
    run4 = _accepted_run(tmp)
    T._decfile(run4, dict(T._decision(run4), gates_not_proven=["D9"]))
    env4 = _next_env(run4)
    check("6: an unknown gate name opens nothing",
          env4["reason_code"] == "ACCEPTANCE_NOT_PROVEN", True)

    print()
    if FAILS:
        print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
