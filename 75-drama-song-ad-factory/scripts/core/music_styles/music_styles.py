"""Music styles D18: the three offered styles and their Suno style prompts,
plus the D15 spoken-share target each one carries. stdlib only, no network.

Owner decisions (2026-10-07):
  D18 - exactly three styles are offered: Soul Ballad, R&B Flow, Soul Rise.
  D15 retarget (Decision log 37, plan 6.7) - spoken-style delivery targets
        45% of runtime, never more than 55%, never less than 40%, for EVERY
        length and EVERY style; rap is spoken-style delivery. The earlier
        wider ceiling and the per-length targets are retired: there is one
        band now, not a table.
  SPK001 (Trevor, 2026-10-08) - retargeted: spoken 22.5% of runtime (20-25),
        judged by Trevor's 5/10 band, so the redo edges are 12.5 and 32.5. The spoken opener stays short and the first real
        singing is targeted at 15% of runtime (H6).

Enforcement lives here: check_share() refuses any spoken share outside
the redo edges (12.5%..32.5%) for every style and every length. The three numbers are read
from core/spoken_share (the single source for the retarget), never kept as
a second copy here. Voice gender is NOT ours -- that is V2B-AUDIO-U1
(core/audio_c3), so prompts say "lead vocal" only.

G1 (owner order 2026-10-08 11:50, part G amended by the Opus audio review,
review item G6): every style prompt ends with a DELIVERY MAP -- one
sentence that names, from the sheet, which lines Suno SINGS and which
it SPEAKS ("SPEAKS the lines tagged Spoken ... SINGS the lines tagged
Sung"). Evidence: both takes that actually sang carried that map. The
earlier version of G1 (banning spoken-word wording and putting "spoken
word, rap" in the negative tags) is REVERSED: banning spoken/rap while
the sheet has spoken blocks contradicts the sheet and confuses Suno.
Instead the gate now REFUSES a payload whose negative tags contain
"spoken word" or "rap" while its lyric sheet has spoken or rap blocks.
Enforced at this single rendering point (style_prompt + delivery_map +
assert_delivery_map) and stamped on every Suno song payload whose sheet
names a delivery by core/audio_c3 no_echo.
"""
from __future__ import annotations

import os
import re
import sys

from math import isfinite

try:
    import spoken_share as _SS                      # core/ on sys.path
except ImportError:                                 # imported as core.*
    from .. import spoken_share as _SS

TOOL_NAME = "music_styles"
TOOL_VERSION = "0.1.0"
SCHEMA_VERSION = "blackceo.music-styles/v1"

#: Owner D15 hard band, as fractions of total runtime. One band: every
#: style, every length. Sourced from core/spoken_share so it cannot drift.
SPOKEN_SHARE_TARGET = _SS.TARGET
SPOKEN_SHARE_MIN = _SS.FLOOR
SPOKEN_SHARE_MAX = _SS.CAP
#: H6: first real singing (measured on the vocal stem) targets this share of
#: runtime. The rule itself lives in core/spoken_share and is re-exported
#: here so the planner/QC read one copy of it.
FIRST_SUNG_TARGET_PCT = _SS.FIRST_SUNG_TARGET_PCT
check_first_sung = _SS.check_first_sung

#: Offered lengths (owner D6 + D23 + F15). 120 (the card's "2 minutes",
#: F15 owner order 2026-10-08) sits between 90 and 180 -- the card always
#: offered it; FU-U2 makes the code agree with the card.
LENGTH_ALIASES = {
    "60": 60, "60s": 60, "60sec": 60, "60seconds": 60,
    "90": 90, "90s": 90, "90sec": 90, "90seconds": 90,
    "120": 120, "120s": 120, "120sec": 120, "120seconds": 120,
    "2m": 120, "2min": 120, "2minutes": 120,
    "180": 180, "3m": 180, "3min": 180, "3minutes": 180,
    "300": 300, "5m": 300, "5min": 300, "5minutes": 300,
    "600": 600, "10m": 600, "10min": 600, "10minutes": 600,
}

#: Every length the factory offers. The D15 band is keyed by NONE of them --
#: this tuple only bounds what a caller may ask about.
#: S75-W05-U3: the scattered duration tuple is REMOVED (D12). THE one table is
#: suno_recipe.duration_registry.CANONICAL_DURATION_S (60, 90, 120, 180, 300,
#: 600, the two-minute 120 s entry included). The registry leaf is loaded BY
#: FILE PATH, never through `import suno_recipe...`: that name resolves to the
#: heavy package __init__ (or to a bare suno_recipe.py shadowing it when the
#: suno_recipe/ dir is on sys.path), which pulls hook_placement back into a
#: partially-initialized length_formula whenever this module is first reached
#: from length_formula's own import. The leaf imports NOTHING, so a file-path
#: load is safe in every import order and never touches sys.modules.
_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

def _load_canonical_durations():
    import importlib.util
    leaf = os.path.join(_CORE, "suno_recipe", "duration_registry.py")
    spec = importlib.util.spec_from_file_location(
        "_suno_recipe_duration_registry", leaf)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.CANONICAL_DURATION_S

