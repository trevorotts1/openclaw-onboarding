"""S75-T19: executable production recipes for the five story-first styles
(Acoustic Pop, Folk Storytelling, Country Pop, Alternative R&B, Afro-Soul).

One versioned JSON source per style lives in ``music_styles/recipes/``. A
recipe carries two separate namespaces by design:

* ``client_references`` -- display-only recognition names. Never serialised
  into a provider field.
* ``production_traits``  -- the only material the compiler may render into a
  Suno style field: instrumentation, rhythm, tempo, vocal behaviour, the
  story-linked energy map, hook shape, spoken/sung split, word fit and
  duration guidance.

Compilation reuses :mod:`music_styles` for the G1 delivery-map sentence and
its assertion, so a recipe prompt can never drift from the sheet it maps.

The first twelve seconds of articulated speech are owned by the caller's
sheet; these recipes only instruct the arrangement to stay out of its way.
The three original styles are untouched here: this module never imports or
rewrites their records, and it refuses an id it does not own.

``assert_no_client_references`` is a narrow compile-time leak check over
these five recipes. It is NOT the S75-T41 send-boundary guard and does not
claim to be.

stdlib only; no network, no provider call, no spend.
"""
from __future__ import annotations

import copy
import json
import os
import re

try:
    from . import music_styles as MS
except ImportError:                                  # imported as core.*
    from music_styles import music_styles as MS      # type: ignore

TOOL_NAME = "music_recipes"
TOOL_VERSION = "0.1.0"
RECIPE_SCHEMA = "blackceo.music-recipe/v1"

RECIPE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "recipes")

#: The five styles this unit owns. Anything else is refused, not guessed.
RECIPE_IDS = (
    "acoustic-pop",
    "folk-storytelling",
    "country-pop",
    "alternative-rnb",
    "afro-soul",
)

_REQUIRED_TOP = ("style_id", "label", "description", "catalog_revision",
                 "recipe_revision", "deliveries", "client_references",
                 "production_traits")
_REQUIRED_TRAITS = ("musical_identity", "instrumentation",
                    "avoided_instrumentation", "rhythm", "tempo",
                    "vocal_delivery", "energy_map", "hook_guidance",
                    "spoken_sung_split", "delivery_constraints", "word_fit",
                    "mood_policy", "story_energy", "duration_guidance")

#: Word-fit defaults (section 3 formula). A recipe may override either.
_WORD_FIT_DEFAULT = {"instrumental_open_seconds": 3.0,
                     "breath_allowance_share": 0.06}


