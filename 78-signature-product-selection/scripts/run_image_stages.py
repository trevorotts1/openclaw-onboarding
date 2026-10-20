#!/usr/bin/env python3
"""run_image_stages.py - the order page's wireframes and mockups, through Skill 71 only.

Skill 71's shared image service is the single pipeline for every page role; this
wrapper is the call it expects from the owning skill, made once per page:

  1. 71 shared_page_service.py --page-version product-selection
        admits the page (page_role product_selection), stages the request, launch
        record, route graph and brand file, and writes intake.json
  2. emit_section_manuscript.py     the approved plan as the five-section manuscript
  3. 71 build_production_request.py --copy-version product-selection   (per stage)
  4. 71 stage_executor.py                                              (per stage)

Everything Trevor taught rides that one route and is not re-implemented here: the
client's brand colours only, the build-spec annotated wireframes, design style A/B/C,
composition variety, the hypersaturated grade, desktop and mobile, one long top-to-bottom
PDF per stage and the overview boards (the last two on the paid provider). The Design
Board (page_role product_selection) runs on its own, after the images and before
final-mockups, when the inputs list the design-board stage and a design_board_spec.

Default stages: desktop-wireframe, mobile-tablet, visual-mockup. final-mockups needs the
client's approval of the Design Board first; 71 stage_executor refuses it otherwise.
The provider is stub (free, placeholders) unless the inputs say kie and --allow-paid is passed.

Package image slots: one per approved offer, in card order, "PKG-n" (circle 1:1 for
design style B, the first one circle for C, 4:3 rectangles for A).

Operator values come from one inputs file (--inputs), so dispatch binds a single path:
  {"route_graph", "brand_file", "brand_owner", "image_cap", "design_style" (A|B|C),
   and optionally "copy", "design_prose", "design_board_spec", "model", "stages",
   "provider" (stub|kie, default stub), "test_run"}
--inputs none is refused (exit 2): a funnel with an order page gets all its pages, so the
order page's wireframes and mockups are never skipped.
Spending is never decided here: a paid run needs the explicit --allow-paid on this command
line, which dispatch never passes.

Usage:
  run_image_stages.py --plan selection-plan.json --request page-request.json \\
      --run-dir DIR --launch-record launch.json --inputs inputs.json|none \\
      [--preflight] [--allow-paid] [--skill71-root DIR]
Exit: 0 every step passed, 2 a step failed or was refused.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from emit_section_manuscript import write as write_manuscript  # noqa: E402

FORM = "product-selection"
DEFAULT_STAGES = ("desktop-wireframe", "mobile-tablet", "visual-mockup")
BOARD = "design-board"
REQUIRED = ("route_graph", "brand_file", "brand_owner", "image_cap")


def package_slots(plan, style):
    """{"3": [slot per offer]}: the page's image plates, one per package card."""
    slots = []
    for i, offer in enumerate(plan["offers_in_order"], 1):
        circle = style == "B" or (style == "C" and i == 1)
        slot = {"slot_id": f"PKG-{i}", "aspect_ratio": "1:1" if circle else "4:3",
                "art_direction": f"{offer['display_name']} package image, one clear subject"}
        if circle:
            slot["mask"] = "circle"  # a circle slot: 1:1, masked to a circle PNG with transparent corners
        slots.append(slot)
    return {"3": slots}


def conform(value, schema):
    """The value cut down to a schema that closes its objects (additionalProperties false)."""
    if isinstance(value, dict) and isinstance(schema.get("properties"), dict):
        keep = schema["properties"] if schema.get("additionalProperties") is False else value
        return {k: conform(v, schema["properties"].get(k, {})) for k, v in value.items() if k in keep}
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        return [conform(v, schema["items"]) for v in value]
    return value


