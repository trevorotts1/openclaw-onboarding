#!/usr/bin/env python3
"""D9 (S75): a recorded WW-21 operator decision releases the PICK.

The music stage honours a valid, digest-bound operator decision
(`factory._song_hold`), but the PICK did not: after music completed through
`--operator-decision`, `song_choices.record_pick` still refused the very
variant the decision named (ACCEPTANCE_NOT_PROVEN / the per-variant refusal),
and every later stage stayed refused with PRODUCTION_ORDER_VIOLATION.

What this proves:
  * a valid decision that NAMES the picked variant lets the pick succeed and
    writes `operator_decision` into pick.json; `refusal()` is then None;
  * a valid decision naming a DIFFERENT variant still refuses;
  * a tampered measured-evidence digest still refuses;
  * no decision still refuses;
  * the OFFERED map is unchanged -- no take is offered, no PASS is written.

A decision never marks a measured gate PASS: the take record's own FAIL
verdicts are read back UNTOUCHED.

Run: cd scripts/core/song_choices && HOME=$(mktemp -d) python3 test_pick_operator_decision_s75.py
"""
import json
import os
import sys
import tempfile

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for _sub in ("", "song_choices", "song_dispatch"):
    _p = os.path.join(CORE, _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)
sys.path.insert(0, CORE)

from song_dispatch import song_dispatch as SD      # noqa: E402
from song_choices import song_choices as SC        # noqa: E402

REQUIRED = ("D1", "D2", "D3", "D4", "D5")
checks, fails = [], []

def check(name, cond, detail=""):
    checks.append(name)
    if not cond:
        fails.append("%s: %s" % (name, detail))
    print("  %-70s %s" % (name, "ok" if cond else "FAIL"))

def _binding():
    return {"export_digest": os.urandom(32).hex(), "creative_revision": "d9-r1",
            "profile_revision": "1.0.0"}

def _run(tmp, vids=("v1",)):
    """A run whose offered map is EMPTY and whose takes FAIL: state required,
    variants {'1':'v1'} (and 2 -> v2 when asked), one presented file per
    variant named '<n> - Title - NOT PASSED.mp3'."""
    run = os.path.join(tempfile.mkdtemp(dir=tmp, prefix="d9-"), "run")
    os.makedirs(os.path.join(run, "song-choices"))
    os.makedirs(os.path.join(run, "music"))
    presented, variants = [], {}
    for i, v in enumerate(vids, 1):
        name = "%d - Title - NOT PASSED.mp3" % i
        f = os.path.join(run, "song-choices", name)
        with open(f, "wb") as fh:
            fh.write(("take for %s" % v).encode())
        presented.append(f)
        variants[str(i)] = v
        b = _binding()
        results = {g: {"verdict": "PASS", "binding": dict(b)} for g in REQUIRED}
        results["D5"] = {"verdict": "FAIL", "binding": dict(b)}
        SD.record_acceptance(run, v, b, results)
    with open(os.path.join(run, "song-choices", "state.json"), "w") as fh:
        json.dump({"required": True, "offered": {}, "variants": variants,
                   "presented": presented}, fh)
    return run

def _digest(run, vids):
    return SD.sha256_evidence_records(
        {v: SD.measure_evidence_digest(run, v) or "" for v in vids})

def _decision(run, vids, digest=None):
    return {"decision": "ACCEPTED_RISK", "operator": "operator",
            "at_utc": "2026-11-19T12:00:00Z", "gates_not_proven": ["D5"],
            "variants": list(vids),
            "measured_evidence_digest": digest if digest is not None else _digest(run, vids),
            "reason": "D5 measured FAIL across estimators; the owner accepts the "
                      "run with D5 not proven"}

def _offered(run):
    with open(os.path.join(run, "song-choices", "state.json")) as fh:
        return json.load(fh).get("offered")

def _pick(run):
    p = os.path.join(run, "song-choices", "pick.json")
    if not os.path.isfile(p):
        return None
    with open(p) as fh:
        return json.load(fh)

def _refused(fn):
    """(refused?, message) — a ChoiceError is the refusal."""
    try:
        fn()
    except SC.ChoiceError as exc:
        return True, str(exc)
    return False, ""

def main():
    tmp = tempfile.mkdtemp(prefix="d9-pick-")

    # --- case 1: a valid decision naming v1 releases the pick ---------------
    run = _run(tmp)
    before_offered = _offered(run)
    acc_before = json.load(open(os.path.join(run, "music", "acceptance", "v1.json")))
    check("no decision: pick refused", _refused(lambda: SC.record_pick(run, "1"))[0])
    check("no decision: later stages refused", SC.refusal(run) is not None,
          SC.refusal(run))
    SD.record_operator_decision(run, _decision(run, ["v1"]))
    label = SC.record_pick(run, "1")
    check("pick 1 succeeds under the decision", label.startswith("1"), label)
    doc = _pick(run)
    check("pick.json records the decision digest",
          doc and doc.get("operator_decision") == _decision(run, ["v1"])["measured_evidence_digest"],
          doc)
    check("pick.json variant is v1", doc and doc.get("variant") == "v1", doc)
    check("refusal() is None after the pick", SC.refusal(run) is None, SC.refusal(run))
    check("offered map unchanged", _offered(run) == before_offered, _offered(run))
    acc_after = json.load(open(os.path.join(run, "music", "acceptance", "v1.json")))
    check("take record UNTOUCHED (no PASS written)", acc_after == acc_before,
          acc_after.get("results", {}).get("D5"))

    # --- case 2: a valid decision naming v2 still refuses pick 1 -----------
    run = _run(tmp, vids=("v1", "v2"))
    SD.record_operator_decision(run, _decision(run, ["v2"]))
    refused, why = _refused(lambda: SC.record_pick(run, "1"))
    check("decision naming v2 does not release v1", refused, why)
    check("no pick.json written", _pick(run) is None, _pick(run))

    # --- case 3: a tampered digest still refuses ---------------------------
    run = _run(tmp)
    bad = _decision(run, ["v1"], digest="ab" * 32)
    p = SD.operator_decision_path(run)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as fh:
        json.dump(bad, fh)
    refused, why = _refused(lambda: SC.record_pick(run, "1"))
    check("tampered digest still refuses", refused, why)
    check("tampered digest: later stages refused", SC.refusal(run) is not None,
          SC.refusal(run))

    # --- case 4: no decision still refuses --------------------------------
    run = _run(tmp)
    refused, why = _refused(lambda: SC.record_pick(run, "1"))
    check("no decision still refuses", refused, why)
    check("no decision: offered map untouched", _offered(run) == {}, _offered(run))

    print("\n%d checks, %d failures" % (len(checks), len(fails)))
    for f in fails:
        print("FAIL:", f)
    return 1 if fails else 0

def test_pick_operator_decision():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
