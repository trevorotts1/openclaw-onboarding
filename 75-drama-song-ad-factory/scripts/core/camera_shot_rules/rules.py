"""DEL-16 shot-planner rule checks — music and dialogue or narration alike.

Stdlib only. Fail-closed: every check returns a list of reason strings; an
empty list is a pass. The rules encoded here, in the order the order states
them:

  1.  one camera move per clip and clips of about four to six seconds;
  2.  whip pans and fast orbits are built as an edit transition between two
      clips (they fail in AI models), never as a single generated move;
  3.  text and logos are added in post;
  4.  prompt with the phrase "shallow depth of field" rather than an f-stop
      number (lens and f-stop words act as style cues);
  5.  shot length shrinks as shots get closer — about eight seconds for
      extreme wides down to about two and a half seconds for extreme
      close-ups;
  6.  medium shots dominate narrative film and over-used close-ups hurt the
      sense of space;
  7.  close-ups at most thirty-five percent of coverage;
  8.  at most two identical framings in a row;
  9.  every scene starts on an establishing wide;
  10. videos of two minutes or more carry at least five shot types and three
      angles;
  11. lens and aperture matched to emotion;
  12. coverage spans master, medium, close-up, reverse, insert and cutaway,
      with the one-hundred-eighty-degree rule, eyelines, scene geometry,
      shot-reverse-shot, motivated camera moves, rack focus, depth of field,
      golden-hour or low-key lighting choices and screen-direction
      continuity.

Any pacing percentage here is a planning range, not a measured standard.
"""
from __future__ import annotations

import re

try:
    from . import vocabulary as V
except ImportError:
    import vocabulary as V  # type: ignore


class RuleError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


# f-stop number (f/2.8, F2, t/2.8) and lens-in-millimeters tokens are
# style cues for video models — never in a prompt.
_FSTOP = re.compile(r"(?:\b[fFtT]/\s*\d|\b[fFtT]\d+(?:\.\d+)?\b)")
_LENS_MM = re.compile(r"\b\d+\s?mm\b", re.I)


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _framing(b):
    return b.get("framing") if isinstance(b, dict) else None


# ------------------------------------------------------------------- rules


def check_one_move_per_clip(briefs):
    """Rule 1 (moves): each clip carries exactly one camera move."""
    reasons = []
    if not isinstance(briefs, list) or not briefs:
        return ["EMPTY_PLAN: plan must be a non-empty list of briefs"]
    for i, b in enumerate(briefs):
        if not isinstance(b, dict):
            reasons.append("BRIEF_NOT_A_RECORD briefs[%d]" % i)
            continue
        move = b.get("camera_moves")
        if move is None:
            move = b.get("camera_move")
        if isinstance(move, str):
            if not move.strip():
                n = 0
            elif move.strip() == "static":
                n = -1  # explicit static: zero moves, still exactly one choice
            else:
                n = 1
        elif isinstance(move, list):
            moves = [m for m in move if isinstance(m, str) and m.strip()]
            n = len(moves) if moves != ["static"] else -1
        else:
            n = 0
        if n == 0:
            reasons.append(
                "NO_CAMERA_MOVE %s carries no camera move" %
                b.get("shot_id", "briefs[%d]" % i))
        elif n > 1:
            reasons.append(
                "MULTI_MOVE_CLIP %s declares %d camera moves; one camera "
                "move per clip (DEL-16)" %
                (b.get("shot_id", "briefs[%d]" % i), n))
    return reasons


def check_clip_length_planning_range(briefs, default_range=None,
                                     allow_override=False):
    """Rule 1 (length): clips of about four to six seconds — planning range,
    not a measured standard.

    A brief inside its framing's ladder range (rule 5) passes. A brief whose
    framing has no ladder entry must sit in the default four-to-six band.
    allow_override=True permits out-of-band lengths (a dialogue lip-sync
    window may run long) — the override is an explicit caller decision, and
    the caller is expected to label the deviation in the plan record.
    """
    reasons = []
    dlo, dhi = default_range or V.DEFAULT_CLIP_SECONDS_PLANNING_RANGE
    for i, b in enumerate(briefs):
        if not isinstance(b, dict):
            continue
        sid = b.get("shot_id", "briefs[%d]" % i)
        dur = b.get("duration_seconds")
        if not _is_num(dur) or dur <= 0:
            reasons.append("BAD_DURATION %s duration_seconds invalid" % sid)
            continue
        if allow_override:
            continue
        band = V.FRAMING_SECONDS_PLANNING_RANGE.get(_framing(b))
        if band is None:
            band = (dlo, dhi)
        lo, hi = band
        if lo - 1e-9 <= dur <= hi + 1e-9:
            continue
        reasons.append(
            "CLIP_LENGTH_OUT_OF_RANGE %s is %.2fs, planning range "
            "%.1f-%.1fs (%s; planning range, not a measured standard)"
            % (sid, dur, lo, hi, V.PLANNING_RANGE_LABEL))
    return reasons


