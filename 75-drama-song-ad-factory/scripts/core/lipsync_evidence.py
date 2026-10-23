"""Policy-independent joins from approved storyboard to materialized lip-sync.

No quota, paid call, or approval is created here. These checks prove identity,
file provenance and timeline use, not that pixels show a correctly moving mouth.
The existing lip-gate measurement and kept-take decisions remain necessary.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from storyboard_director import approval_package as AP
from kie_dispatch.model_lock import is_locked_lipsync
from lip_sync.narrator_rule import person_on_screen


class LipsyncEvidenceError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _need(ok, code, message):
    if not ok:
        raise LipsyncEvidenceError(code, message)


def _num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for part in iter(lambda: f.read(65536), b""):
            h.update(part)
    return h.hexdigest()


def _path(root, value):
    _need(isinstance(value, str) and value.strip(), "LIPSYNC_EVIDENCE_MISSING", "file path required")
    path = Path(value)
    path = (path if path.is_absolute() else root / path).resolve()
    _need(path.is_relative_to(root), "LIPSYNC_FOREIGN_ARTIFACT", "file must belong to this run")
    _need(path.is_file(), "LIPSYNC_FILE_MISSING", str(path))
    return path


def _ids(value):
    return (isinstance(value, list) and bool(value)
            and all(isinstance(x, str) and x.strip() for x in value)
            and len(value) == len(set(value)))


def _approved(run_dir):
    _need(isinstance(run_dir, (str, Path)) and str(run_dir),
          "LIPSYNC_EVIDENCE_MISSING", "run_dir required")
    root = Path(run_dir).resolve()
    sb = root / "storyboard"
    raw = _read(_path(root, str(sb / "shot-list.json")))
    shots = raw.get("shots") if isinstance(raw, dict) else raw
    contracts, stills, approval = [_read(_path(root, str(sb / name))) for name in
                                  ("contracts.json", "stills.json", "approval.json")]
    _need(isinstance(shots, list) and bool(shots) and isinstance(contracts, dict)
          and isinstance(stills, dict) and isinstance(approval, dict),
          "LIPSYNC_EVIDENCE_MISSING", "storyboard inputs missing or malformed")
    per_shot = approval.get("shots")
    _need(approval.get("state") == "approved" and isinstance(per_shot, dict) and bool(per_shot),
          "LIPSYNC_APPROVAL_MISSING", "current per-shot storyboard approval required")
    required, seen = {}, set()
    for shot in shots:
        _need(isinstance(shot, dict), "LIPSYNC_EVIDENCE_MISSING", "malformed shot")
        sid = shot.get("shot_id")
        _need(isinstance(sid, str) and sid.strip() and sid not in seen,
              "LIPSYNC_IDENTITY_MISMATCH", "missing or duplicate shot_id")
        seen.add(sid)
        _need(isinstance(contracts.get(sid), dict), "LIPSYNC_EVIDENCE_MISSING", "shot contract missing")
        still = _path(root, stills.get(sid))
        revision = AP.shot_revision(shot, contracts[sid], str(still))
        rec = per_shot.get(sid)
        _need(isinstance(rec, dict) and rec.get("status") == "approved"
              and rec.get("revision") == revision and rec.get("still_sha256") == _sha(still),
              "LIPSYNC_APPROVAL_STALE", "storyboard approval missing/stale for " + sid)
        if not (shot.get("lip_sync") or shot.get("lip_sync_line_ids")):
            continue
        lids, speaker = shot.get("lip_sync_line_ids"), shot.get("speaker")
        _need(_ids(lids) and _ids(shot.get("lyric_line_ids"))
              and set(lids) <= set(shot["lyric_line_ids"])
              and isinstance(speaker, str) and person_on_screen(speaker)
              and isinstance(shot.get("character_ids"), list) and speaker in shot["character_ids"],
              "LIPSYNC_IDENTITY_MISMATCH", "approved lip-sync needs its own line and character: " + sid)
        start, end = shot.get("song_start"), shot.get("song_end")
        _need(_num(start) and _num(end) and 0 <= start < end,
              "LIPSYNC_TIMING_MISSING", "approved shot window required")
        required[sid] = {"shot_id": sid, "lip_sync_line_ids": lids, "speaker": speaker,
                         "storyboard_revision": revision, "start_s": start, "end_s": end}
    _need(seen == set(per_shot), "LIPSYNC_APPROVAL_STALE",
          "current shot IDs differ from the approved storyboard")
    _need(bool(required), "LIPSYNC_REQUIREMENTS_MISSING", "approved storyboard has no lip-sync requirements")
    all_lids = [lid for r in required.values() for lid in r["lip_sync_line_ids"]]
    _need(len(all_lids) == len(set(all_lids)), "LIPSYNC_IDENTITY_MISMATCH", "a lip-sync line occurs in multiple approved shots")
    return root, required


def _binding(row):
    return {key: row[key] for key in ("shot_id", "lip_sync_line_ids", "speaker", "storyboard_revision")}


def binding_for_request(run_dir, request):
    """Verify a dispatch request against the current approval; never approve it."""
    try:
        _, required = _approved(run_dir)
        _need(isinstance(request, dict), "LIPSYNC_IDENTITY_MISMATCH", "request object required")
        row = required.get(request.get("shot_id"))
        _need(row is not None, "LIPSYNC_IDENTITY_MISMATCH", "request shot not approved for lip-sync")
        _need(request.get("speaker") == row["speaker"]
              and request.get("lip_sync_line_ids") == row["lip_sync_line_ids"],
              "LIPSYNC_IDENTITY_MISMATCH", "requested speaker/lines differ from approved shot")
        _need(request.get("storyboard_revision", row["storyboard_revision"]) == row["storyboard_revision"],
              "LIPSYNC_APPROVAL_STALE", "request carries a stale storyboard revision")
        return _binding(row)
    except LipsyncEvidenceError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise LipsyncEvidenceError("LIPSYNC_EVIDENCE_MISSING", str(exc)) from exc



def _stem_metadata(root, stem):
    _need(isinstance(stem, dict), "LIPSYNC_STEM_MISSING", "isolated stem metadata required")
    keys = ("speaker_id", "kind", "isolated", "line_ids", "start_s", "end_s", "lineage_path")
    meta = {key: stem.get(key) for key in keys}
    _need(_ids(meta["line_ids"]) and _num(meta["start_s"]) and _num(meta["end_s"])
          and 0 <= meta["start_s"] < meta["end_s"],
          "LIPSYNC_STEM_MISSING", "producer must record stem line IDs and timeline window")
    path = _path(root, stem.get("path"))
    _need(path.stat().st_size > 0, "LIPSYNC_STEM_MISSING", "empty isolated stem")
    return dict(meta, path=str(path), sha256=_sha(path))


def upload_stem(run_dir, stem, uploader, run_id):
    """Upload an immutable local copy using an explicitly injected transport.

    Audio prep must supply speaker/isolation/line/window metadata; this helper
    persists those producer assertions and exact uploaded bytes. It does not
    infer the speaker or transcript from audio, or grant approval/spend authority.
    There is intentionally no default network transport.
    """
    import shutil
    import tempfile
    from lip_sync.narrator_rule import check_stems
    root = Path(run_dir).resolve()
    _need(callable(uploader) and isinstance(run_id, str) and run_id.strip(),
          "LIPSYNC_STEM_MISSING", "injected uploader and run_id required")
    meta = _stem_metadata(root, stem)
    ok, code, errors = check_stems([meta], meta["speaker_id"])
    _need(ok and person_on_screen(meta["speaker_id"]), code, str(errors))
    with tempfile.TemporaryDirectory(prefix="lipsync-upload-", dir=root) as temp:
        uploaded = Path(temp) / Path(meta["path"]).name
        shutil.copyfile(meta["path"], uploaded)
        _need(_sha(uploaded) == meta["sha256"], "LIPSYNC_HASH_MISMATCH", "stem changed before upload")
        url = uploader(str(uploaded))
        _need(_sha(uploaded) == meta["sha256"], "LIPSYNC_HASH_MISMATCH", "uploader changed stem bytes")
    _need(isinstance(url, str) and url.startswith("https://"), "LIPSYNC_UPLOAD_MISSING", "upload must return HTTPS URL")
    rec = {"run_id": run_id, "stem": meta, "url": url}
    digest = hashlib.sha256(json.dumps(rec, sort_keys=True).encode()).hexdigest()
    directory = (root / "control" / "lipsync-uploads").resolve()
    _need(directory.is_relative_to(root), "LIPSYNC_FOREIGN_ARTIFACT", "upload receipt directory leaves run")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (digest + ".json")
    if path.exists():
        _need(_read(_path(root, str(path))) == rec, "LIPSYNC_HASH_MISMATCH", "upload receipt collision")
    else:
        with path.open("x", encoding="utf-8") as f:
            json.dump(rec, f, sort_keys=True)
    return dict(meta, url=url, upload_receipt_path=str(path.resolve()))


def inputs_for_request(run_dir, request):
    """Bind actual provider URLs to approved still and isolated own-line bytes."""
    from lip_sync.narrator_rule import check_stems
    from lip_sync.lip_gate import picture_gate as PG
    try:
        root, required = _approved(run_dir)
        binding = binding_for_request(run_dir, request.get("lipsync_binding"))
        row = required[binding["shot_id"]]
        run_id = request.get("run_id")
        _need(isinstance(run_id, str) and run_id.strip(), "LIPSYNC_EVIDENCE_MISSING", "run_id required")
        inp = request.get("input") or {}
        image = _path(root, request.get("lipsync_image_path"))
        image_hash = _sha(image)
        approved_stills = _read(_path(root, str(root / "storyboard/stills.json")))
        _need(image_hash == _sha(_path(root, approved_stills[row["shot_id"]])),
              "LIPSYNC_IMAGE_MISMATCH", "provider picture is not the approved storyboard still")
        rdir = request.get("lipsync_receipt_dir") or PG.default_receipt_dir(str(image))
        rdir = Path(rdir)
        rdir = (rdir if rdir.is_absolute() else root / rdir).resolve()
        gate_path = _path(root, str(rdir / (image_hash + ".json")))
        upload_path = _path(root, str(rdir / (image_hash + ".upload.json")))
        PG.require_receipt(str(image), str(rdir))
        PG.require_upload_bound(str(image), inp.get("image_url"), str(rdir))
        stems = request.get("lipsync_stems")
        ok, code, errors = check_stems(stems, row["speaker"])
        _need(ok, code, str(errors))
        meta = _stem_metadata(root, stems[0])
        _need(meta["line_ids"] == row["lip_sync_line_ids"]
              and meta["start_s"] == row["start_s"] and meta["end_s"] == row["end_s"],
              "LIPSYNC_STEM_MISMATCH", "stem does not contain the approved shot's selected line window")
        from audio_c3.lipsync_producer import verify as verify_lineage
        lineage = verify_lineage(str(root), run_id, row, meta)
        stem_receipt = _path(root, stems[0].get("upload_receipt_path"))
        recorded = _read(stem_receipt)
        _need(recorded == {"run_id": run_id, "stem": meta, "url": inp.get("audio_url")}
              and isinstance(inp.get("audio_url"), str) and inp["audio_url"].startswith("https://"),
              "LIPSYNC_AUDIO_MISMATCH", "actual audio URL is not the recorded upload of this own-line stem")
        normalized = {"run_id": run_id, "lipsync_binding": binding,
                      "lipsync_image_path": str(image), "lipsync_receipt_dir": str(rdir),
                      "lipsync_stems": [dict(meta, upload_receipt_path=str(stem_receipt))],
                      "input": {"image_url": inp.get("image_url"), "audio_url": inp.get("audio_url")}}
        return {"request": normalized, "image_sha256": image_hash, "audio_sha256": meta["sha256"],
                "image_gate_sha256": _sha(gate_path), "image_upload_sha256": _sha(upload_path),
                "audio_upload_sha256": _sha(stem_receipt), "lineage": lineage}
    except LipsyncEvidenceError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError, PG.LipsyncPictureNotGated) as exc:
        raise LipsyncEvidenceError(getattr(exc, "code", "LIPSYNC_INPUTS_MISSING"), str(exc)) from exc


def check_plan(plan, require_measured=False):
    """Join approved requirements, successful receipts, files and actual slots.

    Frame rounding may differ by one frame. Crossfade opacity time is excluded
    from measured coverage. In production, source_dur must be a measured probe.
    Dry-run callers may omit it, explicitly reporting source duration unverified.
    """
    evidence = {"included": [], "requirements": [], "measured_seconds": 0.0,
                "source_duration_verified": bool(require_measured)}
    try:
        _need(isinstance(plan, dict), "LIPSYNC_EVIDENCE_MISSING", "plan object required")
        root, required = _approved(plan.get("run_dir"))
        evidence["requirements"] = list(required.values())
        if require_measured or plan.get("song_path"):
            song = _path(root, plan.get("song_path"))
            _need(song.stat().st_size > 0, "LIPSYNC_AUDIO_MISSING", "final export needs the soundtrack")
            evidence["song_sha256"] = _sha(song)
        fps, delivered = plan.get("fps"), plan.get("total_dur")
        _need(_num(fps) and fps > 0 and _num(delivered) and delivered > 0,
              "LIPSYNC_TIMING_MISSING", "fps and delivered runtime required")
        chosen = plan.get("chosen_length_s")
        _need(chosen is None or (_num(chosen) and chosen > 0), "LIPSYNC_TIMING_MISSING", "invalid chosen runtime")
        evidence.update(chosen_runtime_s=chosen, delivered_runtime_s=delivered,
                        runtime_difference_s=None if chosen is None else delivered - chosen)
        run_id = plan.get("run_id")
        _need(isinstance(run_id, str) and run_id.strip(), "LIPSYNC_EVIDENCE_MISSING", "run_id required")
        lines = plan.get("lines")
        _need(isinstance(lines, list) and bool(lines), "LIPSYNC_EVIDENCE_MISSING", "line metadata required")
        line_map = {}
        for line in lines:
            _need(isinstance(line, dict) and isinstance(line.get("line_id"), str)
                  and line["line_id"] not in line_map, "LIPSYNC_IDENTITY_MISMATCH", "line identities missing/duplicated")
            line_map[line["line_id"]] = line
        segments = plan.get("segments")
        _need(isinstance(segments, list) and bool(segments), "LIPSYNC_EVIDENCE_MISSING", "segments required")
        seen, windows, hashes, tasks = set(), [], set(), set()
        for i, seg in enumerate(segments):
            _need(isinstance(seg, dict), "LIPSYNC_EVIDENCE_MISSING", "malformed segment")
            if not (seg.get("lip_sync") or seg.get("lip_sync_line_ids")):
                continue
            sid = seg.get("shot_id")
            row = required.get(sid)
            _need(row is not None and sid not in seen, "LIPSYNC_IDENTITY_MISMATCH", "unused/unapproved or duplicate lip-sync segment")
            seen.add(sid)
            _need(seg.get("speaker") == row["speaker"] and seg.get("lip_sync_line_ids") == row["lip_sync_line_ids"]
                  and isinstance(seg.get("faces_on_screen"), list) and row["speaker"] in seg["faces_on_screen"],
                  "LIPSYNC_IDENTITY_MISMATCH", "segment speaker/face/lines differ from approval")
            for lid in row["lip_sync_line_ids"]:
                line = line_map.get(lid, {})
                lo, hi = line.get("start", line.get("start_s")), line.get("end", line.get("end_s"))
                _need(line.get("speaker") == row["speaker"] and _num(lo) and _num(hi)
                      and row["start_s"] <= lo < hi <= row["end_s"],
                      "LIPSYNC_IDENTITY_MISMATCH", "line speaker/window missing or inconsistent")
            frames, offset, xfade = seg.get("frames"), seg.get("offset_frames"), seg.get("xfade_frames", 0)
            _need(all(_num(n) for n in (frames, offset, xfade)) and frames > 0 and 0 <= xfade < frames,
                  "LIPSYNC_TIMING_MISSING", "segment frame window required")
            start, duration = (offset - xfade) / fps, frames / fps
            end = start + duration
            _need(abs(start - row["start_s"]) <= 1 / fps + 1e-8
                  and abs(end - row["end_s"]) <= 1 / fps + 1e-8 and 0 <= start < end <= delivered + 1 / fps,
                  "LIPSYNC_TIMELINE_MISMATCH", "clip no longer occupies its approved window")
            _need(not seg.get("hold") and seg.get("stretch", 1) == 1,
                  "LIPSYNC_TIMELINE_MISMATCH", "held/stretched picture is not visible lip-sync evidence")
            source_dur = seg.get("source_dur")
            if require_measured or source_dur is not None:
                _need(_num(source_dur) and source_dur + 1 / fps >= duration,
                      "LIPSYNC_SOURCE_SHORT", "materialized source does not cover the full slot")
            art = seg.get("artifact")
            _need(isinstance(art, dict) and art.get("schema_version") == "1.0.0"
                  and art.get("kind") == "video" and art.get("run_id") == run_id
                  and art.get("artifact_id") and art.get("stage") == "generation" and not art.get("stale"),
                  "LIPSYNC_ARTIFACT_MISSING", "current run video artifact record required")
            source = _path(root, art.get("path"))
            _need(source == _path(root, seg.get("src")), "LIPSYNC_FOREIGN_ARTIFACT", "timeline does not use the proven artifact")
            digest = _sha(source)
            _need(digest == art.get("sha256") and source.stat().st_size > 0,
                  "LIPSYNC_HASH_MISMATCH", "materialized file missing or changed")
            provenance = art.get("provenance") or {}
            task = provenance.get("task_id")
            _need(isinstance(task, str) and task.strip(), "LIPSYNC_TASK_MISSING", "artifact task ID required")
            receipt = _read(_path(root, provenance.get("receipt_path")))
            ev = receipt.get("evidence") or {}
            _need(receipt.get("tool") == "kie_dispatch" and receipt.get("outcome") == "ok" and receipt.get("run_id") == run_id
                  and ev.get("generated") is True and ev.get("task_id") == task,
                  "LIPSYNC_TASK_MISMATCH", "successful task/run receipt required")
            _need(isinstance(ev.get("lipsync_model"), str) and is_locked_lipsync(ev["lipsync_model"]),
                  "LIPSYNC_MODEL_MISMATCH", "unrelated native audio/video cannot count as lip-sync")
            saved_hashes = ev.get("saved_sha256")
            _need(isinstance(saved_hashes, dict), "LIPSYNC_HASH_MISMATCH", "task completion hashes missing")
            matching_hashes = [value for key, value in saved_hashes.items() if _path(root, key) == source]
            _need(bool(matching_hashes) and all(value == digest for value in matching_hashes),
                  "LIPSYNC_HASH_MISMATCH", "file differs from task completion hash")
            _need(ev.get("lipsync_binding") == _binding(row), "LIPSYNC_BINDING_MISMATCH", "task not bound to approved shot revision")
            input_proof = ev.get("lipsync_inputs")
            _need(isinstance(input_proof, dict) and isinstance(input_proof.get("request"), dict),
                  "LIPSYNC_INPUTS_MISSING", "task lacks actual provider input proof")
            _need(input_proof["request"].get("run_id") == run_id
                  and input_proof["request"].get("lipsync_binding") == _binding(row)
                  and inputs_for_request(str(root), input_proof["request"]) == input_proof,
                  "LIPSYNC_INPUTS_MISMATCH", "provider input proof changed or belongs to another shot")
            from audio_c3.lipsync_producer import verify as verify_lineage
            verify_lineage(str(root), run_id, row, input_proof["request"]["lipsync_stems"][0],
                           song_path=plan.get("song_path"))
            saved = ev.get("saved_paths")
            _need(isinstance(saved, list) and source in [_path(root, p) for p in saved],
                  "LIPSYNC_ARTIFACT_MISSING", "task did not materialize this file")
            _need(digest not in hashes and task not in tasks, "LIPSYNC_DUPLICATE_ARTIFACT", "one generated take reused across requirements")
            hashes.add(digest)
            tasks.add(task)
            outgoing_frames = segments[i + 1].get("xfade_frames", 0) if i + 1 < len(segments) else 0
            _need(_num(outgoing_frames) and 0 <= outgoing_frames < frames,
                  "LIPSYNC_TIMING_MISSING", "invalid outgoing crossfade")
            outgoing = outgoing_frames / fps
            clean_start, clean_end = start + xfade / fps, end - outgoing
            _need(clean_end > clean_start, "LIPSYNC_TIMELINE_MISMATCH", "crossfades hide the entire clip")
            windows.append((clean_start, clean_end))
            evidence["included"].append(dict(row, task_id=task, path=str(source), sha256=digest,
                                             visible_start_s=clean_start, visible_end_s=clean_end))
        _need(seen == set(required), "LIPSYNC_UNUSED_REQUIREMENTS", "approved lip-sync clips absent from final timeline")
        cursor, total = -1.0, 0.0
        for lo, hi in sorted(windows):
            total += max(0.0, hi - max(lo, cursor))
            cursor = max(cursor, hi)
        evidence["measured_seconds"] = total
        return {"pass": True, "reason_code": "LIPSYNC_EVIDENCE_OK", "evidence": evidence}
    except (LipsyncEvidenceError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        return {"pass": False, "reason_code": getattr(exc, "code", "LIPSYNC_EVIDENCE_MISSING"),
                "detail": str(exc), "evidence": evidence}
