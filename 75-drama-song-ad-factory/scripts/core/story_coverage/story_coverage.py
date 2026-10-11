#!/usr/bin/env python3
"""Story coverage: the story-start ceiling, the opening-vocalise ceiling, the
lexical-coverage floor, the story-arc window rule, and the words-versus-length
floor.

D1 / F3+F4. The failed run measured: first LEXICAL word at 3.750 s but the
first substantial PLOT line at 22.107 s, with a wordless vocalise union from
8.380 s to 22.037 s -- about 14 seconds of an 88-second ad carried no story at
all (Trevor: "the first 18 seconds is just music"). The sheet arithmetic that
"proved" enough words was 69/1.9 + 13/2 + 19/2.5 + 8 = 58.4158, where the
trailing +8 is INTRO_OUTRO_S, MUSIC-ONLY time: the vocal-only figure is
50.416 s. Presenting 58.4 as seconds OF WORDS overstates word coverage by
8 seconds. This module keeps the two figures apart under two labels and never
adds them under one.

WWFIX-U1 (whose copy of this module landed on main FIRST) measured the same
defect on a second failed run: first LEXICAL word at 2.462-4.707 s, first
substantial PLOT line at 11.980-23.541 s, a wordless vocalise union up to
17.833 s and a lexical union of 48.476-53.991 s against the >= 61.6 s debt at
88 s. Two runs, one defect. This module therefore keeps BOTH opening rules --
main's share rule (the first LEXICAL word must not land after
OPENING_WORDLESS_SHARE_MAX = 0.15 of the delivered seconds) and the absolute
OPENING_VOCALISE_MAX_S = 3.0 ceiling, whose wordless span is measured from the
take's own FIRST ALIGNED ROW. The gate fails on EITHER. The share rule is the
LOOSER of the two and judges the lead-in that a take's alignment does not
cover; the absolute rule closes the 13.7 s hole the share rule left open.

FOUR GATES, all in skill code:

  * STORY START (``story_start_gate``): the first word of the approved PLOT
    line must arrive by FIRST_STORY_WORD_MAX_S (an ABSOLUTE 5.0 s -- not a
    share of the length), and the longest contiguous span inside
    ``[0, first_story_line_start_s]`` that carries NO lexical aligned word must
    not exceed OPENING_VOCALISE_MAX_S (an ABSOLUTE 3.0 s). The filler opener
    ("I'm still up") and a wordless vocalise are never counted as the story
    starting. A take with nothing measurable is UNAVAILABLE, never PASS.
  * LEXICAL COVERAGE (``lexical_coverage_gate``): the in-bounds union of real
    lexical word intervals, with NO vocalise counted, intersected with the
    measured voice when one is supplied, must reach LEXICAL_COVERAGE_MIN
    (0.70) of the delivered duration -- compared RAW, never rounded first. At
    88 s the master owes >= 61.6 s; the measured value was 33.143 s, so this
    gate rejects the shipped master.
  * STORY ARC (``story_arc_gate``): every beats_u16 window of at least
    STORY_ARC_WINDOW_MIN_S seconds must carry at least one measured lexical
    line. A five-second hole with no words is FAIL.
  * WORDS FLOOR (``words_floor``): the delivered words must reach
    WORD_FLOOR_SHARE of the plan's planned words and the voiced time must reach
    VOCAL_TIME_FLOOR_SHARE of the plan's planned voice seconds. TEXT COVERAGE
    (``text_coverage_gate``) keeps its own 0.98 floor and its OWN denominator
    (the approved word count), separate from the 0.90 word and 0.85 voice
    floors -- the three are never folded into one number.

EVERY NUMBER BELOW IS A NEW ACCEPTANCE RULE set by this fix. None is a measured
limit of the failed run; the measured numbers above are only the target the
rules are aimed at.

NEW PROPOSED (not the owner's): OPENING_VOCALISE_MAX_S = 3.0 and TEXT_COVERAGE_MIN
= 0.98. They are proposals, never values credited to Trevor.

stdlib only; pure; no network, no spend.
"""
from __future__ import annotations

import re

TOOL_NAME = "story_coverage"
SCHEMA = "blackceo.story-coverage/v1"

#: NEW ACCEPTANCE RULES (WWFIX 2026-10-11). The failed run's own numbers are in
#: the module docstring; these ceilings and floors are chosen by this fix.
FIRST_STORY_WORD_MAX_S = 5.0           # R1: ABSOLUTE seconds, not a share of D
PLOT_LINE_MIN_WORDS = 4                # a "line" is a run, never one stray word
PLOT_LINE_CEILING_S = 10.0             # retained: the old looser plot-line ceiling
#: WW-02 (NEW PROPOSED): the absolute opening-wordless ceiling. Its span is
#: measured from the take's own FIRST ALIGNED ROW to the first approved story
#: line, so a 13.7 s wordless vocalise inside the take is refused.
OPENING_VOCALISE_MAX_S = 3.0           # R1: ABSOLUTE seconds of wordless opening
#: main's WWFIX-U1 opening rule, KEPT ALONGSIDE the absolute ceiling above: the
#: first LEXICAL word must not land after this SHARE of the delivered seconds.
#: It is the looser of the two and it is what judges the lead-in before a take's
#: own first aligned row -- audio the alignment carries no evidence for. The
#: merged ``story_start_gate`` fails on EITHER rule, so nothing main measured is
#: lost and no take that main refused can pass here.
OPENING_WORDLESS_SHARE_MAX = 0.15      # R1: opening wordless span, share of D
LEXICAL_COVERAGE_MIN = 0.70            # R2: lexical time / duration, no vocalise
STORY_ARC_WINDOW_MIN_S = 5.0           # story arc: the shortest window that counts
WORD_FLOOR_SHARE = 0.90                # delivered words / planned words
VOCAL_TIME_FLOOR_SHARE = 0.85          # voiced seconds / planned voice seconds
#: WW-05 (NEW PROPOSED): the separate 98% TEXT-coverage floor. Its own
#: denominator is the approved normalized word count, never the lexical seconds.
TEXT_COVERAGE_MIN = 0.98

#: The three gates named above are gate names the take judge reports.
GATES = ("story_start", "lexical_coverage", "story_arc", "words_floor")

#: Tokens that are vocal sound, not story: "oo-o-o-o-o-oh", "oh", "la-la", "mmm".
VOCALISE_RE = re.compile(
    r"^(?:o+h*|o+w*|a+h+|e+h+|mmm*|hmm*|na+|la+|da+|yeah*|whoa*|woah*|hey*)$",
    re.IGNORECASE)

