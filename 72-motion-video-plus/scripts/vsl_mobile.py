"""MG-038: the mobile VSL vertical derivative (Skill 72 side).

The desktop VSL (MG-037) is owned by a parent job; the parent owns
the narration, the music, the captions, and the delivery ledger.
This module derives the mobile presentation of the SAME approved
message: a genuine 9:16 composition, planned and rendered as its
own job under the vsl_mobile mode manifest (references/
vsl-mobile-mode.json is the governed mode configuration; the
layer's record shapes live in references/vsl-mobile-schema.json;
the canonical contracts-v2.schema.json is not edited).

Recomposition, never derivation from pixels: the vertical job is
staged from the same handoff facts the desktop insert was staged
from (parent identity, slot, spoken-word cue, copy, dataset,
visual direction), with the scene's layout_variant set to
"portrait", so the shipped component renders the design record's
portrait layout: chart geometry is re-derived from the dataset
against the portrait plot (fixture: width 740, rows at y 520,
820, 1120), not scaled or cropped from the landscape master. The
delivery record carries the numeric proof: bar widths and row
centroids measured on the decoded vertical artifact, compared
against the portrait derivation and against the two forbidden
derivations (a uniform scale of the landscape master, a center
crop of it), either of which is refused by name when detected.

Fit, proven before delivery:

- Narration fit: the same approved narration serves both modes.
  The handoff carries the parent's narration timing record (the
  asset reference the parent declares, its segments, and their
  word timings in samples). The cue's word must resolve, by
  sample-exact arithmetic at the declared sample rate and fps,
  to the slot's first frame; the cue's segment must cover the
  whole slot; and the vertical insert's own compiled timeline
  (the shipped MG-021 compiler, slot mode) must total exactly
  the slot length. Nothing is stretched: if more visual time
  were genuinely needed, the answer is a parent timeline
  revision requested through the handoff, never a silent speed
  change (the mode pins allow_speed_change and allow_slot_resize
  false).

- Text and caption fit: every essential text element is measured
  against the MG-013 floors in references/typography-tokens.json
  at its effective displayed size. The vertical canvas is a
  full-frame recomposed canvas, so the effective size is the
  authored size on that canvas (the tokens' own measurement
  basis, and the same rule MG-035's placement audit applies with
  a placement scale of 1). An element below its floor fails BY
  NAME before anything renders; shrinking essential text is
  never the fix.

QC: the delivery package is gated by the shipped MG-034 gate
(scripts/qc.py) in its package lane, under the vsl_mobile mode
(the manifest the gate reads carries the mode). The gate's font
check compares family names against fontconfig; the canonical
assets record declares the requirement by its registry alias
token, which the gate cannot resolve (the pending checker fix
is recorded at MG-037). Following the MG-035 delivery-stage
convention, the QC-facing assets record in the delivery package
declares the requirement under the resolved family name (the
runtime registry's own resolution of the alias, read from the
shipped registry source), and the intake record is retained
beside it as intake-assets.json. The delivery record discloses
both names and the reason; nothing about the seam is hidden.

Delivery: the delivery record names the desktop job this
derivative derives from (derivative_of), binds the artifacts by
hash, and carries its own approval and its own layout hash (the
directive: a separate approval and layout hash for the mobile
variant). Handing the packager a desktop master (a 16:9
artifact) for the vsl_mobile mode fails BY NAME before any
delivery record is written.

Failure discipline matches MG-037: every failure is a
HandoffError with a stable code, a Section 16.9 category, and
the matching exit class. The CLI prints one JSON document on
stdout on success and one JSON error document on stderr on
failure.

CLI:
    python3 scripts/vsl_mobile.py validate HANDOFF.json
    python3 scripts/vsl_mobile.py produce HANDOFF.json --work DIR
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

SCRIPTS_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import vsl_handoff  # noqa: E402  (MG-037: shared handoff machinery)
from vsl_handoff import (  # noqa: E402
    HandoffError,
    compile_timeline,
    load_json,
    sha256_file,
    write_json,
)

SCHEMA_PATH = SKILL_ROOT / "references" / "vsl-mobile-schema.json"
MODE_CONFIG_PATH = SKILL_ROOT / "references" / "vsl-mobile-mode.json"
TOKENS_PATH = SKILL_ROOT / "references" / "typography-tokens.json"
FONTS_TS_PATH = (SKILL_ROOT / "runtime" / "src" / "remotion"
                 / "fonts.ts")
FIXTURE_MODE_DIR = SKILL_ROOT / "tests" / "fixtures" / "modes" / "vsl_mobile"

EXIT_OK = 0
EXIT_CONTRACT = 2
EXIT_INPUT = 3
EXIT_RENDER = 5
EXIT_QC = 6
EXIT_FOREIGN = 9

MODE_CANVAS = (1080, 1920)
PORTRAIT = "portrait"


def mode_config() -> dict:
    return load_json(MODE_CONFIG_PATH, "mobile mode configuration")


def _type_floors() -> dict:
    tokens = load_json(TOKENS_PATH, "typography tokens")
    return {role["role"]: role["floor_px"] for role in tokens["roles"]}


# --------------------------------------------------------------------
# Schema validation against this layer's own schema.
# --------------------------------------------------------------------

_SCHEMA_CACHE = None


def _validator_for(def_name: str) -> Draft202012Validator:
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        _SCHEMA_CACHE = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    schema = _SCHEMA_CACHE
    if def_name not in schema.get("$defs", {}):
        raise KeyError("unknown mobile contract definition: %s" % def_name)
    wrapper = {"$schema": schema["$schema"],
               "$ref": "#/$defs/%s" % def_name, "$defs": schema["$defs"]}
    return Draft202012Validator(wrapper)


def _require_schema(doc, def_name: str, code: str):
    validator = _validator_for(def_name)
    errors = sorted(validator.iter_errors(doc),
                    key=lambda e: ("/".join(str(p) for p in e.absolute_path),
                                   e.message))
    if errors:
        first = errors[0]
        raise HandoffError(
            code,
            "%s fails %s schema at %s: %s (%d finding(s))"
            % (def_name, def_name,
               "/" + "/".join(str(p) for p in first.absolute_path),
               first.message, len(errors)),
            mg_category="MG_SCHEMA_INVALID", exit_code=EXIT_CONTRACT)


# --------------------------------------------------------------------
# Handoff validation: the named agreements first, then the schema.
# The order mirrors MG-037 (slot, cue, length, audio), then the
# mobile-specific agreements (canvas shape, derivative identity,
# narration identity and anchor).
# --------------------------------------------------------------------

def validate_mobile_handoff(doc) -> None:
    """Raise HandoffError on the first violated agreement."""
    if not isinstance(doc, dict):
        raise HandoffError(
            "VSL_MOBILE_SCHEMA_INVALID",
            "mobile handoff document is not a JSON object",
            mg_category="MG_SCHEMA_INVALID", exit_code=EXIT_CONTRACT)

    parent = doc.get("parent") if isinstance(doc.get("parent"), dict) else {}
    slot = parent.get("slot")
    if not isinstance(slot, dict) \
            or not isinstance(slot.get("start_frame"), int) \
            or not isinstance(slot.get("end_frame_exclusive"), int):
        raise HandoffError(
            "VSL_MOBILE_SLOT_TIMING_MISSING",
            "the handoff names no slot timing: parent.slot must "
            "carry start_frame and end_frame_exclusive in the "
            "parent timeline; the vertical derivative answers the "
            "same slot the desktop insert answers, and a duration "
            "the parent did not declare is never estimated",
            mg_category="MG_TIMELINE_INVALID", exit_code=EXIT_CONTRACT)
    if slot["end_frame_exclusive"] <= slot["start_frame"]:
        raise HandoffError(
            "VSL_MOBILE_SLOT_RANGE_INVALID",
            "parent slot [%d, %d) is empty or reversed"
            % (slot["start_frame"], slot["end_frame_exclusive"]),
            mg_category="MG_TIMELINE_INVALID", exit_code=EXIT_CONTRACT)
    slot_len = slot["end_frame_exclusive"] - slot["start_frame"]

    cue = parent.get("narration_cue")
    if not isinstance(cue, dict) or not isinstance(cue.get("frame"), int) \
            or not cue.get("id") or not cue.get("segment_id"):
        raise HandoffError(
            "VSL_MOBILE_CUE_MISSING",
            "the handoff names no narration cue: parent."
            "narration_cue must carry the cue id, the parent "
            "narration segment it anchors into, the word index, "
            "and the cue frame",
            mg_category="MG_TIMELINE_INVALID", exit_code=EXIT_CONTRACT)
    if cue["frame"] != slot["start_frame"]:
        raise HandoffError(
            "VSL_MOBILE_CUE_FRAME_MISMATCH",
            "narration cue %r is at parent frame %d but the slot "
            "starts at frame %d; the derivative's first frame must "
            "land on the cue's frame, so the two must agree in the "
            "handoff" % (cue.get("id"), cue["frame"],
                         slot["start_frame"]),
            mg_category="MG_TIMELINE_INVALID", exit_code=EXIT_CONTRACT)

    insert = doc.get("insert") if isinstance(doc.get("insert"), dict) else {}
    duration = insert.get("duration_frames")
    if isinstance(duration, int):
        if duration > slot_len:
            raise HandoffError(
                "VSL_MOBILE_INSERT_EXCEEDS_SLOT",
                "insert duration %d frames exceeds its parent slot "
                "of %d frames; if the vertical composition genuinely "
                "needs more visual time, the parent timeline must be "
                "revised through the handoff, never the insert "
                "stretched and never the parent narration shortened"
                % (duration, slot_len),
                mg_category="MG_TIMELINE_INVALID", exit_code=EXIT_CONTRACT)
        if duration < slot_len:
            raise HandoffError(
                "VSL_MOBILE_INSERT_UNDERFILLS_SLOT",
                "insert duration %d frames underfills its parent "
                "slot of %d frames; a slot-mode insert must equal "
                "the slot length exactly" % (duration, slot_len),
                mg_category="MG_TIMELINE_INVALID", exit_code=EXIT_CONTRACT)

    audio = doc.get("audio_ownership") \
        if isinstance(doc.get("audio_ownership"), dict) else {}
    if audio.get("narration") is not None and audio.get("narration") != "parent":
        raise HandoffError(
            "VSL_MOBILE_AUDIO_OWNERSHIP_VIOLATION",
            "audio_ownership.narration is %r; in vsl_mobile the "
            "parent owns narration and the derivative is rendered "
            "silent under inherited audio" % (audio.get("narration"),),
            mg_category="MG_MODE_MISMATCH", exit_code=EXIT_CONTRACT)
    if insert.get("narration_assets"):
        raise HandoffError(
            "VSL_MOBILE_AUDIO_OWNERSHIP_VIOLATION",
            "the insert declares %d narration asset(s) into a "
            "parent-owned-narration slot; the mobile derivative "
            "shares the parent's approved narration and never "
            "carries a voice of its own" % len(insert["narration_assets"]),
            mg_category="MG_MODE_MISMATCH", exit_code=EXIT_CONTRACT)
    if audio.get("insert_sound") == "declared":
        raise HandoffError(
            "VSL_MOBILE_AUDIO_OWNERSHIP_VIOLATION",
            "audio_ownership.insert_sound is 'declared'; the "
            "vsl_mobile mode manifest pins the insert's audio to "
            "inherited with no source assets, so insert sound is "
            "not declarable in this mode",
            mg_category="MG_MODE_MISMATCH", exit_code=EXIT_CONTRACT)

    canvas = parent.get("canvas") if isinstance(parent.get("canvas"), dict) \
        else {}
    if (canvas.get("width"), canvas.get("height")) != MODE_CANVAS:
        raise HandoffError(
            "VSL_MOBILE_CANVAS_MISMATCH",
            "the mobile handoff declares canvas %sx%s; the "
            "vsl_mobile mode canvas is %dx%d (9:16). A desktop "
            "canvas in a mobile handoff means the derivative was "
            "never recomposed, and this layer refuses it rather "
            "than shrinking the desktop composition"
            % (canvas.get("width"), canvas.get("height"),
               MODE_CANVAS[0], MODE_CANVAS[1]),
            mg_category="MG_MODE_MISMATCH", exit_code=EXIT_CONTRACT)

    derivative = doc.get("derivative_of") \
        if isinstance(doc.get("derivative_of"), dict) else {}
    if not derivative.get("desktop_job_id") \
            or not derivative.get("desktop_handoff_id"):
        raise HandoffError(
            "VSL_MOBILE_DERIVATIVE_MISSING",
            "the handoff names no desktop job it derives from: "
            "derivative_of must carry the desktop handoff id and "
            "the desktop insert job id, so the vertical delivery "
            "is bound to the approved desktop production it is a "
            "derivative of, never an unrelated composition",
            mg_category="MG_INPUT_MISSING", exit_code=EXIT_INPUT)

    narration = doc.get("narration") \
        if isinstance(doc.get("narration"), dict) else {}
    segments = narration.get("segments")
    if not narration.get("asset_ref") or not isinstance(segments, list) \
            or not segments:
        raise HandoffError(
            "VSL_MOBILE_NARRATION_MISSING",
            "the handoff carries no narration timing record: the "
            "mobile derivative shares the parent's approved "
            "narration, and its fit cannot be proven without the "
            "asset reference and the segment word timings",
            mg_category="MG_INPUT_MISSING", exit_code=EXIT_INPUT)
    if narration["asset_ref"] != parent.get("audio_ref"):
        raise HandoffError(
            "VSL_MOBILE_NARRATION_MISMATCH",
            "the narration record names asset %r but the parent "
            "declares %r; the same approved narration must serve "
            "both modes, so a derivative planned against a "
            "different narration asset is refused"
            % (narration["asset_ref"], parent.get("audio_ref")),
            mg_category="MG_MODE_MISMATCH", exit_code=EXIT_CONTRACT)
    seg = next((s for s in segments
                if isinstance(s, dict)
                and s.get("id") == cue.get("segment_id")), None)
    words = (seg or {}).get("words") or []
    word = next((w for w in words
                 if isinstance(w, dict)
                 and w.get("index") == cue.get("word_index")), None)
    if seg is None or word is None:
        raise HandoffError(
            "VSL_MOBILE_CUE_ANCHOR_UNRESOLVED",
            "the cue anchors into segment %r word %r, but the "
            "narration record carries no such segment or word; "
            "the cue alignment the mode promises cannot be proven"
            % (cue.get("segment_id"), cue.get("word_index")),
            mg_category="MG_TIMELINE_INVALID", exit_code=EXIT_CONTRACT)

    _require_schema(doc, "vsl_mobile_handoff", "VSL_MOBILE_SCHEMA_INVALID")


# --------------------------------------------------------------------
# Design resolution and the layout hash.
# --------------------------------------------------------------------

def _resolve_design(handoff) -> dict:
    ref = (handoff.get("insert") or {}).get("design_ref", "fixture-editorial")
    if isinstance(ref, dict):
        return ref
    if ref == "fixture-editorial":
        return load_json(FIXTURE_MODE_DIR / "design.json", "fixture design")
    raise HandoffError(
        "VSL_MOBILE_DESIGN_UNRESOLVED",
        "design_ref %r does not resolve; the only registered "
        "design reference is 'fixture-editorial', or an inline "
        "design object" % (ref,),
        mg_category="MG_INPUT_MISSING", exit_code=EXIT_INPUT)


def layout_hash(handoff, design) -> str:
    """The mobile variant's own layout hash: the portrait layout,
    the variant, and the canvas, canonically serialized. The
    desktop production carries a different layout (and would hash
    differently); the derivative's approval binds to this hash."""
    parent = handoff["parent"]
    doc = {"canvas": {"width": parent["canvas"]["width"],
                      "height": parent["canvas"]["height"],
                      "fps": parent["fps"]},
           "layout": design["layouts"][PORTRAIT],
           "layout_variant": PORTRAIT}
    blob = json.dumps(doc, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _expected_widths(design, dataset):
    layout = design["layouts"][PORTRAIT]
    plot_width = layout["plot"]["width"]
    d0, d1 = dataset["domain"]
    span = d1 - d0
    final = [round(plot_width * (r["value"] - d0) / span, 4)
             for r in dataset["rows"]]
    return final, [round(v / 2.0, 4) for v in final]


# --------------------------------------------------------------------
# Staging: the handoff fully determines a vsl_mobile job package.
# Mirrors MG-037's staging with the mode, the canvas, and the
# portrait layout variant (and therefore the portrait semantic
# assertions) as the only differences.
# --------------------------------------------------------------------

def stage_mobile_package(handoff, pkg_dir) -> dict:
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
    layout = design["layouts"][PORTRAIT]
    plot_width = layout["plot"]["width"]
    dataset = insert["dataset"]
    d0, d1 = dataset["domain"]
    span = d1 - d0
    if span <= 0:
        raise HandoffError(
            "VSL_MOBILE_SCHEMA_INVALID",
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
        "layout_variant": PORTRAIT,
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
        "mode": "vsl_mobile",
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
                + [vsl_handoff._num(row["value"]) for row in dataset["rows"]]
                + ([insert["copy"]["disclosure"]]
                   if insert["copy"].get("disclosure") else []),
            "proof_frames": [motion["start_frame"], mid_frame,
                             motion["end_frame_exclusive"], duration - 1],
            "typography_only_exception": None,
        }],
    }

    assets = load_json(FIXTURE_MODE_DIR / "assets.json", "fixture assets")

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
# Fit checks. Each returns its section of the fit report and
# raises by name on failure, before anything renders.
# --------------------------------------------------------------------

