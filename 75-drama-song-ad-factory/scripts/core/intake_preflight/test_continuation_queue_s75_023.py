#!/usr/bin/env python3
"""S75-023: the next-action queue must not lose writes silently.

Run from the skill root:
  python3 -B scripts/core/intake_preflight/test_continuation_queue_s75_023.py

Behavioural checks, plain asserts, no framework, stdlib only:
  1. two processes enqueue 50 actions each at the same time -> 100 actions
     in the file, none lost;
  2. a queue file that exists but does not parse is preserved under
     continuation-queue.corrupt-<epoch>.json and the failure is named;
  3. a read-only control/ folder makes the write fail loudly and the returned
     action says queue_persisted is False;
  4. the queue keeps at most the last 500 actions.

Writes only under a temporary folder (TMPDIR) and one run folder per check.
"""
import glob
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parent
sys.path.insert(0, str(CORE))
sys.path.insert(0, str(HERE))

import factory as F  # noqa: E402

PASS = []

WORKER = r"""
import sys
core, here, run_dir = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, core)
sys.path.insert(0, here)
import factory
for _ in range(50):
    factory.continuation_enqueue(run_dir, "approval", run_id="run-1",
                                 stages=[], got={})
"""


def ok(name):
    PASS.append(name)
    print("PASS  %s" % name)


def read_queue(run_dir):
    p = Path(run_dir) / "control" / "continuation-queue.json"
    return json.loads(p.read_text(encoding="utf-8"))


def write_queue(run_dir, actions):
    control = Path(run_dir) / "control"
    control.mkdir(parents=True, exist_ok=True)
    (control / "continuation-queue.json").write_text(
        json.dumps(actions), encoding="utf-8")


def failure_codes(log_path):
    codes = []
    p = Path(log_path)
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                codes.append(json.loads(line).get("code"))
    return codes


def test_two_writers_lose_nothing():
    root = tempfile.mkdtemp(prefix="s75-023-concurrent-")
    try:
        run = Path(root) / "run"
        (run / "control").mkdir(parents=True)
        log = Path(root) / "failures.jsonl"
        env = dict(os.environ)
        env["DSAF_FAILURE_LOG"] = str(log)
        procs = [subprocess.Popen(
            [sys.executable, "-B", "-c", WORKER, str(CORE), str(HERE), str(run)],
            env=env) for _ in range(2)]
        for p in procs:
            assert p.wait(timeout=120) == 0, "a writer process failed"
        queue = read_queue(run)
        assert len(queue) == 100, "lost writes: %d of 100" % len(queue)
        assert all(a.get("run_id") == "run-1" for a in queue), queue
        assert failure_codes(log) == [], failure_codes(log)
        ok("two writers, 50 actions each, 100 in the file")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_corrupt_queue_is_preserved_and_named():
    root = tempfile.mkdtemp(prefix="s75-023-corrupt-")
    try:
        run = Path(root) / "run"
        write_queue(run, [])
        qpath = run / "control" / "continuation-queue.json"
        qpath.write_text("{not json", encoding="utf-8")
        log = Path(root) / "failures.jsonl"
        os.environ["DSAF_FAILURE_LOG"] = str(log)
        try:
            action = F.continuation_enqueue(run, "approval", run_id="run-1",
                                            stages=[], got={})
        finally:
            os.environ.pop("DSAF_FAILURE_LOG", None)
        assert action.get("queue_persisted") is True, action
        corrupt = sorted(glob.glob(str(run / "control" /
                                       "continuation-queue.corrupt-*.json")))
        assert len(corrupt) == 1, corrupt
        assert Path(corrupt[0]).read_text(encoding="utf-8") == "{not json"
        queue = read_queue(run)
        assert len(queue) == 1 and queue[0]["run_id"] == "run-1", queue
        assert "CONTINUATION_QUEUE_CORRUPT" in failure_codes(log), \
            failure_codes(log)
        ok("a non-parsing queue is preserved and named")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_read_only_control_is_loud_and_not_persisted():
    root = tempfile.mkdtemp(prefix="s75-023-readonly-")
    control = None
    try:
        run = Path(root) / "run"
        control = run / "control"
        control.mkdir(parents=True)
        log = Path(root) / "failures.jsonl"
        os.environ["DSAF_FAILURE_LOG"] = str(log)
        os.chmod(str(control), stat.S_IRUSR | stat.S_IXUSR |
                 stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
        try:
            action = F.continuation_enqueue(run, "approval", run_id="run-1",
                                            stages=[], got={})
        finally:
            os.environ.pop("DSAF_FAILURE_LOG", None)
            os.chmod(str(control), 0o755)
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            print("SKIP  read-only folder check: running as root")
        else:
            assert action.get("queue_persisted") is False, action
            assert not (control / "continuation-queue.json").exists()
            assert "CONTINUATION_QUEUE_WRITE_FAILED" in failure_codes(log), \
                failure_codes(log)
            ok("a read-only control folder is loud and not persisted")
    finally:
        if control is not None and control.exists():
            os.chmod(str(control), 0o755)
        shutil.rmtree(root, ignore_errors=True)


def test_queue_keeps_last_500():
    root = tempfile.mkdtemp(prefix="s75-023-cap-")
    try:
        run = Path(root) / "run"
        write_queue(run, [{"event": "old", "n": i} for i in range(600)])
        action = F.continuation_enqueue(run, "approval", run_id="run-1",
                                        stages=[], got={})
        assert action.get("queue_persisted") is True, action
        queue = read_queue(run)
        assert len(queue) == 500, len(queue)
        assert queue[-1]["event"] == "approval", queue[-1]
        assert queue[-1]["run_id"] == "run-1", queue[-1]
        ok("the queue keeps the last 500 actions")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main():
    test_two_writers_lose_nothing()
    test_corrupt_queue_is_preserved_and_named()
    test_read_only_control_is_loud_and_not_persisted()
    test_queue_keeps_last_500()
    print("\nALL %d CHECKS PASSED" % len(PASS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
