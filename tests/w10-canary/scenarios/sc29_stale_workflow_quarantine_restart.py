#!/usr/bin/env python3
"""sc29_stale_workflow_quarantine_restart.py — acceptance row SC-29 (S75-W10-U1).

Condition (SCENARIO-MATRIX.json, row SC-29, verbatim):
    "Stale workflow quarantine and restart"

Required result (verbatim):
    "NEGATIVE: a stale workflow is quarantined and is not dispatched; after
     restart it stays quarantined until explicitly re-admitted"

The enforcement is the REAL workflow guard of the tree under test:
``revoke_attempt`` (quarantine + checkpoint + lease revocation), the
``admit_launch`` revoked-attempt fence, and the ``restart-attempt`` CLI that
re-creates ONLY the unfinished units under a NEW attempt ID while the
predecessor stays fenced. Fixtures only (tmp plan/run/state); no live launch,
no network, no provider, no channel.

Modes:
  (no flag)   run the scenario and print one assertion line per check
  --dry-run   identical checks, receipt marked mode=dry-run
  selftest    re-run under deliberate defects and REQUIRE the named
              assertions to turn RED (proves the harness can fail)

Exit 0 = every assertion held; 1 = at least one failed; 2 = tooling.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

ROW = "sc29"
TITLE = "stale workflow quarantined; restart re-admits only a new attempt"
GUARD_REL = Path(".claude/skills/hook-skill/hooks/workflow-guard")


def _real_home():
    """The OPERATOR's home, deliberately not $HOME.

    These rows judge a workflow guard that is INSTALLED on the box, so they
    must find the real install even when the harness is run with a throwaway
    HOME for isolation. Reading $HOME here would make the default candidates
    vanish under `HOME=$(mktemp -d)` and turn a missing dependency into a
    confusing tooling error. Consequence, stated plainly: a fresh-HOME run
    still binds the operator's installed guard; it is NOT isolated from it.
    Pass the root explicitly to pin a revision.
    """
    try:
        import pwd
        return Path(pwd.getpwuid(os.getuid()).pw_dir)
    except Exception:
        return Path.home()


DEFAULT_GUARDS = (_real_home() / ".openclaw/persist-home/999-setup" / GUARD_REL,
                  _real_home() / ".claude/hooks/workflow-guard")
WF = "CN-01"
UNIT = "CN-01-U1"
WORKER = "u3-sess"


def resolve_guard(args):
    # An explicitly named guard is AUTHORITATIVE. Falling back to a different
    # guard would let a row pass against a revision it did not name, which is
    # worse than failing: it reads as coverage of code that never ran.
    if args.guard_root:
        named = Path(args.guard_root).expanduser()
        if (named / "guard.py").is_file():
            return named
        print("TOOLING: --guard-root %s contains no guard.py; refusing to "
              "fall back to a different guard" % named)
        raise SystemExit(2)
    cands = []
    env = os.environ.get("WORKFLOW_GUARD_ROOT")
    if env:
        # The env var is as authoritative as the flag: a named root that does
        # not hold guard.py must refuse, not silently fall through to an
        # installed copy the operator did not name.
        named_env = Path(env).expanduser()
        if not (named_env / "guard.py").is_file():
            print("TOOLING: WORKFLOW_GUARD_ROOT=%s contains no guard.py; "
                  "refusing to fall back to a different guard" % named_env)
            raise SystemExit(2)
        cands.append(named_env)
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


def guard_env(state):
    env = dict(os.environ)
    env["WORKFLOW_GUARD_STATE"] = str(state)
    return env


def run_guard(root, state, *argv):
    return subprocess.run([sys.executable, "-I", "-B", str(root / "guard.py")]
                          + list(argv), capture_output=True, text=True,
                          env=guard_env(state), timeout=120)


def read_via_fresh_process(root, state, plan):
    """A separate interpreter re-reads the persisted quarantine (the restart proof)."""
    code = ("import importlib.util,json;"
            "s=importlib.util.spec_from_file_location('g',%r);"
            "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
            "print(json.dumps(m.attempt_revoked(%r,'A1')))"
            % (str(root / "guard.py"), plan))
    return subprocess.run([sys.executable, "-I", "-B", "-c", code],
                          capture_output=True, text=True,
                          env=guard_env(state), timeout=120)


def compact_journal(run):
    jp = Path(run) / "journal.jsonl"
    evs = [json.loads(l) for l in jp.read_text().splitlines() if l.strip()]
    jp.write_text("".join(json.dumps(e, separators=(",", ":")) + "\n"
                          for e in evs))


def hook(guard, event, tool, ti, session, cwd, **extra):
    data = {"hook_event_name": event, "tool_name": tool, "tool_input": ti,
            "session_id": session, "cwd": str(cwd)}
    data.update(extra)
    err, out = io.StringIO(), io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
        rc = guard.hook(data)
    return rc, err.getvalue()


def launches(guard, session):
    return guard.read_rows(
        "SELECT COUNT(*) n FROM launches WHERE session=?", (session,))[0]["n"]


def scenario(guard_root, muts=frozenset()):
    c = H.Checks(ROW, TITLE)
    print("SC29 %s — guard %s%s"
          % (TITLE, guard_root,
             (" [defect: %s]" % ",".join(sorted(muts))) if muts else ""))
    with H.Scratch() as tmp:
        state = Path(tmp) / "state"
        state.mkdir()
        proj = Path(tmp) / "proj"
        proj.mkdir()
        guard = load_guard(guard_root, state)
        st = guard._staffing()

        plan = str(Path(st._mkplan(proj, {WF: 2}, status="running")).resolve())
        tx, run = st._mkrun(proj, WF)
        compact_journal(run)
        now = time.time()
        guard.write_txn([
            ("INSERT OR REPLACE INTO launches VALUES(?,?,?,?,?,?,?,?,?)",
             ("L1", WORKER, str(tx), now, "h", "RETURNED", "n", 2,
              json.dumps({"run_id": "wf_" + WF, "transcript_dir": str(run)}))),
            ("INSERT OR REPLACE INTO launch_tags VALUES(?,?,?,?,?)",
             ("L1", WORKER, WF, plan, now)),
            ("INSERT OR REPLACE INTO attempt_ids VALUES(?,?,?,?,?)",
             (plan, "A1", WF, "L1", now)),
        ])

        vpath = Path(proj) / "evidence" / WF / (UNIT + ".verdict.json")
        vpath.parent.mkdir(parents=True, exist_ok=True)
        vcontent = json.dumps({"verdict": "PASS", "unit_id": UNIT,
                               "attempt_id": "A1",
                               "builder_model": "opus",
                               "reviewer_model": "sonnet"})
        rc_w, err_w = hook(guard, "PreToolUse", "Write",
                           {"file_path": str(vpath), "content": vcontent},
                           WORKER, proj, agent_id="qc-" + UNIT)
        if rc_w == 0:
            vpath.write_text(vcontent)   # the Write tool's own effect, between the two hooks
        if "no_verdict_journal" not in muts and rc_w == 0:
            hook(guard, "PostToolUse", "Write",
                 {"file_path": str(vpath), "content": vcontent},
                 WORKER, proj, agent_id="qc-" + UNIT)
        journaled = len(guard.read_rows(
            "SELECT 1 FROM verdict_records WHERE attempt_id=?", ("A1",)))

        if "no_revoke" in muts:
            ck = {"accepted_outputs": [], "unfinished_units": []}
        else:
            ck = guard.revoke_attempt(plan, WF, "A1",
                                      reason="stale workflow: no progress",
                                      by="sc29-canary")
        revoked = guard.attempt_revoked(plan, "A1")
        c.check("sc29:workflow-quarantined-with-a-checkpoint",
                revoked is not None
                and [r["unit_id"] for r in ck["accepted_outputs"]] == [UNIT]
                and ck["unfinished_units"] == ["CN-01-U2"],
                "pre-write exit=%r journaled=%r; checkpoint "
                "accepted_outputs=%r unfinished=%r; revoke reason=%r"
                % (rc_w, journaled,
                   [r["unit_id"] for r in ck["accepted_outputs"]],
                   ck["unfinished_units"],
                   (revoked or {}).get("reason")))

        guard.write_txn([("UPDATE launches SET state='CANCELLED' WHERE id=?",
                          ("L1",))])
        before = launches(guard, WORKER)
        refused = guard.admit_launch(
            ("L9", WORKER, str(tx), time.time(), "h", "VALIDATED", WF, 2, ""),
            (WF, plan, "A1", 2))
        c.check("sc29:quarantined-workflow-is-not-dispatched",
                refused is not None
                and "REVOKED (fenced attempt)" in refused
                and launches(guard, WORKER) == before,
                "dispatch of the quarantined attempt refused=%r; launches=%r "
                "(unchanged=%r)"
                % ((refused or "NONE")[:100], launches(guard, WORKER),
                   launches(guard, WORKER) == before))

        new_attempt = "A1" if "restart_as_same_attempt" in muts else "A2"
        restart = run_guard(guard_root, state, "restart-attempt",
                            "--plan", plan, "--workflow", WF,
                            "--supersedes", "A1",
                            "--new-attempt", new_attempt,
                            "--reason", "stale workflow restart")
        try:
            out = json.loads(restart.stdout)["restart"]
        except (ValueError, KeyError):
            out = {}
        c.check("sc29:restart-recreates-only-the-unfinished-work",
                restart.returncode == 0
                and out.get("unfinished_units") == ["CN-01-U2"]
                and out.get("accepted_outputs_preserved") == 1
                and vpath.is_file(),
                "exit=%r unfinished=%r accepted_outputs_preserved=%r "
                "verdict file on disk=%r stderr=%r"
                % (restart.returncode, out.get("unfinished_units"),
                   out.get("accepted_outputs_preserved"), vpath.is_file(),
                   restart.stderr.strip()[:100]))

        fresh = read_via_fresh_process(guard_root, state, plan)
        try:
            persisted = json.loads(fresh.stdout or "null")
        except ValueError:
            persisted = None
        c.check("sc29:quarantine-survives-the-restart",
                fresh.returncode == 0 and isinstance(persisted, dict)
                and persisted.get("reason") == "stale workflow: no progress",
                "fresh-process rc=%r attempt_revoked(A1)=%r"
                % (fresh.returncode, persisted))

        after_restart = guard.admit_launch(
            ("L10", WORKER, str(tx), time.time(), "h", "VALIDATED", WF, 2, ""),
            (WF, plan, "A1", 2))
        c.check("sc29:old-attempt-stays-fenced-after-restart",
                after_restart is not None
                and "REVOKED (fenced attempt)" in after_restart,
                "dispatch of A1 after the restart refused=%r"
                % ((after_restart or "NONE")[:110]))

        readmit = guard.admit_launch(
            ("L11", WORKER, str(tx), time.time(), "h", "VALIDATED", WF, 2, ""),
            (WF, plan, new_attempt, 2))
        still = guard.attempt_revoked(plan, "A1")
        c.check("sc29:explicit-readmission-uses-the-new-attempt-only",
                readmit is None and still is not None
                and still.get("reason") == "stale workflow: no progress",
                "admit %s returned=%r; A1 still revoked=%r"
                % (new_attempt, readmit, bool(still)))
    return c


MUTATIONS = {
    "no_verdict_journal": ["sc29:workflow-quarantined-with-a-checkpoint"],
    "no_revoke": ["sc29:workflow-quarantined-with-a-checkpoint"],
    "restart_as_same_attempt": ["sc29:restart-recreates-only-the-unfinished-work"],
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
        receipt = path / "sc29.scenario.json"
        if receipt.is_file():
            doc = json.loads(receipt.read_text("utf-8"))
            doc["mode"] = "dry-run" if args.dry_run else "run"
            receipt.write_text(json.dumps(doc, indent=2) + "\n", "utf-8")
        return code
    return result.finish()


if __name__ == "__main__":
    sys.exit(main())
