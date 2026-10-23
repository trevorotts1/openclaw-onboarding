#!/usr/bin/env python3
"""sc26_checker_fixes_role_swap.py — acceptance row SC-26 (S75-W10-U1).

Condition (SCENARIO-MATRIX.json, row SC-26, verbatim):
    "Checker-fixes role swap"

Required result (verbatim):
    "NEGATIVE: a checker attempting to author fixes is denied by role; the checker
     can only judge and the denial is recorded"

The enforcement is the REAL workflow guard (``guard.py`` + ``staffing.py``) of the
tree under test: the subagent write boundary that lets a checker write ONLY its
``*.verdict.json`` inside a plan evidence tree, and the completion rule that
credits a unit only when the journaled writer is that unit's ``qc:<unit>`` agent
with a separate ``build:<unit>`` agent of another model family. Fixtures only
(tmp plan/run/state); no network, no provider, no channel.

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
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

ROW = "sc26"
TITLE = "checker cannot author fixes; the role denial is recorded"
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
FIX_REFUSAL = ("A subagent may write only *.verdict.json files in a plan "
               "evidence tree")


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


def pre(guard, tool, ti, session, cwd, **extra):
    data = {"hook_event_name": "PreToolUse", "tool_name": tool,
            "tool_input": ti, "session_id": session, "cwd": str(cwd)}
    data.update(extra)
    err, out = io.StringIO(), io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
        rc = guard.hook(data)
    return rc, err.getvalue()


def compact_journal(run):
    jp = Path(run) / "journal.jsonl"
    evs = [json.loads(l) for l in jp.read_text().splitlines() if l.strip()]
    jp.write_text("".join(json.dumps(e, separators=(",", ":")) + "\n"
                          for e in evs))


def admit(guard, tx, run, plan):
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


def scenario(guard_root, muts=frozenset()):
    c = H.Checks(ROW, TITLE)
    print("SC26 %s — guard %s%s"
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
        if "no_compact_journal" not in muts:
            compact_journal(run)
        admit(guard, tx, run, plan)
        st._verdict(proj, WF, attempt="A1", builder="opus", reviewer="sonnet")
        doc = json.loads(Path(plan).read_text())
        wf = st.workflows(doc)[0]
        recs = st._file_records(proj, WF)[WF]
        proof = st._proof(proj, WF)[WF]
        key = sorted(recs)[0]

        done = st.is_done(proj, wf, attempts=("A1",), records=recs, proof=proof)
        c.check("sc26:separated-roles-complete-the-unit", done is True,
                "is_done=%r; journaled writer=%r on attempt A1"
                % (done, proof.get(key, (None, []))[0]))

        swap = st._proof(proj, WF, writer_prefix="bu")[WF]
        swap_proof = proof if "swap_is_accepted" in muts else swap
        done_swap = st.is_done(proj, wf, attempts=("A1",), records=recs,
                               proof=swap_proof)
        c.check("sc26:builder-cannot-write-its-own-verdict", done_swap is False,
                "writer=%r is_done=%r on attempt A1; required: writer "
                "'bu-%s' is not a qc writer, so the unit must not complete"
                % (swap_proof.get(key, (None, []))[0], done_swap, UNIT))

        solo = (Path(tmp) / "solo" / "sess" / "subagents" / "workflows"
                / ("wf_" + WF))
        solo.mkdir(parents=True)
        (solo / "journal.jsonl").write_text(json.dumps(
            {"type": "started", "key": "k1", "agentId": "qc-" + UNIT,
             "label": "qc:" + UNIT}, separators=(",", ":")) + "\n")
        (solo / ("agent-qc-%s.meta.json" % UNIT)).write_text(
            json.dumps({"model": "sonnet"}))
        solo_ok = st.actual_roles_ok(UNIT, "qc-" + UNIT, [str(solo)])
        c.check("sc26:checker-alone-cannot-complete-a-unit", solo_ok is False,
                "actual_roles_ok=%r with 0 build:%s agents in the run; a "
                "checker-only run must never complete a unit"
                % (solo_ok, UNIT))

        fix = (Path(proj) / "lanes" / "x-lane" / "fix.py"
               if "fix_into_lane" in muts
               else Path(proj) / "evidence" / WF / "fix.py")
        fix.parent.mkdir(parents=True, exist_ok=True)
        fix_ti = {"file_path": str(fix), "content": "print('fixed')\n"}
        rc, err = pre(guard, "Write", fix_ti, WORKER, proj,
                      agent_id="qc-" + UNIT)
        c.check("sc26:checker-authoring-a-fix-is-denied-by-role",
                rc == 2 and FIX_REFUSAL in err,
                "exit=%r target=%r refusal=%r"
                % (rc, str(fix.relative_to(proj)), err.strip()[:120]))
        c.check("sc26:checker-fix-write-left-no-file-on-disk",
                not fix.exists(),
                "fix.py exists=%r after the denied write (the boundary refused "
                "the call, so no bytes landed)" % fix.exists())

        vpath = Path(proj) / "evidence" / WF / (UNIT + ".verdict.json")
        vcontent = json.dumps({"verdict": "PASS", "unit_id": UNIT,
                               "attempt_id": "A1", "builder_model": "opus",
                               "reviewer_model": "sonnet"})
        rc_v, err_v = pre(guard, "Write",
                          {"file_path": str(vpath), "content": vcontent},
                          WORKER, proj, agent_id="qc-" + UNIT)
        c.check("sc26:checker-may-write-its-verdict", rc_v == 0,
                "exit=%r refusal=%r for the qc agent's own %s.verdict.json "
                "(control: judging is allowed, authoring is not)"
                % (rc_v, err_v.strip()[:80], UNIT))

        fp = guard.call_fingerprint(
            "Write", {"file_path": str(fix) + ".other"} if "no_record" in muts
            else fix_ti)
        recorded = guard.failure_count(WORKER, fp)
        rows = guard.read_rows(
            "SELECT last_error FROM failures WHERE session=? AND fingerprint=?",
            (WORKER, fp))
        last = rows[0]["last_error"] if rows else None
        c.check("sc26:role-denial-is-recorded",
                recorded == 1 and last == "guard refusal",
                "failure rows for the denied fix write=%r, last_error=%r"
                % (recorded, last))
    return c


MUTATIONS = {
    "no_compact_journal": ["sc26:checker-may-write-its-verdict"],
    "swap_is_accepted": ["sc26:builder-cannot-write-its-own-verdict"],
    "fix_into_lane": ["sc26:checker-authoring-a-fix-is-denied-by-role"],
    "no_record": ["sc26:role-denial-is-recorded"],
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
        receipt = path / "sc26.scenario.json"
        if receipt.is_file():
            doc = json.loads(receipt.read_text("utf-8"))
            doc["mode"] = "dry-run" if args.dry_run else "run"
            receipt.write_text(json.dumps(doc, indent=2) + "\n", "utf-8")
        return code
    return result.finish()


if __name__ == "__main__":
    sys.exit(main())
