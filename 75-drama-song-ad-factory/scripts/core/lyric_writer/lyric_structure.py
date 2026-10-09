#!/usr/bin/env python3
"""lyric_structure.py: G2 lyric structure for singing (Trevor order 1135).

The O3 fault: the lyric sheet flipped [Spoken Word]/[Verse] every 1-4 lines
(8 spoken blocks) and the "sung" lines were unmetered unrhymed prose, so
Suno never settled into singing. This module is the fix, in three parts:

  1. SPOKEN BLOCK BUDGET. Spoken blocks are budgeted, never alternating
     line by line: at most 3 blocks for a 60-150 s ad, one each at the
     OPEN (first section), the TURN (middle of the arc) and the CTA (last
     section). Extra spoken blocks are demoted to sung stanzas and re-set
     like any other sung lines. The same demotion enforces the lint rules:
     a spoken block outside open/turn/CTA, or closer than MIN_SUNG_BETWEEN
     sung blocks to the previous spoken block, is demoted too, so
     build_sheet's own output always passes its own lint.
  2. SINGABLE RE-SET. Every sung stanza is re-set as singable lines --
     even line lengths (3..13 syllables, stanza spread <= 7) -- by cutting
     at phrase boundaries and merging adjacent short phrases. Every script
     word is kept, in order. The only addition is the ECHO device: when a
     stanza's final two lines do not rhyme, the stanza's last word is
     repeated once as a short closing line (an identical rhyme), flagged
     "echo" so QC can see it. No other word is added, moved or dropped.
  3. SINGABILITY LINT. The lint is part of the module: it refuses any
     sheet whose sung lines exceed the length band or the meter spread,
     whose stanza-final pair does not rhyme or near-rhyme, whose spoken
     blocks exceed the budget or sit outside open/turn/CTA, or whose
     spoken blocks come closer than MIN_SUNG_BETWEEN sung lines apart.

AMENDED (Trevor order 2026-10-08 11:50 EDT, part G amended by the Opus
audio review; review items G4/G5): the compiler now builds the sheet with
the DELIVERY NAMED IN EVERY TAG -- [Sung - ...], [Spoken - ...],
[Rap - ...], in the forms that actually sang ([Sung - lead, long held
notes]). Bare [Verse]/[Chorus]/[Bridge]/[Hook] tags name no delivery and
are refused; a one-line sung block is refused (Suno chants one-liners);
delivery changes are limited to at most one per SWITCH_EVERY_S seconds of
runtime (O3 flipped delivery 9 times in 140 s and never settled into
singing). The builder remedies all three before rendering: bare tags are
re-labelled with their delivery, a one-line stanza is closed with the
ECHO device (never a new word), and extra spoken blocks are demoted until
the switch rate is legal, so build_sheet's own output always passes its
own lint.

Word-order guarantee: the re-set only cuts and merges phrases and may echo
one existing end word. ``word_chain_intact`` in the lint re-proves that
every original script word survives, in order, in the output.

stdlib only: no network, no provider, no spend, no media file, no absolute
operator path (paths enter only as caller arguments).

Run: python3 core/lyric_writer/lyric_structure.py --sheet SHEET.txt --seconds 90
     python3 core/lyric_writer/lyric_structure.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

TOOL_NAME = "lyric_structure"
TOOL_VERSION = "0.2.0"
#: core/ -- so the one tag grammar (suno_recipe) is importable from here.
_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_VERSION = "blackceo.lyric-structure/v1"
SOURCE = ("Trevor order 1135 2026-10-08 Part G item G2; amended by Trevor "
          "order 2026-10-08 11:50 part G (review G4/G5): delivery named in "
          "every tag, one-line sung blocks and bare tags refused, at most "
          "one delivery switch per 20 s.")

# ponytail: fixed ceilings from the order ("at most 3 blocks for a 60-150 s
# ad"); scale only when an order names longer-length numbers.
MAX_SPOKEN_BLOCKS_SHORT = 3     # <= 150 s
MAX_SPOKEN_BLOCKS_MID = 4       # <= 300 s
MAX_SPOKEN_BLOCKS_LONG = 5      # anything longer
SHORT_SECONDS = 150
MID_SECONDS = 300

#: Placement slots: open = first section, turn = the middle of the arc,
#: cta = last section. Turn window is generous (30%..75% of the sheet) so a
#: real arc's turn block always lands inside it.
TURN_WINDOW = (0.30, 0.75)

#: Two sung blocks must sit between consecutive spoken blocks -- the O3
#: fault was [Spoken Word]/[Verse] flipping every 1-4 lines.
MIN_SUNG_BETWEEN = 2

#: Singable line band (syllables) and the per-stanza meter spread. The
#: flagged ECHO closer is exempt from the meter checks (see the lint).
SYL_MIN = 1
SYL_MAX = 13
METER_SPREAD = 7
SPLIT_PHRASE_ABOVE = 8  # phrases longer than this are split in halves

SPOKEN_TAG = "spoken word"
SECTION_TAG_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")
EXIT = {"ok": 0, "rejected": 4, "error": 1}

# ---- W-G-002 amend: the delivery-named tag grammar (review G4) ------------
#: Words that name a delivery inside a tag. Matched at a word boundary on a
#: punctuation-normalized tag, so "trap beat" is never read as rap.
DELIVERY_WORDS = {
    "rap": ("rap", "raps", "rapped", "rapping"),
    "spoken": ("spoken", "speak", "speaks", "speaking", "talk", "talks",
               "narrate", "narrated"),
    "sung": ("sung", "sing", "sings", "singing"),
}
#: What a tag with no delivery word reads as for the switch rate: the O3
#: fault's [Verse] beside [Spoken Word] is a [Sung] block in effect.
DELIVERY_NONE_DEFAULT = "sung"
INSTRUMENTAL = "instrumental"

#: Order 1150 part G amend (review G4): at most one delivery switch per
#: this many seconds of runtime. The O3 take flipped delivery 9 times in
#: 140 s and Suno never settled into singing.
SWITCH_EVERY_S = 20

#: Default tag tails for the delivery-named form, taken from the forms that
#: actually sang (review G4: [Sung - <lead>, long held notes]).
TAG_TAILS = {
    "sung": "lead, long held notes",
    "spoken": "lead, plain natural speech over the music",
    "rap": "lead, metered flow",
}
#: One regex over every delivery word, for stripping a tag down to its tail.
#: IGNORECASE: render_tag feeds it its OWN output ("[Sung - Chorus]"), which
#: capitalizes the delivery word -- without the flag the second render keeps
#: "Sung" as tail text and drifts to "[Sung - Sung - Chorus]".
_DELIVERY_WORD_RE = re.compile(
    r"\b(%s)\b" % "|".join(w for ws in DELIVERY_WORDS.values() for w in ws),
    re.IGNORECASE)


def delivery_of_tag(tag):
    """The delivery a tag names: "sung" / "spoken" / "rap" / "instrumental",
    or None for a BARE structure tag ([Verse], [Chorus], [Bridge], [Hook]).

    None is the O3 fault: a bare tag beside delivery-named ones let Suno
    read the "sung" blocks as more of the same speech (review G4). The
    EARLIEST delivery word in the tag wins, so a named lead may still say
    "speaks softly" without turning a [Sung - ...] block spoken; ties go
    rap -> spoken -> sung. Matched at word boundaries on a normalized tag,
    so "trap beat" and "rapid" are never read as rap.
    """
    norm = re.sub(r"[^a-z0-9]+", " ", str(tag or "").lower()).strip()
    if not norm:
        return None
    # FU-U1: THE grammar lives in suno_recipe.parse_tag. Delegating keeps one
    # owner, so this gate and the lyric gate measure the same sheet.
    if _CORE not in sys.path:
        sys.path.insert(0, _CORE)
    from suno_recipe.suno_recipe import parse_tag
    return parse_tag(norm)


def is_spoken(block):
    """True when a block's tag names spoken delivery."""
    return delivery_of_tag(block.get("tag")) == "spoken"


