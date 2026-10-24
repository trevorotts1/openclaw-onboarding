#!/usr/bin/env python3
"""story_planner.py: causal beats + complete pre-song scene plan (S75-T09).

Contract: SCENE-SCRIPT-CONTRACT.md "Causal beats and full scene plan".
Acceptance: S75-A09 -- missing cast/world/story plan prevents script generation;
every scene carries causal necessity and valid cast/location references; timing
is provisional until selected music.

Stdlib only. No model call in this file: the authoring dispatcher is INJECTED
(``submit``), so the unit tests drive a deterministic fake and no spend occurs.

Scope boundary: this module plans. It writes NO dialogue and NO lyrics -- the
scene plan carries *planned dialogue/lyric function* and *expected lip-sync
intention* only. Final words belong to S75-T10 (``script_writer.py``), rich
per-line validation to S75-T11 (``script_validation.py``).

Reuse, not a second pipeline: the nine causal beat fields are
``story_arc.CAUSAL_FIELDS`` verbatim, mapped to the narrative legs the contract
names --

    scene              -> consequence-first opening
    inciting_event     -> inciting pressure
    opposing_action    -> concrete resistance
    escalation         -> escalating attempts
    cost               -> visible cost of avoidance
    choice             -> consequential choice
    product_mechanism  -> relevant, fact-accurate solution
    consequence        -> visible transformation (behavior, not "all better")
    commercial_action  -> the single CTA

Revision identity is TYPE-STRICT (see ``_is_revision`` / ``_same_revision``): a
revision or pinned digest is a non-empty PLAIN string -- type identity, never
isinstance, so a str subclass is not a revision at all -- and two revisions
match only when they are type-identical AND equal, compared as plain str.
Anything else -- None, whitespace, False, True, 0, 0.0, [], {}, any non-str,
and any str SUBCLASS -- is not a declared revision and refuses with a named
error.

Every TYPE decision is exact builtin identity (S75-T09 round 7): ``type(x) is
dict`` / ``is str`` / ``is list`` / ``is int``. ``isinstance`` is never used on
a caller-supplied value -- it delegates to a spoofed ``__class__`` -- and no
``len`` / ``bool`` / ``==`` / ``!=`` / ``in`` / ``str()`` / ``repr()`` ever
touches one either. Emptiness is decided on the exact builtin or not at all;
text equality goes through ``_same_text``, which demands ``type is str`` on
BOTH sides and then compares with ``str.__eq__``. A value whose exact type is
not the required builtin is refused BY NAME (``type-identity-refused`` names a
subclass or spoofed impostor, because it can lie in ``get``, ``__bool__``,
``__len__`` or the reflected ``__eq__``) and is never silently coerced. No
entry point raises: an exception becomes a named ``fail-closed-exception``
refusal.

Run:  python3 story_planner.py validate --plan P.json --cast C.json --world W.json
      python3 story_planner.py selftest
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:                                        # reuse the nine causal fields, not a copy
    import story_arc.story_arc as story_arc  # noqa: E402
except ImportError:                          # flat layout
    import story_arc  # noqa: E402

SCHEMA_VERSION = "blackceo.scene-plan/v1"
TOOL_VERSION = "1.0.0"

#: Pre-song foundations the contract requires at exact revisions.
FOUNDATION_KEYS = (
    "research_bundle",
    "character_identity_library_snapshot",
    "episode_cast_manifest",
    "episode_world",
)

#: A complete plan is authored from the causal beats; a plan with no beats is a
#: mood board with scene numbers.
BEAT_FIELDS = story_arc.CAUSAL_FIELDS

#: What a planned scene must carry BEFORE any song exists.
SCENE_FIELDS = (
    "scene_id",                  # stable identity
    "sequence",                  # ordinal
    "causal_predecessor",        # what forced this scene ("opening" for #1)
    "causal_outcome",            # what its outcome makes necessary next
    "dramatic_purpose",          # specific story work, not "make emotional"
    "time",                      # time-of-day / elapsed relation
    "location_id",               # must resolve in the episode_world
    "world_revision",            # bound world version
    "cast_roles",                # [{cast_id, identity_revision, role, consequence}]
    "immediate_want",
    "obstacle",
    "visible_action",
    "consequential_choice",
    "emotion_before",
    "emotion_after",
    "turn_trigger",              # why the emotion changes
    "planned_dialogue_function", # what the spoken/sung lines must DO
    "claim_ids",                 # relevant research claim IDs (may be empty)
    "sound_music_intention",
    "framing_movement_intention",
    "estimated_duration_seconds",
    "timing_basis",              # must stay provisional until music is selected
    "transition",
    "lip_sync_intention",        # expected, never a measured result
)

#: Prose floors. PROPOSED AUTHORING RULE (S75-T09), not a measured limit of an
#: earlier run and not a number Trevor set: a one-line placeholder cannot clear
#: these, a written scene clears them with room to spare.
MIN_WORDS = {
    "dramatic_purpose": 8,
    "visible_action": 8,
    "consequential_choice": 6,
    "immediate_want": 5,
    "obstacle": 5,
    "turn_trigger": 5,
    "causal_outcome": 5,
    "planned_dialogue_function": 4,
    "sound_music_intention": 4,
    "framing_movement_intention": 4,
    "transition": 4,
    "lip_sync_intention": 3,
    "time": 2,
    "emotion_before": 1,
    "emotion_after": 1,
}

#: Whole-scene floor: the sum of the scene's prose. Clears the per-field floors
#: summed (65) so a scene written to the bare per-field minimum is still a
#: placeholder; a written scene carries ~195.
SCENE_MIN_WORDS = 90

OPENING = "opening"
TIMING_BASIS_PROVISIONAL = "provisional_pending_selected_music"

SCENE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")

#: Quality adjectives are not scene work. A dramatic_purpose built only from
#: these says nothing about what happens.
_QUALITY_FILLER = frozenset("""
a an and the of to very more most make makes made feel feels feeling
emotional emotion cinematic powerful transformational transformative beautiful
dramatic moving impactful epic stunning touching heartfelt inspiring deep
audience vibe vibes energy mood tone moment moments scene it this that
""".split())

#: Timing stays an estimate until the selected song is aligned.
_MEASURED_RE = re.compile(r"\b(measured|actual|confirmed|final timecode|"
                          r"post[- ]music|locked)\b", re.I)

PLAN_MUSIC_KEYS = ("song", "lyrics", "selected_music", "soundtrack")

EXIT = {"ok": 0, "rejected": 4, "error": 1}


# --------------------------------------------------------------------------- #
# helpers -- exact builtin type identity is the only decision basis
# --------------------------------------------------------------------------- #
#: The plain builtins whose own operations cannot lie. Anything else -- a
#: SUBCLASS of one of these, or an arbitrary object that may spoof ``__class__``
#: -- can lie about identity and about emptiness.
_SAFE_TYPES = (str, int, float, bool, type(None), bytes,
               list, dict, tuple, set, frozenset)

#: The named reason every such value is refused outright. Stated on the
#: refusal so the audit can see WHY a subclass is never accepted or coerced.
SUBCLASS_LIE = ("refused outright and never coerced: a subclass, or an object "
                "with a spoofed __class__, can lie in get(), __bool__, __len__ "
                "or the reflected __eq__")


def _lie_capable(value):
    """True when ``value``'s EXACT type can lie about identity or emptiness.

    ``type(value)`` only. ``isinstance`` is never used here because it asks the
    candidate itself, through a spoofed ``__class__``. A plain builtin cannot
    lie; a subclass (its ``get`` / ``__bool__`` / ``__len__`` / ``__eq__`` may
    be overridden) or an arbitrary object can.
    """
    t = type(value)
    for safe in _SAFE_TYPES:
        if t is safe:
            return False
    return True


def _show(value):
    """A safe description of a caller-supplied value.

    An exact builtin prints its own repr; anything else is described by exact
    type only -- its ``__repr__`` / ``__str__`` are NEVER called, because they
    can raise or lie.
    """
    t = type(value)
    for safe in (str, int, float, bool, type(None)):
        if t is safe:
            return repr(value)
    return "a %s instance" % t.__name__


def _type_refusal(name, value, builtin):
    """The NAMED refusal for a value whose exact type is not ``builtin``."""
    return _err("type-identity-refused",
                "%s must be exactly %s, got %s (%s); %s"
                % (name, builtin.__name__, type(value).__name__, _show(value),
                   SUBCLASS_LIE),
                field=name)


def _exact(errors, name, value, builtin):
    """Exact-type gate: True only when ``type(value) is builtin``.

    Appends the named type refusal for a value that can lie. An honest wrong
    type is left to the consuming site's own named code. This gate calls only
    ``type()`` on ``value`` -- never isinstance, len, bool, ==, !=, in, str()
    or repr().
    """
    if type(value) is builtin:
        return True
    if _lie_capable(value):
        errors.append(_type_refusal(name, value, builtin))
    return False


def _blank(v):
    """Nothing is DECLARED here: None, whitespace, empty list/dict, and any
    non-text scalar (False, True, 0, 0.0, an object).

    Declared-ness is TYPE-based, never truthiness: a falsy value is not "missing
    because it is false", and a truthy non-text value is not prose. Emptiness is
    decided on the EXACT builtin only (``type(v) is``), so a candidate's own
    ``__len__`` / ``__bool__`` / ``strip`` never gets a vote: a dict subclass
    that reports ``__len__`` 1 while empty is blank here, and a str subclass is
    not text at all.
    """
    t = type(v)
    if t is str:
        return not v.strip()
    if t is list or t is tuple or t is dict or t is set:
        return len(v) == 0
    return True


def _is_revision(value):
    """A DECLARED revision: a non-empty PLAIN string (S75-T09 round 6).

    The one revision predicate and it is used at EVERY revision/digest
    consumption site. Anything else -- None, "", whitespace, False, True, 0,
    0.0, [], {}, any non-str, and every str SUBCLASS -- is NOT a declared
    revision and must refuse with a named error. Truthiness never decides this,
    and a subclass never declares one through its own ``strip``.
    """
    return type(value) is str and value.strip() != ""


def _same_text(left, right):
    """Compare two texts as PLAIN str -- never through a candidate's ``__eq__``.

    Both sides must be exactly ``str`` or the answer is False. The comparison
    itself is ``str.__eq__``, so no caller-supplied ``__eq__`` / ``__ne__`` can
    vote, contradict itself, or claim equality with everything.
    """
    return (type(left) is str and type(right) is str
            and str.__eq__(left, right) is True)


def _same_revision(left, right):
    """Exact AND type-identical match, compared as plain str.

    0 can never satisfy False; the string "false" is a value while the boolean
    False is not a revision at all. Two undeclared values never match, and the
    comparison never delegates to a candidate's own ``__eq__``.
    """
    return (_is_revision(left) and _is_revision(right)
            and _same_text(left, right))


def _object(value):
    """A JSON object or nothing -- EXACTLY a dict.

    Every artifact is an object; a non-object reaches the check that consumes it
    as None and is refused BY NAME there -- never as an AttributeError inside
    ``.get`` / ``_index`` (S75-T09 round 4 secondary). A dict SUBCLASS is not an
    object here either: its ``get`` / ``__len__`` / ``__contains__`` may lie.
    """
    return value if type(value) is dict else None


def _words(text):
    """Word count of a PLAIN str. Anything else counts as no words at all --
    no ``str()`` coercion, so a lying ``__str__`` never inflates a floor."""
    return len(re.findall(r"[A-Za-z0-9']+", text)) if type(text) is str else 0


def _err(code, detail, **extra):
    out = {"error": code, "detail": detail}
    out.update({k: v for k, v in extra.items() if v is not None})
    return out


def _result(outcome, reason_code, errors, **extra):
    out = {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "outcome": outcome,
        "reason_code": reason_code,
        "errors": errors,
        "next_action": (
            "Plan is complete; hold it for whole-package review. Music may now "
            "be selected against this exact revision."
            if outcome == "ok"
            else "Fix the listed scene/beat defects and re-run validate_scene_plan."
        ),
    }
    out.update(extra)
    return out


def _crash(name, exc):
    """The named refusal for an exception: a validator that raises is not
    fail-closed, so the exception becomes a refusal, never a crash."""
    return [_err("fail-closed-exception",
                 "%s refused to decide: %s raised %s. A validator that raises "
                 "instead of refusing is not fail-closed."
                 % (name, name, type(exc).__name__),
                 field=name)]


# --------------------------------------------------------------------------- #
# foundation: no plan authoring without verified inputs
# --------------------------------------------------------------------------- #
def validate_foundation(foundation):
    """Every early foundation present at a pinned revision with a digest."""
    errors = []
    if not _exact(errors, "foundation", foundation, dict):
        return _result("error", "foundation-not-an-object",
                       [_err("foundation-not-an-object",
                             "foundation must be a JSON object, got %s"
                             % type(foundation).__name__)] + errors)
    for key in FOUNDATION_KEYS:
        art = foundation.get(key)
        if art is None:
            errors.append(_err("foundation-missing",
                               "%s is missing; no causal plan can be authored without it" % key,
                               field=key))
            continue
        if not _exact(errors, key, art, dict):
            errors.append(_err("artifact-not-an-object",
                               "%s must be a JSON object, got %s"
                               % (key, type(art).__name__), field=key))
            continue
        if not _is_revision(art.get("revision")):
            _exact(errors, "%s.revision" % key, art.get("revision"), str)
            errors.append(_err("foundation-unversioned",
                               "%s carries no revision; a revision is a non-empty string, got %s"
                               % (key, _show(art.get("revision"))), field=key))
        if not _is_revision(art.get("digest")):
            _exact(errors, "%s.digest" % key, art.get("digest"), str)
            errors.append(_err("foundation-undigested",
                               "%s carries no content digest" % key, field=key))

    cast = _object(foundation.get("episode_cast_manifest"))
    world = _object(foundation.get("episode_world"))
    cast_rows = cast.get("cast") if cast is not None else None
    world_rows = world.get("locations") if world else None
    if cast is not None and not _exact(errors, "episode_cast_manifest.cast", cast_rows, list):
        errors.append(_err("cast-manifest-shape",
                           "episode_cast_manifest.cast must be a list of {cast_id, "
                           "identity_revision}", field="episode_cast_manifest"))
    if world is not None and not _exact(errors, "episode_world.locations", world_rows, list):
        errors.append(_err("world-shape",
                           "episode_world.locations must be a list of {location_id}",
                           field="episode_world"))

    # an EMPTY foundation set is as unusable as a missing one: it must stop the
    # authoring writer BEFORE the dispatcher is called, not afterwards. The
    # emptiness test runs on the exact builtin -- never on a candidate __len__.
    for code, rows, detail in (
            ("cast-manifest-empty", cast_rows, "episode_cast_manifest.cast"),
            ("world-locations-empty", world_rows, "episode_world.locations"),
            ("research-claims-empty",
             (_object(foundation.get("research_bundle")) or {}).get("claims"),
             "research_bundle.claims")):
        _exact(errors, detail, rows, list)
        if type(rows) is not list or len(rows) == 0:
            errors.append(_err(code,
                               "%s is empty or absent; a foundation with no declared set cannot "
                               "author a plan" % detail, field=detail))

    if errors:
        return _result("rejected", errors[0]["error"], errors,
                       foundation_keys=list(foundation))
    return _result("ok", "foundation-complete", [])


def validate_causal_beats(beats):
    """All nine causal legs declared. 'And then' sequencing is not a beat."""
    errors = []
    if not _exact(errors, "causal_story_beats", beats, dict):
        return _result("error", "beats-not-an-object",
                       [_err("beats-not-an-object",
                             "causal_story_beats must be a JSON object")] + errors)
    missing = []
    for f in BEAT_FIELDS:
        val = beats.get(f)
        if not _exact(errors, "causal_story_beats.%s" % f, val, str) or _blank(val):
            missing.append(f)
    if missing:
        errors.append(_err("causal-beat-missing",
                           "every causal leg must be declared before a scene plan: missing %s"
                           % ", ".join(missing), fields=missing))
    for f in BEAT_FIELDS:
        val = beats.get(f)
        if type(val) is str and not _blank(val) and _words(val) < 3:
            errors.append(_err("causal-beat-thin",
                               "beat %r is %d word(s); a beat states what changes and why"
                               % (f, _words(val)), field=f))
    if errors:
        return _result("rejected", errors[0]["error"], errors)
    return _result("ok", "causal-beats-complete", [])


# --------------------------------------------------------------------------- #
# the plan validator
# --------------------------------------------------------------------------- #
def _index(rows, *keys):
    """Index rows by the first of ``keys`` they carry.

    Tolerant on purpose: the world and cast writers are separate units (S75-T08,
    S75-T06) and their row key is not fixed by this contract, so ``location_id``
    and ``id`` (resp. ``cast_id`` and ``character_id``) both resolve.

    Exact types only: the row set must be exactly a list, a row exactly a dict,
    and an identifier exactly a str -- a subclass identifier is never indexed,
    so no candidate ``__hash__`` / ``__eq__`` can resolve a reference it should
    not. Keys written here are plain str, so the lookups below are plain str
    lookups too.
    """
    out = {}
    for row in rows if type(rows) is list else []:
        if type(row) is not dict:
            continue
        for key in keys:
            val = row.get(key)
            if type(val) is str and val != "":
                out[val] = row
                break
    return out


def _check_scene_detail(scene, sid):
    """Prose presence + floors + purpose that states actual story work.

    ``scene`` is an exact dict (the caller gates it). Every field value is
    type-gated before it is read: a field is prose only when it is exactly a
    str, so no ``strip`` / ``__str__`` / ``__len__`` of a candidate counts
    words, proves presence or clears a floor.
    """
    errors = []
    for field in SCENE_FIELDS:
        if field not in scene:
            errors.append(_err("scene-field-missing",
                               "scene %r is missing %r" % (sid, field),
                               scene_id=sid, field=field))
            continue
        if field in ("sequence", "estimated_duration_seconds", "world_revision",
                     "cast_roles", "claim_ids"):
            continue
        val = scene.get(field)
        if not _exact(errors, "scene %s %s" % (sid, field), val, str):
            # a non-text field dodges the blank check AND every word floor
            errors.append(_err("scene-field-not-text",
                               "scene %r %r is %s, not prose text"
                               % (sid, field, type(val).__name__),
                               scene_id=sid, field=field))
        elif _blank(val):
            errors.append(_err("scene-field-blank",
                               "scene %r has a blank %r" % (sid, field),
                               scene_id=sid, field=field))

    for field, floor in MIN_WORDS.items():
        val = scene.get(field)
        if type(val) is str and val.strip() != "":
            n = _words(val)
            if n < floor:
                errors.append(_err("scene-detail-below-minimum",
                                   "scene %r %r is %d word(s), contract minimum is %d"
                                   % (sid, field, n, floor),
                                   scene_id=sid, field=field, have=n, need=floor))

    purpose = scene.get("dramatic_purpose")
    if type(purpose) is str:
        toks = [t.lower() for t in re.findall(r"[A-Za-z']+", purpose)]
        if toks and all(t in _QUALITY_FILLER for t in toks):
            errors.append(_err("purpose-quality-only",
                               "scene %r dramatic_purpose is quality adjectives, not story work: %r"
                               % (sid, purpose), scene_id=sid, field="dramatic_purpose"))

    total = sum(_words(scene.get(f)) for f in MIN_WORDS if type(scene.get(f)) is str)
    if total < SCENE_MIN_WORDS:
        errors.append(_err("scene-placeholder-thin",
                           "scene %r carries %d prose word(s), contract minimum is %d -- "
                           "a one-line placeholder is not a scene"
                           % (sid, total, SCENE_MIN_WORDS),
                           scene_id=sid, field="_scene", have=total, need=SCENE_MIN_WORDS))

    dur = scene.get("estimated_duration_seconds")
    if type(dur) is int or type(dur) is float:
        if dur <= 0:
            errors.append(_err("duration-invalid",
                               "scene %r estimated_duration_seconds must be a positive number, got %s"
                               % (sid, _show(dur)), scene_id=sid,
                               field="estimated_duration_seconds"))
    else:
        # a bool is NOT a duration, and no other exact type is either
        _exact(errors, "scene %s estimated_duration_seconds" % sid, dur, int)
        errors.append(_err("duration-invalid",
                           "scene %r estimated_duration_seconds must be a positive number, got %s"
                           % (sid, _show(dur)), scene_id=sid,
                           field="estimated_duration_seconds"))

    basis = scene.get("timing_basis")
    if not _exact(errors, "scene %s timing_basis" % sid, basis, str) \
            or not _same_text(basis, TIMING_BASIS_PROVISIONAL):
        errors.append(_err("timing-not-provisional",
                           "scene %r timing_basis=%s; a pre-song plan is provisional until the "
                           "selected music is aligned (%r)"
                           % (sid, _show(basis), TIMING_BASIS_PROVISIONAL),
                           scene_id=sid, field="timing_basis"))

    lip = scene.get("lip_sync_intention")
    if type(lip) is str and _MEASURED_RE.search(lip):
        errors.append(_err("timing-claims-measured",
                           "scene %r lip_sync_intention claims a measured result before any "
                           "music exists: %r" % (sid, lip),
                           scene_id=sid, field="lip_sync_intention"))
    return errors


def _check_causal_chain(scenes):
    """Because/therefore: each outcome IS the next cause. 'And then' fails.

    Both sides of every link comparison are exact str before they are compared
    (``_same_text``), so a candidate's ``__eq__`` / ``__ne__`` can never declare
    its own link intact.
    """
    errors = []
    if not scenes:
        return errors
    for i, scene in enumerate(scenes):
        sid = _show(scene.get("scene_id"))
        pred = scene.get("causal_predecessor")
        outcome = scene.get("causal_outcome")
        if i == 0:
            if not _exact(errors, "scene %s causal_predecessor" % sid, pred, str) \
                    or not _same_text(pred, OPENING):
                errors.append(_err("opening-unlinked",
                                   "scene %s is first but causal_predecessor=%s; a consequence-first "
                                   "opening declares %r" % (sid, _show(pred), OPENING),
                                   scene_id=sid, field="causal_predecessor"))
            continue
        prev = scenes[i - 1]
        prev_outcome = prev.get("causal_outcome")
        pred_declared = _exact(errors, "scene %s causal_predecessor" % sid, pred, str)
        _exact(errors, "the previous scene's causal_outcome", prev_outcome, str)
        if not pred_declared or _blank(pred):
            errors.append(_err("causal-predecessor-missing",
                               "scene %s declares no causal_predecessor; a blank link is not a link"
                               % sid, scene_id=sid, field="causal_predecessor"))
        elif not _same_text(pred, prev_outcome):
            errors.append(_err("causal-link-broken",
                               "scene %s is caused by %s but the previous scene's outcome is %s -- "
                               "the chain is decorative, not causal"
                               % (sid, _show(pred), _show(prev_outcome)),
                               scene_id=sid, field="causal_predecessor"))
        if not _exact(errors, "scene %s causal_outcome" % sid, outcome, str) or _blank(outcome):
            errors.append(_err("causal-outcome-missing",
                               "scene %s changes nothing that forces the next scene"
                               % sid, scene_id=sid, field="causal_outcome"))
    last = scenes[-1]
    last_id = _show(last.get("scene_id"))
    if not _exact(errors, "scene %s causal_outcome" % last_id,
                  last.get("causal_outcome"), str) or _blank(last.get("causal_outcome")):
        errors.append(_err("causal-outcome-missing",
                           "the final scene %s carries no outgoing consequence" % last_id,
                           scene_id=last_id, field="causal_outcome"))
    return errors


def validate_scene_plan(plan, cast_manifest=None, world=None, research=None):
    """Validate a complete pre-song scene plan against its foundations.

    ``cast_manifest``/``world``/``research`` may be passed directly or reached
    through ``plan['foundation']``; a scene reference that does not resolve is a
    defect either way.

    This entry point never raises: an exception becomes a NAMED refusal
    (``fail-closed-exception``), because a validator that raises instead of
    refusing is not fail-closed.
    """
    try:
        return _validate_scene_plan(plan, cast_manifest, world, research)
    except Exception as exc:                       # noqa: BLE001 - refuse, never crash
        return _result("error", "fail-closed-exception",
                       _crash("validate_scene_plan", exc), scene_count=0)


def _validate_scene_plan(plan, cast_manifest, world, research):
    errors = []
    # the plan is EXACTLY a dict: a dict subclass's get/__contains__/__len__ may
    # lie, so it is refused by name before a single field is read
    if not _exact(errors, "scene_plan", plan, dict):
        return _result("error", "plan-not-an-object",
                       [_err("plan-not-an-object",
                             "scene_plan must be a JSON object, got %s"
                             % type(plan).__name__)] + errors)

    raw_foundation = plan.get("foundation")
    if raw_foundation is None:
        foundation = {}
    elif not _exact(errors, "scene_plan.foundation", raw_foundation, dict):
        errors.append(_err("artifact-not-an-object",
                           "foundation must be a JSON object, got %s"
                           % type(raw_foundation).__name__, field="foundation"))
        foundation = {}
    else:
        foundation = raw_foundation

    # an explicit argument is authoritative even when EMPTY: an empty set must
    # fail closed below, never be silently swapped for the plan's own binding
    if cast_manifest is None:
        cast_manifest = foundation.get("episode_cast_manifest")
    if world is None:
        world = foundation.get("episode_world")
    if research is None:
        research = foundation.get("research_bundle")

    # artifacts are JSON objects. A non-object refuses BY NAME at this boundary
    # -- never as an AttributeError inside _index/.get (S75-T09 round 4).
    for name, art in (("episode_cast_manifest", cast_manifest),
                      ("episode_world", world),
                      ("research_bundle", research)):
        if art is not None and not _exact(errors, name, art, dict):
            errors.append(_err("artifact-not-an-object",
                               "%s must be a JSON object, got %s" % (name, type(art).__name__),
                               field=name))
    cast_manifest = _object(cast_manifest)
    world = _object(world)
    research = _object(research)

    version = plan.get("schema_version")
    if not _exact(errors, "schema_version", version, str) or _blank(version):
        errors.append(_err("schema-version-missing",
                           "schema_version is required; an unversioned plan is not a contract plan"))
    elif not _same_text(version, SCHEMA_VERSION):
        errors.append(_err("schema-version-unsupported",
                           "schema_version=%s, expected %r"
                           % (_show(version), SCHEMA_VERSION)))

    for field, builtin in (("plan_id", str), ("episode_id", str),
                           ("foundation_revisions", dict)):
        val = plan.get(field)
        if not _exact(errors, "scene_plan.%s" % field, val, builtin) or _blank(val):
            errors.append(_err("plan-field-missing",
                               "scene_plan is missing %r" % field, field=field))

    for key in FOUNDATION_KEYS:
        bound = foundation.get(key)
        if not _exact(errors, "foundation.%s" % key, bound, dict) or _blank(bound):
            errors.append(_err("foundation-not-bound",
                               "scene_plan does not bind %s; an unbound plan cannot gate a script"
                               % key, field=key))

    cast_by_id = _index((cast_manifest or {}).get("cast"), "cast_id", "character_id")
    loc_by_id = _index((world or {}).get("locations"), "location_id", "id")
    claim_by_id = _index((research or {}).get("claims"), "claim_id", "id")
    world_rev = (world or {}).get("revision")

    # reference sets fail closed: an empty, absent or malformed set must NOT
    # silently switch resolution off the way a populated one enforces it. The
    # emptiness test runs on the exact builtin list, never on a candidate
    # __len__ / __bool__ (a list subclass that reports length 1 while empty is
    # empty here).
    for code, rows, detail in (
            ("cast-manifest-empty", (cast_manifest or {}).get("cast"), "episode_cast_manifest.cast"),
            ("world-locations-empty", (world or {}).get("locations"), "episode_world.locations"),
            ("research-claims-empty", (research or {}).get("claims"), "research_bundle.claims")):
        _exact(errors, detail, rows, list)
        if type(rows) is not list or len(rows) == 0:
            errors.append(_err(code,
                               "%s is empty or absent; every scene reference must resolve "
                               "against a declared set" % detail, field=detail))

    # the plan pins revisions; they must match the artifacts actually validated
    pins = plan.get("foundation_revisions")
    if type(pins) is not dict or len(pins) == 0:
        errors.append(_err("foundation-revisions-missing",
                           "foundation_revisions must pin every foundation artifact; a plan that "
                           "pins nothing cannot be reconciled with what it validates"))
    else:
        for key in FOUNDATION_KEYS:
            pin = pins.get(key)
            artifact = _object(
                cast_manifest if key == "episode_cast_manifest" else
                (world if key == "episode_world" else
                 (research if key == "research_bundle" else foundation.get(key))))
            if not _exact(errors, "foundation_revisions.%s" % key, pin, dict):
                errors.append(_err("foundation-revision-unpinned",
                                   "foundation_revisions carries no pin for %s; a missing pin is a "
                                   "refusal, not a waiver" % key, field="foundation_revisions"))
                continue
            revision = (artifact or {}).get("revision")
            pin_revision = pin.get("revision")
            if not _is_revision(revision):
                _exact(errors, "%s.revision" % key, revision, str)
                errors.append(_err("artifact-revision-missing",
                                   "%s declares no revision (%s is not a revision; a revision is a "
                                   "non-empty string); absence of a revision is not "
                                   "permission to skip the revision check"
                                   % (key, _show(revision)), field=key))
            elif not _is_revision(pin_revision):
                _exact(errors, "foundation_revisions.%s.revision" % key, pin_revision, str)
                errors.append(_err("foundation-pin-revision-invalid",
                                   "foundation_revisions pins %s revision %s; a pin must declare a "
                                   "non-empty string revision" % (key, _show(pin_revision)),
                                   field="foundation_revisions"))
            elif not _same_revision(pin_revision, revision):
                errors.append(_err("foundation-revision-mismatch",
                                   "plan pins %s revision %s but the validated artifact is %s"
                                   % (key, _show(pin_revision), _show(revision)),
                                   field="foundation_revisions"))
            digest = (artifact or {}).get("digest")
            pin_digest = pin.get("digest")
            if not _is_revision(digest):
                _exact(errors, "%s.digest" % key, digest, str)
                errors.append(_err("artifact-digest-missing",
                                   "%s declares no content digest; an undigested artifact cannot "
                                   "be pinned" % key, field=key))
            elif not _is_revision(pin_digest):
                _exact(errors, "foundation_revisions.%s.digest" % key, pin_digest, str)
                errors.append(_err("foundation-revision-undigested",
                                   "foundation_revisions pins %s without a digest" % key,
                                   field="foundation_revisions"))
            elif not _same_revision(pin_digest, digest):
                errors.append(_err("foundation-digest-mismatch",
                                   "plan pins %s digest %s but the validated artifact is %s"
                                   % (key, _show(pin_digest), _show(digest)),
                                   field="foundation_revisions"))

    # a world that declares NO revision must refuse, not switch the check off
    _exact(errors, "episode_world.revision", world_rev, str)
    if not _is_revision(world_rev):
        errors.append(_err("world-revision-missing",
                           "episode_world declares no revision (%s is not a revision; a revision is "
                           "a non-empty string); absence of a revision is not permission to skip "
                           "the world-revision check" % _show(world_rev),
                           field="episode_world"))

    scenes = plan.get("scenes")
    if type(scenes) is not list or len(scenes) == 0:
        errors.append(_err("scenes-missing",
                           "scenes must be a non-empty list of planned scenes"))
        _exact(errors, "scene_plan.scenes", scenes, list)
        return _result("rejected", errors[0]["error"], errors, scene_count=0)

    seen_ids = set()
    seen_seq = []
    for i, scene in enumerate(scenes):
        if not _exact(errors, "scene_plan.scenes[%d]" % i, scene, dict):
            errors.append(_err("scene-not-an-object",
                               "scene index %d is %s, not an object" % (i, _show(scene))))
            continue
        sid = scene.get("scene_id")
        if not _exact(errors, "scene %d scene_id" % i, sid, str) \
                or SCENE_ID_RE.match(sid) is None:
            errors.append(_err("scene-id-invalid",
                               "scene index %d has scene_id %s (pattern %s)"
                               % (i, _show(sid), SCENE_ID_RE.pattern), field="scene_id"))
            sid = "index_%d" % i
        elif sid in seen_ids:
            errors.append(_err("scene-id-duplicate",
                               "scene_id %r appears twice" % sid, scene_id=sid))
        seen_ids.add(sid)

        seq = scene.get("sequence")
        if not _exact(errors, "scene %s sequence" % sid, seq, int):
            errors.append(_err("sequence-invalid",
                               "scene %r sequence must be an int, got %s" % (sid, _show(seq)),
                               scene_id=sid, field="sequence"))
        else:
            seen_seq.append((seq, sid))

        errors.extend(_check_scene_detail(scene, sid))

        # cast references resolve to the declared identity revision
        roles = scene.get("cast_roles")
        if not _exact(errors, "scene %s cast_roles" % sid, roles, list) or len(roles) == 0:
            errors.append(_err("cast-missing",
                               "scene %r declares no cast; an undefined speaker is not a scene"
                               % sid, scene_id=sid, field="cast_roles"))
        else:
            for j, role in enumerate(roles):
                if not _exact(errors, "scene %s cast_roles[%d]" % (sid, j), role, dict):
                    errors.append(_err("cast-role-shape",
                                       "scene %r cast_roles[%d] is not an object" % (sid, j),
                                       scene_id=sid, field="cast_roles"))
                    continue
                cid = role.get("cast_id")
                # the lookup key must be exactly a str: a candidate __hash__ /
                # __eq__ must never resolve a cast reference it should not
                if not _exact(errors, "scene %s cast_roles[%d].cast_id" % (sid, j), cid, str):
                    errors.append(_err("cast-undefined",
                                       "scene %r names cast_id %s, absent from the cast manifest"
                                       % (sid, _show(cid)), scene_id=sid, field="cast_roles",
                                       cast_id=_show(cid)))
                    row = None
                else:
                    row = cast_by_id.get(cid)
                    if row is None:
                        errors.append(_err("cast-undefined",
                                           "scene %r names cast_id %r, absent from the cast manifest"
                                           % (sid, cid), scene_id=sid, field="cast_roles",
                                           cast_id=cid))
                if row is not None:
                    role_revision = role.get("identity_revision")
                    row_revision = row.get("identity_revision")
                    if not _is_revision(role_revision) or not _is_revision(row_revision):
                        # neither side declaring a revision is a refusal, never a match
                        _exact(errors, "scene %s cast %s identity_revision" % (sid, cid),
                               role_revision, str)
                        _exact(errors, "the manifest row for %s identity_revision" % _show(cid),
                               row_revision, str)
                        errors.append(_err("cast-revision-missing",
                                           "scene %r cast %r binds identity_revision %s and the "
                                           "manifest holds %s; a revision is a non-empty string and "
                                           "absence of one is not permission to skip the identity "
                                           "check"
                                           % (sid, cid, _show(role_revision),
                                              _show(row_revision)),
                                           scene_id=sid, field="cast_roles", cast_id=cid))
                    elif not _same_revision(role_revision, row_revision):
                        errors.append(_err("cast-revision-mismatch",
                                           "scene %r binds %r revision %r, manifest holds %r"
                                           % (sid, cid, role_revision, row_revision),
                                           scene_id=sid, field="cast_roles", cast_id=cid))
                for field in ("role", "consequence"):
                    val = role.get(field)
                    if not _exact(errors, "scene %s cast %s %s" % (sid, _show(cid), field),
                                  val, str) or _blank(val):
                        errors.append(_err("cast-role-incomplete",
                                           "scene %r cast %s has no %r"
                                           % (sid, _show(cid), field),
                                           scene_id=sid, field="cast_roles",
                                           cast_id=_show(cid)))

        # world/location references resolve, and to the bound revision
        loc = scene.get("location_id")
        if not _exact(errors, "scene %s location_id" % sid, loc, str) \
                or loc == "" or loc not in loc_by_id:
            errors.append(_err("location-undefined",
                               "scene %r location_id %s is not in the episode world"
                               % (sid, _show(loc)), scene_id=sid, field="location_id",
                               location_id=_show(loc)))
        scene_world_revision = scene.get("world_revision")
        if not _is_revision(scene_world_revision) or not _is_revision(world_rev):
            _exact(errors, "scene %s world_revision" % sid, scene_world_revision, str)
            errors.append(_err("world-revision-unbound",
                               "scene %r cannot bind a world revision: scene world_revision=%s, "
                               "episode_world.revision=%s; a revision is a non-empty string and "
                               "absence of either side is a refusal, not permission to skip the "
                               "check"
                               % (sid, _show(scene_world_revision), _show(world_rev)),
                               scene_id=sid, field="world_revision"))
        elif not _same_revision(scene_world_revision, world_rev):
            errors.append(_err("world-revision-mismatch",
                               "scene %r binds world revision %r, world holds %r"
                               % (sid, scene_world_revision, world_rev),
                               scene_id=sid, field="world_revision"))

        claims = scene.get("claim_ids")
        if not _exact(errors, "scene %s claim_ids" % sid, claims, list) \
                or any(type(c) is not str for c in claims):
            errors.append(_err("claim-ids-invalid",
                               "scene %r claim_ids must be a list of strings, got %s"
                               % (sid, _show(claims)), scene_id=sid, field="claim_ids"))
        else:
            for cid in claims:
                if cid not in claim_by_id:
                    errors.append(_err("claim-undefined",
                                       "scene %r cites claim %r, absent from the research bundle"
                                       % (sid, cid), scene_id=sid, field="claim_ids",
                                       claim_id=cid))

    # ordering: contiguous 1..N, chain intact
    if len(seen_seq) == len([s for s in scenes if type(s) is dict]):
        seqs = [n for n, _ in seen_seq]
        if seqs != list(range(1, len(seqs) + 1)):
            errors.append(_err("sequence-gap",
                               "sequence must be contiguous from 1; got %r" % (seqs,)))
    errors.extend(_check_causal_chain([s for s in scenes if type(s) is dict]))

    findings = errors
    if findings:
        return _result("rejected", findings[0]["error"], findings,
                       scene_count=len(scenes),
                       defect_count=len(findings))
    return _result("ok", "scene-plan-valid", [],
                   scene_count=len(scenes),
                   plan_id=_show(plan.get("plan_id")),
                   scene_ids=[s.get("scene_id") for s in scenes])


# --------------------------------------------------------------------------- #
# music gate: a song is never written against an incomplete plan
# --------------------------------------------------------------------------- #
def music_gate(plan, cast_manifest=None, world=None, research=None):
    """May the intended song be selected/written against this plan?

    Refuses on: any plan defect, a plan that is not marked complete, or a plan
    that already carries song/lyric material (that is S75-T10's output and
    cannot be its own input).

    This entry point never raises: an exception becomes a NAMED refusal.

    The completion mark and the song scan run only on an EXACT dict plan: a dict
    subclass can hide a key in ``__contains__``, lie in ``get`` about ``status``,
    or report a false ``__len__``, so it is refused by name instead of being
    asked whether it is complete.
    """
    try:
        return _music_gate(plan, cast_manifest, world, research)
    except Exception as exc:                       # noqa: BLE001 - refuse, never crash
        out = _result("error", "fail-closed-exception", _crash("music_gate", exc))
        out["allowed"] = False
        return out


def _music_gate(plan, cast_manifest, world, research):
    result = _validate_scene_plan(plan, cast_manifest, world, research)
    reasons = list(result["errors"])
    if not _exact(reasons, "scene_plan", plan, dict):
        reasons.append(_err("plan-not-complete",
                            "plan status=unreachable: the scene plan is not a JSON object and "
                            "cannot be marked complete"))
    else:
        status = plan.get("status")
        # the completion mark is matched as a plain str on both sides
        if not _exact(reasons, "plan.status", status, str) \
                or not _same_text(status, "complete"):
            reasons.append(_err("plan-not-complete",
                                "plan status=%s; the scene plan must be marked complete before "
                                "any song, and an unmarked plan is not complete" % _show(status)))
        for key in PLAN_MUSIC_KEYS:
            if key in plan:
                reasons.append(_err("plan-carries-song",
                                    "plan declares %r; a song cannot be its own parent plan" % key,
                                    field=key))
    allowed = not reasons
    return {
        "schema_version": SCHEMA_VERSION,
        "allowed": allowed,
        "outcome": "ok" if allowed else "rejected",
        "reason_code": "music-may-proceed" if allowed else reasons[0]["error"],
        "errors": reasons,
        "next_action": (
            "Select/create the intended song against this exact plan revision."
            if allowed
            else "Complete and repair the scene plan; do not dispatch a song writer."
        ),
    }


# --------------------------------------------------------------------------- #
# authoring: foundation-check, then dispatch, then validate
# --------------------------------------------------------------------------- #
def build_scene_plan(foundation, beats, submit, attempt_key=None):
    """Author a scene plan through an injected dispatcher.

    ``submit(request) -> {"scenes": [...], ...}`` is the real model/tool layer
    in production and a deterministic fake in tests. It is NEVER called unless
    the foundation and the causal beats are complete: a missing cast, world,
    research or causal leg stops the writer before its dispatcher is called.

    This entry point never raises: an exception becomes a NAMED refusal, and
    the receipt says honestly whether a dispatch had already happened.
    """
    state = {"dispatched": False}
    try:
        return _build_scene_plan(foundation, beats, submit, attempt_key, state)
    except Exception as exc:                       # noqa: BLE001 - refuse, never crash
        return {
            "schema_version": SCHEMA_VERSION,
            "outcome": "error",
            "reason_code": "fail-closed-exception",
            "errors": _crash("build_scene_plan", exc),
            "dispatched": state["dispatched"],
            "next_action": "Inspect the authoring input/response; no retry with a broad rewrite.",
        }


def _build_scene_plan(foundation, beats, submit, attempt_key, state):
    pre_errors = []
    f_res = validate_foundation(foundation)
    b_res = validate_causal_beats(beats)
    pre_errors.extend(f_res["errors"])
    pre_errors.extend(b_res["errors"])
    if pre_errors:
        return {
            "schema_version": SCHEMA_VERSION,
            "outcome": "rejected",
            "reason_code": pre_errors[0]["error"],
            "errors": pre_errors,
            "dispatched": False,
            "next_action": "Supply the missing foundation/beats; no dispatcher was called.",
        }

    request = {
        "operation": "scene_plan",
        "foundation": {
            k: {"revision": (_object(foundation.get(k)) or {}).get("revision"),
                "digest": (_object(foundation.get(k)) or {}).get("digest")}
            for k in FOUNDATION_KEYS
        },
        "causal_story_beats": {f: beats[f] for f in BEAT_FIELDS},
        "attempt_key": attempt_key,
        "timing_basis": TIMING_BASIS_PROVISIONAL,
    }
    state["dispatched"] = True
    raw = submit(request)
    raw_refusals = []
    if not _exact(raw_refusals, "dispatcher response", raw, dict):
        return {
            "schema_version": SCHEMA_VERSION,
            "outcome": "error",
            "reason_code": "dispatcher-bad-response",
            "errors": [_err("dispatcher-bad-response",
                            "submit returned %s, expected an object" % type(raw).__name__)]
                      + raw_refusals,
            "dispatched": True,
            "next_action": "Inspect the dispatcher response; no retry with a broad rewrite.",
        }

    plan = dict(raw)
    plan.setdefault("schema_version", SCHEMA_VERSION)
    # the validated foundation IS the binding: a dispatcher cannot substitute
    # its own and have that one validated in its place
    plan["foundation"] = foundation
    plan.setdefault("foundation_revisions", {
        k: {"revision": (_object(foundation.get(k)) or {}).get("revision"),
            "digest": (_object(foundation.get(k)) or {}).get("digest")}
        for k in FOUNDATION_KEYS
    })

    result = validate_scene_plan(plan, research=foundation.get("research_bundle"))
    receipt = {
        "attempt_key": attempt_key,
        "dispatched": True,
        "requested": {"operation": request["operation"],
                      "foundation": request["foundation"],
                      "beat_fields": list(BEAT_FIELDS)},
        "scene_count": result.get("scene_count", 0),
    }
    if result["outcome"] != "ok":
        return {
            "schema_version": SCHEMA_VERSION,
            "outcome": "rejected",
            "reason_code": result["reason_code"],
            "errors": result["errors"],
            "dispatched": True,
            "receipt": receipt,
            "candidate": plan,
            "next_action": "Repair the listed scene/line pointers; keep the usable candidate.",
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "outcome": "ok",
        "reason_code": "scene-plan-authored",
        "errors": [],
        "dispatched": True,
        "receipt": receipt,
        "plan": plan,
        "plan_digest": _digest(plan),
        "next_action": "Hold for whole-package review; then select music against this revision.",
    }


def _digest(obj):
    import hashlib
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _load(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _load_optional(path):
    return _load(path) if path else None


def main(argv=None):
    ap = argparse.ArgumentParser(prog="story_planner", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="validate a pre-song scene plan")
    v.add_argument("--plan", required=True)
    v.add_argument("--cast")
    v.add_argument("--world")
    v.add_argument("--research")

    m = sub.add_parser("music-gate", help="may a song be written against this plan?")
    m.add_argument("--plan", required=True)
    m.add_argument("--cast")
    m.add_argument("--world")
    m.add_argument("--research")

    sub.add_parser("selftest", help="run the built-in check")

    args = ap.parse_args(argv)
    if args.cmd == "selftest":
        import test_story_planner_s75t09 as t
        return t.run()

    plan = _load(args.plan)
    cast = _load_optional(args.cast)
    world = _load_optional(args.world)
    research = _load_optional(args.research)

    if args.cmd == "validate":
        out = validate_scene_plan(plan, cast, world, research)
        code = EXIT.get(out["outcome"], EXIT["error"])
    else:
        out = music_gate(plan, cast, world, research)
        code = EXIT["ok"] if out["allowed"] else EXIT["rejected"]
    print(json.dumps(out, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
