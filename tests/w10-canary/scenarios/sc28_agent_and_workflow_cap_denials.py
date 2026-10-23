#!/usr/bin/env python3
"""sc28_agent_and_workflow_cap_denials.py — acceptance row SC-28 (S75-W10-U1).

Condition (SCENARIO-MATRIX.json, row SC-28, verbatim):
    "11-agent and 51-workflow cap denials"

Required result (verbatim):
    "NEGATIVE: the 11th agent and the 51st workflow are refused with a named cap
     error; the cap counts are recorded from the live census"

The enforcement is the REAL ``admit_launch`` / ``occupancy`` / ``limits`` of the
workflow guard in the tree under test: one BEGIN IMMEDIATE transaction counts,
checks and reserves, so a launch that breaches a cap leaves nothing behind; the
census is the native run journal and its raw observed count is never clamped to
a declared peak. Fixtures only (tmp state, tmp run journals); no live launch, no
network, no provider.

Modes:
  (no flag)   run the scenario and print one assertion line per check
  --dry-run   identical checks, receipt marked mode=dry-run
  selftest    re-run under deliberate defects and REQUIRE the named
              assertions to turn RED (proves the harness can fail)

Exit 0 = every assertion held; 1 = at least one failed; 2 = tooling.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

ROW = "sc28"
TITLE = "11th agent and 51st workflow refused with named cap errors"
GUARD_REL = Path(".claude/skills/hook-skill/hooks/workflow-guard")


def _real_home():
    try:
        import pwd
        return Path(pwd.getpwuid(os.getuid()).pw_dir)
    except Exception:
        return Path.home()


DEFAULT_GUARDS = (_real_home() / ".openclaw/persist-home/999-setup" / GUARD_REL,
                  _real_home() / ".claude/hooks/workflow-guard")
LIMITS = {"concurrent_agents_per_workflow": 10,
          "concurrent_workflows_per_program": 50,
          "concurrent_agents_total": 500,
          "session_lease_seconds": 3600}


def resolve_guard(args):
    cands = []
    if args.guard_root:
        cands.append(Path(args.guard_root).expanduser())
    env = os.environ.get("WORKFLOW_GUARD_ROOT")
    if env:
        cands.append(Path(env).expanduser())
    cands += DEFAULT_GUARDS
    for c in cands:
        if (c / "guard.py").is_file():
            return c
    print("TOOLING: workflow guard not found; looked at %s"
          % ", ".join(str(c) for c in cands))
    raise SystemExit(2)


def load_guard(root, state):
    os.environ["WORKFLOW_GUARD_STATE"] = str(state)
    spec = importlib.util.spec_from_file_location("s75_guard_%s" % ROW,
                                                  str(root / "guard.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def repoint(guard, base, name, limits=None):
    """A fresh guard state root (module STATE/LIMITS_FILE are read at call time)."""
    state = Path(base) / name
    state.mkdir(parents=True, exist_ok=True)
    guard.STATE = state
    guard.LIMITS_FILE = state / "limits.json"
    guard.LIMITS_FILE.write_text(json.dumps(limits or LIMITS))
    return state


def row(launch_id, session, peak):
    return (launch_id, session, "", time.time(), "h", "RETURNED", "n",
            peak, "")


def launches(guard, session):
    return guard.read_rows(
        "SELECT COUNT(*) n FROM launches WHERE session=?", (session,))[0]["n"]


def census(guard):
    c = guard.db()
    try:
        return guard.occupancy(c)
    finally:
        c.close()


def scenario(guard_root, muts=frozenset()):
    c = H.Checks(ROW, TITLE)
    print("SC28 %s — guard %s%s"
          % (TITLE, guard_root,
             (" [defect: %s]" % ",".join(sorted(muts))) if muts else ""))
    with H.Scratch() as tmp:
        state0 = Path(tmp) / "boot"
        state0.mkdir()
        guard = load_guard(guard_root, state0)
        raised = {"concurrent_agents_per_workflow": 11,
                  "concurrent_workflows_per_program": 51,
                  "concurrent_agents_total": 500,
                  "session_lease_seconds": 3600}
        lim = raised if "cap_raised" in muts else LIMITS

        repoint(guard, tmp, "a", lim)
        read = guard.limits()
        c.check("sc28:caps-read-from-live-limits",
                read["concurrent_agents_per_workflow"] == 10
                and read["concurrent_workflows_per_program"] == 50
                and read["concurrent_agents_total"] == 500,
                "limits read=%r" % (
                    {k: read[k] for k in ("concurrent_agents_per_workflow",
                                          "concurrent_workflows_per_program",
                                          "concurrent_agents_total")},))

        refused = guard.admit_launch(row("L11", "s11", 11), None)
        left = launches(guard, "s11")
        c.check("sc28:eleventh-agent-refused-with-named-cap",
                refused is not None
                and "above the operator limit of 10 per workflow" in refused
                and left == 0,
                "refusal=%r; launches left behind=%r"
                % ((refused or "NONE")[:110], left))

        admitted = guard.admit_launch(row("L10", "s11b", 10), None)
        c.check("sc28:tenth-agent-still-admitted", admitted is None,
                "admit peak 10 returned=%r (control: the cap is not a blanket "
                "refusal)" % admitted)

        repoint(guard, tmp, "b", lim)
        now = time.time()
        guard.write_txn([("INSERT INTO launches VALUES(?,?,?,?,?,?,?,?,?)",
                          ("W%02d" % k, "s51", "", now, "h", "RETURNED", "n",
                           1, "")) for k in range(50)])
        before = census(guard)
        refused_wf = guard.admit_launch(row("W51", "s51", 1), None)
        after = launches(guard, "s51")
        c.check("sc28:cap-counts-recorded-from-the-live-census",
                before["workflows"] == 50 and before["unknown_runs"] == 50
                and before["agents_total"] == 50,
                "census before the 51st: workflows=%r, agents_total=%r, "
                "unknown_runs=%r"
                % (before["workflows"], before["agents_total"],
                   before["unknown_runs"]))
        c.check("sc28:fifty-first-workflow-refused-with-named-cap",
                refused_wf is not None
                and "the operator limit of 50" in refused_wf
                and after == 50,
                "refusal=%r; launches on record=%r (still under the cap)"
                % ((refused_wf or "NONE")[:110], after))

        repoint(guard, tmp, "c", lim)
        run = Path(tmp) / "runs" / "wf_CN-01"
        run.mkdir(parents=True)
        started = 3 if "census_clamped" not in muts else 2
        (run / "journal.jsonl").write_text("".join(
            json.dumps({"type": "started", "key": "k%d" % k,
                        "agentId": "a%d" % k}, separators=(",", ":")) + "\n"
            for k in range(started)))
        guard.write_txn([("INSERT INTO launches VALUES(?,?,?,?,?,?,?,?,?)",
                          ("RAW", "sraw", "", time.time(), "h", "RETURNED", "n",
                           2, json.dumps({"run_id": "wf_CN-01",
                                          "transcript_dir": str(run)})))])
        raw = census(guard)
        c.check("sc28:census-is-raw-not-clamped-to-the-declared-peak",
                raw["agents_observed"] == 3 and raw["unknown_runs"] == 0,
                "declared peak=2, native journal started=%d; census "
                "agents_observed=%r, unknown_runs=%r"
                % (started, raw["agents_observed"], raw["unknown_runs"]))
    return c


MUTATIONS = {
    "cap_raised": ["sc28:eleventh-agent-refused-with-named-cap",
                   "sc28:fifty-first-workflow-refused-with-named-cap"],
    "census_clamped": ["sc28:census-is-raw-not-clamped-to-the-declared-peak"],
}


def selftest(guard_root):
    ok = True
    for name in sorted(MUTATIONS):
        c = scenario(guard_root, frozenset([name]))
        failed = [r["name"] for r in c.failed()]
        expected = MUTATIONS[name]
        hit = [e for e in expected if e in failed]
        good = len(hit) == len(expected) and len(failed) >= 1
        ok = ok and good
        print("selftest:%s — %s; red=%s"
              % (name, "RED as required" if good
                 else "DID NOT FAIL AS EXPECTED", failed or "none"))
        print("selftest:%s — expected hit=%d/%d" % (name, len(hit), len(expected)))
    print("selftest — %s" % ("harness fails on every defect" if ok
                             else "HARNESS CANNOT PROVE A FAILURE"))
    return 0 if ok else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = H.add_args(description=__doc__)
    ap.add_argument("--guard-root", default=None,
                    help="the 999-setup workflow-guard dir under test")
    ap.add_argument("--dry-run", action="store_true")
    if argv and argv[0] == "selftest":
        args = ap.parse_args(argv[1:])
        return selftest(resolve_guard(args))
    args = ap.parse_args(argv)
    result = scenario(resolve_guard(args))
    if args.out:
        path = Path(args.out) / "receipts"
        code = result.finish(path)
        receipt = path / "sc28.scenario.json"
        if receipt.is_file():
            doc = json.loads(receipt.read_text("utf-8"))
            doc["mode"] = "dry-run" if args.dry_run else "run"
            receipt.write_text(json.dumps(doc, indent=2) + "\n", "utf-8")
        return code
    return result.finish()


if __name__ == "__main__":
    sys.exit(main())