class RecipeError(Exception):
    """Unknown recipe, malformed recipe, bad duration, or a leaked reference."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


_CACHE = {}


def _read(style_id):
    """Load and validate one recipe JSON; cached by id."""
    cached = _CACHE.get(style_id)
    if cached is not None:
        return cached
    key = _style_key(style_id)
    path = os.path.join(RECIPE_DIR, "%s.json" % key)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            rec = json.load(fh)
    except FileNotFoundError:
        raise RecipeError("UNKNOWN_RECIPE", "no recipe for %r at %s"
                          % (style_id, path))
    except ValueError as exc:
        raise RecipeError("BAD_RECIPE", "%s is not valid JSON: %s"
                          % (key, exc))
    missing = [k for k in _REQUIRED_TOP if k not in rec]
    traits = rec.get("production_traits") or {}
    missing += ["production_traits.%s" % k for k in _REQUIRED_TRAITS
                if k not in traits]
    if missing:
        raise RecipeError("BAD_RECIPE", "%s is missing %s"
                          % (key, ", ".join(missing)))
    if rec["style_id"] != key:
        raise RecipeError("BAD_RECIPE", "%s declares style_id %r"
                          % (key, rec["style_id"]))
    bad = [d for d in rec["deliveries"] if d not in MS.DELIVERIES]
    if bad:
        raise RecipeError("BAD_RECIPE", "%s names unknown deliveries %s"
                          % (key, bad))
    if set(traits["duration_guidance"]) != {str(s) for s in
                                            MS.OFFERED_LENGTHS_S}:
        raise RecipeError("BAD_RECIPE",
                          "%s duration_guidance must cover exactly %s seconds"
                          % (key, list(MS.OFFERED_LENGTHS_S)))
    _CACHE[key] = rec
    return rec


def _norm(value):
    """Case/punctuation-insensitive key, so labels and ids both resolve."""
    text = value.lower().replace("r & b", "rnb").replace("r&b", "rnb")
    return re.sub(r"[^a-z0-9]+", "", text)


def _style_key(style_id):
    """Normalize an id or a label to one of the five owned ids."""
    if isinstance(style_id, dict):
        style_id = style_id.get("value", style_id.get("style_id"))
    if not isinstance(style_id, str) or not style_id.strip():
        raise RecipeError("BAD_RECIPE_ID", "style_id must be a non-empty "
                          "string, got %r" % (style_id,))
    key = _norm(style_id)
    for rid in RECIPE_IDS:
        if key == _norm(rid):
            return rid
    raise RecipeError("UNKNOWN_RECIPE",
                      "%r is not one of this unit's five styles %s"
                      % (style_id, list(RECIPE_IDS)))


def _length_seconds(duration):
    """Normalize a duration to one of the six offered lengths, in seconds."""
    if isinstance(duration, dict):
        duration = duration.get("value", duration.get("seconds"))
    if isinstance(duration, bool):
        raise RecipeError("BAD_DURATION", "duration must not be a bool")
    if isinstance(duration, (int, float)):
        secs = int(round(float(duration)))
        if secs in MS.OFFERED_LENGTHS_S:
            return secs
    elif isinstance(duration, str):
        key = duration.strip().lower().replace(" ", "").replace("-", "")
        secs = MS.LENGTH_ALIASES.get(key)
        if secs is not None:
            return secs
    raise RecipeError("UNKNOWN_DURATION",
                      "duration %r is not one of %s seconds"
                      % (duration, list(MS.OFFERED_LENGTHS_S)))


def recipe_ids():
    """The five recipe ids this unit owns, in menu order."""
    return RECIPE_IDS


def load_recipe(style_id):
    """Full recipe record (deep copy) for one owned style."""
    return copy.deepcopy(_read(style_id))


def catalog_entry(style_id):
    """Client display record: label, description and recognition names only.

    This is the menu/help projection. It is data for the card, never for a
    provider field.
    """
    rec = _read(style_id)
    return {
        "style_id": rec["style_id"],
        "label": rec["label"],
        "description": rec["description"],
        "catalog_revision": rec["catalog_revision"],
        "recipe_revision": rec["recipe_revision"],
        "client_references": copy.deepcopy(rec["client_references"]),
        "help_line": "%s: %s" % (rec["label"], rec["description"]),
    }


def production_traits(style_id):
    """Provider-safe traits only (deep copy). No reference metadata inside."""
    return copy.deepcopy(_read(style_id)["production_traits"])


def duration_guidance(style_id, duration):
    """One style's arrangement guidance for one of the six durations."""
    rec = _read(style_id)
    secs = _length_seconds(duration)
    return rec["production_traits"]["duration_guidance"][str(secs)]


def energy_for_stage(style_id, stage):
    """The arrangement instruction bound to one story stage.

    Stages: consequence, obstacle, choice, change, hook, cta. The hook stage
    is defined by each recipe to land at or after the change, never before.
    """
    energy = _read(style_id)["production_traits"]["energy_map"]
    key = str(stage).strip().lower()
    if key not in energy:
        raise RecipeError("UNKNOWN_STAGE",
                          "%r is not one of %s" % (stage, sorted(energy)))
    return energy[key]


