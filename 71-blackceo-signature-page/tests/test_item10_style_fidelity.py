#!/usr/bin/env python3
"""Item 10 (Amendment 6, Parts B and C) acceptance tests.

Prompt-side: selection record + trait extraction fidelity checks in
scripts/validate_prompt.py (lock/anchor/trait expression, 3x3 zone,
verbatim-only-where-mandated, denylist, Avoid scope, contamination,
procedural declaration blocks). Image-side: the Amendment 6 Part B4
corrections in scripts/validate_image_grade.py (Blend Profile
SUPPRESS makes color floors N/A; the distinctness register is the
enforcement layer).

Prompts are COMPOSED from the checked-in extraction files at test time
(lock tokens are read from references/style-traits/*.json), so the
tests judge the validator against the same data a run would use.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
PROMPT_SCRIPT = os.path.join(SKILL_ROOT, "scripts", "validate_prompt.py")
GRADE_SCRIPT = os.path.join(SKILL_ROOT, "scripts", "validate_image_grade.py")
TRAITS = Path(SKILL_ROOT) / "references" / "style-traits"

PHOTO = json.loads((TRAITS / "photographers.json").read_text(encoding="utf-8"))
CINE = json.loads((TRAITS / "cinematic.json").read_text(encoding="utf-8"))
VA = json.loads((TRAITS / "visual-artists.json").read_text(encoding="utf-8"))
DENY_PHOTO = json.loads((TRAITS / "denylist-photographers.json").read_text(encoding="utf-8"))

# Prompts a test expects to PASS are grown into the Decision 1 length
# band by the suite's fitting helper (tests/fit_prompt.py; the standing
# convention from test_stage_gate.py / test_validate_copy_prompt.py):
# the composed prompts here are small on purpose, and under the adopted
# band a raw one fails the floor before the fidelity checks under test
# can pass. Prompts a test expects to FAIL keep their raw composed
# form, so the named failure is the one under test.
sys.path.insert(0, HERE)
import fit_prompt  # noqa: E402

NEGATIVE_LINES = [
    "Do not produce flat, muted, pastel, desaturated, washed-out, or low-contrast color.",
    "Do not distort hands, eyes, or teeth.",
    "Do not render any text, letters, or words anywhere in the image.",
    "Do not invent, approximate, or mutate any brand logo on any surface.",
    "Do not render placeholder blocks, dummy graphics, or lorem text anywhere in the frame.",
    "Do not grey, bleach, or lighten the subject's skin or shift its undertone.",
    "Do not add any watermark, corner tag, caption, badge, or footer to the image.",
]


def run(script, *args):
    return subprocess.run([sys.executable, script, *args],
                          capture_output=True, text=True, timeout=60)


def sha256_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def all_tokens(items):
    out = []
    for item in items:
        out += [t for t in (item.get("check_tokens") or []) if t]
    return out


def lock_tokens(entry, mode=None):
    if mode and entry.get("modes"):
        locks = entry["modes"][mode].get("locks") or {}
    else:
        locks = entry.get("locks") or {}
    return all_tokens([v for v in locks.values() if isinstance(v, dict)])


def compose_prompt(style_line, tokens=(), zone="middle-right",
                   element_e=None, element_f=None, element_g=None,
                   subject_extra=""):
    if element_e is None:
        element_e = ("TYPOGRAPHY + VERBATIM COPY: No text, no letters, no words "
                     "anywhere in the image. No typography is baked into this asset.")
    if element_f is None:
        element_f = ("LIGHTING + COLOR GRADE: One motivated window key from camera "
                     "left, a gentle fill, protected highlights, and a deliberate "
                     "color grade that serves this specific scene.")
    if element_g is None:
        element_g = ("PEOPLE / REPRESENTATION: One fictional Black woman with deep "
                     "brown with a neutral-red undertone skin and a short tapered "
                     "natural cut with tight coils; believable hands and a natural, "
                     "unperformed expression.")
    token_text = "; ".join(tokens)
    parts = [
        "ASSET: editorial photograph | BAND: visual_long. One standalone image "
        "for the page, art-directed as a single continuous scene.",
        "SUBJECT + SCENE: The scene belongs to one specific subject in one "
        "specific room at one specific interrupted moment. " + subject_extra,
        f"COMPOSITION GRID: The subject is anchored in the {zone} zone; the "
        "text-safe zone stays in the upper-left; crop-safe margins of 5-10 "
        "percent hold on every edge; the viewpoint is eye-level and the visual "
        "path leads from the foreground to the subject.",
        f"STYLE BLOCK: {style_line}. {token_text}",
        element_e,
        element_f,
        element_g,
        "LOGO / REFERENCE DIRECTIVE: References are style-only. Use the attached "
        "images only as style reference for color grading, lighting, and "
        "composition -- do not copy their subjects, faces, or text. No brand "
        "logo is approximated on any surface.",
        "TECHNICAL: One independent master image at the recorded native ratio; "
        "save the unmodified master; production identifiers stay in filenames "
        "and private manifests only.",
        "NEGATIVE BLOCK:\n" + "\n".join(NEGATIVE_LINES),
    ]
    return "\n\n".join(parts) + "\n"


def photo_entry():
    return {
        "id": "IMG-001",
        "composition": "Subject anchored middle-right zone; text-safe zone "
                       "upper-left; crop-safe margins 5-10 percent.",
        "subject_zone": "middle-right",
        "native_aspect_ratio": "3:2",
        "crop_plan": "Master at native 3:2; delivery crop to 1440x960.",
        "delivery_dimensions": [1440, 960],
        "delivery_filename": "Image-001.png",
        "text_mode": "none",
        "people": [{"description": "one fictional Black woman",
                    "skin_tone": "deep brown with a neutral-red undertone",
                    "hair": "short tapered natural cut with tight coils",
                    "facial_hair": None}],
        "references": [{"role": "style", "file": "style-ref-01.png"}],
    }


def write_run(root, selection, entry, prompt_text, bible=None):
    root = Path(root)
    (root / "image-inventory-prompts").mkdir(parents=True)
    (root / "desktop-wireframe").mkdir(parents=True)
    (root / "visual-mockup").mkdir(parents=True)
    (root / "image-inventory-prompts" / "style-selection.json").write_text(
        json.dumps({"schema_version": 1, "selections": [selection]}, indent=2),
        encoding="utf-8")
    (root / "desktop-wireframe" / "image-inventory.json").write_text(
        json.dumps({"images": [entry]}, indent=2), encoding="utf-8")
    if bible is not None:
        (root / "visual-mockup" / "page-visual-bible.json").write_text(
            json.dumps(bible, indent=2), encoding="utf-8")
    prompt = root / "image-inventory-prompts" / "IMG-001.txt"
    prompt.write_text(prompt_text, encoding="utf-8")
    return prompt


def selection_for(library, style_id, branded, traits_file, **overrides):
    record = {
        "applies_to": ["IMG-001"],
        "source_library": library,
        "style_id": style_id,
        "branded_name": branded,
        "mode": None,
        "blend": None,
        "hybrid_flag": False,
        "extraction_ref": {
            "path": f"references/style-traits/{traits_file}",
            "sha256": sha256_of(TRAITS / traits_file),
        },
        "declared_series": False,
        "declared_style_traits": [],
    }
    record.update(overrides)
    return record


class TestStyleFidelity(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="item10-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_photographers_selection_passes_and_reports_uncheckable(self):
        entry = PHOTO["entries"]["VDL-005"]
        sel = selection_for("photographers", "VDL-005", entry["branded_name"],
                            "photographers.json")
        prompt = fit_prompt.fit_text(compose_prompt(
            "VDL-005 White Field Intensity", lock_tokens(entry)))
        path = write_run(self.tmp / "run", sel, photo_entry(), prompt,
                         bible={"blend_profile": {"hero_color_chroma": "FULL"}})
        proc = run(PROMPT_SCRIPT, str(path))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("PASS", proc.stdout)
        # VDL-005's behavior lock has no checkable tokens: it must be
        # REPORTED as uncheckable-by-design, never silently passed.
        self.assertIn("UNCHECKABLE-BY-DESIGN", proc.stdout)

    def test_denylist_name_fails_and_is_not_echoed(self):
        entry = PHOTO["entries"]["VDL-005"]
        sel = selection_for("photographers", "VDL-005", entry["branded_name"],
                            "photographers.json")
        name = DENY_PHOTO["names"][0]
        prompt = compose_prompt("VDL-005 White Field Intensity",
                                lock_tokens(entry),
                                subject_extra=f"A portrait echoing {name}.")
        path = write_run(self.tmp / "run", sel, photo_entry(), prompt)
        proc = run(PROMPT_SCRIPT, str(path))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("denylist", proc.stdout.lower())
        self.assertNotIn(name, proc.stdout)

    def test_missing_zone_in_element_c_fails(self):
        entry = PHOTO["entries"]["VDL-005"]
        sel = selection_for("photographers", "VDL-005", entry["branded_name"],
                            "photographers.json")
        prompt = compose_prompt("VDL-005 White Field Intensity",
                                lock_tokens(entry), zone="lower-left")
        path = write_run(self.tmp / "run", sel, photo_entry(), prompt)
        proc = run(PROMPT_SCRIPT, str(path))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("subject zone", proc.stdout)
        self.assertIn("IMG-001", proc.stdout)

    def _cinematic_prompt(self):
        entry = CINE["entries"]["CIS-04"]
        tokens = all_tokens(entry["anchors"])
        element_f = ("LIGHTING + COLOR GRADE: Natural light carries the image; "
                     "one motivated source, deliberate contrast, protected "
                     "highlights.")
        return compose_prompt("CIS-04 Precision Storybook Geometry", tokens,
                              element_f=element_f,
                              element_g="PEOPLE / REPRESENTATION: No people "
                                        "appear in this scene; the built "
                                        "environment carries the story.")

    def test_cinematic_blend_with_owner_authorization_passes(self):
        entry = CINE["entries"]["CIS-04"]
        sel = selection_for(
            "cinematic", "CIS-04", entry["branded_name"], "cinematic.json",
            blend={"primary_style_id": "CIS-04",
                   "secondary_style_id": "CIS-35",
                   "secondary_traits": ["Natural light carries the image"],
                   "owner_authorized": True})
        path = write_run(self.tmp / "run", sel,
                         {"id": "IMG-001", "text_mode": "none"},
                         fit_prompt.fit_text(self._cinematic_prompt()))
        proc = run(PROMPT_SCRIPT, str(path))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_cinematic_blend_without_authorization_fails(self):
        entry = CINE["entries"]["CIS-04"]
        sel = selection_for(
            "cinematic", "CIS-04", entry["branded_name"], "cinematic.json",
            blend={"primary_style_id": "CIS-04",
                   "secondary_style_id": "CIS-35",
                   "secondary_traits": ["Natural light carries the image"],
                   "owner_authorized": False})
        path = write_run(self.tmp / "run", sel,
                         {"id": "IMG-001", "text_mode": "none"},
                         self._cinematic_prompt())
        proc = run(PROMPT_SCRIPT, str(path))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("owner authorization", proc.stdout)

    def _va_prompt(self, style_line="ART-31 URBAN PARADOX STENCIL",
                   subject_extra=""):
        entry = VA["entries"]["ART-31"]
        tokens = all_tokens(entry["mandatory_traits"])
        return compose_prompt(style_line, tokens, subject_extra=subject_extra,
                              element_g="PEOPLE / REPRESENTATION: Figures are "
                                        "graphic silhouettes in the stencil "
                                        "system; no photographic casting.")

    def test_visual_artists_selection_passes(self):
        entry = VA["entries"]["ART-31"]
        sel = selection_for("visual-artists", "ART-31", entry["branded_name"],
                            "visual-artists.json")
        path = write_run(self.tmp / "run", sel,
                         {"id": "IMG-001", "text_mode": "none"},
                         fit_prompt.fit_text(self._va_prompt()))
        proc = run(PROMPT_SCRIPT, str(path))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_visual_artists_second_system_contamination_fails(self):
        entry = VA["entries"]["ART-31"]
        sel = selection_for("visual-artists", "ART-31", entry["branded_name"],
                            "visual-artists.json")
        other = VA["entries"]["ART-41"]["branded_name"]
        prompt = self._va_prompt(
            subject_extra=f"The mood borrows {other} wholesale.")
        path = write_run(self.tmp / "run", sel,
                         {"id": "IMG-001", "text_mode": "none"}, prompt)
        proc = run(PROMPT_SCRIPT, str(path))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("contamination", proc.stdout)

    def test_visual_artists_missing_branded_name_fails(self):
        entry = VA["entries"]["ART-31"]
        sel = selection_for("visual-artists", "ART-31", entry["branded_name"],
                            "visual-artists.json")
        prompt = self._va_prompt(style_line="ART-31")
        path = write_run(self.tmp / "run", sel,
                         {"id": "IMG-001", "text_mode": "none"}, prompt)
        proc = run(PROMPT_SCRIPT, str(path))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("branded name", proc.stdout)

    def _procedural_prompt(self):
        return compose_prompt(
            "VDL-045 Editorial Metamorphosis", (),
            element_g="PEOPLE / REPRESENTATION: The declared character "
                      "archetype carries the scene; casting follows the "
                      "declaration block exactly.")

    def test_procedural_declaration_block_passes(self):
        entry = PHOTO["entries"]["VDL-045"]
        block = {field: f"declared {field} for this editorial world"
                 for field in ("era", "social_world", "character", "tone",
                               "set", "camera_language", "styling_logic",
                               "beauty_logic", "color_logic")}
        sel = selection_for("photographers", "VDL-045", entry["branded_name"],
                            "photographers.json", declaration_block=block)
        path = write_run(self.tmp / "run", sel,
                         {"id": "IMG-001", "text_mode": "none"},
                         fit_prompt.fit_text(self._procedural_prompt()))
        proc = run(PROMPT_SCRIPT, str(path))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("procedural", proc.stdout.lower())

    def test_procedural_incomplete_declaration_block_fails(self):
        entry = PHOTO["entries"]["VDL-045"]
        block = {field: f"declared {field}"
                 for field in ("era", "social_world", "character", "set",
                               "camera_language", "styling_logic",
                               "beauty_logic", "color_logic")}  # tone missing
        sel = selection_for("photographers", "VDL-045", entry["branded_name"],
                            "photographers.json", declaration_block=block)
        path = write_run(self.tmp / "run", sel,
                         {"id": "IMG-001", "text_mode": "none"},
                         self._procedural_prompt())
        proc = run(PROMPT_SCRIPT, str(path))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("declaration_block", proc.stdout)
        self.assertIn("tone", proc.stdout)


class TestImageSideB4(unittest.TestCase):
    """Amendment 6 Part B4: Blend Profile N/A handling and the
    distinctness register as the enforcement layer."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="item10-grade-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow unavailable")
        self.Image = Image

    def _brand(self, saturation_floor):
        path = self.tmp / "brand.json"
        path.write_text(json.dumps({"grade": {
            "min_mean_saturation": saturation_floor,
            "min_luma_std": None, "min_sharpness": None,
            "min_colorfulness": None}}), encoding="utf-8")
        return path

    def _bible(self, mode):
        path = self.tmp / "bible.json"
        path.write_text(json.dumps(
            {"blend_profile": {"hero_color_chroma": mode}}), encoding="utf-8")
        return path

    def _gray_image(self, name="Image-001.png", size=(300, 200), rgb=(128, 128, 128)):
        path = self.tmp / name
        self.Image.new("RGB", size, rgb).save(path)
        return path

    def test_suppress_makes_color_floors_na(self):
        brand = self._brand(0.20)
        img = self._gray_image()
        bible = self._bible("SUPPRESS")
        proc = run(GRADE_SCRIPT, str(img), "--brand", str(brand),
                   "--bible", str(bible))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("N/A", proc.stdout)
        self.assertIn("SUPPRESS", proc.stdout)

    def test_full_profile_gray_image_fails_saturation_floor(self):
        brand = self._brand(0.20)
        img = self._gray_image()
        bible = self._bible("FULL")
        proc = run(GRADE_SCRIPT, str(img), "--brand", str(brand),
                   "--bible", str(bible))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("mean_saturation", proc.stdout)

    def _register_inventory(self, continuity=False):
        def entry(id_, skin, hair, facial):
            e = {"id": id_,
                 "people": [{"skin_tone": skin, "hair": hair,
                             "facial_hair": facial}]}
            if continuity:
                e["continuity_rationale"] = (
                    "Same illustrative founder character by design; the "
                    "set plan declares her as the recurring guide.")
            return e
        inv = {"images": [
            entry("IMG-001", "deep brown", "short tapered natural cut", "clean-shaven"),
            entry("IMG-002", "deep brown", "short tapered natural cut", "clean-shaven"),
        ]}
        path = self.tmp / "image-inventory.json"
        path.write_text(json.dumps(inv), encoding="utf-8")
        return path

    def _pattern_image(self, name, size, painter):
        path = self.tmp / name
        img = self.Image.new("RGB", size)
        px = img.load()
        for y in range(size[1]):
            for x in range(size[0]):
                px[x, y] = painter(x, y)
        img.save(path)
        return path

    def test_repeated_register_combination_fails(self):
        brand = self._brand(None)
        img1 = self._pattern_image("Image-001.png", (300, 200),
                                   lambda x, y: (x % 256, 30, 30))
        img2 = self._pattern_image("Image-002.png", (320, 200),
                                   lambda x, y: (30, 30, 255 if (x // 16) % 2 else 40))
        inv = self._register_inventory(continuity=False)
        proc = run(GRADE_SCRIPT, str(img1), str(img2), "--brand", str(brand),
                   "--inventory", str(inv))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("register:", proc.stdout)
        self.assertIn("IMG-001", proc.stdout)
        self.assertIn("IMG-002", proc.stdout)

    def test_register_combination_with_continuity_recorded_passes(self):
        brand = self._brand(None)
        img1 = self._pattern_image("Image-001.png", (300, 200),
                                   lambda x, y: (x % 256, 30, 30))
        img2 = self._pattern_image("Image-002.png", (320, 200),
                                   lambda x, y: (30, 30, 255 if (x // 16) % 2 else 40))
        inv = self._register_inventory(continuity=True)
        proc = run(GRADE_SCRIPT, str(img1), str(img2), "--brand", str(brand),
                   "--inventory", str(inv))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("register:", proc.stdout)


if __name__ == "__main__":
    unittest.main()
