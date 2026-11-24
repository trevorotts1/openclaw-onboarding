#!/usr/bin/env python3
"""vision.py: the shared vision call and every question it answers (N-30,
N-45, N-72, N-89, N-107, N-119, N-122).

One call per frame answers style, the five consistency items, the expression
question, the cast questions and the world questions, so each frame is looked
at once (sections 3B.4, 3C.7, 3C.9, 3C.10, 3M.4). A caller that only needs
one family calls one helper.

Every helper fails closed: an answer of None or a missing key is UNAVAILABLE
at MAJOR item 15, never a pass. Style is never waived. Before each batch the
caller reads one known-match and one known-mismatch pair; if the check cannot
tell them apart it reports itself unavailable (``control_gate``).

stdlib only, no network, no spend. The vision model is injected.
"""
from __future__ import annotations

from . import severity as _SV

# --- reason codes -----------------------------------------------------------
STYLE_MISMATCH = "STYLE_MISMATCH"
STYLE_CHECK_UNAVAILABLE = "STYLE_CHECK_UNAVAILABLE"
STYLE_WAIVER_REFUSED = "STYLE_WAIVER_REFUSED"
CHARACTER_MISMATCH = "CHARACTER_MISMATCH"
CONSISTENCY_CHECK_UNAVAILABLE = "CONSISTENCY_CHECK_UNAVAILABLE"
EXPRESSION_MISMATCH = "EXPRESSION_MISMATCH"
EXPRESSION_DRIFT = "EMOTION_DRIFT"
EXPRESSION_CHECK_UNAVAILABLE = "EXPRESSION_CHECK_UNAVAILABLE"
UNLISTED_PERSON = "UNLISTED_PERSON"
CAST_MEMBER_MISSING = "CAST_MEMBER_MISSING"
PLACE_MISMATCH = "PLACE_MISMATCH"
SET_PIECE_MISSING = "SET_PIECE_MISSING"
CROWD_MISMATCH = "CROWD_MISMATCH"
CHOIR_COUNT_MISMATCH = "CHOIR_COUNT_MISMATCH"
LIGHT_OFF_CLOCK = "LIGHT_OFF_CLOCK"
SCREEN_DIRECTION_BREAK = "SCREEN_DIRECTION_BREAK"
EXIT_ENTRY_MISMATCH = "EXIT_ENTRY_MISMATCH"
LIGHT_COLOR_SHIFT = "LIGHT_COLOR_SHIFT"
PROP_CONTINUITY_BREAK = "PROP_CONTINUITY_BREAK"
FLOATY_MOTION = "FLOATY_MOTION"
CINEMATIC_UNMEASURED = "CINEMATIC_UNMEASURED"

#: The five consistency items plus the sixth question (sections 3C.7, 3G.4).
CONSISTENCY_ITEMS = ("face", "hair", "wardrobe", "accessories", "look")

#: N-107: clips with a person in the foreground need a contact sheet at 2 fps.
CONTACT_SHEET_FPS = 2

#: N-45: a lip-sync take is sampled first, last and every 3 seconds.
LIPSYNC_SAMPLE_EVERY_S = 3.0

#: N-89: automatic remakes stop above this share failing on expression.
EXPRESSION_FAIL_STOP = 3 / 10.0


def style_question(look_wording):
    """N-30: the one fixed style question for a look. Never waived."""
    return ("Is this frame clearly %s, and not a photograph or live action? "
            "Does each named character match the reference pictures? "
            "Answer yes or no."
            % (str(look_wording or "the locked look").strip()))


def expression_question(emotion, intensity):
    """N-72: the sixth fixed question, asked in the same vision call."""
    return ("Does this face express %s at intensity %s, with no smile where "
            "the tag says no smile?" % (emotion, intensity))


