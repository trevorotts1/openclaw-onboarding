#!/usr/bin/env python3
"""Story coverage: the story-start ceiling, the lexical-coverage floor, the
story-arc window rule, and the words-versus-length floor.

D1 / F3+F4. The failed run measured: first LEXICAL word at 2.462-4.707 s but the
first substantial PLOT line at 11.980-23.541 s, with wordless vocalise union up
to 17.833 s -- about 18 seconds of an 88-second ad carried no story at all
(Trevor: "the first 18 seconds is just music"). The sheet arithmetic that
"proved" enough words was 69/1.9 + 13/2 + 19/2.5 + 8 = 58.4158, where the
trailing +8 is INTRO_OUTRO_S, MUSIC-ONLY time: the vocal-only figure is
50.416 s. Presenting 58.4 as seconds OF WORDS overstates word coverage by
8 seconds. This module keeps the two figures apart under two labels and never
adds them under one.

FOUR GATES, all in skill code:

  * STORY START (``story_start_gate``): the first word of the approved PLOT
    line must arrive by FIRST_STORY_WORD_MAX_S (an ABSOLUTE 5.0 s -- not a
    share of the length), and the opening wordless (non-lexical) span must not
    exceed OPENING_NON_LEXICAL_MAX_SHARE of the delivered seconds. The filler
    opener ("I'm still up") and a wordless vocalise are never counted as the
    story starting. A take with nothing measurable is UNAVAILABLE, never PASS.
  * LEXICAL COVERAGE (``lexical_coverage_gate``): the union of real lexical
    word intervals, with NO vocalise counted, must reach LEXICAL_COVERAGE_MIN
    (0.70) of the delivered duration. At 88 s the master owes >= 61.6 s; the
    measured value was 48.476-53.991 s, so this gate rejects the shipped master.
  * STORY ARC (``story_arc_gate``): every beats_u16 window of at least
    STORY_ARC_WINDOW_MIN_S seconds must carry at least one measured lexical
    line. A five-second hole with no words is FAIL.
  * WORDS FLOOR (``words_floor``): the delivered words must reach
    WORD_FLOOR_SHARE of the plan's planned words and the voiced time must reach
    VOCAL_TIME_FLOOR_SHARE of the plan's planned voice seconds.

EVERY NUMBER BELOW IS A NEW ACCEPTANCE RULE set by this fix. None is a measured
limit of the failed run; the measured numbers above are only the target the
rules are aimed at.

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
OPENING_NON_LEXICAL_MAX_SHARE = 0.15   # R1: opening wordless span, share of D
LEXICAL_COVERAGE_MIN = 0.70            # R2: lexical time / duration, no vocalise
STORY_ARC_WINDOW_MIN_S = 5.0           # story arc: the shortest window that counts
WORD_FLOOR_SHARE = 0.90                # delivered words / planned words
VOCAL_TIME_FLOOR_SHARE = 0.85          # voiced seconds / planned voice seconds

#: The three gates named above are gate names the take judge reports.
GATES = ("story_start", "lexical_coverage", "story_arc", "words_floor")

#: Tokens that are vocal sound, not story: "oo-o-o-o-o-oh", "oh", "la-la", "mmm".
VOCALISE_RE = re.compile(
    r"^(?:o+h*|o+w*|a+h+|e+h+|mmm*|hmm*|na+|la+|da+|yeah*|whoa*|woah*|hey*)$",
    re.IGNORECASE)

#: Section tags that are NOT the plot: the opener line, the closing call to
#: action and the wordless vocalise. Everything else on the sheet is the story.
NON_PLOT_TAGS = ("intro", "outro", "vocalise", "end", "instrumental")


class CoverageError(ValueError):
    """Malformed evidence; a gate that cannot read its input never passes."""


def is_vocalise(token):
    """True for a wordless vocal sound (hyphens and repeats stripped first)."""
    t = re.sub(r"[-'`’]", "", str(token or "")).strip().lower()
    if not t:
        return True
    if not re.search(r"[a-z]", t):
        return True
    # a chain of the same letter run together ("ooooooh", "ahhhhh")
    if re.fullmatch(r"(.)\1{2,}", t):
        return True
    return bool(VOCALISE_RE.match(t))


def is_lexical(token):
    """A REAL story word: not a vocalise, and not a bare non-word."""
    t = re.sub(r"[-'`’]", "", str(token or "")).strip()
    if not t or is_vocalise(token):
        return False
    return bool(re.search(r"[a-z]", t, re.IGNORECASE))


# ---- reading the alignment -------------------------------------------------

def _start(w):
    return w.get("startS", w.get("start", w.get("start_s")))


def _end(w):
    return w.get("endS", w.get("end", w.get("end_s")))


def _tok(w):
    """The word text, with Suno's inline section header dropped."""
    return str((w or {}).get("word") or "").split("\n")[-1]


def _lines(w):
    """True when this aligned word starts a NEW lyric line (Suno carries the
    section/line break inline as a leading newline)."""
    return "\n" in str((w or {}).get("word") or "")


