#!/usr/bin/env python3
"""rr_install_verify.py - prove the Rescue Rangers files are really installed on a box.

DRAFT. Not installed anywhere. Target home after build:
  onboarding repo  65-rescue-receiver/rr_install_verify.py

It REPLACES the unconditional line in 65-rescue-receiver/wire.sh (line 409 at
onboarding v27.1.71):
    echo "65-rescue-receiver: files-installed=1 (this installer claims INSTALLATION; ...)"
That line is printed whether or not the files the poll needs are present. The
poll needs shared-utils/rescue-supervise.py to take its lock; when that one file
is missing, every poll exits having done nothing, and the installer still says
files-installed=1.

This script checks every required file: it exists, it is not empty, and it
parses (Python files with ast, shell files with "sh -n" or "bash -n"). It prints
one JSON object and exits 0 only when every file passes.

Exit codes: 0 all present and parse, 20 one or more missing/empty/unparseable,
            2 the skills folder itself was not found.

Usage:
  python3 rr_install_verify.py --skills-root "<openclaw root>/skills"
  python3 rr_install_verify.py --selftest
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
import tempfile

# (path relative to the skills folder, kind)
REQUIRED = [
    ("65-rescue-receiver/rescue-poll.sh", "sh"),
    ("65-rescue-receiver/rescue-notification.py", "py"),
    ("65-rescue-receiver/rr-readiness.sh", "bash"),
    ("65-rescue-receiver/rr-intake-auth-check.sh", "bash"),
    ("65-rescue-receiver/wire.sh", "bash"),
    ("65-rescue-receiver/contracts/result-v3.schema.json", "json"),
    ("shared-utils/rescue-env.sh", "sh"),
    ("shared-utils/rescue-supervise.py", "py"),
    ("shared-utils/rr-readiness.sh", "bash"),
    ("shared-utils/oc-env-descriptor.sh", "bash"),
]
# Added by the build in 01-BUILD-SPEC.md; listed separately so this script can be
# merged before or after them without failing a box that is mid-roll.
ADDED_BY_THIS_BUILD = [
    ("65-rescue-receiver/rr_escalate.py", "py"),
    ("65-rescue-receiver/rr_journal_check.py", "py"),
    ("65-rescue-receiver/rr_owner_message.py", "py"),
    ("65-rescue-receiver/rr_intake_classify.py", "py"),
]


def parses(path: str, kind: str) -> tuple[bool, str]:
    try:
        if kind == "py":
            with open(path, encoding="utf-8") as fh:
                ast.parse(fh.read(), filename=path)
            return True, ""
        if kind == "json":
            with open(path, encoding="utf-8") as fh:
                json.load(fh)
            return True, ""
        shell = "bash" if kind == "bash" else "sh"
        p = subprocess.run([shell, "-n", path], capture_output=True, text=True, timeout=30, check=False)
        return p.returncode == 0, "" if p.returncode == 0 else "%s -n exited %d" % (shell, p.returncode)
    except (OSError, SyntaxError, ValueError, subprocess.TimeoutExpired) as exc:
        return False, type(exc).__name__


def verify(skills_root: str, include_added: bool) -> dict:
    rows = []
    for rel, kind in REQUIRED + (ADDED_BY_THIS_BUILD if include_added else []):
        path = os.path.join(skills_root, rel)
        if not os.path.isfile(path):
            rows.append({"file": rel, "ok": False, "why": "missing"})
        elif os.path.getsize(path) == 0:
            rows.append({"file": rel, "ok": False, "why": "empty"})
        else:
            good, why = parses(path, kind)
            rows.append({"file": rel, "ok": good, "why": why if not good else ""})
    failed = [r for r in rows if not r["ok"]]
    return {"files_installed": not failed, "checked": len(rows), "failed": failed}


def selftest() -> int:
    ok = True
    with tempfile.TemporaryDirectory() as d:
        ok &= verify(d, False)["files_installed"] is False
        for rel, kind in REQUIRED:
            p = os.path.join(d, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as fh:
                fh.write("{}\n" if kind == "json" else "x = 1\n" if kind == "py" else ":\n")
        ok &= verify(d, False)["files_installed"] is True
        open(os.path.join(d, "shared-utils/rescue-supervise.py"), "w").close()      # now empty
        res = verify(d, False)
        ok &= res["files_installed"] is False and res["failed"][0]["why"] == "empty"
        with open(os.path.join(d, "shared-utils/rescue-supervise.py"), "w") as fh:
            fh.write("def broken(:\n")
        ok &= verify(d, False)["files_installed"] is False
    print("selftest PASS" if ok else "selftest FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skills-root")
    ap.add_argument("--include-added", action="store_true", help="also require the files added by this build")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.skills_root or not os.path.isdir(a.skills_root):
        print(json.dumps({"files_installed": False, "why": "skills folder not found"}))
        return 2
    out = verify(a.skills_root, a.include_added)
    print(json.dumps(out, sort_keys=True))
    return 0 if out["files_installed"] else 20


if __name__ == "__main__":
    sys.exit(main())
