"""Issue 12: the order form's copy manuscript has a producer, and it is stamped with the request it came from.

The emitter writes the five-section manuscript from the approved checkout_request, the launch record and the
approved checkout_terms, and puts `<!-- source_request_sha256: <sha256 of the request file> -->` on line 1.
These tests run it against the real consumers on both sides: Skill 49's CHK-13 (checkout_wrapper.check_copy) and
Skill 71's manuscript parser, so a manuscript the emitter writes is one they accept.
"""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve()
SKILL_ROOT = HERE.parents[1]
REPO = HERE.parents[2]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(REPO / "49-signature-funnel" / "scripts"))
sys.path.insert(0, str(REPO / "71-blackceo-signature-page" / "scripts"))

import checkout_wrapper as chk13  # noqa: E402  (Skill 49: the CHK-13 gate this manuscript must pass)
import emit_checkout_manuscript as emitter  # noqa: E402
import validate_checkout  # noqa: E402
from emit_checkout_manuscript import ManuscriptError, ManuscriptStampError, emit, verify_source_stamp  # noqa: E402
from test_checkout_schema_state_and_tier import valid_request  # noqa: E402
from test_validate_checkout_production import BASE, NOW  # noqa: E402
from validate_copy_structure import parse_manuscript  # noqa: E402  (Skill 71)

SCRIPT = SKILL_ROOT / "scripts" / "emit_checkout_manuscript.py"
TERMS = {"guarantee_ref": "g", "guarantee_text": "Try it for 30 days. If it is not right for you, ask for your money "
                                                 "back and we will refund your order.",
         "terms_ref": "t", "terms_text": "By placing this order you agree to the terms of sale and the privacy policy.",
         "consent_ref": "c", "consent_text": "I agree to the terms of sale."}
LAUNCH = {"offers": [
    {"offer_id": "M", "slot": "main", "display_name": "Monthly Planning Studio",
     "deliverables": ["A guided weekly planning session", "A printable planner"],
     "exclusions": ["One-to-one coaching"], "intended_buyer": "Busy founders who want a calm plan",
     "primary_outcome": "A plan for the week ahead",
     "prices": [{"price_choice_id": "p", "currency": "USD", "amount_minor": 9700, "billing_type": "one_time"}]},
    {"offer_id": "B", "slot": "bump", "display_name": "Quick-Start Template Pack", "deliverables": ["Ten templates"],
     "exclusions": [], "prices": [{"price_choice_id": "bp", "currency": "USD", "amount_minor": 2700,
                                   "billing_type": "one_time"}]}]}


class Staged:
    """A request, launch record and terms block written to a temp dir, as the wrapper stages them."""

    def __init__(self, request=None, launch=None, terms=None):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.request = self.put("request.json", request if request is not None else copy.deepcopy(BASE))
        self.launch = self.put("launch.json", launch if launch is not None else copy.deepcopy(LAUNCH))
        self.terms = self.put("checkout-terms.json", terms if terms is not None else dict(TERMS))

    def put(self, name, doc):
        path = self.dir / name
        path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        return path

    def emit(self, **kw):
        return emit(self.request, self.launch, self.terms, now=NOW, **kw)


def staged(test, **kw):
    s = Staged(**kw)
    test.addCleanup(s.tmp.cleanup)
    return s


def refused(test, code, **kw):
    s = staged(test, **kw)
    with test.assertRaises(ManuscriptError) as ctx:
        s.emit()
    test.assertEqual(ctx.exception.code, code, str(ctx.exception))
    return s


