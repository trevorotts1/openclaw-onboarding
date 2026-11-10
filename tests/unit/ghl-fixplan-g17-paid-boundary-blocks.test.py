#!/usr/bin/env python3
"""G-17 (fix plan "already correct — do not regress"): the paid boundary still blocks below
80 percent and above the maximum.

kie_live_adapter.py:1109-1116 refuses the dispatch when the prompt policy says the payload is
out of band. No unit verified it, so a later edit could let a paid call through.

PASSES on origin/main too. This test makes the property CHECKED from now on.

Exit codes of `prompt-budget --check`: 3 below the 80 percent hard floor, 4 above the
documented maximum, 0 in band.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / "74-kie-live-adapter" / "scripts" / "kie_live_adapter.py"
MODEL = "gpt-image-2-6/sunburst-text-to-image"


def run_check(n: int) -> int:
    p = subprocess.run([sys.executable, str(ADAPTER), "prompt-budget", "--model", MODEL,
                        "--check", "--prompt-file", "-"],
                       input="x" * n, capture_output=True, text=True, timeout=180)
    return p.returncode


def main() -> int:
    fails = []
    if not ADAPTER.is_file():
        print("FAIL G-17: kie_live_adapter.py is missing")
        return 1

    below = run_check(10000)     # 50 percent of the 20,000 owner cap
    if below != 3:
        fails.append("below the 80 percent floor returned %r, expected 3 (refused)" % below)
    over = run_check(20500)      # above the 20,000 owner cap
    if over != 4:
        fails.append("above the maximum returned %r, expected 4 (refused)" % over)
    inband = run_check(19500)    # 97.5 percent
    if inband != 0:
        fails.append("a compliant prompt returned %r, expected 0" % inband)

    src = ADAPTER.read_text(encoding="utf-8")
    if "prompt policy refused the payload before any paid call" not in src and \
            '"prompt is outside the strict band"' not in src:
        fails.append("the paid boundary's refusal is no longer in the source")

    for f in fails:
        print("FAIL G-17: " + f)
    if fails:
        return 1
    print("PASS G-17: the paid boundary still refuses <80 percent (exit 3) and over-max "
          "(exit 4), and passes an in-band prompt (exit 0)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
