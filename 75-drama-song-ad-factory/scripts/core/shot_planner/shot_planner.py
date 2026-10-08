"""shot_planner.py: per-shot records bound to lyric timing (directive 14.2-14.3). Stdlib only.

Every shot carries all 14.2 fields and binds to lyric_line_ids from the
W2-08 timing map (directive 12.4 shape; fixture timing.json acceptable).
bind_plan() fails closed: empty plans, duplicate ids, unbound lines and
windows that do not cover their lines are rejected, never coerced.
"""
from __future__ import annotations

SCHEMA_VERSION = "1.0.0"
TOOL_VERSION = "1.0.0"

# Directive 14.2: every shot record carries at least these fields.
SHOT_FIELDS = (
    "shot_id",
    "song_start",
    "song_end",
    "lyric_line_ids",
    "story_stage",
    "visual_objective",
    "character_ids",
    "wardrobe_ids",
    "location_id",
    "product_visibility",
    "camera_direction",
    "reference_assets",
    "image_model_capability_request",
    "video_model_capability_request",
    "continuity_constraints",
    "negative_constraints",
    "cost_estimate",
    "qc_requirements",
    "status",
)

# Directive 14.3: lyric-to-visual contract questions, one key each.
CONTRACT_KEYS = (
    "lyric_text",            # what exact lyric is playing?
    "viewer_understanding",  # what must the viewer understand?
    "character_action",      # what should the character be doing?
    "visible_emotion",       # what emotion should be visible?
    "change_from_prior",     # what changed from the prior shot?
    "treatment",             # literal-repeat | metaphor-amplify | contextual-contrast
    "necessity",             # is the shot necessary?
)

TREATMENTS = frozenset({"literal-repeat", "metaphor-amplify", "contextual-contrast"})

# ponytail: closed visibility set is a local guess; adopt the W2-04
# product-bible enum when it lands and delete this set.
PRODUCT_VISIBILITY = frozenset({"none", "background", "featured", "hero", "packshot"})

# Storyboard QC (14.1) happens BEFORE video spend, so status must record it.
STATUSES = frozenset({"draft", "planned", "storyboard_approved", "parked", "rejected"})

PRODUCT_SHOT_VISIBILITY = frozenset({"featured", "hero", "packshot"})


class PlanError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _str_list(v):
    return (isinstance(v, list) and all(isinstance(x, str) and x.strip() for x in v))


def validate_shot(shot):
    """Structural check of all 14.2 fields. Returns [error strings]."""
    errs = []
    if not isinstance(shot, dict):
        return ["shot-not-a-record"]
    for f in SHOT_FIELDS:
        if f not in shot:
            errs.append("missing-field:%s" % f)
    if errs:
        return errs
    if not isinstance(shot["shot_id"], str) or not shot["shot_id"].strip():
        errs.append("bad-shot_id")
    s, e = shot["song_start"], shot["song_end"]
    if not _is_num(s) or not _is_num(e) or s < 0 or e < 0:
        errs.append("bad-window")
    elif not s < e:
        errs.append("window-not-ordered")
    if not _str_list(shot["lyric_line_ids"]) or not shot["lyric_line_ids"]:
        errs.append("bad-lyric_line_ids")
    for f in ("story_stage", "visual_objective", "location_id", "camera_direction"):
        if not isinstance(shot[f], str) or not shot[f].strip():
            errs.append("bad-%s" % f)
    for f in ("character_ids", "wardrobe_ids", "reference_assets",
              "continuity_constraints", "negative_constraints"):
        if not isinstance(shot[f], list) or not all(isinstance(x, str) for x in shot[f]):
            errs.append("bad-%s" % f)
    if shot["product_visibility"] not in PRODUCT_VISIBILITY:
        errs.append("bad-product_visibility")
    # ponytail: capability request shape fixed as {capabilities:[...]};
    # loosen when skill 67 publishes its router schema.
    for f in ("image_model_capability_request", "video_model_capability_request"):
        r = shot[f]
        if not (isinstance(r, dict) and _str_list(r.get("capabilities")) and r["capabilities"]):
            errs.append("bad-%s" % f)
    c = shot["cost_estimate"]
    if isinstance(c, bool) or not isinstance(c, int) or c < 0:
        errs.append("bad-cost_estimate")
    if not isinstance(shot["qc_requirements"], list):
        errs.append("bad-qc_requirements")
    if shot["status"] not in STATUSES:
        errs.append("bad-status")
    return errs


def validate_contract(contract):
    """All seven 14.3 questions answered. Returns [error strings]."""
    errs = []
    if not isinstance(contract, dict):
        return ["contract-not-a-record"]
    for k in CONTRACT_KEYS:
        v = contract.get(k)
        if not isinstance(v, str) or not v.strip():
            errs.append("missing-contract:%s" % k)
    if isinstance(contract.get("treatment"), str) and contract["treatment"].strip() \
            and contract["treatment"].strip() not in TREATMENTS:
        errs.append("bad-treatment")
    return errs