#: Section tags that are NOT the plot: the opener line, the closing call to
#: action and the wordless vocalise. Everything else on the sheet is the story.
NON_PLOT_TAGS = ("intro", "outro", "vocalise", "end", "instrumental")

_WORD_STRIP = re.compile(r"[^a-z']")
_ALPHA_STRIP = re.compile(r"[^a-z]")


class CoverageError(ValueError):
    """Malformed evidence; a gate that cannot read its input never passes."""


def is_vocalise(token):
    """True for a wordless vocal sound (case, punctuation and repeats folded).

    WW-02: punctuation must not defeat the test -- the stored vocalise renders
    as "Oo-oh," and a trailing comma used to make it read as a lexical story
    word, which is exactly how a 13.7 s wordless span certified coverage.
    """
    t = re.sub(r"[-'`’]", "", str(token or "")).strip().lower()
    if not t:
        return True
    core = _ALPHA_STRIP.sub("", t)
    if not core:
        return True
    # a chain of the same letter run together ("ooooooh", "ahhhhh")
    if re.fullmatch(r"(.)\1{2,}", core):
        return True
    return bool(VOCALISE_RE.match(core))


def is_lexical(token):
    """A REAL story word: not a vocalise, not a bare non-word, and never a
    piece of section MARKUP.

    WWFIXGAPS U1: a bracketed section tag or marker is not story text. Suno
    splits a long tag across rows ('[Instrumental ' / 'Break]') and leaves the
    closing fragment of the '[End]' marker alone on a row ('...[' then 'End]'),
    so the middle and tail fragments carry letters and used to read as lexical
    story words: they inflated ``lexical_seconds`` and could fill a story-arc
    window. Any token holding a bracket is markup, never a story word.
    """
    raw = str(token or "")
    if "[" in raw or "]" in raw:
        return False
    t = re.sub(r"[-'`’]", "", raw).strip()
    if not t or is_vocalise(raw):
        return False
    return bool(re.search(r"[a-z]", t, re.IGNORECASE))


def _markup_rows(aligned_words):
    """Indices of aligned rows that lie INSIDE a bracketed tag/marker.

    A row that merely OPENS a tag keeps its lyric word ('[Hook (sung): …]'
    then 'Girl, '), so only a row that STARTS inside an open ``[...]`` span is
    dropped whole: that is exactly the split case the row-level token test
    above cannot see ('[Instrumental ' then 'Break]')."""
    depth, out = 0, set()
    for i, w in enumerate(aligned_words or []):
        if not isinstance(w, dict):
            continue
        inside = depth > 0
        raw = str(w.get("word") or "")
        depth += raw.count("[") - raw.count("]")
        if depth < 0:
            depth = 0
        if inside:
            out.add(i)
    return out


# ---- reading the alignment -------------------------------------------------

def _start(w):
    return w.get("startS", w.get("start", w.get("start_s")))


def _end(w):
    return w.get("endS", w.get("end", w.get("end_s")))


def _tok(w):
    """The word text, with Suno's inline section header dropped.

    WW-22: UNCHANGED, on purpose. The header-drop rule this module shipped --
    the last newline-separated segment -- is what an ALIGNED row's own token is
    (Suno puts the section tag before the break and the lyric after it), and a
    row that ends on a break carries the segment Suno emitted there. The
    lexical-token preservation WW-22 asks for already holds through the
    PUBLIC token API this module matches on: ``is_lexical("up\\n\\n")`` is True,
    ``_norm("up\\n\\n")`` is "up" and ``words_of("up\\n\\n")`` is ["up"], so a
    trailing break never erases a token on the SHEET path. ``_norm`` is applied
    only to a token that has already had its header dropped, never to a raw
    row, so "[Verse 1 (rap): ...]\\nI " normalizes to "i", not to the tag."""
    return str((w or {}).get("word") or "").split("\n")[-1]


def _norm(tok):
    """A word for matching: lowercase, apostrophes kept, punctuation dropped."""
    return _WORD_STRIP.sub("", str(tok or "").lower())


def _lines(w):
    """True when this aligned word starts a NEW lyric line (Suno carries the
    section/line break inline as a leading newline)."""
    return "\n" in str((w or {}).get("word") or "")


def aligned_lexical_words(aligned_words):
    """[(start_s, end_s, word)] for every aligned word that is real story,
    in time order. A vocalise is skipped, so is anything with no usable time,
    and so is any row that is section MARKUP (a tag or the split '[End]'
    marker: see is_lexical / _markup_rows)."""
    out = []
    markup = _markup_rows(aligned_words)
    for i, w in enumerate(aligned_words or []):
        if not isinstance(w, dict) or i in markup:
            continue
        tok = _tok(w)
        if not is_lexical(tok):
            continue
        s, e = _start(w), _end(w)
        if not isinstance(s, (int, float)) or isinstance(s, bool):
            continue
        if not isinstance(e, (int, float)) or isinstance(e, bool) or e < s:
            e = s
        out.append((float(s), float(e), tok))
    return sorted(out)


def words_of(text):
    """The lexical words of a piece of lyric text, lowercased, apostrophes kept."""
    return [_norm(t) for t in str(text or "").split()
            if is_lexical(t)]


def plot_lines_from_sheet(sheet_text):
    """The APPROVED PLOT as ORDERED LINES: every line that is not the opener,
    the closing call to action or a wordless vocalise, each a list of plot
    words in the sheet's own order.

    The order is load-bearing (WW-02): the story gate matches a RUN OF ONE
    APPROVED LINE, in order, so four repeated filler tokens can never stand in
    for the plot. Reads the sheet with the repository's ONE tag grammar
    (``suno_recipe.parse_lyrics``)."""
    import suno_recipe as _RP
    parse_lyrics = getattr(_RP, "parse_lyrics", None) or _RP.suno_recipe.parse_lyrics
    lines = []
    for sec in parse_lyrics(sheet_text):
        tag = str(sec.get("tag") or "").strip().lower()
        if any(tag.startswith(t) or tag == t for t in NON_PLOT_TAGS):
            continue
        for line in sec["lines"]:
            ws = words_of(line)
            if ws:
                lines.append(ws)
    return lines


def plot_words_from_sheet(sheet_text):
    """The APPROVED PLOT vocabulary (a set), kept for back-compat reporting.
    The story START is measured on ``plot_lines_from_sheet`` (an ordered run),
    NEVER on this vocabulary membership set."""
    out = set()
    for ws in plot_lines_from_sheet(sheet_text):
        out.update(ws)
    return out


