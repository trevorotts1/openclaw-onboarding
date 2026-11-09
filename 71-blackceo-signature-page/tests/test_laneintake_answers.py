#!/usr/bin/env python3
"""Lane intake: the one client answers file feeds Skill 71 intake and the brand file.

Free: no network, no model, no paid call. The fixtures come from shared-utils/client_intake.
Run: python3 71-blackceo-signature-page/tests/test_laneintake_answers.py
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
FIX = REPO / "shared-utils" / "client_intake" / "fixtures"
sys.path.insert(0, str(ROOT / "scripts"))
import brand_colors as bc  # noqa: E402

try:
    import jsonschema
except ImportError:  # the schema check is skipped, everything else still runs
    jsonschema = None

SCHEMA = json.loads((ROOT / "assets/brand/brand.schema.json").read_text())
PY = sys.executable


def run(*args):
    return subprocess.run([PY, str(ROOT / "scripts" / args[0]), *map(str, args[1:])], capture_output=True, text=True)


def doc(name):
    return json.loads((FIX / name).read_text())


@unittest.skipUnless(FIX.is_dir(), "shared-utils/client_intake fixtures not in this checkout")
class AnswersFeedSkill71(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def intake(self, name, *extra):
        r = run("write_intake.py", self.run_dir, "--answers-file", FIX / name, "--page-kind", "sales", *extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r, json.loads((self.run_dir / "intake.json").read_text())

    def brand(self):
        return json.loads((self.run_dir / "brand" / "client-brand.json").read_text())

    def test_client_given_colors_make_a_valid_brand_file_without_to_confirm_for_colors(self):
        r, intake = self.intake("answers.elevation.json")
        self.assertEqual(intake["brand_owner"], "Elevation Coaching Co")
        self.assertEqual((intake["image_cap"], intake["design_style"], intake["page_version"]), (12, "B", "standard"))
        self.assertEqual(intake["design_style_source"], "client_choice")
        brand = self.brand()
        if jsonschema:
            jsonschema.validate(brand, SCHEMA)
        self.assertEqual(brand["palette_status"], "provided")
        self.assertEqual(brand["palette_roles"]["primary"], "#0A7E8C")
        self.assertEqual(brand["palette_roles"]["secondary"], "#102A43")
        self.assertEqual((brand["palette"]["gold"], brand["palette"]["navy"], brand["palette"]["cream"]), ("#0A7E8C", "#1B2A33", "#FFFFFF"))
        self.assertEqual(brand["fonts"], {"display": "Playfair Display", "body": "Source Sans 3", "accent": "Playfair Display"})
        self.assertEqual(brand["logo"]["wordmark_text"], "Elevation Coaching Co")
        self.assertTrue(brand["photos"]["empty_frame"])
        self.assertEqual(brand["photos"]["likeness_generation"], "never")
        res = bc.resolve(self.run_dir)
        self.assertTrue(res.ok)
        self.assertEqual(res.status, "provided")
        out = run("brand_colors.py", "check", self.run_dir).stdout
        self.assertNotIn("TO CONFIRM", out)
        self.assertIn("primary #0A7E8C", out)

    def test_defaulted_palette_passes_check_and_says_to_confirm(self):
        r, intake = self.intake("answers.7fig.json")
        brand = self.brand()
        if jsonschema:
            jsonschema.validate(brand, SCHEMA)
        self.assertEqual(brand["palette_status"], "default_to_confirm")
        self.assertEqual(brand["fonts_status"], "default_to_confirm")
        self.assertEqual(brand["fonts"]["display"], "CLIENT_MUST_SUPPLY")  # the derive-document policy still decides the fonts
        self.assertIn("display", brand["fonts_suggested"])
        self.assertEqual(brand["logo"]["status"], "default_to_confirm")
        self.assertEqual(brand["photos"]["permission"], "yes")
        self.assertTrue(brand["photos"]["empty_frame"], "no photo file was supplied, so the frame stays empty")
        self.assertEqual(intake["design_style"], "C")
        self.assertEqual({t["id"] for t in intake["to_confirm"]} >= {"brand_colors", "fonts", "logo"}, True)
        self.assertIn("TO CONFIRM brand_colors", r.stdout)
        check = run("brand_colors.py", "check", self.run_dir)
        self.assertEqual(check.returncode, 0, check.stdout)
        self.assertIn("TO CONFIRM", check.stdout)

    def test_default_palette_is_never_another_clients(self):
        self.intake("answers.7fig.json")
        palette = {v.upper() for v in self.brand()["palette"].values()}
        blackceo = json.loads((ROOT / "assets/brand/blackceo-brand.json").read_text())["palette"]
        self.assertFalse(palette & {v.upper() for v in blackceo.values()})
        # and the file belongs to this client only: BlackCEO's own pages do not resolve it
        intake = json.loads((self.run_dir / "intake.json").read_text())
        intake["brand_owner"] = "someone else"
        (self.run_dir / "intake.json").write_text(json.dumps(intake))
        self.assertFalse(bc.resolve(self.run_dir).ok)

    def test_no_colors_and_no_default_still_blocks_with_the_primary_ask(self):
        d = doc("answers.elevation.json")
        for k in [k for k in d["answers"] if k.startswith("brand_")]:
            del d["answers"][k]
        f = self.run_dir / "partial.json"
        f.write_text(json.dumps(d))
        r = run("write_intake.py", self.run_dir, "--answers-file", f, "--page-kind", "sales")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("NOTE brand colors", r.stdout)
        check = run("brand_colors.py", "check", self.run_dir)
        self.assertEqual(check.returncode, 1)
        self.assertIn("BRAND_COLORS_MISSING", check.stdout)
        self.assertIn("MAIN (primary) color", check.stdout)

    def test_a_flag_on_the_command_line_beats_the_answers_file(self):
        _, intake = self.intake("answers.elevation.json", "--image-cap", "6", "--design-style", "A")
        self.assertEqual((intake["image_cap"], intake["design_style"]), (6, "A"))

    def test_documented_answers_command_fills_both_copy_selectors(self):
        # Finding 17: INTAKE.md documents `write_intake.py RUN --answers-file A`
        # with no --copy-version; the copy stage reads copy_version, so a run
        # that records only page_version cannot close copy.
        r = run("write_intake.py", self.run_dir, "--answers-file", FIX / "answers.elevation.json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        intake = json.loads((self.run_dir / "intake.json").read_text())
        self.assertEqual((intake["page_version"], intake["copy_version"]), ("standard", "standard"))

    def test_page_kind_is_collected_before_the_length(self):
        # Finding 17: an answers file that records the page kind imports it,
        # and the length is read against that kind.
        d = doc("answers.7fig.json")  # copy_profile long_form, provided
        d["answers"]["page_kind"] = {"value": "opt_in", "status": "provided", "source": "client"}
        f = self.run_dir / "kind.json"
        f.write_text(json.dumps(d))
        r = run("write_intake.py", self.run_dir, "--answers-file", f)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        intake = json.loads((self.run_dir / "intake.json").read_text())
        self.assertEqual((intake["page_kind"], intake["page_version"], intake["copy_version"]),
                         ("opt_in", "long-form", "long-form"))

    def test_a_recorded_kind_refuses_a_length_it_cannot_use_with_a_recovery_action(self):
        d = doc("answers.elevation.json")  # copy_profile standard, provided
        d["answers"]["page_kind"] = {"value": "opt_in", "status": "provided", "source": "client"}
        f = self.run_dir / "kind-standard.json"
        f.write_text(json.dumps(d))
        r = run("write_intake.py", self.run_dir, "--answers-file", f)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("REFUSED", r.stdout)
        self.assertIn("NEXT (operator, role:", r.stdout)
        self.assertIn("long-form", r.stdout)
        self.assertFalse((self.run_dir / "intake.json").exists())

    def two_registers(self, r):
        """The refusal's two lines: the client-safe REFUSED summary and the
        operator NEXT line on its own line right after it, never fused."""
        lines = r.stdout.splitlines()
        refusals = [i for i, l in enumerate(lines) if l.startswith("REFUSED:")]
        self.assertEqual(len(refusals), 1, r.stdout)
        summary = lines[refusals[0]]
        self.assertNotIn("NEXT", summary, r.stdout)
        self.assertTrue(lines[refusals[0] + 1].startswith("NEXT (operator"), r.stdout)
        return summary, lines[refusals[0] + 1]

    def test_a_credential_refusal_names_the_operator_recovery_and_no_internals(self):
        # Finding 24: the operator gets the exact recovery action and role; the
        # summary is plain. Provisioning topology and tier backstops never print.
        r = run("write_intake.py", self.run_dir, "--page-version", "standard",
                "--brand-owner", "Fixture", "--image-cap", "1",
                "--publish-target", "ghl", "--automation-scope", "workflows",
                "--ghl-pit-absent", "--ghl-location-absent")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        summary, nxt = self.two_registers(r)
        self.assertIn("NEXT (operator, role: account access)", nxt)
        self.assertIn("GHL_PRIVATE_INTEGRATION_TOKEN", nxt)
        self.assertNotIn("GHL_PRIVATE_INTEGRATION_TOKEN", summary)
        for internal in ("fleet-contabo", "per-container", "Tier 4", "publish_target"):
            self.assertNotIn(internal, r.stdout)
        r = run("write_intake.py", self.run_dir, "--page-version", "standard",
                "--brand-owner", "Fixture", "--image-cap", "1",
                "--publish-target", "ghl", "--automation-scope", "workflows",
                "--ghl-pit-present", "--ghl-location-present", "--ghl-firebase-absent")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        summary, nxt = self.two_registers(r)
        self.assertIn("firebase-choice", nxt)
        self.assertIn("NEXT (operator, role: account access)", nxt)
        for internal in ("fleet-contabo", "per-container", "Tier 4", "publish_target"):
            self.assertNotIn(internal, r.stdout)

    def test_a_page_kind_answer_that_is_no_kind_is_refused_by_name(self):
        # The import refuses an unrecordable kind cleanly - by name, with the
        # operator action - and never with a traceback.
        for bad in ("webinar", 42):
            d = doc("answers.elevation.json")
            d["answers"]["page_kind"] = {"value": bad, "status": "provided", "source": "client"}
            f = self.run_dir / "bad-kind.json"
            f.write_text(json.dumps(d))
            r = run("write_intake.py", self.run_dir, "--answers-file", f)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertNotIn("Traceback", r.stderr)
            summary, nxt = self.two_registers(r)
            self.assertIn("sales", summary)
            self.assertIn("opt_in", summary)
            self.assertIn("NEXT (operator, role: intake)", nxt)
            self.assertFalse((self.run_dir / "intake.json").exists())

    def test_neither_copy_selector_refuses_with_the_operator_action(self):
        r = run("write_intake.py", self.run_dir, "--brand-owner", "Fixture", "--image-cap", "1")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        summary, nxt = self.two_registers(r)
        self.assertIn("NEXT (operator, role: intake)", nxt)
        self.assertIn("--page-version", nxt)
        self.assertFalse((self.run_dir / "intake.json").exists())

    def test_one_selector_on_the_command_line_fills_the_other_and_beats_the_answers_file(self):
        # One copy selection, two selectors (finding 17): whichever selector the
        # command line names fills the other, and a flag always wins over the
        # answers file's copy_profile.
        r = run("write_intake.py", self.run_dir, "--brand-owner", "Fixture",
                "--image-cap", "1", "--copy-version", "long-form")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        intake = json.loads((self.run_dir / "intake.json").read_text())
        self.assertEqual((intake["page_version"], intake["copy_version"]), ("long-form", "long-form"))
        (self.run_dir / "intake.json").unlink()
        r = run("write_intake.py", self.run_dir, "--answers-file", FIX / "answers.elevation.json",
                "--page-version", "long-form")  # the answers file records copy_profile standard
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        intake = json.loads((self.run_dir / "intake.json").read_text())
        self.assertEqual((intake["page_version"], intake["copy_version"]), ("long-form", "long-form"))

    def test_a_page_type_run_keeps_its_own_form_over_the_answers_file_and_records_no_kind(self):
        # The answers file feeds this run too; its copy_profile and page_kind
        # are the signature page's decisions, and a page type's own form is
        # both its page_version and its copy_version (SPF030: the page type
        # has no kind, so the kind is never recorded on it).
        d = doc("answers.elevation.json")
        d["answers"]["page_kind"] = {"value": "sales", "status": "provided", "source": "client"}
        f = self.run_dir / "answers-thankyou.json"
        f.write_text(json.dumps(d))
        r = run("write_intake.py", self.run_dir, "--answers-file", f, "--page-version", "thank-you")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        intake = json.loads((self.run_dir / "intake.json").read_text())
        self.assertEqual((intake["page_role"], intake["page_version"], intake["copy_version"]),
                         ("thank_you", "thank-you", "thank-you"))
        self.assertNotIn("page_kind", intake)
        self.assertIn("NOTE page_kind", r.stdout)

    def test_answers_file_of_another_schema_is_refused(self):
        f = self.run_dir / "bad.json"
        f.write_text(json.dumps({"schema": "nope"}))
        r = run("write_intake.py", self.run_dir, "--answers-file", f, "--page-kind", "sales")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not a client-intake-answers/v1 file", r.stdout)

    def test_without_the_answers_file_the_flags_are_still_required(self):
        r = run("write_intake.py", self.run_dir, "--page-version", "standard")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--brand-owner", r.stderr)

    def test_founder_photos_supplied_are_recorded_only_with_permission(self):
        photo = self.run_dir / "me.png"
        photo.write_bytes(b"x")
        self.intake("answers.7fig.json")
        bc.record_from_answers(self.run_dir, FIX / "answers.7fig.json", [str(photo)])
        brand = self.brand()
        self.assertEqual(brand["founder_photos"], [str(photo)])
        self.assertFalse(brand["photos"]["empty_frame"])
        d = doc("answers.7fig.json")
        d["answers"]["photos_permission"]["value"] = "no"
        f = self.run_dir / "noperm.json"
        f.write_text(json.dumps(d))
        bc.record_from_answers(self.run_dir, f, [str(photo)])
        self.assertEqual(self.brand()["founder_photos"], "CLIENT_MUST_SUPPLY")


class SchemaAndTemplate(unittest.TestCase):
    @unittest.skipUnless(jsonschema, "jsonschema not installed")
    def test_bundled_brand_and_template_still_validate(self):
        for rel in ("assets/brand/blackceo-brand.json", "assets/brand/client-brand.template.json"):
            jsonschema.validate(json.loads((ROOT / rel).read_text()), SCHEMA)

    @unittest.skipUnless(jsonschema, "jsonschema not installed")
    def test_a_status_without_its_companions_is_refused(self):
        brand = json.loads((ROOT / "assets/brand/blackceo-brand.json").read_text())
        brand["palette_status"] = "provided"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(brand, SCHEMA)

    def test_the_ask_names_the_primary_color(self):
        self.assertIn("MAIN (primary) color", bc.ASK)
        self.assertIn("help me", bc.ASK)


if __name__ == "__main__":
    unittest.main(verbosity=1)