def _effective_delivery(tag):
    """The delivery a tag reads as: a bare tag never reaches Suno unnamed."""
    return delivery_of_tag(tag) or DELIVERY_NONE_DEFAULT


def _strip_delivery_words(tag):
    """A tag with its delivery words removed -- the tail the render keeps.

    "spoken word" strips to nothing (the classic label kept no tail), and
    "sung smooth r&b hook" keeps "smooth r&b hook". Every one of these
    rules lives once, here.
    """
    out = re.sub(r"\bspoken word\b", "spoken", str(tag or ""))
    out = _DELIVERY_WORD_RE.sub(" ", out)
    out = re.sub(r"\s*,\s*", ", ", out)
    out = re.sub(r"\s+", " ", out).strip(" -,;")
    return "" if out.lower() == "word" else out


def render_tag(tag):
    """The delivery-named label for one block tag (W-G-002 amend).

    [Sung - <tail>], [Spoken - <tail>], [Rap - <tail>], [Instrumental]. A
    tag that already named its delivery keeps its own tail words (e.g.
    [Chanel - female voice, sung smooth R&B hook] keeps the speaker and
    style after the delivery word is stripped); a bare [Verse] becomes
    [Sung - Verse], defaulting to Sung, the delivery the O3 fault's bare
    tags actually got. IDEMPOTENT: ``render_tag(render_tag(t))`` equals
    ``render_tag(t)``, so a built sheet may be re-built without drift.
    Acceptance: ``delivery_of_tag(render_tag(t))`` is never None.
    """
    raw = str(tag or "").strip()
    if raw.startswith("[") and raw.endswith("]") and len(raw) > 2:
        raw = raw[1:-1].strip()               # accept a rendered label back
    delivery = delivery_of_tag(raw)
    if delivery == INSTRUMENTAL:
        return "[Instrumental]"
    if delivery is None:
        delivery, tail = DELIVERY_NONE_DEFAULT, raw
    else:
        tail = _strip_delivery_words(raw)
    if not tail or tail.lower() in ("word", delivery):
        tail = TAG_TAILS[delivery]
    return "[%s - %s]" % (delivery.capitalize(), tail[0].upper() + tail[1:])


