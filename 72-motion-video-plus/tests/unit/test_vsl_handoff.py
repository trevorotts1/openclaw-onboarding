"""MG-037: desktop VSL handoff contract tests (fast layer).

Covers the handoff record's named failures (missing slot timing,
cue off the slot, insert longer or shorter than its slot, an
insert carrying its own narration into a parent-owned slot), the
insert package the producer stages from a handoff (validated
through the shipped contracts layer), the return package's hash
discipline, the Skill 47 bridge's ledger behavior, and the parent
program the producer compiles (placement, cue resolution, totals)
without rendering anything. The rendered acceptance build lives
in test_vsl_assembly.py.
"""

import copy
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

sys.path.insert(0, SCRIPTS)

spec = importlib.util.spec_from_file_location(
    "vsl_handoff", os.path.join(SCRIPTS, "vsl_handoff.py"))
producer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(producer)

spec = importlib.util.spec_from_file_location(
    "skill47_vsl_bridge", BRIDGE_PATH)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

HAVE_NODE = shutil.which("node") is not None


def load_handoff():
    with open(os.path.join(FIXTURES, "handoff-desktop.json")) as f:
        return json.load(f)


def assert_named(case, err, code, exit_code):
    case.assertEqual(getattr(err, "code", None), code)
    case.assertEqual(getattr(err, "exit_code", None), exit_code)


class HandoffValidationTests(unittest.TestCase):
    def trial(self, mutate):
        doc = load_handoff()
        mutate(doc)
        with self.assertRaises(producer.HandoffError) as cm:
            producer.validate_handoff(doc)
        return cm.exception

    def test_fixture_handoff_is_valid(self):
        producer.validate_handoff(load_handoff())

    def test_missing_slot_timing_fails_by_name(self):
        err = self.trial(lambda d: d["parent"].pop("slot"))
        assert_named(self, err, "VSL_HANDOFF_SLOT_TIMING_MISSING", 2)
        self.assertEqual(err.mg_category, "MG_TIMELINE_INVALID")

    def test_empty_slot_range_fails_by_name(self):
        err = self.trial(lambda d: d["parent"].update(
            slot={"start_frame": 900, "end_frame_exclusive": 900}))
        assert_named(self, err, "VSL_HANDOFF_SLOT_RANGE_INVALID", 2)

    def test_missing_cue_fails_by_name(self):
        err = self.trial(lambda d: d["parent"].pop("narration_cue"))
        assert_named(self, err, "VSL_HANDOFF_CUE_MISSING", 2)

    def test_cue_off_the_slot_start_fails_by_name(self):
        err = self.trial(
            lambda d: d["parent"]["narration_cue"].update(frame=915))
        assert_named(self, err, "VSL_HANDOFF_CUE_FRAME_MISMATCH", 2)

    def test_insert_longer_than_slot_fails_by_name(self):
        err = self.trial(lambda d: d["insert"].update(duration_frames=240))
        assert_named(self, err, "VSL_HANDOFF_INSERT_EXCEEDS_SLOT", 2)
        self.assertEqual(err.mg_category, "MG_TIMELINE_INVALID")

    def test_insert_shorter_than_slot_fails_by_name(self):
        err = self.trial(lambda d: d["insert"].update(duration_frames=120))
        assert_named(self, err, "VSL_HANDOFF_INSERT_UNDERFILLS_SLOT", 2)

    def test_insert_owned_narration_fails_by_name(self):
        err = self.trial(
            lambda d: d["audio_ownership"].update(narration="insert"))
        assert_named(self, err, "VSL_HANDOFF_AUDIO_OWNERSHIP_VIOLATION", 2)
        self.assertEqual(err.mg_category, "MG_MODE_MISMATCH")

    def test_insert_narration_assets_fail_by_name(self):
        err = self.trial(lambda d: d["insert"].update(
            narration_assets=[{"id": "n1", "path": "voice.wav"}]))
        assert_named(self, err, "VSL_HANDOFF_AUDIO_OWNERSHIP_VIOLATION", 2)

    def test_declared_insert_sound_fails_by_name(self):
        err = self.trial(
            lambda d: d["audio_ownership"].update(insert_sound="declared"))
        assert_named(self, err, "VSL_HANDOFF_AUDIO_OWNERSHIP_VIOLATION", 2)

    def test_shape_break_is_a_schema_failure(self):
        err = self.trial(lambda d: d.update(mode="vsl_mobile"))
        assert_named(self, err, "VSL_HANDOFF_SCHEMA_INVALID", 2)
        self.assertEqual(err.mg_category, "MG_SCHEMA_INVALID")


class StagingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mg037-stage-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.pkg = os.path.join(self.tmp, "insert-job")
        producer.stage_insert_package(load_handoff(), self.pkg)

    def read(self, *parts):
        with open(os.path.join(self.pkg, *parts)) as f:
            return json.load(f)

    def test_staged_package_passes_the_contracts_layer(self):
        findings = producer.motion_contracts.validate_job(self.pkg)
        self.assertEqual(findings, [])

    def test_manifest_carries_the_mode_and_the_parent(self):
        manifest = self.read("manifest.json")
        self.assertEqual(manifest["mode"], "vsl_desktop")
        self.assertEqual(manifest["job_id"], "fixture-vsl-desktop")
        self.assertEqual(manifest["parent"]["job_id"], "fixture-parent-vsl")
        self.assertEqual(manifest["parent"]["slot"],
                         {"start_frame": 900, "end_frame_exclusive": 1080})
        self.assertEqual(manifest["duration_frames"], 180)
        self.assertEqual(manifest["audio"]["mode"], "inherited")
        self.assertEqual(manifest["audio"]["parent_audio_ref"],
                         "fixture-parent-audio")
        self.assertFalse(manifest["audio"]["create_voiceover"])
        self.assertFalse(manifest["audio"]["create_music"])
        self.assertEqual(manifest["delivery"]["poster_frame"], 150)

    def test_canonical_parent_handoff_mapping(self):
        handoff = self.read("parent-handoff.json")
        self.assertEqual(handoff["parent_job_id"], "fixture-parent-vsl")
        self.assertEqual(handoff["slot"],
                         {"start_frame": 900, "end_frame_exclusive": 1080})
        self.assertEqual(handoff["narration_cue"]["id"], "fixture-cue")
        self.assertEqual(handoff["narration_cue"]["frame"], 900)
        self.assertEqual(handoff["audio_owner"], "parent")
        self.assertFalse(handoff["allow_speed_change"])
        self.assertFalse(handoff["allow_slot_resize"])

    def test_scene_assertions_are_derived_from_the_dataset(self):
        scene = self.read("scenes", "bar-01.json")
        by_id = {a["id"]: a for a in scene["semantic_motion_assertions"]}
        self.assertEqual(by_id["half-reveal"]["frame"], 45)
        self.assertEqual(by_id["half-reveal"]["expected_values"],
                         [240.0, 360.0, 600.0])
        self.assertEqual(by_id["final-ratios"]["frame"], 75)
        self.assertEqual(by_id["final-ratios"]["expected_values"],
                         [480.0, 720.0, 1200.0])


