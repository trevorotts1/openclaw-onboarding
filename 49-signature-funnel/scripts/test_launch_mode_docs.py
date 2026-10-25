#!/usr/bin/env python3
"""test_launch_mode_docs.py - proves LAUNCH_MODE.md and prompt-policy-adoption.json
describe the wiring that exists: the launch chain the entry hash-pins, and checkout's
design-only dispatch beside its native-form and prompt-policy exclusions.
Stdlib only, no network. Run: python3 test_launch_mode_docs.py"""
import json
import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
ENTRY = SKILL / "signature-funnel-entry.sh"
LAUNCH_DOC = SKILL / "LAUNCH_MODE.md"
ADOPTION = SKILL / "prompt-policy-adoption.json"
STRUCTURE = SKILL / "structure" / "funnel_structure.json"
PAGE_TYPES = SKILL / "structure" / "page_types.json"
ADAPTERS = SKILL / "launch-adapters.example.json"

# The launch-chain modules the entry pins (read from the shell, never assumed).
LAUNCH_CHAIN = (
    "scripts/dispatch_launch.py",
    "scripts/compile_launch_route.py",
    "scripts/page_set.py",
    "scripts/page_swarm.py",
    "scripts/validate_launch_plan.py",
    "scripts/agnes_dispatch.py",
    "scripts/agnes_gates.py",
    "scripts/agnes_orchestrator.py",
    "scripts/agnes_response.py",
)
ROLES = ("landing", "product_selection", "checkout", "upsell_1",
         "downsell_1", "upsell_2", "thank_you")


def pinned_files():
    text = ENTRY.read_text(encoding="utf-8")
    block = re.search(r"PINNED_FILES=\((.*?)\n\)", text, re.S)
    assert block, "PINNED_FILES array not found in signature-funnel-entry.sh"
    return tuple(re.findall(r'"([^"]+)"', block.group(1)))


class PinnedLaunchChain(unittest.TestCase):
    def test_entry_pins_every_launch_module(self):
        pinned = pinned_files()
        missing = [f for f in LAUNCH_CHAIN if f not in pinned]
        self.assertEqual(missing, [], "launch module not hash-pinned")
        for rel in LAUNCH_CHAIN:
            self.assertTrue((SKILL / rel).is_file(), rel)

    def test_launch_doc_names_the_pinned_chain(self):
        doc = LAUNCH_DOC.read_text(encoding="utf-8")
        self.assertNotIn("no pinned file changed", doc,
                         "LAUNCH_MODE.md still claims launch mode pinned nothing")
        for rel in LAUNCH_CHAIN:
            self.assertIn(Path(rel).name, doc,
                          "LAUNCH_MODE.md does not name %s" % rel)


class CheckoutAdoption(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads(ADOPTION.read_text(encoding="utf-8"))
        self.checkout = self.doc["roles"]["checkout"]

    def test_every_dispatch_role_has_an_entry(self):
        self.assertEqual(self.doc["schema"],
                         "signature-launch-prompt-policy-adoption/v1")
        self.assertEqual(sorted(self.doc["roles"]), sorted(ROLES))

    def test_checkout_stays_out_of_prompt_policy_by_design(self):
        self.assertEqual(self.checkout["state"], "never_by_design")
        self.assertIsNone(self.checkout["flipped_at"])

    def test_adoption_evidence_records_the_design_adapter(self):
        ref = self.checkout["evidence_ref"]
        self.assertNotIn("not dispatch-wired", ref,
                         "adoption file still says checkout is not dispatch-wired")
        self.assertIn("checkout_wrapper.py", ref)
        self.assertIn("Skill 06", ref, "native-form exclusion missing")
        self.assertIn("prompt", ref.lower(), "prompt-policy exclusion missing")

    def test_the_wiring_the_evidence_names_exists(self):
        structure = json.loads(STRUCTURE.read_text(encoding="utf-8"))
        checkout = structure["page_role_map"]["page_types"]["checkout"]
        self.assertEqual(checkout["adapter"], "design_only")
        self.assertIn("checkout_wrapper.py", checkout["rule"])
        row = json.loads(PAGE_TYPES.read_text(encoding="utf-8"))["pages"]["checkout"]
        self.assertEqual(row["wrapper"], "checkout_wrapper.py")
        self.assertTrue(row["design_only"])
        cmd = json.loads(ADAPTERS.read_text(encoding="utf-8"))["adapters"]["checkout"]["command"]
        self.assertTrue(any("checkout_wrapper.py" in part for part in cmd))


if __name__ == "__main__":
    unittest.main(verbosity=2)
