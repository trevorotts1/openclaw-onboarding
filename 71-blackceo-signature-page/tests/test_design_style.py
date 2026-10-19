#!/usr/bin/env python3
"""Acceptance tests for design styles A Block, B Circle, C Hybrid (Skill 71).

Pinned here, with no network and no paid call:

  (a) circle_image.apply masks a rectangle to a square RGBA PNG, transparent
      outside, opaque inside, ring drawn in the supplied brand color;
  (b) circle_image.check passes a masked PNG and fails an unmasked square by name;
  (c) a ring without a brand color is refused (no default color);
  (d) design_style refuses circle slots in Style A, caps Style C accents, and
      reads `mask: circle` as `shape: circle`;
  (e) stage_executor adds the style block to stage prompts, resolves the style
      from intake.json, and a circle item is masked, recorded, and refused when
      its prompt lacks the circle clause;
  (f) the intake question prints one example link per placeholder-aware style,
      and write_intake records the choice;
  (g) gate:intake_design_style blocks a production intake without a choice;
  (h) validate_image_manifest and validate_production_record enforce shape/style;
  (i) validate_image_grade measures only the opaque photo of a circle PNG.
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import circle_image  # noqa: E402
import design_style  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from brand_fixture import give_blackceo_colors  # noqa: E402


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def photo(path, size=(600, 900)):
    """A deterministic non-flat rectangle standing in for a generated photo."""
    im = Image.new("RGB", size)
    px = im.load()
    for y in range(size[1]):
        for x in range(size[0]):
            px[x, y] = ((x * 255) // size[0], (y * 255) // size[1], (x + y) % 256)
    im.save(path)
    return path


def run(script, *args):
    return subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                          capture_output=True, text=True)


class CircleImageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.src = photo(self.d / "rect.png")

    def tearDown(self):
        self.tmp.cleanup()

    def test_apply_masks_to_transparent_circle(self):
        out = self.d / "circle.png"
        proc = run("circle_image.py", "apply", self.src, out)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        with Image.open(out) as im:
            self.assertEqual(im.mode, "RGBA")
            self.assertEqual(im.size, (600, 600))      # square crop of the 600x900 source
        stats = circle_image.alpha_stats(out)
        self.assertEqual(set(stats["corner_max_alpha"].values()), {0})
        self.assertEqual(stats["center_min_alpha"], 255)
        self.assertTrue(0.18 < stats["transparent_share"] < 0.25, stats)
        self.assertEqual(circle_image.shape_failures(stats), [])

    def test_apply_is_deterministic(self):
        a, b = self.d / "a.png", self.d / "b.png"
        run("circle_image.py", "apply", self.src, a, "--focus", "0.5,0.3")
        run("circle_image.py", "apply", self.src, b, "--focus", "0.5,0.3")
        self.assertEqual(a.read_bytes(), b.read_bytes())

    def test_focus_moves_the_crop(self):
        top, bottom = self.d / "t.png", self.d / "b.png"
        run("circle_image.py", "apply", self.src, top, "--focus", "0.5,0.0")
        run("circle_image.py", "apply", self.src, bottom, "--focus", "0.5,1.0")
        self.assertNotEqual(top.read_bytes(), bottom.read_bytes())

    def test_ring_draws_the_brand_color_and_keeps_corners_clear(self):
        for style in ("full", "crescent"):
            out = self.d / f"{style}.png"
            proc = run("circle_image.py", "apply", self.src, out, "--ring-style", style,
                       "--ring-color", "#123456", "--ring-width-pct", "4")
            self.assertEqual(proc.returncode, 0, proc.stdout)
            stats = circle_image.alpha_stats(out)
            self.assertEqual(circle_image.shape_failures(stats), [], (style, stats))
            colors = {px[:3] for px in Image.open(out).convert("RGBA").getdata() if px[3] == 255}
            self.assertIn((0x12, 0x34, 0x56), colors, style)

    def test_ring_without_brand_color_is_refused(self):
        proc = run("circle_image.py", "apply", self.src, self.d / "x.png", "--ring-style", "full")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("brand color", proc.stdout)
        self.assertFalse((self.d / "x.png").exists())

    def test_check_passes_masked_and_fails_unmasked_square(self):
        masked = self.d / "Image-01.png"
        run("circle_image.py", "apply", self.src, masked)
        square = photo(self.d / "Image-02.png", (600, 600))
        inv = self.d / "inv.json"
        inv.write_text(json.dumps({"images": [{"id": "IMG-001", "shape": "circle"},
                                              {"id": "IMG-002", "shape": "circle"},
                                              {"id": "IMG-003", "shape": "rect"}]}))
        ok = run("circle_image.py", "check", masked, "--inventory", inv)
        self.assertEqual(ok.returncode, 0, ok.stdout)
        bad = run("circle_image.py", "check", square, "--inventory", inv)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("no alpha channel", bad.stdout)
        self.assertIn("corner", bad.stdout)
        rect = photo(self.d / "Image-03.png", (600, 600))
        self.assertEqual(run("circle_image.py", "check", rect, "--inventory", inv).returncode, 0)

    def test_check_fails_a_circle_that_is_not_a_png(self):
        # a masked circle saved as lossless WebP under a .png name is not a PNG
        webp = self.d / "as-webp.png"
        out = circle_image.make_circle(Image.open(self.src))
        out.save(webp, format="WEBP", lossless=True)
        proc = run("circle_image.py", "check", webp, "--force-circle")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("not a PNG", proc.stdout)

    def test_check_fails_a_transparent_square_with_opaque_corners(self):
        # RGBA but a full-bleed rectangle: alpha everywhere, so the corners are opaque.
        p = self.d / "full.png"
        Image.new("RGBA", (400, 400), (10, 20, 30, 255)).save(p)
        proc = run("circle_image.py", "check", p, "--force-circle")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("corner regions are not fully transparent", proc.stdout)

    def test_check_fails_a_non_square_circle(self):
        p = self.d / "wide.png"
        out = circle_image.make_circle(Image.open(self.src))
        out.resize((600, 400)).save(p)
        self.assertEqual(run("circle_image.py", "check", p, "--force-circle").returncode, 1)

    def test_mask_alias_reads_as_circle(self):
        self.assertEqual(circle_image.entry_shape({"mask": "circle"}), "circle")
        self.assertEqual(circle_image.entry_shape({}), "rect")


class DesignStyleTests(unittest.TestCase):
    def test_style_a_refuses_circle_slots(self):
        fails = design_style.slot_failures("A", [{"slot_id": "IMG-001", "shape": "circle"}])
        self.assertTrue(any("Style A" in f and "IMG-001" in f for f in fails), fails)

    def test_circle_slot_must_be_square(self):
        fails = design_style.slot_failures(
            "B", [{"slot_id": "IMG-001", "shape": "circle", "aspect_ratio": "3:4"}])
        self.assertTrue(any("1:1" in f for f in fails), fails)

    def test_ring_needs_a_color(self):
        fails = design_style.slot_failures(
            "B", [{"slot_id": "IMG-001", "shape": "circle", "ring": {"style": "full"}}])
        self.assertTrue(any("brand color" in f for f in fails), fails)

    def test_style_c_caps_circle_accents_at_one_in_three(self):
        slots = [{"slot_id": f"IMG-{i}", "shape": "circle" if i < 3 else "rect"} for i in range(6)]
        self.assertTrue(design_style.slot_failures("C", slots))      # 3 of 6
        slots[2]["shape"] = "rect"
        self.assertEqual(design_style.slot_failures("C", slots), [])  # 2 of 6
        self.assertEqual(design_style.slot_failures("B", [{"shape": "circle"}] * 5), [])

    def test_mask_alias_counts_for_style_rules(self):
        self.assertTrue(design_style.slot_failures("A", [{"slot_id": "x", "mask": "circle"}]))

    def test_data_file_defines_three_styles_and_honest_placeholder(self):
        data = design_style.load()
        self.assertEqual([s["id"] for s in data["styles"]], ["A", "B", "C"])
        by_id = {s["id"]: s for s in data["styles"]}
        self.assertEqual(by_id["C"]["example"]["status"], "placeholder")
        self.assertIsNone(by_id["C"]["example"]["url"])
        for sid in ("A", "B"):
            self.assertTrue(by_id[sid]["example"]["url"].startswith("https://"))
        self.assertIn("CIRCLE CROP SAFE FRAME", data["circle_clause"])

    def test_question_lists_every_style_with_a_link_or_placeholder_note(self):
        text = design_style.question_text()
        for line in ("A. Block", "B. Circle", "C. Hybrid"):
            self.assertIn(line, text)
        self.assertEqual(text.count("See it: https://"), 2)
        self.assertIn("No example picture yet", text)
        proc = run("design_style.py", "question")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), text.strip())

    def test_board_prompt_block_draws_circle_tiles_only_for_circle_slots(self):
        text = design_style.board_prompt_block("C", [{"slot_id": "IMG-001", "mask": "circle"}, {"slot_id": "IMG-002"}])
        self.assertIn("Style C Hybrid", text)
        self.assertIn("circle slots (IMG-001) are drawn as circular tiles", text)
        self.assertIn("every color is the client's", text)
        self.assertIn("every image slot is drawn as a rectangle", design_style.board_prompt_block("A", []))

    def test_board_block_names_style_and_circle_slots(self):
        block = design_style.board_block("B", [{"slot_id": "IMG-001", "shape": "circle"},
                                               {"slot_id": "IMG-002"}])
        self.assertEqual(block["design_style"]["name"], "Circle")
        self.assertEqual(block["design_style"]["circle_slot_ids"], ["IMG-001"])


EXEC = load("stage_executor")


def request(style=None, circle=True):
    req = {"model": "STUB-NO-MODEL",
           "sections": [{"section_id": "core", "section_name": "Core", "copy": "Core copy.",
                         "slots": [{"slot_id": "IMG-001", "aspect_ratio": "1:1",
                                    "shape": "circle" if circle else "rect",
                                    "art_direction": "Portrait."}]}]}
    if style:
        req["design_style"] = style
    return req


class ExecutorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tmp.name) / "run"
        (self.run_dir / "desktop-wireframe").mkdir(parents=True)
        (self.run_dir / "image-inventory-prompts").mkdir()
        give_blackceo_colors(self.run_dir)  # every image stage starts from the client's colors

    def tearDown(self):
        self.tmp.cleanup()

    def write_request(self, req):
        (self.run_dir / "production-request.json").write_text(json.dumps(req), encoding="utf-8")

    def test_style_block_reaches_the_stage_prompt_for_each_stage_kind(self):
        req = request("B")
        self.write_request(req)
        loaded = EXEC.load_request(self.run_dir, "production-request.json")
        sec = loaded["sections"][0]
        wire = EXEC.stage_prompt("desktop-wireframe", sec, 1, 1440, loaded, "16:9")
        mock = EXEC.stage_prompt("final-mockups", sec, 1, 1440, loaded, "3:4")
        self.assertIn("STYLE B CIRCLE", wire)
        self.assertIn("Draw each circle slot as a circle", wire)
        self.assertIn("round photo with its ring", mock)
        self.assertIn("Circle slots in this section: IMG-001", wire)

    def test_circle_slot_never_sets_the_section_slice_ratio(self):
        sec = {"section_id": "s", "slots": [{"slot_id": "IMG-1", "aspect_ratio": "1:1", "shape": "circle"},
                                            {"slot_id": "IMG-2", "aspect_ratio": "16:9"}]}
        self.assertEqual(EXEC.target_ratio("desktop-wireframe", "section-{n:02d}.png", sec, self.run_dir, 1),
                         "16:9")
        only = {"section_id": "s", "slots": [{"slot_id": "IMG-1", "aspect_ratio": "1:1", "mask": "circle"}]}
        self.assertEqual(EXEC.target_ratio("desktop-wireframe", "section-{n:02d}.png", only, self.run_dir, 1),
                         EXEC.RATIO_DEFAULT["desktop-wireframe"])

    def test_no_style_leaves_prompts_unchanged(self):
        self.write_request(request(None))
        loaded = EXEC.load_request(self.run_dir, "production-request.json")
        prompt = EXEC.stage_prompt("desktop-wireframe", loaded["sections"][0], 1, 1440, loaded, "16:9")
        # the wireframe build spec's own "STYLE REFERENCE" line is not a design-style block
        self.assertNotRegex(prompt, r"STYLE [ABC]\b")

    def test_style_resolves_from_intake_json(self):
        self.write_request(request(None, circle=False))
        (self.run_dir / "intake.json").write_text(json.dumps({"design_style": "C"}))
        self.assertEqual(EXEC.load_request(self.run_dir, "production-request.json")["design_style"], "C")

    def test_style_a_with_a_circle_slot_is_refused_before_any_call(self):
        self.write_request(request("A"))
        with self.assertRaises(EXEC.ExecutorError) as ctx:
            EXEC.load_request(self.run_dir, "production-request.json")
        self.assertIn("Style A", str(ctx.exception))

    def test_circle_item_is_masked_recorded_and_passes_the_shape_check(self):
        inv = {"images": [{"id": "IMG-001", "shape": "circle", "aspect_ratio": "1:1",
                           "ring": {"style": "crescent", "color": "#0A5C36"}}]}
        (self.run_dir / "desktop-wireframe" / "image-inventory.json").write_text(json.dumps(inv))
        clause = design_style.circle_clause()
        (self.run_dir / "image-inventory-prompts" / "IMG-001.txt").write_text(f"A portrait. {clause}")
        entry = EXEC.run_item(self.run_dir, "image-generation-qc", "IMG-001", {}, EXEC.StubProvider(),
                              False)
        out = self.run_dir / "image-generation-qc" / "Image-01.png"
        with Image.open(out) as im:
            self.assertEqual(im.mode, "RGBA")
        self.assertEqual(circle_image.shape_failures(circle_image.alpha_stats(out)), [])
        self.assertEqual(entry["circle"]["raw_file"], "image-generation-qc/raw-square/Image-01.png")
        self.assertEqual(entry["sha256"], EXEC.sha256(out))
        self.assertEqual(entry["circle"]["ring"]["color"], "#0A5C36")
        proc = run("circle_image.py", "check", out, "--inventory",
                   self.run_dir / "desktop-wireframe" / "image-inventory.json")
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def inventory_run(self, style, shapes):
        inv = {"images": [{"id": f"IMG-{i:03d}", "shape": sh, "aspect_ratio": "1:1" if sh == "circle" else "3:2"}
                          for i, sh in enumerate(shapes, start=1)]}
        (self.run_dir / "desktop-wireframe" / "image-inventory.json").write_text(json.dumps(inv))
        (self.run_dir / "intake.json").write_text(json.dumps({"design_style": style}))
        give_blackceo_colors(self.run_dir)
        clause = design_style.circle_clause()
        for i in range(1, len(shapes) + 1):
            (self.run_dir / "image-inventory-prompts" / f"IMG-{i:03d}.txt").write_text(f"A photo. {clause}")

    def test_style_a_inventory_circle_is_refused_by_executor_and_gate_validator(self):
        # request slot is rect, inventory marks the slot circle: the inventory path must refuse
        self.write_request(request("A", circle=False))
        self.inventory_run("A", ["circle"])
        with self.assertRaises(EXEC.ExecutorError) as ctx:
            EXEC.run_item(self.run_dir, "image-generation-qc", "IMG-001",
                          EXEC.load_request(self.run_dir, "production-request.json"),
                          EXEC.StubProvider(), False)
        self.assertIn("Style A", str(ctx.exception))
        self.assertFalse((self.run_dir / "image-generation-qc" / "Image-01.png").exists())
        # the same refusal with no request file at all (the --item path loads {})
        with self.assertRaises(EXEC.ExecutorError):
            EXEC.run_item(self.run_dir, "image-generation-qc", "IMG-001", {}, EXEC.StubProvider(), False)
        proc = run("design_style.py", "validate-inventory", self.run_dir)
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("Style A", proc.stdout)
        # `validate` on the request also reads the sibling inventory
        self.assertEqual(run("design_style.py", "validate", self.run_dir / "production-request.json").returncode, 1)

    def test_style_c_inventory_over_the_circle_budget_is_refused(self):
        self.inventory_run("C", ["circle", "circle", "rect"])
        with self.assertRaises(EXEC.ExecutorError) as ctx:
            EXEC.run_item(self.run_dir, "image-generation-qc", "IMG-001", {}, EXEC.StubProvider(), False)
        self.assertIn("one in three", str(ctx.exception))
        self.assertEqual(run("design_style.py", "validate-inventory", self.run_dir).returncode, 1)

    def test_inventory_within_style_passes_and_styleless_run_is_exempt(self):
        self.inventory_run("C", ["circle", "rect", "rect"])
        self.assertEqual(run("design_style.py", "validate-inventory", self.run_dir).returncode, 0)
        EXEC.run_item(self.run_dir, "image-generation-qc", "IMG-001", {}, EXEC.StubProvider(), False)
        (self.run_dir / "intake.json").write_text(json.dumps({"test_run": True}))
        give_blackceo_colors(self.run_dir)
        self.assertEqual(run("design_style.py", "validate-inventory", self.run_dir).returncode, 0)

    def test_gate_contract_runs_the_inventory_validator_on_both_stages(self):
        contract = json.loads((ROOT / "references" / "stage-contract.json").read_text())
        for stage in ("desktop-wireframe", "image-generation-qc"):
            self.assertIn("python3 scripts/design_style.py validate-inventory {run_dir}",
                          contract["stages"][stage]["validators"], stage)

    def test_circle_item_prompt_without_the_clause_is_refused(self):
        inv = {"images": [{"id": "IMG-001", "shape": "circle"}]}
        (self.run_dir / "desktop-wireframe" / "image-inventory.json").write_text(json.dumps(inv))
        (self.run_dir / "image-inventory-prompts" / "IMG-001.txt").write_text("A portrait.")
        with self.assertRaises(EXEC.ExecutorError) as ctx:
            EXEC.run_item(self.run_dir, "image-generation-qc", "IMG-001", {}, EXEC.StubProvider(), False)
        self.assertIn("circle clause", str(ctx.exception))
        self.assertFalse((self.run_dir / "image-generation-qc" / "Image-01.png").exists())

    def test_rect_item_is_untouched(self):
        (self.run_dir / "image-inventory-prompts" / "IMG-002.txt").write_text("A desk.")
        entry = EXEC.run_item(self.run_dir, "image-generation-qc", "IMG-002", {}, EXEC.StubProvider(), False)
        self.assertNotIn("circle", entry)
        with Image.open(self.run_dir / "image-generation-qc" / "Image-02.png") as im:
            self.assertEqual(im.mode, "RGB")


class IntakeAndGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def intake(self, *extra, test_run=True):
        args = [self.d, "--page-version", "standard", "--brand-owner", "Client",
                "--image-cap", "3", "--copy-version", "standard", *extra]
        if test_run:
            args.append("--test-run")
        return run("write_intake.py", *args)

    def test_write_intake_records_the_choice(self):
        proc = self.intake("--design-style", "B")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        intake = json.loads((self.d / "intake.json").read_text())
        self.assertEqual((intake["design_style"], intake["design_style_source"]), ("B", "client_choice"))

    def test_write_intake_without_a_choice_prints_the_note_and_records_nothing(self):
        proc = self.intake()
        self.assertIn("NOTE design_style", proc.stdout)
        self.assertNotIn("design_style", json.loads((self.d / "intake.json").read_text()))

    def gate(self, intake):
        stage_gate = load("stage_gate")
        (self.d / "intake.json").write_text(json.dumps(intake))
        return stage_gate.run_builtin("gate:intake_design_style", [], self.d)

    def test_gate_blocks_a_production_intake_without_a_choice(self):
        msg = self.gate({"test_run": False, "image_engine": "kie"})
        self.assertIn("design_style", msg)
        self.assertIn("design_style.py question", msg)

    def test_gate_passes_with_a_choice_and_for_style_less_test_runs(self):
        self.assertIsNone(self.gate({"test_run": False, "design_style": "C",
                                     "design_style_source": "recommended_accepted"}))
        self.assertIsNone(self.gate({"test_run": True}))
        self.assertIn("gate:intake_design_style", load("stage_gate").GATE_BUILTINS)

    def test_gate_rejects_an_unrecorded_source(self):
        self.assertIsNotNone(self.gate({"test_run": False, "design_style": "A"}))


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def entry(self, **extra):
        item = {"id": "IMG-001", "job": "j", "filename": "Image-01.png", "status": "planned"}
        item.update(extra)
        return {"images": [item]}

    def test_manifest_shape_rules(self):
        vim = load("validate_image_manifest")
        self.assertEqual(vim.validate(self.entry(shape="circle", aspect_ratio="1:1")), [])
        self.assertTrue(any("1:1" in e for e in vim.validate(self.entry(shape="circle", aspect_ratio="3:4"))))
        self.assertTrue(any("rect or circle" in e for e in vim.validate(self.entry(shape="star"))))
        self.assertTrue(any("brand color" in e for e in vim.validate(
            self.entry(shape="circle", ring={"style": "full"}))))

    def test_manifest_measure_fails_an_unmasked_circle_asset(self):
        vim = load("validate_image_manifest")
        square = photo(self.d / "Image-01.png", (300, 300))
        data = self.entry(shape="circle", status="ready", asset_path="Image-01.png", qc_status="passed",
                          width=300, height=300, intended_ratio="1:1")
        errors = vim.validate(data, base_dir=self.d, measure=True)
        self.assertTrue(any("circle slot but" in e for e in errors), errors)
        circle_image.make_circle(Image.open(square)).save(self.d / "Image-01.png")
        self.assertFalse([e for e in vim.validate(data, base_dir=self.d, measure=True)
                          if "circle slot but" in e])

    def test_production_record_design_style(self):
        vpr = load("validate_production_record")
        self.assertTrue(any("design_style" in f for f in vpr.check_record({"design_style": "Z"})))
        (self.d / "intake.json").write_text(json.dumps({"design_style": "B"}))
        fails = vpr.check_record({"artifact": "mockup", "design_style": "A", "sections": [{}]},
                                 base_dir=self.d)
        self.assertTrue(any("differs from intake.json" in f for f in fails), fails)

    def test_grade_measure_ignores_transparent_corners(self):
        vig = load("validate_image_grade")
        base = photo(self.d / "p.png", (400, 400))
        circle_image.make_circle(Image.open(base)).save(self.d / "c.png")
        a, b = vig.measure(base), vig.measure(self.d / "c.png")
        # Same photo: opaque-only measurement must stay near the unmasked photo's, not
        # collapse toward black the way converting the transparent corners to RGB would.
        self.assertAlmostEqual(a["mean_saturation"], b["mean_saturation"], delta=0.08)
        naive = Image.open(self.d / "c.png").convert("RGB")
        self.assertLess(sum(naive.resize((1, 1)).getpixel((0, 0))),
                        sum(Image.open(base).convert("RGB").resize((1, 1)).getpixel((0, 0))))


if __name__ == "__main__":
    unittest.main(verbosity=2)
