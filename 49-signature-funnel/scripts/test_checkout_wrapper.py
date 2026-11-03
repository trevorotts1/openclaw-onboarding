#!/usr/bin/env python3
"""checkout_wrapper.py tests: dispatch's checkout request through the REAL Skill 71 pipeline.

Stages S49's own dispatch emission (compile_launch_route, dispatch_launch.build_requests) over the
fixture launch, then runs the wrapper as the checkout adapter command with the stub provider (no
network, no paid call). Proves:
  * the run is admitted through shared_page_service.py and the intake records page_role checkout
    and the client's design style;
  * the three design stages build from the checkout manuscript on the five-section structure and
    produce desktop and mobile wireframes plus desktop and mobile mockups (20 images);
  * the placed page-result validates against collect_launch_receipts.validate_result, is capped at
    authored / L0, has no native binding, and names the native-form and stub blockers;
  * the adapter's own command (launch-adapters.example.json, no --model) runs to a valid result
    once the staged design-prose-checkout.json is in the work dir, and the wrapper refuses without it;
  * fail-closed, with no result left behind: a request for another role, a missing manuscript, a
    manuscript that holds card fields, a section-count mismatch;
  * CHK-13: a price line, bump price or headline, guarantee, terms or consent text that differs from the
    launch record and the approved checkout_terms block is refused, as is a missing block;
  * CHK-14: the card-field guard is parser-based (labels, placeholders, inputs, cc-* autocomplete) on the
    manuscript and on produced HTML, and does not trip on reassurance prose such as "credit card".

Run: python3 test_checkout_wrapper.py [-v]
"""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import checkout_wrapper as cw  # noqa: E402
import compile_launch_route as clr  # noqa: E402
import dispatch_launch as dispatch_mod  # noqa: E402
import collect_launch_receipts as receipts  # noqa: E402
from test_landing_bridge import fixture_launch, dump  # noqa: E402

REPO = HERE.parents[1]
S71 = REPO / "71-blackceo-signature-page"
WRAPPER = HERE / "checkout_wrapper.py"
MANUSCRIPT = S71 / "tests" / "fixtures" / "copy_examples" / "checkout-example.md"
TERMS = {  # the 83 intake's approved checkout_terms block, worded as the fixture manuscript prints it
    "guarantee_ref": "TEST-ONLY-GUARANTEE-REF",
    "guarantee_text": "Try it for 30 days. If it is not right for you, ask for your money back and we will "
                      "refund your order.",
    "terms_ref": "TEST-ONLY-TERMS-REF",
    "terms_text": "By placing this order you agree to the terms of sale and the privacy policy.",
    "consent_ref": "TEST-ONLY-CONSENT-REF",
    "consent_text": "I agree to the terms of sale.",
}
BRAND_RAW = (S71 / "assets" / "brand" / "blackceo-brand.json").read_bytes()


class CheckoutWrapperCase(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="s49-checkout-wrapper-")).resolve()
        self.addCleanup(lambda: shutil.rmtree(self.td, ignore_errors=True))
        launch, _approval = fixture_launch()
        launch["brand_hash"] = hashlib.sha256(BRAND_RAW).hexdigest()
        for offer, name in zip(launch["offers"], ("Monthly Planning Studio", "Quick-Start Template Pack")):
            offer["display_name"] = name  # the fixture manuscript's offer and bump names (prices $97 and $27)
        graph = clr.compile_route(launch)
        launch["route_graph_hash"] = clr.graph_hash(graph)
        requests = {r["page_role"]: r for r in dispatch_mod.build_requests(
            launch, graph, copy_profile="standard", allowed_write_target="local_only")}
        self.request = requests["checkout"]
        self.launch_path = self.td / "launch.json"
        self.launch_path.write_bytes(dump(launch))
        self.terms_path = self.td / "checkout-terms.json"  # staged beside the launch record, as the adapter expects
        self.terms_path.write_text(json.dumps(TERMS), encoding="utf-8")
        self.request_path = self.td / "request-checkout.json"
        self.request_path.write_bytes(dump(self.request))
        self.graph_path = self.td / "route-graph.json"
        self.graph_path.write_bytes(clr.serialize_graph(graph))
        self.brand_path = self.td / "brand-src.json"
        self.brand_path.write_bytes(BRAND_RAW)
        self.result_path = self.td / "result-checkout.json"
        self.run_dir = self.td / "checkout-run"

    def wrap(self, request_path=None, manuscript=MANUSCRIPT, extra=()):
        cmd = [sys.executable, str(WRAPPER), "--request", str(request_path or self.request_path),
               "--result", str(self.result_path), "--manuscript", str(manuscript),
               "--launch", str(self.launch_path), "--route-graph", str(self.graph_path),
               "--brand-file", str(self.brand_path), "--brand-owner", "blackceo",
               "--image-cap", "2", "--run-dir", str(self.run_dir), "--model", "STUB-NO-MODEL", *extra]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=600)


