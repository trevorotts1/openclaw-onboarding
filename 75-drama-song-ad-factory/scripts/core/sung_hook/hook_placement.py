#!/usr/bin/env python3
"""FU-HOOK-PLACEMENT: the sung hook is the payoff, never the opener.

Trevor, 2026-10-09, on a client's One-Check ad: "IT'S SINGING THE
HOOK TOO SOON AT THE VERY BEGINNING. THERE IS NO BUILD-UP TO THE HOOK AND IT
DOESN'T MAKE SENSE WITHIN THE STORY ARC. THE HOOK HAS TO MAKE SENSE AND BE
PLACED CORRECTLY." v1 sang "Girl, I got you" at 24 s, before help had arrived
in the story; the v2 sheet put the hook straight after the vocalise and Suno
added one more hook block at 13.6 s.

The old doctrine caused it: suno_recipe rule 3 said "the first hook comes
after the vocalise", sung_hook.check_sheet_count wanted the first hook within
the first four sections, and the golden sheets opened Intro -> Vocalise ->
Hook. The rules here replace that:

  1. BUILD-UP. Before the first hook the sheet carries the build-up the
     style's own structure calls for: a verse, plus a pre-chorus (or build)
     when the style's section plan has one AND the length plan has
     pre-choruses (the 60 s plan has none). Measured on a take, the first
     hook may not start before ``min_first_hook_s``: the length plan's own
     spoken opener plus one planned sung section per build-up section, so
     a 60 s ad gets an earlier, still built-up hook and a 300 s ad a later
     one. No fixed second count.
  2. STORY SENSE, always on. The hook_plan names the beat of the U16 story
     arc (length_formula.STORY_ARC_U16) where the hook's words become true
     (``true_at_beat``); music_director emits it with every request it
     builds. The gate MEASURES where each hook block sits: its planned start
     (the words before it at the style's own rates, words_fit) as a share of
     the sheet, mapped onto the arc (the arc after its opening beat spans the
     runtime evenly). The first hook must sit at or after ``true_at_beat``;
     the arc's opening beat can never carry the sung hook. Beats are never
     taken from the plan: a plan's "beats" list is a receipt only.
  3. COUNT. hook_target: sung_hook.hook_count for the length, reduced to
     what fits in the runtime after ``true_at_beat`` starts.

  4. AFTER SUNO, BEFORE PICTURE SPEND. From Suno's returned lyric text and
     aligned word times: fail if Suno added hook blocks (or any blocks)
     beyond the sheet, moved a hook block earlier in the section order, or
     sang the first hook inside the build-up window, or before the second
     its ``true_at_beat`` starts. Headers present but none a hook: FAIL
     (UNMEASURED), never a pass with no first hook.
     NO HEADERS (word timing from local transcription, or Suno sent none):
     the hook is placed from the approved hook words found on the measured,
     ordered word times, each occurrence confirmed sung by the detector's
     measured segments; the same floors and the extra-hook check apply.
     Untrusted timing, missing hook words or no measured segments block.
     Headers are never invented at planned times.

  hook_plan JSON shape (SKILL.md "Hook placement"):
     {"true_at_beat": "the_turn"}
     plan_for() adds "beats" (one measured beat per hook block) as a receipt.

  No gate switches itself off: a missing style_id, length_s, sheet,
  hook_plan or true_at_beat is a FAIL reading "UNMEASURED: <field>".

stdlib only; no network, no spend, no speech-to-text of any kind.
Run: python3 core/sung_hook/hook_placement.py --sheet S.txt --length 148 \
        --style rnb-flow --hook-plan P.json [--aligned A.json]
"""
from __future__ import annotations

import argparse
import difflib
import json
import math
import os
import re
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from length_formula import length_formula as _LF   # noqa: E402
from music_styles import music_styles as _MS       # noqa: E402
from sung_hook import sung_hook as _SH             # noqa: E402
import words_fit as _WF                            # noqa: E402

TOOL_NAME = "hook_placement"
TOOL_VERSION = "1.3.0"
SOURCE = "Trevor 2026-10-09: the hook is the payoff, placed after the build-up, at its story beat"

