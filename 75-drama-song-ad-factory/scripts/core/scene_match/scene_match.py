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
MIN_FRAMES = 3          # frames sampled per shot (start, middle, end)
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


def shot_card(shot, contract):
    """The four storyboard facts for one shot (empty string when unknown)."""
    c = contract if isinstance(contract, dict) else {}
    lyric = (c.get("lyric_text") or "").strip()
    emotion = (c.get("visible_emotion") or "").strip() \
        or FE.line_emotion(shot.get("story_stage"), lyric)
    where = " - ".join(x for x in ((shot.get("location_id") or "").strip(),
                                   (c.get("character_action") or "").strip()) if x)
    return {"shot_id": shot.get("shot_id"), "line": lyric,
            "meaning": (c.get("viewer_understanding") or "").strip(),
            "where_action": where if c.get("character_action") else "",
            "face_emotion": emotion if lyric else ""}


def check_cards(shots, contracts):
    """Findings for shots whose card lacks a line, meaning, action or emotion."""
    findings = []
    for s in shots or []:
        card = shot_card(s, (contracts or {}).get(s.get("shot_id")))
        for k in ("line", "meaning", "where_action", "face_emotion"):
            if not card[k]:
                findings.append({"shot_id": s.get("shot_id"), "code": CARD_INCOMPLETE,
                                 "detail": "storyboard card has no %s" % k})
    return {"outcome": "ok" if not findings else "rejected",
            "reason_code": "I2_CARDS_COMPLETE" if not findings else CARD_INCOMPLETE,
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
