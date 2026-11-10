#!/usr/bin/env python3
"""G-15 (fix plan section 6, plan-wide): no fix lets through anything that is refused today.

Every change in this batch was chosen to NARROW: the visual stage gained a required member, the
provider default moved off `stub`, the prompt gate gained a transport check and a fail-closed
warning rule, and the build gate gained a required slot-set binding. This test asserts the
monotonicity directly, so a later edit cannot quietly widen a gate while the per-item tests
still pass.

FAILS if any of these is ever weakened:
  * VISUAL_STAGES loses one of the three stages that were required before;
  * the wireframe provider defaults back to `stub`;
  * a prompt refused before (too short / over max / no grade block) stops being refused, or
    changes its AF code;
  * a run with no visual set stops failing the build gate.
"""
import importlib.machinery
import importlib.util
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "49-signature-funnel" / "scripts"

ORIGINAL_VISUAL = ("desktop-wireframe", "mobile-tablet", "visual-mockup")
ORIGINAL_CODES = {"too_short": "AF-FUN-PROMPT-FLOOR",
                  "too_long": "AF-FUN-PROMPT-CEILING",
                  "no_grade_block": "AF-FUN-PROMPT-GRADE"}


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def main() -> int:
    fails = []
    build = load("sf_build_g15", SCRIPTS / "prove_sf_build.py")
    floor = load("sf_floor_g15", SCRIPTS / "prove_sf_prompt_floor.py")

    for stage in ORIGINAL_VISUAL:
        if stage not in build.VISUAL_STAGES:
            fails.append("G-15: visual stage %r is no longer required (gate WIDENED)" % stage)

    legacy = (SCRIPTS / "legacy_downsell_images.py").read_text(encoding="utf-8")
    m = re.search(r'"--image-provider"[^)]*default="(\w+)"', legacy)
    if not m:
        fails.append("G-15: the provider default could not be read")
    elif m.group(1) != "kie":
        fails.append("G-15: the provider defaults to %r again (gate WIDENED)" % m.group(1))

    with tempfile.TemporaryDirectory(prefix="bld002-g15-") as d:
        good = floor._valid_photo_prompt(target=19500)
        cases = {
            "too_short": "short prompt " * 5,
            "too_long": good + "x" * 4000,
            "no_grade_block": good.replace(floor._GRADE_BLOCK, "A stylish portrait. " * 4),
        }
        for name, prompt in cases.items():
            got, _r = floor.evaluate_prompt({"page_type": "main", "section": 1,
                                             "text_bearing": False, "prompt": prompt})
            codes = {c for c, _m in got}
            if ORIGINAL_CODES[name] not in codes:
                fails.append("G-15: %s is no longer refused with %s (got %r) — gate WIDENED"
                             % (name, ORIGINAL_CODES[name], sorted(codes)))

        rd = Path(d) / "run"
        rd.mkdir()
        build.write_valid_run_evidence(rd, 5)
        shutil.rmtree(rd / build.PAGE_IMAGES_REL)
        v = build.visual_direction_violations(rd, 5)
        if "AF-FUN-BUILD-VISUAL" not in {c for c, _m in v}:
            fails.append("G-15: a run with no visual set no longer fails AF-FUN-BUILD-VISUAL")

    for f in fails:
        print("FAIL: " + f)
    if fails:
        return 1
    print("PASS G-15: every gate only narrowed — the pre-existing refusals still refuse, with "
          "the same codes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
