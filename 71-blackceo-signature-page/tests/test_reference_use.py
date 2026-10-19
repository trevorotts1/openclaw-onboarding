#!/usr/bin/env python3
"""Reference images are structure only: the prompt block and the bleed check.

Pins references/reference-image-use.md:
  - every stage that attaches reference images carries the labelled block,
    and a request with no reference carries none;
  - the block fits the model's prompt budget next to the copy and the
    other contract blocks, and copy still comes first;
  - the QC check flags an output that reuses the reference's palette or
    brand text, passes a clean output, and never reports PASS for a
    reference it cannot fingerprint or a leg it could not run.

No network, no paid call, no generation.
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from brand_fixture import give_blackceo_colors  # noqa: E402
try:
    from PIL import Image
except ImportError:
    print("SKIPMOD Pillow not importable (reference_use pixel tests need it)")
    sys.exit(0)


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ru = load("reference_use")
exe = load("stage_executor")

LIB = ru.load_library()
BOARD = next(e for e in LIB["references"] if e["kind"] == "design-board")
SECTION = {"section_id": "S01", "section_name": "Hero",
           "copy": "Everything your client needs. CTA: BOOK NOW.",
           "slots": [{"slot_id": "IMG-001", "aspect_ratio": "3:4", "art_direction": "Desk."}]}
REQUEST = {"model": "gpt-image-2-5-sunburst-image-to-image", "style": "warm editorial",
           "stage_prompts": {"visual-mockup": "Mockup {section_name} at {width}px. {copy}"}}


def resolved_roles():
    """The page color system roles of a run with BlackCEO's colors (mockup prompts refuse without)."""
    with tempfile.TemporaryDirectory() as tmp:
        give_blackceo_colors(tmp)
        return exe.hypersaturation.roles_for_run(Path(tmp))


REQUEST["_hypersat"] = resolved_roles()


def bands(path, colors, size=(600, 400)):
    img = Image.new("RGB", size)
    step = size[0] // len(colors)
    for i, code in enumerate(colors):
        img.paste(ru._rgb(code), (i * step, 0, (i + 1) * step if i < len(colors) - 1 else size[0], size[1]))
    img.save(path)
    return path


class BlockTests(unittest.TestCase):
    def test_block_labelled_with_take_and_never(self):
        block = ru.reference_block([BOARD["url"]], ["design-board"])
        self.assertTrue(block.startswith("REFERENCE IMAGE - structure only."))
        for take in ("layout grid and block arrangement", "section order and rhythm",
                     "information hierarchy", "density and whitespace balance",
                     "composition and framing", "annotated or grouped", "level of polish"):
            self.assertIn(take, block)
        for never in ("color palette or gradients", "font styling", "logo",
                      "brand names", "people, photography subjects or icons",
                      "client identity"):
            self.assertIn(never, block)
        for owner in ("resolved brand palette", "logo only from this client",
                      "selected images", "this client's copy"):
            self.assertIn(owner, block)
        self.assertIn("(design-board)", block)
        self.assertNotIn("Set for Life", block)

    def test_no_reference_no_block_and_dedup_and_role_filter(self):
        self.assertEqual(ru.reference_block([]), "")
        self.assertEqual(ru.reference_block(None), "")
        block = ru.reference_block(["https://a/x.png", "https://a/x.png", "https://a/y.png"],
                                   ["mock up!", "wireframe"])
        self.assertIn("first 2 attached images", block)
        self.assertNotIn("mock up!", block)

    def test_stage_prompt_carries_block_after_copy_within_budget(self):
        req = dict(REQUEST, references=[BOARD["url"]], reference_roles=["design-board"])
        prompt, sizes = exe.stage_prompt("visual-mockup", SECTION, 1, 1440, req, "3:4",
                                         with_sizes=True)
        self.assertTrue(prompt.startswith("VERBATIM COPY"))
        self.assertLess(prompt.index("REFERENCE IMAGE - structure only"),
                        prompt.index("FRAME CONTRACT"))
        self.assertLessEqual(sizes["chars"], sizes["max_chars"])
        bare = exe.stage_prompt("visual-mockup", SECTION, 1, 1440, REQUEST, "3:4")
        self.assertNotIn("REFERENCE IMAGE", bare)

    def test_item_prompt_gets_block_and_cap_is_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            give_blackceo_colors(run)  # an item image is graded in the client's palette
            (run / "image-inventory-prompts").mkdir()
            (run / "image-inventory-prompts" / "IMG-001.txt").write_text("A desk.", encoding="utf-8")
            seen = {}

            class Spy:
                name, mode = "stub", "stub"

                def generate(self, job, request):
                    seen["prompt"] = job["prompt"]
                    exe.stub_png(job["out"], 64, 64, "x")
                    return {"provider": "stub", "mode": "stub", "model": "m"}

            req = {"references": [BOARD["url"]]}
            exe.run_item(run, "image-generation-qc", "IMG-001", req, Spy(), False)
            self.assertTrue(seen["prompt"].startswith("REFERENCE IMAGE - structure only"))
            self.assertTrue(seen["prompt"].endswith("A desk."))


