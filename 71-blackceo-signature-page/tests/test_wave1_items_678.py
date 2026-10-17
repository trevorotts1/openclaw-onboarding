#!/usr/bin/env python3
"""Tests for update plan Wave 1 Items 6, 7, and 8.

Item 6: the font-map and action-plan schemas now written into
references/artifact-contracts.md must match what the gate machinery
reads. The font-map example is extracted from the document itself and
run through gate:brand_fonts, so the documented schema and the gate
cannot drift apart silently.

Item 7: on the derive path, gate:brand_fonts requires the font map's
derivation documentation fields (fonts_source "derived", non-empty
font_rationale, font_reviewer named) and still checks no approval: the
approval is recorded once, at the visual bible review.

Item 8: gate:copy_handoff pins copy/public-copy.md's Markdown links as
the renderer's source for button labels and destinations; every CTA
declared by the copy manifest (or, absent a manifest inventory, by the
internal manuscript's CTA markers) must resolve a label and a
destination from that source.
"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import stage_gate  # noqa: E402

CONTRACTS = (ROOT / "references" / "artifact-contracts.md").read_text(encoding="utf-8")

BANNED = ["Inter", "Arial", "Helvetica", "Helvetica Neue", "Roboto",
          "Open Sans", "system-ui", "-apple-system", "BlinkMacSystemFont",
          "Segoe UI", "sans-serif-only"]


def section_text(start_marker, end_marker=None):
    start = CONTRACTS.index(start_marker)
    end = CONTRACTS.index(end_marker, start) if end_marker else len(CONTRACTS)
    return CONTRACTS[start:end]


def font_map_example():
    sec = section_text("## Font map", "## Action plan")
    m = re.search(r"```json\n(.*?)```", sec, re.S)
    assert m, "font map section carries no JSON example"
    return json.loads(m.group(1))


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def brand_file(dirpath, fonts, policy=None):
    brand = {"fonts": fonts, "banned_fonts": BANNED}
    if policy is not None:
        brand["font_policy"] = policy
    p = Path(dirpath) / "brand.json"
    write(p, json.dumps(brand))
    return p


SUPPLIED_BRAND_FONTS = {"display": "Fraunces", "body": "Newsreader",
                        "accent": "Libre Franklin"}
DERIVE_POLICY = {"when_brand_fonts_missing": "derive-document",
                 "requires_rationale": True, "requires_reviewer": True}
DERIVE_BRAND_FONTS = {"display": "TREVOR_MUST_SUPPLY",
                      "body": "TREVOR_MUST_SUPPLY",
                      "accent": "TREVOR_MUST_SUPPLY"}


def run_brand_fonts(run_dir, font_map_obj, brand_path):
    fm = Path(run_dir) / "font-action-plan" / "font-map.json"
    write(fm, json.dumps(font_map_obj))
    return stage_gate.run_builtin(
        "gate:brand_fonts",
        ["--font-map", str(fm), "--brand", str(brand_path)], Path(run_dir))


class Item6FontMapSchemaTest(unittest.TestCase):
    def test_example_font_map_passes_gate_with_supplied_brand(self):
        with tempfile.TemporaryDirectory() as td:
            brand = brand_file(td, SUPPLIED_BRAND_FONTS)
            result = run_brand_fonts(td, font_map_example(), brand)
            self.assertIsNone(result, f"documented example must pass the gate: {result}")

    def test_example_font_map_passes_gate_on_derive_path(self):
        with tempfile.TemporaryDirectory() as td:
            brand = brand_file(td, DERIVE_BRAND_FONTS, DERIVE_POLICY)
            result = run_brand_fonts(td, font_map_example(), brand)
            self.assertIsNone(result, f"documented derived example must pass the gate: {result}")

    def test_schema_names_every_field_the_gate_reads(self):
        sec = section_text("## Font map", "## Action plan")
        for field in ("fonts", "fonts_source", "font_rationale", "font_reviewer",
                      "families", "css2_request", "weights_used", "italics_used",
                      "axes_used", "fallback_stack", "typography",
                      "derivation_record", "fallback_behavior"):
            self.assertIn(f"`{field}`", sec, f"schema must document {field}")
        # The load-bearing gate semantics: every string under "fonts" is
        # collected and tested as a used family name.
        self.assertIn('collects EVERY string under this key', sec)
        self.assertIn("display=swap", sec)

    def test_fallback_stack_rule_is_labeled_review_enforced(self):
        # Review defect D1 (repair, post-incident rebuild): the Font map
        # section once claimed the gate's banned-fonts check covers
        # fallback stacks. No code reads families/fallback_stack; the
        # rule is a contract requirement enforced by review, and the
        # document must label it that way, never as gate coverage.
        sec = " ".join(section_text("## Font map", "## Action plan").split())
        self.assertNotIn("banned-fonts check covers fallback stacks", sec)
        self.assertIn("enforced by review, not by the gate", sec)
        self.assertIn("reads neither `families` nor `fallback_stack`", sec)

    def test_gate_ignores_fallback_stacks_by_design(self):
        # Pins the truth the contract now states: gate:brand_fonts tests
        # only the strings under "fonts". A banned family recorded only
        # inside a fallback stack, and a generic-only stack, both pass
        # the gate; catching them is the bible reviewer's job, under the
        # review-enforced contract rule. If the gate ever grows a stack
        # check, this test and the contract sentence change together.
        with tempfile.TemporaryDirectory() as td:
            brand = brand_file(td, SUPPLIED_BRAND_FONTS)
            m = font_map_example()
            m["families"]["display"]["fallback_stack"] = ["Inter", "sans-serif"]
            m["families"]["body"]["fallback_stack"] = ["sans-serif"]
            result = run_brand_fonts(td, m, brand)
            self.assertIsNone(result, f"gate must not read fallback stacks: {result}")

    def test_action_plan_schema_names_the_required_content(self):
        sec = " ".join(section_text("## Action plan", "## Delivery receipts").split())
        for phrase in ("on-page form", "button-triggered popup",
                       "separate page or destination",
                       "CTA inventory", "Section 12 in-letter link",
                       "success destination", "keyboard focus",
                       "close behavior and return to scroll",
                       "mobile scrolling", "loading and error handling",
                       "scripts fail", "prefers-reduced-motion",
                       "production plan for the remaining stages",
                       "Type decisions in brief"):
            self.assertIn(phrase, sec, f"action-plan schema must require: {phrase!r}")


class Item7DerivedFontApprovalTest(unittest.TestCase):
    def derive_brand(self, td):
        return brand_file(td, DERIVE_BRAND_FONTS, DERIVE_POLICY)

    def test_complete_documentation_passes(self):
        with tempfile.TemporaryDirectory() as td:
            result = run_brand_fonts(td, font_map_example(), self.derive_brand(td))
            self.assertIsNone(result)

    def test_missing_fonts_source_fails_by_name(self):
        with tempfile.TemporaryDirectory() as td:
            m = font_map_example()
            del m["fonts_source"]
            result = run_brand_fonts(td, m, self.derive_brand(td))
            self.assertIsNotNone(result)
            self.assertIn("fonts_source", result)

    def test_empty_rationale_fails_by_name(self):
        with tempfile.TemporaryDirectory() as td:
            m = font_map_example()
            m["font_rationale"] = "  "
            result = run_brand_fonts(td, m, self.derive_brand(td))
            self.assertIsNotNone(result)
            self.assertIn("font_rationale", result)

    def test_missing_reviewer_fails_by_name(self):
        with tempfile.TemporaryDirectory() as td:
            m = font_map_example()
            del m["font_reviewer"]
            result = run_brand_fonts(td, m, self.derive_brand(td))
            self.assertIsNotNone(result)
            self.assertIn("font_reviewer", result)

    def test_gate_checks_documentation_not_approval(self):
        # A font map naming the designated reviewer as a forward
        # reference (no approval recorded anywhere) must pass: the
        # approval belongs to the later bible review.
        with tempfile.TemporaryDirectory() as td:
            m = font_map_example()
            m["font_reviewer"] = ("Independent reviewer session at the "
                                  "visual-mockup stage; no approval is "
                                  "recorded yet.")
            result = run_brand_fonts(td, m, self.derive_brand(td))
            self.assertIsNone(result)

    def test_supplied_brand_needs_no_derivation_fields(self):
        with tempfile.TemporaryDirectory() as td:
            brand = brand_file(td, SUPPLIED_BRAND_FONTS)
            bare = {"fonts": dict(SUPPLIED_BRAND_FONTS)}
            result = run_brand_fonts(td, bare, brand)
            self.assertIsNone(result, f"supplied-font maps must not be held to the derive path: {result}")

    def test_placeholder_fonts_still_fail_first(self):
        with tempfile.TemporaryDirectory() as td:
            m = {"fonts": dict(DERIVE_BRAND_FONTS),
                 "fonts_source": "derived", "font_rationale": "x",
                 "font_reviewer": "y"}
            result = run_brand_fonts(td, m, self.derive_brand(td))
            self.assertIsNotNone(result)
            self.assertIn("placeholder", result)

    def test_three_texts_state_the_pinned_rule(self):
        contract = json.loads((ROOT / "references" / "stage-contract.json").read_text(encoding="utf-8"))
        note = contract["stages"]["font-action-plan"].get("note", "")
        self.assertIn("recorded exactly once", note)
        self.assertIn("visual bible review", note)
        self.assertFalse(contract["stages"]["font-action-plan"]["review_required"])
        sop = (ROOT / "references" / "BlackCEO-Signature-Landing-Page-Production-and-QC-SOP-v1.md").read_text(encoding="utf-8")
        self.assertIn("no approval is recorded at this stage", sop)
        self.assertIn("recorded there, exactly once, at the bible review", sop)
        law = (ROOT / "references" / "BlackCEO-Page-Brand-Law.md").read_text(encoding="utf-8")
        self.assertIn("recorded exactly once, in the visual bible at its review", law)
        rule = section_text("## Derived-font approval", "## Action plan")
        for phrase in ("WHO", "WHERE", "WHEN", "exactly once"):
            self.assertIn(phrase, rule)


SEVEN_LABELS = ["Build My AI Workforce", "Build My First Department",
                "Take My Place as the Leader", "Build My AI Workforce",
                "Start Building My Workforce", "Lead My Business Again",
                "Join and Build My Team"]


def run_copy_handoff(run_dir, manifest_obj, public_text, manuscript_text):
    write(Path(run_dir) / "copy" / "copy-manifest.json", json.dumps(manifest_obj))
    write(Path(run_dir) / "copy" / "public-copy.md", public_text)
    write(Path(run_dir) / "copy" / "internal-manuscript.md", manuscript_text)
    return stage_gate.run_builtin(
        "gate:copy_handoff",
        ["--manifest", str(Path(run_dir) / "copy" / "copy-manifest.json"),
         "--public-copy", str(Path(run_dir) / "copy" / "public-copy.md"),
         "--manuscript", str(Path(run_dir) / "copy" / "internal-manuscript.md")],
        Path(run_dir))


def manuscript_with_markers(labels):
    parts = ["## Section 1: fixture\n"]
    for label in labels:
        parts.append(f"[CTA BUTTON: {label}]\n[CTA MICROCOPY: Join us.]\n")
    parts.append("## Section 12: letter\n\nJoin the [BlackCEO School of AI](#join) today.\n")
    return "\n".join(parts)


def public_with_links(labels, destination="#join", letter_link=True):
    parts = ["Welcome.\n"]
    for label in labels:
        parts.append(f"[{label}]({destination})\nJoin us.\n")
    if letter_link:
        parts.append("Join the [BlackCEO School of AI](#join) today.\n")
    return "\n".join(parts)


class Item8CopyHandoffTest(unittest.TestCase):
    def test_seven_ctas_resolve_from_markers_and_manifest_destination(self):
        # The School of AI run's shape: no manifest ctas array, the
        # manuscript carries the markers, the manifest the destination,
        # and the letter carries one extra prose link to the same
        # destination that is NOT a CTA and must not be counted.
        with tempfile.TemporaryDirectory() as td:
            result = run_copy_handoff(
                td, {"cta_destination": "#join", "offer_name": "X"},
                public_with_links(SEVEN_LABELS),
                manuscript_with_markers(SEVEN_LABELS))
            self.assertIsNone(result, f"the run's shape must pass: {result}")

    def test_manifest_ctas_inventory_resolves(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = {"cta_destination": "#join",
                        "ctas": [{"section": str(i + 1), "label": label}
                                 for i, label in enumerate(SEVEN_LABELS)]}
            result = run_copy_handoff(td, manifest,
                                      public_with_links(SEVEN_LABELS),
                                      manuscript_with_markers(SEVEN_LABELS))
            self.assertIsNone(result)

    def test_missing_link_fails_by_label(self):
        with tempfile.TemporaryDirectory() as td:
            labels = SEVEN_LABELS[:-1]  # last CTA never made it to the public file
            result = run_copy_handoff(
                td, {"cta_destination": "#join"},
                public_with_links(labels),
                manuscript_with_markers(SEVEN_LABELS))
            self.assertIsNotNone(result)
            self.assertIn("Join and Build My Team", result)

    def test_wrong_destination_fails(self):
        with tempfile.TemporaryDirectory() as td:
            public = public_with_links(SEVEN_LABELS, destination="#elsewhere")
            result = run_copy_handoff(
                td, {"cta_destination": "#join"}, public,
                manuscript_with_markers(SEVEN_LABELS))
            self.assertIsNotNone(result)
            self.assertIn("#join", result)

    def test_manifest_and_manuscript_inventories_must_agree(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = {"cta_destination": "#join",
                        "ctas": [{"section": "1", "label": "A Different Label"}]}
            result = run_copy_handoff(
                td, manifest, public_with_links(SEVEN_LABELS),
                manuscript_with_markers(SEVEN_LABELS))
            self.assertIsNotNone(result)
            self.assertIn("does not match", result)
            self.assertIn("A Different Label", result)

    def test_cta_without_any_destination_fails(self):
        with tempfile.TemporaryDirectory() as td:
            result = run_copy_handoff(
                td, {}, public_with_links(SEVEN_LABELS),
                manuscript_with_markers(SEVEN_LABELS))
            self.assertIsNotNone(result)
            self.assertIn("no destination", result)

    def test_per_entry_destination_override_resolves(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = {"cta_destination": "#join",
                        "ctas": [{"section": "1", "label": "Build My AI Workforce",
                                  "destination": "#register"}]}
            manuscript = "## Section 1: fixture\n\n[CTA BUTTON: Build My AI Workforce]\n"
            public = "[Build My AI Workforce](#register)\n"
            result = run_copy_handoff(td, manifest, public, manuscript)
            self.assertIsNone(result)

    def test_legacy_stub_run_passes_vacuously(self):
        with tempfile.TemporaryDirectory() as td:
            result = run_copy_handoff(td, {}, "x", "x")
            self.assertIsNone(result)

    def test_copy_stage_contract_wires_the_gate(self):
        contract = json.loads((ROOT / "references" / "stage-contract.json").read_text(encoding="utf-8"))
        validators = contract["stages"]["copy"]["validators"]
        self.assertTrue(any(v.startswith("gate:copy_handoff") for v in validators))
        self.assertIn("public-copy.md", contract["stages"]["copy"].get("note", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
