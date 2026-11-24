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
from kie_dispatch.model_lock import is_allowed_lipsync, is_locked_lipsync

#: F-LIP-2 / 3C.4: H3 image-to-video is the STORY-CLIP model. A landed H3 take
#: may count as lip-sync evidence only with a written order bound to the shot
#: (receipt binds order + shot revision + sha + task + binding). It is never a
#: lip-sync JOB model: that is omnihuman-2-0 alone (S-42).
H3_FALLBACK_MODEL = "minimax-h3/image-to-video"
from lip_sync.narrator_rule import person_on_screen
from lipsync_clips import OPT_OUT_MISSING, ROUTE_NO_LIPSYNC, no_lipsync_opt_out


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


def _storyboard_v3(root):
    """F-LIP-3: the run's ``storyboard-v3.json`` as (shots, contracts, stills,
    approval), or None when the file is absent.

    The v3 layout keeps the four pieces in one document. Tolerant reader: the
    shot list is ``shots`` or ``shot_list``; approval is ``approval`` (a
    ``state`` + per-shot dict) or per-shot ``approval_state``/``status`` keys on
    the shots themselves. Anything malformed is left to the ordinary
    LIPSYNC_EVIDENCE_MISSING validation in ``_approved``, never guessed.
    """
    path = root / "storyboard-v3.json"
    if not path.is_file():
        return None
    doc = _read(_path(root, str(path)))
    _need(isinstance(doc, dict), "LIPSYNC_EVIDENCE_MISSING",
          "storyboard-v3.json is malformed")
    shots = doc.get("shots", doc.get("shot_list"))
    contracts, stills = doc.get("contracts"), doc.get("stills")
    approval = doc.get("approval")
    if approval is None and isinstance(shots, list):
        per_shot = {}
        for shot in shots:
            if not isinstance(shot, dict):
                continue
            status = shot.get("approval_state", shot.get("status"))
            if status in ("approved", "invalidated"):
                per_shot[shot.get("shot_id")] = {
                    "status": status, "revision": shot.get("revision"),
                    "still_sha256": shot.get("still_sha256")}
        approval = {"state": doc.get("approval_state", "approved"),
                    "shots": per_shot}
    return shots, contracts, stills, approval


def _approved_stills(root):
    """The approved stills dict from whichever storyboard layout the run has."""
    path = root / "storyboard" / "stills.json"
    if path.is_file():
        return _read(_path(root, str(path)))
    v3 = _storyboard_v3(root)
    _need(isinstance(v3, tuple) and isinstance(v3[2], dict),
          "LIPSYNC_EVIDENCE_MISSING", "no storyboard stills in either layout")
    return v3[2]


def _approved_shots(root):
    """The raw shot list from either layout (chain needs it for dispatch)."""
    path = root / "storyboard" / "shot-list.json"
    if path.is_file():
        raw = _read(_path(root, str(path)))
        return raw.get("shots") if isinstance(raw, dict) else raw
    v3 = _storyboard_v3(root)
    _need(v3 is not None, "LIPSYNC_EVIDENCE_MISSING",
          "no storyboard shot list in either layout")
    return v3[0]


def _approved(run_dir, route=None):
    """Approved lip-sync requirements for the run.

    S75-047: ``route=ROUTE_NO_LIPSYNC`` is honoured ONLY when
    ``control/method.json`` records ``lipsync_opt_out`` with ``who`` and
    ``at`` (lipsync_clips.no_lipsync_opt_out, the one reader). With the
    record the run needs no storyboard requirements and returns ``{}``;
    without it the gate refuses LIPSYNC_OPT_OUT_MISSING. Every other route
    keeps the ordinary approved-storyboard requirement.
    """
    _need(isinstance(run_dir, (str, Path)) and str(run_dir),
          "LIPSYNC_EVIDENCE_MISSING", "run_dir required")
    root = Path(run_dir).resolve()
    if route == ROUTE_NO_LIPSYNC:
        _need(no_lipsync_opt_out(root) is not None, OPT_OUT_MISSING,
              "the no-lip-sync route needs control/method.json "
              "lipsync_opt_out with who and at; an ordinary run keeps its "
              "approved lip-sync")
        return root, {}
    sb = root / "storyboard"
    if (sb / "shot-list.json").is_file():
        raw = _read(_path(root, str(sb / "shot-list.json")))
        shots = raw.get("shots") if isinstance(raw, dict) else raw
        contracts, stills, approval = [_read(_path(root, str(sb / name)))
                                       for name in ("contracts.json", "stills.json", "approval.json")]
    else:
        # F-LIP-3: no storyboard/ files -> read storyboard-v3.json. Refuse
        # LIPSYNC_EVIDENCE_MISSING only when NEITHER layout yields a package.
        v3 = _storyboard_v3(root)
        _need(v3 is not None, "LIPSYNC_EVIDENCE_MISSING",
              "no storyboard/ files and no storyboard-v3.json in the run")
        shots, contracts, stills, approval = v3
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
                         "storyboard_revision": revision, "start_s": start, "end_s": end,
                         # F-LIP-2 route token the storyboard claims; the join
                         # compares it with the landed clip, never the reverse.
                         "route": shot.get("lip_sync_route") or "lip_sync",
                         # N-73: the Shot Router names the expression sheet.
                         "expression_sheet": shot.get("expression_sheet"),
                         "emotion": shot.get("emotion") or (shot.get("beat") or {}).get("emotion")}
    _need(seen == set(per_shot), "LIPSYNC_APPROVAL_STALE",
          "current shot IDs differ from the approved storyboard")
    _need(bool(required), "LIPSYNC_REQUIREMENTS_MISSING", "approved storyboard has no lip-sync requirements")
    all_lids = [lid for r in required.values() for lid in r["lip_sync_line_ids"]]
    _need(len(all_lids) == len(set(all_lids)), "LIPSYNC_IDENTITY_MISMATCH", "a lip-sync line occurs in multiple approved shots")
    return root, required


