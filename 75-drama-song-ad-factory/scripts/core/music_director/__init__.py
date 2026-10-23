#!/usr/bin/env python3
"""Music director: directive 12.1 + 12.3 stage flow. Stdlib only.

Flow: approved lyrics -> build request (current Skill 68 envelope; route
and version names read from the work-copy models.json at runtime, never
copied here) -> validate through the owner validator -> ledger plan +
reserve via W1-03 spend_ledger (every paid call reserved before dispatch)
-> candidate intake from caller-supplied fixtures (no network transport in
this module; dispatch rides the W1-06 canonical transport) -> score on the
12.3 axes (lyrical fidelity, intelligibility, voice identity, genre fit,
emotional fit, tempo, energy arc, artifacts) -> select best -> persona
lock -> extend-for-length.

Tests run on throwaway ledger DBs with fixture costs and task IDs; no paid
call leaves this module.

WW-29 (reconciled templates and researched guidance): the direction that
reaches the provider is the CALLER's style text (built from the recipe and
the music data) plus the ending clause and, when a pace plan was approved,
the pace clause. This module never mandates a wordless held-note opening and
never emits a percent-of-runtime hook rule: the opening vocalise is OPTIONAL
(a sheet may open on a verse) and the hook is placed by MEASUREMENT against
``true_at_beat`` (``sung_hook.hook_placement``), never by a heuristic. The
required directions (custom_mode, instrumental, title, lyrics, style,
negative_tags, duration) and the required clauses (cast, pace/shift, hook,
ending, negatives) must still be present on the EXACT serialized ``input``
after every mutation; an over-cap field raises
``prompt_limits.PromptLimitError`` (PROMPT_OVER_CAP) and nothing is dropped.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ending_qc
import music_qc
import prompt_limits
import suno_recipe
import spend_ledger as L
import protected_names
import words_match
import words_fit
import target_engine as TE
from method_plan import method_plan as _method_plan   # S75X-W4-U2: blueprint reader
from sung_hook import hook_placement

TOOL_NAME = "music_director"
TOOL_VERSION = "1.0.0"

#: WW-30: the createTask route, endpoint and outer model come from ONE named
#: place (suno_recipe), never a second copy here. The legacy
#: /api/v1/generate music path is retired with no fallback.
CREATE_TASK_ENDPOINT = suno_recipe.KIE_MUSIC_TASK_ENDPOINT
MUSIC_TASK_MODEL = suno_recipe.KIE_MUSIC_TASK_MODEL
MUSIC_MODEL_VALUE = suno_recipe.KIE_MUSIC_MODEL_VALUE
MUSIC_MODEL_VALUE_STATUS = suno_recipe.KIE_MUSIC_MODEL_VALUE_STATUS
GENERATE_CATALOG_ID = "suno-generate"
EXTEND_CATALOG_ID = "suno-extend"
PERSONA_OP = "generate-persona"

# ponytail: uncalibrated floors; calibrate per 17.8 before qualification.
TOTAL_MIN = 0.75
AXIS_FLOOR = 0.5
PERSONA_SIM_MIN = 0.8
HARD_ZERO_ARTIFACTS = ("clipping", "broken_transition")

_cat = None


def workcopy_paths():
    """Locate the W1-06 work copy from this file's position.

    The catalog lives at 68-kie-audio/models.json at the REPO ROOT (tracked
    tree), i.e. parents[4] of this file under the repackaged skill layout
    (75-drama-song-ad-factory/scripts/core/music_director). Legacy checkouts
    kept it under <root>/onboarding/68-kie-audio — try that first so the
    operator's existing tree keeps working, then fall back to the tracked
    repo-root copy found by walking ancestors.
    """
    here = Path(__file__).resolve()
    for anc in here.parents:
        for cand in (anc / "68-kie-audio", anc / "onboarding" / "68-kie-audio"):
            if (cand / "models.json").is_file():
                return {"root": anc, "models": cand / "models.json",
                        "validator": cand / "scripts" / "validate_audio_request.py"}
    root = here.parents[2]
    base = root / "onboarding" / "68-kie-audio"
    return {"root": root, "models": base / "models.json",
            "validator": base / "scripts" / "validate_audio_request.py"}


def catalog():
    """Read the work-copy model catalog (route ids, versions, defaults)."""
    global _cat
    if _cat is None:
        p = workcopy_paths()
        doc = json.loads(p["models"].read_text(encoding="utf-8"))
        _cat = {e.get("canonical_model_id"): e
                for e in doc.get("entries", []) if e.get("canonical_model_id")}
    return _cat


def route_model(catalog_id):
    """Current-envelope top-level route id, read from the work copy."""
    route = catalog()[catalog_id]["route_models"]["current"].split()[0]
    return route


def default_version(catalog_id=GENERATE_CATALOG_ID):
    """Default version for a catalog entry, read from the work copy."""
    return catalog()[catalog_id]["model_default"]


def version_enum(catalog_id=GENERATE_CATALOG_ID):
    """Allowed versions for a catalog entry, read from the work copy."""
    return tuple(catalog()[catalog_id]["model_enum"])


def _checked_version(version, catalog_id=GENERATE_CATALOG_ID):
    v = version or default_version(catalog_id)
    if v not in version_enum(catalog_id):
        raise ValueError("unknown version %r for %s" % (v, catalog_id))
    return v


#: WW-27: the ensemble cast gate (character_bible.character_bible), imported
#: LAZILY so a build with no cast never loads it.
_CB_MOD = None


def _cast_model():
    """character_bible.character_bible, loaded once (WW-27's cast gate)."""
    global _CB_MOD
    if _CB_MOD is None:
        import character_bible.character_bible as _cb   # noqa: PLC0415
        _CB_MOD = getattr(_cb, "character_bible", _cb)
    return _CB_MOD


def build_generate_request(lyrics_text, style_text, title, version=None,
                           vocal_gender=None, instrumental=False,
                           duration=None, callback_url="https://example.invalid/cb",
                           packet_lines=None, protected=(),
                           style_id=None, client_text=None, length_s=None,
                           mode=None, true_at_beat=None, hook_plan=None, pace_plan=None,
                           cast=None):
    """Current-envelope generate payload. Lyrics are verbatim (floor-exempt).

    F7 (words match the script exactly): when ``packet_lines`` is given, the
    lyric text is word-checked against the packet before any payload is
    built — a rewritten word ("gonna" where the packet says "going to") or
    an invented line raises ValueError ``(CAPTION_WORD_MISMATCH ...)`` and
    the master request is never built. ``packet_lines=None`` keeps the old
    behavior (packet binding happens upstream in lyric QC).

    G9 (words-fit, order 2026-10-08 11:50): when ``length_s`` is given, the
    word mix is checked against the carded length at measured delivery speed
    BEFORE any payload is built (and before the recipe guard, so the three
    options always reach the person). Infeasible raises
    ``words_fit.WordsFitError`` carrying longer ad / lower sung target /
    fewer words. A feasible plan stamps ``input.duration`` with the
    DELIVERED length (``length_s``, the card minus the END_EARLY_S tail),
    the number song_dispatch.run_takes requires, unless the caller already
    set ``duration``.

    FU-HOOK-PLACEMENT: ``true_at_beat`` (the story beat where the hook's
    words become true, from the story plan) makes the director emit the
    sheet's hook_plan (``hook_placement.plan_for``: {"true_at_beat", "beats"
    measured from the sheet}); the recipe guard measures where every hook
    sits against it (rules 2-3), and the request carries it as
    ``_hook_plan`` (underscore: song_dispatch.run_takes moves it into the
    judge's plan and never sends it to KIE). A caller-made ``hook_plan`` is
    checked and carried the same way. With a Suno style and neither, the
    guard refuses: "UNMEASURED: hook_plan". Shape in SKILL.md "Hook placement".

    WW-27: ``cast`` (a brief carrying ``characters``, or a resolved cast) runs
    the ensemble gate BEFORE anything is built and again on the FINAL
    ``input.lyrics``/``input.style``. The cast rides the script the request
    carries (the speaker tags in ``input.lyrics``), never a provider field this
    builder invents. No cast -> nothing changes.

    WW-29: the opening vocalise is OPTIONAL -- a sheet that opens on a verse
    is accepted; the mandate lives in the recipe/data (``suno_recipe``), never
    in this builder, and this builder adds no such direction. The hook is
    placed by MEASUREMENT against ``true_at_beat`` (above), never by a
    percent-of-runtime rule. The required directions and the ending, pace/shift,
    hook, cast and negative clauses reach the EXACT serialized ``input``: the
    ending clause is appended BEFORE the catalog caps are measured and the pace
    clause is appended LAST, so an overflow raises PROMPT_OVER_CAP and no clause
    is ever truncated away to fit.
    """
    # WW-27: the CAST DECISION precedes drafting. With a cast the ensemble is
    # resolved and judged FIRST -- an incomplete character, a cast with fewer
    # than two characters, a villain/foil that never speaks or is never
    # answered, a shared Suno voice direction or a single-voice cast is refused
    # while no payload exists. The final pass on the exact serialized payload
    # follows below. No cast -> nothing changes, exactly as before.
    cast_rcpt = None
    if cast is not None:
        cast_rcpt = _cast_model().check_cast(cast)
        if cast_rcpt["reasons"]:
            raise ValueError("; ".join(cast_rcpt["reasons"]))
    # FU-U4: concept mode means the client's own lines; no packet, no request.
    errors = protected_names.packet_required({"mode": mode}, packet_lines)
    if errors:
        raise ValueError("; ".join(errors))
    fit = None
    if length_s is not None and style_id:
        # v2.9.72 (R1): a style whose rap reservation cannot coexist with its
        # sung-share floor inside this card length is refused HERE, before the
        # sheet, before any spend, naming the shortest card that works. Before
        # this, R&B Flow at 30/45/60 s was planned, drafted, and then refused
        # by the fit gate forever -- the same loop the stage-3 fixes removed.
        try:
            import length_formula as _LF   # noqa: PLC0415
        except ImportError:                # pragma: no cover - packaging
            _LF = None
        if _LF is not None:
            _plan = _LF.plan(length_s, style_id=style_id)
            _bad = _plan.get("infeasible")
            if _bad:
                raise words_fit.WordsFitError(_bad["reason_code"],
                                              _bad["message"])
    if length_s is not None:
        # FU-U2: the style travels with the sheet, so R&B Flow is judged at
        # R&B Flow rates and rap words are counted (never the ballad default).
        fit = words_fit.preflight_sheet(length_s, lyrics_text, style=style_id)
        if fit["outcome"] != "ok":
            raise words_fit.WordsFitError(
                fit["reason_code"],
                fit["detail"] + " | options: "
                + "; ".join("%s -> %s" % (k, v.get("detail", v))
                            for k, v in (fit.get("options") or {}).items()))
    # U8: the DISPLAY words are spell-checked before the recipe guard, so a
    # misspelled lyric is refused with the word named while nothing has been
    # built yet (it used to surface only at delivery). Performance spelling
    # ("you-u", "sma-a-all") is display_text's own job and never refused.
    misspelled = protected_names.check_lyrics_spelling(lyrics_text, protected)
    if misspelled:
        raise ValueError("; ".join(misspelled))
    if hook_plan is None and true_at_beat is not None:
        hook_plan = hook_placement.plan_for(lyrics_text, length_s, true_at_beat, style_id)
    # The client's own lines are a contract: a sheet that drops one is refused
    # naming the line before the recipe guard asks about style or hook placement.
    if packet_lines is not None and (protected or any(
            isinstance(x, dict) for x in packet_lines)):
        # H7 (supersedes the F7 whole-text match, which forbids any sung
        # line beyond the packet): every packet line verbatim and every
        # protected name intact, extra lines allowed. This is what stops
        # the "Stale" -> "still" request files.
        errors = protected_names.check_sheet(lyrics_text, packet_lines, protected)
        if errors:
            raise ValueError("; ".join(errors))
    elif packet_lines is not None:
        errors = words_match.validate_words_match(lyrics_text, packet_lines)
        if errors:
            raise ValueError("; ".join(errors))
    suno_recipe.guard_request(style_text, lyrics_text, style_id, client_text, length_s,
                              hook_plan=hook_plan, cast=cast)  # recipe v2 + I8 + hook placement + WW-27 cast
    if not instrumental:  # I5: ask for a real ending (outro + resolved chord)
        lyrics_text, style_text = ending_qc.with_clean_ending(lyrics_text, style_text)
    # WW-07: the approved pace direction (the lowest-point drop and the return)
    # is written into the FINAL style AFTER the ending clause is appended, and
    # BEFORE the catalog cap is measured below, so an over-cap append raises
    # rather than truncating. `pace_plan` is judging metadata only -- it reaches
    # the judge as the internal `_pace_plan` and never the provider.
    _sr = getattr(suno_recipe, "suno_recipe", suno_recipe)
    pace_note = _sr.pace_clause(pace_plan)
    if pace_note:
        style_text = "%s %s" % (str(style_text).rstrip(), pace_note)
    ver = _checked_version(version)
    # WW-30: the outer model is the createTask ROUTE, never a version; the
    # version rides input.model. negative_tags is a REQUIRED direction of the
    # envelope, so it is always present (empty only when no style is known --
    # the recipe's own negative_tags() is the single source when there is one).
    req = {"endpoint": CREATE_TASK_ENDPOINT,
           "model": MUSIC_TASK_MODEL,
           "callBackUrl": callback_url,
           "input": {"custom_mode": True, "instrumental": bool(instrumental),
                     "model": ver, "style": style_text, "title": title,
                     "lyrics": lyrics_text,
                     "negative_tags": (suno_recipe.negative_tags(style_id)
                                       if style_id else "")}}
    if vocal_gender is not None:
        req["input"]["vocal_gender"] = vocal_gender
    # ponytail: ''duration'' is always PRESENT (a required direction), from the
    # caller''s value, else the delivered length. It is null only on the
    # pre-length seams (style_id=None fixtures that never reach a dispatch);
    # song_dispatch.run_takes still refuses a null/short duration on any real
    # generation. Upgrade path: require a number here once every caller knows
    # its delivered length.
    req["input"]["duration"] = duration if duration is not None else length_s
    # WW-30: the FINAL envelope is checked against the ONE contract (outer
    # model, top-level callBackUrl, nested input, exactly one lyrics source)
    # before its caps are measured; the retired flat payload is refused here.
    envelope_errs = suno_recipe.check_envelope(req)
    if envelope_errs:
        raise ValueError("; ".join(envelope_errs))
    # FU-U6 (plan E.2): the FINAL payload, measured after every mutation
    # (with_clean_ending appends the ending to the style ABOVE). Over a cap,
    # prompt_limits raises PROMPT_OVER_CAP naming field, chars, cap, source and
    # status; nothing is ever truncated.
    prompt_limits.check_request(GENERATE_CATALOG_ID, req)
    if cast is not None:
        # WW-27: the FINAL serialized payload, after every transformation --
        # the sheet the provider will sing and the style it will follow.
        cast_rcpt = _cast_model().check_cast(
            cast, sheet_text=req["input"]["lyrics"], style_text=req["input"]["style"])
        if cast_rcpt["reasons"]:
            raise ValueError("; ".join(cast_rcpt["reasons"]))
    if hook_plan is not None:
        req["_hook_plan"] = hook_plan
    # WW-07: the pace plan rides the request like the hook plan; run_takes moves
    # _pace_plan into the judge's plan and it never reaches KIE.
    if pace_plan is not None:
        req["_pace_plan"] = pace_plan
    return req


# ---- S75X-W4-U2: request inputs populated from the blueprint ---------------
#
# The blueprint (creative/blueprint.json, SPEC C1) carries the story AND the
# musical direction: ``music_cues[]`` places every turn on the clock. The
# generic request path never read it -- the director was handed a pace order
# from somewhere else, so the music could follow a different story than the
# blueprint's. These functions turn the cues into the ACTUAL inputs
# ``build_generate_request`` needs (instrumental flag, delivered length, the
# two-seam pace order, the hook plan's ``true_at_beat``) and refuse a blueprint
# whose turns have collapsed.
#
# The four turns stay DISTINCT, in this order:
#   spoken_attention_hook   the script's own opening line, spoken at zero. The
#                           opening may carry instrumental support but never
#                           becomes dead exposition: it stays under the
#                           recipe's own ``opener_max`` words.
#   erm_first_singing       the first sung word at the ERM Drop; nothing sings
#                           before it. Instrumental support before it is allowed
#                           and reported, never refused.
#   hero_shift              a SECOND transition at another moment, changing
#                           pace, rhythm AND emotional direction against the ERM.
#   solution_signature_hook the earned hook, at/after the breakthrough; no
#                           chorus or hook cue may precede that point, and the
#                           hook line may never be forced into the opening.
#
# The seams and ``true_at_beat`` come from method_plan (the ONE reader of the
# record) and are then written in the blueprint's OWN words: the ERM clause is
# its pace + rhythmic change, the Hero clause its pace + rhythm + emotional
# direction, so the clause that reaches the provider IS these cues.

#: The four turns a blueprint-driven request must keep distinguishable, in
#: story order. The first is spoken by the script; the rest are cues.
BLUEPRINT_TURNS = ("spoken_attention_hook", "erm_first_singing", "hero_shift",
                   "solution_signature_hook")
#: Every cue the four-turn receipt needs to place itself on the clock.
BLUEPRINT_REQUIRED_CUES = ("BASELINE", "ERM_DROP", "BREAKTHROUGH", "HERO_SHIFT",
                           "SOLUTION_HOOK")
#: The directions the Hero Shift must change, each distinct from the ERM Drop's.
HERO_SHIFT_AXES = ("pace_after", "rhythmic_change", "emotional_direction")
OPENING_CUE = "BASELINE"


def _blueprint_cues(blueprint):
    """music_cue_id -> cue, in record order ({} when the record has none)."""
    cues = blueprint.get("music_cues") if isinstance(blueprint, dict) else None
    if not isinstance(cues, list):
        return {}
    return {str(c.get("music_cue_id")): c for c in cues
            if isinstance(c, dict) and c.get("music_cue_id")}


def _seconds(obj, key="start_s"):
    """The field as a float, or None when absent/unreadable (never guessed)."""
    try:
        return float((obj or {}).get(key))
    except (TypeError, ValueError):
        return None


def _text(cue, *keys):
    """The first non-empty of ``keys`` on a cue, stripped ('' when none)."""
    for key in keys:
        value = str((cue or {}).get(key) or "").strip()
        if value:
            return value
    return ""


def _direction(cue, *keys):
    """The cue's own words for one transition: distinct parts joined by '; '.

    Empty when the cue names none -- the caller fails closed, because an
    unstated direction is a request that cannot follow the blueprint."""
    parts = []
    for key in keys:
        value = str((cue or {}).get(key) or "").strip().rstrip(".")
        if value and value.lower() not in [p.lower() for p in parts]:
            parts.append(value)
    return "; ".join(parts)


def _blueprint_turns(blueprint):
    """The four-turn receipt, or ValueError naming every collapsed turn."""
    idx = _blueprint_cues(blueprint)
    missing = [c for c in BLUEPRINT_REQUIRED_CUES if c not in idx]
    if missing:
        raise ValueError(
            "BLUEPRINT_CUES_MISSING: the blueprint needs music_cues %s"
            % ", ".join(missing))
    erm, hero, hook = idx["ERM_DROP"], idx["HERO_SHIFT"], idx["SOLUTION_HOOK"]
    beat, base = idx["BREAKTHROUGH"], idx[OPENING_CUE]
    erm_s, hero_s, hook_s = _seconds(erm), _seconds(hero), _seconds(hook)
    beat_s, base_s = _seconds(beat), _seconds(base)
    if None in (erm_s, hero_s, hook_s, beat_s, base_s):
        raise ValueError(
            "BLUEPRINT_CUES_MISSING: every required cue needs a numeric start_s")

    errors = []
    # 2. the first sung word enters at the ERM Drop; nothing sings before it.
    status = str(erm.get("vocal_status") or "").strip().lower()
    if status != "first_sung":
        errors.append(
            "ERM_NOT_FIRST_SUNG: ERM_DROP carries vocal_status %r; the first sung "
            "line enters as the groove drops at the ERM apex (method 11.2)"
            % status)
    early = [cid for cid, cue in idx.items()
             if str(cue.get("vocal_status") or "").strip().lower()
             in _method_plan.SINGING
             and _seconds(cue) is not None and _seconds(cue) < erm_s]
    if early:
        errors.append(
            "SINGING_BEFORE_ERM: %s sings before the ERM apex at %s s; no sung "
            "word before the ERM (method 11.2)" % (", ".join(early), erm_s))
    # 3. the Hero Shift is a distinct transition: another moment AND another
    # direction on every axis. A shared word or a blank axis is not a turn.
    if hero_s == erm_s:
        errors.append(
            "HERO_SHIFT_NOT_DISTINCT: HERO_SHIFT starts at %s s, the ERM apex's own "
            "moment; the two turns are two distinct musical transitions (method 11.2)"
            % hero_s)
    same = [key for key in HERO_SHIFT_AXES
            if not str(hero.get(key) or "").strip()
            or str(hero.get(key)).strip().lower()
            == str(erm.get(key) or "").strip().lower()]
    if same:
        errors.append(
            "HERO_SHIFT_NOT_DISTINCT: HERO_SHIFT does not change %s against the "
            "ERM Drop; the two turns are two distinct musical transitions "
            "(method 11.2)" % ", ".join(same))
    # 4. the hook is earned: it starts at/after the breakthrough, and no other
    # chorus or hook cue may precede that point.
    if hook_s < beat_s:
        errors.append(
            "HOOK_UNEARNED: SOLUTION_HOOK starts at %s s, before the breakthrough "
            "at %s s; the build toward the hook starts once the story earns it"
            % (hook_s, beat_s))
    early_hooks = [cid for cid, cue in idx.items()
                   if cid != "SOLUTION_HOOK" and cid != "ERM_DROP"
                   and ("HOOK" in cid.upper() or "CHORUS" in cid.upper())
                   and _seconds(cue) is not None and _seconds(cue) < beat_s]
    if early_hooks:
        errors.append(
            "CHORUS_BEFORE_EARNED: %s starts before the breakthrough at %s s; no "
            "triumphant chorus precedes the story earning it"
            % (", ".join(early_hooks), beat_s))
    if errors:
        raise ValueError("; ".join(errors))

    support = (erm_s - base_s) if base_s <= erm_s else 0.0
    turns = {
        "spoken_attention_hook": {
            "source": "script", "cue_id": OPENING_CUE, "at_s": base_s,
            "vocal_status": str(base.get("vocal_status") or "").strip()},
        "erm_first_singing": {
            "cue_id": "ERM_DROP", "at_s": erm_s, "vocal_status": "first_sung"},
        "hero_shift": {
            "cue_id": "HERO_SHIFT", "at_s": hero_s,
            "pace_after": str(hero.get("pace_after") or "").strip(),
            "rhythmic_change": str(hero.get("rhythmic_change") or "").strip(),
            "emotional_direction": str(hero.get("emotional_direction") or "").strip(),
            "distinct_from_erm": True},
        "solution_signature_hook": {
            "cue_id": "SOLUTION_HOOK", "at_s": hook_s,
            "earned_after": "BREAKTHROUGH", "earned_from_s": beat_s,
            "lyric": str(hook.get("lyric_or_dialogue") or "").strip()},
    }
    # A blueprint whose first sung word is required is never an instrumental-
    # only request; the flag is stated, never guessed.
    return {"turns": turns, "instrumental": False,
            "instrumental_support_s": round(support, 3)}


def blueprint_request_inputs(blueprint, style_id=None):
    """The music-request inputs, populated from the blueprint's own cues.

    Returns the ``build_generate_request`` arguments that follow the beats:
    ``instrumental``, ``length_s`` (the DELIVERED seconds of the blueprint's
    runtime target at ``style_id``, via length_formula -- None when either is
    absent, never a guess), ``pace_plan`` (the two blueprint seams, written in
    the cues' words), ``true_at_beat`` and the four-turn ``turns`` receipt
    plus ``instrumental_support_s`` (allowed before the first singing).

    Raises ValueError on a collapsed blueprint; it never invents a turn.
    """
    receipt = _blueprint_turns(blueprint)
    idx = _blueprint_cues(blueprint)
    order = _method_plan.pace_order(blueprint)
    if not order:
        raise ValueError("BLUEPRINT_CUES_MISSING: no ERM / Hero Shift seams to order")
    drop = _direction(idx["ERM_DROP"], "pace_after", "rhythmic_change")
    hero = _direction(idx["HERO_SHIFT"], *HERO_SHIFT_AXES)
    if not drop or not hero:
        raise ValueError(
            "BLUEPRINT_DIRECTION_MISSING: the blueprint must state the ERM Drop's "
            "pace and the Hero Shift's pace, rhythm and emotional direction")
    # The blueprint's OWN words ride the two seams, so pace_clause writes these
    # cues into the final style and check_pace_style measures the same text.
    order["drop"] = drop
    order["return"] = hero
    order["hero_direction"] = str(
        idx["HERO_SHIFT"].get("emotional_direction") or "").strip()
    from music_qc import pace_change as _PC   # noqa: PLC0415  the owner gate
    seam_errs = _PC.check_pace_plan(order)
    if seam_errs:
        raise ValueError("; ".join(seam_errs))
    length_s = None
    target = _seconds(blueprint, "runtime_target_seconds")
    if target is not None and style_id is not None:
        import length_formula as _LF   # noqa: PLC0415  the ONE arc/length table
        length_s = _LF.plan(target, style_id=style_id)["delivered_s"]
    return {"instrumental": receipt["instrumental"], "length_s": length_s,
            "pace_plan": order,
            "true_at_beat": _method_plan.true_at_beat(blueprint),
            "turns": receipt["turns"],
            "instrumental_support_s": receipt["instrumental_support_s"]}


def _opening_errors(lyrics_text, blueprint, length_s):
    """The opening stays the immediate attention hook, never dead exposition.

    The first section must be the script's SPOKEN line (attention hook) --
    an instrumental tag may follow it, but a sung section may not open the
    request and the earned hook lyric may not be forced into the opening. A
    spoken opener is capped by the recipe's own ``opener_max`` words.
    """
    try:
        sheet = suno_recipe.parse_lyrics(lyrics_text)
    except suno_recipe.RecipeError:
        return []          # the builder's own parse refusal names that defect
    if not sheet:
        return []
    errors = []
    first = sheet[0]
    if str(first.get("delivery") or "").strip() != "spoken":
        errors.append(
            "OPENING_NOT_ATTENTION_HOOK: the request opens with %r (%s); a "
            "blueprint request opens on the spoken attention hook, never a sung "
            "line and never a tag that carries no voice"
            % (str(first.get("tag") or ""), first.get("delivery") or "no voice"))
    if length_s is not None:
        import length_formula as _LF   # noqa: PLC0415
        words = sum(len(str(ln).split()) for ln in first.get("lines") or [])
        cap = (_LF.plan(length_s).get("words") or {}).get("opener_max")
        if cap is not None and words > cap:
            errors.append(
                "OPENING_DEAD_EXPOSITION: the spoken opener is %d words, max %d "
                "at %g s; the opening is an attention hook, not a narration block"
                % (words, cap, length_s))
    hook_line = _text(_blueprint_cues(blueprint).get("SOLUTION_HOOK"),
                      "lyric_or_dialogue")
    opened = " ".join(str(ln) for ln in first.get("lines") or [])
    if hook_line and hook_line.lower() in opened.lower():
        errors.append(
            "HOOK_FORCED_INTO_OPENING: the earned Solution Signature Hook (%r) "
            "sits in the opening; it becomes true later and is never forced "
            "into the opening" % hook_line)
    return errors


def build_blueprint_request(blueprint, lyrics_text, style_text, title, style_id=None,
                            length_s=None, **kw):
    """build_generate_request with every input populated from the blueprint.

    The four turns are checked before anything is built (``_blueprint_turns``),
    the opening is judged as the attention hook (``_opening_errors``), and the
    FINAL style must carry both blueprint directions (the owner gate
    ``song_contract.check_pace_style``) -- so a request whose music drifts off
    the beats is refused here, at the request, not after spend.
    """
    inputs = blueprint_request_inputs(blueprint, style_id=style_id)
    if length_s is None:
        length_s = inputs["length_s"]
    opening = _opening_errors(lyrics_text, blueprint, length_s)
    if opening:
        raise ValueError("; ".join(opening))
    req = build_generate_request(
        lyrics_text, style_text, title, style_id=style_id, length_s=length_s,
        instrumental=inputs["instrumental"], pace_plan=inputs["pace_plan"],
        true_at_beat=inputs["true_at_beat"], **kw)
    from song_contract import song_contract as _SC   # noqa: PLC0415  owner gate
    style_errs = _SC.check_pace_style(req["input"]["style"], inputs["pace_plan"])
    if style_errs:
        raise ValueError("; ".join(style_errs))
    return req


def build_extend_request(audio_id, continue_at=None, version=None,
                         title=None, prompt=None,
                         callback_url="https://example.invalid/cb"):
    """Current-envelope extend payload against a prior audio id."""
    ver = _checked_version(version, EXTEND_CATALOG_ID)
    req = {"endpoint": CREATE_TASK_ENDPOINT,
           "model": route_model(EXTEND_CATALOG_ID).split()[0],
           "callBackUrl": callback_url,
           "input": {"audio_id": audio_id, "model": ver}}
    if continue_at is not None:
        req["input"]["continue_at"] = continue_at
    if title is not None:
        req["input"]["title"] = title
    if prompt is not None:
        req["input"]["prompt"] = prompt
    return req


PERSONA_ROUTE = "ai-music-api/generate-persona"


def persona_route():
    """Persona-lock route id. Work copy lists this op under the
    suno-other-operations routes; asserted live below, never hardcoded as a
    version."""
    return PERSONA_ROUTE


def build_persona_request(task_id, audio_id, name, description,
                          vocal_start, vocal_end,
                          callback_url="https://example.invalid/cb"):
    """Current-envelope persona-lock payload (vocal window per work copy)."""
    return {"endpoint": CREATE_TASK_ENDPOINT, "model": persona_route(),
            "callBackUrl": callback_url,
            "input": {"task_id": task_id, "audio_id": audio_id,
                      "name": name, "description": description,
                      "vocal_start": vocal_start, "vocal_end": vocal_end}}


def validate_payload(payload):
    """Run the owner Skill 68 validator on one payload. No dispatch."""
    p = workcopy_paths()
    env = dict(os.environ, KIE_LIVE_ADAPTER_PATH="",
               PYTHONDONTWRITEBYTECODE="1")
    with tempfile.TemporaryDirectory(prefix="blackceo-DTS-303-") as td:
        f = Path(td) / "payload.json"
        f.write_text(json.dumps(payload), encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(p["validator"]), "--domain", "music",
             "--payload", str(f)], capture_output=True, text=True,
            timeout=120, env=env)
    return {"ok": r.returncode == 0, "rc": r.returncode,
            "output": (r.stdout + r.stderr)[-2000:]}


