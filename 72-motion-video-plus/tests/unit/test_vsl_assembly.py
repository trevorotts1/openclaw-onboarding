"""MG-037: desktop VSL handoff acceptance tests (rendered layer).

The full acceptance build, from the build's own fixtures:

1. The producer renders the insert through the shipped dispatcher
   (a real Remotion render of the shipped C05 component) and
   packages the return.
2. The parent fixture (host program, real narration segments with
   word timings, a music bed) is built by
   tests/fixtures/vsl/make_parent_media.py.
3. The Skill 47 bridge requests the insert, consumes the return,
   and assembles the parent VSL through the shipped assembler.

Acceptance (directive MG-037): the graphic lands at the intended
speech cue (the compiled cue resolves to parent frame 900 and the
insert's first frame is measured there, within one frame), with
no duplicate narration or music (the assembler's input registry
carries exactly the parent's three narration segments and one
music bed, the insert itself is video-only, and the parent's
narration measures present through the insert's span), no missing
final words (the parent's narration tail measures present at the
planned end of the assembled output), and no unauthorized
duration change (the assembled output decodes to exactly the
parent plan's 1440 frames). A return whose insert is shorter
than its slot is refused by the assembler by name, never trimmed
into place.

These tests need node, ffmpeg/ffprobe, a built runtime dist, and
the provisioned shared runtime; they skip cleanly without them
(the fast-gate environment builds and provisions first).
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
BRIDGE_PATH = os.path.join(
    REPO, "47-movie-producer", "scripts", "vsl_handoff.py")
DIST_ADAPTERS = os.path.join(
    SKILL, "runtime", "dist", "src", "adapters", "index.js")
RUNTIME_LOCK = os.path.join(
    REPO, "shared-utils", "motion-render-runtime", ".runtime",
    "runtime-lock.json")

sys.path.insert(0, SCRIPTS)

spec = importlib.util.spec_from_file_location(
    "vsl_handoff", os.path.join(SCRIPTS, "vsl_handoff.py"))
producer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(producer)

spec = importlib.util.spec_from_file_location(
    "skill47_vsl_bridge", BRIDGE_PATH)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

READY = (shutil.which("node") is not None
         and shutil.which("ffmpeg") is not None
         and shutil.which("ffprobe") is not None
         and os.path.isfile(DIST_ADAPTERS)
         and os.path.isfile(RUNTIME_LOCK))


@unittest.skipUnless(READY, "needs node, ffmpeg, built runtime dist, "
                            "and the provisioned shared runtime")
class VslAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="mg037-acceptance-")
        cls.handoff_path = os.path.join(FIXTURES, "handoff-desktop.json")
        # 1. Produce the insert (real render through the dispatcher).
        cls.produced = producer.produce(
            cls.handoff_path, os.path.join(cls.tmp, "produce"))
        cls.return_dir = cls.produced["return_dir"]
        cls.return_doc = cls.produced["return_package"]
        # 2. Build the parent fixture media.
        cls.media_dir = os.path.join(cls.tmp, "parent-media")
        subprocess.run(
            [sys.executable,
             os.path.join(FIXTURES, "make_parent_media.py"), cls.media_dir],
            check=True, capture_output=True, text=True)
        cls.media_spec = os.path.join(cls.media_dir, "media-spec.json")
        # 3. The parent Skill 47 run directory.
        cls.run_dir = os.path.join(cls.tmp, "parent-run")
        os.makedirs(os.path.join(cls.run_dir, "working"))
        manifest = {
            "job_id": "fixture-parent-vsl",
            "topic": "Fixture VSL",
            "target_duration_sec": 48,
            "aspect_ratio": "16:9",
            "budget_ceiling_usd": 0,
            "tone": "direct",
            "brief_complete": True,
            "status": "in_progress",
        }
        with open(os.path.join(cls.run_dir, "working",
                               "job-manifest.json"), "w") as f:
            json.dump(manifest, f)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def read_manifest(self):
        with open(os.path.join(self.run_dir, "working",
                               "job-manifest.json")) as f:
            return json.load(f)

    def test_return_package_facts(self):
        doc = self.return_doc
        producer.verify_return_hashes(doc, self.return_dir)
        self.assertEqual(doc["timing"]["placed_start_frame"], 900)
        self.assertEqual(doc["timing"]["placed_end_frame_exclusive"], 1080)
        self.assertEqual(doc["timing"]["cue_frame"], 900)
        self.assertEqual(doc["artifacts"]["poster"]["frame"], 150)
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-of", "json",
             os.path.join(self.return_dir, "insert.mp4")],
            capture_output=True, text=True)
        streams = [s["codec_type"]
                   for s in json.loads(probe.stdout)["streams"]]
        self.assertEqual(streams, ["video"],
                         "the insert contributes no audio of its own")

    def test_insert_motion_proof(self):
        """The returned insert passes the shipped MG-032 evaluator
        for its component, against an MG-031 coverage bundle bound
        to the artifact's own hash."""
        with open(os.path.join(
                SKILL, "tests", "fixtures", "motion-proof",
                "c05-bar-reveal.case.json")) as f:
            case = json.load(f)
        case["id"] = "c05-bar-reveal-vsl-desktop"
        case["job_id"] = "fixture-vsl-desktop"
        case_path = os.path.join(self.tmp, "insert-proof-case.json")
        with open(case_path, "w") as f:
            json.dump(case, f)
        # The bundle's targeted frames come from the compiled
        # timeline's events plus a caller-supplied beat grid; the
        # case's proof checkpoint (frame 45) is declared as a beat,
        # the same discipline the MG-032 suite's bundle build uses.
        beats_path = os.path.join(self.tmp, "insert-beats.json")
        with open(beats_path, "w") as f:
            json.dump({"beat_times": sorted(
                {cp["frame"] / 30.0 for cp in case["checkpoints"]})}, f)
        bundle_dir = os.path.join(self.tmp, "bundle-insert")
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "critique_bundle.py"),
             "build", "--video",
             os.path.join(self.return_dir, "insert.mp4"),
             "--outdir", bundle_dir, "--job-id", "fixture-vsl-desktop",
             "--timeline",
             os.path.join(self.return_dir, "compiled-timeline.json"),
             "--sidecar",
             os.path.join(self.return_dir, "timeline-sidecar.json"),
             "--beats", beats_path],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout[-600:])
        coverage = os.path.join(
            bundle_dir, "fixture-vsl-desktop__coverage.json")
        self.assertTrue(os.path.isfile(coverage))
        with open(coverage) as f:
            self.assertEqual(json.load(f)["verdict"], "complete")

        proc = subprocess.run(
            ["node", os.path.join(SCRIPTS, "vsl-proof.mjs"),
             "--case", case_path,
             "--video", os.path.join(self.return_dir, "insert.mp4"),
             "--coverage", coverage,
             "--job-dir", self.produced["job_dir"],
             "--out-dir", os.path.join(self.tmp, "proof-insert")],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr[-600:])
        record = json.loads(proc.stdout)["record"]
        self.assertEqual(record["verdict"], "pass")
        self.assertTrue(
            all(a["verdict"] == "pass" for a in record["assertions"]))

    def test_full_bridge_assembly_acceptance(self):
        receipt = bridge.request_insert(self.run_dir, self.handoff_path)
        self.assertEqual(receipt["status"], "requested")
        receipt = bridge.consume_return(self.run_dir, self.return_dir)
        self.assertEqual(receipt["status"], "returned")
        delivery = bridge.assemble(self.run_dir, self.media_spec)
        self.assertEqual(delivery["decoded_frames"], 1440)
        self.assertEqual(delivery["duration_seconds"], 48.0)

        with open(os.path.join(self.run_dir, "working", "checkpoints",
                               "vsl-assembly-report.json")) as f:
            report = json.load(f)
        self.assertEqual(report["verdict"], "pass")
        checks = report["checks"]
        # The cue: resolved by the compiler to the slot's first
        # frame, and the insert's first frame measured there.
        self.assertEqual(report["cue"]["first_frame_delta"], 0)
        self.assertEqual(report["cue"]["resolved_frame"], 900)
        self.assertEqual(checks["insert_first_frame"]["observed"]
                         ["bar_widths"], [0, 0, 0])
        # The motion plays in place: half reveal at parent frame
        # 945, final widths at parent frame 975.
        motion = checks["insert_motion_in_place"]["observed"]
        self.assertEqual(motion["mid_parent_frame"], 945)
        self.assertEqual(motion["final_parent_frame"], 975)
        for actual, expected in zip(motion["mid_widths"],
                                    [240, 360, 600]):
            self.assertLessEqual(abs(actual - expected), 3)
        self.assertEqual(motion["final_widths"], [480, 720, 1200])
        # No duplicate narration or music: exactly the parent's
        # three narration inputs and one bed entered the assembly;
        # the parent's voice measures present in every segment,
        # including the segment the insert answers.
        self.assertEqual(checks["audio_registry"]["observed"]
                         ["narration_inputs"], 3)
        self.assertEqual(checks["audio_registry"]["observed"]
                         ["music_inputs"], 1)
        presence = checks["narration_presence"]["observed"]
        self.assertTrue(all(seg["present"] for seg in presence.values()))
        self.assertTrue(presence["narr-cue"]["present"])
        # No missing final words, and the duration is the plan's.
        self.assertTrue(checks["final_words"]["observed"]
                        ["presentAtPlannedEnd"])
        self.assertEqual(checks["plan_totals"]["observed"]
                         ["decoded_frames"], 1440)
        self.assertEqual(checks["plan_totals"]["observed"]
                         ["plan_total_frames"], 1440)

        manifest = self.read_manifest()
        entry = manifest["motion_inserts"][0]
        self.assertEqual(entry["status"], "assembled")
        self.assertEqual(entry["delivery"]["sha256"],
                         report["assembled"]["sha256"])
        # The parent job kept its own identity and brief throughout.
        self.assertEqual(manifest["job_id"], "fixture-parent-vsl")
        self.assertEqual(manifest["status"], "in_progress")

    def test_short_insert_is_refused_by_the_assembler_by_name(self):
        """A return package whose insert is shorter than the plan
        (hashes honestly recomputed over the wrong file) is refused
        at assembly: the segment's actual duration governs, and
        nothing is trimmed or stretched to fit."""
        bad_dir = os.path.join(self.tmp, "return-short")
        shutil.copytree(self.return_dir, bad_dir)
        short = os.path.join(bad_dir, "insert.mp4")
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i",
             os.path.join(self.return_dir, "insert.mp4"),
             "-frames:v", "120", "-c:v", "libx264",
             "-pix_fmt", "yuv420p", short + ".tmp.mp4"],
            check=True, capture_output=True)
        os.replace(short + ".tmp.mp4", short)
        doc_path = os.path.join(bad_dir, "return-package.json")
        with open(doc_path) as f:
            doc = json.load(f)
        doc["artifacts"]["mp4"]["sha256"] = producer.sha256_file(short)
        doc["artifacts"]["mp4"]["bytes"] = os.path.getsize(short)
        with open(doc_path, "w") as f:
            json.dump(doc, f)
        out = os.path.join(self.tmp, "should-not-exist.mp4")
        with self.assertRaises(producer.HandoffError) as cm:
            producer.assemble_parent(
                self.handoff_path, bad_dir, self.media_spec, out,
                os.path.join(self.tmp, "assembly-short"))
        self.assertEqual(cm.exception.code,
                         "ASSEMBLE_MEDIA_SHORTER_THAN_PLAN")
        self.assertFalse(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()
