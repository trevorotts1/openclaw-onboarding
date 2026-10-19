#!/usr/bin/env python3
"""Composition library: words over images, shaped crops, light full-width fields.

Pins (acceptance checks of unit SPF023):
  1. The hosted reference catalog: every row complete, sha256 unique, the
     bundled-sheet rows match the bundled files, no anti-example is in it,
     mobile slices are at most 780x3000 and pair by section.
  2. composition-treatments.json: all 13 treatments, tokens only (no hex, no
     named color), every role default is a real treatment.
  3. layout-trait-vocabulary.json re-admits the words-over-image and
     break-the-frame families citing Trevor's request.
  4. Prompts: every treatment yields its photo sentence; an overlay section's
     mockup prompt says not to split it; the wireframe negative block allows
     IMG labels; three section roles each get a non-split instruction and
     typed references within the prompt budget.
  5. The wireframe budget gate: 100 percent split fails, a plan meeting the
     budget passes, adjacent repeats and unknown ids fail.
  6. Built-page checks on fixture pages in a real browser (skipped, not failed,
     when Chromium is unavailable): circle passes and a square img labelled
     mask-circle fails; overlay classifies OVERLAY; text over a face fails; a
     textured light field passes and a flat fill fails; a mutation of the circle
     fixture to border-radius:0 turns the check red; light and dark brand token
     sets pass without code changes.
"""
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from brand_fixture import give_blackceo_colors  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# the hosted-reference base is operator-injected at run time; tests use a fake one
os.environ["SKILL71_REFERENCE_MEDIA_BASE"] = "https://media.example.test/demo-account"
comp = _load("composition")
exe = _load("stage_executor")
vp = _load("validate_page")

VS = ROOT / "assets" / "visual-standards"
CATALOG = json.loads((VS / "reference-catalog.json").read_text(encoding="utf-8"))
LIB = json.loads((ROOT / "references" / "composition-treatments.json").read_text(encoding="utf-8"))
SCHEMA_FIELDS = ("id", "type", "viewport", "form", "sections", "traits", "pair", "use",
                 "contains_reference_only_text", "sha256", "media_path", "source")
# rows that hold a signature, a person's name or placeholder tokens (verified by eye and OCR)
MUST_BE_FLAGGED = (["std-hybrid-board", "desktop-annotated-mockup", "lf-desktop-mockup-c",
                    "set-for-life-desktop-mockup", "set-for-life-desktop-wireframe"]
                   + [f"lf-mobile-{k}-{n}" for k in ("wireframe", "mockup")
                      for n in ("s01", "s07a", "s07b", "s07c", "s07d", "s12a", "s12b", "s12c")])
# first 16 hex of the sha256 of the sources the plan keeps OUT of the library
ANTI_EXAMPLE_PREFIXES = ("b6fda360817fa4ed", "3fae3fb2ac4c978f", "cbb23ced83920755")
NAMED_COLORS = ("black", "white", "red", "green", "blue", "gold", "grey", "gray", "yellow",
                "orange", "pink", "purple", "brown", "cream", "ivory", "navy", "teal", "silver",
                "crimson", "maroon", "beige", "tan", "olive", "lime", "aqua", "cyan", "magenta")


class CatalogTests(unittest.TestCase):
    rows = CATALOG["rows"]

    def test_every_row_has_every_field(self):
        for row in self.rows:
            for field in SCHEMA_FIELDS:
                self.assertIn(field, row, f"{row.get('id')} lacks {field}")
            self.assertRegex(row["media_path"], r"^media/[0-9a-f-]+\.png$", row["id"])
            self.assertNotIn("url", row, row["id"])
            self.assertRegex(row["sha256"], r"^[0-9a-f]{64}$", row["id"])
            self.assertIn(row["type"], CATALOG["types"], row["id"])

    def test_sha256_unique_and_ids_unique(self):
        self.assertEqual(len({r["sha256"] for r in self.rows}), len(self.rows))
        self.assertEqual(len({r["id"] for r in self.rows}), len(self.rows))

    def test_no_anti_example_in_the_library(self):
        for row in self.rows:
            for prefix in ANTI_EXAMPLE_PREFIXES:
                self.assertFalse(row["sha256"].startswith(prefix), row["id"])

    def test_bundled_rows_match_the_bundled_bytes(self):
        checked = 0
        for row in self.rows:
            bundle = row.get("source_bundle")
            if not bundle or row["id"].startswith("lf-mobile-mockup-"):
                continue
            digest = hashlib.sha256((VS / bundle).read_bytes()).hexdigest()
            if row["id"] in ("std-hybrid-board", "desktop-annotated-mockup"):
                self.assertEqual(row["sha256"], digest, row["id"])
                checked += 1
        self.assertEqual(checked, 2)

    def test_mobile_slices_fit_and_pair_by_section(self):
        wf = {r["id"].rsplit("-", 1)[1]: r for r in self.rows if r["id"].startswith("lf-mobile-wireframe-")}
        mk = {r["id"].rsplit("-", 1)[1]: r for r in self.rows if r["id"].startswith("lf-mobile-mockup-")}
        self.assertEqual(set(wf), set(mk))
        self.assertTrue(len(wf) >= 20)
        for key, row in list(wf.items()) + list(mk.items()):
            self.assertLessEqual(row["height_px"], 3000, key)
            self.assertEqual(row["width_px"], 780)
        for key in wf:
            self.assertEqual(wf[key]["pair"], f"lf-mobile-mockup-{key}")
            self.assertEqual(wf[key]["sections"], mk[key]["sections"])
        for row in mk.values():
            self.assertIn("counter-example-composition", row["tags"])

    def test_every_pair_points_back(self):
        by_id = {r["id"]: r for r in self.rows}
        for row in self.rows:
            if row["pair"]:
                self.assertEqual(by_id[row["pair"]]["pair"], row["id"], row["id"])


