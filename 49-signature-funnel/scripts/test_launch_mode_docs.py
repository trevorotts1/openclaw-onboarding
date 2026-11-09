#!/usr/bin/env python3
"""test_launch_mode_docs.py - proves LAUNCH_MODE.md and prompt-policy-adoption.json
describe the wiring that exists: the launch chain the entry hash-pins (read from the
shell's own PINNED_FILES group, never assumed), and checkout's design-only dispatch
beside its native-form and prompt-policy exclusions.
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

# The shell groups the launch dispatch chain under this comment inside PINNED_FILES.
CHAIN_MARKER = "# The launch dispatch chain:"
ROLES = ("landing", "product_selection", "checkout", "upsell_1",
         "downsell_1", "upsell_2", "thank_you")


def pinned_block():
    text = ENTRY.read_text(encoding="utf-8")
    m = re.search(r"PINNED_FILES=\((.*?)\n\)", text, re.S)
    if not m:
        raise RuntimeError("PINNED_FILES array not found in signature-funnel-entry.sh")
    return m.group(1)


def pinned_files():
    return tuple(re.findall(r'"([^"]+)"', pinned_block()))


def launch_chain():
    """The launch-chain members of PINNED_FILES, taken from the shell's own group."""
    block = pinned_block()
    _head, sep, tail = block.partition(CHAIN_MARKER)
    if not sep:
        raise RuntimeError("launch dispatch chain group marker %r missing in "
                           "signature-funnel-entry.sh" % CHAIN_MARKER)
    chain = tuple(re.findall(r'"([^"]+)"', tail))
    if not chain:
        raise RuntimeError("launch dispatch chain group is empty")
    return chain


def pin_paragraph():
    """The one LAUNCH_MODE.md paragraph that describes PINNED_FILES."""
    for para in LAUNCH_DOC.read_text(encoding="utf-8").split("\n\n"):
        if "PINNED_FILES" in para:
            return para
    raise RuntimeError("LAUNCH_MODE.md has no paragraph naming PINNED_FILES")


class PinnedLaunchChain(unittest.TestCase):
    def test_entry_pins_every_launch_module(self):
        pinned = pinned_files()
        for rel in launch_chain():
            self.assertIn(rel, pinned, "launch module not hash-pinned: %s" % rel)
            self.assertTrue((SKILL / rel).is_file(), rel)

    def test_launch_doc_pin_paragraph_tracks_the_shell_exactly(self):
        doc = LAUNCH_DOC.read_text(encoding="utf-8")
        self.assertNotIn("no pinned file changed", doc,
                         "LAUNCH_MODE.md still claims launch mode pinned nothing")
        para = pin_paragraph()
        named = set(re.findall(r"scripts/[a-z0-9_]+\.py", para))
        self.assertEqual(named, set(launch_chain()),
                         "LAUNCH_MODE.md pin paragraph and the shell's "
                         "PINNED_FILES launch group disagree")
        self.assertIn("--write-pin", para, "pin paragraph omits the --write-pin path")
        self.assertIn("SF-PROVER-PIN.sha256", para,
                      "pin paragraph omits the pin file it mints")


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
        self.assertIsNone(self.checkout["verified_against_main"])

    def test_adoption_evidence_records_the_design_adapter(self):
        ref = self.checkout["evidence_ref"]
        self.assertNotIn("not dispatch-wired", ref,
                         "adoption file still says checkout is not dispatch-wired")
        self.assertIn("checkout_wrapper.py", ref)
        self.assertIn("Skill 06", ref, "native-form exclusion missing")
        self.assertIn("schema_version 1.0", ref, "1.0 stamp claim missing")
        self.assertIn("prompt_policy_id", ref, "prompt-policy exclusion missing")
        rule = json.loads(STRUCTURE.read_text(encoding="utf-8"))[
            "page_role_map"]["page_types"]["checkout"]["rule"]
        self.assertEqual("awaiting Trevor's ratification" in ref,
                         "awaiting Trevor's ratification" in rule,
                         "adoption evidence and the funnel_structure rule "
                         "disagree on CR-S49-003's ratification status")

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
