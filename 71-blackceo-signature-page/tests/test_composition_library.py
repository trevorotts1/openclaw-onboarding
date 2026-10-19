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
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


comp = _load("composition")
exe = _load("stage_executor")
vp = _load("validate_page")

VS = ROOT / "assets" / "visual-standards"
CATALOG = json.loads((VS / "reference-catalog.json").read_text(encoding="utf-8"))
LIB = json.loads((ROOT / "references" / "composition-treatments.json").read_text(encoding="utf-8"))
SCHEMA_FIELDS = ("id", "type", "viewport", "form", "sections", "traits", "pair", "use",
                 "contains_reference_only_text", "sha256", "url", "source")
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
            self.assertTrue(row["url"].startswith("https://"), row["id"])
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
           "slots": [{"slot_id": "IMG-01", "aspect_ratio": "8:5", "art_direction": "Founder at a desk.",
                      "copy_zone": [4, 20, 55, 80], "subject_zone": [62, 5, 98, 95]}]}
MOCKUP_TEMPLATE = "Mockup section {section_number} {section_name} at {width}px. {copy} {slots}"


def _request(sections, stage_prompt_stage="final-mockups"):
    return {"model": "gpt-image-2-5-sunburst-image-to-image", "style": "warm editorial",
            "sections": sections,
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
            text = comp.photo_rules({"slot_id": "IMG-9"}, tid)
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
        self.assertIn("composition.budget_failures(composition.plan_sections(plan))", text)
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
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

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
        page = self.browser.new_page(viewport={"width": 1200, "height": 800})
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
