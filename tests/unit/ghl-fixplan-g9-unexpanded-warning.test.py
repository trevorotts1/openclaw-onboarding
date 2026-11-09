#!/usr/bin/env python3
"""G-9 (fix plan A4, unowned): an unexpanded warn-and-expand verdict FAILS CLOSED.

The 80-to-below-95 percent band PASSES with a warning naming the characters to ADD. Skill 49
tested only `verdict["ok"]`, so that warning was dropped and a short prompt certified as if it
were compliant. A warning is not a pass: if the warning is still on the verdict it was never
expanded, so the run must be refused.

FAILS before the change: a prompt at ~86 percent of the maximum produced no violation.
"""
import importlib.util
import importlib.machinery
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROVER = ROOT / "49-signature-funnel" / "scripts" / "prove_sf_prompt_floor.py"
MODEL = "gpt-image-2-6/sunburst-text-to-image"
MAX_CHARS = 20000  # owner ruling 2026-11-08; read by the sibling transport offline


def load_prover():
    spec = importlib.util.spec_from_file_location("psf_g9", PROVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    fails = []
    os.environ.pop("KIE_LIVE_ADAPTER_PATH", None)  # let the real sibling transport resolve the max
    psf = load_prover()
    cache = getattr(psf, "_ADAPTER_CACHE", None)
    if isinstance(cache, dict):
        cache.clear()

    warn_prompt = psf._valid_photo_prompt(target=int(MAX_CHARS * 0.85))
    got_fails, receipt = psf.evaluate_prompt(
        {"page_type": "main", "section": 2, "text_bearing": False, "prompt": warn_prompt})
    codes = [c for c, _m in got_fails]
    ratio = (receipt or {}).get("ratio")
    if "AF-FUN-PROMPT-UNEXPANDED" not in codes:
        fails.append("G-9: an unexpanded warn-band prompt did not fail closed "
                     "(ratio=%r codes=%r)" % (ratio, codes))

    ok_prompt = psf._valid_photo_prompt(target=int(MAX_CHARS * 0.975))
    ok_fails, ok_receipt = psf.evaluate_prompt(
        {"page_type": "main", "section": 3, "text_bearing": False, "prompt": ok_prompt})
    ok_codes = [c for c, _m in ok_fails]
    if "AF-FUN-PROMPT-UNEXPANDED" in ok_codes:
        fails.append("G-9: a target-band prompt was wrongly refused as unexpanded (ratio=%r)"
                     % (ok_receipt or {}).get("ratio"))
    if ok_codes:
        fails.append("G-9: the target-band valid fixture is no longer clean: %r" % (ok_codes,))

    for f in fails:
        print("FAIL: " + f)
    if fails:
        return 1
    print("PASS G-9: an unexpanded warn-band prompt fails closed; a target-band prompt passes clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
