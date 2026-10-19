"""Shared fixtures for the Design Board tests: a run folder for one page of a fictional client."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOUBLE = ROOT / "tests" / "fixtures" / "brand_colors_double"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.append(str(DOUBLE))  # last: the real brand_colors, once installed beside the scripts, wins
import design_board  # noqa: E402

BRAND = "Test Client Co"
PALETTE_ROLES = {"primary": "#1F4E79", "secondary": "#C8963E", "accent": ["#9C2F3A"],
                 "background": ["#F6F1E7"], "text": "#222222"}
SPEC = {
    "brand_name": BRAND, "positioning_line": "Clear steps for busy founders.",
    "logo": "inputs/logo.png",
    "color_names": {"primary": "Harbor", "secondary": "Brass"},
    "aesthetic_words": ["Clear", "Warm", "Steady"],
    "typography": {"display": {"sample": "Plan the week.", "usage": "page headlines"},
                   "body": {"sample": "Short practical steps.", "usage": "body copy"},
                   "accent": {"sample": "you can do this", "usage": "pull quotes"}},
    "imagery_line": "Natural light. Real founders. Calm desks.",
    "icons": ["Plan", "Call", "Win"], "size_guidance": True,
    "cues": ["Large headlines", "One idea per section", "Real photography",
             "Generous spacing", "No clutter"],
    "banner_line": "Steady growth, one step at a time.",
    "footer_taglines": ["BUILT TO LAST.", "WORK THAT COMPOUNDS."]}
FONT_MAP = {"fonts": {"display": "Playfair Display", "body": "Lora", "accent": "Pinyon Script"},
            "typography": [{"element": "Headline", "sizes": {"desktop": {"px": 56}, "mobile": {"px": 34}}},
                           {"element": "Body", "sizes": {"desktop": {"px": 18}, "mobile": {"px": 17}}}]}


def png(path: Path, color=(120, 140, 160), size=(64, 48)):
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)


def subprocess_env():
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(DOUBLE), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    return env


def make_run(run_dir: Path, role="landing", spec_over=None, slot_files=1, brand=BRAND,
             base_request=None) -> Path:
    """base_request: an existing production request to add the design_board block to."""
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "intake.json").write_text(json.dumps(
        {"brand_owner": brand, "brand_file": "inputs/brand.json",
         "launch": {"page_role": role}}), encoding="utf-8")
    palette = {"gold": PALETTE_ROLES["primary"], "navy": PALETTE_ROLES["text"],
               "cream": PALETTE_ROLES["background"][0], "secondary": PALETTE_ROLES["secondary"],
               "accent1": PALETTE_ROLES["accent"][0]}
    (run_dir / "inputs").mkdir(exist_ok=True)
    (run_dir / "inputs" / "brand.json").write_text(json.dumps(
        {"brand_id": "test-client-co", "palette": palette, "palette_roles": PALETTE_ROLES}),
        encoding="utf-8")
    (run_dir / "font-action-plan").mkdir(exist_ok=True)
    (run_dir / "font-action-plan" / "font-map.json").write_text(json.dumps(FONT_MAP), encoding="utf-8")
    png(run_dir / "inputs" / "logo.png", (30, 60, 90))
    spec = {**SPEC, **(spec_over or {})}
    if base_request is not None:
        request = dict(base_request, design_board=spec)
    else:
        slots = []
        for i in range(1, 4):
            slot = {"slot_id": f"IMG-00{i}", "aspect_ratio": "4:3", "art_direction": f"Scene {i}."}
            if i <= slot_files:
                png(run_dir / "inputs" / f"img{i}.png", (40 * i, 90, 140))
                slot["file"] = f"inputs/img{i}.png"
            slots.append(slot)
        request = {"model": "STUB-NO-MODEL", "design_board": spec,
                   "sections": [{"section_id": "hero", "section_name": "Hero",
                                 "copy": "Hero copy here.", "slots": slots[:2]},
                                {"section_id": "proof", "section_name": "Proof",
                                 "copy": "Proof copy here.", "slots": slots[2:]}]}
    (run_dir / "production-request.json").write_text(json.dumps(request), encoding="utf-8")
    return run_dir


def seed_board(run_dir: Path, approved=True, provider="kie") -> dict:
    """Make the board the way the executor does (minus the paid call), then read-back and approve."""
    request = json.loads((run_dir / "production-request.json").read_text(encoding="utf-8"))
    plan = design_board.plan(run_dir, request)
    prompt, _ = design_board.compose_prompt(plan, request)
    png(run_dir / design_board.BOARD_FILE, (200, 190, 170), (160, 120))
    design_board.write_record(run_dir, plan, prompt,
                              {"provider": provider, "mode": "active", "model": "m", "task_id": "t1"}, 1)
    anchors = [a for lst in plan["expected"]["anchors"].values() for a in lst]
    (run_dir / "readback.txt").write_text("\n".join(anchors), encoding="utf-8")
    design_board.finalize(run_dir, "\n".join(anchors), "reader")
    if approved:
        design_board.approve(run_dir, "Test Client", "message-123")
    return plan
