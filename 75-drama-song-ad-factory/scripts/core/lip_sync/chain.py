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
  5. ``kie_dispatch``      the paid ``kling/ai-avatar-standard`` job, under the
                           ledger reserve, the card gate, the picture gate and
                           the stem/picture input join.
  6. ``run_gate``          ``lip_gate.run_gate``: the 2-try rule, the attempt
                           ceiling and ``load_governor.kie_request`` pacing.

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

MODEL = "kling/ai-avatar-standard"
TOOL = "lip_sync.run"
SCHEMA = "blackceo.lipsync-run/v1"
VERSION = "1.0.0"
STAGES = ("video-generation", "qc-retakes")
STEPS = ("gate_picture", "upload_measured", "cut_line_from_one_stem",
         "upload_stem", "kie_dispatch", "run_gate")
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
            "make_strip": None, "advisory": None, "person_verdicts": {},
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

    gated = PG.gate_picture(str(image), receipt_dir=str(rdir),
                            measure=p["picture_measure"], no_smile=True)
    _need(gated.get("verdict") in PG.ACCEPTED, "LIPSYNC_PICTURE_NOT_GATED",
          "%s: %s" % (gated.get("verdict"),
                      "; ".join("%s: %s" % tuple(x)
                                for x in gated.get("reasons", []))))
    _need(Path(gated["image"]).resolve() == image, "LIPSYNC_GATED_NOT_APPROVED",
          "the gate kept a different picture (%s); the approved still is the "
          "only lip-sync source (settled by U-U03)" % gated["image"])
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
        _need(provider == "kling", "LIPSYNC_MODEL_MISMATCH",
              "the locked lip-sync model is %s" % MODEL)
        return _dispatch_clip(root, run_id, shot_id, row, image, rdir,
                              image_url, uploaded, spec, attrs)

    prior = len(list((root / "control" / "lip-sync" / "receipts").glob(
        shot_id + "-try*.json")))
    from lip_sync.lip_gate import image_gate
    try:
        gate_row = gate.run_gate(
            shot_id, generate, measure_clip, source_image=str(image),
            image_check=image_check, sung=bool(p["sung"]),
            retry_input=None,
            prior_jobs=prior,
            make_strip=p["make_strip"], advisory=p["advisory"],
            look=p["look"],
            person_verdict=(p["person_verdicts"] or {}).get(shot_id))
    except gate.LipTryLimit as exc:
        raise ChainError(gate.LIP_TRY_LIMIT, str(exc))
    except image_gate.LipsyncImageRefused as exc:
        raise ChainError("LIPSYNC_PICTURE_NOT_GATED", str(exc))
    last = attrs.get("last") or {}
    _need(bool(last.get("receipt_path")), "LIPSYNC_DISPATCH_FAILED",
          "the gate kept no dispatched try for " + shot_id)
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
            "artifact": artifact, "face_on_screen": row["speaker"]}


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
        stills = _read(root / "storyboard" / "stills.json")
        gate_doc = root / "storyboard" / "gate.json"
        gate = _read(gate_doc) if gate_doc.is_file() else {}
        shots = _read(root / "storyboard" / "shot-list.json")
        shots = shots.get("shots") if isinstance(shots, dict) else shots
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