def check_length_ladder(briefs):
    """Rule 5: shot length shrinks as shots get closer.

    Checks the ladder's integrity (extreme wides plan longer than extreme
    close-ups) and that each brief's duration band sits inside the ladder's
    overall envelope.
    """
    reasons = []
    ew = V.FRAMING_SECONDS_PLANNING_RANGE["extreme_wide"]
    ec = V.FRAMING_SECONDS_PLANNING_RANGE["extreme_close"]
    if not (ew[0] > ec[1]):
        reasons.append(
            "LADDER_INVERTED extreme_wide band %s must plan longer than "
            "extreme_close band %s" % (ew, ec))
    prev_lo = None
    for name in V.SHOT_SIZE_LADDER:
        lo, hi = V.FRAMING_SECONDS_PLANNING_RANGE[name]
        if prev_lo is not None and lo >= prev_lo:
            reasons.append(
                "LADDER_NOT_SHRINKING %s band (%.1f-%.1f) does not shrink "
                "below the wider framing" % (name, lo, hi))
        prev_lo = lo
    return reasons


def check_close_up_share(briefs, cap=None):
    """Rule 7: close-ups at most thirty-five percent of coverage."""
    cap = V.CLOSE_UP_SHARE_CAP if cap is None else cap
    if not briefs:
        return ["EMPTY_PLAN: plan must be a non-empty list of briefs"]
    close = sum(1 for b in briefs
                if isinstance(b, dict)
                and _framing(b) in V.CLOSE_UP_FRAMINGS)
    share = float(close) / float(len(briefs))
    if share > cap + 1e-9:
        return [
            "CLOSE_UP_OVERUSE %d of %d shots are close-ups (%.0f%%); cap "
            "is %.0f%% of coverage — over-used close-ups hurt the sense of "
            "space (planning range, not a measured standard)"
            % (close, len(briefs), share * 100.0, cap * 100.0)]
    return []


def check_medium_dominance(briefs, floor=None):
    """Rule 6: medium shots dominate narrative film.

    floor comes from the medium-share planning range's lower bound. A plan
    with no narrative content (pure insert/detail) is exempt; a plan that
    has medium-capable shots but starves them fails.
    """
    floor = V.MEDIUM_SHARE_PLANNING_RANGE[0] if floor is None else floor
    if not briefs:
        return ["EMPTY_PLAN: plan must be a non-empty list of briefs"]
    valid = [b for b in briefs if isinstance(b, dict)
             and _framing(b) in V.SHOT_TYPES]
    if not valid:
        return ["EMPTY_PLAN: no valid briefs"]
    mediums = sum(1 for b in valid if _framing(b) in V.MEDIUM_FRAMINGS)
    share = float(mediums) / float(len(valid))
    if mediums == 0 and len(valid) >= 3:
        return [
            "NO_MEDIUM_SHOTS narrative plan of %d shots has no medium "
            "framing; medium shots dominate narrative film (planning "
            "range, not a measured standard)" % len(valid)]
    if share + 1e-9 < floor and len(valid) >= 4:
        return [
            "MEDIUM_UNDERUSED medium share %.0f%% below planning-range "
            "floor %.0f%% (planning range, not a measured standard)"
            % (share * 100.0, floor * 100.0)]
    return []


