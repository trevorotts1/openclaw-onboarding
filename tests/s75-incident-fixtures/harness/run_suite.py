#!/usr/bin/env python3
"""Fixture suite runner: one isolated driver per fixture, repro verdicts printed.

Usage:
  python3 harness/run_suite.py --core-999 <core> --pending-head <root> \
      --timer-dir <dir> --tmp <scratch> [--only S75-F01] [--log <path>]

Exits 0 only when every executed fixture REPRODUCES its documented defect.
Runtime paths are injected as arguments and never appear in the output.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIXDIR = os.path.join(os.path.dirname(HERE), "fixtures")


def compare(fixture_id, expected, observed):
    """Containment for lists, equality for scalars. Returns (ok, problems)."""
    problems = []
    for k, want in expected.items():
        got = observed.get(k)
        if isinstance(want, list):
            if not isinstance(got, list) or not all(w in got for w in want):
                problems.append("%s: want %r within %r" % (k, want, got))
        elif want != got:
            problems.append("%s: want %r got %r" % (k, want, got))
    return (not problems), problems


def run_one(args, fixture_id):
    cmd = [sys.executable, "-B", "-I", os.path.join(HERE, "_run_one.py"),
           "--fixture", fixture_id, "--core-999", args.core_999,
           "--pending-head", args.pending_head, "--timer-dir", args.timer_dir,
           "--tmp", args.tmp, "--fixtures-dir", FIXDIR]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    try:
        res = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        return {"fixture_id": fixture_id, "status": "runner-error",
                "error": (r.stdout + r.stderr)[-400:]}
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--core-999", required=True)
    ap.add_argument("--pending-head", required=True)
    ap.add_argument("--timer-dir", required=True)
    ap.add_argument("--tmp", required=True)
    ap.add_argument("--only")
    ap.add_argument("--log")
    a = ap.parse_args()
    ids = [a.only] if a.only else sorted(
        f[:-5] for f in os.listdir(FIXDIR) if f.endswith(".json"))
    log = []
    failed = 0
    for fid in ids:
        fx = json.load(open(os.path.join(FIXDIR, fid + ".json")))
        res = run_one(a, fid)
        if res.get("status") != "ran":
            verdict, problems = "DRIVER-ERROR", [str(res.get("error"))]
        else:
            ok, problems = compare(fid, fx["observed_defect"], res["observed"])
            verdict = "REPRODUCED" if ok else "MISMATCH"
        if verdict != "REPRODUCED":
            failed += 1
        line = "%s %s %s" % (fid, verdict, fx["pattern"])
        print(line)
        for pr in problems:
            print("  ! " + pr)
        log.append({"fixture_id": fid, "pattern": fx["pattern"], "verdict": verdict,
                    "observed": res.get("observed"), "problems": problems,
                    "driver_error": res.get("error")})
    print("SUMMARY %d/%d reproduced" % (len(ids) - failed, len(ids)))
    if a.log:
        with open(a.log, "w") as f:
            json.dump(log, f, indent=1, sort_keys=True, default=str)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