def check_narration_fit(handoff, compiled_sidecar) -> dict:
    parent = handoff["parent"]
    slot = parent["slot"]
    cue = parent["narration_cue"]
    narration = handoff["narration"]
    rate = narration["sample_rate"]
    fps = parent["fps"]
    slot_len = slot["end_frame_exclusive"] - slot["start_frame"]

    seg = next(s for s in narration["segments"]
               if s["id"] == cue["segment_id"])
    word = next(w for w in seg.get("words") or []
                if w["index"] == cue["word_index"])
    start_sample = word["startSample"]
    if start_sample * fps % rate != 0:
        raise HandoffError(
            "VSL_MOBILE_CUE_NOT_FRAME_ALIGNED",
            "the cue word starts at sample %d, which is not a "
            "whole frame at %d fps and %d Hz; the derivative "
            "cannot land its first frame exactly on the cue"
            % (start_sample, fps, rate),
            mg_category="MG_QC_FAILED", exit_code=EXIT_QC)
    resolved = start_sample * fps // rate
    if resolved != cue["frame"] or resolved != slot["start_frame"]:
        raise HandoffError(
            "VSL_MOBILE_CUE_RESOLUTION_MISMATCH",
            "the cue word resolves to frame %d from the narration "
            "timings, but the handoff declares the cue at frame "
            "%d and the slot starts at frame %d; the three must "
            "agree" % (resolved, cue["frame"], slot["start_frame"]),
            mg_category="MG_QC_FAILED", exit_code=EXIT_QC)
    covers = seg["start_frame"] <= slot["start_frame"] \
        and seg["end_frame_exclusive"] >= slot["end_frame_exclusive"]
    if not covers:
        raise HandoffError(
            "VSL_MOBILE_NARRATION_DOES_NOT_COVER_SLOT",
            "the cue segment %r spans [%d, %d) but the slot is "
            "[%d, %d); the narration the insert answers to does "
            "not cover its whole slot"
            % (seg["id"], seg["start_frame"],
               seg["end_frame_exclusive"], slot["start_frame"],
               slot["end_frame_exclusive"]),
            mg_category="MG_QC_FAILED", exit_code=EXIT_QC)
    total = compiled_sidecar["total_frames"]
    if total != slot_len:
        raise HandoffError(
            "VSL_MOBILE_TIMELINE_SLOT_MISMATCH",
            "the vertical insert's compiled timeline totals %d "
            "frames but its slot is %d frames; a derivative that "
            "does not fit its slot exactly is never stretched "
            "into it" % (total, slot_len),
            mg_category="MG_QC_FAILED", exit_code=EXIT_QC)
    parent_total = max(s["end_frame_exclusive"]
                       for s in narration["segments"])
    return {
        "asset_ref": narration["asset_ref"],
        "parent_audio_ref": parent["audio_ref"],
        "same_approved_narration":
            narration["asset_ref"] == parent["audio_ref"],
        "cue": {"id": cue["id"], "segment_id": cue["segment_id"],
                "word_index": cue["word_index"],
                "word_start_sample": start_sample,
                "resolved_frame": resolved,
                "slot_start_frame": slot["start_frame"],
                "resolution_method":
                    "word startSample x fps / sample_rate, "
                    "sample-exact integer arithmetic at %d Hz "
                    "(the resolution the shipped compiler records "
                    "as the sidecar cue anchor)" % rate},
        "cue_segment_covers_slot": covers,
        "compiled_total_frames": total,
        "slot_length_frames": slot_len,
        "parent_total_frames": parent_total,
        "verdict": "pass",
    }