def check_identical_framings(briefs, max_run=None):
    """Rule 8: at most two identical framings in a row."""
    max_run = V.MAX_IDENTICAL_FRAMINGS_IN_A_ROW if max_run is None else max_run
    reasons = []
    run, prev = 0, None
    for i, b in enumerate(briefs):
        if not isinstance(b, dict):
            continue
        f = _framing(b)
        if f == prev:
            run += 1
        else:
            prev, run = f, 1
        if run > max_run:
            reasons.append(
                "FRAMING_RUN %s: %d identical %s framings in a row "
                "(max %d)" % (b.get("shot_id", "briefs[%d]" % i), run, f,
                              max_run))
    return reasons


def check_scene_opens_establishing_wide(briefs, require_establishing=True):
    """Rule 9: every scene starts on an establishing wide.

    require_establishing=False accepts any wide-family framing (wide,
    extreme_wide, establishing_wide) — the wide-first rule without the
    named establishing entry.
    """
    reasons = []
    if not isinstance(briefs, list) or not briefs:
        return ["EMPTY_PLAN: plan must be a non-empty list of briefs"]
    first_by_scene = {}
    for i, b in enumerate(briefs):
        if not isinstance(b, dict):
            continue
        sid = b.get("scene_id") or "scene-1"
        if sid not in first_by_scene:
            first_by_scene[sid] = (i, b)
    ok = {"establishing_wide"} if require_establishing else {
        "establishing_wide", "extreme_wide", "wide"}
    for sid, (i, b) in first_by_scene.items():
        if _framing(b) not in ok:
            reasons.append(
                "SCENE_NO_ESTABLISHING_WIDE scene %s opens on %s "
                "(briefs[%d]); every scene starts on an establishing wide"
                % (sid, _framing(b), i))
    return reasons


def check_long_video_coverage(briefs, total_seconds):
    """Rule 10: videos of two minutes or more carry at least five shot types
    and three angles."""
    if not _is_num(total_seconds) or total_seconds < V.LONG_VIDEO_SECONDS:
        return []
    if not briefs:
        return ["EMPTY_PLAN: plan must be a non-empty list of briefs"]
    reasons = []
    types = {_framing(b) for b in briefs if isinstance(b, dict)}
    angles = {b.get("angle") for b in briefs
              if isinstance(b, dict) and b.get("angle") in V.ANGLES}
    if len(types) < V.LONG_VIDEO_MIN_SHOT_TYPES:
        reasons.append(
            "LONG_VIDEO_FEW_SHOT_TYPES %.0fs video carries %d shot types; "
            "at least %d required" % (total_seconds, len(types),
                                      V.LONG_VIDEO_MIN_SHOT_TYPES))
    if len(angles) < V.LONG_VIDEO_MIN_ANGLES:
        reasons.append(
            "LONG_VIDEO_FEW_ANGLES %.0fs video carries %d angles; at "
            "least %d required" % (total_seconds, len(angles),
                                   V.LONG_VIDEO_MIN_ANGLES))
    return reasons


def check_lens_aperture_emotion(briefs):
    """Rule 11: lens and aperture matched to emotion."""
    reasons = []
    for i, b in enumerate(briefs):
        if not isinstance(b, dict):
            continue
        sid = b.get("shot_id", "briefs[%d]" % i)
        emotion = b.get("emotion")
        match = V.EMOTION_LENS_APERTURE.get(emotion)
        if match is None:
            reasons.append("UNKNOWN_EMOTION %s emotion %r not in vocabulary"
                           % (sid, emotion))
            continue
        lens = b.get("lens_mm")
        if lens not in match["lenses"]:
            reasons.append(
                "LENS_EMOTION_MISMATCH %s: %s mm on %s (matched: %s mm)"
                % (sid, lens, emotion, ", ".join(str(x) for x in
                                                 match["lenses"])))
        intent = b.get("aperture_intent")
        if intent is None and _is_num(b.get("f_number")):
            intent = V.APERTURE_INTENT.get(float(b["f_number"]))
        if intent != match["aperture_intent"]:
            reasons.append(
                "APERTURE_EMOTION_MISMATCH %s: aperture %s on %s "
                "(matched: %s)" % (sid, intent, emotion,
                                   match["aperture_intent"]))
    return reasons


