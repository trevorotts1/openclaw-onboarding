#!/usr/bin/env python3
"""sc30_legitimate_human_waits.py — acceptance row SC-30 (S75-W10-U1).

Condition (SCENARIO-MATRIX.json, row SC-30, verbatim):
    "Legitimate human waits"

Required result (verbatim):
    "NEGATIVE of a false positive: a legitimate human wait (approval pending) is
     not killed, reaped or reported as failure within the wait window"

The enforcement is the REAL supervision policy of the tree under test:
``75-drama-song-ad-factory/scripts/core/heartbeat/run_watch.py`` —
``legitimate_wait`` (a client approval is a NAMED wait), ``stall_check`` (a
named wait never consumes the 30-minute technical stall timeout), and
``build`` (a wait is never HEARTBEAT_EXPIRED, never stops supervision).

The module is a read-only observer: the harness hashes the run state before and
after the look and re-reads it in a FRESH interpreter, so "not killed, not
reaped" is proven as unchanged durable state, not as prose.

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

ROW = "sc30"
TITLE = "a legitimate human wait is not killed, reaped or reported as failure"
RUN = "run-sc30"
STAGES = ("research", "creative-strategy", "script-lyrics", "music")
APPROVAL_STAGE = "script-lyrics"


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


def mk_state(run, rows):
    ctl = Path(run) / "control"
    ctl.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(ctl / "state.sqlite3"))
    con.executescript(
        "CREATE TABLE stages(run_id TEXT,stage TEXT,state TEXT,owner TEXT,"
        "lease_expires REAL,reason TEXT,updated_at REAL);"
        "CREATE TABLE events(run_id TEXT,stage TEXT,at REAL);")
    con.executemany("INSERT INTO stages VALUES(?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    H.write_json(ctl / "run-state.json", {"run_id": RUN})
    return Path(run)


def fixture(base, now, label, waiting_state="WAITING_APPROVAL", age_min=95):
    """A run whose current stage is parked on the client, silent for age_min."""
    run = Path(base) / ("wf_" + label)
    t0 = now - age_min * 60
    rows = [(RUN, "research", "COMPLETE", "u1", None, None, t0),
            (RUN, "creative-strategy", "COMPLETE", "u1", None, None, t0),
            (RUN, APPROVAL_STAGE, waiting_state, "u1", None, None, t0),
            (RUN, "music", "NOT_STARTED", "u1", None, None, t0)]
    return mk_state(run, rows)


def digest(path):
    p = Path(path)
    if not p.is_file():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


def fresh_read(mod_path, run, now, home):
    """A separate interpreter re-reads the run (the restart proof)."""
    p = subprocess.run([sys.executable, "-I", "-B", str(mod_path),
                        "--run-dir", str(run), "--now", "%.3f" % now],
                       capture_output=True, text=True,
                       env=child_env(home), timeout=180)
    try:
        return p, json.loads(p.stdout)
    except ValueError:
        return p, None


def loud_codes(env):
    return [str(x).split(" ")[0].split(":")[0] for x in (env or {}).get("loud") or []]


def look(mod, run, now):
    """One read-only look; the module's loud printer must not reach our stdout."""
    with contextlib.redirect_stderr(io.StringIO()):
        return mod.build(str(run), now=now)


def scenario(mod_path, muts=frozenset()):
    c = H.Checks(ROW, TITLE)
    print("SC30 %s — run_watch %s%s"
          % (TITLE, mod_path,
             (" [defect: %s]" % ",".join(sorted(muts))) if muts else ""))
    mod = H.load_file(mod_path, "s75_run_watch_%s" % ROW)
    with H.Scratch() as tmp:
        now = time.time()
        home = Path(tmp) / "home"
        home.mkdir()
        wait_state = "RUNNING" if "undeclared_wait" in muts \
            else "WAITING_APPROVAL"
        run = fixture(tmp, now, "wait", wait_state)
        db = run / "control" / "state.sqlite3"
        decisions = run / "control" / "run-state.json"
        before = (digest(db), digest(decisions))

        env = look(mod, run, now)
        wait = env.get("wait")
        stalled = env.get("stalled")
        c.check("sc30:approval-wait-is-not-a-stall",
                stalled is False and env.get("stall_detail") == ""
                and isinstance(wait, dict)
                and wait.get("kind") == "client-approval"
                and wait.get("on") == APPROVAL_STAGE,
                "observed stalled=%r stall_detail=%r wait=%r (waited %d min "
                "with no durable event, past the 30-minute technical timeout)"
                % (stalled, env.get("stall_detail"), wait, 95))

        c.check("sc30:approval-wait-not-reported-as-failure",
                "HEARTBEAT_STALLED" not in loud_codes(env)
                and env.get("expired") is False
                and env.get("loop_should_stop") is False
                and env.get("supervising") is True,
                "observed loud=%r expired=%r loop_should_stop=%r "
                "supervising=%r"
                % (env.get("loud"), env.get("expired"),
                   env.get("loop_should_stop"), env.get("supervising")))

        later = now + 105 * 60
        capped = look(mod, run, later)
        c.check("sc30:wait-holds-past-the-supervision-cap",
                capped.get("expired") is False
                and capped.get("supervising") is True
                and capped.get("stalled") is False
                and "HEARTBEAT_EXPIRED" not in loud_codes(capped),
                "observed at elapsed_minutes=%r loud=%r expired=%r "
                "supervising=%r"
                % (capped.get("elapsed_minutes"), capped.get("loud"),
                   capped.get("expired"), capped.get("supervising")))

        if "state_removed" in muts:
            db.unlink()
        after = (digest(db), digest(decisions))
        proc, doc = fresh_read(mod_path, run, later, home)
        wait_after = (doc or {}).get("wait")
        c.check("sc30:state-not-killed-or-reaped",
                before[0] is not None and before == after
                and proc.returncode == 0
                and isinstance(wait_after, dict)
                and wait_after.get("kind") == "client-approval",
                "observed state.sqlite3 sha256 before=%s after=%s; "
                "run-state.json sha256 before=%s after=%s; fresh-interpreter "
                "rc=%r wait=%r"
                % (before[0], after[0], before[1], after[1],
                   proc.returncode, wait_after))

        control = fixture(tmp, now, "control", "RUNNING")
        ctl_env = look(mod, control, now)
        c.check("sc30:control-a-silent-running-stage-does-stall",
                ctl_env.get("stalled") is True
                and "HEARTBEAT_STALLED" in loud_codes(ctl_env)
                and ctl_env.get("wait") is None,
                "control (same age, stage RUNNING, no event): observed "
                "stalled=%r wait=%r loud=%r — the wait exemption is specific, "
                "not a blanket pass"
                % (ctl_env.get("stalled"), ctl_env.get("wait"),
                   ctl_env.get("loud")))
    return c


MUTATIONS = {
    # The run does not declare the human wait: the same silence becomes a stall.
    "undeclared_wait": ["sc30:approval-wait-is-not-a-stall",
                        "sc30:approval-wait-not-reported-as-failure",
                        "sc30:wait-holds-past-the-supervision-cap"],
    # A reaper deleted the state between looks.
    "state_removed": ["sc30:state-not-killed-or-reaped"],
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