class CatalogSafetyTests(unittest.TestCase):
    """Signature flags, the account identifier, and the gfp row corrections."""

    def test_no_account_identifier_or_host_is_committed(self):
        text = (VS / "reference-catalog.json").read_text(encoding="utf-8")
        self.assertNotIn("filesafe", text)
        self.assertNotIn("https://", text)

    def test_load_catalog_assembles_urls_from_the_injected_base(self):
        rows = comp.load_catalog()["rows"]
        self.assertTrue(all(r["url"] == "https://media.example.test/demo-account/" + r["media_path"] for r in rows))
        saved = os.environ.pop("SKILL71_REFERENCE_MEDIA_BASE")
        try:
            bare = comp.load_catalog()["rows"]
            self.assertTrue(all("url" not in r for r in bare))
            self.assertEqual(comp.typed_references("final-mockups", "desktop", "1", ["overlay-light"]), [])
        finally:
            os.environ["SKILL71_REFERENCE_MEDIA_BASE"] = saved

    def test_rows_with_a_signature_or_placeholder_are_flagged_and_described(self):
        by_id = {r["id"]: r for r in CATALOG["rows"]}
        for rid in MUST_BE_FLAGGED:
            self.assertTrue(by_id[rid]["contains_reference_only_text"], rid)
            self.assertTrue(by_id[rid].get("reference_only_text"), rid)

    def test_typed_references_never_return_a_flagged_row(self):
        flagged = {r["id"] for r in CATALOG["rows"] if r["contains_reference_only_text"]}
        every = [t for t in comp.treatment_ids()]
        for stage in comp.WIREFRAME_STAGES + comp.MOCKUP_STAGES:
            for platform in ("desktop", "mobile"):
                for sid in [str(n) for n in range(1, 13)] + ["2A", "5B", "12"]:
                    for tids in (["split"], every, ["overlay-light"]):
                        for ref in comp.typed_references(stage, platform, sid, tids):
                            self.assertNotIn(ref["id"], flagged, (stage, platform, sid))

    def test_founder_letter_mockup_does_not_get_the_signature_sheet(self):
        for stage in comp.MOCKUP_STAGES:
            ids = [r["id"] for r in comp.typed_references(stage, "desktop", "12", ["overlay-light"])]
            self.assertNotIn("desktop-annotated-mockup", ids)
            self.assertIn("gen-hero-overlay-light", ids)

    def test_gfp_shaped_mask_is_not_tagged_as_an_arch_or_a_frame_break(self):
        row = next(r for r in CATALOG["rows"] if r["id"] == "gfp-shaped-mask")
        self.assertNotIn("mask-arch", row["traits"])
        self.assertNotIn("break-the-frame", row["traits"])
        picked = comp.typed_references("final-mockups", "desktop", "8", ["mask-arch"])
        self.assertNotIn("gfp-shaped-mask", [r["id"] for r in picked])

    def test_every_non_split_treatment_with_a_row_has_an_unflagged_example(self):
        for tid in ("overlay-light", "overlay-dark-scrim", "band-light-field", "mask-circle", "mask-arch", "mask-pill"):
            got = comp.typed_references("final-mockups", "desktop", "99", [tid])
            self.assertTrue(any(tid in (r.get("traits") or []) for r in got), tid)

    def test_generated_references_exist_and_are_marked(self):
        gen = [r for r in CATALOG["rows"] if r["id"].startswith("gen-")]
        self.assertEqual({r["id"] for r in gen}, {"gen-hero-overlay-light", "gen-hero-light-field",
                                                  "gen-circle-persona-band", "gen-arch-pill-band"})
        for r in gen:
            self.assertIn("generated-reference", r["tags"])
            self.assertFalse(r["contains_reference_only_text"])


