#!/usr/bin/env python3
"""S75-T41: compile outgoing Suno fields from APPROVED MUSICAL TRAITS ONLY.

Two namespaces, never mixed:

  ``production_traits``  the T18 catalog's approved musical direction
                         (identity, instruments, tempo, meter, vocal delivery,
                         energy, hook, delivery constraints, avoid lists).
                         The ONLY input to any outgoing provider field.
  ``client_references``  the recognition artists. CLIENT DISPLAY ONLY. Read by
                         ``client_display()`` and by nothing that builds a
                         provider field.

The compiler never reads ``client_references`` and never falls back to a
reference when a trait is missing: a recipe without usable traits is refused
(``MISSING_PRODUCTION_TRAITS``). A display key found inside the trait
namespace is refused too, so an artist name cannot ride out one refactor
later.

Approved creative bytes -- ``lyrics`` and ``character_names`` -- are passed
through untouched. This module never rewrites them.

stdlib only, no network, no provider calls, no file writes.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE = os.path.dirname(_HERE)
#: Only CORE joins sys.path. Adding _HERE would shadow the ``music_styles``
#: package with the ``music_styles.py`` leaf for every later importer in the
#: same process (e.g. suno_recipe -> words_fit).
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

try:                                    # imported as music_styles.suno_prompt_compiler
    from . import catalog as _catalog
except ImportError:                     # script/top-level import: HERE is sys.path[0]
    import catalog as _catalog

TOOL_NAME = "suno_prompt_compiler"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.suno-prompt-compiler/v1"

#: The real T18 trait keys, in rendered order. A key absent from a record
#: contributes nothing; anything outside the approved keys is ignored.
#: The order is a CAP PRIORITY, not cosmetic: every field is rendered whole
#: while it fits the style-field cap, and a whole field that cannot fit is
#: omitted and named in ``_omitted_traits`` -- no trait is ever truncated.
TRAIT_ORDER = (
    "musical_identity",
    "instrumentation",
    "tempo_bpm",
    "vocal_delivery",
    "energy_map",
    "hook_guidance",
    "meter",
    "delivery_constraints",
)

#: suno_recipe.SUNO_STYLE_FIELD_MAX; the cap prompt_limits measures.
STYLE_FIELD_MAX = 1000

#: Trait keys that are negative direction, not positive style text.
NEGATIVE_TRAIT_FIELDS = ("avoid_instrumentation", "negative_constraints")

#: Keys that are display metadata by construction. Finding one inside the
#: trait namespace is a catalog defect and is refused, never filtered.
DISPLAY_ONLY_KEYS = frozenset({
    "client_references",
    "artist_references",
    "reference_artists",
    "artists",
    "artist",
    "aliases",
    "alias",
    "display_metadata",
    "recognition",
})

#: Trevor's dry rule; production character, carried in the negative field.
DRY_NEGATIVES = ("choir", "reverb", "echo")

#: The mandated band sentence (suno_recipe.check_style_text reads the literal
#: "band keeps playing"); kept short so the trait budget is not spent here.
BAND_KEEPS_PLAYING = "full band keeps playing under spoken lines"

#: The G1 delivery-map clauses are owned by music_styles; read from the leaf
#: catalog already loaded, so this module keeps no second copy of the words.
DELIVERY_MAP_CLAUSES = _catalog._MS.DELIVERY_MAP_CLAUSES


class CompileError(ValueError):
    """A recipe that cannot produce a clean outgoing field."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def _record(recipe):
    """Resolve a style id, a catalog record or a bare {'style_id': ...}."""
    if isinstance(recipe, str):
        try:
            return _catalog.style(recipe)
        except _catalog.CatalogError as exc:
            raise CompileError("UNKNOWN_STYLE", str(exc)) from exc
    if not isinstance(recipe, dict):
        raise CompileError("BAD_RECIPE",
                           "recipe must be a style id or a record, got %r"
                           % (type(recipe).__name__,))
    if "production_traits" in recipe:
        return recipe
    sid = recipe.get("style_id") or recipe.get("id")
    if isinstance(sid, str) and sid.strip():
        return _catalog.style(sid)
    raise CompileError("BAD_RECIPE",
                       "record carries no production_traits and no style_id")