class Emit(unittest.TestCase):
    def test_writes_the_five_sections_with_the_stamp_on_line_one(self):
        s = staged(self)
        made = s.emit()
        first = made["text"].splitlines()[0]
        self.assertEqual(first, f"<!-- source_request_sha256: {hashlib.sha256(s.request.read_bytes()).hexdigest()} -->")
        self.assertEqual(made["sections"], [1, 2, 3, 4, 5])
        for n, name in ((1, "Offer or selected package"), (2, "Offer details and price"), (3, "Order bump"),
                        (4, "Guarantee and terms"), (5, "Secure checkout")):
            self.assertIn(f"\n## Section {n}: {name}\n", made["text"])
        self.assertIn("Monthly Planning Studio, one payment of $97.00.", made["text"])
        self.assertIn("Due today: $97.00.", made["text"])
        self.assertIn("Yes, add the Quick-Start Template Pack to my order.", made["text"])
        self.assertIn("Price: one payment of $27.00.", made["text"])
        self.assertIn("[CTA BUTTON: Complete my order]", made["text"])

    def test_section_names_come_from_the_71_role_spec(self):
        spec = json.loads(emitter.ROLE_SPEC.read_text())
        self.assertEqual(emitter._role_sections(), {int(sec["id"]): sec["name"] for sec in spec["sections"]})

    def test_section_one_ends_in_closing_punctuation_so_skill_71_does_not_read_it_as_cut_off(self):
        """The launch record writes deliverables and exclusions as bare phrases; Skill 71's stage executor
        refuses section copy whose last character is not terminal punctuation (stage_executor.TERMINAL)."""
        launch = copy.deepcopy(LAUNCH)
        launch["offers"][0]["exclusions"] = []
        text = staged(self, launch=launch).emit()["text"]
        section_one = text.split("## Section 1")[1].split("## Section 2")[0].rstrip()
        self.assertTrue(section_one.endswith(emitter.TERMINAL), section_one[-40:])
        self.assertIn("- A guided weekly planning session.", text)
        self.assertIn("- A printable planner.", text)

    def test_a_bullet_that_already_ends_in_punctuation_is_not_doubled(self):
        launch = copy.deepcopy(LAUNCH)
        launch["offers"][0]["deliverables"] = ["Weekly sessions!", "A planner (printable)"]
        text = staged(self, launch=launch).emit()["text"]
        self.assertIn("- Weekly sessions!\n", text)
        self.assertIn("- A planner (printable)\n", text)
        self.assertNotIn("!.", text)

    def test_no_bump_means_sections_1_2_4_5(self):
        for bump in (None, dict(BASE["bump"], enabled=False)):
            with self.subTest(bump=bump):
                request = copy.deepcopy(BASE)
                request["bump"] = bump
                s = staged(self, request=request)
                made = s.emit()
                self.assertEqual(made["sections"], [1, 2, 4, 5])
                self.assertNotIn("## Section 3", made["text"])

    def test_the_text_passes_skill_49_chk13_and_71_parsing(self):
        s = staged(self)
        text = s.emit()["text"]
        chk13.check_copy(text, LAUNCH, {}, dict(TERMS))  # raises WrapperError on any CHK-13 breach
        self.assertEqual(chk13.card_field_hits(text), [])
        units, order, _ = parse_manuscript(text)
        self.assertEqual(order, ["1", "2", "3", "4", "5"])
        self.assertEqual([u.text for u in units if u.kind == "cta_button"], ["Complete my order"])
        self.assertNotIn("source_request_sha256", " ".join(u.text for u in units))  # the stamp is a comment, never copy

    def test_no_bump_text_passes_chk13_for_a_launch_without_a_bump(self):
        request = copy.deepcopy(BASE)
        request["bump"] = None
        launch = {"offers": [LAUNCH["offers"][0]]}
        text = staged(self, request=request, launch=launch).emit()["text"]
        chk13.check_copy(text, launch, {}, dict(TERMS))
        self.assertEqual(parse_manuscript(text)[1], ["1", "2", "4", "5"])

    def test_a_trial_price_says_nothing_is_charged_today_and_prints_no_zero(self):
        request = copy.deepcopy(BASE)
        request["main_price"].update(billing_type="trial_then_recurring", recurring_interval="month", trial_period="7 days")
        text = staged(self, request=request).emit()["text"]
        self.assertIn("recurring basis after your trial (billing interval: month, trial period: 7 days)", text)
        self.assertIn("Nothing is charged today.", text)
        self.assertNotIn("$0", text)

    def test_a_recurring_price_is_printed_per_interval_for_every_cadence(self):
        for interval in ("week", "month", "quarter", "year"):
            request = copy.deepcopy(BASE)
            request["main_price"].update(billing_type="recurring", recurring_interval=interval)
            text = staged(self, request=request).emit()["text"]
            self.assertIn(f"/{interval} on a recurring basis (billing interval: {interval})", text)

    def test_schedule_rows_and_due_today_are_printed_from_the_price(self):
        request = copy.deepcopy(BASE)
        request["main_price"].update(
            amount_due_now_minor=4850,
            schedule=[{"sequence": 1, "due": "in 30 days", "amount_minor": 4850}])
        text = staged(self, request=request).emit()["text"]
        self.assertIn("Payment 1, in 30 days: $48.50.", text)
        self.assertIn("Due today: $48.50.", text)

    def test_money_uses_the_currency_exponent_and_grouping(self):
        self.assertEqual(emitter._money(149700, "USD", 2), "$1,497.00")
        self.assertEqual(emitter._money(9850, "JPY", 0), "JPY 9,850")
        self.assertEqual(emitter._money(12400, "KWD", 3), "KWD 12.400")

    def test_post_selection_mode_prints_the_package_summary_not_the_explanation(self):
        request = copy.deepcopy(BASE)
        request.update(checkout_mode="post_selection", selection_ref="sel", selection_revision=1)
        text = staged(self, request=request).emit()["text"]
        self.assertIn("Your selected package: Monthly Planning Studio.", text)
        self.assertIn("Change package", text)
        self.assertNotIn("What is included:", text)

    def test_what_the_record_cannot_supply_is_reported_never_invented(self):
        notes = staged(self).emit()["notes"]
        self.assertTrue(any("access and delivery" in n for n in notes), notes)


