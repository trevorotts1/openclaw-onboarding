#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_page_image_inputs.py - the wrappers take the shared image inputs file and put every design
file in the page result. Real Skill 71 pipeline, free stub provider, no network, no paid call.
Run: python3 test_page_image_inputs.py [-v] (from scripts/).
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import collect_launch_receipts as receipts  # noqa: E402
import page_set as ps  # noqa: E402
from test_checkout_wrapper import CheckoutWrapperCase, MANUSCRIPT, WRAPPER as CHECKOUT  # noqa: E402
import test_downsell_wrapper as tdw  # noqa: E402

REPO = HERE.parents[1]


def write_inputs(directory, brand_file, **over):
    doc = {"design_style": "B", "brand_file": str(brand_file), "brand_owner": "blackceo", "image_cap": 40,
           "image_provider": "stub"}
    doc.update(over)
    path = Path(directory) / "image_inputs.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


class CheckoutTakesTheSharedInputs(CheckoutWrapperCase):
    def run_checkout(self, inputs):
        cmd = [sys.executable, str(CHECKOUT), "--request", str(self.request_path), "--result", str(self.result_path),
               "--manuscript", str(MANUSCRIPT), "--launch", str(self.launch_path),
               "--route-graph", str(self.graph_path), "--run-dir", str(self.run_dir),
               "--model", "STUB-NO-MODEL", "--image-inputs", str(inputs)]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    def test_one_file_replaces_the_brand_owner_cap_and_style_flags(self):
        bible = self.td / "bible.json"
        bible.write_text('{"design_style": "B"}', encoding="utf-8")
        inputs = write_inputs(self.td, self.brand_path, visual_bible_ref=str(bible))
        proc = self.run_checkout(inputs)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = json.loads(self.result_path.read_text(encoding="utf-8"))
        self.assertEqual(receipts.validate_result(result, self.request), [])
        intake = json.loads((self.run_dir / "intake.json").read_text(encoding="utf-8"))
        self.assertEqual(intake["design_style"], "B")
        # every design file is in the result: 20 section images plus the records and the visual bible
        names = [Path(a["path"]).relative_to(self.run_dir).as_posix() for a in result["artifacts"]]
        self.assertEqual(len([n for n in names if n.endswith(".png")]), 20)
        self.assertIn("visual-bible.json", names)
        got = ps.check_deliverables("checkout", self.run_dir, rendered=False)
        self.assertTrue(got["images_complete"], got)
        self.assertFalse(got["complete"], "a stub run has no review PDFs or boards yet")
        self.assertEqual(len(got["render_pending"]), 5)

    def test_the_paid_provider_without_the_clients_approval_is_refused_plainly(self):
        proc = self.run_checkout(write_inputs(self.td, self.brand_path, image_provider="kie"))
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("paid_render_approval_ref", proc.stderr)
        self.assertFalse(self.result_path.exists())

    def test_an_agnes_launch_is_refused_by_name(self):
        proc = self.run_checkout(write_inputs(self.td, self.brand_path, image_provider="agnes"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("agnes", proc.stderr)

    def test_a_flag_typed_on_the_command_line_still_wins(self):
        inputs = write_inputs(self.td, self.brand_path, design_style="A")
        cmd = [sys.executable, str(CHECKOUT), "--request", str(self.request_path), "--result", str(self.result_path),
               "--manuscript", str(MANUSCRIPT), "--launch", str(self.launch_path),
               "--route-graph", str(self.graph_path), "--run-dir", str(self.run_dir),
               "--model", "STUB-NO-MODEL", "--image-inputs", str(inputs), "--design-style", "C"]
        self.assertEqual(subprocess.run(cmd, capture_output=True, text=True).returncode, 0)
        intake = json.loads((self.run_dir / "intake.json").read_text(encoding="utf-8"))
        self.assertEqual(intake["design_style"], "C")


class SecondDownsellIsLabelledDownsell2(unittest.TestCase):
    stage_images = tdw.DownsellWrapperImagesTests.stage_images  # the staged downsell run, reused as is

    def run_second(self, paths, inputs, *extra):
        cmd = [sys.executable, str(tdw.WRAPPER), "--request", str(paths["request-downsell_1.json"]),
               "--result", str(paths["workdir"] / "page-result-downsell_2.json"),
               "--launch", str(paths["launch.json"]), "--route-graph", str(paths["route-graph.json"]),
               "--copy", str(paths["copy-downsell_1.json"]), "--skill71-root", str(tdw.SKILL71),
               "--role-instance", "downsell_2", "--image-inputs", str(inputs), *extra]
        return subprocess.run(cmd, capture_output=True, text=True, cwd=str(paths["workdir"]))

    def test_downsell_2_gets_its_own_wireframes_and_mockups_and_an_honest_result(self):
        paths = self.stage_images()
        proc = self.run_second(paths, write_inputs(paths["workdir"], paths["brand"]))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        summary = json.loads(proc.stdout)
        run_dir = Path(summary["images"]["run_dir"])
        self.assertEqual(run_dir.name, "downsell_2-images")
        got = ps.check_deliverables("downsell_2", run_dir, rendered=False)
        self.assertTrue(got["images_complete"], got)
        result = json.loads((paths["workdir"] / "page-result-downsell_2.json").read_text(encoding="utf-8"))
        self.assertEqual((result["status"], result["proof_class"]), ("authored", "L0"))
        self.assertTrue(any(b.startswith("D2-DESIGN-ONLY") for b in result["blockers"]))
        intake = json.loads((run_dir / "intake.json").read_text(encoding="utf-8"))
        self.assertEqual(intake["design_style"], "B")
        self.assertEqual(len([a for a in result["artifacts"] if a["path"].endswith(".png")]), 8 * 4)

    def test_every_file_it_makes_says_downsell_2(self):
        paths = self.stage_images()
        proc = self.run_second(paths, write_inputs(paths["workdir"], paths["brand"]))
        run_dir = Path(json.loads(proc.stdout)["images"]["run_dir"])
        env = dict(os.environ, SIGNATURE_ROLE_INSTANCE="downsell_2")  # what the wrapper sets for its run
        out = subprocess.run([sys.executable, str(tdw.SKILL71 / "scripts" / "combine_review_pdf.py"), str(run_dir),
                              "--stage", "desktop-wireframe"], capture_output=True, text=True, env=env)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue((run_dir / "review-pdfs" / "downsell-2_DESKTOP_WIREFRAMES.pdf").is_file())
        self.assertEqual([d["glob"] for d in ps.deliverables_for("downsell_2")
                          if d["id"] == "desktop_wireframe_pdf"],
                         ["review-pdfs/downsell-2_DESKTOP_WIREFRAMES.pdf"])

    def test_downsell_2_refuses_a_request_for_another_role(self):
        paths = self.stage_images()
        request = json.loads(paths["request-downsell_1.json"].read_text(encoding="utf-8"))
        request.update(page_role="landing", assigned_skill=71)
        paths["request-downsell_1.json"].write_text(json.dumps(request), encoding="utf-8")
        proc = self.run_second(paths, write_inputs(paths["workdir"], paths["brand"]))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("downsell_2 rides on", proc.stderr)

    def test_downsell_1_still_needs_its_contract_inputs(self):
        paths = self.stage_images()
        proc = subprocess.run([sys.executable, str(tdw.WRAPPER), "--request", str(paths["request-downsell_1.json"]),
                               "--result", str(paths["result"]), "--launch", str(paths["launch.json"]),
                               "--route-graph", str(paths["route-graph.json"]),
                               "--copy", str(paths["copy-downsell_1.json"])], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertIn("--journey", proc.stderr)


if __name__ == "__main__":
    unittest.main()
