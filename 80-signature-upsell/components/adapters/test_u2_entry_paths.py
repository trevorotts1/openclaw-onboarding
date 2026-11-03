"""U-upsell-03 - U2 entry paths, U1/D1 exclusion, product names, scarcity facts.

UPS-04 a journey with both U1 and D1 records is refused (rc 2 at the CLI).
UPS-05 a launch with U1 and D1 enabled gives a U2 bundle with BOTH
       conditional bands, declared as mutually exclusive runtime variants.
UPS-06 acknowledgement text comes from the offer / journey, never from code.
UPS-09 scarcity wording needs a matching fact in the approved launch record.

Run: python3 -m pytest 80-signature-upsell/components/adapters/test_u2_entry_paths.py -q
"""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent / "80-signature-upsell"
FIXTURES = HERE / "fixtures"
sys.path.insert(0, str(HERE))

import adapter_common as common
import upsell1_adapter
import upsell2_adapter

U2_COPY = SKILL_DIR / "fixtures" / "copy-upsell2-public.valid.json"
U1_COPY = SKILL_DIR / "fixtures" / "copy-upsell1-public.valid.json"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def u2_inputs():
    return (
        load(FIXTURES / "request-upsell2-from-upsell1.testonly.json"),
        load(U2_COPY),
        load(FIXTURES / "journey-upsell2-from-upsell1.testonly.json"),
    )


def both_records_journey():
    journey = load(FIXTURES / "journey-upsell2-from-upsell1.testonly.json")
    journey["verified_purchases"].append(
        {"evidence_ref": "TEST-ONLY-d1-ledger-entry", "offer_display_name": "TEST ONLY Lite Start Pass",
         "slot": "downsell_1", "verification_source": "s44_event_adapter"})
    return journey


def launch_record(u1=True, d1=True, facts=None):
    record = {
        "extras": {"upsell_1": u1, "downsell_1": d1, "upsell_2": True},
        "offers": [
            {"slot": "upsell_1", "display_name": "TEST ONLY Deep Work Library"},
            {"slot": "downsell_1", "display_name": "TEST ONLY Lite Start Pass"},
            {"slot": "upsell_2", "display_name": "TEST ONLY Implementation Studio"},
        ],
    }
    if facts is not None:
        record["scarcity_facts"] = facts
    return record


def build_u2(request, copy_doc, journey, launch=None):
    return upsell2_adapter.build_bundle(
        request, copy_doc, journey, copy_sha256="0" * 64,
        copy_artifact_path="copy-u2.json", launch=launch)


