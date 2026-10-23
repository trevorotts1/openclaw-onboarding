#!/usr/bin/env python3
"""method_plan.py: the Story Beat Blueprint validator (SPEC C1; method 10.2-10.4). stdlib only.

The Drama-to-Demand Method keeps TWO records tied together (conflict C10):
``creative/blueprint.json`` carries ``story_beats[]`` (the narrative) and
``music_cues[]`` (the musical direction), and this module is the ONE validator
for them. It is inert until the run carries ``control/method.json``: a run with
no method record never calls it, and nothing here changes today's behaviour.

  validate(blueprint, method)  the record fields; the required cue set per
      purpose (a lesson sings MEMORY_HOOK and recaps with RECAP instead of
      SOLUTION_HOOK + COMMERCIAL_CONTINUATION); anchor order -- backstory <
      ERM apex < Hero Shift < first breakthrough <= first hook < commercial;
      the ERM cue's ``vocal_status == "first_sung"`` with no singing before it;
      a Hero Shift distinct from the ERM; an earned hook (never before the
      solution is introduced, Trevor 2026-10-13); ``claim_source`` on every
      testimonial claim beat; ``trailer_value`` on every campaign beat.
  gates(method)                the A-F record with ``evidence_level`` per gate:
      planned / generated / inspected / approved, and approved only with a
      recorded human answer, else it reads planned (SPEC C6).
  pace_order(blueprint)        the song's two pace seams: ``boundary_s`` at the
      ERM apex, ``return_boundary_s`` at the Hero Shift, both directions in the
      blueprint's own words, ``method`` true so the method clauses are written
      into the style, and ``true_at_beat`` -- the stage where the solution is
      introduced (``the_turn``) or later.

``claim_source`` and ``trailer_value`` are the two conditional story-beat fields
of SPEC C1: each has its own gate, so a missing source is always named
CLAIM_UNSOURCED and never hidden behind a generic record error.

The production projection (method 10.3-10.4) turns the same record into the
inputs the rest of the factory already reads, and never into a second beat
engine:

  teaching_map(purpose)         the twelve production beats from
      ``story_arc.BEATS``, each with the teaching function it carries and the
      cue that sounds it. Twelve rows, one per canonical beat -- no new beats,
      no five-beat scheme competing with the story's own.
  musical_turns(blueprint)      the four required musical turns with the
      REASON and the intended AUDIBLE change at each: the immediate spoken
      attention hook, the first singing at the ERM Drop, the distinct Hero
      Shift, and the later earned Solution Signature Hook.
  shot_seeds(blueprint)         one seed per story beat in ``shot_planner``'s
      own field names; the fields only the planner can supply are named in
      ``unresolved``, never invented.
  storyboard_input(blueprint)   the same seeds as 14.1 storyboard cards.
  music_request_input(blueprint) ``pace_order`` + ``true_at_beat`` + the turns,
      the exact keys the music request builder reads.

An unknown ``method.purpose`` is refused instead of guessed: with no purpose the
lesson, testimonial and campaign gates have nothing to apply to, and a consent
gate must never fail open on a typo.

No network, no spend, no provider call, stdlib only.
"""
from __future__ import annotations

import os
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from length_formula import length_formula as _LF   # noqa: E402  the ONE arc table
from story_arc.story_arc import BEATS as PRODUCTION_BEATS   # noqa: E402  one beat list
from shot_planner.shot_planner import CONTRACT_KEYS as _CONTRACT_KEYS   # noqa: E402
from shot_planner.shot_planner import SHOT_FIELDS as _SHOT_FIELDS       # noqa: E402

SCHEMA_VERSION = "blackceo.method-plan/v1"
TOOL_VERSION = "0.1.0"

#: SPEC B1: the five purposes control/method.json can carry.
PURPOSES = ("campaign", "testimonial", "lesson", "paid_ad", "short_post")

#: SPEC C6 / method 11.3: the four evidence levels, weakest first.
EVIDENCE_LEVELS = ("planned", "generated", "inspected", "approved")

