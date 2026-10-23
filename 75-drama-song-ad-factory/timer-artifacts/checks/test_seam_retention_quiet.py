#!/usr/bin/env python3
"""test_seam_retention_quiet.py — W07-U2 seams for the persistent timer (D34).

Proves the two behaviors installed through the existing runtime-maintenance
owner (timer-artifacts/run-timer.sh) plus the readiness seam W07-U3 builds on:

  T1  bounded log retention: past DS_LOG_MAX_BYTES the log keeps only its last
      half, in place; an under-cap log is untouched (negative control).
  T2  quiet disabled capability: capability.disabled / DS_CAPABILITY_DISABLED=1
      -> exit 0, no poll, and steady-state silence after one transition line;
      without the marker the same run is a visible refusal (negative control).
  T3  transition notices: an unpaired box with an existing state dir says "not
      paired" once per state change, never once per tick.
  T4  no-write invariant: with NO state dir the unpaired poller writes nothing
      (it is a reader until pairing) — the contract timer check G narrates.
  T5  readiness seam: --ready exits 0 and prints one "ready:" line exactly when
      key, address, bridge and interpreter all resolve; a bogus argument is
      refused with exit 1 (negative control).
  T6  capability.json is evaluated BEFORE the credential demand: a recorded
      disabled / needs-enrollment capability is a quiet exit 0 even with no
      machine.url/machine.key; a recorded ready capability is still REFUSED
      (exit 2) without them, and --ready is never skipped (negative controls).
  T7  ordinary chat intake stays independent of Studio pairing: the factory's
      intake envelope is produced with no capability record and no credentials.

Run:  python3 test_seam_retention_quiet.py      (exit 0 all pass, 1 any fail)
Writes only in its scratch (DS_TEST_SCRATCH, else a mkdtemp under HOME — the
mac state rule requires HOME; removed in a finally block). No network, no
scheduler registration, no real key values. Stdlib only.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                      # timer-artifacts/
RUN_TIMER = os.path.join(ROOT, "run-timer.sh")

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("  [%s] %s%s" % ("PASS" if ok else "FAIL", name,
                           (" — " + detail) if detail else ""))
    return ok


def run_timer(state_dir, extra=None, args=(), log_file=None, log_cap=None):
    env = dict(os.environ)
    env.update({"DS_PLATFORM": "mac", "DS_STATE_DIR": state_dir})
    if log_file is not None:
        env["DS_LOG_FILE"] = log_file
    if log_cap is not None:
        env["DS_LOG_MAX_BYTES"] = str(log_cap)
    if extra:
        env.update(extra)
    return subprocess.run([RUN_TIMER, *args], capture_output=True, text=True,
                          env=env, cwd=ROOT)


def main():
    if sys.platform != "darwin":
        print("SKIP: mac-only exercise (run-timer identity rules are per platform)")
        return 0
    home = os.path.expanduser("~")
    scratch = os.environ.get("DS_TEST_SCRATCH") or tempfile.mkdtemp(
        prefix="s75-w07-u2-seam-", dir=home)
    os.makedirs(scratch, exist_ok=True)
    try:
        state = os.path.join(scratch, "state")
        log = os.path.join(scratch, "timer.log")

        # ---- T4 first: no state dir -> the poller writes nothing -----------
        ghost = os.path.join(scratch, "ghost-state")
        r = run_timer(ghost, log_file=os.path.join(scratch, "ghost.log"))
        check("T4-no-write-without-state-dir",
              r.returncode == 2 and not os.path.exists(ghost),
              "rc=%s created=%s" % (r.returncode, os.path.exists(ghost)))

        # ---- T3: transition notices, steady state silent -------------------
        os.makedirs(state)
        r1 = run_timer(state, log_file=log)
        r2 = run_timer(state, log_file=log)
        check("T3-transition-notice-once",
              r1.returncode == 2 and "not paired" in r1.stderr
              and r2.returncode == 2 and r2.stderr.strip() == "",
              "run1 rc=%s run2 rc=%s" % (r1.returncode, r2.returncode))
        # state change (a pairing attempt resolved) -> the notice returns
        with open(os.path.join(state, ".poll-state"), "w") as f:
            f.write("ok\n")
        r3 = run_timer(state, log_file=log)
        check("T3-notice-returns-on-transition",
              r3.returncode == 2 and "not paired" in r3.stderr)

        # ---- T2: quiet disabled capability --------------------------------
        with open(os.path.join(state, "capability.disabled"), "w") as f:
            f.write("operator disabled studio (chat-only box)\n")
        r1 = run_timer(state, log_file=log)
        r2 = run_timer(state, log_file=log)
        check("T2-disabled-marker-quiet",
              r1.returncode == 0 and r2.returncode == 0
              and r2.stderr.strip() == "" and r2.stdout.strip() == "",
              "run1 rc=%s run2 rc=%s" % (r1.returncode, r2.returncode))
        os.remove(os.path.join(state, "capability.disabled"))
        rn = run_timer(state, log_file=log)
        check("T2-negative-control-refuses-when-enabled",
              rn.returncode == 2 and "not paired" in rn.stderr,
              "rc=%s" % rn.returncode)
        r1 = run_timer(state, extra={"DS_CAPABILITY_DISABLED": "1"}, log_file=log)
        r2 = run_timer(state, extra={"DS_CAPABILITY_DISABLED": "1"}, log_file=log)
        check("T2-env-disabled-quiet",
              r1.returncode == 0 and r2.returncode == 0 and r2.stderr.strip() == "")

        # ---- T6: capability.json evaluated BEFORE credential demand --------
        # The canonical record (written by studio_bridge.py) must be honoured
        # ahead of machine.url/machine.key. A chat-only box is quiet; an
        # enabled-but-broken box is still refused.
        cap = os.path.join(state, "capability.json")
        with open(cap, "w") as f:
            f.write('{\n  "capability": "disabled",\n  "intent": "disabled"\n}\n')
        r1 = run_timer(state, log_file=log)
        r2 = run_timer(state, log_file=log)
        check("T6-capability-json-disabled-quiet-before-credentials",
              r1.returncode == 0 and r2.returncode == 0
              and r2.stderr.strip() == "" and r2.stdout.strip() == "",
              "run1 rc=%s run2 rc=%s" % (r1.returncode, r2.returncode))
        with open(cap, "w") as f:
            f.write('{\n  "capability": "needs-enrollment"\n}\n')
        run_timer(state, log_file=log)          # consume the disabled -> change transition
        r = run_timer(state, log_file=log)
        check("T6-capability-json-needs-enrollment-quiet",
              r.returncode == 0 and r.stderr.strip() == "", "rc=%s" % r.returncode)
        with open(cap, "w") as f:
            f.write('{\n  "capability": "ready"\n}\n')
        os.remove(os.path.join(state, ".poll-state"))
        r = run_timer(state, log_file=log)
        check("T6-negative-control-enabled-no-key-refuses",
              r.returncode == 2 and "not paired" in r.stderr, "rc=%s" % r.returncode)
        os.remove(os.path.join(state, ".poll-state"))
        r = run_timer(state, args=("--ready",), log_file=log)
        check("T6-negative-control-ready-probe-not-skipped",
              r.returncode == 2 and "not paired" in r.stderr, "rc=%s" % r.returncode)
        os.remove(cap)

        # ---- T7: chat intake is independent of Studio pairing --------------
        factory = os.path.join(os.path.dirname(ROOT), "scripts", "core",
                               "intake_preflight", "factory.py")
        if os.path.exists(factory):
            brief = ('{"offer": "demo offer", "audience": "busy parents", '
                     '"action": "buy now"}')
            ir = subprocess.run([sys.executable, factory, "intake", "--brief", brief],
                                capture_output=True, text=True, cwd=os.path.dirname(ROOT),
                                env=dict(os.environ, DRAMA_STUDIO_STATE=state))
            try:
                env_json = json.loads(ir.stdout)
            except Exception:
                env_json = {}
            outcome = env_json.get("outcome")
            blob = (ir.stdout + ir.stderr).lower()
            check("T7-chat-intake-independent-of-pairing",
                  outcome in ("ok", "waiting") and "not paired" not in blob
                  and "no_key" not in blob,
                  "rc=%s outcome=%s" % (ir.returncode, outcome))

        # ---- T1: bounded log retention ------------------------------------
        big = "x" * 5000 + "SENTINEL-TAIL\n"
        with open(log, "w") as f:
            f.write(big)
        r = run_timer(state, extra={"DS_CAPABILITY_DISABLED": "1"},
                      log_file=log, log_cap=1000)
        body = open(log).read()
        check("T1-log-trimmed-to-cap",
              len(body) <= 1000 and "SENTINEL-TAIL" in body
              and "log retention" in r.stderr,
              "size=%s" % len(body))
        with open(log, "w") as f:
            f.write("small log\n")
        r = run_timer(state, extra={"DS_CAPABILITY_DISABLED": "1"},
                      log_file=log, log_cap=1000)
        check("T1-negative-control-small-log-untouched",
              open(log).read() == "small log\n" and "log retention" not in r.stderr)

        # ---- T5: readiness seam -------------------------------------------
        os.remove(os.path.join(state, ".poll-state"))
        r = run_timer(state, args=("--ready",), log_file=log)
        check("T5-ready-refuses-unpaired",
              r.returncode == 2 and "not paired" in r.stderr,
              "rc=%s" % r.returncode)
        with open(os.path.join(state, "machine.key"), "w") as f:
            f.write("unit-test-fake-key\n")
        with open(os.path.join(state, "machine.url"), "w") as f:
            f.write("https://studio.invalid\n")
        r = run_timer(state, args=("--ready",), log_file=log)
        check("T5-ready-when-fully-resolved",
              r.returncode == 0 and "ready:" in r.stderr,
              "rc=%s %s" % (r.returncode, r.stderr.strip()[:120]))
        r = run_timer(state, args=("--bogus",), log_file=log)
        check("T5-negative-control-bogus-argument",
              r.returncode == 1 and "unknown argument" in r.stderr)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    print("\n%s passed, %s failed" % (len(PASS), len(FAIL)))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