HOOK_HEADS = ("hook", "chorus")
PRE_WORDS = ("pre-chorus", "pre chorus", "prechorus", "pre-hook", "pre hook", "build")
#: Recipe and Suno instruction wording (rule 5). Kept here so the prompt and
#: the gate say the same thing.
PROMPT_CLAUSE = ("Sing the sections in the order written; the song never "
                 "opens with the hook: build up through the verse first")
NEGATIVE_CLAUSE = "hook in the intro"


class HookPlacementError(ValueError):
    pass


# ---- section kinds ----------------------------------------------------------

def _norm(tag):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9-]+", " ", str(tag or "").lower())).strip()


def kind_of(section):
    """'hook' | 'pre' | 'verse' | 'other' for one sheet section dict."""
    tag, d = _norm(section.get("tag")), section.get("delivery")
    if any(w in tag for w in PRE_WORDS):
        return "pre"
    head = tag.split(" ")[0] if tag else ""
    if head in HOOK_HEADS and d == "sung":
        return "hook"
    if re.search(r"\bverse\b", tag) and d in ("sung", "rap"):
        return "verse"
    return "other"


def _sheet(sheet):
    if isinstance(sheet, str):
        import suno_recipe as _R   # lazy: suno_recipe imports this module
        return _R.parse_lyrics(sheet)
    return list(sheet or [])


# ---- rule 1: the build-up ---------------------------------------------------

def style_has_pre(style_id):
    """True when the style's own section plan names a pre-chorus/build stage
    before its first chorus/hook (music_styles.SECTION_HINTS)."""
    hint = _MS.section_hint(style_id).lower()
    first = min([hint.find("[" + h) for h in HOOK_HEADS if hint.find("[" + h) >= 0] or [len(hint)])
    return any(w in hint[:first] for w in PRE_WORDS)


def unmeasured(**fields):
    """["UNMEASURED: <field>", ...] for every missing input (never a skip)."""
    return ["UNMEASURED: %s" % k for k, v in fields.items() if v is None]


def buildup(style_id, delivered_s):
    """Sections required before the first hook: ['verse'] or ['verse', 'pre']."""
    need = ["verse"]
    p = _LF.plan(delivered_s + _LF.END_EARLY_S)
    if style_has_pre(style_id) and p["sections"]["pre_chorus"] > 0:
        need.append("pre")
    return need


def min_first_hook_s(style_id, delivered_s):
    """Earliest second the first hook may start: the plan's spoken opener plus
    one planned sung section per build-up section, where a section is the
    plan's sung time split over its sung blocks (verses, pre-choruses,
    bridges and the hook_count hook blocks). Proportional to length:
    58 s -> 13.3 s, 148 s -> 27.6 s (17.8 s with no pre-chorus), 298 s -> 30.9 s."""
    p = _LF.plan(delivered_s + _LF.END_EARLY_S)
    s = p["sections"]
    n_sung = max(1, s["verses"] + s["pre_chorus"] + s["bridge"] + _SH.hook_count(delivered_s))
    section_s = p["words"]["sung"] / _LF.SUNG_WPS / n_sung
    opener_s = p["words"]["opener_max"] / _LF.SPOKEN_WPS
    return round(opener_s + len(buildup(style_id, delivered_s)) * section_s, 1)


def check_buildup(sheet, style_id, delivered_s):
    """Rule 1 on a sheet, always on. [] = pass; else plain-English reasons.
    A missing style_id or length is a FAIL ("UNMEASURED: <field>")."""
    miss = unmeasured(style_id=style_id, length_s=delivered_s)
    if miss:
        return miss
    secs = _sheet(sheet)
    kinds = [kind_of(s) for s in secs]
    if "hook" not in kinds:
        return []
    first = kinds.index("hook")
    before = kinds[:first]
    need = buildup(style_id, delivered_s)
    names = {"verse": "a verse", "pre": "a pre-chorus (or build)"}
    missing = [names[k] for k in need if k not in before]
    if missing:
        return ["the first hook is section #%d (%r) and comes before %s: the hook is the "
                "payoff, it needs the build-up (%s) first"
                % (first + 1, secs[first].get("tag"), " and ".join(missing),
                   " then ".join(names[k] for k in need))]
    return []