def check_text_fit(handoff, design) -> dict:
    floors = _type_floors()
    roles = mode_config()["type_floors"]["element_roles"]
    layout = design["layouts"][PORTRAIT]
    authored = {"headline": layout["headline_px"],
                "category_labels": layout["label_px"],
                "values": layout["value_px"],
                "disclosure": layout["disclosure_px"]}
    elements = []
    failures = []
    for element, size in authored.items():
        role = roles[element]
        floor = floors[role]
        # Full-frame recomposed canvas: the authored size IS the
        # effective displayed size (the typography tokens'
        # measurement basis; MG-035's placement audit with a
        # placement scale of 1). The floor never scales down.
        effective = size
        ok = effective >= floor
        elements.append({"element": element, "role": role,
                         "authored_px": size, "floor_px": floor,
                         "effective_px": effective,
                         "verdict": "pass" if ok else "fail"})
        if not ok:
            failures.append("%s (%s: authored %spx, floor %spx)"
                            % (element, role, size, floor))
    if failures:
        raise HandoffError(
            "VSL_MOBILE_TEXT_BELOW_FLOOR",
            "essential text below its MG-013 floor at the "
            "vertical placement: %s. Essential text is never "
            "shrunk to fit; shorten the copy or restage the "
            "composition" % "; ".join(failures),
            mg_category="MG_QC_FAILED", exit_code=EXIT_QC)
    canvas = handoff["parent"]["canvas"]
    return {"canvas": {"width": canvas["width"],
                       "height": canvas["height"]},
            "elements": elements, "verdict": "pass"}


