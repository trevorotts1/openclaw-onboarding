#!/usr/bin/env python3
"""Items 20 + 21 (Update Plan, Wave 6): governing documents land last.

Item 20 = proposal P10 + the P12 remainder:
  (a) universal-sops/signature-page-craft/README.md carries P10's rail
      paragraph verbatim (stage_gate.py over private/state.json as the
      rail, swarm_runner.py as the orchestrator, validate_state.py
      marked legacy);
  (b) validate_state.py appears in the README only in legacy-marked
      lines, and the retired workflow-state rail claims are gone;
  (c) the README's restated stage list matches
      references/stage-contract.json stage for stage (14 stages, the
      conditional automation-wiring stage named), and the README states
      the regeneration rule;
  (d) the SOP's scope section carries P12's website-craft boundary
      sentence verbatim (SKILL.md already carries the boundary).

Item 21 = proposal P13 (Decision 5: VENDOR):
  (e) the SOP scoring paragraph no longer defers to an unnamed external
      Graphics repository; it states the vendored bar;
  (f) references/qc-contract.md states the bar as the skill's own
      vendored standard (no "stricter Graphics threshold" deferral);
  (g) the Image Guide's QC section carries the vendored scoring bar
      statement, and its former repository-attributed pass lines are
      conformed;
  (h) the bar agrees number for number across all three files
      (8.5 average, every criterion at least 8, zero auto-fails);
  (i) blast radius: the stage contract's stage order is unchanged.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
README = (REPO / "universal-sops" / "signature-page-craft" / "README.md").read_text(encoding="utf-8")
SOP = (ROOT / "references" / "BlackCEO-Signature-Landing-Page-Production-and-QC-SOP-v1.md").read_text(encoding="utf-8")
GUIDE = (ROOT / "references" / "BlackCEO-Signature-Image-Intelligence-and-Prompt-Creation-Guide-v5.md").read_text(encoding="utf-8")
QC = (ROOT / "references" / "qc-contract.md").read_text(encoding="utf-8")
SKILL = (ROOT / "SKILL.md").read_text(encoding="utf-8")
CONTRACT = json.loads((ROOT / "references" / "stage-contract.json").read_text(encoding="utf-8"))

P10_RAIL = ("The rail for a page build is the skill's own gate (scripts/stage_gate.py over the run's "
            "private/state.json) with scripts/swarm_runner.py as the orchestrator for item-level "
            "fan-out. scripts/validate_state.py is legacy: it validates the retired workflow-state "
            "format and is kept for old runs only.")
P12_SENTENCE = ("A multi-page marketing website whose governing copy contract is not this BlackCEO "
                "single-page system is website-craft work, not a signature page, however similar "
                "the pages look.")


class TestItem20ReadmeRail(unittest.TestCase):
    def test_rail_paragraph_verbatim(self):
        self.assertIn(P10_RAIL, README)

    def test_validate_state_only_legacy_marked(self):
        for line in README.splitlines():
            if "validate_state.py" in line:
                self.assertIn("legacy", line.lower(), line)

    def test_retired_rail_claims_gone(self):
        self.assertNotIn("no gate-code family", README)
        self.assertNotIn("workflow-state.json", README)
        self.assertNotIn("run per stage as the workflow-state", README)
        self.assertIn("state.json, internal-copy.md", README)

    def test_stage_list_matches_contract(self):
        m = re.search(r"through the contract's 14 stages in order:\n(.*?)\n\nStage-list rule:",
                      README, re.S)
        self.assertIsNotNone(m, "restated stage list block not found")
        listed = [part.strip() for part in m.group(1).replace("\n", " ").split("->")]
        listed = [p for p in listed if p]
        last = listed[-1]
        self.assertTrue(last.startswith("automation-wiring"), last)
        self.assertIn("conditional", last)
        listed[-1] = "automation-wiring"
        self.assertEqual(listed, CONTRACT["stage_order"])
        self.assertEqual(len(CONTRACT["stage_order"]), 14)

    def test_stage_list_regeneration_rule_stated(self):
        self.assertIn("any stage list this README restates is regenerated from", README)
        self.assertIn("references/stage-contract.json`, never written by hand", README)


class TestItem20SopBoundary(unittest.TestCase):
    def test_scope_carries_boundary_sentence_verbatim(self):
        scope_line = next(l for l in SOP.splitlines() if l.startswith("**Scope:**"))
        self.assertIn(P12_SENTENCE, scope_line)

    def test_skill_md_carries_the_boundary(self):
        self.assertIn("governing copy contract is not this BlackCEO single-page system", SKILL)


class TestItem21VendoredBar(unittest.TestCase):
    def test_sop_deferral_replaced(self):
        self.assertNotIn("The primary Graphics repository is stricter", SOP)
        self.assertIn("vendored into the Image Guide's QC section", SOP)
        self.assertIn("Decision 5", SOP)

    def test_qc_contract_states_own_bar(self):
        self.assertNotIn("stricter Graphics threshold", QC)
        self.assertIn("vendored here and in the Image Guide's QC section", QC)
        self.assertIn("average at least 8.5", QC)
        self.assertIn("every applicable individual criterion at least 8", QC)
        self.assertIn("zero automatic failures", QC)

    def test_guide_qc_carries_vendored_bar(self):
        self.assertIn("Vendored scoring bar (Skill 71's own; Update Plan Item 21, Decision 5)", GUIDE)
        self.assertIn("not deferred to any external repository", GUIDE)
        self.assertNotIn("average >=8.5 for Graphics prompts", GUIDE)
        self.assertNotIn("repository image-QC average", GUIDE)
        self.assertNotIn("Retain the repository's stricter 8.5 average", GUIDE)

    def test_bar_agrees_number_for_number(self):
        for name, text in (("SOP", SOP), ("qc-contract", QC), ("guide", GUIDE)):
            self.assertIn("8.5", text, name)
        self.assertIn("8.5 minimum average", SOP)
        self.assertIn("every individual applicable criterion at least 8", SOP)
        self.assertIn("zero auto-fails", SOP)
        self.assertIn("average >=8.5", GUIDE)
        self.assertIn("every applicable individual criterion >=8", GUIDE)


class TestBlastRadius(unittest.TestCase):
    def test_stage_order_unchanged(self):
        self.assertEqual(CONTRACT["stage_order"], [
            "intake", "copy", "font-action-plan", "desktop-wireframe", "mobile-tablet",
            "visual-mockup", "image-inventory-prompts", "image-generation-qc",
            "image-map-upload", "final-mockups", "responsive-html", "ghl-install-test",
            "publish-verify", "automation-wiring"])


if __name__ == "__main__":
    unittest.main()
