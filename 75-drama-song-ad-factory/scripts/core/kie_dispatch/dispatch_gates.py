#!/usr/bin/env python3
"""dispatch_gates.py: pre-spend gates for the governed KIE dispatcher.

Every gate is a pure function of (model, request) returning None (allowed)
or {"code", "detail"}. `_dispatch_pipeline` calls them in one block after
the F-MODEL-AUTH lock and before any ledger row or spend.

Each gate is inert until its producing unit writes the record it reads
(request["style_lock"], request["bible"], request["picture_gate"],
request["shot"], request["step"], request["lip_sync"]). That is how a
single wave can land the enforcement point without a half-built producer
refusing every job in the skill.

Rows: N-12 (lip-sync fixed, LIPSYNC_MODEL_MISMATCH), N-32 (route lock),
N-34 (style block from lock), N-41 (keyframes from references),
N-42 (the clip call, WRONG_CALL_FOR_STEP), N-71 (expression),
N-83 (video burst after the picture gate), N-101 (lip-sync length),
N-119 / N-122 (Cast Lock and Bible Guard), G-FACE-01 / R-5 (FAIL stills
never dispatch), R-4 (pre-spend motion probe, advice only under N-03).
"""
from __future__ import annotations

TOOL_NAME = "dispatch_gates"
TOOL_VERSION = "1.0.0"

LIPSYNC_MODEL = "omnihuman-2-0"

# N-42: the exact call for each step (section 3C.1 table).
STEP_MODEL = {
    "first_picture": "gpt-image-2-6/sunburst-text-to-image",
    "reference_set": "gpt-image-2-6/sunburst-image-to-image",
    "keyframe": "gpt-image-2-6/sunburst-image-to-image",
    "storyboard_picture": "gpt-image-2-6/sunburst-image-to-image",
    "story_clip": "minimax-h3/image-to-video",
    "wide_group": "minimax-h3/reference-to-video",
    "lipsync": LIPSYNC_MODEL,
}

# N-71: words that contradict the beat's emotion tag (section 3G.3).
EMOTION_CONTRADICTS = {
    "pain": ("smiling", "smile", "grin", "beaming", "laughing", "cheerful",
             "teeth showing"),
    "worry": ("smiling", "smile", "grin", "beaming", "laughing", "cheerful"),
    "exhaustion": ("smiling", "smile", "grin", "beaming", "laughing"),
    "anger": ("smiling", "smile", "grin", "beaming", "laughing"),
    "resolve": ("smiling", "smile", "grin", "beaming", "laughing",
                "teeth showing"),
    "joy": ("frowning", "scowling", "tearful"),
}

# N-101 (section 3.3a): a lip-sync piece is whole sentences, 5 to 30 s.
LIPSYNC_MIN_S = 5.0
LIPSYNC_MAX_S = 30.0


def _ref(code, detail):
    return {"ok": False, "code": code, "detail": detail}


def _inp(request):
    return request.get("input") if isinstance(request, dict) and isinstance(
        request.get("input"), dict) else {}


def _first(request, *names):
    """First present value among dotted-free top-level/input/shot fields."""
    req = request if isinstance(request, dict) else {}
    shot = req.get("shot") if isinstance(req.get("shot"), dict) else {}
    inp = _inp(req)
    for name in names:
        for bag in (req, shot, inp):
            if name in bag and bag[name] is not None:
                return bag[name]
    return None


def _is_lipsync_row(model, request):
    req = request if isinstance(request, dict) else {}
    if (model or "").strip() == LIPSYNC_MODEL:
        return True
    if model and ("ai-avatar" in str(model) or "infinitalk" in str(model)
                  or "omnihuman" in str(model)):
        return True
    return bool(_first(req, "lip_sync", "lipsync")) is True