#: SPEC C1: the required cue set. A lesson sings the lesson and recaps instead
#: of pitching, so its last two cues are MEMORY_HOOK and RECAP.
BASE_CUES = ("BASELINE", "PAIN_BUILD", "ERM_DROP", "PAIN_DEEPEN", "HERO_SHIFT",
             "BREAKTHROUGH", "SOLUTION_HOOK", "COMMERCIAL_CONTINUATION")
LESSON_CUES = ("BASELINE", "PAIN_BUILD", "ERM_DROP", "PAIN_DEEPEN", "HERO_SHIFT",
               "BREAKTHROUGH", "MEMORY_HOOK", "RECAP")

#: SPEC C1 story-beat fields (method 10.3) every beat carries.
BEAT_FIELDS = ("story_beat_id", "start_s", "end_s", "development", "change",
               "why_it_belongs", "viewer_understanding", "intended_emotion",
               "character_state_before_after", "music_cue_ids")

#: SPEC C1 music-cue fields (method 10.4), all twelve of them.
CUE_FIELDS = ("music_cue_id", "story_beat_id", "trigger", "start_s",
              "pace_before", "pace_after", "rhythmic_change",
              "emotional_direction", "vocal_status", "lyric_or_dialogue",
              "transition_method", "verification_evidence")

#: A cue status that sings. Everything else (instrumental, narration, dialogue)
#: is not a sung word, so it never trips the no-singing-before-the-ERM rule.
SINGING = frozenset(("first_sung", "sung", "singing", "vocal", "vocals"))

#: METHOD-INTEGRATION 5: gate -> (name, the existing stop it sits on). No new
#: client stop is added for any method gate.
GATES = (
    ("A", "Strategy and references",
     "card recap, intake essentials and character approval"),
    ("B", "Story", "SCRIPT APPROVAL"),
    ("C", "Soundtrack", "SONG APPROVAL pick and song_dispatch.judge_take"),
    ("D", "Storyboard", "STORYBOARD APPROVAL"),
    ("E", "Master", "final-qc"),
    ("F", "Derivatives and release",
     "delivery gate, clips and trailers, Ready-to-Post kit"),
)

#: The anchor order SPEC C1 states: backstory < ERM apex < Hero Shift <
#: first visible breakthrough <= first hook < commercial.
ANCHOR_ORDER = (("backstory", "erm_apex", True),
                ("erm_apex", "hero_shift", True),
                ("hero_shift", "breakthrough", True),
                ("breakthrough", "hook", False),
                ("hook", "commercial", True))
ANCHOR_TEXT = ("backstory < ERM apex < Hero Shift < first visible breakthrough "
               "<= first hook < commercial")

#: Method 10.3: what the viewer must LEARN at each of the twelve production
#: beats (``PRODUCTION_BEATS``, in that order) and the cue that sounds it.
#: Twelve rows, one per canonical beat -- this is a projection onto the story's
#: own twelve beats, never a second beat list.
TEACHING_FUNCTION_ROWS = (
    ("attention", "BASELINE"),
    ("problem", "PAIN_BUILD"),
    ("pain", "PAIN_BUILD"),
    ("stuck", "ERM_DROP"),
    ("recognition", "ERM_DROP"),
    ("false_solution", "PAIN_DEEPEN"),
    ("guidance", "HERO_SHIFT"),
    ("solution", "HERO_SHIFT"),
    ("doubt", "BREAKTHROUGH"),
    ("proof", "BREAKTHROUGH"),
    ("signature", "SOLUTION_HOOK"),
    ("invitation", "COMMERCIAL_CONTINUATION"),
)

#: Method 11.2 / Trevor 2026-10-13: the four musical turns every method run
#: must record a REASON and an audible change for. ``kind`` picks the extra
#: rule: the attention turn is spoken, the Hero Shift must turn all three of
#: pace, rhythm and emotional direction.
TURN_SPEC = (
    ("attention_hook", "BASELINE", "attention"),
    ("first_singing", "ERM_DROP", "first_sung"),
    ("hero_shift", "HERO_SHIFT", "hero_shift"),
    ("solution_signature_hook", "SOLUTION_HOOK", "signature"),
)

