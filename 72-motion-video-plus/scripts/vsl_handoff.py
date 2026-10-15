"""MG-037: the desktop VSL handoff (Skill 72 side).

The desktop VSL is owned by a parent job (today, a Skill 47 movie
production). The parent owns the narration, the music, the captions,
and the delivery ledger; Skill 72 owns the motion insert that answers
one narration cue inside one fixed slot of the parent's timeline.
This module is the contract between the two sides and the producer
that executes it:

- ``vsl_handoff``: the typed, validated request record (schema:
  references/vsl-handoff-schema.json, this layer's own versioned
  schema; the canonical contracts-v2.schema.json is not edited).
  It names the parent job and task, the parent scene holding the
  slot, the slot's frame range in the PARENT timeline, the
  narration cue the insert answers to (a spoken-word anchor into
  the parent's narration), the proof and copy, the dataset, the
  visual direction, the audio ownership on both sides, and the
  return requirements.

- ``produce``: stages the insert as a normal V2 job package under
  the vsl_desktop mode manifest, validates it through the shipped
  contracts layer (scripts/motion_contracts.py), compiles its
  timeline in slot mode through the shipped MG-021 compiler,
  renders the final through the shipped dispatcher and adapter
  (scripts/vsl-render.mjs), and writes a ``return_package``: the
  approved insert MP4, its poster, hashes, and timing (the
  insert's own compiled timeline plus its placement in the parent
  slot).

- ``assemble-parent``: lands the returned insert in the parent
  VSL through the shipped assembler (scripts/assemble.py, plan
  mode). The parent program (host scenes before and after the
  slot, the insert at the slot, the parent's narration and music)
  is compiled by the same MG-021 compiler in program mode, so
  placement comes from the compiled timeline only. Durations
  entering assembly are the segments' ACTUAL probed durations:
  the assembler refuses a segment shorter than the plan by name
  instead of trimming or stretching anything.

Timing doctrine (directive Sections 5.4, 16 and 17): the slot is
fixed. The insert's duration must equal the slot length exactly;
the cue's frame must be the slot's first frame. A handoff that is
missing its slot timing, whose insert is longer or shorter than
its slot, whose cue does not land on the slot start, or that
carries its own narration into a parent-owned-narration slot
fails BY NAME before anything renders. Nothing in this module
estimates a duration, resizes a slot, changes a speed, or mixes
audio: the insert contributes no audio, and the assembled VSL's
audio is the parent's, resolved exactly once by the MG-023 audio
policy inside the assembler.

Failure discipline: every failure is a HandoffError carrying a
stable code, a Section 16.9 category, and the matching exit class
(2 contract/timeline, 3 input, 4 approval, 5 render, 6 QC,
9 foreign/hash). The CLI prints one JSON document on stdout on
success and one JSON error document on stderr on failure; it never
prints a bare PASS.

CLI:
    python3 scripts/vsl_handoff.py validate HANDOFF.json
    python3 scripts/vsl_handoff.py produce HANDOFF.json --work DIR
    python3 scripts/vsl_handoff.py assemble-parent HANDOFF.json \
        --return-dir DIR --media-spec SPEC.json --out FINAL.mp4 \
        --work DIR
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

SCRIPTS_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import audio_policy  # noqa: E402  (MG-023: the one audio resolution layer)
import motion_contracts  # noqa: E402  (MG-007: the contracts layer)

SCHEMA_PATH = SKILL_ROOT / "references" / "vsl-handoff-schema.json"
FIXTURE_MODE_DIR = SKILL_ROOT / "tests" / "fixtures" / "modes" / "vsl_desktop"

EXIT_OK = 0
EXIT_INTERNAL = 1
EXIT_CONTRACT = 2
EXIT_INPUT = 3
EXIT_APPROVAL = 4
EXIT_RENDER = 5
EXIT_QC = 6
EXIT_CANCELLED = 8
EXIT_FOREIGN = 9

SAMPLE_RATE = 48000


class HandoffError(Exception):
    """A named, categorized failure. ``code`` is the stable name a
    caller (or a test) matches on; ``mg_category`` and ``exit_code``
    follow directive Section 16.9."""

    def __init__(self, code, message, mg_category="MG_SCHEMA_INVALID",
                 exit_code=EXIT_CONTRACT):
        super().__init__(message)
        self.code = code
        self.message = message
        self.mg_category = mg_category
        self.exit_code = exit_code

    def document(self):
        return {"status": "FAILED", "code": self.code,
                "mg_category": self.mg_category,
                "exit_code": self.exit_code, "message": self.message}


# --------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------

def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, doc) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return path


def load_json(path, what):
    path = Path(path)
    if not path.is_file():
        raise HandoffError(
            "VSL_HANDOFF_INPUT_MISSING",
            "%s not found: %s" % (what, path),
            mg_category="MG_INPUT_MISSING", exit_code=EXIT_INPUT)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HandoffError(
            "VSL_HANDOFF_INPUT_INVALID",
            "%s is not parseable JSON: %s" % (what, exc),
            mg_category="MG_SCHEMA_INVALID", exit_code=EXIT_CONTRACT)


_SCHEMA_CACHE = None


def _validator_for(def_name: str) -> Draft202012Validator:
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        _SCHEMA_CACHE = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    schema = _SCHEMA_CACHE
    if def_name not in schema.get("$defs", {}):
        raise KeyError("unknown handoff contract definition: %s" % def_name)
    wrapper = {"$schema": schema["$schema"],
               "$ref": "#/$defs/%s" % def_name, "$defs": schema["$defs"]}
    return Draft202012Validator(wrapper)


def _schema_findings(doc, def_name: str) -> list:
    validator = _validator_for(def_name)
    errors = sorted(validator.iter_errors(doc),
                    key=lambda e: ("/".join(str(p) for p in e.absolute_path),
                                   e.message))
    return [{"path": "/" + "/".join(str(p) for p in e.absolute_path),
             "message": e.message} for e in errors]


def _require_schema(doc, def_name: str, code: str):
    findings = _schema_findings(doc, def_name)
    if findings:
        first = findings[0]
        raise HandoffError(
            code,
            "%s fails %s schema at %s: %s (%d finding(s))"
            % (def_name, def_name, first["path"] or "/", first["message"],
               len(findings)),
            mg_category="MG_SCHEMA_INVALID", exit_code=EXIT_CONTRACT)


# --------------------------------------------------------------------
# Handoff validation: the named agreements first, then the schema.
#
# The order is the contract. A missing slot, a mismatched cue, a
# wrong-length insert, and an audio-ownership violation are each
# refused with their own name before generic shape findings are
# considered, because those four are the failures a parent job can
# actually act on.
# --------------------------------------------------------------------

def validate_handoff(doc) -> None:
    """Raise HandoffError on the first violated agreement."""
    if not isinstance(doc, dict):
        raise HandoffError(
            "VSL_HANDOFF_SCHEMA_INVALID",
            "handoff document is not a JSON object",
            mg_category="MG_SCHEMA_INVALID", exit_code=EXIT_CONTRACT)

    parent = doc.get("parent") if isinstance(doc.get("parent"), dict) else {}
    slot = parent.get("slot")
    if not isinstance(slot, dict) \
            or not isinstance(slot.get("start_frame"), int) \
            or not isinstance(slot.get("end_frame_exclusive"), int):
        raise HandoffError(
            "VSL_HANDOFF_SLOT_TIMING_MISSING",
            "the handoff names no slot timing: parent.slot must carry "
            "start_frame and end_frame_exclusive in the parent timeline; "
            "a fixed-duration insert is never placed by estimating a "
            "duration the parent did not declare",
            mg_category="MG_TIMELINE_INVALID", exit_code=EXIT_CONTRACT)
    if slot["end_frame_exclusive"] <= slot["start_frame"]:
        raise HandoffError(
            "VSL_HANDOFF_SLOT_RANGE_INVALID",
            "parent slot [%d, %d) is empty or reversed"
            % (slot["start_frame"], slot["end_frame_exclusive"]),
            mg_category="MG_TIMELINE_INVALID", exit_code=EXIT_CONTRACT)
    slot_len = slot["end_frame_exclusive"] - slot["start_frame"]

    cue = parent.get("narration_cue")
    if not isinstance(cue, dict) or not isinstance(cue.get("frame"), int) \
            or not cue.get("id") or not cue.get("segment_id"):
        raise HandoffError(
            "VSL_HANDOFF_CUE_MISSING",
            "the handoff names no narration cue: parent.narration_cue "
            "must carry the cue id, the parent narration segment it "
            "anchors into, the word index, and the cue frame",
            mg_category="MG_TIMELINE_INVALID", exit_code=EXIT_CONTRACT)
    if cue["frame"] != slot["start_frame"]:
        raise HandoffError(
            "VSL_HANDOFF_CUE_FRAME_MISMATCH",
            "narration cue %r is at parent frame %d but the slot "
            "starts at frame %d; the insert's first frame must land "
            "on the cue's frame, so the two must agree in the handoff"
            % (cue.get("id"), cue["frame"], slot["start_frame"]),
            mg_category="MG_TIMELINE_INVALID", exit_code=EXIT_CONTRACT)

    insert = doc.get("insert") if isinstance(doc.get("insert"), dict) else {}
    duration = insert.get("duration_frames")
    if isinstance(duration, int):
        if duration > slot_len:
            raise HandoffError(
                "VSL_HANDOFF_INSERT_EXCEEDS_SLOT",
                "insert duration %d frames exceeds its parent slot of "
                "%d frames; the slot is never resized and the parent "
                "narration is never shortened to fit an insert"
                % (duration, slot_len),
                mg_category="MG_TIMELINE_INVALID", exit_code=EXIT_CONTRACT)
        if duration < slot_len:
            raise HandoffError(
                "VSL_HANDOFF_INSERT_UNDERFILLS_SLOT",
                "insert duration %d frames underfills its parent slot "
                "of %d frames; a slot-mode insert must equal the slot "
                "length exactly" % (duration, slot_len),
                mg_category="MG_TIMELINE_INVALID", exit_code=EXIT_CONTRACT)

    audio = doc.get("audio_ownership") \
        if isinstance(doc.get("audio_ownership"), dict) else {}
    if audio.get("narration") is not None and audio.get("narration") != "parent":
        raise HandoffError(
            "VSL_HANDOFF_AUDIO_OWNERSHIP_VIOLATION",
            "audio_ownership.narration is %r; in vsl_desktop the "
            "parent owns narration and the insert is rendered silent "
            "under inherited audio" % (audio.get("narration"),),
            mg_category="MG_MODE_MISMATCH", exit_code=EXIT_CONTRACT)
    if insert.get("narration_assets"):
        raise HandoffError(
            "VSL_HANDOFF_AUDIO_OWNERSHIP_VIOLATION",
            "the insert declares %d narration asset(s) into a "
            "parent-owned-narration slot; an insert carrying its own "
            "narration would double the parent's voice and is refused"
            % len(insert["narration_assets"]),
            mg_category="MG_MODE_MISMATCH", exit_code=EXIT_CONTRACT)
    if audio.get("insert_sound") == "declared":
        raise HandoffError(
            "VSL_HANDOFF_AUDIO_OWNERSHIP_VIOLATION",
            "audio_ownership.insert_sound is 'declared'; the "
            "vsl_desktop mode manifest pins the insert's audio to "
            "inherited with no source assets, so insert sound is "
            "not declarable in this mode",
            mg_category="MG_MODE_MISMATCH", exit_code=EXIT_CONTRACT)

    _require_schema(doc, "vsl_handoff", "VSL_HANDOFF_SCHEMA_INVALID")


def validate_return_package(doc) -> None:
    _require_schema(doc, "return_package", "VSL_RETURN_PACKAGE_INVALID")


def verify_return_hashes(doc, return_dir) -> None:
    """Recompute the returned artifacts' hashes against the record."""
    return_dir = Path(return_dir)
    for key in ("mp4", "poster"):
        rec = doc.get("artifacts", {}).get(key)
        if rec is None:
            continue
        path = return_dir / rec["path"]
        if not path.is_file():
            raise HandoffError(
                "VSL_RETURN_ARTIFACT_MISSING",
                "return package names %s at %s but the file is absent"
                % (key, path),
                mg_category="MG_INPUT_MISSING", exit_code=EXIT_INPUT)
        actual = sha256_file(path)
        if actual != rec["sha256"]:
            raise HandoffError(
                "VSL_RETURN_HASH_MISMATCH",
                "%s hash mismatch: the record claims %s, the file "
                "measures %s" % (key, rec["sha256"], actual),
                mg_category="MG_HASH_MISMATCH", exit_code=EXIT_FOREIGN)