# ---- rules 2 and 3: story beats and returns ---------------------------------

def beat_start_s(beat, delivered_s):
    """Second where a story beat starts: the arc after its opening beat
    spans the runtime evenly, beat k (k >= 1) from (k - 1) / 7 of it."""
    arc = _LF.STORY_ARC_U16
    # ponytail: even beat spacing; per-ad beat seconds from the story plan if it ever carries them
    return delivered_s * (arc.index(beat) - 1) / (len(arc) - 1)


def beat_at(share):
    """The story beat at a share (0-1) of the runtime (beat_start_s inverted)."""
    arc = _LF.STORY_ARC_U16
    return arc[min(len(arc) - 1, 1 + int(share * (len(arc) - 1)))]


def hook_target(delivered_s, hook_plan=None):
    """Hook blocks the sheet carries: sung_hook.hook_count for the length,
    reduced to what fits in the runtime left once ``true_at_beat`` starts."""
    n = _SH.hook_count(delivered_s)
    true_at = hook_plan.get("true_at_beat") if isinstance(hook_plan, dict) else None
    if true_at not in _LF.STORY_ARC_U16[1:]:
        return n
    return min(n, _SH.hook_count(delivered_s - beat_start_s(true_at, delivered_s)))


def hook_positions(sheet, style_id):
    """Planned start of every hook block as a share (0-1) of the sheet's
    planned seconds: the words before it at the style's own rates."""
    rates = _WF.rates_for(style_id)
    t, starts = 0.0, []
    for s in _sheet(sheet):
        if kind_of(s) == "hook":
            starts.append(t)
        if s.get("delivery") in rates:
            t += len(" ".join(s.get("lines") or []).split()) / float(rates[s["delivery"]])
    return [round(x / t, 3) for x in starts] if t else []


def plan_for(sheet, delivered_s, true_at_beat, style_id):
    """The hook_plan music_director emits: {"true_at_beat"} plus "beats",
    the MEASURED beat of every hook block (a receipt; the gate re-measures)."""
    return {"true_at_beat": true_at_beat,
            "beats": [beat_at(x) for x in hook_positions(sheet, style_id)]}


def beat_errors(true_at):
    """[] when ``true_at`` is a beat after the arc's opening; else the FAIL
    reason. Sheet (check_story) and take (check_returned) share it, so an
    invalid or opening beat never silently drops the story-beat check."""
    arc = list(_LF.STORY_ARC_U16)
    if true_at is None:
        return ["UNMEASURED: true_at_beat"]
    if true_at not in arc:
        return ["true_at_beat %r is not a beat of the story arc %s" % (true_at, arc)]
    if arc.index(true_at) == 0:
        return ["the hook's words are tied to the opening beat %r: the hook is the payoff, "
                "never the opener" % true_at]
    return []


def check_story(sheet, hook_plan, delivered_s, style_id):
    """Rules 2-3 on a sheet, always on. [] = pass; else plain-English reasons.
    The first hook's beat is measured from the sheet, never read from the plan.
    A missing plan, true_at_beat, style or length is "UNMEASURED: <field>"."""
    true_at = hook_plan.get("true_at_beat") if isinstance(hook_plan, dict) else None
    errs = unmeasured(hook_plan=hook_plan, style_id=style_id, length_s=delivered_s)
    if errs:
        return errs
    errs = beat_errors(true_at)
    if errs:
        return errs
    arc = list(_LF.STORY_ARC_U16)
    at = hook_positions(sheet, style_id)
    if not at:
        return []
    want = hook_target(delivered_s, hook_plan)
    if len(at) > want:
        errs.append("%d hook blocks, the %g s plan fits at most %d after the beat %r"
                    % (len(at), delivered_s, want, true_at))
    first = beat_at(at[0])
    if arc.index(first) < arc.index(true_at):
        errs.append("the first hook sits at %d%% of the song (beat %r), before %r (from %d%%) "
                    "where its words become true"
                    % (round(at[0] * 100), first, true_at,
                       round(100 * beat_start_s(true_at, delivered_s) / delivered_s)))
    return errs


