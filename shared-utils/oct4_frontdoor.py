#!/usr/bin/env python3
"""oct4_frontdoor.py — the shared repair-and-gate stage every update route runs.

Order (OCT4 repo-fix issue #10): after onboarding has been brought current and
any installed 999-setup refreshed, each route runs

    1. repair runner:
       repair-placeholder-sops.py   (issue #5)
    -> repair-userlinks.py          (issue #6)
    -> repair-directors-doctrine.py (issue #7)
    -> ensure-revenue-goal.py       (issue #9)
    -> author-missing-sops.py       (issue #1, the remaining gaps)
    2. health gate: scripts/health/library-gate-check.sh (issue #11)

Each callee path is the integration contract from the OCT4 order, issues #5-#7,
#9 and #11 — invoked, never re-implemented. A callee that is MISSING on this
box is reported as {"present": false} and the stage is marked "incomplete-gaps"
(a known gap, surfaced to the operator), never silently dropped and never a
false pass.

Idempotent: the repair scripts are dry-run-safe and idempotent; running this
stage again after a clean repair changes nothing.

Exit contract of run_repair_runner / run_health_gate / run_full_stage: they
return dicts, never raise, never write outside the box's OpenClaw root, and
never touch openclaw.json. The repair scripts each print their own counts; the
tail of their output is kept in the report.

Callee exit codes read as: 0 = ok; 2 = content gap needs attention; 3 = gaps
left for a human / unresolved; 4 = queued inline work files (author); anything
else = that stage failed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Every callee path is the OCT4 integration contract; see the module docstring.
REPAIR_PY = (
    ("placeholder-sops",
     "23-ai-workforce-blueprint/scripts/repair/repair-placeholder-sops.py",
     []),
    ("userlinks",
     "23-ai-workforce-blueprint/scripts/repair/repair-userlinks.py",
     []),
    ("directors-doctrine",
     "23-ai-workforce-blueprint/scripts/repair/repair-directors-doctrine.py",
     []),
    ("revenue-goal",
     "23-ai-workforce-blueprint/scripts/repair/ensure-revenue-goal.py",
     []),
    ("author-missing-sops",
     "23-ai-workforce-blueprint/scripts/author-missing-sops.py",
     []),
)
HEALTH_GATE_SH = "scripts/health/library-gate-check.sh"

# The repair scripts are maintenance: they must never emit to a client chat,
# whatever the box's chat config says (the same suppression the fleet roll
# exports into update-skills.sh; qc-completeness.sh treats this var as a hard
# send-suppression gate).
MAINTENANCE_ENV = {"OPENCLAW_MAINTENANCE_SILENT": "1"}

EXIT_MEANING = {
    0: "ok",
    2: "needs-attention",
    3: "gaps-left-for-human",
    4: "queued-inline-work",
    5: "cannot-verify",
}


def _oc_root() -> Path:
    """This box's OpenClaw root (same resolution the platform layer pins)."""
    env_root = os.environ.get("OPENCLAW_ROOT", "").strip()
    if env_root:
        return Path(env_root)
    if Path("/data/.openclaw").is_dir():
        return Path("/data/.openclaw")
    return Path.home() / ".openclaw"


def _skills_dir(root: Path) -> Path:
    """The installed skills tree: <root>/skills, or the legacy box layout
    ~/clawd/skills when the standard tree does not exist."""
    std = root / "skills"
    if std.is_dir():
        return std
    legacy = Path.home() / "clawd" / "skills"
    if legacy.is_dir():
        return legacy
    return std


def _maintenance_env() -> dict:
    return {**os.environ, "OPENCLAW_MAINTENANCE_SILENT": "1"}