class TestEndToEnd(CheckoutWrapperCase):
    def test_wrapper_builds_the_checkout_design_stages_through_skill_71(self):
        proc = self.wrap(extra=("--design-style", "C"))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = json.loads(self.result_path.read_text(encoding="utf-8"))
        self.assertEqual(receipts.validate_result(result, self.request), [])
        self.assertEqual((result["status"], result["proof_class"]), ("authored", "L0"))
        self.assertIsNone(result["native_bindings_ref"])
        self.assertFalse(result["independent_review"])
        self.assertTrue(any("Skill 06" in b for b in result["blockers"]))
        self.assertTrue(any("stub provider" in b for b in result["blockers"]))
        intake = json.loads((self.run_dir / "intake.json").read_text(encoding="utf-8"))
        self.assertEqual(intake["launch"]["page_role"], "checkout")
        self.assertEqual(intake["design_style"], "C")
        names = [Path(a["path"]).relative_to(self.run_dir).as_posix() for a in result["artifacts"]]
        for stage in ("desktop-wireframe", "mobile-tablet"):
            self.assertEqual(sorted(n for n in names if n.startswith(f"{stage}/section-")),
                             [f"{stage}/section-0{i}.png" for i in range(1, 6)])
        for platform in ("desktop", "mobile"):
            self.assertEqual(sorted(n for n in names if n.startswith(f"visual-mockup/{platform}/")),
                             [f"visual-mockup/{platform}/part-0{i}.png" for i in range(1, 6)])
        for stage in ("desktop-wireframe", "mobile-tablet", "visual-mockup"):
            built = json.loads((self.run_dir / f"production-request-{stage}.json").read_text(encoding="utf-8"))
            self.assertEqual([s["section_id"] for s in built["sections"]], list("12345"))
            self.assertEqual(built["page_role"], "checkout")
        for a in result["artifacts"]:
            self.assertEqual(hashlib.sha256(Path(a["path"]).read_bytes()).hexdigest(), a["sha256"])


class TestFailClosed(CheckoutWrapperCase):
    def refused(self, proc, text):
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn(text, proc.stderr)
        self.assertFalse(self.result_path.exists())

    def test_a_stale_result_is_removed_when_the_run_is_refused(self):
        self.result_path.write_text("{}")
        self.refused(self.wrap(manuscript=self.td / "nope.md"), "manuscript")

    def test_request_for_another_role_is_refused(self):
        other = dict(self.request, page_role="landing", assigned_skill=71)
        path = self.td / "request-landing.json"
        path.write_bytes(dump(other))
        self.refused(self.wrap(request_path=path), "serves 'checkout'")

    def test_manuscript_naming_card_fields_is_refused(self):
        bad = self.td / "bad.md"
        bad.write_text(MANUSCRIPT.read_text(encoding="utf-8").replace(
            "Enter your details below", "Enter your card number and CVC below"), encoding="utf-8")
        self.refused(self.wrap(manuscript=bad), "native checkout form only")

    def test_html_with_a_card_field_in_the_run_is_refused(self):
        (self.run_dir / "visual-mockup").mkdir(parents=True)
        (self.run_dir / "visual-mockup" / "page.html").write_text('<input autocomplete="cc-number">')
        self.refused(self.wrap(), "produced HTML")

    def test_a_landing_shaped_manuscript_fails_the_section_count(self):
        landing = S71 / "tests" / "fixtures" / "copy_examples" / "standard-path-b.md"
        self.refused(self.wrap(manuscript=landing), "5 canonical sections")
        self.assertFalse(any((self.run_dir / "desktop-wireframe").glob("*.png")))