def _text(value, field, style_id):
    """One trait value as text; a list joins with a comma."""
    if isinstance(value, str):
        parts = [value]
    elif isinstance(value, (list, tuple)):
        parts = []
        for item in value:
            if not isinstance(item, str):
                raise CompileError(
                    "BAD_TRAIT",
                    "%r: %s must be text or a list of text, got %r"
                    % (style_id, field, type(item).__name__))
            parts.append(item)
    else:
        raise CompileError("BAD_TRAIT",
                           "%r: %s must be text or a list of text, got %r"
                           % (style_id, field, type(value).__name__))
    cleaned = [" ".join(part.split()) for part in parts if part.strip()]
    return ", ".join(cleaned)


def _tempo(value, style_id):
    """The approved (low, high) bpm pair as one provider-safe phrase."""
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or not all(isinstance(n, int) for n in value)
            or not 0 < value[0] < value[1] <= 300):
        raise CompileError("BAD_TRAIT",
                           "%r: tempo_bpm must be a positive ascending pair"
                           % (style_id,))
    return "%d-%d bpm" % (value[0], value[1])


def production_traits(recipe):
    """The trait record of one recipe, validated; display keys are refused."""
    rec = _record(recipe)
    style_id = rec.get("style_id") or "<unnamed>"
    traits = rec.get("production_traits")
    if not isinstance(traits, dict) or not traits:
        raise CompileError(
            "MISSING_PRODUCTION_TRAITS",
            "%r: no production_traits record; a recipe without approved "
            "traits fails here and never falls back to a reference artist"
            % (style_id,))
    leaked = sorted(set(traits) & DISPLAY_ONLY_KEYS)
    if leaked:
        raise CompileError(
            "DISPLAY_KEY_IN_TRAITS",
            "%r carries display-only %s inside production_traits; client "
            "references are a separate namespace" % (style_id, leaked))
    return rec, traits, style_id


def _deliveries(recipe, choices):
    rec = _record(recipe)
    allowed = tuple(rec.get("deliveries") or ())
    chosen = (choices or {}).get("deliveries")
    if chosen is None:
        return allowed
    if isinstance(chosen, str):
        chosen = (chosen,)
    deliveries = tuple(str(d).strip().lower() for d in chosen)
    bad = [d for d in deliveries if d not in ("spoken", "rap", "sung")]
    if bad:
        raise CompileError("BAD_CHOICE",
                           "unknown delivery %r; known: spoken, rap, sung"
                           % (bad,))
    if allowed:
        outside = [d for d in deliveries if d not in allowed]
        if outside:
            raise CompileError(
                "BAD_CHOICE",
                "delivery %r is not offered by this style %r"
                % (outside, allowed))
    return deliveries


def delivery_map(deliveries):
    """The G1 sentence naming which lines are spoken, rapped and sung."""
    chosen = set(deliveries or ())
    parts = [clause for name, clause in DELIVERY_MAP_CLAUSES if name in chosen]
    if not parts:
        raise CompileError("NO_DELIVERY",
                           "no delivery selected ([spoken], [rap], [sung])")
    return "The lead %s." % ", ".join(parts)


def _style_part(field, traits, style_id):
    if field not in traits:
        return None
    if field == "tempo_bpm":
        return _tempo(traits[field], style_id)
    return _text(traits[field], field, style_id) or None


def compile_style(recipe, choices=None):
    """The outgoing Suno style field: approved musical traits only.

    Each approved trait field is rendered whole. A whole field that would
    push the style past ``STYLE_FIELD_MAX`` is OMITTED and named in the
    returned omissions list -- never cut mid-clause. The approved delivery
    map and the mandated band sentence are reserved first, because they are
    required on every rendered style.
    """
    rec, traits, style_id = production_traits(recipe)
    tail = "%s. %s" % (BAND_KEEPS_PLAYING,
                       delivery_map(_deliveries(rec, choices)))
    parts, omitted = [], []
    for field in TRAIT_ORDER:
        part = _style_part(field, traits, style_id)
        if part is None:
            continue
        candidate = ", ".join(parts + [part]).rstrip(".,")
        if len("%s. %s" % (candidate, tail)) > STYLE_FIELD_MAX:
            omitted.append(field)
            continue
        parts.append(part)
    if not parts:
        raise CompileError(
            "STYLE_OVER_CAP",
            "%r: no approved trait fits the %d-char style field"
            % (style_id, STYLE_FIELD_MAX))
    text = "%s. %s" % (", ".join(parts).rstrip(".,"), tail)
    return " ".join(text.split()), tuple(omitted)


