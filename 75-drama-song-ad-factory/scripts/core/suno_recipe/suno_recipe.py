"""The Suno song recipe v2 (replaces G12): the default for EVERY Suno style.

Built from the measured BSW passes (spoken opener of 3 words or fewer, a
wordless sung vocalise, hyphen-held vowels, about 65 words for 58 s) and the
cited research (Suno prompt research 09, Perplexity 10 and 11, 2026-10-08).
Only the Velvet Voiceover version keeps its own flow. stdlib only; no
network, no spend.

The rules (verbatim in SKILL.md):
  1. Spoken tags only in [Intro] and [Outro]; spoken is named at most once
     in the style text, and the style says the full band keeps playing
     under the spoken lines.
  2. Sung lines are short (5-6 syllables aimed, 8 at most), rhymed, with
     hyphen-held vowels; a wordless sung vocalise leads in.
  3. The hook is the payoff, never the opener (FU-HOOK-PLACEMENT, Trevor
     2026-10-09): it comes after the build-up the style's own structure
     calls for (a verse, plus a pre-chorus/build where the style and the
     length plan have one), the first hook measured at or after the story
     beat where its words become true. The hook is
     built from the client's own words and repeated by length.
  4. Each take's singing is measured, not taken from its labels.
Style text is 1000 characters or less. Negative tags never include
"spoken word". Trevor's dry close-vocal rule (no string pads, layered
vocals, choir or reverb) stays.
"""
from __future__ import annotations

import os
import re
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import ending_qc as _EQ         # noqa: E402
import length_formula as _LF    # noqa: E402
import music_styles as _MS      # noqa: E402
import prompt_limits as _PL     # noqa: E402
import prompt_templates as _PT  # noqa: E402
import spoken_share as _SS      # noqa: E402
import sung_hook as _SH         # noqa: E402
from sung_hook import hook_placement as _HP   # noqa: E402

TOOL_NAME = "suno_recipe"
TOOL_VERSION = "2.0.0"

RULES = (
    "Spoken tags only in [Intro] and [Outro]; spoken named once in the style text; the full band keeps playing under it.",
    "Sung lines are short, rhymed, with hyphen-held vowels, after a wordless sung vocalise.",
    "The hook is the payoff, never the opener: it comes after the build-up (a verse, plus a pre-chorus where the style has one), measured at or after the story beat where its words become true; the hook is the client's own words.",
    "Each take's singing is measured, not taken from its labels.",
)

#: The ONLY style id that skips the recipe: the spoken Google voiceover over
#: the song (core/voice_velvet_echo VELVET_ID). Keep this set to one id.
EXEMPT_STYLE_IDS = frozenset({"velvet_voiceover"})

#: Trevor 5/10 band: first real singing is due by 15% of runtime; within 5
#: points of runtime still passes, within 10 passes with a flag, past that fails.
FIRST_SING_TARGET = 0.15
ACCEPT_PTS, FLAG_PTS = 5, 10
SUNO_STYLE_FIELD_MAX = 1000          # Suno style field character limit
MIN_HOOK_REPEATS = 2
MAX_SUNG_LINE_SYLLABLES = 8
BAND_WORDING = "the full band keeps playing continuously under them"
#: U15d (design 4.2): the style lead, the cue strings and the gender words are
#: DATA now (references/prompt-templates/music/*.json and models/suno-v6.json),
#: never constants here. STYLE_LEAD was `female lead, ... slow tempo` for every
#: style, which contradicted the R&B Flow rap verses (file 18 E.2).
PRODUCT_SHARE_FLOOR_PCT, PRODUCT_SHARE_CAP_PCT = 10.0, 15.0
#: No-voice section tags: a tag only, NEVER a lyric line Suno could sing.
NO_VOICE_TAGS = ("instrumental", "break")
#: The villain/pain lyric guidance (U16) rides in the model block; read from
#: product_style_bible/bible.py VILLAIN_LYRIC_GUIDANCE when that tree has it.
VILLAIN_GUIDANCE_SOURCE = ("product_style_bible/bible.py VILLAIN_LYRIC_GUIDANCE "
                           "(U16 onb 8467e0354d3116eec980928cab7abaab8cef51ed, "
                           "999 c4787e2c13e71e3f7877d232aa7c80271f477adc)")
_MUSIC_CACHE, _MODEL_CACHE = {}, {}
#: Negative tags (research 09 + 10 + Trevor's dry rule). NEVER "spoken word".
NEGATIVE_TAGS = ("rap", "rapping", "choir", "reverb", "echo", "band dropout",
                 "acapella sections", "talk-singing", "monotone delivery")
REQUIRED_NEGATIVES = ("choir", "reverb", "echo")     # Trevor's dry rule
FORBIDDEN_NEGATIVES = ("spoken word", "spoken", "speech", "narration", "voiceover")
RAP_STYLE_IDS = frozenset({"rnb-flow"})              # rap IS this style: no rap negatives
#: KIE generate-music values measured/researched 2026-10-08.
KIE_PARAMS = {"model": "V6", "custom_mode": True, "instrumental": False,
              "style_weight": 0.75, "weirdness_constraint": 0.3, "variety": 0}
_SPOKEN_WORD_RE = re.compile(r"\b(spoken|speaks?|speaking|speech|talk\w*|narrat\w*)\b", re.I)


class RecipeError(ValueError):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def _words(text):
    return _SH.words(text)


# ---------------------------------------------------------------------------
# U15d (design 4.2-4.3, 8.8): every style text, cue and gender word is DATA.
#   references/prompt-templates/music/<style>.json  -> style_parts, cue_overrides,
#                                                      negative_tags, rap_allowed
#   references/prompt-templates/models/suno-v6.json -> cue_vocabulary, tag_grammar,
#                                                      kie_params, hook_formula
# Nothing below is a second copy of those files.

def music_block(style_id):
    """The music/<style>.json block for one style id. Fails closed, names path."""
    sid = str(style_id)
    if sid not in _MUSIC_CACHE:
        _MUSIC_CACHE[sid] = _PT.load("music", sid)
    return _MUSIC_CACHE[sid]