CANONICAL_DURATION_S = _load_canonical_durations()
OFFERED_LENGTHS_S = CANONICAL_DURATION_S

#: Delivery labels a timing segment may carry.
DELIVERIES = ("spoken", "rap", "sung")

#: Rap is spoken-style delivery (D18 table, R&B Flow note). Counting it is
#: what stops a rap-heavy cut from measuring under the cap by accident.
SPOKEN_STYLE_DELIVERIES = frozenset({"spoken", "rap"})

#: G1 amended (review G6): negative tags that contradict a lyric sheet.
#: A payload whose negative tags contain "spoken word" or "rap" while its
#: sheet carries spoken or rap blocks is refused -- telling Suno "no
#: spoken word" while tagging blocks [Spoken ...] removes the one
#: ingredient both working takes shared.
CONTRADICTING_NEGATIVE_TAGS = ("spoken word", "rap")

#: G1 amended: the delivery-map clauses, ONE copy. style_prompt(),
#: delivery_map() and every assertion render from these, so the sentence a
#: payload carries can never drift from the sentence the gate checks.
DELIVERY_MAP_CLAUSES = (
    ("spoken", "SPEAKS the lines tagged Spoken in a plain natural voice "
               "over the music"),
    ("rap", "RAPS the lines tagged Rap with confident metered flow"),
    ("sung", "SINGS the lines tagged Sung with long held notes"),
)
#: delivery name -> the verb that must appear in a mapped style text.
DELIVERY_MAP_VERBS = {name: clause.split(" ", 1)[0]
                      for name, clause in DELIVERY_MAP_CLAUSES}
#: The spoken + sung sentence in the exact form the working takes used.
DELIVERY_MAP_TEMPLATE = "The lead %s, and %s." % (
    DELIVERY_MAP_CLAUSES[0][1], DELIVERY_MAP_CLAUSES[2][1])

#: Sheet tag words: a block counts as rap when its tag names rap, as
#: spoken when it names spoken, as sung when it names sung/sing/hook/
#: chorus/verse. Matched at a word boundary on a normalized tag, so
#: "trap beat" is never read as rap and "spoken-word" still counts.
SHEET_SPOKEN_TAGS = ("spoken",)
SHEET_SUNG_TAGS = ("sung", "sing", "hook", "chorus", "verse")
SHEET_RAP_TAGS = ("rap",)

SOURCE_D18 = "Owner D18 2026-10-07, plan 6.7"
SOURCE_D15 = "Owner D15 retarget 2026-10-07, Decision log 37; plan 6.7"