# --------------------------------------------------------------------
# Insert package staging: the handoff fully determines the job.
# --------------------------------------------------------------------

def _num(value):
    """Format a dataset value the way fixture copy writes it."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _resolve_design(handoff) -> dict:
    ref = (handoff.get("insert") or {}).get("design_ref", "fixture-editorial")
    if isinstance(ref, dict):
        return ref
    if ref == "fixture-editorial":
        return load_json(FIXTURE_MODE_DIR / "design.json", "fixture design")
    raise HandoffError(
        "VSL_HANDOFF_DESIGN_UNRESOLVED",
        "design_ref %r does not resolve; the only registered design "
        "reference is 'fixture-editorial', or an inline design object"
        % (ref,),
        mg_category="MG_INPUT_MISSING", exit_code=EXIT_INPUT)


def stage_insert_package(handoff, pkg_dir) -> dict:
    """Write the V2 job package the handoff describes.

    Returns a dict of the written paths. The package is a normal
    vsl_desktop job: manifest, storyboard, one C05 scene spec, the
    dataset, the design, the authoring timeline, and the canonical
    parent-handoff.json the contracts layer validates.
    """
    parent = handoff["parent"]
    insert = handoff["insert"]
    req = handoff["return_requirements"]
    slot = parent["slot"]
    cue = parent["narration_cue"]
    duration = insert["duration_frames"]
    motion = insert.get("motion") or {
        "start_frame": 15,
        "end_frame_exclusive": 75,
        "hold_to_frame_exclusive": duration,
    }
    design = _resolve_design(handoff)
    layout = design["layouts"]["landscape"]
    plot_width = layout["plot"]["width"]
    dataset = insert["dataset"]
    d0, d1 = dataset["domain"]
    span = d1 - d0
    if span <= 0:
        raise HandoffError(
            "VSL_HANDOFF_SCHEMA_INVALID",
            "dataset domain %r is not increasing" % (dataset["domain"],),
            mg_category="MG_SCHEMA_INVALID", exit_code=EXIT_CONTRACT)

    def final_width(row):
        return plot_width * (row["value"] - d0) / span

    mid_frame = (motion["start_frame"] + motion["end_frame_exclusive"]) // 2
    subject_ids = ["bar-%s" % row["id"] for row in dataset["rows"]]
    scene = {
        "schema_version": "2.0",
        "id": insert["scene_id"],
        "component_id": insert["component_id"],
        "component_version": insert["component_version"],
        "engine": "remotion",
        "layout_variant": "landscape",
        "duration_frames": duration,
        "asset_ids": [],
        "data_path": "data/%s.json" % dataset["id"],
        "design_path": "design.json",
        "copy": {"headline": insert["copy"]["headline"],
                 "disclosure": insert["copy"].get("disclosure")},
        "motion": {"kind": "linear_bar_reveal",
                   "start_frame": motion["start_frame"],
                   "end_frame_exclusive": motion["end_frame_exclusive"],
                   "hold_to_frame_exclusive": motion["hold_to_frame_exclusive"],
                   "overshoot_data": False},
        "semantic_motion_assertions": [
            {"id": "half-reveal", "kind": "bar_widths",
             "subject_ids": subject_ids, "frame": mid_frame,
             "expected_values": [round(final_width(r) / 2.0, 4)
                                 for r in dataset["rows"]],
             "tolerance": 1, "unit": "source_px",
             "evidence": ["geometry", "decoded_frame", "full_fps_clip"]},
            {"id": "final-ratios", "kind": "bar_widths",
             "subject_ids": subject_ids,
             "frame": motion["end_frame_exclusive"],
             "expected_values": [round(final_width(r), 4)
                                 for r in dataset["rows"]],
             "tolerance": 1, "unit": "source_px",
             "evidence": ["geometry", "decoded_frame"]},
        ],
    }

    manifest = {
        "schema_version": "2.0",
        "job_id": insert["job_id"],
        "company_id": parent["company_id"],
        "execution_context": "fixture",
        "parent": {"job_id": parent["job_id"], "task_id": parent["task_id"],
                   "handoff_path": "parent-handoff.json",
                   "slot": {"start_frame": slot["start_frame"],
                            "end_frame_exclusive": slot["end_frame_exclusive"]},
                   "narration_cue_id": cue["id"]},
        "mode": "vsl_desktop",
        "content_scope": "insert",
        "canvas": {"width": parent["canvas"]["width"],
                   "height": parent["canvas"]["height"],
                   "fps": parent["fps"]},
        "duration_frames": duration,
        "authoring": {"selection": "inherit_config", "provider": None,
                      "model": None, "harness": None},
        "rendering": {"default_engine": "remotion",
                      "allow_legacy_fallback": False,
                      "runtime_lock": "runtime-lock.json"},
        "storyboard": "storyboard.json",
        "assets": "assets.json",
        "design": "design.json",
        "timeline": "timeline.json",
        "audio": {"mode": "inherited",
                  "parent_audio_ref": parent["audio_ref"],
                  "create_voiceover": False, "create_music": False,
                  "source_assets": []},
        "approval_policy": "fixture_only",
        "variants": [],
        "scenes": [{"id": insert["scene_id"],
                    "spec": "scenes/%s.json" % insert["scene_id"]}],
        "delivery": {"video_profile": "h264_opaque",
                     "poster_frame": req["poster_frame"],
                     "placement": "full_frame",
                     "playback": {"start": "automatic", "repeat": "once",
                                  "end": "hold_final"},
                     "required": list(req["artifacts"])},
    }

    storyboard = {
        "schema_version": "2.0",
        "id": "story-%s" % insert["scene_id"],
        "beats": [{
            "id": "beat-%s" % insert["scene_id"],
            "scene_id": insert["scene_id"],
            "job": insert["copy"]["headline"],
            "viewer_question": "How do the quantities compare?",
            "intended_understanding":
                "The bars compare on one shared zero-based scale.",
            "visual_verb": "compare",
            "subject_ids": subject_ids,
            "representation": "chart",
            "explanatory": True,
            "initial_state": "Labeled marks begin at zero on a shared scale.",
            "transformation":
                "The bar widths increase together on one linear progress clock.",
            "proof_state": "Widths equal the declared values on the shared domain.",
            "final_state": "Marks, values and labels hold still for reading.",
            "asset_ids": [],
            "data_ids": [dataset["id"]],
            "essential_text": [insert["copy"]["headline"]]
                + [row["label"] for row in dataset["rows"]]
                + [_num(row["value"]) for row in dataset["rows"]]
                + ([insert["copy"]["disclosure"]]
                   if insert["copy"].get("disclosure") else []),
            "proof_frames": [motion["start_frame"], mid_frame,
                             motion["end_frame_exclusive"], duration - 1],
            "typography_only_exception": None,
        }],
    }

    assets = load_json(FIXTURE_MODE_DIR / "assets.json", "fixture assets")

    # The canonical parent-handoff.json is the contracts layer's
    # file. Its narration_cue.kind is pinned by the canonical
    # schema to the fixture timing-marker constant; the handoff
    # record itself carries the full spoken-word anchor (segment
    # and word index), which the parent program compile consumes.
    # The mapping is documented in references/vsl-desktop-handoff.md.
    parent_handoff = {
        "schema_version": "2.0",
        "parent_job_id": parent["job_id"],
        "parent_task_id": parent["task_id"],
        "company_id": parent["company_id"],
        "fps": parent["fps"],
        "slot": {"start_frame": slot["start_frame"],
                 "end_frame_exclusive": slot["end_frame_exclusive"]},
        "canvas": {"width": parent["canvas"]["width"],
                   "height": parent["canvas"]["height"],
                   "fps": parent["fps"]},
        "narration_cue": {"id": cue["id"], "frame": cue["frame"],
                          "kind": "fixture_timing_marker_not_real_speech"},
        "audio_owner": "parent",
        "allow_speed_change": False,
        "allow_slot_resize": False,
    }

    timeline = {
        "schema_version": "2.0",
        "job_id": insert["job_id"],
        "fps": parent["fps"],
        "total_frames": duration,
        "scenes": [{"id": insert["scene_id"], "start_frame": 0,
                    "end_frame_exclusive": duration, "source_start_frame": 0,
                    "transition_in_frames": 0, "transition_out_frames": 0}],
        "events": [
            {"id": "reveal-start", "scene_id": insert["scene_id"],
             "frame": motion["start_frame"], "type": "reveal_start"},
            {"id": "final-proof", "scene_id": insert["scene_id"],
             "frame": motion["end_frame_exclusive"], "type": "proof"},
            {"id": "final-hold", "scene_id": insert["scene_id"],
             "frame": motion["end_frame_exclusive"], "type": "hold_start"},
        ],
        "parent_slot": {"start_frame": slot["start_frame"],
                        "end_frame_exclusive": slot["end_frame_exclusive"]},
        "audio_owner": "parent",
    }

    dataset_doc = {"schema_version": "2.0", "id": dataset["id"],
                   "kind": dataset["kind"],
                   "source_note": dataset["source_note"],
                   "units": dataset["units"],
                   "domain": dataset["domain"], "rows": dataset["rows"]}

    pkg_dir = Path(pkg_dir)
    written = {}
    written["manifest"] = write_json(pkg_dir / "manifest.json", manifest)
    written["storyboard"] = write_json(pkg_dir / "storyboard.json", storyboard)
    written["assets"] = write_json(pkg_dir / "assets.json", assets)
    written["design"] = write_json(pkg_dir / "design.json", design)
    written["scene"] = write_json(
        pkg_dir / "scenes" / ("%s.json" % insert["scene_id"]), scene)
    written["dataset"] = write_json(
        pkg_dir / "data" / ("%s.json" % dataset["id"]), dataset_doc)
    written["parent_handoff"] = write_json(
        pkg_dir / "parent-handoff.json", parent_handoff)
    written["timeline"] = write_json(pkg_dir / "timeline.json", timeline)
    return written


# --------------------------------------------------------------------
# Node drivers: the shipped compiler and dispatcher, never rewrites.
# --------------------------------------------------------------------

def _run_driver(script_name, args, what):
    script = SCRIPTS_DIR / script_name
    proc = subprocess.run(["node", str(script)] + list(args),
                          capture_output=True, text=True)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise HandoffError(
            "VSL_HANDOFF_DRIVER_FAILED",
            "%s failed (exit %d): %s" % (what, proc.returncode, detail[-1200:]),
            mg_category="MG_RENDER_FAILED", exit_code=EXIT_RENDER)
    try:
        return json.loads(proc.stdout)
    except ValueError:
        raise HandoffError(
            "VSL_HANDOFF_DRIVER_FAILED",
            "%s printed no JSON document: %s" % (what, proc.stdout[-400:]),
            mg_category="MG_RENDER_FAILED", exit_code=EXIT_RENDER)


def compile_timeline(input_doc, work_dir, name):
    """Compile one timeline through the shipped MG-021 compiler.

    Returns the combined {timeline, sidecar} document. Compiler
    findings are refused verbatim (MG_TIMELINE_INVALID, exit 2):
    a plan that does not fit is a failed plan, never an adjusted
    one."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    input_path = write_json(work_dir / ("%s-input.json" % name), input_doc)
    out_path = work_dir / ("%s-plan.json" % name)
    proc = subprocess.run(
        ["node", str(SCRIPTS_DIR / "vsl-compile.mjs"),
         "--input", str(input_path), "--out", str(out_path)],
        capture_output=True, text=True)
    if proc.returncode != 0:
        try:
            doc = json.loads(proc.stdout)
            findings = doc.get("findings") or []
        except ValueError:
            findings = []
        if findings:
            first = findings[0]
            raise HandoffError(
                "VSL_HANDOFF_TIMELINE_INVALID",
                "timeline compile refused the plan: %s at %s: %s"
                % (first.get("category"), first.get("path"),
                   first.get("message")),
                mg_category=first.get("category", "MG_TIMELINE_INVALID"),
                exit_code=EXIT_CONTRACT)
        raise HandoffError(
            "VSL_HANDOFF_DRIVER_FAILED",
            "timeline compile driver failed (exit %d): %s"
            % (proc.returncode, (proc.stderr or "")[-800:]),
            mg_category="MG_RENDER_FAILED", exit_code=EXIT_RENDER)
    return load_json(out_path, "compiled plan")