class TestCopyMatchesTheApprovedRecord(CheckoutWrapperCase):
    """CHK-13: sections 2-4 of the manuscript are compared with the launch record and checkout_terms."""

    def edited(self, old, new):
        text = MANUSCRIPT.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path = self.td / "edited.md"
        path.write_text(text.replace(old, new), encoding="utf-8")
        return path

    def refused(self, proc, text):
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn(text, proc.stderr)
        self.assertFalse(self.result_path.exists())

    def test_every_commercial_line_that_differs_from_the_record_is_refused(self):
        cases = (
            ("section 2 price", "one payment of $97.", "one payment of $47.", "section 2"),
            ("section 2 due today", "Due today: $97.", "Due today: $47.", "section 2"),
            ("section 2 offer name", "Monthly Planning Studio, one", "Weekly Planning Studio, one", "section 2"),
            ("bump price", "One-time price of $27.", "One-time price of $17.", "section 3"),
            ("bump headline", "add the Quick-Start Template Pack to", "add the Mega Pack to", "section 3"),
            ("guarantee", "Try it for 30 days.", "Try it for 60 days.", "guarantee"),
            ("terms", "and the privacy policy.", "and the refund policy.", "terms"),
            ("consent", "I agree to the terms of sale.", "I agree to everything.", "consent"),
        )
        for label, old, new, where in cases:
            with self.subTest(label):
                self.refused(self.wrap(manuscript=self.edited(old, new)), where)

    def test_an_extra_unapproved_claim_in_section_4_is_refused(self):
        path = self.edited("I agree to the terms of sale.", "I agree to the terms of sale.\n\nLifetime guarantee.")
        self.refused(self.wrap(manuscript=path), "not in the approved checkout_terms")

    def test_a_missing_checkout_terms_block_is_refused(self):
        self.terms_path.unlink()
        self.refused(self.wrap(), "checkout_terms block")

    def test_the_terms_file_flag_is_checked_like_the_record_block(self):
        terms = self.td / "terms.json"
        terms.write_text(json.dumps(dict(TERMS, guarantee_text="Try it for 90 days.")), encoding="utf-8")
        self.refused(self.wrap(extra=("--checkout-terms", str(terms))), "guarantee")


class TestOrderBumpSectionFollowsTheBump(CheckoutWrapperCase):
    """F5: section 3 (order bump) is required only when the launch record has a bump offer."""

    def setUp(self):
        super().setUp()
        self.text = MANUSCRIPT.read_text(encoding="utf-8")
        self.launch = json.loads(self.launch_path.read_text(encoding="utf-8"))
        self.no_bump_text = "".join(
            part for part in __import__("re").split(r"(?m)^(?=##\s+Section\s+\d+)", self.text)
            if not part.startswith("## Section 3"))
        self.no_bump_launch = dict(self.launch, offers=[o for o in self.launch["offers"] if o.get("slot") != "bump"])
        self.assertNotIn("## Section 3", self.no_bump_text)
        self.assertEqual(sorted(cw.sections(self.no_bump_text)), [1, 2, 4, 5])
        self.assertTrue(any(o.get("slot") == "bump" for o in self.launch["offers"]))

    def test_a_funnel_without_a_bump_needs_no_section_3(self):
        cw.check_copy(self.no_bump_text, self.no_bump_launch, self.request, TERMS)

    def test_a_funnel_with_a_bump_still_needs_section_3(self):
        with self.assertRaises(cw.WrapperError) as ctx:
            cw.check_copy(self.no_bump_text, self.launch, self.request, TERMS)
        self.assertIn("section 3", str(ctx.exception))

    def test_a_missing_section_other_than_3_is_still_refused(self):
        gone = self.no_bump_text.replace("## Section 4", "## Part 4")
        with self.assertRaises(cw.WrapperError) as ctx:
            cw.check_copy(gone, self.no_bump_launch, self.request, TERMS)
        self.assertIn("canonical sections", str(ctx.exception))

    def test_an_unpriced_bump_price_in_a_no_bump_funnel_is_refused(self):
        with self.assertRaises(cw.WrapperError) as ctx:
            cw.check_copy(self.text, self.no_bump_launch, self.request, TERMS)
        self.assertIn("section 3", str(ctx.exception))


