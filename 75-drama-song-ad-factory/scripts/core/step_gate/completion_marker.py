#!/usr/bin/env python3
"""completion_marker.py - N-51: wait on a completion marker, never a timer.

Section 3D.6. A step is finished when it writes a marker holding its output's
content fingerprint. The next step reads the marker; it never sleeps on a
timer and never gives up on elapsed time alone. When a marker is past its
deadline the keep-on-track loop restarts that ONE step.

The marker is ``control/markers/<step>.json``:
  {"schema": "blackceo.completion-marker/v1",
   "step": "<step>", "output": "<relative output>",
   "sha256": "<sha256 of the output bytes>", "bytes": <int>,
   "completed_unix": <float>}
A marker whose output no longer has the recorded sha256 is STALE, not ready.

This module evaluates state once per call; it never blocks or polls. A caller
waits by re-reading ``decision`` on the next keep-on-track tick (10E: two
minutes), which is a marker check, not a timer wait.
"""
import argparse
import hashlib
import json
import os
import sys

SCHEMA = "blackceo.completion-marker/v1"
MARKER_REL = os.path.join("control", "markers")


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def marker_path(run_dir, step):
    return os.path.join(run_dir, MARKER_REL, "%s.json" % step)


def write_marker(run_dir, step, output_rel, now=None):
    """Write a marker that fingerprints the step's output. Refuses an absent output."""
    output_path = os.path.join(run_dir, output_rel)
    if not os.path.isfile(output_path):
        raise FileNotFoundError("step %r output %r does not exist" % (step, output_rel))
    marker = {"schema": SCHEMA, "step": str(step), "output": output_rel,
              "sha256": _sha256_file(output_path),
              "bytes": os.path.getsize(output_path),
              "completed_unix": float(now if now is not None else _now())}
    path = marker_path(run_dir, step)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(marker, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)
    return marker


def read_marker(run_dir, step):
    path = marker_path(run_dir, step)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def marker_state(run_dir, step):
    """Return ``present`` (and fresh), ``stale`` or ``absent``."""
    marker = read_marker(run_dir, step)
    if marker is None:
        return "absent", None
    output = os.path.join(run_dir, marker.get("output") or "")
    if not os.path.isfile(output):
        return "stale", marker
    if _sha256_file(output) != marker.get("sha256"):
        return "stale", marker
    return "present", marker


def decision(run_dir, step, deadline_unix=None, now=None):
    """One-shot state: ready | waiting | overdue | stale.

    ``overdue`` needs a deadline; without one an absent marker is ``waiting``.
    A stale marker is always a restart (its step wrote it over a changed output).
    """
    state, marker = marker_state(run_dir, step)
    if state == "present":
        return {"step": step, "decision": "ready", "marker": marker}
    if state == "stale":
        return {"step": step, "decision": "stale",
                "action": "restart this one step; its output changed after the marker"}
    now = float(now if now is not None else _now())
    if deadline_unix is not None and now > float(deadline_unix):
        return {"step": step, "decision": "overdue", "deadline_unix": deadline_unix,
                "action": "restart this one step; its marker is overdue"}
    return {"step": step, "decision": "waiting", "marker": None}


def overdue_steps(run_dir, deadlines, now=None):
    """Return the steps whose marker is missing/stale past their own deadline."""
    now = float(now if now is not None else _now())
    due = []
    for step, deadline in (deadlines or {}).items():
        verdict = decision(run_dir, step, deadline, now)
        if verdict["decision"] in ("overdue", "stale"):
            due.append(verdict)
    return due


def _now():
    import time
    return time.time()


def selftest():
    import tempfile
    proofs = []
    with tempfile.TemporaryDirectory() as run:
        out = os.path.join(run, "out.json")
        with open(out, "w", encoding="utf-8") as fh:
            json.dump({"result": "real"}, fh)
        proofs.append(("an absent marker is waiting before its deadline",
                       decision(run, "join", deadline_unix=1000, now=10)["decision"]
                       == "waiting"))
        write_marker(run, "join", "out.json", now=10)
        proofs.append(("a written marker reads ready",
                       decision(run, "join", now=11)["decision"] == "ready"))
        proofs.append(("an absent marker past its deadline is overdue",
                       decision(run, "master", deadline_unix=1000, now=1001)["decision"]
                       == "overdue"))
        with open(out, "w", encoding="utf-8") as fh:
            json.dump({"result": "changed after the marker"}, fh)
        proofs.append(("a changed output makes the marker stale, not ready",
                       decision(run, "join", now=12)["decision"] == "stale"))
        due = overdue_steps(run, {"join": 5, "master": 999}, now=1001)
        proofs.append(("overdue_steps names only the missing/stale step",
                       [d["step"] for d in due] == ["master"]))
    for name, ok in proofs:
        print(("ok   " if ok else "FAIL ") + name)
    return 0 if all(ok for _, ok in proofs) else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run-dir", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_write = sub.add_parser("write")
    p_write.add_argument("--step", required=True)
    p_write.add_argument("--output", required=True)
    p_check = sub.add_parser("check")
    p_check.add_argument("--step", required=True)
    p_check.add_argument("--deadline-unix", type=float, default=None)
    sub.add_parser("selftest")
    args = ap.parse_args(argv)
    if args.cmd == "selftest":
        return selftest()
    if args.cmd == "write":
        out = write_marker(args.run_dir, args.step, args.output)
    else:
        out = decision(args.run_dir, args.step, args.deadline_unix)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