# --------------------------------------------------------------------
# Produce: stage, validate, compile, render, and package the return.
# --------------------------------------------------------------------

def produce(handoff_path, work_dir) -> dict:
    handoff = load_json(handoff_path, "handoff")
    validate_handoff(handoff)
    parent = handoff["parent"]
    insert = handoff["insert"]
    req = handoff["return_requirements"]
    slot = parent["slot"]
    motion = insert.get("motion") or {
        "start_frame": 15, "end_frame_exclusive": 75,
        "hold_to_frame_exclusive": insert["duration_frames"]}

    work_dir = Path(work_dir)
    pkg_dir = work_dir / "insert-job"
    stage_insert_package(handoff, pkg_dir)

    findings = motion_contracts.validate_job(pkg_dir)
    if findings:
        first = findings[0]
        raise HandoffError(
            "VSL_HANDOFF_JOB_INVALID",
            "the staged insert job fails the contracts layer: %s at "
            "%s: %s (%d finding(s))"
            % (first["category"], first["path"], first["message"],
               len(findings)),
            mg_category=first["category"], exit_code=EXIT_CONTRACT)

    insert_input = {
        "jobId": insert["job_id"], "fps": parent["fps"], "mode": "slot",
        "audioOwner": "parent",
        "parentSlot": {
            "range": {"startFrame": slot["start_frame"],
                      "endFrameExclusive": slot["end_frame_exclusive"]},
            "grantedHandles": {"headFrames": 0, "tailFrames": 0}},
        "scenes": [{"id": insert["scene_id"],
                    "durationFrames": insert["duration_frames"]}],
        "cues": [
            {"id": "reveal-start", "sceneId": insert["scene_id"],
             "type": "reveal_start",
             "anchor": {"kind": "semantic_state", "state": "reveal_start",
                        "sceneLocalFrame": motion["start_frame"]}},
            {"id": "final-proof", "sceneId": insert["scene_id"],
             "type": "proof",
             "anchor": {"kind": "semantic_state", "state": "final_proof",
                        "sceneLocalFrame": motion["end_frame_exclusive"]}},
            {"id": "final-hold", "sceneId": insert["scene_id"],
             "type": "hold_start",
             "anchor": {"kind": "semantic_state", "state": "final_hold",
                        "sceneLocalFrame": motion["end_frame_exclusive"]}},
        ],
    }
    compiled = compile_timeline(insert_input, work_dir / "compile", "insert")
    write_json(pkg_dir / "plan.json", compiled)
    write_json(pkg_dir / "compiled-timeline.json", compiled["timeline"])
    write_json(pkg_dir / "timeline-sidecar.json", compiled["sidecar"])

    approval = {
        "schema_version": "2.0",
        "approval_id": "%s-delivery" % handoff["handoff_id"],
        "job_id": insert["job_id"],
        "company_id": parent["company_id"],
        "scope": "delivery",
        "decision": "approved",
        "subject_revision": "fixture",
        "artifact_refs": [],
        "actor_id": "mg037-vsl-producer",
        "source_event_ref": handoff["handoff_id"],
        # Fixture-context approval for a fixture_only job, the same
        # convention the shipped render suites use: the record says
        # plainly that its authority is not verified.
        "authority_status": "not_verified",
    }
    approval_path = write_json(
        work_dir / "approvals" / "delivery-approval.json", approval)

    evidence = _run_driver(
        "vsl-render.mjs",
        ["--job-dir", str(pkg_dir), "--out-dir", str(work_dir / "render"),
         "--approval", str(approval_path)],
        "insert render")
    mp4_src = Path(evidence["mp4"])
    poster_src = Path(evidence["poster"]) if evidence.get("poster") else None
    if "mp4" in req["artifacts"] and not mp4_src.is_file():
        raise HandoffError(
            "VSL_HANDOFF_RENDER_INCOMPLETE",
            "the render produced no MP4 at %s" % mp4_src,
            mg_category="MG_RENDER_FAILED", exit_code=EXIT_RENDER)
    if "poster" in req["artifacts"] and (poster_src is None
                                         or not poster_src.is_file()):
        raise HandoffError(
            "VSL_HANDOFF_RENDER_INCOMPLETE",
            "the render produced no poster, but the return "
            "requirements name one",
            mg_category="MG_RENDER_FAILED", exit_code=EXIT_RENDER)

    return_dir = work_dir / "return"
    return_dir.mkdir(parents=True, exist_ok=True)
    mp4_dst = return_dir / "insert.mp4"
    shutil.copyfile(mp4_src, mp4_dst)
    artifacts = {
        "mp4": {"path": "insert.mp4", "sha256": sha256_file(mp4_dst),
                "bytes": mp4_dst.stat().st_size},
        "source_package": {"path": str(pkg_dir)},
    }
    if poster_src is not None and poster_src.is_file():
        poster_dst = return_dir / "poster.png"
        shutil.copyfile(poster_src, poster_dst)
        artifacts["poster"] = {
            "path": "poster.png", "sha256": sha256_file(poster_dst),
            "bytes": poster_dst.stat().st_size,
            "frame": req["poster_frame"]}
    shutil.copyfile(pkg_dir / "compiled-timeline.json",
                    return_dir / "compiled-timeline.json")
    shutil.copyfile(pkg_dir / "timeline-sidecar.json",
                    return_dir / "timeline-sidecar.json")

    doc = {
        "schema_version": "1.0",
        "handoff_id": handoff["handoff_id"],
        "insert_job_id": insert["job_id"],
        "parent_job_id": parent["job_id"],
        "engine": evidence.get("engine") or "remotion",
        "component_id": insert["component_id"],
        "artifacts": artifacts,
        "timing": {
            "slot": {"start_frame": slot["start_frame"],
                     "end_frame_exclusive": slot["end_frame_exclusive"]},
            "cue_id": parent["narration_cue"]["id"],
            "cue_frame": parent["narration_cue"]["frame"],
            "insert_duration_frames": insert["duration_frames"],
            "placed_start_frame": slot["start_frame"],
            "placed_end_frame_exclusive": slot["end_frame_exclusive"],
            "compiled_timeline_path": "compiled-timeline.json",
            "sidecar_path": "timeline-sidecar.json",
        },
        "approval": {"approval_id": approval["approval_id"],
                     "scope": "delivery", "decision": "approved",
                     "authority_status": "not_verified",
                     "execution_context": "fixture"},
        "proof": {"motion_proof_verdict": None, "qc_report_path": None},
    }
    validate_return_package(doc)
    write_json(return_dir / "return-package.json", doc)
    return {"return_package": doc, "return_dir": str(return_dir),
            "job_dir": str(pkg_dir),
            "render_evidence": evidence}