def check_post_only_overlays(briefs):
    """Rule 3: text and logos are added in post.

    A brief may carry text/logo overlay strings on the *_overlay_post
    fields; a brief that asks the generation prompt for text or a logo is
    refused.
    """
    reasons = []
    banned = ("text overlay", "on-screen text", "caption in scene",
              "burned-in text", "logo in scene", "logo on screen",
              "watermark", "title card in shot", "supers in shot")
    for i, b in enumerate(briefs):
        if not isinstance(b, dict):
            continue
        sid = b.get("shot_id", "briefs[%d]" % i)
        prompt = b.get("prompt")
        if not isinstance(prompt, str):
            continue
        low = prompt.lower()
        for token in banned:
            if token in low:
                reasons.append(
                    "TEXT_LOGO_NOT_IN_POST %s prompt asks for %r; text and "
                    "logos are added in post" % (sid, token))
        if b.get("text_overlay") and not b.get("text_overlay_post"):
            reasons.append(
                "TEXT_LOGO_NOT_IN_POST %s carries text_overlay without "
                "text_overlay_post; text is added in post" % sid)
        if b.get("logo_overlay") and not b.get("logo_overlay_post"):
            reasons.append(
                "TEXT_LOGO_NOT_IN_POST %s carries logo_overlay without "
                "logo_overlay_post; logos are added in post" % sid)
    return reasons


def check_depth_of_field_prompt(briefs):
    """Rule 4: prompt with the phrase "shallow depth of field" rather than
    an f-stop number (lens and f-stop words act as style cues)."""
    reasons = []
    for i, b in enumerate(briefs):
        if not isinstance(b, dict):
            continue
        sid = b.get("shot_id", "briefs[%d]" % i)
        prompt = b.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            reasons.append("NO_PROMPT %s has no prompt" % sid)
            continue
        low = prompt.lower()
        if _FSTOP.search(prompt) or "f-stop" in low or "f stop" in low:
            reasons.append(
                "FSTOP_IN_PROMPT %s prompt carries an f-stop number; lens "
                "and f-stop words act as style cues — prompt with the "
                "depth-of-field phrase instead" % sid)
        if _LENS_MM.search(prompt) or "mm lens" in low:
            reasons.append(
                "LENS_WORD_IN_PROMPT %s prompt names a lens in "
                "millimeters; lens words act as style cues — keep the "
                "lens in the structured fields only" % sid)
        intent = b.get("aperture_intent")
        if intent is None and _is_num(b.get("f_number")):
            intent = V.APERTURE_INTENT.get(float(b["f_number"]))
        if intent == "wide_open" and "shallow depth of field" not in low:
            reasons.append(
                "DOF_PHRASE_MISSING %s is shot wide open; the prompt must "
                "carry the phrase 'shallow depth of field'" % sid)
    return reasons


def _scenes_of(briefs):
    scenes = {}
    for i, b in enumerate(briefs):
        if not isinstance(b, dict):
            continue
        scenes.setdefault(b.get("scene_id") or "scene-1", []).append((i, b))
    return scenes


def check_degree_180_rule(briefs):
    """Rule 12: the one-hundred-eighty-degree rule.

    The camera stays on one side of the line for a scene. A shot on the
    other side must declare crosses_axis with an axis_cross_motivation; a
    break without one is an axis jump.
    """
    reasons = []
    for sid, rows in _scenes_of(briefs).items():
        axis = None
        for i, b in rows:
            side = b.get("camera_side")
            if side not in V.CAMERA_SIDES:
                reasons.append(
                    "BAD_CAMERA_SIDE scene %s briefs[%d] camera_side %r"
                    % (sid, i, side))
                continue
            if axis is None:
                axis = side
            if side == axis:
                continue
            if b.get("crosses_axis") and str(
                    b.get("axis_cross_motivation") or "").strip():
                continue
            reasons.append(
                "AXIS_JUMP scene %s briefs[%d] shoots from side %s across "
                "the line (scene side %s) without crosses_axis and an "
                "axis_cross_motivation; the one-hundred-eighty-degree rule"
                % (sid, i, side, axis))
    return reasons


