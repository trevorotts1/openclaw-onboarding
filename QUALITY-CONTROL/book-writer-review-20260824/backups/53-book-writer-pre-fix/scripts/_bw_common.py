#!/usr/bin/env python3
# =============================================================================
# SKILL 53 — BOOK WRITER :: SHARED PROVER PRIMITIVES
# -----------------------------------------------------------------------------
# Deterministic, stdlib-only helpers shared by the twelve fail-closed Book Writer
# provers (prove_bw_intake / prove_bw_titlelock / prove_bw_stories /
# prove_bw_chapters / prove_bw_continuity / prove_bw_tone / prove_bw_challenge /
# prove_bw_433 / prove_bw_placeholder / prove_bw_noanthropic / prove_bw_anon /
# prove_bw_process). No network, no model judgement, no third-party imports. Runs
# identically on every box (operator or client).
#
# DESIGN LAW: enforcement, not description. Every measurer works on the STRIPPED
# text of the artifact — markdown syntax, list bullets, code fences, and collapsed
# whitespace are removed before anything is counted. A model's SELF-REPORTED count
# (a "Final word count: 2,800 words" line) is NEVER trusted; we measure the real
# words. That is why a whitespace-padding attack (pad a short chapter to length
# with blank lines/spaces) cannot fool a floor: whitespace collapses to nothing.
#
# EXIT CODE CONTRACT (every prover):
#   0  PASS      — every rule satisfied.
#   2  AUTOFAIL  — one or more AF-BK-* violations (fail-closed).
#   3  USAGE/IO  — missing file / unreadable / invalid input (still fail-closed).
# =============================================================================
"""Shared deterministic primitives for the Skill 53 Book Writer provers."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# ---- exit codes (shared by every prover) ------------------------------------
EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3

# ---- SACRED constants (from the PRD §5.4 sacred constraints + GOLDEN-BOOK-BIBLE) --
CHAPTER_COUNT = 12               # exactly 12 chapters (anthology exempt — separate Skill 54)
CHAP_WORD_MIN = 2000             # per-chapter stripped-word floor
CHAP_WORD_MAX = 3500             # per-chapter stripped-word ceiling
TONE_WORD_FLOOR = 3000           # blended "The {First} {Last} Tone" floor (shared tone core)
CHALLENGE_DAYS = 30              # 30-Day Challenge: exactly 30 day-sections
FOUR_OUTCOMES = 4                # 4x3x3: exactly 4 Transformational Outcomes
TITLES_433 = 30                  # 4x3x3: exactly 30 program-title options
PHASES_433 = 4                   # 4x3x3: 4 phases
CHAPTERS_PER_PHASE = 3           # 4x3x3: 3 chapters per phase (4x3=12)

# The required intake fields for a full/4x3x3 book run (PRD §4.3). book_stories,
# cover_description and both tone styles accept "N/A" as a real (permitted) answer.
INTAKE_REQUIRED = (
    "version", "mode", "first_name", "last_name", "ideal_avatar", "niche",
    "primary_goal", "tone_style_1", "tone_style_2", "book_about",
    "book_stories", "cover_description",
)
VERSION_ENUM = ("book", "brand")
MODE_ENUM = ("full", "4x3x3")

_BOILERPLATE = {
    "", "todo", "tbd", "...", "<fill>", "<fill me>", "fill me", "xxx",
    "your answer here", "answer here", "example", "placeholder", "lorem ipsum",
}
# "N/A" spellings that count as a real, permitted non-answer.
_NA_TOKENS = {"n/a", "na", "none", "n.a."}

# ---- regexes ----------------------------------------------------------------
_HEADER_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*\S)\s*$")          # markdown ATX header
_MD_INLINE_RE = re.compile(r"[*_`~#>|]")                          # inline markdown punctuation
_CODEFENCE_RE = re.compile(r"^\s*```")
_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?")
# A chapter heading: "# Chapter 1 — Title", "## Chapter 1: Title", "Chapter 1. Title",
# or an ATX header whose text begins "Chapter <n>".
_CHAPTER_HEAD_RE = re.compile(r"^\s{0,3}#{0,6}\s*chapter\s+(\d{1,2})\b", re.IGNORECASE)
# A 30-Day-Challenge day-section heading: "## Day 1 — ...", "Day 1 -", "Day 1:".
_DAY_HEAD_RE = re.compile(r"^\s{0,3}#{0,6}\s*day\s+(\d{1,2})\b\s*[—\-:]", re.IGNORECASE)
# Unresolved template tokens: {{...}} or $('...') / $("...").
_PLACEHOLDER_RE = re.compile(r"\{\{[^}]*\}\}|\$\(\s*['\"][^'\"]*['\"]\s*\)")
# Anthropic / claude model-id family (case-insensitive by design for ledger ids).
_ANTHROPIC_RE = re.compile(r"anthropic|claude", re.IGNORECASE)
# Numbered / bulleted top-level list item (for counting titles / outcomes).
_NUM_ITEM_RE = re.compile(r"^\s*\d+[\.\)]\s+\S")
_BULLET_ITEM_RE = re.compile(r"^\s*[-*+•]\s+\S")


# ---- IO ---------------------------------------------------------------------
def read_text(path) -> str:
    """Read a UTF-8 text artifact or fail-closed (EXIT_USAGE)."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        print("USAGE/IO: cannot read %s: %s" % (path, exc), file=sys.stderr)
        sys.exit(EXIT_USAGE)


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("USAGE/IO: cannot read/parse JSON %s: %s" % (path, exc), file=sys.stderr)
        sys.exit(EXIT_USAGE)