#: A turn states what is heard on at least one of these. The Hero Shift states
#: all three (requirement c).
AUDIBLE_FIELDS = ("pace_after", "rhythmic_change", "emotional_direction")

#: The first production beat that may show the product (story_arc beat 8).
PRODUCT_FIRST_BEAT = PRODUCTION_BEATS.index("product_intro") \
    if "product_intro" in PRODUCTION_BEATS else len(PRODUCTION_BEATS)


def _e(code, detail):
    return {"error": code, "detail": detail}


def _text(v):
    return v.strip() if isinstance(v, str) else ""


def _purpose(method):
    return str((method or {}).get("purpose") or "").strip() \
        if isinstance(method, dict) else ""


def _purpose_cue(cue_id, purpose):
    """The lesson sings MEMORY_HOOK and recaps; every other purpose keeps the
    sale's cues. One swap table, the same one ``_required_cues`` uses."""
    if purpose == "lesson":
        return {"SOLUTION_HOOK": "MEMORY_HOOK",
                "COMMERCIAL_CONTINUATION": "RECAP"}.get(cue_id, cue_id)
    return cue_id


def _beat_index(blueprint):
    beats = blueprint.get("story_beats") if isinstance(blueprint, dict) else None
    if not isinstance(beats, list):
        return {}
    return {str(b.get("story_beat_id")): b for b in beats
            if isinstance(b, dict) and b.get("story_beat_id")}


def teaching_map(purpose=None):
    """The twelve production beats, each with its teaching function and cue.

    Fails closed to ``[]`` when the arc module and this table disagree in
    length: a map that does not land one row per canonical beat is a broken
    projection, never a shorter arc.
    """
    if len(TEACHING_FUNCTION_ROWS) != len(PRODUCTION_BEATS):
        return []
    return [{"production_beat": beat, "teaching_function": fn,
             "cue_id": _purpose_cue(cue, purpose or "")}
            for beat, (fn, cue) in zip(PRODUCTION_BEATS, TEACHING_FUNCTION_ROWS)]


def _production_beat_for_cue(cue_id, purpose):
    for row in teaching_map(purpose):
        if row["cue_id"] == cue_id:
            return row["production_beat"]
    return None


def _cue_reason(cue, beat):
    """The cue's trigger and the beat's why_it_belongs -- the record's own
    words. No prose is authored here."""
    parts = (_text(cue.get("trigger")),
             _text((beat or {}).get("why_it_belongs")))
    return " -- ".join(p for p in parts if p)


def _turn_spec(purpose):
    return [(name, _purpose_cue(cue, purpose or ""), kind)
            for name, cue, kind in TURN_SPEC]


def musical_turns(blueprint, method=None):
    """The four required turns, each with its REASON and AUDIBLE change.

    Every value is read from the record: the reason is the cue's trigger plus
    the beat's why_it_belongs, the audible change is that cue's own before /
    after / rhythm / emotional direction / vocal fields. A missing cue is left
    out -- CUE_MISSING names it, this never invents one.
    """
    purpose = _purpose(method)
    idx = _cue_index(blueprint)
    beats = _beat_index(blueprint)
    out = []
    for name, cue_id, kind in _turn_spec(purpose):
        cue = idx.get(cue_id)
        if cue is None:
            continue
        beat = beats.get(_text(cue.get("story_beat_id")))
        out.append({
            "turn": name,
            "kind": kind,
            "cue_id": cue_id,
            "production_beat": _production_beat_for_cue(cue_id, purpose),
            "at_s": _num(cue, "start_s"),
            "vocal_status": _text(cue.get("vocal_status")) or None,
            "reason": _cue_reason(cue, beat) or None,
            "audible_change": {
                "from": _text(cue.get("pace_before")) or None,
                "to": _text(cue.get("pace_after")) or None,
                "rhythm": _text(cue.get("rhythmic_change")) or None,
                "emotional_direction": _text(cue.get("emotional_direction")) or None,
                "vocal": _text(cue.get("lyric_or_dialogue")) or None,
            },
        })
    return out