class MusicStyleError(Exception):
    """Unknown style, unknown length, or a malformed measurement input."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


#: The three offered styles (D18). Prompts are Suno style-field text: comma
#: separated tags, no lyric text, no character gender (voice casting is U1).
#: Every style carries the SAME D15 share rule: one band, not a table.
_SHARE_RULE = ("target %g%% of runtime, redo past %g%% or under %g%% "
               "(rap counts as spoken)"
               % (_SS.SPOKEN_TARGET_PCT, _SS.SPOKEN_MAX_PCT,
                  _SS.SPOKEN_MIN_PCT))
STYLES = {
    "soul-ballad": {
        "style_id": "soul-ballad",
        "label": "Soul Ballad",
        "sound": "Slow, emotional, soulful singing",
        "share_rule": _SHARE_RULE,
        "deliveries": ("spoken", "sung"),
        "notes": ("The original drama-song style."),
        "suno_style_prompt": (
            "soul ballad, slow emotional 62-68 bpm, warm felt piano, "
            "brushed kit entering at the chorus, deep rounded bass, "
            "soulful lead vocal with melismatic runs, close dry upfront "
            "vocal, minor key, restrained verse opening into a full-voiced "
            "chorus, no distortion."
        ),
    },
    "rnb-flow": {
        "style_id": "rnb-flow",
        "label": "R&B Flow",
        "sound": "Rap verses with a smooth sung R&B hook",
        "share_rule": _SHARE_RULE,
        "deliveries": ("spoken", "rap", "sung"),
        "notes": ("Like the One Check Chanel reference. Approved example: "
                  "Version F (final-9x16-h3-F-3d-rnb-rap.mp4, lifelike 3D), "
                  "Trevor 2026-10-07: a keeper."),
        "suno_style_prompt": (
            "contemporary r&b with hip-hop flow, 84-94 bpm, crisp programmed "
            "drums with tight hats, deep sub bass, Rhodes chord stabs, bright "
            "synth plucks, rhythmic rap verses delivered with clear diction "
            "over the beat, smooth sung r&b hook, call-and-response ad-libs, "
            "confident swagger, dry upfront vocal, radio-ready mix, no vocals "
            "in the intro pad"
        ),
    },
    "soul-rise": {
        "style_id": "soul-rise",
        "label": "Soul Rise",
        "sound": ("Starts slow and soulful through the pain, lifts into an "
                  "upbeat groove at the turning point (mentor / product)"),
        "share_rule": _SHARE_RULE,
        "deliveries": ("spoken", "sung"),
        "notes": ("The tempo lift lands on the story's turn."),
        "suno_style_prompt": (
            "soul with a two-part arc, brooding 62-68 bpm opening lifting to "
            "an upbeat 100-112 bpm groove at the turn, warm piano and round "
            "bass foundation, percussion thickening as it lifts, triumphant "
            "horn stabs and claps from the turnaround, hopeful minor-to-major "
            "resolution, soulful lead vocal rising in register, close dry "
            "upfront vocal, single continuous take"
        ),
    },
}

#: S75-T20: executable rap recipes. Melodic Rap, Trap Rap and Pop Rap are
#: recipe records, not menu entries -- the eighteen-choice catalog is the
#: T18 catalog owner's write, so ``style_ids()`` (the card menu) stays at the
#: three D18 styles while these ids already resolve through style(),
#: style_prompt(), spoken_target() and the payload compiler.
#:
#: Client recognition names live ONLY in ``client_references`` (display
#: metadata). The provider compiler reads ``production_traits`` only, so no
#: artist name can reach an outgoing style field by construction.
#:
#: Trap Rap does NOT enable explicitness: ``explicit_lyrics`` is an explicit
#: False on every recipe, never inferred from the genre label. A genre word
#: is not permission for profanity, violence or an invented biography.
RAP_RECIPE_REVISION = "s75-t20/1"
SOURCE_S75_T20 = "Owner S75-T20 approval 2026-10-24"

RECIPES = {
    "melodic-rap": {
        "style_id": "melodic-rap",
        "label": "Melodic Rap",
        "description": ("emotional rap that moves between rhythmic lines and "
                        "a tuneful hook."),
        "recipe_revision": RAP_RECIPE_REVISION,
        "deliveries": ("spoken", "rap", "sung"),
        "explicit_lyrics": False,
        "client_references": ("Drake", "Rod Wave"),
        "production_traits": {
            "genre": "melodic rap",
            "tempo": ("70-90 bpm felt half-time or 140-180 counted "
                      "double-time, one documented interpretation"),
            "meter": "4/4",
            "instrumentation": (
                "restrained minor-key piano motif", "warm pad",
                "controlled 808 bass", "sparse kick and snare",
                "selective hi-hat movement"),
            "avoided_instrumentation": (
                "dense triplet hi-hat rolls", "wall of distorted guitars"),
            "vocal_delivery": (
                "clear rhythmic rap moving into a pitched melodic hook; "
                "emotional cracks carried by dynamics, not a copied voice"),
            "energy_map": (
                "sparse under the spoken consequence, beat thins at the "
                "costly admission, harmonic width after the character "
                "chooses differently"),
            "hook": ("pitched melodic hook is required after the rap states "
                     "the tension; a spoken-only hook fails"),
            "delivery_constraints": (
                "names and offer words remain readable; pitch tuning is "
                "texture only, never a voice change"),
            "word_fit": ("separate rapid syllables from held notes and leave "
                         "a breath before the hook"),
            "example": ("fictional: the lead admits the missed call before "
                        "the beat thickens; the sung line returns after they "
                        "answer"),
            "negatives": ("no spoken-only hook", "no doubled tempo",
                          "no unreadable names"),
        },
    },
    "trap-rap": {
        "style_id": "trap-rap",
        "label": "Trap Rap",
        "description": ("punchy rap over deep bass and crisp, rolling "
                        "hi-hats, with a strong hook."),
        "recipe_revision": RAP_RECIPE_REVISION,
        "deliveries": ("spoken", "rap", "sung"),
        # A trap label is not a licence: clean by default, every audience.
        "explicit_lyrics": False,
        "client_references": ("Cardi B", "Future"),
        "production_traits": {
            "genre": "trap rap",
            "tempo": ("65-85 bpm half-time or 130-170 counted double-time, "
                      "one documented counted feel"),
            "meter": "4/4",
            "instrumentation": (
                "controlled 808 low end", "punchy kick", "dry snare and clap",
                "crisp rolling hi-hats", "sparse dark synth, bell or piano "
                "motif"),
            "avoided_instrumentation": (
                "unbroken maximal triplet density", "generic four-on-the-floor"),
            "vocal_delivery": (
                "rhythmic, confident and intelligible lead; short emphatic "
                "phrases and purposeful rests, not automatic triplet density"),
            "energy_map": (
                "bass and percussion articulate escalating pressure after "
                "the spoken opening; bass drops out briefly for the "
                "emotional admission, then returns"),
            "hook": ("compact hook with a melodic or rhythmic anchor inside "
                     "the accepted spoken/rap budget"),
            "delivery_constraints": (
                "ad-libs never mask names, business claims or the call to "
                "action; lyrics stay inside the approved audience and tone"),
            "word_fit": ("allocate rests and consonants explicitly; never "
                         "solve overlength with all double-time delivery"),
            "example": ("fictional: the counter goes silent as the payment "
                        "is declined; a precise rap passage names the choice, "
                        "then the hook carries the changed response"),
            "negatives": ("no profanity", "no violence", "no invented street "
                          "biography", "no rap-negative tags"),
        },
    },
    "pop-rap": {
        "style_id": "pop-rap",
        "label": "Pop Rap",
        "description": ("upbeat, easy-to-follow rap with a bright, catchy "
                        "pop hook."),
        "recipe_revision": RAP_RECIPE_REVISION,
        "deliveries": ("spoken", "rap", "sung"),
        "explicit_lyrics": False,
        "client_references": ("Nelly", "Flo Rida", "Puff Daddy"),
        "production_traits": {
            "genre": "pop rap",
            "tempo": "92-118 bpm",
            "meter": "4/4",
            "instrumentation": (
                "bright bass", "crisp hip-hop and pop drums",
                "buoyant piano or synth stabs",
                "clean accessible melodic chorus"),
            "avoided_instrumentation": (
                "unbroken ominous trap texture",
                "instrumental dance drop replacing the vocal hook"),
            "vocal_delivery": (
                "rhythmic, easy-to-follow rap with fewer crowded "
                "subdivisions than trap, then a clearly sung or deliberately "
                "chant-like hook"),
            "energy_map": (
                "serious spoken consequence even under an energetic sound; "
                "action-focused rap builds pressure, the pre-hook clears "
                "space, the bright hook arrives only when the choice earns it"),
            "hook": ("immediately memorable original hook supporting the same "
                     "single call to action; never a borrowed known tune"),
            "delivery_constraints": (
                "mix stays open for story words; light call and response only "
                "for declared cast"),
            "word_fit": "short rhyme units and a low-density hook",
            "example": ("fictional: a failed handoff opens the scene; the rap "
                        "follows two concrete attempts, and the chorus lifts "
                        "when the team makes a clear plan"),
            "negatives": ("no repeated brand slogan", "no unexplained party "
                          "extras", "no second call to action"),
        },
    },
}

#: Trap Rap must never turn explicitness on by itself (owner hard rule).
#: Named so a caller reads the rule instead of inferring it from a genre.
EXPLICIT_NEVER_INFERRED = ("trap-rap",)


def recipe_ids():
    """The three S75-T20 rap recipe ids."""
    return tuple(RECIPES)


def _record(style_id):
    """One style or recipe record by id (STYLES wins on a shared id)."""
    sid = _style_key(style_id)
    if sid in STYLES:
        return STYLES[sid]
    return RECIPES[sid]


def enables_explicit_lyrics(style_id):
    """Whether choosing this style turns explicitness on. Never, for any
    recipe: rap and trap are genres, not consent to profanity."""
    return bool(_record(style_id).get("explicit_lyrics", False))


def recipe(style_id):
    """Full recipe record including display-only client_references."""
    return dict(_record(style_id))


def _compile_traits(traits):
    """Provider style text from production_traits ALONE.

    Client reference metadata is a different key and is never read here, so
    an artist name cannot reach a Suno field through this compiler.
    """
    parts = [traits["genre"], traits["tempo"], traits["meter"]]
    parts.extend(traits["instrumentation"])
    parts.append(traits["vocal_delivery"])
    parts.append(traits["energy_map"])
    parts.append(traits["hook"])
    parts.append(traits["delivery_constraints"])
    parts.extend("avoid %s" % a for a in traits["avoided_instrumentation"])
    return ", ".join(parts)


#: G1 amended: the two contradicting tag words, whole-word matched in a
#: joined tag list by assert_no_contradiction().
_CONTRADICTING_PATTERNS = tuple(
    (word, re.compile(r"\b%s\b" % re.escape(word), re.IGNORECASE))
    for word in CONTRADICTING_NEGATIVE_TAGS
)


def sheet_deliveries(sheet_text):
    """Which deliveries a lyric sheet carries: {"spoken", "rap", "sung"}.

    A block counts as rap when its tag names rap, as spoken when its tag
    names spoken ("[Spoken ...]", "[Spoken Word]"), and as sung when its
    tag names sung/sing/hook/chorus/verse. Case-insensitive, matched at a
    word boundary on a punctuation-normalized tag, so "trap beat" is never
    read as rap while "spoken-word" still counts. The sheet is a string of
    [Tag] blocks; a tag naming no delivery counts as nothing.

    FU-U1: THE tag grammar lives in suno_recipe.parse_tag -- this delegates
    to it so the delivery map and the lyric gate read the same sheet.
    """
    found = set()
    if not isinstance(sheet_text, str) or not sheet_text.strip():
        return found
    from suno_recipe.suno_recipe import parse_tag
    for m in re.finditer(r"\[([^\]]*)\]", sheet_text):
        d = parse_tag(m.group(1))
        if d in ("sung", "spoken", "rap"):
            found.add(d)
    return found


def _map_sentence(deliveries):
    """The delivery-map sentence for one set of deliveries."""
    parts = [clause for name, clause in DELIVERY_MAP_CLAUSES
             if name in _deliveries_of(deliveries)]
    if not parts:
        raise MusicStyleError(
            "EMPTY_SHEET_DELIVERIES",
            "no named delivery to map ([Spoken ...], [Sung ...], "
            "[Rap ...]); every tag must name its delivery (G1)")
    return "The lead %s." % ", ".join(parts)


def delivery_map(sheet_text):
    """The G1 amended delivery-map sentence for one lyric sheet.

    Built from the sheet's own tags, in the plain-word form both working
    takes carried ("SPEAKS the lines tagged Spoken ... SINGS the lines
    tagged Sung"); RAPS joins them when the sheet has rap blocks. Raises
    MusicStyleError(EMPTY_SHEET_DELIVERIES) on a sheet that names no
    delivery at all -- a sheet whose tags never name a delivery is the O3
    fault this unit exists to prevent.
    """
    return _map_sentence(sheet_deliveries(sheet_text))


def default_delivery_map(style_id):
    """The delivery-map sentence for a style when no sheet is at hand."""
    return _map_sentence(set(_record(style_id)["deliveries"]))


def _deliveries_of(deliveries):
    """A sheet string -> the deliveries its tags name; a collection of
    delivery names -> that collection. One choke point, so no caller can
    pass the wrong one and get characters instead of deliveries.
    """
    if isinstance(deliveries, str):
        return sheet_deliveries(deliveries)
    return set(deliveries or ())


def missing_delivery_verbs(text, deliveries):
    """Verbs a style text still owes a set of deliveries (empty = mapped)."""
    deliveries = _deliveries_of(deliveries)
    if not isinstance(text, str) or not text.strip():
        return [DELIVERY_MAP_VERBS[d] for d in sorted(deliveries)]
    upper = text.upper()
    return [DELIVERY_MAP_VERBS[d] for d in sorted(deliveries)
            if DELIVERY_MAP_VERBS[d] not in upper]


def has_delivery_map(text, deliveries):
    """True when the style text already carries every verb of a sheet."""
    return not missing_delivery_verbs(text, deliveries)


def assert_delivery_map(style_id, text, deliveries):
    """Raise MusicStyleError(NO_DELIVERY_MAP) when a style text for a set
    of named deliveries carries no delivery map ("SINGS ... the lines
    tagged"). Pass the sheet text or the delivery names -- both are
    accepted. A sheet that names no delivery owes no map and passes --
    the G2 tag grammar owns that refusal. This is the amended G1 gate:
    the map, not a ban.
    """
    named = _deliveries_of(deliveries)
    missing = missing_delivery_verbs(text, named)
    if missing:
        names = "/".join(sorted(named))
        raise MusicStyleError(
            "NO_DELIVERY_MAP",
            "%r: style text for a %s sheet carries no delivery map (%s "
            "missing): G1 amended" % (style_id, names, " and ".join(missing)))
    return text


def pattern_contradicts(word, tags, deliveries):
    """True when one contradicting tag word is present and the sheet uses
    that delivery."""
    delivery = "spoken" if word == "spoken word" else word
    return bool(re.search(r"\b%s\b" % re.escape(word), tags)
                and delivery in _deliveries_of(deliveries))


def assert_no_contradiction(negative_tags, sheet_text):
    """Raise MusicStyleError(NEGATIVE_TAG_CONTRADICTION) when negative tags
    ban a delivery the lyric sheet itself uses ("spoken word" or "rap"
    tags beside [Spoken ...] / [Rap ...] blocks). The reversed-G1 gate
    (review G6: never ban spoken/rap while the sheet has spoken blocks).
    A sheet that names no delivery contradicts nothing and passes.
    """
    if not isinstance(negative_tags, (list, tuple)):
        negative_tags = ()
    tags = " | ".join(str(t) for t in negative_tags).lower()
    deliveries = sheet_deliveries(sheet_text)
    conflicts = [word for word, _pattern in _CONTRADICTING_PATTERNS
                 if pattern_contradicts(word, tags, deliveries)]
    if conflicts:
        raise MusicStyleError(
            "NEGATIVE_TAG_CONTRADICTION",
            "negative tags ban %r while the lyric sheet carries %s blocks: "
            "the tags contradict the sheet (G1 amended)"
            % (", ".join(conflicts),
               "/".join(sorted("spoken" if c == "spoken word" else c
                               for c in conflicts))))
    return list(negative_tags)


#: Recommended Suno section tags for the arc, keyed by style. Advisory only:
#: the lyric writer owns line text, this owns the style field.
SECTION_HINTS = {
    "soul-ballad": "[Verse] slow and close, [Pre-Chorus] lift, "
                   "[Chorus] full voice, [Bridge] stripped back",
    "rnb-flow": "[Verse] rap, [Hook] sung r&b, [Verse] rap, [Hook] sung r&b",
    "soul-rise": "[Verse] slow soul, [Build] pressure, "
                 "[Chorus] upbeat groove, [Outro] hold the lift",
    "melodic-rap": "[Verse] rap, [Hook] sung melodic, [Verse] rap, "
                   "[Hook] sung melodic",
    "trap-rap": "[Verse] rap, [Hook] rap, [Verse] rap, [Hook] sung or rap",
    "pop-rap": "[Verse] rap, [Pre-Hook] clear space, [Chorus] sung pop hook",
}


def style_ids():
    """The three offered style ids, in the order the card lists them."""
    return tuple(STYLES)


def _style_key(style):
    """Normalize an id, a label, or a card option record to a style id."""
    if isinstance(style, dict):          # card option block {"value": ...}
        style = style.get("value", style.get("style_id"))
    if not isinstance(style, str) or not style.strip():
        raise MusicStyleError("BAD_STYLE",
                              "style must be a non-empty string, got %r"
                              % (style,))
    key = style.strip().lower()
    if key in STYLES or key in RECIPES:
        return key
    for sid, rec in list(STYLES.items()) + list(RECIPES.items()):
        if key == rec["label"].lower():
            return sid
    raise MusicStyleError("UNKNOWN_STYLE",
                          "not one of the three D18 styles or the S75-T20 "
                          "rap recipes: %r" % style)


def _length_key(length):
    """Normalize a length to the seconds key the offered menu uses."""
    if isinstance(length, dict):
        length = length.get("value", length.get("seconds"))
    if isinstance(length, bool):
        raise MusicStyleError("BAD_LENGTH", "length must not be a bool")
    if isinstance(length, (int, float)):
        secs = int(round(float(length)))
        if secs in OFFERED_LENGTHS_S:
            return secs
        raise MusicStyleError("UNKNOWN_LENGTH",
                              "length %r s is not one of the offered lengths "
                              "%s" % (length, list(OFFERED_LENGTHS_S)))
    if isinstance(length, str):
        key = length.strip().lower().replace(" ", "").replace("-", "")
        if key in LENGTH_ALIASES:
            return LENGTH_ALIASES[key]
        raise MusicStyleError("UNKNOWN_LENGTH",
                              "length %r is not one of the offered lengths"
                              % length)
    raise MusicStyleError("BAD_LENGTH",
                          "length must be seconds or an id, got %r"
                          % (type(length).__name__,))


def style(style_id):
    """Full record for one style or rap recipe. Raises on an unknown id."""
    sid = _style_key(style_id)
    if sid in RECIPES:
        return style_prompt_record(sid)
    return dict(STYLES[sid])


def style_prompt_record(style_id):
    """A recipe exposed in the same shape as a STYLES menu record."""
    rec = RECIPES[_style_key(style_id)]
    return {
        "style_id": rec["style_id"],
        "label": rec["label"],
        "sound": rec["description"],
        "description": rec["description"],
        "share_rule": _SHARE_RULE,
        "deliveries": rec["deliveries"],
        "explicit_lyrics": rec["explicit_lyrics"],
        "recipe_revision": rec["recipe_revision"],
        "notes": (SOURCE_S75_T20 + "; rap counts as spoken delivery; "
                  "client references are display only"),
        "suno_style_prompt": _compile_traits(rec["production_traits"]),
    }


def style_prompt(style_id, sung=None, sheet_text=None):
    """Suno style-field text for one style or rap recipe (id or label).

    Contract consumed by core/style_defaults (V2B-AUDIO-U5): returns a
    non-empty str, raises only on an unknown style id.

    G1 amended (owner order 2026-10-08 11:50, part G, review G6): every
    rendered prompt carries the DELIVERY MAP -- one sentence naming, from
    the sheet, which lines Suno SINGS and which it SPEAKS ("The lead
    SPEAKS the lines tagged Spoken ... SINGS the lines tagged Sung"; RAPS
    joins them for a sheet with rap blocks). sheet_text builds the map
    from the sheet's own tags; without a sheet the style's own deliveries
    are used, so a default prompt never ships unmapped. ``sung`` is
    accepted and ignored: the earlier 11:35 ban on spoken-word wording in
    the style text is REVERSED by this order.

    S75-T20: a rap recipe's base text is compiled from production_traits
    only, so its display-only client references can never be serialized.
    The three D18 prompt strings stay byte-for-byte unchanged.
    """
    sid = _style_key(style_id)
    if sid in RECIPES:
        text = _compile_traits(RECIPES[sid]["production_traits"])
    else:
        text = STYLES[sid]["suno_style_prompt"]
    deliveries = sheet_deliveries(sheet_text) if sheet_text else set()
    if not deliveries:
        deliveries = set(_record(sid)["deliveries"])
    if not has_delivery_map(text, deliveries):
        # U15d (design 4.2): the base text ends with a PERIOD before the map is
        # appended. Without it "no distortion" ran into "The lead" and the style
        # read "no distortion The lead SPEAKS ...".
        text = "%s. %s" % (text.rstrip(".,"), _map_sentence(deliveries))
    return assert_delivery_map(sid, text, deliveries)


def section_hint(style_id):
    """Advisory Suno section-tag string for one style."""
    return SECTION_HINTS[_style_key(style_id)]


def d15_range(length):
    """The owner's D15 spoken-share band for one length: (floor, cap).

    Since the retarget the band is ONE range for every offered length --
    asking by length is kept only so existing callers keep working.
    """
    _length_key(length)
    return (SPOKEN_SHARE_MIN, SPOKEN_SHARE_MAX)


def spoken_target(style_id, length):
    """Spoken-share target for one style at one length.

    target is the point the song brief aims at (22.5% of runtime); floor/cap
    are the redo edges (12.5%..32.5%) and they are identical for every style
    and every length. Rap counts toward the target as spoken-style delivery.

    The earlier per-length target table and the earlier per-style upper end
    are retired: there is one target now.
    """
    sid = _style_key(style_id)
    secs = _length_key(length)
    return {
        "style_id": sid,
        "label": _record(sid)["label"],
        "length_seconds": secs,
        "d15_min": SPOKEN_SHARE_MIN,
        "d15_max": SPOKEN_SHARE_MAX,
        "target": SPOKEN_SHARE_TARGET,
        "target_mode": "d15",
        "target_note": ("target %g%% of runtime; rap counts as spoken-style"
                        % (SPOKEN_SHARE_TARGET * 100.0)),
        "floor": SPOKEN_SHARE_MIN,
        "cap": SPOKEN_SHARE_MAX,
        "first_sung_target_pct": FIRST_SUNG_TARGET_PCT,
        "rap_counts_as_spoken": True,
        "source": "%s; %s" % (SOURCE_D18, SOURCE_D15),
    }


def spoken_targets(style_id=None):
    """The D15 share-target table: every offered length for one style, or
    every style x length pair when style_id is None. Every cell is the same
    band -- the table is shape, not a per-length rule."""
    sids = [_style_key(style_id)] if style_id is not None else list(STYLES)
    out = {}
    for sid in sids:
        out[sid] = {str(secs): spoken_target(sid, secs)
                    for secs in OFFERED_LENGTHS_S}
    return out


def _segment_seconds(seg):
    """Seconds one timing segment covers. Accepts seconds or start/end."""
    if not isinstance(seg, dict):
        raise MusicStyleError("BAD_SEGMENT",
                              "segment must be a record, got %r"
                              % (type(seg).__name__,))
    delivery = seg.get("delivery")
    if not isinstance(delivery, str) or delivery.strip().lower() not in DELIVERIES:
        raise MusicStyleError("BAD_DELIVERY",
                              "delivery must be one of %s, got %r"
                              % (list(DELIVERIES), delivery))
    if "seconds" in seg:
        secs = seg["seconds"]
        if isinstance(secs, bool) or not isinstance(secs, (int, float)):
            raise MusicStyleError("BAD_SEGMENT",
                                  "seconds must be a number, got %r" % (secs,))
        secs = float(secs)
    elif "start" in seg and "end" in seg:
        st, en = seg["start"], seg["end"]
        if any(isinstance(v, bool) or not isinstance(v, (int, float))
               for v in (st, en)):
            raise MusicStyleError("BAD_SEGMENT", "start/end must be numbers")
        secs = float(en) - float(st)
    else:
        raise MusicStyleError("BAD_SEGMENT",
                              "segment needs seconds, or start and end")
    if secs < 0:
        raise MusicStyleError("BAD_SEGMENT", "segment seconds must be >= 0")
    return delivery.strip().lower(), secs


def segment_basis(segments):
    """G8: "measured" only when every segment is detector output carrying
    source="measured"; a list built from lyric/section labels is "planned"."""
    if not isinstance(segments, list) or not segments:
        return _SS.BASIS_PLANNED
    for seg in segments:
        if not isinstance(seg, dict) or seg.get("source") != _SS.MEASURED_SOURCE:
            return _SS.BASIS_PLANNED
    return _SS.BASIS_MEASURED

def measure_share(segments, basis=_SS.BASIS_MEASURED):
    """Spoken-style share of runtime from timing segments (G8: AUDIO, never
    labels).

    A segment is {"delivery": "spoken"|"rap"|"sung", "seconds": n} or
    {"delivery": ..., "start": a, "end": b}. Rap is spoken-style, so it is
    counted -- that is the rule that catches a rap-heavy R&B cut.

    basis="measured" (default) accepts only detector segments carrying
    source="measured"; label-built lists are refused with
    LABELS_NOT_MEASURED ("labels, not measured"). basis="planned" is the
    planner's own timeline and the result names itself planned.

    Returns spoken/rap/sung/total seconds and share as a fraction of total.
    Total 0 is refused rather than reported as 0%.
    """
    if not isinstance(segments, list) or not segments:
        raise MusicStyleError("BAD_SEGMENTS",
                              "segments must be a non-empty list")
    if basis == _SS.BASIS_MEASURED and segment_basis(segments) != _SS.BASIS_MEASURED:
        raise MusicStyleError(
            "LABELS_NOT_MEASURED",
            "measure_share: segments are built from lyric labels, not "
            "measured; feed the detector output (source=\"measured\", "
            "detector version and stem id), or pass basis=\"planned\"")
    seconds = dict.fromkeys(DELIVERIES, 0.0)
    for seg in segments:
        delivery, secs = _segment_seconds(seg)
        if not isfinite(secs):
            raise MusicStyleError("BAD_SEGMENT",
                                  "segment seconds must be finite, got %r"
                                  % (secs,))
        seconds[delivery] += secs
    spoken, rap, sung = (seconds[d] for d in ("spoken", "rap", "sung"))
    total = spoken + rap + sung
    if total <= 0:
        raise MusicStyleError("ZERO_RUNTIME",
                              "segments total 0 seconds; share undefined")
    spoken_style = sum(v for d, v in seconds.items()
                       if d in SPOKEN_STYLE_DELIVERIES)
    return {
        "spoken_seconds": round(spoken, 6),
        "rap_seconds": round(rap, 6),
        "sung_seconds": round(sung, 6),
        "total_seconds": round(total, 6),
        "spoken_style_seconds": round(spoken_style, 6),
        "share": round(spoken_style / total, 6),
        "rap_counts_as_spoken": True,
        "basis": segment_basis(segments),
        "share_source": segment_basis(segments),
        "detector": (segments[0] or {}).get("detector"),
        "detector_version": (segments[0] or {}).get("detector_version"),
        "stem_id": (segments[0] or {}).get("stem_id"),
    }


def share_pct(share):
    """Human percent for a share fraction, rounded to one decimal."""
    return round(float(share) * 100.0, 1)


def check_share(style_id, length, share, segments=None, basis=_SS.BASIS_MEASURED):
    """Enforce the D15 band on one style at one length. Never raises on a
    share that is merely out of band -- that is a FAIL verdict, not an error.

    Returns {"verdict": PASS|FAIL, "share", "floor", "cap", "target",
             "reasons": [...]}. Raises MusicStyleError only for an unknown
    style/length or a malformed share, which are caller bugs.

    segments, when given, is measured first and its share is the one judged
    (rap included); share then must agree with it or the check fails closed.
    """
    target = spoken_target(style_id, length)
    if isinstance(share, bool) or not isinstance(share, (int, float)):
        raise MusicStyleError("BAD_SHARE",
                              "share must be a fraction 0..1, got %r"
                              % (type(share).__name__,))
    share = float(share)
    if not isfinite(share):
        raise MusicStyleError("BAD_SHARE", "share must be finite, got %r"
                              % (share,))
    measured = None
    if segments is not None:
        measured = measure_share(segments, basis)
        if abs(measured["share"] - share) > 1e-6:
            return {
                "verdict": "FAIL",
                "share": share,
                "measured_share": measured["share"],
                "floor": target["floor"],
                "cap": target["cap"],
                "target": target["target"],
                "style_id": target["style_id"],
                "length_seconds": target["length_seconds"],
                "reasons": ["share %s disagrees with the timing measurement "
                            "%s (rap included)" % (share, measured["share"])],
                "measurement": measured,
                "checker_version": TOOL_VERSION,
            }
    reasons = []
    if share < 0.0 or share > 1.0:
        reasons.append("share %r is not a fraction in 0..1" % share)
    if share < target["floor"]:
        reasons.append("spoken share %.1f%% below the D15 floor %g%%"
                       % (share_pct(share), share_pct(target["floor"])))
    if share > target["cap"]:
        if target["target_mode"] == "d15-upper":
            reasons.append("spoken share %.1f%% above the R&B cap %g%% "
                           "(rap counts as spoken-style delivery)"
                           % (share_pct(share), share_pct(target["cap"])))
        else:
            reasons.append("spoken share %.1f%% above the D15 cap %g%% "
                           "(target %g%%, rap counts as spoken-style "
                           "delivery)"
                           % (share_pct(share), share_pct(target["cap"]),
                              share_pct(target["target"])))
    target_met = target["d15_min"] <= share <= target["d15_max"]
    return {
        "verdict": "FAIL" if reasons else "PASS",
        "share": share,
        "share_pct": share_pct(share),
        "floor": target["floor"],
        "cap": target["cap"],
        "target": target["target"],
        "target_range": [target["d15_min"], target["d15_max"]],
        "target_met": target_met,
        "style_id": target["style_id"],
        "length_seconds": target["length_seconds"],
        "rap_counts_as_spoken": True,
        "reasons": reasons,
        "measurement": measured,
        "checker_version": TOOL_VERSION,
    }


def refusal(style_id, length, share, segments=None, basis=_SS.BASIS_MEASURED):
    """Compact refusal text for a FAILED share; empty string when it passes.

    Lets a caller refuse early with one readable sentence instead of
    re-deriving the reason list.
    """
    result = check_share(style_id, length, share, segments, basis)
    if result["verdict"] == "PASS":
        return ""
    return "REFUSED %s at %ss: %s" % (result["style_id"],
                                      result["length_seconds"],
                                      "; ".join(result["reasons"]))
