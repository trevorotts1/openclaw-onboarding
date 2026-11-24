#!/usr/bin/env python3
"""One command for the whole lip-sync chain (S75-038; unit U-U02).

    cd scripts/core && python3 -m lip_sync run --run-dir "$RUN" ...

For every planned lip-sync clip (every approved shot that carries
``lip_sync_line_ids``) the chain runs, in this order and nothing else:

  1. ``gate_picture``      measured close-up gate + sha256 receipt
                           (``lip_gate/picture_gate.py``). A picture that is
                           not PASS/ACCEPT_WITH_FLAG refuses the run before any
                           spend; a gated picture that is not the approved
                           storyboard still also refuses (the evidence layer
                           joins the provider picture to the approved bytes).
  2. ``upload_measured``   the exact measured bytes, URL bound to their sha256.
  3. cut the line          ``audio_c3.lipsync_producer.produce`` -- ONE vocal
                           separation per song (S75-056), every clip cut from
                           ``music/vocal-stem.mp3``.
  4. ``upload_stem``       the own-line stem, receipt bound to the URL.
  5. ``kie_dispatch``      the paid ``omnihuman-2-0`` job, under the
                           ledger reserve, the card gate, the picture gate and
                           the stem/picture input join.
  6. ``run_gate``          ``lip_gate.run_gate``: the 2-try rule, the attempt
                           ceiling and ``load_governor.kie_request`` pacing.
  7. ``eye_check``         the whole-frame contact sheet at 4 frames per
                           second (N-113) for the kept take. The code builds
                           the sheet; who looked and the verdict are a
                           reader's, and a take without them is refused
                           ``LIP_TAKE_NOT_EYE_CHECKED`` at the evidence join.

What it writes under ``<run>/control/lip-sync/``:

  evidence.json            one row per clip: the artifact record, the dispatch
                           receipt path, the gate row and the measured numbers.
  receipts/<shot>-tryN.json  every dispatch envelope, kept verbatim.
  picture-receipts/        the picture gate receipts and upload bindings.

``final_assembler``'s ``check_plan`` reads the receipt each row's
``artifact.provenance.receipt_path`` names; with the command never run there is
no receipt, so ``check_plan`` refuses (the control in
``test_lipsync_run_s75_038.py``).

Injection: ``run(..., providers={...})`` takes the offline doubles the test
needs. Picture measurement, uploads, the Skill 74 separation runner and the
dispatch transport are all injectable; nothing is synthesized as a default.
``skill74_runner`` needs ``source_uploader`` and ``isolated_stem_reader``
(``audio_c3/lipsync_producer.py``); the command builds the source uploader
from the real Skill 74 ``upload`` path, and reads the isolation metadata the
run's existing audio preparation/QC recorded (``--isolation-metadata``), never
a guess.

ponytail: try 2 (a person's DEFECT) is capped and held here -- ``run_gate``
refuses a second paid job without a CHANGED input, and the evidence contract
binds the stem to the approved shot window, so a different window is already
refused upstream. When the shot window becomes a legal retry input, pass it as
``retry_input`` and re-cut in ``_generate``.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from kie_dispatch import model_lock as _ML

# F-LIP-2 / S-42: ONE source of truth. The lip-sync model id lives in
# kie_dispatch.model_lock and this chain follows it, so the route that is
# dispatched can never drift from the route the evidence join verifies.
MODEL = _ML.LOCKED_LIPSYNC_MODEL
PROVIDER = MODEL.split("/")[0] if "/" in MODEL else MODEL
TOOL = "lip_sync.run"
SCHEMA = "blackceo.lipsync-run/v1"
VERSION = "1.0.0"
STAGES = ("video-generation", "qc-retakes")
STEPS = ("gate_picture", "upload_measured", "cut_line_from_one_stem",
         "upload_stem", "kie_dispatch", "run_gate", "eye_check")
ACCEPTED = ("PASS", "ACCEPT_WITH_FLAG", "KEPT_BEST_OF_2", "UNDETERMINED",
            "UNMEASURABLE")
EXIT = {"ok": 0, "refused": 5, "error": 1}


class ChainError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _need(ok, code, message):
    if not ok:
        raise ChainError(code, message)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    temp.replace(path)


def _sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for part in iter(lambda: f.read(1 << 20), b""):
            h.update(part)
    return h.hexdigest()


def _envelope(outcome, code, detail="", **rest):
    return dict({"schema_version": SCHEMA, "tool": TOOL, "tool_version": VERSION,
                 "command": "run", "outcome": outcome, "reason_code": code,
                 "detail": detail, "steps": list(STEPS),
                 "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                **rest)


def _run_id(root):
    """The run's own id: the stage store first, then the run state file."""
    import sqlite3
    db = root / "control" / "state.sqlite3"
    if db.is_file():
        try:
            conn = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=10)
            try:
                rows = conn.execute("SELECT DISTINCT run_id FROM stages").fetchall()
            finally:
                conn.close()
        except sqlite3.Error as exc:
            raise ChainError("RUN_STATE_UNREADABLE", str(exc))
        ids = {r[0] for r in rows if r[0]}
        if len(ids) == 1:
            return ids.pop()
    state = root / "control" / "run-state.json"
    if state.is_file():
        held = _read(state)
        if isinstance(held, dict) and held.get("run_id"):
            return str(held["run_id"])
    raise ChainError("RUN_ID_MISSING", "no control/state.sqlite3 run id and no "
                                      "control/run-state.json run_id")