class TestProduceTellsSkill71WhetherTheLaunchHasABump(CheckoutWrapperCase):
    """F5 across the seam: the S71 build keeps checkout section 3 unless produce() hands it --no-bump, which it
    must do exactly when the launch has no bump. The S71 scripts here are stand-ins that log argv; the real S71
    build is exercised end to end by TestNoBumpLaunchBuildsThroughTheRealSkill71."""

    class Stop(Exception):
        pass

    def produce_with(self, launch, build_text, text):
        s71 = self.td / "s71"
        (s71 / "scripts").mkdir(parents=True)
        for name in ("shared_page_service.py", "stage_executor.py"):
            (s71 / "scripts" / name).write_text("", encoding="utf-8")
        (s71 / "scripts" / "build_production_request.py").write_text(build_text, encoding="utf-8")
        self.launch_path.write_text(json.dumps(launch), encoding="utf-8")
        manuscript = self.td / "manuscript.md"
        manuscript.write_text(text, encoding="utf-8")
        args = type("A", (), dict(
            manuscript=str(manuscript), launch=str(self.launch_path), skill71_root=str(s71), run_dir=str(self.run_dir),
            request=str(self.request_path), brand_owner="b", image_cap="2", brand_file="f", route_graph="g",
            design_style=None, slots=None, design_prose=None, model=None, provider="stub", allow_paid=False,
            inputs=None, checkout_terms=str(self.terms_path)))()
        seen = []

        def fake_run(cmd, label):
            seen.append([str(c) for c in cmd])
            if "build_production_request.py" in str(cmd[1]):
                raise self.Stop()
        with mock.patch.object(cw, "run", fake_run), mock.patch.object(cw.page_set, "stage_visual_bible"):
            with self.assertRaises(self.Stop):
                cw.produce(args, self.request)
        return next(c for c in seen if "build_production_request.py" in c[1])

    def setUp(self):
        super().setUp()
        self.launch = json.loads(self.launch_path.read_text(encoding="utf-8"))
        self.text = MANUSCRIPT.read_text(encoding="utf-8")
        self.no_bump_text = "".join(
            part for part in __import__("re").split(r"(?m)^(?=##\s+Section\s+\d+)", self.text)
            if not part.startswith("## Section 3"))
        self.no_bump_launch = dict(self.launch, offers=[o for o in self.launch["offers"] if o.get("slot") != "bump"])

    def test_a_no_bump_funnel_is_handed_no_bump(self):
        cmd = self.produce_with(self.no_bump_launch, "", self.no_bump_text)
        self.assertIn("--no-bump", cmd)

    def test_a_funnel_with_a_bump_is_not_handed_no_bump(self):
        cmd = self.produce_with(self.launch, "", self.text)
        self.assertNotIn("--no-bump", cmd)


class TestNoBumpLaunchBuildsThroughTheRealSkill71(CheckoutWrapperCase):
    """F5 end to end, no stand-ins: the real wrapper subprocess against the real Skill 71 in this repo. A launch
    without an order bump builds four checkout sections (1,2,4,5); the with-bump control keeps all five."""

    def built_sections(self):
        return [json.loads((self.run_dir / f"production-request-{stage}.json").read_text(encoding="utf-8"))
                ["sections"] for stage in ("desktop-wireframe", "mobile-tablet", "visual-mockup")]

    def test_a_no_bump_launch_builds_four_sections(self):
        launch = json.loads(self.launch_path.read_text(encoding="utf-8"))
        launch["offers"] = [o for o in launch["offers"] if o.get("slot") != "bump"]
        self.launch_path.write_text(json.dumps(launch), encoding="utf-8")
        manuscript = self.td / "no-bump.md"
        manuscript.write_text("".join(
            part for part in __import__("re").split(r"(?m)^(?=##\s+Section\s+\d+)", MANUSCRIPT.read_text(encoding="utf-8"))
            if not part.startswith("## Section 3")), encoding="utf-8")
        proc = self.wrap(manuscript=manuscript, extra=("--design-style", "C", "--checkout-terms", str(self.terms_path)))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for sections in self.built_sections():
            self.assertEqual([x["section_id"] for x in sections], list("1245"))

    def test_the_with_bump_control_keeps_five_sections(self):
        proc = self.wrap(extra=("--design-style", "C", "--checkout-terms", str(self.terms_path)))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for sections in self.built_sections():
            self.assertEqual([x["section_id"] for x in sections], list("12345"))