def sample_points(duration_s, every_s=LIPSYNC_SAMPLE_EVERY_S):
    """First frame, last frame, and one frame every ``every_s`` seconds."""
    try:
        duration_s = float(duration_s)
    except (TypeError, ValueError):
        return [0.0]
    if duration_s <= 0:
        return [0.0]
    points = [0.0]
    t = every_s
    while t < duration_s:
        points.append(round(t, 3))
        t += every_s
    points.append(round(max(duration_s - 1e-3, 0.0), 3))
    return sorted(set(points))


def _no(answer):
    return answer is False


def _missing(answer):
    return answer is None


def control_gate(known_match, known_mismatch, unanswered_code):
    """A check must tell a known match from a known mismatch, or it is
    unavailable (never a pass). Returns None when it discriminates."""
    if known_match is True and known_mismatch is False:
        return None
    return {"code": unanswered_code, "level": _SV.MAJOR, "item": 15,
            "text": "the check could not tell its known-match and "
                    "known-mismatch controls apart"}


# ------------------------------------------------------------- N-30 --------

def style_check(answer, controls=(None, None)):
    """N-30: every character sheet, keyframe, clip sample and lip-sync source
    picture and take against the locked look. ``answer`` is yes/no/None.
    Style is never waived: a waiver request is itself a finding."""
    gate = control_gate(controls[0], controls[1], STYLE_CHECK_UNAVAILABLE)
    if gate:
        return {"code": gate["code"], "level": _SV.MAJOR, "item": 15,
                "text": gate["text"], "pass": False}
    if _missing(answer):
        return {"code": STYLE_CHECK_UNAVAILABLE, "level": _SV.MAJOR,
                "item": 15, "text": "no style answer", "pass": False}
    if _no(answer):
        return {"code": STYLE_MISMATCH, "level": _SV.MAJOR, "item": 6,
                "text": "frame is not in the locked look", "pass": False}
    return {"code": None, "level": None, "pass": True}


def style_waiver():
    """N-30: the style check is never waived. A requested waiver is refused."""
    return {"code": STYLE_WAIVER_REFUSED, "level": _SV.MAJOR, "item": 6,
            "text": "the style check is never waived", "pass": False}


# ------------------------------------------------------ N-45 + N-72 -------

def consistency_check(answers, controls=(None, None), expression=None,
                      intensity=None):
    """N-45: the five items (face, hair, wardrobe, accessories, look) plus the
    N-72 expression question. ``answers`` maps item -> yes/no/None;
    ``expression`` is the sixth answer. Any "no" fails, naming the item; any
    missing answer fails closed."""
    gate = control_gate(controls[0], controls[1],
                        CONSISTENCY_CHECK_UNAVAILABLE)
    if gate:
        return {"findings": [gate], "pass": False}
    findings = []
    if not isinstance(answers, dict):
        answers = {}
    for item in CONSISTENCY_ITEMS:
        answer = answers.get(item)
        if _missing(answer):
            findings.append({"code": CONSISTENCY_CHECK_UNAVAILABLE,
                             "level": _SV.MAJOR, "item": 15,
                             "text": "%s was not answered" % item})
        elif _no(answer):
            findings.append({"code": CHARACTER_MISMATCH, "level": _SV.MAJOR,
                             "item": 5, "text": "%s does not match the lock"
                             % item, "item_name": item})
    if _missing(expression):
        findings.append({"code": EXPRESSION_CHECK_UNAVAILABLE,
                         "level": _SV.MAJOR, "item": 15,
                         "text": "the expression question was not answered"})
    elif _no(expression):
        findings.append(_SV.finding(EXPRESSION_MISMATCH,
                                    "the face contradicts its emotion tag",
                                    intensity=intensity))
    return {"findings": findings, "pass": not _SV.only_major(findings)}


# --------------------------------------------------------------- N-89 -----

