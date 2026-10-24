"""S75-T22: executable recipes for the four orchestral / theater / gospel
styles (Cinematic Orchestral Song, Musical Theater, Contemporary Gospel,
Urban Gospel). stdlib only, no network, no provider call, no paid generation.

Owner scope (MUSIC-AND-VIDEO-UX.md sections 2, 3, 4.12-4.15, S75-A22):
each style is ONE versioned structured record whose ``production_traits``
compile into the real style field; display-only artist/reference metadata
(``client_references``, ``aliases``) never reaches a provider field.

Seams, deliberately small:
  * ``as_catalog_entries()`` renders the four records in the existing
    ``music_styles.STYLES`` shape, so the catalog owner's registry adopts
    them with one ``STYLES.update(...)`` -- no second choice catalog here.
  * ``compile_style_field()`` is the whole provider compiler and takes NO
    client argument: a client fact cannot be invented or serialized,
    because nothing but ``production_traits["provider_clauses"]`` is read.
  * delivery map, negative-tag contradiction gate and the F13 dry-style ban
    stay where they already live (``music_styles``, ``audio_c3/no_echo``);
    this module never re-implements them.

ponytail: the accepted F13 dry-style fix bans the words strings, gospel,
choir, harmonies and cinematic in song style text. Provider clauses here use
"violin and viola section", "faith-centered", "backing vocal ensemble" and
"film-style" instead. Upgrade path: replace the clause text when F13 is
revisited; no gate is bypassed.

Run: python3 core/music_styles/test_recipes_s75_t22.py
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
import unicodedata

try:                                    # imported as music_styles.recipes_s75_t22
    from . import music_styles as _MS
except ImportError:                     # imported bare from core/ on sys.path
    import music_styles as _MS

TOOL_NAME = "music_styles.recipes_s75_t22"
TOOL_VERSION = "0.1.0"
SCHEMA_VERSION = "blackceo.music-styles/s75-recipes/v1"
RECIPE_REVISION = "s75-t22.1"

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _canonical_durations():
    """The one duration table (suno_recipe/duration_registry.py), by path."""
    leaf = os.path.join(_CORE, "suno_recipe", "duration_registry.py")
    spec = importlib.util.spec_from_file_location(
        "_s75t22_duration_registry", leaf)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return tuple(mod.CANONICAL_DURATION_S)


#: Shared rules every recipe inherits. The durations are the canonical six,
#: never a new copy; the opener and the visible-lip-sync band are the owner's
#: numbers unchanged. Spoken duration and visible lip-sync stay separate
#: measurements -- this module measures neither, it only carries the bounds.
SHARED_RULES = {
    "durations_s": _canonical_durations(),
    "spoken_opener_seconds": 12,
    "visible_lip_sync_target": (0.25, 0.30),
    "visible_lip_sync_cap": 0.35,
    "language_locked_to_client": True,
    "vocal_gender_locked_to_client": True,
    "accent_locked_to_client": True,
    "explicitness_locked_to_client": True,
    "invents_client_facts": False,
}


def _traits(identity, instrumentation, avoided, tempo, meter, vocal, energy,
            hook, delivery, story, negative, clauses):
    """One ``production_traits`` block; only ``clauses`` reaches a prompt."""
    return {
        "musical_identity": identity,
        "instrumentation": tuple(instrumentation),
        "avoided_instrumentation": tuple(avoided),
        "tempo_range_bpm": tuple(tempo),
        "meter": meter,
        "vocal_delivery": vocal,
        "energy_map": tuple(energy),
        "hook_guidance": hook,
        "delivery_constraints": tuple(delivery),
        "story_dynamics": story,
        "negative_constraints": tuple(negative),
        "provider_clauses": tuple(clauses),
    }


RECIPES = {
    "cinematic-orchestral-song": {
        "style_id": "cinematic-orchestral-song",
        "label": "Cinematic Orchestral Song",
        "description": (
            "a dramatic song with sweeping strings and a powerful film-style "
            "chorus. Keep the singing and spoken words clear and easy to hear, "
            "even when the music gets big and powerful."),
        "recipe_revision": RECIPE_REVISION,
        "deliveries": ("spoken", "sung"),
        "notes": "A song with a real sung lead, not an instrumental score.",
        "client_references": (
            "Adele's “Skyfall” / Celine Dion's “My Heart Will "
            "Go On” as arrangement and emotional-scale references.",),
        "aliases": ("Adele", "Skyfall", "Celine Dion",
                    "My Heart Will Go On"),
        "production_traits": _traits(
            identity="orchestral film-style song with a full sung lead",
            instrumentation=("expressive lead vocal", "piano",
                             "low cello foundation", "violin and viola "
                             "section", "warm brass",
                             "controlled film-score percussion"),
            avoided=("instrumental score only", "sound-effect reel",
                     "copied reference motif"),
            tempo=(60, 88),
            meter="4/4, or a justified 6/8",
            vocal="clear-diction lead vocal carrying original full lyrics",
            energy=("sparse piano and low cello under the spoken opening",
                    "viola and violin register tighten under pressure",
                    "brief reduction at the emotional turn",
                    "full earned sung refrain after the consequential choice",
                    "final refrain resolves the same proposition and one CTA"),
            hook=("one sung refrain that expresses the earned change, not a "
                  "second slogan"),
            delivery=("voice forward and intelligible at every dynamic",
                      "reserve large percussion and brass for consequential "
                      "moments"),
            story=("dramatic scale never replaces specific story detail; "
                   "orchestral tails and held notes get their own seconds"),
            negative=("no instrumental-only cut", "no copied melody or "
                      "arrangement sequence"),
            clauses=(
                "orchestral film-style song",
                "60-88 bpm",
                "expressive lead vocal with clear diction",
                "piano and low cello foundation",
                "sweeping violin and viola section",
                "warm brass entering at the turn",
                "controlled film-score percussion",
                "wide dynamic swells",
                "powerful earned sung refrain",
                "no distortion",
            ),
        ),
        "narrow_tests": ("T22-ORCH-VOCAL", "T22-ORCH-DISTINCT",
                         "T22-NO-ARTIST", "T22-F13-DRY"),
    },
    "musical-theater": {
        "style_id": "musical-theater",
        "label": "Musical Theater",
        "description": (
            "character-driven singing and dialogue that build into a dramatic "
            "stage-style payoff."),
        "recipe_revision": RECIPE_REVISION,
        "deliveries": ("spoken", "sung"),
        "notes": ("Dialogue and reprises only when the approved script already "
                  "elected them; no automatic multi-voice route."),
        "client_references": (
            "Idina Menzel / Cynthia Erivo for character intention and dramatic "
            "vocal storytelling.",),
        "aliases": ("Idina Menzel", "Cynthia Erivo"),
        "production_traits": _traits(
            identity="piano-led theatrical stage song with a character lead",
            instrumentation=("character lead vocal", "piano-led orchestra",
                             "woodwind answers", "selective brass",
                             "responsive rhythm section"),
            avoided=("copied celebrity belt", "unapproved ensemble route",
                     "automatic dialogue insertion"),
            tempo=(72, 132),
            meter="4/4 with planned rubato or scene-linked tempo changes",
            vocal=("character-specific, articulate, intentional lead vocal "
                   "that sings when the want outgrows speech"),
            energy=("spoken consequence opens over piano",
                    "want-driven verse answers the obstacle",
                    "short motif turns at the emotional choice",
                    "orchestra pivot then earned stage-style payoff"),
            hook=("one motif whose meaning changes at the turn; a reprise only "
                  "when the approved script elected one"),
            delivery=("diction outranks showy runs",
                      "spoken interjections, sung phrases and held dramatic "
                      "notes each budget their own seconds",
                      "dialogue and reprises only if already approved"),
            story=("characters sing because immediate pressure makes the "
                   "moment larger than speech; stage directions are never "
                   "sung as lyric"),
            negative=("no copied belt or celebrity voice", "no invented "
                      "ensemble", "no automatic reprise"),
            clauses=(
                "theatrical stage song",
                "piano-led orchestra",
                "woodwind answers",
                "selective brass",
                "responsive rhythm section",
                "72-132 bpm with planned rubato",
                "character-driven articulate lead vocal",
                "spoken dialogue into a sung payoff",
                "big earned final refrain",
                "clear diction",
                "no distortion",
            ),
        ),
        "narrow_tests": ("T22-THEATER-CAST", "T22-THEATER-OPTIONAL-DIALOGUE",
                         "T22-NO-ARTIST", "T22-F13-DRY"),
    },
    "contemporary-gospel": {
        "style_id": "contemporary-gospel",
        "label": "Contemporary Gospel",
        "description": (
            "faith-centered singing with piano, organ, and a powerful choir "
            "that builds from testimony to an uplifting chorus."),
        "recipe_revision": RECIPE_REVISION,
        "deliveries": ("spoken", "sung"),
        "notes": ("Faith-centered arrangement and lyric intention; never a "
                  "real client's faith, church or testimony."),
        "client_references": (
            "Kirk Franklin's contemporary gospel work; overlaps Urban Gospel "
            "without merging the two choices.",),
        "aliases": ("Kirk Franklin",),
        "production_traits": _traits(
            identity=("faith-centered sung arrangement with piano and organ "
                      "leadership"),
            instrumentation=("lead vocal", "warm piano",
                             "hammond organ foundation", "live bass",
                             "live drums", "expressive backing vocal ensemble"),
            avoided=("generic inspirational pop label",
                     "unapproved sermon or conversion event",
                     "invented church affiliation"),
            tempo=(68, 100),
            meter="deliberate 4/4 or 6/8 sway",
            vocal=("clear-conviction lead vocal with restrained, purposeful "
                   "runs"),
            energy=("restrained piano and organ under the spoken consequence",
                    "lead need and chosen action build the testimony",
                    "backing vocal answers deepen the meaning",
                    "earned uplifting chorus of faith, hope or redemption "
                    "already grounded in the approved story"),
            hook=("one sung refrain stating the faith-centered change; a "
                  "larger final refrain only if duration and story permit"),
            delivery=("backing vocal answers support the lead, never bury the "
                      "words",
                      "held notes, replies and breaths get separate seconds"),
            story=("faith content comes from the approved fictional script; "
                   "no fixed church-service structure is imposed"),
            negative=("no invented client faith fact", "no extra character"),
            clauses=(
                "faith-centered sung arrangement",
                "warm piano and hammond organ foundation",
                "live bass and live drums",
                "expressive backing vocal ensemble answering the lead",
                "swaying 68-100 bpm in 4/4 or 6/8",
                "testimony building from a restrained verse to an uplifting "
                "sung chorus",
                "rich chord movement",
                "clear diction",
                "no distortion",
            ),
        ),
        "narrow_tests": ("T22-GOSPEL-FAITH", "T22-GOSPEL-SPLIT",
                         "T22-NO-CLIENT-FACTS", "T22-F13-DRY"),
    },
    "urban-gospel": {
        "style_id": "urban-gospel",
        "label": "Urban Gospel",
        "description": (
            "faith-centered singing with R&B and hip-hop grooves, choir "
            "responses, and a memorable gospel hook."),
        "recipe_revision": RECIPE_REVISION,
        "deliveries": ("spoken", "rap", "sung"),
        "notes": ("Rhythmic verses answered by a sung faith hook; the groove "
                  "never removes the faith-centered intention."),
        "client_references": (
            "Kirk Franklin's gospel-centered blend of R&B, hip-hop and choir "
            "response.",),
        "aliases": ("Kirk Franklin",),
        "production_traits": _traits(
            identity=("faith-centered sung arrangement over an r&b and "
                      "hip-hop groove"),
            instrumentation=("lead vocal", "deep controlled bass",
                             "rhodes and piano", "selective organ texture",
                             "defined r&b/hip-hop drum pocket",
                             "responsive backing vocal replies"),
            avoided=("ordinary secular r&b copy", "automatic slang",
                     "invented church affiliation"),
            tempo=(78, 110),
            meter="4/4 with an optional documented half-time feel",
            vocal=("lead moves between rhythmic rap passages and a sung faith "
                   "hook only as the approved delivery map allows"),
            energy=("sparse groove leaves the spoken consequence audible",
                    "rhythmic verses trace pressure and choice",
                    "brief reduction at the costly admission",
                    "backing vocal response and sung hook lift after the turn"),
            hook=("one unmistakably vocal faith hook after the choice is made"),
            delivery=("gaps left for vocal replies; lead, rap and replies never "
                      "stack over critical words",
                      "rap passages counted as spoken-style delivery"),
            story=("faith content and any testimony come from the approved "
                   "fictional script, never from a real client"),
            negative=("no invented client belief or testimony", "no stereotype"),
            clauses=(
                "faith-centered sung arrangement over an r&b and hip-hop groove",
                "78-110 bpm",
                "deep controlled bass",
                "rhodes and piano",
                "selective organ texture",
                "responsive backing vocal replies",
                "rhythmic rap verses into a sung faith hook",
                "clear diction",
                "no distortion",
            ),
        ),
        "narrow_tests": ("T22-GOSPEL-SPLIT", "T22-URBAN-RAP-MAP",
                         "T22-NO-CLIENT-FACTS", "T22-F13-DRY"),
    },
}

STYLE_IDS = tuple(RECIPES)

_NORMALIZE_KEEP = re.compile(r"[^0-9a-z ]+")


def _norm(text):
    """Casefold, strip accents and punctuation, collapse spaces."""
    folded = unicodedata.normalize("NFKD", str(text)).casefold()
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return " ".join(_NORMALIZE_KEEP.sub(" ", folded).split())


def _recipe_key(style):
    """An id or label (or a card option dict) -> a style id."""
    if isinstance(style, dict):
        style = style.get("value", style.get("style_id"))
    if not isinstance(style, str) or not style.strip():
        raise _MS.MusicStyleError("BAD_STYLE",
                                  "style must be a non-empty string, got %r"
                                  % (style,))
    key = style.strip().lower()
    if key in RECIPES:
        return key
    for sid, rec in RECIPES.items():
        if key == rec["label"].lower():
            return sid
    raise _MS.MusicStyleError(
        "UNKNOWN_STYLE", "not one of the four S75-T22 recipes: %r" % style)


def style_ids():
    """The four stable ids, in spec order."""
    return STYLE_IDS


def recipe(style_id):
    """A shallow copy of one recipe record; raises on an unknown id."""
    return dict(RECIPES[_recipe_key(style_id)])


def describe(style_id):
    """Client-facing menu record: exact label, description, references only."""
    rec = RECIPES[_recipe_key(style_id)]
    return {
        "style_id": rec["style_id"],
        "label": rec["label"],
        "description": rec["description"],
        "client_references": rec["client_references"],
        "recipe_revision": rec["recipe_revision"],
    }


def compile_style_field(style_id):
    """The provider style text: only ``production_traits.provider_clauses``.

    Takes no client argument by design -- a client fact, an artist name and
    this record's human prose have no path into the string. The shared
    delivery map is appended later by ``music_styles.style_prompt`` so the
    one choke point stays the one choke point.
    """
    rec = RECIPES[_recipe_key(style_id)]
    clauses = rec["production_traits"]["provider_clauses"]
    if not clauses:
        raise _MS.MusicStyleError(
            "MISSING_RECIPE", "%s carries no provider clauses" % style_id)
    return ", ".join(clauses)


def client_reference_hits(text, style_id=None):
    """Reference names/aliases found in outbound text (empty = clean).

    Unicode, case and punctuation aware. Only the four recipes' own aliases
    are known here; the full eighteen-style guard is S75-T41's task.
    """
    if not isinstance(text, str) or not text.strip():
        return []
    haystack = " %s " % _norm(text)
    sids = [_recipe_key(style_id)] if style_id else list(STYLE_IDS)
    hits = []
    for sid in sids:
        for alias in RECIPES[sid]["aliases"]:
            needle = " %s " % _norm(alias)
            if needle in haystack and alias not in hits:
                hits.append(alias)
    return hits


def assert_no_client_reference(text, style_id=None):
    """Raise when an artist name or alias reached outbound text."""
    hits = client_reference_hits(text, style_id)
    if hits:
        raise _MS.MusicStyleError(
            "CLIENT_REFERENCE_IN_PAYLOAD",
            "outbound text names client-only reference(s) %s" % ", ".join(hits))
    return text


def as_catalog_entries():
    """The four records in ``music_styles.STYLES`` shape.

    The catalog owner merges them once (``STYLES.update(...)``); every
    existing consumer -- style_prompt, spoken_target, the card -- then works
    unchanged. ``suno_style_prompt`` is the compiled clause text without the
    delivery map, exactly like the three original records.
    """
    share_rule = _MS.STYLES["soul-ballad"]["share_rule"]
    out = {}
    for sid, rec in RECIPES.items():
        out[sid] = {
            "style_id": sid,
            "label": rec["label"],
            "sound": rec["production_traits"]["musical_identity"],
            "share_rule": share_rule,
            "deliveries": rec["deliveries"],
            "notes": rec["notes"],
            "suno_style_prompt": compile_style_field(sid),
        }
    return out


__all__ = [
    "RECIPES",
    "RECIPE_REVISION",
    "SCHEMA_VERSION",
    "SHARED_RULES",
    "STYLE_IDS",
    "TOOL_NAME",
    "TOOL_VERSION",
    "as_catalog_entries",
    "assert_no_client_reference",
    "client_reference_hits",
    "compile_style_field",
    "describe",
    "recipe",
    "style_ids",
]