def lipsync_refusal(model, request):
    """N-12 + N-101 + section 3C.1a: the fixed model, run plain, 5-30 s."""
    req = request if isinstance(request, dict) else {}
    if not _is_lipsync_row(model, req):
        return None
    if (model or "").strip() != LIPSYNC_MODEL:
        return _ref("LIPSYNC_MODEL_MISMATCH",
                    "the lip-sync model is %s on every run; %r is not it "
                    "(no alternative, no backup)" % (LIPSYNC_MODEL, model))
    if _first(req, "lip_sync", "lipsync") is False:
        return _ref("ROUTE_CHANGED",
                    "%s rides ONLY lip_sync:true shots (talking or singing); "
                    "re-plan as an H3 remake" % LIPSYNC_MODEL)
    prompt = _first(req, "prompt")
    if isinstance(prompt, str) and prompt.strip():
        return _ref("LIPSYNC_PROMPT_PRESENT",
                    "a lip-sync job carries no prompt: picture + audio only")
    wm = _first(req, "enable_watermark")
    if wm is not None and wm is not False:
        return _ref("LIPSYNC_WATERMARK_ON",
                    "enable_watermark must be false (the provider default is "
                    "true)")
    pics = _first(req, "image_urls")
    if isinstance(pics, list) and len(pics) != 1:
        return _ref("LIPSYNC_MULTI_PICTURE",
                    "exactly one picture per lip-sync job (got %d)"
                    % len(pics))
    audio = _first(req, "audio_duration_s", "audio_seconds")
    if isinstance(audio, (int, float)) and not isinstance(audio, bool):
        if audio < LIPSYNC_MIN_S:
            return _ref("LIPSYNC_AUDIO_TOO_SHORT",
                        "%.2f s of audio is under the %.1f s floor: join the "
                        "same singer's whole sentence" % (audio, LIPSYNC_MIN_S))
        if audio > LIPSYNC_MAX_S:
            return _ref("LIPSYNC_AUDIO_TOO_LONG",
                        "%.2f s of audio is over %.1f s: stitch at a breath"
                        % (audio, LIPSYNC_MAX_S))
    if _first(req, "cuts_sentence") is True:
        return _ref("LIPSYNC_CUTS_SENTENCE",
                    "the audio starts or ends inside a sentence: nobody is "
                    "cut off, for any reason")
    return None


def take_length_refusal(audio_s, clip_s):
    """N-101 / gate G1: the returned clip is shorter than its audio."""
    try:
        a, c = float(audio_s), float(clip_s)
    except (TypeError, ValueError):
        return _ref("LIPSYNC_TAKE_SHORT", "unreadable take length")
    if c + 0.05 < a:
        return _ref("LIPSYNC_TAKE_SHORT",
                    "clip %.2f s is shorter than its %.2f s audio" % (c, a))
    return None


def route_lock_refusal(model, request):
    """N-32: image-to-video only; first frame is this run's keyframe."""
    req = request if isinstance(request, dict) else {}
    mid = str(model or "")
    if _first(req, "neighbour_clip_fallback") is True:
        return _ref("CLIP_NOT_FROM_RUN_KEYFRAME",
                    "no neighbour's clip as a fallback: every clip comes "
                    "from this shot's own keyframe")
    if _first(req, "has_keyframes") is True and "text-to-video" in mid:
        return _ref("WRONG_CALL_FOR_STEP",
                    "text-to-video is refused in a build that has keyframes; "
                    "use image-to-video from this shot's keyframe")
    fp = _first(req, "first_frame_fingerprint", "first_frame_sha256")
    run_kf = _first(req, "run_keyframes")
    if isinstance(fp, str) and fp and isinstance(run_kf, (list, tuple, set)) \
            and run_kf and fp not in run_kf:
        return _ref("CLIP_NOT_FROM_RUN_KEYFRAME",
                    "first frame %s is not one of this run's keyframes"
                    % fp[:12])
    return None


def keyframe_refusal(model, request):
    """N-41: a frame with a known character is image-to-image from references."""
    req = request if isinstance(request, dict) else {}
    step = str(_first(req, "step") or "").lower()
    if step not in ("keyframe", "storyboard_picture"):
        return None
    chars = _first(req, "character_ids", "cast")
    if not chars:
        return None
    if "text-to-image" in str(model or ""):
        return _ref("KEYFRAME_NOT_FROM_REFERENCES",
                    "a keyframe with a known character is image-to-image, "
                    "never text-to-image")
    refs = _first(req, "reference_fingerprints")
    if not isinstance(refs, (list, tuple)) or not refs:
        return _ref("KEYFRAME_NOT_FROM_REFERENCES",
                    "no character reference pictures are attached")
    return None


