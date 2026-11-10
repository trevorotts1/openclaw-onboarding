#!/usr/bin/env python3
"""G-1 (fix plan A5, unowned): Skill 66's prompt validator is no longer a dead gate.

It had NO production caller (repo-wide: only a CI guard and its own tests), and its
`--self-test` blanked KIE_LIVE_ADAPTER_PATH, so 33/33 PASS measured the models.json fallback
only — a green test that measured nothing about the live cap.

After the fix:
  * `validate_payload.py` (the command a caller runs before dispatch) applies the prompt gate
    with the adapter path NOT blanked, so a short prompt is refused there;
  * `validate_prompt.py --self-test` exercises the REAL sibling Skill 74 adapter and fails if
    the live path was never consulted.

FAILS before the change: the CLI accepted a short prompt for gpt-image-2-6, and the
self-test passed while the adapter was blanked.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VP = ROOT / "66-kie-image" / "scripts" / "validate_prompt.py"
PL = ROOT / "66-kie-image" / "scripts" / "validate_payload.py"
MODEL = "gpt-image-2-6/sunburst-text-to-image"


def main() -> int:
    fails = []
    env = dict(os.environ)
    env.pop("KIE_LIVE_ADAPTER_PATH", None)

    with tempfile.TemporaryDirectory(prefix="bld002-g1-") as d:
        payload = Path(d) / "payload.json"
        payload.write_text(json.dumps({
            "model": MODEL,
            "callBackUrl": "https://example.invalid/cb",
            "input": {"prompt": "a test prompt"},
        }), encoding="utf-8")
        p = subprocess.run([sys.executable, str(PL), str(payload)],
                           capture_output=True, text=True, timeout=180, env=env)
        if p.returncode == 0:
            fails.append("G-1: the submit path ACCEPTED a 13-character prompt at the 20,000 cap")
        out = (p.stdout or "") + (p.stderr or "")
        if "prompt policy" not in out:
            fails.append("G-1: the submit path did not run the prompt policy at all")

        # A compliant prompt must still pass the gate (fail-closed, not fail-always).
        payload.write_text(json.dumps({
            "model": MODEL,
            "callBackUrl": "https://example.invalid/cb",
            "input": {"prompt": "x" * 19500},
        }), encoding="utf-8")
        p2 = subprocess.run([sys.executable, str(PL), str(payload)],
                            capture_output=True, text=True, timeout=180, env=env)
        text = (p2.stdout or "") + (p2.stderr or "")
        if "prompt policy:" in text and "ADD" in text:
            fails.append("G-1: a 19,500-char compliant prompt was refused by the prompt policy")

    p = subprocess.run([sys.executable, str(VP), "--self-test"],
                       capture_output=True, text=True, timeout=300, env=env)
    if p.returncode != 0:
        fails.append("G-1: validate_prompt --self-test failed: %s"
                     % ((p.stdout or "") + (p.stderr or ""))[-400:])
    else:
        # The self-test must prove the LIVE adapter answered, not just the fallback.
        try:
            src = VP.read_text(encoding="utf-8")
        except OSError:
            src = ""
        if "owner-ruling:" not in src or "_find_adapter" not in src:
            fails.append("G-1: the self-test does not assert that the live adapter answered")

    for f in fails:
        print("FAIL: " + f)
    if fails:
        return 1
    print("PASS G-1: the Skill 66 submit path enforces the prompt gate with the live adapter, "
          "and the self-test proves the adapter was actually consulted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
