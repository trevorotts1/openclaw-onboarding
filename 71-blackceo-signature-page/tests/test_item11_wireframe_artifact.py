#!/usr/bin/env python3
"""Item 11 (Update Plan): wireframe artifact definition pins.

The wireframe is a designed, annotated build spec rendered as images, in
the client's brand colors: generated per section, carrying section
numbers and names, printed type specs, image slots as deliberate
placeholders labeled with aspect ratio and art direction, the run's real
copy, CTA chips with real button text and microcopy specs, per-section
behavior notes, and a header strip stating page width and content width.
It is delivered, per wireframe, as section slices, one stitched
full-page PNG, and one combined PDF. It is not an HTML render.

Pins:
  (a) both wireframe stages' contract artifacts are exactly the spec
      image set plus the stage's retained records, and no part-*.png
      export glob remains in either wireframe stage;
  (b) both wireframe stages record the definition in a `purpose` field;
  (c) stage IDs, stage order, and the wireframe stages' depends_on are
      unchanged (this item redefines an artifact, not the stage list);
  (d) references/artifact-contracts.md enumerates exactly the contract's
      stage IDs in the same order (the P4 regeneration rule);
  (e) references/artifact-contracts.md carries the wireframe artifact
      contract: the three deliverables and the annotation elements;
  (f) the SOP's Stage 4 and Stage 5 text states the same definition and
      deliverables, and the retired export-part instruction is gone;
  (g) the change's blast radius: the mockup stages' part-*.png renders
      are untouched (they are renders of HTML mockups, not wireframes).
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "references" / "stage-contract.json").read_text(encoding="utf-8"))
ORDER = CONTRACT["stage_order"]
STAGES = CONTRACT["stages"]

WIREFRAME_STAGES = ["desktop-wireframe", "mobile-tablet"]
RETAINED = {
    "desktop-wireframe": ["desktop-wireframe/image-inventory.json",
                          "desktop-wireframe/section-plan.json",
                          "desktop-wireframe/production-record.json"],
    "mobile-tablet": ["mobile-tablet/tablet-rules.md",
                      "mobile-tablet/section-plan.json",
                      "mobile-tablet/production-record.json"],
}


def globs(stage):
    return [a["glob"] for a in STAGES[stage]["artifacts"]]


class WireframeArtifactTest(unittest.TestCase):
    def test_contract_deliverables_are_the_spec_image_set(self):
        for stage in WIREFRAME_STAGES:
            expected = [f"{stage}/section-*.png",
                        f"{stage}/wireframe-full.png",
                        f"{stage}/wireframe.pdf"] + RETAINED[stage]
            self.assertEqual(globs(stage), expected,
                             f"{stage} artifacts must be the spec image set "
                             f"plus its retained records")
            self.assertFalse(any("part-" in g for g in globs(stage)),
                             f"{stage} must not keep a part-*.png export glob")

    def test_stage_purpose_records_the_definition(self):
        for stage in WIREFRAME_STAGES:
            purpose = STAGES[stage]["purpose"].lower()
            self.assertIn("spec image", purpose)
            self.assertIn("brand colors", purpose)
            self.assertIn("never an html render", purpose)
            self.assertIn("section slice", purpose)
            self.assertIn("aspect ratio and art direction", purpose)
            self.assertIn("header strip", purpose)
            self.assertIn("stitched full-page png", purpose)
            self.assertIn("combined pdf", purpose)

    def test_stage_list_and_dependencies_unchanged(self):
        self.assertEqual(len(ORDER), 15)
        self.assertLess(ORDER.index("font-action-plan"), ORDER.index("desktop-wireframe"))
        self.assertLess(ORDER.index("desktop-wireframe"), ORDER.index("mobile-tablet"))
        self.assertEqual(STAGES["desktop-wireframe"]["depends_on"], ["font-action-plan"])
        self.assertEqual(STAGES["mobile-tablet"]["depends_on"], ["desktop-wireframe"])
        for stage in WIREFRAME_STAGES:
            # desktop-wireframe also runs the design-style inventory check (the inventory
            # lives there; SPF025): the chosen style is checked against the slot shapes.
            style_gate = (["python3 scripts/design_style.py validate-inventory {run_dir}"]
                          if stage == "desktop-wireframe" else [])
            self.assertEqual(STAGES[stage]["validators"],
                             [f"python3 scripts/validate_wireframe.py {{run_dir}} {stage}", *style_gate,
                              f"python3 scripts/validate_production_record.py {{run_dir}}/{stage}/production-record.json",
                              # no notes between sections: the review PDF gate (one title band on page 1 only)
                              f"python3 scripts/validate_review_pdf.py {{run_dir}} --stage {stage}"],
                             f"{stage} validators are the wireframe check plus the Item 13 "
                             f"production-record gate, the review-PDF gate (and the style inventory check on desktop-wireframe)")
            self.assertTrue(STAGES[stage]["review_required"])

    def test_artifact_contracts_enumeration_matches_contract(self):
        text = (ROOT / "references" / "artifact-contracts.md").read_text(encoding="utf-8")
        block = re.search(r'"workflow_id":\s*"client-page-001".*?\n\}', text, re.S)
        self.assertIsNotNone(block, "workflow-state example not found in artifact-contracts.md")
        example = json.loads("{" + block.group(0))
        self.assertEqual(list(example["stages"].keys()), ORDER,
                         "artifact-contracts.md must enumerate the contract's stage IDs in order")

    def test_artifact_contracts_carry_the_wireframe_contract(self):
        text = (ROOT / "references" / "artifact-contracts.md").read_text(encoding="utf-8")
        section = " ".join(text.split("## Wireframe artifact", 1)[1]
                            .split("## Section plan", 1)[0].lower().split())
        for phrase in ("section-*.png", "wireframe-full.png", "wireframe.pdf",
                       "never an html render", "brand colors",
                       "aspect ratio and its art direction", "behavior notes",
                       "header strip", "page width", "content width",
                       "cta chips", "microcopy", "assembly map",
                       "match the slices section for section"):
            self.assertIn(phrase, section,
                          f"wireframe artifact contract must state: {phrase}")

    def test_sop_stage_text_states_the_definition(self):
        sop = (ROOT / "references" /
               "BlackCEO-Signature-Landing-Page-Production-and-QC-SOP-v1.md").read_text(encoding="utf-8")
        stage4 = sop.split("## Stage 4 -", 1)[1].split("## Stage 5 -", 1)[0]
        stage5 = sop.split("## Stage 5 -", 1)[1].split("## Stage 6 -", 1)[0]
        low4, low5 = " ".join(stage4.lower().split()), " ".join(stage5.lower().split())
        for phrase in ("annotated build spec", "brand colors", "not an html render",
                       "header strip", "aspect ratio and its art direction",
                       "behavior notes", "cta chips", "section slice"):
            self.assertIn(phrase, low4, f"SOP Stage 4 must state: {phrase}")
        for phrase in ("section-*.png", "wireframe-full.png", "wireframe.pdf",
                       "private assembly map", "section for section"):
            self.assertIn(phrase, stage4, f"SOP Stage 4 must name: {phrase}")
        for phrase in ("annotated build spec", "brand colors", "header strip",
                       "aspect ratio and art direction", "behavior note", "section slice"):
            self.assertIn(phrase, low5, f"SOP Stage 5 must state: {phrase}")
        for phrase in ("section-*.png", "wireframe-full.png", "wireframe.pdf"):
            self.assertIn(phrase, stage5, f"SOP Stage 5 must name: {phrase}")
        self.assertNotIn("part-a, part-b", low4,
                         "the retired lettered export-part instruction must be gone from Stage 4")
        self.assertNotIn("consecutive png parts", low5,
                         "the retired export-part instruction must be gone from Stage 5")

    def test_mockup_stage_renders_untouched(self):
        self.assertIn("visual-mockup/desktop/part-*.png", globs("visual-mockup"))
        self.assertIn("visual-mockup/mobile/part-*.png", globs("visual-mockup"))
        self.assertIn("final-mockups/desktop/part-*.png", globs("final-mockups"))
        self.assertIn("final-mockups/mobile/part-*.png", globs("final-mockups"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