class ExpressionGuard(object):
    """N-89: a plain contradiction fails; a borderline answer is flagged, not
    remade; intensity 1 only flags; above 3 in 10 failing on expression the
    automatic remakes stop and the check is re-read against its controls."""

    def __init__(self):
        self.seen = 0
        self.failed = 0
        self.flags = []
        self.findings = []

    def observe(self, verdict, intensity=2):
        """verdict: 'pass' | 'plain_contradiction' | 'borderline' |
        'unavailable'."""
        self.seen += 1
        verdict = str(verdict or "").strip().lower()
        if verdict == "unavailable":
            self.findings.append({"code": EXPRESSION_CHECK_UNAVAILABLE,
                                  "level": _SV.MAJOR, "item": 15,
                                  "text": "the expression check could not run"})
            return None
        if verdict == "borderline":
            self.flags.append({"verdict": "borderline", "intensity": intensity,
                               "action": "flagged, not remade"})
            return "flagged"
        if verdict != "plain_contradiction":
            return "pass"
        if intensity == 1:
            self.flags.append({"verdict": "plain_contradiction",
                               "intensity": 1, "action": "flagged only"})
            return "flagged"
        self.failed += 1
        self.findings.append(_SV.finding(
            EXPRESSION_MISMATCH, "a plain contradiction at intensity %s"
            % intensity, intensity=intensity))
        return "fail"

    def stop_remakes(self):
        """True when more than 3 in 10 failed; then re-read the controls."""
        return self.seen > 0 and (self.failed / float(self.seen)) > \
            EXPRESSION_FAIL_STOP

    def result(self):
        return {"seen": self.seen, "failed": self.failed,
                "findings": list(self.findings), "flags": list(self.flags),
                "stop_remakes": self.stop_remakes(),
                "reread_controls": self.stop_remakes()}


# -------------------------------------------------------------- N-119 -----

def cast_check(answers, cast_ids, declared_crowd=False):
    """N-119: the cast-consistency questions on a picture or clip frame.
    ``answers`` keys: unlisted_person, cast_match, wardrobe_match,
    cast_missing. Any no fails at MAJOR item 5 (item 11 for a missing cast
    member)."""
    findings = []
    answers = answers if isinstance(answers, dict) else {}
    if _missing(answers.get("unlisted_person")):
        findings.append({"code": CONSISTENCY_CHECK_UNAVAILABLE,
                         "level": _SV.MAJOR, "item": 15,
                         "text": "cast presence was not answered"})
    elif _no(answers.get("unlisted_person")) and not declared_crowd:
        findings.append({"code": UNLISTED_PERSON, "level": _SV.MAJOR,
                         "item": 5,
                         "text": "a person with a visible face is not on the "
                                 "cast list"})
    for key, code, item in (("cast_match", CHARACTER_MISMATCH, 5),
                            ("wardrobe_match", CHARACTER_MISMATCH, 5),
                            ("cast_missing", CAST_MEMBER_MISSING, 11)):
        answer = answers.get(key)
        if _missing(answer):
            findings.append({"code": CONSISTENCY_CHECK_UNAVAILABLE,
                             "level": _SV.MAJOR, "item": 15,
                             "text": "%s was not answered" % key})
        elif _no(answer):
            findings.append({"code": code, "level": _SV.MAJOR, "item": item,
                             "text": "%s failed for %s"
                                     % (key, ", ".join(cast_ids or ()) or
                                        "the cast")})
    return {"findings": findings, "pass": not _SV.only_major(findings)}


# -------------------------------------------------------------- N-122 -----