def model_block():
    """The models/suno-v6.json block."""
    if "suno-v6" not in _MODEL_CACHE:
        _MODEL_CACHE["suno-v6"] = _PT.load("model", "suno-v6")
    return _MODEL_CACHE["suno-v6"]


def vocal_gender_word(vocal_gender=None):
    """The {gender} slot from the brief. Never hard-coded female (U15d/U5).

    "f"/"female" and "m"/"male" map to the plain word; any other non-empty
    string is the brief's own wording (the sheet example uses "Warm female");
    None gives no gender word at all rather than a default one.
    """
    if vocal_gender is None:
        return ""
    if not isinstance(vocal_gender, str) or not vocal_gender.strip():
        raise RecipeError("BAD_VOCAL_GENDER",
                          "vocal_gender must be a non-empty string, got %r"
                          % (vocal_gender,))
    key = vocal_gender.strip().lower()
    return {"f": "female", "female": "female",
            "m": "male", "male": "male"}.get(key, vocal_gender.strip())


def base_prompt(style_id):
    """The style's own first part (data), WITHOUT the Suno-style-text wrapper."""
    return "%s." % str(music_block(style_id)["style_parts"][0]).rstrip(".")


#: The two fields the brief fills, which the model block documents in prose.
KIE_BRIEF_FIELDS = ("vocal_gender", "duration")


def kie_params():
    """The concrete KIE generate values, read from models/suno-v6.json.

    The model block carries prose for the two fields the brief fills
    (vocal_gender, duration); only those are dropped, so a value the data
    changes (model, weights, constraints) reaches the payload automatically.
    """
    block = model_block().get("kie_params") or {}
    out = {k: v for k, v in block.items() if k not in KIE_BRIEF_FIELDS}
    return out if isinstance(out.get("model"), str) else dict(KIE_PARAMS)


def cue_for(delivery, tag, style_id=None):
    """The cue string for one section, read from the data (design 4.3).

    music/<style>.json cue_overrides first ("sung:hook"), then the model
    block's cue_vocabulary; a section with no entry of its own falls back to
    that delivery's verse cue, so a cue is never invented in code.
    """
    vocab = model_block()["cue_vocabulary"].get(delivery) or {}
    key = str(tag).lower().split()[0]
    over = (music_block(style_id).get("cue_overrides") or {}) if style_id else {}
    # FU-RNBFLOW-SONG: a section with no cue of its own falls back to the
    # STYLE's verse cue first, so an upbeat style never inherits "slow".
    return (over.get("%s:%s" % (delivery, key)) or vocab.get(key)
            or over.get("%s:verse" % delivery) or vocab.get("verse") or "")


def syllables(line):
    """Rough syllable count; hyphen-held vowels (sma-a-all) count once."""
    n = 0
    for w in re.findall(r"[A-Za-z'-]+", str(line)):
        w = re.sub(r"(.)\1+", r"\1", w.replace("-", "").lower())
        if len(w) > 2 and w.endswith("e") and w[-2] not in "aeiouy":
            w = w[:-1]
        n += max(len(re.findall(r"[aeiouy]+", w)), 1)
    return n


def is_exempt(style_id):
    return style_id in EXEMPT_STYLE_IDS


def suno_style_ids():
    """Every style that must use the recipe (the music_styles menu)."""
    return tuple(_MS.style_ids())


def is_no_voice_tag(tag):
    """True for a section that has NO voice: a tag only, never a lyric line."""
    head = str(tag).lower()
    return any(word in head for word in NO_VOICE_TAGS)


def _tag(sec, style_id=None):
    d = sec["delivery"]
    if d is None or is_no_voice_tag(sec["tag"]):
        # no voice: a TAG ONLY, with its cue inside the tag, never a line
        return ("[%s: %s]" % (sec["tag"], sec["cue"])) if sec.get("cue") \
            else "[%s]" % sec["tag"]
    # A section may carry its own cue / vocalist label (a rap verse sung by
    # "Vocal B, male voice"); otherwise the cue is read from the data.
    note = sec.get("cue") or cue_for(d, sec["tag"], style_id)
    voice = sec.get("voice")
    if voice and note:
        note = "%s, %s" % (voice, note)
    return ("[%s (%s): %s]" % (sec["tag"], d, note)) if note else \
        "[%s (%s)]" % (sec["tag"], d)


def render_lyrics(sheet, style_id=None):
    """Lyric sheet text: spoken tags only Intro/Outro, ends with [End].

    A no-voice section renders as a TAG with no lyric line: a line under an
    instrumental tag would be SUNG by Suno (design 4.3).
    """
    out = []
    for s in sheet:
        if str(s["tag"]).strip().lower() == "end":
            continue                          # the terminator is appended once
        tag = _tag(s, style_id)
        if s.get("delivery") is None or is_no_voice_tag(s["tag"]):
            out.append(tag)
        else:
            out.append(tag + "\n" + "\n".join(s["lines"]))
    return "\n\n".join(out) + "\n\n[End]"


# ---- FU-U1: THE one tag grammar ------------------------------------------
# Plan 18-OPUS-SKILL75-FUTURE-PLAN 2.A (A1/A2): one parser owns the tag
# grammar so every gate measures the same sheet. Delivery words, matched at
# a word boundary on a punctuation-normalized tag, so "trap beat" is never
# read as rap and "spoken-word" still counts. The earliest delivery word in
# the tag wins; ties go rap -> spoken -> sung. Both bracket dialects parse
# here: [Name (sung|spoken|rap): note] and [Sung|Spoken|Rap - ...].
_DELIVERY_WORDS = (
    ("rap", ("rap", "raps", "rapped", "rapping")),
    ("spoken", ("spoken", "speak", "speaks", "speaking", "talk", "talks",
                "narrate", "narrated")),
    ("sung", ("sung", "sing", "sings", "singing")),
)
DELIVERIES = ("sung", "spoken", "rap")
INSTRUMENTAL = "instrumental"
_BRACKET_RE = re.compile(r"^\[([^\]]*)\]\s*$")
#: The recipe's own dialect: [Name (sung|spoken|rap): note]. The tag kept is
#: Name, so render_lyrics -> parse_lyrics round-trips.
_NAMED_TAG_RE = re.compile(r"^(.*?)\s*\((sung|spoken|rap)\)(?::[^\]]*)?$", re.I)


