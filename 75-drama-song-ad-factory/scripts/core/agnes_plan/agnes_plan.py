#!/usr/bin/env python3
"""agnes_plan: fixed 10-second Agnes segments and the prompts for them.

SPEC A5 (decided): the Agnes path does not ask for one clip per shot. It cuts
the delivered timeline D into ``ceil(D / 10)`` fixed windows of ``seconds
"10"``, the last one trimmed to D, behind a hard 5-minute cap. SPEC A7 gives
the lip-sync close-up prompt. Trial A measured the prompt structure that works
(RESEARCH.md test A): character bible, style bible, framing, setting, a
second-by-second nine-channel direction, physics, continuity, the text ban,
palette, expression library, self-check.

Pure functions, stdlib only: no file, no network, no key, no spend. The
5,000-20,000 character band belongs to the door (``agnes_dispatch``), which is
why ``video_prompt`` hands back the count instead of judging it.

Run: python3 -m pytest -q scripts/core/agnes_plan
"""
from __future__ import annotations

import math

TOOL_NAME = "agnes_plan"
TOOL_VERSION = "0.1.0"

#: One Agnes clip is exactly ``seconds "10"`` (SPEC A5.1; the door refuses any
#: other value locally).
SEGMENT_S = 10

#: The Agnes 5-minute cap (SPEC A5.1, Trevor 2026-10-13): 5 min = 300 s of
#: clips + 20% retakes = 360 s, which still fits the 500-second day with room
#: for a redo. The same number anchors the quota ledger (agnes_quota); this
#: module stays pure and does not import it.
AGNES_MAX_DELIVERED_S = 298

#: SPEC A5.3: need = clips x 10 x 1.2 (20% retakes).
ALLOWANCE = 1.2

#: SPEC A6: every still and every video prompt carries this block.
NO_TEXT_BLOCK = ("No words, letters, numbers, logos or signage anywhere in "
                 "the image.")

#: The nine channels of the trial A second-by-second direction (RESEARCH, test
#: A: body, head, face, arms, legs, hair/clothing, props, camera, light).
CHANNELS = ("body", "head", "face", "arms", "legs", "hair/clothing", "props",
            "camera", "light")


