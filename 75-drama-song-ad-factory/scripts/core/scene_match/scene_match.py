"""scene_match.py: every shot must show what its line says (Part I I2). Stdlib only.

Trevor, 2026-10-08: reinforce that scenes match the song and the facial
expressions. Two moments:

1. Storyboard time: ``shot_card`` gives each shot four plain facts, and
   ``check_cards`` refuses a shot missing any of them before video spend.
     line          the exact words sung or spoken
     meaning       what the viewer must understand from the line
     where_action  the place and what the person is doing
     face_emotion  the emotion the face shows (G6 ``line_emotion``)
2. After the clips exist: ``qc_scene_match`` looks at sampled frames per
   shot. A frame's ``seen`` text (from the vision sampler, or a stub in tests)
   must share words with the planned place/action/meaning (else
   SCENE_OFF_TOPIC), and a smiling face under a pain line fails through the
   G6 gate (FACE_EMOTION_MISMATCH). The result lists ``regenerate_shot_ids``:
   only the failing shots are redone, never the whole ad.
3. Method runs (SPEC C4, METHOD-INTEGRATION F8): the card also carries the
   story beat id, the music cue and the character state, and
   ``check_cards(..., method=True)`` requires them. ``transformation_lock``
   refuses a present-time shot after the breakthrough that still shows the
   before-state, unless it is tagged ``flashback``/``setback`` WITH a reason.
   Paid/social runs pass the platform row and the card's ``safe_zone`` boxes
   must sit inside that row's margins. Every one of these is off unless the
   caller asks for it, so a run without ``control/method.json`` is unchanged.
"""
from __future__ import annotations

import os
import re
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import face_emotion.face_emotion as FE   # noqa: E402

CARD_INCOMPLETE = "SCENE_CARD_INCOMPLETE"
OFF_TOPIC = "SCENE_OFF_TOPIC"
NO_FRAMES = "SCENE_FRAMES_MISSING"
LOCK_BROKEN = "TRANSFORMATION_LOCK_BROKEN"
LOCK_HELD = "TRANSFORMATION_LOCK_HELD"
SAFE_ZONE = "SCENE_SAFE_ZONE_BREACH"
MIN_FRAMES = 3          # frames sampled per shot (start, middle, end)
STATES = frozenset({"before", "after", "neutral"})   # SPEC C4 character state
SAFE_ZONE_BOXES = ("key_action", "on_screen_text")  # SPEC C4 safe-zone fields
# The three method card facts (SPEC C1 blueprint names first, short names
# beside them): (card key, contract keys tried in order).
CARRIED = (("story_beat", ("story_beat_id", "story_beat")),
           ("music_cue", ("music_cue_id", "music_cue", "music_cue_ids")),
           ("state", ("character_state", "state", "character_state_before_after")))
_LABEL = {"story_beat": "story beat id",
          "music_cue": "music cue",
          "state": "character state (before/after/neutral)"}
_STOP = frozenset("a an the and or of to in on at is are was her his she he it "
                  "with for from by as that this their into over under".split())


def _words(text):
    if isinstance(text, (list, tuple)):
        text = " ".join(str(t) for t in text)
    out = set()
    for w in re.findall(r"[a-z]+", str(text or "").lower()):
        w = w[:-1] if w.endswith("s") and len(w) > 3 else w   # ponytail: crude plural strip
        if w not in _STOP and len(w) > 2:
            out.add(w)
    return out


def _carried(contract, keys):
    """First non-empty contract value among ``keys`` (a cue id list joins)."""
    c = contract if isinstance(contract, dict) else {}
    for k in keys:
        v = c.get(k)
        if isinstance(v, (list, tuple)):
            v = ", ".join(str(x) for x in v if str(x).strip())
        v = str(v or "").strip()
        if v:
            return v
    return ""


def _state(value):
    """A before/after/neutral token (the first word may carry the rest)."""
    v = str(value or "").strip()
    first = v.split()[0].lower() if v else ""
    return first if first in STATES else v


