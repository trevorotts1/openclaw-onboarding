#!/usr/bin/env python3
"""SPF016: the wireframe stages send the owner's style references and an
annotated build-spec prompt, and the wireframe gate fails a colourless sheet.

Pins:
  (a) each stage and form picks the right bundled sheet (Standard desktop
      sheet 1, Long-Form desktop sheet 3, mobile sheet 4), the file is the one
      the manifest pins, and sheet 2 and the greyscale Set for Life sheet are
      never chosen;
  (b) a request that still lists the greyscale sheet, asks for "warm grey line
      work ... no colour fill", or prints a ratio such as 3:9 is refused by name;
  (c) the prompt block carries the sheet grammar, names no hex colour, passes
      the executor's own scrub unchanged, and keeps the founder letter one block;
  (d) the executor attaches the reference first, records the merged inputs, and
      --preflight prints the references sent;
  (e) the gate fails repeated or skipped numbers, invalid ratios, a slice with
      no chip, the greyscale no-colour style (W8), and a palette that is not the
      client's, and passes a slice drawn in the client's colours.

No paid API is called anywhere in this module.
"""
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
STANDARDS = ROOT / "assets" / "visual-standards"
sys.path.insert(0, str(SCRIPTS))
import wireframe_spec as w  # noqa: E402
import validate_wireframe as v  # noqa: E402

spec = importlib.util.spec_from_file_location("stage_executor", SCRIPTS / "stage_executor.py")
exe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exe)

CRIMSON = (200, 9, 26)
INK = (10, 10, 10)
PAPER = (248, 248, 248)
PALETTE = {"brand_id": "fixture-client",
           "palette": {"gold": "#C8091A", "navy": "#0A0A0A", "cream": "#F8F8F8"},
           "logo_only_colors": {"black": "#000000", "white": "#FFFFFF"}}


def request(form="long-form", sections=None):
    return {"model": "STUB-NO-MODEL", "copy_version": form,
            "sections": sections or [
                {"section_id": "S01", "section_name": "Hero claim", "copy": "You do every job.",
                 "cta": "SAVE MY SEAT",
                 "slots": [{"slot_id": "IMG-001", "aspect_ratio": "16:9",
                            "art_direction": "Founder at a desk, window light, hand at chin"}]},
                {"section_id": "S02", "section_name": "First problem", "copy": "It all lands on you.",
                 "slots": []},
                {"section_id": "S02A", "section_name": "First solution", "copy": "Hand it off.",
                 "cta": "SHOW ME HOW", "slots": []},
                {"section_id": "S11", "section_name": "Seven steps", "copy": "Seven steps follow.",
                 "slots": []},
                {"section_id": "S12", "section_name": "Founder letter", "copy": "Dear founder.",
                 "cta": "SAVE MY SEAT", "slots": []}]}


def canonical(req, form=None):
    """Pad a short fixture request to the declared form's canonical sections (SPF018: a request
    with a declared copy_version carries exactly the form's sections, in order)."""
    form = form or req["copy_version"]
    sequence = json.loads((exe.SPEC_DIR / f"{form}-v6.json").read_text(encoding="utf-8"))["sequence"]
    have = {exe.canon_section_id(x["section_id"]): x for x in req["sections"]}
    return dict(req, sections=[have.get(i) or {"section_id": i, "section_name": f"Section {i}",
                                               "copy": "Copy of the section.", "slots": []}
                               for i in sequence])


