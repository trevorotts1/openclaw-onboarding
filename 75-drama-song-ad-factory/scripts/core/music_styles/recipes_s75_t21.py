"""S75-T21: executable recipes for Pop Rock, Reggaeton and Country Rap.

This module owns the three recipe records WF06 still owed. It does NOT write
the menu: S75-T18 owns ``catalog.py``, and the eighteen-style catalog already
carries ``pop-rock``, ``reggaeton`` and ``country-rap``. ``menu_record()``
renders this owner's record in the shape that catalog reads, for the catalog
owner to splice; nothing here registers, edits or reorders a style.

What this owner does own is the part a menu cannot fake: each record compiles,
through the SAME composer the live styles use
(``suno_recipe.compose_style_block``), into a provider-ready style field with
the one clean ending, the FU-HOOK-PLACEMENT order clause, the G1 delivery map,
the band wording and the 1000-character cap composed and checked in one place.

Separation a name list cannot fake either:
  * ``client_references`` are DISPLAY-ONLY recognition notes. They are never
    serialised by ``compile_style`` or ``negative_tags``; ``client_reference_
    leaks`` proves that on real output.
  * ``production_traits.word_fit`` is read and asserted against the record that
    declares it (``word_fit_findings``), so the field is verified data, never
    dead prose: guidance naming another style's frame, a banned element, a
    delivery this record does not declare, or a cut-the-CTA order is a finding
    and ``load_recipe`` refuses the record.

Registry shape: T19 keeps ``recipes.py`` + ``recipes/*.json`` and T22 keeps
``recipes_s75_t22.py``; each is a complete registry with one schema version.
This module follows that precedent for its three styles -- one
``SCHEMA_VERSION``, one ``RECIPE_REVISION`` per record, every record the same
shape. It deliberately does not re-open T19's registry: T19's own suite pins
``recipes.recipe_ids()`` to exactly its five ids and pins ``reggaeton`` as an
UNKNOWN_RECIPE refusal there, so adding these three to that module would
either break an accepted unit's test or leave one file with two scopes.

stdlib only, no network, no provider call, no paid generation.
"""
from __future__ import annotations

import copy
import re

try:                                    # imported as music_styles.recipes_s75_t21
    from . import music_styles as _MS
except ImportError:                     # imported bare from core/ on sys.path
    import music_styles as _MS

try:                                    # the ONE composer, bound at import time
    import suno_recipe.suno_recipe as _SR
except ImportError:                     # loaded as a plain module (core/ on sys.path)
    import suno_recipe as _SR

TOOL_NAME = "music_styles.recipes_s75_t21"
TOOL_VERSION = "0.1.0"

#: The one schema version this registry's three records speak.
SCHEMA_VERSION = "blackceo.music-styles/s75-t21-recipes/v1"
#: The one content revision every record declares (bumped together).
RECIPE_REVISION = "s75-t21/1"

#: Stable ids in menu order (S75-T21 owns exactly these three).
RECIPE_ORDER = ("pop-rock", "reggaeton", "country-rap")

#: The one duration table; the six numbers are read from that leaf, never
#: copied here (see ``test_recipes_s75_t21.py``).
DURATION_POLICY = "suno_recipe.duration_registry.CANONICAL_DURATION_S"

#: Inherited owner rules (SPEC "choices that must survive unchanged").
OPENING_SPOKEN_SECONDS = 12
VISIBLE_LIP_SYNC_TARGET_PCT = (25, 30)
VISIBLE_LIP_SYNC_CAP_PCT = 35

#: Production and structure nouns a word-fit line may name; each named group
#: must be backed by the record's OWN executable wording.
WORD_FIT_MIN_WORDS = 4
WORD_FIT_TERM_GROUPS = (
    ("guitar", "guitars"),
    ("snare",),
    ("drum", "drums"),
    ("kick",),
    ("bass",),
    ("percussion",),
    ("dembow",),
    ("keyboard",),
    ("piano",),
    ("organ",),
    ("horns",),
    ("synth",),
    ("clap", "claps"),
    ("beat",),
    ("groove",),
    ("chorus", "hook", "refrain"),
)
#: The protection a word-fit line must state, and may never order away.
PROTECTED_WORDS_RE = re.compile(
    r"protect\w*|critical business words|named words|call to action|\bCTA\b",
    re.I)