def word_fit(style_id, duration):
    """Word-fit budget for one style at one duration.

    ``available_vocal_seconds = duration - instrumental_only_seconds -
    explicit breath/transition allowance`` (MUSIC-AND-VIDEO-UX.md section 3).
    The result is an estimate; measured timestamps remain the proof.
    """
    rec = _read(style_id)
    secs = _length_seconds(duration)
    policy = dict(_WORD_FIT_DEFAULT)
    policy.update(rec.get("word_fit_policy") or {})
    open_secs = float(policy["instrumental_open_seconds"])
    allowance = round(secs * float(policy["breath_allowance_share"]), 1)
    available = round(secs - open_secs - allowance, 1)
    if available <= 0:
        raise RecipeError("BAD_WORD_FIT", "%s at %ss leaves no vocal time"
                          % (rec["style_id"], secs))
    return {
        "style_id": rec["style_id"],
        "duration_seconds": secs,
        "instrumental_only_seconds": open_secs,
        "breath_allowance_seconds": allowance,
        "available_vocal_seconds": available,
        "note": rec["production_traits"]["word_fit"],
        "basis": "estimate; verify against measured timestamps",
    }


def reference_aliases():
    """Every display-only artist name this unit's recipes carry."""
    names = []
    for rid in RECIPE_IDS:
        for name in _read(rid)["client_references"].get("artists", ()):
            if name not in names:
                names.append(name)
    return tuple(names)


def find_client_references(text):
    """Display-only names present in text (case/punctuation aware)."""
    if not isinstance(text, str):
        return []
    return [name for name in reference_aliases()
            if re.search(r"\b%s\b" % re.escape(name), text, re.IGNORECASE)]


def assert_no_client_references(text):
    """Raise when a provider-bound text carries a display-only name.

    Narrow compile-time check over these five recipes; the S75-T41 guard at
    the send boundary remains the authoritative one.
    """
    hits = find_client_references(text)
    if hits:
        raise RecipeError("ARTIST_REFERENCE_IN_PROMPT",
                          "provider text carries display-only reference(s) "
                          "%s; compile production_traits only" % ", ".join(hits))
    return text


def compile_style_prompt(style_id, duration=None, sheet_text=None):
    """Render one recipe into a Suno style field.

    Only ``production_traits`` are rendered. The G1 delivery map is built
    from the sheet's own tags when a sheet is passed, otherwise from the
    recipe's deliveries, and is asserted through :mod:`music_styles`.
    """
    rec = _read(style_id)
    t = rec["production_traits"]
    tempo = t["tempo"]
    parts = [
        t["musical_identity"],
        "instrumentation: %s" % "; ".join(t["instrumentation"]),
        "avoid %s" % "; ".join(t["avoided_instrumentation"]),
        t["rhythm"],
        "tempo %g-%g bpm, %s, %s" % (tempo["min_bpm"], tempo["max_bpm"],
                                     tempo["meter"], tempo["note"]),
        t["vocal_delivery"],
        t["hook_guidance"],
        t["spoken_sung_split"],
        t["delivery_constraints"],
        t["story_energy"],
    ]
    if duration is not None:
        secs = _length_seconds(duration)
        parts.append("at %g seconds: %s"
                     % (secs, t["duration_guidance"][str(secs)]))
    deliveries = set(MS.sheet_deliveries(sheet_text)) if sheet_text else set()
    if not deliveries:
        deliveries = set(rec["deliveries"])
    clauses = [clause for name, clause in MS.DELIVERY_MAP_CLAUSES
               if name in deliveries]
    if not clauses:
        raise RecipeError("EMPTY_SHEET_DELIVERIES",
                          "no named delivery to map; every tag must name "
                          "Spoken, Rap or Sung")
    body = ". ".join(p.strip().rstrip(".") for p in parts if str(p).strip())
    text = "%s. The lead %s." % (body, ", ".join(clauses))
    MS.assert_delivery_map(rec["style_id"], text, deliveries)
    return assert_no_client_references(text)