def parse_tag(tag):
    """The delivery a tag names: "sung" / "spoken" / "rap" / "instrumental",
    or None for a tag that names no delivery ([Verse], [End]).

    THE one parser (FU-U1): suno_recipe.parse_lyrics, words_fit.parse_sheet_words,
    music_styles.sheet_deliveries and lyric_writer.lyric_structure.delivery_of_tag
    all read tags through here, so no gate measures a different sheet.
    """
    raw = str(tag or "").strip()
    if raw.startswith("[") and raw.endswith("]") and len(raw) > 2:
        raw = raw[1:-1]
    norm = re.sub(r"[^a-z0-9]+", " ", raw.lower()).strip()
    if not norm:
        return None
    if re.search(r"\binstrumental\b", norm) or norm == "inst":
        return INSTRUMENTAL
    best = None
    for rank, (delivery, words) in enumerate(_DELIVERY_WORDS):
        for word in words:
            m = re.search(r"\b%s\b" % word, norm)
            if m is not None and (best is None or (m.start(), rank) < best[:2]):
                best = (m.start(), rank, delivery)
    return best[2] if best else None


#: FU-U1: the name every other module reads this grammar by. words_fit,
#: music_styles and lyric_writer resolve a tag's delivery through here, so no
#: gate measures a different sheet.
delivery_of_tag = parse_tag


def parse_lyrics(text):
    """Inverse of render_lyrics. Untagged text yields an empty sheet.

    FU-U1: a lyric line under a bracket the grammar cannot classify raises
    RecipeError(UNTAGGED_LYRIC_LINES) naming the lines -- never cur = None,
    which silently threw away every [Rap Verse ... (rap)] line. An
    [Instrumental] block carries no lyrics by definition. Both bracket
    dialects parse: [Name (sung|spoken|rap): note] keeps Name as the tag,
    [Sung|Spoken|Rap - ...] keeps the bracket text.
    """
    sheet, cur, lost = [], None, []
    for ln in str(text).splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith("["):
            m = _BRACKET_RE.match(s)
            if m is not None:
                inner = m.group(1).strip()
                named = _NAMED_TAG_RE.match(inner)
                if named is not None:
                    cur = {"tag": named.group(1).strip(),
                           "delivery": named.group(2).lower(), "lines": []}
                    sheet.append(cur)
                    continue
                d = parse_tag(inner)
                if d in DELIVERIES:
                    cur = {"tag": inner, "delivery": d, "lines": []}
                    sheet.append(cur)
                else:
                    # instrumental: wordless; anything else: refuse if lyrics follow
                    cur = None if d == INSTRUMENTAL else "lost"
                continue
        if isinstance(cur, dict):
            cur["lines"].append(s)
        elif cur == "lost":
            lost.append(s)
        # cur is None: text before any tag -- untagged sheet, still empty
    if lost:
        raise RecipeError("UNTAGGED_LYRIC_LINES",
                          "lyric text sits under a tag with no delivery (name it "
                          "sung|spoken|rap): %s" % "; ".join(repr(x) for x in lost[:8]))
    return sheet


def check_no_voice_lines(text):
    """[] when no lyric line sits under a no-voice tag (design 4.3/8.8).

    Suno sings whatever line it finds; "6 s, band only" under
    [Instrumental Break] would be sung. The checker reads the RAW text,
    because a parser could drop the line silently.
    """
    errs, no_voice = [], False
    for ln in str(text).splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith("[") and s.endswith("]"):
            no_voice = "(" not in s or is_no_voice_tag(s[1:].split(":")[0])
            no_voice = no_voice or is_no_voice_tag(s)
            continue
        if s.startswith("["):
            no_voice = False
            continue
        if no_voice:
            errs.append("lyric line under a no-voice tag (it would be sung): %r" % s)
            no_voice = False
    return errs


def sheet_words(sheet, delivery=None):
    return sum(len(str(l).split()) for s in sheet
               if delivery in (None, s["delivery"]) for l in s["lines"])


# ---- FU-U5: voice tags come from the cast ---------------------------------
# Plan 18-OPUS-SKILL75-FUTURE-PLAN unit U5 / root cause A7: the One-Check
# lyric sheet was hand-tagged "[... Desk Neighbor (rap): Female voice ...]"
# while the cast record said the desk neighbour was a man, and no code ever
# compared the two. This is the SHEET TAG versus CAST RECORD check. It is
# NOT the style-prompt gender slot (U15d owns that: the {gender} in
# music/*.json and suno-v6.json vocal_gender come from the brief, never
# hard-coded), and it does not touch vocal_gender.
GENDER_WORDS = {"female": "female", "woman": "female", "f": "female",
                "male": "male", "man": "male", "m": "male"}
#: Same two words voice_casting accepts; a cast that says anything else is
#: not a gender this check can prove, so it fails closed.
CAST_GENDERS = frozenset(("male", "female"))
_GENDER_WORD_RE = re.compile(r"\b(female|woman|male|man)\b", re.I)
_ANY_BRACKET_RE = re.compile(r"\[([^\]\n]*)\]")
#: Section words that are never a character name (the recipe's own tags).
_SECTION_WORDS = frozenset((
    "rap", "verse", "hook", "intro", "outro", "bridge", "vocalise", "chorus",
    "end", "instrumental", "break", "pre", "post", "section", "part"))