SACRIFICE_RE = re.compile(
    r"\b(?:cut|drop|remove|delete|omit|shorten|trim)\b[^.;]{0,32}"
    r"\b(?:cta\b|call to action|protected\s+\w+|named words|business words)",
    re.I)
#: Human-facing prose that is never part of the recipe's executable frame.
_NON_EXECUTABLE_TRAITS = ("word_fit", "example_direction")

_REQUIRED_TOP = ("style_id", "label", "description", "schema_version",
                 "recipe_revision", "deliveries", "style_parts",
                 "negative_tags", "rap_allowed", "client_references",
                 "production_traits")
_REQUIRED_TRAITS = ("musical_identity", "instrumentation",
                    "avoided_instrumentation", "tempo_bpm", "meter",
                    "vocal_delivery", "energy_map", "hook_guidance",
                    "delivery_constraints", "word_fit", "duration_policy")


class RecipeError(ValueError):
    """A missing, malformed or unknown recipe record."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def _record(identity, label, description, deliveries, style_parts,
            negative_tags, client_references, **traits):
    """One record, every field the schema requires and nothing shape-different."""
    return {
        "style_id": identity,
        "label": label,
        "description": description,
        "schema_version": SCHEMA_VERSION,
        "recipe_revision": RECIPE_REVISION,
        "deliveries": tuple(deliveries),
        "style_parts": tuple(style_parts),
        "negative_tags": negative_tags,
        "rap_allowed": "rap" in deliveries,
        "client_references": client_references,
        "production_traits": traits,
    }


_DRY_NEGATIVES = ("choir, reverb, echo, band dropout, acapella sections, "
                  "talk-singing, monotone delivery")
_BAND_PART = ("The intro and the outro are spoken; the full band keeps "
              "playing continuously under them.")
_SPOKEN_SUNG_MAP = ("The lead SPEAKS the lines tagged Spoken in a plain "
                    "natural voice over the music, and SINGS the lines tagged "
                    "Sung with long held notes.")
_SPOKEN_RAP_SUNG_MAP = ("The lead SPEAKS the lines tagged Spoken in a plain "
                        "natural voice over the music, RAPS the lines tagged "
                        "Rap with confident metered flow, and SINGS the lines "
                        "tagged Sung with long held notes.")

RECIPES = {
    "pop-rock": _record(
        "pop-rock",
        "Pop Rock",
        "driving guitars and drums with a big, singable chorus.",
        ("spoken", "sung"),
        (
            "pop rock, 100-142 bpm in 4/4, driving rhythmic electric guitars, "
            "defined electric bass, live-feeling kick and snare kit, tight "
            "acoustic guitar support, restrained verses opening into wide "
            "guitars and a lifted kit at the chorus, forward melodic lead with "
            "controlled edge, close dry upfront vocal, clear words, no "
            "continuous maximal distortion, no electronic dance drop.",
            "{gender} lead sings forward and melodic with clear words; never a "
            "scream and never a copied singer.",
            _SPOKEN_SUNG_MAP,
            _BAND_PART,
        ),
        _DRY_NEGATIVES,
        {"display_only": True,
         "artists": ("Maroon 5", "Paramore"),
         "note": "Recognition only: a driving band arrangement with a large "
                 "sung chorus. Never a copied voice, melody or recording, and "
                 "never serialised into a provider field."},
        musical_identity=(
            "pop rock band arrangement: guitar-led verses that open into a "
            "wide, singable chorus, with the live drum kit carrying the lift."),
        instrumentation=(
            "rhythmic electric guitars", "defined electric bass",
            "live-feeling kick and snare kit", "tight acoustic guitar support",
            "small keyboard layer when useful"),
        avoided_instrumentation=(
            "continuous maximal distortion that buries dialogue",
            "electronic dance drop", "orchestral trailer percussion"),
        tempo_bpm=(100, 142),
        meter="4/4",
        vocal_delivery=(
            "forward and melodic with controlled edge and clear words; verses "
            "leave headroom, choruses widen without screaming."),
        energy_map=(
            "restrained guitar and pulse under the spoken consequence",
            "tighter drum groove builds under the obstacle",
            "a short stop or stripped bar marks the emotional choice",
            "full guitars and lifted kit open after visible action changes the "
            "situation",
            "bridge reduces texture before the final chorus"),
        hook_guidance=(
            "one compact singable chorus hook that states the earned change and "
            "supports the same single call to action; never a second unrelated "
            "slogan."),
        delivery_constraints=(
            "no forced screaming and no imitation of a singer",
            "preserve the elected voice, language, gender, accent and "
            "explicitness",
            "the first twelve seconds remain plainly articulated speech"),
        word_fit=(
            "let snare and guitar accents support syllables instead of "
            "competing with them; reserve held vowels for the refrain and the "
            "call to action."),
        example_direction=(
            "A rehearsal space empties after a failed pitch; a guitar mute "
            "marks the admission, then the band opens as the lead returns with "
            "a concrete plan."),
        negative_constraints=(
            "no added profanity", "no invented biography",
            "no copied voice or melody", "no silent route change"),
        duration_policy=DURATION_POLICY,
        opening_spoken_seconds=OPENING_SPOKEN_SECONDS,
        visible_lip_sync={"target_pct": list(VISIBLE_LIP_SYNC_TARGET_PCT),
                          "hard_cap_pct": VISIBLE_LIP_SYNC_CAP_PCT},
    ),
    "reggaeton": _record(
        "reggaeton",
        "Reggaeton",
        "a rolling dembow groove, rhythmic vocals, and a danceable chorus.",
        ("spoken", "sung"),
        (
            "reggaeton, 88-105 bpm in 4/4, rolling dembow kick and snare "
            "pattern, rounded sub bass, syncopated percussion, economical "
            "plucks, rhythmic verses into a tuneful repeatable hook, danceable "
            "chorus, close dry upfront vocal, preserve the approved language "
            "and accent, no invented slang, no four-on-the-floor pulse.",
            "{gender} lead alternates articulate rhythmic lines with a tuneful "
            "repeatable hook; every word stays clear.",
            _SPOKEN_SUNG_MAP,
            _BAND_PART,
        ),
        _DRY_NEGATIVES,
        {"display_only": True,
         "artists": ("Daddy Yankee", "Bad Bunny"),
         "note": "Recognition only: a rolling dembow groove with a danceable "
                 "sung hook. Never a copied voice, melody or recording, and "
                 "never serialised into a provider field."},
        musical_identity=(
            "dembow-led reggaeton: the kick and snare pattern carries the "
            "identity, with articulate rhythmic lines answering a tuneful "
            "repeatable hook."),
        instrumentation=(
            "dembow kick and snare pattern", "rounded controlled sub bass",
            "syncopated percussion",
            "economical pluck, guitar or keyboard figures"),
        avoided_instrumentation=(
            "generic four-on-the-floor pulse",
            "trap hats used alone in place of the dembow",
            "club drop that replaces the vocal hook"),
        tempo_bpm=(88, 105),
        meter="4/4",
        vocal_delivery=(
            "alternates articulate rhythmic lines with a tuneful repeatable "
            "hook; stressed syllables sit against the groove with clean "
            "endings."),
        energy_map=(
            "percussion kept low under the spoken consequence",
            "the groove grows as choices create movement",
            "the rhythm pulls back briefly for the emotional admission",
            "fuller percussion and a more open sung hook return for the "
            "visible change"),
        hook_guidance=(
            "one danceable, repeatable sung hook that carries the earned change "
            "without trivialising the consequence or turning every scene into "
            "a party."),
        delivery_constraints=(
            "preserve the client's selected language and accent; this genre "
            "never automatically translates English into Spanish",
            "never add an accent, new slang or an unapproved language",
            "preserve the elected voice, gender and explicitness; this genre "
            "never turns explicitness on",
            "danciness must not trivialise the consequence"),
        word_fit=(
            "fit stressed syllables to the groove with clean endings; never "
            "stretch critical business words across inaudible effects."),
        example_direction=(
            "A locked community door interrupts the rhythm; the character "
            "chooses to ask directly, and the hook blooms as the group enters."),
        negative_constraints=(
            "no automatic Spanish or added accent", "no invented slang",
            "no added profanity", "no copied voice or melody",
            "no silent route change"),
        duration_policy=DURATION_POLICY,
        opening_spoken_seconds=OPENING_SPOKEN_SECONDS,
        visible_lip_sync={"target_pct": list(VISIBLE_LIP_SYNC_TARGET_PCT),
                          "hard_cap_pct": VISIBLE_LIP_SYNC_CAP_PCT},
    ),
    "country-rap": _record(
        "country-rap",
        "Country Rap",
        "Country storytelling meets rock power and hip-hop rhythm. Gritty, "
        "soulful singing and rhythmic rap verses build into a big, emotional "
        "chorus. Think acoustic guitars, heavy drums, deep bass and "
        "electric-guitar lift, with stories about struggle, regret, resilience "
        "and redemption.",
        ("spoken", "rap", "sung"),
        (
            "country rap, 74-100 bpm in 4/4 with a half-time pocket, picked "
            "acoustic guitar and a country guitar figure, heavy hip-hop kick "
            "and snare, deep bass, defined electric-guitar lift at the "
            "emotional turn, conversational rap verses into a big strongly sung "
            "chorus, gritty soulful lead, close dry upfront vocal.",
            "{gender} lead raps in clear conversational flow and sings the "
            "chorus with held notes; never a forced accent.",
            _SPOKEN_RAP_SUNG_MAP,
            _BAND_PART,
        ),
        _DRY_NEGATIVES,
        {"display_only": True,
         "artists": ("Jelly Roll",),
         "note": "Client recognition only: a country-rock and hip-hop blend. "
                 "Never a copied voice, melody, lyrics, recording or personal "
                 "biography, and never serialised into a provider field."},
        musical_identity=(
            "country storytelling carried by hip-hop rhythm and rock power: "
            "acoustic and country guitar figures under a heavy kick and snare, "
            "with an earned electric-guitar lift into a big sung chorus."),
        instrumentation=(
            "picked acoustic guitar", "understated country guitar figure",
            "heavy controlled hip-hop kick and snare", "deep bass",
            "defined electric-guitar lift at the emotional turn"),
        avoided_instrumentation=(
            "continuous maximal distortion that buries dialogue",
            "bluegrass virtuosity", "generic dance synth"),
        tempo_bpm=(74, 100),
        meter="4/4 with a documented half-time pocket",
        vocal_delivery=(
            "alternates clear conversational rap verses with gritty, soulful "
            "singing in a strongly sung chorus; grit is expressive texture, "
            "never a forced accent or an obscured word."),
        energy_map=(
            "restrained opening under the mandatory articulated speech",
            "bass and drums grow as choices raise pressure",
            "regret or admission strips the arrangement back",
            "electric guitars and a fully sung chorus deliver the payoff after "
            "changed action"),
        hook_guidance=(
            "one big emotional sung chorus hook that states the earned change "
            "and supports the same single call to action; the theme comes from "
            "the approved causal scene plan, never from a reference artist's "
            "biography."),
        delivery_constraints=(
            "preserve the elected voice, language, gender, accent, explicitness "
            "and route",
            "rap phrases stay breath-sized and conversational",
            "never infer addiction, incarceration, violence or religion from a "
            "recognition reference",
            "the first twelve seconds remain plainly articulated speech"),
        word_fit=(
            "keep rap phrases breath-sized and conversational; budget held "
            "chorus notes and the guitar lift while preserving protected words "
            "and one call to action."),
        example_direction=(
            "The returned keys land on the counter; the lead names the "
            "consequence, raps one honest decision in plain words, and earns "
            "the electric-guitar chorus by following through."),
        negative_constraints=(
            "no fabricated client history", "no added profanity or violence",
            "no forced accent", "no copied voice, melody or lyrics",
            "no silent route change"),
        duration_policy=DURATION_POLICY,
        opening_spoken_seconds=OPENING_SPOKEN_SECONDS,
        visible_lip_sync={"target_pct": list(VISIBLE_LIP_SYNC_TARGET_PCT),
                          "hard_cap_pct": VISIBLE_LIP_SYNC_CAP_PCT},
    ),
}

_CACHE = {}


def _normalize(style_id):
    """An id (or a label) -> the stable id; unknown raises, never aliases."""
    if isinstance(style_id, dict):
        style_id = style_id.get("value", style_id.get("style_id"))
    if not isinstance(style_id, str) or not style_id.strip():
        raise RecipeError("BAD_STYLE", "style id must be a non-empty string")
    key = style_id.strip().lower()
    if key in RECIPES:
        return key
    for sid, record in RECIPES.items():
        if key == record["label"].lower():
            return sid
    raise RecipeError(
        "UNKNOWN_STYLE",
        "%r is not one of the S75-T21 recipes %s; this owner does not alias a "
        "recipe onto another style" % (style_id, list(RECIPE_ORDER)))


def _word_fit_corpus(record):
    """(executable wording, banned wording) of one record, for word fit."""
    executable, banned = [], []
    traits = record.get("production_traits") or {}
    for key, value in traits.items():
        if key in _NON_EXECUTABLE_TRAITS:
            continue
        bucket = (banned if key in ("avoided_instrumentation",
                                    "negative_constraints") else executable)
        items = value if isinstance(value, (list, tuple)) else (value,)
        bucket.extend(str(i) for i in items if isinstance(i, str))
    executable.extend(str(p) for p in record.get("style_parts") or ())
    banned.append(str(record.get("negative_tags") or ""))
    return " ".join(executable).lower(), " ".join(banned).lower()


def word_fit_findings(record):
    """Everything wrong with one record's declared word fit (empty = clean).

    Reads ``production_traits.word_fit`` and asserts it against the record
    that declares it: the guidance may name only production elements this
    record's own executable wording carries (and never one it bans), must
    state the protected-word/CTA rule without ordering it away, and may
    budget only the deliveries the record declares.
    """
    guidance = str((record.get("production_traits") or {}).get("word_fit") or "")
    if len(guidance.split()) < WORD_FIT_MIN_WORDS:
        return ["declares no usable word_fit guidance (%r)" % guidance]
    findings = []
    low = guidance.lower()
    executable, banned = _word_fit_corpus(record)
    for group in WORD_FIT_TERM_GROUPS:
        named = [t for t in group if re.search(r"\b%s\b" % re.escape(t), low)]
        if not named:
            continue
        if any(re.search(r"\b%s\b" % re.escape(t), banned) for t in named):
            findings.append("names %s, which this recipe bans" % named[0])
        elif not any(t in executable for t in group):
            findings.append("names %s, which this recipe never declares"
                            % named[0])
    if not PROTECTED_WORDS_RE.search(low):
        findings.append("never protects the named words, protected words or CTA")
    if SACRIFICE_RE.search(low):
        findings.append("orders protected words or the CTA cut")
    deliveries = set(record.get("deliveries") or ())
    if re.search(r"\braps?\b", low) and "rap" not in deliveries:
        findings.append("budgets rap delivery this recipe declares no rap for")
    if re.search(r"\b(?:held|vowels?|sing\w*|sung|chorus|refrain|hook)\b", low) \
            and "sung" not in deliveries:
        findings.append("budgets sung material this recipe declares no sung for")
    return findings


def _undeclared_verbs(record):
    """Delivery verbs the record's own text carries but does not declare."""
    text = " ".join(str(p) for p in record.get("style_parts") or ())
    declared = set(record.get("deliveries") or ())
    return [name for name, verb in _MS.DELIVERY_MAP_VERBS.items()
            if name not in declared and re.search(r"\b%s\b" % verb, text)]