def shot_card(shot, contract):
    """The storyboard facts for one shot (empty string when unknown).

    The first four are the original card; the last three are the method card
    facts (SPEC C4) and are only filled when the contract carries them.
    """
    c = contract if isinstance(contract, dict) else {}
    lyric = (c.get("lyric_text") or "").strip()
    emotion = (c.get("visible_emotion") or "").strip() \
        or FE.line_emotion(shot.get("story_stage"), lyric)
    where = " - ".join(x for x in ((shot.get("location_id") or "").strip(),
                                   (c.get("character_action") or "").strip()) if x)
    card = {"shot_id": shot.get("shot_id"), "line": lyric,
            "meaning": (c.get("viewer_understanding") or "").strip(),
            "where_action": where if c.get("character_action") else "",
            "face_emotion": emotion if lyric else ""}
    for name, keys in CARRIED:
        card[name] = _state(_carried(c, keys)) if name == "state" else _carried(c, keys)
    return card


def _margins(row):
    """The platform row's safe-zone margins as fractions, or None when absent."""
    if not isinstance(row, dict):
        return None
    z = row.get("safe_zone")
    if z is None:
        z = row.get("safe_zones")
    if not isinstance(z, dict):
        return None
    out = {}
    for k in ("top", "bottom", "left", "right"):
        v = z.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = float(v)
    return out or None


def _box(value):
    """A ``[x, y, w, h]`` frame-fraction box, or None when not usable."""
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        return [float(v) for v in value]
    except (TypeError, ValueError):
        return None


def _inside(box, margins):
    x, y, w, h = box
    return (x >= margins.get("left", 0.0) and y >= margins.get("top", 0.0)
            and x + w <= 1.0 - margins.get("right", 0.0)
            and y + h <= 1.0 - margins.get("bottom", 0.0))


def check_cards(shots, contracts, method=False, platform_row=None):
    """Findings for shots whose card lacks a line, meaning, action or emotion.

    ``method=True`` (a run carrying ``control/method.json``) additionally
    requires the three method card facts: story beat id, music cue and a
    character state of before/after/neutral. ``platform_row`` (paid and social
    runs) additionally checks the contract's ``safe_zone`` boxes against the
    row's margins; a row that carries no margin data checks nothing.
    """
    findings = []
    margins = _margins(platform_row)
    keys = ["line", "meaning", "where_action", "face_emotion"]
    if method:
        keys += [name for name, _ in CARRIED]
    for s in shots or []:
        sid = s.get("shot_id")
        contract = (contracts or {}).get(sid)
        card = shot_card(s, contract)
        for k in keys:
            if not card[k]:
                findings.append({"shot_id": sid, "code": CARD_INCOMPLETE,
                                 "detail": "storyboard card has no %s"
                                           % _LABEL.get(k, k)})
        if method and card["state"] and card["state"] not in STATES:
            findings.append({"shot_id": sid, "code": CARD_INCOMPLETE,
                             "detail": "storyboard card state is not before/after/neutral: %s"
                                       % card["state"]})
        if margins:
            zone = contract.get("safe_zone") if isinstance(contract, dict) else None
            zone = zone if isinstance(zone, dict) else {}
            for name in SAFE_ZONE_BOXES:
                box = _box(zone.get(name))
                if box is None:
                    findings.append({"shot_id": sid, "code": SAFE_ZONE,
                                     "detail": "safe_zone has no %s box" % name})
                elif not _inside(box, margins):
                    findings.append({"shot_id": sid, "code": SAFE_ZONE,
                                     "detail": "%s box %s is outside the platform safe zone"
                                               % (name, box)})
    return {"outcome": "ok" if not findings else "rejected",
            "reason_code": "I2_CARDS_COMPLETE" if not findings else findings[0]["code"],
            "findings": findings}


