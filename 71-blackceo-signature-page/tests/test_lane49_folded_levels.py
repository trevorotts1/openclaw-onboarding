#!/usr/bin/env python3
"""LANE-49: a sales page that folds N levels into itself (journey_mode folded_levels, no selection
page) closes on an N-card levels panel, on the wireframes, with every card's button leading to
checkout; and a second downsell is labelled Downsell 2 on every file it makes.

No provider is called anywhere in this module.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SCRIPTS))
import deliverable_labels as labels  # noqa: E402
import page_kinds as pk  # noqa: E402
import stage_executor as executor  # noqa: E402
import wireframe_spec as w  # noqa: E402
from brand_fixture import give_blackceo_colors  # noqa: E402

_spec = importlib.util.spec_from_file_location("build_production_request", SCRIPTS / "build_production_request.py")
builder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(builder)
MANUSCRIPT = HERE / "fixtures" / "copy_examples" / "long-form-path-b.md"


def slice_block(kind, index, total, **request_extra):
    request = {"copy_version": "long-form", "page_kind": kind, **request_extra}
    section = {"section_id": str(index), "section_name": "Founder letter", "copy": "A finished sentence.",
               "cta": "GET IT", "slots": []}
    return w.prompt_block("desktop-wireframe", section, index, total, 1440, request)


class FoldedLevelsTests(unittest.TestCase):
    def test_sales_page_closes_on_a_three_card_levels_panel(self):
        last = slice_block("sales", 15, 15, folded_levels=3)
        self.assertIn("exactly 3 level cards", last)
        self.assertIn("one card per level", last)
        self.assertNotIn("one full-width closing checkout panel", last)

    def test_levels_panel_is_on_the_last_slice_only(self):
        self.assertNotIn("level cards", slice_block("sales", 14, 15, folded_levels=3))

    def test_without_levels_the_sales_page_is_byte_for_byte_unchanged(self):
        plain = slice_block("sales", 15, 15)
        self.assertEqual(plain, slice_block("sales", 15, 15, folded_levels=None))
        self.assertEqual(plain, slice_block("sales", 15, 15, folded_levels=1))
        self.assertIn("closing checkout panel", plain)

    def test_an_opt_in_page_never_shows_levels(self):
        self.assertEqual(slice_block("opt_in", 15, 15), slice_block("opt_in", 15, 15, folded_levels=3))

    def test_a_bad_level_count_is_refused(self):
        with self.assertRaises(pk.KindError):
            pk.wireframe_lines("sales", "Long-Form", 15, 15, "GET IT", levels="three")

    def test_mockup_line_carries_the_levels_panel(self):
        self.assertIn("exactly 3 level cards", pk.mockup_line("sales", "GET IT", levels=3))
        self.assertNotIn("level cards", pk.mockup_line("sales", "GET IT"))


class BuilderStampsFoldedLevelsTests(unittest.TestCase):
    """The production request a real run builds carries the level count, read from the run's own
    launch record, so the wireframes of a folded-levels sales page close on the levels panel."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name)
        give_blackceo_colors(self.run)
        self.addCleanup(self.tmp.cleanup)

    def write_run_launch(self, mode, mains):
        # the shape 83 to_launch_record really writes: an offer's place in the journey is "slot"
        offers = [{"offer_id": f"M{i}", "slot": "main"} for i in range(mains)] + [{"offer_id": "U1", "slot": "upsell_1"}]
        (self.run / "launch.json").write_text(json.dumps({"journey_mode": mode, "offers": offers}), encoding="utf-8")

    def request(self, kind="sales"):
        return builder.build("desktop-wireframe", "long-form", MANUSCRIPT.read_text(encoding="utf-8"), {}, {}, [],
                             "STUB-NO-MODEL", "", self.run, page_kind=kind)

    def test_a_folded_levels_launch_stamps_its_main_offer_count(self):
        self.write_run_launch("folded_levels", 3)
        request = self.request()
        self.assertEqual(request["folded_levels"], 3)
        last = request["sections"][-1]
        block = w.prompt_block("desktop-wireframe", last, len(request["sections"]), len(request["sections"]), 1440, request)
        self.assertIn("exactly 3 level cards", block)

    def test_the_real_83_seven_figure_preneur_record_yields_three_levels(self):
        # the record 83 to_launch_record builds from its seven-figure-preneur fixture, built in a child
        # process so 83's modules never touch this test's import path
        root = HERE.parents[1] / "83-black-friday-launcher"
        code = ("import json,sys;from pathlib import Path;sys.path.insert(0,'.');"
                "from launcher_core import intake,route,launch_bridge as lb;"
                "n=intake.validate(json.loads(Path('fixtures/seven-figure-preneur/intake.json').read_text()));"
                "print(json.dumps(lb.to_launch_record(n,route.compile_route(n),{'image_provider':'kie','design_style':'B'})))")
        proc = subprocess.run([sys.executable, "-I", "-c", code], cwd=root, text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        record = json.loads(proc.stdout)
        self.assertTrue(all("slot" in o and "role" not in o for o in record["offers"]))
        (self.run / "launch.json").write_text(json.dumps(record), encoding="utf-8")
        self.assertEqual(builder.folded_levels(self.run), 3)
        self.assertEqual(self.request()["folded_levels"], 3)

    def test_no_launch_record_a_single_offer_or_an_opt_in_page_is_unchanged(self):
        self.assertNotIn("folded_levels", self.request())
        self.write_run_launch("single_simple", 1)
        self.assertNotIn("folded_levels", self.request())
        self.write_run_launch("folded_levels", 3)
        self.assertNotIn("folded_levels", self.request("opt_in"))

    def test_the_visual_mockup_prompt_closes_on_the_levels_panel_too(self):
        self.write_run_launch("folded_levels", 3)
        request = builder.build("visual-mockup", "long-form", MANUSCRIPT.read_text(encoding="utf-8"), {}, {}, [],
                                "STUB-NO-MODEL", "", self.run, page_kind="sales")
        (self.run / "production-request.json").write_text(json.dumps(request), encoding="utf-8")
        loaded = executor.load_request(self.run, "production-request.json")
        sections = loaded["sections"]
        last = executor.stage_prompt("visual-mockup", sections[-1], len(sections), 1440, loaded, "3:2")
        self.assertIn("exactly 3 level cards", last)
        self.assertNotIn("one full-width closing checkout panel", last)

    def test_the_stamped_request_still_preflights(self):
        self.write_run_launch("folded_levels", 3)
        (self.run / "production-request.json").write_text(json.dumps(self.request()), encoding="utf-8")
        proc = subprocess.run([sys.executable, str(SCRIPTS / "stage_executor.py"), str(self.run), "--preflight",
                               "--stages", "desktop-wireframe"], text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class UpsellLayoutStampTests(unittest.TestCase):
    """UPS-20/21 (carried from U-upsell-05): with page-structures.json `layouts` declared, an upsell
    section carries its layout tag and an image plate from the layout, never one derived from its heading."""
    SKILL80 = HERE.parents[1] / "80-signature-upsell"
    COPY = SKILL80 / "components/80-signature-upsell/fixtures/copy-upsell1-public.valid.json"
    BUNDLE = SKILL80 / "examples/upsell-result-bundle-upsell1.example.json"

    def sections(self, structures):
        path = Path(tempfile.mkdtemp()) / "page-structures.json"
        path.write_text(json.dumps(structures), encoding="utf-8")
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        old, executor.STRUCTURES_FILE = executor.STRUCTURES_FILE, path
        self.addCleanup(lambda: setattr(executor, "STRUCTURES_FILE", old))
        spec = json.loads((executor.SPEC_DIR / "upsell-v6.json").read_text(encoding="utf-8"))
        load = lambda f: json.loads(f.read_text(encoding="utf-8"))
        return builder.sections_from_copy_json(load(self.COPY), load(self.BUNDLE), spec, {})

    def test_layout_tag_and_plate_come_from_the_declared_layout(self):
        if not self.COPY.is_file():
            self.skipTest("Skill 80 is not installed beside Skill 71")
        layout = {"sections": [{"id": str(i), "layout_tag": f"tag-{i}", "geometry": f"Band {i} geometry.",
                                "slot": {"slot_id": f"IMG-{i:03d}", "aspect_ratio": "4:3"}} for i in range(1, 9)]}
        out = self.sections({"layouts": {"note": "x", "upsell_1": layout}})
        self.assertEqual([s["layout_tag"] for s in out], [f"tag-{i}" for i in range(1, 9)])
        for s in out:
            art = s["slots"][0]["art_direction"]
            self.assertNotIn("illustrates", art)
            self.assertTrue(art.startswith(f"Band {s['section_id']} geometry."))
        with self.assertRaises(builder.BuildError):  # layouts declared, but none for this instance
            self.sections({"layouts": {"upsell_2": layout}})


class SelectionStructureEnforcementTests(unittest.TestCase):
    """PRD-23: a required section's rows must parse; an empty Compare is a failure, not a flag."""
    SPEC = HERE.parent / "references" / "copy-specs" / "product-selection-v1.json"
    SELECTION = (HERE / "fixtures" / "copy_examples" / "product-selection-path-b.md").read_text(encoding="utf-8")

    def verdict(self, text):
        import validate_copy_structure as v
        units, order, notes = v.parse_manuscript(text)
        return v.validate(units, order, notes, v.load_spec(self.SPEC)).fails

    def compare_with(self, body):
        head, rest = self.SELECTION.split("## Section 4: Compare\n", 1)
        return head + "## Section 4: Compare\n" + body + "\n## Section 5:" + rest.split("## Section 5:", 1)[1]

    def test_the_real_manuscript_still_passes(self):
        self.assertEqual(self.verdict(self.SELECTION), [])

    def test_an_empty_compare_fails_in_the_validator_and_exits_non_zero(self):
        self.assertTrue(any("Compare" in f for f in self.verdict(self.compare_with(""))))
        path = Path(tempfile.mkdtemp()) / "empty-compare.md"
        path.write_text(self.compare_with(""), encoding="utf-8")
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        proc = subprocess.run([sys.executable, str(SCRIPTS / "validate_copy_structure.py"), str(path),
                               "--spec", str(self.SPEC)], text=True, capture_output=True)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)

    def test_prose_instead_of_rows_fails_and_a_matrix_table_passes(self):
        self.assertTrue(self.verdict(self.compare_with("Everything is included in every package.\n")))
        table = "| Item | Essential | Pro |\n|---|---|---|\n| Course | included | included |\n"
        self.assertEqual(self.verdict(self.compare_with(table)), [])
        self.assertTrue(self.verdict(self.compare_with("| Item | Essential | Pro |\n|---|---|---|\n")))


class StructureRatificationTests(unittest.TestCase):
    """STR-17: no copy spec still reads as a proposal, each carries its dated decision, and the page
    handoff manifest carries a structure_approval field."""

    def test_no_spec_status_says_proposed_or_awaiting(self):
        specs = sorted((HERE.parent / "references" / "copy-specs").rglob("*.json"))
        self.assertGreaterEqual(len(specs), 6)
        for path in specs:
            status = str(json.loads(path.read_text(encoding="utf-8")).get("status", "")).lower()
            for word in ("proposed", "proposal", "awaiting", "pending"):
                self.assertNotIn(word, status, path.name)

    def test_each_ratified_spec_carries_the_dated_decision(self):
        for rel in ("product-selection-v1.json", "thank-you-v1.json", "standard-v6.json", "long-form-v6.json", "roles/checkout.json"):
            spec = json.loads((HERE.parent / "references" / "copy-specs" / rel).read_text(encoding="utf-8"))
            self.assertEqual(spec["structure_approval"]["decision"], "ratified_as_built", rel)
            self.assertRegex(spec["structure_approval"]["date"], r"^\d{4}-\d{2}-\d{2}$")

    def test_the_page_handoff_manifest_carries_the_structure_approval(self):
        import page_result
        for request in ({"page_role": "thank_you"}, {"page_role": "checkout"}, {"page_role": "product_selection"},
                        {"page_role": "landing", "copy_profile": "standard"},
                        {"page_role": "landing", "copy_profile": "long_form"}):
            got = page_result.structure_approval(request)
            self.assertEqual((got["decision"], got["date"]), ("ratified_as_built", "2026-11-02"), request)
        # a page whose spec records no decision is labelled, never silently approved
        self.assertEqual(page_result.structure_approval({"page_role": "downsell_1"})["decision"],
                         "structure pending approval")


class SecondDownsellLabelTests(unittest.TestCase):
    def setUp(self):
        self.run_dir = tempfile.mkdtemp()
        Path(self.run_dir, "page-request.json").write_text('{"page_role": "downsell_1"}', encoding="utf-8")
        os.environ.pop("SIGNATURE_ROLE_INSTANCE", None)

    def tearDown(self):
        os.environ.pop("SIGNATURE_ROLE_INSTANCE", None)

    def test_a_downsell_run_is_downsell_1_unless_it_is_the_second_instance(self):
        self.assertEqual(labels.declared_page_role(self.run_dir), "downsell_1")
        os.environ["SIGNATURE_ROLE_INSTANCE"] = "downsell_2"
        self.assertEqual(labels.declared_page_role(self.run_dir), "downsell_2")
        self.assertEqual(labels.title_band("downsell_2", "mobile", "visual-mockup", 8),
                         "DOWNSELL 2 · MOBILE MOCKUP · 8 SECTIONS")

    def test_an_instance_of_another_family_is_ignored(self):
        os.environ["SIGNATURE_ROLE_INSTANCE"] = "upsell_2"
        self.assertEqual(labels.declared_page_role(self.run_dir), "downsell_1")


class UpsellBandLayoutTagTests(unittest.TestCase):
    """CARRIED 7: every upsell band is drawn from its declared layout (page-structures.json layouts)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        layout = json.loads(executor.STRUCTURES_FILE.read_text(encoding="utf-8"))["layouts"]["upsell_1"]
        self.tags = [s["layout_tag"] for s in layout["sections"]]

    def check(self, tags):
        sections = [{"section_id": str(i), **({"layout_tag": t} if t else {})} for i, t in enumerate(tags, 1)]
        return executor.check_section_count(self.run, {"page_role": "upsell_1", "copy_version": "upsell",
                                                       "sections": sections}, True)

    def test_the_declared_tags_pass(self):
        self.assertEqual(self.check(self.tags)[1], [str(i) for i in range(1, 9)])

    def test_a_swapped_tag_is_refused_naming_the_section(self):
        tags = list(self.tags)
        tags[2] = tags[3]
        with self.assertRaises(executor.ExecutorError) as ctx:
            self.check(tags)
        self.assertIn("band layout: section 3 of upsell_1", str(ctx.exception))

    def test_no_tag_is_refused(self):
        with self.assertRaises(executor.ExecutorError) as ctx:
            self.check([None] + self.tags[1:])
        self.assertIn("band layout: section 1 of upsell_1 carries layout_tag None", str(ctx.exception))


class CheckoutRecordingTests(unittest.TestCase):
    """CARRIED 54: write_intake.py records the CHK-28 proof; validate_handoff.py accepts it."""

    URL = "https://pay.example.com/checkout/elevate"
    ATTEST = {"url": URL, "attested_by": "client", "product": "Elevate", "price": {"amount": 97, "currency": "usd"}}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name) / "run"
        self.run.mkdir()
        self.addCleanup(self.tmp.cleanup)
        self.attest = Path(self.tmp.name) / "attest.json"
        self.attest.write_text(json.dumps(self.ATTEST), encoding="utf-8")

    def write_intake(self, *extra):
        return subprocess.run([sys.executable, str(SCRIPTS / "write_intake.py"), str(self.run), "--brand-owner", "TEST",
                               "--image-cap", "5", "--copy-version", "standard", "--page-kind", "sales",
                               "--design-style", "A", "--test-run", *extra], text=True, capture_output=True)

    def test_the_recorded_proof_passes_validate_handoff(self):
        done = self.write_intake("--approved-price", "97:USD", "--checkout-attestation-json", str(self.attest))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        handoff = json.loads((self.run / "intake.json").read_text(encoding="utf-8"))["funnel_handoff"]
        self.assertEqual(handoff["approved_price"], {"amount": "97", "currency": "USD"})
        self.assertEqual(handoff["checkout_attestation"], self.ATTEST)
        (self.run / "copy").mkdir()
        (self.run / "responsive-html").mkdir()
        (self.run / "copy" / "copy-manifest.json").write_text(json.dumps({"ctas": [
            {"label": "Claim Your Seat", "handoff_type": "external_link", "primary": True}]}), encoding="utf-8")
        (self.run / "responsive-html" / "index.html").write_text(
            f'<html><body><a class="cta" href="{self.URL}">Claim Your Seat</a></body></html>', encoding="utf-8")
        proc = subprocess.run([sys.executable, str(SCRIPTS / "validate_handoff.py"), str(self.run)],
                              text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_a_malformed_amount_or_empty_currency_is_refused(self):
        for bad in ("abc:USD", "-5:USD", "97:", "97", "0:USD"):
            self.assertEqual(self.write_intake("--approved-price", bad).returncode, 2, bad)
        self.assertEqual(self.write_intake("--approved-bump", "19:USD").returncode, 2)


class KieReceiptBindingGateTests(unittest.TestCase):
    """CARRIED 117: stage_gate._kie74_problems re-checks the transport binding of each receipt."""

    REL = "visual-mockup/part-01.png"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        (self.run / "visual-mockup").mkdir()
        (self.run / self.REL).write_bytes(b"\x89PNG\r\n\x1a\nbytes-1")
        self.gate = importlib.import_module("stage_gate")
        self.task = [{"task_id": "abc123", "file": self.REL}]
        self.result = {"provider": "kie", "adapter": "74-kie-live-adapter", "adapter_mode": "active",
                       "backend": "native-live", "model_id": "gpt-image-x", "task_id": "abc123", "state": "success",
                       "result_urls": ["https://example.invalid/a.png"], "saved_paths": [str(self.run / self.REL)],
                       "fallback_used": False, "warnings": [], "data": {}}
        (self.run / "intake.json").write_text("{}", encoding="utf-8")

    def problems(self):
        return self.gate._kie74_problems(self.run, "image-generation-qc", self.task)

    def test_a_receipt_written_by_the_executors_writer_passes(self):
        self.gate._kie74_receipt_module().write_bound_receipt(self.run, self.result, self.REL, 1000, 996)
        self.assertEqual(self.problems(), [])

    def test_a_png_that_no_longer_hashes_to_its_binding_is_refused(self):
        self.gate._kie74_receipt_module().write_bound_receipt(self.run, self.result, self.REL, 1000, 996)
        (self.run / self.REL).write_bytes(b"swapped")
        self.assertTrue(self.problems())

    def test_a_hand_made_receipt_has_no_transport_unless_the_run_is_a_test_run(self):
        (self.run / "receipts" / "kie74").mkdir(parents=True)
        (self.run / "receipts" / "kie74" / "abc123.json").write_text(json.dumps(self.result), encoding="utf-8")
        self.assertIn("has no transport binding", " ".join(self.problems()))
        (self.run / "intake.json").write_text('{"test_run": true}', encoding="utf-8")
        self.assertEqual(self.problems(), [])


if __name__ == "__main__":
    unittest.main()