class TestCardFieldGuard(unittest.TestCase):
    """CHK-14 (probe4): field-like variants are blocked, reassurance sentences pass."""
    FIELDS = ("Card number", "Card-number:", "cardnumber", "CC number", "Card no.", "Card #", "PAN", "Exp. date",
              "MM/YY", "Expiry (MM / YY)", "Expiration", "Expiration date: ____", "CVC", "CVV", "CSC",
              "Security code", "Name on card", "cc-number", "cc-exp", "**Card Number** *", "- Card\u2011number",
              "[INPUT: Card number]", "Enter your card number and CVC below",
              '<input name="card_number">', '<input autocomplete="cc-csc">', '<input placeholder="MM / YY">',
              '<label for="x">Card number</label>', '<span>CVC</span>',
              "Card\nnumber", "Expiry\ndate", "Security\ncode", 'autocomplete="cc-exp"',
              '[INPUT autocomplete="cc-exp"]', 'Field: autocomplete="cc-number"', "autocomplete=cc-csc")
    PROSE = ("We never store your credit card.", "Your payment is processed securely. You will see a "
             "confirmation right away.", "Your card details are never stored on this page.",
             "Pay securely; your credit card is processed by Stripe", "We never store your\ncredit card details.")

    def test_every_field_like_variant_is_blocked(self):
        for text in self.FIELDS:
            with self.subTest(text):
                self.assertTrue(cw.card_field_hits(text))
                self.assertTrue(cw.card_field_hits(f"## Section 5: x\n\n{text}\n"))

    def test_reassurance_prose_passes(self):
        for text in self.PROSE:
            with self.subTest(text):
                self.assertEqual(cw.card_field_hits(text), [])
                self.assertEqual(cw.card_field_hits(f"## Section 5: x\n\n{text}\n"), [])

    def test_produced_html_is_scanned(self):
        (self.td / "visual-mockup").mkdir()
        (self.td / "visual-mockup" / "page.html").write_text("<p>We never store your credit card.</p>")
        cw.scan_html(self.td)
        (self.td / "visual-mockup" / "form.html").write_text('<form><input autocomplete="cc-number"></form>')
        with self.assertRaises(cw.WrapperError):
            cw.scan_html(self.td)

    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="s49-checkout-guard-")).resolve()
        self.addCleanup(lambda: shutil.rmtree(self.td, ignore_errors=True))


def measured_design_prose(chars=14500):
    """Unique pseudo-sentences standing in for a run's measured design system (the size of a real one)."""
    syl = ["ba", "ke", "lo", "mi", "su", "ta", "ve", "zo", "ri", "na"]
    words = [a + b + c + d for a in syl for b in syl for c in syl for d in syl]
    text, state = [], 7
    while sum(len(t) + 1 for t in text) < chars:
        sentence = []
        for _ in range(12):
            state = (state * 1103515245 + 12345) % 2147483648
            sentence.append(words[state % len(words)])
        text.append(" ".join(sentence) + ".")
    return {"rules_md": "\n".join(text)}


class TestAdapterCommand(CheckoutWrapperCase):
    """Runs the checkout adapter command exactly as launch-adapters.example.json spells it: no --model."""

    def adapter_cmd(self):
        raw = json.loads((HERE.parent / "launch-adapters.example.json").read_text(encoding="utf-8"))
        subs = {"{request}": self.request_path, "{result}": self.result_path, "{work_dir}": self.td,
                "/path/to/49-signature-funnel": HERE.parent, "/path/to/71-blackceo-signature-page": S71,
                "<approved brand file>": self.brand_path, "<recorded brand owner>": "blackceo",
                "<image cap>": "2", "<A|B|C>": "C"}
        cmd = []
        for arg in raw["adapters"]["checkout"]["command"]:
            for key, value in subs.items():
                arg = arg.replace(key, str(value))
            cmd.append(arg)
        self.assertNotIn("--model", cmd)
        self.assertIn("--design-prose", cmd)
        (self.td / "copy-checkout.md").write_text(MANUSCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
        return cmd

    def test_adapter_command_with_staged_design_prose_and_no_model_succeeds(self):
        (self.td / "design-prose-checkout.json").write_text(json.dumps(measured_design_prose()), encoding="utf-8")
        proc = subprocess.run(self.adapter_cmd(), capture_output=True, text=True, timeout=600)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = json.loads(self.result_path.read_text(encoding="utf-8"))
        self.assertEqual(receipts.validate_result(result, self.request), [])
        self.assertEqual(len([a for a in result["artifacts"] if "/visual-mockup/" in a["path"] and a["path"].endswith(".png")]), 10)

    def test_adapter_command_without_the_staged_design_prose_fails_closed(self):
        proc = subprocess.run(self.adapter_cmd(), capture_output=True, text=True, timeout=600)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("design-prose-checkout.json", proc.stderr)
        self.assertFalse(self.result_path.exists())


class TestLegacyCardFieldsExport(unittest.TestCase):
    """legacy_downsell_images.py imports CARD_FIELDS from this module; removing it broke that tool at import."""

    def test_legacy_tool_imports(self):
        import legacy_downsell_images  # noqa: F401

    def test_card_fields_search_flags_fields_only(self):
        for text in ("Card number field.", 'autocomplete="cc-exp"', "Expiry\ndate", "MM/YY"):
            self.assertIsNotNone(cw.CARD_FIELDS.search(text), text)
        self.assertIsNone(cw.CARD_FIELDS.search("Thank you for your order."))


if __name__ == "__main__":
    unittest.main()