def aligned_lexical_words(aligned_words):
    """[(start_s, end_s, word)] for every aligned word that is real story,
    in time order. A vocalise is skipped; so is anything with no usable time."""
    out = []
    for w in aligned_words or []:
        if not isinstance(w, dict):
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
    return [re.sub(r"[^a-z']", "", t.lower())
            for t in str(text or "").split()
            if is_lexical(t)]


def plot_words_from_sheet(sheet_text):
    """The APPROVED PLOT words: every line that is not the opener, the closing
    call to action or a wordless vocalise.

    Reads the sheet with the repository's ONE tag grammar
    (``suno_recipe.parse_lyrics``), so the plot this gate measures is the same
    text the recipe and words-fit gates measure. Returns a set of lowercased
    words; an empty set means the sheet named no plot and the gate reports
    UNAVAILABLE rather than passing."""
    import suno_recipe as _RP
    parse_lyrics = getattr(_RP, "parse_lyrics", None) or _RP.suno_recipe.parse_lyrics
    out = set()
    for sec in parse_lyrics(sheet_text):
        tag = str(sec.get("tag") or "").strip().lower()
        if any(tag.startswith(t) or tag == t for t in NON_PLOT_TAGS):
            continue
        for line in sec["lines"]:
            out.update(words_of(line))
    return out


# ---- gate 1: story start ---------------------------------------------------

def first_plot_word_s(aligned_words, plot_words):
    """Seconds of the first aligned word that belongs to the approved PLOT.

    Filler such as "I'm still up" and a wordless vocalise are not in the plot
    set, so they cannot start the story. None when the plot never lands."""
    want = {w for w in (plot_words or ()) if w}
    if not want:
        return None
    for s, _e, tok in aligned_lexical_words(aligned_words):
        if re.sub(r"[^a-z']", "", tok.lower()) in want:
            return round(s, 3)
    return None


def first_plot_line_s(aligned_words, plot_words, min_words=4):
    """Seconds at which the first run of ``min_words`` consecutive plot words
    begins, or None. A single stray word is not a plot line."""
    want = {w for w in (plot_words or ()) if w}
    if not want:
        raise CoverageError("plot_words is empty; nothing to look for")
    run, start = 0, None
    for s, _e, tok in aligned_lexical_words(aligned_words):
        if re.sub(r"[^a-z']", "", tok.lower()) in want:
            if run == 0:
                start = s
            run += 1
            if run >= min_words:
                return round(start, 3)
        else:
            run, start = 0, None
    return None


def opening_non_lexical_s(aligned_words):
    """The opening wordless span, in seconds: from 0.0 to the first aligned
    word that is REAL story. None when no lexical word was measured."""
    lex = aligned_lexical_words(aligned_words)
    return None if not lex else round(lex[0][0], 3)


def story_start_gate(aligned_words, plot_words, delivered_s,
                     max_s=FIRST_STORY_WORD_MAX_S,
                     opening_share=OPENING_NON_LEXICAL_MAX_SHARE,
                     min_words=PLOT_LINE_MIN_WORDS):
    """PASS / FAIL / UNAVAILABLE on how soon the STORY starts.

    THE MEASUREMENT IS THE APPROVED PLOT LINE, not the first stray word: a run
    of at least ``min_words`` consecutive words of the approved plot, in order.
    That is what stops the filler opener ("I'm still up") and a wordless
    vocalise from being read as the story starting -- "I'm" alone matched a
    plot word that happens to appear later in the sheet, which is exactly the
    false pass this avoids.

    FAIL when that first plot line lands after ``max_s`` (an ABSOLUTE 5.0 s,
    never a share of the length), and FAIL when the opening non-lexical span
    exceeds ``opening_share`` of the delivered seconds. A take with no
    measurable plot line at all is FAIL, never PASS. Missing evidence is
    UNAVAILABLE."""
    if not aligned_words:
        return {"verdict": "UNAVAILABLE", "reason_code": "NO_ALIGNED_WORDS",
                "detail": "no aligned words: the story start cannot be measured",
                "ceiling_s": max_s}
    if not plot_words:
        return {"verdict": "UNAVAILABLE", "reason_code": "NO_PLOT_TEXT",
                "detail": "the sheet names no plot line; nothing to measure",
                "ceiling_s": max_s}
    D = float(delivered_s or 0.0)
    line = first_plot_line_s(aligned_words, plot_words, min_words=min_words)
    loose = first_plot_word_s(aligned_words, plot_words)
    opening = opening_non_lexical_s(aligned_words)
    fails = []
    if line is None:
        fails.append("NO_PLOT_LINE_SUNG")
    elif line > max_s:
        fails.append("FIRST_STORY_WORD_LATE")
    if D > 0 and opening is not None and opening > opening_share * D:
        fails.append("OPENING_NON_LEXICAL_TOO_LONG")
    return {
        "verdict": "FAIL" if fails else "PASS",
        "reason_code": fails[0] if fails else "STORY_STARTS_IN_TIME",
        "failed": fails,
        "first_story_word_s": line,
        "first_plot_line_s": line,
        "first_plot_word_s": loose,
        "opening_non_lexical_s": opening,
        "opening_ceiling_s": round(opening_share * D, 3),
        "plot_line_min_words": min_words,
        "ceiling_s": max_s,
        "detail": ("first approved plot line %s (ceiling %.1f s), first plot word "
                   "%s, opening wordless %s s (ceiling %.1f s)"
                   % ("n/a" if line is None else "%.3f s" % line, max_s,
                      "n/a" if loose is None else "%.3f s" % loose,
                      "n/a" if opening is None else "%.3f s" % opening,
                      opening_share * D)),
        "thresholds_are_new_acceptance_rules": True,
        "source": "WWFIX D1/F4: absolute first-story-line ceiling + opening span",
    }