def check_caption_fit(handoff) -> dict:
    floors = _type_floors()
    config = mode_config()["caption_profile"]
    profile = handoff.get("caption_profile") or {}
    size = profile.get("font_size_px") or config["default_font_size_px"]
    placement = profile.get("placement") or config["placement"]
    role_default = config["role"]
    entries = []
    failures = []
    for cap in handoff.get("captions") or []:
        role = cap.get("role") or role_default
        floor = floors[role]
        ok = size >= floor
        entries.append({"id": cap["id"], "role": role,
                        "floor_px": floor, "effective_px": size,
                        "verdict": "pass" if ok else "fail"})
        if not ok:
            failures.append("caption %s (%s: %spx at placement, "
                            "floor %spx)" % (cap["id"], role, size,
                                             floor))
    if failures:
        raise HandoffError(
            "VSL_MOBILE_CAPTION_BELOW_FLOOR",
            "captions below their MG-013 floor at the vertical "
            "placement: %s. The mobile caption profile must carry "
            "speech at a readable size on the 9:16 canvas"
            % "; ".join(failures),
            mg_category="MG_QC_FAILED", exit_code=EXIT_QC)
    return {"profile": {"font_size_px": size, "placement": placement,
                        "role": role_default},
            "entries": entries, "verdict": "pass"}


def run_fit_checks(handoff, design, compiled_sidecar) -> dict:
    report = {
        "schema_version": "1.0",
        "handoff_id": handoff["handoff_id"],
        "insert_job_id": handoff["insert"]["job_id"],
        "narration": check_narration_fit(handoff, compiled_sidecar),
        "text": check_text_fit(handoff, design),
        "captions": check_caption_fit(handoff),
        "verdict": "pass",
    }
    _require_schema(report, "mobile_fit_report",
                    "VSL_MOBILE_FIT_REPORT_INVALID")
    return report


# --------------------------------------------------------------------
# Recomposition measurement: the numeric not-a-crop proof.
# --------------------------------------------------------------------

def _probe_video(path) -> dict:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json",
         str(path)], capture_output=True, text=True)
    if proc.returncode != 0:
        raise HandoffError(
            "VSL_MOBILE_INPUT_INVALID",
            "ffprobe failed on %s: %s" % (path, proc.stderr[-400:]),
            mg_category="MG_INPUT_MISSING", exit_code=EXIT_INPUT)
    streams = json.loads(proc.stdout).get("streams") or []
    video = next((s for s in streams
                  if s.get("codec_type") == "video"), None)
    if video is None:
        raise HandoffError(
            "VSL_MOBILE_INPUT_INVALID",
            "%s carries no video stream" % path,
            mg_category="MG_INPUT_MISSING", exit_code=EXIT_INPUT)
    frames = video.get("nb_frames")
    if frames is None:
        count = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-count_frames", "-show_entries",
             "stream=nb_read_frames", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True)
        frames = count.stdout.strip()
    return {"width": int(video["width"]), "height": int(video["height"]),
            "frame_count": int(frames)}


def _row_centroids(rgb, width, layout, accent=(0xC0, 0x4A, 0x26), tol=28):
    """Mean y of the accent pixels of each bar, on one decoded
    frame: where each bar actually sits vertically."""
    plot = layout["plot"]
    centroids = []
    for row_y in layout["row_y"]:
        lo = max(0, row_y - layout["bar_height"])
        hi = row_y + 2 * layout["bar_height"]
        total = 0
        count = 0
        for y in range(lo, hi):
            base = y * width * 3
            for x in range(plot["x"], plot["x"] + plot["width"]):
                i = base + x * 3
                if (abs(rgb[i] - accent[0]) <= tol
                        and abs(rgb[i + 1] - accent[1]) <= tol
                        and abs(rgb[i + 2] - accent[2]) <= tol):
                    total += y
                    count += 1
        centroids.append(round(total / count, 2) if count else None)
    return centroids


