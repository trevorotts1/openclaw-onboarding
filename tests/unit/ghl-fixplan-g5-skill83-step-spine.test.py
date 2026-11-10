#!/usr/bin/env python3
"""G-5 (fix plan C6/B4, unowned): Skill 83 has a STEP SPINE, and assemble refuses a
design-less package.

Skill 49 aborts on the first failing phase and writes a process manifest. Skill 83 had no
equivalent: `cmd_assemble` called package.assemble, optionally image_stages.drive and
graphics_hooks.handle_handoff, and returned — it never called `checks`, so a package with no
wireframes at all could be assembled and handed off.

After the fix:
  * `_close_step_spine` records every declared step with the artifact it owes, checks them,
    writes <out>/assemble-steps.json, and REFUSES (AF-LAUNCH-STEP-ARTIFACT) if a required
    artifact is absent;
  * `cmd_assemble` calls `page_designs.design_violations` on the sealed manifest and refuses
    (AF-LAUNCH-ASSEMBLE-DESIGN) unless the package was explicitly allowed to have no designs.

FAILS before the change: `_close_step_spine` did not exist and cmd_assemble never called
design_violations.
"""
import importlib.machinery
import importlib.util
import inspect
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "83-black-friday-launcher"


def load_cli():
    if str(LAUNCHER) not in sys.path:
        sys.path.insert(0, str(LAUNCHER))
    import launcher_core.cli as cli  # noqa: PLC0415
    return cli


def main() -> int:
    fails = []
    cli = load_cli()

    if not hasattr(cli, "_close_step_spine"):
        fails.append("G-5: launcher_core.cli has no _close_step_spine — no step spine exists")
        spine = None
    else:
        spine = cli._close_step_spine

    if spine is not None:
        with tempfile.TemporaryDirectory(prefix="bld002-g5-") as d:
            out = Path(d)
            good = out / "manifest.json"
            good.write_text("{}", encoding="utf-8")
            record = spine(out, [{"step": "assemble", "required": True, "artifacts": [str(good)]}])
            if not record.get("closed"):
                fails.append("G-5: the spine refused a step whose artifact exists")
            if not (out / "assemble-steps.json").is_file():
                fails.append("G-5: the spine wrote no assemble-steps.json")

            missing = out / "receipt-that-was-never-written.json"
            try:
                spine(out, [{"step": "assemble", "required": True,
                             "artifacts": [str(good), str(missing)]}])
                fails.append("G-5: the spine ACCEPTED a required step with a missing artifact")
            except Exception as exc:  # noqa: BLE001
                if "AF-LAUNCH-STEP-ARTIFACT" not in str(exc):
                    fails.append("G-5: the refusal did not carry AF-LAUNCH-STEP-ARTIFACT: %s" % exc)

    src = inspect.getsource(cli.cmd_assemble) if hasattr(cli, "cmd_assemble") else ""
    if "design_violations" not in src:
        fails.append("G-5: cmd_assemble never calls design_violations — a design-less package "
                     "can still be assembled and handed off")
    if "AF-LAUNCH-ASSEMBLE-DESIGN" not in src:
        fails.append("G-5: cmd_assemble has no AF-LAUNCH-ASSEMBLE-DESIGN refusal")
    if "_close_step_spine" not in src:
        fails.append("G-5: cmd_assemble never closes the step spine")

    for f in fails:
        print("FAIL: " + f)
    if fails:
        return 1
    print("PASS G-5: assemble refuses a design-less package and a declared step with no "
          "artifact (AF-LAUNCH-STEP-ARTIFACT), and writes assemble-steps.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
