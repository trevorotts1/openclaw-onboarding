#!/usr/bin/env python3
"""SWB-550 (1.3.56): each section's request key covers only that section's own inputs.

Before: the job folder name and request key of every slice hashed the WHOLE request (every
section's layout text, the layout-overrides file's sha256, per-section char budgets), so one
changed override re-keyed all five sections and the executor generated all five again. Now a
stage's slice key is section_revision(): that section's own entry, its own override row, its own
copy-manifest and image-inventory rows, plus what every section shares (stage template, design
prose, brand, model, style, spec version, section order).
"""
import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ["SKILL71_FIXTURE_RUN"] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import stage_executor as exe  # noqa: E402

STAGE = "mobile-tablet"


def request():
    sections = []
    for n in range(1, 6):
        sections.append({"section_id": str(n), "section_name": f"Section {n}", "copy": f"Copy {n}",
                         "cta": "", "slots": [], "composition_role": "hero", "ground": "hero",
                         "layout": f"Base layout {n}. Override text {n}.", "type_specs": {"H1": "38 px"}})
    return {
        "model": "gpt-image-2-6/sunburst-image-to-image", "style": "", "copy_version": "thank-you",
        "references": [], "sections": sections, "page_role": "thank_you", "design_style": "A",
        "stage_prompts": {STAGE: "Sheet {section_number} of {section_total}. {layout}"},
        "layout_overrides": {"source": "/x/overrides.json", "sha256": "a" * 64, "stage": STAGE,
                             "applied": [{"section_id": str(n), "appended_text": f"Override text {n}."}
                                         for n in range(1, 6)]},
        "metadata": {"stage": STAGE, "copy_version": "thank-you", "page_role": "thank_you",
                     "page_kind": None, "section_count": 5, "canonical_ids": ["1", "2", "3", "4", "5"],
                     "provider_calls": 0,
                     "char_budget": {"per_section": {str(n): 18000 + n for n in range(1, 6)},
                                     "min_seen": 18001, "max_seen": 18005}},
        "_step_band": {"section_id": "4", "name": "What happens next", "count": 5},
        "_brand_block": "BRAND COLORS: red #ED1C24", "_hypersat": {"accent": "#ED1C24"},
    }


def keys(req, run):
    return [exe.base_identity(run, req, stage=STAGE, slot=f"section-{i:02d}.png", viewport="390x1080",
                              section=s, index=i)["plan_revision"]
            for i, s in enumerate(req["sections"], start=1)]


def edit_override(req, n, text):
    """What the builder does when one section's override text changes: the section's layout, its applied
    row and the whole file's sha256 change, plus the char budget numbers of the metadata."""
    req["sections"][n - 1]["layout"] += " " + text
    req["layout_overrides"]["applied"][n - 1]["appended_text"] += " " + text
    req["layout_overrides"]["sha256"] = hashlib.sha256(text.encode()).hexdigest()
    req["metadata"]["char_budget"]["per_section"][str(n)] += 77
    req["metadata"]["char_budget"]["max_seen"] += 77