# --------------------------------------------------------------------
# Parent assembly: the insert lands in the parent's program.
# --------------------------------------------------------------------

def build_parent_plan(handoff, return_doc, return_dir, media_spec, plan_dir):
    """Compile the parent program and write plan + media registry.

    The program is the parent's own timeline: host scenes around
    the slot, the insert at the slot, the parent's narration (with
    word timings), the parent's captions, and the placement cue
    anchored to the exact spoken word the handoff names. Returns
    (plan_path, media_path, compiled)."""
    parent = handoff["parent"]
    insert = handoff["insert"]
    slot = parent["slot"]
    cue = parent["narration_cue"]
    return_dir = Path(return_dir)

    scenes_in = media_spec["scenes"]
    compile_scenes = []
    media_scenes = []
    for entry in scenes_in:
        if entry.get("use_return_artifact"):
            duration = insert["duration_frames"]
            path = str(return_dir / return_doc["artifacts"]["mp4"]["path"])
            engine = return_doc["engine"]
            scene_id = insert["scene_id"]
        else:
            duration = entry["duration_frames"]
            path = entry["path"]
            engine = entry.get("engine")
            scene_id = entry["id"]
        compile_scenes.append({"id": scene_id, "durationFrames": duration})
        media_scenes.append({"id": scene_id, "path": path, "engine": engine})

    narration_in = media_spec.get("narration") or []
    compile_narration = []
    media_narration = []
    for seg in narration_in:
        entry = {"id": seg["id"], "startFrame": seg["start_frame"],
                 "endFrameExclusive": seg["end_frame_exclusive"]}
        if seg.get("words"):
            entry["words"] = seg["words"]
        compile_narration.append(entry)
        media_narration.append({"id": seg["id"], "path": seg["path"]})

    captions_in = media_spec.get("captions") or []
    compile_captions = [{"id": c["id"], "startFrame": c["start_frame"],
                         "endFrameExclusive": c["end_frame_exclusive"]}
                        for c in captions_in]

    program_input = {
        "jobId": parent["job_id"], "fps": parent["fps"], "mode": "program",
        "audioOwner": "self",
        "scenes": compile_scenes,
        "narration": compile_narration,
        "captions": compile_captions,
        "cues": [{
            "id": cue["id"], "sceneId": insert["scene_id"], "type": "cue",
            "anchor": {"kind": "spoken_word", "segmentId": cue["segment_id"],
                       "wordIndex": cue["word_index"]},
        }],
    }
    compiled = compile_timeline(program_input, plan_dir, "parent")

    plan_path = write_json(Path(plan_dir) / "plan.json", compiled)
    media = {
        "canvas": media_spec["canvas"],
        "scenes": media_scenes,
        "narration": media_narration,
        "audio": {"musicVolume": float(
                      (media_spec.get("mix") or {}).get("musicVolume", 0.5)),
                  "ducking": (media_spec.get("mix") or {}).get("ducking"),
                  "loudnessTarget": media_spec.get(
                      "loudness_target") or dict(
                          audio_policy.DEFAULT_LOUDNESS_TARGET)},
        "syntheticSegments": bool(media_spec.get("synthetic_segments")),
    }
    if media_spec.get("music"):
        media["music"] = {"path": media_spec["music"]["path"]}
    media_path = write_json(Path(plan_dir) / "media.json", media)
    return plan_path, media_path, compiled