def measure_recomposition(mp4_path, design, dataset, motion) -> dict:
    config = mode_config()["recomposition_proof"]
    width_tol = config["width_tolerance_px"]
    centroid_tol = config["centroid_tolerance_px"]
    margin = config["counterfactual_margin_px"]
    portrait = design["layouts"][PORTRAIT]
    landscape = design["layouts"]["landscape"]
    canvas_w, canvas_h = MODE_CANVAS
    probe = _probe_video(mp4_path)
    if (probe["width"], probe["height"]) != MODE_CANVAS:
        raise HandoffError(
            "VSL_MOBILE_ASPECT_MISMATCH",
            "the artifact probes %dx%d; the vsl_mobile canvas is "
            "%dx%d" % (probe["width"], probe["height"],
                       canvas_w, canvas_h),
            mg_category="MG_MODE_MISMATCH", exit_code=EXIT_CONTRACT)

    final_expected, half_expected = _expected_widths(design, dataset)
    mid_frame = (motion["start_frame"] + motion["end_frame_exclusive"]) // 2
    final_frame = motion["end_frame_exclusive"]
    rgb_mid = vsl_handoff._frame_rgb(mp4_path, mid_frame, canvas_w, canvas_h)
    rgb_final = vsl_handoff._frame_rgb(mp4_path, final_frame,
                                       canvas_w, canvas_h)
    widths_mid = vsl_handoff._bar_widths(rgb_mid, canvas_w, portrait)
    widths_final = vsl_handoff._bar_widths(rgb_final, canvas_w, portrait)
    centroids = _row_centroids(rgb_final, canvas_w, portrait)
    expected_centroids = [y + portrait["bar_height"] / 2.0
                          for y in portrait["row_y"]]

    def close(actual, expected, tol):
        return all(a is not None and abs(a - e) <= tol
                   for a, e in zip(actual, expected))

    # Counterfactual 1: a uniform scale of the landscape master
    # to the mobile width. Its bar widths are fully determined
    # by the landscape derivation.
    d0, d1 = dataset["domain"]
    landscape_finals = [
        landscape["plot"]["width"] * (r["value"] - d0) / (d1 - d0)
        for r in dataset["rows"]]
    scale = canvas_w / 1920.0
    scale_predicted = [round(v * scale, 2) for v in landscape_finals]
    scale_min_diff = min(abs(a - p) for a, p in
                         zip(widths_final, scale_predicted))
    # Counterfactual 2: a center crop of the landscape master,
    # scaled to the mobile height. The landscape plot origin
    # (x=420) falls outside the centered source window, so the
    # bars' left edges would be clipped away entirely; and the
    # row centroids would land at the scaled landscape positions.
    crop_factor = canvas_h / 1080.0
    window_w = canvas_w / crop_factor
    window_x0 = (1920.0 - window_w) / 2.0
    window_x1 = window_x0 + window_w
    crop_centroids = [round((y + landscape["bar_height"] / 2.0)
                            * crop_factor, 2)
                      for y in landscape["row_y"]]
    crop_min_diff = min(abs(a - p) for a, p in
                        zip(centroids, crop_centroids))

    portrait_ok = close(widths_mid, half_expected, width_tol) \
        and close(widths_final, final_expected, width_tol) \
        and close(centroids, expected_centroids, centroid_tol)
    scale_like = close(widths_final, scale_predicted, width_tol)
    if scale_like and not portrait_ok:
        raise HandoffError(
            "VSL_MOBILE_CROP_DETECTED",
            "the artifact's bar widths %s match a uniform scale "
            "of the landscape master (predicted %s), not the "
            "portrait derivation %s; a scaled desktop master is "
            "not a mobile composition"
            % (widths_final, scale_predicted, final_expected),
            mg_category="MG_QC_FAILED", exit_code=EXIT_QC)
    if not portrait_ok:
        raise HandoffError(
            "VSL_MOBILE_RECOMPOSITION_FAILED",
            "decoded portrait frames do not carry the portrait "
            "geometry: widths at frame %d measure %s (portrait "
            "derivation %s), at frame %d measure %s (derivation "
            "%s), row centroids measure %s (portrait rows center "
            "at %s)"
            % (mid_frame, widths_mid, half_expected, final_frame,
               widths_final, final_expected, centroids,
               expected_centroids),
            mg_category="MG_QC_FAILED", exit_code=EXIT_QC)
    if scale_min_diff <= margin or crop_min_diff <= margin:
        raise HandoffError(
            "VSL_MOBILE_RECOMPOSITION_FAILED",
            "the portrait measurements are not separable from "
            "the forbidden derivations (uniform-scale min "
            "difference %spx, center-crop min difference %spx, "
            "margin %spx); the not-a-crop proof would be "
            "ambiguous" % (scale_min_diff, crop_min_diff, margin),
            mg_category="MG_QC_FAILED", exit_code=EXIT_QC)

    return {
        "probe": probe,
        "measured": {
            "half_reveal_frame": mid_frame,
            "half_reveal_widths": widths_mid,
            "final_frame": final_frame,
            "final_widths": widths_final,
            "row_centroids_y": centroids,
            "expected_row_centroids_y": expected_centroids},
        "counterfactuals": {
            "uniform_scale": {
                "factor": scale,
                "predicted_widths": scale_predicted,
                "min_abs_difference": round(scale_min_diff, 2)},
            "center_crop": {
                "factor": crop_factor,
                "source_window": {"x_start": window_x0,
                                  "x_end": window_x1},
                "predicted_row_centroids_y": crop_centroids,
                "min_abs_difference": round(crop_min_diff, 2),
                "landscape_bar_left_edge": landscape["plot"]["x"],
                "bar_origins_inside_window":
                    window_x0 <= landscape["plot"]["x"]}},
        "verdict": "pass",
    }


# --------------------------------------------------------------------
# Motion proof: the shipped MG-032 evaluator over the vertical
# artifact, with a case derived from the staged portrait scene.
# --------------------------------------------------------------------