def parse_voice_tags(sheet_text):
    """Every bracket in a lyric sheet with the gender word it names.

    Returns [{"tag", "gender", "name"}] per bracket. gender is
    "female"/"male" or None when the bracket names no gender word; name is
    the cast character the bracket names, or None when it names nobody
    ([Hook], [Intro], [End]). One parser, so the check and any caller read
    the same brackets (FU-U1's rule applied to this check).
    """
    out = []
    for m in _ANY_BRACKET_RE.finditer(str(sheet_text or "")):
        inner = m.group(1).strip()
        norm = re.sub(r"[^a-z0-9]+", " ", inner.lower()).strip()
        g = _GENDER_WORD_RE.search(norm)
        out.append({"tag": inner,
                    "gender": GENDER_WORDS[g.group(1).lower()] if g else None,
                    "name": _tag_character(inner)})
    return out


def _tag_character(inner):
    """The cast character a bracket names, or None when it names none.

    "[Rap Verse 3 Desk Neighbor (rap): ...]" names "Desk Neighbor";
    "[Hook (sung): ...]", "[Intro (spoken): ...]", "[End]" and
    "[Instrumental Break]" name nobody and are never judged. The bracket's
    own name (the text before the delivery in parentheses, or before the
    first comma or dash) has its leading section words and numbers stripped.
    """
    head = re.split(r"[(,]", str(inner or ""))[0]
    head = re.split(r"\s+-\s+|\s+-\s*|\s+—\s*", head)[0]
    norm = re.sub(r"[^a-z0-9]+", " ", head.lower()).strip()
    words = norm.split()
    while words and (words[0] in _SECTION_WORDS or words[0].isdigit()):
        words.pop(0)
    name = " ".join(words).strip()
    return name if len(name) >= 2 else None


def check_voice_tags(sheet_text, cast_genders=None):
    """FU-U5: every cast character's sheet tag gender equals the cast record.

    ``cast_genders`` maps a cast character name to "male"/"female" (the
    brief's ``characters[].gender``; ``protected_names.cast_genders`` builds
    it from a brief). Returns a list of error strings, [] = pass.

    - A bracket naming a cast character whose tag gender differs from the
      cast -> VOICE_TAG_MISMATCH naming both sides.
    - A bracket naming a cast character with NO gender word -> fail closed,
      VOICE_TAG_UNCHECKED (an unverifiable tag is never a pass).
    - A cast entry whose gender is neither "male" nor "female" -> fail
      closed, VOICE_TAG_UNCHECKED: the check cannot prove the tag.
    - A bracket naming no cast character ([Hook], [Intro], [End], a bare
      [Rap Verse 3], a name the cast does not list) is never judged.
    - No cast record at all (None or empty) -> []: the check is off, exactly
      as today, so this unit changes nothing for a caller who passes no cast.

    This never judges the style prompt and never touches vocal_gender: All
    Suno is the default voice and this unit adds no voice option.
    """
    if not cast_genders:
        return []
    cast = {}
    for name, gender in cast_genders.items():
        g = str(gender or "").strip().lower()
        cast[_norm_char(name)] = (name, g if g in CAST_GENDERS else None)
    errs = []
    for t in parse_voice_tags(sheet_text):
        if not t["name"]:
            continue
        hit = cast.get(t["name"])
        if hit is None:
            continue                      # names nobody in this cast
        name, want = hit
        if want is None:
            errs.append("VOICE_TAG_UNCHECKED: [%s] names %s, whose cast record "
                        "has no gender (male|female)" % (t["tag"], name))
        elif t["gender"] is None:
            errs.append("VOICE_TAG_UNCHECKED: [%s] names %s with no gender "
                        "word; the cast says %s" % (t["tag"], name, want))
        elif t["gender"] != want:
            errs.append("VOICE_TAG_MISMATCH: [%s] tags %s %s voice, the cast "
                        "says %s" % (t["tag"], name, t["gender"], want))
    return errs


def _norm_char(name):
    """A character name normalized for matching: case, spacing, separators."""
    return re.sub(r"[^a-z0-9]+", " ", str(name or "").lower()).strip()


def check_lyric_sheet(sheet, client_text, length_s=None, spoken_share_pct=None,
                      style_id=None, hook_plan=None):
    """Rules 1-3 on the sheet. Returns a list of errors (empty = pass).

    With length_s (delivered seconds) the I8 hook count and the length-formula
    word budget are enforced too. FU-U1: rap sections are counted in the total
    budget and allowed only where the style is a rap style (RAP_STYLE_IDS, or
    music/<style>.json rap_allowed) -- a rap section with no style named fails
    closed. U15d: a no-voice section (Instrumental, Break) must carry no lines.
    """
    errs = []
    if not sheet:
        return ["no tagged sections: every section must be (sung), (spoken) or (rap)"]
    for s in sheet:
        d, tag = s.get("delivery"), str(s.get("tag", ""))
        if d is None or is_no_voice_tag(tag):
            if s.get("lines"):
                errs.append("section %r has no voice but carries lyric lines "
                            "(Suno would sing them)" % tag)
            continue
        if d not in DELIVERIES or not s.get("lines"):
            errs.append("section %r needs delivery sung|spoken|rap and lines" % s.get("tag"))
    if errs:
        return errs
    rap = [s for s in sheet if s.get("delivery") == "rap"]
    rap_ok = style_id in RAP_STYLE_IDS or (
        bool(style_id) and bool(music_block(style_id).get("rap_allowed")))
    if rap and not rap_ok:
        errs.append("rap sections need a rap style (got style_id=%r): %s"
                    % (style_id, ", ".join(repr(s["tag"]) for s in rap[:4])))
    for s in sheet:
        head = s["tag"].lower().split()[0]
        if s["delivery"] == "spoken" and head not in ("intro", "outro"):
            errs.append("spoken section %r: spoken tags are only allowed in [Intro]/[Outro]" % s["tag"])
        if s["delivery"] == "sung" and head != "vocalise":
            for ln in s["lines"]:
                if syllables(ln) > MAX_SUNG_LINE_SYLLABLES:
                    errs.append("sung line over %d syllables: %r" % (MAX_SUNG_LINE_SYLLABLES, ln))
    sung = [s for s in sheet if s["delivery"] == "sung"]
    if not sung:
        return errs + ["no sung section"]
    if not any(s["tag"].lower().startswith("vocalise") for s in sung):
        errs.append("no sung vocalise lead-in (wordless, before the first hook)")
    if sheet[0]["tag"].lower().startswith("hook"):
        errs.append("the first hook may not open the song: a vocalise comes first")
    keys = [tuple(_words(" ".join(s["lines"]))) for s in sung
            if not s["tag"].lower().startswith("vocalise")]
    hooks = [k for k in set(keys) if keys.count(k) >= MIN_HOOK_REPEATS]
    if not hooks:
        return errs + ["no repeated sung hook (same sung lines at least %d times)" % MIN_HOOK_REPEATS]
    client = set(_words(client_text or ""))
    # No gate switches itself off: no client text = the own-words rule is
    # UNMEASURED (a refusal); the hook count and structure run regardless.
    if not client:
        errs.append("UNMEASURED: client_text (the hook must be the client's own words)")
    elif not any(h and set(h) <= client for h in hooks):
        errs.append("repeated hook is not built from the client's own words")
    if length_s is not None:
        best = max(hooks, key=keys.count)
        errs += _SH.check_sheet_count(sheet, best, length_s,
                                      _HP.hook_target(length_s, hook_plan))
    if length_s is not None:
        p = _LF.plan(length_s + _LF.END_EARLY_S, spoken_share_pct, style_id=style_id)
        total = sheet_words(sheet)
        # R&B word budget: U2 landed on 999 main only (MGB010a); on the
        # onboarding tree the rap budget is still open (file 18 decision 1),
        # so the ballad budget is not applied to a rap sheet there.
        rap_pending = sheet_words(sheet, "rap") > 0 and not rap_ok
        if not rap_pending and total > p["words"]["total"] * 1.1 + 2:
            errs.append("%d words, the %d s budget is %d" % (total, length_s, p["words"]["total"]))
        intro = [s for s in sheet if s["delivery"] == "spoken" and s["tag"].lower().startswith("intro")]
        if intro and sheet_words(intro) > p["words"]["opener_max"]:
            errs.append("spoken intro is %d words, max %d at this length"
                        % (sheet_words(intro), p["words"]["opener_max"]))
    return errs


