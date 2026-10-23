#!/usr/bin/env python3
"""sc27_hidden_worker_orchestrator_edit.py — acceptance row SC-27 (S75-W10-U1).

Condition (SCENARIO-MATRIX.json, row SC-27, verbatim):
    "Hidden worker and orchestrator-edit denials"

Required result (verbatim):
    "NEGATIVE: a hidden worker and an orchestrator edit to a unit-owned file
     are both denied with a recorded reason"

The denial boundary is the REAL workflow guard of the tree under test:
``plan_agent_block`` (under a swarm plan, an Agent/Task call must be read-only),
``fence`` (a session registered as a program/orchestrator seat may not spawn a
build worker and may not write implementation — only named lane/work/evidence
accounting paths), and ``protected_write_block`` (the conductor may not write a
unit's verdict file; only the checker agent that judged the unit may). Fixtures
only (tmp plan/run/state); no network, no provider, no channel, no live session.

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

ROW = "sc27"
TITLE = "hidden worker and orchestrator unit-owned edit both denied"
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
CONDUCTOR = "u3-conductor"
ORCH = "u3-orch"           # program seat registered over the plan run root
ORCH_PLAIN = "u3-orch-2"   # program seat registered over a planless run root
BUILD_AGENT = {"subagent_type": "general-purpose", "description": "builder",
               "prompt": "build and implement the module"}
READ_AGENT = {"subagent_type": "Explore", "description": "read only",
              "prompt": "read these files and report what they contain"}


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


def pre(guard, tool, ti, cwd, session, **extra):
    data = {"hook_event_name": "PreToolUse", "tool_name": tool,
            "tool_input": ti, "session_id": session, "cwd": str(cwd)}
    data.update(extra)
    err, out = io.StringIO(), io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
        rc = guard.hook(data)
    return rc, err.getvalue()


def scenario(guard_root, muts=frozenset()):
    c = H.Checks(ROW, TITLE)
    print("SC27 %s — guard %s%s"
          % (TITLE, guard_root,
             (" [defect: %s]" % ",".join(sorted(muts))) if muts else ""))
    with H.Scratch() as tmp:
        state = Path(tmp) / "state"
        state.mkdir()
        proj = Path(tmp) / "proj"
        proj.mkdir()
        plain = Path(tmp) / "plain"          # no plan governs this run root
        plain.mkdir()
        guard = load_guard(guard_root, state)
        st = guard._staffing()
        st._mkplan(proj, {WF: 2}, status="running")
        now = time.time()
        guard.write_txn([(
            "INSERT INTO programs(session,run_root,registered) VALUES(?,?,?)",
            (ORCH, str(proj), now)),
            ("INSERT INTO programs(session,run_root,registered) VALUES(?,?,?)",
             (ORCH_PLAIN, str(plain), now))])

        worker = READ_AGENT if "readonly_helper" in muts else BUILD_AGENT
        rc, err = pre(guard, "Agent", worker, proj, ORCH)
        c.check("sc27:hidden-worker-denied-under-a-plan",
                rc == 2 and "HIDDEN BUILD" in err and "read-only" in err,
                "exit=%r subagent_type=%r refusal=%r"
                % (rc, worker["subagent_type"], err.strip()[:140]))

        rc2, err2 = pre(guard, "Agent", worker, plain, ORCH_PLAIN)
        c.check("sc27:hidden-worker-denied-without-a-plan",
                rc2 == 2 and "HIDDEN WORKER" in err2
                and "read-only helpers" in err2,
                "exit=%r subagent_type=%r refusal=%r"
                % (rc2, worker["subagent_type"], err2.strip()[:140]))

        vpath = Path(proj) / "evidence" / WF / (UNIT + ".verdict.json")
        vpath.parent.mkdir(parents=True, exist_ok=True)
        vcontent = json.dumps({"verdict": "PASS", "unit_id": UNIT,
                               "attempt_id": "A1",
                               "builder_model": "opus",
                               "reviewer_model": "sonnet"})
        owned_ti = {"file_path": str(vpath), "content": vcontent}
        if "conductor_writes_elsewhere" in muts:
            owned_ti = {"file_path": str(Path(proj) / "notes.md"),
                        "content": "note"}
        rc3, err3 = pre(guard, "Write", owned_ti, proj, CONDUCTOR)
        c.check("sc27:orchestrator-unit-owned-edit-denied",
                rc3 == 2 and "may not write unit verdict files" in err3
                and "written only by the checker agent" in err3,
                "exit=%r target=%r refusal=%r"
                % (rc3, Path(owned_ti["file_path"]).name,
                   err3.strip()[:130]))

        impl = Path(proj) / "impl.py"
        target = (Path(proj) / "lanes" / "x-lane" / "note.md"
                  if "edit_in_lane" in muts else impl)
        rc4, err4 = pre(guard, "Edit",
                        {"file_path": str(target), "old_string": "a",
                         "new_string": "b"}, proj, ORCH)
        c.check("sc27:orchestrator-implementation-edit-denied",
                rc4 == 2 and "ORCHESTRATOR ALLOWLIST" in err4
                and "implementation writes are denied" in err4,
                "exit=%r target=%r refusal=%r"
                % (rc4, str(target.relative_to(proj)), err4.strip()[:130]))

        note = (Path(proj) / "impl.py" if "edit_in_lane" in muts
                else Path(proj) / "lanes" / "x-lane" / "note.md")
        note.parent.mkdir(parents=True, exist_ok=True)
        rc5, err5 = pre(guard, "Edit",
                        {"file_path": str(note), "old_string": "a",
                         "new_string": "b"}, proj, ORCH)
        c.check("sc27:orchestrator-accounting-edit-allowed", rc5 == 0,
                "exit=%r target=%r refusal=%r (control: named lane accounting "
                "stays writable for the seat)"
                % (rc5, str(note.relative_to(proj)), err5.strip()[:80]))

        fp = guard.call_fingerprint(
            "Write", {"file_path": str(Path(proj) / "other.md"),
                      "content": ""} if "no_record" in muts else owned_ti)
        recorded = guard.failure_count(CONDUCTOR, fp)
        rows = guard.read_rows(
            "SELECT last_error FROM failures WHERE session=? AND fingerprint=?",
            (CONDUCTOR, fp))
        last = rows[0]["last_error"] if rows else None
        c.check("sc27:denial-is-recorded",
                recorded == 1 and last == "guard refusal",
                "failure rows for the denied unit-owned write=%r, "
                "last_error=%r" % (recorded, last))
    return c


MUTATIONS = {
    "readonly_helper": ["sc27:hidden-worker-denied-under-a-plan"],
    "conductor_writes_elsewhere": ["sc27:orchestrator-unit-owned-edit-denied"],
    "edit_in_lane": ["sc27:orchestrator-implementation-edit-denied"],
    "no_record": ["sc27:denial-is-recorded"],
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
        receipt = path / "sc27.scenario.json"
        if receipt.is_file():
            doc = json.loads(receipt.read_text("utf-8"))
            doc["mode"] = "dry-run" if args.dry_run else "run"
            receipt.write_text(json.dumps(doc, indent=2) + "\n", "utf-8")
        return code
    return result.finish()


if __name__ == "__main__":
    sys.exit(main())