class Refusals(unittest.TestCase):
    def test_an_unapproved_request_is_not_turned_into_copy(self):
        request = copy.deepcopy(BASE)
        request["main_price"]["approval_status"] = "test_only"
        refused(self, "S79-MANUSCRIPT-REQUEST-INVALID", request=request)

    def test_a_recommended_price_needs_the_verified_plan_approval(self):
        request = copy.deepcopy(BASE)
        request["main_price"]["approval_status"] = "recommended_unapproved"
        s = refused(self, "S79-MANUSCRIPT-REQUEST-INVALID", request=request)
        ok = lambda ref, kind, plan_hash, scope, **kw: {  # noqa: E731
            "ok": True, "kind": kind, "approval_id": ref, "authority": "command-center"}
        with mock.patch.object(validate_checkout, "_shared_verify", return_value=ok):
            self.assertEqual(s.emit()["sections"], [1, 2, 3, 4, 5])

    def test_terms_that_belong_to_another_approval_are_refused(self):
        for key in ("terms_ref", "consent_ref"):
            refused(self, "S79-MANUSCRIPT-TERMS", terms=dict(TERMS, **{key: "other"}))

    def test_blank_or_missing_approved_text_is_refused(self):
        for key in ("guarantee_text", "terms_text", "consent_text", "guarantee_ref"):
            refused(self, "S79-MANUSCRIPT-TERMS", terms=dict(TERMS, **{key: "  "}))
        missing = dict(TERMS)
        del missing["consent_text"]
        refused(self, "S79-MANUSCRIPT-TERMS", terms=missing)

    def test_the_terms_block_may_sit_inside_a_document(self):
        self.assertEqual(staged(self, terms={"checkout_terms": dict(TERMS)}).emit()["sections"], [1, 2, 3, 4, 5])

    def test_an_offer_the_record_does_not_name_is_never_invented(self):
        refused(self, "S79-MANUSCRIPT-FACT-MISSING", launch={"offers": [LAUNCH["offers"][1]]})
        nameless = copy.deepcopy(LAUNCH)
        nameless["offers"][0]["display_name"] = " "
        refused(self, "S79-MANUSCRIPT-FACT-MISSING", launch=nameless)

    def test_a_bump_the_record_does_not_name_is_refused(self):
        refused(self, "S79-MANUSCRIPT-FACT-MISSING", launch={"offers": [LAUNCH["offers"][0]]})

    def test_an_offer_with_no_deliverables_is_refused_in_combined_mode(self):
        bare = copy.deepcopy(LAUNCH)
        bare["offers"][0]["deliverables"] = []
        refused(self, "S79-MANUSCRIPT-FACT-MISSING", launch=bare)

    def test_unreadable_inputs_are_refused_by_name(self):
        with self.assertRaises(ManuscriptError) as ctx:
            emit("/nonexistent/request.json", "/nonexistent/launch.json", "/nonexistent/terms.json", now=NOW)
        self.assertEqual(ctx.exception.code, "S79-MANUSCRIPT-INPUT")