def validate_record(record):
    """Raise RecipeError on any malformed record; return it unchanged."""
    if not isinstance(record, dict):
        raise RecipeError("RECIPE_NOT_AN_OBJECT", "a record must be an object")
    sid = record.get("style_id")
    if sid not in RECIPES:
        raise RecipeError("UNKNOWN_STYLE", "%r is not this owner's" % (sid,))
    missing = [k for k in _REQUIRED_TOP if k not in record]
    missing += ["production_traits.%s" % k for k in _REQUIRED_TRAITS
                if k not in (record.get("production_traits") or {})]
    if missing:
        raise RecipeError("RECIPE_MISSING_FIELD",
                          "%s lacks %s" % (sid, ", ".join(missing)))
    if record["schema_version"] != SCHEMA_VERSION:
        raise RecipeError("RECIPE_BAD_SCHEMA",
                          "%s speaks %r, not %r"
                          % (sid, record["schema_version"], SCHEMA_VERSION))
    if record["recipe_revision"] != RECIPE_REVISION:
        raise RecipeError("RECIPE_BAD_REVISION",
                          "%s declares %r, not %r"
                          % (sid, record["recipe_revision"], RECIPE_REVISION))
    deliveries = record["deliveries"]
    if not isinstance(deliveries, tuple) or not deliveries \
            or any(d not in _MS.DELIVERIES for d in deliveries):
        raise RecipeError("RECIPE_BAD_DELIVERIES",
                          "%s deliveries must be a non-empty subset of %s"
                          % (sid, list(_MS.DELIVERIES)))
    if record["rap_allowed"] is not ("rap" in deliveries):
        raise RecipeError("RECIPE_BAD_RAP_FLAG",
                          "%s rap_allowed disagrees with its deliveries" % sid)
    parts = record["style_parts"]
    if not isinstance(parts, tuple) or len(parts) < 4 \
            or any(not isinstance(p, str) or not p.strip() for p in parts):
        raise RecipeError("RECIPE_BAD_STYLE_PARTS",
                          "%s needs at least four non-empty style_parts" % sid)
    if "{gender}" not in parts[1]:
        raise RecipeError("RECIPE_BAD_STYLE_PARTS",
                          "%s style_parts[1] must carry the {gender} slot" % sid)
    traits = record["production_traits"]
    tempo = traits.get("tempo_bpm")
    if not (isinstance(tempo, tuple) and len(tempo) == 2
            and all(isinstance(v, int) and not isinstance(v, bool) for v in tempo)
            and 0 < tempo[0] < tempo[1] <= 300):
        raise RecipeError("RECIPE_BAD_TEMPO",
                          "%s tempo_bpm must be (low, high) integers" % sid)
    if traits.get("duration_policy") != DURATION_POLICY:
        raise RecipeError("RECIPE_BAD_DURATION_POLICY",
                          "%s must name the one canonical duration registry"
                          % sid)
    if traits.get("opening_spoken_seconds") != OPENING_SPOKEN_SECONDS:
        raise RecipeError("RECIPE_BAD_OPENING",
                          "%s must keep the %d spoken seconds"
                          % (sid, OPENING_SPOKEN_SECONDS))
    refs = record["client_references"]
    if not isinstance(refs, dict) or refs.get("display_only") is not True:
        raise RecipeError("RECIPE_BAD_REFERENCES",
                          "%s client_references must be display_only" % sid)
    undeclared = _undeclared_verbs(record)
    if undeclared:
        raise RecipeError("RECIPE_UNDECLARED_DELIVERY",
                          "%s text maps %s but declares %s"
                          % (sid, undeclared, list(deliveries)))
    missing_verbs = _MS.missing_delivery_verbs(" ".join(parts), deliveries)
    if missing_verbs:
        raise RecipeError("RECIPE_NO_DELIVERY_MAP",
                          "%s style_parts carry no %s delivery map"
                          % (sid, " / ".join(missing_verbs)))
    negatives = _SR.check_negatives(str(record["negative_tags"]), sid)
    if negatives:
        raise RecipeError("RECIPE_BAD_NEGATIVES",
                          "%s negative_tags: %s" % (sid, "; ".join(negatives)))
    findings = word_fit_findings(record)
    if findings:
        raise RecipeError("RECIPE_BAD_WORD_FIT",
                          "%s word_fit: %s" % (sid, "; ".join(findings)))
    return record