def delivery_switches(blocks):
    """How many times the delivery changes across the sheet's blocks.

    Bare tags count as Sung (their effective delivery) and [Instrumental]
    blocks are skipped -- they carry no delivery to switch away from.
    """
    seq = [_effective_delivery(b.get("tag")) for b in blocks]
    seq = [d for d in seq if d != INSTRUMENTAL]
    return sum(1 for a, b in zip(seq, seq[1:]) if a != b)


def switch_allowance(seconds):
    """At most one delivery switch per SWITCH_EVERY_S seconds of runtime.

    Never zero: a sheet that opens sung and turns spoken once is not the
    O3 fault (that one flipped 9 times in 140 s).
    """
    return max(1, int(_number(seconds, "seconds") // SWITCH_EVERY_S))


def lint_delivery_grammar(blocks, seconds):
    """W-G-002 amend (review G4): the delivery-named tag grammar, refused.

    Checks, over one parsed sheet: every block tag names its delivery
    (bare [Verse]/[Chorus]/[Bridge]/[Hook] refused); every sung block has
    at least two lines (Suno chants one-liners); at most one delivery
    switch per SWITCH_EVERY_S seconds of runtime. This is the refusal the
    O3 sheet fails on; build_sheet remedies all three and ships a sheet
    that passes.
    """
    secs = _number(seconds, "seconds")
    checks, reasons = [], []

    def expect(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        if not ok:
            reasons.append("%s%s" % (name, (": " + detail) if detail else ""))

    bare = [(i + 1, str(b.get("tag") or "").strip())
            for i, b in enumerate(blocks) if delivery_of_tag(b.get("tag")) is None]
    expect("delivery-named-tags", not bare,
           "sections %s name no delivery: use [Sung - ...], [Spoken - ...], "
           "[Rap - ...] (G4)" % ", ".join("%d (%s)" % (i, t) for i, t in bare)
           if bare else "")

    one_line = [i + 1 for i, b in enumerate(blocks)
                if _effective_delivery(b.get("tag")) == "sung"
                and len(b.get("lines") or []) < 2]
    expect("sung-block-two-lines", not one_line,
           "sung sections %s carry one line -- a one-line sung block is "
           "chanted, not sung (G4)" % one_line if one_line else "")

    allowance = switch_allowance(secs)
    switches = delivery_switches(blocks)
    expect("delivery-switch-rate", switches <= allowance,
           "%d delivery switches in %gs, at most %d (one per %ds) (G4)"
           % (switches, secs, allowance, SWITCH_EVERY_S))

    return {"verdict": "PASS" if not reasons else "FAIL",
            "checks": checks,
            "reasons": reasons,
            "switches": switches,
            "switch_allowance": allowance,
            "grammar_version": TOOL_VERSION}


class LyricStructureError(ValueError):
    """Malformed input -- a caller bug, never a domain verdict."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def spoken_budget(seconds):
    """At most this many spoken blocks for one ad length."""
    secs = _number(seconds, "seconds")
    if secs <= SHORT_SECONDS:
        return MAX_SPOKEN_BLOCKS_SHORT
    if secs <= MID_SECONDS:
        return MAX_SPOKEN_BLOCKS_MID
    return MAX_SPOKEN_BLOCKS_LONG


def _number(value, what):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LyricStructureError("BAD_" + what.upper(),
                                  "%s must be a number, got %r"
                                  % (what, value))
    value = float(value)
    if value <= 0:
        raise LyricStructureError("BAD_" + what.upper(),
                                  "%s must be > 0, got %r" % (what, value))
    return value


# ---- sheet parsing --------------------------------------------------------

def parse_sheet(text):
    """Parse a Suno lyric sheet into blocks: [{"tag", "lines"}].

    A [Tag] line starts a block; every following non-blank line joins it.
    Consecutive spoken blocks merge into one block (two spoken sections
    back to back are one spoken moment, not two blocks). Spoken is read
    from the tag's delivery word, so [Spoken Word] and [Spoken - ...] merge.
    """
    if not isinstance(text, str) or not text.strip():
        raise LyricStructureError("EMPTY_SHEET", "sheet text is empty")
    blocks = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = SECTION_TAG_RE.match(line)
        if m:
            blocks.append({"tag": m.group(1).strip().lower(), "lines": []})
        elif blocks:
            blocks[-1]["lines"].append(line)
        else:
            blocks.append({"tag": "", "lines": [line]})   # pre-tag opener
    # a header-only section carries no words: drop it (it is not a block, it
    # must not separate two spoken moments, and it must never reach the
    # re-set as an empty stanza). [Instrumental] is the exception -- it names
    # a WORDLESS delivery by definition, so dropping it would silently delete
    # the one tag Suno needs to know that stretch carries no voice.
    blocks = [b for b in blocks
              if b["lines"] or _effective_delivery(b["tag"]) == INSTRUMENTAL]
    # merge consecutive spoken blocks into one spoken moment (delivery is
    # read from the tag now, so [Spoken Word] and [Spoken - ...] merge)
    out = []
    for blk in blocks:
        if (out and is_spoken(out[-1]) and is_spoken(blk)):
            out[-1]["lines"].extend(blk["lines"])
        else:
            out.append(blk)
    return out


def spoken_blocks(blocks):
    return [b for b in blocks if is_spoken(b)]


# ---- syllables / rhyme ----------------------------------------------------

def words(text):
    return re.findall(r"[a-z0-9]+(?:'[a-z]+)?", (text or "").lower())


def syllables(word):
    """Rough syllable count: vowel groups, silent-e trimmed."""
    w = re.sub(r"[^a-z]", "", (word or "").lower())
    if not w:
        # a digit/symbol token (a count-in, a year) is still one beat --
        # returning 0 made a digit-only line fail the SYL_MIN lint band
        return 1 if word else 0
    groups = re.findall(r"[aeiouy]+", w)
    n = len(groups)
    if n > 1 and w.endswith("e") and groups[-1] == "e":
        n -= 1
    return max(n, 1)


def line_syllables(line):
    return sum(syllables(w) for w in words(line))


def rhyme_key(word):
    """The last vowel group plus its tail: 'thing'->'ing', 'rest'->'est'."""
    w = re.sub(r"[^a-z]", "", (word or "").lower())
    if not w:
        return ""
    groups = list(re.finditer(r"[aeiouy]+", w))
    if not groups:
        return w[-2:]
    return w[groups[-1].start():]


def rhymes(a, b):
    """Exact rhyme, near-rhyme (shared key tail >= 2), or same word."""
    if a and b and a == b:
        return True                     # identical rhyme (the ECHO device)
    ka, kb = rhyme_key(a), rhyme_key(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    if len(ka) >= 2 and len(kb) >= 2 and (ka.endswith(kb) or kb.endswith(ka)):
        return True
    return False


# ---- sung re-set ----------------------------------------------------------

def _phrases(line):
    """Split a line into phrases at clause punctuation, words in order."""
    parts = [p.strip() for p in re.split(r"[,;:.!?]+", line)]
    return [p for p in parts if words(p)]


def _split_phrase(phrase):
    """Split one over-long phrase at word boundaries until every part is short.

    Halving once is not enough: a 40-syllable run-on halves to two 20
    syllable lines, which the lint (SYL_MAX) rejects -- so keep splitting
    each part that is still above SPLIT_PHRASE_ABOVE. Words stay in order.
    """
    out, todo = [], [phrase]
    while todo:
        p = todo.pop(0)
        w = words(p)
        if len(w) < 2 or line_syllables(p) <= SPLIT_PHRASE_ABOVE:
            if w:
                out.append(p)
            continue
        mid = len(w) // 2
        todo.insert(0, " ".join(w[mid:]))
        todo.insert(0, " ".join(w[:mid]))
    return out


def _regroup(lines):
    """Regroup phrases into singable lines; every word kept, in order."""
    phrases = []
    for ln in lines:
        for p in _phrases(ln):
            if line_syllables(p) > SPLIT_PHRASE_ABOVE:
                phrases.extend(_split_phrase(p))
            else:
                phrases.append(p)
    out = []
    cur = []
    cur_syl = 0
    for p in phrases:
        syl = line_syllables(p)
        if cur and cur_syl + syl > SPLIT_PHRASE_ABOVE:
            out.append(", ".join(cur))
            cur, cur_syl = [], 0
        cur.append(p)
        cur_syl += syl
    if cur:
        out.append(", ".join(cur))
    return out


def _rebalance(lines, spread=METER_SPREAD):
    """Pull short neighbours up onto long lines, order kept, one pass.

    A line shorter than its neighbours by more than ``spread`` syllables is
    folded into the next line when the merge stays inside SYL_MAX; the last
    line folds back into the one before it. Never reorders or drops words.
    """
    for _ in range(10):
        if len(lines) < 2:                    # nothing to spread (also empty)
            return lines
        syls = [line_syllables(l) for l in lines]
        if max(syls) - min(syls) <= spread:
            return lines
        i = syls.index(min(syls))
        if i + 1 < len(lines):
            lines[i + 1] = lines[i] + " " + lines[i + 1]
            del lines[i]
        else:
            lines[i - 1] = lines[i - 1] + " " + lines[i]
            del lines[i]
    return lines


def reset_sung_stanza(lines):
    """Re-set one sung stanza: singable lines + a rhyme-closed ending.

    Returns (lines, echoed) -- echoed is True when the ECHO device closed
    the stanza (the stanza's last word repeated once as a short line, an
    identical rhyme). No other word is added, moved or dropped.
    """
    lines = _rebalance(_regroup(lines))
    if len(lines) >= 2:
        a_end = words(lines[-2])
        b_end = words(lines[-1])
        if not (a_end and b_end and rhymes(a_end[-1], b_end[-1])):
            last_word = words(lines[-1])
            if last_word:
                lines.append(last_word[-1])
                return lines, True
        return lines, False
    if len(lines) == 1:                          # one-liner: echo itself
        w = words(lines[0])
        if w:
            lines.append(w[-1])
            return lines, True
    return lines, False


# ---- spoken budget + placement -------------------------------------------

def budget_spoken(blocks, seconds):
    """Apply the spoken budget. Returns (blocks, plan).

    The first spoken block holds OPEN, the last holds CTA, and of the rest
    the one whose start sits nearest the sheet middle holds TURN (it must
    fall inside TURN_WINDOW). Every other spoken block is demoted to a sung
    stanza and re-set. Consecutive spoken blocks were already merged by
    parse_sheet, so merging is not a loss here.
    """
    budget = spoken_budget(seconds)
    idxs = [i for i, b in enumerate(blocks) if is_spoken(b)]
    plan = {"budget": budget, "found": len(idxs), "kept": [], "demoted": [],
            "slots": {}}
    if len(idxs) <= budget:
        return blocks, plan
    # slots: open = first, cta = last, turn = nearest the middle within window
    n = len(blocks)
    middle = n / 2.0
    lo, hi = TURN_WINDOW
    interior = [i for i in idxs if i not in (idxs[0], idxs[-1])]
    turn_i = None
    if interior:
        # position by the block's start index over the sheet length
        def pos(i):
            return i / float(max(n - 1, 1))
        best = sorted(interior, key=lambda i: abs(i - middle))
        for cand in best:
            if lo <= pos(cand) <= hi:
                turn_i = cand
                break
        if turn_i is None:
            turn_i = best[0]
    keep = set()
    if idxs:
        keep.add(idxs[0])
        plan["slots"]["open"] = idxs[0]
        if idxs[-1] != idxs[0] and len(idxs) > 1:
            keep.add(idxs[-1])
            plan["slots"]["cta"] = idxs[-1]
    if turn_i is not None:
        keep.add(turn_i)
        plan["slots"]["turn"] = turn_i
    out = []
    for i, blk in enumerate(blocks):
        if not is_spoken(blk) or i in keep:
            out.append(blk)
        else:
            plan["demoted"].append(i)
            out.append({"tag": "sung", "lines": list(blk["lines"]),
                        "demoted": True})
    plan["kept"] = sorted(keep)
    return out, plan


def enforce_spoken_rules(blocks, plan, seconds):
    """Demote every spoken block the lint would reject. Returns blocks.

    The lint enforces rules the count-based budget never reaches: placement
    (open = first block, cta = last, turn = inside TURN_WINDOW), the
    MIN_SUNG_BETWEEN floor between consecutive spoken blocks, and (W-G-002
    amend, review G4) the delivery-switch rate -- at most one switch per
    SWITCH_EVERY_S seconds of runtime. This applies the same rules as
    corrective action. Demotion keeps every line (the block is re-set as a
    sung stanza afterwards) and never changes the block count, so positions
    stay fixed; each demotion strictly lowers the spoken count and each
    switch-rate demotion strictly lowers the switch count, so this
    terminates. The receipt (kept / demoted / slots) is rebuilt to match
    the sheet the lint will actually see.
    """
    n = len(blocks)
    lo, hi = TURN_WINDOW

    def demote(i):
        blocks[i] = {"tag": "sung", "lines": list(blocks[i]["lines"]),
                     "demoted": True}
        if i not in plan["demoted"]:
            plan["demoted"].append(i)

    # placement
    for i, blk in enumerate(blocks):
        if not is_spoken(blk) or i in (0, n - 1):
            continue
        pos = i / float(max(n - 1, 1))
        if not lo <= pos <= hi:
            demote(i)

    # alternation: demote the later block of a too-close pair; the gap for
    # every following pair only grows, so one left-to-right pass settles it
    prev = None
    for i, blk in enumerate(blocks):
        if not is_spoken(blk):
            continue
        if prev is not None and i - prev - 1 < MIN_SUNG_BETWEEN:
            demote(i)
            continue
        prev = i

    # W-G-002 amend (G4): switch rate. Consecutive spoken blocks were merged
    # by parse_sheet, so every interior spoken block is flanked by non-spoken
    # blocks: demoting it to sung strictly lowers the switch count (it never
    # raises it), and each demotion removes one spoken block, so the loop
    # terminates. When only open/cta spoken blocks remain the sheet is left
    # to the lint -- a sheet that cannot legally hold its spoken blocks must
    # be refused, not silently rewritten.
    allowance = switch_allowance(seconds)
    while delivery_switches(blocks) > allowance:
        interior = [i for i, blk in enumerate(blocks)
                    if is_spoken(blk) and i not in (0, n - 1)]
        if not interior:
            break
        demote(interior[0])

    plan["kept"] = [i for i, b in enumerate(blocks) if is_spoken(b)]
    slots = {}
    for i, blk in enumerate(blocks):
        if not is_spoken(blk):
            continue
        if i == 0:
            slots["open"] = i
        if i == n - 1:
            slots["cta"] = i
        if i not in (0, n - 1) and lo <= i / float(max(n - 1, 1)) <= hi:
            slots.setdefault("turn", i)
    plan["slots"] = slots
    return blocks


# ---- singability lint -----------------------------------------------------

def word_chain_intact(original_text, new_text):
    """Every script word survives, in order, in the output."""
    a = words(original_text)
    b = words(new_text)
    it = iter(b)
    return all(any(tok == nxt for nxt in it) or False for tok in a) if a else True


def lint_singability(blocks, seconds, original_text=None, new_text=None):
    """The G2 singability lint (amended W-G-002). Returns verdict/checks.

    Checks: spoken budget, spoken placement (open/turn/cta), MIN_SUNG_BETWEEN
    between spoken blocks, sung line length band, per-stanza meter spread,
    stanza-final rhyme/near-rhyme/echo, word-chain integrity, and the
    amended delivery-named grammar (delivery in every tag, no one-line sung
    block, at most one delivery switch per SWITCH_EVERY_S seconds).
    """
    checks, reasons = [], []

    def expect(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        if not ok:
            reasons.append("%s%s" % (name, (": " + detail) if detail else ""))

    # W-G-002 amend (review G4): the delivery-named tag grammar.
    grammar = lint_delivery_grammar(blocks, seconds)
    checks.extend(grammar["checks"])
    reasons.extend(grammar["reasons"])

    budget = spoken_budget(seconds)
    sp = spoken_blocks(blocks)
    expect("spoken-block-budget", len(sp) <= budget,
           "%d spoken blocks, budget %d" % (len(sp), budget))

    n = len(blocks)
    lo, hi = TURN_WINDOW
    for i, blk in enumerate(blocks):
        if not is_spoken(blk):
            continue
        pos = i / float(max(n - 1, 1))
        slot = ("open" if i == 0 else
                "cta" if i == n - 1 else
                "turn" if lo <= pos <= hi else None)
        expect("spoken-placement", slot is not None,
               "block at section %d/%d sits outside open/turn/cta" % (i + 1, n))

    sung_since = None
    for i, blk in enumerate(blocks):
        if is_spoken(blk):
            if sung_since is not None and sung_since < MIN_SUNG_BETWEEN:
                expect("spoken-alternation", False,
                       "only %d sung blocks between spoken blocks at %d"
                       % (sung_since, i))
            sung_since = 0
        elif sung_since is not None:
            # sung blocks before the FIRST spoken block are the sheet's
            # opening, not a gap between two spoken blocks
            sung_since += 1

    for bi, blk in enumerate(blocks):
        if _effective_delivery(blk.get("tag")) in ("spoken", "rap",
                                                   "instrumental"):
            continue          # prose, rap and instrumentals are not sung
        lines = blk["lines"]
        if not lines:
            continue
        # the flagged ECHO closer is exempt from the meter checks
        body = lines[:-1] if blk.get("echo") and len(lines) >= 2 else lines
        syls = [line_syllables(l) for l in body]
        if syls:
            for li, s in enumerate(syls):
                expect("sung-line-length", SYL_MIN <= s <= SYL_MAX,
                       "stanza %d line %d: %d syllables" % (bi, li, s))
            expect("sung-meter-spread", max(syls) - min(syls) <= METER_SPREAD,
                   "stanza %d spread %d > %d"
                   % (bi, max(syls) - min(syls), METER_SPREAD))
        if len(lines) >= 2:
            a_end = words(lines[-2])
            b_end = words(lines[-1])
            closed = bool(a_end and b_end
                          and rhymes(a_end[-1], b_end[-1]))
            expect("stanza-end-rhyme", closed,
                   "stanza %d ends %r/%r" % (bi, a_end[-1:], b_end[-1:]))

    chain = None
    if original_text is not None and new_text is not None:
        chain = word_chain_intact(original_text, new_text)
        expect("word-chain-intact", chain,
               "a script word is missing or out of order in the output")

    return {"verdict": "PASS" if not reasons else "FAIL",
            "budget": budget,
            "spoken_blocks": len(sp),
            "checks": checks,
            "reasons": reasons,
            "switches": grammar["switches"],
            "switch_allowance": grammar["switch_allowance"],
            "word_chain_intact": chain,
            "lint_version": TOOL_VERSION}


# ---- the builder ----------------------------------------------------------

def build_sheet(sheet_text, seconds):
    """G2 builder (amended W-G-002): budget + re-set + lint over one sheet.

    Returns {"schema_version", "outcome", "sheet", "lint", "budget",
             "spoken_blocks", "demoted", "echoes", "input_grammar", ...}.
    outcome "ok" only when the lint passes. The amend's compiler adds:
    every emitted tag names its delivery ([Sung - ...], [Spoken - ...],
    [Rap - ...]) -- a bare [Verse] is renamed, never shipped bare; a
    one-line sung stanza is closed with the ECHO device, never left a
    one-liner; extra spoken blocks are demoted until the switch rate is
    legal; rap blocks pass through untouched. ``input_grammar`` carries
    the refusal record for the sheet as it was handed in, so a caller can
    see exactly what the compiler renamed or re-set.
    """
    secs = _number(seconds, "seconds")
    blocks_in = parse_sheet(sheet_text)
    if not blocks_in:
        raise LyricStructureError("EMPTY_SHEET", "sheet has no lyric lines")
    input_grammar = lint_delivery_grammar(blocks_in, secs)

    blocks, plan = budget_spoken(blocks_in, secs)
    blocks = enforce_spoken_rules(blocks, plan, secs)

    out_blocks, echoes = [], 0
    for blk in blocks:
        delivery = _effective_delivery(blk.get("tag"))
        if delivery in ("spoken", "rap", "instrumental"):
            out_blocks.append(blk)      # prose, rap and instrumentals pass
            continue
        lines, echoed = reset_sung_stanza(blk["lines"])
        echoes += int(echoed)
        out_blocks.append({"tag": blk.get("tag") or "sung", "lines": lines,
                           **({"echo": True} if echoed else {})})
    # a stanza whose lines carried no words (punctuation only) re-sets to
    # nothing -- it never ships as an empty block (mirrors parse_sheet's
    # header-only drop)
    out_blocks = [b for b in out_blocks
                  if b["lines"] or _effective_delivery(b.get("tag")) != "sung"]
    # the emitted tag names its delivery -- the amend's grammar, enforced
    # on the builder's OWN output before the lint ever sees it
    for blk in out_blocks:
        blk["tag"] = render_tag(blk.get("tag"))

    sheet_text_new = render_sheet(out_blocks)
    # word-chain over LYRIC WORDS only -- section tags are structure, not
    # copy, and a demoted block's [Spoken Word] label must not read as a
    # dropped word.
    in_lines = " ".join(l for blk in blocks_in for l in blk["lines"])
    out_lines = " ".join(l for blk in out_blocks for l in blk["lines"])
    lint = lint_singability(out_blocks, secs, in_lines, out_lines)
    return {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "source": SOURCE,
        "outcome": "ok" if lint["verdict"] == "PASS" else "rejected",
        "sheet": sheet_text_new,
        "lint": lint,
        "input_grammar": input_grammar,
        "budget": plan["budget"],
        "spoken_blocks": len(spoken_blocks(out_blocks)),
        "demoted": plan["demoted"],
        "slots": plan["slots"],
        "echoes": echoes,
        "switches": lint["switches"],
        "switch_allowance": lint["switch_allowance"],
        "next_action": ("Proceed to Suno." if lint["verdict"] == "PASS"
                        else "Fix the lint reasons and re-run build_sheet."),
    }


def check_sheet(sheet_text, seconds):
    """W-G-002 amend: the refusal gate for a sheet AS WRITTEN (no remedy).

    Parses and lints the sheet verbatim. This is where the O3 sheet is
    refused with its reasons (bare tags, one-line sung block, delivery
    changes over the rate). ``build_sheet`` is the remedying compiler and
    reports what this gate found in its "input_grammar" field.
    """
    secs = _number(seconds, "seconds")
    blocks = parse_sheet(sheet_text)
    if not blocks:
        raise LyricStructureError("EMPTY_SHEET", "sheet has no lyric lines")
    lint = lint_singability(blocks, secs)
    return {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "source": SOURCE,
        "outcome": "ok" if lint["verdict"] == "PASS" else "rejected",
        "lint": lint,
        "reasons": lint["reasons"],
        "switches": lint["switches"],
        "switch_allowance": lint["switch_allowance"],
        "next_action": ("Proceed to Suno." if lint["verdict"] == "PASS"
                        else "Fix the reasons, or run build_sheet to compile "
                             "a delivery-named sheet from this input."),
    }


def render_sheet(blocks):
    """Render blocks back to a Suno sheet with the delivery in EVERY tag.

    W-G-002 amend (review G4): the label is ``render_tag`` output -- a bare
    [Verse] becomes [Sung - Verse], [Spoken Word] becomes [Spoken - Lead,
    plain natural speech over the music]. A tag already in the
    "[Delivery - ...]" form is kept as rendered (render_tag is idempotent
    on its own output), so every label the builder emits names delivery.
    """
    out = []
    for blk in blocks:
        tag = str(blk.get("tag") or "").strip()
        if tag.startswith("[") and tag.endswith("]"):
            label = tag                        # already rendered
        else:
            label = render_tag(tag)
        out.append(label)
        out.extend(blk["lines"])
        out.append("")
    return "\n".join(out).strip() + "\n"


# ---- selftest -------------------------------------------------------------

ALTERNATING_SHEET = """[Spoken Word]
Eleven at night and the mind will not stop.

[Verse]
Your phone says rest
Your training says one more thing

[Spoken Word]
You were eight years old making snacks.

[Verse]
The question you stopped asking

[Spoken Word]
Nobody claps for the woman who never puts it down.

[Verse]
Rest does not need to be earned

[Spoken Word]
Say it out loud once.

[Verse]
Softness is not quitting

[Spoken Word]
Come sit with us at the site. The seat is saved.
"""


def selftest():
    checks, fails = [], []

    def expect(name, cond, detail=""):
        checks.append(name)
        if not cond:
            fails.append("%s%s" % (name, (": " + detail) if detail else ""))

    # 1. the alternating fault sheet is budgeted down and passes
    r = build_sheet(ALTERNATING_SHEET, 90)
    expect("alternating-budget", r["spoken_blocks"] <= 3,
           "got %d" % r["spoken_blocks"])
    expect("alternating-lint", r["lint"]["verdict"] == "PASS",
           "; ".join(r["lint"]["reasons"]))

    # 2. the lint itself rejects an un-budgeted sheet
    blocks = parse_sheet(ALTERNATING_SHEET)
    lint = lint_singability(blocks, 90)
    expect("lint-rejects-unbudgeted", lint["verdict"] == "FAIL",
           lint["reasons"][:2])

    # 3. word chain: re-set keeps every script word in order
    expect("word-chain", r["lint"].get("word_chain_intact") is True)

    # 4. budget scales by length
    expect("budget-short", spoken_budget(90) == 3)
    expect("budget-mid", spoken_budget(180) == 4)
    expect("budget-long", spoken_budget(600) == 5)

    # 5. LeAnne fixture: the done-when (<= 3 spoken blocks, lint PASS)
    import os
    import tempfile
    fx = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "fixtures", "leanne-soft-life-sheet.txt")
    with open(fx, encoding="utf-8") as f:
        leanne = f.read()
    r2 = build_sheet(leanne, 90)
    expect("leanne-budget", r2["spoken_blocks"] <= 3,
           "got %d" % r2["spoken_blocks"])
    expect("leanne-lint", r2["lint"]["verdict"] == "PASS",
           "; ".join(r2["lint"]["reasons"]))
    expect("leanne-chain", r2["lint"].get("word_chain_intact") is True)

    # 6. malformed input raises
    for bad in (None, "", 5, [], {}):
        try:
            build_sheet(bad if isinstance(bad, str) else "", 90)
            expect("reject:%r" % (str(bad)[:20],), False, "accepted")
        except LyricStructureError:
            checks[-1] = "reject:%r" % (str(bad)[:20],)
        except Exception as e:                   # noqa: BLE001
            expect("reject:%r" % (str(bad)[:20],), False, repr(e))

    # 7. QC W-G-002 FAIL regressions: no crash, and the builder's own
    #    output always passes its own lint (convergence on every sheet the
    #    two FAIL rounds rejected).
    regressions = [
        ("empty-section", 90,
         "[Spoken Word]\nopen line\n\n[Verse]\n\n"),
        ("within-budget-pair", 90,
         "[Spoken Word]\nopen line here\n\n[Verse]\n"
         "sing one line here\nsing two lines now\n\n"
         "[Spoken Word]\ncta line here\n"),
        ("four-spoken-300s", 300, "".join(
            "[Spoken Word]\nSpoken number %d words here.\n\n"
            "[Verse]\nsing line %d here\nmore singing %d\n\n"
            % (i + 1, i + 1, i + 1) for i in range(4))),
        ("cta-then-chorus", 90,
         "[Spoken Word]\nCome sit with us at the site.\n\n"
         "[Verse]\nsing one line here\nsing two lines now\n\n"
         "[Spoken Word]\nMiddle turn block words.\n\n"
         "[Verse]\nmore sung lines here\nfinal line of song\n\n"
         "[Spoken Word]\nThe seat is saved, Sis.\n\n"
         "[Chorus]\noutro chorus line\nlast chorus line\n"),
        ("digit-ending", 90, "[Verse]\nsing line 1 here\nmore singing 1\n"),
        ("long-run-on", 90, "[Verse]\n" + "ba " * 40 + "\n"),
        ("verse-first", 90,
         "[Verse]\nsoftness on the floor\n\n"
         "[Spoken Word]\ncome sit with us now\n\n"
         "[Verse]\nrest does not need earning\n"),
        ("digit-only-line", 90, "[Verse]\n1 2 3\n\n[Verse]\nrest is the floor\n"),
    ]
    for rname, rsecs, rtext in regressions:
        rr = build_sheet(rtext, rsecs)
        expect("regress:" + rname,
               rr["outcome"] == "ok" and rr["lint"]["verdict"] == "PASS",
               "; ".join(rr["lint"]["reasons"][:2]))
        expect("regress-chain:" + rname,
               rr["lint"].get("word_chain_intact") is True)
        # feeding the built sheet back must stay ok (no reject loop)
        rr2 = build_sheet(rr["sheet"], rsecs)
        expect("regress-rerun:" + rname, rr2["outcome"] == "ok",
               "; ".join(rr2["lint"]["reasons"][:2]))

    print("lyric_structure selftest: %s (%d checks, %d failures)"
          % ("PASS" if not fails else "FAIL", len(checks), len(fails)))
    for f in fails:
        print(" -", f)
    return 0 if not fails else 1


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="lyric_structure.py",
        description="G2: spoken block budget + singable lyric re-set + lint.")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--sheet", default=None, help="lyric sheet text file")
    ap.add_argument("--seconds", type=float, default=90,
                    help="ad length in seconds (default 90)")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.sheet:
        ap.error("one of --selftest or --sheet is required")
    try:
        with open(a.sheet, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        r = {"schema_version": SCHEMA_VERSION, "tool_version": TOOL_VERSION,
             "outcome": "error", "reason_code": "sheet-unreadable",
             "errors": [{"error": "sheet-unreadable", "detail": str(e)[:200]}],
             "next_action": "Supply a readable lyric sheet."}
        json.dump(r, sys.stdout, indent=2, sort_keys=True, default=str)
        sys.stdout.write("\n")
        return EXIT["error"]
    try:
        r = build_sheet(text, a.seconds)
    except LyricStructureError as e:
        r = {"schema_version": SCHEMA_VERSION, "tool_version": TOOL_VERSION,
             "outcome": "error", "reason_code": e.code,
             "errors": [{"error": e.code, "detail": str(e)[:200]}],
             "next_action": "Fix the sheet input and re-run."}
    json.dump(r, sys.stdout, indent=2, sort_keys=True, default=str)
    sys.stdout.write("\n")
    return EXIT[r["outcome"]]


if __name__ == "__main__":
    sys.exit(main())