def _binding(row):
    return {key: row[key] for key in ("shot_id", "lip_sync_line_ids", "speaker", "storyboard_revision")}


#: The status approval_package.approval_entries and the runner use for a shot
#: whose approval no longer stands (a scoped revision). A regenerated lip-sync
#: picture re-opens exactly its own shot and nothing else.
REOPENED_STATUS = "invalidated"

#: F-LIP-2: after two lettered lip-sync tries the third job is a remake of the
#: SAME route with a fixed prompt -- letters and decor removed from the source
#: record -- never a silent switch to another model.
THIRD_TRY_RULE = ("third job = same-route remake with the fixed prompt "
                  "(letters and decor removed); a model switch is never silent")


def reopen_shot_approval(run_dir, shot_id):
    """Re-open ONE shot's storyboard approval, in place, atomically.

    Used when a lip-sync picture was REGENERATED (a new picture is not the
    approved still). Only that shot changes; every other shot keeps its
    standing. Returns the approval record that was written.
    """
    root = Path(run_dir).resolve()
    path = _path(root, str(root / "storyboard" / "approval.json"))
    record = _read(path)
    shots = record.get("shots") if isinstance(record, dict) else None
    _need(isinstance(shots, dict) and isinstance(shots.get(shot_id), dict),
          "LIPSYNC_APPROVAL_MISSING",
          "no per-shot storyboard approval to re-open for %s" % (shot_id,))
    entry = shots[shot_id]
    if entry.get("status") != REOPENED_STATUS:
        entry["status"] = REOPENED_STATUS
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
        temp.replace(path)
    return record


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
    if stem.get("delivery") is not None:      # the line's own delivery (sung/spoken)
        meta["delivery"] = stem.get("delivery")
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
    """Bind actual provider URLs to the approved still and isolated own-line bytes.

    The provider picture may be the approved still itself or a CROP of it,
    recorded by the picture gate as a derivation (source_sha256 = the approved
    still, operation "crop"). A regenerated picture is a new picture: it is
    refused LIPSYNC_PICTURE_NEEDS_APPROVAL and that shot's storyboard approval
    is re-opened (U-U03).
    """
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
        rdir = request.get("lipsync_receipt_dir") or PG.default_receipt_dir(str(image))
        rdir = Path(rdir)
        rdir = (rdir if rdir.is_absolute() else root / rdir).resolve()
        # F-LIP-3: the approved stills come from whichever layout the run has
        # (storyboard/ or storyboard-v3.json); the dispatch proof must read the
        # same package the join approved, never one layout only.
        approved_stills = _approved_stills(root)
        approved_hash = _sha(_path(root, approved_stills[row["shot_id"]]))
        derivation = None
        if image_hash != approved_hash:
            derivation = PG.read_derivation(image_hash, str(rdir))
            _need(bool(derivation), "LIPSYNC_IMAGE_MISMATCH",
                  "provider picture is not the approved storyboard still")
            crop = (derivation.get("operation") == PG.OPERATION_CROP
                    and derivation.get("source_sha256") == approved_hash
                    and derivation.get("derived_sha256") == image_hash)
            if not crop:
                if derivation.get("operation") == PG.OPERATION_REGENERATE:
                    reopen_shot_approval(root, row["shot_id"])
                raise LipsyncEvidenceError(
                    "LIPSYNC_PICTURE_NEEDS_APPROVAL",
                    "provider picture is a %s, not the approved still; the "
                    "storyboard approval for %s is re-opened for a person"
                    % (derivation.get("operation") or "change", row["shot_id"]))
        gate_path = _path(root, str(rdir / (image_hash + ".json")))
        upload_path = _path(root, str(rdir / (image_hash + ".upload.json")))
        PG.require_receipt(str(image), str(rdir))
        PG.require_upload_bound(str(image), inp.get("image_url"), str(rdir))
        lock = _read(_path(root, str(root / "control" / "look-lock.json"))) \
            if (root / "control" / "look-lock.json").is_file() else None
        # N-43: a lip-sync picture is a step-2 keyframe of THIS lock version made
        # from the approved references. A frame grabbed from a clip, or a picture
        # from an older lock version, refuses before any paid job.
        if isinstance(derivation, dict):
            _need(derivation.get("operation") not in ("clip_frame", "frame_from_clip"),
                  "LIPSYNC_PICTURE_NOT_FROM_REFERENCES",
                  "the provider picture was grabbed from a clip; a lip-sync "
                  "picture is made from the approved references")
        if isinstance(lock, dict):
            current = lock.get("lock_version", lock.get("version"))
            carried = request.get("lock_version", row.get("lock_version"))
            _need(carried is None or carried == current,
                  "LIPSYNC_PICTURE_NOT_FROM_REFERENCES",
                  "the lip-sync picture comes from lock version %r but the run "
                  "is at %r; remake it from the current references" % (carried, current))
        # N-73: the Shot Router names the expression sheet. A picture whose
        # sheet is not the named one is refused before any paid job.
        named_sheet = row.get("expression_sheet")
        if named_sheet:
            _need(request.get("expression_sheet") == named_sheet,
                  "LIPSYNC_EXPRESSION_MISMATCH",
                  "the shot names expression sheet %r and the picture request "
                  "carries %r; a sad line is never sung from another sheet"
                  % (named_sheet, request.get("expression_sheet")))
        emotion = row.get("emotion")
        if emotion:
            _need(request.get("emotion") in (None, emotion),
                  "LIPSYNC_EXPRESSION_MISMATCH",
                  "the line is %r and the picture request is %r"
                  % (emotion, request.get("emotion")))
        stems = request.get("lipsync_stems")
        # One stem per SONG: the separated vocal carries the separation job's
        # first-line speaker, while this request is for THIS line. Screen this
        # line's cut (kind, isolation, sung rule), not the job's speaker.
        line_stem = dict(stems[0], speaker_id=row["speaker"])
        ok, code, errors = check_stems([line_stem], row["speaker"])
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