def _ffprobe_streams(path):
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json",
         str(path)], capture_output=True, text=True)
    if proc.returncode != 0:
        raise HandoffError(
            "VSL_HANDOFF_INPUT_INVALID",
            "ffprobe failed on %s: %s" % (path, proc.stderr[-400:]),
            mg_category="MG_INPUT_MISSING", exit_code=EXIT_INPUT)
    return json.loads(proc.stdout).get("streams") or []


def _frame_rgb(path, frame, width, height):
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path),
         "-vf", "select='eq(n\\,%d)'" % frame, "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True)
    if proc.returncode != 0 or len(proc.stdout) != width * height * 3:
        raise HandoffError(
            "VSL_HANDOFF_MEASUREMENT_FAILED",
            "could not decode frame %d of %s" % (frame, path),
            mg_category="MG_QC_FAILED", exit_code=EXIT_QC)
    return proc.stdout


def _bar_widths(rgb, width, layout, accent=(0xC0, 0x4A, 0x26), tol=28):
    """Measure accent bar widths on one decoded frame: for each
    row, the rightmost accent pixel inside the plot span, relative
    to the plot origin. An independent Python implementation of
    the same landmark the runtime's decoded measurement uses."""
    plot = layout["plot"]
    widths = []
    for row_y in layout["row_y"]:
        y = row_y + layout["bar_height"] // 2
        base = y * width * 3
        last = -1
        for x in range(plot["x"], plot["x"] + plot["width"]):
            i = base + x * 3
            if (abs(rgb[i] - accent[0]) <= tol
                    and abs(rgb[i + 1] - accent[1]) <= tol
                    and abs(rgb[i + 2] - accent[2]) <= tol):
                last = x
        widths.append(0 if last < 0 else last - plot["x"] + 1)
    return widths


