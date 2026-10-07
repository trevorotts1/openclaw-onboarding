"""Shared helpers for the W4-03-U1 resume/repair evidence suite. Stdlib only.

Never imported as a test (runner only executes test_*.py). Temp scratch is
prefixed lane-W4-03-U1- under /tmp per lane hygiene; each test removes its
own scratch in a finally block.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
CORE = os.path.join(ROOT, "core")
FACTORY = os.path.join(CORE, "intake_preflight", "factory.py")
LEDGER = os.path.join(CORE, "spend_ledger.py")
RECOVERY = os.path.join(CORE, "job_recovery.py")
FIXTURES = os.path.join(HERE, "fixtures")
EVIDENCE = os.path.join(HERE, "evidence")

# spend_ledger.py / job_recovery.py import spend_ledger as a sibling module.
for p in (CORE, os.path.dirname(FACTORY), HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

# spend_ledger.py exit codes: ok 0, waiting 3, parked 4, rejected 5, error 1.
# factory.py exit codes:     ok 0, waiting 2, parked 3, rejected 4, error 1.
RC = {"ok": 0, "ok_ledger": 0, "ok_factory": 0,
      "waiting_ledger": 3, "parked_ledger": 4, "rejected_ledger": 5,
      "error_ledger": 1, "waiting_factory": 2, "parked_factory": 3,
      "rejected_factory": 4, "error_factory": 1}

CHECKS = []


def check(name, cond, detail=""):
    """Record one evidence check; fail hard on False (fault-suite style)."""
    row = {"check": name, "pass": bool(cond)}
    if detail != "":
        row["detail"] = detail
    CHECKS.append(row)
    assert cond, "FAILED: %s%s" % (name, (" -- " + str(detail)) if detail else "")
    print("ok: %s" % name)


def mktmp():
    """Box temp dir: /tmp/lane-W4-03-U1-XXXX."""
    return tempfile.mkdtemp(prefix="lane-W4-03-U1-", dir="/tmp")


def rm_tmp(path):
    if path and os.path.isdir(path) and os.path.basename(path).startswith(
            "lane-W4-03-U1-"):
        shutil.rmtree(path, ignore_errors=True)


def run_py(script, *args):
    """Run a stdlib CLI, capture rc + parsed JSON envelope."""
    proc = subprocess.run([sys.executable, script] + [str(a) for a in args],
                          capture_output=True, text=True, timeout=120)
    out = proc.stdout.strip()
    env = None
    if out:
        try:
            env = json.loads(out)
        except ValueError:
            env = None
    return env, proc.returncode, proc.stderr.strip()


def ledger(db, *args):
    return run_py(LEDGER, "--db", db, *args)


def factory(*args):
    return run_py(FACTORY, *args)


def recover(db, run_id):
    return run_py(RECOVERY, "--db", db, "recover", "--run", run_id)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_evidence(name, payload):
    """Persist suite evidence inside the owned output tree."""
    os.makedirs(EVIDENCE, exist_ok=True)
    path = os.path.join(EVIDENCE, name)
    doc = {"schema": "blackceo.resume-repair-evidence/v1",
           "unit": "W4-03-U1",
           "suite": name,
           "checks": CHECKS,
           "pass_count": sum(1 for c in CHECKS if c["pass"]),
           "fail_count": sum(1 for c in CHECKS if not c["pass"]),
           "payload": payload}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, sort_keys=True, default=str)
        f.write("\n")
    print("evidence: %s" % path)
    return path


def finish(name, payload):
    """Write evidence then exit with the suite's own pass/fail code."""
    write_evidence(name, payload)
    if any(not c["pass"] for c in CHECKS):
        print("SUMMARY FAIL %s (%d checks)" % (name, len(CHECKS)))
        sys.exit(1)
    print("SUMMARY PASS %s (%d checks)" % (name, len(CHECKS)))
    sys.exit(0)
