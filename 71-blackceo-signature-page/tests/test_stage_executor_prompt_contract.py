#!/usr/bin/env python3
"""Contract tests for the generation wire's prompt and geometry repairs.

Pins the four source-level repairs:
  - verbatim copy goes first, exactly once, with the exact CTA label;
  - provenance (local paths, reference filenames, reference raster px)
    never reaches the model;
  - copy padded with style prose, or cut mid-sentence, is refused
    before a paid call;
  - each job sees only its own section's earlier slices, and the
    requested ratio is the pixel-mate's, not one 3:4 for every part.
"""
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("stage_executor", ROOT / "scripts/stage_executor.py")
exe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exe)

SECTION = {
    "section_id": "S01", "section_name": "Hero",
    "copy": "You’re doing every job. CTA: SAVE MY SEAT.",
    "slots": [{"slot_id": "IMG-001", "aspect_ratio": "3:4",
               "art_direction": "Founder at a desk."}],
}
LEAKY = ("Styled mockup section {section_number} {section_name} at {width}px ratio {ratio}. "
         "File: /Users/example/ref/chatgpt-mockup-4.png. Pixels: 724 × 2172. "
         "SHA-256: deadbeef. Raster: 724 × 2172. {copy} {slots}")
# Mockup prompts need a resolved client palette (hypersaturation is built in); a made-up client.
PALETTE = {"hero": "#0B5FFF", "dark": "#0A0A12", "light": "#FFFFFF", "accent": "#FFB400"}
REQUEST = {"model": "gpt-image-2-5-sunburst-image-to-image", "_hypersat": PALETTE,
           "style": "warm editorial", "stage_prompts": {"visual-mockup": LEAKY}}