def _contract(beat, cue):
    """The seven 14.3 questions answered from the beat and its cue; a question
    the blueprint does not answer stays None and is named ``unresolved``."""
    cue = cue or {}
    return {
        "lyric_text": _text(cue.get("lyric_or_dialogue")) or None,
        "viewer_understanding": _text(beat.get("viewer_understanding")) or None,
        "character_action": _text(beat.get("development")) or None,
        "visible_emotion": _text(beat.get("intended_emotion")) or None,
        "change_from_prior": _text(beat.get("change")) or None,
        "treatment": _text(beat.get("treatment")) or None,
        "necessity": _text(beat.get("why_it_belongs")) or None,
    }


def shot_seeds(blueprint, method=None):
    """One seed per story beat, in ``shot_planner``'s own field names.

    Only what the blueprint itself resolves is filled. ``story_stage`` is one
    of the twelve production beats, ``beat_cut`` marks a required musical turn
    so the planner can honour the on-beat cut floor, and ``unresolved`` names
    the planner fields this record does not carry (line ids, cast, wardrobe,
    location, camera, capability requests, cost, QC, status) -- never invented
    here.
    """
    purpose = _purpose(method)
    beats = blueprint.get("story_beats") if isinstance(blueprint, dict) else None
    if not isinstance(beats, list):
        return []
    idx = _cue_index(blueprint)
    turn_cues = {cue for _n, cue, _k in _turn_spec(purpose)}
    resolved = ("shot_id", "song_start", "song_end", "story_stage",
                "visual_objective", "product_visibility")
    out = []
    for pos, beat in enumerate(beats):
        if not isinstance(beat, dict):
            continue
        raw = beat.get("music_cue_ids")
        cue_ids = [str(c) for c in raw if str(c).strip()] \
            if isinstance(raw, list) else []
        stage = _production_beat_for_cue(cue_ids[0], purpose) if cue_ids else None
        seed = {
            "shot_id": str(beat.get("story_beat_id", pos)),
            "song_start": _num(beat, "start_s"),
            "song_end": _num(beat, "end_s"),
            "story_stage": stage,
            "visual_objective": _text(beat.get("viewer_understanding")) or None,
            "cue_ids": cue_ids,
            "beat_cut": any(c in turn_cues for c in cue_ids),
            "product_visibility": (
                "featured" if stage in PRODUCTION_BEATS
                and PRODUCTION_BEATS.index(stage) >= PRODUCT_FIRST_BEAT
                else "none"),
            "contract": _contract(beat, idx.get(cue_ids[0]) if cue_ids else None),
        }
        seed["unresolved"] = [f for f in _SHOT_FIELDS if f not in resolved] + \
            [k for k in _CONTRACT_KEYS if seed["contract"].get(k) is None]
        out.append(seed)
    return out


def storyboard_input(blueprint, method=None):
    """The seeds as 14.1 storyboard cards: the gate needs a non-blank
    ``story_stage`` and ``viewer_understanding`` on every shot, and the 14.3
    contract beside it."""
    cards = [{"shot_id": s["shot_id"],
              "story_stage": s["story_stage"],
              "viewer_understanding": s["visual_objective"],
              "contract": s["contract"],
              "turn": s["beat_cut"]}
             for s in shot_seeds(blueprint, method)]
    return {"cards": cards,
            "ready": bool(cards) and all(
                c["story_stage"] and c["viewer_understanding"] for c in cards)}


def music_request_input(blueprint, method=None):
    """The music request's method keys: ``pace_order`` (both seams, in the
    blueprint's own words), ``true_at_beat``, and the four turns with their
    reasons. ``hook_plan_seed`` carries the one key ``hook_placement.plan_for``
    needs before it measures the sheet's beats. No blueprint, no seam: ``{}``.
    """
    order = pace_order(blueprint)
    if not order:
        return {}
    return {"pace_order": order,
            "true_at_beat": order["true_at_beat"],
            "hook_plan_seed": {"true_at_beat": order["true_at_beat"]},
            "turns": musical_turns(blueprint, method)}