class TreatmentLibraryTests(unittest.TestCase):
    def test_all_thirteen_treatments(self):
        ids = {t["id"] for t in LIB["treatments"]}
        self.assertEqual(ids, {"split", "overlay-light", "overlay-dark-scrim", "caption-over-photo",
                               "card-overlaps-photo", "band-over-texture", "band-light-field",
                               "mask-circle", "mask-arch", "mask-pill", "mask-diagonal",
                               "break-the-frame", "section-intersect"})

    def test_tokens_only_no_hex_no_named_color(self):
        text = (ROOT / "references" / "composition-treatments.json").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"#[0-9a-fA-F]{3,8}\b", text), [])
        words = re.findall(r"[a-z]+", text.lower())
        self.assertEqual([w for w in NAMED_COLORS if w in words], [])
        # control: the same grep does find hex values in the real brand file
        brand = (ROOT / "assets" / "brand" / "blackceo-brand.json").read_text(encoding="utf-8")
        self.assertTrue(re.findall(r"#[0-9a-fA-F]{6}\b", brand))

    def test_roles_point_at_real_treatments(self):
        for role in LIB["roles"]:
            for tid in [role["default"], *role["alternates"], *role.get("rotate", [])]:
                self.assertIn(tid, comp.treatments(), role["role"])

    def test_every_treatment_has_its_prompt_sentences(self):
        for tid, t in comp.treatments().items():
            for key in ("photo_prompt", "wireframe_drawing", "section_prompt", "css", "when"):
                self.assertTrue(t.get(key), f"{tid} lacks {key}")

    def test_trait_vocabulary_readmits_the_families(self):
        vocab = json.loads((ROOT / "references" / "layout-trait-vocabulary.json").read_text(encoding="utf-8"))
        dropped = json.dumps(vocab["dropped"]).lower()
        self.assertNotIn("full-bleed image with copy overlay", dropped)
        self.assertNotIn("offset image frame breaking the column", dropped)
        self.assertIn("trevor", json.dumps(vocab["readmitted"]).lower())
        self.assertIn("2026-10-19", json.dumps(vocab["readmitted"]))
        self.assertTrue(any(t["id"] == "composition-treatments" for t in vocab["traits"]))

    def test_leak_check_outside_reference_descriptions(self):
        banned = ("Set for" + " Life", "Trevor" + " Otts", "E.R." + " Spaulding", "September 29," + " 2026")
        for rel in ("references/composition-treatments.json", "references/composition-patterns.md",
                    "scripts/composition.py"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            for phrase in banned:
                self.assertFalse(phrase in text, f"{rel} carries {phrase!r}")


SECTION = {"section_id": "1", "section_name": "The Big Bold Claim",
           "copy": "You are doing every job yourself. CTA: SAVE MY SEAT.",
           "slots": [{"slot_id": "IMG-01", "aspect_ratio": "3:2", "art_direction": "Founder at a desk.",
                      "copy_zone": [4, 20, 55, 80], "subject_zone": [62, 5, 98, 95]}]}
MOCKUP_TEMPLATE = "Mockup section {section_number} {section_name} at {width}px. {copy} {slots}"


def _roles():
    """The page color system roles of a run with BlackCEO's colors; mockup prompts refuse without."""
    with tempfile.TemporaryDirectory() as tmp:
        give_blackceo_colors(tmp)
        return exe.hypersaturation.roles_for_run(Path(tmp))


def _request(sections, stage_prompt_stage="final-mockups"):
    return {"model": "gpt-image-2-5-sunburst-image-to-image", "style": "warm editorial",
            "sections": sections, "_hypersat": _roles(),
            "stage_prompts": {s: MOCKUP_TEMPLATE for s in exe.STAGES}}


class PromptContractTests(unittest.TestCase):
    def test_each_treatment_yields_its_photo_sentence_and_the_universal_negative(self):
        probes = {"overlay-light": "reserved copy space", "overlay-dark-scrim": "falls off to the darkest tone",
                  "caption-over-photo": "corner quiet", "band-over-texture": "falls off to the darkest tone",
                  "band-light-field": "line-art pattern", "mask-circle": "inscribed circle",
                  "mask-arch": "rounded top", "mask-pill": "rounded edges",
                  "break-the-frame": "cut-out friendly", "card-overlaps-photo": "solid card",
                  "mask-diagonal": "angled", "section-intersect": "straddle"}
        for tid, needle in probes.items():
            text = comp.photo_rules({"slot_id": "IMG-9"}, tid, comp.load_brand())
            self.assertIn(needle, text, tid)
            self.assertIn("do not leave a blank column", text, tid)
            self.assertNotIn("{", text, tid)

    def test_overlay_copy_space_follows_the_slot_zones(self):
        text = comp.photo_rules(SECTION["slots"][0], "overlay-light")
        self.assertIn("right 36 percent", text)      # subject zone 62..98
        self.assertIn("left 51 percent", text)       # copy zone 4..55
        mirrored = dict(SECTION["slots"][0], copy_zone=[45, 20, 96, 80], subject_zone=[2, 5, 38, 95])
        self.assertIn("The right 51 percent", comp.photo_rules(mirrored, "overlay-light"))

    def test_mockup_prompt_for_an_overlay_section_says_do_not_split(self):
        request = _request([SECTION])
        prompt = exe.stage_prompt("final-mockups", SECTION, 1, 1440, request, "3:2")
        self.assertIn("Do not split this section into an image column and a text column", prompt)
        self.assertIn("ON the photograph", prompt)
        self.assertIn("treatment overlay-light", prompt)

    def test_wireframe_negative_block_allows_img_labels_other_stages_do_not(self):
        wire = exe.negative_block("desktop-wireframe")
        strict = exe.negative_block("final-mockups")
        self.assertIn("slot labels with pixel size", wire)
        self.assertNotIn("production labels", wire)
        self.assertIn("production labels", strict)
        prompt = exe.stage_prompt("desktop-wireframe", SECTION, 1, 1440, _request([SECTION]), "16:9")
        self.assertIn("Print the slot label with its pixel size, ratio and treatment (overlay-light)", prompt)
        self.assertIn("Wireframe annotations are allowed", prompt)

    def test_declared_treatment_wins_and_role_default_fills_the_rest(self):
        pain = {"section_id": "2", "section_name": "Pain", "copy": "Every hour goes to the business.",
                "slots": [{"slot_id": "IMG-02", "aspect_ratio": "4:3", "art_direction": "Desk."}]}
        declared = {"section_id": "3", "section_name": "Pain", "copy": "Nothing is left for family.",
                    "slots": [{"slot_id": "IMG-03", "aspect_ratio": "4:3", "art_direction": "Dinner.",
                               "treatment": "mask-arch"}]}
        got = comp.assign_treatments([SECTION, pain, declared])
        self.assertEqual([e["slots"][0]["treatment"] for e in got],
                         ["overlay-light", "card-overlaps-photo", "mask-arch"])
        self.assertEqual([e["slots"][0]["source"] for e in got],
                         ["role-default", "role-default", "declared"])

    def test_no_two_adjacent_sections_repeat_a_non_split_default(self):
        sections = [{"section_id": str(n), "section_name": "Benefits",
                     "slots": [{"slot_id": f"IMG-{n}"}]} for n in (8, 9, 10, 8, 9)]
        picks = [e["slots"][0]["treatment"] for e in comp.assign_treatments(sections)]
        for a, b in zip(picks, picks[1:]):
            self.assertNotEqual(a, b, picks)

    def test_photo_rules_are_appended_to_an_item_prompt_within_the_cap(self):
        request = _request([SECTION])
        merged = exe.with_photo_rules("A founder at a desk.", "IMG-01", request)
        self.assertIn("reserved copy space", merged)
        self.assertEqual(exe.with_photo_rules(merged, "IMG-01", request), merged)
        huge = "x" * 19900
        with self.assertRaises(exe.ExecutorError):
            exe.with_photo_rules(huge, "IMG-01", request)


BRAND = {"palette": {"cream": "#F5F0E8", "navy": "#1A1A2E", "gold": "#C9A227"},
         "composition_cues": {"imagery_direction": "fine botanical leaves and small dots"}}
FIELD_SECTION = {"section_id": "7", "section_name": "What you get", "copy": "Here is what is included.",
                 "slots": [{"slot_id": "IMG-07", "aspect_ratio": "16:5", "art_direction": "Pattern.",
                            "treatment": "band-light-field"}]}


class ConcretePromptAndCuesTests(unittest.TestCase):
    def test_light_field_photo_prompt_names_the_motifs_and_the_color_values(self):
        text = comp.photo_rules({"slot_id": "IMG-07"}, "band-light-field", BRAND)
        self.assertIn("fine botanical leaves and small dots", text)
        self.assertIn("#F5F0E8", text)
        self.assertNotIn("{", text)
        self.assertNotIn("brand surface color", text)
        line = re.findall(r"#[0-9A-F]{6}", text)
        self.assertEqual(len(line), 2, text)
        rgb = lambda h: tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))  # noqa: E731
        self.assertLessEqual(comp.contrast_ratio(rgb(line[0]), rgb(line[1])), 1.15)
        self.assertNotEqual(line[0], line[1])

    def test_slot_motifs_beat_the_brand_and_a_default_is_stated_when_none_are_given(self):
        slot = {"slot_id": "IMG-07", "motifs": "paper planes and clouds"}
        self.assertIn("paper planes and clouds", comp.photo_rules(slot, "band-light-field", BRAND))
        bare = {"palette": BRAND["palette"]}
        text = comp.photo_rules({"slot_id": "IMG-07"}, "band-light-field", bare)
        self.assertIn(comp.DEFAULT_MOTIFS, text)
        self.assertNotIn("{", text)

    def test_unsupplied_brand_colors_refuse_instead_of_sending_a_placeholder(self):
        unset = {"palette": {"cream": "CLIENT_MUST_SUPPLY", "navy": "CLIENT_MUST_SUPPLY", "gold": "CLIENT_MUST_SUPPLY"}}
        with self.assertRaises(ValueError):
            comp.photo_rules({"slot_id": "IMG-07"}, "band-light-field", unset)
        request = dict(_request([FIELD_SECTION]), _composition_brand=unset)
        with self.assertRaises(exe.ExecutorError):
            exe.with_photo_rules("Pattern.", "IMG-07", request)

    def test_executor_sends_a_section_7_field_slot_a_filled_prompt(self):
        request = dict(_request([FIELD_SECTION]), _composition_brand=BRAND)
        merged = exe.with_photo_rules("Pattern.", "IMG-07", request)
        self.assertIn("botanical leaves", merged)
        self.assertRegex(merged, r"#[0-9A-F]{6}")
        self.assertNotIn("{", merged)

    def test_composition_cues_drop_unknown_ids_and_never_prefer_a_forbidden_one(self):
        cues = comp.composition_cues({"composition_cues": {"preferred": ["mask-pill", "nope", "mask-arch"],
                                                          "forbidden": ["mask-arch", "also-nope"]}})
        self.assertEqual(cues["preferred"], ["mask-pill"])
        self.assertEqual(cues["forbidden"], ["mask-arch"])
        self.assertEqual(comp.composition_cues({}), {"preferred": [], "forbidden": [], "imagery_direction": ""})

    def test_a_forbidden_treatment_is_never_a_role_default(self):
        hero = {"section_id": "1", "section_name": "The Big Bold Claim", "slots": [{"slot_id": "IMG-01"}]}
        self.assertEqual(comp.assign_treatments([hero])[0]["slots"][0]["treatment"], "overlay-light")
        cues = comp.composition_cues({"composition_cues": {"forbidden": ["overlay-light"]}})
        self.assertEqual(comp.assign_treatments([hero], cues)[0]["slots"][0]["treatment"], "overlay-dark-scrim")
        everything = comp.composition_cues({"composition_cues": {"forbidden": [
            "overlay-light", "overlay-dark-scrim", "break-the-frame", "caption-over-photo"]}})
        self.assertEqual(comp.assign_treatments([hero], everything)[0]["slots"][0]["treatment"], "split")

    def test_a_preferred_treatment_in_the_roles_pool_goes_first(self):
        benefit = {"section_id": "8", "section_name": "Benefits", "slots": [{"slot_id": "IMG-08"}]}
        cues = comp.composition_cues({"composition_cues": {"preferred": ["mask-diagonal"]}})
        self.assertEqual(comp.assign_treatments([benefit], cues)[0]["slots"][0]["treatment"], "mask-diagonal")

    def test_the_stage_prompt_follows_the_brand_cues(self):
        hero = {"section_id": "1", "section_name": "The Big Bold Claim", "copy": "A claim.",
                "slots": [{"slot_id": "IMG-01", "aspect_ratio": "3:2", "art_direction": "A person."}]}
        brand = {"palette": BRAND["palette"], "composition_cues": {"forbidden": ["overlay-light"]}}
        request = dict(_request([hero]), _composition_brand=brand)
        prompt = exe.stage_prompt("final-mockups", hero, 1, 1440, request, "3:2")
        self.assertIn("treatment overlay-dark-scrim", prompt)
        self.assertNotIn("treatment overlay-light", prompt)

    def test_budget_rejects_a_forbidden_declared_treatment_and_waives_what_only_it_could_meet(self):
        cues = comp.composition_cues({"composition_cues": {"forbidden": ["mask-circle"]}})
        rows = comp.plan_sections(_plan(MEETS))
        out = comp.budget_failures(rows, cues)
        self.assertTrue(any("'mask-circle' is forbidden" in line for line in out), out)
        no_masks = comp.composition_cues({"composition_cues": {"forbidden": [
            "mask-circle", "mask-arch", "mask-pill", "mask-diagonal"]}})
        spec = [(sid, ["split"] if any(t.startswith("mask-") for t in ts) else ts) for sid, ts in
                [(r[0], r[1]) for r in MEETS if not isinstance(r[1], str)]]
        spec = [("1", ["overlay-light"]), ("2", ["card-overlaps-photo"]), ("3", ["caption-over-photo"]),
                ("4", ["split"]), ("5", ["band-over-texture"]), ("6", ["split"]), ("7", ["split"]),
                ("8", ["caption-over-photo"]), ("9", ["card-overlaps-photo"]), ("10", ["split"])]
        rows = comp.plan_sections(_plan(spec))
        self.assertTrue(any("shaped crops" in l for l in comp.budget_failures(rows)))
        self.assertEqual([l for l in comp.budget_failures(rows, no_masks) if "mask" in l], [])


