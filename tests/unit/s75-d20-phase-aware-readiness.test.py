#!/usr/bin/env python3
"""D-20 regression: the readiness resolver must be phase-aware.

DECISIONS.md D-20 measured the defect: after 13 units were moved to
phase=IN_BATCH (heads already proven inside batch/s75-wave2 and
batch/s75-wave3), the kit's readiness.ready_units still listed all 13 and the
count stayed 18 -> 18, so a tick that obeyed readiness rebuilt batched work.

Root cause, all in swarmctl.py:
  1. action_classes() took the default merge queue from `phase in
     ("ACCEPTED", "IN_BATCH")`, so a batched unit stayed in ready_units exactly
     like an unbatched one;
  2. action_classes() repair_ready took `phase == "REPAIR" or uid in failed`,
     where `failed` is any FAIL receipt lineage, so a historical FAIL
     resurrected a batched or landed unit as ready work;
  3. plan_tick() rebuilt readiness.merge_due and readiness.ready_units from the
     per-repo merge candidates, which were still selected from `phase in
     ("ACCEPTED", "IN_BATCH")` — the tick surface leaked the same units even
     when action_classes() was gated.

The test carries its own control: the SAME fixture runs against the unpatched
kit and every control assertion must FAIL there (it must show the defect).
A green run can therefore never be a fixture that does not discriminate.
When the kit already carries the fix (marker present), the unpatched control no
longer exists; the control assertions are reported as SKIP and the fix
assertions run against the kit itself, so this stays a permanent regression.

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
import time

HERE = pathlib.Path(__file__).resolve().parent
PATCH = HERE / "s75-d20-phase-aware-readiness.patch"
KIT = pathlib.Path(os.environ.get("SWARM_KIT")
                   or pathlib.Path.home() / ".claude/skills/swarm-control")
MARKER = "NOT_READY = BATCHED | LANDED"
STATUS = {"ok": 0}
AT = "2026-10-26T12:00:00+00:00"
VERDICTS = {"A": "PASS", "B": "PASS", "M": "PASS", "W": "FAIL", "F": "FAIL", "G": "FAIL"}


def fail(msg):
    STATUS["ok"] = 1
    print("FAIL  " + msg)


def ok(msg):
    print("PASS  " + msg)


def skip(msg):
    print("SKIP  " + msg)


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


def units_fixture():
    """The D-20 shape: batched and landed rows, plus one historical FAIL on each."""
    return [
        unit("A", "ACCEPTED", accepted_at=AT),                       # genuine merge candidate
        unit("R", "READY", digest=None, head=None, base=None),        # genuine build work
        unit("B", "IN_BATCH", accepted_at=AT),                        # already in a batch
        unit("W", "WITH_BATCH", accepted_at=AT),                      # batch phase, other spelling
        unit("M", "MERGED", accepted_at=AT),                          # landed
        unit("F", "IN_BATCH", accepted_at=AT),                        # batched, historical FAIL
        unit("G", "MERGED", accepted_at=AT),                          # landed, historical FAIL
    ]


def writer_receipts(units, qc):
    for u in units:
        uid = u["id"]
        if uid in VERDICTS:
            (qc / ("%s.%s.json" % (uid, u["digest"]))).write_text(
                json.dumps(receipt(uid, u["digest"], VERDICTS[uid])))


def fixture(tmp):
    c = tmp / "control"
    qc = c / "qc"
    qc.mkdir(parents=True)
    units = units_fixture()
    writer_receipts(units, qc)
    return c, units


def kit_carries_fix():
    try:
        return MARKER in (KIT / "swarmctl.py").read_text()
    except OSError:
        return False


def modules(tmp):
    """Return the unpatched control (None once the fix is in the kit) and the fixed module."""
    if kit_carries_fix():
        return {"old": None, "new": load(KIT / "swarmctl.py", "swarmctl_kit"),
                "old_path": None, "new_path": KIT / "swarmctl.py"}
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
    if orig.read_bytes() == patched.read_bytes():
        sys.exit("FAIL  the patch changed nothing; the candidate is not applied")
    return {"old": load(orig, "swarmctl_unpatched"), "new": load(patched, "swarmctl_patched"),
            "old_path": orig, "new_path": patched}


def tick_readiness(module_path, tmp, name):
    """Run the real `tick` surface against one kit copy and return its plan JSON."""
    base = tmp / ("tick-" + name)
    control = base / "ctl"
    repo = base / "repo"
    repo.mkdir(parents=True)
    (repo / "src").mkdir()
    for d in ("tmp", "authority"):
        (base / d).mkdir()
    env = dict(os.environ, SWARM_CONTROL_BASE=str(control),
               SWARM_FALLBACK_BASE=str(base / "fb"),
               SWARM_PORTABLE_ROOT=str(base / "p"),
               SWARM_STORAGE_FORCE="FALLBACK",
               SWARM_OWNER_EVENTS_DIR=str(base / "authority"),
               TMPDIR=str(base / "tmp"))

    def run(*a):
        r = subprocess.run([sys.executable, "-I", str(module_path)] + [str(x) for x in a],
                           env=env, capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit("FAIL  tick fixture %s: %s rc=%d\n%s%s"
                     % (name, a, r.returncode, r.stdout, r.stderr))
        return r

    pid = "d20probe"
    run("init", pid)
    c = control / pid
    units = units_fixture()
    for u in units:
        if u["id"] == "R":
            u.update({"stream": "s1", "owned_paths": ["src/a.py"], "title": "R",
                      "acceptance": ["row"]})
            for k in ("digest", "head", "base"):
                u.pop(k, None)
    (c / "ledger.json").write_text(json.dumps({
        "project": {"id": pid, "repos": [{"path": str(repo), "target": "main"}],
                    "provider_limits": {}},
        "units": units}))
    (c / "census.json").write_text(json.dumps({"ts": time.time(), "complete": True,
                                               "stale": False, "agents": []}))
    qc = c / "qc"
    qc.mkdir(exist_ok=True)
    writer_receipts(units, qc)
    return json.loads(run("tick", pid).stdout)


def main():
    if not (KIT / "swarmctl.py").is_file():
        sys.exit("FAIL  no swarmctl.py under %s (set SWARM_KIT)" % KIT)
    if not PATCH.is_file() and not kit_carries_fix():
        sys.exit("FAIL  patch missing beside this test: %s" % PATCH)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="s75-d20-"))
    m = modules(tmp)
    old, new = m["old"], m["new"]
    c, units = fixture(tmp)

    ready = new.action_classes(c, units)

    # --- control: the unpatched resolver must exhibit the defect, or the test is blind.
    if old is None:
        skip("control: the kit already carries the fix; no unpatched resolver to compare")
    else:
        control = old.action_classes(c, units)
        check("B" in control["ready_units"], "control: unpatched resolver lists IN_BATCH B as ready")
        check("W" in control["ready_units"], "control: unpatched resolver revives WITH_BATCH W from a FAIL receipt")
        check("F" in control["repair_ready"], "control: unpatched resolver revives batched F from a FAIL receipt")
        check("G" in control["ready_units"], "control: unpatched resolver lists landed G as ready")
        check(old.action_classes(c, units, merge_ids=["A", "B", "M"])["merge_due"] == ["A", "B", "M"],
              "control: unpatched resolver trusts explicit merge_ids blindly")

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
    check(new.action_classes(c, units, merge_ids=["A", "B", "M"])["merge_due"] == ["A"],
          "explicit merge_ids are gated by the unit's phase, never by its id")
    check("B" in ready["batch_due"],
          "a batched unit with a valid receipt is reported under batch_due instead of being dropped")

    # --- the fix must not swallow real work.
    check("A" in ready["merge_due"] and "A" in ready["ready_units"],
          "an ACCEPTED unit with a valid receipt stays a merge candidate")
    check("R" in ready["build_ready"] and "R" in ready["ready_units"],
          "a READY unit with no owner stays build work")
    check(ready["ready_units_n"] == len(set(ready["ready_units"])),
          "ready_units stays de-duplicated")

    # --- the tick surface: plan_tick rebuilds readiness, so it must be gated the same way.
    t_old = tick_readiness(m["old_path"], tmp, "old") if m["old_path"] else None
    t_new = tick_readiness(m["new_path"], tmp, "new")
    if t_old is None:
        skip("control: the kit already carries the fix; tick control not available")
    else:
        check("B" in (t_old.get("readiness") or {}).get("ready_units", []),
              "control: tick readiness lists IN_BATCH B as ready")
        check(any("B" in (r.get("candidates") or []) for r in t_old.get("merge_due") or []),
              "control: tick offers batched B as a merge-claim candidate")
        check("G" in (t_old.get("readiness") or {}).get("ready_units", []),
              "control: tick readiness lists landed G as ready")
    tn = t_new.get("readiness") or {}
    check("B" not in tn.get("ready_units", []), "tick readiness: IN_BATCH B is never ready work")
    check("M" not in tn.get("ready_units", []), "tick readiness: MERGED M is never ready work")
    check("F" not in tn.get("repair_ready", []) and "G" not in tn.get("repair_ready", []),
          "tick readiness: a FAIL on a batched or landed unit never revives repair work")
    check(not any("B" in (r.get("candidates") or []) for r in t_new.get("merge_due") or []),
          "tick: no batched unit is offered as a merge-claim candidate")
    check("B" in (tn.get("batch_due") or []),
          "tick readiness: batched B is reported under batch_due")
    check("A" in tn.get("ready_units", []), "tick readiness: ACCEPTED A stays ready work")
    check("R" in tn.get("build_ready", []), "tick readiness: READY R stays build work")

    if STATUS["ok"]:
        print("D20 REGRESSION FAIL")
        return 1
    print("D20 REGRESSION PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