def png(path, width, height, base, chip=None):
    from PIL import Image, ImageDraw
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (width, height), base)
    if chip:
        draw = ImageDraw.Draw(img)
        draw.rectangle([40, 40, 240, 100], fill=chip)
        draw.rectangle([0, height // 2, width, height // 2 + 90], fill=chip)
    img.save(path)


class ReferenceSelectionTests(unittest.TestCase):
    def test_stage_and_form_pick_the_owners_sheets(self):
        want = {("standard", "desktop-wireframe"): "chatgpt-wireframe-1",
                ("long-form", "desktop-wireframe"): "chatgpt-wireframe-3",
                ("standard", "mobile-tablet"): "chatgpt-wireframe-4",
                ("long-form", "mobile-tablet"): "chatgpt-wireframe-4"}
        manifest = {e["file"]: e for e in
                    json.loads((STANDARDS / "manifest.json").read_text())["files"]}
        for (form, stage), name in want.items():
            ref = w.style_reference(stage, form)
            self.assertEqual(ref["name"], name)
            self.assertTrue(ref["url"].endswith(f"visual-standards/wireframes/{name}.png"))
            entry = manifest[f"wireframes/{name}.png"]
            self.assertEqual(hashlib.sha256(ref["path"].read_bytes()).hexdigest(), entry["sha256"])
        for ref in (w.style_reference(s, f) for f in w.FORMS for s in w.WIREFRAME_STAGES):
            self.assertNotIn(ref["name"], ("chatgpt-wireframe-2", "set-for-life-desktop-wireframe"))

    def test_manifest_and_spec_agree(self):
        manifest = json.loads((STANDARDS / "manifest.json").read_text())
        table = manifest["wireframe_style_references"]
        for form in w.FORMS:
            for stage in w.WIREFRAME_STAGES:
                self.assertEqual(table[form][stage], w.spec()["style_references"][form][stage]["file"])
        roles = {e["file"]: e.get("role", "") for e in manifest["files"]}
        self.assertIn("never attached", roles["wireframes/chatgpt-wireframe-2.png"])
        self.assertIn("not a target style", roles["wireframes/set-for-life-desktop-wireframe.png"])

    def test_form_is_declared_inferred_or_refused_when_paid(self):
        self.assertEqual(w.form_of({"copy_version": "Long-Form"}), "long-form")
        self.assertEqual(w.form_of({"metadata": {"copy_version": "standard"}}), "standard")
        self.assertEqual(w.form_of({"sections": [{"section_id": "S02A"}]}), "long-form")
        plain = {"sections": [{"section_id": f"S{n:02d}"} for n in range(1, 13)]}
        self.assertEqual(w.form_of(plain), "standard")
        with self.assertRaises(w.SpecError):
            w.form_of({"sections": [{"section_id": "hero"}]}, strict=True)

    def test_greyscale_sheet_reference_is_refused_by_name(self):
        for ref in ("https://x.example/uploads/set-for-life-desktop-wireframe.png",
                    "https://x.example/uploads/sfl-wireframe-part3.png",
                    str(STANDARDS / "wireframes" / "set-for-life-desktop-wireframe.png")):
            req = request()
            req["references"] = [ref]
            with self.assertRaises(w.SpecError) as ctx:
                w.reference_urls("desktop-wireframe", req)
            self.assertIn("greyscale", str(ctx.exception))
        req = request()
        req["references"] = ["https://x.example/uploads/some-other-reference.png"]
        self.assertEqual(len(w.reference_urls("desktop-wireframe", req)), 1)
        self.assertEqual(w.reference_urls("visual-mockup", req), [])


class PromptBlockTests(unittest.TestCase):
    def block(self, stage="desktop-wireframe", index=1, form="long-form", sections=None):
        req = request(form, sections)
        section = req["sections"][index - 1]
        width = 1440 if stage == "desktop-wireframe" else 390
        return w.prompt_block(stage, section, index, len(req["sections"]), width, req)

    def test_sheet_grammar_and_no_hard_coded_colour(self):
        text = self.block()
        for needle in ('"SECTION 1"', '"HERO CLAIM"', "INLINE TYPE SPECS", "IMAGE 16:9",
                       "edge bar", "CTA MICROCOPY", "1440 PX PAGE / 1200 PX CONTENT",
                       "BEHAVIOUR NOTE", "BRAND COLORS", "never colourless",
                       "DO NOT COPY THE EXAMPLE'S MISTAKES"):
            self.assertIn(needle, text)
        self.assertIsNone(re.search(r"#[0-9A-Fa-f]{6}\b", text), "no hex colour in the block")
        self.assertNotIn("no colour fill", text.lower().replace("never colourless", ""))
        self.assertEqual(exe.sanitize_prompt(text), text.strip(), "the scrub leaves the block alone")

    def test_header_strip_only_on_first_slice_and_mobile_widths(self):
        self.assertIn("WIDTHS HEADER STRIP — none", self.block(index=2))
        mobile = self.block(stage="mobile-tablet")
        self.assertIn("390 PX PAGE / 342 PX CONTENT", mobile)
        self.assertIn("single-column phone stack", mobile)

    def test_standard_mobile_carries_the_single_column_rule(self):
        text = self.block(stage="mobile-tablet", form="standard")
        self.assertIn("never side-by-side text-and-image rows", text)
        self.assertIn("narrowed desktop", text)

    def test_long_form_pairs_and_lettered_chip(self):
        text = self.block(index=3)
        self.assertIn('"SECTION 2A"', text)
        self.assertIn("SOLUTION band", text)
        self.assertIn("CTA strip", text)
        self.assertIn("PAIN band", self.block(index=2))
        self.assertNotIn("PAIN band", self.block(index=2, form="standard"))

    def test_founder_letter_stays_one_block_and_steps_run_one_to_seven(self):
        self.assertIn("one continuous reading column", self.block(index=5))
        self.assertIn("Never six cards", self.block(index=5))
        self.assertIn("1, 2, 3, 4, 5, 6, 7 once each", self.block(index=4))

    def test_invalid_ratio_and_colourless_prose_are_refused(self):
        sections = request()["sections"]
        sections[0]["slots"][0]["aspect_ratio"] = "3:9"
        with self.assertRaises(w.SpecError) as ctx:
            self.block(sections=sections)
        self.assertIn("3:9", str(ctx.exception))
        for prose in ("Draw the layout in warm grey line work on ivory, no colour fill.",
                      "Render a strictly greyscale wireframe."):
            with self.assertRaises(w.SpecError):
                w.refuse_colourless_prose("desktop-wireframe", prose)
        w.refuse_colourless_prose("desktop-wireframe", "Photography stays greyscale plates.")

    def test_art_direction_label_is_short(self):
        self.assertEqual(w.short_direction("Founder at a desk, window light, hand at chin"),
                         "Founder at a desk")
        self.assertLessEqual(len(w.short_direction("a " * 40).split()), 8)


class RepairRound1Tests(unittest.TestCase):
    """Defects from the round-1 review: ratio list, palette source, form source,
    negated colourless prose."""

    def test_ratio_list_is_one_list_for_executor_and_w3(self):
        labels = set(w.spec()["ratio_labels"])
        self.assertTrue(set(exe.RATIO_ENUM) <= labels)
        self.assertTrue({"2:1", "3:1", "1:3", "9:21", "1:2"} <= labels)
        self.assertEqual(labels, set(v.VALID_RATIO_LABELS))

    def test_every_documented_ratio_builds_and_unreduced_is_refused(self):
        for ratio in sorted(w.spec()["ratio_labels"]):
            sections = request()["sections"]
            sections[0]["slots"][0]["aspect_ratio"] = ratio
            self.assertIn(f"IMAGE {ratio} - ", w.prompt_block(
                "desktop-wireframe", sections[0], 1, len(sections), 1440, request(sections=sections)))
        for bad in ("3:9", "6:4", "7:5"):
            sections = request()["sections"]
            sections[0]["slots"][0]["aspect_ratio"] = bad
            with self.assertRaises(w.SpecError):
                w.prompt_block("desktop-wireframe", sections[0], 1, 5, 1440, request(sections=sections))

    def test_style_direction_reaches_a_wireframe_prompt_without_a_template(self):
        req = request("standard")
        req["style"] = "teal #0F7C7A on warm ivory"
        prompt = exe.stage_prompt("desktop-wireframe", req["sections"][0], 1, 1440, req, "16:9")
        self.assertIn("#0F7C7A", prompt)

    def test_paid_wireframe_without_a_brand_colors_line_is_refused(self):
        with self.assertRaises(exe.ExecutorError):
            exe.require_brand_line("desktop-wireframe", "COLOUR - from the BRAND COLORS line in this prompt")
        exe.require_brand_line("desktop-wireframe", "x\nBRAND COLORS - primary #C8091A")
        exe.require_brand_line("visual-mockup", "no colour line needed here")

    def test_form_is_read_from_intake_when_the_request_omits_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "intake.json").write_text(json.dumps({"copy_version": "standard"}))
            (run / "production-request.json").write_text(json.dumps(
                canonical({"sections": [{"section_id": "1", "copy": "x"}]}, "standard")))
            req = exe.load_request(run, "production-request.json")
            self.assertEqual(w.form_of(req, strict=True), "standard")
            self.assertTrue(w.reference_urls("desktop-wireframe", req, strict=True)[0]
                            .endswith("chatgpt-wireframe-1.png"))
            (run / "production-request.json").write_text(json.dumps(
                canonical({"copy_version": "long-form", "sections": [{"section_id": "1", "copy": "x"}]})))
            self.assertEqual(w.form_of(exe.load_request(run, "production-request.json"), strict=True),
                             "long-form")

    def test_colourless_prose_ignores_negated_and_plate_sentences(self):
        for ok in ("Plates are neutral grey with no colour fill.",
                   "Image plates stay neutral grey, never grey line work.",
                   "The sheet is never grey line work on a pale ground, never colourless.",
                   "Never use grey line work. Fill chips in the primary colour."):
            w.refuse_colourless_prose("desktop-wireframe", ok)
        for blocks in w.spec()["blocks"].values():
            for text in ([blocks] if isinstance(blocks, str) else blocks):
                w.refuse_colourless_prose("desktop-wireframe", text)
        run_002 = ("Draw the layout only: stacked blocks, rules, type placeholders and image "
                   "boxes in warm grey line work on ivory, no photography, no colour fill.")
        for bad in (run_002,
                    "Draw the layout in warm grey line work on ivory, no colour fill.",
                    "Keep the sheet pure greyscale.",
                    "Use grey line work. Photos are muted."):
            with self.assertRaises(w.SpecError):
                w.refuse_colourless_prose("desktop-wireframe", bad)


class ExecutorWiringTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tmp.name) / "run"
        self.run_dir.mkdir()
        # A run needs resolved client brand colors before an image stage starts
        # (SPF019, scripts/brand_colors.py); BlackCEO's own intake resolves from the
        # bundled file. Ignored on a tree without that gate.
        (self.run_dir / "intake.json").write_text(
            json.dumps({"brand_owner": "blackceo", "brand_file": "assets/brand/blackceo-brand.json"}),
            encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, req):
        (self.run_dir / "production-request.json").write_text(json.dumps(canonical(req)), encoding="utf-8")

    def execute(self, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / "stage_executor.py"),
                               str(self.run_dir), *args], capture_output=True, text=True)

    def test_stage_prompt_carries_the_block_only_on_wireframe_stages(self):
        req = request()
        section = req["sections"][0]
        wire = exe.stage_prompt("desktop-wireframe", section, 1, 1440, req, "16:9")
        req["_hypersat"] = exe.hypersaturation.roles_for_run(self.run_dir)  # mockups need the resolved palette
        mock = exe.stage_prompt("visual-mockup", section, 1, 1440, req, "3:4")
        self.assertIn("WIREFRAME BUILD SPEC", wire)
        self.assertNotIn("WIREFRAME BUILD SPEC", mock)
        self.assertTrue(wire.index("VERBATIM COPY") < wire.index("WIREFRAME BUILD SPEC"))

    def test_request_with_grey_prompt_is_refused_before_any_call(self):
        req = request()
        req["stage_prompts"] = {"desktop-wireframe": "Warm grey line work on ivory, no colour fill."}
        self.write(req)
        proc = self.execute("--preflight", "--stages", "desktop-wireframe")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("colourless", proc.stdout)

    def test_preflight_prints_the_reference_sent_by_form(self):
        self.write(request("long-form"))
        proc = self.execute("--preflight", "--stages", "desktop-wireframe,mobile-tablet")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        desk = [l for l in proc.stdout.splitlines()
                if l.startswith("PREFLIGHT_WIREFRAME_REFS desktop-wireframe")]
        mob = [l for l in proc.stdout.splitlines()
               if l.startswith("PREFLIGHT_WIREFRAME_REFS mobile-tablet")]
        self.assertTrue(desk and all("form=long-form" in l and "chatgpt-wireframe-3.png" in l
                                     for l in desk), proc.stdout)
        self.assertTrue(mob and all("chatgpt-wireframe-4.png" in l for l in mob), proc.stdout)
        self.assertNotIn("set-for-life", "\n".join(desk + mob))

    def test_greyscale_reference_in_a_request_is_refused(self):
        req = request()
        req["references"] = ["https://x.example/set-for-life-desktop-wireframe.png"]
        self.write(req)
        proc = self.execute("--preflight", "--stages", "mobile-tablet")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("greyscale", proc.stdout)

    def test_record_inputs_list_the_style_reference_first(self):
        self.write(request("standard"))
        proc = self.execute("--provider", "stub", "--stages", "desktop-wireframe")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        record = json.loads((self.run_dir / "desktop-wireframe" / exe.RECORD).read_text())
        for image in record["images"]:
            self.assertTrue(image["inputs"][0].endswith("chatgpt-wireframe-1.png"), image["inputs"])

    def test_build_input_orders_style_reference_before_request_references(self):
        job = {"prompt": "p", "references": ["/slice.png"], "style_refs": ["https://s/style.png"]}
        out = exe.build_input(job, {"references": ["https://r/other.png"]})
        self.assertEqual(out["input_urls"], ["https://s/style.png", "https://r/other.png", "/slice.png"])


