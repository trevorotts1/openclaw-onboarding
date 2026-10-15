"""MG-038: mobile VSL vertical derivative acceptance tests
(rendered layer).

The full acceptance build, from the build's own fixtures: the
producer stages the SAME parent facts the desktop handoff
carries (same parent job, same slot [900, 1080), same spoken-word
cue, same dataset and copy) as a vsl_mobile job whose scene uses
the design record's portrait layout, compiles its own timeline,
proves narration, text, and caption fit, renders through the
shipped dispatcher, measures the decoded artifact against the
portrait derivation (and against the scale and crop
counterfactuals), passes the shipped MG-032 motion proof for the
portrait case, and passes the shipped MG-034 technical QC gate
in the package lane under the vsl_mobile mode.

Acceptance (directive MG-038): 1080x1920 output; readable chart
labels (the text fit section measures every essential element
against its MG-013 floor); intact subjects and truthful data
(the decoded bar widths equal the portrait derivation from the
dataset, which is the landscape derivation's ratios on the
portrait plot); synchronization with the declared parent slot
(the narration fit section: the cue word resolves to frame 900,
the compiled insert totals exactly the 180-frame slot).

These tests need node, ffmpeg/ffprobe, a built runtime dist, and
the provisioned shared runtime; they skip cleanly without them.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SKILL = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPTS = os.path.join(SKILL, "scripts")
FIXTURES = os.path.join(SKILL, "tests", "fixtures", "vsl")
REPO = os.path.abspath(os.path.join(SKILL, ".."))
DIST_ADAPTERS = os.path.join(
    SKILL, "runtime", "dist", "src", "adapters", "index.js")
RUNTIME_LOCK = os.path.join(
    REPO, "shared-utils", "motion-render-runtime", ".runtime",
    "runtime-lock.json")

sys.path.insert(0, SCRIPTS)

spec = importlib.util.spec_from_file_location(
    "vsl_mobile", os.path.join(SCRIPTS, "vsl_mobile.py"))
mobile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mobile)

READY = (shutil.which("node") is not None
         and shutil.which("ffmpeg") is not None
         and shutil.which("ffprobe") is not None
         and os.path.isfile(DIST_ADAPTERS)
         and os.path.isfile(RUNTIME_LOCK))


@unittest.skipUnless(READY, "needs node, ffmpeg, built runtime dist, "
                            "and the provisioned shared runtime")
class MobileAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="mg038-acceptance-")
        cls.work = os.path.join(cls.tmp, "produce")
        cls.result = mobile.produce(
            os.path.join(FIXTURES, "handoff-mobile.json"), cls.work)
        cls.record = cls.result["delivery_record"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_delivery_record_names_its_desktop_parent(self):
        record = self.record
        self.assertEqual(record["mode"], "vsl_mobile")
        self.assertEqual(record["parent_job_id"], "fixture-parent-vsl")
        self.assertEqual(record["insert_job_id"], "fixture-vsl-mobile")
        self.assertEqual(record["derivative_of"], {
            "desktop_handoff_id": "handoff-vsl-desktop-fixture",
            "desktop_job_id": "fixture-vsl-desktop",
            "relationship": "vertical_derivative_recomposed"})
        self.assertEqual(record["approval"]["approval_id"],
                         "handoff-vsl-mobile-fixture-mobile-delivery")
        self.assertEqual(record["approval"]["authority_status"],
                         "not_verified")
        self.assertEqual(len(record["layout"]["layout_hash"]), 64)
        self.assertEqual(record["layout"]["variant"], "portrait")

    def test_artifact_is_a_true_vertical_full_length_insert(self):
        record = self.record
        self.assertEqual(record["canvas"],
                         {"width": 1080, "height": 1920, "fps": 30})
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-of", "json",
             os.path.join(self.result["delivery_dir"],
                          "insert-mobile.mp4")],
            capture_output=True, text=True)
        streams = json.loads(probe.stdout)["streams"]
        video = [s for s in streams if s["codec_type"] == "video"]
        self.assertEqual(len(video), 1)
        self.assertEqual((video[0]["width"], video[0]["height"]),
                         (1080, 1920))
        self.assertEqual([s["codec_type"] for s in streams], ["video"],
                         "the derivative contributes no audio of its own")
        sha = mobile.sha256_file(os.path.join(
            self.result["delivery_dir"], "insert-mobile.mp4"))
        self.assertEqual(sha, record["artifacts"]["mp4"]["sha256"])
        self.assertEqual(record["artifacts"]["poster"]["frame"], 150)

    def test_recomposition_numbers(self):
        measured = self.record["recomposition"]["measured"]
        self.assertEqual(measured["half_reveal_frame"], 45)
        for actual, expected in zip(measured["half_reveal_widths"],
                                    [148, 222, 370]):
            self.assertLessEqual(abs(actual - expected), 3)
        self.assertEqual(measured["final_frame"], 75)
        self.assertEqual(measured["final_widths"], [296, 444, 740])
        for actual, expected in zip(measured["row_centroids_y"],
                                    [570.0, 870.0, 1170.0]):
            self.assertLessEqual(abs(actual - expected), 4)
        counter = self.record["recomposition"]["counterfactuals"]
        self.assertEqual(counter["uniform_scale"]["predicted_widths"],
                         [270.0, 405.0, 675.0])
        self.assertGreater(
            counter["uniform_scale"]["min_abs_difference"], 10)
        self.assertEqual(
            counter["center_crop"]["predicted_row_centroids_y"],
            [720.0, 1004.44, 1288.89])
        self.assertGreater(
            counter["center_crop"]["min_abs_difference"], 10)
        self.assertFalse(
            counter["center_crop"]["bar_origins_inside_window"])
        self.assertEqual(self.record["recomposition"]["verdict"],
                         "pass")

    def test_fit_verdicts(self):
        self.assertEqual(self.record["fit"], {
            "narration_verdict": "pass", "text_verdict": "pass",
            "captions_verdict": "pass", "verdict": "pass"})
        self.assertEqual(self.record["cue"]["resolved_frame"], 900)
        fit = self.result["fit_report"]
        self.assertTrue(fit["narration"]["same_approved_narration"])
        self.assertEqual(fit["narration"]["compiled_total_frames"], 180)
        elements = {e["element"]: e
                    for e in fit["text"]["elements"]}
        self.assertEqual(elements["category_labels"]["authored_px"], 60)
        self.assertEqual(elements["category_labels"]["floor_px"], 54)

    def test_motion_proof_and_qc_verdicts(self):
        self.assertEqual(self.record["proof"]["motion_proof_verdict"],
                         "pass")
        self.assertEqual(self.record["proof"]["qc_verdict"], "pass")
        qc = self.result["qc_report"]
        self.assertEqual(qc["verdict"], "pass")
        self.assertEqual(qc["mode"], "package")
        by_id = {c["id"]: c for c in qc["checks"]}
        self.assertEqual(by_id["package.fonts"]["status"], "PASS")
        fonts = by_id["package.fonts"]["observed"]["fonts"]
        self.assertEqual(fonts[0]["family_alias"], "Liberation Sans")
        self.assertEqual(fonts[0]["status"], "resolved")
        self.assertEqual(
            self.record["font_declaration"]["intake_family_alias"],
            "fixture-sans")
        self.assertEqual(
            self.record["font_declaration"]["qc_facing_family_alias"],
            "Liberation Sans")
        proof = self.result["proof_record"]
        self.assertEqual(proof["verdict"], "pass")
        self.assertTrue(
            all(a["verdict"] == "pass" for a in proof["assertions"]))


if __name__ == "__main__":
    unittest.main()
