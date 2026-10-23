#!/usr/bin/env python3
"""sc31_run_older_than_three_hours.py — acceptance row SC-31 (S75-W10-U1).

Condition (SCENARIO-MATRIX.json, row SC-31, verbatim):
    "Runs older than three hours"

Required result (verbatim):
    "NEGATIVE: a run older than three hours is classified by the supervision
     policy (surfaced/warned) without silently deleting state or claiming
     completion"

The enforcement is the REAL supervision policy of the tree under test:
``75-drama-song-ad-factory/scripts/core/heartbeat/run_watch.py`` — the
``DEFAULT_MAX_HOURS`` cap anchored on the run's own start, the
``HEARTBEAT_EXPIRED`` loud escalation, and the invariant that supervision ends
only on verified completion or an explicit cancellation
(``loop_should_stop`` / ``supervising``).

Nothing about "not deleted" is taken on trust: the harness hashes the durable
state before and after the classification and re-reads it in a FRESH
interpreter.

Fixtures only (tmp state database, tmp decision files); no live run, no
network, no provider, no channel.

Modes:
  (no flag)   run the scenario and print one assertion line per check
  --dry-run   identical checks, receipt marked mode=dry-run
  selftest    re-run under deliberate defects and REQUIRE the named
              assertions to turn RED (proves the harness can fail)

Exit 0 = every assertion held; 1 = at least one failed; 2 = tooling.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

ROW = "sc31"
TITLE = "a run older than three hours is surfaced, never deleted or claimed done"
RUN = "run-sc31"
STAGES = ("research", "creative-strategy", "script-lyrics", "music")
CAP_HOURS = 3.0


def resolve_run_watch(args):
    """The run_watch.py of the tree under test.

    An explicitly named --core-root is AUTHORITATIVE: if it does not hold the
    module, the harness exits 2 and names the path. It never falls back to a
    different installed copy, which would let the row pass against code the
    operator did not name.
    """
    core = H.resolve_core(args)
    mod = core / "heartbeat" / "run_watch.py"
    if not mod.is_file():
        print("TOOLING: %s holds no heartbeat/run_watch.py; refusing to fall "
              "back to a different tree" % core)
        raise SystemExit(2)
    return mod


def child_env(home):
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONPATH", "OPENCLAW_HOME")}
    env["HOME"] = str(home)
    return env


def mk_run(base, label, now, age_min, last_state="RUNNING", all_complete=False):
    """A run whose stages all started age_min ago; one stage is still active."""
    run = Path(base) / ("wf_" + label)
    ctl = run / "control"
    ctl.mkdir(parents=True, exist_ok=True)
    t0 = now - age_min * 60
    tail = "COMPLETE" if all_complete else "NOT_STARTED"
    rows = [(RUN, "research", "COMPLETE", "u1", None, None, t0),
            (RUN, "creative-strategy", last_state, "u1", None, None, t0),
            (RUN, "script-lyrics", tail, "u1", None, None, t0),
            (RUN, "music", tail, "u1", None, None, t0)]
    con = sqlite3.connect(str(ctl / "state.sqlite3"))
    con.executescript(
        "CREATE TABLE stages(run_id TEXT,stage TEXT,state TEXT,owner TEXT,"
        "lease_expires REAL,reason TEXT,updated_at REAL);"
        "CREATE TABLE events(run_id TEXT,stage TEXT,at REAL);")
    con.executemany("INSERT INTO stages VALUES(?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    H.write_json(ctl / "run-state.json", {"run_id": RUN})
    return run


def digest(path):
    p = Path(path)
    if not p.is_file():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


def look(mod, run, now, max_hours=CAP_HOURS):
    """One read-only look: (envelope, the loud printer's own text).

    The envelope carries the codes; the named escalation detail (elapsed
    minutes, stages complete) is what the printer writes, so it is captured
    rather than allowed to reach stdout.
    """
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        env = mod.build(str(run), max_hours=max_hours, now=now)
    return env, err.getvalue()


def loud_codes(env):
    return [str(x).split(" ")[0].split(":")[0] for x in (env or {}).get("loud") or []]


def fresh_read(mod_path, run, now, home):
    p = subprocess.run([sys.executable, "-I", "-B", str(mod_path),
                        "--run-dir", str(run), "--now", "%.3f" % now],
                       capture_output=True, text=True,
                       env=child_env(home), timeout=180)
    try:
        return p, json.loads(p.stdout)
    except ValueError:
        return p, None


def scenario(mod_path, muts=frozenset()):
    c = H.Checks(ROW, TITLE)
    print("SC31 %s — run_watch %s%s"
          % (TITLE, mod_path,
             (" [defect: %s]" % ",".join(sorted(muts))) if muts else ""))
    mod = H.load_file(mod_path, "s75_run_watch_%s" % ROW)
    with H.Scratch() as tmp:
        now = time.time()
        home = Path(tmp) / "home"
        home.mkdir()
        run = mk_run(tmp, "over", now, 200)
        db = run / "control" / "state.sqlite3"
        decisions = run / "control" / "run-state.json"
        before = (digest(db), digest(decisions))
        cap = 99.0 if "cap_raised" in muts else CAP_HOURS

        env, loud_text = look(mod, run, now, cap)
        detail = "200 minutes elapsed, 1/4 stages COMPLETE"
        c.check("sc31:older-than-three-hours-is-surfaced",
                env.get("expired") is True
                and env.get("elapsed_minutes") == 200
                and "HEARTBEAT_EXPIRED" in loud_codes(env)
                and detail in loud_text,
                "observed elapsed_minutes=%r expired=%r loud=%r escalation=%r"
                % (env.get("elapsed_minutes"), env.get("expired"),
                   env.get("loud"), loud_text.strip()[:160]))

        message = str(env.get("message_for_client") or "")
        c.check("sc31:no-completion-claim-and-supervision-continues",
                env.get("loop_should_stop") is False
                and env.get("supervising") is True
                and env.get("completed_stages") == 1
                and env.get("stages_total") == 4
                and "Your video is finished" not in message,
                "observed loop_should_stop=%r supervising=%r completed=%r/%r "
                "and the client message claims finished=%r"
                % (env.get("loop_should_stop"), env.get("supervising"),
                   env.get("completed_stages"), env.get("stages_total"),
                   "Your video is finished" in message))

        if "state_removed" in muts:
            db.unlink()
        after = (digest(db), digest(decisions))
        proc, doc = fresh_read(mod_path, run, now, home)
        c.check("sc31:state-not-silently-deleted",
                before[0] is not None and before == after
                and proc.returncode == 0
                and (doc or {}).get("expired") is True,
                "observed state.sqlite3 sha256 before=%s after=%s; "
                "run-state.json sha256 before=%s after=%s; fresh-interpreter "
                "rc=%r expired=%r"
                % (before[0], after[0], before[1], after[1],
                   proc.returncode, (doc or {}).get("expired")))

        under = mk_run(tmp, "under", now, 120)
        under_hours = 1.0 if "cap_always_on" in muts else CAP_HOURS
        under_env, _ = look(mod, under, now, under_hours)
        c.check("sc31:control-under-the-cap-is-not-expired",
                under_env.get("expired") is False
                and "HEARTBEAT_EXPIRED" not in loud_codes(under_env),
                "control at elapsed_minutes=%r: observed expired=%r loud=%r "
                "— the cap is a threshold, not an always-on alarm"
                % (under_env.get("elapsed_minutes"),
                   under_env.get("expired"), under_env.get("loud")))

        finished = mk_run(tmp, "finished", now, 200, last_state="COMPLETE",
                          all_complete=True)
        fin_env, _ = look(mod, finished, now)
        c.check("sc31:control-a-finished-run-is-not-expired",
                fin_env.get("completed_stages") == 4
                and fin_env.get("expired") is False
                and fin_env.get("loop_should_stop") is True,
                "control at elapsed_minutes=%r all stages COMPLETE: observed "
                "completed=%r/%r expired=%r loop_should_stop=%r — elapsed time "
                "alone never expires finished work"
                % (fin_env.get("elapsed_minutes"),
                   fin_env.get("completed_stages"), fin_env.get("stages_total"),
                   fin_env.get("expired"), fin_env.get("loop_should_stop")))
    return c


MUTATIONS = {
    # The cap is raised, so a 200-minute run is never classified.
    "cap_raised": ["sc31:older-than-three-hours-is-surfaced"],
    # The cap fires under the threshold: the control at 120 minutes expires too.
    "cap_always_on": ["sc31:control-under-the-cap-is-not-expired"],
    # Something deleted the durable state after classifying.
    "state_removed": ["sc31:state-not-silently-deleted"],
}


def selftest(mod_path):
    ok = True
    for name in sorted(MUTATIONS):
        c = scenario(mod_path, frozenset([name]))
        failed = [r["name"] for r in c.failed()]
        expected = MUTATIONS[name]
        hit = [e for e in expected if e in failed]
        good = len(hit) == len(expected) and len(failed) >= 1
        ok = ok and good
        print("selftest:%s — %s; red=%s"
              % (name, "RED as required" if good
                 else "DID NOT FAIL AS EXPECTED", failed or "none"))
        print("selftest:%s — expected hit=%d/%d"
              % (name, len(hit), len(expected)))
    print("selftest — %s" % ("harness fails on every defect" if ok
                             else "HARNESS CANNOT PROVE A FAILURE"))
    return 0 if ok else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = H.add_args(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    if argv and argv[0] == "selftest":
        args = ap.parse_args(argv[1:])
        return selftest(resolve_run_watch(args))
    args = ap.parse_args(argv)
    result = scenario(resolve_run_watch(args))
    if args.out:
        path = Path(args.out) / "receipts"
        code = result.finish(path)
        receipt = path / ("%s.scenario.json" % ROW)
        if receipt.is_file():
            doc = json.loads(receipt.read_text("utf-8"))
            doc["mode"] = "dry-run" if args.dry_run else "run"
            receipt.write_text(json.dumps(doc, indent=2) + "\n", "utf-8")
        return code
    return result.finish()


if __name__ == "__main__":
    sys.exit(main())