def production_map(blueprint, method=None):
    """Every production projection in one record: the twelve-beat teaching map,
    the four turns, the shot seeds, the storyboard cards and the music inputs.
    The stage that needs one calls the function above; this is for a receipt."""
    return {"teaching_functions": teaching_map(_purpose(method)),
            "turns": musical_turns(blueprint, method),
            "shot_seeds": shot_seeds(blueprint, method),
            "storyboard": storyboard_input(blueprint, method),
            "music_request": music_request_input(blueprint, method)}


def _num(obj, key):
    """The field as a float, or None when it is absent or unreadable (a cue
    that cannot place itself on the clock never gets an order check)."""
    v = obj.get(key) if isinstance(obj, dict) else None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _cue_index(blueprint):
    cues = blueprint.get("music_cues") if isinstance(blueprint, dict) else None
    if not isinstance(cues, list):
        return {}
    return {str(c.get("music_cue_id")): c for c in cues
            if isinstance(c, dict) and c.get("music_cue_id")}


def _hook_cue(purpose):
    return "MEMORY_HOOK" if purpose == "lesson" else "SOLUTION_HOOK"


def _commercial_cue(purpose):
    return "RECAP" if purpose == "lesson" else "COMMERCIAL_CONTINUATION"


def _required_cues(purpose):
    return LESSON_CUES if purpose == "lesson" else BASE_CUES


def _anchors(blueprint, purpose):
    """The six anchor seconds, read from the cues themselves -- the blueprint
    never states them twice, so the order check and the pace order cannot
    disagree with the record."""
    idx = _cue_index(blueprint)

    def start(cue_id):
        return _num(idx.get(cue_id, {}), "start_s")

    return {"backstory": start("BASELINE"),
            "erm_apex": start("ERM_DROP"),
            "hero_shift": start("HERO_SHIFT"),
            "breakthrough": start("BREAKTHROUGH"),
            "hook": start(_hook_cue(purpose)),
            "commercial": start(_commercial_cue(purpose))}


def _res(errors, purpose, anchors, cue_ids):
    outcome = "ok" if not errors else "rejected"
    return {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "outcome": outcome,
        "reason_code": errors[0]["error"] if errors else None,
        "errors": errors,
        "purpose": purpose or None,
        "cues": list(cue_ids),
        "anchors": anchors,
        "next_action": (
            "Proceed to script and soundtrack approval." if outcome == "ok"
            else "Fix the listed blueprint or method errors and re-run validate."),
    }


def _hero_shift_distinct(erm, hero, erm_s, hero_s):
    """Why the Hero Shift is not a distinct turn, or None when it is.

    Two turns are distinct when they start at different moments and the second
    does not simply repeat the first. When both cues state a facet, at least
    one of pace / rhythm / emotional direction must differ (requirement c).
    """
    if not isinstance(erm, dict) or not isinstance(hero, dict):
        return None
    if erm_s is not None and hero_s is not None and erm_s == hero_s:
        return ("HERO_SHIFT starts at %s s, the same moment as the ERM apex; "
                "the two turns are two distinct musical transitions "
                "(method 11.2)" % hero_s)
    same = [f for f in AUDIBLE_FIELDS
            if _text(erm.get(f)) and _text(erm.get(f)) == _text(hero.get(f))]
    if same and len(same) == len([f for f in AUDIBLE_FIELDS
                                  if _text(erm.get(f)) and _text(hero.get(f))]):
        return ("HERO_SHIFT repeats the ERM apex on %s; the second turn has to "
                "change pace, rhythm or emotional direction, not restate the "
                "first (method 11.2)" % ", ".join(same))
    return None


