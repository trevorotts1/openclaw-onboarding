#!/usr/bin/env python3
"""G-4 (fix plan B3, unowned): `final-mockups` is in VISUAL_STAGES, so a run without it
cannot certify.

Skill 71's stage contract has FOUR visual stages; Skill 49's build gate required THREE,
because it mirrored legacy_downsell_images.STAGES (which stops at visual-mockup). A run
that never produced a final mockup therefore passed P7-BUILD.

FAILS before the change: VISUAL_STAGES was ("desktop-wireframe","mobile-tablet","visual-mockup")
and a run dir with the final-mockups record removed produced zero violations.
"""
import importlib.machinery
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "49-signature-funnel" / "scripts"


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def main() -> int:
    fails = []
    build = load("sf_build_g4", SCRIPTS / "prove_sf_build.py")

    if "final-mockups" not in build.VISUAL_STAGES:
        fails.append("G-4: final-mockups is NOT in VISUAL_STAGES (%r)" % (build.VISUAL_STAGES,))
    if "visual-mockup" not in build.VISUAL_STAGES:
        fails.append("G-4: the earlier three stages were dropped (%r)" % (build.VISUAL_STAGES,))

    with tempfile.TemporaryDirectory(prefix="bld002-g4-") as d:
        rd = Path(d) / "run"
        rd.mkdir()
        build.write_valid_run_evidence(rd, 5)
        clean = build.visual_direction_violations(rd, 5)
        if clean:
            fails.append("G-4: the fresh valid fixture is not clean before mutation: %r" % (clean,))

        target = rd / build.PAGE_IMAGES_REL / "main" / "final-mockups"
        if not target.is_dir():
            fails.append("G-4: write_valid_run_evidence did not create main/final-mockups "
                         "(VISUAL_STAGES drives the fixture)")
        else:
            shutil.rmtree(target)
            rec = rd / build.PAGE_IMAGES_REL / build.PAGE_IMAGES_RECEIPT
            data = json.loads(rec.read_text(encoding="utf-8"))
            (data.get("pages", {}).get("main", {}).get("stages") or {}).pop("final-mockups", None)
            rec.write_text(json.dumps(data), encoding="utf-8")
            v = build.visual_direction_violations(rd, 5)
            if not any("main" in m and "final-mockups" in m for _c, m in v):
                fails.append("G-4: a run with NO final-mockups did not fail the visual gate: %r" % (v,))

    for f in fails:
        print("FAIL: " + f)
    if fails:
        return 1
    print("PASS G-4: final-mockups is gated; a run without it fails the visual gate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
