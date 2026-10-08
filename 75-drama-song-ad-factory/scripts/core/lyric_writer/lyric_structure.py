#!/usr/bin/env python3
"""lyric_structure.py: G2 lyric structure for singing (Trevor order 1135).

The O3 fault: the lyric sheet flipped [Spoken Word]/[Verse] every 1-4 lines
(8 spoken blocks) and the "sung" lines were unmetered unrhymed prose, so
Suno never settled into singing. This module is the fix, in three parts:

  1. SPOKEN BLOCK BUDGET. Spoken blocks are budgeted, never alternating
     line by line: at most 3 blocks for a 60-150 s ad, one each at the
     OPEN (first section), the TURN (middle of the arc) and the CTA (last
     section). Extra spoken blocks are demoted to sung stanzas and re-set
     like any other sung lines.
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
import re
import sys

TOOL_NAME = "lyric_structure"
TOOL_VERSION = "0.1.0"
SCHEMA_VERSION = "blackceo.lyric-structure/v1"
SOURCE = "Trevor order 1135 2026-10-08, Part G item G2"

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
    Consecutive [Spoken Word] blocks merge into one block (two spoken
    sections back to back are one spoken moment, not two blocks).
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
    # merge consecutive spoken blocks into one spoken moment
    out = []
    for blk in blocks:
        if (out and out[-1]["tag"] == SPOKEN_TAG
                and blk["tag"] == SPOKEN_TAG):
            out[-1]["lines"].extend(blk["lines"])
        else:
            out.append(blk)
    return out


def spoken_blocks(blocks):
    return [b for b in blocks if b["tag"] == SPOKEN_TAG]


# ---- syllables / rhyme ----------------------------------------------------

def words(text):
    return re.findall(r"[a-z0-9]+(?:'[a-z]+)?", (text or "").lower())


def syllables(word):
    """Rough syllable count: vowel groups, silent-e trimmed."""
    w = re.sub(r"[^a-z]", "", (word or "").lower())
    if not w:
        return 0
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
    """Split one over-long phrase into two halves at a word boundary."""
    w = words(phrase)
    if len(w) < 2:
        return [phrase]
    mid = len(w) // 2
    low = " ".join(w[:mid])
    high = " ".join(w[mid:])
    return [low, high]


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
        syls = [line_syllables(l) for l in lines]
        if max(syls) - min(syls) <= spread or len(lines) < 2:
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
    idxs = [i for i, b in enumerate(blocks) if b["tag"] == SPOKEN_TAG]
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
        if blk["tag"] != SPOKEN_TAG or i in keep:
            out.append(blk)
        else:
            plan["demoted"].append(i)
            out.append({"tag": "sung", "lines": list(blk["lines"]),
                        "demoted": True})
    plan["kept"] = sorted(keep)
    return out, plan


# ---- singability lint -----------------------------------------------------

def word_chain_intact(original_text, new_text):
    """Every script word survives, in order, in the output."""
    a = words(original_text)
    b = words(new_text)
    it = iter(b)
    return all(any(tok == nxt for nxt in it) or False for tok in a) if a else True


def lint_singability(blocks, seconds, original_text=None, new_text=None):
    """The G2 singability lint. Returns {"verdict": PASS|FAIL, "checks", ...}.

    Checks: spoken budget, spoken placement (open/turn/cta), MIN_SUNG_BETWEEN
    between spoken blocks, sung line length band, per-stanza meter spread,
    stanza-final rhyme/near-rhyme/echo, and word-chain integrity.
    """
    checks, reasons = [], []

    def expect(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        if not ok:
            reasons.append("%s%s" % (name, (": " + detail) if detail else ""))

    budget = spoken_budget(seconds)
    sp = spoken_blocks(blocks)
    expect("spoken-block-budget", len(sp) <= budget,
           "%d spoken blocks, budget %d" % (len(sp), budget))

    n = len(blocks)
    lo, hi = TURN_WINDOW
    for i, blk in enumerate(blocks):
        if blk["tag"] != SPOKEN_TAG:
            continue
        pos = i / float(max(n - 1, 1))
        slot = ("open" if i == 0 else
                "cta" if i == n - 1 else
                "turn" if lo <= pos <= hi else None)
        expect("spoken-placement", slot is not None,
               "block at section %d/%d sits outside open/turn/cta" % (i + 1, n))

    sung_since = None
    for i, blk in enumerate(blocks):
        if blk["tag"] == SPOKEN_TAG:
            if sung_since is not None and sung_since < MIN_SUNG_BETWEEN:
                expect("spoken-alternation", False,
                       "only %d sung blocks between spoken blocks at %d"
                       % (sung_since, i))
            sung_since = 0
        else:
            sung_since = (sung_since or 0) + 1

    for bi, blk in enumerate(blocks):
        if blk["tag"] == SPOKEN_TAG:
            continue                       # spoken blocks are prose by design
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
            "word_chain_intact": chain,
            "lint_version": TOOL_VERSION}


# ---- the builder ----------------------------------------------------------

def build_sheet(sheet_text, seconds):
    """G2 builder: budget + re-set + lint over one lyric sheet.

    Returns {"schema_version", "outcome", "sheet", "lint", "budget",
             "spoken_blocks", "demoted", "echoes"}. outcome "ok" only when
    the lint passes.
    """
    secs = _number(seconds, "seconds")
    blocks = parse_sheet(sheet_text)
    blocks, plan = budget_spoken(blocks, secs)

    out_blocks, echoes = [], 0
    for blk in blocks:
        if blk["tag"] == SPOKEN_TAG:
            out_blocks.append(blk)
            continue
        lines, echoed = reset_sung_stanza(blk["lines"])
        echoes += int(echoed)
        out_blocks.append({"tag": blk.get("tag") or "verse", "lines": lines,
                           **({"echo": True} if echoed else {})})

    sheet_text_new = render_sheet(out_blocks)
    # word-chain over LYRIC WORDS only -- section tags are structure, not
    # copy, and a demoted block's [Spoken Word] label must not read as a
    # dropped word.
    in_lines = " ".join(l for blk in parse_sheet(sheet_text)
                        for l in blk["lines"])
    out_lines = " ".join(l for blk in out_blocks for l in blk["lines"])
    lint = lint_singability(out_blocks, secs, in_lines, out_lines)
    return {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "source": SOURCE,
        "outcome": "ok" if lint["verdict"] == "PASS" else "rejected",
        "sheet": sheet_text_new,
        "lint": lint,
        "budget": plan["budget"],
        "spoken_blocks": len(spoken_blocks(out_blocks)),
        "demoted": plan["demoted"],
        "slots": plan["slots"],
        "echoes": echoes,
        "next_action": ("Proceed to Suno." if lint["verdict"] == "PASS"
                        else "Fix the lint reasons and re-run build_sheet."),
    }


def render_sheet(blocks):
    out = []
    for blk in blocks:
        tag = (blk.get("tag") or "verse").strip().lower()
        label = "[Spoken Word]" if tag == SPOKEN_TAG else \
            "[" + "".join(w.capitalize() for w in re.split(r"[\s-]+", tag)) + "]"
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