def reserve_spend(db_path, run_id, logical_key, attempt_id, payload,
                  estimated_cost, stage="music", owner="dts-303"):
    """Digest + plan + reserve before any dispatch. Estimates are caller
    fixtures: the work copy publishes no prices, so unknown cost blocks."""
    digest = L.digest_request(payload)
    plan = L.plan(db_path, run_id, logical_key, attempt_id, digest,
                  estimated_cost, stage=stage, owner=owner)
    if plan["outcome"] != "ok":
        return {"ok": False, "plan": plan, "reserve": None}
    reserve = L.reserve(db_path, run_id, logical_key, attempt_id,
                        owner=owner)
    return {"ok": reserve["outcome"] == "ok", "plan": plan,
            "reserve": reserve}


def submit_fixture_task(db_path, run_id, logical_key, attempt_id,
                        remote_task_id, owner="dts-303"):
    """Persist a fixture task id (local acceptance only, never a dispatch)."""
    return L.mark_submitted(db_path, run_id, logical_key, attempt_id,
                            remote_task_id, owner=owner)


def settle(db_path, run_id, logical_key, attempt_id, outcome, actual_cost,
           provider_ref="", evidence_ref="", owner="dts-303"):
    """Terminal + reconcile with fixture outcome/cost; writes the receipt."""
    term = L.mark_terminal(db_path, run_id, logical_key, attempt_id,
                           outcome, owner=owner)
    if term["outcome"] != "ok":
        return {"ok": False, "terminal": term, "reconcile": None}
    rec = L.reconcile(db_path, run_id, logical_key, attempt_id, outcome,
                      actual_cost, provider_ref, evidence_ref, owner=owner)
    return {"ok": rec["outcome"] == "ok", "terminal": term,
            "reconcile": rec}