class SectionKeys(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.run = Path(self._t.name) / "thank_you-run"
        (self.run / "copy").mkdir(parents=True)
        (self.run / "desktop-wireframe").mkdir()
        (self.run / "intake.json").write_text(json.dumps({"run_id": "r1"}))
        (self.run / "copy" / "copy-manifest.json").write_text(json.dumps({
            "copy_version": "thank-you", "sections": [{"id": str(n), "name": f"S{n}"} for n in range(1, 6)],
            "ctas": [{"section": "1", "label": "Go"}, {"section": "3", "label": "Open"}]}))
        (self.run / "desktop-wireframe" / "image-inventory.json").write_text(json.dumps({"images": [
            {"id": "IMG-001", "section_id": "1", "aspect_ratio": "1:1"}]}))

    def tearDown(self):
        self._t.cleanup()

    def test_identical_inputs_identical_keys(self):
        a, b = keys(request(), self.run), keys(request(), self.run)
        self.assertEqual(a, b)
        self.assertEqual(len(set(a)), 5, "five sections must have five different keys")

    def test_section3_override_changes_only_section3(self):
        base = keys(request(), self.run)
        req = request()
        edit_override(req, 3, "Print the heading once.")
        new = keys(req, self.run)
        self.assertEqual([i for i in range(5) if base[i] != new[i]], [2])

    def test_each_section_alone(self):
        base = keys(request(), self.run)
        for n in range(1, 6):
            req = request()
            edit_override(req, n, "x")
            new = keys(req, self.run)
            self.assertEqual([i + 1 for i in range(5) if base[i] != new[i]], [n])

    def test_shared_prose_changes_all(self):
        base = keys(request(), self.run)
        req = request()
        req["stage_prompts"][STAGE] += " Shared design rule."
        self.assertTrue(all(a != b for a, b in zip(base, keys(req, self.run))))

    def test_brand_changes_all(self):
        base = keys(request(), self.run)
        req = request()
        req["_brand_block"] = "BRAND COLORS: blue #0000FF"
        self.assertTrue(all(a != b for a, b in zip(base, keys(req, self.run))))
        req = request()
        req["_hypersat"] = {"accent": "#0000FF"}
        self.assertTrue(all(a != b for a, b in zip(base, keys(req, self.run))))

    def test_spec_version_model_style_change_all(self):
        base = keys(request(), self.run)
        for field, value in (("copy_version", "thank-you-v2"), ("model", "other/model"),
                             ("design_style", "B"), ("style", "bold")):
            req = request()
            req[field] = value
            self.assertTrue(all(a != b for a, b in zip(base, keys(req, self.run))), field)

    def test_section_order_changes_all(self):
        base = keys(request(), self.run)
        req = request()
        req["sections"].append(copy.deepcopy(req["sections"][0]) | {"section_id": "6"})
        self.assertTrue(all(a != b for a, b in zip(base, keys(req, self.run)[:5])))

    def test_own_copy_and_inventory_rows(self):
        base = keys(request(), self.run)
        manifest = self.run / "copy" / "copy-manifest.json"
        data = json.loads(manifest.read_text())
        data["ctas"][1]["label"] = "Open now"          # section 3's own button row
        manifest.write_text(json.dumps(data))
        new = keys(request(), self.run)
        self.assertEqual([i for i in range(5) if base[i] != new[i]], [2])
        inv = self.run / "desktop-wireframe" / "image-inventory.json"
        data = json.loads(inv.read_text())
        data["images"][0]["art_direction"] = "warm"      # section 1's own slot row
        inv.write_text(json.dumps(data))
        newer = keys(request(), self.run)
        self.assertEqual([i for i in range(5) if new[i] != newer[i]], [0])

    def test_whole_plan_revision_is_unchanged_for_non_section_jobs(self):
        req = request()
        a = exe.base_identity(self.run, req, stage="design-board", slot="board", viewport="1440x760")
        edit_override(req, 3, "x")
        b = exe.base_identity(self.run, req, stage="design-board", slot="board", viewport="1440x760")
        self.assertNotEqual(a["plan_revision"], b["plan_revision"], "a non-section job still keys the whole plan")
        self.assertEqual(exe.plan_revision(self.run, request()), a["plan_revision"])

    def test_unchanged_section_resumes_its_settled_attempt(self):
        req = request()
        out = self.run / STAGE / "section-01.png"
        out.parent.mkdir()
        out.write_bytes(b"png-bytes-1")
        base = exe.base_identity(self.run, req, stage=STAGE, slot="section-01.png", viewport="390x1080",
                                 section=req["sections"][0], index=1)
        ident = exe.allocate_attempt(self.run, base)
        exe.write_attempt_result(self.run, ident, {"file": f"{STAGE}/section-01.png", "sha256": exe.sha256(out),
                                                   "state": "settled", "attempt": ident["attempt"]})
        again = exe.base_identity(self.run, req, stage=STAGE, slot="section-01.png", viewport="390x1080",
                                  section=req["sections"][0], index=1)
        self.assertIsNotNone(exe.reusable_record(self.run, again, out))
        edit_override(req, 3, "section 3 only")           # another section changes: section 1 still resumes
        same = exe.base_identity(self.run, req, stage=STAGE, slot="section-01.png", viewport="390x1080",
                                 section=req["sections"][0], index=1)
        self.assertIsNotNone(exe.reusable_record(self.run, same, out))
        edit_override(req, 1, "section 1 itself")         # its own text changes: new key, no resume
        own = exe.base_identity(self.run, req, stage=STAGE, slot="section-01.png", viewport="390x1080",
                                section=req["sections"][0], index=1)
        self.assertIsNone(exe.reusable_record(self.run, own, out))

    def test_prewired_attempt_adopted_only_on_same_prompt_and_same_bytes(self):
        req = request()
        out = self.run / STAGE / "section-02.png"
        out.parent.mkdir()
        out.write_bytes(b"png-bytes-2")
        legacy = exe.base_identity(self.run, req, stage=STAGE, slot="section-02.png", viewport="390x1080")
        ident = exe.allocate_attempt(self.run, legacy)
        prompt = "the prompt text"
        exe.write_attempt_result(self.run, ident, {
            "file": f"{STAGE}/section-02.png", "sha256": exe.sha256(out), "state": "settled",
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "attempt": ident["attempt"]})
        new = exe.base_identity(self.run, req, stage=STAGE, slot="section-02.png", viewport="390x1080",
                                section=req["sections"][1], index=2)
        self.assertIsNone(exe.reusable_record(self.run, new, out), "the old whole-plan key never matches")
        self.assertIsNotNone(exe.adopt_prewired_attempt(self.run, new, out, prompt))
        self.assertIsNone(exe.adopt_prewired_attempt(self.run, new, out, prompt + " changed"))
        out.write_bytes(b"other-bytes")
        self.assertIsNone(exe.adopt_prewired_attempt(self.run, new, out, prompt))
        other = exe.base_identity(self.run, req, stage="desktop-wireframe", slot="section-02.png",
                                  viewport="390x1080", section=req["sections"][1], index=2)
        out.write_bytes(b"png-bytes-2")
        self.assertIsNone(exe.adopt_prewired_attempt(self.run, other, out, prompt), "another stage never adopts")


if __name__ == "__main__":
    unittest.main()
