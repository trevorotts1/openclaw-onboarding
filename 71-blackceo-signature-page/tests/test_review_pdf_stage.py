#!/usr/bin/env python3
"""The client never receives loose section images: each image stage ends by
combining its sections, in section order, into validator-gated desktop and
mobile review PDFs (scripts/combine_review_pdf.py --stage)."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import combine_review_pdf as crp  # noqa: E402
import validate_review_pdf as vrp  # noqa: E402
import deliverable_labels as dl  # noqa: E402

spec = importlib.util.spec_from_file_location("stage_executor", SCRIPTS / "stage_executor.py")
exe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exe)

HEIGHTS = [300, 420, 360]  # unequal on purpose: pages keep each section's own height


def make_images(run, stage, template, width, sections=(1, 2, 3)):
    from PIL import Image, ImageDraw
    for n in sections:
        path = run / stage / template.format(n=n)
        path.parent.mkdir(parents=True, exist_ok=True)
        im = Image.new("RGB", (width, HEIGHTS[n - 1]), (40 * n, 90, 200 - 30 * n))
        ImageDraw.Draw(im).text((10, 10), f"SECTION {n}", fill="white")
        im.save(path)


def old_style_pdf(images, out):
    """The retired layout, rebuilt here only to prove the guard rejects it: a header band
    and a footer band on EVERY page (the notes in the middle of the wireframe PDF)."""
    from PIL import Image
    pages = []
    for p in images:
        im = Image.open(p).convert("RGB")
        w, h = im.size
        bh = max(56, round(w * 0.04))
        page = Image.new("RGB", (w, h + 2 * bh), (242, 242, 242))
        page.paste(im, (0, bh))
        pages.append(page)
    pages[0].save(out, "PDF", save_all=True, append_images=pages[1:], resolution=144)


class Kie:  # compose() only reads provider.name
    name = "kie"


class ReviewPdfStageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, script, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                              capture_output=True, text=True)

    def test_sales_page_deliverables_are_named_sales_not_landing(self):
        (self.run_dir / "intake.json").write_text(json.dumps({"page_role": "landing", "page_kind": "sales"}))
        role = dl.declared_page_role(self.run_dir)
        self.assertEqual(dl.title_band(role, "desktop", "desktop-wireframe", 10),
                         "SIGNATURE SALES PAGE \u00b7 DESKTOP WIREFRAME \u00b7 10 SECTIONS")
        self.assertEqual(dl.pdf_name(role, "desktop", "desktop-wireframe"), "sales-page_DESKTOP_WIREFRAMES.pdf")
        (self.run_dir / "intake.json").write_text(json.dumps({"page_role": "landing", "page_kind": "opt_in"}))
        self.assertEqual(dl.declared_page_role(self.run_dir), "landing")

    def test_every_stage_gets_named_ordered_pdfs_at_native_size(self):
        make_images(self.run_dir, "final-mockups", "desktop/part-{n:02d}.png", 600)
        make_images(self.run_dir, "final-mockups", "mobile/part-{n:02d}.png", 200)
        proc = self.cli("combine_review_pdf.py", self.run_dir, "--stage", "final-mockups", "--expect", 3)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        review = self.run_dir / "review-pdfs"
        for name, width in (("landing_DESKTOP_MOCKUPS-FINAL.pdf", 600), ("landing_MOBILE_MOCKUPS-FINAL.pdf", 200)):
            sizes = vrp.page_sizes(review / name)
            band = dl.band_height(width)  # 144 dpi: 1px = 0.5pt; ONE title band, on page 1 only
            self.assertEqual([round(h * 2) for _, h in sizes], [HEIGHTS[0] + band, HEIGHTS[1], HEIGHTS[2]])
            self.assertTrue(all(round(w * 2) == width for w, _ in sizes))
            receipt = json.loads((review / (name + ".manifest.json")).read_text())
            device = "DESKTOP" if "DESKTOP" in name else "MOBILE"
            self.assertEqual([p["label"] for p in receipt["pages"]],
                             [f"SIGNATURE LANDING PAGE \u00b7 {device} MOCKUP \u00b7 SECTION {n} OF 3" for n in (1, 2, 3)])
            self.assertEqual([Path(p["path"]).name for p in receipt["pages"]],
                             ["part-01.png", "part-02.png", "part-03.png"])
        self.assertEqual(self.cli("validate_review_pdf.py", self.run_dir, "--stage", "final-mockups").returncode, 0)
        # labeled section images sit in the client folders, named by page type + device + kind + section
        self.assertEqual(sorted(p.name for p in (review / "mobile-mockups").iterdir()),
                         [f"landing_mobile_mockup-final_s0{n}-of-03_section-{n}.png" for n in (1, 2, 3)])

    def test_no_notes_between_sections_one_title_band_on_page_one_only(self):
        from PIL import Image
        make_images(self.run_dir, "desktop-wireframe", "section-{n:02d}.png", 600)
        self.assertEqual(self.cli("combine_review_pdf.py", self.run_dir, "--stage", "desktop-wireframe").returncode, 0)
        review = self.run_dir / "review-pdfs"
        manifest = json.loads((review / "landing_DESKTOP_WIREFRAMES.order.json").read_text())
        self.assertEqual(manifest["pages"][0]["title"], "SIGNATURE LANDING PAGE \u00b7 DESKTOP WIREFRAME \u00b7 3 SECTIONS")
        self.assertTrue(all("title" not in p and "band" not in p for p in manifest["pages"][1:]))
        self.assertEqual(dl.title_band("downsell_1", "desktop", "desktop-wireframe", 8),
                         "DOWNSELL 1 \u00b7 DESKTOP WIREFRAME \u00b7 8 SECTIONS")
        # render: page 2 and the last page are the bare section image, edge to edge, no label of any kind
        import pypdf
        for n in (1, 2):
            src = Image.open(self.run_dir / "desktop-wireframe" / f"section-0{n + 1}.png").convert("RGB")
            self.assertEqual(vrp.page_sizes(review / "landing_DESKTOP_WIREFRAMES.pdf")[n][1] * 2, src.size[1])
        self.assertEqual(len(pypdf.PdfReader(str(review / "landing_DESKTOP_WIREFRAMES.pdf")).pages), 3)

    def test_old_layout_with_bands_between_sections_fails_the_validator(self):
        make_images(self.run_dir, "desktop-wireframe", "section-{n:02d}.png", 600)
        self.assertEqual(self.cli("combine_review_pdf.py", self.run_dir, "--stage", "desktop-wireframe").returncode, 0)
        review = self.run_dir / "review-pdfs"
        name = "landing_DESKTOP_WIREFRAMES.pdf"
        manifest = review / "landing_DESKTOP_WIREFRAMES.order.json"
        sources = [self.run_dir / "desktop-wireframe" / f"section-0{n}.png" for n in (1, 2, 3)]
        self.assertEqual(vrp.check_geometry(review / name, sources), [])  # the new layout passes
        # swap in a PDF built the OLD way (header + footer on every page) with a receipt that honestly matches it
        old_style_pdf(sources, review / name)
        receipt = json.loads((review / (name + ".manifest.json")).read_text())
        receipt["pdf_sha256"] = vrp.sha256(review / name)
        (review / (name + ".manifest.json")).write_text(json.dumps(receipt))
        proc = self.cli("validate_review_pdf.py", manifest)
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("no notes between sections", proc.stdout)
        self.assertTrue(any("Page 2" in e for e in vrp.check_geometry(review / name, sources)))
        # the stage gate (the form delivery and the stage contract run) refuses it too
        self.assertEqual(self.cli("validate_review_pdf.py", self.run_dir, "--stage", "desktop-wireframe").returncode, 1)
        # a band only on the last page, or a title band repeated on page 2, fails the same way
        from PIL import Image
        bare = [Image.open(p).convert("RGB") for p in sources]
        for variant in ("footer-on-last", "title-on-page-2"):
            pages = list(bare)
            if variant == "footer-on-last":
                pages[2] = Image.new("RGB", (600, HEIGHTS[2] + 60), "gray"); pages[2].paste(bare[2], (0, 0))
            else:
                pages[1] = Image.new("RGB", (600, HEIGHTS[1] + dl.band_height(600)), "gray"); pages[1].paste(bare[1], (0, dl.band_height(600)))
            first = Image.new("RGB", (600, HEIGHTS[0] + dl.band_height(600)), "gray"); first.paste(pages[0], (0, dl.band_height(600)))
            pdf = self.run_dir / f"{variant}.pdf"
            first.save(pdf, "PDF", save_all=True, append_images=pages[1:], resolution=144)
            self.assertTrue(vrp.check_geometry(pdf, sources), variant)

    def test_manifest_declaring_a_band_on_a_later_page_is_refused_at_compose_and_validate(self):
        make_images(self.run_dir, "desktop-wireframe", "section-{n:02d}.png", 600)
        self.assertEqual(self.cli("combine_review_pdf.py", self.run_dir, "--stage", "desktop-wireframe").returncode, 0)
        path = self.run_dir / "review-pdfs" / "landing_DESKTOP_WIREFRAMES.order.json"
        data = json.loads(path.read_text())
        data["pages"][1]["band"] = {"top": ["x"], "bottom": ["y"]}
        path.write_text(json.dumps(data))
        proc = self.cli("combine_review_pdf.py", path, "--overwrite")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("no notes between sections", proc.stdout)
        self.assertEqual(self.cli("validate_review_pdf.py", path).returncode, 1)

    def test_wireframe_stage_contract_runs_the_pdf_validator_and_a_swapped_wireframe_pdf_fails(self):
        contract = json.loads((SCRIPTS.parent / "references" / "stage-contract.json").read_text())
        stages = contract.get("stages", contract)
        for st in ("desktop-wireframe", "mobile-tablet", "visual-mockup", "final-mockups"):
            self.assertIn(f"python3 scripts/validate_review_pdf.py {{run_dir}} --stage {st}", stages[st]["validators"])
        make_images(self.run_dir, "desktop-wireframe", "section-{n:02d}.png", 600)
        self.assertEqual(self.cli("combine_review_pdf.py", self.run_dir, "--stage", "desktop-wireframe").returncode, 0)
        gate = lambda: self.cli("validate_review_pdf.py", self.run_dir, "--stage", "desktop-wireframe")
        self.assertEqual(gate().returncode, 0)
        old_style_pdf([self.run_dir / "desktop-wireframe" / f"section-0{n}.png" for n in (1, 2, 3)],
                      self.run_dir / "desktop-wireframe" / "wireframe.pdf")  # the contract copy, hand-swapped
        self.assertEqual(gate().returncode, 1)

    def test_wireframe_stage_also_writes_the_contract_wireframe_pdf(self):
        make_images(self.run_dir, "desktop-wireframe", "section-{n:02d}.png", 600)
        self.assertEqual(self.cli("combine_review_pdf.py", self.run_dir, "--stage", "desktop-wireframe").returncode, 0)
        self.assertTrue((self.run_dir / "review-pdfs" / "landing_DESKTOP_WIREFRAMES.pdf").is_file())
        self.assertTrue((self.run_dir / "desktop-wireframe" / "wireframe.pdf").is_file())

    def test_a_missing_section_is_refused_and_leaves_no_pdf(self):
        make_images(self.run_dir, "mobile-tablet", "section-{n:02d}.png", 200, sections=(1, 3))
        proc = self.cli("combine_review_pdf.py", self.run_dir, "--stage", "mobile-tablet")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("not contiguous", proc.stdout)
        self.assertFalse(list((self.run_dir).rglob("*.pdf")))

    def test_wrong_section_count_is_refused(self):
        make_images(self.run_dir, "mobile-tablet", "section-{n:02d}.png", 200, sections=(1, 2))
        proc = self.cli("combine_review_pdf.py", self.run_dir, "--stage", "mobile-tablet", "--expect", 3)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("expected sections", proc.stdout)

    def test_validator_rejects_a_stretched_page(self):
        from PIL import Image
        a, b = self.run_dir / "a.png", self.run_dir / "b.png"
        Image.new("RGB", (400, 300), "white").save(a)
        Image.new("RGB", (400, 600), "white").save(b)
        pdf = self.run_dir / "x.pdf"
        crp.add_title_band(Image.open(a).convert("RGB"), "TITLE").save(pdf, "PDF", resolution=144)  # page 1 = image + the one title band
        self.assertEqual(vrp.check_geometry(pdf, [a]), [])
        self.assertTrue(any("cropped, stretched or padded" in e for e in vrp.check_geometry(pdf, [b])))

    def test_validator_catches_a_delivered_folder_that_drifted_from_the_pdf(self):
        import shutil
        make_images(self.run_dir, "mobile-tablet", "section-{n:02d}.png", 200)
        self.assertEqual(self.cli("combine_review_pdf.py", self.run_dir, "--stage", "mobile-tablet").returncode, 0)
        manifest = self.run_dir / "review-pdfs" / "landing_MOBILE_WIREFRAMES.order.json"
        delivered = self.run_dir / "delivered"
        shutil.copytree(self.run_dir / "mobile-tablet", delivered)
        self.assertEqual(self.cli("validate_review_pdf.py", manifest, "--delivered", delivered).returncode, 0)
        # the client's copy of one section is a different image from the one the PDF holds
        from PIL import Image
        Image.new("RGB", (200, HEIGHTS[1]), "black").save(delivered / "section-02.png")
        proc = self.cli("validate_review_pdf.py", manifest, "--delivered", delivered)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("different images", proc.stdout)

    def test_a_stale_delivered_pdf_fails_the_gate_and_deliver_refreshes_it(self):
        from PIL import Image
        make_images(self.run_dir, "mobile-tablet", "section-{n:02d}.png", 200)
        client = self.run_dir / "client-pdfs"
        gate = lambda *a: self.cli("validate_review_pdf.py", self.run_dir, "--stage", "mobile-tablet", *a)
        proc = self.cli("combine_review_pdf.py", self.run_dir, "--stage", "mobile-tablet", "--deliver", client)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        built = self.run_dir / "review-pdfs" / "landing_MOBILE_WIREFRAMES.pdf"
        mine = client / "mobile-wireframes" / "landing_MOBILE_WIREFRAMES.pdf"  # client folder = the category name
        self.assertEqual(vrp.sha256(mine), vrp.sha256(built))
        self.assertEqual(gate("--delivered-pdfs", client).returncode, 0)
        # a section is redone and the PDF rebuilt, but nobody copies it over: the client's PDF is the old build
        Image.new("RGB", (200, HEIGHTS[1]), "black").save(self.run_dir / "mobile-tablet" / "section-02.png")
        self.assertEqual(self.cli("combine_review_pdf.py", self.run_dir, "--stage", "mobile-tablet").returncode, 0)
        proc = gate("--delivered-pdfs", client)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("stale or different PDF", proc.stdout)
        manifest = self.run_dir / "review-pdfs" / "landing_MOBILE_WIREFRAMES.order.json"
        self.assertEqual(self.cli("validate_review_pdf.py", manifest, "--delivered-pdf", mine).returncode, 1)
        mine.unlink()
        self.assertIn("is missing", gate("--delivered-pdfs", client).stdout)
        # re-running the build with --deliver replaces the client's copy and the gate passes again
        self.assertEqual(self.cli("combine_review_pdf.py", self.run_dir, "--stage", "mobile-tablet", "--deliver", client).returncode, 0)
        self.assertEqual(gate("--delivered-pdfs", client).returncode, 0)

    def test_stage_validator_fails_when_pdf_was_never_built(self):
        make_images(self.run_dir, "mobile-tablet", "section-{n:02d}.png", 200)
        proc = self.cli("validate_review_pdf.py", self.run_dir, "--stage", "mobile-tablet")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("never built", proc.stdout)

    def test_executor_compose_runs_the_combine_step_and_stub_does_not(self):
        make_images(self.run_dir, "visual-mockup", "desktop/part-{n:02d}.png", 600)
        make_images(self.run_dir, "visual-mockup", "mobile/part-{n:02d}.png", 200)
        done = exe.compose("visual-mockup", self.run_dir, Kie(), 3)
        self.assertEqual(done["review_pdf"]["status"], "pass", done)
        self.assertTrue((self.run_dir / "review-pdfs" / "landing_MOBILE_MOCKUPS-VISUAL.pdf").is_file())
        self.assertEqual(exe.compose("visual-mockup", self.run_dir, exe.StubProvider(), 3)["status"], "skipped")
        short = exe.compose("visual-mockup", self.run_dir, Kie(), 4)
        self.assertEqual(short["review_pdf"]["status"], "fail")


if __name__ == "__main__":
    unittest.main(verbosity=2)
