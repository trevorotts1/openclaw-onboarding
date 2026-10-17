#!/usr/bin/env python3
"""Item 5 (Update Plan, Decision 2 option (i)): stage architecture pins.

The client-judged mockup is a single stage (final-mockups) that opens only
after the image generation chain closes; the former stage-6 mockup stage
(visual-mockup) is an internal layout proof that produces the page visual
bible and is never the client-facing mockup.

Pins:
  (a) stage_order places the generation chain (image-inventory-prompts,
      image-generation-qc, image-map-upload) before final-mockups, and the
      layout-proof stage before the prompt stage that requires its bible.
  (b) final-mockups depends_on includes image-map-upload (the generation
      chain's last stage) and visual-mockup (the layout proof it finalizes).
  (c) the contract records each stage's role in its `purpose` field.
  (d) references/artifact-contracts.md enumerates exactly the contract's
      stage IDs in the same order (the P4 regeneration rule).
  (e) the SOP and SKILL.md carry the same role statements in prose.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "references" / "stage-contract.json").read_text(encoding="utf-8"))
ORDER = CONTRACT["stage_order"]
STAGES = CONTRACT["stages"]

GENERATION_CHAIN = ["image-inventory-prompts", "image-generation-qc", "image-map-upload"]


class StageArchitectureTest(unittest.TestCase):
    def test_generation_chain_precedes_judged_mockup(self):
        mockup_at = ORDER.index("final-mockups")
        for stage in GENERATION_CHAIN:
            self.assertLess(ORDER.index(stage), mockup_at,
                            f"{stage} must precede final-mockups in stage_order")
        chain = [ORDER.index(s) for s in GENERATION_CHAIN]
        self.assertEqual(chain, sorted(chain), "generation chain must keep its internal order")

    def test_layout_proof_precedes_prompt_stage(self):
        self.assertLess(ORDER.index("visual-mockup"), ORDER.index("image-inventory-prompts"))
        prompts = STAGES["image-inventory-prompts"]
        self.assertIn("visual-mockup/page-visual-bible.json", prompts["requires_artifacts"])
        bible = [a for a in STAGES["visual-mockup"]["artifacts"]
                 if a["glob"] == "visual-mockup/page-visual-bible.json"]
        self.assertEqual(len(bible), 1, "the layout-proof stage must produce the visual bible")

    def test_judged_mockup_depends_on_generation_chain(self):
        deps = STAGES["final-mockups"]["depends_on"]
        self.assertIn("image-map-upload", deps)
        self.assertIn("visual-mockup", deps)

    def test_stage_roles_recorded_in_contract(self):
        proof = STAGES["visual-mockup"]["purpose"].lower()
        self.assertIn("internal layout proof", proof)
        self.assertIn("never", proof)
        self.assertIn("client-judged mockup", proof)
        mockup = STAGES["final-mockups"]["purpose"].lower()
        self.assertIn("single client-judged mockup", mockup)
        self.assertIn("real photography", mockup)
        self.assertIn("never generated", mockup)

    def test_artifact_contracts_enumeration_matches_contract(self):
        text = (ROOT / "references" / "artifact-contracts.md").read_text(encoding="utf-8")
        block = re.search(r'"workflow_id":\s*"client-page-001".*?\n\}', text, re.S)
        self.assertIsNotNone(block, "workflow-state example not found in artifact-contracts.md")
        example = json.loads("{" + block.group(0))
        self.assertEqual(list(example["stages"].keys()), ORDER,
                         "artifact-contracts.md must enumerate the contract's stage IDs in order")

    def test_prose_surfaces_state_the_roles(self):
        sop = (ROOT / "references" /
               "BlackCEO-Signature-Landing-Page-Production-and-QC-SOP-v1.md").read_text(encoding="utf-8")
        stage6 = sop.split("## Stage 6 -", 1)[1].split("## Stage 7 -", 1)[0].lower()
        self.assertIn("internal layout proof", stage6)
        self.assertIn("never", stage6)
        stage11 = sop.split("## Stage 11 -", 1)[1].split("## Stage 12 -", 1)[0].lower()
        self.assertIn("client-judged mockup", stage11)
        self.assertIn("placed as files", stage11)
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8").lower()
        self.assertIn("internal layout proof", skill)
        self.assertIn("single client-judged mockup", skill)


if __name__ == "__main__":
    unittest.main(verbosity=2)