def _continuity_tag(shot, contract):
    """The flashback/setback exemption tag and its reason (SPEC C4)."""
    tag, reason = "", ""
    for src in (contract, shot):
        if not isinstance(src, dict):
            continue
        tag = tag or str(src.get("continuity_tag") or "").strip().lower()
        reason = reason or str(src.get("continuity_reason") or "").strip()
    return tag, reason


def transformation_lock(shots, contracts, token, breakthrough_s):
    """Refuse a present-time shot after the breakthrough showing the before-state.

    SPEC C4 / method Steps 11 and 16: once the transformation happens (the
    cape comes off) no later present-time shot may show the before-state,
    unless it is tagged ``continuity_tag`` ``flashback`` or ``setback`` WITH a
    ``continuity_reason``. A shot that starts before ``breakthrough_s`` is the
    breakthrough itself or the pain side and is never refused here.
    ``token`` names what is locked (e.g. "cape off"); it is only reported.
    """
    findings = []
    name = str(token or "").strip() or "the transformation"
    try:
        cut = float(breakthrough_s)
    except (TypeError, ValueError):
        return {"outcome": "rejected", "reason_code": LOCK_BROKEN,
                "findings": [{"shot_id": "run", "code": LOCK_BROKEN,
                              "detail": "no breakthrough time to lock %s against" % name}]}
    for s in shots or []:
        sid = s.get("shot_id")
        contract = (contracts or {}).get(sid)
        if shot_card(s, contract)["state"] != "before":
            continue
        tag, reason = _continuity_tag(s, contract)
        if tag in ("flashback", "setback"):
            if reason:
                continue
            findings.append({"shot_id": sid, "code": LOCK_BROKEN,
                             "detail": "marked %s with no reason" % tag})
            continue
        try:
            starts = float(s.get("song_start") or 0.0)
        except (TypeError, ValueError):
            starts = 0.0
        if starts >= cut:
            findings.append({"shot_id": sid, "code": LOCK_BROKEN,
                             "detail": "present-time shot after the breakthrough still "
                                       "shows the before-state of %s" % name})
    return {"outcome": "ok" if not findings else "rejected",
            "reason_code": LOCK_HELD if not findings else LOCK_BROKEN,
            "findings": findings}


def qc_scene_match(shots, contracts, frames_by_shot, min_frames=MIN_FRAMES):
    """Check sampled frames against each shot's card; name shots to regenerate.

    frames_by_shot: {shot_id: [{"seen": "what the frame shows", "happy": bool}]}
    """
    contracts = contracts or {}
    findings = []
    for s in shots or []:
        sid = s.get("shot_id")
        frames = [f for f in (frames_by_shot or {}).get(sid) or [] if isinstance(f, dict)]
        if len(frames) < min_frames:
            findings.append({"shot_id": sid, "code": NO_FRAMES,
                             "detail": "%d of %d frames sampled" % (len(frames), min_frames)})
            continue
        card = shot_card(s, contracts.get(sid))
        want = _words(" ".join((card["where_action"], card["meaning"],
                                s.get("visual_objective") or "")))
        hits = sum(1 for f in frames if want & _words(f.get("seen")))
        if want and hits * 2 <= len(frames):          # need a majority of frames on topic
            findings.append({"shot_id": sid, "code": OFF_TOPIC,
                             "detail": "%d of %d frames show the planned scene (%s)"
                                       % (hits, len(frames), card["where_action"][:60])})
        face = FE.qc_frame_gate(
            [dict(s, contract=dict(contracts.get(sid) or {}, visible_emotion=card["face_emotion"]))],
            {sid: frames})
        findings.extend(face["findings"])
    ids = sorted({f["shot_id"] for f in findings})
    return {"outcome": "ok" if not findings else "rejected",
            "reason_code": "I2_SCENES_MATCH" if not findings else findings[0]["code"],
            "findings": findings, "regenerate_shot_ids": ids}