def build_portrait_case(handoff, design) -> dict:
    insert = handoff["insert"]
    motion = insert.get("motion") or {
        "start_frame": 15, "end_frame_exclusive": 75,
        "hold_to_frame_exclusive": insert["duration_frames"]}
    layout = design["layouts"][PORTRAIT]
    plot = layout["plot"]
    subjects = []
    for row, y in zip(insert["dataset"]["rows"], layout["row_y"]):
        subjects.append({
            "id": "bar-%s" % row["id"], "role": "data_mark",
            "region": {"x": plot["x"], "y": y, "width": plot["width"],
                       "height": layout["bar_height"]}})
    mid = (motion["start_frame"] + motion["end_frame_exclusive"]) // 2
    return {
        "schema_version": "1.0",
        "kind": "motion_proof_case",
        "id": "c05-bar-reveal-portrait",
        "job_id": insert["job_id"],
        "component_id": insert["component_id"],
        "scene_id": insert["scene_id"],
        "checkpoints": [
            {"frame": 0, "role": "initial"},
            {"frame": mid, "role": "proof"},
            {"frame": motion["end_frame_exclusive"], "role": "final"},
            {"frame": insert["duration_frames"] - 1, "role": "hold"}],
        "evidence_required": ["geometry", "decoded_frame",
                              "full_fps_clip"],
        "judgment": {"mode": "automated"},
        "subject_appearance": {"color": design["colors"]["accent"]},
        "subjects": subjects,
        "tolerances": {"decoded_px": 2, "geometry_px": 1},
        "transformation": {
            "claims_depth": False,
            "interval": {"start_frame": motion["start_frame"],
                         "end_frame_exclusive":
                             motion["end_frame_exclusive"]},
            "kind": "linear_reveal"},
    }


def run_motion_proof(handoff, design, pkg_dir, mp4_path, work_dir) -> dict:
    insert = handoff["insert"]
    work_dir = Path(work_dir)
    case = build_portrait_case(handoff, design)
    case_path = write_json(work_dir / "portrait-case.json", case)
    beats_path = write_json(
        work_dir / "beats.json",
        {"beat_times": sorted({cp["frame"] / handoff["parent"]["fps"]
                               for cp in case["checkpoints"]})})
    bundle_dir = work_dir / "bundle"
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "critique_bundle.py"),
         "build", "--video", str(mp4_path), "--outdir", str(bundle_dir),
         "--job-id", insert["job_id"],
         "--timeline", str(Path(pkg_dir) / "compiled-timeline.json"),
         "--sidecar", str(Path(pkg_dir) / "timeline-sidecar.json"),
         "--beats", str(beats_path)],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise HandoffError(
            "VSL_MOBILE_COVERAGE_FAILED",
            "the MG-031 coverage bundle build failed (exit %d): "
            "%s" % (proc.returncode, (proc.stdout or "")[-800:]),
            mg_category="MG_QC_FAILED", exit_code=EXIT_QC)
    coverage = bundle_dir / ("%s__coverage.json" % insert["job_id"])
    if not coverage.is_file():
        raise HandoffError(
            "VSL_MOBILE_COVERAGE_FAILED",
            "the coverage bundle produced no coverage record at "
            "%s" % coverage,
            mg_category="MG_QC_FAILED", exit_code=EXIT_QC)
    proc = subprocess.run(
        ["node", str(SCRIPTS_DIR / "vsl-proof.mjs"),
         "--case", str(case_path), "--video", str(mp4_path),
         "--coverage", str(coverage), "--job-dir", str(pkg_dir),
         "--out-dir", str(work_dir / "proof")],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise HandoffError(
            "VSL_MOBILE_MOTION_PROOF_FAILED",
            "the MG-032 evaluator refused the vertical artifact "
            "(exit %d): %s" % (proc.returncode,
                               (proc.stderr or proc.stdout)[-800:]),
            mg_category="MG_QC_FAILED", exit_code=EXIT_QC)
    record = json.loads(proc.stdout)["record"]
    if record.get("verdict") != "pass":
        raise HandoffError(
            "VSL_MOBILE_MOTION_PROOF_FAILED",
            "the MG-032 evaluator's verdict on the vertical "
            "artifact is %r, not pass" % (record.get("verdict"),),
            mg_category="MG_QC_FAILED", exit_code=EXIT_QC)
    return {"record": record, "coverage_path": str(coverage),
            "case_path": str(case_path)}


# --------------------------------------------------------------------
# QC: the shipped MG-034 gate over the delivery package, under
# the vsl_mobile mode. The QC-facing font declaration follows
# the MG-035 delivery-stage convention (module docstring).
# --------------------------------------------------------------------

def resolve_family_alias(alias) -> str:
    """Resolve a font alias through the runtime's shipped
    registry source (runtime/src/remotion/fonts.ts), the same
    registry the adapter resolves through. No second copy of the
    mapping lives here."""
    text = FONTS_TS_PATH.read_text(encoding="utf-8")
    match = re.search(
        r'"%s"\s*:\s*\{\s*family:\s*"([^"]+)"' % re.escape(alias), text)
    if not match:
        raise HandoffError(
            "VSL_MOBILE_FONT_UNRESOLVED",
            "font alias %r has no registration in the runtime "
            "registry; substitution is forbidden and this layer "
            "does not invent a family" % (alias,),
            mg_category="MG_SCHEMA_INVALID", exit_code=EXIT_CONTRACT)
    return match.group(1)


def build_qc_package(handoff, pkg_dir, mp4_path, work_dir):
    """Copy the staged job into the delivery package the gate
    judges: the rendered final in place, and the assets record
    restated for the gate under the resolved family name (the
    intake record retained beside it). Returns (package_dir,
    font_declaration)."""
    delivery_pkg = Path(work_dir) / "delivery-package"
    if delivery_pkg.exists():
        shutil.rmtree(delivery_pkg)
    shutil.copytree(pkg_dir, delivery_pkg)
    renders = delivery_pkg / "renders"
    renders.mkdir(exist_ok=True)
    shutil.copyfile(mp4_path, renders / "final.mp4")

    intake = load_json(delivery_pkg / "assets.json", "intake assets")
    write_json(delivery_pkg / "intake-assets.json", intake)
    requirements = intake.get("font_requirements") or []
    resolved = {}
    delivery_assets = json.loads(json.dumps(intake))
    for req in delivery_assets.get("font_requirements") or []:
        if req.get("source") == "runtime_registry":
            family = resolve_family_alias(req["family_alias"])
            resolved[req["family_alias"]] = family
            req["family_alias"] = family
    write_json(delivery_pkg / "assets.json", delivery_assets)
    first_alias = (requirements[0].get("family_alias")
                   if requirements else None)
    declaration = {
        "intake_family_alias": first_alias,
        "qc_facing_family_alias": resolved.get(first_alias),
        "resolution_source":
            "runtime/src/remotion/fonts.ts ALIAS_REGISTRY (the "
            "registry the adapter resolves the alias through)",
        "disclosure":
            "The delivery package's QC-facing assets record "
            "declares the font requirement under the resolved "
            "family name, following the MG-035 delivery-stage "
            "convention, because the MG-034 gate compares family "
            "names against fontconfig and cannot resolve the "
            "canonical alias token (the pending checker fix is "
            "recorded at MG-037). The intake assets record with "
            "the canonical alias is retained in the delivery "
            "package as intake-assets.json. The render itself "
            "resolved the alias through the runtime registry, "
            "as it refuses to render otherwise.",
    }
    return delivery_pkg, declaration


def run_qc(handoff, delivery_pkg, plan_path, coverage_path,
           proof_record_path, work_dir) -> dict:
    out_path = Path(work_dir) / "qc-mobile.json"
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "qc.py"), "check",
         "--job-dir", str(delivery_pkg), "--plan", str(plan_path),
         "--coverage", str(coverage_path),
         "--motion-proof", str(proof_record_path),
         "--out", str(out_path)],
        capture_output=True, text=True)
    try:
        report = json.loads(proc.stdout)
    except ValueError:
        raise HandoffError(
            "VSL_MOBILE_QC_FAILED",
            "the MG-034 gate produced no report (exit %d): %s"
            % (proc.returncode, (proc.stderr or "")[-800:]),
            mg_category="MG_QC_FAILED", exit_code=EXIT_QC)
    if proc.returncode != 0 or report.get("verdict") != "pass":
        summary = report.get("summary") or {}
        raise HandoffError(
            "VSL_MOBILE_QC_FAILED",
            "the MG-034 gate's verdict on the vsl_mobile delivery "
            "package is %r (exit %d): %d pass, %d fail, failed "
            "checks %s" % (report.get("verdict"), proc.returncode,
                           summary.get("pass", 0),
                           summary.get("fail", 0),
                           summary.get("failed_checks")),
            mg_category="MG_QC_FAILED", exit_code=EXIT_QC)
    return {"report": report, "report_path": str(out_path)}


