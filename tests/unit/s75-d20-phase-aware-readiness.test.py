#!/usr/bin/env python3
"""D-20 regression: the readiness resolver must be phase-aware.

DECISIONS.md D-20 measured the defect: after 13 units were moved to
phase=IN_BATCH (heads already proven inside batch/s75-wave2 and
batch/s75-wave3), the kit's readiness.ready_units still listed all 13 and the
count stayed 18 -> 18, so a tick that obeyed readiness rebuilt batched work.

Root cause, both in swarmctl.py action_classes():
  1. the default merge queue was taken from `phase in ("ACCEPTED", "IN_BATCH")`,
     so a batched unit stayed in ready_units exactly like an unbatched one;
  2. repair_ready took `phase == "REPAIR" or uid in failed`, where `failed` is
     any FAIL receipt lineage, so a historical FAIL resurrected a batched or
     landed unit as ready work.

The test carries its own control: the SAME fixture runs against the unpatched
resolver and every patched-passing assertion must FAIL there. A green run can
therefore never be a fixture that does not discriminate.

Run:  python3 -I tests/unit/s75-d20-phase-aware-readiness.test.py
Env:  SWARM_KIT=<path to the swarm-control kit>
      (default: ~/.claude/skills/swarm-control)
"""
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
PATCH = HERE / "s75-d20-phase-aware-readiness.patch"
KIT = pathlib.Path(os.environ.get("SWARM_KIT")
                   or pathlib.Path.home() / ".claude/skills/swarm-control")
STATUS = {"ok": 0}


def fail(msg):
    STATUS["ok"] = 1
    print("FAIL  " + msg)


def ok(msg):
    print("PASS  " + msg)


def check(cond, msg):
    ok(msg) if cond else fail(msg)
    return bool(cond)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def receipt(unit, digest, verdict="PASS"):
    return {"unit": unit, "attempt": 1, "digest": digest,
            "head": "h-" + unit, "base": "b0", "checker": "qc-1",
            "author": "builder-1", "model": "m", "rows": ["row1"],
            "checks": [{"cmd": "run", "exit": 0 if verdict == "PASS" else 1,
                        "status": verdict}],
            "defects": [], "verdict": verdict}


def unit(uid, phase, **extra):
    row = {"id": uid, "phase": phase, "digest": "d-" + uid, "attempt": 1,
           "head": "h-" + uid, "base": "b0", "author": "builder-1"}
    row.update(extra)
    return row


def fixture(tmp):
    """The D-20 shape: batched and landed rows, plus one historical FAIL on each."""
    c = tmp / "control"
    (c / "qc").mkdir(parents=True)
    at = "2026-10-26T12:00:00+00:00"
    units = [
        unit("A", "ACCEPTED", accepted_at=at),            # genuine merge candidate
        unit("R", "READY"),                               # genuine build work
        unit("B", "IN_BATCH", accepted_at=at),            # already in a batch
        unit("W", "WITH_BATCH", accepted_at=at),          # batch phase, other spelling
        unit("M", "MERGED", accepted_at=at),              # landed
        unit("F", "IN_BATCH", accepted_at=at),            # batched, historical FAIL
        unit("G", "MERGED", accepted_at=at),              # landed, historical FAIL
    ]
    pass_units, fail_units = {"A", "B", "M"}, {"F", "G", "W"}
    for u in units:
        verdict = "FAIL" if u["id"] in fail_units else "PASS"
        path = c / "qc" / ("%s.%s.json" % (u["id"], u["digest"]))
        path.write_text(json.dumps(receipt(u["id"], u["digest"], verdict)))
    return c, units, pass_units, fail_units


def patched_module(tmp):
    orig = tmp / "orig" / "swarmctl.py"
    patched = tmp / "patched" / "swarmctl.py"
    orig.parent.mkdir()
    patched.parent.mkdir()
    shutil.copyfile(KIT / "swarmctl.py", orig)
    shutil.copyfile(KIT / "swarmctl.py", patched)
    r = subprocess.run(["patch", "-p1", "-s", "-i", str(PATCH), "-d", str(patched.parent)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("FAIL  could not apply %s (rc %d)\n%s%s"
                 % (PATCH.name, r.returncode, r.stdout, r.stderr))
    before = orig.read_bytes()
    after = patched.read_bytes()
    if before == after:
        sys.exit("FAIL  the patch changed nothing; the candidate is not applied")
    return load(orig, "swarmctl_unpatched"), load(patched, "swarmctl_patched")


def main():
    if not (KIT / "swarmctl.py").is_file():
        sys.exit("FAIL  no swarmctl.py under %s (set SWARM_KIT)" % KIT)
    if not PATCH.is_file():
        sys.exit("FAIL  patch missing beside this test: %s" % PATCH)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="s75-d20-"))
    old, new = patched_module(tmp)
    c, units, _, _ = fixture(tmp)

    control = old.action_classes(c, units)
    ready = new.action_classes(c, units)

    # --- control: the unpatched resolver must exhibit the defect, or the test is blind.
    check("B" in control["ready_units"], "control: unpatched resolver lists IN_BATCH B as ready")
    check("W" in control["ready_units"], "control: unpatched resolver revives WITH_BATCH W from a FAIL receipt")
    check("F" in control["repair_ready"], "control: unpatched resolver revives batched F from a FAIL receipt")
    check("G" in control["ready_units"], "control: unpatched resolver lists landed G as ready")

    # --- the fix: phase decides.
    check("B" not in ready["ready_units"], "IN_BATCH B is never in ready_units")
    check("W" not in ready["ready_units"] and "W" not in ready["repair_ready"],
          "WITH_BATCH W is never in ready_units, even with a historical FAIL")
    check("M" not in ready["ready_units"], "MERGED M is never in ready_units")
    check("F" not in ready["ready_units"] and "F" not in ready["repair_ready"],
          "a FAIL receipt on an IN_BATCH unit never revives it as repair work")
    check("G" not in ready["ready_units"] and "G" not in ready["repair_ready"],
          "a FAIL receipt on a MERGED unit never revives it as repair work")
    check("M" not in ready["merge_due"] and "B" not in ready["merge_due"],
          "batched and landed units are never in merge_due")
    check("B" in ready["batch_due"],
          "a batched unit with a valid receipt is reported under batch_due instead of being dropped")

    # --- the fix must not swallow real work.
    check("A" in ready["merge_due"] and "A" in ready["ready_units"],
          "an ACCEPTED unit with a valid receipt stays a merge candidate")
    check("R" in ready["build_ready"] and "R" in ready["ready_units"],
          "a READY unit with no owner stays build work")
    check(ready["ready_units_n"] == len(set(ready["ready_units"])),
          "ready_units stays de-duplicated")

    if STATUS["ok"]:
        print("D20 REGRESSION FAIL")
        return 1
    print("D20 REGRESSION PASS")
    return 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        pass
    sys.exit(code)
