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

# Part E E3 (manual 02): a real ad was chopped into 29 hard-cut pieces with
# 8 under 1.5 s and one 0.39 s. Planning floor: every produced segment is at
# least MIN_SHOT_S (1.5 s), or BEAT_CUT_MIN_SHOT_S (1.0 s) when the boundary
# it starts on is marked beat_cut. Overridable via validate_timeline_min_shot
# /plan_shot_floor arguments. Shorter segments are merged into their neighbour
# or extended; storyboard scene order is never reordered.
MIN_SHOT_S = 1.5
BEAT_CUT_MIN_SHOT_S = 1.0


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
    """
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


def _segment_seconds(seg):
    """Segment duration in seconds from a timeline/segment record.

    Accepts song_start/song_end (shot records) or dur (blackceo.timeline
    segments). Unknown shape -> None (caller decides fail-open/closed).
    """
    if not isinstance(seg, dict):
        return None
    if _is_num(seg.get("song_start")) and _is_num(seg.get("song_end")) \
            and seg["song_start"] < seg["song_end"]:
        return float(seg["song_end"]) - float(seg["song_start"])
    if _is_num(seg.get("dur")) and seg["dur"] > 0:
        return float(seg["dur"])
    return None


def _is_beat_cut(seg):
    """True when this segment's boundary is marked as an on-beat cut."""
    return bool(isinstance(seg, dict) and seg.get("beat_cut"))


def plan_shot_floor(shots, floor=MIN_SHOT_S, beat_cut_floor=BEAT_CUT_MIN_SHOT_S,
                    lip_sync_atomic=False):
    """Enforce the E3 minimum shot length at planning time. In-place on a
    shot-list ordered by storyboard scene order; order is never changed.

    A shot shorter than its applicable floor (beat_cut shots get
    beat_cut_floor, everyone else floor) is:
      - MERGED into its neighbour when merging preserves adjacency and
        does not break an atomic lip-sync clip; the surviving shot keeps
        the earlier shot_id and lyric_line_ids of both are concatenated;
      - EXTENDED otherwise (lip_sync_atomic=True, or no mergeable
        neighbour): song_end grows by the shortfall, or song_start is
        pulled back for a leading shot whose extension would collide
        with its predecessor — a lip-sync clip is never split.

    lip_sync_atomic=True asserts every shot is an E5 atomic lip-sync
    clip, so merging is always refused and short shots extend.

    Returns (shots, report) with report rows
    {shot_id, action, before_s, after_s, floor_s}. Raises PlanError
    SHOTS_INVALID on a non-list, and PLAN_ERROR_SHAPE on bad records.
    """
    if not isinstance(shots, list):
        raise PlanError("SHOTS_INVALID", "shots must be a list")
    if not shots:
        return shots, []
    if not _is_num(floor) or floor <= 0 or not _is_num(beat_cut_floor) \
            or beat_cut_floor <= 0 or beat_cut_floor > floor:
        raise PlanError("FLOORS_INVALID", "floors must be positive, "
                        "beat_cut_floor <= floor")
    out = list(shots)
    # Validate shape once: each shot needs an ordered window (or, for the
    # timeline-segment shape, a dur).
    for i, sh in enumerate(out):
        if not isinstance(sh, dict):
            raise PlanError("PLAN_ERROR_SHAPE", "shot %d not a record" % i)
        if _segment_seconds(sh) is None:
            raise PlanError("PLAN_ERROR_SHAPE",
                            "shot %d has no usable duration window" % i)
    report = []
    i = 0
    while i < len(out):
        sh = out[i]
        floor_i = beat_cut_floor if _is_beat_cut(sh) else floor
        dur = _segment_seconds(sh)
        if dur >= floor_i:
            i += 1
            continue
        before = dur
        merged = False
        if not lip_sync_atomic:
            # Prefer merging into the NEXT neighbour (keeps later shots in
            # place); fall back to the PREVIOUS neighbour. Two refusals:
            #  - a gap between neighbour windows means the merge would
            #    splice different camera time — extend instead;
            #  - either side is an E5 lip-sync atomic clip — extending a
            #    lip-sync clip's neighbours is allowed, but merging a
            #    lip-sync shot itself would destroy its line window —
            #    extend instead.
            if i + 1 < len(out) and not _is_beat_cut(out[i]):
                nxt = out[i + 1]
                if not _is_beat_cut(nxt) \
                        and not (nxt.get("lip_sync") or sh.get("lip_sync")) \
                        and _is_num(nxt.get("song_start")) \
                        and _is_num(sh.get("song_end")) \
                        and float(nxt["song_start"]) - float(sh["song_end"]) < 1e-6:
                    sh["song_end"] = float(nxt["song_end"])
                    sh["lyric_line_ids"] = list(
                        (sh.get("lyric_line_ids") or [])
                        + (nxt.get("lyric_line_ids") or []))
                    out.pop(i + 1)
                    merged = True
            if not merged and i > 0 and not _is_beat_cut(sh):
                prev = out[i - 1]
                if not _is_beat_cut(prev) \
                        and not (prev.get("lip_sync") or sh.get("lip_sync")) \
                        and _is_num(prev.get("song_end")) \
                        and _is_num(sh.get("song_start")) \
                        and float(sh["song_start"]) - float(prev["song_end"]) < 1e-6:
                    prev["song_end"] = float(sh["song_end"])
                    prev["lyric_line_ids"] = list(
                        (prev.get("lyric_line_ids") or [])
                        + (sh.get("lyric_line_ids") or []))
                    out.pop(i)
                    merged = True
                    i -= 1
        if not merged:
            # Extend: grow into free time. End-first; when the next shot
            # (or the end of measured time) blocks song_end, pull
            # song_start back instead. Lip-sync shots extend, never split.
            shortfall = floor_i - dur
            if i + 1 < len(out):
                next_start = float(out[i + 1]["song_start"])
            else:
                next_start = float(sh["song_end"]) + shortfall * 4
            room_end = next_start - float(sh["song_end"])
            if room_end >= shortfall - 1e-9:
                sh["song_end"] = float(sh["song_end"]) + shortfall
            else:
                if i > 0 and _is_num(sh.get("song_start")) \
                        and _is_num(out[i - 1].get("song_end")):
                    prev_end = float(out[i - 1]["song_end"])
                else:
                    prev_end = 0.0
                room_start = float(sh["song_start"]) - prev_end
                grab = min(shortfall, room_start) if room_start > 0 else shortfall
                sh["song_start"] = float(sh["song_start"]) - grab
                sh["song_end"] = float(sh["song_end"]) \
                    + max(0.0, shortfall - grab)
        report.append({"shot_id": sh.get("shot_id", ""),
                       "action": "merged" if merged else "extended",
                       "before_s": round(before, 6),
                       "after_s": round(_segment_seconds(sh), 6),
                       "floor_s": floor_i})
        i += 1
    return out, report