class LibraryTests(unittest.TestCase):
    def test_library_entries_are_public_links_with_fingerprints(self):
        self.assertGreaterEqual(len(LIB["references"]), 3)
        for e in LIB["references"]:
            self.assertTrue(e["url"].startswith("https://assets.cdn.filesafe.space/"), e["name"])
            self.assertEqual(len(e["sha256"]), 64)
            self.assertIn("signature_palette", e)
            self.assertTrue(e["brand_text"])
        self.assertEqual(sorted(ru.library_urls("design-board")), [BOARD["url"]])

    def test_bundled_references_match_their_recorded_hash(self):
        for e in LIB["references"]:
            path = ROOT / e["origin"]
            if path.is_file():
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), e["sha256"], e["name"])


class BleedCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_fixture_reusing_the_reference_palette_is_flagged(self):
        out = bands(self.dir / "reuse.png", BOARD["signature_palette"])
        result = ru.check(out, [BOARD["url"]], ocr=False)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["palette"]["status"], "FAIL")
        self.assertTrue(result["palette"]["reasons"])

    def test_clean_fixture_passes(self):
        out = bands(self.dir / "clean.png", ["#1F3A93", "#F28C28", "#0B7A75", "#FFFFFF"])
        result = ru.check(out, [BOARD["url"]], text="Book your seat today", ocr=False)
        self.assertEqual(result["status"], "PASS", result)

    def test_clients_own_palette_is_never_bleed(self):
        out = bands(self.dir / "own.png", BOARD["signature_palette"])
        result = ru.check(out, [BOARD["url"]], client_palette=BOARD["signature_palette"], ocr=False)
        self.assertEqual(result["palette"]["status"], "PASS")

    def test_reference_brand_text_is_flagged_and_clean_text_is_not(self):
        out = bands(self.dir / "t.png", ["#1F3A93", "#FFFFFF"])
        bad = ru.check(out, [BOARD["url"]], text="Welcome. A richer you lives here!", ocr=False)
        self.assertEqual(bad["status"], "FAIL")
        self.assertIn("A richer you lives here", bad["text"]["found"])
        good = ru.check(out, [BOARD["url"]], text="A steadier business lives here.", ocr=False)
        self.assertEqual(good["status"], "PASS")

    def test_unknown_reference_and_missing_ocr_are_undetermined_never_pass(self):
        out = bands(self.dir / "u.png", ["#1F3A93", "#FFFFFF"])
        unknown = ru.check(out, ["https://example.com/unknown.png"], ocr=False)
        self.assertEqual(unknown["status"], "UNDETERMINED")
        self.assertEqual(ru.check(out, [BOARD["url"]], ocr=False)["status"], "UNDETERMINED")  # text leg never ran
        real_which = ru.shutil.which
        ru.shutil.which = lambda _name: None
        try:
            noocr = ru.check(out, [BOARD["url"]], ocr=True)
        finally:
            ru.shutil.which = real_which
        self.assertEqual(noocr["status"], "UNDETERMINED")
        self.assertTrue(any("OCR unavailable" in p for p in noocr["problems"]))

    def test_unreadable_image_is_undetermined_not_a_crash(self):
        junk = self.dir / "junk.png"
        junk.write_text("not an image", encoding="utf-8")
        result = ru.check(junk, [BOARD["url"]], text="Book your seat today", ocr=False)
        self.assertEqual(result["status"], "UNDETERMINED")
        self.assertEqual(result["palette"]["status"], "UNDETERMINED")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ru.main(["check", str(junk), "--reference", BOARD["url"], "--no-ocr"]), 3)

    def test_item_and_stage_images_both_record_bleed_and_survive_junk(self):
        class Paid:
            name, mode = "kie", "paid"

            def __init__(self, colors):
                self.colors = colors

            def generate(self, job, request):
                job["out"].parent.mkdir(parents=True, exist_ok=True)
                if self.colors:
                    bands(job["out"], self.colors)
                else:
                    job["out"].write_text("junk", encoding="utf-8")
                return {"provider": "kie", "mode": "paid", "model": "m"}

        give_blackceo_colors(self.dir)
        prompts = self.dir / "image-inventory-prompts"
        prompts.mkdir()
        (prompts / "IMG-001.txt").write_text("A desk.", encoding="utf-8")
        req = {"references": [BOARD["url"]]}
        with contextlib.redirect_stdout(io.StringIO()):
            bad = exe.run_item(self.dir, "image-generation-qc", "IMG-001", req,
                               Paid(BOARD["signature_palette"]), False)
            self.assertEqual(bad["reference_bleed"]["status"], "FAIL")
            junk = exe.run_item(self.dir, "image-generation-qc", "IMG-001", req, Paid(None), True)
        self.assertEqual(junk["reference_bleed"]["status"], "UNDETERMINED")
        saved = json.loads((self.dir / "image-generation-qc" / exe.RECORD).read_text())
        self.assertEqual(saved["items"][0]["reference_bleed"]["status"], "UNDETERMINED")
        self.assertNotIn("reference_bleed", exe.run_item(
            self.dir, "image-generation-qc", "IMG-001", {}, Paid(["#1F3A93"]), True))

    def test_cli_exit_codes(self):
        bad = bands(self.dir / "cli-bad.png", BOARD["signature_palette"])
        good = bands(self.dir / "cli-good.png", ["#1F3A93", "#F28C28", "#FFFFFF"])
        words = self.dir / "words.txt"
        words.write_text("Book your seat today", encoding="utf-8")
        args = ["--reference", BOARD["url"], "--no-ocr", "--text-file", str(words)]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ru.main(["check", str(bad)] + args), 1)
            self.assertEqual(ru.main(["check", str(good)] + args), 0)
            self.assertEqual(ru.main(["check", str(good), "--reference", BOARD["url"], "--no-ocr"]), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
