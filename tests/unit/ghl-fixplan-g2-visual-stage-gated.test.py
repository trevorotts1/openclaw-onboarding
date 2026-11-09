#!/usr/bin/env python3
"""G-2 (fix plan B1, unowned): Skill 49's visual stage is a real gate, not a prose sentence.

The wireframe step lived only as "after P1 copy passes, run scripts/legacy_downsell_images.py"
in SKILL.md. Searching run_signature_funnel.py for the tool returned nothing, so the step was
skipped silently — the mechanical reason wireframes went missing.

After the fix:
  * `prove_sf_build.py --visual-only` is a separately runnable visual gate;
  * P7-BUILD runs that gate FIRST, so a run with no visual set fails as AF-FUN-VISUAL-PHASE
    before the FAB/QC seams are even consulted;
  * the orchestrator has a mandatory VISUAL-STEP that invokes the tool when the brief asks
    for it, and refuses with the exact command when the brief's paths are missing.

FAILS before the change: `--visual-only` did not exist, `_gate_visual`/`_run_visual_stage`
did not exist, and a run dir with neither a visual set nor a FAB artifact reported
AF-FUN-BUILD-FAB (not the visual phase).
"""
import importlib.machinery
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SF = ROOT / "49-signature-funnel"
SCRIPTS = SF / "scripts"


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def main() -> int:
    fails = []
    build_mod = load("sf_build_g2", SCRIPTS / "prove_sf_build.py")
    run_mod = load("sf_run_g2", SF / "run_signature_funnel.py")

    for name in ("_gate_visual", "_run_visual_stage"):
        if not hasattr(run_mod, name):
            fails.append("G-2: orchestrator has no %s — the visual step is still prose" % name)

    with tempfile.TemporaryDirectory(prefix="bld002-g2-") as d:
        rd = Path(d) / "run"
        rd.mkdir()
        build_mod.write_valid_run_evidence(rd, 5)
        brief = rd / "brief.json"
        brief.write_text(json.dumps({"funnel_size": 5}), encoding="utf-8")

        # The valid fixture must pass the standalone visual gate.
        p = subprocess.run([sys.executable, str(SCRIPTS / "prove_sf_build.py"),
                            "--visual-only", "--run-dir", str(rd), "--funnel-size", "5"],
                           capture_output=True, text=True, timeout=120)
        if p.returncode != 0:
            fails.append("G-2: --visual-only refused a VALID visual set (rc=%d): %s"
                         % (p.returncode, (p.stdout + p.stderr)[-300:]))

        # Remove the visual set; the standalone gate must refuse.
        shutil.rmtree(rd / build_mod.PAGE_IMAGES_REL)
        p = subprocess.run([sys.executable, str(SCRIPTS / "prove_sf_build.py"),
                            "--visual-only", "--run-dir", str(rd), "--funnel-size", "5"],
                           capture_output=True, text=True, timeout=120)
        if p.returncode == 0:
            fails.append("G-2: --visual-only PASSED with no visual set at all")

        # P7-BUILD must fail on the VISUAL phase first (no FAB artifact exists either).
        if hasattr(run_mod, "_gate_build"):
            ok, detail = run_mod._gate_build(rd)
            if ok:
                fails.append("G-2: P7-BUILD accepted a run with no visual set")
            elif "AF-FUN-VISUAL-PHASE" not in detail:
                fails.append("G-2: P7-BUILD failed, but not on the visual gate: %s" % detail[:300])

        # The mandatory step: requested but unresolvable -> refuse with the exact command.
        brief.write_text(json.dumps({"funnel_size": 5, "visual_stage": "required"}), encoding="utf-8")
        if hasattr(run_mod, "_run_visual_stage"):
            ok, detail = run_mod._run_visual_stage(rd)
            if ok:
                fails.append("G-2: the mandatory visual step did not refuse an unresolvable brief")
            elif "AF-FUN-VISUAL-ARGS" not in detail or "legacy_downsell_images.py" not in detail:
                fails.append("G-2: the mandatory step refused without naming the tool/args: %s"
                             % detail[:300])

    for f in fails:
        print("FAIL: " + f)
    if fails:
        return 1
    print("PASS G-2: the visual stage is a named gate (--visual-only), P7-BUILD consults it "
          "first, and the orchestrator has a mandatory VISUAL-STEP that names the tool")
    return 0


if __name__ == "__main__":
    sys.exit(main())