def _plot_lines(plot):
    """Approved plot lines from a caller's ``plot``.

    Accepts a list of word-lists (ordered), or a flat list/set of words. A flat
    list is ONE approved line; a bare set has no order, so it is sorted -- a
    caller that needs the order must pass lines (or a flat list)."""
    if not plot:
        return []
    if isinstance(plot, (set, frozenset)):
        return [sorted(_norm(w) for w in plot if _norm(w))]
    items = list(plot)
    if all(isinstance(x, str) for x in items):
        line = [_norm(x) for x in items]
        return [[w for w in line if w]]
    lines = []
    for x in items:
        if isinstance(x, (list, tuple)):
            ws = [_norm(w) for w in x]
            ws = [w for w in ws if w]
            if ws:
                lines.append(ws)
    return lines


# ---- gate 1: story start ---------------------------------------------------

def first_plot_word_s(aligned_words, plot):
    """Seconds of the first aligned word that belongs to the approved PLOT
    vocabulary. Reporting only: it is NOT the gate (a stray word is not a
    line). None when the plot never lands."""
    want = set()
    for line in _plot_lines(plot):
        want.update(line)
    if not want:
        return None
    for s, _e, tok in aligned_lexical_words(aligned_words):
        if _norm(tok) in want:
            return round(s, 3)
    return None


def first_plot_line_s(aligned_words, plot, min_words=PLOT_LINE_MIN_WORDS):
    """Seconds at which the first run of at least ``min_words`` consecutive
    APPROVED plot words, IN ORDER -- a contiguous slice of one approved line,
    never a vocabulary membership test -- begins, or None.

    WW-02: the membership version returned 1.0 s for four repeated filler
    tokens; a run matched against an approved LINE cannot, because the filler
    is not a slice of the approved line."""
    lines = _plot_lines(plot)
    if not lines:
        raise CoverageError("plot is empty; nothing to look for")
    toks = [(s, _norm(tok)) for s, _e, tok in aligned_lexical_words(aligned_words)]
    # WW-22: the ONE ordered matcher, shared with the text-coverage gate. The
    # token list is time-ordered, so the first matching INDEX is the first
    # matching START in seconds -- the same value the inline loop returned.
    idx = ordered_run_match(lines, [t[1] for t in toks], min_words=min_words)
    if idx is None:
        return None
    return round(toks[idx][0], 3)


def _opening_non_lexical_s(aligned_words):
    """main's WWFIX-U1 opening measurement, KEPT: the seconds of the opening
    wordless span, from 0.0 to the first aligned word that is REAL story. None
    when no lexical word was measured.

    Private because it is the measurement of the SOFTER rule (the share rule
    ``story_start_gate`` still applies); the harder, absolute rule is
    :func:`longest_opening_wordless_s`."""
    lex = aligned_lexical_words(aligned_words)
    return None if not lex else round(lex[0][0], 3)


def _first_aligned_start_s(aligned_words):
    """The earliest startS of any aligned row (lexical or not), or None.

    It is the take's own measured extent: the lead-in before it carries no
    alignment evidence at all."""
    base = None
    for row in aligned_words or []:
        if not isinstance(row, dict):
            continue
        raw = row.get("startS", row.get("start"))
        try:
            s = float(raw)
        except (TypeError, ValueError):
            continue
        if s != s or s in (float("inf"), float("-inf")):
            continue
        base = s if base is None else min(base, s)
    return base


def longest_opening_wordless_s(aligned_words, first_story_line_start_s):
    """The longest contiguous span, measured FROM THE TAKE'S OWN FIRST ALIGNED
    ROW to ``first_story_line_start_s``, that contains NO lexical aligned word
    (WW-02), in seconds.

    A wordless vocalise ("Oo-oh") is not lexical, so it counts as a gap: on
    the stored take this is the span from the last filler word's end (8.299 s)
    to the story line at 22.107 s, 13.808 s -- where the softer
    ``_opening_non_lexical_s`` measurement (0 to the first LEXICAL word) read
    only 3.75 s and passed the wordless opening.

    The scan starts at the first aligned row, not at 0.0: the lead-in before a
    take's first measured row is audio this gate has NO alignment for, and it
    is judged by the share rule (``OPENING_WORDLESS_SHARE_MAX``) instead.
    Returns 0.0 when the story line starts at or before that first row."""
    if first_story_line_start_s is None:
        return None
    end = float(first_story_line_start_s)
    base = _first_aligned_start_s(aligned_words)
    if base is None:
        return None
    if end <= base:
        return 0.0
    spans = []
    for s, e, _t in aligned_lexical_words(aligned_words):
        s2, e2 = max(base, s), min(e, end)
        if e2 > s2:
            spans.append((s2, e2))
    spans.sort()
    gap, cur = 0.0, base
    for s, e in spans:
        if s > cur:
            gap = max(gap, s - cur)
        cur = max(cur, e)
    if end > cur:
        gap = max(gap, end - cur)
    return round(gap, 3)