def _turn_errors(blueprint, purpose, idx):
    """The four required turns record a reason and an audible change.

    A missing cue is skipped: CUE_MISSING already names it. The attention turn
    is spoken and first; the Hero Shift states pace AND rhythm AND emotional
    direction; every turn states at least one audible change.
    """
    errs = []
    beats = _beat_index(blueprint)
    starts = [s for s in (_num(c, "start_s") for c in idx.values()
                          if isinstance(c, dict)) if s is not None]
    for name, cue_id, kind in _turn_spec(purpose):
        cue = idx.get(cue_id)
        if cue is None:
            continue
        label = "%s (%s)" % (name, cue_id)
        beat = beats.get(_text(cue.get("story_beat_id")))
        if not _cue_reason(cue, beat):
            errs.append(_e(
                "TURN_REASON_MISSING",
                "%s carries no reason; the cue's trigger and the beat's "
                "why_it_belongs state why the music turns here (method 10.4)"
                % label))
        stated = [f for f in AUDIBLE_FIELDS if _text(cue.get(f))]
        need = AUDIBLE_FIELDS if kind == "hero_shift" else ()
        blank = [f for f in need if not _text(cue.get(f))]
        if not stated or blank:
            errs.append(_e(
                "TURN_AUDIBLE_CHANGE_MISSING",
                "%s states no audible change on %s; every required turn records "
                "what is heard before and after (method 10.4)"
                % (label, ", ".join(blank or AUDIBLE_FIELDS))))
        if kind == "attention":
            if not _text(cue.get("lyric_or_dialogue")):
                errs.append(_e(
                    "ATTENTION_HOOK_NOT_SPOKEN",
                    "%s carries no spoken line; the ad opens with a spoken hook "
                    "before any singing (method 11.2)" % label))
            at = _num(cue, "start_s")
            if at is not None and starts and at > min(starts):
                errs.append(_e(
                    "ATTENTION_HOOK_NOT_SPOKEN",
                    "%s starts at %s s, after the record's first cue at %s s; "
                    "the spoken hook is the first thing heard (method 11.2)"
                    % (label, at, min(starts))))
    return errs