def _mean_abs_diff(a: bytes, b: bytes) -> float:
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    total = 0
    step = 97  # sample every 97th byte: a stable content statistic
    count = 0
    for i in range(0, n, step):
        total += abs(a[i] - b[i])
        count += 1
    return total / max(count, 1)


def assemble_parent(handoff_path, return_dir, media_spec_path,
                    out_path, work_dir) -> dict:
    handoff = load_json(handoff_path, "handoff")
    validate_handoff(handoff)
    parent = handoff["parent"]
    insert = handoff["insert"]
    slot = parent["slot"]
    cue = parent["narration_cue"]
    return_dir = Path(return_dir)
    return_doc = load_json(return_dir / "return-package.json",
                           "return package")
    validate_return_package(return_doc)
    if return_doc["handoff_id"] != handoff["handoff_id"] \
            or return_doc["parent_job_id"] != parent["job_id"]:
        raise HandoffError(
            "VSL_RETURN_FOREIGN_HANDOFF",
            "return package answers handoff %r for parent %r, not "
            "handoff %r for parent %r"
            % (return_doc["handoff_id"], return_doc["parent_job_id"],
               handoff["handoff_id"], parent["job_id"]),
            mg_category="MG_FOREIGN_JOB", exit_code=EXIT_FOREIGN)
    verify_return_hashes(return_doc, return_dir)
    media_spec = load_json(media_spec_path, "parent media spec")

    work_dir = Path(work_dir)
    plan_path, media_path, compiled = build_parent_plan(
        handoff, return_doc, return_dir, media_spec, work_dir / "plan")
    sidecar = compiled["sidecar"]
    timeline = compiled["timeline"]

    # The insert's designed final hold is a plan-side fact (the
    # handoff's motion window, confirmed by the insert's compiled
    # timeline): declare it in the assembly workdir so the QC
    # gate's intent-aware freeze check reads the approval from
    # plan data, never from the artifact.
    motion = insert.get("motion") or {
        "start_frame": 15, "end_frame_exclusive": 75,
        "hold_to_frame_exclusive": insert["duration_frames"]}
    if motion["hold_to_frame_exclusive"] > motion["end_frame_exclusive"]:
        write_json(work_dir / "qc-approved-intervals.json", {
            "intervals": [{
                "start_frame": slot["start_frame"]
                    + motion["end_frame_exclusive"],
                "end_frame_exclusive": slot["start_frame"]
                    + motion["hold_to_frame_exclusive"],
                "kinds": ["freeze"],
                "reason": "the insert's designed final hold: the "
                          "component's reveal ends at insert-local "
                          "frame %d and holds to frame %d for "
                          "reading" % (motion["end_frame_exclusive"],
                                       motion["hold_to_frame_exclusive"]),
                "source": "vsl handoff motion window; insert "
                          "compiled timeline final-hold event",
            }]})

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "assemble.py"),
         "--plan", str(plan_path), "--media", str(media_path),
         "--out", str(out_path), "--workdir", str(work_dir / "assemble")],
        capture_output=True, text=True)
    if proc.returncode != 0:
        code = "VSL_HANDOFF_ASSEMBLY_FAILED"
        category = "MG_QC_FAILED"
        message = (proc.stderr or proc.stdout or "")[-1200:]
        try:
            finding = json.loads(proc.stderr)
            code = finding.get("code", code)
            category = finding.get("mg_category", category)
            message = finding.get("message", message)
        except ValueError:
            pass
        raise HandoffError(code, "the shipped assembler refused the "
                           "parent program: %s" % message,
                           mg_category=category, exit_code=proc.returncode)
    record = json.loads(proc.stdout)

    # ---- Measurements: the acceptance facts, on the encoded output.
    checks = {}

    total_frames = sidecar["total_frames"]
    total_samples = sidecar["total_samples"]
    out_samples = audio_policy.decode_pcm("ffmpeg", str(out_path))
    checks["plan_totals"] = {
        "verdict": "pass" if record["decoded_frames"] == total_frames
        else "fail",
        "observed": {"plan_total_frames": total_frames,
                     "decoded_frames": record["decoded_frames"],
                     "plan_total_samples": total_samples,
                     "decoded_audio_samples": len(out_samples),
                     "duration_seconds": record["duration_seconds"]}}

    cue_records = [c for c in sidecar.get("cues") or []
                   if c["id"] == cue["id"]]
    resolved_frame = cue_records[0]["frame"] if cue_records else None
    checks["cue_resolved"] = {
        "verdict": "pass" if resolved_frame == slot["start_frame"]
        else "fail",
        "observed": {"cue_id": cue["id"], "resolved_frame": resolved_frame,
                     "slot_start_frame": slot["start_frame"],
                     "handoff_cue_frame": cue["frame"]}}

    design = _resolve_design(handoff)
    layout = design["layouts"]["landscape"]
    width = parent["canvas"]["width"]
    height = parent["canvas"]["height"]
    insert_mp4 = return_dir / return_doc["artifacts"]["mp4"]["path"]
    motion = insert.get("motion") or {
        "start_frame": 15, "end_frame_exclusive": 75,
        "hold_to_frame_exclusive": insert["duration_frames"]}
    mid_frame = (motion["start_frame"] + motion["end_frame_exclusive"]) // 2
    d0, d1 = insert["dataset"]["domain"]
    final_expected = [layout["plot"]["width"] * (r["value"] - d0) / (d1 - d0)
                      for r in insert["dataset"]["rows"]]
    half_expected = [v / 2.0 for v in final_expected]

    def widths_at(frame, path):
        return _bar_widths(_frame_rgb(path, frame, width, height),
                           width, layout)

    at_start = widths_at(slot["start_frame"], out_path)
    at_mid = widths_at(slot["start_frame"] + mid_frame, out_path)
    at_final = widths_at(slot["start_frame"] + motion["end_frame_exclusive"],
                         out_path)
    before_slot = _frame_rgb(out_path, slot["start_frame"] - 1, width, height)
    at_slot = _frame_rgb(out_path, slot["start_frame"], width, height)

    def close(actual, expected, tol=3):
        return all(abs(a - e) <= tol for a, e in zip(actual, expected))

    checks["insert_first_frame"] = {
        "verdict": "pass" if at_start == [0, 0, 0] else "fail",
        "observed": {"parent_frame": slot["start_frame"],
                     "bar_widths": at_start,
                     "expected": [0, 0, 0]}}
    checks["boundary_switch"] = {
        "verdict": "pass" if _mean_abs_diff(before_slot, at_slot) > 8.0
        else "fail",
        "observed": {"mean_abs_diff_frames_%d_%d"
                     % (slot["start_frame"] - 1, slot["start_frame"]):
                     round(_mean_abs_diff(before_slot, at_slot), 3)}}
    checks["insert_motion_in_place"] = {
        "verdict": "pass" if close(at_mid, half_expected)
        and close(at_final, final_expected) else "fail",
        "observed": {"mid_parent_frame": slot["start_frame"] + mid_frame,
                     "mid_widths": at_mid,
                     "mid_expected": half_expected,
                     "final_parent_frame": slot["start_frame"]
                     + motion["end_frame_exclusive"],
                     "final_widths": at_final,
                     "final_expected": final_expected,
                     "tolerance_px": 3}}

    kinds = [e["kind"] for e in record["inputs"]]
    insert_streams = [s.get("codec_type")
                      for s in _ffprobe_streams(insert_mp4)]
    checks["audio_registry"] = {
        "verdict": "pass" if kinds.count("narration") == len(
            sidecar.get("narration") or []) and kinds.count("music") == 1
        and insert_streams == ["video"] else "fail",
        "observed": {"input_kinds": kinds,
                     "narration_inputs": kinds.count("narration"),
                     "music_inputs": kinds.count("music"),
                     "insert_stream_types": insert_streams}}

    media_narr = {n["id"]: n["path"]
                  for n in (media_spec.get("narration") or [])}
    presence = {}
    all_present = True
    for seg in sidecar.get("narration") or []:
        src = audio_policy.decode_pcm("ffmpeg", media_narr[seg["id"]])
        rep = audio_policy.segment_presence_report(
            out_samples, src, seg["startSample"], seg["endSampleExclusive"])
        presence[seg["id"]] = {"present": rep["present"],
                               "bandRatio": rep["bandRatio"],
                               "outputRmsDbfs": rep["outputRmsDbfs"]}
        all_present = all_present and rep["present"]
    checks["narration_presence"] = {
        "verdict": "pass" if all_present else "fail",
        "observed": presence}

    last_seg = (sidecar.get("narration") or [])[-1]
    last_src = audio_policy.decode_pcm("ffmpeg", media_narr[last_seg["id"]])
    tail = audio_policy.narration_tail_report(
        out_samples, last_src, last_seg["startSample"],
        last_seg["endSampleExclusive"])
    checks["final_words"] = {
        "verdict": "pass" if tail["presentAtPlannedEnd"] else "fail",
        "observed": {"segment": last_seg["id"],
                     "presentAtPlannedEnd": tail["presentAtPlannedEnd"],
                     "bandRatio": tail["bandRatio"],
                     "outputTailRmsDbfs": tail["outputTailRmsDbfs"]}}

    target = (media_spec.get("loudness_target")
              or dict(audio_policy.DEFAULT_LOUDNESS_TARGET))
    measured = audio_policy.measure_loudness("ffmpeg", str(out_path), target)
    verdict = audio_policy.loudness_verdict(measured, target)
    checks["loudness"] = {
        "verdict": "pass" if verdict["ok"] else "fail",
        "observed": {"integratedLufs": measured["integratedLufs"],
                     "truePeakDb": measured["truePeakDb"],
                     "target": target,
                     "integratedDeltaLufs": verdict["integratedDeltaLufs"]}}

    checks["assembler_verification"] = {
        "verdict": "pass",
        "observed": {"assemble_exit_code": 0,
                     "note": "the shipped assembler's own encoded-output "
                             "verification (narration presence, final "
                             "words, loudness finish) ran inside plan "
                             "mode and the run succeeded"}}

    verdict_all = all(c["verdict"] == "pass" for c in checks.values())
    report = {
        "schema_version": "1.0",
        "handoff_id": handoff["handoff_id"],
        "parent_job_id": parent["job_id"],
        "plan": {"total_frames": total_frames,
                 "total_samples": total_samples,
                 "fps": parent["fps"]},
        "assembled": {"path": str(out_path),
                      "sha256": sha256_file(out_path),
                      "bytes": out_path.stat().st_size,
                      "decoded_frames": record["decoded_frames"],
                      "duration_seconds": record["duration_seconds"],
                      "audio_samples": len(out_samples)},
        "cue": {"id": cue["id"], "resolved_frame": resolved_frame,
                "slot_start_frame": slot["start_frame"],
                "first_frame_delta": (resolved_frame - slot["start_frame"])
                if resolved_frame is not None else None},
        "checks": checks,
        "verdict": "pass" if verdict_all else "fail",
    }
    _require_schema(report, "assembly_report", "VSL_ASSEMBLY_REPORT_INVALID")
    write_json(work_dir / "assembly-report.json", report)
    return {"assembly_report": report,
            "assembly_report_path": str(work_dir / "assembly-report.json"),
            "assemble_record": record,
            "plan_path": str(plan_path), "media_path": str(media_path)}