def story_start_gate(aligned_words, plot, delivered_s,
                     max_s=FIRST_STORY_WORD_MAX_S,
                     opening_max_s=OPENING_VOCALISE_MAX_S,
                     opening_share=OPENING_WORDLESS_SHARE_MAX,
                     min_words=PLOT_LINE_MIN_WORDS):
    """PASS / FAIL / UNAVAILABLE on how soon the STORY starts.

    THE MEASUREMENT IS THE APPROVED PLOT LINE, not the first stray word and
    never a vocabulary membership test: a RUN of at least ``min_words``
    consecutive words of ONE approved plot line, in order. That is what stops
    the filler opener ("I'm still up"), a wordless vocalise, and four repeated
    filler tokens from being read as the story starting.

    FAIL when that first plot line lands after ``max_s`` (an ABSOLUTE 5.0 s,
    never a share of the length). Two opening rules then apply and the gate
    fails on EITHER:

      * ``opening_max_s`` (WW-02, an ABSOLUTE 3.0 s): the longest wordless span
        between the take's own first aligned row and the story line;
      * ``opening_share`` (main's WWFIX-U1 rule, kept): the first LEXICAL word
        must not land after this share of the delivered seconds.

    A take with no measurable plot line at all is FAIL, never PASS. Missing
    evidence is UNAVAILABLE."""
    if not aligned_words:
        return {"verdict": "UNAVAILABLE", "reason_code": "NO_ALIGNED_WORDS",
                "detail": "no aligned words: the story start cannot be measured",
                "ceiling_s": max_s, "opening_ceiling_s": opening_max_s}
    lines = _plot_lines(plot)
    if not lines:
        return {"verdict": "UNAVAILABLE", "reason_code": "NO_PLOT_TEXT",
                "detail": "the sheet names no plot line; nothing to measure",
                "ceiling_s": max_s, "opening_ceiling_s": opening_max_s}
    D = float(delivered_s or 0.0)
    line = first_plot_line_s(aligned_words, lines, min_words=min_words)
    loose = first_plot_word_s(aligned_words, lines)
    lead = _opening_non_lexical_s(aligned_words)
    opening = None
    fails = []
    if line is None:
        fails.append("NO_PLOT_LINE_SUNG")
    else:
        if line > max_s:
            fails.append("FIRST_STORY_WORD_LATE")
        opening = longest_opening_wordless_s(aligned_words, line)
        if opening is not None and opening > opening_max_s:
            fails.append("OPENING_VOCALISE_TOO_LONG")
    # main's WWFIX-U1 share rule, KEPT: the first LEXICAL word must not land
    # after ``opening_share`` of the delivered seconds. Failing on EITHER rule
    # means main's refusals are a subset of this gate's refusals.
    if D > 0 and lead is not None and lead > opening_share * D:
        fails.append("OPENING_NON_LEXICAL_TOO_LONG")
    return {
        "verdict": "FAIL" if fails else "PASS",
        "reason_code": fails[0] if fails else "STORY_STARTS_IN_TIME",
        "failed": fails,
        "first_story_word_s": line,
        "first_plot_line_s": line,
        "first_plot_word_s": loose,
        "opening_wordless_s": opening,
        "opening_non_lexical_s": lead,
        "opening_vocalise_max_s": opening_max_s,
        "opening_ceiling_s": opening_max_s,
        "opening_share_ceiling_s": round(opening_share * D, 3),
        "plot_line_min_words": min_words,
        # WW-22: the EXACT approved opening line (ordered, repeats kept) rides
        # in this gate's context, so a caller measures an onset against the
        # approved LINE, never against a vocabulary. The onset itself is
        # assessed by audio gate D2, never here.
        "approved_opening_line": list(lines[0]) if lines else [],
        "approved_opening_line_ordered": True,
        # WW-22: no onset is claimed here. The delivered ONSET on the take is
        # audio gate D2's measurement, never this pre/post story context.
        "delivered_onset_owner": "D2",
        "ceiling_s": max_s,
        "detail": ("first approved plot line %s (ceiling %.1f s), first plot word "
                   "%s, opening wordless %s s, longest opening wordless span %s s "
                   "(ceiling %.1f s)"
                   % ("n/a" if line is None else "%.3f s" % line, max_s,
                      "n/a" if loose is None else "%.3f s" % loose,
                      "n/a" if lead is None else "%.3f s" % lead,
                      "n/a" if opening is None else "%.3f s" % opening,
                      opening_max_s)),
        "thresholds_are_new_acceptance_rules": True,
        "source": ("WW-02: absolute first-story-LINE ceiling + absolute "
                   "OPENING_VOCALISE_MAX_S ceiling, with main's WWFIX-U1 "
                   "OPENING_WORDLESS_SHARE_MAX opening rule kept alongside "
                   "(the gate fails on either)"),
    }


# ---- gate 2: lexical coverage ---------------------------------------------

def _clip_union(spans, lo, hi):
    """Union length of ``spans`` clipped to ``[lo, hi]``; overlaps once."""
    clipped = []
    for s, e in spans:
        s2, e2 = max(float(s), lo), min(float(e), hi)
        if e2 > s2:
            clipped.append((s2, e2))
    clipped.sort()
    total, cur_s, cur_e = 0.0, None, None
    for s, e in clipped:
        if cur_s is None:
            cur_s, cur_e = s, e
        elif s <= cur_e:
            cur_e = max(cur_e, e)
        else:
            total += cur_e - cur_s
            cur_s, cur_e = s, e
    if cur_s is not None:
        total += cur_e - cur_s
    return total


def _lexical_union_raw(aligned_words, duration_s=None, voice_intervals=None):
    """The RAW (unrounded) in-bounds, voice-intersected lexical union."""
    spans = []
    for s, e, _t in aligned_lexical_words(aligned_words):
        try:
            s, e = float(s), float(e)
        except (TypeError, ValueError):
            continue
        if s != s or e != e or s in (float("inf"), float("-inf")) \
                or e in (float("inf"), float("-inf")):
            continue
        spans.append((s, e))
    if voice_intervals:
        voice = sorted((float(a), float(b)) for a, b in voice_intervals)
        inter = []
        for s, e in spans:
            for a, b in voice:
                s2, e2 = max(s, a), min(e, b)
                if e2 > s2:
                    inter.append((s2, e2))
        spans = inter
    lo = 0.0
    hi = float("inf") if duration_s is None else float(duration_s)
    return _clip_union(spans, lo, hi)


def lexical_seconds(aligned_words, duration_s=None, voice_intervals=None):
    """The union of the real lexical word intervals, in seconds (WW-05).

    A vocalise contributes nothing; overlapping intervals are counted once.
    With ``duration_s`` the union is IN-BOUNDS: intervals are clipped to
    ``[0, duration_s]``, so a malformed far-out-of-range interval (100-200 s
    over 88 s of audio) clips to nothing and cannot inflate the coverage. With
    ``voice_intervals`` the union is INTERSECTED with the measured voice, so
    only words over audible voice count. Non-finite intervals are dropped."""
    return round(_lexical_union_raw(aligned_words, duration_s, voice_intervals), 3)


def lexical_coverage_gate(aligned_words, delivered_s, floor=LEXICAL_COVERAGE_MIN,
                          voice_intervals=None):
    """PASS / FAIL / UNAVAILABLE on how much of the ad actually carries words.

    ``lexical_seconds(aligned_words, delivered_s, voice_intervals) / delivered_s
    >= floor`` (0.70), compared RAW (never rounded before the comparison). No
    vocalise is counted; the union is in-bounds and intersected with the
    measured voice when one is given. Unmeasured input is UNAVAILABLE, never
    PASS."""
    D = float(delivered_s or 0.0)
    if D <= 0 or not aligned_words:
        return {"verdict": "UNAVAILABLE", "reason_code": "COVERAGE_UNMEASURED",
                "lexical_s": None, "delivered_s": D or None, "floor": floor,
                "detail": "the delivered duration or the alignment is missing"}
    raw = _lexical_union_raw(aligned_words, duration_s=D,
                             voice_intervals=voice_intervals)
    secs = round(raw, 3)
    share = raw / D                        # RAW: no rounding before the compare
    owed = round(floor * D, 3)
    passed = share >= floor
    return {
        "verdict": "PASS" if passed else "FAIL",
        "reason_code": "LEXICAL_COVERAGE_MET" if passed
                       else "LEXICAL_COVERAGE_BELOW_FLOOR",
        "lexical_s": secs, "delivered_s": round(D, 3), "owed_s": owed,
        "coverage": round(share, 4), "coverage_raw": share, "floor": floor,
        "in_bounds_union": True,
        "voice_intersected": bool(voice_intervals),
        "vocalise_counted": False,
        "detail": ("%.3f s of real words over %.3f s delivered (%.1f%%, floor "
                   "%.0f%%: %.3f s owed); in-bounds union, no vocalise counted"
                   % (secs, D, share * 100, floor * 100, owed)),
        "thresholds_are_new_acceptance_rules": True,
        "source": ("WW-05: the separate lexical-coverage gate (0.70, in-bounds "
                   "voice-intersected union, raw comparison)"),
    }


