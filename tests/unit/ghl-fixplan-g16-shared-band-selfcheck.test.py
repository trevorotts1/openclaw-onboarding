#!/usr/bin/env python3
"""G-16 (fix plan "already correct — do not regress"): the shared band still self-checks PASS.

shared-utils/prompt_policy.py:68,70,71 holds the ONE band (FLOOR 95, CEILING 100, HARD_FLOOR
80). Every fix in this batch narrows behaviour; none may move these numbers. No unit verified
this, so a later edit could quietly widen the band.

PASSES on origin/main too (the code is already correct). This test exists so the property is
CHECKED from now on, not remembered.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "shared-utils" / "prompt_policy.py"


def main() -> int:
    fails = []
    if not POLICY.is_file():
        print("FAIL G-16: shared-utils/prompt_policy.py is missing")
        return 1
    src = POLICY.read_text(encoding="utf-8")
    for name, want in (("FLOOR_PERCENT", 95), ("CEILING_PERCENT", 100), ("HARD_FLOOR_PERCENT", 80)):
        m = re.search(r"^%s\s*=\s*(\d+)" % name, src, re.M)
        if not m:
            fails.append("%s is not declared" % name)
        elif int(m.group(1)) != want:
            fails.append("%s is %s, expected %d" % (name, m.group(1), want))

    p = subprocess.run([sys.executable, str(POLICY), "--self-test"],
                       capture_output=True, text=True, timeout=180)
    out = (p.stdout or "") + (p.stderr or "")
    if p.returncode != 0 or "self-check: PASS" not in out:
        fails.append("prompt_policy.py --self-test did not PASS: %s" % out.strip()[-300:])

    for f in fails:
        print("FAIL G-16: " + f)
    if fails:
        return 1
    print("PASS G-16: the shared band is unchanged (95/100/80) and its self-check PASSES")
    return 0


if __name__ == "__main__":
    sys.exit(main())