# ---- stripped-text measurement ----------------------------------------------
def strip_markdown(text: str) -> str:
    """Reduce markdown/prose to bare words + newlines. Code fences dropped, inline
    markdown punctuation removed, each line trimmed. This is what every counter
    measures — never the raw bytes, so whitespace padding is inert."""
    out_lines = []
    in_fence = False
    for line in text.splitlines():
        if _CODEFENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        out_lines.append(_MD_INLINE_RE.sub("", line).strip())
    return "\n".join(out_lines)


def word_count(text: str) -> int:
    """Deterministic STRIPPED word count. Collapses all whitespace to single tokens,
    so blank-line / space padding cannot inflate the number. The model's
    self-reported count is irrelevant here — this is the measured truth."""
    return len(_WORD_RE.findall(strip_markdown(text)))


def normalize_phrase(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace — the canonical form used
    for story key-phrase matching and any tolerant substring comparison. Deterministic
    and order-preserving (unlike a token set)."""
    lowered = text.lower()
    # keep alphanumerics and single spaces; everything else becomes a space.
    cleaned = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", cleaned).strip()


# ---- structure parsing ------------------------------------------------------
def find_chapters(text: str):
    """Return an ordered list of (chapter_number:int, heading_line_index:int) for
    every chapter heading found, matched ONLY against heading-shaped lines."""
    found = []
    for i, line in enumerate(text.splitlines()):
        m = _CHAPTER_HEAD_RE.match(line)
        if m:
            found.append((int(m.group(1)), i))
    return found


def chapter_bodies(text: str) -> dict:
    """Return {chapter_number: body_text} — each chapter's text from its heading
    (exclusive) up to the next chapter heading (exclusive)."""
    lines = text.splitlines()
    heads = find_chapters(text)
    bodies = {}
    for idx, (num, start) in enumerate(heads):
        end = heads[idx + 1][1] if idx + 1 < len(heads) else len(lines)
        bodies[num] = "\n".join(lines[start + 1:end])
    return bodies


def count_day_sections(text: str) -> int:
    """Count 30-Day-Challenge day-sections by heading pattern 'Day <n> —|-|:'."""
    return sum(1 for line in text.splitlines() if _DAY_HEAD_RE.match(line))


def count_list_items(text: str) -> int:
    """Count numbered OR bulleted top-level list items (titles, outcomes)."""
    return sum(1 for line in text.splitlines()
               if _NUM_ITEM_RE.match(line) or _BULLET_ITEM_RE.match(line))


def find_placeholders(text: str):
    """Every unresolved {{...}} / $('...') token in the text."""
    return _PLACEHOLDER_RE.findall(text)


def is_present(value) -> bool:
    """Non-empty, not boilerplate. 'N/A' counts as a real (permitted) answer."""
    s = ("" if value is None else str(value)).strip()
    return bool(s) and s.lower() not in _BOILERPLATE


def is_na(value) -> bool:
    """The value is a permitted N/A non-answer."""
    s = ("" if value is None else str(value)).strip().lower()
    return s in _NA_TOKENS


# ---- result plumbing --------------------------------------------------------
class Result:
    """Accumulates AF-BK-* violations; decides the exit code fail-closed."""

    def __init__(self, prover: str):
        self.prover = prover
        self.violations = []   # list of (code, message)
        self.notes = []

    def fail(self, code: str, message: str):
        self.violations.append((code, message))

    def note(self, message: str):
        self.notes.append(message)

    @property
    def passed(self) -> bool:
        return not self.violations

    def emit(self, as_json: bool) -> int:
        if as_json:
            print(json.dumps({
                "prover": self.prover,
                "passed": self.passed,
                "violations": [{"code": c, "message": m} for c, m in self.violations],
                "notes": self.notes,
            }, indent=2))
        else:
            if self.passed:
                print("PASS [%s]: all rules satisfied." % self.prover)
                for n in self.notes:
                    print("  - %s" % n)
            else:
                print("AUTOFAIL [%s]: %d violation(s)" % (self.prover, len(self.violations)),
                      file=sys.stderr)
                for c, m in self.violations:
                    print("  [%s] %s" % (c, m), file=sys.stderr)
        return EXIT_PASS if self.passed else EXIT_AUTOFAIL


def selftest_report(name: str, checks) -> int:
    """checks: list of (label, ok_bool). Returns 0 iff all ok."""
    ok = True
    for label, good in checks:
        print("  [%s] %s" % ("OK" if good else "XX", label))
        ok = ok and good
    print("== %s self-test: %s ==" % (name, "ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return 0 if ok else 1