# ---- gate 2: lexical coverage ---------------------------------------------

def lexical_seconds(aligned_words):
    """The union of the real lexical word intervals, in seconds. A vocalise
    contributes nothing; overlapping intervals are counted once."""
    spans = sorted((s, e) for s, e, _t in aligned_lexical_words(aligned_words))
    total, cur_s, cur_e = 0.0, None, None
    for s, e in spans:
        if cur_s is None:
            cur_s, cur_e = s, e
        elif s <= cur_e:
            cur_e = max(cur_e, e)
        else:
            total += cur_e - cur_s
            cur_s, cur_e = s, e
    if cur_s is not None:
        total += cur_e - cur_s
    return round(total, 3)


def lexical_coverage_gate(aligned_words, delivered_s, floor=LEXICAL_COVERAGE_MIN):
    """PASS / FAIL / UNAVAILABLE on how much of the ad actually carries words.

    ``lexical_seconds(aligned_words) / delivered_s >= floor`` (0.70). No
    vocalise is counted. Unmeasured input is UNAVAILABLE, never PASS."""
    D = float(delivered_s or 0.0)
    if D <= 0 or not aligned_words:
        return {"verdict": "UNAVAILABLE", "reason_code": "COVERAGE_UNMEASURED",
                "lexical_s": None, "delivered_s": D or None, "floor": floor,
                "detail": "the delivered duration or the alignment is missing"}
    secs = lexical_seconds(aligned_words)
    share = round(secs / D, 4)
    owed = round(floor * D, 3)
    return {
        "verdict": "PASS" if share >= floor else "FAIL",
        "reason_code": "LEXICAL_COVERAGE_MET" if share >= floor
                       else "LEXICAL_COVERAGE_BELOW_FLOOR",
        "lexical_s": secs, "delivered_s": round(D, 3), "owed_s": owed,
        "coverage": share, "floor": floor,
        "vocalise_counted": False,
        "detail": ("%.3f s of real words over %.3f s delivered (%.1f%%, floor "
                   "%.0f%%: %.3f s owed); no vocalise counted"
                   % (secs, D, share * 100, floor * 100, owed)),
        "thresholds_are_new_acceptance_rules": True,
        "source": "WWFIX D1: the separate lexical-coverage gate (0.70, no vocalise)",
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


# ---- the take judge's seam -------------------------------------------------

def judge_returned_take(take, plan, sheet_text=None, delivered_s=None):
    """The four story gates on one measured take, for ``song_contract``.

    ``take`` carries ``aligned_words`` (Suno's aligned words), optionally
    ``delivered_words`` and ``vocal_seconds``; ``plan`` carries the story arc
    (``beats_u16`` / ``STORY_ARC_U16``) and the word budget. Returns
    {verdict, gates:{name:{...}}} where PASS needs every applicable gate to
    PASS and an UNAVAILABLE gate blocks PASS (QC 17.8)."""
    take = take or {}
    plan = plan or {}
    D = delivered_s or plan.get("delivered_s") or take.get("duration_s")
    aligned = take.get("aligned_words") or []
    plot = plot_words_from_sheet(sheet_text) if sheet_text else set()
    arc = plan.get("beats_u16") or plan.get("story_arc_u16") or plan.get("STORY_ARC_U16")
    gates = {
        "story_start": story_start_gate(aligned, plot, D),
        "lexical_coverage": lexical_coverage_gate(aligned, D),
        "story_arc": story_arc_gate(aligned, arc, D),
    }
    # The words-versus-length floor needs the plan's own word budget; a caller
    # with no budget (the style-contract seam) leaves that one gate out rather
    # than reporting a false UNAVAILABLE against every take.
    if isinstance((plan.get("words") or {}).get("total"), (int, float)):
        gates["words_floor"] = words_floor(plan, take.get("delivered_words"),
                                           take.get("vocal_seconds"))
    verdicts = {g["verdict"] for g in gates.values()}
    verdict = ("FAIL" if "FAIL" in verdicts
               else "UNAVAILABLE" if "UNAVAILABLE" in verdicts else "PASS")
    return {"verdict": verdict, "gates": gates, "applicable": True,
            "detail": " | ".join("%s=%s" % (k, v["verdict"])
                                 for k, v in sorted(gates.items())),
            "source": "WWFIX D1: the story gates run on the returned take"}


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