def check_eyelines(briefs):
    """Rule 12: eyelines.

    Inside a scene, every shot of one subject keeps that subject's eyeline;
    the eyeline is a declared vocabulary value.
    """
    reasons = []
    seen = {}
    for sid, rows in _scenes_of(briefs).items():
        for i, b in rows:
            eye = b.get("eyeline")
            if eye not in V.EYE_LINES:
                reasons.append(
                    "BAD_EYELINE scene %s briefs[%d] eyeline %r not in %s"
                    % (sid, i, eye, V.EYE_LINES))
                continue
            key = (sid, b.get("subject_id"))
            if key in seen and seen[key] != eye:
                reasons.append(
                    "EYELINE_INCONSISTENT scene %s subject %s eyeline %s "
                    "then %s; eyelines stay consistent inside a scene"
                    % (sid, b.get("subject_id"), seen[key], eye))
            seen.setdefault(key, eye)
    return reasons


def check_scene_geometry(briefs, scenes=None):
    """Rule 12: scene geometry.

    A subject keeps one position inside a scene (a brief that contradicts
    the subject's established position is a geometry break). When a scenes
    record is supplied, every subject a shot uses must be declared in its
    scene's geometry[].
    """
    reasons = []
    declared = {}
    if isinstance(scenes, dict):
        for sid, scene in scenes.items():
            if isinstance(scene, dict):
                geo = scene.get("geometry")
                if isinstance(geo, list):
                    declared[sid] = {
                        g.get("subject_id"): g.get("position")
                        for g in geo if isinstance(g, dict)}
    positions = {}
    for sid, rows in _scenes_of(briefs).items():
        geo = declared.get(sid, {})
        for i, b in rows:
            subj = b.get("subject_id")
            pos = b.get("subject_position")
            if geo and subj not in geo:
                reasons.append(
                    "SCENE_GEOMETRY_MISSING scene %s briefs[%d] subject %r "
                    "is not in the scene geometry" % (sid, i, subj))
                continue
            if geo and subj in geo and pos is not None \
                    and pos != geo[subj]:
                reasons.append(
                    "SCENE_GEOMETRY_CONTRADICTION scene %s briefs[%d] puts "
                    "%s at %s; scene geometry says %s"
                    % (sid, i, subj, pos, geo[subj]))
                continue
            if pos is None:
                continue
            key = (sid, subj)
            if key in positions and positions[key] != pos:
                reasons.append(
                    "SCENE_GEOMETRY_CONTRADICTION scene %s subject %s sits "
                    "at %s then %s; scene geometry stays put"
                    % (sid, subj, positions[key], pos))
            positions.setdefault(key, pos)
    return reasons


def check_shot_reverse_shot(briefs):
    """Rule 12: shot-reverse-shot.

    A reverse-coverage shot sits on the same side of the line as the scene
    (see check_degree_180_rule) and looks back at the shot it answers:
    opposite eyeline, different subject.
    """
    reasons = []
    for sid, rows in _scenes_of(briefs).items():
        for pos, (i, b) in enumerate(rows):
            if b.get("coverage_role") != "reverse":
                continue
            answer = None
            for j in range(pos - 1, -1, -1):
                if rows[j][1].get("coverage_role") != "cutaway":
                    answer = rows[j]
                    break
            if answer is None:
                reasons.append(
                    "SHOT_REVERSE_SHOT_GAP scene %s briefs[%d] reverse has "
                    "no shot to answer" % (sid, i))
                continue
            ai, other = answer
            if other.get("subject_id") == b.get("subject_id"):
                reasons.append(
                    "SHOT_REVERSE_SHOT_SAME_SUBJECT scene %s reverse at "
                    "briefs[%d] answers briefs[%d] of the same subject"
                    % (sid, i, ai))
            e1, e2 = b.get("eyeline"), other.get("eyeline")
            if e1 in V.EYE_LINES and e2 in V.EYE_LINES \
                    and "center" not in (e1, e2) and e1 == e2:
                reasons.append(
                    "SHOT_REVERSE_SHOT_EYELINE scene %s reverse at "
                    "briefs[%d] and the shot it answers at briefs[%d] share "
                    "eyeline %s; reverse eyelines cross" % (sid, i, ai, e1))
    return reasons