def _defaults():
    """Every collaborator the chain calls; a real default where one exists."""
    from audio_c3 import lipsync_producer as producer
    from lip_sync.lip_gate import lip_gate as gate
    from lip_sync.lip_gate import picture_gate as PG
    return {"picture_gate": PG, "producer": producer, "lip_gate": gate,
            "picture_measure": None, "picture_uploader": None,
            "stem_uploader": None, "source_uploader": None,
            "isolated_stem_reader": None, "separation_runner": None,
            "dispatch_fn": None, "dispatch_runner": None, "adapter_path": None,
            "measure_offset": None, "cut_runner": None, "measure_clip": None,
            "make_strip": None, "make_eye_sheet": None,
            "advisory": None, "person_verdicts": {},
            "eye_records": None, "landed_takes": None,
            "image_analyze": None, "identity_references": None,
            "emotion_takes": None, "voice_map": None,
            "sung": True, "look": None, "stage": "video-generation",
            "ledger_db": None, "state_store": None, "usd_per_s": None,
            "remaining_usd": None, "shots": None, "budget": True}


def _providers(overrides):
    import lip_sync.lip_gate.picture_gate as PG
    out = _defaults()
    out.update({k: v for k, v in (overrides or {}).items() if v is not None})
    if out["picture_gate"] is None:
        out["picture_gate"] = PG
    return out


def _remaining_usd(ledger_db, run_id):
    import spend_ledger
    summary = spend_ledger.summary(str(ledger_db), run_id)
    _need(summary.get("outcome") != "error", "LIPSYNC_LEDGER_UNREADABLE",
          str(summary.get("reason_code")))
    return summary["evidence"]["remaining_budget"] / 100.0


def _budget(total_s, p):
    """The module's own pre-dispatch cap check; unknown price or cap refuses."""
    import lipsync_clips
    usd_per_s = p["usd_per_s"]
    remaining = p["remaining_usd"]
    if remaining is None and p["ledger_db"]:
        remaining = _remaining_usd(p["ledger_db"], p["run_id"])
    return lipsync_clips.check_budget(total_s, usd_per_s, remaining)