@unittest.skipUnless(HAVE_NODE, "node required for the timeline compiler")
class ParentPlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mg037-plan-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.handoff = load_handoff()
        self.return_dir = os.path.join(self.tmp, "return")
        os.makedirs(self.return_dir)
        mp4 = os.path.join(self.return_dir, "insert.mp4")
        with open(mp4, "wb") as f:
            f.write(b"fixture-bytes")
        self.return_doc = {
            "schema_version": "1.0",
            "handoff_id": self.handoff["handoff_id"],
            "insert_job_id": "fixture-vsl-desktop",
            "parent_job_id": "fixture-parent-vsl",
            "engine": "remotion", "component_id": "C05",
            "artifacts": {
                "mp4": {"path": "insert.mp4",
                        "sha256": producer.sha256_file(mp4), "bytes": 13},
                "source_package": {"path": self.tmp}},
            "timing": {
                "slot": {"start_frame": 900, "end_frame_exclusive": 1080},
                "cue_id": "fixture-cue", "cue_frame": 900,
                "insert_duration_frames": 180,
                "placed_start_frame": 900,
                "placed_end_frame_exclusive": 1080,
                "compiled_timeline_path": "compiled-timeline.json",
                "sidecar_path": "timeline-sidecar.json"},
            "approval": {"approval_id": "a1", "scope": "delivery",
                         "decision": "approved",
                         "authority_status": "not_verified",
                         "execution_context": "fixture"},
        }
        words = [{"index": i, "startSample": 1440000 + i * 48000,
                  "endSample": 1440000 + i * 48000 + 38400}
                 for i in range(6)]
        self.media_spec = {
            "canvas": {"width": 1920, "height": 1080},
            "synthetic_segments": True,
            "scenes": [
                {"id": "host-a", "path": "/x/host-a.mp4",
                 "duration_frames": 900, "engine": "fixture-host"},
                {"id": "bar-01", "use_return_artifact": True},
                {"id": "host-b", "path": "/x/host-b.mp4",
                 "duration_frames": 360, "engine": "fixture-host"}],
            "narration": [
                {"id": "narr-intro", "path": "/x/intro.wav",
                 "start_frame": 0, "end_frame_exclusive": 900},
                {"id": "narr-cue", "path": "/x/cue.wav",
                 "start_frame": 900, "end_frame_exclusive": 1080,
                 "words": words},
                {"id": "narr-outro", "path": "/x/outro.wav",
                 "start_frame": 1080, "end_frame_exclusive": 1440}],
            "captions": [
                {"id": "cap-cue", "start_frame": 900,
                 "end_frame_exclusive": 1080}],
            "music": {"path": "/x/music.wav"},
            "mix": {"musicVolume": 0.5, "ducking": None},
        }

    def test_parent_program_compiles_with_the_insert_at_its_cue(self):
        plan_path, media_path, compiled = producer.build_parent_plan(
            self.handoff, self.return_doc, self.return_dir,
            self.media_spec, os.path.join(self.tmp, "plan"))
        sidecar = compiled["sidecar"]
        self.assertEqual(sidecar["total_frames"], 1440)
        self.assertEqual(sidecar["total_samples"], 2304000)
        placed = {s["id"]: s["placedRange"] for s in sidecar["scenes"]}
        self.assertEqual(placed["host-a"],
                         {"startFrame": 0, "endFrameExclusive": 900})
        self.assertEqual(placed["bar-01"],
                         {"startFrame": 900, "endFrameExclusive": 1080})
        self.assertEqual(placed["host-b"],
                         {"startFrame": 1080, "endFrameExclusive": 1440})
        cues = {c["id"]: c for c in sidecar["cues"]}
        self.assertEqual(cues["fixture-cue"]["frame"], 900)
        self.assertEqual(cues["fixture-cue"]["anchorRef"], "narr-cue#0")
        self.assertEqual(cues["fixture-cue"]["anchorKind"], "spoken_word")
        with open(media_path) as f:
            media = json.load(f)
        insert_entry = [s for s in media["scenes"] if s["id"] == "bar-01"][0]
        self.assertTrue(insert_entry["path"].endswith("insert.mp4"))
        self.assertEqual(insert_entry["engine"], "remotion")

    def test_parent_audio_resolves_once_as_the_parents_own(self):
        _, media_path, _ = producer.build_parent_plan(
            self.handoff, self.return_doc, self.return_dir,
            self.media_spec, os.path.join(self.tmp, "plan"))
        with open(media_path) as f:
            media = json.load(f)
        plan = producer.audio_policy.resolve_audio_plan(
            "self", ["narr-intro", "narr-cue", "narr-outro"], [], media)
        self.assertEqual(plan["mode"], "own")
        self.assertEqual(plan["music"]["kind"], "supplied")
        self.assertEqual(plan["loudnessTarget"],
                         {"integratedLufs": -14.0, "truePeakDb": -1.0})


class ReturnPackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mg037-return-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.mp4 = os.path.join(self.tmp, "insert.mp4")
        with open(self.mp4, "wb") as f:
            f.write(b"returned-insert-bytes")
        self.doc = {
            "schema_version": "1.0", "handoff_id": "h1",
            "insert_job_id": "fixture-vsl-desktop",
            "parent_job_id": "fixture-parent-vsl",
            "engine": "remotion", "component_id": "C05",
            "artifacts": {
                "mp4": {"path": "insert.mp4",
                        "sha256": producer.sha256_file(self.mp4),
                        "bytes": os.path.getsize(self.mp4)},
                "source_package": {"path": self.tmp}},
            "timing": {
                "slot": {"start_frame": 900, "end_frame_exclusive": 1080},
                "cue_id": "fixture-cue", "cue_frame": 900,
                "insert_duration_frames": 180, "placed_start_frame": 900,
                "placed_end_frame_exclusive": 1080,
                "compiled_timeline_path": "compiled-timeline.json",
                "sidecar_path": "timeline-sidecar.json"},
            "approval": {"approval_id": "a1", "scope": "delivery",
                         "decision": "approved",
                         "authority_status": "not_verified",
                         "execution_context": "fixture"},
        }

    def test_valid_package_and_hashes_verify(self):
        producer.validate_return_package(self.doc)
        producer.verify_return_hashes(self.doc, self.tmp)

    def test_tampered_artifact_fails_by_name(self):
        with open(self.mp4, "ab") as f:
            f.write(b"x")
        with self.assertRaises(producer.HandoffError) as cm:
            producer.verify_return_hashes(self.doc, self.tmp)
        assert_named(self, cm.exception, "VSL_RETURN_HASH_MISMATCH", 9)
        self.assertEqual(cm.exception.mg_category, "MG_HASH_MISMATCH")

    def test_missing_artifact_fails_by_name(self):
        os.remove(self.mp4)
        with self.assertRaises(producer.HandoffError) as cm:
            producer.verify_return_hashes(self.doc, self.tmp)
        assert_named(self, cm.exception, "VSL_RETURN_ARTIFACT_MISSING", 3)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mg037-bridge-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.run_dir = os.path.join(self.tmp, "parent-run")
        os.makedirs(os.path.join(self.run_dir, "working"))
        self.manifest = {
            "job_id": "fixture-parent-vsl",
            "topic": "Fixture VSL",
            "target_duration_sec": 48,
            "aspect_ratio": "16:9",
            "budget_ceiling_usd": 0,
            "tone": "direct",
            "brief_complete": True,
            "status": "in_progress",
        }
        with open(os.path.join(self.run_dir, "working",
                               "job-manifest.json"), "w") as f:
            json.dump(self.manifest, f)
        self.handoff_path = os.path.join(FIXTURES, "handoff-desktop.json")

    def read_manifest(self):
        with open(os.path.join(self.run_dir, "working",
                               "job-manifest.json")) as f:
            return json.load(f)

    def test_request_files_the_handoff_and_opens_the_ledger_entry(self):
        receipt = bridge.request_insert(self.run_dir, self.handoff_path)
        self.assertEqual(receipt["status"], "requested")
        self.assertTrue(os.path.isfile(os.path.join(
            self.run_dir, "working", "checkpoints", "vsl-handoff.json")))
        self.assertTrue(os.path.isfile(os.path.join(
            self.run_dir, "working", "checkpoints",
            "vsl-request-receipt.json")))
        manifest = self.read_manifest()
        entries = manifest["motion_inserts"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["status"], "requested")
        self.assertEqual(entries[0]["insert_job_id"],
                         "fixture-vsl-desktop")
        # The parent's own manifest fields are untouched.
        for key, value in self.manifest.items():
            self.assertEqual(manifest[key], value)

    def test_request_for_another_parent_is_refused_by_name(self):
        doc = load_handoff()
        doc["parent"]["job_id"] = "someone-elses-vsl"
        path = os.path.join(self.tmp, "foreign-handoff.json")
        with open(path, "w") as f:
            json.dump(doc, f)
        with self.assertRaises(bridge.BridgeError) as cm:
            bridge.request_insert(self.run_dir, path)
        assert_named(self, cm.exception, "VSL_BRIDGE_PARENT_MISMATCH", 9)

    def test_request_without_any_identity_is_refused_by_name(self):
        manifest = dict(self.manifest)
        del manifest["job_id"]
        with open(os.path.join(self.run_dir, "working",
                               "job-manifest.json"), "w") as f:
            json.dump(manifest, f)
        with self.assertRaises(bridge.BridgeError) as cm:
            bridge.request_insert(self.run_dir, self.handoff_path)
        assert_named(self, cm.exception,
                     "VSL_BRIDGE_PARENT_IDENTITY_MISSING", 3)

    def test_consume_without_a_request_is_refused_by_name(self):
        with self.assertRaises(bridge.BridgeError) as cm:
            bridge.consume_return(self.run_dir, self.tmp)
        assert_named(self, cm.exception,
                     "VSL_BRIDGE_HANDOFF_NOT_REQUESTED", 3)

    def _fake_return(self):
        return_dir = os.path.join(self.tmp, "return")
        os.makedirs(return_dir)
        mp4 = os.path.join(return_dir, "insert.mp4")
        with open(mp4, "wb") as f:
            f.write(b"fake-insert")
        doc = {
            "schema_version": "1.0",
            "handoff_id": "handoff-vsl-desktop-fixture",
            "insert_job_id": "fixture-vsl-desktop",
            "parent_job_id": "fixture-parent-vsl",
            "engine": "remotion", "component_id": "C05",
            "artifacts": {
                "mp4": {"path": "insert.mp4",
                        "sha256": producer.sha256_file(mp4), "bytes": 11},
                "source_package": {"path": return_dir}},
            "timing": {
                "slot": {"start_frame": 900, "end_frame_exclusive": 1080},
                "cue_id": "fixture-cue", "cue_frame": 900,
                "insert_duration_frames": 180, "placed_start_frame": 900,
                "placed_end_frame_exclusive": 1080,
                "compiled_timeline_path": "compiled-timeline.json",
                "sidecar_path": "timeline-sidecar.json"},
            "approval": {"approval_id": "a1", "scope": "delivery",
                         "decision": "approved",
                         "authority_status": "not_verified",
                         "execution_context": "fixture"},
        }
        with open(os.path.join(return_dir, "return-package.json"), "w") as f:
            json.dump(doc, f)
        return return_dir

    def test_consume_records_the_return_in_the_ledger(self):
        bridge.request_insert(self.run_dir, self.handoff_path)
        return_dir = self._fake_return()
        receipt = bridge.consume_return(self.run_dir, return_dir)
        self.assertEqual(receipt["status"], "returned")
        manifest = self.read_manifest()
        entry = manifest["motion_inserts"][0]
        self.assertEqual(entry["status"], "returned")
        self.assertEqual(entry["artifacts"]["mp4"]["sha256"],
                         receipt["artifacts"]["mp4"]["sha256"])

    def test_consume_a_tampered_return_is_refused_by_name(self):
        bridge.request_insert(self.run_dir, self.handoff_path)
        return_dir = self._fake_return()
        with open(os.path.join(return_dir, "insert.mp4"), "ab") as f:
            f.write(b"tampered")
        with self.assertRaises(Exception) as cm:
            bridge.consume_return(self.run_dir, return_dir)
        assert_named(self, cm.exception, "VSL_RETURN_HASH_MISMATCH", 9)

    def test_assemble_without_a_consumed_return_is_refused_by_name(self):
        bridge.request_insert(self.run_dir, self.handoff_path)
        with self.assertRaises(bridge.BridgeError) as cm:
            bridge.assemble(self.run_dir, os.path.join(FIXTURES,
                                                       "handoff-desktop.json"))
        assert_named(self, cm.exception,
                     "VSL_BRIDGE_RETURN_NOT_CONSUMED", 3)


if __name__ == "__main__":
    unittest.main()
