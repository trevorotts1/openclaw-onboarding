#!/usr/bin/env python3
"""G-10 (fix plan B6, unowned): the required per-section image set is BOUND to the wireframe
inventory.

The required set already existed (prove_sf_prompt_floor.required_image_pairs, derived from
structure/funnel_structure.json) but nothing connected it to the wireframe. A page could ship
with zero slots for a required section and no gate noticed — which is why "2-3 images on a
page" was unenforceable.

FAILS before the change: a fixture with a required section's slot removed from the wireframe
section plan, and one with the slot missing from the image inventory, produced zero violations.
"""
import importlib.machinery
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "49-signature-funnel" / "scripts" / "prove_sf_build.py"
CODE = "AF-FUN-VISUAL-SLOTSET"


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def codes(v):
    return {c for c, _m in v}


def main() -> int:
    fails = []
    build = load("sf_build_g10", BUILD)

    with tempfile.TemporaryDirectory(prefix="bld002-g10-") as d:
        rd = Path(d) / "run"
        rd.mkdir()
        build.write_valid_run_evidence(rd, 5)
        base = build.visual_direction_violations(rd, 5)
        if CODE in codes(base):
            fails.append("G-10: the valid fixture already fails the slot-set binding: %r"
                         % [m for c, m in base if c == CODE][:2])

        wf = rd / build.PAGE_IMAGES_REL / "main" / "desktop-wireframe"
        plan_p, inv_p = wf / "section-plan.json", wf / "image-inventory.json"
        if not plan_p.is_file() or not inv_p.is_file():
            fails.append("G-10: the build fixtures write no wireframe section plan / inventory, "
                         "so no required image slot can be bound to one")
            plan = {}
        else:
            plan = json.loads(plan_p.read_text(encoding="utf-8"))
        inv = (json.loads(inv_p.read_text(encoding="utf-8")) if inv_p.is_file() else {})
        if not plan or not inv.get("images"):
            fails.append("G-10: the fixture has no wireframe section plan / inventory to mutate")
        else:
            # (a) a required section with no slot in the plan
            saved_plan = json.loads(plan_p.read_text(encoding="utf-8"))
            broken = json.loads(json.dumps(plan))
            broken[0]["image_slot_ids"] = []
            plan_p.write_text(json.dumps(broken), encoding="utf-8")
            v = build.visual_direction_violations(rd, 5)
            if not any(c == CODE and "main" in m and "declares NO image slot" in m for c, m in v):
                fails.append("G-10: a required section with NO slot did not fail: %r"
                             % [m for c, m in v if c == CODE][:2])
            plan_p.write_text(json.dumps(saved_plan), encoding="utf-8")

            # (b) the plan names a slot the inventory does not carry
            saved_inv = json.loads(inv_p.read_text(encoding="utf-8"))
            dropped = json.loads(json.dumps(inv))
            dropped["images"] = dropped["images"][1:]
            inv_p.write_text(json.dumps(dropped), encoding="utf-8")
            v = build.visual_direction_violations(rd, 5)
            if not any(c == CODE and "not in" in m for c, m in v):
                fails.append("G-10: a slot absent from the inventory did not fail: %r"
                             % [m for c, m in v if c == CODE][:2])
            inv_p.write_text(json.dumps(saved_inv), encoding="utf-8")

    for f in fails:
        print("FAIL: " + f)
    if fails:
        return 1
    print("PASS G-10: every required (page, section) image slot is bound to the wireframe "
          "inventory; a missing plan slot or a missing inventory entry fails the build gate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