def wrong_call_refusal(model, request):
    """N-42: the exact model id for the step (section 3C.1 table)."""
    req = request if isinstance(request, dict) else {}
    step = str(_first(req, "step") or "").lower()
    want = STEP_MODEL.get(step)
    if not want:
        return None
    got = str(model or "")
    if got == want:
        return None
    if step == "keyframe" and got == STEP_MODEL["keyframe"]:
        return None
    return _ref("WRONG_CALL_FOR_STEP",
                "step %r is %s; %r is not that call" % (step, want, got))


def style_lock_refusal(model, request):
    """N-34: a prompt's style section comes from the lock, stamped."""
    req = request if isinstance(request, dict) else {}
    lock = req.get("style_lock")
    if not isinstance(lock, dict):
        return None
    stamp = req.get("style_stamp")
    if not isinstance(stamp, dict):
        return _ref("STYLE_BLOCK_NOT_FROM_LOCK",
                    "the prompt carries no style stamp; the builder stamps "
                    "every prompt from the look lock")
    if stamp.get("version") != lock.get("version"):
        return _ref("STYLE_BLOCK_NOT_FROM_LOCK",
                    "style stamp version %r is not the lock's %r"
                    % (stamp.get("version"), lock.get("version")))
    fp = lock.get("fingerprint")
    if fp and stamp.get("fingerprint") != fp:
        return _ref("STYLE_BLOCK_NOT_FROM_LOCK",
                    "the style section does not match the look lock byte for "
                    "byte")
    block = req.get("style_block")
    if isinstance(block, str) and block:
        allowed = {str(lock.get(k) or "") for k in
                   ("h3_block", "keyframe_clause")}
        if block not in allowed:
            return _ref("STYLE_BLOCK_NOT_FROM_LOCK",
                        "the style words are not the locked block")
    return None


def expression_refusal(model, request):
    """N-71: every prompt for a shot with a person carries its expression."""
    req = request if isinstance(request, dict) else {}
    has_person = (_first(req, "has_person") is True
                  or bool(_first(req, "cast", "character_ids")))
    if not has_person:
        return None
    if req.get("style_lock") is not None and "expression" not in req:
        return _ref("EXPRESSION_MISSING",
                    "the prompt carries no expression: the beat sheet's "
                    "emotion, intensity and cues go into every prompt")
    tag = str(_first(req, "emotion") or "").lower()
    if not tag:
        return _ref("EXPRESSION_MISSING",
                    "the prompt carries no expression tag")
    text = str(_first(req, "expression_text", "prompt") or "").lower()
    for word in EMOTION_CONTRADICTS.get(tag, ()):
        if word in text:
            return _ref("EXPRESSION_CONTRADICTS",
                        "%r contradicts the %r emotion tag" % (word, tag))
    return None


def bible_guard_refusal(model, request):
    """N-119 + N-122 part 1: nobody and nowhere is invented in a shot."""
    req = request if isinstance(request, dict) else {}
    bible = req.get("bible")
    if not isinstance(bible, dict):
        return None
    cast = [str(c) for c in (bible.get("cast") or [])]
    places = [str(p) for p in (bible.get("locations") or [])]
    shot_cast = [str(c) for c in (_first(req, "cast", "character_ids") or [])]
    for cid in shot_cast:
        if cid not in cast:
            return _ref("CAST_NOT_IN_BIBLE",
                        "%r is in this shot and not in the Character Bible; "
                        "create and lock the entry first" % cid)
    attached = [str(c) for c in (bible.get("attached_cast") or [])]
    for cid in shot_cast:
        if cid not in attached:
            return _ref("CAST_REFERENCE_MISSING",
                        "%r's locked pictures are not attached" % cid)
    place = _first(req, "location_id", "place_id")
    if isinstance(place, str) and place:
        if place not in places:
            return _ref("LOCATION_NOT_IN_WORLD_BIBLE",
                        "%r has no World Bible entry; create and lock it "
                        "first" % place)
        attached_world = [str(w) for w in (bible.get("attached_world") or [])]
        if place not in attached_world:
            return _ref("WORLD_REFERENCE_MISSING",
                        "the place reference for %r is not attached" % place)
    if req.get("unnamed_person_in_prompt") is True:
        return _ref("UNNAMED_PERSON_IN_PROMPT",
                    "a person is described in words with no id behind them")
    if req.get("unnamed_place_in_prompt") is True:
        return _ref("UNNAMED_PLACE_IN_PROMPT",
                    "a room is described in words with no id behind them")
    blocks = req.get("identity_blocks")
    if isinstance(blocks, dict):
        for cid, owner in blocks.items():
            if str(owner) != str(cid):
                return _ref("IDENTITY_BLOCK_WRONG_CHARACTER",
                            "the identity block for %r belongs to %r"
                            % (cid, owner))
    return None