def validate(blueprint, method):
    """Check the Story Beat Blueprint against the run's method record.

    Returns the report above: ``outcome`` ok / rejected, ``reason_code`` the
    first error, every error as ``{"error": CODE, "detail": ...}``.
    """
    errors = []
    method = method if isinstance(method, dict) else {}
    purpose = str(method.get("purpose") or "").strip()
    if purpose not in PURPOSES:
        errors.append(_e(
            "PURPOSE_UNKNOWN",
            "method purpose %r is not one of %s; the lesson, testimonial and "
            "campaign gates have no purpose to apply to and fail closed"
            % (purpose, ", ".join(PURPOSES))))

    beats = blueprint.get("story_beats") if isinstance(blueprint, dict) else None
    cues = blueprint.get("music_cues") if isinstance(blueprint, dict) else None
    if not isinstance(beats, list) or not isinstance(cues, list):
        errors.append(_e("RECORD_FIELDS_MISSING",
                         "the blueprint needs story_beats[] and music_cues[]"))
        return _res(errors, purpose, {}, [])

    for pos, beat in enumerate(beats):
        if not isinstance(beat, dict):
            errors.append(_e("RECORD_FIELDS_MISSING",
                             "story_beats[%d] is not an object" % pos))
            continue
        missing = [f for f in BEAT_FIELDS if f not in beat]
        if missing:
            errors.append(_e(
                "RECORD_FIELDS_MISSING",
                "story beat %r is missing %s"
                % (beat.get("story_beat_id", pos), ", ".join(missing))))
        elif _num(beat, "start_s") is None or _num(beat, "end_s") is None:
            errors.append(_e(
                "RECORD_FIELDS_MISSING",
                "story beat %r carries a non-numeric start_s / end_s"
                % (beat.get("story_beat_id", pos),)))

    for pos, cue in enumerate(cues):
        if not isinstance(cue, dict):
            errors.append(_e("RECORD_FIELDS_MISSING",
                             "music_cues[%d] is not an object" % pos))
            continue
        missing = [f for f in CUE_FIELDS if f not in cue]
        if missing:
            errors.append(_e(
                "RECORD_FIELDS_MISSING",
                "music cue %r is missing %s"
                % (cue.get("music_cue_id", pos), ", ".join(missing))))
        elif _num(cue, "start_s") is None:
            errors.append(_e(
                "RECORD_FIELDS_MISSING",
                "music cue %r carries a non-numeric start_s"
                % (cue.get("music_cue_id", pos),)))

    idx = _cue_index(blueprint)
    missing_cues = [c for c in _required_cues(purpose) if c not in idx]
    if missing_cues:
        errors.append(_e(
            "CUE_MISSING",
            "purpose %r requires these music cues and the blueprint has none "
            "of them: %s" % (purpose, ", ".join(missing_cues))))

    erm = idx.get("ERM_DROP")
    erm_s = _num(erm, "start_s") if erm else None
    if erm is not None:
        status = str(erm.get("vocal_status") or "").strip()
        if status != "first_sung":
            errors.append(_e(
                "ERM_NOT_FIRST_SUNG",
                "the ERM_DROP cue carries vocal_status %r; the first sung line "
                "enters as the groove drops at the ERM apex (method 11.2)"
                % status))
        if erm_s is not None:
            for cue in cues:
                if not isinstance(cue, dict):
                    continue
                if str(cue.get("vocal_status") or "").strip().lower() not in SINGING:
                    continue
                at = _num(cue, "start_s")
                if at is not None and at < erm_s:
                    errors.append(_e(
                        "SINGING_BEFORE_ERM",
                        "music cue %r sings at %s s, before the ERM apex at "
                        "%s s; no sung word before the ERM (method 11.2)"
                        % (cue.get("music_cue_id"), at, erm_s)))
                    break

    anchors = _anchors(blueprint, purpose)
    hero_s, hook_s = anchors["hero_shift"], anchors["hook"]
    hero_cue = idx.get("HERO_SHIFT") or {}
    hero_distinct = _hero_shift_distinct(erm, hero_cue, erm_s, hero_s)
    if hero_distinct:
        errors.append(_e("HERO_SHIFT_NOT_DISTINCT", hero_distinct))

    if hook_s is not None and hero_s is not None and hook_s < hero_s:
        errors.append(_e(
            "HOOK_UNEARNED",
            "the first hook starts at %s s, before the solution is introduced "
            "at the Hero Shift (%s s); the build toward the hook starts once "
            "help arrives, never before it (Trevor 2026-10-13)"
            % (hook_s, hero_s)))

    reported = {err["error"] for err in errors}
    for lo, hi, strict in ANCHOR_ORDER:
        if lo == "erm_apex" and hi == "hero_shift" \
                and "HERO_SHIFT_NOT_DISTINCT" in reported:
            continue                      # already named by the specific gate
        x, y = anchors[lo], anchors[hi]
        if x is None or y is None:
            continue                      # a missing cue already named CUE_MISSING
        if (x < y) if strict else (x <= y):
            continue
        errors.append(_e(
            "ANCHOR_ORDER",
            "%s at %s s does not come %s %s at %s s; the anchors are ordered %s"
            % (lo, x, "before" if strict else "at or before", hi, y, ANCHOR_TEXT)))

    errors.extend(_turn_errors(blueprint, purpose, idx))

    if purpose == "testimonial":
        for pos, beat in enumerate(beats):
            if not isinstance(beat, dict) or not beat.get("claim"):
                continue
            if not str(beat.get("claim_source") or "").strip():
                errors.append(_e(
                    "CLAIM_UNSOURCED",
                    "story beat %r states a claim with no claim_source traceable "
                    "to the testimonial text (method 10.3)"
                    % (beat.get("story_beat_id", pos),)))

    if purpose == "campaign":
        for pos, beat in enumerate(beats):
            if isinstance(beat, dict) and "trailer_value" not in beat:
                errors.append(_e(
                    "TRAILER_VALUE_MISSING",
                    "story beat %r carries no trailer_value; a campaign beat "
                    "records whether and why it could work in a promotional "
                    "edit (method 10.3)"
                    % (beat.get("story_beat_id", pos),)))

    cue_ids = [str(c.get("music_cue_id")) for c in cues
               if isinstance(c, dict) and c.get("music_cue_id")]
    report = _res(errors, purpose, anchors, cue_ids)
    report["turns"] = musical_turns(blueprint, {"purpose": purpose})
    return report


