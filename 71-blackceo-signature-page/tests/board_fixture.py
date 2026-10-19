"""Shared fixtures for the Design Board tests: a run folder for one page of a fictional client."""
import json
import os
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOUBLE = ROOT / "tests" / "fixtures" / "brand_colors_double"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.append(str(DOUBLE))  # last: the real brand_colors, once installed beside the scripts, wins
import design_board  # noqa: E402

needs_ocr = unittest.skipUnless(shutil.which("tesseract"),
                                "tesseract (the board's independent reader) is not installed")

BRAND = "Test Client Co"
PALETTE_ROLES = {"primary": "#1F4E79", "secondary": "#C8963E", "accent": ["#9C2F3A"],
                 "background": ["#F6F1E7"], "text": "#222222"}
SPEC = {
    "brand_name": BRAND, "positioning_line": "Clear steps for busy founders.",
    "logo": "inputs/logo.png",
    "color_names": {"primary": "Harbor", "secondary": "Brass"},
    "aesthetic_words": ["Clear", "Warm", "Steady", "Practical", "Calm"],
    "aesthetic_phrase": "Plain steps and honest numbers",
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


def render_board(path: Path, palette, lines=(), size=(1600, 1200)):
    """A board-like image: palette swatches plus `lines` of real, OCR-readable text in three columns."""
    from PIL import Image, ImageDraw, ImageFont
    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", size, (255, 255, 255))
    d = ImageDraw.Draw(im)
    for i, x in enumerate(palette):
        d.rectangle([20 + i * 90, 1100, 100 + i * 90, 1180], fill=x["hex"])
    font = ImageFont.load_default(size=26)
    for i, line in enumerate(lines):
        d.text((20 + (i // 28) * 530, 20 + (i % 28) * 38), line, fill=(20, 20, 20), font=font)
    im.save(path)


BOARD_TEXT = [""]  # what the in-process OCR double "sees" on the board; seed_board sets it


def fake_ocr(_png):
    """In-process stand-in for design_board.ocr_text (tests patch it; the CLI tests use the real one)."""
    return BOARD_TEXT[0]


def subprocess_env():
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(DOUBLE), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    return env


def make_run(run_dir: Path, role="landing", spec_over=None, slot_files=3, brand=BRAND,
             base_request=None, chain=False) -> Path:
    """One page's run. Every image slot has its real file (the board is made after the image
    chain). base_request: an existing production request to add the design_board block to.
    chain=True lays the images out the way the real pipeline does (wireframe inventory and
    section plan, image-generation-qc files, image map) instead of `file` fields on the request."""
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
            if i <= slot_files and not chain:
                png(run_dir / "inputs" / f"img{i}.png", (40 * i, 90, 140))
                slot["file"] = f"inputs/img{i}.png"
            slots.append(slot)
        request = {"model": "STUB-NO-MODEL", "design_board": spec,
                   "sections": [{"section_id": "hero", "section_name": "Hero",
                                 "copy": "Hero copy here.", "slots": slots[:2]},
                                {"section_id": "proof", "section_name": "Proof",
                                 "copy": "Proof copy here.", "slots": slots[2:]}]}
    if chain:
        lay_chain(run_dir)
    (run_dir / "production-request.json").write_text(json.dumps(request), encoding="utf-8")
    return run_dir


def lay_chain(run_dir: Path):
    """The pipeline's own artifacts for three slots: IMG-001 generated and mapped, IMG-002 generated
    (found by its Image-NNN name), IMG-003 a supplied photo recorded on the inventory entry."""
    wf = run_dir / "desktop-wireframe"
    wf.mkdir(exist_ok=True)
    (wf / "image-inventory.json").write_text(json.dumps([
        {"id": "IMG-001", "source": "generated"}, {"id": "IMG-002", "source": "generated"},
        {"id": "IMG-003", "source": "supplied-founder-photo", "file": "inputs/founder.png"}]))
    (wf / "section-plan.json").write_text(json.dumps([
        {"section_id": "hero", "image_slot_ids": ["IMG-001", "IMG-002"]},
        {"section_id": "proof", "image_slot_ids": ["IMG-003"]}]))
    png(run_dir / "image-generation-qc" / "Image-001.png", (40, 90, 140))
    png(run_dir / "image-generation-qc" / "Image-002.png", (80, 90, 140))
    png(run_dir / "inputs" / "founder.png", (120, 90, 140))
    (run_dir / "image-map-upload").mkdir(exist_ok=True)
    (run_dir / "image-map-upload" / "image-map.json").write_text(json.dumps(
        {"images": [{"id": "IMG-001", "asset_file": "Image-001.png"}]}))


def board_lines(plan) -> list:
    return [a for lst in plan["expected"]["anchors"].values() for a in lst]


def seed_board(run_dir: Path, approved=True, provider="kie", board_text=None) -> dict:
    """Make the board the way the executor does (minus the paid call), read it back and approve.
    The board image carries the palette; the in-process OCR double shows `board_text` (default:
    every expected text), so tests patch design_board.ocr_text with fake_ocr."""
    request = json.loads((run_dir / "production-request.json").read_text(encoding="utf-8"))
    plan = design_board.plan(run_dir, request)
    prompt, _ = design_board.compose_prompt(plan, request, run_dir)
    anchors = board_lines(plan)
    render_board(run_dir / design_board.BOARD_FILE, plan["palette"])
    BOARD_TEXT[0] = "\n".join(anchors) if board_text is None else board_text
    design_board.write_record(run_dir, plan, prompt,
                              {"provider": provider, "mode": "active", "model": "m", "task_id": "t1"}, 1)
    (run_dir / "readback.txt").write_text("\n".join(anchors), encoding="utf-8")
    design_board.finalize(run_dir, "\n".join(anchors), "reader")
    if approved:
        design_board.approve(run_dir, "Test Client", "message-123")
    return plan


def seed_real_board(run_dir: Path, approved=True) -> dict:
    """The same, with the board drawn as real text and read by the real tesseract (CLI tests)."""
    request = json.loads((run_dir / "production-request.json").read_text(encoding="utf-8"))
    plan = design_board.plan(run_dir, request)
    prompt, _ = design_board.compose_prompt(plan, request, run_dir)
    anchors = board_lines(plan)
    render_board(run_dir / design_board.BOARD_FILE, plan["palette"], anchors)
    design_board.write_record(run_dir, plan, prompt,
                              {"provider": "kie", "mode": "active", "model": "m", "task_id": "t1"}, 1)
    design_board.finalize(run_dir, "\n".join(anchors), "reader")
    if approved:
        design_board.approve(run_dir, "Test Client", "message-123")
    return plan