def _axis(value, name, reasons):
    if not isinstance(value, (int, float)) or not (0.0 <= value <= 1.0):
        reasons.append("bad fixture %s=%r (want 0..1)" % (name, value))
        return 0.0
    return float(value)


def score_candidate(candidate, approved_lines, target_tempo_bpm,
                    tempo_tol_bpm=10.0, pronunciation_map=None):
    """Score one fixture candidate on the 12.3 axes. Deterministic."""
    reasons = []
    if target_tempo_bpm <= 0 or tempo_tol_bpm <= 0:
        raise ValueError("tempo target/tolerance must be positive")
    diff = music_qc.diff_lyrics(approved_lines,
                                candidate.get("observed_lines", []),
                                pronunciation_map)
    axes = {
        "lyrical_fidelity": diff["coverage"],
        "intelligibility": _axis(candidate.get("intelligibility"),
                                 "intelligibility", reasons),
        "voice_identity": _axis(candidate.get("voice_similarity"),
                                "voice_similarity", reasons),
        "genre_fit": _axis(candidate.get("genre_fit"), "genre_fit",
                           reasons),
        "emotional_fit": _axis(candidate.get("emotional_fit"),
                               "emotional_fit", reasons),
        "energy_arc": _axis(candidate.get("energy_match"), "energy_match",
                            reasons),
    }
    bpm = candidate.get("tempo_bpm")
    if not isinstance(bpm, (int, float)) or bpm <= 0:
        reasons.append("bad fixture tempo_bpm=%r" % (bpm,))
        axes["tempo"] = 0.0
    else:
        axes["tempo"] = max(
            0.0, 1.0 - abs(float(bpm) - target_tempo_bpm) / tempo_tol_bpm)
    flags = candidate.get("artifacts") or []
    if any(f in HARD_ZERO_ARTIFACTS for f in flags):
        axes["artifacts"] = 0.0
    elif flags:
        axes["artifacts"] = 0.5
    else:
        axes["artifacts"] = 1.0
    total = round(sum(axes.values()) / len(axes), 4)
    verdict, why = "PASS", []
    if diff["critical_missing"]:
        verdict = "FAIL"
        why.append("critical words missing: %s"
                   % ",".join(diff["critical_missing"][:8]))
    for name, score in axes.items():
        if score < AXIS_FLOOR:
            verdict = "FAIL"
            why.append("axis %s=%.2f below floor %.2f"
                       % (name, score, AXIS_FLOOR))
    if total < TOTAL_MIN:
        verdict = "FAIL"
        why.append("total %.4f below %.2f" % (total, TOTAL_MIN))
    return {"candidate_id": candidate.get("candidate_id", ""),
            "axes": {k: round(v, 4) for k, v in axes.items()},
            "total": total, "verdict": verdict,
            "reasons": reasons + why, "lyric_diff": diff}