def check_sheet(sheet, style_id, delivered_s, hook_plan=None):
    """Rules 1-3 together: {"verdict", "reasons", "min_first_hook_s", "buildup",
    "hook_beats" (measured)}. No hook_plan = FAIL "UNMEASURED: hook_plan"."""
    reasons = check_buildup(sheet, style_id, delivered_s)
    reasons += [r for r in check_story(sheet, hook_plan, delivered_s, style_id) if r not in reasons]
    ok = not unmeasured(style_id=style_id, length_s=delivered_s)
    return {"verdict": "FAIL" if reasons else "PASS", "reasons": reasons,
            "buildup": buildup(style_id, delivered_s) if ok else None,
            "min_first_hook_s": min_first_hook_s(style_id, delivered_s) if ok else None,
            "hook_beats": [beat_at(x) for x in hook_positions(sheet, style_id)] if ok else None,
            "source": SOURCE}


# ---- rule 4: what Suno actually returned ------------------------------------

_HEADER_RE = re.compile(r"\[([^\]]*)\]")


def returned_sections(aligned_words):
    """[(tag, start_s)] from Suno's aligned words, whose text carries the
    section headers inline (a header can be split across two words)."""
    text, starts = "", []
    for w in aligned_words or []:
        starts.append((len(text), w.get("start", w.get("startS"))))
        text += str(w.get("word", ""))
    out = []
    for m in _HEADER_RE.finditer(text):
        # the word holding the closing "]" also holds the section's first sung
        # word, so its start time is when the section starts
        t = [s for pos, s in starts if pos <= m.end() - 1][-1]
        out.append((m.group(1).strip(), t))
    return out


def _parsed(tag):
    """One returned header as a sheet section (tag name + delivery)."""
    import suno_recipe as _R
    try:
        sec = _R.parse_lyrics("[%s]\nx" % tag)
    except _R.RecipeError:                 # [End], [Instrumental Break]: no voice
        sec = []
    return sec[0] if sec else {"tag": tag, "delivery": None}


def _head_kind(tag):
    return kind_of(_parsed(tag))


def _floor_reasons(first, style_id, delivered_s, true_at):
    """The two time floors on the first sung hook: the build-up window and the
    story beat where the hook's words become true. Shared by both readers."""
    floor, out = min_first_hook_s(style_id, delivered_s), []
    if first < floor:
        out.append("first hook sung at %.1f s, inside the %.1f s build-up window for a %g s ad"
                   % (first, floor, delivered_s))
    at = beat_start_s(true_at, delivered_s)
    if first < at:
        out.append("first hook sung at %.1f s (beat %r), before %r starts at %.1f s where "
                   "its words become true" % (first, beat_at(first / delivered_s), true_at, at))
    return out


def _timed_tokens(aligned_words):
    """[(token, start, end)] from ordered word records, every token of a record
    kept (Suno packs "Verse 3 " or "talking.\\n\\n" into one record). None when the
    timing cannot be trusted: a non-numeric, non-finite or reversed time, or
    starts that run backwards."""
    out, last = [], None
    for w in aligned_words or []:
        if not isinstance(w, dict):
            return None
        a, b = _SH._span(w)
        if not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
                   for x in (a, b)) or b < a or (last is not None and a < last):
            return None
        last = a
        text = re.sub(r"\[[^\]]*\]?|^[^\[]*\]", " ", str(w.get("word", "")))
        out += [(t, float(a), float(b)) for t in _SH._words(text)]
    return out


def _find(seq, key):
    """Start indexes of every non-overlapping run of ``key`` in ``seq``."""
    hits, i, n, key = [], 0, len(key), list(key)
    while n and i + n <= len(seq):
        if list(seq[i:i + n]) == key:
            hits.append(i)
            i += n
        else:
            i += 1
    return hits


def _lexical_unmeasured(why, wh):
    return {"verdict": "FAIL", "reasons": ["UNMEASURED: " + why], "first_hook_s": None,
            "min_first_hook_s": None, "hook_blocks_sheet": wh, "hook_blocks_returned": None,
            "basis": "lexical", "source": SOURCE}