def compile_negatives(recipe):
    """The outgoing negative field: approved avoid/negative traits + dry rule."""
    _rec, traits, style_id = production_traits(recipe)
    tags = []
    for field in NEGATIVE_TRAIT_FIELDS:
        if field not in traits:
            continue
        for tag in _text(traits[field], field, style_id).split(", "):
            tag = tag.strip()
            if tag:
                tags.append(tag)
    tags.extend(DRY_NEGATIVES)
    seen, ordered = set(), []
    for tag in tags:
        key = tag.casefold()
        if key not in seen:
            seen.add(key)
            ordered.append(tag)
    if not ordered:
        raise CompileError("EMPTY_NEGATIVES",
                           "%r produces no negative direction" % (style_id,))
    return ", ".join(ordered)


def compile_outgoing(recipe, choices=None):
    """Every outgoing field for one approved recipe + client-selected choices.

    ``choices``: lyrics, title, duration_s, deliveries, vocal_gender,
    character_names. Lyrics and character names are approved creative bytes
    and are returned untouched (digest included so a caller can prove it).
    """
    choices = dict(choices or {})
    rec = _record(recipe)
    deliveries = _deliveries(rec, choices)
    style, omitted = compile_style(rec, {"deliveries": deliveries})
    payload = {
        "style": style,
        "negative_tags": compile_negatives(rec),
        "title": choices.get("title") or "",
        "lyrics": choices.get("lyrics") or "",
        "duration": choices.get("duration_s", choices.get("duration")),
        "character_names": tuple(choices.get("character_names") or ()),
        "_omitted_traits": omitted,
    }
    if choices.get("vocal_gender") is not None:
        payload["vocal_gender"] = choices["vocal_gender"]
    if payload["duration"] is not None:
        offered = tuple(rec.get("durations_s") or ())
        if offered and payload["duration"] not in offered:
            raise CompileError("BAD_CHOICE",
                               "duration %r is not one of the offered lengths "
                               "%r" % (payload["duration"], offered))
    if not isinstance(payload["lyrics"], str):
        raise CompileError("BAD_CHOICE", "lyrics must be a string")
    if not all(isinstance(n, str) for n in payload["character_names"]):
        raise CompileError("BAD_CHOICE", "character_names must be strings")
    if not payload["style"].strip():
        raise CompileError("EMPTY_STYLE", "%r compiled an empty style" % (rec,))
    if len(payload["style"]) > STYLE_FIELD_MAX:
        raise CompileError("STYLE_OVER_CAP",
                           "style is %d chars, cap %d"
                           % (len(payload["style"]), STYLE_FIELD_MAX))
    payload["_lyrics_sha256"] = hashlib.sha256(
        payload["lyrics"].encode("utf-8")).hexdigest()
    payload["_character_names_sha256"] = hashlib.sha256(
        repr(tuple(payload["character_names"])).encode("utf-8")).hexdigest()
    return payload


def client_display(recipe):
    """The separate CLIENT DISPLAY path: recognition references live here.

    Returns no provider field at all, so a display surface cannot accidentally
    forward this record as generation metadata.
    """
    rec = _record(recipe)
    return {
        "style_id": rec.get("style_id"),
        "label": rec.get("label"),
        "description": rec.get("description"),
        "client_references": tuple(rec.get("client_references") or ()),
        "display_only": True,
    }


def outgoing_field_names(payload):
    """Every field name a provider would receive, in stable order."""
    return tuple(sorted(str(k) for k in payload
                        if not str(k).startswith("_")))


if __name__ == "__main__":              # tiny manual smoke, no framework
    out = compile_outgoing("soul-ballad",
                           {"lyrics": "[Spoken] hello\n[Sung] hello",
                            "title": "Hello", "duration_s": 60})
    print(out["style"])
    print("NEGATIVES:", out["negative_tags"])
    print("DISPLAY:", client_display("soul-ballad")["client_references"])
