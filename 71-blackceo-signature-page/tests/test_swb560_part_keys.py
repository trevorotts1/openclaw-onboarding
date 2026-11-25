#!/usr/bin/env python3
"""SWB-560 (1.3.57): each mockup part's request key covers only that part's own inputs.

final-mockups and visual-mockup draw a desktop and a mobile slice per section. Before this version a
mobile-only design change re-keyed the section's desktop slice too (one shared key per section), and
two repairs each redrew all ten parts (about 290 to 300 credits each) when only one or two needed work.
Now a part's key is section_revision(..., platform): the desktop key leaves out what only the phone
slice reads (its mobile-only design text and its frame ratio); a mobile key carries everything; shared
inputs (stage template, design prose, brand, model, style, design board, input_extra, spec version,
part order and count) re-key every part.
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
import build_production_request as bpr  # noqa: E402

STAGE = "final-mockups"
PARTS = [(t, w, h) for t, w, h in exe.LAYOUT[STAGE]]


def request():
    sections = []
    for n in range(1, 6):
        sections.append({"section_id": str(n), "section_name": f"Section {n}", "copy": f"Copy number {n} is here.",
                         "cta": "", "slots": [{"slot_id": f"IMG-00{n}", "aspect_ratio": "1:1"}],
                         "composition_role": "hero", "ground": "hero",
                         "layout": f"Base layout {n}. Override text {n}.", "type_specs": {"H1": "38 px"}})
    return {
        "model": "gpt-image-2-6/sunburst-image-to-image", "style": "", "copy_version": "thank-you",
        "references": [], "sections": sections, "page_role": "thank_you", "design_style": "A",
        "stage_prompts": {STAGE: "Part {section_number} of {section_total}. {layout}"},
        "design_board": {"page_role": "thank_you", "brand_name": "Brand", "positioning_line": "Line"},
        "input_extra": {"resolution": "4K"},
        "layout_overrides": {"source": "/x/overrides.json", "sha256": "a" * 64, "stage": STAGE,
                             "applied": [{"section_id": str(n), "appended_text": f"Override text {n}."}
                                         for n in range(1, 6)]},
        "metadata": {"stage": STAGE, "copy_version": "thank-you", "page_role": "thank_you",
                     "page_kind": None, "section_count": 5, "canonical_ids": ["1", "2", "3", "4", "5"],
                     "char_budget": {"per_section": {str(n): 18000 + n for n in range(1, 6)}}},
        "_step_band": {"section_id": "4", "name": "What happens next", "count": 5},
        "_brand_block": "BRAND COLORS: red #ED1C24", "_hypersat": {"hero": "#ED1C24", "dark": "#111111", "light": "#FFFFFF", "accent": "#ED1C24"},
    }


def keys(req, run):
    """{(viewport label, part number): key} for all ten parts."""
    out = {}
    for i, s in enumerate(req["sections"], start=1):
        for template, w, h in PARTS:
            ident = exe.base_identity(run, req, stage=STAGE, slot=template.format(n=i), viewport=f"{w}x{h}",
                                      section=s, index=i)
            out[(template.split("/")[0], i)] = ident["plan_revision"]
    return out


def edit_mobile(req, n, text, ratio=None):
    """What the builder does for a mobile-only override entry: section.layout_mobile, an applied row
    carrying mobile_text, the file sha256 and the char budget numbers."""
    sec = req["sections"][n - 1]
    sec["layout_mobile"] = (sec.get("layout_mobile", "") + " " + text).strip()
    row = req["layout_overrides"]["applied"][n - 1]
    row["mobile_text"] = sec["layout_mobile"]
    row["viewport"] = "mobile"
    if ratio:
        sec["layout_aspect_ratio"] = {"stage": STAGE, "viewport": "mobile", "ratio": ratio}
        row["aspect_ratio"] = ratio
    req["layout_overrides"]["sha256"] = hashlib.sha256(text.encode()).hexdigest()
    req["metadata"]["char_budget"]["per_section"][str(n)] += 91


def changed(a, b):
    return sorted(k for k in a if a[k] != b[k])


class PartKeys(unittest.TestCase):
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
            {"id": f"IMG-00{n}", "section_id": str(n), "aspect_ratio": "1:1"} for n in range(1, 6)]}))

    def tearDown(self):
        self._t.cleanup()

    def test_identical_inputs_identical_keys_and_ten_distinct(self):
        a, b = keys(request(), self.run), keys(request(), self.run)
        self.assertEqual(a, b)
        self.assertEqual(len(set(a.values())), 10, "ten parts have ten different keys")

    def test_desktop_and_mobile_of_one_section_are_separate_keys(self):
        k = keys(request(), self.run)
        for n in range(1, 6):
            self.assertNotEqual(k[("desktop", n)], k[("mobile", n)])
        a = exe.base_identity(self.run, request(), stage=STAGE, slot="desktop/part-01.png", viewport="1440x760",
                              section=request()["sections"][0], index=1)
        b = exe.base_identity(self.run, request(), stage=STAGE, slot="mobile/part-01.png", viewport="390x1080",
                              section=request()["sections"][0], index=1)
        self.assertNotEqual(exe._target_slug(a), exe._target_slug(b))

    def test_mobile_part2_text_rekeys_only_mobile_part2(self):
        base = keys(request(), self.run)
        req = request()
        edit_mobile(req, 2, "Print the card once.")
        self.assertEqual(changed(base, keys(req, self.run)), [("mobile", 2)])

    def test_mobile_part2_frame_ratio_rekeys_only_mobile_part2(self):
        base = keys(request(), self.run)
        req = request()
        req["sections"][1]["layout_aspect_ratio"] = {"stage": STAGE, "viewport": "mobile", "ratio": "1:1"}
        req["layout_overrides"]["applied"][1].update({"aspect_ratio": "1:1", "viewport": "mobile"})
        self.assertEqual(changed(base, keys(req, self.run)), [("mobile", 2)])

    def test_mobile_parts_1_and_2_together(self):
        base = keys(request(), self.run)
        req = request()
        edit_mobile(req, 1, "one")
        edit_mobile(req, 2, "two")
        self.assertEqual(changed(base, keys(req, self.run)), [("mobile", 1), ("mobile", 2)])

    def test_shared_layout_text_of_a_section_rekeys_both_of_its_parts(self):
        base = keys(request(), self.run)
        req = request()
        req["sections"][2]["layout"] += " shared change"
        req["layout_overrides"]["applied"][2]["appended_text"] += " shared change"
        self.assertEqual(changed(base, keys(req, self.run)), [("desktop", 3), ("mobile", 3)])

    def test_shared_inputs_rekey_all_ten(self):
        base = keys(request(), self.run)
        for name, edit in (
                ("design board", lambda r: r["design_board"].update(positioning_line="Another line")),
                ("stage template", lambda r: r["stage_prompts"].update({STAGE: r["stage_prompts"][STAGE] + " X"})),
                ("brand", lambda r: r.update(_brand_block="BRAND COLORS: blue #0000FF")),
                ("model", lambda r: r.update(model="other/model")),
                ("style", lambda r: r.update(style="bold")),
                ("input_extra", lambda r: r["input_extra"].update(resolution="2K")),
                ("spec version", lambda r: r.update(copy_version="thank-you-v2"))):
            req = request()
            edit(req)
            self.assertEqual(len(changed(base, keys(req, self.run))), 10, name)

    def test_part_order_and_count_rekey_all(self):
        base = keys(request(), self.run)
        req = request()
        req["sections"].append(copy.deepcopy(req["sections"][0]) | {"section_id": "6"})
        new = keys(req, self.run)
        self.assertTrue(all(base[k] != new[k] for k in base))

    def test_own_copy_slot_and_inventory_rows_rekey_only_that_section(self):
        base = keys(request(), self.run)
        req = request()
        req["sections"][3]["slots"][0]["art_direction"] = "warm"
        self.assertEqual(changed(base, keys(req, self.run)), [("desktop", 4), ("mobile", 4)])
        inv = self.run / "desktop-wireframe" / "image-inventory.json"
        data = json.loads(inv.read_text())
        data["images"][4]["art_direction"] = "cool"
        inv.write_text(json.dumps(data))
        self.assertEqual(changed(base, keys(request(), self.run)), [("desktop", 5), ("mobile", 5)])

    def test_mobile_key_is_the_swb550_scope_for_mobile_only_stages(self):
        req = request()
        s = req["sections"][0]
        self.assertEqual(exe.section_revision(self.run, req, s, 1),
                         exe.section_revision(self.run, req, s, 1, "mobile"))

    def test_viewport_platform(self):
        self.assertEqual(exe.viewport_platform("1440x760"), "desktop")
        self.assertEqual(exe.viewport_platform("390x1080"), "mobile")
        self.assertEqual(exe.viewport_platform("garbage"), "desktop")

    def test_prompt_mobile_text_reaches_only_the_mobile_prompt(self):
        req = request()
        edit_mobile(req, 1, "MOBILE-ONLY-LINE")
        s = req["sections"][0]
        mobile = exe.stage_prompt(STAGE, s, 1, 390, req, "3:4", platform="mobile")
        desktop = exe.stage_prompt(STAGE, s, 1, 1440, req, "3:4", platform="desktop")
        self.assertIn("MOBILE-ONLY-LINE", mobile)
        self.assertNotIn("MOBILE-ONLY-LINE", desktop)
        plain = exe.stage_prompt(STAGE, request()["sections"][0], 1, 1440, request(), "3:4")
        self.assertEqual(desktop, plain, "a desktop prompt with no mobile text is byte-identical to before")

    def test_resume_only_for_unchanged_parts(self):
        req = request()
        for part in ("desktop/part-02.png", "mobile/part-02.png"):
            out = self.run / STAGE / part
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(part.encode())
            vp = "1440x760" if part.startswith("desktop") else "390x1080"
            base = exe.base_identity(self.run, req, stage=STAGE, slot=part, viewport=vp,
                                     section=req["sections"][1], index=2)
            ident = exe.allocate_attempt(self.run, base)
            exe.write_attempt_result(self.run, ident, {"file": f"{STAGE}/{part}", "sha256": exe.sha256(out),
                                                       "state": "settled", "attempt": ident["attempt"]})
        edit_mobile(req, 2, "mobile repair")
        d = exe.base_identity(self.run, req, stage=STAGE, slot="desktop/part-02.png", viewport="1440x760",
                              section=req["sections"][1], index=2)
        m = exe.base_identity(self.run, req, stage=STAGE, slot="mobile/part-02.png", viewport="390x1080",
                              section=req["sections"][1], index=2)
        self.assertIsNotNone(exe.reusable_record(self.run, d, self.run / STAGE / "desktop/part-02.png"))
        self.assertIsNone(exe.reusable_record(self.run, m, self.run / STAGE / "mobile/part-02.png"))

    def test_prewired_attempt_adopted_per_part_only_on_same_prompt_and_bytes(self):
        req = request()
        out = self.run / STAGE / "mobile" / "part-01.png"
        out.parent.mkdir(parents=True)
        out.write_bytes(b"bytes")
        legacy = exe.base_identity(self.run, req, stage=STAGE, slot="mobile/part-01.png", viewport="390x1080")
        ident = exe.allocate_attempt(self.run, legacy)
        prompt = "p"
        exe.write_attempt_result(self.run, ident, {"file": f"{STAGE}/mobile/part-01.png", "sha256": exe.sha256(out),
                                                   "state": "settled", "attempt": ident["attempt"],
                                                   "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()})
        new = exe.base_identity(self.run, req, stage=STAGE, slot="mobile/part-01.png", viewport="390x1080",
                                section=req["sections"][0], index=1)
        self.assertIsNotNone(exe.adopt_prewired_attempt(self.run, new, out, prompt))
        self.assertIsNone(exe.adopt_prewired_attempt(self.run, new, out, prompt + "x"))
        desk = exe.base_identity(self.run, req, stage=STAGE, slot="desktop/part-01.png", viewport="1440x760",
                                 section=req["sections"][0], index=1)
        self.assertIsNone(exe.adopt_prewired_attempt(self.run, desk, self.run / STAGE / "desktop" / "part-01.png", prompt))


class OverrideBuilder(unittest.TestCase):
    def _load(self, doc, stage=STAGE):
        sections = [{"section_id": str(n), "layout": f"L{n}", "slots": [{"slot_id": f"I{n}", "aspect_ratio": "1:1"}]}
                    for n in range(1, 4)]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "o.json"
            p.write_text(json.dumps(doc))
            return bpr.load_layout_overrides(p, stage, sections), sections

    def test_mobile_layout_is_kept_apart_from_the_shared_layout(self):
        res, secs = self._load({STAGE: {"1": {"mobile_layout": "phone text", "mobile_negatives": "no chips"}}})
        self.assertEqual(secs[0]["layout"], "L1")
        self.assertEqual(secs[0]["layout_mobile"], "phone text\nNEGATIVES: no chips")
        self.assertEqual(res["applied"][0]["mobile_text"], secs[0]["layout_mobile"])
        self.assertEqual(res["applied"][0]["appended_text"], "")

    def test_mobile_layout_beside_layout(self):
        res, secs = self._load({STAGE: {"2": {"layout": "both", "mobile_layout": "phone"}}})
        self.assertEqual(secs[1]["layout"], "L2\nboth")
        self.assertEqual(secs[1]["layout_mobile"], "phone")

    def test_refusals(self):
        for doc in ({STAGE: {"1": {"mobile_layout": "  "}}},
                    {STAGE: {"1": {"mobile_negatives": "x"}}},
                    {"desktop-wireframe": {"1": {"layout": "x", "mobile_layout": "y"}}},
                    {STAGE: {"1": {"mobile_layout": 5}}}):
            stage = next(iter(doc))
            with self.assertRaises(bpr.BuildError):
                self._load(doc, stage)


if __name__ == "__main__":
    unittest.main()