class ThreeRolesPreflightTests(unittest.TestCase):
    """Wireframe and mockup prompts for three section roles carry typed
    references and a non-split instruction, inside the prompt budget."""

    ROLES = [("1", "The Big Bold Claim"), ("6", "The Big Bold Who"), ("8", "The Big Bold Benefits 1")]

    def test_each_role_gets_typed_references_and_a_non_split_instruction(self):
        sections = [{"section_id": sid, "section_name": name,
                     "copy": f"Section {sid} copy is a full sentence.",
                     "slots": [{"slot_id": f"IMG-{sid}", "aspect_ratio": "4:3", "art_direction": "A person."}]}
                    for sid, name in self.ROLES]
        request = _request(sections)
        budget = exe.prompt_budget(request["model"])
        for index, section in enumerate(sections, start=1):
            resolved = exe.resolve_composition(section, index, request)
            tids = [e["treatment"] for e in resolved["slots"]]
            self.assertNotEqual(tids[0], "split", section["section_id"])
            for stage in ("desktop-wireframe", "final-mockups"):
                typed = exe.section_typed_references(stage, 1440, resolved, section)
                prompt, sizes = exe.stage_prompt(stage, section, index, 1440, request, "3:2",
                                                 with_sizes=True, typed_refs=typed)
                self.assertLessEqual(sizes["chars"], budget["max_chars"])
                self.assertIn("COMPOSITION CONTRACT", prompt)
                self.assertIn(tids[0], prompt)
                text_over = comp.treatments()[tids[0]]["text_relation"] in ("over", "overlap-card", "behind")
                self.assertEqual("Do not split this section" in prompt, text_over, tids[0])
                self.assertNotIn("shows split", prompt)
                self.assertTrue(typed, f"{stage} section {section['section_id']} has no typed reference")
                self.assertIn("REFERENCE ROLES", prompt)
                for ref in typed:
                    self.assertTrue(ref["url"].startswith("https://"))
                    self.assertNotIn(ref["id"], prompt)  # ids and filenames never reach the model

    def test_counter_example_rows_are_skipped_for_non_split_sections(self):
        got = comp.typed_references("final-mockups", "mobile", "2", ["card-overlaps-photo"])
        self.assertTrue(all("counter-example-composition" not in (r.get("tags") or []) for r in got))
        split = comp.typed_references("final-mockups", "mobile", "2", ["split"])
        self.assertTrue(any("counter-example-composition" in (r.get("tags") or []) for r in split))