def recipe_ids():
    """The three recipe ids this owner carries, in menu order."""
    return RECIPE_ORDER


style_ids = recipe_ids


def load_recipe(style_id):
    """One validated recipe record (a copy; callers cannot mutate the file)."""
    sid = _normalize(style_id)
    cached = _CACHE.get(sid)
    if cached is None:
        cached = validate_record(copy.deepcopy(RECIPES[sid]))
        _CACHE[sid] = cached
    return copy.deepcopy(cached)


def recipe(style_id):
    """Alias of :func:`load_recipe`, the name T20/T22 also publish."""
    return load_recipe(style_id)


def production_traits(style_id):
    """Provider-safe traits only (a copy)."""
    return load_recipe(style_id)["production_traits"]


def word_fit(style_id):
    """The record's declared word-fit guidance -- the field is READ here."""
    return str(production_traits(style_id)["word_fit"])


def negative_tags(style_id):
    """The record's own negative tags (data; never a second copy in code)."""
    return str(load_recipe(style_id)["negative_tags"])


def client_references(style_id):
    """Display-only recognition metadata; never a provider field."""
    return load_recipe(style_id)["client_references"]


def client_reference_leaks(text, style_id=None):
    """Artist names/aliases found in ``text`` (empty = clean).

    A local, deterministic check for this owner's recipes. S75-T41 owns the
    final outgoing guard for every catalog reference; this never replaces it.
    """
    haystack = str(text or "").lower()
    ids = [style_id] if style_id is not None else list(RECIPE_ORDER)
    hits = []
    for sid in ids:
        for name in client_references(sid)["artists"]:
            if name.lower() in haystack and name not in hits:
                hits.append(name)
    return hits