# --------------------------------------------------------------------
# Delivery packaging: the artifact gate first, then the record.
# --------------------------------------------------------------------

def assert_deliverable_artifact(handoff, artifact_path) -> dict:
    """Probe one artifact against the mode's delivery promises.
    A desktop master handed to the mobile packager fails here,
    by name, before any delivery record exists."""
    probe = _probe_video(artifact_path)
    canvas = handoff["parent"]["canvas"]
    if (probe["width"], probe["height"]) != (canvas["width"],
                                             canvas["height"]):
        raise HandoffError(
            "VSL_MOBILE_ASPECT_MISMATCH",
            "the artifact probes %dx%d but the vsl_mobile mode "
            "delivers %dx%d (9:16); a desktop master is not a "
            "mobile delivery, and no delivery record is written "
            "for one" % (probe["width"], probe["height"],
                         canvas["width"], canvas["height"]),
            mg_category="MG_MODE_MISMATCH", exit_code=EXIT_CONTRACT)
    expected = handoff["insert"]["duration_frames"]
    if probe["frame_count"] != expected:
        raise HandoffError(
            "VSL_MOBILE_ARTIFACT_DURATION_MISMATCH",
            "the artifact carries %d frames; the mobile insert "
            "is %d frames (the parent slot's length, never "
            "resized)" % (probe["frame_count"], expected),
            mg_category="MG_QC_FAILED", exit_code=EXIT_QC)
    return probe


def write_delivery_record(handoff, design, artifact_path, poster_path,
                          delivery_dir, evidence) -> dict:
    probe = assert_deliverable_artifact(handoff, artifact_path)
    parent = handoff["parent"]
    insert = handoff["insert"]
    req = handoff["return_requirements"]
    final_expected, half_expected = _expected_widths(
        design, insert["dataset"])
    delivery_dir = Path(delivery_dir)
    delivery_dir.mkdir(parents=True, exist_ok=True)
    mp4_dst = delivery_dir / "insert-mobile.mp4"
    shutil.copyfile(artifact_path, mp4_dst)
    artifacts = {
        "mp4": {"path": "insert-mobile.mp4",
                "sha256": sha256_file(mp4_dst),
                "bytes": mp4_dst.stat().st_size},
        "source_package": {"path": evidence["job_dir"]},
    }
    if poster_path is not None and Path(poster_path).is_file():
        poster_dst = delivery_dir / "poster.png"
        shutil.copyfile(poster_path, poster_dst)
        artifacts["poster"] = {
            "path": "poster.png", "sha256": sha256_file(poster_dst),
            "bytes": poster_dst.stat().st_size,
            "frame": req["poster_frame"]}
    fit = evidence["fit_report"]
    recomposition = dict(evidence["recomposition"])
    recomposition["probe"] = probe
    record = {
        "schema_version": "1.0",
        "mode": "vsl_mobile",
        "handoff_id": handoff["handoff_id"],
        "insert_job_id": insert["job_id"],
        "parent_job_id": parent["job_id"],
        "derivative_of": {
            "desktop_handoff_id":
                handoff["derivative_of"]["desktop_handoff_id"],
            "desktop_job_id": handoff["derivative_of"]["desktop_job_id"],
            "relationship": "vertical_derivative_recomposed"},
        "engine": evidence.get("engine") or "remotion",
        "component_id": insert["component_id"],
        "canvas": {"width": parent["canvas"]["width"],
                   "height": parent["canvas"]["height"],
                   "fps": parent["fps"]},
        "slot": {"start_frame": parent["slot"]["start_frame"],
                 "end_frame_exclusive":
                     parent["slot"]["end_frame_exclusive"]},
        "cue": {"id": parent["narration_cue"]["id"],
                "frame": parent["narration_cue"]["frame"],
                "resolved_frame":
                    fit["narration"]["cue"]["resolved_frame"]},
        "layout": {
            "variant": PORTRAIT,
            "layout_hash": layout_hash(handoff, design),
            "plot": {"x": design["layouts"][PORTRAIT]["plot"]["x"],
                     "width":
                         design["layouts"][PORTRAIT]["plot"]["width"]},
            "expected_bar_widths": {"half_reveal": half_expected,
                                    "final": final_expected}},
        "approval": evidence["approval"],
        "artifacts": artifacts,
        "recomposition": recomposition,
        "fit": {"narration_verdict": fit["narration"]["verdict"],
                "text_verdict": fit["text"]["verdict"],
                "captions_verdict": fit["captions"]["verdict"],
                "verdict": fit["verdict"]},
        "proof": {"motion_proof_verdict": evidence["proof_verdict"],
                  "qc_verdict": evidence["qc_verdict"],
                  "qc_report_path": evidence["qc_report_path"]},
        "font_declaration": evidence["font_declaration"],
    }
    _require_schema(record, "mobile_delivery_record",
                    "VSL_MOBILE_DELIVERY_RECORD_INVALID")
    write_json(delivery_dir / "delivery-record.json", record)
    return record