def gates(method):
    """The A-F record (METHOD-INTEGRATION 5) with ``evidence_level`` per gate.

    The level is read from ``control/method.json``'s ``gates`` object; an
    unreadable level reads ``planned``, and ``approved`` without a recorded
    human answer (``approvals``) is written back as ``planned`` -- an approval
    is never inferred (SPEC C6).
    """
    method = method if isinstance(method, dict) else {}
    recorded = method.get("gates") if isinstance(method.get("gates"), dict) else {}
    answers = method.get("approvals") if isinstance(method.get("approvals"), dict) else {}
    out = {}
    for key, name, stop in GATES:
        level = recorded.get(key)
        if level not in EVIDENCE_LEVELS:
            level = "planned"
            evidence = ("control/method.json carries no readable evidence level "
                        "for gate %s; a record that cannot be read is planned, "
                        "never inspected" % key)
        elif level == "approved" and not answers.get(key):
            level = "planned"
            evidence = ("gate %s was recorded approved with no recorded human "
                        "answer; approved needs a recorded client or Trevor "
                        "answer (SPEC C6)" % key)
        else:
            evidence = "control/method.json gates.%s = %s" % (key, level)
            if level == "approved":
                evidence += " with a recorded answer"
        out[key] = {"gate": key, "name": name, "stop": stop,
                    "evidence_level": level, "evidence": evidence}
    return out


def true_at_beat(blueprint):
    """The U16 stage where the solution is introduced: ``the_turn`` or later.

    The blueprint may name a later stage (``the_rise``); it may never name an
    earlier one -- the 60 s golden sheet's ``lowest_point`` is the conflict C6
    defect, so such a declaration reads ``the_turn`` instead.
    """
    arc = _LF.STORY_ARC_U16
    turn = arc.index("the_turn")
    declared = blueprint.get("true_at_beat") if isinstance(blueprint, dict) else None
    declared = str(declared or "").strip()
    if declared not in arc or arc.index(declared) < turn:
        return arc[turn]
    return declared


def pace_order(blueprint):
    """The song's two pace seams, in the blueprint's own words.

    ``boundary_s`` is the ERM apex and ``return_boundary_s`` the Hero Shift --
    two distinct timestamps, the shape ``music_qc.pace_change.check_pace_plan``
    requires -- plus ``method`` (the method clauses are written into the style),
    both directions taken from the cues, and ``true_at_beat``. An unreadable
    blueprint returns ``{}``: no seam is ever invented.
    """
    idx = _cue_index(blueprint)
    erm = idx.get("ERM_DROP") or {}
    hero = idx.get("HERO_SHIFT") or {}
    erm_s, hero_s = _num(erm, "start_s"), _num(hero, "start_s")
    if erm_s is None or hero_s is None:
        return {}
    order = {
        "method": True,
        "drop_anchor": "erm_drop",
        "return_anchor": "hero_shift",
        "boundary_s": erm_s,
        "return_boundary_s": hero_s,
        # The two blueprint seconds both seams must sit on. The blueprint itself
        # lives in creative/blueprint.json, which music_qc.pace_change cannot
        # read, so this is where those seconds are copied onto the order
        # (check_pace_plan's METHOD_SEAM_ANCHORS contract).
        "erm_apex_s": erm_s,
        "hero_shift_s": hero_s,
        "true_at_beat": true_at_beat(blueprint),
        "reason": "ERM Drop at %s s (%s); Hero Shift at %s s (%s)"
                  % (erm_s, str(erm.get("trigger") or "the emotional apex").strip(),
                     hero_s, str(hero.get("trigger") or "help arrives").strip()),
    }
    for key, cue in (("drop", erm), ("return", hero)):
        direction = str(cue.get("pace_after") or "").strip()
        if direction:
            order[key] = direction
    return order