def _dispatch_clip(root, run_id, shot_id, row, image, rdir, image_url, uploaded,
                   spec, attrs):
    """One paid lip-sync job through kie_dispatch; returns the saved clip."""
    import kie_dispatch.kie_dispatch as D
    from lipsync_evidence import _binding
    _need(spec.get("source_image") in (None, str(image)),
          "LIPSYNC_INPUTS_MISMATCH",
          "the gate input is not the approved storyboard still")
    shots = attrs["shots"]
    gate_doc = attrs["gate"]
    request = {"input": {"image_url": image_url, "audio_url": uploaded["url"]},
               "card_receipt": attrs["card_receipt"],
               "run_dir": str(root),
               "request_kind": "lipsync",
               "lipsync_binding": _binding(row),
               "lipsync_image_path": str(image),
               "lipsync_receipt_dir": str(rdir),
               "lipsync_stems": [uploaded],
               # N-43 / N-73: the request names the lock version and the sheet
               # the shot's line came from; the join refuses a mismatch.
               "lock_version": (row.get("lock_version")),
               "expression_sheet": row.get("expression_sheet"),
               "emotion": row.get("emotion"),
               "production_stage": attrs["stage"],
               "storyboard": {"shots": shots, "review": gate_doc.get("review") or {}}}
    save_dir = root / "generation" / "lipsync" / shot_id
    save_dir.mkdir(parents=True, exist_ok=True)
    envelope = (attrs["dispatch_fn"] or D.dispatch)(
        model=MODEL, request=request, save_dir=str(save_dir),
        ledger_db=str(attrs["ledger_db"]), run_id=run_id,
        logical_key="lip-ad-" + shot_id, attempt_id="",
        estimated_cost=attrs["estimated_cost"], prompt="",
        stage=attrs["stage"], owner="lip-sync", adapter_path=attrs["adapter_path"],
        runner=attrs["dispatch_runner"], state_store=attrs["state_store"])
    try_number = len(list((root / "control" / "lip-sync" / "receipts").glob(
        shot_id + "-try*.json"))) + 1
    receipt = root / "control" / "lip-sync" / "receipts" / (
        "%s-try%d.json" % (shot_id, try_number))
    _write(receipt, envelope)
    _need(envelope.get("outcome") == "ok", "LIPSYNC_DISPATCH_FAILED",
          "%s: %s" % (envelope.get("reason_code"), envelope.get("next_action")))
    evidence = envelope.get("evidence") or {}
    saved = [str(p) for p in evidence.get("saved_paths") or []]
    _need(bool(saved), "LIPSYNC_DISPATCH_FAILED", "the task saved no clip")
    clip = next((s for s in saved if Path(s).suffix.lower() in
                 (".mp4", ".mov", ".webm")), saved[0])
    _need(Path(clip).is_file(), "LIPSYNC_DISPATCH_FAILED", clip)
    attrs["last"] = {"receipt_path": str(receipt), "clip": clip,
                     "task_id": evidence.get("task_id"),
                     "sha256": evidence.get("saved_sha256", {}).get(clip)
                     or _sha_file(clip)}
    return clip


def _reference_paths(root, speaker):
    """F-PIC-1: the approved reference pictures for one character, from the
    run's look lock. Returns [] when the lock or the entry is absent."""
    path = Path(root) / "control" / "look-lock.json"
    if not path.is_file():
        return []
    doc = _read(path)
    chars = doc.get("characters") if isinstance(doc, dict) else None
    entry = None
    if isinstance(chars, dict):
        entry = chars.get(speaker)
    elif isinstance(chars, list):
        entry = next((c for c in chars if isinstance(c, dict)
                      and (c.get("character") == speaker or c.get("id") == speaker)), None)
    out = []

    def collect(v):
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            for key in ("path", "file"):
                if isinstance(v.get(key), str):
                    out.append(v[key])
    for source in (entry if isinstance(entry, list) else [entry]):
        if isinstance(source, dict):
            for key in ("refs", "references", "pictures", "views"):
                for item in source.get(key) or []:
                    collect(item)
            collect(source)
        elif isinstance(source, str):
            collect(source)
    resolved = []
    for value in out:
        q = Path(value)
        q = (q if q.is_absolute() else Path(root) / q).resolve()
        if q.is_file():
            resolved.append(str(q))
    return resolved


def _eye_sheet_builder(root):
    """N-113: the real whole-frame 4-fps contact sheet, built with ffmpeg.

    Returns make_eye_sheet(clip, shot_id) -> sheet path; raises on failure so
    the caller records the error instead of inventing a pass. A take with no
    completed eye record is refused LIP_TAKE_NOT_EYE_CHECKED at the join."""
    from lip_sync.lip_gate import lip_process as _LP
    import load_governor as _LG

    def build(clip, shot_id, duration_s=None):
        dur = duration_s
        if not dur:
            raise RuntimeError("eye sheet needs the take's measured duration")
        out = _LP.eye_sheet_path(str(root), shot_id)
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        proc = _LG.run_ffmpeg(_LP.eye_sheet_argv(clip, out, dur),
                              "eye-sheet", stdout=-1, stderr=-1)
        if proc.returncode != 0 or not Path(out).is_file():
            raise RuntimeError("ffmpeg contact sheet failed for " + shot_id)
        return out
    return build