def target_receipt(sc):
    """G4 seam: the target engine's band as a receipt block. Bands and
    numbers come from core/spoken_share through target_engine -- never a
    second band here. Past FLAG_PTS the take is redone, never cancelled."""
    flags = []
    if sc["band"] == TE.BAND_FLAG:
        flags.append("FLAG: %.4g points off target (band %d accept / %d "
                     "flag / past %d redo): accepted with a flag"
                     % (sc["worst_pts"], TE.ACCEPT_PTS, TE.FLAG_PTS,
                        TE.FLAG_PTS))
    verdict = {TE.BAND_ACCEPT: TE.VERDICT_ACCEPT,
               TE.BAND_FLAG: TE.VERDICT_FLAG,
               TE.BAND_REDO: TE.VERDICT_REDO}[sc["band"]]
    return {"verdict": verdict, "band": sc["band"],
            "worst_pts": sc["worst_pts"], "flags": flags}


def select_best(scored, target_metrics=None, targets=None):
    """Highest-total PASS candidate; handback when none passes.

    With ``target_metrics`` (the winning take's measured metrics) the G4
    target engine bands the pick against ``targets`` (default: the
    spoken_share target set). The result then carries ``target`` =
    {verdict: ACCEPT | ACCEPT_WITH_FLAG | REDO, band, worst_pts, flags}:
    within 5 points accept, past 5 up to 10 accept WITH the flag in the
    receipt, past 10 REDO (regenerate the take -- never cancel, never
    keep-the-closest)."""
    passing = [s for s in scored if s["verdict"] == "PASS"]
    if not passing:
        return {"winner": None,
                "note": "no candidate passed; bounded handback with evidence"}
    best = max(passing, key=lambda s: s["total"])
    out = {"winner": best,
           "note": "selected %s at total %.4f"
                   % (best["candidate_id"], best["total"])}
    if target_metrics is not None:
        try:
            sc = TE.score(TE.normalize_metrics(target_metrics),
                          TE.targets() if targets is None else targets)
        except TE.TargetEngineError as exc:
            raise ValueError("target_metrics: %s" % exc)
        out["target"] = target_receipt(sc)
        if sc["band"] == TE.BAND_REDO:
            out["note"] += ("; REDO: %.4g points off target (past %d), "
                            "regenerate the take"
                            % (sc["worst_pts"], TE.FLAG_PTS))
    return out