def _plan(spec):
    plan = []
    for sid, treatments in spec:
        entry = {"section_id": sid, "image_slot_ids": [], "slot_labels": {}}
        if isinstance(treatments, str):
            entry["treatment"] = treatments  # section-level (typography-led) backdrop
        else:
            for n, t in enumerate(treatments):
                slot = f"IMG-{sid}-{n}"
                entry["image_slot_ids"].append(slot)
                entry["slot_labels"][slot] = {"aspect_ratio": "4:3", "art_direction": "A person.",
                                              **({"treatment": t} if t else {})}
        plan.append(entry)
    return plan


MEETS = [("1", ["overlay-light"]), ("2", ["card-overlaps-photo"]), ("2A", "band-light-field"),
         ("3", ["caption-over-photo"]), ("4", ["split"]), ("5", ["band-over-texture"]),
         ("6", ["mask-circle"]), ("7", ["split"]), ("8", ["mask-arch"]),
         ("9", ["caption-over-photo"]), ("10", ["mask-diagonal"]), ("11", ["split"]),
         ("12", ["overlay-dark-scrim"])]


class WireframeBudgetGateTests(unittest.TestCase):
    def failures(self, spec):
        return comp.budget_failures(comp.plan_sections(_plan(spec)))

    def test_all_split_plan_fails_and_names_the_share(self):
        out = self.failures([(str(n), ["split"]) for n in range(1, 13)])
        self.assertTrue(any("12 of 12" in line for line in out), out)
        self.assertTrue(any("no mask-circle" in line for line in out), out)

    def test_undeclared_slots_count_as_split(self):
        out = self.failures([(str(n), [None]) for n in range(1, 13)])
        self.assertTrue(any("photo-bearing sections are split" in line for line in out), out)

    def test_plan_meeting_the_budget_passes(self):
        self.assertEqual(self.failures(MEETS), [])

    def test_adjacent_identical_non_split_fails(self):
        spec = [list(row) for row in MEETS]
        spec[9] = ["9", ["mask-arch"]]   # sections 8 and 9 both mask-arch
        out = self.failures([tuple(r) for r in spec])
        self.assertTrue(any("both use 'mask-arch'" in line for line in out), out)

    def test_unknown_treatment_always_fails_even_on_a_small_plan(self):
        out = self.failures([("1", ["fancy-frame"])])
        self.assertTrue(any("unknown treatment" in line for line in out), out)

    def test_small_plans_are_not_judged(self):
        self.assertEqual(self.failures([("1", ["split"]), ("2", ["split"])]), [])

    def test_validate_wireframe_runs_the_gate(self):
        text = (SCRIPTS / "validate_wireframe.py").read_text(encoding="utf-8")
        self.assertIn("composition.budget_failures(", text)
        self.assertIn("composition.composition_cues(composition.load_brand(run_dir, brand_arg))", text)
        self.assertIn('("COMP", comp_failures)', text)