# --------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Skill 72 desktop VSL handoff (MG-037).")
    sub = parser.add_subparsers(dest="command", required=True)
    p_validate = sub.add_parser("validate", help="Validate a handoff record.")
    p_validate.add_argument("handoff")
    p_produce = sub.add_parser(
        "produce", help="Stage, render, and package the insert return.")
    p_produce.add_argument("handoff")
    p_produce.add_argument("--work", required=True)
    p_asm = sub.add_parser(
        "assemble-parent",
        help="Assemble the parent VSL with the returned insert in its slot.")
    p_asm.add_argument("handoff")
    p_asm.add_argument("--return-dir", required=True)
    p_asm.add_argument("--media-spec", required=True)
    p_asm.add_argument("--out", required=True)
    p_asm.add_argument("--work", required=True)
    args = parser.parse_args(argv)

    try:
        if args.command == "validate":
            doc = load_json(args.handoff, "handoff")
            validate_handoff(doc)
            print(json.dumps({"status": "VALID",
                              "handoff_id": doc["handoff_id"],
                              "parent_job_id": doc["parent"]["job_id"],
                              "slot": doc["parent"]["slot"],
                              "insert_duration_frames":
                                  doc["insert"]["duration_frames"]},
                             indent=2))
            return EXIT_OK
        if args.command == "produce":
            result = produce(args.handoff, args.work)
            print(json.dumps({"status": "PRODUCED",
                              "return_dir": result["return_dir"],
                              "job_dir": result["job_dir"],
                              "return_package": result["return_package"]},
                             indent=2))
            return EXIT_OK
        if args.command == "assemble-parent":
            result = assemble_parent(args.handoff, args.return_dir,
                                     args.media_spec, args.out, args.work)
            report = result["assembly_report"]
            print(json.dumps({"status": "ASSEMBLED",
                              "assembly_report": report,
                              "assembly_report_path":
                                  result["assembly_report_path"]},
                             indent=2))
            return EXIT_OK if report["verdict"] == "pass" else EXIT_QC
    except HandoffError as err:
        print(json.dumps(err.document(), indent=2), file=sys.stderr)
        return err.exit_code
    return EXIT_INTERNAL


if __name__ == "__main__":
    sys.exit(main())