class PlanError(ValueError):
    """An input the planner cannot use. Fail loud, carry a code and a reason."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def _bad(why):
    return PlanError("AGNES_PLAN_INPUT", why)


def _length(delivered_s):
    """The delivered length in seconds, behind the 5-minute Agnes cap."""
    if isinstance(delivered_s, bool) or not isinstance(delivered_s, (int, float)):
        raise _bad("delivered length must be seconds, got %r" % (delivered_s,))
    if delivered_s <= 0:
        raise _bad("delivered length must be over 0 s, got %r" % (delivered_s,))
    if delivered_s > AGNES_MAX_DELIVERED_S:
        raise PlanError("AGNES_LENGTH_CAP",
                        "Agnes is capped at 5 minutes: %s s delivered is over "
                        "%s s (SPEC A5.1, Trevor 2026-10-13); 7- and 10-minute "
                        "episodes are KIE-only"
                        % (delivered_s, AGNES_MAX_DELIVERED_S))
    return float(delivered_s)


def segments(delivered_s):
    """The fixed windows: ``ceil(D/10)`` of them, last one trimmed to D.

    Returns ``[{"index": 1, "start_s": 0.0, "end_s": 10.0}, ...]``; ``index``
    is 1-based so a caller can say "segment 3". Raises
    ``PlanError("AGNES_LENGTH_CAP")`` past the 5-minute cap.
    """
    d = _length(delivered_s)
    n = int(math.ceil(d / SEGMENT_S))
    return [{"index": i,
             "start_s": float((i - 1) * SEGMENT_S),
             "end_s": min(float(i * SEGMENT_S), d)}
            for i in range(1, n + 1)]


def lipsync_cutaways(segments, lipsync_windows):
    """Map each KIE close-up window onto the Agnes segment it covers.

    A window is ``{"start_s": 23.0, "end_s": 27.5}`` or
    ``{"start_s": 23.0, "duration_s": 4.5}``. The Agnes clip still covers its
    full 10 s and the cutaway is laid over it inside its own window, so a
    cutaway never needs a second Agnes clip (SPEC A5.1). Returns
    ``[{"start_s", "end_s", "segment_index"}]`` in the order given.
    """
    if not segments:
        raise _bad("no segments to map a lip-sync window onto")
    out = []
    for w in lipsync_windows:
        if not isinstance(w, dict) or "start_s" not in w:
            raise _bad("a lip-sync window needs start_s, got %r" % (w,))
        try:
            start = float(w["start_s"])
            end = float(w["end_s"]) if "end_s" in w else start + float(w["duration_s"])
        except (KeyError, TypeError, ValueError):
            raise _bad("a lip-sync window needs end_s or duration_s, got %r"
                       % (w,)) from None
        if math.isnan(start) or math.isnan(end) or end < start:
            raise _bad("a lip-sync window runs backwards or is not a number: %r"
                       % (w,))
        last = segments[-1]
        if start < segments[0]["start_s"] or start > last["end_s"]:
            raise _bad("lip-sync window starts at %s s, outside the %s-%s s "
                       "delivered timeline" % (start, segments[0]["start_s"],
                                               last["end_s"]))
        hit = last
        for s in segments:
            if start < s["end_s"]:
                hit = s
                break
        out.append({"start_s": start, "end_s": end,
                    "segment_index": hit["index"]})
    return out


def need(segments, shapes):
    """What one run costs the Agnes day: ``{"video_seconds", "images",
    "allowance_seconds"}`` (SPEC A5.2/A5.3: clips x 10 x shapes, plus the 20%
    retake allowance).

    ``segments`` is the list from ``segments()`` (a bare clip count is
    accepted too); ``shapes`` is the list of looks the run makes, one clip and
    one still per shape per segment.
    """
    if isinstance(segments, bool) or not isinstance(segments, (int, float, list, tuple)):
        raise _bad("need() takes the windows from segments() or a clip count, "
                   "got %r" % (type(segments).__name__,))
    clips = int(segments) if isinstance(segments, (int, float)) else len(segments)
    if clips < 0:
        raise _bad("a run cannot have a negative clip count")
    try:
        per_shape = len(shapes)
    except TypeError:
        raise _bad("shapes must be the list of looks, got %r"
                   % (type(shapes).__name__,)) from None
    video_seconds = clips * SEGMENT_S * per_shape
    return {"video_seconds": video_seconds,
            "images": clips * per_shape,
            "allowance_seconds": round(video_seconds * ALLOWANCE)}


def _beats(blueprint):
    """The blueprint's story beats, ordered (SPEC C1)."""
    beats = blueprint.get("story_beats") if isinstance(blueprint, dict) else None
    if not isinstance(beats, list) or not beats:
        raise _bad("blueprint needs a non-empty story_beats[] (SPEC C1: "
                   "creative/blueprint.json)")
    return sorted(beats, key=lambda b: b.get("start_s") or 0.0)


def _beat_at(beats, t):
    """The beat covering absolute second t; a gap falls to the nearest started beat."""
    for b in beats:
        if (b.get("start_s") or 0.0) <= t < (b.get("end_s") or 0.0):
            return b
    before = [b for b in beats if (b.get("start_s") or 0.0) <= t]
    return before[-1] if before else beats[0]


def _second_row(segment, k, beat):
    """One second of the trial A nine-channel direction."""
    a = segment["start_s"] + k
    b = min(a + 1.0, segment["end_s"])
    body = (beat.get("change") or beat.get("development") or "").strip()
    if not body:
        body = "carry the beat this second belongs to"
    emotion = (beat.get("intended_emotion") or "").strip() or "neutral"
    return (
        "second %d (%.1f-%.1fs) [%s] | body: %s | head: chin level, eyes "
        "leading the body | face: %s | arms: follow the body, hands empty "
        "unless the beat names a prop | legs: planted, weight moving only "
        "where the body moves | hair/clothing: unchanged from the approved "
        "still | props: only the props this beat names | camera: one locked "
        "portrait 9:16 shot, no cut inside the second | light: the setting's "
        "own light, constant across the second"
        % (k + 1, a, b, beat.get("story_beat_id") or "unknown", body, emotion)
    )


def _expressions(beats, segment):
    """The emotions this segment's beats ask for (the expression library)."""
    names = []
    for b in beats:
        if ((b.get("end_s") or 0.0) <= segment["start_s"]
                or (b.get("start_s") or 0.0) >= segment["end_s"]):
            continue
        e = (b.get("intended_emotion") or "").strip()
        if e and e not in names:
            names.append(e)
    return "neutral baseline, then " + ", ".join(names) if names else "neutral baseline"