# ---------------------------------------------------------------- pixel + page checks
try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover
    Image = None


def _flat(size, rgb):
    return Image.new("RGB", size, rgb)


class PixelCheckTests(unittest.TestCase):
    """Pure pixel functions, no browser."""

    BG = (244, 240, 232)

    def circle_img(self, rounded=True):
        img = _flat((120, 120), self.BG)
        draw = ImageDraw.Draw(img)
        if rounded:
            draw.ellipse((0, 0, 119, 119), fill=(60, 80, 120))
        else:
            draw.rectangle((0, 0, 119, 119), fill=(60, 80, 120))
        return img

    def test_circle_passes_and_square_fails_the_corner_test(self):
        self.assertTrue(comp.corner_test(self.circle_img(True), self.BG, "circle")[0])
        ok, detail = comp.corner_test(self.circle_img(False), self.BG, "circle")
        self.assertFalse(ok)
        self.assertIn("corner patches", detail)

    def test_arch_checks_only_the_top_corners(self):
        img = _flat((120, 120), (60, 80, 120))
        draw = ImageDraw.Draw(img)
        draw.rectangle((0, 0, 12, 12), fill=self.BG)
        draw.rectangle((107, 0, 119, 12), fill=self.BG)
        self.assertTrue(comp.corner_test(img, self.BG, "arch")[0])
        self.assertFalse(comp.corner_test(img, self.BG, "circle")[0])

    def test_light_field_needs_light_and_texture(self):
        import random
        rng = random.Random(7)
        field = Image.new("L", (200, 120))
        field.putdata([min(255, 244 + rng.randint(0, 11)) for _ in range(200 * 120)])
        self.assertTrue(comp.light_field_check(field.convert("RGB"))[0])
        flat = _flat((200, 120), (250, 250, 250))
        ok, detail = comp.light_field_check(flat)
        self.assertFalse(ok)
        self.assertIn("flat fill", detail)
        dark = _flat((200, 120), (120, 120, 120))
        self.assertFalse(comp.light_field_check(dark)[0])

    def test_light_field_on_a_dark_surface_uses_field_to_surface_contrast(self):
        import random
        rng = random.Random(3)
        surface = (20, 24, 30)
        field = Image.new("RGB", (200, 120))
        offsets = [rng.randint(0, 8) for _ in range(200 * 120)]
        field.putdata([(20 + o, 24 + o, 30 + o) for o in offsets])
        self.assertTrue(comp.light_field_check(field, surface)[0])
        loud = _flat((200, 120), (120, 120, 120))
        self.assertFalse(comp.light_field_check(loud, surface)[0])

    def test_light_field_on_a_beige_surface_passes_by_the_ratio_not_the_absolute_floor(self):
        import random
        rng = random.Random(5)
        surface = (228, 220, 206)
        field = Image.new("RGB", (200, 120))
        field.putdata([(228 + o, 220 + o, 206 + o) for o in (rng.randint(0, 6) for _ in range(200 * 120))])
        ok, detail = comp.light_field_check(field, surface)
        self.assertTrue(ok, detail)
        ok, detail = comp.light_field_check(field)       # no surface known: the old floor
        self.assertFalse(ok)
        self.assertIn("under 235", detail)

    def test_line_color_stays_inside_the_contrast_limit_on_any_palette(self):
        for surface, ink in (((245, 240, 232), (26, 26, 46)), ((228, 220, 206), (40, 30, 20)),
                             ((22, 26, 34), (240, 236, 226))):
            line = comp.line_color(surface, ink)
            self.assertLessEqual(comp.contrast_ratio(line, surface), 1.15)
            self.assertNotEqual(line, tuple(surface))

    def test_contrast_and_zone_geometry(self):
        self.assertAlmostEqual(comp.contrast_ratio((0, 0, 0), (255, 255, 255)), 21.0, places=1)
        ok, ratio, need = comp.backdrop_contrast(_flat((50, 20), (250, 250, 250)), (20, 20, 20), False)
        self.assertTrue(ok)
        ok, ratio, need = comp.backdrop_contrast(_flat((50, 20), (120, 120, 120)), (140, 140, 140), False)
        self.assertFalse(ok)
        frame = {"left": 0, "right": 1000, "top": 0, "bottom": 500}
        over_face = {"left": 700, "right": 900, "top": 100, "bottom": 200}
        clear = {"left": 60, "right": 400, "top": 100, "bottom": 200}
        zone = [62, 5, 98, 95]
        self.assertTrue(comp.face_zone_overlap(over_face, frame, zone))
        self.assertFalse(comp.face_zone_overlap(clear, frame, zone))
        self.assertTrue(comp.safe_margin_ok(clear, frame))
        self.assertFalse(comp.safe_margin_ok({"left": 5, "right": 400, "top": 100, "bottom": 200}, frame))

    def test_copy_space_check_on_a_raw_photo(self):
        img = _flat((200, 100), (240, 240, 240))
        draw = ImageDraw.Draw(img)
        for x in range(110, 200, 6):
            draw.rectangle((x, 0, x + 2, 99), fill=(20, 30, 60))
        self.assertTrue(comp.copy_space_ok(img, [0, 0, 50, 100])[0])
        self.assertFalse(comp.copy_space_ok(img, [50, 0, 100, 100])[0])