def route_agrees(route, model, order, row, *, sid, digest, task):
    """F-LIP-2: verify the PLAN's route against the LANDED clip, never the
    reverse. Returns {"role", "fallback"} for an admitted take; raises
    LIPSYNC_MODEL_UNLISTED for a third model name nobody approved and
    LIPSYNC_ROUTE_CHANGED when the route says the locked lip-sync route but the
    landed clip is from another approved model with no recorded order bound to
    this shot's revision, bytes and task.

    ``route`` is the plan/segment route (e.g. ``kling_lipsync``); it is used for
    the message only, because the authority is always the landed clip. Under
    S-42 the locked model is omnihuman-2-0 and there is no backup model, so a
    fallback take can never pass; the branch stays so an older run is refused,
    not silently admitted."""
    model = (model or "").strip() if isinstance(model, str) else ""
    _need(model, "LIPSYNC_MODEL_MISMATCH",
          "unrelated native audio/video cannot count as lip-sync")
    # S-42: the lip-sync JOB model is omnihuman-2-0, one model, no backup. The
    # H3 evidence fallback of F-LIP-2 is not a lip-sync job: it is a landed
    # motion take that may stand as lip-sync evidence ONLY under a written
    # order. A third model name is LIPSYNC_MODEL_UNLISTED.
    role = "locked" if is_locked_lipsync(model) else (
        "fallback" if model == H3_FALLBACK_MODEL else None)
    _need(role is not None, "LIPSYNC_MODEL_UNLISTED",
          "lip-sync model %r is neither the locked lip-sync model nor an "
          "approved fallback" % (model,))
    if role == "fallback":
        ok = (isinstance(order, dict)
              and str(order.get("order") or "").strip()
              and order.get("shot_id") == sid
              and order.get("shot_revision") == row["storyboard_revision"]
              and order.get("sha256") == digest
              and str(order.get("task_id") or "").strip() == task
              and order.get("binding") == _binding(row))
        _need(ok, "LIPSYNC_ROUTE_CHANGED",
              "route %s says the locked lip-sync model but the landed clip is "
              "%s with no recorded order bound to this shot/revision/sha/task"
              % (route or "lip_sync", model))
    return {"role": role, "fallback": role == "fallback"}