def _run(cmd: list[str], timeout: int) -> dict:
    """Run one callee; never raises. detail keeps the head of stderr first:
    the repair scripts print their counts to stdout but their verdicts to
    stderr, and the verdict is what an operator needs."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           env=_maintenance_env())
    except FileNotFoundError:
        return _result(127, "python3 / interpreter missing")
    except subprocess.TimeoutExpired:
        return _result(124, f"timed out after {timeout}s")
    except OSError as e:
        return _result(1, str(e)[-200:])
    detail = ((r.stderr or "") + "\n" + (r.stdout or "")).strip()
    return _result(r.returncode, detail)


def _result(exit_code: int, detail: str) -> dict:
    return {"exit": exit_code,
            "meaning": EXIT_MEANING.get(exit_code, "failed"),
            "present": True,
            "detail": detail[:2000]}


def run_repair_runner(skills_dir: Path) -> dict:
    """Stage R: run every repair script, then the author of remaining gaps.

    Each entry records present/exit/meaning/detail. A missing script is a
    skip-by-design entry ({present: false}), never silently dropped — the
    stage result says "incomplete-gaps" so nobody reads a partial repair as a
    full one.
    """
    steps: dict = {}
    for name, rel, extra in REPAIR_PY:
        p = skills_dir / rel
        if not p.is_file():
            steps[name] = {"present": False, "path": rel}
            continue
        steps[name] = _run([sys.executable or "python3", str(p), *extra],
                           timeout=5400 if name == "author-missing-sops" else 1800)

    gate_count = sum(1 for s in steps.values() if s.get("present") and
                     s.get("meaning") == "ok")
    missing = [n for n, s in steps.items() if not s.get("present")]
    failing = [n for n, s in steps.items()
               if s.get("present") and s.get("meaning") not in
               ("ok", "needs-attention", "gaps-left-for-human", "queued-inline-work",
                "cannot-verify")]
    if missing:
        status = "incomplete-gaps"   # installed tree lacks stage scripts: report, never fail the route
    elif gate_count == len(REPAIR_PY):
        status = "ok"
    else:
        status = "ran-with-notes"
    return {"status": status, "steps": steps,
            "missing": missing, "failing": failing}


def run_health_gate(skills_dir: Path) -> dict:
    """Stage G: the library-standard health gate (issue #11). Read-only.

    Exit 0 = box meets the library standard (warnings allowed); 1 = at least
    one item failed; 5 = cannot tell (undetermined — reported, never read as
    a pass); anything else = the gate itself failed to run.
    """
    p = skills_dir / HEALTH_GATE_SH
    if not p.is_file():
        return {"present": False, "path": HEALTH_GATE_SH}
    r = _run(["bash", str(p)], timeout=900)
    verdict = r["meaning"]
    if r["exit"] == 0:
        verdict = "pass"
    elif r["exit"] == 1:
        verdict = "fail"
    elif r["exit"] == 5:
        verdict = "undetermined"
    r["meaning"] = verdict
    return r


def run_full_stage(skills_dir: Path | None = None) -> dict:
    """The whole shared stage: repairs, then the health gate."""
    skills_dir = Path(skills_dir) if skills_dir else _skills_dir(_oc_root())
    repair = run_repair_runner(skills_dir)
    gate = run_health_gate(skills_dir)
    status = "ok"
    if gate.get("present") is False:
        status = "incomplete-gaps"   # gate script absent: known gap surfaced to the operator
    elif gate["meaning"] == "fail":
        status = "gate-failed"
    elif gate["meaning"] == "undetermined":
        status = "gate-undetermined"
    elif repair["status"] != "ok":
        status = "ran-with-notes"
    return {"status": status, "repair": repair, "gate": gate,
            "skills_dir": str(skills_dir)}


# ── CLI ───────────────────────────────────────────────────────────────────────

def _selftest() -> int:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # 1. Missing callees are reported, never executed, never silent.
        rep = run_repair_runner(root)
        assert rep["status"] == "incomplete-gaps", rep
        assert rep["missing"] == [n for n, _p, _x in REPAIR_PY], rep
        assert all(s["present"] is False for s in rep["steps"].values()), rep
        # 2. run_health_gate over an empty skills dir reports the absent gate.
        g = run_health_gate(root)
        assert g["present"] is False, g
        # 3. A callee that exits 3 is read as gaps-left-for-human, still "ok-family"
        with tempfile.TemporaryDirectory() as td2:
            sd = Path(td2)
            # a real script on disk: present + runs
            rel = REPAIR_PY[0][1]
            (sd / rel).parent.mkdir(parents=True, exist_ok=True)
            (sd / rel).write_text('import sys; print("3 gaps left"); sys.exit(3)\n')
            rep2 = run_repair_runner(sd)
            step = rep2["steps"]["placeholder-sops"]
            assert step["present"] is True and step["meaning"] == "gaps-left-for-human", step
            assert rep2["missing"] == [n for n, _p, _x in REPAIR_PY][1:], rep2["missing"]
            assert rep2["failing"] == [], rep2["failing"]
            # a non-contract exit code is a failing stage
            (sd / rel).write_text('import sys; sys.exit(9)\n')
            rep3 = run_repair_runner(sd)
            assert rep3["steps"]["placeholder-sops"]["meaning"] == "failed", rep3["steps"]
            assert "placeholder-sops" in rep3["failing"], rep3
            # 4. the gate contract over a real file
            (sd / HEALTH_GATE_SH).parent.mkdir(parents=True, exist_ok=True)
            (sd / HEALTH_GATE_SH).write_text('#!/bin/sh\nexit 1\n')
            g2 = run_health_gate(sd)
            assert g2["meaning"] == "fail", g2
            (sd / HEALTH_GATE_SH).write_text('#!/bin/sh\nexit 5\n')
            assert run_health_gate(sd)["meaning"] == "undetermined"
            (sd / HEALTH_GATE_SH).write_text('#!/bin/sh\nexit 0\n')
            assert run_health_gate(sd)["meaning"] == "pass"
            full = run_full_stage(sd)
            assert full["status"] in ("ok", "ran-with-notes"), full  # author stage absent here -> notes
    # 5. _oc_root honors OPENCLAW_ROOT
    old = os.environ.get("OPENCLAW_ROOT")
    os.environ["OPENCLAW_ROOT"] = "/nonexistent-oc-root"
    try:
        assert str(_oc_root()) == "/nonexistent-oc-root"
    finally:
        if old is None:
            os.environ.pop("OPENCLAW_ROOT", None)
        else:
            os.environ["OPENCLAW_ROOT"] = old
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Shared repair-runner + health-gate stage")
    ap.add_argument("--json", action="store_true", help="print the report as one JSON object")
    ap.add_argument("--selftest", action="store_true", help="run the built-in self-check and exit")
    a = ap.parse_args(argv)
    if a.selftest:
        rc = _selftest()
        print("oct4_frontdoor.py --selftest: PASS" if rc == 0 else "oct4_frontdoor.py --selftest: FAIL")
        return rc
    report = run_full_stage()
    if a.json:
        print(json.dumps(report, indent=2))
    else:
        print("[oct4-frontdoor] stage status: %s" % report["status"])
        for name, s in report["repair"]["steps"].items():
            print("[oct4-frontdoor]   repair %-22s %s" % (name, s.get("meaning", "absent")))
        print("[oct4-frontdoor]   gate                   %s" % report["gate"].get("meaning", "absent"))
    return 0 if report["status"] in ("ok", "ran-with-notes", "incomplete-gaps") else 1


if __name__ == "__main__":
    sys.exit(main())