def run_cli(instance, request, copy_doc, journey, launch=None):
    """produce.py through the CLI; returns (returncode, stderr, out_exists)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        args = [sys.executable, str(HERE / "produce.py"), "--instance", instance]
        for name, doc in (("request", request), ("copy", copy_doc), ("journey", journey)):
            (tmp / (name + ".json")).write_text(json.dumps(doc), encoding="utf-8")
            args += ["--" + name, str(tmp / (name + ".json"))]
        if launch is not None:
            (tmp / "launch.json").write_text(json.dumps(launch), encoding="utf-8")
            args += ["--launch", str(tmp / "launch.json")]
        args += ["--out", str(tmp / "bundle.json")]
        proc = subprocess.run(args, capture_output=True, text=True)
        return proc.returncode, proc.stderr, (tmp / "bundle.json").exists()


class MutualExclusionTests(unittest.TestCase):
    def test_u2_cli_refuses_journey_with_both_records_naming_the_exclusion(self):
        request, copy_doc, _ = u2_inputs()
        rc, err, wrote = run_cli("upsell_2", request, copy_doc, both_records_journey())
        self.assertEqual(rc, 2)
        self.assertIn("mutually exclusive", err)
        self.assertFalse(wrote)

    def test_u1_cli_refuses_journey_with_both_records(self):
        request = load(SKILL_DIR / "fixtures" / "request-upsell1.testonly.json")
        rc, err, wrote = run_cli("upsell_1", request, load(U1_COPY), both_records_journey())
        self.assertEqual(rc, 2)
        self.assertIn("mutually exclusive", err)
        self.assertFalse(wrote)

    def test_eligibility_check_names_the_exclusion(self):
        request, _, _ = u2_inputs()
        check = upsell2_adapter.check_u2_eligibility(request, both_records_journey())
        self.assertFalse(check["verified"])
        self.assertTrue(any("mutually exclusive" in p for p in check["problems"]))

    def test_single_record_journeys_still_build(self):
        request, copy_doc, journey = u2_inputs()
        self.assertEqual(build_u2(request, copy_doc, journey)["result"]["status"], "authored")


class BothEntryPathsTests(unittest.TestCase):
    def test_both_enabled_emits_both_mutually_exclusive_bands(self):
        request, copy_doc, journey = u2_inputs()
        plan = build_u2(request, copy_doc, journey, launch_record())["page_plan"]
        conditions = [b["condition"] for b in plan["acknowledgement_blocks"]]
        self.assertIn("from_upsell_1", conditions)
        self.assertIn("from_downsell_1", conditions)
        strip = plan["acknowledgement_strip"]
        self.assertEqual(strip["mode"], "runtime_conditional_mutually_exclusive")
        self.assertEqual(strip["variants"], ["from_upsell_1", "from_downsell_1"])
        self.assertTrue(strip["design_shows_all_variants"])

    def test_d1_band_never_claims_the_u1_package_and_names_come_from_launch(self):
        request, copy_doc, journey = u2_inputs()  # journey proves U1 only
        blocks = {b["condition"]: b["text"] for b in
                  build_u2(request, copy_doc, journey, launch_record())["page_plan"]["acknowledgement_blocks"]}
        self.assertIn("TEST ONLY Lite Start Pass", blocks["from_downsell_1"])  # launch offer name
        self.assertNotIn("first upgrade is confirmed", blocks["from_downsell_1"])
        self.assertIn("TEST ONLY Deep Work Library", blocks["from_upsell_1"])  # journey name
        self.assertNotIn("downsell choice", blocks["from_upsell_1"])

    def test_only_u1_enabled_emits_one_band_and_no_strip(self):
        request, copy_doc, journey = u2_inputs()
        plan = build_u2(request, copy_doc, journey, launch_record(d1=False))["page_plan"]
        self.assertEqual([b["condition"] for b in plan["acknowledgement_blocks"]],
                         ["verified_original_purchase", "from_upsell_1"])
        self.assertNotIn("acknowledgement_strip", plan)

    def test_qualifying_slot_the_launch_did_not_enable_is_blocked(self):
        request, copy_doc, journey = u2_inputs()
        bundle = build_u2(request, copy_doc, journey, launch_record(u1=False))
        self.assertEqual(bundle["result"]["status"], "blocked")
        self.assertIn("not enabled in the launch record", " ".join(bundle["result"]["blockers"]))

    def test_without_a_launch_record_the_staged_journey_decides_alone(self):
        request, copy_doc, journey = u2_inputs()
        plan = build_u2(request, copy_doc, journey)["page_plan"]
        self.assertEqual([b["condition"] for b in plan["acknowledgement_blocks"]],
                         ["verified_original_purchase", "from_upsell_1"])


class ProductNameTests(unittest.TestCase):
    def test_no_hardcoded_product_or_category_wording_in_code(self):
        for name in ("upsell1_adapter.py", "upsell2_adapter.py", "produce.py"):
            text = (HERE / name).read_text(encoding="utf-8")
            self.assertNotIn("Implementation" + " Studio", text, name)
            self.assertNotIn("content" + " upgrade", text, name)

    def test_zeta_pack_name_flows_from_the_offer(self):
        request, copy_doc, journey = u2_inputs()
        request["offer"]["display_name"] = "Zeta Pack"
        for launch in (None, launch_record()):
            text = " ".join(b["text"] for b in
                            build_u2(request, copy_doc, journey, launch)["page_plan"]["acknowledgement_blocks"])
            self.assertIn("Zeta Pack", text)
            self.assertNotIn("Implementation Studio", text)


class ScarcityFactTests(unittest.TestCase):
    PHRASE = "Last chance: this offer ends Friday."
    FACT = {"family": "time_bound", "fact": "Promotion ends Friday 18:00",
            "source_ref": "ledger:promotion.ends_at"}

    def scarce_copy(self):
        copy_doc = copy.deepcopy(load(U2_COPY))
        copy_doc["sections"][0]["body"] += " " + self.PHRASE
        # The author's own evidence entry must not clear anything.
        copy_doc["verified_scarcity_evidence"] = [
            {"fact": "ends Friday", "source_ref": "ledger:author-says-so-1"}]
        return copy_doc

    def test_scarcity_wording_without_a_launch_fact_is_refused_rc_2(self):
        request, _, journey = u2_inputs()
        copy_doc = self.scarce_copy()
        with self.assertRaises(common.AdapterError):
            build_u2(request, copy_doc, journey, launch_record(facts=[]))
        rc, err, wrote = run_cli("upsell_2", request, copy_doc, journey, launch_record())
        self.assertEqual(rc, 2)
        self.assertIn("scarcity", err)
        self.assertFalse(wrote)

    def test_scarcity_wording_with_a_matching_launch_fact_builds(self):
        request, _, journey = u2_inputs()
        request["factual_scarcity_evidence"] = [
            {"fact": self.FACT["fact"], "source_ref": self.FACT["source_ref"]}]
        bundle = build_u2(request, self.scarce_copy(), journey, launch_record(facts=[self.FACT]))
        self.assertEqual(bundle["result"]["status"], "authored")

    def test_a_fact_of_another_family_does_not_clear_the_wording(self):
        request, _, journey = u2_inputs()
        other = dict(self.FACT, family="availability")
        with self.assertRaises(common.AdapterError):
            build_u2(request, self.scarce_copy(), journey, launch_record(facts=[other]))

    def test_evidence_not_in_the_launch_record_is_refused(self):
        request, copy_doc, journey = u2_inputs()
        request["factual_scarcity_evidence"] = [
            {"fact": "ends Friday", "source_ref": "ledger:author-says-so-1"}]
        with self.assertRaises(common.AdapterError):
            build_u2(request, copy_doc, journey, launch_record(facts=[self.FACT]))

    def test_u1_applies_the_same_gate(self):
        request = load(SKILL_DIR / "fixtures" / "request-upsell1.testonly.json")
        copy_doc = copy.deepcopy(load(U1_COPY))
        copy_doc["sections"][0]["body"] += " " + self.PHRASE
        journey = load(FIXTURES / "journey-main-only.testonly.json")
        with self.assertRaises(common.AdapterError):
            upsell1_adapter.build_bundle(request, copy_doc, journey, copy_sha256="0" * 64,
                                         copy_artifact_path="copy-u1.json")

    def test_clean_copy_needs_no_launch_fact(self):
        request, copy_doc, journey = u2_inputs()
        self.assertEqual(build_u2(request, copy_doc, journey, launch_record())["result"]["status"],
                         "authored")


if __name__ == "__main__":
    unittest.main()
