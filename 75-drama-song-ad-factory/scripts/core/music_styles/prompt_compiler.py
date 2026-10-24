#!/usr/bin/env python3
"""S75-T41: compile a Suno style field from APPROVED MUSICAL TRAITS ONLY.

Two namespaces, never mixed:

  * ``production_traits``  -- instruments, rhythm, vocal delivery, mood,
    arrangement, tempo, story dynamics, hook guidance, constraints.  The ONLY
    input to a provider prompt.
  * ``client_references``  -- artist names, aliases, reference songs, artist
    explanation sentences.  CLIENT DISPLAY ONLY.  Never read here, never
    serialized, never used as a fallback when a trait record is missing.

A record with no usable trait record fails with a precise missing-recipe
error.  Falling back to a reference artist name is forbidden: that fallback is
the leak this module exists to prevent.

stdlib only, no network, no file writes.
"""
from __future__ import annotations

from collections.abc import Mapping

TOOL_NAME = "music_styles.prompt_compiler"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.suno-prompt-compiler/v1"

#: Trait keys the compiler reads, in rendered order.  A key absent from a
#: record contributes nothing; a key that is present must be text or a list of
#: text.  Anything not listed is ignored -- except the forbidden keys below.
TRAIT_FIELDS = (
    "instruments",
    "avoided_instrumentation",
    "rhythm",
    "tempo",
    "vocal_delivery",
    "mood",
    "arrangement",
    "story_dynamics",
    "hook_guidance",
    "constraints",
)

#: A record that carries reference metadata INSIDE the trait namespace is
#: refused rather than filtered: silently dropping a key hides a catalog defect
#: and leaves the artist name one refactor away from the wire.
FORBIDDEN_TRAIT_KEYS = frozenset({
    "client_references",
    "artists",
    "artist",
    "aliases",
    "alias",
    "reference_songs",
    "reference_song",
    "recognition",
    "recognition_references",
    "display_metadata",
})

#: Keys that are structurally display-only.  Named here so a caller can assert
#: a compiled record never carries them onward.
DISPLAY_ONLY_KEYS = frozenset({"client_references", "display_metadata",
                               "recognition", "recognition_references"})


class PromptCompileError(ValueError):
    """A recipe that cannot be compiled into a provider style field."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def _as_text(value, field, style_id):
    """One trait value as text; lists join with a comma."""
    if isinstance(value, str):
        parts = [value]
    elif isinstance(value, (list, tuple)):
        parts = []
        for item in value:
            if not isinstance(item, str):
                raise PromptCompileError(
                    "BAD_TRAIT",
                    "%r: %s must be text or a list of text, got %r"
                    % (style_id, field, type(item).__name__))
            parts.append(item)
    else:
        raise PromptCompileError(
            "BAD_TRAIT",
            "%r: %s must be text or a list of text, got %r"
            % (style_id, field, type(value).__name__))
    cleaned = []
    for part in parts:
        text = " ".join(part.split())
        if text:
            cleaned.append(text)
    return ", ".join(cleaned)


def production_traits(recipe):
    """The trait record of one catalog entry; raises when it cannot compose.

    ``recipe`` may be the catalog record itself or a mapping with a single
    style record under ``recipe`` / ``record``.  A missing or empty trait
    record is a MISSING_RECIPE error -- never an artist-name fallback.
    """
    if not isinstance(recipe, dict):
        raise PromptCompileError(
            "BAD_RECIPE", "a recipe must be an object, got %r"
            % (type(recipe).__name__,))
    style_id = recipe.get("style_id") or recipe.get("id") or "<unnamed>"
    traits = recipe.get("production_traits")
    if traits is None and isinstance(recipe.get("record"), dict):
        return production_traits(recipe["record"])
    if not isinstance(traits, dict) or not traits:
        raise PromptCompileError(
            "MISSING_PRODUCTION_TRAITS",
            "%r: no production_traits record; an adapter without approved "
            "traits fails here and never falls back to a reference artist"
            % (style_id,))
    forbidden = sorted(set(traits) & FORBIDDEN_TRAIT_KEYS)
    if forbidden:
        raise PromptCompileError(
            "REFERENCE_IN_TRAITS",
            "%r: production_traits carries display-only key(s) %s; reference "
            "metadata belongs in client_references and must not be compiled"
            % (style_id, ", ".join(forbidden)))
    return traits


def compile_style_field(recipe):
    """The provider style field for one recipe, built from traits only.

    Deterministic: same record in, same text out.  ``client_references`` and
    every other non-trait key are structurally unreadable here, so display
    metadata cannot reach the field even when the record carries it.
    """
    traits = production_traits(recipe)
    style_id = recipe.get("style_id") or recipe.get("id") or "<unnamed>"
    parts = []
    seen = set()
    for field in TRAIT_FIELDS:
        if field not in traits:
            continue
        text = _as_text(traits[field], field, style_id)
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            parts.append(text)
    if not parts:
        raise PromptCompileError(
            "MISSING_PRODUCTION_TRAITS",
            "%r: production_traits carries none of the approved trait fields "
            "%s" % (style_id, ", ".join(TRAIT_FIELDS)))
    return ", ".join(parts)


def compile_from_catalog(catalog, style_id):
    """Compile one style out of a catalog mapping / record list."""
    for record in catalog_records(catalog):
        if (record.get("style_id") or record.get("id")) == style_id:
            return compile_style_field(record)
    raise PromptCompileError(
        "UNKNOWN_STYLE", "no catalog record for style %r" % (style_id,))


def catalog_records(catalog):
    """Catalog as an iterable of records: a list, or a mapping of id->record."""
    if isinstance(catalog, dict):
        styles = catalog.get("styles")
        if isinstance(styles, dict):
            for key, value in styles.items():
                record = dict(value)
                record.setdefault("style_id", key)
                yield record
            return
        if isinstance(styles, list):
            for value in styles:
                yield value
            return
        # a plain {style_id: record} mapping
        for key, value in catalog.items():
            if isinstance(value, dict):
                record = dict(value)
                record.setdefault("style_id", key)
                yield record
        return
    if isinstance(catalog, (list, tuple)):
        for value in catalog:
            if isinstance(value, dict):
                yield value
        return
    raise PromptCompileError(
        "BAD_CATALOG", "a catalog must be a mapping or a list, got %r"
        % (type(catalog).__name__,))


class DisplayOnly(Mapping):
    """The client-facing reference block: readable for a screen, never a wire.

    A Mapping, not a dict, so ``json.dumps`` refuses it by construction: display
    metadata cannot serialise into a provider payload even when a caller hands
    it along by mistake.  ``suno_prompt_guard`` refuses it at the boundary too.
    """

    def __init__(self, data):
        self._data = dict(data)

    def __getitem__(self, key):
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def __eq__(self, other):
        if isinstance(other, Mapping):
            return dict(self._data) == dict(other)
        return NotImplemented

    def __repr__(self):
        return "DisplayOnly(%r)" % (self._data,)


def display_metadata(recipe):
    """The client-facing reference block, for UI rendering only.

    Returned to a screen; never consumed by a compiler or a payload builder,
    and unserialisable into a payload by type.
    """
    if not isinstance(recipe, dict):
        return DisplayOnly({})
    refs = recipe.get("client_references")
    return DisplayOnly(refs if isinstance(refs, Mapping) else {})