def world_check(answers):
    """N-122 part 2 / 3M.4: place, set pieces, crowd, choir, clock, asked in
    the same vision call. Levels come from the fixed table (section 3M.4).

    A conditional MAJOR must name its fixed-list item (3J): item 12 for the
    world group (an empty room where the story says full, and the place, set
    piece, choir and clock breaks 3M.4 raises to MAJOR). Everything else is a
    MEDIUM that passes and is logged.
    """
    findings = []
    answers = answers if isinstance(answers, dict) else {}
    place = answers.get("place_match")
    if _missing(place):
        findings.append({"code": CINEMATIC_UNMEASURED, "level": _SV.MAJOR,
                         "item": 15, "text": "the place was not answered"})
    elif _no(place):
        # 3M.4: a lip-sync picture in the wrong place is MAJOR; any other
        # place break is MAJOR only when it confuses the story.
        raise_it = (answers.get("lip_sync_picture") is True
                    or answers.get("confuses_story") is True)
        findings.append(_SV.finding(
            PLACE_MISMATCH, "the place differs from its world reference",
            item=12 if raise_it else None,
            lip_sync_picture=bool(answers.get("lip_sync_picture"))))
    for key, code, ctx_key in (
            ("set_pieces", SET_PIECE_MISSING, "wrong_room"),
            ("crowd_state", CROWD_MISMATCH, "should_be_full"),
            ("choir_count", CHOIR_COUNT_MISMATCH,
             "under_half_or_over_double"),
            ("light_clock", LIGHT_OFF_CLOCK, "contradicts_story")):
        answer = answers.get(key)
        if _missing(answer):
            findings.append({"code": CINEMATIC_UNMEASURED, "level": _SV.MAJOR,
                             "item": 15,
                             "text": "%s was not answered" % key})
        elif _no(answer):
            findings.append(_SV.finding(
                code, "%s failed" % key,
                item=12 if answers.get(ctx_key) is True else None,
                **{ctx_key: bool(answers.get(ctx_key))}))
    return {"findings": findings, "pass": not _SV.only_major(findings)}


# -------------------------------------------------------------- N-107 -----

#: The questions every clip is asked. An unasked one is a check that could not
#: run: MAJOR item 15, never a pass (3J item 15, fail closed).
CINEMATIC_QUESTIONS = ("screen_direction_ok", "jump_cut", "entry_exit_ok",
                       "light_colour_ok", "prop_continuity_ok", "place_match")


def cinematic_check(row, required=None):
    """N-107: screen direction, jump cuts, entry/exit joins, light and colour
    inside a scene, prop continuity, the place check and the exit-against-
    entry check on the clip's last frame. MEDIUM unless the break confuses
    the story or matters to it, then MAJOR; floaty or morphing foreground
    motion is MAJOR.

    ``required`` names the questions that must be answered; an unanswered one
    is ``CINEMATIC_UNMEASURED`` at MAJOR item 15 (a check that could not run).

    A conditional MAJOR must name its fixed-list item (3J: a finding that
    names no item number is MEDIUM at most): item 16 when it confuses the
    story, item 17 when the prop break matters to it.
    """
    findings = []
    row = dict(row if isinstance(row, dict) else {})
    required = tuple(CINEMATIC_QUESTIONS if required is None else required)
    for key in required:
        if row.get(key) is None:
            findings.append({"code": CINEMATIC_UNMEASURED, "level": _SV.MAJOR,
                             "item": 15,
                             "text": "the check could not run: %s was not "
                                     "answered" % key})
    confuses = row.get("confuses_story") is True
    item16 = 16 if confuses else None
    if row.get("screen_direction_ok") is False:
        findings.append(_SV.finding(
            SCREEN_DIRECTION_BREAK, "screen direction broke",
            item=item16))
    if row.get("jump_cut") is True:
        findings.append(_SV.finding(
            "JUMP_CUT_DETECTED", "a jump cut inside the clip", item=item16))
    if row.get("entry_exit_ok") is False:
        findings.append(_SV.finding(
            EXIT_ENTRY_MISMATCH, "the exit does not match the next entry",
            item=item16))
    if row.get("light_colour_ok") is False:
        findings.append(_SV.finding(
            LIGHT_COLOR_SHIFT, "light or colour shifted inside the scene"))
    if row.get("prop_continuity_ok") is False:
        findings.append(_SV.finding(
            PROP_CONTINUITY_BREAK, "prop continuity broke",
            item=17 if row.get("matters") is True else None))
    if row.get("place_match") is False:
        # The place is on no item of its own; a story-confusing place break is
        # item 16, and a lip-sync picture in the wrong place breaks the story.
        findings.append(_SV.finding(
            PLACE_MISMATCH, "the place check failed",
            item=16 if (confuses or row.get("lip_sync_picture") is True)
            else None))
    if row.get("floaty_motion") is True:
        findings.append({"code": FLOATY_MOTION, "level": _SV.MAJOR, "item": 13,
                         "text": "floaty, rubbery or morphing foreground "
                                 "motion"})
    return {"findings": findings, "pass": not _SV.only_major(findings)}


