"""MG-038: mobile VSL vertical derivative contract tests (fast layer).

Covers the mobile handoff's named failures (missing slot timing,
cue off the slot, insert longer or shorter than its slot, an
insert carrying its own narration into a parent-owned slot, a
desktop canvas in a mobile handoff, a missing derivative
identity, a narration record that is absent, foreign, or missing
the cue's anchor word), the job package the producer stages from
a handoff (validated through the shipped contracts layer,
portrait assertions re-derived from the portrait plot), the fit
checks (narration cue resolution and coverage, text floors at
the vertical placement, caption floor, each failure named), the
delivery packager's refusal of a desktop master, and the mode's
own layout hash. The rendered acceptance build lives in
test_vsl_mobile_acceptance.py.
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

sys.path.insert(0, SCRIPTS)

spec = importlib.util.spec_from_file_location(
    "vsl_mobile", os.path.join(SCRIPTS, "vsl_mobile.py"))
mobile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mobile)

producer = mobile.vsl_handoff

HAVE_NODE = shutil.which("node") is not None
HAVE_FFMPEG = shutil.which("ffmpeg") is not None \
    and shutil.which("ffprobe") is not None


def load_handoff():
    with open(os.path.join(FIXTURES, "handoff-mobile.json")) as f:
        return json.load(f)


def assert_named(case, err, code, exit_code):
    case.assertEqual(getattr(err, "code", None), code)
    case.assertEqual(getattr(err, "exit_code", None), exit_code)


class HandoffValidationTests(unittest.TestCase):
    def trial(self, mutate):
        doc = load_handoff()
        mutate(doc)
        with self.assertRaises(producer.HandoffError) as cm:
            mobile.validate_mobile_handoff(doc)
        return cm.exception

    def test_fixture_handoff_is_valid(self):
        mobile.validate_mobile_handoff(load_handoff())

    def test_missing_slot_timing_fails_by_name(self):
        err = self.trial(lambda d: d["parent"].pop("slot"))
        assert_named(self, err, "VSL_MOBILE_SLOT_TIMING_MISSING", 2)
        self.assertEqual(err.mg_category, "MG_TIMELINE_INVALID")

    def test_empty_slot_range_fails_by_name(self):
        err = self.trial(lambda d: d["parent"].update(
            slot={"start_frame": 900, "end_frame_exclusive": 900}))
        assert_named(self, err, "VSL_MOBILE_SLOT_RANGE_INVALID", 2)

    def test_missing_cue_fails_by_name(self):
        err = self.trial(lambda d: d["parent"].pop("narration_cue"))
        assert_named(self, err, "VSL_MOBILE_CUE_MISSING", 2)

    def test_cue_off_the_slot_start_fails_by_name(self):
        err = self.trial(
            lambda d: d["parent"]["narration_cue"].update(frame=915))
        assert_named(self, err, "VSL_MOBILE_CUE_FRAME_MISMATCH", 2)

    def test_insert_longer_than_slot_fails_by_name(self):
        err = self.trial(lambda d: d["insert"].update(duration_frames=240))
        assert_named(self, err, "VSL_MOBILE_INSERT_EXCEEDS_SLOT", 2)

    def test_insert_shorter_than_slot_fails_by_name(self):
        err = self.trial(lambda d: d["insert"].update(duration_frames=120))
        assert_named(self, err, "VSL_MOBILE_INSERT_UNDERFILLS_SLOT", 2)

    def test_insert_owned_narration_fails_by_name(self):
        err = self.trial(
            lambda d: d["audio_ownership"].update(narration="insert"))
        assert_named(self, err, "VSL_MOBILE_AUDIO_OWNERSHIP_VIOLATION", 2)
        self.assertEqual(err.mg_category, "MG_MODE_MISMATCH")

    def test_insert_narration_assets_fail_by_name(self):
        err = self.trial(lambda d: d["insert"].update(
            narration_assets=[{"id": "n1", "path": "voice.wav"}]))
        assert_named(self, err, "VSL_MOBILE_AUDIO_OWNERSHIP_VIOLATION", 2)

    def test_declared_insert_sound_fails_by_name(self):
        err = self.trial(
            lambda d: d["audio_ownership"].update(insert_sound="declared"))
        assert_named(self, err, "VSL_MOBILE_AUDIO_OWNERSHIP_VIOLATION", 2)

    def test_desktop_canvas_in_a_mobile_handoff_fails_by_name(self):
        err = self.trial(lambda d: d["parent"].update(
            canvas={"width": 1920, "height": 1080, "fps": 30}))
        assert_named(self, err, "VSL_MOBILE_CANVAS_MISMATCH", 2)
        self.assertEqual(err.mg_category, "MG_MODE_MISMATCH")

    def test_missing_derivative_identity_fails_by_name(self):
        err = self.trial(lambda d: d.pop("derivative_of"))
        assert_named(self, err, "VSL_MOBILE_DERIVATIVE_MISSING", 3)
        self.assertEqual(err.mg_category, "MG_INPUT_MISSING")

    def test_missing_narration_record_fails_by_name(self):
        err = self.trial(lambda d: d.pop("narration"))
        assert_named(self, err, "VSL_MOBILE_NARRATION_MISSING", 3)

    def test_foreign_narration_asset_fails_by_name(self):
        err = self.trial(
            lambda d: d["narration"].update(asset_ref="someone-elses-audio"))
        assert_named(self, err, "VSL_MOBILE_NARRATION_MISMATCH", 2)

    def test_cue_anchor_word_absent_fails_by_name(self):
        def mutate(d):
            seg = next(s for s in d["narration"]["segments"]
                       if s["id"] == "narr-cue")
            seg["words"] = [w for w in seg["words"] if w["index"] != 0]
        err = self.trial(mutate)
        assert_named(self, err, "VSL_MOBILE_CUE_ANCHOR_UNRESOLVED", 2)

    def test_desktop_mode_in_a_mobile_handoff_is_a_schema_failure(self):
        err = self.trial(lambda d: d.update(mode="vsl_desktop"))
        assert_named(self, err, "VSL_MOBILE_SCHEMA_INVALID", 2)
        self.assertEqual(err.mg_category, "MG_SCHEMA_INVALID")


class StagingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mg038-stage-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.pkg = os.path.join(self.tmp, "insert-job")
        mobile.stage_mobile_package(load_handoff(), self.pkg)

    def read(self, *parts):
        with open(os.path.join(self.pkg, *parts)) as f:
            return json.load(f)

    def test_staged_package_passes_the_contracts_layer(self):
        findings = producer.motion_contracts.validate_job(self.pkg)
        self.assertEqual(findings, [])

    def test_manifest_carries_the_mobile_mode_and_canvas(self):
        manifest = self.read("manifest.json")
        self.assertEqual(manifest["mode"], "vsl_mobile")
        self.assertEqual(manifest["job_id"], "fixture-vsl-mobile")
        self.assertEqual(manifest["canvas"],
                         {"width": 1080, "height": 1920, "fps": 30})
        self.assertEqual(manifest["parent"]["job_id"],
                         "fixture-parent-vsl")
        self.assertEqual(manifest["parent"]["slot"],
                         {"start_frame": 900, "end_frame_exclusive": 1080})
        self.assertEqual(manifest["duration_frames"], 180)
        self.assertEqual(manifest["audio"]["mode"], "inherited")
        self.assertEqual(manifest["audio"]["parent_audio_ref"],
                         "fixture-parent-audio")
        self.assertFalse(manifest["audio"]["create_voiceover"])
        self.assertFalse(manifest["audio"]["create_music"])
        self.assertEqual(manifest["delivery"]["poster_frame"], 150)

    def test_scene_is_the_portrait_variant(self):
        scene = self.read("scenes", "bar-01.json")
        self.assertEqual(scene["layout_variant"], "portrait")
        self.assertEqual(scene["engine"], "remotion")

    def test_scene_assertions_are_the_portrait_derivation(self):
        scene = self.read("scenes", "bar-01.json")
        by_id = {a["id"]: a for a in scene["semantic_motion_assertions"]}
        self.assertEqual(by_id["half-reveal"]["frame"], 45)
        self.assertEqual(by_id["half-reveal"]["expected_values"],
                         [148.0, 222.0, 370.0])
        self.assertEqual(by_id["final-ratios"]["frame"], 75)
        self.assertEqual(by_id["final-ratios"]["expected_values"],
                         [296.0, 444.0, 740.0])

    def test_canonical_parent_handoff_carries_the_mobile_canvas(self):
        handoff = self.read("parent-handoff.json")
        self.assertEqual(handoff["canvas"],
                         {"width": 1080, "height": 1920, "fps": 30})
        self.assertEqual(handoff["slot"],
                         {"start_frame": 900, "end_frame_exclusive": 1080})
        self.assertEqual(handoff["audio_owner"], "parent")
        self.assertFalse(handoff["allow_speed_change"])
        self.assertFalse(handoff["allow_slot_resize"])

    def test_layout_hash_is_stable_and_portrait_specific(self):
        handoff = load_handoff()
        design = mobile._resolve_design(handoff)
        first = mobile.layout_hash(handoff, design)
        self.assertEqual(first, mobile.layout_hash(handoff, design))
        self.assertEqual(len(first), 64)
        # The same design's landscape layout hashes differently:
        # the mobile approval binds to the portrait layout only.
        land = copy.deepcopy(design)
        land["layouts"]["portrait"] = land["layouts"]["landscape"]
        self.assertNotEqual(first, mobile.layout_hash(handoff, land))


@unittest.skipUnless(HAVE_NODE, "node required for the timeline compiler")
class FitCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mg038-fit-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.handoff = load_handoff()
        pkg = os.path.join(self.tmp, "insert-job")
        mobile.stage_mobile_package(self.handoff, pkg)
        insert = self.handoff["insert"]
        slot = self.handoff["parent"]["slot"]
        motion = insert["motion"]
        doc = {
            "jobId": insert["job_id"], "fps": 30, "mode": "slot",
            "audioOwner": "parent",
            "parentSlot": {
                "range": {"startFrame": slot["start_frame"],
                          "endFrameExclusive":
                              slot["end_frame_exclusive"]},
                "grantedHandles": {"headFrames": 0, "tailFrames": 0}},
            "scenes": [{"id": insert["scene_id"],
                        "durationFrames": insert["duration_frames"]}],
            "cues": [
                {"id": "final-hold", "sceneId": insert["scene_id"],
                 "type": "hold_start",
                 "anchor": {"kind": "semantic_state",
                            "state": "final_hold",
                            "sceneLocalFrame":
                                motion["end_frame_exclusive"]}}],
        }
        self.compiled = producer.compile_timeline(
            doc, os.path.join(self.tmp, "compile"), "insert")
        self.design = mobile._resolve_design(self.handoff)

    def test_fit_report_passes_on_the_fixture(self):
        report = mobile.run_fit_checks(
            self.handoff, self.design, self.compiled["sidecar"])
        self.assertEqual(report["verdict"], "pass")
        narration = report["narration"]
        self.assertTrue(narration["same_approved_narration"])
        self.assertEqual(narration["asset_ref"], "fixture-parent-audio")
        self.assertEqual(narration["cue"]["resolved_frame"], 900)
        self.assertEqual(narration["cue"]["word_start_sample"], 1440000)
        self.assertTrue(narration["cue_segment_covers_slot"])
        self.assertEqual(narration["compiled_total_frames"], 180)
        self.assertEqual(narration["slot_length_frames"], 180)
        self.assertEqual(narration["parent_total_frames"], 1440)

    def test_text_elements_measure_at_or_above_their_floors(self):
        section = mobile.check_text_fit(self.handoff, self.design)
        by_element = {e["element"]: e for e in section["elements"]}
        self.assertEqual(by_element["headline"]["authored_px"], 112)
        self.assertEqual(by_element["headline"]["floor_px"], 96)
        self.assertEqual(by_element["category_labels"]["authored_px"], 60)
        self.assertEqual(by_element["category_labels"]["floor_px"], 54)
        self.assertEqual(by_element["values"]["authored_px"], 64)
        self.assertEqual(by_element["values"]["floor_px"], 60)
        self.assertEqual(by_element["disclosure"]["authored_px"], 48)
        self.assertEqual(by_element["disclosure"]["floor_px"], 40)
        for entry in section["elements"]:
            self.assertEqual(entry["effective_px"], entry["authored_px"])
            self.assertEqual(entry["verdict"], "pass")

    def test_caption_entries_pass_at_the_profile_size(self):
        section = mobile.check_caption_fit(self.handoff)
        self.assertEqual(section["profile"]["font_size_px"], 64)
        self.assertEqual(section["profile"]["placement"], "lower_third")
        self.assertEqual(len(section["entries"]), 3)
        for entry in section["entries"]:
            self.assertEqual(entry["floor_px"], 54)
            self.assertEqual(entry["effective_px"], 64)
            self.assertEqual(entry["verdict"], "pass")

    def test_caption_below_the_floor_fails_by_name(self):
        doc = load_handoff()
        doc["caption_profile"] = {"font_size_px": 40,
                                   "placement": "lower_third"}
        with self.assertRaises(producer.HandoffError) as cm:
            mobile.check_caption_fit(doc)
        assert_named(self, cm.exception,
                     "VSL_MOBILE_CAPTION_BELOW_FLOOR", 6)
        self.assertIn("cap-intro", cm.exception.message)

    def test_text_below_the_floor_fails_by_name(self):
        design = copy.deepcopy(self.design)
        design["layouts"]["portrait"]["label_px"] = 40
        with self.assertRaises(producer.HandoffError) as cm:
            mobile.check_text_fit(self.handoff, design)
        assert_named(self, cm.exception, "VSL_MOBILE_TEXT_BELOW_FLOOR", 6)
        self.assertIn("category_labels", cm.exception.message)

    def test_cue_word_off_the_slot_fails_the_narration_fit_by_name(self):
        doc = load_handoff()
        seg = next(s for s in doc["narration"]["segments"]
                   if s["id"] == "narr-cue")
        seg["words"][0]["startSample"] = 1441600
        seg["words"][0]["endSample"] = 1478400
        with self.assertRaises(producer.HandoffError) as cm:
            mobile.check_narration_fit(doc, self.compiled["sidecar"])
        assert_named(self, cm.exception,
                     "VSL_MOBILE_CUE_RESOLUTION_MISMATCH", 6)

    def test_cue_segment_not_covering_the_slot_fails_by_name(self):
        doc = load_handoff()
        seg = next(s for s in doc["narration"]["segments"]
                   if s["id"] == "narr-cue")
        seg["end_frame_exclusive"] = 1000
        with self.assertRaises(producer.HandoffError) as cm:
            mobile.check_narration_fit(doc, self.compiled["sidecar"])
        assert_named(self, cm.exception,
                     "VSL_MOBILE_NARRATION_DOES_NOT_COVER_SLOT", 6)


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg/ffprobe required")
class DeliveryGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mg038-gate-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.handoff = load_handoff()

    def make_clip(self, name, size, frames):
        path = os.path.join(self.tmp, name)
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
             "testsrc2=size=%s:rate=30" % size, "-frames:v", str(frames),
             "-an", "-c:v", "libx264", "-preset", "veryfast",
             "-pix_fmt", "yuv420p", path],
            check=True, capture_output=True)
        return path

    def test_a_desktop_master_is_refused_by_name_before_delivery(self):
        master = self.make_clip("desktop.mp4", "1920x1080", 180)
        with self.assertRaises(producer.HandoffError) as cm:
            mobile.assert_deliverable_artifact(self.handoff, master)
        assert_named(self, cm.exception, "VSL_MOBILE_ASPECT_MISMATCH", 2)
        self.assertEqual(cm.exception.mg_category, "MG_MODE_MISMATCH")

    def test_a_desktop_master_writes_no_delivery_record(self):
        master = self.make_clip("desktop.mp4", "1920x1080", 180)
        delivery_dir = os.path.join(self.tmp, "delivery")
        design = mobile._resolve_design(self.handoff)
        evidence = {
            "job_dir": self.tmp, "engine": "remotion",
            "approval": {"approval_id": "a1", "scope": "delivery",
                         "decision": "approved",
                         "authority_status": "not_verified",
                         "execution_context": "fixture"},
            "fit_report": {"narration": {"cue": {"resolved_frame": 900},
                                         "verdict": "pass"},
                           "text": {"verdict": "pass"},
                           "captions": {"verdict": "pass"},
                           "verdict": "pass"},
            "recomposition": {"verdict": "pass"},
            "proof_verdict": "pass", "qc_verdict": "pass",
            "qc_report_path": "qc.json",
            "font_declaration": {
                "intake_family_alias": "fixture-sans",
                "qc_facing_family_alias": "Liberation Sans",
                "resolution_source": "registry",
                "disclosure": "disclosed"},
        }
        with self.assertRaises(producer.HandoffError) as cm:
            mobile.write_delivery_record(
                self.handoff, design, master, None, delivery_dir,
                evidence)
        assert_named(self, cm.exception, "VSL_MOBILE_ASPECT_MISMATCH", 2)
        self.assertFalse(os.path.exists(
            os.path.join(delivery_dir, "delivery-record.json")))
        self.assertFalse(os.path.exists(
            os.path.join(delivery_dir, "insert-mobile.mp4")))

    def test_a_vertical_artifact_with_the_wrong_length_fails_by_name(self):
        clip = self.make_clip("short.mp4", "1080x1920", 120)
        with self.assertRaises(producer.HandoffError) as cm:
            mobile.assert_deliverable_artifact(self.handoff, clip)
        assert_named(self, cm.exception,
                     "VSL_MOBILE_ARTIFACT_DURATION_MISMATCH", 6)

    def test_a_true_vertical_artifact_passes_the_gate(self):
        clip = self.make_clip("vertical.mp4", "1080x1920", 180)
        probe = mobile.assert_deliverable_artifact(self.handoff, clip)
        self.assertEqual(probe, {"width": 1080, "height": 1920,
                                  "frame_count": 180})


class FontResolutionTests(unittest.TestCase):
    def test_the_fixture_alias_resolves_through_the_shipped_registry(self):
        self.assertEqual(mobile.resolve_family_alias("fixture-sans"),
                         "Liberation Sans")

    def test_an_unregistered_alias_fails_by_name(self):
        with self.assertRaises(producer.HandoffError) as cm:
            mobile.resolve_family_alias("no-such-alias")
        assert_named(self, cm.exception, "VSL_MOBILE_FONT_UNRESOLVED", 2)


if __name__ == "__main__":
    unittest.main()