def load_timing_map(obj):
    """Normalize a 12.4 timing map to {song_id, duration_seconds, lines}.

    lines[line_id] = {start, end, text, section_id}. Raises PlanError on
    bad shape, duplicate lines or unordered line windows.
    """
    if not isinstance(obj, dict) or not isinstance(obj.get("sections"), list) \
            or not obj["sections"]:
        raise PlanError("BAD_TIMING_SHAPE", "timing map needs non-empty sections list")
    lines = {}
    latest = 0.0
    for sec in obj["sections"]:
        if not isinstance(sec, dict) or not isinstance(sec.get("lyrics"), list):
            raise PlanError("BAD_TIMING_SHAPE", "section needs lyrics list")
        for ln in sec["lyrics"]:
            if not isinstance(ln, dict):
                raise PlanError("BAD_TIMING_SHAPE", "lyric line needs a record")
            lid = ln.get("line_id")
            if not isinstance(lid, str) or not lid.strip():
                raise PlanError("BAD_TIMING_SHAPE", "lyric line needs line_id")
            if lid in lines:
                raise PlanError("DUP_LINE_ID", "duplicate line_id %s" % lid)
            st, en = ln.get("start"), ln.get("end")
            if not _is_num(st) or not _is_num(en) or not st < en:
                raise PlanError("BAD_LINE_WINDOW", "line %s window unordered" % lid)
            lines[lid] = {"start": st, "end": en,
                          "text": ln.get("text") if isinstance(ln.get("text"), str) else "",
                          "section_id": sec.get("section_id", "")}
            latest = max(latest, en)
    dur = obj.get("duration_seconds")
    if not _is_num(dur) or dur <= 0:
        dur = latest
    return {"song_id": obj.get("song_id", ""),
            "duration_seconds": dur, "lines": lines}


def bind_plan(shots, timing, contracts=None):
    """Validate shots against timing; every lyric_line_id must resolve and
    each shot window must cover its lines. Returns ok record, raises PlanError.

    Part E E5 (lip-sync clips stay whole): a shot list that puts one
    lip-synced line in two different shots raises PlanError LIPSYNC_SPLIT
    before it can reach the assembler, which enforces the same atomicity
    on the timeline (validate_lipsync_atomic)."""
    if not isinstance(shots, list) or not shots:
        raise PlanError("EMPTY_PLAN", "shot plan must be a non-empty list")
    seen = set()
    for sh in shots:
        sid = sh.get("shot_id") if isinstance(sh, dict) else None
        if sid in seen:
            raise PlanError("DUP_SHOT_ID", "duplicate shot_id %s" % sid)
        seen.add(sid)
        errs = validate_shot(sh)
        if errs:
            raise PlanError("SHOT_INVALID", "%s: %s" % (sid, ";".join(errs)))
    t = timing if isinstance(timing, dict) and "lines" in timing else load_timing_map(timing)
    lines = t["lines"]
    # Part E E5: one lip-synced line, one shot. Declared via the shot's
    # lip_sync_line_ids (speaker_check, Decision 26) or, when absent,
    # an unsplit shot for each line is not required — plain lyric lines may
    # span shots; only lip-synced lines are atomic.
    lipsync_seen = {}
    for sh in shots:
        lids = sh.get("lip_sync_line_ids") or []
        if not isinstance(lids, list):
            raise PlanError("LIPSYNC_SPLIT_BAD_DECL",
                            "%s lip_sync_line_ids must be a list"
                            % sh["shot_id"])
        for lid in lids:
            if lid in lipsync_seen and lipsync_seen[lid] != sh["shot_id"]:
                raise PlanError(
                    "LIPSYNC_SPLIT",
                    "lip-synced line %s is planned in shots %s and %s; "
                    "a lip-sync clip is atomic and may not be split "
                    "across two segments (manual Part E E5)"
                    % (lid, lipsync_seen[lid], sh["shot_id"]))
            lipsync_seen[lid] = sh["shot_id"]
    bindings = []
    for sh in shots:
        bounds = []
        for lid in sh["lyric_line_ids"]:
            if lid not in lines:
                raise PlanError("UNBOUND_LYRIC_LINE",
                                "%s references unknown line %s" % (sh["shot_id"], lid))
            bounds.append(lines[lid])
        lo = min(b["start"] for b in bounds)
        hi = max(b["end"] for b in bounds)
        if not (sh["song_start"] <= lo and sh["song_end"] >= hi):
            raise PlanError("SHOT_WINDOW_MISMATCH",
                            "%s window [%s,%s] does not cover lines [%s,%s]"
                            % (sh["shot_id"], sh["song_start"], sh["song_end"], lo, hi))
        bindings.append({"shot_id": sh["shot_id"],
                         "line_ids": list(sh["lyric_line_ids"]),
                         "window": [sh["song_start"], sh["song_end"]],
                         "covered_text": " / ".join(b["text"] for b in bounds)})
    if contracts is not None:
        if not isinstance(contracts, dict):
            raise PlanError("CONTRACT_INVALID", "contracts must map shot_id to contract")
        for sh in shots:
            sid = sh["shot_id"]
            if sid not in contracts:
                raise PlanError("CONTRACT_MISSING", "no 14.3 contract for %s" % sid)
            errs = validate_contract(contracts[sid])
            if errs:
                raise PlanError("CONTRACT_INVALID", "%s: %s" % (sid, ";".join(errs)))
    return {"outcome": "ok", "reason_code": "plan-bound",
            "shots": [s["shot_id"] for s in shots], "bindings": bindings,
            "duration_seconds": t["duration_seconds"]}