def contact_sheet_required(foreground_person):
    """N-107: a contact sheet at 2 frames per second for clips with a person
    in the foreground."""
    return bool(foreground_person)


# ------------------------------------------------------------- ledger -----

def ledger_row(shot, fingerprint, character, lock_version, answers,
               checking_model, at, findings=()):
    """Every result is written to the run's ledger: shot, file fingerprint,
    character, lock version, the answers, the checking model, the time."""
    return {"shot": shot, "sha256": fingerprint, "character": character,
            "lock_version": lock_version, "answers": dict(answers or {}),
            "checking_model": checking_model, "at": at,
            "findings": list(findings)}


if __name__ == "__main__":
    # One control over the five answer-families this module implements.
    # A check that could not run is never a pass; style has no waiver.
    ok_ctl = (True, False)

    # N-30 style: no answer -> unavailable; a no -> MAJOR item 6; no waiver.
    assert style_check(None, ok_ctl)["item"] == 15
    assert style_check(False, ok_ctl)["item"] == 6
    assert style_check(True, ok_ctl)["pass"] is True
    assert style_check(True, (None, None))["item"] == 15
    assert style_waiver()["code"] == STYLE_WAIVER_REFUSED

    # N-45: five items plus the sixth; any no fails naming the item.
    clean = {item: True for item in CONSISTENCY_ITEMS}
    assert consistency_check(clean, ok_ctl, expression=True)["pass"]
    broke = dict(clean, wardrobe=False)
    out = consistency_check(broke, ok_ctl, expression=True)
    assert not out["pass"] and out["findings"][0]["code"] == CHARACTER_MISMATCH
    assert out["findings"][0].get("item_name") == "wardrobe"
    assert consistency_check(clean, ok_ctl, expression=None)["findings"][0][
        "code"] == EXPRESSION_CHECK_UNAVAILABLE
    assert consistency_check(clean, (None, None), expression=True)[
        "findings"][0]["item"] == 15

    # N-119 cast presence: an unlisted face fails unless the frame declares a
    # crowd; a missing cast member is item 11.
    assert cast_check({"unlisted_person": True, "cast_match": True,
                       "wardrobe_match": True, "cast_missing": True},
                      ["lead"], declared_crowd=False)["pass"]
    assert cast_check({"unlisted_person": False, "cast_match": True,
                       "wardrobe_match": True, "cast_missing": True},
                      ["lead"])["findings"][0]["code"] == UNLISTED_PERSON
    assert cast_check({"unlisted_person": False, "cast_match": True,
                       "wardrobe_match": True, "cast_missing": True},
                      ["lead"], declared_crowd=True)["pass"]
    assert cast_check({"unlisted_person": True, "cast_match": True,
                       "wardrobe_match": True, "cast_missing": False},
                      ["lead"])["findings"][0]["item"] == 11

    # N-122 world: an unanswered place fails closed; a full-room miss is
    # MAJOR item 12; the same questions come back from one call.
    assert world_check({})["findings"][0]["item"] == 15
    full = {"place_match": True, "set_pieces": True, "crowd_state": False,
            "choir_count": True, "light_clock": True, "should_be_full": True}
    assert world_check(full)["findings"][0]["item"] == 12

    # The sample plan: first, last, every 3 s for a lip-sync take.
    pts = sample_points(7.0)
    assert pts[0] == 0.0 and max(pts) < 7.0

    row = ledger_row("S12", "sha", "lead", 3, {"face": True}, "m", "19:00")
    assert row["shot"] == "S12" and row["lock_version"] == 3
    print("vision: control PASS")
