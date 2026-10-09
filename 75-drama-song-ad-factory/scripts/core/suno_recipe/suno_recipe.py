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
  3. The first hook comes after the vocalise, never at 0 s; the hook is
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

import length_formula as _LF    # noqa: E402
import music_styles as _MS      # noqa: E402
import spoken_share as _SS      # noqa: E402
import sung_hook as _SH         # noqa: E402

TOOL_NAME = "suno_recipe"
TOOL_VERSION = "2.0.0"

RULES = (
    "Spoken tags only in [Intro] and [Outro]; spoken named once in the style text; the full band keeps playing under it.",
    "Sung lines are short, rhymed, with hyphen-held vowels, after a wordless sung vocalise.",
    "The first hook comes after the vocalise, never at 0 s; the hook is the client's own words.",
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
#: Per style (plan 2.A3): R&B Flow is a rap style, so the ballad lead (slow
#: tempo, long held open vowels) is wrong for it. Voice gender words come
#: from vocal_gender, never hard-coded -- "female" is gone from here.
STYLE_LEAD = {
    "soul-ballad": "sung melody with long held open vowels, dry close vocal, "
                   "slow tempo, natural resolved ending, final chord rings out and fades",
    "rnb-flow": "dry close vocal, rhythmic flow over the beat, natural resolved ending, "
                "final chord rings out and fades",
    "soul-rise": "sung melody with long held open vowels, dry close vocal, "
                 "slow start lifting into an upbeat groove, natural resolved ending, "
                 "final chord rings out and fades",
}
#: Back-compat default (the original ballad lead, minus the gender word).
STYLE_LEAD_DEFAULT = STYLE_LEAD["soul-ballad"]
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


SUNG_DIRECTION = {"vocalise": "wordless, full melodic voice, two very long held notes",
                  "hook": "full melody, slow long held notes"}
SPOKEN_DIRECTION = "close dry voice, plain speech, no melody"
RAP_DIRECTION = "close dry voice, rhythmic metered flow over the beat"


def _tag(sec):
    d = sec["delivery"]
    note = (SPOKEN_DIRECTION if d == "spoken" else
            RAP_DIRECTION if d == "rap" else
            SUNG_DIRECTION.get(sec["tag"].lower().split()[0],
                               "soulful lead vocal, melodic, rhymed, slow long held notes"))
    return "[%s (%s): %s]" % (sec["tag"], d, note)


def render_lyrics(sheet):
    """Lyric sheet text: spoken tags only Intro/Outro, ends with [End]."""
    return "\n\n".join(_tag(s) + "\n" + "\n".join(s["lines"]) for s in sheet) + "\n\n[End]"


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
                      style_id=None):
    """Rules 1-3 on the sheet. Returns a list of errors (empty = pass).

    With length_s (delivered seconds) the I8 hook count and the length-formula
    word budget are enforced too. FU-U1: rap sections are counted in the total
    budget and allowed only when style_id is in RAP_STYLE_IDS -- a rap section
    in Soul Ballad / Soul Rise (or with no style named, fail closed) is refused.
    """
    errs = []
    if not sheet:
        return ["no tagged sections: every section must be (sung), (spoken) or (rap)"]
    for s in sheet:
        if s.get("delivery") not in DELIVERIES or not s.get("lines"):
            errs.append("section %r needs delivery sung|spoken|rap and lines" % s.get("tag"))
    if errs:
        return errs
    rap = [s for s in sheet if s["delivery"] == "rap"]
    if rap and style_id not in RAP_STYLE_IDS:
        errs.append("rap sections need the rap style %s (got style_id=%r): %s"
                    % (sorted(RAP_STYLE_IDS), style_id,
                       ", ".join(repr(s["tag"]) for s in rap[:4])))
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
    client = set(_words(client_text))
    if not any(h and set(h) <= client for h in hooks):
        errs.append("repeated hook is not built from the client's own words")
    elif length_s is not None:
        best = max(hooks, key=keys.count)
        errs += _SH.check_sheet_count(sheet, best, length_s)
    if length_s is not None:
        p = _LF.plan(length_s + _LF.END_EARLY_S, spoken_share_pct)
        total = sheet_words(sheet)
        if total > p["words"]["total"] * 1.1 + 2:
            errs.append("%d words, the %d s budget is %d" % (total, length_s, p["words"]["total"]))
        intro = [s for s in sheet if s["delivery"] == "spoken" and s["tag"].lower().startswith("intro")]
        if intro and sheet_words(intro) > p["words"]["opener_max"]:
            errs.append("spoken intro is %d words, max %d at this length"
                        % (sheet_words(intro), p["words"]["opener_max"]))
    return errs


def hook_target(style_id, length_s):
    """I8 hook repeats for a style and delivered length (0 = exempt voiceover)."""
    return 0 if is_exempt(style_id) else _SH.hook_count(length_s)


def negative_tags(style_id=None):
    """The negative-tag string for a style (rap dropped for the rap style)."""
    tags = [t for t in NEGATIVE_TAGS if not (style_id in RAP_STYLE_IDS and t.startswith("rap"))]
    return ", ".join(tags)


#: Gender word from the caller's vocal_gender; no hard-coded "female".
_GENDER_WORDS = {"f": "female", "m": "male"}