# --------------------------------------------------------------------
# Produce: stage, validate, compile, fit, render, prove, gate,
# and package the vertical delivery.
# --------------------------------------------------------------------

def produce(handoff_path, work_dir) -> dict:
    handoff = load_json(handoff_path, "handoff")
    validate_mobile_handoff(handoff)
    parent = handoff["parent"]
    insert = handoff["insert"]
    req = handoff["return_requirements"]
    slot = parent["slot"]
    motion = insert.get("motion") or {
        "start_frame": 15, "end_frame_exclusive": 75,
        "hold_to_frame_exclusive": insert["duration_frames"]}
    design = _resolve_design(handoff)

    work_dir = Path(work_dir)
    pkg_dir = work_dir / "insert-job"
    stage_mobile_package(handoff, pkg_dir)

    findings = vsl_handoff.motion_contracts.validate_job(pkg_dir)
    if findings:
        first = findings[0]
        raise HandoffError(
            "VSL_MOBILE_JOB_INVALID",
            "the staged mobile job fails the contracts layer: "
            "%s at %s: %s (%d finding(s))"
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
    compiled = compile_timeline(insert_input, work_dir / "compile",
                                "insert")
    write_json(pkg_dir / "plan.json", compiled)
    write_json(pkg_dir / "compiled-timeline.json", compiled["timeline"])
    write_json(pkg_dir / "timeline-sidecar.json", compiled["sidecar"])

    fit_report = run_fit_checks(handoff, design, compiled["sidecar"])
    write_json(work_dir / "fit-report.json", fit_report)

    # The mobile variant's own approval: separate from the
    # desktop production's, per the directive. Fixture context,
    # stated plainly, as the shipped suites' convention.
    approval = {
        "schema_version": "2.0",
        "approval_id": "%s-mobile-delivery" % handoff["handoff_id"],
        "job_id": insert["job_id"],
        "company_id": parent["company_id"],
        "scope": "delivery",
        "decision": "approved",
        "subject_revision": "fixture",
        "artifact_refs": [],
        "actor_id": "mg038-vsl-mobile-producer",
        "source_event_ref": handoff["handoff_id"],
        "authority_status": "not_verified",
    }
    approval_path = write_json(
        work_dir / "approvals" / "mobile-delivery-approval.json",
        approval)

    evidence = vsl_handoff._run_driver(
        "vsl-render.mjs",
        ["--job-dir", str(pkg_dir), "--out-dir", str(work_dir / "render"),
         "--approval", str(approval_path)],
        "mobile insert render")
    mp4_src = Path(evidence["mp4"])
    poster_src = Path(evidence["poster"]) if evidence.get("poster") else None
    if "mp4" in req["artifacts"] and not mp4_src.is_file():
        raise HandoffError(
            "VSL_MOBILE_RENDER_INCOMPLETE",
            "the render produced no MP4 at %s" % mp4_src,
            mg_category="MG_RENDER_FAILED", exit_code=EXIT_RENDER)
    if "poster" in req["artifacts"] and (poster_src is None
                                         or not poster_src.is_file()):
        raise HandoffError(
            "VSL_MOBILE_RENDER_INCOMPLETE",
            "the render produced no poster, but the return "
            "requirements name one",
            mg_category="MG_RENDER_FAILED", exit_code=EXIT_RENDER)

    recomposition = measure_recomposition(
        mp4_src, design, insert["dataset"], motion)

    proof = run_motion_proof(handoff, design, pkg_dir, mp4_src,
                             work_dir / "proof-run")
    proof_record_path = write_json(
        work_dir / "motion-proof-record.json", proof["record"])

    delivery_pkg, font_declaration = build_qc_package(
        handoff, pkg_dir, mp4_src, work_dir)
    qc = run_qc(handoff, delivery_pkg, delivery_pkg / "plan.json",
                proof["coverage_path"], proof_record_path, work_dir)

    record = write_delivery_record(
        handoff, design, mp4_src, poster_src, work_dir / "delivery",
        {"job_dir": str(pkg_dir),
         "engine": evidence.get("engine") or "remotion",
         "approval": {"approval_id": approval["approval_id"],
                      "scope": "delivery", "decision": "approved",
                      "authority_status": "not_verified",
                      "execution_context": "fixture"},
         "fit_report": fit_report,
         "recomposition": recomposition,
         "proof_verdict": proof["record"].get("verdict"),
         "qc_verdict": qc["report"].get("verdict"),
         "qc_report_path": qc["report_path"],
         "font_declaration": font_declaration})
    shutil.copyfile(pkg_dir / "compiled-timeline.json",
                    work_dir / "delivery" / "compiled-timeline.json")
    shutil.copyfile(pkg_dir / "timeline-sidecar.json",
                    work_dir / "delivery" / "timeline-sidecar.json")
    return {"delivery_record": record,
            "delivery_dir": str(work_dir / "delivery"),
            "job_dir": str(pkg_dir),
            "fit_report": fit_report,
            "recomposition": recomposition,
            "qc_report": qc["report"],
            "proof_record": proof["record"],
            "render_evidence": evidence}


# --------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Skill 72 mobile VSL vertical derivative (MG-038).")
    sub = parser.add_subparsers(dest="command", required=True)
    p_validate = sub.add_parser("validate",
                                help="Validate a mobile handoff record.")
    p_validate.add_argument("handoff")
    p_produce = sub.add_parser(
        "produce",
        help="Stage, render, prove, gate, and package the derivative.")
    p_produce.add_argument("handoff")
    p_produce.add_argument("--work", required=True)
    args = parser.parse_args(argv)

    try:
        if args.command == "validate":
            doc = load_json(args.handoff, "handoff")
            validate_mobile_handoff(doc)
            print(json.dumps({
                "status": "VALID",
                "handoff_id": doc["handoff_id"],
                "parent_job_id": doc["parent"]["job_id"],
                "derivative_of": doc["derivative_of"],
                "canvas": doc["parent"]["canvas"],
                "slot": doc["parent"]["slot"],
                "insert_duration_frames":
                    doc["insert"]["duration_frames"]}, indent=2))
            return EXIT_OK
        if args.command == "produce":
            result = produce(args.handoff, args.work)
            print(json.dumps({
                "status": "PRODUCED",
                "delivery_dir": result["delivery_dir"],
                "job_dir": result["job_dir"],
                "delivery_record": result["delivery_record"]},
                indent=2))
            return EXIT_OK
    except HandoffError as err:
        print(json.dumps(err.document(), indent=2), file=sys.stderr)
        return err.exit_code
    return 1


if __name__ == "__main__":
    sys.exit(main())
