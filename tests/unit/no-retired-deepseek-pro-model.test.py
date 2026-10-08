#!/usr/bin/env python3
"""KEF001 K2: DeepSeek V4 Pro no longer exists (owner order 2026-10-08). The id
must not appear anywhere in tracked files except CHANGELOG history, QC tickets
and evidence/ledger records. Use deepseek-v4.1-flash on the same provider prefix.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NEEDLE = re.compile("deepseek-v4-" + "pro", re.I)  # split so this file never matches itself
HISTORY = re.compile(r"(^|/)CHANGELOG[^/]*\.md$|^(QUALITY-CONTROL|evidence|ledgers)/")


def offenders():
    files = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout.split(b"\0")
    out = []
    for raw in filter(None, files):
        rel = raw.decode()
        if HISTORY.search(rel) or not (ROOT / rel).is_file():
            continue
        try:
            text = (ROOT / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        out += [f"{rel}:{n}" for n, line in enumerate(text.splitlines(), 1) if NEEDLE.search(line)]
    return out


if __name__ == "__main__":
    bad = offenders()
    if bad:
        print("FAIL: retired model id present (use deepseek-v4.1-flash):\n  " + "\n  ".join(bad[:50]))
        sys.exit(1)
    print("OK: no retired DeepSeek V4 Pro id outside history")
