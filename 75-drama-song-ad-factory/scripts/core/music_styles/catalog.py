"""S75-T18: THE eighteen-style catalog (owner approvals 2026-10-24).

One canonical catalog of exactly eighteen separately selectable music styles:
the three originals (D18) plus the fifteen approved additions. stdlib only,
no network, no provider call, no spend.

Two hard invariants this module owns:

1. **The three originals are untouched.** Their display strings are the
   byte-exact owner strings from MUSIC-AND-VIDEO-UX.md section 2, and their
   recipes are the live records in ``music_styles.STYLES`` -- read by
   reference at call time, never copied here. ``music_styles.py`` is not
   edited by this unit, so its bytes and the three records stay identical.
2. **Display metadata is not provider data.** ``client_references`` (the
   recognition artists) exist for the client explanation only. Every
   compiled field is built from ``production_traits`` and the policy fields;
   no reference name, alias or phrase can reach a provider field from here
   (see the artist-free boundary test, and S75-T41 at the send boundary).

Scope boundary: this module supplies the catalog, its recipes and the
compiled guidance text. It does not call a provider, and it does not render
the final Suno style field (the existing adapter owns field limits and the
dry-style vocabulary gate; the recipe owners S75-T19..S75-T22 and the
outgoing guard S75-T41 consume these traits). ``provider_hint()`` is that
compiled guidance: deterministic, trait-only text safe to hand to payload
assembly.
"""
from __future__ import annotations

import os
import re
import sys
import unicodedata