def picture_gate_refusal(model, request, choir_row=False):
    """G-FACE-01 + R-5 + N-83: FAIL stills never dispatch; one face.

    A FAIL verdict has no measure-but-proceed path. An avatar source still
    needs exactly one face (one or two large faces on a choir-row take,
    N-07 / S-8) and a lead face at least 25 percent of the frame height.
    """
    req = request if isinstance(request, dict) else {}
    if not choir_row:
        _shot = req.get("shot") if isinstance(req.get("shot"), dict) else {}
        choir_row = bool(req.get("choir_row") or _shot.get("choir_row")
                         or req.get("take_kind") == "choir")
    gate = req.get("picture_gate")
    if isinstance(gate, dict):
        if str(gate.get("verdict") or "").upper() == "FAIL":
            return _ref("LIPSYNC_PICTURE_NOT_GATED",
                        "a FAIL still never dispatches; the verdict is not "
                        "'recorded as measured' into a paid job")
        faces = gate.get("face_count")
        if isinstance(faces, int) and not isinstance(faces, bool):
            allowed = (1, 2) if choir_row else (1,)
            if faces not in allowed:
                return _ref("LIPSYNC_PICTURE_NOT_GATED",
                            "the avatar source still shows %d faces; %s "
                            "required" % (faces,
                                          "1 (lead take)" if not choir_row
                                          else "1 or 2 large faces"))
        height = gate.get("face_height_pct")
        if isinstance(height, (int, float)) and not isinstance(height, bool) \
                and height < 25:
            return _ref("LIPSYNC_PICTURE_NOT_GATED",
                        "the lead face is %.1f%% of the frame height; under "
                        "25%% never feeds the avatar" % height)
    if req.get("picture_gate_passed") is False and _is_clip_row(model, req):
        return _ref("PICTURE_GATE_NOT_PASSED",
                    "no H3 or lip-sync job is sent until the picture gate "
                    "has passed")
    return None


def _is_clip_row(model, request):
    req = request if isinstance(request, dict) else {}
    if _is_lipsync_row(model, req):
        return True
    mid = str(model or "")
    return ("image-to-video" in mid or "reference-to-video" in mid
            or req.get("video_job") is True)


def staggered_send_refusal(ready_count, batch_send):
    """N-79: the dispatcher offers only a batch send; no drip, no test batch."""
    try:
        ready = int(ready_count or 0)
    except (TypeError, ValueError):
        return None
    if ready > 1 and not batch_send:
        return _ref("STAGGERED_SEND",
                    "%d ready jobs belong in one burst paced at 20 per 15 s; "
                    "never one by one" % ready)
    return None


def motion_probe_advice(request):
    """R-4: one cheap probe measured before a full blast. Advice only (N-03)."""
    req = request if isinstance(request, dict) else {}
    if req.get("motion_probe_required") is True and not req.get("motion_probe"):
        return {"ok": True, "code": "MOTION_PROBE_MISSING",
                "severity": "advice",
                "detail": "no pre-spend motion probe recorded; the motion "
                          "score is advice, never a block (N-03)"}
    return None