class SourceStamp(unittest.TestCase):
    def test_the_stamp_holds_for_the_request_it_was_written_from(self):
        s = staged(self)
        text = s.emit()["text"]
        self.assertEqual(verify_source_stamp(text, s.request), hashlib.sha256(s.request.read_bytes()).hexdigest())

    def test_a_changed_request_is_a_mismatch(self):
        s = staged(self)
        text = s.emit()["text"]
        s.put("request.json", dict(BASE, quantity=2))  # same path, other bytes
        with self.assertRaises(ManuscriptStampError) as ctx:
            verify_source_stamp(text, s.request)
        self.assertEqual(ctx.exception.code, "S79-MANUSCRIPT-STAMP-MISMATCH")

    def test_a_re_serialised_but_equal_request_is_still_a_mismatch(self):
        # The stamp binds the raw bytes of the staged file, exactly what the wrapper hashes.
        s = staged(self)
        text = s.emit()["text"]
        s.request.write_text(json.dumps(json.loads(s.request.read_text()), separators=(",", ":")), encoding="utf-8")
        with self.assertRaises(ManuscriptStampError) as ctx:
            verify_source_stamp(text, s.request)
        self.assertEqual(ctx.exception.code, "S79-MANUSCRIPT-STAMP-MISMATCH")

    def test_a_missing_or_malformed_stamp_is_refused(self):
        s = staged(self)
        text = s.emit()["text"]
        good = text.splitlines()[0]
        digest = good.split()[2]
        bad = {
            "no stamp": text.split("\n", 1)[1],
            "not on line one": "# Order form page\n" + text,
            "upper-case hex": text.replace(digest, digest.upper(), 1),
            "short hex": text.replace(digest, digest[:-1], 1),
            "other label": text.replace("source_request_sha256", "request_sha256", 1),
            "leading space": " " + text,
            "empty": "",
        }
        for name, manuscript in bad.items():
            with self.subTest(name), self.assertRaises(ManuscriptStampError) as ctx:
                verify_source_stamp(manuscript, s.request)
            self.assertEqual(ctx.exception.code, "S79-MANUSCRIPT-STAMP-MISSING")


class CommandLine(unittest.TestCase):
    """The shell path, on a test_only request (no Command Center read)."""

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True)

    def staged_test_only(self):
        request = valid_request()
        launch = {"offers": [
            {"offer_id": "MAIN-A", "slot": "main", "display_name": "Main A", "deliverables": ["One thing"],
             "exclusions": [], "prices": []},
            {"offer_id": "BUMP", "slot": "bump", "display_name": "The Bump", "deliverables": ["Another"],
             "exclusions": [], "prices": []}]}
        terms = dict(TERMS, terms_ref="TEST-TERMS", consent_ref="TEST-CONSENT")
        return staged(self, request=request, launch=launch, terms=terms)

    def test_writes_the_manuscript_and_check_confirms_the_stamp(self):
        s = self.staged_test_only()
        out = s.dir / "copy-checkout.md"
        done = self.run_cli("--request", s.request, "--launch", s.launch, "--checkout-terms", s.terms, "--out", out)
        self.assertEqual(done.returncode, 0, done.stderr)
        summary = json.loads(done.stdout)
        self.assertEqual(summary["sections"], [1, 2, 3, 4, 5])
        self.assertTrue(out.read_text().startswith("<!-- source_request_sha256: "))
        self.assertEqual(self.run_cli("--check", out, "--request", s.request).returncode, 0)

    def test_check_refuses_after_the_request_changes(self):
        s = self.staged_test_only()
        out = s.dir / "copy-checkout.md"
        self.run_cli("--request", s.request, "--launch", s.launch, "--checkout-terms", s.terms, "--out", out)
        s.put("request.json", dict(valid_request(), quantity=3))
        done = self.run_cli("--check", out, "--request", s.request)
        self.assertEqual(done.returncode, 2)
        self.assertIn("S79-MANUSCRIPT-STAMP-MISMATCH", done.stderr)

    def test_a_refusal_writes_nothing(self):
        s = self.staged_test_only()
        out = s.dir / "copy-checkout.md"
        s.put("checkout-terms.json", dict(TERMS, terms_ref="not-the-requests"))
        done = self.run_cli("--request", s.request, "--launch", s.launch, "--checkout-terms", s.terms, "--out", out)
        self.assertEqual(done.returncode, 2)
        self.assertIn("S79-MANUSCRIPT-TERMS", done.stderr)
        self.assertFalse(out.exists())

    def test_missing_arguments_are_a_usage_error(self):
        s = self.staged_test_only()
        self.assertEqual(self.run_cli("--request", s.request).returncode, 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