def _voice_map_passed(root):
    """N-117: the run's Voice Map gate result. Absent or unpassed is a refusal;
    a map that is present but has not passed is never guessed at."""
    path = Path(root) / "control" / "voice-map.json"
    if not path.is_file():
        return False
    try:
        doc = _read(path)
    except (OSError, ValueError):
        return False
    if not isinstance(doc, dict):
        return False
    gate = doc.get("gate") if isinstance(doc.get("gate"), dict) else {}
    return doc.get("passed") is True or gate.get("passed") is True \
        or doc.get("state") == "passed"


def _identity_analyzer(root, p, speaker):
    """F-PIC-1: the real supplier called in the intake path before any spend.
    Identity is MEASURED against the approved reference set; with no reference
    set the chain refuses rather than taking a caller's word."""
    from lip_sync.lip_gate import image_gate, picture_measure
    measure = p.get("picture_measure") or getattr(picture_measure, "measure")
    refs = p.get("identity_references") or _reference_paths(root, speaker)
    if not refs:
        raise ChainError("LIPSYNC_IMAGE_UNMEASURED",
                         "no approved reference pictures for %r; face identity "
                         "cannot be measured" % (speaker,))
    return image_gate.reference_analyzer(measure, refs)


def _clip(root, run_id, shot_id, row, p, stills, attrs):
    """The chain for ONE planned clip. Returns its evidence row."""
    PG = p["picture_gate"]
    producer = p["producer"]
    gate = p["lip_gate"]
    attrs["last"] = None
    rdir = root / "control" / "lip-sync" / "picture-receipts"
    image = Path(stills[shot_id])
    image = (image if image.is_absolute() else root / image).resolve()
    _need(image.is_file() and image.is_relative_to(root), "LIPSYNC_IMAGE_MISSING",
          str(image))

    # N-118 / 3G.6 lever 1 and 2: the remake prompt carries the sentence's own
    # expression, one step stronger on pain lines (the picture is the only
    # control OmniHuman gets; it is fed no prompt).
    gated = PG.gate_picture(str(image), receipt_dir=str(rdir),
                            measure=p["picture_measure"], no_smile=True,
                            emotion=row.get("emotion"),
                            intensity=int(row.get("emotion_intensity") or 2))
    _need(gated.get("verdict") in PG.ACCEPTED, "LIPSYNC_PICTURE_NOT_GATED",
          "%s: %s" % (gated.get("verdict"),
                      "; ".join("%s: %s" % tuple(x)
                                for x in gated.get("reasons", []))))
    _need(Path(gated["image"]).resolve() == image, "LIPSYNC_GATED_NOT_APPROVED",
          "the gate kept a different picture (%s); the approved still is the "
          "only lip-sync source (settled by U-U03)" % gated["image"])
    # F-PIC-1: measure face identity against the approved references at intake.
    from lip_sync.lip_gate import image_gate as _IG
    analyze = p.get("image_analyze") or _identity_analyzer(root, p, row["speaker"])
    try:
        _IG.require_source_image(str(image), analyze)
    except _IG.LipsyncImageRefused as exc:
        raise ChainError((exc.reasons[0][0] if exc.reasons
                          else _IG.UNMEASURED), str(exc))
    image_url = PG.upload_measured(str(image), uploader=p["picture_uploader"],
                                   receipt_dir=str(rdir))

    runner = p["separation_runner"]
    if runner is None:
        _need(callable(p["source_uploader"]) and callable(p["isolated_stem_reader"]),
              "LIPSYNC_PROVIDER_MAPPING_MISSING",
              "the real run needs a source uploader and the run's audio "
              "preparation/QC isolation metadata; neither is invented here")
        runner = producer.skill74_runner(
            str(root), p["source_uploader"],
            {"ledger_db": str(attrs["ledger_db"]), "stage": attrs["stage"],
             "adapter_path": attrs["adapter_path"],
             "runner": attrs["dispatch_runner"], "attempt_id": "",
             "estimated_cost": attrs["estimated_cost"]},
            p["isolated_stem_reader"], dispatch_fn=p["dispatch_fn"])
    stem = producer.produce(
        str(root), run_id, shot_id, attrs["song_path"], runner,
        measure_offset=p["measure_offset"], cut_runner=p["cut_runner"])

    uploader = p["stem_uploader"]
    _need(callable(uploader), "LIPSYNC_PROVIDER_MAPPING_MISSING",
          "the own-line stem upload needs the Skill 74 upload transport")
    from lipsync_evidence import upload_stem
    uploaded = upload_stem(str(root), stem, uploader, run_id)

    def image_check(path):
        try:
            PG.require_receipt(path, str(rdir))
            PG.require_upload_bound(path, image_url, str(rdir))
            return {"pass": True}
        except PG.LipsyncPictureNotGated as exc:
            return {"pass": False, "reasons": [(PG.REFUSED, str(exc))]}

    def measure_clip(clip):
        measure = p["measure_clip"]
        if measure is not None:
            return measure(clip)
        return gate.measure_file(clip, audio=stem["path"])

    def generate(provider, spec):
        _need(provider == PROVIDER, "LIPSYNC_MODEL_MISMATCH",
              "the locked lip-sync model is %s" % MODEL)
        return _dispatch_clip(root, run_id, shot_id, row, image, rdir,
                              image_url, uploaded, spec, attrs)

    prior = len(list((root / "control" / "lip-sync" / "receipts").glob(
        shot_id + "-try*.json")))
    from lip_sync.lip_gate import image_gate
    # N-117: no passed Voice Map, no lip-sync piece.
    if p.get("require_voice_map", True):
        _need(_voice_map_passed(root), "VOICE_MAP_MISSING",
              "the run has no passed control/voice-map.json; who sings what "
              "must be known before a paid lip-sync piece")
    # N-101: the piece is a whole sentence group, 5 to 30 seconds. The
    # constants are lipsync_clips' (U-PLAN owns the numbers); this is the
    # dispatcher's refusal before any spend.
    import lipsync_clips as _LC
    window = float(row["end_s"]) - float(row["start_s"])
    _need(window + 1e-9 >= _LC.CLIP_MIN_S, "LIPSYNC_AUDIO_TOO_SHORT",
          "piece %s is %.2f s of audio; the floor is %.1f s (join the singer's "
          "neighbouring sentence)" % (shot_id, window, _LC.CLIP_MIN_S))
    _need(window <= _LC.CLIP_MAX_S + 1e-9, "LIPSYNC_AUDIO_TOO_LONG",
          "piece %s is %.2f s of audio; the top is %.0f s (the stitch is the fix)"
          % (shot_id, window, _LC.CLIP_MAX_S))
    try:
        gate_row = gate.run_gate(
            shot_id, generate, measure_clip, source_image=str(image),
            image_check=image_check, sung=bool(p["sung"]),
            retry_input=None,
            prior_jobs=prior,
            make_strip=p["make_strip"], advisory=p["advisory"],
            look=p["look"],
            eye_record=(p.get("eye_records") or {}).get(shot_id),
            landed=(p.get("landed_takes") or {}).get(shot_id),
            emotion=row.get("emotion"),
            intensity=int(row.get("emotion_intensity") or 2),
            emotion_check=p.get("emotion_check"),
            person_verdict=(p["person_verdicts"] or {}).get(shot_id))
    except gate.LipTryLimit as exc:
        raise ChainError(gate.LIP_TRY_LIMIT, str(exc))
    except image_gate.LipsyncImageRefused as exc:
        raise ChainError("LIPSYNC_PICTURE_NOT_GATED", str(exc))
    last = attrs.get("last") or {}
    _need(bool(last.get("receipt_path")), "LIPSYNC_DISPATCH_FAILED",
          "the gate kept no dispatched try for " + shot_id)
    # N-113 (3C.1b lesson 3), the seventh step: build the whole-frame contact
    # sheet at 4 frames per second for the kept take. The sheet is made here;
    # who LOOKED and the verdict are a reader's to write, never this code's.
    eye_sheet = None
    make_sheet = p.get("make_eye_sheet") or _eye_sheet_builder(root)
    take_s = last.get("take_dur_s") or (float(row["end_s"]) - float(row["start_s"]))
    try:
        eye_sheet = make_sheet(last["clip"], shot_id, take_s)
    except Exception as exc:              # a sheet that cannot be built is reported
        eye_sheet = None
        attrs["eye_sheet_error"] = "%s: %s" % (type(exc).__name__, exc)
    artifact = {"schema_version": "1.0.0", "artifact_id": "lipsync-" + shot_id,
                "run_id": run_id, "stage": "generation", "kind": "video",
                "path": last["clip"], "sha256": last["sha256"],
                "provenance": {"task_id": last["task_id"],
                               "receipt_path": last["receipt_path"]}}
    return {"shot_id": shot_id, "speaker": row["speaker"],
            "lip_sync_line_ids": list(row["lip_sync_line_ids"]),
            "storyboard_revision": row["storyboard_revision"],
            "start_s": row["start_s"], "end_s": row["end_s"],
            "sung": bool(p["sung"]),
            "image_path": str(image), "image_sha256": _sha_file(image),
            "image_receipt_dir": str(rdir), "image_url": image_url,
            "lineage_path": stem["lineage_path"], "stem_path": stem["path"],
            "stem_sha256": _sha_file(stem["path"]),
            "stem_upload_receipt_path": uploaded["upload_receipt_path"],
            "audio_url": uploaded["url"],
            "clip_path": last["clip"], "clip_sha256": last["sha256"],
            "receipt_path": last["receipt_path"], "task_id": last["task_id"],
            "verdict": gate_row["verdict"], "gate": gate_row,
            # N-113 / G-WIDE-01 / N-118: the eye record the reader wrote (sheet,
            # who looked, verdict, right-voice and emotion results) and the
            # landed close-up facts. Both are REQUIRED for the take to enter the
            # timeline; the chain never invents either.
            "eye_record": _eye_record_with_sheet(
                (p.get("eye_records") or {}).get(shot_id) or gate_row.get("eye_record"),
                eye_sheet),
            # N-113: the whole-frame 4-fps sheet this step built for the take.
            "eye_sheet": eye_sheet,
            "eye_sheet_error": attrs.get("eye_sheet_error"),
            "landed": (p.get("landed_takes") or {}).get(shot_id) or gate_row.get("landed"),
            "emotion_hold": gate_row.get("emotion_hold"),
            # N-118: the line's own tag travels with the row, so the join can
            # refuse a tagged take that never had its Emotion Hold.
            "emotion": row.get("emotion"),
            "emotion_intensity": int(row.get("emotion_intensity") or 2),
            "take_dur_s": last.get("take_dur_s"),
            "artifact": artifact, "face_on_screen": row["speaker"]}