def video_prompt(segment, blueprint, bibles):
    """The Agnes video prompt for one segment, and its character count.

    ``segment`` is a window from ``segments()``; ``blueprint`` is
    ``creative/blueprint.json`` as SPEC C1; ``bibles`` is
    ``{"character": <character bible text>, "style": <style bible text>}`` for
    the approved look. Returns ``(prompt, len(prompt))`` -- the 5,000-20,000
    character band is the door's judgement, not this module's.
    """
    for key in ("character", "style"):
        text = bibles.get(key) if isinstance(bibles, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise _bad("bibles needs a non-empty %r section" % (key,))
    for key in ("index", "start_s", "end_s"):
        if key not in segment:
            raise _bad("segment needs %r; pass a window from segments()" % key,)
    beats = _beats(blueprint)

    span = segment["end_s"] - segment["start_s"]
    seconds = max(1, int(math.ceil(span - 1e-9)))
    rows = [_second_row(segment, k, _beat_at(beats, segment["start_s"] + k))
            for k in range(seconds)]

    sections = [
        ("AGNES VIDEO PROMPT - 10-second segment %d (%.1f-%.1f s), one "
         "continuous shot, seconds \"10\", keyframe mode, first_frame is the "
         "approved still for this window"
         % (segment["index"], segment["start_s"], segment["end_s"])),
        "CHARACTER BIBLE\n" + bibles["character"].strip(),
        "STYLE BIBLE\n" + bibles["style"].strip(),
        "FRAMING\n"
        "Portrait 9:16, one continuous shot for the whole 10 seconds, the "
        "storyboard card's own framing, head fully inside the frame, the face "
        "visible whenever the beat turns on an expression, nothing important "
        "in the caption safe zones.",
        "SETTING\n"
        "The approved storyboard setting for this window: same room, same "
        "furniture placement, same time of day and same weather as the still; "
        "no new objects and no background change inside the segment.",
        "SECOND-BY-SECOND DIRECTION (9 channels each)\n" + "\n".join(rows),
        "PHYSICS\n"
        "Motion is solid and continuous: gravity, contact and weight are real "
        "- feet push off the floor, hands meet objects, cloth and hair follow "
        "the movement with a natural lag. No floating, no teleporting, no limb "
        "stretch, no passing through furniture, no impossible holds, no speed "
        "ramps and no slow motion.",
        "CONTINUITY\n"
        "The character keeps the same face, build, hair and wardrobe as the "
        "approved still in every frame; the opening frame matches first_frame "
        "exactly and motion continues out of it; props stay where they were "
        "put; no re-staging, no costume or lighting change, no cut.",
        "TEXT BAN\n" + NO_TEXT_BLOCK,
        "PALETTE\n"
        "Only the colours of the approved style bible and the still: same "
        "hues, same values, no colour drift between seconds, no new colours, "
        "no filter change.",
        "EXPRESSION LIBRARY\n" + _expressions(beats, segment),
        "SELF-CHECK BEFORE FINISHING\n"
        "The face matches the approved reference in every frame; all nine "
        "channels above are obeyed in every second; no words anywhere; no "
        "extra limbs and no warped hands; no wardrobe or background change; "
        "the last frame lands where the next segment's first_frame expects it.",
    ]
    prompt = "\n\n".join(sections)
    return prompt, len(prompt)


def closeup_prompt(character):
    """The Agnes Image prompt that makes a lip-sync close-up (SPEC A7).

    Front-facing or at most three-quarter head-and-shoulders, face large in
    frame, soft even light, nothing over the mouth, neutral, lips gently
    closed or slightly parted, no teeth showing, no words. The picture used
    for a lip-sync shot is never smiling (Trevor 2026-10-13, both paths).

    This is the Agnes still prompt: it MAKES the close-up the lip-sync picture
    gate then measures (``lip_sync/lip_gate/image_gate.closeup_prompt`` is the
    same rule set as a check on the picture, plus SPEC A6's no-words block,
    which is why the wording lives here and is not imported).
    """
    if not isinstance(character, str) or not character.strip():
        raise _bad("character description is required")
    parts = [
        character.strip().rstrip("."),
        "head-and-shoulders close-up, front-facing or at most a slight "
        "three-quarter turn, never profile, no steep up or down angle",
        "the face fills a large share of the frame, head centred, eyes to lens",
        "soft even light across the whole face, no shadow across the mouth",
        "nothing over the mouth: no hand, no microphone, no hair across the "
        "face, no hat brim, no scarf",
        "neutral expression, lips gently closed or slightly parted, no teeth "
        "showing, never a smiling picture for a lip-sync shot",
        "sharp focus on the eyes and lips, plain background separated from "
        "the head",
    ]
    return ". ".join(p.rstrip(".") for p in parts) + ". " + NO_TEXT_BLOCK