def _check_lexical(secs, want, aligned_words, segments, style_id, delivered_s, true_at):
    """Rule 4 with NO section headers in the returned words (local transcription
    hears words, never editorial labels). Each sheet hook block is found as its
    exact approved words on the measured word times and counts only when the
    singing detector measured it sung. Everything incomplete blocks: untrusted
    timing, no measured segments, ambiguous hook words, or fewer sung hook
    blocks than the sheet carries (an unread earlier hook cannot be ruled out).
    No header is ever invented at a planned time."""
    wh = want.count("hook")
    keys = sorted({tuple(_SH._words(" ".join(s.get("lines") or [])))
                   for s, k in zip(secs, want) if k == "hook"} - {()}, key=len, reverse=True)
    if not keys:
        return _lexical_unmeasured("section headers (Suno returned none) and the sheet carries "
                                   "no hook words to place", wh)
    for s, k in zip(secs, want):
        own = _SH._words(" ".join(s.get("lines") or []))
        if k != "hook" and any(_find(own, key) for key in keys):
            return _lexical_unmeasured("hook words also sit in the sheet's %r section: hook "
                                       "placement is ambiguous without section headers"
                                       % s.get("tag"), wh)
    toks = _timed_tokens(aligned_words)
    if not toks:
        return _lexical_unmeasured("section headers (Suno returned none) and the word timing "
                                   "is missing or untrusted, so the hook cannot be placed", wh)
    segs = [s for s in segments or [] if isinstance(s, dict)]
    if not segs or any(s.get("source") != "measured" for s in segs):
        return _lexical_unmeasured("section headers (Suno returned none) and no detector-"
                                   "measured segments confirm the hook was sung", wh)
    seq = [t for t, _, _ in toks]
    found = set()
    for key in keys:                                # longest key first: no double count
        for i in _find(seq, key):
            if not any(i <= j < i + len(key) or j <= i < j + n for j, n in found):
                found.add((i, len(key)))
    sung = []
    for i, n in sorted(found):
        a, b = toks[i][1], toks[i + n - 1][2]
        if any(s.get("delivery") == "sung" and s["start"] <= (a + b) / 2 <= s["end"] for s in segs):
            sung.append(round(a, 3))
    if len(sung) > wh:
        return {"verdict": "FAIL", "first_hook_s": sung[0], "basis": "lexical",
                "reasons": ["Suno sang %d hook blocks, the sheet has %d (hook words sung at %s)"
                            % (len(sung), wh, ", ".join("%.1f s" % t for t in sung))]
                + _floor_reasons(sung[0], style_id, delivered_s, true_at),
                "min_first_hook_s": min_first_hook_s(style_id, delivered_s),
                "hook_blocks_sheet": wh, "hook_blocks_returned": len(sung), "source": SOURCE}
    if len(sung) < wh:
        r = _lexical_unmeasured("section headers (Suno returned none); the approved hook words "
                                "were heard sung %d of the sheet's %d times, so an earlier "
                                "unread hook cannot be ruled out" % (len(sung), wh), wh)
        r["hook_blocks_returned"] = len(sung)
        return r
    reasons = _floor_reasons(sung[0], style_id, delivered_s, true_at)
    return {"verdict": "FAIL" if reasons else "PASS", "reasons": reasons,
            "first_hook_s": sung[0], "min_first_hook_s": min_first_hook_s(style_id, delivered_s),
            "hook_blocks_sheet": wh, "hook_blocks_returned": len(sung), "basis": "lexical",
            "source": SOURCE}