def _eye_record_with_sheet(record, sheet):
    """N-113: the receipt needs the sheet, who looked and the verdict.

    The sheet is a fact this step built; who looked and the verdict are the
    reader's and are never invented here. A reader record that names no sheet
    gets the built one; a take with no reader record stays without one (the
    join refuses LIP_TAKE_NOT_EYE_CHECKED)."""
    if not isinstance(record, dict):
        return record
    if record.get("sheet") or not sheet:
        return record
    return dict(record, sheet=str(sheet))


def _complete(row):
    """A row already paid for and still true: never bought twice."""
    return (isinstance(row, dict) and row.get("verdict") in ACCEPTED
            and row.get("receipt_path") and Path(row["receipt_path"]).is_file()
            and row.get("clip_path") and Path(row["clip_path"]).is_file()
            and row.get("artifact", {}).get("sha256") == _sha_file(row["clip_path"]))


def run(run_dir, run_id=None, *, providers=None):
    """Run the chain for every planned lip-sync clip; returns the envelope."""
    return _run(run_dir, run_id, providers)


def _run(run_dir, run_id, overrides):
    from audio_c3 import lipsync_producer as producer
    from delivery_package.run_inputs import audio_sources
    from lipsync_evidence import LipsyncEvidenceError, _approved
    from lipsync_evidence import _approved_shots, _approved_stills
    try:
        p = _providers(overrides)
        root, required = _approved(run_dir)
        run_id = run_id or _run_id(root)
        p["run_id"] = run_id
        ledger = p["ledger_db"]
        _need(isinstance(ledger, str) and Path(ledger).is_file(),
              "LIPSYNC_LEDGER_MISSING",
              "name this run's spend ledger (--ledger) before any paid job")
        _need(p["stage"] in STAGES, "LIPSYNC_PRODUCTION_STAGE_REQUIRED",
              "name video-generation or qc-retakes, never a substitute")
        wanted = p["shots"]
        planned = [sid for sid in required if not wanted or sid in wanted]
        _need(bool(planned), "LIPSYNC_REQUIREMENTS_MISSING",
              "the approved storyboard has no planned lip-sync clip")
        # F-LIP-3: read either storyboard layout (storyboard/ files or the one
        # storyboard-v3.json); the evidence join uses the same two readers.
        stills = _approved_stills(root)
        gate_doc = root / "storyboard" / "gate.json"
        gate = _read(gate_doc) if gate_doc.is_file() else {}
        shots = _approved_shots(root)
        shots = [dict(s, status="storyboard_approved") for s in shots or []]
        attrs = {"shots": shots, "gate": gate,
                 "card_receipt": producer._approval_context(root, run_id),
                 "stage": p["stage"], "ledger_db": ledger,
                 "adapter_path": p["adapter_path"],
                 "dispatch_runner": p["dispatch_runner"],
                 "dispatch_fn": p["dispatch_fn"],
                 "state_store": p["state_store"],
                 "song_path": str(audio_sources(str(root))["mix"]),
                 "last": None, "estimated_cost": 0}
        evidence_path = root / "control" / "lip-sync" / "evidence.json"
        held_rows = _read(evidence_path).get("rows") if evidence_path.is_file() else []
        held_rows = [r for r in (held_rows or []) if isinstance(r, dict)]
        done = [r for r in held_rows if r.get("shot_id") in planned and _complete(r)]
        planned = [sid for sid in planned
                   if sid not in {r["shot_id"] for r in done}]
        rows = [r for r in held_rows if r.get("shot_id") not in planned]
        if not planned:
            return _envelope("ok", "LIPSYNC_CHAIN_COMPLETE",
                             "every planned lip-sync clip already has its receipt",
                             run_dir=str(root), run_id=run_id,
                             evidence_path=str(evidence_path), rows=len(rows),
                             clips=[r["shot_id"] for r in rows], planned=0)
        if p["budget"]:
            total = sum(float(required[sid]["end_s"]) - float(required[sid]["start_s"])
                        for sid in planned)
            caps = _budget(total, p)
            attrs["estimated_cost"] = max(1, int(round(
                caps["cost_usd"] / max(total, 1e-9) * 100)))
        for sid in planned:
            row = _clip(root, run_id, sid, required[sid], p, stills, attrs)
            _need(row["verdict"] in ACCEPTED, "LIP_SYNC_GATE_FAILED",
                  "%s: %s" % (sid, row["verdict"]))
            rows = [r for r in rows if r.get("shot_id") != sid] + [row]
            _write(evidence_path, {"schema_version": SCHEMA, "tool": TOOL,
                                   "tool_version": VERSION, "run_dir": str(root),
                                   "run_id": run_id,
                                   "created": time.strftime(
                                       "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                   "rows": rows})
        return _envelope("ok", "LIPSYNC_CHAIN_COMPLETE",
                         "every planned lip-sync clip has its receipt",
                         run_dir=str(root), run_id=run_id,
                         evidence_path=str(evidence_path), rows=len(rows),
                         clips=[r["shot_id"] for r in rows],
                         planned=len(planned))
    except LipsyncEvidenceError as exc:
        return _envelope("refused", exc.code, str(exc))
    except ChainError as exc:
        return _envelope("refused", exc.code, str(exc))
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        return _envelope("error", getattr(exc, "code", "LIPSYNC_CHAIN_FAILED"),
                         str(exc))
