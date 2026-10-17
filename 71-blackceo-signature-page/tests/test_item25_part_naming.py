#!/usr/bin/env python3
"""Item 25 (Update Plan, proposal P5 as ruled): wireframe part-naming pins.

Ruling (2026-10-15, option (a)): the SOP's letter scheme governs
human-facing exports; the numeric scheme is recorded in the assembly
map as the machine name for the same file; the mapping is written
down in BOTH documents (the Production/QC SOP and
references/artifact-contracts.md).

Reconciled with Item 11's deliverable names: a wireframe "part" is
one section slice. Its machine name is the slice's numeric file name
(`section-01.png`, `section-02.png`, ... in the stage folder); its
human-facing name is its Part letter (Part-A for the first slice in
section order, Part-B for the second, consecutive letters after).
The stitched `wireframe-full.png` and the combined `wireframe.pdf`
are single files and carry no part name.

Pins:
  (a) the SOP's Stage 4 text states the full mapping (letters
      human-facing, numbers the machine names, the assembly map
      records both names per slice, single files carry no part name);
  (b) the SOP's Stage 5 text applies the same mapping per wireframe
      (letters restart at the mobile page's first section, folder
      name disambiguates);
  (c) artifact-contracts.md's wireframe section states the same
      mapping, including the review-vocabulary consequence (review
      item ids derive from machine names, never Part letters) and
      the Review-PDF page-label consequence;
  (d) both documents agree on the worked example: the first slice is
      Part-A and `section-01.png`, the second Part-B and
      `section-02.png`;
  (e) blast radius: the stage contract is untouched by this item, so
      the wireframe stages still deliver Item 11's spec image set
      and the mockup stages keep their `part-*.png` renders.
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOP = (ROOT / "references" /
       "BlackCEO-Signature-Landing-Page-Production-and-QC-SOP-v1.md").read_text(encoding="utf-8")
CONTRACTS = (ROOT / "references" / "artifact-contracts.md").read_text(encoding="utf-8")
CONTRACT = json.loads((ROOT / "references" / "stage-contract.json").read_text(encoding="utf-8"))
STAGES = CONTRACT["stages"]


def squash(text):
    return " ".join(text.lower().split())


def sop_stage(number, following):
    return SOP.split(f"## Stage {number} -", 1)[1].split(f"## Stage {following} -", 1)[0]


class PartNamingTest(unittest.TestCase):
    def test_sop_stage4_states_the_mapping(self):
        low = squash(sop_stage(4, 5))
        for phrase in ("each section slice is one part of the wireframe export",
                       "two names for the same file",
                       "human-facing name is lettered",
                       "first slice in section order is part-a",
                       "machine name is numeric",
                       "section-01.png",
                       "human-facing exports",
                       "never become page headings",
                       "assembly map is where the two names meet",
                       "machine name (the file)",
                       "human-facing name (its part letter)",
                       "carry no part name",
                       "assembly map is the authority"):
            self.assertIn(phrase, low, f"SOP Stage 4 part naming must state: {phrase}")

    def test_sop_stage5_applies_the_mapping_per_wireframe(self):
        low = squash(sop_stage(5, 6))
        for phrase in ("part naming follows the stage 4 mapping",
                       "lettered from part-a at the mobile page's first section",
                       "machine names are the `section-*.png` files",
                       "mobile-tablet",
                       "folder name is what disambiguates"):
            self.assertIn(phrase, low, f"SOP Stage 5 part naming must state: {phrase}")

    def test_artifact_contracts_state_the_mapping(self):
        section = CONTRACTS.split("## Wireframe artifact", 1)[1].split("## Section plan", 1)[0]
        low = squash(section)
        for phrase in ("part naming (human-facing letters, machine numbers)",
                       "two names for the same file",
                       "human-facing name is lettered",
                       "first slice in section order is part-a",
                       "machine name is numeric",
                       "section-01.png",
                       "review-pdf manifest's page `label` values",
                       "never becomes a page heading",
                       "review item ids use machine names only",
                       "never from the part letter",
                       "assembly map is where the two names meet",
                       "one entry per slice, in section order",
                       "letters restart per wireframe",
                       "folder name disambiguates",
                       "carry no part name"):
            self.assertIn(phrase, low,
                          f"artifact-contracts wireframe section must state: {phrase}")

    def test_both_documents_agree_on_the_worked_example(self):
        for doc, name in ((squash(sop_stage(4, 5)), "SOP Stage 4"),
                          (squash(CONTRACTS.split("## Wireframe artifact", 1)[1]
                                  .split("## Section plan", 1)[0]), "artifact-contracts")):
            self.assertIn("section-01.png` for the first slice", doc,
                          f"{name} must pair the first slice's machine name with its order")
            self.assertIn("section-02.png` for the second", doc,
                          f"{name} must pair the second slice's machine name with its order")

    def test_stage_contract_blast_radius(self):
        def globs(stage):
            return [a["glob"] for a in STAGES[stage]["artifacts"]]
        for stage in ("desktop-wireframe", "mobile-tablet"):
            self.assertIn(f"{stage}/section-*.png", globs(stage))
            self.assertIn(f"{stage}/wireframe-full.png", globs(stage))
            self.assertIn(f"{stage}/wireframe.pdf", globs(stage))
        self.assertIn("visual-mockup/desktop/part-*.png", globs("visual-mockup"))
        self.assertIn("final-mockups/desktop/part-*.png", globs("final-mockups"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