def compile_style(style_id, sheet=None, vocal_gender="f", pace_plan=None):
    """The provider style field for one recipe, through the live composer.

    ``compose_style_block`` composes the one clean ending, the hook-order
    clause, the delivery map, the band wording and the 1000-character cap on
    the FINAL text -- the same code path ``suno_recipe.style_text`` uses for a
    registered style, never a second implementation here.
    """
    record = load_recipe(style_id)
    return _SR.compose_style_block(
        record, sheet=sheet, vocal_gender=vocal_gender, pace_plan=pace_plan,
        style_id=record["style_id"], deliveries=record["deliveries"])


def style_error_type():
    """The MusicStyleError class the one composer raises."""
    return _MS.MusicStyleError


def menu_record(style_id):
    """A ``music_styles.STYLES``-shaped row for the S75-T18 catalog owner.

    Carries only what ``music_styles.style_prompt`` reads (label, deliveries,
    base prompt) plus the client description and the recognition names. The
    catalog already holds these three ids; this is a projection for its owner,
    never a registration call.
    """
    record = load_recipe(style_id)
    return {
        "style_id": record["style_id"],
        "label": record["label"],
        "sound": record["description"],
        "deliveries": tuple(record["deliveries"]),
        "suno_style_prompt": record["style_parts"][0],
        "client_references": copy.deepcopy(record["client_references"]),
        "recipe_revision": record["recipe_revision"],
    }