def sheet_seconds(sheet, rate=None):
    """Estimated delivered seconds of a sheet at the length-formula rates.

    The rate for rap comes from music/<style>.json rap_rate_wps (data); the
    sung and spoken rates stay length_formula's own measured constants. A
    no-voice section contributes its own ``seconds`` when it carries one.
    """
    rate = rate or {"sung": _LF.SUNG_WPS, "spoken": _LF.SPOKEN_WPS}
    total = 0.0
    for s in sheet:
        if s.get("delivery") is None or is_no_voice_tag(s.get("tag", "")):
            total += float(s.get("seconds") or 0.0)
            continue
        wps = rate.get(s["delivery"])
        if wps is None and s.get("style_id") is not None:
            wps = music_block(s["style_id"]).get("rap_rate_wps")
        total += sheet_words([s]) / float(wps or _LF.SUNG_WPS)
    return round(total, 3)


def is_product_section(tag):
    """True for the product passage and its reprises ([Product (reprise 2)])."""
    return str(tag).strip().lower().startswith("product")


def product_share_pct(sheet, delivered_s):
    """The product passage's share of the delivered seconds (U13: 10-15%).

    Counts every [Product ...] section, reprises included, at the measured
    delivery rates. This is the number the gate judges; the fixtures' own
    measured block carries the same rule (design 4.6).
    """
    if not isinstance(delivered_s, (int, float)) or delivered_s <= 0:
        raise RecipeError("BAD_DELIVERED_S",
                          "delivered_s must be positive seconds, got %r" % (delivered_s,))
    prod = [s for s in sheet if is_product_section(s.get("tag", ""))]
    return round(100.0 * sheet_seconds(prod) / float(delivered_s), 2)


def check_product_share(sheet, delivered_s,
                        floor_pct=PRODUCT_SHARE_FLOOR_PCT,
                        cap_pct=PRODUCT_SHARE_CAP_PCT):
    """[] when the product passage covers 10-15% of the delivered seconds.

    The rule is judged on the passage the sheet HAS: a sheet carrying no
    [Product ...] section is the planner's business (U13/U15h own the product
    seconds), not this gate's, so it makes no claim here rather than measuring
    a share of zero.
    """
    if not any(is_product_section(s.get("tag", "")) for s in sheet):
        return []
    pct = product_share_pct(sheet, delivered_s)
    if not floor_pct <= pct <= cap_pct:
        return ["product passage is %.1f%% of the %g s delivered length, "
                "outside %g-%g%%" % (pct, delivered_s, floor_pct, cap_pct)]
    return []


def hook_target(style_id, length_s):
    """I8 hook repeats for a style and delivered length (0 = exempt voiceover)."""
    return 0 if is_exempt(style_id) else _SH.hook_count(length_s)


def negative_tags(style_id=None):
    """The negative-tag string for a style, read from music/<style>.json (data).

    The rap style's data carries no rap negatives; every other style keeps
    them. No second copy lives here.
    """
    if style_id is not None and not is_exempt(style_id):
        block = music_block(_style_key(style_id))
        if block.get("negative_tags") is not None:
            return str(block["negative_tags"])
    tags = [t for t in NEGATIVE_TAGS if not (style_id in RAP_STYLE_IDS and t.startswith("rap"))]
    return ", ".join(tags)


def _style_key(style_id):
    """The data file's own style id (label or id accepted, via music_styles)."""
    return _MS.style(style_id)["style_id"]


def _gender_variant(part, gender_word):
    """One style part with {gender} replaced by the brief's word (never fixed).

    The data's placeholder is ``{gender} lead``; with a real gender word the
    sentence reads "Warm female lead". The golden sheets wrote "Warm female
    lead" from a brief whose word was "Warm female", so the word goes in
    verbatim; with no word from the brief the placeholder is refused rather
    than defaulted, because a hard-coded female is the U5 defect.
    """
    if "{gender}" in part:
        if not gender_word:
            raise RecipeError("GENDER_REQUIRED",
                              "the style part needs {gender} and the brief names none: %r"
                              % part)
        return part.replace("{gender}", gender_word)
    return part