def check_depth_of_field(briefs):
    """Rule 12: depth of field.

    A declared depth-of-field value is in the vocabulary and does not
    contradict the aperture the brief was built with.
    """
    reasons = []
    for i, b in enumerate(briefs):
        if not isinstance(b, dict):
            continue
        sid = b.get("shot_id", "briefs[%d]" % i)
        dof = b.get("depth_of_field")
        if dof not in V.DEPTH_OF_FIELD:
            reasons.append("BAD_DEPTH_OF_FIELD %s depth_of_field %r not in %s"
                           % (sid, dof, V.DEPTH_OF_FIELD))
            continue
        intent = b.get("aperture_intent")
        if intent is None and _is_num(b.get("f_number")):
            intent = V.APERTURE_INTENT.get(float(b["f_number"]))
        if intent == "wide_open" and dof == "deep":
            reasons.append(
                "DOF_APERTURE_CONTRADICTION %s is wide open but declares "
                "deep depth of field" % sid)
        if intent == "stopped_down" and dof == "shallow":
            reasons.append(
                "DOF_APERTURE_CONTRADICTION %s is stopped down but "
                "declares shallow depth of field" % sid)
        if intent == "mid" and dof in ("shallow", "deep"):
            reasons.append(
                "DOF_APERTURE_CONTRADICTION %s sits at a mid aperture but "
                "declares %s depth of field" % (sid, dof))
    return reasons


def check_shot_reverse_shot_geometry(briefs, scenes=None):
    """Rule 12 (geometry family): 180 rule + eyelines + shot-reverse-shot.

    Kept as one entry point so callers can run the whole family; each part
    is also registered on its own in the gate.
    """
    return (check_degree_180_rule(briefs) + check_eyelines(briefs)
            + check_shot_reverse_shot(briefs)
            + check_scene_geometry(briefs, scenes))


def _moves_of(b):
    """Every camera move a brief declares, as a list of strings."""
    raw = b.get("camera_moves")
    if isinstance(raw, list):
        return [m for m in raw if isinstance(m, str)]
    single = b.get("camera_move")
    return [single] if isinstance(single, str) else []


def check_edit_transitions(briefs, transitions=None):
    """Rule 2: whip pans and fast orbits are built as an edit transition
    between two clips, never as a single generated move.

    A transition of those kinds must name two different clips that exist.
    A shot may also carry transition_from (the clip it cuts from).
    """
    reasons = []
    if not isinstance(briefs, list):
        return ["SHOTS_INVALID: briefs must be a list"]
    ids = {b.get("shot_id") for b in briefs if isinstance(b, dict)}
    rows = transitions if isinstance(transitions, list) else []
    for i, t in enumerate(rows):
        if not isinstance(t, dict):
            reasons.append("BAD_TRANSITION transitions[%d] not a record" % i)
            continue
        kind = t.get("kind")
        if kind not in V.EDIT_TRANSITION_MOVES:
            continue
        a, b = t.get("from_shot"), t.get("to_shot")
        if a == b or a not in ids or b not in ids:
            reasons.append(
                "TRANSITION_MUST_BRIDGE_TWO_CLIPS transitions[%d] %r goes "
                "%r -> %r; a whip pan or fast orbit is an edit transition "
                "between two clips" % (i, kind, a, b))
    for i, shot in enumerate(briefs):
        if not isinstance(shot, dict):
            continue
        origin = shot.get("transition_from")
        if origin is None:
            continue
        if origin == shot.get("shot_id") or origin not in ids:
            reasons.append(
                "TRANSITION_MUST_BRIDGE_TWO_CLIPS briefs[%d] transition_from "
                "%r does not name a different clip in the plan"
                % (i, origin))
    return reasons


def check_motivated_camera_moves(briefs):
    """Rule 12 (motivation): motivated camera moves.

    Every non-static move must carry a motivation string; rack-focus shots
    must name the focus origin; whip pans and fast orbits never appear as a
    generated move (rule 2).
    """
    reasons = []
    for i, b in enumerate(briefs):
        if not isinstance(b, dict):
            continue
        sid = b.get("shot_id", "briefs[%d]" % i)
        moves = _moves_of(b)
        if not moves:
            reasons.append(
                "NO_CAMERA_MOVE %s declares no camera move; name one "
                "including static" % sid)
        for move in moves:
            if move in V.EDIT_TRANSITION_MOVES:
                reasons.append(
                    "WHIP_PAN_AS_MOVE %s declares %r as a generated move; "
                    "whip pans and fast orbits fail in AI models — build "
                    "them as an edit transition between two clips"
                    % (sid, move))
            if move in (None, "", "static"):
                continue
            if move not in V.CAMERA_MOVES:
                reasons.append(
                    "BAD_CAMERA_MOVE %s move %r not in the move vocabulary"
                    % (sid, move))
                continue
            motivation = b.get("camera_motivation")
            if not isinstance(motivation, str) or not motivation.strip():
                reasons.append(
                    "UNMOTIVATED_MOVE %s declares move %r without "
                    "camera_motivation; camera moves are motivated"
                    % (sid, move))
            if move == "rack-focus" and not b.get("rack_focus_from"):
                reasons.append(
                    "RACK_FOCUS_NO_ORIGIN %s declares rack-focus without "
                    "rack_focus_from" % sid)
    return reasons