def lock_persona(winner, persona_id=""):
    """Lock the winning voice identity for continuity checks."""
    cid = winner.get("candidate_id", "")
    return {"persona_id": persona_id or ("persona:" + cid),
            "source_candidate_id": cid,
            "locked_at_total": winner.get("total", 0.0)}


def check_persona_continuity(candidate, lock, min_similarity=PERSONA_SIM_MIN):
    """Persona-continuity gate: a new take must still sound like the lock."""
    sim = candidate.get("voice_similarity_to_lock")
    if not isinstance(sim, (int, float)):
        return {"verdict": "FAIL", "similarity": sim,
                "reason": "fixture lacks voice_similarity_to_lock"}
    ok = sim >= min_similarity
    return {"verdict": "PASS" if ok else "FAIL", "similarity": sim,
            "reason": ("similarity %.2f %s %.2f against lock %s"
                       % (sim, ">=" if ok else "<", min_similarity,
                          lock.get("persona_id", "")))}


def plan_repair(section_results, repair_cap=2):
    """17.7 targeted repair: extend the failed section, keep the rest."""
    actions, n = [], 0
    for s in section_results:
        if s.get("verdict") == "FAIL" and n < repair_cap:
            actions.append({"section_id": s.get("section_id", ""),
                            "action": "extend",
                            "note": "repair the section, not the track"})
            n += 1
        elif s.get("verdict") == "FAIL":
            actions.append({"section_id": s.get("section_id", ""),
                            "action": "park",
                            "note": "repair cap spent; escalate"})
        else:
            actions.append({"section_id": s.get("section_id", ""),
                            "action": "keep", "note": ""})
    return actions
