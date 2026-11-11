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
  * CHK-13 source stamp: a manuscript is accepted only when it carries `source_request_sha256` equal to the
    sha256 of the staged --checkout-request (the request Skill 79's emitter wrote it from); an unstamped,
    wrongly stamped or request-less run is refused;
  * CHK-13 money in the launch record's own currency and exponent (EUR, JPY), never an assumed USD: a
    foreign currency mark or a wrong amount is refused by name;
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
        # the staged Skill 79 checkout request every manuscript below is written "from" (CHK-13 source stamp)
        self.checkout_request_path = self.td / "checkout-request.json"
        self.checkout_request_path.write_text(json.dumps({"main_offer_id": "TEST-ONLY"}), encoding="utf-8")

    def stamped(self, text, request=None):
        """The manuscript text with the source stamp Skill 79's emitter writes (sha256 of the request file)."""
        digest = hashlib.sha256(Path(request or self.checkout_request_path).read_bytes()).hexdigest()
        return f"<!-- source_request_sha256: {digest} -->\n\n" + text

    def stamped_copy(self, manuscript):
        """A stamped copy of a manuscript file; a missing file is passed through (the run refuses it by name)."""
        manuscript = Path(manuscript)
        if not manuscript.is_file():
            return manuscript
        out = self.td / ("stamped-" + manuscript.name)
        out.write_text(self.stamped(manuscript.read_text(encoding="utf-8")), encoding="utf-8")
        return out

    def wrap(self, request_path=None, manuscript=MANUSCRIPT, extra=(), stamp=True):
        manuscript = self.stamped_copy(manuscript) if stamp else manuscript
        cmd = [sys.executable, str(WRAPPER), "--request", str(request_path or self.request_path),
               "--result", str(self.result_path), "--manuscript", str(manuscript),
               "--launch", str(self.launch_path), "--route-graph", str(self.graph_path),
               "--brand-file", str(self.brand_path), "--brand-owner", "blackceo",
               "--image-cap", "2", "--run-dir", str(self.run_dir), "--model", "STUB-NO-MODEL",
               "--checkout-request", str(self.checkout_request_path), *extra]
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
        self.assertTrue(any(b.startswith("REVIEW-PENDING") for b in result["blockers"]))  # issue 30
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


class TestReview(CheckoutWrapperCase):
    """Issue 30: --review turns REVIEW-PENDING into a recorded independent review, or leaves it pending."""

    def review_run(self, **over):
        """Run the wrapper in-process over fixed artifacts (a real re-run rewrites the stage-executor
        records' timestamps), then again with --review."""
        art = self.td / "design.txt"
        art.write_text("fixed design bytes", encoding="utf-8")
        made = {"artifacts": [{"path": str(art), "sha256": hashlib.sha256(art.read_bytes()).hexdigest()}],
                "blockers": ["the native checkout form is installed by Skill 06"]}
        record = {"schema": "signature-launch-review-record/v1", "reviewer_session": "TEST-REVIEWER",
                  "reviewer_model": "m", "verdict": "PASS", "request_id": self.request["request_id"],
                  "reviewed_artifacts": list(made["artifacts"])}
        record.update(over)
        (self.td / "review.json").write_text(json.dumps(record), encoding="utf-8")
        (self.td / "dispatch-session-registry.json").write_text(
            json.dumps({"sessions": [{"session_id": "TEST-REVIEWER", "model": "m"}]}), encoding="utf-8")
        argv = ["--request", str(self.request_path), "--result", str(self.result_path),
                "--manuscript", str(MANUSCRIPT), "--launch", str(self.launch_path),
                "--route-graph", str(self.graph_path), "--brand-file", str(self.brand_path),
                "--brand-owner", "blackceo", "--image-cap", "2", "--run-dir", str(self.run_dir),
                "--review", str(self.td / "review.json")]
        with mock.patch.object(cw, "produce", return_value=made), mock.patch("sys.stdout"):
            self.assertEqual(cw.main(argv), 0)
        return json.loads(self.result_path.read_text(encoding="utf-8"))

    def test_a_passing_review_record_is_recorded(self):
        result = self.review_run()
        self.assertTrue(result["independent_review"], result["blockers"])
        self.assertEqual(result["reviewer_session"], "TEST-REVIEWER")
        self.assertFalse(any(b.startswith("REVIEW-PENDING") for b in result["blockers"]))

    def test_a_record_for_other_bytes_stays_pending_naming_the_artifact_path(self):
        result = self.review_run(reviewed_artifacts=[{"path": "design.txt", "sha256": "0" * 64}])
        self.assertFalse(result["independent_review"])
        self.assertEqual(result["status"], "authored")
        self.assertTrue(any(b.startswith("REVIEW-PENDING") and "was not listed as reviewed" in b
                            and "design.txt" in b for b in result["blockers"]), result["blockers"])

    def test_a_failing_review_record_stays_pending(self):
        result = self.review_run(verdict="FAIL")
        self.assertFalse(result["independent_review"])
        self.assertIsNone(result["reviewer_session"])
        self.assertTrue(any(b.startswith("REVIEW-PENDING") and "verdict" in b for b in result["blockers"]))


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


class TestSourceStamp(CheckoutWrapperCase):
    """CHK-13 source stamp (issue 12): the copy provably comes from the staged Skill 79 checkout request."""

    def refused(self, proc, text):
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn(text, proc.stderr)
        self.assertFalse(self.result_path.exists())

    def test_an_unstamped_hand_written_manuscript_is_refused(self):
        self.refused(self.wrap(stamp=False), "source_request_sha256")

    def test_a_stamp_for_another_request_is_refused(self):
        other = self.td / "other-request.json"
        other.write_text(json.dumps({"main_offer_id": "SOMETHING-ELSE"}), encoding="utf-8")
        wrong = self.td / "wrong.md"
        wrong.write_text(self.stamped(MANUSCRIPT.read_text(encoding="utf-8"), request=other), encoding="utf-8")
        self.refused(self.wrap(manuscript=wrong, stamp=False), "not the staged checkout request's sha256")

    def test_a_request_edited_after_the_copy_was_written_is_refused(self):
        stamped = self.stamped_copy(MANUSCRIPT)
        self.checkout_request_path.write_text(json.dumps({"main_offer_id": "EDITED"}), encoding="utf-8")
        self.refused(self.wrap(manuscript=stamped, stamp=False), "not the staged checkout request's sha256")

    def test_two_stamps_are_refused(self):
        text = self.stamped(self.stamped(MANUSCRIPT.read_text(encoding="utf-8")))
        double = self.td / "double.md"
        double.write_text(text, encoding="utf-8")
        self.refused(self.wrap(manuscript=double, stamp=False), "no single `source_request_sha256`")

    def test_a_run_with_no_checkout_request_is_refused(self):
        cmd = [sys.executable, str(WRAPPER), "--request", str(self.request_path), "--result", str(self.result_path),
               "--manuscript", str(self.stamped_copy(MANUSCRIPT)), "--launch", str(self.launch_path),
               "--route-graph", str(self.graph_path), "--brand-file", str(self.brand_path),
               "--brand-owner", "blackceo", "--image-cap", "2", "--run-dir", str(self.run_dir)]
        self.refused(subprocess.run(cmd, capture_output=True, text=True, timeout=600), "--checkout-request")


class TestSourceStampNeedsARealRequestFile(CheckoutWrapperCase):
    def test_a_request_path_that_is_not_a_file_is_a_named_refusal_not_a_crash(self):
        text = self.stamped("x")
        for missing in (None, self.td / "nowhere.json", self.td):
            with self.subTest(path=str(missing)), self.assertRaises(cw.WrapperError):
                cw.check_source_stamp(text, missing)


class TestCopyInTheLaunchRecordsCurrency(CheckoutWrapperCase):
    """CHK-13 / issue 90: money is read in the launch record's own currency and exponent, not as dollars."""

    def relaunch(self, currency):
        launch = json.loads(self.launch_path.read_text(encoding="utf-8"))
        for offer in launch["offers"]:
            for price in offer["prices"]:
                price["currency"] = currency
        return launch

    def check(self, text, launch):
        cw.check_copy(text, launch, self.request, TERMS)

    def test_a_euro_launch_is_checked_against_euro_copy(self):
        launch = self.relaunch("EUR")
        text = MANUSCRIPT.read_text(encoding="utf-8").replace("$97", "€97.00").replace("$27", "27,00 €")
        self.check(text, launch)  # does not raise: both marks, both decimal styles, the record's amounts

    def test_a_euro_launch_with_dollar_copy_is_refused_as_the_wrong_currency(self):
        launch = self.relaunch("EUR")
        with self.assertRaises(cw.WrapperError) as ctx:
            self.check(MANUSCRIPT.read_text(encoding="utf-8"), launch)  # the fixture copy prints $97
        self.assertIn("currency must match the launch record's currency (EUR)", str(ctx.exception))

    def test_a_euro_price_that_differs_from_the_record_is_refused(self):
        launch = self.relaunch("EUR")
        text = MANUSCRIPT.read_text(encoding="utf-8").replace("$97", "€97.00").replace("$27", "€17.00")
        with self.assertRaises(cw.WrapperError) as ctx:
            self.check(text, launch)
        self.assertIn("EUR 17.00", str(ctx.exception))

    def test_a_zero_decimal_currency_uses_its_own_exponent(self):
        launch = self.relaunch("JPY")  # amount_minor 9700 and 2700 ARE yen: yen has no minor unit
        text = MANUSCRIPT.read_text(encoding="utf-8").replace("$97", "¥9,700").replace("$27", "¥2,700")
        self.check(text, launch)
        with self.assertRaises(cw.WrapperError):
            self.check(text.replace("¥9,700", "¥97"), launch)

    def test_a_three_decimal_currency_uses_its_own_exponent(self):
        launch = self.relaunch("KWD")  # the exponent is 3: 1234567 minor units are 1234.567 dinars
        for offer in launch["offers"]:
            for price in offer["prices"]:
                price["amount_minor"] = 1234567
        text = MANUSCRIPT.read_text(encoding="utf-8").replace("$97", "KWD 1234.567").replace("$27", "KWD 1234.567")
        self.check(text, launch)
        with self.assertRaises(cw.WrapperError):
            self.check(text.replace("KWD 1234.567", "KWD 1234.56"), launch)  # two decimals is not a dinar amount

    THREE_DECIMAL = ("KWD", "BHD", "OMR", "JOD", "TND")

    def priced(self, currency, minor, shown):
        """A launch record priced at `minor` and the fixture copy printing `shown` for both offers."""
        launch = self.relaunch(currency)
        for offer in launch["offers"]:
            for price in offer["prices"]:
                price["amount_minor"] = minor
        text = MANUSCRIPT.read_text(encoding="utf-8").replace("$97", shown).replace("$27", shown)
        return text, launch

    def test_a_dot_and_three_digits_is_the_decimal_point_in_a_three_decimal_currency(self):
        for cur in self.THREE_DECIMAL:
            with self.subTest(cur=cur):
                text, launch = self.priced(cur, 9700, f"{cur} 9.700")
                self.check(text, launch)  # 9.700 is nine dinars seven hundred fils: 9700 minor units
                text, launch = self.priced(cur, 9700000, f"{cur} 9.700")
                with self.assertRaises(cw.WrapperError) as ctx:
                    self.check(text, launch)  # a record price of 9,700 is not what 9.700 prints
                self.assertIn(f"{cur} 9.700", str(ctx.exception))
                text, launch = self.priced(cur, 9700000, f"9,700 {cur}")
                self.check(text, launch)  # a comma stays the thousands separator: 9,700 is nine thousand seven hundred

    def test_the_dot_decimal_reads_after_comma_groups_and_before_the_mark(self):
        text, launch = self.priced("KWD", 1234567, "1,234.567 KWD")
        self.check(text, launch)
        text, launch = self.priced("KWD", 1234567000, "KWD 1,234,567")
        self.check(text, launch)
        text, launch = self.priced("KWD", 1234567, "KWD 1.234")
        with self.assertRaises(cw.WrapperError):
            self.check(text, launch)  # 1.234 is 1234 minor units, not the 1234567 on record

    def test_an_ambiguous_european_grouping_is_refused_by_name(self):
        for shown, digits in (("KWD 1.234.567", "1.234.567"), ("KWD 1.234,567", "1.234,567"),
                              ("1.234.567,891 KWD", "1.234.567,891"), ("KWD 1,234.567.890", "1,234.567.890")):
            with self.subTest(shown=shown):
                text, launch = self.priced("KWD", 1234567, shown)
                with self.assertRaises(cw.WrapperError) as ctx:
                    self.check(text, launch)
                self.assertIn(f"{digits!r} KWD", str(ctx.exception))
                self.assertIn("ambiguous European grouping", str(ctx.exception))
                self.assertIn("reword the copy", str(ctx.exception))

    def test_every_amount_in_a_section_is_read_and_checked(self):
        self.assertEqual(cw._minor_amounts("KWD 9.700, 1,234.567 KWD and KWD 5", "KWD", 3), {9700, 1234567, 5000})
        with self.assertRaises(cw.WrapperError):
            cw._minor_amounts("KWD 9.700 now, or KWD 1.234.567 later", "KWD", 3)

    def test_the_dot_rule_is_only_for_three_decimal_currencies(self):
        text, launch = self.priced("EUR", 970000, "€9.700")
        self.check(text, launch)  # two decimals: 9.700 is still grouped, 9,700.00
        text, launch = self.priced("JPY", 9700, "¥9.700")
        self.check(text, launch)  # no decimals: 9.700 is still grouped, 9700 yen
        text, launch = self.priced("EUR", 970, "€9.700")
        with self.assertRaises(cw.WrapperError):
            self.check(text, launch)

    def test_an_offer_with_no_price_in_the_record_cannot_be_checked_against(self):
        launch = self.relaunch("USD")
        for price in launch["offers"][0]["prices"]:
            price.pop("amount_minor", None)
        with self.assertRaises(cw.WrapperError) as ctx:
            self.check(MANUSCRIPT.read_text(encoding="utf-8"), launch)
        self.assertIn("has no price in the launch record", str(ctx.exception))

    def test_without_the_shared_mapper_the_money_cannot_be_read(self):
        with mock.patch.object(cw, "_OFFER_MAPPER", self.td / "absent.py"), mock.patch.dict(sys.modules):
            sys.modules.pop("offer_mapper", None)
            with self.assertRaises(cw.WrapperError) as ctx:
                cw._offer_mapper()
        self.assertIn("not installed", str(ctx.exception))

    def test_an_iso_code_prints_the_currency_too(self):
        launch = self.relaunch("EUR")
        text = MANUSCRIPT.read_text(encoding="utf-8").replace("$97", "EUR 97.00").replace("$27", "27.00 EUR")
        self.check(text, launch)

    def test_a_currency_that_is_not_an_iso_code_is_refused(self):
        for bad in ("usd", None):
            with self.subTest(currency=bad), self.assertRaises(cw.WrapperError) as ctx:
                self.check(MANUSCRIPT.read_text(encoding="utf-8"), self.relaunch(bad))
            self.assertIn("one currency", str(ctx.exception))

    def test_the_record_must_name_one_currency(self):
        launch = self.relaunch("USD")
        launch["offers"][1]["prices"][0]["currency"] = "EUR"
        with self.assertRaises(cw.WrapperError) as ctx:
            self.check(MANUSCRIPT.read_text(encoding="utf-8"), launch)
        self.assertIn("one currency", str(ctx.exception))

    def test_no_usd_literal_decides_the_check(self):
        source = (HERE / "checkout_wrapper.py").read_text(encoding="utf-8")
        body = source.split("def check_copy", 1)[1].split("def check_source_stamp", 1)[0]
        self.assertNotIn('"USD"', body)
        self.assertNotIn('"USD"', source)  # the whole wrapper: the symbol table is data, not a literal here
        self.assertIn("USD", cw.SYMBOL_CURRENCIES["$"])  # and the data still carries the dollar family


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
        manuscript.write_text(self.stamped(text), encoding="utf-8")
        args = type("A", (), dict(
            manuscript=str(manuscript), launch=str(self.launch_path), skill71_root=str(s71), run_dir=str(self.run_dir),
            request=str(self.request_path), brand_owner="b", image_cap="2", brand_file="f", route_graph="g",
            design_style=None, slots=None, design_prose=None, model=None, provider="stub", allow_paid=False,
            inputs=None, checkout_terms=str(self.terms_path),
            checkout_request=str(self.checkout_request_path)))()
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
                "<staged Skill 79 checkout request>": self.checkout_request_path,
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
        self.assertIn("--checkout-request", cmd)
        (self.td / "copy-checkout.md").write_text(self.stamped(MANUSCRIPT.read_text(encoding="utf-8")),
                                                  encoding="utf-8")
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