def validate_timeline_min_shot(timeline, floor=MIN_SHOT_S,
                               beat_cut_floor=BEAT_CUT_MIN_SHOT_S):
    """E3 QC check for the final gate: every timeline segment meets its
    applicable minimum shot length (floor, or beat_cut_floor when the
    segment is marked beat_cut). Never reorders or mutates.

    timeline: blackceo.timeline/v1 dict (segments[].dur) or a bare segment
    list. Returns [reason strings]; reasons carry SEGMENT_TOO_SHORT plus
    the segment index, measured length and applied floor:
      "SEGMENT_TOO_SHORT segments[2] 0.39s < floor 1.50s"
    An empty segments list is vacuously ok: this check guards length, not
    count (coverage floors live in other checks).
    """
    if isinstance(timeline, dict):
        segs = timeline.get("segments")
        path = "segments"
    elif isinstance(timeline, list):
        segs = timeline
        path = "segments"
    else:
        return ["TIMELINE_BAD_SHAPE: timeline must be a dict or list"]
    if not isinstance(segs, list):
        return ["TIMELINE_BAD_SHAPE: segments[] required"]
    errors = []
    for i, seg in enumerate(segs):
        floor_i = beat_cut_floor if _is_beat_cut(seg) else floor
        dur = _segment_seconds(seg)
        if dur is None:
            errors.append("TIMELINE_BAD_SEGMENT segments[%d] has no usable "
                          "duration" % i)
            continue
        if dur < floor_i:
            errors.append(
                "SEGMENT_TOO_SHORT %s[%d] %.2fs < floor %.2fs"
                % (path, i, dur, floor_i))
    return errors
