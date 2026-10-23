"""Synthetic file/receipt joins only: no network, decoding or paid media."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import lipsync_evidence as E
from storyboard_director import approval_package as AP


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def attach_evidence(timeline, root, run_id="synthetic-run"):
    """Enrich marked test segments; preserve existing media and line metadata.

    Caller marks desired clips first. This creates the normal persisted evidence
    using synthetic approvals, never modifies a real client run, and returns the
    same timeline. Synthetic bytes are only written for nonexistent source files.
    """
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    timeline.update(run_dir=str(root), run_id=run_id)
    if not timeline.get("song_path"):
        song = root / "synthetic-song.wav"
        song.write_bytes(b"synthetic-audio-evidence-not-a-real-wav")
        timeline["song_path"] = str(song)
    fps = timeline.setdefault("fps", 30)
    _write(root / "song-choices/pick.json", {"pick": 1, "label": "synthetic", "take": 1,
                                             "sha256": hashlib.sha256(Path(timeline["song_path"]).read_bytes()).hexdigest()})
    timeline.setdefault("lines", [])
    lines = {line["line_id"]: line for line in timeline["lines"]}
    cursor, shots, contracts, stills = 0, [], {}, {}
    for i, seg in enumerate(timeline["segments"]):
        frames = seg.get("frames", round(seg.get("dur", seg.get("snapped_dur", 0)) * fps))
        transition = seg.get("transition", "fade" if i else "none")
        overlap = seg.get("xfade_frames", round(timeline.get("transition_duration", 0.4) * fps)
                          if i and transition != "none" else 0)
        start, end = (cursor - overlap) / fps, (cursor - overlap + frames) / fps
        cursor += frames - overlap
        source = Path(seg["src"])
        source = (source if source.is_absolute() else root / source).resolve()
        source.parent.mkdir(parents=True, exist_ok=True)
        if not source.exists():
            source.write_bytes(("synthetic-clip-%d" % i).encode())
        if not (seg.get("lip_sync") or seg.get("lip_sync_line_ids")):
            continue
        sid = seg.setdefault("shot_id", "shot-%d" % i)
        lids = seg.setdefault("lip_sync_line_ids", ["line-%d" % i])
        first_line = lines.get(lids[0], {})
        faces = seg.get("faces_on_screen") or []
        speaker = seg.setdefault("speaker", first_line.get("speaker") or (faces[0] if faces else "lead"))
        seg.setdefault("faces_on_screen", [speaker])
        for lid in lids:
            if lid not in lines:
                ln = {"line_id": lid, "speaker": speaker, "start_s": start, "end_s": end}
                timeline["lines"].append(ln)
                lines[lid] = ln
        shot = {"shot_id": sid, "lip_sync": True, "lip_sync_line_ids": lids,
                "lyric_line_ids": lids, "speaker": speaker, "character_ids": [speaker],
                "song_start": start, "song_end": end}
        shots.append(shot)
        contracts[sid] = {"meaning": "synthetic fixture"}
        still = root / "storyboard" / (sid + ".png")
        still.parent.mkdir(parents=True, exist_ok=True)
        still.write_bytes(("synthetic-still-" + sid).encode())
        stills[sid] = str(still)
        revision = AP.shot_revision(shot, contracts[sid], str(still))
        binding = {key: shot[key] for key in ("shot_id", "lip_sync_line_ids", "speaker")}
        binding["storyboard_revision"] = revision
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        task = "task-" + sid
        receipt_path = root / "receipts" / (task + ".json")
        _write(receipt_path, {"tool": "kie_dispatch", "outcome": "ok", "run_id": run_id,
                             "evidence": {"generated": True, "task_id": task,
                                          "lipsync_model": "kling/ai-avatar-standard",
                                          "saved_paths": [str(source)],
                                          "saved_sha256": {str(source): digest},
                                          "lipsync_binding": binding}})
        seg["artifact"] = {"schema_version": "1.0.0", "artifact_id": "video-" + sid,
                           "run_id": run_id, "stage": "generation", "kind": "video",
                           "path": str(source), "sha256": digest,
                           "provenance": {"task_id": task, "receipt_path": str(receipt_path)}}
    sb = root / "storyboard"
    _write(sb / "shot-list.json", {"shots": shots})
    _write(sb / "contracts.json", contracts)
    _write(sb / "stills.json", stills)
    entries = AP.approval_entries(shots, contracts, stills)
    for entry in entries.values():
        entry["status"] = "approved"
    _write(sb / "approval.json", {"state": "approved", "shots": entries})
    for seg in timeline["segments"]:
        if not seg.get("artifact"):
            continue
        request = fixture_request(timeline, run_id=run_id, shot_id=seg["shot_id"])
        receipt_path = Path(seg["artifact"]["provenance"]["receipt_path"])
        receipt = json.loads(receipt_path.read_text())
        receipt["evidence"]["lipsync_inputs"] = E.inputs_for_request(str(root), request)
        _write(receipt_path, receipt)
    return timeline


def fixture_request(plan, run_id=None, shot_id=None):
    """Create a bound synthetic provider request; injected fake uploaders only."""
    from lip_sync.lip_gate import picture_gate as PG
    root = Path(plan["run_dir"]).resolve()
    run_id = run_id or plan["run_id"]
    _, rows = E._approved(str(root))
    row = rows[shot_id or next(iter(rows))]
    sid = row["shot_id"]
    image = Path(json.loads((root / "storyboard/stills.json").read_text())[sid])
    rdir = root / "picture-receipts"
    image_sha = hashlib.sha256(image.read_bytes()).hexdigest()
    if not (rdir / (image_sha + ".json")).exists():
        PG.write_receipt(str(image), image_sha, "PASS",
                         {"face_count": 1, "face_h_pct": 40, "roll_deg": 0,
                          "yaw_proxy": 0, "jaw_open": 0, "smile": 0,
                          "inner_gap_pct": 0, "sharp_face_256": 400}, [], [], [], str(rdir))
    image_url = PG.upload_measured(str(image), uploader=lambda p: "https://fixture.invalid/image/" + image_sha,
                                   receipt_dir=str(rdir))
    from audio_c3.lipsync_producer import produce, skill74_runner
    def fake_dispatch(**request):
        assert request["request"]["model"] == request["model"] == "ai-music-api/separate-vocals"
        assert request["request"]["input"]["audio_url"].startswith("https://")
        path = Path(request["save_dir"]) / "isolated.wav"
        path.write_bytes(("synthetic-isolated-" + sid).encode())
        return {"tool": "kie_dispatch", "outcome": "ok", "run_id": run_id,
                "evidence": {"generated": True, "task_id": "separation-" + sid,
                             "saved_paths": [str(path)],
                             "isolated_stem": {"path": str(path), "speaker_id": row["speaker"],
                                               "kind": "speech", "isolated": True}}}
    def cut_runner(argv, *args, **kwargs):
        Path(argv[-1]).write_bytes(("synthetic-own-speaker-" + sid).encode())
    separation_runner = skill74_runner(str(root), lambda p: "https://fixture.invalid/selected-song",
                                       {}, lambda result: result["evidence"]["isolated_stem"],
                                       dispatch_fn=fake_dispatch)
    stem = produce(str(root), run_id, sid, plan["song_path"], separation_runner,
                   measure_offset=lambda *args: {"offset_s": 0, "corr": 1}, cut_runner=cut_runner)
    uploaded = E.upload_stem(str(root), stem,
                             lambda p: "https://fixture.invalid/audio/" + hashlib.sha256(Path(p).read_bytes()).hexdigest(),
                             run_id)
    return {"run_id": run_id, "lipsync_binding": E._binding(row),
            "lipsync_image_path": str(image), "lipsync_receipt_dir": str(rdir),
            "lipsync_stems": [uploaded],
            "input": {"image_url": image_url, "audio_url": uploaded["url"]}}


def fixture(root):
    tl = {"fps": 30, "chosen_length_s": 60,
          "segments": [{"src": "clip%d.mp4" % i, "dur": 5,
                        "lip_sync": True, "transition": "none"} for i in range(3)]}
    attach_evidence(tl, root)
    for i, seg in enumerate(tl["segments"]):
        seg.update(frames=150, offset_frames=i * 150, xfade_frames=0,
                   snapped_dur=5, source_dur=5, stretch=1)
    tl["total_dur"] = 15
    return tl


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.plan = fixture(self.root)

    def check_bad(self, code):
        result = E.check_plan(self.plan, require_measured=True)
        self.assertFalse(result["pass"], result)
        self.assertEqual(code, result["reason_code"], result)

    def mutate_receipt(self, change):
        path = Path(self.plan["segments"][0]["artifact"]["provenance"]["receipt_path"])
        rec = json.loads(path.read_text())
        change(rec)
        _write(path, rec)

    def test_proven_join_and_runtime_difference(self):
        result = E.check_plan(self.plan, require_measured=True)
        self.assertTrue(result["pass"], result)
        self.assertEqual(15, result["evidence"]["measured_seconds"])
        self.assertEqual(-45, result["evidence"]["runtime_difference_s"])

    def test_missing_song_cannot_credit_silent_export(self):
        self.plan["song_path"] = None
        self.check_bad("LIPSYNC_EVIDENCE_MISSING")

    def test_empty_song_cannot_credit_silent_export(self):
        Path(self.plan["song_path"]).write_bytes(b"")
        self.check_bad("LIPSYNC_AUDIO_MISSING")

    def test_foreign_storyboard_symlink_refused(self):
        with tempfile.TemporaryDirectory() as foreign:
            current = self.root / "storyboard/shot-list.json"
            outside = Path(foreign) / "shot-list.json"
            outside.write_bytes(current.read_bytes())
            current.unlink()
            current.symlink_to(outside)
            self.check_bad("LIPSYNC_FOREIGN_ARTIFACT")

    def test_old_receipt_without_actual_inputs_refused(self):
        self.mutate_receipt(lambda r: r["evidence"].pop("lipsync_inputs"))
        self.check_bad("LIPSYNC_INPUTS_MISSING")

    def test_wrong_audio_url_refused(self):
        req = fixture_request(self.plan)
        req["input"]["audio_url"] = "https://fixture.invalid/unrelated.wav"
        with self.assertRaises(E.LipsyncEvidenceError) as exc:
            E.inputs_for_request(str(self.root), req)
        self.assertEqual("LIPSYNC_AUDIO_MISMATCH", exc.exception.code)

    def test_wrong_image_url_refused(self):
        req = fixture_request(self.plan)
        req["input"]["image_url"] = "https://fixture.invalid/unrelated.png"
        with self.assertRaises(E.LipsyncEvidenceError):
            E.inputs_for_request(str(self.root), req)

    def test_wrong_stem_line_ids_refused(self):
        req = fixture_request(self.plan)
        req["lipsync_stems"][0]["line_ids"] = ["other-line"]
        with self.assertRaises(E.LipsyncEvidenceError) as exc:
            E.inputs_for_request(str(self.root), req)
        self.assertEqual("LIPSYNC_STEM_MISMATCH", exc.exception.code)

    def test_wrong_stem_speaker_refused(self):
        req = fixture_request(self.plan)
        req["lipsync_stems"][0]["speaker_id"] = "different-person"
        with self.assertRaises(E.LipsyncEvidenceError):
            E.inputs_for_request(str(self.root), req)

    def test_unisolated_stem_refused(self):
        req = fixture_request(self.plan)
        req["lipsync_stems"][0]["isolated"] = False
        with self.assertRaises(E.LipsyncEvidenceError):
            E.inputs_for_request(str(self.root), req)

    def test_actual_image_must_match_approved_still(self):
        req = fixture_request(self.plan)
        foreign_picture = self.root / "unapproved.png"
        foreign_picture.write_bytes(b"unapproved-face")
        req["lipsync_image_path"] = str(foreign_picture)
        with self.assertRaises(E.LipsyncEvidenceError) as exc:
            E.inputs_for_request(str(self.root), req)
        self.assertEqual("LIPSYNC_IMAGE_MISMATCH", exc.exception.code)

    def test_changed_audio_bytes_invalidates_generation_proof(self):
        rec = json.loads(Path(self.plan["segments"][0]["artifact"]["provenance"]["receipt_path"]).read_text())
        req = rec["evidence"]["lipsync_inputs"]["request"]
        Path(req["lipsync_stems"][0]["path"]).write_bytes(b"different-audio")
        self.check_bad("LIPSYNC_LINEAGE_MISMATCH")

    def test_uploader_cannot_change_private_copy(self):
        req = fixture_request(self.plan)
        def bad_uploader(path):
            Path(path).write_bytes(b"changed-during-upload")
            return "https://fixture.invalid/changed.wav"
        with self.assertRaises(E.LipsyncEvidenceError) as exc:
            E.upload_stem(str(self.root), req["lipsync_stems"][0], bad_uploader, self.plan["run_id"])
        self.assertEqual("LIPSYNC_HASH_MISMATCH", exc.exception.code)

    def test_upload_uses_private_copy(self):
        req = fixture_request(self.plan)
        original = Path(req["lipsync_stems"][0]["path"])
        def uploader(path):
            self.assertNotEqual(original, Path(path))
            self.assertEqual(original.read_bytes(), Path(path).read_bytes())
            return "https://fixture.invalid/copied.wav"
        result = E.upload_stem(str(self.root), req["lipsync_stems"][0], uploader, self.plan["run_id"])
        self.assertTrue(Path(result["upload_receipt_path"]).is_file())

    def lineage_record(self):
        receipt_path = Path(self.plan["segments"][0]["artifact"]["provenance"]["receipt_path"])
        receipt = json.loads(receipt_path.read_text())
        stem = receipt["evidence"]["lipsync_inputs"]["request"]["lipsync_stems"][0]
        path = Path(stem["lineage_path"])
        return path, json.loads(path.read_text())

    def test_missing_producer_lineage_refused(self):
        path, _ = self.lineage_record()
        path.unlink()
        self.check_bad("LIPSYNC_FILE_MISSING")

    def test_selected_song_swap_refused(self):
        Path(self.plan["song_path"]).write_bytes(b"different-selected-song")
        self.check_bad("LIPSYNC_SELECTED_SONG_MISMATCH")

    def test_separated_stem_swap_refused(self):
        _, rec = self.lineage_record()
        Path(rec["separated_path"]).write_bytes(b"different-isolated-source")
        self.check_bad("LIPSYNC_LINEAGE_MISMATCH")

    def test_cut_window_shift_refused(self):
        path, rec = self.lineage_record()
        rec["cut"]["cut_start_stem"] += 1
        _write(path, rec)
        self.check_bad("LIPSYNC_LINEAGE_MISMATCH")

    def test_one_song_route_needs_no_human_pick(self):
        mix = self.root / "music/mix.mp3"
        mix.parent.mkdir(exist_ok=True)
        mix.write_bytes(Path(self.plan["song_path"]).read_bytes())
        self.plan["song_path"] = str(mix)
        (self.root / "song-choices/pick.json").unlink()
        request = fixture_request(self.plan)
        self.assertTrue(E.inputs_for_request(str(self.root), request)["lineage"])

    def test_all_markers_lost(self):
        for seg in self.plan["segments"]:
            seg.pop("lip_sync_line_ids")
            seg.pop("lip_sync")
        self.check_bad("LIPSYNC_UNUSED_REQUIREMENTS")

    def test_speaker_lost(self):
        self.plan["segments"][0].pop("speaker")
        self.check_bad("LIPSYNC_IDENTITY_MISMATCH")

    def test_lines_lost(self):
        self.plan.pop("lines")
        self.check_bad("LIPSYNC_EVIDENCE_MISSING")

    def test_generated_but_unused(self):
        self.plan["segments"].pop()
        self.check_bad("LIPSYNC_UNUSED_REQUIREMENTS")

    def test_legacy_approval_refused(self):
        _write(self.root / "storyboard/approval.json", {"state": "approved"})
        self.check_bad("LIPSYNC_APPROVAL_MISSING")

    def test_stale_storyboard_refused(self):
        path = self.root / "storyboard/shot-list.json"
        value = json.loads(path.read_text())
        value["shots"][0]["speaker"] = "someone-else"
        _write(path, value)
        self.check_bad("LIPSYNC_APPROVAL_STALE")

    def test_deleted_approved_shot_cannot_shrink_requirements(self):
        path = self.root / "storyboard/shot-list.json"
        value = json.loads(path.read_text())
        value["shots"].pop()
        _write(path, value)
        self.plan["segments"].pop()
        self.check_bad("LIPSYNC_APPROVAL_STALE")

    def test_stale_still_refused(self):
        (self.root / "storyboard/shot-0.png").write_bytes(b"changed")
        self.check_bad("LIPSYNC_APPROVAL_STALE")

    def test_foreign_run_receipt_refused(self):
        self.mutate_receipt(lambda r: r.update(run_id="foreign"))
        self.check_bad("LIPSYNC_TASK_MISMATCH")

    def test_failed_task_refused(self):
        self.mutate_receipt(lambda r: r.update(outcome="error"))
        self.check_bad("LIPSYNC_TASK_MISMATCH")

    def test_saved_hash_path_alias_resolves_to_same_file(self):
        (self.root / "alias").symlink_to(self.root, target_is_directory=True)
        def alias_hash(rec):
            hashes = rec["evidence"]["saved_sha256"]
            digest = next(iter(hashes.values()))
            rec["evidence"]["saved_sha256"] = {str(self.root / "alias/clip0.mp4"): digest}
        self.mutate_receipt(alias_hash)
        result = E.check_plan(self.plan, require_measured=True)
        self.assertTrue(result["pass"], result)

    def test_changed_source_even_rehashed_inline(self):
        seg = self.plan["segments"][0]
        path = Path(seg["artifact"]["path"])
        path.write_bytes(b"changed")
        seg["artifact"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.check_bad("LIPSYNC_HASH_MISMATCH")

    def test_native_video_receipt_cannot_count(self):
        self.mutate_receipt(lambda r: r["evidence"].update(lipsync_model="minimax-hailuo-02"))
        self.check_bad("LIPSYNC_MODEL_MISMATCH")

    def test_other_tool_receipt_cannot_count(self):
        self.mutate_receipt(lambda r: r.update(tool="native_video"))
        self.check_bad("LIPSYNC_TASK_MISMATCH")

    def test_crossfade_uses_actual_start_and_excludes_opaque_overlap(self):
        tl = {"fps": 30, "transition_duration": 0.4,
              "segments": [{"src": "fade%d.mp4" % i, "dur": 5,
                            "lip_sync": True} for i in range(3)]}
        attach_evidence(tl, self.root)
        cursor = 0
        for i, seg in enumerate(tl["segments"]):
            fade = 12 if i else 0
            seg.update(frames=150, offset_frames=cursor, xfade_frames=fade,
                       source_dur=5, stretch=1)
            cursor += 150 - fade
        tl["total_dur"] = cursor / 30
        result = E.check_plan(tl, require_measured=True)
        self.assertTrue(result["pass"], result)
        self.assertAlmostEqual(13.4, result["evidence"]["measured_seconds"])

    def test_binding_required(self):
        self.mutate_receipt(lambda r: r["evidence"].pop("lipsync_binding"))
        self.check_bad("LIPSYNC_BINDING_MISMATCH")

    def test_moved_window_refused(self):
        self.plan["segments"][0]["offset_frames"] += 60
        self.check_bad("LIPSYNC_TIMELINE_MISMATCH")

    def test_hold_and_short_source_refused(self):
        self.plan["segments"][0]["hold"] = True
        self.check_bad("LIPSYNC_TIMELINE_MISMATCH")
        self.plan["segments"][0]["hold"] = False
        self.plan["segments"][0]["source_dur"] = 2
        self.check_bad("LIPSYNC_SOURCE_SHORT")

    def test_dry_run_reports_unmeasured_source(self):
        for seg in self.plan["segments"]:
            seg["source_dur"] = None
        result = E.check_plan(self.plan)
        self.assertTrue(result["pass"], result)
        self.assertFalse(result["evidence"]["source_duration_verified"])
        self.check_bad("LIPSYNC_SOURCE_SHORT")

    def test_binding_request_verifies_own_speaker(self):
        request = {"shot_id": "shot-0", "speaker": "lead", "lip_sync_line_ids": ["line-0"]}
        binding = E.binding_for_request(str(self.root), request)
        self.assertEqual("shot-0", binding["shot_id"])
        request["speaker"] = "narrator"
        with self.assertRaises(E.LipsyncEvidenceError):
            E.binding_for_request(str(self.root), request)

    def test_duplicate_shot_refused(self):
        self.plan["segments"].append(copy.deepcopy(self.plan["segments"][0]))
        self.check_bad("LIPSYNC_IDENTITY_MISMATCH")

    def test_foreign_file_path_refused(self):
        with tempfile.TemporaryDirectory() as foreign:
            path = Path(foreign) / "other.mp4"
            path.write_bytes(b"foreign")
            self.plan["segments"][0]["artifact"]["path"] = str(path)
            self.check_bad("LIPSYNC_FOREIGN_ARTIFACT")

    def test_missing_materialized_file_refused(self):
        Path(self.plan["segments"][0]["artifact"]["path"]).unlink()
        self.check_bad("LIPSYNC_FILE_MISSING")

    def test_wrong_task_id_refused(self):
        self.mutate_receipt(lambda r: r["evidence"].update(task_id="other-task"))
        self.check_bad("LIPSYNC_TASK_MISMATCH")

    def test_stale_request_revision_refused(self):
        request = {"shot_id": "shot-0", "speaker": "lead", "lip_sync_line_ids": ["line-0"],
                   "storyboard_revision": "old"}
        with self.assertRaises(E.LipsyncEvidenceError) as exc:
            E.binding_for_request(str(self.root), request)
        self.assertEqual("LIPSYNC_APPROVAL_STALE", exc.exception.code)

    def test_malformed_plan_fails_closed(self):
        self.plan["segments"][1]["xfade_frames"] = -30
        self.check_bad("LIPSYNC_TIMING_MISSING")

    def test_no_requirements_refused(self):
        _write(self.root / "storyboard/shot-list.json", {"shots": []})
        self.check_bad("LIPSYNC_EVIDENCE_MISSING")


if __name__ == "__main__":
    unittest.main()