def check_lighting_continuity(briefs):
    """Rule 12 (lighting): golden-hour or low-key lighting choices.

    Every brief declares a lighting choice; within a scene the choice
    changes at most once (a lighting change is a deliberate beat, not
    drift).
    """
    reasons = []
    scenes = {}
    for i, b in enumerate(briefs):
        if not isinstance(b, dict):
            continue
        sid = b.get("scene_id") or "scene-1"
        scenes.setdefault(sid, []).append((i, b))
        if b.get("lighting") not in V.LIGHTING_CHOICES:
            reasons.append(
                "NO_LIGHTING_CHOICE %s lighting %r not in %s"
                % (b.get("shot_id", "briefs[%d]" % i), b.get("lighting"),
                   V.LIGHTING_CHOICES))
    for sid, rows in scenes.items():
        changes = 0
        prev = None
        for _i, b in rows:
            light = b.get("lighting")
            if prev is not None and light != prev:
                changes += 1
            prev = light
        if changes > 1:
            reasons.append(
                "LIGHTING_DRIFT scene %s changes lighting %d times; keep a "
                "golden-hour or low-key choice stable inside a scene"
                % (sid, changes))
    return reasons


def check_screen_direction_continuity(briefs):
    """Rule 12 (screen direction): screen-direction continuity.

    Inside a scene every directional brief keeps the scene's screen
    direction; a motivated reversal is an explicit direction_change beat.
    """
    reasons = []
    scenes = {}
    for i, b in enumerate(briefs):
        if not isinstance(b, dict):
            continue
        scenes.setdefault(b.get("scene_id") or "scene-1", []).append((i, b))
    for sid, rows in scenes.items():
        prev = None
        for i, b in rows:
            d = b.get("screen_direction")
            if d not in V.SCREEN_DIRECTIONS:
                continue
            if prev is not None and d != prev and not b.get("direction_change"):
                reasons.append(
                    "SCREEN_DIRECTION_BREAK scene %s briefs[%d] flips "
                    "screen direction %s -> %s without a direction_change "
                    "beat" % (sid, i, prev, d))
            prev = d
    return reasons


def check_coverage_roles(briefs):
    """Rule 12 (coverage): coverage spans master, medium, close-up, reverse,
    insert and cutaway.

    A plan shorter than three shots is judged on the roles it can carry
    (master + medium + close_up); a full plan must span all six.
    """
    if not isinstance(briefs, list) or not briefs:
        return ["EMPTY_PLAN: plan must be a non-empty list of briefs"]
    roles = {b.get("coverage_role") for b in briefs if isinstance(b, dict)}
    required = V.REQUIRED_COVERAGE_ROLES if len(briefs) >= 3 else (
        "master", "medium", "close_up")
    reasons = []
    for role in required:
        if role not in roles:
            reasons.append(
                "COVERAGE_GAP required coverage role %r missing; coverage "
                "spans master, medium, close-up, reverse, insert and "
                "cutaway" % role)
    return reasons


def check_vocabulary_carried(briefs):
    """Every brief carries the full vocabulary block."""
    reasons = []
    for i, b in enumerate(briefs):
        if not isinstance(b, dict):
            continue
        sid = b.get("shot_id", "briefs[%d]" % i)
        missing = V.missing_from(b.get("vocabulary"))
        if missing:
            reasons.append(
                "VOCABULARY_INCOMPLETE %s: %s" % (sid, ", ".join(missing[:8])))
    return reasons


