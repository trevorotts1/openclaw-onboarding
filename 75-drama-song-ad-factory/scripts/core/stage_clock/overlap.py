"""overlap.py - N-68: the stages that may run beside each other (10B).

Character masters start when the look is locked and the cast is named; picture
remakes are sent the minute a check fails; the remake burst goes when 9 in 10
clips are back; the side-by-side passes, the overlays and the placeholder
timeline run beside the bursts; the action question joins the one vision call
(3F.4). The table lives in references/time-budgets.json; this module reads it.

A stage not in the table is ordinary sequence and is allowed here.
"""
import os


def _load_overlaps(path=None):
    try:
        try:
            from .clock import load_budgets
        except ImportError:
            from clock import load_budgets
        overlaps = (load_budgets(path) or {}).get("overlaps")
    except Exception:                      # noqa: BLE001 - a missing file is data
        overlaps = None
    return overlaps or [
        {"stage": "character-masters",
         "starts_when": ["look_locked", "cast_named"],
         "runs_beside": ["story-spine", "story-gate"]},
        {"stage": "picture-remakes", "starts_when": ["check_failed"],
         "runs_beside": ["picture-checks"]},
        {"stage": "remake-burst", "starts_when": ["nine_in_ten_clips_back"],
         "runs_beside": ["video-checks"]},
        {"stage": "side-by-side-picture-pass", "starts_when": ["pictures_picked"],
         "runs_beside": ["picture-remakes"], "gates": ["video-burst"]},
        {"stage": "side-by-side-clip-pass", "starts_when": ["clips_landing"],
         "runs_beside": ["remake-burst"]},
        {"stage": "overlays-and-placeholder-timeline",
         "starts_when": ["storyboard_approved"], "runs_beside": ["video-burst"]},
        {"stage": "action-question", "joins": "vision_call"},
    ]


def can_start(stage_id, state, *, path=None):
    """Whether an overlapping stage may start now.

    ``state`` is the set of facts already true (for example ``look_locked``,
    ``cast_named``, ``check_failed``). Returns ``{"ok", "missing", ...}``.
    """
    state = set(state or ())
    for rec in _load_overlaps(path):
        if rec.get("stage") != stage_id:
            continue
        if rec.get("joins"):
            return {"ok": True, "missing": [], "joins": rec["joins"],
                    "reason": "runs inside one vision call, never a separate wait"}
        missing = sorted(set(rec.get("starts_when") or []) - state)
        return {"ok": not missing, "missing": missing,
                "runs_beside": list(rec.get("runs_beside") or []),
                "gates": list(rec.get("gates") or []),
                "reason": None if not missing
                else "waiting on %s" % ", ".join(missing)}
    return {"ok": True, "missing": [], "runs_beside": [], "gates": [],
            "reason": "not an overlapping special case; ordinary sequence"}


def runs_beside(stage_id, *, path=None):
    for rec in _load_overlaps(path):
        if rec.get("stage") == stage_id:
            return list(rec.get("runs_beside") or [])
    return []


def gated_stages(stage_id, *, path=None):
    """Stages this one gates (the side-by-side picture pass gates the video burst)."""
    out = []
    for rec in _load_overlaps(path):
        if stage_id in (rec.get("gates") or []):
            out.append(rec["stage"])
    return out
