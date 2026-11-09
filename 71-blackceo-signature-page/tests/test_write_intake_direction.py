#!/usr/bin/env python3
"""U-images-07: the prompt-policy registry is self-consistent, and write_intake carries
creative direction, design-style source and palette status (IMG-07/08/09/20).

Free: no network, no model, no paid call.
Run: python3 -m pytest 71-blackceo-signature-page/tests/test_write_intake_direction.py -q
"""
import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
DOMAIN = REPO / "shared-utils" / "signature_launch" / "domain"
FIX = REPO / "shared-utils" / "client_intake" / "fixtures"
sys.path.insert(0, str(ROOT / "scripts"))
import brand_colors as bc  # noqa: E402

try:
    import jsonschema
except ImportError:  # the schema check is skipped, everything else still runs
    jsonschema = None

REGISTRY = json.loads((DOMAIN / "prompt-policy-registry.json").read_text(encoding="utf-8"))


def entry_hash(entry):
    body = {k: v for k, v in entry.items() if k != "entry_hash"}
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def receipts_module():
    path = REPO / "49-signature-funnel" / "scripts" / "collect_launch_receipts.py"
    spec = importlib.util.spec_from_file_location("collect_launch_receipts_u07", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class RegistryIsConsistent(unittest.TestCase):
    def active(self):
        return [e for e in REGISTRY["entries"] if e["entry_status"] == "active"]

    def test_exactly_one_active_entry_and_ids_are_distinct(self):
        ids = [e["policy_id"] for e in REGISTRY["entries"]]
        self.assertEqual(len(ids), len(set(ids)), f"two entries share a policy_id: {ids}")
        self.assertEqual(len(self.active()), 1)

    def test_the_active_entry_supersedes_a_different_existing_entry(self):
        (act,) = self.active()
        self.assertNotEqual(act["supersedes"], act["policy_id"], "an entry cannot supersede itself")
        superseded = {e["policy_id"] for e in REGISTRY["entries"] if e["entry_status"] == "superseded"}
        self.assertIn(act["supersedes"], superseded)

    def test_percentage_band_parameters_match_the_95_100_statement(self):
        # IMG-20 proof: parameters must be consistent with length_basis percentage_band
        for e in self.active():
            doctrine = e["doctrine"]
            par = doctrine["parameters"]
            self.assertEqual(doctrine["length_basis"], "percentage_band")
            self.assertEqual(par["floor_percent_of_max"], 80)
            self.assertEqual(par["target_percent_of_max"], 95)
            for fixed in ("floor_chars", "preferred_min_chars", "preferred_max_chars"):
                self.assertIsNone(par[fixed], f"{fixed} is a fixed-band number on a percentage_band entry")
            self.assertIn("95 to 100 percent", doctrine["statement"])
            self.assertIn("floor 80 percent", doctrine["statement"])

    def test_active_entry_hash_matches_its_content(self):
        for e in self.active():
            self.assertEqual(e["entry_hash"], entry_hash(e))

    def test_receipt_finder_resolves_every_id_to_its_own_entry(self):
        finder = receipts_module().find_registry_entry
        for e in REGISTRY["entries"]:
            self.assertIs(finder(REGISTRY, e["policy_id"]), e)

    @unittest.skipUnless(jsonschema, "jsonschema not installed")
    def test_registry_validates_against_its_format_schema(self):
        schema = json.loads((DOMAIN / "prompt-policy-registry.schema.json").read_text(encoding="utf-8"))
        jsonschema.validate(REGISTRY, schema)


def run(*args):
    return subprocess.run([sys.executable, str(ROOT / "scripts" / args[0]), *map(str, args[1:])],
                          capture_output=True, text=True)


@unittest.skipUnless(FIX.is_dir(), "shared-utils/client_intake fixtures not in this checkout")
class WriteIntakeRecordsDirection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tmp.name) / "run"
        self.run_dir.mkdir()
        self.scratch = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def answers(self, name, **changes):
        doc = json.loads((FIX / name).read_text(encoding="utf-8"))
        for key, entry in changes.items():
            if entry is None:
                doc["answers"].pop(key, None)
            else:
                doc["answers"][key] = entry
        path = self.scratch / f"{name}.edited.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        return path

    def intake_json(self):
        return json.loads((self.run_dir / "intake.json").read_text(encoding="utf-8"))

    def write(self, answers, *extra):
        return run("write_intake.py", self.run_dir, "--answers-file", answers, "--page-kind", "sales", *extra)

    def test_creative_direction_flag_is_recorded_with_its_source(self):
        r = self.write(FIX / "answers.elevation.json", "--creative-direction", "Editorial, like Kinfolk")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        intake = self.intake_json()
        self.assertEqual(intake["creative_direction"], "Editorial, like Kinfolk")
        self.assertEqual(intake["creative_direction_source"], "client_choice")

    def test_creative_direction_answer_fills_the_flag_and_the_house_look_is_explicit(self):
        direction = {"value": "Warm film grain, 1970s kitchen", "status": "provided", "source": "client"}
        r = self.write(self.answers("answers.elevation.json", creative_direction=direction))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        intake = self.intake_json()
        self.assertEqual((intake["creative_direction"], intake["creative_direction_source"]),
                         ("Warm film grain, 1970s kitchen", "client_choice"))
        house = {"value": {"mode": "house_look"}, "status": "provided", "source": "client"}
        r = self.write(self.answers("answers.elevation.json", creative_direction=house))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        intake = self.intake_json()
        self.assertIsNone(intake["creative_direction"])
        self.assertEqual(intake["creative_direction_source"], "house_look_accepted")

    def test_no_direction_asked_is_recorded_as_not_asked(self):
        r = self.write(FIX / "answers.elevation.json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        intake = self.intake_json()
        self.assertIsNone(intake["creative_direction"])
        self.assertEqual(intake["creative_direction_source"], "not_asked")

    def test_provided_style_is_client_choice_and_a_source_flag_is_recorded(self):
        r = self.write(FIX / "answers.elevation.json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.intake_json()["design_style_source"], "client_choice")
        r = run("write_intake.py", self.run_dir, "--page-version", "standard", "--brand-owner", "Fixture",
                "--image-cap", "1", "--design-style", "A", "--design-style-source", "recommended_accepted")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.intake_json()["design_style_source"], "recommended_accepted")

    def test_default_style_is_refused_on_a_production_run_and_recorded_on_a_test_run(self):
        base = ("--page-version", "standard", "--brand-owner", "Fixture", "--image-cap", "1",
                "--design-style", "A", "--design-style-source", "default_to_confirm")
        r = run("write_intake.py", self.run_dir, *base)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("REFUSED", r.stdout)
        self.assertIn("NEXT (operator, role: intake)", r.stdout)
        self.assertFalse((self.run_dir / "intake.json").exists())
        r = run("write_intake.py", self.run_dir, *base, "--test-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.intake_json()["design_style_source"], "default_to_confirm")

    def test_an_answers_file_default_style_is_never_stamped_client_choice(self):
        style = {"value": "A", "status": "default_to_confirm", "source": "default"}
        answers = self.answers("answers.elevation.json", design_style=style)
        r = self.write(answers)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertFalse((self.run_dir / "intake.json").exists())
        r = self.write(answers, "--test-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        intake = self.intake_json()
        self.assertEqual((intake["design_style_source"], intake["design_style_status"]),
                         ("default_to_confirm", "default_to_confirm"))

    def test_palette_status_is_carried_into_the_intake(self):
        self.assertEqual(self.write(FIX / "answers.elevation.json").returncode, 0)
        self.assertEqual(self.intake_json()["palette_status"], "provided")
        self.assertEqual(self.write(FIX / "answers.7fig.json").returncode, 0)
        self.assertEqual(self.intake_json()["palette_status"], "default_to_confirm")

    def test_a_proposal_palette_refuses_the_paid_stages_on_a_production_run_only(self):
        self.assertEqual(self.write(FIX / "answers.7fig.json").returncode, 0)
        self.assertIsNone(bc.failure(self.run_dir, "desktop-wireframe"), "internal design work may use a proposal")
        for stage in bc.PAID_IMAGE_STAGES:
            self.assertIn("only a proposal", bc.failure(self.run_dir, stage))
        intake = self.intake_json()
        intake["test_run"] = True
        (self.run_dir / "intake.json").write_text(json.dumps(intake), encoding="utf-8")
        self.assertIsNone(bc.failure(self.run_dir, "final-mockups"))

    def test_a_confirmed_palette_does_not_refuse_the_paid_stages(self):
        self.assertEqual(self.write(FIX / "answers.elevation.json").returncode, 0)
        self.assertIsNone(bc.failure(self.run_dir, "final-mockups"))


class SkillTextCarriesNoModelId(unittest.TestCase):
    def test_skill_md_names_no_image_model_id(self):
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8").lower()
        for banned in ("gpt-image", "sunburst"):
            self.assertNotIn(banned, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