def style_text(style_id, sheet=None, vocal_gender="f"):
    """Suno style field: the style's OWN parts, in order, one clean ending.

    Built from music/<style>.json style_parts (design 4.2): part 1 is the base
    prompt (ending with a period, which fixes the "no distortion The lead"
    run-on), part 2 is the sung lead carrying the brief's gender word, part 3
    the delivery map, part 4 the spoken clause. The gender word comes from the
    brief (``vocal_gender``), never hard-coded female.

    The style's data owns the negatives; the ending clause is ending_qc's
    (composed there, never restated here).
    """
    if style_id is not None and not is_exempt(style_id):
        sid = _style_key(style_id)
        block = music_block(sid)
        word = vocal_gender_word(vocal_gender)
        parts = [_gender_variant(str(p).rstrip("."), word).rstrip(".") + "."
                 for p in block["style_parts"]]
        # The clean-ending clause is ending_qc's, appended the way ending_qc
        # appends it (comma, no double period). It is here so the measured
        # style counts equal the design's (623/699/707, 733/809/817 with the
        # FU-HOOK-PLACEMENT order clause) and so the final
        # payload is the same whether or not with_clean_ending has run.
        text = " ".join(parts).rstrip(".") + ", " + _EQ.STYLE_ENDING + "."
        # FU-HOOK-PLACEMENT rule 5: the section order is the sheet's, and the
        # song never opens with the hook (Suno added a hook at 13.6 s in v2).
        text = "%s %s." % (text, _HP.PROMPT_CLAUSE)
        # G1 delivery map: the map sentence must name the sheet's deliveries.
        text = _MS.assert_delivery_map(sid, text, _sheet_deliveries(sheet, sid))
        if len(text) > SUNO_STYLE_FIELD_MAX:
            raise RecipeError("STYLE_TOO_LONG",
                              "%d chars, limit %d" % (len(text), SUNO_STYLE_FIELD_MAX))
        return text
    text = "%s. Only the short intro and the final outro are spoken; %s." % (
        _MS.style_prompt(style_id).rstrip(".,"), BAND_WORDING)
    if len(text) > SUNO_STYLE_FIELD_MAX:
        raise RecipeError("STYLE_TOO_LONG", "%d chars, limit %d" % (len(text), SUNO_STYLE_FIELD_MAX))
    return text


def _sheet_deliveries(sheet, style_id):
    """The deliveries a sheet names, or the style's own when it names none."""
    if sheet:
        names = {s["delivery"] for s in sheet if s.get("delivery") and s.get("lines")}
        if names:
            return names
    return set(music_block(style_id)["deliveries"])


def check_style_text(text):
    """Style rules: 1000 chars or less, spoken named at most once, band wording."""
    text = str(text)
    errs = []
    if len(text) > SUNO_STYLE_FIELD_MAX:
        errs.append("style text is %d chars, limit %d" % (len(text), SUNO_STYLE_FIELD_MAX))
    # G1 delivery map (merged on main) is the one mandated spoken clause; it is
    # not counted against the at-most-once rule.
    own = text.replace(_MS.DELIVERY_MAP_CLAUSES[0][1], "")
    own = own.replace(_MS.DELIVERY_MAP_CLAUSES[1][1], "").replace(_MS.DELIVERY_MAP_CLAUSES[2][1], "")
    n = len(_SPOKEN_WORD_RE.findall(own))
    if n > 1:
        errs.append("style text names spoken delivery %d times, at most once" % n)
    if "band keeps playing" not in text.lower():
        errs.append("style text must say the full band keeps playing under the spoken lines")
    return errs


def check_negatives(neg, style_id=None):
    low = [t.strip().lower() for t in str(neg).split(",") if t.strip()]
    errs = ["negative_tags missing %r" % w for w in REQUIRED_NEGATIVES if w not in low]
    errs += ["negative_tags must not contain %r (it would suppress our own spoken lines)" % w
             for w in FORBIDDEN_NEGATIVES if any(w in t for t in low)]
    if style_id in RAP_STYLE_IDS and any(t.startswith("rap") for t in low):
        errs.append("rap style must not exclude rap")
    return errs


def prepare(style_id, sheet, client_text, length_s=None, spoken_share_pct=None,
            vocal_gender="f", delivered_s=None, hook_plan=None):
    """THE gate every Suno style goes through. Returns style + lyrics text.

    Exempt (voiceover) -> {"exempt": True}. Unknown id -> fail closed.
    ``delivered_s`` (or ``length_s``) enables the U13 product-share gate.
    """
    if is_exempt(style_id):
        return {"exempt": True}
    if style_id not in suno_style_ids():
        raise RecipeError("UNKNOWN_STYLE", "%r is not a Suno style and not "
                          "exempt; add it to music_styles" % (style_id,))
    errs = check_lyric_sheet(sheet, client_text, length_s, spoken_share_pct,
                             style_id=style_id, hook_plan=hook_plan)
    errs += check_no_voice_lines(render_lyrics(sheet, style_id))
    d = delivered_s if delivered_s is not None else length_s
    # FU-HOOK-PLACEMENT rule 1, always on (no length = UNMEASURED: length_s)
    errs += _HP.check_buildup(sheet, style_id, d)
    if d is not None:
        errs += check_product_share(sheet, d)
    # FU-HOOK-PLACEMENT rules 2-3, always on: the first hook MEASURED at or
    # after its story beat (no hook_plan = UNMEASURED: hook_plan)
    errs += _HP.check_story(sheet, hook_plan, d, style_id)
    if errs:
        raise RecipeError("LYRICS_REJECTED", "; ".join(errs))
    return {"exempt": False, "style": style_text(style_id, sheet, vocal_gender),
            "lyrics": render_lyrics(sheet, style_id),
            "negative_tags": negative_tags(style_id)}