class PromptContractTests(unittest.TestCase):
    def test_copy_first_once_and_provenance_removed(self):
        prompt = exe.stage_prompt("visual-mockup", SECTION, 1, 1440, REQUEST, "3:4")
        self.assertTrue(prompt.startswith("VERBATIM COPY"), prompt[:80])
        self.assertEqual(prompt.count("You’re doing every job."), 1)
        self.assertIn('CTA LABEL — print exactly: "SAVE MY SEAT"', prompt)
        for leak in ("/Users/", "chatgpt-mockup-4", "724", "2172", "SHA-256"):
            self.assertNotIn(leak, prompt)
        self.assertIn("FRAME CONTRACT", prompt)
        self.assertIn("no blank bands", prompt)

    def test_style_padding_inside_copy_is_refused(self):
        section = dict(SECTION, copy=SECTION["copy"] + " Preserve the measured band order.")
        with self.assertRaises(exe.ExecutorError) as ctx:
            exe.stage_prompt("visual-mockup", section, 1, 1440, REQUEST, "3:4")
        self.assertIn("style padding", str(ctx.exception))

    def test_mid_sentence_copy_is_refused(self):
        for tail in ("The leads, the follow-up, the invoices,", "Every hire adds cost and management, not"):
            with self.assertRaises(exe.ExecutorError) as ctx:
                exe.stage_prompt("visual-mockup", dict(SECTION, copy=tail), 1, 1440, REQUEST, "3:4")
            self.assertIn("ends mid-sentence", str(ctx.exception))

    def test_nearest_offered_ratio(self):
        self.assertEqual(exe.nearest_ratio(1024, 3072), "9:16")
        self.assertEqual(exe.nearest_ratio(1672, 941), "16:9")
        self.assertEqual(exe.nearest_ratio(1440, 1920), "3:4")
        self.assertEqual(exe.nearest_ratio(390, 520), "3:4")

    def test_only_same_index_slices_are_attached(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            for stage in ("desktop-wireframe", "mobile-tablet", "visual-mockup"):
                (run / stage / "desktop").mkdir(parents=True)
                (run / stage / "mobile").mkdir(parents=True)
            exe.stub_png(run / "desktop-wireframe/section-01.png", 1440, 810, "d1")
            exe.stub_png(run / "desktop-wireframe/section-02.png", 1440, 810, "d2")
            exe.stub_png(run / "mobile-tablet/section-01.png", 390, 693, "m1")
            exe.stub_png(run / "visual-mockup/desktop/part-01.png", 1440, 2560, "v1")
            refs = exe.prior_slices("visual-mockup", run, 1, "desktop/part-01.png")
            self.assertEqual(len(refs), 2)
            self.assertTrue(all("01" in p.name for p in refs))
            ratio = exe.target_ratio("visual-mockup", "desktop/part-01.png",
                                     SECTION, run, 1)
            self.assertEqual(ratio, "16:9")

    def test_png_size_reads_ihdr(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "slice.png"
            exe.stub_png(out, 390, 520, "size")
            self.assertEqual(exe.png_size(out), (390, 520))


class WireRepairRoundThreeTests(unittest.TestCase):
    """Attempt-3 contract: placeholders, CTA recovery, leaks, budget band."""

    NO_CTA = {"section_id": "S02", "section_name": "Problem",
              "copy": "Every hour goes to the business.",
              "slots": [{"slot_id": "IMG-002", "aspect_ratio": "4:3",
                         "art_direction": "Desk detail."}]}

    def test_double_brace_template_renders_clean(self):
        request = {"model": "stub", "_hypersat": PALETTE,
                   "stage_prompts": {"visual-mockup":
                       "{{section_name}} section {{section_number}} at {width}px. "
                       "{copy} {slots}"}}
        prompt = exe.stage_prompt("visual-mockup", SECTION, 1, 1440, request, "3:4")
        self.assertIn("Hero section 1 at 1440px", prompt)
        self.assertNotIn("{section_name}", prompt)
        self.assertNotIn("{section_number}", prompt)

    def test_genuine_leftover_placeholder_refuses(self):
        request = {"model": "stub", "style": "warm {layout_tokens}",
                   "stage_prompts": {"visual-mockup": "{{section_name}} {style}"}}
        with self.assertRaises(exe.ExecutorError) as ctx:
            exe.stage_prompt("visual-mockup", SECTION, 1, 1440, request, "3:4")
        self.assertIn("placeholder", str(ctx.exception))
        self.assertIn("before any provider call", str(ctx.exception))

    def test_cta_accepted_from_section_payload_dict(self):
        section = dict(self.NO_CTA, cta={"label": "SHOW ME THE SYSTEM",
                                         "microcopy": "45 minutes"})
        prompt = exe.stage_prompt("visual-mockup", section, 2, 1440,
                                  {"model": "stub", "_hypersat": PALETTE}, "4:3")
        self.assertIn('CTA LABEL — print exactly: "SHOW ME THE SYSTEM"', prompt)

    def test_cta_resolves_from_the_run_copy_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "copy.json").write_text(json.dumps({"sections": [
                {"id": "S01", "cta": {"label": "SAVE MY SEAT"}},
                {"id": "S02", "headline": "No button here"}]}), encoding="utf-8")
            (run / "intake.json").write_text(json.dumps({"brand_owner": "blackceo", "brand_file": "assets/brand/blackceo-brand.json"}), encoding="utf-8")
            (run / "production-request.json").write_text(json.dumps({
                "model": "stub", "sections": [
                    {"section_id": "S01", "section_name": "Hero",
                     "copy": "You’re doing every job.", "slots": []}]}), encoding="utf-8")
            request = exe.load_request(run, "production-request.json")
            prompt = exe.stage_prompt("final-mockups", request["sections"][0], 1,
                                      1440, request, "3:4")
            self.assertIn('CTA LABEL — print exactly: "SAVE MY SEAT"', prompt)

    def test_cta_required_without_a_source_refuses_by_section(self):
        section = {"section_id": "S09", "section_name": "No CTA",
                   "copy": "Copy with no button.", "slots": [],
                   "cta_required": True}
        with self.assertRaises(exe.ExecutorError) as ctx:
            exe.stage_prompt("final-mockups", section, 9, 1440, {"model": "stub"}, "3:4")
        self.assertIn("S09", str(ctx.exception))
        self.assertIn("CTA", str(ctx.exception))

    def test_cross_client_and_dimension_leaks_removed(self):
        template = (
            "Design system measured.\n"
            "- Excluded: the Set for Life desktop mockup (MD, 1440×16723). "
            "The prior review classifies MD as Tier H (flat, sparse).\n"
            "MD (Set for Life desktop mockup) is classified Tier H by the prior review.\n"
            "The page canvas is 1440x16736 and the reference is 724 × 2172.\n"
            "Keep the BlackCEO gold hairline rules and the 1440px frame.\n"
            "{copy} {slots}")
        request = {"model": "stub", "_hypersat": PALETTE, "stage_prompts": {"visual-mockup": template}}
        prompt = exe.stage_prompt("visual-mockup", SECTION, 1, 1440, request, "3:4")
        for leak in ("Set for Life", "Tier H", "1440×16723", "1440x16736",
                     "724 × 2172", "MD ("):
            self.assertNotIn(leak, prompt)
        self.assertIn("BlackCEO gold hairline", prompt)
        self.assertIn("1440px frame", prompt)

    def test_below_floor_warns_and_names_the_deficit(self):
        request = {"model": "gpt-image-2-5-sunburst", "_hypersat": PALETTE,
                   "stage_prompts": {"visual-mockup": "{copy}"}}
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            prompt = exe.stage_prompt("visual-mockup", SECTION, 1, 1440, request, "3:4")
        self.assertIn("below the 16000-char floor", stderr.getvalue())
        self.assertIn("chars", stderr.getvalue())
        self.assertTrue(prompt)

    def test_design_prose_section_budget_refuses(self):
        filler = "Detailed rule. " * 1400
        request = {"model": "gpt-image-2-5-sunburst", "_hypersat": PALETTE,
                   "stage_prompts": {"visual-mockup": filler + "{copy} {slots}"}}
        with self.assertRaises(exe.ExecutorError) as ctx:
            exe.stage_prompt("visual-mockup", SECTION, 1, 1440, request, "3:4")
        message = str(ctx.exception)
        self.assertIn("design prose", message)
        self.assertIn("section budget", message)
        self.assertIn("20000", message)


class CopySourceAndTierRoundFourTests(unittest.TestCase):
    """SUPP007R4: real copy-source layouts and standalone tier verdicts."""

    COPY = {"sections": [
        {"id": "S01", "cta": {"label": "SAVE MY SEAT"}},
        {"id": "S02", "cta": None},
        {"id": "S05", "cta": {"label": "SHOW ME THE SYSTEM"}},
    ]}

    @staticmethod
    def _request(**extra):
        request = {"model": "stub", "sections": [
            {"section_id": f"S{i:02d}", "copy": "Sentence ends here.", "slots": []}
            for i in range(1, 7)]}
        request.update(extra)
        return request

    def test_inputs_copy_json_resolves_when_run_root_has_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "inputs").mkdir()
            (run / "inputs" / "copy.json").write_text(json.dumps(self.COPY), encoding="utf-8")
            (run / "r.json").write_text(json.dumps(self._request()), encoding="utf-8")
            data = exe.load_request(run, "r.json")
            labels = {s["section_id"]: s.get("cta") for s in data["sections"] if s.get("cta")}
            self.assertEqual(labels, {"S01": "SAVE MY SEAT", "S05": "SHOW ME THE SYSTEM"})

    def test_metadata_copy_source_resolves(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            source = run / "elsewhere.json"
            source.write_text(json.dumps(self.COPY), encoding="utf-8")
            request = self._request(metadata={"copy_source": str(source)})
            self.assertEqual(exe.copy_source_ctas(run, request)["S05"], "SHOW ME THE SYSTEM")

    def test_inline_cta_survives_a_raw_id_copy_conflict_with_a_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "inputs").mkdir()
            (run / "inputs" / "copy.json").write_text(json.dumps(self.COPY), encoding="utf-8")
            request = self._request()
            request["sections"][4]["cta"] = "JOIN THE FREE TRAINING"
            (run / "r.json").write_text(json.dumps(request), encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                data = exe.load_request(run, "r.json")
            self.assertEqual(data["sections"][4]["cta"], "JOIN THE FREE TRAINING")
            note = stderr.getvalue()
            self.assertIn("NOTE cta_namespace section S05", note)
            self.assertIn("SHOW ME THE SYSTEM", note)
            self.assertNotIn("WARN cta_conflict", note)

    def test_run_003_band_layout_keeps_all_six_mapping_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "copy.json").write_text(json.dumps(self.COPY), encoding="utf-8")
            sections = [
                {"section_id": "S01", "cta": "SAVE MY SEAT"},
                {"section_id": "S02", "cta": None},
                {"section_id": "S03", "cta": None},
                {"section_id": "S04", "cta": "SHOW ME THE SYSTEM"},
                {"section_id": "S05", "cta": "JOIN THE FREE TRAINING"},
                {"section_id": "S06", "cta": "SAVE MY SEAT"},
            ]
            for section in sections:
                section.update({"copy": "Sentence ends here.", "slots": []})
            (run / "r.json").write_text(
                json.dumps({"model": "stub", "sections": sections}),
                encoding="utf-8")
            data = exe.load_request(run, "r.json")
            self.assertEqual(
                [exe._cta_label(s.get("cta")) or "-" for s in data["sections"]],
                ["SAVE MY SEAT", "-", "-", "SHOW ME THE SYSTEM",
                 "JOIN THE FREE TRAINING", "SAVE MY SEAT"])

    def test_run_001_copy_source_layout_resolves_two_of_six(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "copy.json").write_text(json.dumps(self.COPY), encoding="utf-8")
            (run / "r.json").write_text(json.dumps(self._request()), encoding="utf-8")
            data = exe.load_request(run, "r.json")
            labels = [exe._cta_label(s.get("cta")) for s in data["sections"]]
            self.assertEqual(len([label for label in labels if label]), 2)
            self.assertIn("SAVE MY SEAT", labels)
            self.assertIn("SHOW ME THE SYSTEM", labels)

    def test_no_copy_source_and_cta_required_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "r.json").write_text(json.dumps(self._request(cta_required=True)),
                                        encoding="utf-8")
            data = exe.load_request(run, "r.json")
            with self.assertRaises(exe.ExecutorError) as ctx:
                exe.copy_contract(data["sections"][0])
            self.assertIn("requires a CTA label", str(ctx.exception))

    def test_standalone_tier_shapes_strip(self):
        shapes = (
            "**Mockup — Tier H (flat, sparse).** Cream #f7f2e9.",
            "**Mockup — Tier R (layered, photo-dense).** Rust #a2362d.",
            "Tier H sparse, one photo per planned band at most.",
            "# SPF003 — reference design rules (Tier R rich mockup, M4)",
            "The sheet is REF Tier H and must read flat.",
            "AA Tier H is the fallback classification.",
        )
        for shape in shapes:
            self.assertNotIn("Tier", exe.sanitize_prompt(shape), shape)
        keep = "You’re doing every job. CTA: SAVE MY SEAT."
        self.assertEqual(exe.sanitize_prompt(keep), keep)



if __name__ == "__main__":
    unittest.main(verbosity=2)
