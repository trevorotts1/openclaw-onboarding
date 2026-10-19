#!/usr/bin/env python3
"""Item 15 (Update Plan): wireframe and mockup gates fail on named traits.

The wireframe gate (scripts/validate_wireframe.py) fails when any
section lacks its number and name annotation (W1), its printed type
specs (W2), its header strip (W5, first section), or its behavior
notes (W6); when any image slot lacks its ratio plus art-direction
label (W3); and when a slice's measured colors fall outside the brand
palette (W4). The mockup gate (scripts/validate_mockup_slots.py, a
final-mockups validator) fails when any slot traces, through the
section generation record, to neither a generated image file nor a
placed supplied asset under Item 3's supplied-asset record (M1).
Mockup traits bind at final-mockups only.

Pins:
  (a) a fully annotated, brand-colored wireframe fixture passes;
  (b) the Item 14 deficient wireframe fixture (an unannotated
      wireframe: no numbers/names, no type specs, no header strip, no
      behavior notes, unlabeled slots) fails at the gate with W1, W2,
      W3, W5, and W6 each named, per section and per slot;
  (c) an off-brand slice fails naming W4 and its section;
  (d) a fully generated mockup (plus one placed supplied asset) passes
      the mockup gate, and the stage contract wires the validator and
      the generation record into final-mockups;
  (e) the Item 14 deficient mockup fixture (a mockup with a
      placeholder slot) fails naming M1 and the slot; a mockup with no
      generation record at all (the School of AI run's form) fails
      every slot by name;
  (f) supplied-asset discipline: a supplied sha256 mismatch, a
      supplied claim on a non-supplied inventory entry, and a supplied
      slot traced as generated each fail by name;
  (g) mutation-scope pin: the layout proof stage (visual-mockup) is
      never a mockup-gate target -- the contract carries the
      validate_mockup_slots validator on final-mockups only.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
VALIDATE_WIREFRAME = ROOT / "scripts" / "validate_wireframe.py"
VALIDATE_MOCKUP = ROOT / "scripts" / "validate_mockup_slots.py"
CONTRACT = json.loads((ROOT / "references" / "stage-contract.json").read_text(encoding="utf-8"))
STAGES = CONTRACT["stages"]

NAVY = (26, 26, 46)        # brand palette navy  #1A1A2E
GOLD = (201, 162, 39)      # brand palette gold  #C9A227
CREAM = (245, 240, 232)    # brand palette cream #F5F0E8
OFF_BRAND = (123, 47, 255)  # saturated purple, in no palette


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data, encoding="utf-8")


def make_png(path, width, height, color, chip=None):
    """A flat slice; with `chip` it also carries a section chip and a CTA-like
    accent band in that colour (SPF016: a real slice is never colourless)."""
    from PIL import Image, ImageDraw
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (width, height), color)
    if chip:
        draw = ImageDraw.Draw(img)
        draw.rectangle([40, 40, 240, 100], fill=chip)
        draw.rectangle([0, 600, width, 1000], fill=chip)
    img.save(path)


def annotated_section(section_id, number, name, slot_id, ratio, direction,
                      header=False):
    section = {
        "section_id": section_id, "section_number": number,
        "section_name": name, "copy_block_ids": [f"{section_id}-copy"],
        "image_slot_ids": [slot_id] if slot_id else [],
        "reference_traits": [],
        "type_specs": {"h1": "64px", "h2": "32px", "body": "18px", "cta": "18px"},
        "behavior_notes": "No CTA" if number % 2 == 0 else "CTA before portrait on mobile",
        "slot_labels": ({slot_id: {"aspect_ratio": ratio, "art_direction": direction}}
                        if slot_id else {}),
    }
    if header:
        section["header_strip"] = {"page_width_px": 1440, "content_width_px": 1200}
    return section


def good_wireframe_run(td):
    run = Path(td) / "run"
    write(run / "intake.json", json.dumps({"brand_owner": "blackceo"}))  # SPF019: BlackCEO fallback palette
    write(run / "copy" / "copy-manifest.json", json.dumps(
        {"sections": [{"section_id": "hero"}, {"section_id": "offer"}]}))
    write(run / "desktop-wireframe" / "image-inventory.json", json.dumps(
        {"images": [{"id": "IMG-001", "aspect_ratio": "16:9"},
                    {"id": "IMG-002", "aspect_ratio": "4:5"}]}))
    plan = [annotated_section("hero", 1, "Hero", "IMG-001", "16:9",
                              "Founder portrait in hero frame", header=True),
            annotated_section("offer", 2, "Offer", "IMG-002", "4:5",
                              "Product still life on cream")]
    write(run / "desktop-wireframe" / "section-plan.json", json.dumps(plan))
    # Heights sum to 17,000px, above the 16,736px desktop page floor: the
    # compliant fixture is a real long-scroll page.
    make_png(run / "desktop-wireframe" / "section-01.png", 1440, 9000, NAVY, chip=GOLD)
    make_png(run / "desktop-wireframe" / "section-02.png", 1440, 8000, CREAM, chip=GOLD)
    write(run / "desktop-wireframe" / "wireframe-full.png", "stub")
    write(run / "desktop-wireframe" / "wireframe.pdf", "stub")
    return run, plan


def deficient_wireframe_run(td):
    """The Item 14 deficient fixture in gate form: the Simulator Room
    run's unannotated wireframe -- sections and slots named by id only,
    no annotations, no slot labels."""
    run = Path(td) / "run"
    write(run / "intake.json", json.dumps({"brand_owner": "blackceo"}))  # SPF019: BlackCEO fallback palette
    write(run / "copy" / "copy-manifest.json", json.dumps(
        {"sections": [{"section_id": "hero"}, {"section_id": "offer"}]}))
    write(run / "desktop-wireframe" / "image-inventory.json", json.dumps(
        {"images": [{"id": "IMG-001", "aspect_ratio": "16:9"},
                    {"id": "IMG-002", "aspect_ratio": "4:5"}]}))
    plan = [{"section_id": "hero", "copy_block_ids": ["hero-copy"],
             "image_slot_ids": ["IMG-001"], "reference_traits": []},
            {"section_id": "offer", "copy_block_ids": ["offer-copy"],
             "image_slot_ids": ["IMG-002"], "reference_traits": []}]
    write(run / "desktop-wireframe" / "section-plan.json", json.dumps(plan))
    make_png(run / "desktop-wireframe" / "section-01.png", 1440, 300, NAVY)
    make_png(run / "desktop-wireframe" / "section-02.png", 1440, 300, NAVY)
    write(run / "desktop-wireframe" / "wireframe-full.png", "stub")
    write(run / "desktop-wireframe" / "wireframe.pdf", "stub")
    return run


def run_wireframe(run):
    return subprocess.run([PY, str(VALIDATE_WIREFRAME), str(run), "desktop-wireframe"],
                          text=True, capture_output=True)


def mockup_run(td, record, inventory=None, plan_sections=("hero", "offer")):
    run = Path(td) / "run"
    if inventory is None:
        inventory = {"images": [{"id": "IMG-001", "aspect_ratio": "16:9"},
                                 {"id": "IMG-002", "aspect_ratio": "4:5"}]}
    write(run / "desktop-wireframe" / "image-inventory.json", json.dumps(inventory))
    plan = [{"section_id": "hero", "copy_block_ids": [], "image_slot_ids": ["IMG-001"],
             "reference_traits": []},
            {"section_id": "offer", "copy_block_ids": [], "image_slot_ids": ["IMG-002"],
             "reference_traits": []}]
    write(run / "desktop-wireframe" / "section-plan.json", json.dumps(plan))
    write(run / "image-generation-qc" / "Image-001.png", b"generated-001")
    write(run / "image-generation-qc" / "Image-002.png", b"generated-002")
    if record is not None:
        write(run / "final-mockups" / "generation-record.json", json.dumps(record))
    return run


def run_mockup(run):
    return subprocess.run([PY, str(VALIDATE_MOCKUP), str(run), "final-mockups"],
                          text=True, capture_output=True)


GENERATED_RECORD = {"stage": "final-mockups", "sections": [
    {"section_id": "hero", "slots": [
        {"slot_id": "IMG-001", "source": "generated",
         "file": "image-generation-qc/Image-001.png"}]},
    {"section_id": "offer", "slots": [
        {"slot_id": "IMG-002", "source": "generated",
         "file": "image-generation-qc/Image-002.png"}]}]}


class WireframeTraitGateTest(unittest.TestCase):
    def test_compliant_wireframe_passes(self):
        with tempfile.TemporaryDirectory() as td:
            run, _ = good_wireframe_run(td)
            proc = run_wireframe(run)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("W1/W2/W5/W6", proc.stdout)
            self.assertIn("W3", proc.stdout)
            self.assertIn("W4", proc.stdout)

    def test_deficient_wireframe_fails_on_named_traits(self):
        with tempfile.TemporaryDirectory() as td:
            run = deficient_wireframe_run(td)
            proc = run_wireframe(run)
            self.assertEqual(proc.returncode, 1, proc.stdout)
            for trait in ("W1", "W2", "W3", "W5", "W6"):
                self.assertIn(trait, proc.stdout, proc.stdout)
            self.assertIn("'hero'", proc.stdout)
            self.assertIn("'offer'", proc.stdout)
            self.assertIn("IMG-001", proc.stdout)
            self.assertIn("IMG-002", proc.stdout)
            self.assertIn("art direction", proc.stdout)

    def test_missing_type_spec_and_behavior_note_fail_by_name(self):
        with tempfile.TemporaryDirectory() as td:
            run, plan = good_wireframe_run(td)
            plan[1]["type_specs"] = {"h1": "48px"}
            del plan[0]["behavior_notes"]
            write(run / "desktop-wireframe" / "section-plan.json", json.dumps(plan))
            proc = run_wireframe(run)
            self.assertEqual(proc.returncode, 1, proc.stdout)
            self.assertIn("W2", proc.stdout)
            self.assertIn("W6", proc.stdout)
            self.assertIn("'offer'", proc.stdout)

    def test_slot_label_ratio_mismatch_fails_w3(self):
        with tempfile.TemporaryDirectory() as td:
            run, plan = good_wireframe_run(td)
            plan[0]["slot_labels"]["IMG-001"]["aspect_ratio"] = "1:1"
            write(run / "desktop-wireframe" / "section-plan.json", json.dumps(plan))
            proc = run_wireframe(run)
            self.assertEqual(proc.returncode, 1, proc.stdout)
            self.assertIn("W3", proc.stdout)
            self.assertIn("IMG-001", proc.stdout)

    def test_off_brand_slice_fails_w4_by_section(self):
        with tempfile.TemporaryDirectory() as td:
            run, _ = good_wireframe_run(td)
            make_png(run / "desktop-wireframe" / "section-02.png", 1440, 300, OFF_BRAND)
            proc = run_wireframe(run)
            self.assertEqual(proc.returncode, 1, proc.stdout)
            self.assertIn("W4", proc.stdout)
            self.assertIn("'offer'", proc.stdout)
            self.assertIn("off-brand", proc.stdout)


class MockupTraitGateTest(unittest.TestCase):
    def test_fully_generated_mockup_passes(self):
        with tempfile.TemporaryDirectory() as td:
            run = mockup_run(td, GENERATED_RECORD)
            proc = run_mockup(run)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("zero placeholder slots (M1)", proc.stdout)

    def test_placeholder_slot_fails_m1_by_name(self):
        record = json.loads(json.dumps(GENERATED_RECORD))
        record["sections"][1]["slots"] = [
            {"slot_id": "IMG-002", "source": "placeholder", "file": None}]
        with tempfile.TemporaryDirectory() as td:
            run = mockup_run(td, record)
            proc = run_mockup(run)
            self.assertEqual(proc.returncode, 1, proc.stdout)
            self.assertIn("M1", proc.stdout)
            self.assertIn("IMG-002", proc.stdout)
            self.assertIn("placeholder slot", proc.stdout)

    def test_missing_generation_record_fails_every_slot(self):
        # The School of AI run's mockup form under the new definitions:
        # slots exist, no generation record traces any of them.
        with tempfile.TemporaryDirectory() as td:
            run = mockup_run(td, None)
            proc = run_mockup(run)
            self.assertEqual(proc.returncode, 1, proc.stdout)
            self.assertIn("IMG-001", proc.stdout)
            self.assertIn("IMG-002", proc.stdout)
            self.assertIn("generation-record.json", proc.stdout)

    def test_generated_trace_to_wrong_file_fails(self):
        record = json.loads(json.dumps(GENERATED_RECORD))
        record["sections"][0]["slots"][0]["file"] = "image-generation-qc/Image-002.png"
        with tempfile.TemporaryDirectory() as td:
            run = mockup_run(td, record)
            proc = run_mockup(run)
            self.assertEqual(proc.returncode, 1, proc.stdout)
            self.assertIn("IMG-001", proc.stdout)

    def test_supplied_asset_traces_and_sha_discipline(self):
        logo_bytes = b"supplied-logo-bytes"
        sha = hashlib.sha256(logo_bytes).hexdigest()
        inventory = {"images": [{"id": "IMG-001", "aspect_ratio": "16:9"},
                                {"id": "IMG-002", "aspect_ratio": "4:5",
                                 "source": "supplied-logo"}]}
        record = {"stage": "final-mockups", "sections": [
            {"section_id": "hero", "slots": [
                {"slot_id": "IMG-001", "source": "generated",
                 "file": "image-generation-qc/Image-001.png"}]},
            {"section_id": "offer", "slots": [
                {"slot_id": "IMG-002", "source": "supplied",
                 "file": "final-mockups/assets/logo.png",
                 "supplied_asset": True, "sha256": sha}]}]}
        with tempfile.TemporaryDirectory() as td:
            run = mockup_run(td, record, inventory=inventory)
            write(run / "final-mockups" / "assets" / "logo.png", logo_bytes)
            proc = run_mockup(run)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            # sha mismatch fails by name
            write(run / "final-mockups" / "assets" / "logo.png", b"different-bytes")
            proc = run_mockup(run)
            self.assertEqual(proc.returncode, 1, proc.stdout)
            self.assertIn("IMG-002", proc.stdout)
            self.assertIn("sha256 mismatch", proc.stdout)

    def test_supplied_claim_on_generated_inventory_entry_fails(self):
        record = json.loads(json.dumps(GENERATED_RECORD))
        record["sections"][1]["slots"] = [
            {"slot_id": "IMG-002", "source": "supplied",
             "file": "image-generation-qc/Image-002.png",
             "supplied_asset": True,
             "sha256": hashlib.sha256(b"generated-002").hexdigest()}]
        with tempfile.TemporaryDirectory() as td:
            run = mockup_run(td, record)
            proc = run_mockup(run)
            self.assertEqual(proc.returncode, 1, proc.stdout)
            self.assertIn("IMG-002", proc.stdout)
            self.assertIn("not a supplied entry", proc.stdout)

    def test_supplied_slot_traced_as_generated_fails(self):
        inventory = {"images": [{"id": "IMG-001", "aspect_ratio": "16:9"},
                                {"id": "IMG-002", "aspect_ratio": "4:5",
                                 "source": "supplied-founder-photo"}]}
        with tempfile.TemporaryDirectory() as td:
            run = mockup_run(td, GENERATED_RECORD, inventory=inventory)
            proc = run_mockup(run)
            self.assertEqual(proc.returncode, 1, proc.stdout)
            self.assertIn("IMG-002", proc.stdout)
            self.assertIn("never generated", proc.stdout)


class ContractWiringTest(unittest.TestCase):
    def test_final_mockups_contract_wires_the_gate(self):
        spec = STAGES["final-mockups"]
        self.assertIn("python3 scripts/validate_mockup_slots.py {run_dir} final-mockups",
                      spec["validators"])
        globs = [a["glob"] for a in spec["artifacts"]]
        self.assertIn("final-mockups/generation-record.json", globs)
        self.assertIn("M1", spec["purpose"])
        self.assertIn("bind at this stage only", spec["purpose"])

    def test_mockup_gate_binds_at_final_mockups_only(self):
        for stage, spec in STAGES.items():
            wired = any("validate_mockup_slots" in v
                        for v in spec.get("validators", []))
            if stage == "final-mockups":
                self.assertTrue(wired)
            else:
                self.assertFalse(wired, f"{stage} must not carry the mockup slot gate")


if __name__ == "__main__":
    unittest.main(verbosity=2)
