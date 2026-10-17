"""approval_package.py: the storyboard approval message shows BOTH the written
shot card and that shot's still image (Trevor, 2026-10-09). Stdlib only.

Order: storyboard cards -> one still per shot (cheap) -> THIS approval ->
only then video (the expensive part). ``build`` refuses a shot with no card
fact or no still file; ``approve`` is the only thing that stamps
``storyboard_approved`` (the 14.1 gate kie_dispatch already enforces);
``revise_shot`` redoes one shot's still and re-sends that shot only.

Method runs (SPEC C4, METHOD-INTEGRATION F8) add three opt-in arguments, all
defaulting to today's behaviour:
    ``method=True``        the card also carries Story beat / Music / State,
                           and ``scene_match.check_cards`` requires them.
    ``lock_token`` + ``breakthrough_s``
                           the Transformation Lock: the package is refused
                           when a present-time shot after the breakthrough
                           still shows the before-state.
    ``platform_row``       paid/social runs: the card's safe_zone boxes are
                           checked against that platform row's margins.
"""
from __future__ import annotations

import os
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import scene_match.scene_match as SM   # noqa: E402

STILL_MISSING = "STORYBOARD_STILL_MISSING"
CARD_INCOMPLETE = SM.CARD_INCOMPLETE
FOOTER = "Reply GO to approve, or 'shot 2: change ...' to fix one shot."
# Method card lines (SPEC C4): shown only when the contract carries them, so
# a package built from today's contracts renders byte for byte as before.
_CARD_LINES = (("story_beat", "Story beat"),
               ("music_cue", "Music"),
               ("state", "State"))


class ApprovalError(Exception):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def _clock(s):
    m, sec = divmod(int(round(s)), 60)
    return "%d:%02d" % (m, sec)


def _entry(n, shot, contract, still):
    c = SM.shot_card(shot, contract)
    e = {"n": n, "shot_id": shot["shot_id"],
         "time": "%s-%s" % (_clock(shot["song_start"]), _clock(shot["song_end"])),
         "line": c["line"], "meaning": c["meaning"],
         "where_action": c["where_action"], "face_emotion": c["face_emotion"],
         "still": still}
    for key, _ in _CARD_LINES:
        if c.get(key):
            e[key] = c[key]
    return e


def _text(e):
    head = "".join("\n%s: %s" % (label, e[key]) for key, label in _CARD_LINES if e.get(key))
    return ("Shot %d (%s)%s\nLine: \"%s\"\nViewer must understand: %s\n"
            "Place and action: %s\nFace: %s\nPicture: %s"
            % (e["n"], e["time"], head, e["line"], e["meaning"], e["where_action"],
               e["face_emotion"], e["still"]))


def build(shots, contracts, stills, method=False, lock_token=None,
          breakthrough_s=None, platform_row=None):
    """Approval package, shots in song order: card + still for every shot.

    stills: {shot_id: image file path}. Raises ApprovalError when any card
    fact is missing or any still file does not exist (fail closed).
    ``method`` also requires the story beat / music cue / state card facts,
    ``lock_token`` runs the Transformation Lock, ``platform_row`` checks the
    safe zones; each is off unless the caller passes it.
    """
    ordered = sorted(shots or [], key=lambda s: (s["song_start"], s["song_end"]))
    if not ordered:
        raise ApprovalError("STORYBOARD_EMPTY", "no shots to approve")
    bad = SM.check_cards(ordered, contracts, method=method, platform_row=platform_row)
    if bad["findings"]:
        raise ApprovalError(bad["reason_code"], "; ".join(
            "%s: %s" % (f["shot_id"], f["detail"]) for f in bad["findings"]))
    if lock_token or breakthrough_s is not None:
        lock = SM.transformation_lock(ordered, contracts, lock_token, breakthrough_s)
        if lock["findings"]:
            raise ApprovalError(lock["reason_code"], "; ".join(
                "%s: %s" % (f["shot_id"], f["detail"]) for f in lock["findings"]))
    gone = [s["shot_id"] for s in ordered
            if not os.path.isfile((stills or {}).get(s["shot_id"]) or "")]
    if gone:
        raise ApprovalError(STILL_MISSING, "no still image for: " + ", ".join(gone))
    items = [_entry(i, s, contracts.get(s["shot_id"]), stills[s["shot_id"]])
             for i, s in enumerate(ordered, 1)]
    # ponytail: one attached image per shot, in order; a single numbered
    # contact sheet is the upgrade if a channel caps attachments.
    return {"items": items, "images": [e["still"] for e in items],
            "message": "Storyboard: %d shots. Nothing is made into video until you say go.\n\n%s\n\n%s"
                       % (len(items), "\n\n".join(_text(e) for e in items), FOOTER)}


def approve(shots, contracts, stills, method=False, lock_token=None,
            breakthrough_s=None, platform_row=None):
    """Stamp every shot storyboard_approved, only if the full package builds."""
    build(shots, contracts, stills, method=method, lock_token=lock_token,
          breakthrough_s=breakthrough_s, platform_row=platform_row)
    return [dict(s, status="storyboard_approved") for s in shots]


def revise_shot(shots, contracts, stills, shot_id, changes, make_still,
                method=False, lock_token=None, breakthrough_s=None, platform_row=None):
    """Client edit to one shot: apply ``changes`` to its contract, call
    ``make_still(shot_id, card)`` for THAT shot only, return
    (contracts, stills, message) where message re-sends only that shot.
    The client then approves again; only approve() stamps shots.
    """
    if shot_id not in {s["shot_id"] for s in shots}:
        raise ApprovalError("SHOT_UNKNOWN", shot_id)
    contracts = dict(contracts, **{shot_id: dict(contracts.get(shot_id) or {}, **changes)})
    shot = next(s for s in shots if s["shot_id"] == shot_id)
    stills = dict(stills, **{shot_id: make_still(shot_id, SM.shot_card(shot, contracts[shot_id]))})
    pkg = build(shots, contracts, stills, method=method, lock_token=lock_token,
                breakthrough_s=breakthrough_s, platform_row=platform_row)
    e = next(i for i in pkg["items"] if i["shot_id"] == shot_id)
    return contracts, stills, "Updated shot %d.\n\n%s\n\n%s" % (e["n"], _text(e), FOOTER)