_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE = os.path.dirname(_HERE)
for _p in (_HERE, _CORE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

#: The original-records module, loaded BY FILE PATH (the same pattern
#: core/music_styles/music_styles.py uses for duration_registry). A plain
#: `import music_styles` is ambiguous: with core/ first on sys.path it resolves
#: to the package __init__, which does not export the private delivery-map
#: helpers this module reads. The leaf imports nothing itself, so a file-path
#: load is safe in every import order.
def _load_music_styles_leaf():
    import importlib.util
    leaf = os.path.join(_HERE, "music_styles.py")
    spec = importlib.util.spec_from_file_location(
        "_catalog_music_styles_leaf", leaf)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_MS = _load_music_styles_leaf()

TOOL_NAME = "music_style_catalog"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.music-style-catalog/v1"

#: The catalog contract revision. Bump on any trait change; the stable ids
#: below are frozen for this change (MUSIC-AND-VIDEO-UX.md section 2).
CATALOG_REVISION = "2026-10-24.1"
RECIPE_REVISION = "1"

#: Exactly eighteen. A nineteenth is refused, never quietly appended.
MAX_STYLES = 18

#: Frozen order. Index 0..2 are the D18 originals, which is also the order of
#: the old three-item menu -- an old run's numeric answer (1/2/3) still lands
#: on the same style. Never reorder; append-only is not allowed either.
STYLE_IDS = (
    "soul-ballad",
    "rnb-flow",
    "soul-rise",
    "acoustic-pop",
    "folk-storytelling",
    "country-pop",
    "melodic-rap",
    "trap-rap",
    "pop-rap",
    "pop-rock",
    "reggaeton",
    "cinematic-orchestral-song",
    "musical-theater",
    "contemporary-gospel",
    "urban-gospel",
    "alternative-rnb",
    "afro-soul",
    "country-rap",
)
ORIGINAL_STYLE_IDS = STYLE_IDS[:3]
ADDED_STYLE_IDS = STYLE_IDS[3:]

if len(STYLE_IDS) != MAX_STYLES or len(set(STYLE_IDS)) != MAX_STYLES:
    raise ImportError("catalog must hold exactly %d unique style ids"
                      % MAX_STYLES)

#: The byte-exact owner client descriptions for the originals. Compared with
#: bytes, including case and punctuation (SPEC.md "Choices that must survive
#: unchanged"; MUSIC-AND-VIDEO-UX.md section 2).
ORIGINAL_DESCRIPTIONS = {
    "soul-ballad":
        "slow, heartfelt singing; builds to a big emotional chorus.",
    "rnb-flow":
        "rhythmic rap verses, then a smooth sung hook you remember.",
    "soul-rise":
        "starts slow and sad, then lifts into an upbeat, hopeful groove.",
}

#: The six offered durations, from THE canonical registry (never a new copy).
DURATIONS_S = _MS.OFFERED_LENGTHS_S

#: Policy values shared by the whole catalog; a style never changes a client's
#: elected language, voice, accent or explicitness, and never invents facts.
PRESERVE_LANGUAGE = ("preserve the client's selected language exactly; "
                     "the style never switches, translates or infers one")
PRESERVE_EXPLICITNESS = ("preserve the client's selected explicitness "
                         "exactly; the style never adds profanity")
PRESERVE_VOICE = ("preserve the client's selected vocal gender, accent and "
                  "approved route exactly")
NO_INVENTED_FACTS = ("use only approved story facts; never invent a real "
                     "client's history, faith, testimony or biography")
VOCAL_SONG = "vocal song with full original lyrics; never an instrumental"
DURATION_POLICY = ("the one canonical duration registry: 60/90/120/180/300/"
                   "600 s; word fit per recipe, no unnatural speed-up")

#: Trait keys every record must carry (MUSIC-AND-VIDEO-UX.md section 3).
TRAIT_FIELDS = (
    "musical_identity",
    "instrumentation",
    "avoid_instrumentation",
    "tempo_bpm",
    "meter",
    "vocal_delivery",
    "energy_map",
    "hook_guidance",
    "delivery_constraints",
    "example",
    "negative_constraints",
)

#: Record fields every catalog entry must carry.
RECORD_FIELDS = (
    "style_id", "label", "description", "client_references",
    "recipe_revision", "deliveries", "production_traits",
    "language_policy", "explicitness_policy", "voice_policy",
    "fact_policy", "vocal_song", "durations_s", "section_hint",
)


class CatalogError(Exception):
    """Unknown style, malformed record, or a full catalog."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def _t(identity, instrumentation, avoid, tempo, meter, vocal, energy, hook,
       delivery, example, negative):
    """One production_traits record, positional-free: keyword clarity."""
    return {
        "musical_identity": identity,
        "instrumentation": tuple(instrumentation),
        "avoid_instrumentation": tuple(avoid),
        "tempo_bpm": (int(tempo[0]), int(tempo[1])),
        "meter": meter,
        "vocal_delivery": vocal,
        "energy_map": energy,
        "hook_guidance": hook,
        "delivery_constraints": delivery,
        "example": example,
        "negative_constraints": tuple(negative),
    }


# ---------------------------------------------------------------------------
# The fifteen additions. The three originals are built further down from the
# live music_styles records, never re-declared.
# ---------------------------------------------------------------------------

_ADDED = {
    "acoustic-pop": {
        "label": "Acoustic Pop",
        "description": ("warm acoustic guitar, clear storytelling, and a "
                        "catchy sung chorus."),
        "client_references": ("Ed Sheeran", "Jason Mraz"),
        "deliveries": ("spoken", "sung"),
        "section_hint": ("[Verse] close conversational, [Chorus] warm open, "
                         "[Bridge] guitar under the turn"),
        "production_traits": _t(
            "warm acoustic pop built on fingerpicked steel-string guitar",
            ("fingerpicked steel-string acoustic guitar",
             "warm round bass", "hand percussion", "restrained kick and snare",
             "small piano or vocal harmony only when the story opens"),
            ("wall of electric guitars", "orchestral trailer percussion",
             "constant trap-hat pattern", "generic synthetic pop bed"),
            (80, 112), "4/4 with a relaxed pocket",
            "close, conversational and melodic lead; crisp words; modest "
            "embellishment",
            "exposed spoken consequence over a small guitar figure; clearer "
            "strum and bass when action is needed; open chorus after the "
            "specific decision",
            "compact repeated melodic phrase that can carry the emotional "
            "change; last return supports the one call to action",
            "spoken opener is plain natural speech; sung blocks genuinely "
            "sing; no machine-gun delivery to reach a duration",
            "an owner speaks one dry line about a closed shop, then warm "
            "strums support the decision to ask for help",
            ("no borrowed melody", "no forced accent", "no invented owner "
             "fact", "no buried words under a big mix"),
        ),
    },
    "folk-storytelling": {
        "label": "Folk Storytelling",
        "description": ("intimate, detail-rich storytelling over simple "
                        "acoustic instruments."),
        "client_references": ("Tracy Chapman", "Bob Dylan"),
        "deliveries": ("spoken", "sung"),
        "section_hint": ("[Verse] concrete detail, [Refrain] changing meaning, "
                         "[Bridge] reduced accompaniment"),
        "production_traits": _t(
            "spare acoustic narrative folk with a direct unvarnished vocal",
            ("spare picked acoustic guitar", "optional upright bass",
             "light shaker", "small harmonica or mandolin answer"),
            ("polished stadium-pop drop", "trap rolls", "dense choir",
             "dense layered production"),
            (68, 100), "4/4, or a deliberate narrative 6/8 when the line "
            "rhythm supports it",
            "direct unvarnished lead; character-specific language carries the "
            "weight; no imitation of a singer's rasp or phrasing",
            "verse-led detail accumulates; silence or reduced accompaniment "
            "marks the turn; a modest harmony or bass entrance makes the "
            "change audible",
            "short recurring refrain whose meaning changes as choices "
            "accumulate; no forced big chorus every few lines",
            "spoken passages are deliberate narration; sung story verses and "
            "refrain are tagged; complete breaths for longer lines",
            "describe the flour on a returned apron and an unopened letter; "
            "the final refrain changes when the letter is read",
            ("no copied rasp, accent or phrasing", "no invented detail as "
             "owner fact", "no filler adjective lists for longer cuts"),
        ),
    },
    "country-pop": {
        "label": "Country Pop",
        "description": ("plainspoken country storytelling with a polished, "
                        "memorable pop chorus."),
        "client_references": ("Shania Twain", "Carrie Underwood"),
        "deliveries": ("spoken", "sung"),
        "section_hint": ("[Verse] lived-in detail, [Pre-Chorus] pressure, "
                         "[Chorus] polished open, [Bridge] mistaken belief"),
        "production_traits": _t(
            "polished country pop with plainspoken narrative and a big sung "
            "chorus",
            ("acoustic rhythm guitar", "restrained clean electric guitar",
             "steady bass", "live-feeling drum kit",
             "tasteful fiddle or pedal steel as punctuation"),
            ("bluegrass virtuosity", "generic dance synth track",
             "imposed regional accent or biography"),
            (88, 120), "4/4",
            "clear grounded narrative lead with a strong sung chorus and "
            "controlled country inflection only if the accepted voice allows",
            "concrete lived-in consequence in the opener; verse names "
            "behaviour and friction; pre-chorus tightens pressure; chorus "
            "opens after the character acts",
            "chorus repeats the emotional proposition, not multiple offers; "
            "one call to action across the last chorus",
            "brief intentional spoken dialogue; sung passages carry the "
            "melody under the existing delivery policy",
            "a shopkeeper turns the sign to closed and one honest call "
            "drives a drum-and-guitar lift",
            ("no imposed accent", "no invented owner fact", "no parody "
             "instrumentation", "no second slogan"),
        ),
    },
    "melodic-rap": {
        "label": "Melodic Rap",
        "description": ("emotional rap that moves between rhythmic lines and "
                        "a tuneful hook."),
        "client_references": ("Drake", "Rod Wave"),
        "deliveries": ("spoken", "rap", "sung"),
        "section_hint": ("[Verse] rap, [Hook] pitched melodic, "
                         "[Verse] rap, [Hook] pitched melodic"),
        "production_traits": _t(
            "emotional melodic rap alternating clear rap lines with a pitched "
            "melodic hook",
            ("restrained minor-key piano or guitar motif", "warm pad",
             "controlled 808 bass", "sparse kick and snare",
             "selective hi-hat movement"),
            ("spoken-only delivery", "renamed sung lines counted as rap",
             "copied vocal identity"),
            (70, 90), "4/4 felt half-time (one documented interpretation; "
            "never doubled actual speed)",
            "lead moves from clear rap to a pitched melodic hook; emotion "
            "carried through dynamics, not imitation",
            "consequence spoken and exposed; rap reveals tension and "
            "contradiction; thin the beat at the costly admission; widen "
            "harmony after the character chooses differently",
            "a melodic phrase is the emotional anchor and is required; never "
            "collapse into spoken rap",
            "separate rapid syllables from held notes in the timing plan; "
            "leave a breath before the hook; names and offer words stay "
            "readable",
            "the lead admits a missed call before the beat thickens; the "
            "sung line returns after they finally answer",
            ("no copied voice", "no invented voice or language", "no "
             "auto-tune masking of names", "no all-rap rewrite"),
        ),
    },
    "trap-rap": {
        "label": "Trap Rap",
        "description": ("punchy rap over deep bass and crisp, rolling "
                        "hi-hats, with a strong hook."),
        "client_references": ("Cardi B", "Future"),
        "deliveries": ("spoken", "rap", "sung"),
        "section_hint": ("[Verse] rap, [Hook] compact, [Verse] rap, "
                         "[Hook] compact"),
        "production_traits": _t(
            "punchy trap rap over controlled 808 low end and rolling hi-hats",
            ("controlled 808 bass", "punchy kick", "dry snare or clap",
             "crisp rolling hi-hats", "sparse dark synth, bell or piano "
             "motif"),
            ("automatic triplet density", "ad-libs masking names or offer "
             "words", "invented street biography"),
            (65, 85), "4/4 half-time (one explicit counted feel; 130-170 "
            "double-time only if documented)",
            "rhythmic, confident and intelligible lead; short emphatic "
            "phrases; purposeful rests",
            "bass and percussion articulate escalating pressure after the "
            "spoken opening; a beat drop underlines a choice; remove bass "
            "briefly for the admission",
            "compact hook with a melodic or rhythmic anchor compatible with "
            "the accepted spoken and rap budget",
            "rhythmic rap passages are tagged and counted under the existing "
            "spoken-style policy; the twelve-second spoken opener survives",
            "a counter goes silent as a payment is declined; a precise rap "
            "passage names the choice, then a hook carries the changed "
            "response",
            ("no profanity added", "no violence", "no invented biography",
             "no double-time all the way through"),
        ),
    },
    "pop-rap": {
        "label": "Pop Rap",
        "description": ("upbeat, easy-to-follow rap with a bright, catchy pop "
                        "hook."),
        "client_references": ("Nelly", "Flo Rida", "Puff Daddy"),
        "deliveries": ("spoken", "rap", "sung"),
        "section_hint": ("[Verse] rap, [Pre-Hook] clear space, [Hook] bright "
                         "sung, [Bridge] held"),
        "production_traits": _t(
            "upbeat accessible pop rap with a bright immediately memorable "
            "vocal hook",
            ("bright bass", "crisp hip-hop and pop drums",
             "buoyant piano or synth stabs", "clean accessible melodic "
             "chorus"),
            ("unbroken ominous trap texture", "substitute instrumental dance "
             "drop for the vocal hook", "crowded subdivisions"),
            (92, 118), "4/4",
            "rhythmic easy-to-follow rap lead; fewer crowded subdivisions "
            "than the trap recipe; hook clearly sung or deliberately "
            "chant-like as the approved script elects",
            "serious consequence in plainly articulated speech first; "
            "action-focused rap builds pressure; pre-hook clears space; "
            "bright hook arrives only when the choice earns it",
            "casual chant-like call and response only for declared cast; one "
            "call to action in the last chorus",
            "short rhyme units and a low-density hook; brand name not "
            "repeated as a substitute for story",
            "a failed handoff opens the scene; the rap follows two concrete "
            "attempts; the chorus lifts when the team makes a clear plan",
            ("no borrowed tune", "no unexplained extras", "no invented "
             "profanity", "no second call to action"),
        ),
    },
    "pop-rock": {
        "label": "Pop Rock",
        "description": ("driving guitars and drums with a big, singable "
                        "chorus."),
        "client_references": ("Maroon 5", "Paramore"),
        "deliveries": ("spoken", "sung"),
        "section_hint": ("[Verse] restrained pulse, [Chorus] full guitars, "
                         "[Bridge] reduced texture, [Chorus] resolved"),
        "production_traits": _t(
            "driving pop rock with live drums and a big singable chorus",
            ("rhythmic electric guitars", "defined electric bass",
             "live-feeling kick and snare kit", "tight acoustic support",
             "small keyboard layer when useful"),
            ("continuous maximal distortion that buries dialogue", "automatic "
             "EDM drop", "forced screaming", "imitation of a singer"),
            (100, 142), "4/4",
            "forward melodic vocal with controlled edge and clear words; "
            "verses leave headroom; choruses widen guitars and harmonies",
            "restrained guitar and pulse under the spoken consequence; "
            "tighter groove under the obstacle; a short stop or stripped bar "
            "marks the choice; full guitars open after visible action",
            "compact hook, not a second unrelated slogan; snare and guitar "
            "accents support syllables",
            "spoken consequence stays intelligible; held vowels reserved for "
            "the emotional refrain and call to action",
            "a rehearsal room empties after a failed pitch; a guitar mute "
            "marks the admission, then the band opens as the lead returns "
            "with a concrete plan",
            ("no screaming", "no new voice choice", "no buried words", "no "
             "second slogan"),
        ),
    },
    "reggaeton": {
        "label": "Reggaeton",
        "description": ("a rolling dembow groove, rhythmic vocals, and a "
                        "danceable chorus."),
        "client_references": ("Daddy Yankee", "Bad Bunny"),
        "deliveries": ("spoken", "sung"),
        "section_hint": ("[Verse] rhythmic, [Hook] open sung, "
                         "[Verse] rhythmic, [Hook] fuller percussion"),
        "production_traits": _t(
            "reggaeton built on a recognizable rolling dembow pattern",
            ("dembow kick and snare pattern", "rounded controlled sub bass",
             "syncopated percussion", "economical pluck, guitar or keyboard "
             "figures"),
            ("generic four-on-the-floor", "trap hats alone", "automatic "
             "language switch", "new slang"),
            (88, 105), "4/4",
            "alternates articulate rhythmic lines with a tuneful repeatable "
            "hook as the approved tags direct; words stay intelligible",
            "percussion low under the spoken consequence; groove grows as "
            "choices create movement; rhythm pulls back at the emotional "
            "admission; fuller percussion and an open sung hook for visible "
            "change",
            "repeatable tuneful hook; danciness never trivializes the "
            "consequence or turns every scene into a party",
            "preserve the client's selected language exactly; the genre never "
            "switches to Spanish, adds an accent or authorizes new slang",
            "a locked community-room door interrupts the rhythm; the "
            "character asks directly and the hook blooms as the group enters",
            ("never auto-selects Spanish", "no added accent", "no new slang",
             "no dembow replacement", "no party-every-scene"),
        ),
    },
    "cinematic-orchestral-song": {
        "label": "Cinematic Orchestral Song",
        "description": ("a dramatic song with sweeping strings and a powerful "
                        "film-style chorus. Keep the singing and spoken words "
                        "clear and easy to hear, even when the music gets big "
                        "and powerful."),
        "client_references": ("Adele - Skyfall",
                              "Celine Dion - My Heart Will Go On"),
        "deliveries": ("spoken", "sung"),
        "section_hint": ("[Verse] bare piano and low strings, [Build] "
                         "orchestral register, [Chorus] full film-style, "
                         "[Outro] resolve"),
        "production_traits": _t(
            "dramatic orchestral song with sweeping strings and a powerful "
            "film-style chorus; a lyrical song, never a score or trailer reel",
            ("expressive lead", "piano", "low strings",
             "violas and violins", "warm brass",
             "controlled cinematic percussion"),
            ("instrumental score output", "trailer sound-effects reel",
             "large percussion and brass on every line", "reproduced "
             "reference motifs"),
            (60, 88), "4/4, or a justified 6/8",
            "original full lyrics with clear diction and a strong earned "
            "melodic chorus; words stay audible through the large arrangement",
            "sparse piano and low strings frame the opening loss; harmony and "
            "register tighten under pressure; a brief reduction reveals the "
            "turn; full chorus after the consequential choice",
            "final refrain resolves the same emotional proposition and one "
            "call to action; story stays specific under the large sound",
            "keep the singing and spoken words clear and easy to hear, even "
            "when the music gets big and powerful",
            "an unsigned agreement sits on the table; the admission is "
            "nearly bare voice and strings rise only after the pen is "
            "offered back",
            ("never instrumental-only", "no copied motifs or arrangement "
             "sequence", "no singer imitation", "no long intro"),
        ),
    },
    "musical-theater": {
        "label": "Musical Theater",
        "description": ("character-driven singing and dialogue that build into "
                        "a dramatic stage-style payoff."),
        "client_references": ("Idina Menzel", "Cynthia Erivo"),
        "deliveries": ("spoken", "sung"),
        "section_hint": ("[Verse] want-driven, [Dialogue] spoken, "
                         "[Chorus] stage payoff, [Reprise] changed meaning"),
        "production_traits": _t(
            "character-driven theatrical storytelling with a dramatic "
            "stage-style payoff",
            ("piano-led theatrical orchestration", "strings", "woodwinds",
             "selective brass", "responsive rhythm section"),
            ("copied belt", "celebrity voice imitation", "ensemble beyond "
             "the selected route", "automatic inserted dialogue"),
            (72, 132), "4/4 with supported rubato or planned scene-linked "
            "tempo changes",
            "character-specific articulate intentional lead; characters sing "
            "because the immediate want makes the moment larger than speech",
            "spoken consequence opens; want-driven verse and obstacle "
            "response; short motif whose meaning changes at the emotional "
            "choice; orchestra follows action with a pause or harmonic pivot",
            "earned final payoff; dialogue and reprises only when the "
            "approved script already elected them; every voice maps to a "
            "declared cast id",
            "spoken interjections, sung phrases and held dramatic notes each "
            "get time; diction outranks vocal runs",
            "the lead sings a confident plan until one spoken question "
            "exposes the fear; the reprise changes after an honest choice",
            ("no copied belt", "no invented ensemble", "no sung stage "
             "directions", "no extra approval loop", "no multiple calls to "
             "action"),
        ),
    },
    "contemporary-gospel": {
        "label": "Contemporary Gospel",
        "description": ("faith-centered singing with piano, organ, and a "
                        "powerful choir that builds from testimony to an "
                        "uplifting chorus."),
        "client_references": ("Kirk Franklin",),
        "deliveries": ("spoken", "sung"),
        "section_hint": ("[Verse] restrained, [Chorus] choir lift, "
                         "[Verse] testimony, [Chorus] fuller"),
        "production_traits": _t(
            "contemporary gospel: faith-centered singing with piano and warm "
            "organ building from testimony to an uplifting chorus",
            ("piano", "warm organ", "live-feeling bass and drum section",
             "tasteful orchestral support", "expressive choir supporting the "
             "lead"),
            ("generic inspirational pop relabel", "choir drowning the words",
             "forced excess on every line", "invented church-service "
             "structure"),
            (68, 100), "deliberate 4/4 or 6/8 gospel feel",
            "clear-conviction lead; choir answers and harmony build the "
            "testimony; words stay easy to hear",
            "restrained under the spoken consequence; the lead's need and "
            "chosen action create the testimony; piano, organ and choir build "
            "toward an earned statement already grounded in the approved "
            "narrative",
            "larger final refrain only if duration and story permit; a choir "
            "response may deepen meaning, never replace it",
            "the approved text stays explicitly faith-centered; budget held "
            "notes, choir replies and breaths separately so protected words "
            "remain complete",
            "a character names the consequence in plain speech; after "
            "choosing to seek help, piano and choir support the "
            "faith-centered refrain already in the approved fiction",
            ("no invented client faith, history or testimony", "no "
             "unapproved sermon or conversion event", "no assumed "
             "real-client religion", "no melody borrowed"),
        ),
    },
    "urban-gospel": {
        "label": "Urban Gospel",
        "description": ("faith-centered singing with R&B and hip-hop grooves, "
                        "choir responses, and a memorable gospel hook."),
        "client_references": ("Kirk Franklin",),
        "deliveries": ("spoken", "rap", "sung"),
        "section_hint": ("[Verse] rhythmic, [Chorus] choir response, "
                         "[Verse] rhythmic, [Hook] gospel hook"),
        "production_traits": _t(
            "urban gospel: faith-centered singing over R&B and hip-hop "
            "grooves with rhythmically responsive choir answers",
            ("defined R&B and hip-hop drum pocket", "deep controlled bass",
             "Rhodes or piano", "selective organ or synth texture",
             "responsive choir harmonies"),
            ("ordinary secular R&B copy relabelled gospel", "invented church "
             "affiliation", "automatic slang", "stereotype"),
            (78, 110), "4/4, with an optional documented half-time feel",
            "lead may use rhythmic speech or rap passages and sung gospel "
            "hooks only as the approved delivery map allows; hook "
            "unmistakably vocal",
            "sparse groove leaves the spoken consequence easy to hear; "
            "rhythmic verses trace pressure and choice; choir response and "
            "sung hook grow after the emotional turn; brief reduction at the "
            "costly admission",
            "memorable vocal gospel hook; choir answers only after the "
            "choice is made; no stacking lead, rap and choir over critical "
            "words",
            "every story responder maps to the full cast; non-diegetic "
            "backing is identified as such; preserve language, vocal gender, "
            "accent and explicitness",
            "a clear rhythmic admission moves into a faith-centered hook; "
            "the choir answers only after the choice is made",
            ("no invented beliefs or testimony", "no secular copy relabel",
             "no added slang or accent", "no assumed real-client religion"),
        ),
    },
    "alternative-rnb": {
        "label": "Alternative R&B",
        "description": ("intimate, spacious R&B with inventive textures, "
                        "flexible grooves, and an expressive vocal."),
        "client_references": ("Tems",),
        "deliveries": ("spoken", "sung"),
        "section_hint": ("[Verse] textural, [Hook] understated, "
                         "[Bridge] harmonic friction, [Hook] warmer"),
        "production_traits": _t(
            "intimate open-textured alternative R&B with inventive structure "
            "and a flexible pocket",
            ("spacious R&B harmony", "restrained bass line",
             "dry or unusual percussion", "negative space",
             "atmospheric guitar, keyboard or synth textures"),
            ("mandatory sadness or slow tempo", "whispered formless meander",
             "instrumental meander replacing cause and effect"),
            (68, 112), "4/4, with a syncopated or flexible pocket when the "
            "words support it",
            "expressive close lead with purposeful rests, original melodic "
            "shapes and optional layered harmonies that keep words easy to "
            "hear",
            "small textural gesture underscores the consequence before the "
            "groove emerges; space and harmonic friction expose "
            "contradiction; a clear change in harmony, register or rhythmic "
            "density follows the consequential choice",
            "hook may be understated but is recognizable and expresses the "
            "earned change; nonstandard form allowed when coherent",
            "negative space counts as intentional time; leave room around "
            "important names and breath-driven phrasing",
            "an unanswered phone rings into a sparse beat; after the lead "
            "answers a warmer harmony changes the returning melodic phrase",
            ("not automatically sad or slow", "no invented language or "
             "accent", "no route change", "no meander without the call to "
             "action"),
        ),
    },
    "afro-soul": {
        "label": "Afro-Soul",
        "description": ("soulful vocals over warm, organic instruments and "
                        "interlocking African-influenced rhythms."),
        "client_references": ("Tems",),
        "deliveries": ("spoken", "sung"),
        "section_hint": ("[Verse] light interlock, [Chorus] warm open, "
                         "[Bridge] reduced percussion, [Chorus] fuller "
                         "interlock"),
        "production_traits": _t(
            "warm organic Afro-soul with soulful vocals over interlocking "
            "African-influenced rhythms",
            ("rounded bass", "acoustic or electric guitar figures",
             "keys", "interlocking hand-percussion parts with a gentle sway"),
            ("vague continental sound effect", "automatic dance-pop",
             "full club production", "dembow track", "fabricated dialect or "
             "ethnic identity"),
            (80, 108), "4/4 pulse with syncopated interlocking subdivisions",
            "soulful melodic clear lead; controlled call and response or "
            "harmony only if the approved material calls for it",
            "spoken consequence close over a light organic figure; "
            "complementary percussion as pressure grows; reduce for an "
            "intimate realization; restore warmer interlock and vocal lift "
            "after the consequential choice",
            "refrain gains warmth through action already in the scene plan, "
            "not through unrelated celebration",
            "place stresses against the interlock with room for vowels and "
            "consonants; keep vocals clear over percussion",
            "a returned apron lies by the door; the lead speaks the cost "
            "over guitar and a warm percussion weave grows when they choose "
            "to return",
            ("not automatically dance-pop or slow-sad", "no fabricated "
             "dialect", "no invented cultural claim", "no chanting filler"),
        ),
    },
    "country-rap": {
        "label": "Country Rap",
        "description": ("Country storytelling meets rock power and hip-hop "
                        "rhythm. Gritty, soulful singing and rhythmic rap "
                        "verses build into a big, emotional chorus. Think "
                        "acoustic guitars, heavy drums, deep bass and "
                        "electric-guitar lift, with stories about struggle, "
                        "regret, resilience and redemption."),
        "client_references": ("Jelly Roll",),
        "deliveries": ("spoken", "rap", "sung"),
        "section_hint": ("[Verse] rap, [Chorus] fully sung, "
                         "[Verse] rap, [Chorus] electric lift"),
        "production_traits": _t(
            "country rap: country storytelling over rock power and hip-hop "
            "rhythm with a fully sung chorus",
            ("picked acoustic or understated country guitar figure",
             "hip-hop drums with a heavy controlled kick and snare",
             "deep bass", "defined electric-guitar lift at the earned turn"),
            ("forced accent or voice clone", "copied melody or biography",
             "doubled actual speed from misread notation", "invented "
             "addiction or incarceration"),
            (74, 100), "4/4, with a documented half-time pocket or 148-200 "
            "counted double-time only when natural words support it",
            "alternates clear conversational rap verses with gritty soulful "
            "singing in a strongly sung memorable chorus; grit is expressive "
            "texture, not obscurity",
            "restrained opening under the twelve spoken seconds; bass and "
            "drums grow as pressure rises; regret or admission strips back; "
            "electric guitars and a fully sung chorus deliver the payoff "
            "after changed action",
            "chorus carries the earned change; keep rap phrases "
            "breath-sized; budget the guitar lift and held notes",
            "struggle, regret, resilience and redemption are available "
            "directions, not assumed real client facts; theme comes from the "
            "approved cast, world and causal scene plan",
            "returned keys land on the counter; the lead names the "
            "consequence, raps one honest decision, and earns the "
            "electric-guitar chorus by following through",
            ("no artist name or imitation", "no new explicitness", "no "
             "invented client history", "no fixed verse or chorus count over "
             "the selected duration"),
        ),
    },
}

if tuple(_ADDED) != ADDED_STYLE_IDS:
    raise ImportError("added style ids drifted from the frozen order: %r"
                      % (tuple(_ADDED),))


# ---------------------------------------------------------------------------
# The originals: label, id and recipe read from the live music_styles record.
# ---------------------------------------------------------------------------

_ORIGINAL_RECIPES = {
    "soul-ballad": _t(
        "slow soul ballad with heartfelt singing building to a big emotional "
        "chorus",
        ("warm felt piano", "rounded bass foundation",
         "brushed drums entering at the first emotional opening",
         "restrained string pad"),
        ("distorted guitars", "trap-hat bed", "unearned triumphant first "
         "chorus"),
        (62, 68), "4/4",
        "close dry lead moving from vulnerable near-conversational verses to "
        "a full-voiced chorus with controlled original melismatic movement; "
        "business words stay intelligible",
        "sparse piano under consequence; bass and brush tension under "
        "obstacle; pull back for the consequential choice; widen harmony and "
        "drums for the earned change",
        "one memorable sung refrain after its meaning exists; short cuts let "
        "one chorus carry the payoff; long cuts revisit it with changed "
        "meaning",
        "after the mandatory spoken opening the musical body is fully sung "
        "and grows from intimate singing to the emotional chorus; no added "
        "rap and no forced extra spoken passages",
        "the empty chair is the first image; the lead speaks the cost, then "
        "sings an original refrain about asking for help",
        ("no copied voice", "no invented owner fact", "no extra rap verses"),
    ),
    "rnb-flow": _t(
        "contemporary R&B with rhythmic rap verses and a smooth sung hook",
        ("contemporary R&B harmony", "Rhodes chord stabs",
         "deep controlled sub bass", "crisp programmed drums",
         "tight hi-hats", "selective bright synth plucks"),
        ("chant replacing the hook", "all verses turned into a ballad",
         "ad-libs over names or offer words"),
        (84, 94), "4/4",
        "lead raps designated passages with clear metered diction; hook is "
        "recognizably sung with sustained notes; sparse ad-libs outside "
        "names, claim language and the call to action",
        "tight specific rap carries the obstacle and choice; harmonic space "
        "opens for the emotional hook; strip drums for the wound; return "
        "with a controlled bass and drum lift after the decision",
        "sung hook is the payoff; short call and response only for declared "
        "cast ids",
        "rap blocks count under the existing delivery policy; no renamed tag "
        "evades it; spoken opener is articulate over a low bed with no stray "
        "vocal pad",
        "a delivery receipt lands on an empty counter; the rap names the "
        "consequence and the sung hook earns a shared next step",
        ("no chant hook", "no ballad rewrite", "no invented voice"),
    ),
    "soul-rise": _t(
        "two-part soul arc: brooding slow soul lifting into an upbeat hopeful "
        "groove at the story turn",
        ("brooding piano", "round bass",
         "percussion thickening at the lift", "claps",
         "warm horn accents from the turnaround"),
        ("unrelated track splicing", "celebration before the problem is felt",
         "silent removal of the promised energy arc"),
        (62, 112), "4/4",
        "close lead rising in register and confidence; voice identity "
        "preserved; fully sung body after the spoken opening",
        "sparse spoken consequence and restrained sung struggle precede the "
        "decisive choice; the groove lift lands on the actual change beat, "
        "never an arbitrary percentage; refrain starts unresolved and "
        "returns hopeful after visible action",
        "one refrain whose meaning turns from unresolved to hopeful; budget "
        "both sections and the transition and leave breaths at the turn",
        "after the mandatory spoken opening the musical body is fully sung "
        "and melancholy singing changes into an earned upbeat hopeful groove; "
        "no rap and no arbitrary dialogue",
        "the lead stops hiding an unanswered request; only when they hand it "
        "over do claps and horns enter",
        ("no spliced tracks", "no premature celebration", "no removed "
         "energy arc"),
    ),
}


def _original_record(style_id):
    """One original catalog record, built from the live music_styles record.

    The label and the recipe are the same objects the current file holds, so
    they cannot drift; only the client description comes from the owner spec,
    and it is compared byte-for-byte by the tests.
    """
    live = _MS.STYLES[style_id]
    return {
        "style_id": style_id,
        "label": live["label"],
        "description": ORIGINAL_DESCRIPTIONS[style_id],
        "client_references": _ORIGINAL_REFERENCES[style_id],
        "recipe_revision": RECIPE_REVISION,
        "deliveries": tuple(live["deliveries"]),
        "production_traits": _ORIGINAL_RECIPES[style_id],
        "language_policy": PRESERVE_LANGUAGE,
        "explicitness_policy": PRESERVE_EXPLICITNESS,
        "voice_policy": PRESERVE_VOICE,
        "fact_policy": NO_INVENTED_FACTS,
        "vocal_song": VOCAL_SONG,
        "durations_s": DURATIONS_S,
        "section_hint": _MS.SECTION_HINTS[style_id],
        "original_recipe_field": "suno_style_prompt",
    }


_ORIGINAL_REFERENCES = {
    "soul-ballad": ("Luther Vandross", "Whitney Houston"),
    "rnb-flow": ("Lauryn Hill", "Missy Elliott"),
    "soul-rise": ("Andra Day", "Bill Withers"),
}


def _added_record(style_id):
    src = _ADDED[style_id]
    return {
        "style_id": style_id,
        "label": src["label"],
        "description": src["description"],
        "client_references": src["client_references"],
        "recipe_revision": RECIPE_REVISION,
        "deliveries": src["deliveries"],
        "production_traits": src["production_traits"],
        "language_policy": PRESERVE_LANGUAGE,
        "explicitness_policy": PRESERVE_EXPLICITNESS,
        "voice_policy": PRESERVE_VOICE,
        "fact_policy": NO_INVENTED_FACTS,
        "vocal_song": VOCAL_SONG,
        "durations_s": DURATIONS_S,
        "section_hint": src["section_hint"],
    }


CATALOG = {}
for _sid in STYLE_IDS:
    CATALOG[_sid] = (_original_record(_sid) if _sid in ORIGINAL_DESCRIPTIONS
                     else _added_record(_sid))

if tuple(CATALOG) != STYLE_IDS:
    raise ImportError("catalog order drifted")

def _norm(text):
    """Case-folded, accent- and punctuation-normalized form.

    S75-T41 needs the same normalization for the outgoing guard; it is kept
    here so the catalog and its tests agree on what "the same name" means.
    """
    if not isinstance(text, str):
        return ""
    folded = unicodedata.normalize("NFKD", text)
    folded = "".join(ch for ch in folded
                     if not unicodedata.combining(ch))
    return re.sub(r"[\s\W_]+", " ", folded).strip().casefold()


#: Label (lower-cased) -> stable id. Only unambiguous aliases: each label
#: names exactly one style.
_LABEL_INDEX = {_rec["label"].strip().lower(): _sid
                for _sid, _rec in CATALOG.items()}


def style_ids():
    """The eighteen stable ids, in the frozen order."""
    return STYLE_IDS


def added_style_ids():
    """The fifteen approved additions, in the frozen order."""
    return ADDED_STYLE_IDS


def style(style_id):
    """Full catalog record for one style id (a copy; the catalog is frozen)."""
    sid = _style_key(style_id)
    rec = dict(CATALOG[sid])
    rec["production_traits"] = dict(CATALOG[sid]["production_traits"])
    return rec


def _style_key(style):
    """Normalize an id, a label, or a card option record to a stable id.

    Numeric answers are NOT interpreted here: an old run's numeric answer is
    resolved by its own question snapshot (MUSIC-AND-VIDEO-UX.md section 2),
    never against this enlarged menu.
    """
    if isinstance(style, dict):
        style = style.get("value", style.get("style_id"))
    if not isinstance(style, str) or not style.strip():
        raise CatalogError("BAD_STYLE",
                           "style must be a non-empty string, got %r"
                           % (style,))
    key = style.strip().lower()
    if key in CATALOG:
        return key
    if key in _LABEL_INDEX:
        return _LABEL_INDEX[key]
    raise CatalogError("UNKNOWN_STYLE",
                       "not one of the eighteen catalog styles: %r" % style)


def label(style_id):
    return CATALOG[_style_key(style_id)]["label"]


def description(style_id):
    """The frozen client-facing description, byte-exact for the originals."""
    return CATALOG[_style_key(style_id)]["description"]


def client_references(style_id):
    """Recognition artists. DISPLAY ONLY: never printable to a provider."""
    return CATALOG[_style_key(style_id)]["client_references"]


def production_traits(style_id):
    """The executable guidance: structured, provider-safe, reference-free."""
    return dict(CATALOG[_style_key(style_id)]["production_traits"])


def section_hint(style_id):
    return CATALOG[_style_key(style_id)]["section_hint"]


def delivery_map(style_id, sheet_text=None):
    """The G1 delivery-map sentence, from the sheet or the style's defaults."""
    sid = _style_key(style_id)
    if sheet_text:
        return _MS.delivery_map(sheet_text)
    return _MS._map_sentence(set(CATALOG[sid]["deliveries"]))


def provider_hint(style_id, sheet_text=None):
    """Compiled guidance text: traits only, never a client reference.

    The three originals return the live ``suno_style_prompt`` unchanged (plus
    the delivery map), so their recipe bytes are the current file's. The
    fifteen additions render from ``production_traits`` in a fixed order.
    """
    sid = _style_key(style_id)
    if sid in ORIGINAL_STYLE_IDS:
        return _MS.style_prompt(sid, sheet_text=sheet_text)
    tr = CATALOG[sid]["production_traits"]
    parts = [
        tr["musical_identity"],
        ", ".join(tr["instrumentation"]),
        "%d-%d bpm" % tr["tempo_bpm"],
        tr["meter"],
        tr["vocal_delivery"],
        tr["hook_guidance"],
        "avoid " + ", ".join(tr["avoid_instrumentation"]),
        "dry close upfront vocal",
    ]
    text = ", ".join(parts)
    deliveries = (_MS.sheet_deliveries(sheet_text) if sheet_text
                  else set(CATALOG[sid]["deliveries"]))
    return _MS.assert_delivery_map(
        sid, "%s. %s" % (text.rstrip(".,"), _MS._map_sentence(deliveries)),
        deliveries)


def choice_rows():
    """The eighteen rows a choice surface renders: id, label, description."""
    return tuple({"style_id": sid,
                  "label": CATALOG[sid]["label"],
                  "description": CATALOG[sid]["description"]}
                 for sid in STYLE_IDS)


def register_style(record):
    """Refuse an eighteenth-plus style: the catalog is closed.

    Returns nothing; raises CatalogError(CATALOG_FULL) once the count is at
    MAX_STYLES, and CatalogError(DUPLICATE_STYLE) for a repeated id. A
    nineteenth style is never appended, aliased or coerced.
    """
    if not isinstance(record, dict):
        raise CatalogError("BAD_STYLE", "record must be a dict")
    sid = record.get("style_id")
    if not isinstance(sid, str) or not sid.strip():
        raise CatalogError("BAD_STYLE", "record needs a style_id")
    if sid.strip().lower() in CATALOG:
        raise CatalogError("DUPLICATE_STYLE",
                           "%r already in the catalog" % sid)
    raise CatalogError(
        "CATALOG_FULL",
        "the catalog holds exactly %d approved styles; %r is refused"
        % (MAX_STYLES, sid))


def validate_catalog():
    """Raise CatalogError on any malformed record; return the count.

    Checks: exactly MAX_STYLES unique ids and labels, every record field,
    every trait field non-empty, a positive tempo range, and no client
    reference leaking into the compiled traits or provider hint.
    """
    if len(CATALOG) != MAX_STYLES:
        raise CatalogError("BAD_CATALOG",
                           "catalog holds %d styles, not %d"
                           % (len(CATALOG), MAX_STYLES))
    if len({_norm(r["label"]) for r in CATALOG.values()}) != MAX_STYLES:
        raise CatalogError("BAD_CATALOG", "style labels are not unique")
    for sid, rec in CATALOG.items():
        missing = [f for f in RECORD_FIELDS if f not in rec]
        if missing:
            raise CatalogError("BAD_RECORD",
                               "%s is missing %s" % (sid, missing))
        for field in TRAIT_FIELDS:
            value = rec["production_traits"].get(field)
            if value is None or value == "" or value == ():
                raise CatalogError("BAD_TRAIT",
                                   "%s.%s is empty" % (sid, field))
        lo, hi = rec["production_traits"]["tempo_bpm"]
        if not (0 < lo < hi <= 300):
            raise CatalogError("BAD_TRAIT",
                               "%s tempo range %r is not positive" % (sid,
                                                                       (lo, hi)))
        if not rec["vocal_song"]:
            raise CatalogError("BAD_RECORD", "%s is not a vocal song" % sid)
        if rec["durations_s"] != (60, 90, 120, 180, 300, 600):
            raise CatalogError("BAD_RECORD",
                               "%s durations %r" % (sid, rec["durations_s"]))
        blob = repr(rec["production_traits"]).casefold()
        for ref in rec["client_references"]:
            if _norm(ref) and _norm(ref) in _norm(blob):
                raise CatalogError(
                    "REFERENCE_LEAK",
                    "%s: display-only reference %r reached provider traits"
                    % (sid, ref))
    return len(CATALOG)