def check_returned(sheet, aligned_words, style_id, delivered_s, hook_plan=None, segments=None):
    """Rule 4 on one take, always on. {"verdict", "reasons", "first_hook_s", ...}.
    A missing sheet, style_id, length or hook_plan is a FAIL ("UNMEASURED: <field>").
    ``segments``: the singing detector's measured segments, needed only when the
    returned words carry no section headers (the lexical reader)."""
    true_at = hook_plan.get("true_at_beat") if isinstance(hook_plan, dict) else None
    miss = unmeasured(sheet_text=sheet or None, style_id=style_id, length_s=delivered_s,
                      hook_plan=hook_plan) or beat_errors(true_at)
    if miss:
        return {"verdict": "FAIL", "reasons": miss, "first_hook_s": None,
                "min_first_hook_s": None, "source": SOURCE}
    secs = [s for s in _sheet(sheet) if s.get("delivery") is not None]
    want = [kind_of(s) for s in secs]
    got_tags = returned_sections(aligned_words)
    if not got_tags:
        return _check_lexical(secs, want, aligned_words, segments, style_id, delivered_s, true_at)
    got = [(_head_kind(t), t, s) for t, s in got_tags
           if t.lower() != "end" and "instrumental" not in t.lower()]
    reasons = []
    wh, gh = want.count("hook"), sum(1 for k, _, _ in got if k == "hook")
    if gh > wh:
        reasons.append("Suno sang %d hook blocks, the sheet has %d (added at %s)"
                       % (gh, wh, ", ".join("%.1f s" % s for k, _, s in _extra_hooks(secs, got))))
    if len(got) > len(want):
        reasons.append("Suno returned %d sections, the sheet has %d" % (len(got), len(want)))
    w_idx = [i for i, k in enumerate(want) if k == "hook"]
    g_idx = [i for i, (k, _, _) in enumerate(got) if k == "hook"]
    if g_idx and w_idx and g_idx[0] < w_idx[0]:
        reasons.append("Suno moved the first hook earlier: section #%d, the sheet has it at #%d"
                       % (g_idx[0] + 1, w_idx[0] + 1))
    first = next((s for k, _, s in got if k == "hook"), None)
    floor = min_first_hook_s(style_id, delivered_s)
    if first is not None:
        reasons += _floor_reasons(first, style_id, delivered_s, true_at)
    elif wh:
        # the sheet carries a hook but no returned header names one: the first
        # hook time is unread, which never passes the time floors
        reasons.append("UNMEASURED: no returned section header names a hook (%d headers, the "
                       "sheet has %d hook blocks); the first hook time cannot be read"
                       % (len(got), wh))
    return {"verdict": "FAIL" if reasons else "PASS", "reasons": reasons,
            "first_hook_s": first, "min_first_hook_s": floor,
            "hook_blocks_sheet": wh, "hook_blocks_returned": gh, "basis": "headers",
            "source": SOURCE}


def _extra_hooks(secs, got):
    """Returned hook blocks the sheet does not have, by sequence alignment of
    section names (Suno echoes the sheet's own tags)."""
    want = [_norm(x.get("tag")) for x in secs]
    have = [_norm(_tag_name(t)) for _, t, _ in got]
    out = []
    for op, _, _, j1, j2 in difflib.SequenceMatcher(None, want, have, autojunk=False).get_opcodes():
        if op in ("insert", "replace"):
            for j in range(j1, j2):
                if got[j][0] != "hook":
                    continue
                # a doubled hook: the sheet's hook is the first of the pair,
                # the extra is the one that follows it
                nxt = j + 1 < len(got) and got[j + 1][0] == "hook" and j + 1 >= j2
                out.append(got[j + 1] if nxt else got[j])
    return out


def _tag_name(tag):
    return _parsed(tag)["tag"]


# ---- CLI ---------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(prog="hook_placement.py", description=__doc__.split("\n")[0])
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--length", type=float, required=True, help="delivered seconds (chosen - 2)")
    ap.add_argument("--style", required=True)
    ap.add_argument("--hook-plan", default=None, help='JSON file: {"true_at_beat": "the_turn"}')
    ap.add_argument("--aligned", default=None, help="Suno aligned words JSON")
    a = ap.parse_args(argv)
    with open(a.sheet, encoding="utf-8") as f:
        sheet = f.read()
    hp = json.load(open(a.hook_plan, encoding="utf-8")) if a.hook_plan else None
    out = {"sheet": check_sheet(sheet, a.style, a.length, hp)}
    if a.aligned:
        words = json.load(open(a.aligned, encoding="utf-8"))
        if isinstance(words, dict):
            words = words.get("alignedWords") or words.get("aligned_words") or []
        out["returned"] = check_returned(sheet, words, a.style, a.length, hp)
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if all(v["verdict"] == "PASS" for v in out.values()) else 4


if __name__ == "__main__":
    sys.exit(main())