def _norm_tokens(seq):
    """Lowercased alphanumeric words from a string or an iterable of words.

    A non-text input (a bare word COUNT, a number, a dict) normalizes to no
    tokens rather than raising: the gate above turns that into its own
    UNAVAILABLE/FAIL, never into a traceback."""
    if isinstance(seq, str):
        return [w for w in re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?", seq.lower())]
    if not isinstance(seq, (list, tuple, set, frozenset)):
        return []
    out = []
    for x in seq:
        out.extend(re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?", str(x).lower()))
    return out


def normalize_approved_words(approved):
    """The APPROVED words as an ORDERED sequence, with REPEATS KEPT (WW-22).

    The approved side of a match is a SEQUENCE, never a vocabulary. A set or
    frozenset carries no order, so it is REFUSED (no words) rather than sorted
    into an order the sheet never had; a string or a flat list/tuple of words
    is read left to right and every repeat is kept. A caller that needs an
    ordered match must hand over an ordered input."""
    if isinstance(approved, (set, frozenset)):
        return []
    if isinstance(approved, str):
        return _norm_tokens(approved)
    if not isinstance(approved, (list, tuple)):
        return []
    out = []
    for x in approved:
        out.extend(_norm_tokens(x))
    return out


def ordered_match(approved, observed):
    """Match the APPROVED words against the OBSERVED words IN ORDER (WW-22).

    Greedy left-to-right: each approved word is looked for at or after the
    observed cursor, and the cursor advances past each hit. Returns
    {"matched", "covered", "approved_n", "observed_n", "coverage", "refusal",
    "approved"}.

    Never a set-membership or multiset test, which is what this replaces: a
    ``Counter`` pool counted the SAME coverage for "two for cooked i" as for
    "i cooked for two", so reversed words covered the approved line. Here the
    approved words are consumed IN ORDER, so four repeated filler tokens
    ("i i i i") cover one approved word and reversed words cover one -- both
    refused. Vocables are not on the approved side by construction (the sheet's
    plot lines carry real words only) and never match a real approved word.

    A set/frozenset on EITHER side is refused along with the match: it carries
    no order to match against, which is the whole point of this function."""
    ap = normalize_approved_words(approved)
    if isinstance(observed, (set, frozenset)):
        ob = []
    elif isinstance(observed, str):
        ob = _norm_tokens(observed)
    elif isinstance(observed, (list, tuple)):
        ob = []
        for x in observed:
            ob.extend(_norm_tokens(x))
    else:
        ob = []
    covered, i = 0, 0
    for w in ap:
        while i < len(ob):
            hit = ob[i] == w
            i += 1
            if hit:
                covered += 1
                break
    n = len(ap)
    return {
        "matched": bool(n) and covered == n,
        "covered": covered,
        "approved_n": n,
        "observed_n": len(ob),
        "coverage": (covered / n) if n else 0.0,
        "refusal": ("" if (n and covered == n)
                    else ("empty approved sequence" if not n
                          else "approved words not carried in order (%d of %d)"
                               % (covered, n))),
        "approved": ap,
        "ordered": True,
        "repeats_kept": True,
        "source": "WW-22: ordered, repeats kept; never set membership",
    }


def ordered_run_match(approved_lines, observed_tokens, min_words=PLOT_LINE_MIN_WORDS):
    """The index of the FIRST observed token that opens a CONTIGUOUS run of at
    least ``min_words`` words of ONE approved line, IN ORDER; None when there
    is no such run (WW-22).

    The run is a contiguous slice of ONE approved line matched against a
    contiguous slice of the observed tokens: not a vocabulary membership test
    and not a subsequence. Repeats are retained on both sides, so four repeated
    filler tokens never stand in for the approved line. This is the ONE ordered
    matcher the story gates use; ``first_plot_line_s`` maps its index to a
    timestamp."""
    lines = []
    for ln in (approved_lines or []):
        ws = [str(w) for w in ln] if isinstance(ln, (list, tuple)) else _norm_tokens(ln)
        lines.append([n for n in (_norm(w) for w in ws) if n])
    toks = _norm_tokens(observed_tokens)
    best = None
    for line in lines:
        if len(line) < min_words:
            continue
        for j in range(0, len(line) - min_words + 1):
            win = line[j:j + min_words]
            n = len(win)
            for i in range(0, len(toks) - n + 1):
                if toks[i:i + n] == win:
                    if best is None or i < best:
                        best = i
                    break
    return best


def approved_opening_line(sheet_text):
    """The EXACT approved opening story line, as its ORDERED words (WW-22).

    The opening PLOT line of the sheet -- the first line under a section that
    is not the opener, the closing call to action or a wordless vocalise --
    normalized to lowercase words with REPEATS KEPT and the sheet's own order
    preserved. This is the value carried into the request/evidence context so
    an onset is measured against the APPROVED line, never against a vocabulary.

    Returns {"line": [...], "lines_considered": n, "ordered": True,
    "repeats_kept": True, "source": ...}; "line" is [] when the sheet names no
    plot line, which the caller reports as UNAVAILABLE, never as a pass."""
    lines = plot_lines_from_sheet(sheet_text)
    return {"line": list(lines[0]) if lines else [],
            "lines_considered": len(lines),
            "ordered": True,
            "repeats_kept": True,
            "source": "WW-22: the approved opening story line, exact and ordered"}


def delivered_words_ordered(sections):
    """The sheet's delivered lyric words IN ORDER, headers/tags excluded.

    ``sections`` is ``song_contract.parse_sections`` output (or anything shaped
    like it): [{"lines": [...]}]. The words are read line by line, in the
    sheet's own order, so an ordered match runs against what the request asks
    Suno to deliver -- not against a sorted vocabulary."""
    out = []
    for s in sections or []:
        if not isinstance(s, dict):
            continue
        for ln in (s.get("lines") or []):
            out.extend(words_of(ln))
    return out


def text_coverage_gate(approved_words, observed_words=None,
                       floor=TEXT_COVERAGE_MIN):
    """The 98% TEXT-coverage gate, kept SEPARATE from the 0.90 word-retention
    and 0.85 voice-retention floors (WW-05).

    Its own denominator is the APPROVED normalized word count -- text against
    text -- never the lexical seconds and never the runtime. Returns
    PASS / FAIL, or UNAVAILABLE when an input the gate needs is ABSENT: a
    missing argument is never a PASS (ORCH-DEFECTS-0710b)."""
    if approved_words is None or observed_words is None:
        return {"verdict": "UNAVAILABLE", "reason_code": "TEXT_EVIDENCE_MISSING",
                "text_coverage": None, "approved_n": 0, "floor": floor,
                "denominator": "approved normalized words (text)",
                "detail": "the approved text or the observed text is absent: "
                          "the 0.98 text floor cannot be measured"}
    approved = normalize_approved_words(approved_words)
    observed = _norm_tokens(observed_words)
    if not approved:
        return {"verdict": "UNAVAILABLE", "reason_code": "NO_APPROVED_TEXT",
                "text_coverage": None, "approved_n": 0, "floor": floor,
                "denominator": "approved normalized words (text)",
                "detail": "no approved text to cover"}
    # WW-22: the coverage is ORDERED, never a multiset pool. The greedy
    # left-to-right scan is what the Counter could not do -- it refuses reversed
    # words and repeated filler that a pool count accepted as full coverage.
    m = ordered_match(approved, observed)
    covered, share = m["covered"], m["coverage"]
    passed = share >= floor
    return {
        "verdict": "PASS" if passed else "FAIL",
        "reason_code": "TEXT_COVERAGE_MET" if passed
                       else "TEXT_COVERAGE_BELOW_FLOOR",
        "text_coverage": round(share, 4), "coverage_raw": share,
        "approved_n": len(approved), "covered_n": covered, "floor": floor,
        "matched_in_order": m["matched"], "ordered": True,
        "denominator": "approved normalized words (text), separate from the "
                       "0.90 word and 0.85 voice floors",
        "detail": ("%d of %d approved words present IN ORDER (%.1f%%, floor "
                   "%.0f%%)" % (covered, len(approved), share * 100, floor * 100)),
        "thresholds_are_new_acceptance_rules": True,
        "source": ("WW-05: 0.98 text coverage with its own denominator; "
                   "WW-22: matched IN ORDER, never a multiset pool"),
    }


# ---- gate 3: the story arc ------------------------------------------------

def story_arc_gate(aligned_words, beats_u16, delivered_s,
                   window_s=STORY_ARC_WINDOW_MIN_S, min_words=1):
    """PASS / FAIL / UNAVAILABLE: every beats_u16 window of at least
    ``window_s`` seconds carries at least one measured lexical line.

    ``beats_u16`` is the story arc: a list of beat records (a mapping with
    ``start_s``/``end_s``, or a ``(start, end)`` pair, or anything the plan's
    ``length_formula.STORY_ARC_U16`` emits). Window boundaries are snapped onto
    the beats, and only windows at least ``window_s`` long are judged -- a
    shorter closing beat is not a hole. A window with no lexical word is
    ``NO_WORDS_IN_WINDOW`` and FAILS. Missing evidence is UNAVAILABLE."""
    windows = _windows(beats_u16, float(delivered_s or 0.0))
    if not windows or not aligned_words:
        return {"verdict": "UNAVAILABLE", "reason_code": "ARC_UNMEASURED",
                "windows": len(windows), "window_s": window_s,
                "detail": "the story arc or the alignment is missing"}
    lex = [(s, e) for s, e, _t in aligned_lexical_words(aligned_words)]
    holes, rows = [], []
    for i, (a, b) in enumerate(windows):
        if b - a < window_s:
            continue
        n = sum(1 for s, e in lex if s < b and e > a)
        rows.append({"beat": i, "start_s": round(a, 3), "end_s": round(b, 3),
                     "lexical_words": n})
        if n < min_words:
            holes.append(i)
    if not rows:
        return {"verdict": "UNAVAILABLE", "reason_code": "NO_JUDGEABLE_WINDOW",
                "windows": 0, "window_s": window_s,
                "detail": "no story-arc window is at least %.1f s long" % window_s}
    return {
        "verdict": "FAIL" if holes else "PASS",
        "reason_code": "STORY_ARC_HAS_WORDLESS_WINDOW" if holes else STORY_ARC_CODE_OK,
        "failed_windows": holes,
        "windows": rows,
        "window_s": window_s,
        "detail": ("%d window(s) carry no lexical word: %s"
                   % (len(holes), holes) if holes else
                   "every window >= %.1f s carries a measured lexical line" % window_s),
        "thresholds_are_new_acceptance_rules": True,
        "source": "WWFIX D1: every beats_u16 window carries a measured line",
    }


STORY_ARC_CODE_OK = "STORY_ARC_COVERED"


def _windows(beats_u16, delivered_s):
    """[(start_s, end_s)] from a beats list, or the even split of delivered_s
    when the arc is a bare beat count. Never raises on a missing arc."""
    if isinstance(beats_u16, int) and not isinstance(beats_u16, bool):
        n = beats_u16
        if n <= 0 or delivered_s <= 0:
            return []
        step = delivered_s / float(n)
        return [(i * step, min((i + 1) * step, delivered_s)) for i in range(n)]
    out = []
    for b in beats_u16 or []:
        if isinstance(b, dict):
            s = b.get("start_s", b.get("start"))
            e = b.get("end_s", b.get("end"))
        elif isinstance(b, (list, tuple)) and len(b) >= 2:
            s, e = b[0], b[1]
        else:
            continue
        if isinstance(s, (int, float)) and isinstance(e, (int, float)) \
                and not isinstance(s, bool) and not isinstance(e, bool) and e > s:
            out.append((float(s), float(e)))
    return out


# ---- gate 4: words versus ad length ---------------------------------------

def words_floor(plan, delivered_words=None, vocal_seconds=None,
                word_share=WORD_FLOOR_SHARE, time_share=VOCAL_TIME_FLOOR_SHARE):
    """PASS / FAIL / UNAVAILABLE on words versus ad length.

    The floor: delivered words >= ``word_share`` of the plan's planned word
    total, and voiced seconds >= ``time_share`` of the plan's planned voice
    seconds (spoken + rap + sung). Unmeasured inputs are UNAVAILABLE, never a
    pass. The failed run's 58.416 figure is split here: the plan's own
    ``intro_outro_s`` is MUSIC-ONLY and is never part of the voice seconds."""
    planned_words = ((plan or {}).get("words") or {}).get("total")
    if not isinstance(planned_words, (int, float)) or planned_words <= 0:
        raise CoverageError("plan.words.total is missing or not positive")
    planned_voice = planned_voice_s(plan)
    if delivered_words is None or vocal_seconds is None:
        return {"verdict": "UNAVAILABLE", "reason_code": "WORDS_UNMEASURED",
                "planned_words": planned_words, "planned_voice_s": planned_voice,
                "word_share": word_share, "time_share": time_share,
                "detail": "delivered words or voiced seconds were not measured"}
    w_share = round(float(delivered_words) / planned_words, 4)
    t_share = round(float(vocal_seconds) / planned_voice, 4) if planned_voice else 0.0
    fails = []
    if w_share < word_share:
        fails.append("WORD_FLOOR_MISSED")
    if t_share < time_share:
        fails.append("VOCAL_TIME_FLOOR_MISSED")
    return {
        "verdict": "FAIL" if fails else "PASS",
        "reason_code": fails[0] if fails else "WORDS_MEET_FLOOR",
        "failed": fails,
        "delivered_words": delivered_words,
        "planned_words": planned_words,
        "word_share": w_share,
        "word_floor_share": word_share,
        "vocal_seconds": vocal_seconds,
        "planned_voice_s": planned_voice,
        "time_share": t_share,
        "time_floor_share": time_share,
        "detail": ("%d words of %d planned (%.1f%%, floor %.0f%%); %.1f s voiced of "
                   "%.1f s planned (%.1f%%, floor %.0f%%)"
                   % (delivered_words, planned_words, w_share * 100, word_share * 100,
                      vocal_seconds, planned_voice, t_share * 100, time_share * 100)),
        "thresholds_are_new_acceptance_rules": True,
        "source": "WWFIX D1: words-versus-ad-length hard gate with a stated floor",
    }


def planned_voice_s(plan):
    """The plan's planned VOICE seconds: spoken + rap + sung. Music-only time
    (``intro_outro_s``) is deliberately NOT included."""
    words = ((plan or {}).get("words") or {})
    rates = {"spoken": 1.4, "sung": 1.07, "rap": 2.0}
    try:
        import words_fit as _WF
        rates = dict(_WF.DEFAULT_RATES)
    except Exception:  # noqa: BLE001 - rates unavailable: the plan's own numbers stand
        pass
    total = 0.0
    for key in ("spoken", "rap", "sung"):
        n = words.get(key)
        if isinstance(n, (int, float)) and not isinstance(n, bool) and n > 0:
            total += float(n) / rates.get(key, 1.0)
    return round(total, 3)


# ---- the words-versus-music label -----------------------------------------

def coverage_report(vocal_words_s, music_only_s, intro_outro_s=None):
    """The two figures the failed summary conflated, under separate labels.

    ``vocal_words_s`` is the words figure; ``music_only_s`` is music time. They
    are returned separately and their sum is labelled as a TOTAL, never as
    words. This is the fix for "58.4 s of words": 50.416 s of words plus 8 s of
    music-only time is 58.416 s of RUNTIME, not of words."""
    words = round(float(vocal_words_s), 3)
    music = round(float(music_only_s), 3)
    return {
        "schema": SCHEMA,
        "vocal_words_s": words,
        "music_only_s": music,
        "intro_outro_s": None if intro_outro_s is None else round(float(intro_outro_s), 3),
        "runtime_s": round(words + music, 3),
        "words_and_music_are_separate_labels": True,
        "label": ("%.3f s of words; %.3f s of music-only time; %.3f s runtime "
                  "(the music-only seconds are NEVER counted as word time)"
                  % (words, music, words + music)),
        "source": "WWFIX: the 58.4 s figure is 50.416 s of words + 8 s of music",
    }


#: WW-24: the rounding tolerance the script report compares labels at -- the
#: same 1e-9 arithmetic ``timing_guard._EPS`` uses, never a new universal rule.
REPORT_EPS = 1e-9


def script_report(lexical_estimate_s, music_only_allowance_s, runtime_s=None,
                  inflated_seconds_of_words=None):
    """WW-24: the SCRIPT report's three figures, under SEPARATE labels.

    ``lexical_estimate_s`` is the estimate of words-in-seconds (a lexical
    estimate, never a measurement of returned audio); ``music_only_allowance_s``
    is the music-only allowance (intro / outro / gaps / end card);
    ``runtime_s`` is their sum. The lexical estimate is NEVER reported as the
    runtime, and the runtime is never reported as "seconds of words".

    ``inflated_seconds_of_words`` is a single combined label a caller may try to
    report ("58.4 s of words"). When it names more than the lexical estimate it
    is the failed-ad shape and is REFUSED with ``INFLATED_SECONDS_OF_WORDS`` --
    words and music-only time must sit under separate labels, and their sum may
    appear only as ``runtime_s``. ``audit_summary_labels`` owns the receipt
    audit; this is the script report's own writer, wired through
    ``judge_returned_take``.
    """
    out = {"schema": SCHEMA,
           "lexical_estimate_s": round(float(lexical_estimate_s), 3),
           "music_only_allowance_s": round(float(music_only_allowance_s), 3),
           "words_and_music_are_separate_labels": True}
    if runtime_s is None:
        runtime_s = out["lexical_estimate_s"] + out["music_only_allowance_s"]
    out["runtime_s"] = round(float(runtime_s), 3)
    if inflated_seconds_of_words is not None:
        inflated = float(inflated_seconds_of_words)
        out["inflated_seconds_of_words"] = round(inflated, 3)
        if inflated > out["lexical_estimate_s"] + REPORT_EPS:
            out["verdict"] = "FAIL"
            out["reason_code"] = "INFLATED_SECONDS_OF_WORDS"
            out["detail"] = ("a single '%.3f s of words' label exceeds the lexical "
                             "estimate %.3f s; report words, music-only time and the "
                             "runtime under separate labels"
                             % (inflated, out["lexical_estimate_s"]))
            return out
    out["verdict"] = "PASS"
    out["reason_code"] = "SEPARATE_FIGURES"
    out["detail"] = ("%.3f s lexical estimate; %.3f s music-only allowance; %.3f s "
                     "runtime (the lexical estimate is NEVER the runtime)"
                     % (out["lexical_estimate_s"], out["music_only_allowance_s"],
                        out["runtime_s"]))
    out["source"] = "WW-24: lexical estimate, music-only allowance and runtime, separate"
    return out


def words_vs_music_figures(plan):
    """The words figure and the music-only figure for a PLAN, under separate
    labels, WIRED to ``coverage_report`` -- the arithmetic is never re-derived
    in a summary (WW-13).

    words = the plan's voice seconds (spoken + rap + sung, no music);
    music = the plan's own ``intro_outro_s``; runtime = their sum."""
    plan = plan or {}
    words_s = planned_voice_s(plan)
    music_s = plan.get("intro_outro_s") or 0.0
    return coverage_report(words_s, music_s, plan.get("intro_outro_s"))


def audit_summary_labels(summary):
    """Audit a summary/receipt: words and music-only time must sit under
    SEPARATE labels, and their sum may appear only as a runtime figure
    (WW-13). FAIL a single label that conflates the two."""
    summary = dict(summary or {})
    words = summary.get("vocal_words_s", summary.get("words_s"))
    music = summary.get("music_only_s", summary.get("music_s"))
    combined = summary.get("seconds_of_words", summary.get("words_seconds"))
    if words is not None and music is not None:
        return {"verdict": "PASS", "reason_code": "SEPARATE_LABELS",
                "words_s": words, "music_only_s": music,
                "detail": "the words figure and the music-only figure are separate labels"}
    if combined is not None:
        return {"verdict": "FAIL",
                "reason_code": "WORDS_AND_MUSIC_UNDER_ONE_LABEL",
                "combined_s": combined,
                "detail": ("a single '%.3f s of words' label sums words and "
                           "music-only time; report them separately and their "
                           "sum only as runtime" % float(combined))}
    return {"verdict": "UNAVAILABLE", "reason_code": "NO_FIGURES",
            "detail": "the summary reports no words and music-only figures"}


# ---- the take judge's seam -------------------------------------------------

def judge_returned_take(take, plan, sheet_text=None, delivered_s=None):
    """The four story gates on one measured take, for ``song_contract``.

    ``take`` carries ``aligned_words`` (Suno's aligned words), optionally
    ``delivered_words`` and ``vocal_seconds``; ``plan`` carries the story arc
    (``beats_u16`` / ``STORY_ARC_U16``) and the word budget. Returns
    {verdict, gates:{name:{...}}, coverage:{...}} where PASS needs every
    applicable gate to PASS and an UNAVAILABLE gate blocks PASS (QC 17.8).
    The story START is measured on the sheet's ORDERED plot lines, and the
    coverage labels ride along from ``coverage_report`` (WW-13).

    The measured voice the take carries is PASSED INTO the lexical gate at the
    call site below (ORCH-DEFECTS-0710a), and the 0.98 TEXT-coverage gate RUNS
    as a member of ``gates`` (ORCH-DEFECTS-0710b): an absent input is
    UNAVAILABLE and blocks PASS, never a silent PASS."""
    take = take or {}
    plan = plan or {}
    D = delivered_s or plan.get("delivered_s") or take.get("duration_s")
    aligned = take.get("aligned_words") or []
    plot = plot_lines_from_sheet(sheet_text) if sheet_text else []
    arc = plan.get("beats_u16") or plan.get("story_arc_u16") or plan.get("STORY_ARC_U16")
    # ORCH-DEFECTS-0710a: the gate declares ``voice_intervals``, so the measured
    # voice must actually reach it here -- declaring it and never passing it is
    # the defect, not the fix.
    voice = take.get("voice_intervals")
    if voice is None:
        voice = plan.get("voice_intervals")
    gates = {
        "story_start": story_start_gate(aligned, plot, D),
        "lexical_coverage": lexical_coverage_gate(aligned, D,
                                                  voice_intervals=voice),
        "story_arc": story_arc_gate(aligned, arc, D),
    }
    # The words-versus-length floor needs the plan's own word budget; a caller
    # with no budget (the style-contract seam) leaves that one gate out rather
    # than reporting a false UNAVAILABLE against every take.
    if isinstance((plan.get("words") or {}).get("total"), (int, float)):
        gates["words_floor"] = words_floor(plan, take.get("delivered_words"),
                                           take.get("vocal_seconds"))
    # ORCH-DEFECTS-0710b: the 0.98 TEXT-coverage gate is a MEMBER of this
    # dictionary, so it runs as part of this function's own gate evaluation. A
    # caller that carries no approved or no observed text gets UNAVAILABLE and
    # the overall verdict below reflects it -- never a PASS on a missing input.
    approved_text = take.get("approved_words")
    if approved_text is None:
        approved_text = sheet_text or None
    observed_text = take.get("observed_words")
    if observed_text is None:
        observed_text = take.get("delivered_text")
    gates["text_coverage"] = text_coverage_gate(approved_text, observed_text)
    verdicts = {g["verdict"] for g in gates.values()}
    verdict = ("FAIL" if "FAIL" in verdicts
               else "UNAVAILABLE" if "UNAVAILABLE" in verdicts else "PASS")
    out = {"verdict": verdict, "gates": gates, "applicable": True,
           "approved_opening_line":
               gates["story_start"].get("approved_opening_line") or [],
           "delivered_onset_owner": "D2",
           "detail": " | ".join("%s=%s" % (k, v["verdict"])
                                for k, v in sorted(gates.items())),
           "source": "WWFIX D1: the story gates run on the returned take"}
    if isinstance(D, (int, float)) and D > 0:
        out["coverage"] = words_vs_music_figures(dict(plan, delivered_s=D))
    # WW-24: the SCRIPT report rides with every returned-take judgement, its
    # three figures under separate labels -- the lexical estimate (the plan's
    # voice seconds), the music-only allowance (the plan's own intro/outro) and
    # their runtime. Written here so the production seam and the report can
    # never drift apart.
    out["script_report"] = script_report(planned_voice_s(plan),
                                         plan.get("intro_outro_s") or 0.0)
    return out


def judge_plan_coverage(plan, take):
    """Back-compat seam: the plan opts in with a ``story_coverage`` block."""
    cfg = (plan or {}).get("story_coverage")
    if not cfg:
        return {"verdict": "PASS", "applicable": False,
                "detail": "no story_coverage block in the plan"}
    cfg = cfg if isinstance(cfg, dict) else {}
    out = judge_returned_take(take or {}, plan, cfg.get("sheet_text"),
                              cfg.get("delivered_s"))
    out["applicable"] = True
    return out
