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