def run(cmd):
    print("RUN " + " ".join(str(c) for c in cmd[1:3]), flush=True)
    proc = subprocess.run([str(c) for c in cmd])
    if proc.returncode:
        raise SystemExit(f"FAIL: step exited {proc.returncode}: {Path(str(cmd[1])).name}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    for flag in ("plan", "request", "run-dir", "launch-record"):
        p.add_argument(f"--{flag}", type=Path, required=True)
    p.add_argument("--inputs", required=True)
    p.add_argument("--allow-paid", action="store_true")
    p.add_argument("--preflight", action="store_true", help="compose and check every prompt; no provider call")
    p.add_argument("--skill71-root", type=Path, default=HERE.parents[1] / "71-blackceo-signature-page")
    a = p.parse_args(argv)
    if a.inputs == "none":
        print("REFUSED: --inputs none; the order page's wireframes and mockups are required in a full funnel")
        return 2
    s71 = a.skill71_root / "scripts"
    py, run_dir = sys.executable, a.run_dir
    try:
        cfg = json.loads(Path(a.inputs).read_text(encoding="utf-8"))
        missing = [k for k in REQUIRED if not cfg.get(k)]
        if missing:
            raise SystemExit(f"REFUSED: the inputs file is missing {', '.join(missing)}")
        plan = json.loads(a.plan.read_text(encoding="utf-8"))
        if plan.get("outcome") != "plan":
            raise SystemExit(f"REFUSED: the plan outcome is {plan.get('outcome')!r}; no order page is built")
        stages = cfg.get("stages") or list(DEFAULT_STAGES)
        style, provider = cfg.get("design_style"), cfg.get("provider", "stub")
        # 1. admit the page into the shared image service (the one pipeline for every page role).
        # The service checks the launch record's identity, status, brand and route hashes against the frozen
        # packet schema, which closes every object; Skill 78's own launch fields (buyer, outcome, FAQ and the
        # like) belong to the plan, so the service is given the record cut down to the packet's fields.
        launch = json.loads(a.launch_record.read_text(encoding="utf-8"))
        schema = json.loads((a.skill71_root / "references" / "launch.schema.json").read_text(encoding="utf-8"))
        view = conform(launch, schema)
        run_dir.mkdir(parents=True, exist_ok=True)
        launch_view = run_dir / "launch-packet-view.json"
        launch_view.write_text(json.dumps(view, indent=2) + "\n", encoding="utf-8")
        intake = [py, s71 / "shared_page_service.py", "--request", a.request, "--run-dir", run_dir,
                  "--page-version", FORM, "--brand-owner", cfg["brand_owner"], "--image-cap", cfg["image_cap"],
                  "--brand-file", cfg["brand_file"], "--launch-record", launch_view,
                  "--route-graph", cfg["route_graph"]]
        if style:
            intake += ["--design-style", style]
        if cfg.get("test_run"):
            intake.append("--test-run")
        run(intake)
        # 2. the approved plan as Skill 71's five-section copy
        manuscript, _manifest = write_manuscript(a.plan, run_dir, cfg.get("copy"))
        slots = run_dir / "slots.json"
        slots.write_text(json.dumps(package_slots(plan, style), indent=2) + "\n", encoding="utf-8")
        # 3 and 4. one request and one executor call per stage
        for stage in stages:
            request = run_dir / f"production-request-{stage}.json"
            build = [py, s71 / "build_production_request.py", "--copy-version", FORM,
                     "--manuscript", manuscript, "--stage", "visual-mockup" if stage == BOARD else stage,
                     "--out", request, "--slots", slots, "--run-dir", run_dir]
            for flag, key in (("--design-prose", "design_prose"), ("--model", "model")):
                if cfg.get(key):
                    build += [flag, cfg[key]]
            run(build)
            if stage == BOARD:
                if not cfg.get("design_board_spec"):
                    raise SystemExit("REFUSED: the design-board stage needs design_board_spec (the client's own brand facts)")
                doc = json.loads(request.read_text(encoding="utf-8"))
                doc["design_board"] = {**json.loads(Path(cfg["design_board_spec"]).read_text(encoding="utf-8")),
                                       "page_role": "product_selection"}
                request.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            execute = [py, s71 / "stage_executor.py", run_dir, "--request", request.name,
                       "--stages", stage, "--provider", provider]
            if a.allow_paid:
                execute.append("--allow-paid")
            if a.preflight:
                execute.append("--preflight")
            run(execute)
    except SystemExit as exc:
        print(exc)
        return 2
    except (OSError, ValueError) as exc:
        print(f"REFUSED: {exc}")
        return 2
    print(f"order page {'preflight' if a.preflight else 'stages'} ok: {', '.join(stages)} in {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
