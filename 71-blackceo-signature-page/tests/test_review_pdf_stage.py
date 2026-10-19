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

    def test_every_stage_gets_named_ordered_pdfs_at_native_size(self):
        make_images(self.run_dir, "final-mockups", "desktop/part-{n:02d}.png", 600)
        make_images(self.run_dir, "final-mockups", "mobile/part-{n:02d}.png", 200)
        proc = self.cli("combine_review_pdf.py", self.run_dir, "--stage", "final-mockups", "--expect", 3)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        review = self.run_dir / "review-pdfs"
        for name, width in (("final-mockups-desktop.pdf", 600), ("final-mockups-mobile.pdf", 200)):
            sizes = vrp.page_sizes(review / name)
            self.assertEqual([round(h * 2) for _, h in sizes], HEIGHTS)  # 144 dpi: 1px = 0.5pt
            self.assertTrue(all(round(w * 2) == width for w, _ in sizes))
            receipt = json.loads((review / (name + ".manifest.json")).read_text())
            self.assertEqual([p["label"] for p in receipt["pages"]], ["Part-A", "Part-B", "Part-C"])
            self.assertEqual([Path(p["path"]).name for p in receipt["pages"]],
                             ["part-01.png", "part-02.png", "part-03.png"])
        self.assertEqual(self.cli("validate_review_pdf.py", self.run_dir, "--stage", "final-mockups").returncode, 0)

    def test_wireframe_stage_also_writes_the_contract_wireframe_pdf(self):
        make_images(self.run_dir, "desktop-wireframe", "section-{n:02d}.png", 600)
        self.assertEqual(self.cli("combine_review_pdf.py", self.run_dir, "--stage", "desktop-wireframe").returncode, 0)
        self.assertTrue((self.run_dir / "review-pdfs" / "wireframes-desktop.pdf").is_file())
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
        Image.open(a).save(pdf, "PDF", resolution=144)
        self.assertEqual(vrp.check_geometry(pdf, [a]), [])
        self.assertTrue(any("cropped, stretched or padded" in e for e in vrp.check_geometry(pdf, [b])))

    def test_validator_catches_a_delivered_folder_that_drifted_from_the_pdf(self):
        import shutil
        make_images(self.run_dir, "mobile-tablet", "section-{n:02d}.png", 200)
        self.assertEqual(self.cli("combine_review_pdf.py", self.run_dir, "--stage", "mobile-tablet").returncode, 0)
        manifest = self.run_dir / "review-pdfs" / "wireframes-mobile.order.json"
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
        built = self.run_dir / "review-pdfs" / "wireframes-mobile.pdf"
        self.assertEqual(vrp.sha256(client / "wireframes-mobile.pdf"), vrp.sha256(built))
        self.assertEqual(gate("--delivered-pdfs", client).returncode, 0)
        # a section is redone and the PDF rebuilt, but nobody copies it over: the client's PDF is the old build
        Image.new("RGB", (200, HEIGHTS[1]), "black").save(self.run_dir / "mobile-tablet" / "section-02.png")
        self.assertEqual(self.cli("combine_review_pdf.py", self.run_dir, "--stage", "mobile-tablet").returncode, 0)
        proc = gate("--delivered-pdfs", client)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("stale or different PDF", proc.stdout)
        manifest = self.run_dir / "review-pdfs" / "wireframes-mobile.order.json"
        self.assertEqual(self.cli("validate_review_pdf.py", manifest, "--delivered-pdf", client / "wireframes-mobile.pdf").returncode, 1)
        (client / "wireframes-mobile.pdf").unlink()
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
        self.assertTrue((self.run_dir / "review-pdfs" / "visual-mockups-mobile.pdf").is_file())
        self.assertEqual(exe.compose("visual-mockup", self.run_dir, exe.StubProvider(), 3)["status"], "skipped")
        short = exe.compose("visual-mockup", self.run_dir, Kie(), 4)
        self.assertEqual(short["review_pdf"]["status"], "fail")


if __name__ == "__main__":
    unittest.main(verbosity=2)