def check_content_mode_parity(briefs):
    """The same rules apply for music and for dialogue or narration alike.

    Every brief declares a content mode from the vocabulary; a plan mixing
    modes is fine, an undeclared mode is not.
    """
    reasons = []
    for i, b in enumerate(briefs):
        if not isinstance(b, dict):
            continue
        if b.get("content_mode") not in V.CONTENT_MODES:
            reasons.append(
                "BAD_CONTENT_MODE briefs[%d] content_mode %r not in %s"
                % (i, b.get("content_mode"), V.CONTENT_MODES))
    return reasons


# --------------------------------------------------------------- the gate

def plan_total_seconds(briefs):
    """Sum of brief durations; 0.0 when unmeasurable."""
    total = 0.0
    for b in briefs:
        if isinstance(b, dict) and _is_num(b.get("duration_seconds")):
            total += float(b["duration_seconds"])
    return total


def run_rule_checks(briefs, total_seconds=None, allow_length_override=False,
                    scenes=None, transitions=None):
    """Run every DEL-16 rule over a plan. Returns a result record.

    scenes maps scene_id -> {"geometry": [{"subject_id", "position"}]};
    without it the scene-geometry check judges whether each scene declares
    its geometry at all.

    result["reasons"] is a flat list of reason strings (empty == pass);
    result["checks"] maps check name -> its reasons so evidence can quote
    each rule running.
    """
    if not isinstance(briefs, list):
        return {"outcome": "rejected", "reason_code": "SHOTS_INVALID",
                "reasons": ["SHOTS_INVALID: briefs must be a list"],
                "checks": {}}
    if total_seconds is None:
        total_seconds = plan_total_seconds(briefs)
    checks = [
        ("content_mode_parity", lambda: check_content_mode_parity(briefs)),
        ("vocabulary_carried", lambda: check_vocabulary_carried(briefs)),
        ("one_move_per_clip", lambda: check_one_move_per_clip(briefs)),
        ("clip_length_planning_range",
         lambda: check_clip_length_planning_range(
             briefs, allow_override=allow_length_override)),
        ("length_ladder", lambda: check_length_ladder(briefs)),
        ("edit_transition_not_move", lambda: [
            r for r in check_motivated_camera_moves(briefs)
            if r.startswith("WHIP_PAN_AS_MOVE")]),
        ("edit_transitions_bridge_two_clips",
         lambda: check_edit_transitions(briefs, transitions)),
        ("motivated_camera_moves", lambda: [
            r for r in check_motivated_camera_moves(briefs)
            if not r.startswith("WHIP_PAN_AS_MOVE")]),
        ("post_only_overlays", lambda: check_post_only_overlays(briefs)),
        ("depth_of_field_prompt", lambda: check_depth_of_field_prompt(briefs)),
        ("close_up_share", lambda: check_close_up_share(briefs)),
        ("medium_dominance", lambda: check_medium_dominance(briefs)),
        ("identical_framings", lambda: check_identical_framings(briefs)),
        ("scene_opens_establishing_wide",
         lambda: check_scene_opens_establishing_wide(briefs)),
        ("long_video_coverage",
         lambda: check_long_video_coverage(briefs, total_seconds)),
        ("lens_aperture_emotion", lambda: check_lens_aperture_emotion(briefs)),
        ("degree_180_rule", lambda: check_degree_180_rule(briefs)),
        ("eyelines", lambda: check_eyelines(briefs)),
        ("shot_reverse_shot", lambda: check_shot_reverse_shot(briefs)),
        ("scene_geometry",
         lambda: check_scene_geometry(briefs, scenes)),
        ("lighting_continuity", lambda: check_lighting_continuity(briefs)),
        ("screen_direction_continuity",
         lambda: check_screen_direction_continuity(briefs)),
        ("coverage_roles", lambda: check_coverage_roles(briefs)),
        ("depth_of_field", lambda: check_depth_of_field(briefs)),
    ]
    checks_out = {}
    flat = []
    for name, fn in checks:
        reasons = fn()
        checks_out[name] = reasons
        flat.extend(reasons)
    if flat:
        return {"outcome": "rejected",
                "reason_code": "+".join(sorted(
                    {r.split(" ", 1)[0] for r in flat})),
                "reasons": flat, "checks": checks_out,
                "total_seconds": total_seconds}
    return {"outcome": "ok", "reason_code": "DEL16_RULES_PASS",
            "reasons": [], "checks": checks_out,
            "total_seconds": total_seconds}
