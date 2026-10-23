#!/usr/bin/env python3
"""sc33_merge_window_delegates_to_wm.py — acceptance row SC-33 (S75-W10-U1).

Condition (SCENARIO-MATRIX.json, row SC-33, verbatim):
    "Merge windows delegating to S75-WM"

Required result (verbatim):
    "NEGATIVE: merge-window handling delegates to S75-WM; the unit never merges
     or pushes on its own"

The enforcement is the REAL timer of the tree under test:
``.claude/skills/spec-protocol/tools/watch-tick.sh`` (installed copy under
``~/.claude/skills/spec-protocol/tools`` unless an explicit root is named) —
section 4e of its contract: every MERGE_BATCH_MINUTES the tick reaches a merge
WINDOW and writes ONE durable request into ``<area>/wm-queue/`` addressed to
the visible S75-WM workflow. The timer executes NO integration tool, and a
zero cadence is REJECTED (it used to mean "eligible on every tick").

The "never merges" half is proven by a canary: WATCH_MERGE_TRAIN_SH points at
a stub that writes a marker the moment any path executes it, and the marker
must never appear.

Fixtures only (a tmp project home); no real project, no network, no provider,
no channel.

Modes:
  (no flag)   run the scenario and print one assertion line per check
  --dry-run   identical checks, receipt marked mode=dry-run
  selftest    re-run under deliberate defects and REQUIRE the named
              assertions to turn RED (proves the harness can fail)

Exit 0 = every assertion held; 1 = at least one failed; 2 = tooling.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

ROW = "sc33"
TITLE = "a merge window enqueues to S75-WM and never merges or pushes itself"
TOOLS_REL = Path(".claude/skills/spec-protocol/tools")


def _real_home():
    try:
        import pwd
        return Path(pwd.getpwuid(os.getuid()).pw_dir)
    except Exception:
        return Path.home()


def resolve_tools(args):
    """The spec-protocol tools dir under test.

    An explicitly named --tools-root is AUTHORITATIVE: if it holds no
    watch-tick.sh the harness exits 2 and names the path. It never falls back
    to the installed copy, which would let the row pass against a revision the
    operator did not name.
    """
    if args.tools_root:
        named = Path(args.tools_root).expanduser()
        if (named / "watch-tick.sh").is_file():
            return named
        print("TOOLING: --tools-root %s contains no watch-tick.sh; refusing to "
              "fall back to a different copy" % named)
        raise SystemExit(2)
    cands = []
    env = os.environ.get("SPEC_PROTOCOL_TOOLS_ROOT")
    if env:
        cands.append(Path(env).expanduser())
    cands.append(_real_home() / TOOLS_REL)
    cands.append(Path(args.tree) / TOOLS_REL)
    for c in cands:
        if (c / "watch-tick.sh").is_file():
            return c
    print("TOOLING: watch-tick.sh not found; looked at %s"
          % ", ".join(str(c) for c in cands))
    raise SystemExit(2)


def mk_home(base):
    """The minimum project home the tick reads (the selftest's own fixture)."""
    home = Path(base) / "project"
    (home / "SPEC").mkdir(parents=True)
    (home / "CONTROL").mkdir(parents=True)
    (home / "SPEC" / "GOAL.md").write_text("Goal: build the thing.\n")
    (home / "CONTROL" / "setup_progress.json").write_text('{"step":4,"of":9}\n')
    (home / "CONTROL" / "CHECKLIST.md").write_text(
        "- [x] U-01 build the parser\n- [ ] U-02 qc the parser\n")
    (home / "CONTROL" / "TODO.md").write_text("- [ ] U-02 qc the parser\n")
    return home


def tick_env(base, home, extra=None):
    """A child env that can never open a window, launch a session or integrate."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONPATH", "OPENCLAW_HOME")}
    canary = Path(base) / "merge-train-canary"
    marker = Path(base) / "merge-train-executed.marker"
    canary.write_text('#!/bin/sh\necho executed > "%s"\nexit 0\n' % marker)
    canary.chmod(0o755)
    env.update({
        "HOME": str(Path(base) / "home"),
        "XDG_STATE_HOME": str(Path(base) / "xdg"),
        "WATCH_TICK_LAUNCHER_CMD": "/usr/bin/true",
        "WATCH_TICK_OPEN_CMD": "/usr/bin/false",
        "WATCH_TICK_OSASCRIPT_CMD": "/usr/bin/false",
        "WATCH_TICK_CRONTAB_FILE": str(Path(base) / "crontab.fixture"),
        "WATCH_MERGE_TRAIN_SH": str(canary),
        "MERGE_BATCH_DISABLE": "1",
    })
    env.update(extra or {})
    return env


def run_tick(tools, home, env):
    try:
        p = subprocess.run(["bash", str(tools / "watch-tick.sh"), str(home)],
                           capture_output=True, text=True, env=env, timeout=300)
        return p.returncode, p.stdout + p.stderr, ""
    except subprocess.TimeoutExpired:
        return None, "", "watch-tick.sh exceeded 300s"


def requests(home):
    return sorted(home.rglob("*.request.json"))


def stamp(home):
    found = sorted(home.rglob("merge-batch.stamp"))
    return found[0] if found else None


def actions(out):
    return [l for l in out.splitlines() if l.startswith("ACTION|wm-merge-request|")]


def scenario(tools, muts=frozenset()):
    c = H.Checks(ROW, TITLE)
    print("SC33 %s — watch-tick %s%s"
          % (TITLE, tools / "watch-tick.sh",
             (" [defect: %s]" % ",".join(sorted(muts))) if muts else ""))
    with H.Scratch() as tmp:
        base = Path(tmp)
        (base / "home").mkdir()
        home = mk_home(base)
        marker = base / "merge-train-executed.marker"

        zero_cadence = "10" if "cadence_not_rejected" in muts else "0"
        rc, out, err = run_tick(tools, home, tick_env(base, home, {
            "MERGE_BATCH_DISABLE": "0",
            "MERGE_BATCH_MINUTES": zero_cadence}))
        c.check("sc33:zero-cadence-rejected-by-name",
                rc == 2
                and "MERGE_BATCH_MINUTES must be a positive integer" in out
                and "MERGE_BATCH_DISABLE=1" in out
                and "S-CHECK" not in out,
                "observed rc=%r with MERGE_BATCH_MINUTES=%s: the rejection "
                "text present=%r, the explicit disable named=%r, a tick ran=%r"
                % (rc, zero_cadence,
                   "MERGE_BATCH_MINUTES must be a positive integer" in out,
                   "MERGE_BATCH_DISABLE=1" in out, "S-CHECK" in out))

        rc1, out1, err1 = run_tick(tools, home, tick_env(base, home, {
            "MERGE_BATCH_DISABLE": "0", "MERGE_BATCH_MINUTES": "10"}))
        reqs = requests(home)
        req = json.loads(reqs[0].read_text()) if len(reqs) == 1 else {}
        c.check("sc33:due-window-enqueues-one-wm-request",
                len(reqs) == 1
                and req.get("from") == "watch-tick.timer"
                and req.get("to") == "S75-WM"
                and req.get("action") == "run-merge-train-batch"
                and len(actions(out1)) == 1
                and "MERGE-WINDOW | " in out1 and "| delegated |" in out1,
                "observed rc=%r, %d request file(s) %r, fields from=%r to=%r "
                "action=%r, ACTION lines=%d, MERGE-WINDOW delegated line=%r, "
                "run error=%r"
                % (rc1, len(reqs), [p.name for p in reqs], req.get("from"),
                   req.get("to"), req.get("action"), len(actions(out1)),
                   any(l.startswith("MERGE-WINDOW | ") and "| delegated |" in l
                       for l in out1.splitlines()), err1))

        if "duplicate_requests" in muts and reqs:
            first = reqs[0]
            shutil.copy2(first, first.with_name("stacked-copy.request.json"))
        st = stamp(home)
        if st is not None:
            old = time.time() - 3600
            os.utime(st, (old, old))
        rc2, out2, err2 = run_tick(tools, home, tick_env(base, home, {
            "MERGE_BATCH_DISABLE": "0", "MERGE_BATCH_MINUTES": "10"}))
        reqs2 = requests(home)
        windows = 1
        try:
            windows = int(json.loads(reqs2[0].read_text()).get("requested_windows"))
        except (IndexError, ValueError, TypeError):
            windows = None
        c.check("sc33:one-open-request-is-extended-not-duplicated",
                len(reqs2) == 1 and windows == 2 and len(actions(out2)) == 0,
                "observed %d request file(s) after the second due window, "
                "requested_windows=%r (want 2), ACTION lines in that run=%d "
                "(want 0 — one durable request, one delegation), run error=%r"
                % (len(reqs2), windows, len(actions(out2)), err2))

        st = stamp(home)
        if "stamp_not_fresh" not in muts and st is not None:
            now = time.time()
            os.utime(st, (now, now))
        rc3, out3, err3 = run_tick(tools, home, tick_env(base, home, {
            "MERGE_BATCH_DISABLE": "0", "MERGE_BATCH_MINUTES": "10"}))
        reqs3 = requests(home)
        c.check("sc33:control-a-fresh-window-is-not-due",
                len(reqs3) == len(reqs2)
                and "MERGE-WINDOW" not in out3
                and "merge-batch=not-due" in out3,
                "observed rc=%r, %d request file(s) (unchanged from %d=%r), a "
                "MERGE-WINDOW line=%r, the S-CHECK not-due note=%r, run error=%r"
                % (rc3, len(reqs3), len(reqs2), len(reqs3) == len(reqs2),
                   "MERGE-WINDOW" in out3, "merge-batch=not-due" in out3, err3))

        c.check("sc33:no-timer-originated-merge-or-push",
                not marker.is_file()
                and "MERGED:" not in out1 + out2 + out3
                and "LANDED:" not in out1 + out2 + out3,
                "observed merge-train canary marker at %s exists=%r after "
                "every tick; MERGED/LANDED lines in the tick output=%r — the "
                "timer only enqueues"
                % (marker, marker.is_file(),
                   any(t in out1 + out2 + out3 for t in ("MERGED:", "LANDED:"))))
    return c


MUTATIONS = {
    # A nonzero cadence is used where the zero cadence must be refused.
    "cadence_not_rejected": ["sc33:zero-cadence-rejected-by-name"],
    # A duplicate request was stacked instead of extending the open one.
    "duplicate_requests": ["sc33:one-open-request-is-extended-not-duplicated"],
    # The stamp is left stale, so the "not due" window acts anyway.
    "stamp_not_fresh": ["sc33:control-a-fresh-window-is-not-due"],
}


def selftest(tools):
    ok = True
    for name in sorted(MUTATIONS):
        c = scenario(tools, frozenset([name]))
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
    ap.add_argument("--tools-root", default=None,
                    help="the spec-protocol tools dir under test")
    ap.add_argument("--dry-run", action="store_true")
    if argv and argv[0] == "selftest":
        args = ap.parse_args(argv[1:])
        return selftest(resolve_tools(args))
    args = ap.parse_args(argv)
    result = scenario(resolve_tools(args))
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
