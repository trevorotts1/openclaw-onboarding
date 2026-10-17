#!/usr/bin/env python3
"""Wave 6 Items 22 + 24 + 28 (Update Plan, proposals P1 / P3 / P8): governing-text pins.

All three proposals were RULED approved on 2026-10-15 and are applied
verbatim from SKILL71-UPDATE-PLAN.md:

  Item 22 (P1): the Brand Law Signature Grade Block passage states
  that uncalibrated WARN is a working state in test runs and during
  production work, never a production verdict, and that a production
  close of the image stage is refused while either grade threshold
  is null.
  Item 24 (P3): the SOP's scope section states that creating a
  missing GHL product is inside the page job's scope exactly once
  per missing product, after an existence check, for the product the
  funnel's order form binds, recorded in the funnel-completion
  receipt.
  Item 28 (P8): the fidelity-gate governing-rule note is added to
  BOTH the Image Guide's QC section (section 13) and
  references/qc-contract.md (style fidelity enforcement section):
  a style library's own apparatus governs the style-level verdict,
  the guide's fidelity gate governs the page-level verdict, and the
  two verdicts are recorded separately.

Pins:
  (a) the Item 22 approved text appears verbatim (whitespace
      normalised) inside the Brand Law's Signature Grade Block
      section, and the old indefinite wording (WARN with no
      production-close refusal) no longer ends that sentence;
  (b) the Item 24 approved scope sentences appear verbatim inside
      the SOP's opening scope area (before the first stage
      documents table);
  (c) the Item 28 approved note appears verbatim in BOTH named
      places, in the guide's section 13 and in qc-contract.md's
      style fidelity section;
  (d) blast radius: the stage contract's stage list is unchanged.
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFS = ROOT / "references"
BRAND_LAW = (REFS / "BlackCEO-Page-Brand-Law.md").read_text(encoding="utf-8")
SOP = (REFS / "BlackCEO-Signature-Landing-Page-Production-and-QC-SOP-v1.md").read_text(encoding="utf-8")
GUIDE = (REFS / "BlackCEO-Signature-Image-Intelligence-and-Prompt-Creation-Guide-v5.md").read_text(encoding="utf-8")
QC_CONTRACT = (REFS / "qc-contract.md").read_text(encoding="utf-8")
CONTRACT = json.loads((REFS / "stage-contract.json").read_text(encoding="utf-8"))

ITEM22_TEXT = (
    "Until the grade thresholds (grade.min_mean_saturation, grade.min_luma_std) "
    "are calibrated by Trevor-approved images, they stay null and grade checks "
    "run as uncalibrated WARN in test runs and during production work. "
    "A production close of the image stage is refused while either threshold "
    "is null (Item 6): uncalibrated WARN is a working state, never a "
    "production verdict. Calibration is Item 8 and waits on the owner's "
    "gold images."
)
ITEM24_TEXT = (
    "Creating a missing GHL product is inside this job's scope exactly once "
    "per missing product: only after an existence check proves it absent, "
    "only the product the funnel's order form binds, and always recorded in "
    "the funnel-completion receipt (Item 32). Everything else about products "
    "(pricing changes, catalog management) stays outside this job."
)
ITEM28_TEXT = (
    "When a style library supplies its own fidelity apparatus, that "
    "apparatus governs the style-level verdict for images under that "
    "selection. The guide's fidelity gate governs the page-level verdict "
    "(coherence across the page's images) and remains the only gate when "
    "no library apparatus applies. The two verdicts are recorded "
    "separately in the review; neither silently overrides the other."
)


def squash(text):
    return " ".join(text.split())


class Item22BrandLawTest(unittest.TestCase):
    def test_approved_text_in_signature_grade_block(self):
        section = BRAND_LAW.split("## Signature Grade Block", 1)[1].split(
            "**Ruling 6 conformance", 1)[0]
        self.assertIn(ITEM22_TEXT, squash(section),
                      "Brand Law Signature Grade Block must carry the P1 approved text verbatim")

    def test_old_indefinite_wording_gone(self):
        self.assertNotIn(
            "they stay `null` and grade checks run as uncalibrated WARN.",
            BRAND_LAW,
            "the pre-P1 sentence blessing uncalibrated WARN indefinitely must be gone")
        self.assertIn("never a production verdict", squash(BRAND_LAW))


class Item24SopScopeTest(unittest.TestCase):
    def test_approved_sentence_in_scope_area(self):
        scope_area = SOP.split("## Start here:", 1)[0]
        self.assertIn(ITEM24_TEXT, squash(scope_area),
                      "SOP scope section must carry the P3 approved sentence verbatim")

    def test_scope_sentence_marked_as_item24(self):
        scope_area = SOP.split("## Start here:", 1)[0]
        self.assertIn("Product-creation scope (Update Plan Item 24 / proposal P3)",
                      squash(scope_area))


class Item28FidelityGateNoteTest(unittest.TestCase):
    def test_note_in_guide_qc_section(self):
        section13 = GUIDE.split("## 13. QC and repair the generated pixels", 1)[1].split(
            "## 14. Required output", 1)[0]
        self.assertIn(ITEM28_TEXT, squash(section13),
                      "Image Guide QC section (13) must carry the P8 note verbatim")
        self.assertIn("Fidelity-gate governing rule (Update Plan Item 28 / proposal P8)",
                      squash(section13))

    def test_note_in_qc_contract_style_fidelity_section(self):
        section = QC_CONTRACT.split("## Style fidelity enforcement", 1)[1].split(
            "## Residual judgment", 1)[0]
        self.assertIn(ITEM28_TEXT, squash(section),
                      "qc-contract.md style fidelity section must carry the P8 note verbatim")
        self.assertIn("Fidelity-gate governing rule (Update Plan Item 28 / proposal P8)",
                      squash(section))

    def test_note_identical_in_both_documents(self):
        self.assertEqual(squash(GUIDE).count(ITEM28_TEXT), 1,
                         "guide must carry the P8 note exactly once")
        self.assertEqual(squash(QC_CONTRACT).count(ITEM28_TEXT), 1,
                         "qc-contract must carry the P8 note exactly once")


class BlastRadiusTest(unittest.TestCase):
    def test_stage_contract_stage_list_unchanged(self):
        stages = list(CONTRACT["stages"].keys()) if isinstance(CONTRACT.get("stages"), dict) else [
            s.get("id") for s in CONTRACT.get("stages", [])]
        self.assertEqual(len(stages), 14,
                         f"governing-text items must not change the stage list; got {stages}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
