#!/usr/bin/env python3
"""approve_once.py: the run owner approves the storyboard once (N-17, section 3.11). Stdlib only.

Replacing a picture or a clip to fix a defect inside the approved story does
not reopen approval. Only a changed story beat does: a new lyric line, a
different speaker, a different place, wardrobe or cast, or a different event.
Presentation fields -- the picture, the clip, the prompt, the model, the render
notes -- are never story, so swapping one for a better take keeps the approval.

``approval_required(previous, current)`` answers one question and returns the
exact shot ids that changed. ``carry_approval`` applies the answer to the new
shot list: unchanged shots keep ``storyboard_approved``; changed or new shots
drop back to ``planned`` so only they are presented again.

Stdlib only, no IO, no provider call.
"""
from __future__ import annotations

SCHEMA_VERSION = "blackceo.approve-once/v1"

APPROVAL_HELD = "APPROVAL_HELD"
APPROVAL_REQUIRED = "APPROVAL_REQUIRED"

#: Fields that are the STORY. A change to any of them reopens approval.
BEAT_FIELDS = (
    "beat_id",
    "story_beat_id",
    "lyric_line_ids",
    "lyric_lines",
    "speaker",
    "story_stage",
    "location_id",
    "location_ids",
    "wardrobe_ids",
    "character_ids",
    "event",
    "visible_action",
    "action",
    "entrance",
    "exit_state",
)

#: Fields that are PRESENTATION. They never reopen an approval; named so a
#: reader can see they were considered and deliberately excluded.
PRESENTATION_FIELDS = (
    "still_path",
    "clip_path",
    "image_path",
    "prompt",
    "image_model",
    "video_model",
    "render_notes",
    "camera_direction",
    "cost_estimate",
    "qc_requirements",
)


def _normal(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        return tuple(_normal(v) for v in value)
    if isinstance(value, dict):
        return tuple(sorted((str(k), _normal(v)) for k, v in value.items()))
    return value


def beat_signature(shot):
    """The story parts of one shot, in a stable order."""
    shot = shot if isinstance(shot, dict) else {}
    return {field: _normal(shot.get(field)) for field in BEAT_FIELDS
            if field in shot}


def _by_id(shots):
    out = {}
    for shot in shots or []:
        if isinstance(shot, dict) and shot.get("shot_id"):
            out[shot["shot_id"]] = shot
    return out


def story_changed(previous, current):
    """Shot ids whose story beat changed, was added or was removed."""
    before, after = _by_id(previous), _by_id(current)
    changed = []
    for sid in sorted(set(before) | set(after), key=str):
        if sid not in before or sid not in after:
            changed.append(sid)
            continue
        if beat_signature(before[sid]) != beat_signature(after[sid]):
            changed.append(sid)
    return changed


def approval_required(previous, current):
    """Whether the run owner must approve again, and which shots changed."""
    changed = story_changed(previous, current)
    return {
        "schema_version": SCHEMA_VERSION,
        "required": bool(changed),
        "reason_code": APPROVAL_REQUIRED if changed else APPROVAL_HELD,
        "changed_shots": changed,
        "detail": ("the story beats changed: %s" % ", ".join(sorted(map(str, changed)))
                   if changed else
                   "presentation only; the approved storyboard stands"),
    }


def carry_approval(previous, current, approved_status="storyboard_approved",
                   draft_status="planned"):
    """Apply the approval answer to a new shot list, shot by shot.

    An unchanged shot keeps its approved status. A changed shot, or a shot with
    no previous row, drops back to the draft status. Returns
    ``{"approval": ..., "shots": [...]}``; the input shots are not mutated.
    """
    before = _by_id(previous)
    changed = set(story_changed(previous, current))
    out = []
    for shot in current or []:
        if not isinstance(shot, dict):
            out.append(shot)
            continue
        sid = shot.get("shot_id")
        row = dict(shot)
        if sid in before and sid not in changed and \
                before[sid].get("status") == approved_status:
            row["status"] = approved_status
        elif sid in changed or sid not in before:
            row["status"] = draft_status
        out.append(row)
    return {"approval": approval_required(previous, current), "shots": out}


__all__ = [
    "SCHEMA_VERSION", "APPROVAL_HELD", "APPROVAL_REQUIRED", "BEAT_FIELDS",
    "PRESENTATION_FIELDS", "beat_signature", "story_changed",
    "approval_required", "carry_approval",
]