def build_request(style_id, sheet, client_text, title, length_s, vocal_gender="f",
                  spoken_share_pct=None, delivered_s=None, hook_plan=None):
    """KIE generate-music input for one ad (snake_case). ``length_s`` is the
    DELIVERED length (chosen - 2). Raises RecipeError on any rule break."""
    out = prepare(style_id, sheet, client_text, length_s, spoken_share_pct,
                  vocal_gender, delivered_s, hook_plan)
    if out.get("exempt"):
        raise RecipeError("EXEMPT", "voiceover style has no Suno request")
    req = kie_params()
    req.update({"duration": length_s, "vocal_gender": vocal_gender, "title": title,
                "style": out["style"], "lyrics": out["lyrics"],
                "negative_tags": out["negative_tags"]})
    # FU-U6 (plan E.1): the final payload measured against the catalog caps;
    # over a cap, prompt_limits raises naming field, chars, cap, source, status.
    _PL.check_request("suno-generate", req)
    return req


def guard_request(style_text_, lyrics_text, style_id=None, client_text=None,
                  length_s=None, cast_genders=None, hook_plan=None):
    """Seam for music_director.build_generate_request. Raises RecipeError.

    With style_id: the full recipe is enforced (exempt id passes untouched).
    Without: a raw Suno base prompt is a bypass and is refused; any other
    free-form style text is left to the caller (legacy behavior).

    FU-U5: with ``cast_genders`` (a name -> "male"/"female" map from the
    brief's characters, e.g. ``protected_names.cast_genders(brief)``) every
    sheet voice tag must agree with the cast record. This runs FIRST and in
    BOTH branches, because the cheapest place to catch a wrong tag is before
    any recipe work at all -- and it never touches vocal_gender.
    """
    cast_errs = check_voice_tags(lyrics_text, cast_genders)
    if cast_errs:
        raise RecipeError("VOICE_TAG_MISMATCH", "; ".join(cast_errs))
    if style_id is None:
        if any(str(style_text_).startswith(_MS.style_prompt(i))
               for i in suno_style_ids()):
            raise RecipeError("RECIPE_BYPASSED", "Suno style used without "
                              "the song recipe; pass style_id and client_text")
        # No gate switches itself off: without the style, the song contract,
        # hook placement and the recipe cannot be measured, so a sheet that
        # carries sung or rap sections is refused, never waved through.
        # Any non-empty lyrics are refused: Suno sings untagged text too. Only
        # an empty / instrumental-only request (no voiced words) passes.
        try:
            voiced = any(s["delivery"] or s["lines"] for s in parse_lyrics(lyrics_text))
        except RecipeError:   # lyric lines under a bracket naming no delivery: Suno sings them
            voiced = True
        voiced = voiced or any(ln.strip() and not ln.strip().startswith("[")
                               for ln in str(lyrics_text or "").splitlines())
        if voiced:
            raise RecipeError("UNMEASURED", "UNMEASURED: style_id (the request carries lyrics; "
                              "the song contract, hook placement and recipe need the style)")
        return
    if is_exempt(style_id):
        return
    if style_id not in suno_style_ids():
        raise RecipeError("UNKNOWN_STYLE", repr(style_id))
    # FU-RNBFLOW-SONG: the style's own contract (real sung lyrics, rap tagged
    # as rap on the beat, plain spoken outro). No length -> "UNMEASURED:
    # length_s", a refusal, never a skipped check.
    from song_contract import song_contract as _SC
    errs = _SC.check_sheet(lyrics_text, style_id, length_s, style_text_)["reasons"]
    errs += check_style_text(style_text_)
    errs += check_lyric_sheet(parse_lyrics(lyrics_text), client_text or "", length_s,
                              style_id=style_id, hook_plan=hook_plan)
    errs += _HP.check_buildup(lyrics_text, style_id, length_s)   # FU-HOOK-PLACEMENT rule 1
    errs += _HP.check_story(lyrics_text, hook_plan, length_s, style_id)   # rules 2-3, always on
    if errs:
        raise RecipeError("RECIPE_BYPASSED", "; ".join(errs))


def check_payload(payload, client_text=None, vocal_gender=None):
    """Every U15d rule on one BUILT payload (the golden-sheet shape). [] = pass.

    Measures the FINAL payload: the style after ending_qc, the lyric chars per
    segment, the title and the negative tags against their caps; the hook
    count across all segments against sung_hook.hook_count(D); the product
    share across all segments against 10-15%; and each segment's text against
    the no-voice-line rule and a render/parse roundtrip.
    """
    errs = []
    D = payload.get("delivered_s")
    segs = payload.get("segments") or []
    if not segs:
        return ["payload carries no segments"]
    sheets, hooks = [], 0
    for i, seg in enumerate(segs):
        text = seg.get("lyrics") or ""
        errs += ["segment %d: %s" % (i, e) for e in check_no_voice_lines(text)]
        if len(text) > 5000:
            errs.append("segment %d lyrics is %d chars, cap 5000" % (i, len(text)))
        sh = parse_lyrics(text)
        sheets += sh
        hooks += sum(1 for s in sh if str(s["tag"]).lower().startswith("hook"))
    style = payload.get("style") or ""
    errs += check_style_text(style)
    title, neg = payload.get("title") or "", payload.get("negative_tags") or ""
    if len(title) > 80:
        errs.append("title is %d chars, cap 80" % len(title))
    if len(neg) > 1000:
        errs.append("negative_tags is %d chars, cap 1000" % len(neg))
    sid = payload.get("music_style")
    if not sid:   # no gate switches itself off: no style, nothing below is measured
        return errs + ["UNMEASURED: music_style"]
    if not is_exempt(sid):
        errs += check_negatives(neg, sid)
        errs += check_lyric_sheet(sheets, client_text or "", None, None, style_id=sid)
        errs += _HP.check_buildup(sheets, sid, D)   # FU-HOOK-PLACEMENT rule 1, always on
        errs += _HP.check_story(sheets, payload.get("hook_plan"), D, sid)   # rules 2-3
        if vocal_gender is not None and "{gender}" in style:
            errs.append("a {gender} placeholder reached the payload")
    if D:
        want = _HP.hook_target(D, payload.get("hook_plan"))
        if hooks != want:
            errs.append("hook count %d, the %g s delivered length needs %d" % (hooks, D, want))
        errs += check_product_share(sheets, D)
    return errs