class GateTraitTests(unittest.TestCase):
    def palette(self, brand=PALETTE):
        return v.brand_color_sets(brand)[0]

    def test_tag_and_badge_sequences(self):
        self.assertEqual(v.tag_sequence_failures(["1", "2", "2A", "3", "3A", "4", "4A", "5", "6"]), [])
        self.assertEqual(v.tag_sequence_failures(["1", "2", "3", "4", "5A", "5B", "5C", "6"]), [])
        repeated = v.tag_sequence_failures(["1", "2", "3", "3", "5"])  # sheet 1: 3 twice, 4 skipped
        self.assertTrue(any("3 appears more than once" in l for l in repeated), repeated)
        self.assertTrue(any("5 is out of sequence" in l for l in repeated), repeated)
        wrong = v.tag_sequence_failures(["1", "2", "2A", "3", "3A", "4", "3A"])  # sheet 3
        self.assertTrue(any("3A appears more than once" in l and "4A" in l for l in wrong), wrong)
        self.assertEqual(v.badge_failures({"steps": list("1234567")}), [])
        self.assertTrue(v.badge_failures({"steps": ["1", "02", "icon", "3", "4", "6", "7"]}))
        self.assertTrue(v.badge_failures({"letter": ["01", "02", "05", "04", "05", "06"]}))

    def test_invalid_ratio_label_fails_w3(self):
        plan = [{"section_id": "a", "slot_labels": {"IMG-1": {"aspect_ratio": "3:9",
                                                              "art_direction": "x"}}}]
        lines = v.ratio_label_failures(plan)
        self.assertEqual(len(lines), 1)
        self.assertIn("3:9", lines[0])
        plan[0]["slot_labels"]["IMG-1"]["aspect_ratio"] = "1:3"
        self.assertEqual(v.ratio_label_failures(plan), [])

    def test_greyscale_slice_fails_w8_and_chip_and_branded_slice_passes(self):
        with tempfile.TemporaryDirectory() as td:
            grey = Path(td) / "grey.png"
            good = Path(td) / "good.png"
            png(grey, 1440, 810, PAPER)
            png(good, 1440, 810, INK, chip=CRIMSON)
            palette = self.palette()
            bad = v.style_failures("slice grey.png", v.measure_style(grey, palette), "fixture.json")
            self.assertTrue(bad["W8"], bad)
            self.assertTrue(bad["W1"], bad)
            self.assertTrue(bad["W4"], bad)  # grey never counts toward a brand colour
            ok = v.style_failures("slice good.png", v.measure_style(good, palette), "fixture.json")
            self.assertEqual(ok, {"W1": [], "W4": [], "W8": []})

    def test_palette_is_counted_against_the_resolved_client_palette(self):
        teal = dict(PALETTE, palette={"gold": "#0E7C86", "navy": "#12263A", "cream": "#F3F7F7"})
        with tempfile.TemporaryDirectory() as td:
            good = Path(td) / "good.png"
            png(good, 1440, 810, INK, chip=CRIMSON)
            lines = v.style_failures("slice good.png",
                                     v.measure_style(good, self.palette(teal)), "teal.json")
            self.assertTrue(lines["W4"] and "chromatic colour" in lines["W4"][0], lines)

    def test_achromatic_palette_has_nothing_to_measure(self):
        mono = dict(PALETTE, palette={"gold": "#111111", "navy": "#222222", "cream": "#FFFFFF"})
        with tempfile.TemporaryDirectory() as td:
            grey = Path(td) / "grey.png"
            png(grey, 800, 400, PAPER)
            self.assertEqual(v.style_failures("s", v.measure_style(grey, self.palette(mono)), "m"),
                             {"W1": [], "W4": [], "W8": []})

    def test_bundled_owner_sheets_pass_the_pixel_traits_in_a_red_palette(self):
        for n in (1, 3, 4):
            m = v.measure_style(STANDARDS / "wireframes" / f"chatgpt-wireframe-{n}.png",
                                self.palette(), slice_zone=False)
            self.assertEqual(v.style_failures(f"sheet {n}", m, "fixture.json"),
                             {"W1": [], "W4": [], "W8": []}, f"sheet {n}")
        grey = v.measure_style(STANDARDS / "wireframes" / "set-for-life-desktop-wireframe-slice1.png",
                               self.palette())
        self.assertTrue(v.style_failures("slice", grey, "fixture.json")["W8"])

    def test_directory_run_fails_a_greyscale_stage_and_records_w8(self):
        with tempfile.TemporaryDirectory() as td:
            run = Path(td) / "run"
            (run / "copy").mkdir(parents=True)
            (run / "desktop-wireframe").mkdir()
            (run / "copy" / "copy-manifest.json").write_text(
                json.dumps({"sections": [{"section_id": "hero"}]}))
            (run / "desktop-wireframe" / "image-inventory.json").write_text(
                json.dumps({"images": [{"id": "IMG-001", "aspect_ratio": "16:9"}]}))
            (run / "desktop-wireframe" / "section-plan.json").write_text(json.dumps([{
                "section_id": "hero", "section_number": 1, "section_name": "Hero",
                "section_tag": "1", "copy_block_ids": [], "image_slot_ids": ["IMG-001"],
                "type_specs": {"h1": "64", "h2": "48", "body": "18", "cta": "18"},
                "behavior_notes": "No CTA",
                "header_strip": {"page_width_px": 1440, "content_width_px": 1200},
                "slot_labels": {"IMG-001": {"aspect_ratio": "16:9", "art_direction": "founder portrait"}}}]))
            png(run / "desktop-wireframe" / "section-01.png", 1440, 17000, PAPER)
            (run / "desktop-wireframe" / "wireframe-full.png").write_text("x")
            (run / "desktop-wireframe" / "wireframe.pdf").write_text("x")
            brand = Path(td) / "brand.json"
            brand.write_text(json.dumps(PALETTE))
            proc = subprocess.run([sys.executable, str(SCRIPTS / "validate_wireframe.py"), str(run),
                                   "desktop-wireframe", "--brand", str(brand)],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 1, proc.stdout)
            self.assertIn("W8", proc.stdout)
            record = json.loads((run / "private" / "wireframe-verdicts.json").read_text())
            traits = record["stages"]["desktop-wireframe"]["traits"]
            self.assertEqual(traits["W8"]["verdict"], "fail")
            self.assertEqual(traits["W1"]["verdict"], "fail")


if __name__ == "__main__":
    unittest.main(verbosity=2)