def check_plan(plan, require_measured=False, route=None):
    """Join approved requirements, successful receipts, files and actual slots.

    Frame rounding may differ by one frame. Crossfade opacity time is excluded
    from measured coverage. In production, source_dur must be a measured probe.
    Dry-run callers may omit it, explicitly reporting source duration unverified.

    ``route`` defaults to ``plan["route"]``. ROUTE_NO_LIPSYNC (S75-047) passes
    with zero requirements only when ``control/method.json`` records the owner
    opt-out; otherwise it is refused by ``_approved``.
    """
    evidence = {"included": [], "requirements": [], "measured_seconds": 0.0,
                "source_duration_verified": bool(require_measured)}
    try:
        _need(isinstance(plan, dict), "LIPSYNC_EVIDENCE_MISSING", "plan object required")
        route = route or plan.get("route")
        root, required = _approved(plan.get("run_dir"), route)
        evidence["requirements"] = list(required.values())
        if route == ROUTE_NO_LIPSYNC:
            evidence["route"] = route
            evidence["lipsync_opt_out"] = no_lipsync_opt_out(root)
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
            sid = seg.get("shot_id")
            if not (seg.get("lip_sync") or seg.get("lip_sync_line_ids")):
                # F-LIP-2: a motion-flagged shot is remade with H3, never with
                # the lip-sync model. A non-lip-sync slot whose own receipt
                # names a lip-sync model is the route read backwards.
                art0 = seg.get("artifact") or {}
                rec0 = (art0.get("provenance") or {}).get("receipt_path")
                if rec0:
                    m0 = (_read(_path(root, rec0)).get("evidence") or {}).get("lipsync_model")
                    _need(not (isinstance(m0, str) and is_allowed_lipsync(m0)),
                          "LIPSYNC_ROUTE_CHANGED",
                          "shot %r is not lip-sync but its take is %r; motion "
                          "shots are remade with H3, never the lip-sync model"
                          % (sid, m0))
                continue
            row = required.get(sid)
            _need(row is not None and sid not in seen, "LIPSYNC_IDENTITY_MISMATCH", "unused/unapproved or duplicate lip-sync segment")
            seen.add(sid)
            _need(seg.get("speaker") == row["speaker"] and seg.get("lip_sync_line_ids") == row["lip_sync_line_ids"]
                  and isinstance(seg.get("faces_on_screen"), list) and row["speaker"] in seg["faces_on_screen"],
                  "LIPSYNC_IDENTITY_MISMATCH", "segment speaker/face/lines differ from approval")
            piece_starts, piece_ends = [], []
            for lid in row["lip_sync_line_ids"]:
                line = line_map.get(lid, {})
                lo, hi = line.get("start", line.get("start_s")), line.get("end", line.get("end_s"))
                _need(line.get("speaker") == row["speaker"] and _num(lo) and _num(hi)
                      and row["start_s"] <= lo < hi <= row["end_s"],
                      "LIPSYNC_IDENTITY_MISMATCH", "line speaker/window missing or inconsistent")
                piece_starts.append(lo)
                piece_ends.append(hi)
            # N-101 (3.3a rules 1 and 6): a piece is whole sentences. It runs
            # from its first sentence's first word to its last sentence's last
            # word; a piece cut inside a sentence refuses here, before assembly.
            # One frame of rounding is allowed.
            _need(abs(row["start_s"] - min(piece_starts)) <= 1 / fps + 1e-8
                  and abs(row["end_s"] - max(piece_ends)) <= 1 / fps + 1e-8,
                  "LIPSYNC_CUTS_SENTENCE",
                  "lip-sync piece %r starts or ends inside a sentence; a piece is "
                  "whole sentences, never cut mid-sentence" % (sid,))
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
            # Lock 2 (NEVER-AGAIN dispatch lock): only kie_dispatch receipts
            # count; a direct-API receipt refuses NO_DIRECT_SUBMIT, never a
            # generic mismatch.
            if receipt.get("tool") != "kie_dispatch":
                import never_again as _na
                raise LipsyncEvidenceError(
                    _na.NO_DIRECT_SUBMIT,
                    "paid job submitted outside kie_dispatch "
                    "(direct API post refused; re-blast via dispatch())")
            _need(receipt.get("outcome") == "ok" and receipt.get("run_id") == run_id
                  and ev.get("generated") is True and ev.get("task_id") == task,
                  "LIPSYNC_TASK_MISMATCH", "successful task/run receipt required")
            # N-16: an ADOPTED take (already paid, registered from the governed
            # ledger) is accepted on its ledger row -- job id, model and file
            # fingerprint -- exactly like a freshly dispatched one. The row
            # carries `adopted` and its ledger job; the receipt must still be
            # the governed kie_dispatch one (checked above), so nothing bought
            # outside the governor can be adopted.
            if seg.get("adopted"):
                _need(isinstance(seg.get("ledger_job"), str) and seg["ledger_job"].strip(),
                      "LIPSYNC_TASK_MISSING",
                      "an adopted take must name its governed ledger job row")
                evidence.setdefault("adopted", []).append(sid)
            # LIP-02 / F-LIP-2: the PLAN's route is verified against the LANDED
            # clip, never the reverse. A third model name refuses
            # LIPSYNC_MODEL_UNLISTED; a route that claims the locked lip-sync
            # model but lands another approved model with no recorded order
            # bound to this shot/revision/sha/task refuses LIPSYNC_ROUTE_CHANGED
            # right here, before assembly.
            role = route_agrees(row.get("route"), ev.get("lipsync_model"),
                                ev.get("h3_fallback_order"), row, sid=sid,
                                digest=digest, task=task)["role"]
            model = ev["lipsync_model"]
            if model.strip() not in evidence.setdefault("models", []):
                evidence["models"].append(model.strip())
            if role == "fallback" and "models_fallback" not in evidence:
                evidence["models_fallback"] = True
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
            # N-113: no eye record, no entry to the timeline. N-118 rides the
            # same record: a wrong-voice mouth or an emotion drift written there
            # refuses before assembly. G-WIDE-01: the singer must be seen close.
            # Every lip-sync take needs the eye record -- a scan alone is never
            # a pass, so there is no declaration that turns this off.
            from lip_sync.lip_gate import lip_gate as _LG
            _need(_LG.eye_recorded(seg), _LG.LIP_TAKE_NOT_EYE_CHECKED,
                  "lip-sync take %r has no eye record (4-frames-per-second "
                  "contact sheet, who looked, verdict); a scan is not a pass"
                  % (sid,))
            eye = seg.get("eye_record") or {}
            _need(str(eye.get("wrong_voice", "")).lower() not in ("true", "yes", "1")
                  and eye.get("wrong_voice_mouthed") is not True,
                  "WRONG_VOICE_MOUTHED",
                  "take %r mouths a part that is not its own (Right Voice check)" % (sid,))
            # G-WIDE-01: the singer must be seen close. Every landed take is
            # checked -- a take with no landed facts refuses, never passes.
            close = _LG.closeup_landed(seg.get("landed"))
            _need(close["pass"], _LG.LIPSYNC_NO_CLOSEUP,
                  "%s: %s" % (sid, close.get("detail")))
            # N-118 (3G.6): a tagged line's take carries the Emotion Hold result.
            # A drift at intensity 2 or 3 refuses EMOTION_DRIFT; a check that
            # could not run refuses too, never a silent pass.
            if row.get("emotion"):
                hold = seg.get("emotion_hold")
                _need(isinstance(hold, dict), "EMOTION_DRIFT",
                      "take %r has no Emotion Hold result for its %r line; no "
                      "take enters the timeline unchecked" % (sid, row["emotion"]))
                _need(hold.get("verdict") in (None, "PASS", "OK"), "EMOTION_DRIFT",
                      "%s: %s" % (sid, hold.get("detail") or hold.get("verdict")))
            # N-101: the returned clip is at least as long as the audio sent.
            # `take_dur_s` is the measured returned length; a take that reports
            # shorter than its sentence window refuses LIPSYNC_TAKE_SHORT.
            take_dur = seg.get("take_dur_s")
            if take_dur is not None:
                _need(_num(take_dur) and _num(row["end_s"]) and _num(row["start_s"])
                      and take_dur + 1 / fps >= (row["end_s"] - row["start_s"]),
                      "LIPSYNC_TAKE_SHORT",
                      "take %r came back shorter than its audio; cut the take at "
                      "the sentence's length, never the sentence at the take"
                      % (sid,))
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
                                             visible_start_s=clean_start, visible_end_s=clean_end,
                                             # N-101: every piece stamps what was sent and
                                             # what came back, with its price and job time.
                                             sent_s=round(row["end_s"] - row["start_s"], 3),
                                             returned_s=source_dur,
                                             credits=ev.get("credits"),
                                             job_s=ev.get("job_time_s")))
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