def _planned_pct(plan, style_id, key):
    """Percent of delivered runtime one delivery holds in the APPROVED plan
    (U3): words[key] / words_fit's measured rate for the style, over the
    plan's delivered seconds. Missing counts -> None (fall back)."""
    words = (plan or {}).get("words") or {}
    if key not in words:
        return None
    delivered = (plan or {}).get("delivered_s")
    if not isinstance(delivered, (int, float)) or delivered <= 0:
        return None
    import words_fit as _WF
    rate = _WF.rates_for(style_id).get(key)
    if not rate:
        return None
    return round(float(words[key]) / float(rate) / float(delivered) * 100.0, 3)

def score_take(take, hook_text=None, words=None, length_s=None,
               style_id=None, plan=None):
    """Rule 4: judge a take from MEASURED or ALIGNED segments only.

    take = {"segments": [{"delivery", "start", "end", "source": "measured"
    or "aligned"}]}. A take with no segments, or any segment built from
    labels alone, fails. "aligned" is the rap-versus-speech split (measured
    word timestamps x the sheet's delivery labels) and is NEVER recorded as
    "measured".

    FU-U3: ``style_id`` carries the music style and ``plan`` the approved
    plan (U2) through the judge. Bands per style, always the 5/10 band:
    Soul Ballad and Soul Rise keep spoken 22.5 / sung-of-voice 77.5 exactly;
    for a rap style (R&B Flow) the plain-spoken and rap shares are judged
    against the share each delivery has in the APPROVED plan -- the
    documented default from plan 18 section 9 item 1 (a TREVOR-DECISION
    ITEM; no new number invented), plain spoken with no rap keeps 22.5, and
    sung-of-voice on a rap sheet is recorded, not gated. The 6 s sung
    stretch and the hook count stay hard.

    Checks first singing by 15% of runtime on the same band. With hook_text,
    Suno aligned words and length_s, the sung hook count is measured too (I8,
    Trevor band) and the receipt is returned under "hook". Returns
    {"verdict": PASS|FLAG|FAIL, "reasons"}.
    """
    segs = (take or {}).get("segments")
    if not segs:
        return _res("FAIL", ["take has no measured segments (labels are not a measurement)"])
    srcs = {s.get("source") for s in segs}
    if not srcs <= {"measured", "aligned"} or "measured" not in srcs:
        return _res("FAIL", ["take scored from labels: segments must come from the detector (source=measured) or the aligned word split (source=aligned)"])
    basis = _SS.segment_basis(segs)
    t = _SS.style_targets(style_id)
    reasons, flags = [], []
    shares = _SS.measure_share(segs, basis, style_id=style_id)
    if t["rap_delivery"] and t["target_from_plan"]:
        planned = _planned_pct(plan, style_id, "spoken")
        tgt = _SS.SPOKEN_TARGET_PCT if planned is None else planned
    else:
        tgt = _SS.SPOKEN_TARGET_PCT
    band = _SS.check_share(shares["share"], segs, basis, target_pct=tgt,
                           style_id=style_id)
    if band["verdict"] == "FAIL":
        reasons += band["reasons"]
    flags += band.get("flags", [])
    # rap as its own delivery: judged against the plan's own rap share for a
    # rap style, against zero for a style that allows none.
    if t["rap_delivery"]:
        planned_rap = _planned_pct(plan, style_id, "rap")
        if shares["rap_seconds"] > 0 or planned_rap:
            j = _SS.judge_gap(shares["rap_share_pct"],
                              planned_rap if planned_rap is not None
                              else _SS.SPOKEN_TARGET_PCT)
            if j["verdict"] == "FAIL":
                reasons.append("rap share %.1f%% vs plan %s: %.1f points off, redo"
                               % (shares["rap_share_pct"],
                                  "none" if planned_rap is None else "%.1f%%" % planned_rap,
                                  j["gap_pts"]))
    elif shares["rap_seconds"] > 0:
        j = _SS.judge_gap(shares["rap_share_pct"], 0.0)
        if j["verdict"] != "PASS":
            reasons.append("%.1f%% rap measured in a style that allows none"
                           % shares["rap_share_pct"])
    # SPK001: singing is judged against VOICE time (sung / voice); intro,
    # gaps and end card never count against it. For a rap style the
    # percentage is recorded, not gated (hook content, not a planned share).
    if shares["voice_seconds"] - shares["sung_seconds"] > 0:
        voice = _SS.check_sung_of_voice(segs, basis=basis, style_id=style_id)
        reasons += voice["reasons"]
        flags += voice["flags"]
    sung = [s["start"] for s in segs if s["delivery"] == "sung"]
    total = shares["total_seconds"]
    if not sung:
        reasons.append("no singing in the take")
    else:
        gap = (min(sung) / total - FIRST_SING_TARGET) * 100.0
        if gap > FLAG_PTS:
            reasons.append("first singing at %.0f%% of runtime, target %.0f%% "
                           "(%.1f points late)" % (min(sung) / total * 100,
                                                   FIRST_SING_TARGET * 100, gap))
        elif gap > ACCEPT_PTS:
            flags.append("first singing %.1f points past target" % gap)
    receipt = None
    if hook_text is not None:
        hook_segs = [s for s in segs if s.get("source") == "measured"]
        receipt = _SH.measure(hook_text, words or [], hook_segs, _SH.hook_count(length_s))
        if receipt["verdict"] == "FAIL":
            reasons.append("hook sung %d of %d times %s" % (
                receipt["measured"], receipt["target"], receipt["reason"]))
        elif receipt["verdict"] == "FLAG":
            flags.append("hook sung %d of %d times" % (receipt["measured"], receipt["target"]))
    out = _res("FAIL" if reasons else ("FLAG" if flags else "PASS"), reasons + flags)
    out["basis"] = basis
    out["style_id"] = style_id
    if receipt:
        out["hook"] = receipt
    return out

def _res(verdict, reasons):
    return {"verdict": verdict, "reasons": reasons}