TOKENS = {
    "light": {"--brand-surface": "rgb(244,240,232)", "--brand-ink": "rgb(28,32,44)", "--brand-dark": "rgb(20,24,30)"},
    "beige": {"--brand-surface": "rgb(228,220,206)", "--brand-ink": "rgb(40,30,20)", "--brand-dark": "rgb(20,14,8)"},
    "dark": {"--brand-surface": "rgb(22,26,34)", "--brand-ink": "rgb(240,236,226)", "--brand-dark": "rgb(8,10,14)"},
}


def _png(path, img):
    img.save(path)
    return path.name


try:
    from playwright.sync_api import sync_playwright
    _probe = tempfile.mkdtemp(prefix="skill71-probe-")
    try:
        with sync_playwright() as _p:
            _p.chromium.launch_persistent_context(_probe, headless=True).close()
        PLAYWRIGHT_OK = True
    finally:
        shutil.rmtree(_probe, ignore_errors=True)
except Exception:
    PLAYWRIGHT_OK = False


@unittest.skipUnless(PLAYWRIGHT_OK and Image is not None, "Playwright + Chromium not available")
class BuiltPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import random
        cls.tmp = Path(tempfile.mkdtemp(prefix="skill71-comp-"))
        rng = random.Random(11)
        cls.portrait = _png(cls.tmp / "portrait.png", _flat((400, 400), (70, 90, 130)))
        # photo: bright, almost flat left 55 percent (copy space), darker subject on the right
        photo = _flat((1200, 500), (236, 232, 224))
        ImageDraw.Draw(photo).rectangle((700, 0, 1199, 499), fill=(60, 70, 90))
        cls.photo = _png(cls.tmp / "photo.png", photo)
        photo_dark = _flat((1200, 500), (24, 28, 36))   # low-key: copy side falls off to the darkest tone
        ImageDraw.Draw(photo_dark).rectangle((700, 0, 1199, 499), fill=(90, 100, 120))
        cls.photo_dark = _png(cls.tmp / "photo-dark.png", photo_dark)
        for name, base, spread in (("field-light", 246, 9), ("field-flat", 250, 0), ("field-dark", 24, 6)):
            img = Image.new("RGB", (400, 300))
            img.putdata([(min(255, base + rng.randint(0, spread)),) * 3 for _ in range(400 * 300)])
            setattr(cls, name.replace("-", "_"), _png(cls.tmp / f"{name}.png", img))
        beige = Image.new("RGB", (400, 300))        # a faint 0-6 texture on the beige brand surface
        beige.putdata([(228 + o, 220 + o, 206 + o) for o in (rng.randint(0, 6) for _ in range(400 * 300))])
        cls.field_beige = _png(cls.tmp / "field-beige.png", beige)
        cls.pw = sync_playwright().start()
        # managed pattern the agent-browser guard requires: persistent context, headless
        cls.browser = cls.pw.chromium.launch_persistent_context(
            str(cls.tmp / "profile"), headless=True, viewport={"width": 1200, "height": 800})

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def open(self, body, tokens="light", name="page"):
        css = ":root{" + ";".join(f"{k}:{v}" for k, v in TOKENS[tokens].items()) + "}"
        html = (f"<!doctype html><meta charset=utf-8><style>{css}"
                "body{margin:0;background:var(--brand-surface);color:var(--brand-ink);font:20px/1.4 sans-serif}"
                "section{position:relative}</style>" + body)
        path = self.tmp / f"{name}.html"
        path.write_text(html, encoding="utf-8")
        page = self.browser.new_page()
        page.goto(path.as_uri())
        return page

    def checks(self, body, tokens="light"):
        page = self.open(body, tokens)
        try:
            data = page.evaluate(vp.LAYOUT_JS)
            return data, comp.page_failures(data) + vp.composition_pixel_failures(page)
        finally:
            page.close()

    def circle(self, radius="50%", label="mask-circle", tokens="light"):
        return (f'<section data-treatment="{label}" style="padding:40px">'
                f'<img data-image-slot="IMG-1" src="{self.portrait}" style="display:block;width:240px;'
                f'height:240px;object-fit:cover;border-radius:{radius}"></section>')

    def test_circle_fixture_passes(self):
        _data, out = self.checks(self.circle())
        self.assertEqual(out, [])

    def test_square_img_labelled_mask_circle_fails(self):
        _data, out = self.checks(self.circle(radius="0"))
        joined = "\n".join(out)
        self.assertIn("declares 'mask-circle'", joined)
        self.assertIn("shape check failed", joined)

    def test_mutation_proof_flip_to_border_radius_zero_goes_red_and_restore_goes_green(self):
        self.assertEqual(self.checks(self.circle())[1], [])
        self.assertNotEqual(self.checks(self.circle(radius="0"))[1], [])
        self.assertEqual(self.checks(self.circle())[1], [])

    def overlay(self, h1_style="", zone="", treatment="overlay-light", photo=None):
        return (f'<section data-treatment="{treatment}" style="height:500px;display:flow-root">'
                f'<img data-image-slot="IMG-2" {zone} src="{photo or self.photo}" style="position:absolute;inset:0;'
                f'width:100%;height:100%;object-fit:cover">'
                f'<h1 style="position:relative;margin:140px 0 0 90px;width:520px;font-size:44px;{h1_style}">'
                "Make room for a life you get to live.</h1></section>")

    def test_overlay_fixture_classifies_overlay_and_passes(self):
        data, out = self.checks(self.overlay(zone='data-subject-zone="62,5,98,95"'))
        self.assertEqual(comp.classify_section(data["sections"][0]), "OVERLAY")
        self.assertEqual(out, [])

    def test_text_over_a_face_fails(self):
        body = self.overlay(h1_style="margin-left:700px;width:400px;color:rgb(240,240,240)",
                            zone='data-subject-zone="62,5,98,95"')
        _data, out = self.checks(body)
        self.assertTrue(any("subject zone" in line for line in out), out)

    def test_split_section_classifies_split(self):
        body = (f'<section style="display:grid;grid-template-columns:1fr 1fr;height:300px">'
                f'<img src="{self.portrait}" style="width:100%;height:300px;object-fit:cover">'
                '<div><h2>Words beside a photo.</h2></div></section>')
        data, _out = self.checks(body)
        self.assertEqual(comp.classify_section(data["sections"][0]), "SPLIT")

    def field(self, name, text="Here is where possibility gets specific."):
        return (f'<section data-treatment="band-light-field" style="padding:60px 80px;'
                f'background:var(--brand-surface) url({getattr(self, name)})">'
                f'<h2 style="margin:0">{text}</h2></section>')

    def test_textured_light_field_passes_and_flat_fill_fails(self):
        self.assertEqual(self.checks(self.field("field_light"))[1], [])
        out = self.checks(self.field("field_flat"))[1]
        self.assertTrue(any("flat fill" in line for line in out), out)

    BUTTON = ('<a style="display:inline-block;margin-top:24px;padding:14px 28px;background:rgb(15,15,15);'
              'color:rgb(250,250,250);font-weight:700">Reserve my seat</a>')
    CARDS = ('<div style="display:flex;gap:20px;margin-top:24px"><div style="background:rgb(30,30,30);color:white;'
             'padding:24px;width:200px">Card one</div><div style="border:3px solid rgb(10,10,10);padding:24px;'
             'width:200px">Card two</div></div>')

    def test_light_field_on_a_beige_brand_surface_passes(self):
        # the field behind the type is within the contrast limit of the surface; the old 235 floor failed this at 219
        self.assertEqual(self.checks(self.field("field_beige"), "beige")[1], [])

    def test_dark_buttons_and_cards_in_front_of_the_field_do_not_fail_it(self):
        body = self.field("field_light", text="Pick one.")[:-len("</section>")] + self.BUTTON + self.CARDS + "</section>"
        self.assertEqual(self.checks(body, "light")[1], [])
        beige = self.field("field_beige", text="Pick one.")[:-len("</section>")] + self.BUTTON + self.CARDS + "</section>"
        self.assertEqual(self.checks(beige, "beige")[1], [])

    def test_a_flat_fill_with_a_button_still_fails_the_texture_floor(self):
        body = self.field("field_flat", text="Pick one.")[:-len("</section>")] + self.BUTTON + "</section>"
        out = self.checks(body, "light")[1]
        self.assertTrue(any("flat fill" in line for line in out), out)

    def test_a_field_too_far_from_the_surface_fails_on_the_ratio(self):
        out = self.checks(self.field("field_dark"), "light")[1]
        self.assertTrue(any("field-to-surface contrast" in line for line in out), out)

    def test_a_full_bleed_image_field_is_not_mistaken_for_foreground(self):
        body = (f'<section data-treatment="band-light-field" style="position:relative;padding:60px 80px">'
                f'<img data-image-slot="IMG-7" src="{self.field_light}" style="position:absolute;inset:0;'
                'width:100%;height:100%;object-fit:cover"><div style="position:relative">'
                '<h2 style="margin:0">Pick one.</h2>' + self.BUTTON + '</div></section>')
        self.assertEqual(self.checks(body, "light")[1], [])

    def test_type_that_is_too_pale_for_its_light_field_fails(self):
        body = (f'<section data-treatment="band-light-field" style="padding:60px 80px;'
                f'background:var(--brand-surface) url({self.field_light})">'
                '<h2 style="margin:0;color:rgb(215,212,205)">Washed out.</h2></section>')
        out = self.checks(body, "light")[1]
        self.assertTrue(any("over the light field" in line for line in out), out)

    def test_palette_independence_light_and_dark_brand_sets(self):
        self.assertEqual(self.checks(self.circle(), "light")[1], [])
        self.assertEqual(self.checks(self.circle(), "dark")[1], [])
        self.assertEqual(self.checks(self.field("field_light"), "light")[1], [])
        self.assertEqual(self.checks(self.field("field_dark"), "dark")[1], [])
        dark_overlay = self.overlay(zone='data-subject-zone="62,5,98,95"', treatment="overlay-dark-scrim",
                                    photo=self.photo_dark)
        self.assertEqual(self.checks(dark_overlay, "dark")[1], [])
        self.assertEqual(self.checks(self.overlay(zone='data-subject-zone="62,5,98,95"'), "light")[1], [])

    def test_page_without_declarations_is_not_touched(self):
        data, out = self.checks("<section><h1>Plain page</h1><p>No treatments declared.</p></section>")
        self.assertEqual(out, [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