def _style_lead(style_id, vocal_gender=None):
    """The lead wording for one style (plan 2.A3): per style, and gendered
    from vocal_gender. Unknown style -> the ballad lead; no gender word ->
    "lead"."""
    lead = STYLE_LEAD.get(style_id, STYLE_LEAD_DEFAULT)
    gender = _GENDER_WORDS.get(str(vocal_gender or "").lower())
    return ("%s lead, %s" % (gender, lead)) if gender else ("lead, %s" % lead)


def style_text(style_id, sheet=None, vocal_gender=None):
    """Suno style field: base prompt, the per-style lead, ONE spoken mention,
    band wording. FU-U1: the lead is per style (R&B Flow gets no "slow tempo,
    long held open vowels") and the gender word comes from vocal_gender; the
    "Only the short intro and the final outro are spoken" claim is dropped
    when the sheet carries rap sections."""
    rap = any(s.get("delivery") == "rap" for s in (sheet or []))
    spoken_claim = ("Spoken lines stay in the intro and the outro"
                    if rap else
                    "Only the short intro and the final outro are spoken")
    text = "%s, %s. %s; %s." % (_MS.style_prompt(style_id),
                                _style_lead(style_id, vocal_gender),
                                spoken_claim, BAND_WORDING)
    if len(text) > SUNO_STYLE_FIELD_MAX:
        raise RecipeError("STYLE_TOO_LONG", "%d chars, limit %d" % (len(text), SUNO_STYLE_FIELD_MAX))
    return text


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
            vocal_gender="f"):
    """THE gate every Suno style goes through. Returns style + lyrics text.

    Exempt (voiceover) -> {"exempt": True}. Unknown id -> fail closed.
    """
    if is_exempt(style_id):
        return {"exempt": True}
    if style_id not in suno_style_ids():
        raise RecipeError("UNKNOWN_STYLE", "%r is not a Suno style and not "
                          "exempt; add it to music_styles" % (style_id,))
    errs = check_lyric_sheet(sheet, client_text, length_s, spoken_share_pct,
                             style_id=style_id)
    if errs:
        raise RecipeError("LYRICS_REJECTED", "; ".join(errs))
    return {"exempt": False, "style": style_text(style_id, sheet, vocal_gender),
            "lyrics": render_lyrics(sheet), "negative_tags": negative_tags(style_id)}


def build_request(style_id, sheet, client_text, title, length_s, vocal_gender="f",
                  spoken_share_pct=None):
    """KIE generate-music input for one ad (snake_case). ``length_s`` is the
    DELIVERED length (chosen - 2). Raises RecipeError on any rule break."""
    out = prepare(style_id, sheet, client_text, length_s, spoken_share_pct,
                  vocal_gender=vocal_gender)
    if out.get("exempt"):
        raise RecipeError("EXEMPT", "voiceover style has no Suno request")
    req = dict(KIE_PARAMS)
    req.update({"duration": length_s, "vocal_gender": vocal_gender, "title": title,
                "style": out["style"], "lyrics": out["lyrics"],
                "negative_tags": out["negative_tags"]})
    return req


def guard_request(style_text_, lyrics_text, style_id=None, client_text=None,
                  length_s=None, cast_genders=None):
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
        return
    if is_exempt(style_id):
        return
    if style_id not in suno_style_ids():
        raise RecipeError("UNKNOWN_STYLE", repr(style_id))
    errs = check_style_text(style_text_)
    errs += check_lyric_sheet(parse_lyrics(lyrics_text), client_text or "", length_s,
                              style_id=style_id)
    if errs:
        raise RecipeError("RECIPE_BYPASSED", "; ".join(errs))


def score_take(take, hook_text=None, words=None, length_s=None):
    """Rule 4: judge a take from MEASURED segments only.

    take = {"segments": [{"delivery", "start", "end", "source": "measured"}]}.
    A take with no segments, or any segment not measured (labels), fails.
    Checks the spoken share of runtime (target 22.5), the sung share of voice
    time (target 77.5) and first singing by 15% of runtime, all on the 5/10 band. With hook_text, Suno aligned words and
    length_s, the sung hook count is measured too (I8, Trevor band) and the
    receipt is returned under "hook". Returns {"verdict": PASS|FLAG|FAIL, "reasons"}.
    """
    segs = (take or {}).get("segments")
    if not segs:
        return _res("FAIL", ["take has no measured segments (labels are not a measurement)"])
    if any(s.get("source") != "measured" for s in segs):
        return _res("FAIL", ["take scored from labels: every segment must come from the detector (source=measured)"])
    reasons, flags = [], []
    shares = _SS.measure_share(segs)
    band = _SS.check_share(shares["share"], segs)
    if band["verdict"] == "FAIL":
        reasons += band["reasons"]
    flags += band.get("flags", [])
    # SPK001: singing is judged against VOICE time (sung / (sung + spoken)),
    # target 77.5; intro, gaps and end card never count against it.
    if shares["sung_seconds"] + shares["spoken_style_seconds"] > 0:
        voice = _SS.check_sung_of_voice(segs)
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
        receipt = _SH.measure(hook_text, words or [], segs, _SH.hook_count(length_s))
        if receipt["verdict"] == "FAIL":
            reasons.append("hook sung %d of %d times %s" % (
                receipt["measured"], receipt["target"], receipt["reason"]))
        elif receipt["verdict"] == "FLAG":
            flags.append("hook sung %d of %d times" % (receipt["measured"], receipt["target"]))
    out = _res("FAIL" if reasons else ("FLAG" if flags else "PASS"), reasons + flags)
    if receipt:
        out["hook"] = receipt
    return out


def _res(verdict, reasons):
    return {"verdict": verdict, "reasons": reasons}
