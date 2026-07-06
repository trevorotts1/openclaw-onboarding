#!/usr/bin/env python3
# =============================================================================
# SKILL 55 — PRODUCT BIO :: SHARED PROVER PRIMITIVES
# -----------------------------------------------------------------------------
# Deterministic, stdlib-only helpers shared by the five fail-closed Product Bio
# provers (prove_pb_intake / prove_pb_fidelity / prove_pb_wordcount /
# prove_pb_sections / prove_pb_html). No network, no model judgement, no
# third-party imports. Runs identically on every box (operator or client).
#
# DESIGN LAW: enforcement, not description. Every measurer here works on the
# STRIPPED text of the artifact — markdown syntax, list bullets, code fences,
# and collapsed whitespace are removed before anything is counted. A model's
# SELF-REPORTED count (the "Final word count: 6500 words" line, the COMPLETION
# VERIFICATION numbers) is NEVER trusted; we measure the real words. This is why
# a whitespace-padding attack (pad a short bio with blank lines/spaces to look
# long) cannot fool the word-count floor: whitespace collapses to nothing.
#
# EXIT CODE CONTRACT (every prover):
#   0  PASS      — every rule satisfied.
#   2  AUTOFAIL  — one or more AF-PB-* violations (fail-closed).
#   3  USAGE/IO  — missing file / unreadable / invalid input (still fail-closed).
# =============================================================================
"""Shared deterministic primitives for the Skill 55 Product Bio provers."""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

# ---- exit codes (shared by every prover) ------------------------------------
EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3

# ---- SACRED constants (from source prompt P1 — 01-product-bio-writer.md) -----
# The 10 mandatory sections, in order, each with the header keyword patterns the
# section prover matches against a document's HEADER lines only (never prose).
SECTIONS = [
    ("product_name",      "Product Name",        [r"product\s+name"]),
    ("power_adjectives",  "Power Adjectives",    [r"power\s+adjective", r"\badjectives?\b"]),
    ("who_its_best_for",  "Who It's Best For",   [r"who\s+it'?s?\s+best\s+for", r"best\s+for", r"ideal\s+customer"]),
    ("product_description", "Product Description", [r"product\s+description"]),
    ("positioning",       "Product Positioning", [r"positioning"]),
    ("objections",        "Objections",          [r"objection"]),
    ("faqs",              "FAQs",                [r"\bfaqs?\b", r"frequently\s+asked"]),
    ("social_proof",      "Social Proof",        [r"social\s+proof", r"testimonial"]),
    ("storybrand",        "StoryBrand 2.0",      [r"storybrand"]),
    ("signature_closes",  "Signature Closes",    [r"signature\s+close"]),
]

# The 24 signature-close styles the tracker mandates (P1 lines 900-928, 947).
# The prompt TEACHES 20 styles but the tracker + anti-truncation rule demand 24;
# per PRD O3 the GATE enforces 24 (the later, stricter law). Verbatim, in order.
CLOSE_STYLES = [
    "Michelle Obama", "TD Jakes", "Grant Cardone", "David Goggins", "Simon Sinek",
    "Mel Robbins", "Brené Brown", "Dave Chappelle", "Ali Wong", "Raymond Reddington",
    "Iyanla Vanzant", "Tony Robbins", "Oprah", "Gary Vaynerchuk", "Daymond John",
    "Les Brown", "John Maxwell", "Rachel Rodgers", "Dean Graziosi", "Hook Point",
    "Sense of Urgency", "Luxury Positioning", "FOMO", "Challenger",
]
CLOSES_REQUIRED = 24

# Per-close matching patterns (tolerant of accent/punctuation variants).
_CLOSE_PATTERNS = {
    "Michelle Obama":     r"michelle\s+obama",
    "TD Jakes":           r"t\.?\s*d\.?\s*jakes",
    "Grant Cardone":      r"grant\s+cardone",
    "David Goggins":      r"david\s+goggins",
    "Simon Sinek":        r"simon\s+sinek",
    "Mel Robbins":        r"mel\s+robbins",
    "Brené Brown":        r"bren[eé]\s+brown",
    "Dave Chappelle":     r"dave\s+chappelle",
    "Ali Wong":           r"ali\s+wong",
    "Raymond Reddington": r"raymond\s+reddington",
    "Iyanla Vanzant":     r"iyanla\s+vanzant",
    "Tony Robbins":       r"tony\s+robbins",
    "Oprah":              r"\boprah\b",
    "Gary Vaynerchuk":    r"gary\s+vaynerchuk",
    "Daymond John":       r"daymond\s+john",
    "Les Brown":          r"les\s+brown",
    "John Maxwell":       r"john\s+maxwell",
    "Rachel Rodgers":     r"rachel\s+rodgers",
    "Dean Graziosi":      r"dean\s+graziosi",
    "Hook Point":         r"hook\s+point",
    "Sense of Urgency":   r"sense\s+of\s+urgency",
    "Luxury Positioning": r"luxury\s+positioning",
    "FOMO":               r"\bfomo\b",
    "Challenger":         r"challenger",
}

# The 7 StoryBrand 2.0 beats (P1 line 898). Each maps to accepted keyword forms.
STORYBRAND_BEATS = {
    "Character":       [r"\bcharacter\b", r"\bhero\b"],
    "Problem":         [r"\bproblem\b"],
    "Guide":           [r"\bguide\b"],
    "Plan":            [r"\bplan\b"],
    "Call to Action":  [r"call[\s-]?to[\s-]?action", r"\bcta\b"],
    "Avoid Failure":   [r"avoid(?:ing)?\s+failure", r"\bfailure\b", r"\bstakes\b"],
    "Success":         [r"\bsuccess\b"],
}

# Per-section enumerated-item floor bands (min, max) — from P1 tracker.
# max is None where the source states only a minimum.
COUNT_BANDS = {
    "product_name":     (10, None),   # 10 different ways to introduce the product
    "power_adjectives": (15, 20),     # 15-20 power adjectives with explanations
    "objections":       (8, 10),      # 8-10 objections
    "faqs":             (10, 12),     # 10-12 FAQs
    "social_proof":     (8, 10),      # 8-10 unattributed testimonial statements
}

# Word-count band for the whole bio (P1 lines 952-953).
WORDCOUNT_MIN = 6000
WORDCOUNT_MAX = 7000

# The MANDATORY FINAL STATEMENT block header (P1 line 992).
VERIFY_BLOCK_MARKER = "COMPLETION VERIFICATION"

# The four required intake fields the IP actually consumes (PRD §3.3, §2.1).
INTAKE_REQUIRED = ("product_name", "product_description", "first_name", "last_name")

# ---- client-exact override channel (logged, tied to the locked brief) --------
# The word band (WORDCOUNT_MIN..MAX) and the per-section enumerated COUNT_BANDS are
# DEFAULT floors. A client-stated EXACT target is honored VERBATIM — never floored,
# capped, or substituted (fleet-wide absolute law) — but ONLY when it is LOGGED in
# the locked brief (working/intake.json). An override that is APPLIED (passed on the
# command line) but NOT present-and-equal in the locked brief is fail-closed
# (AF-PB-OVERRIDE-UNLOGGED): a run can never quietly relax a SACRED band from an
# unlogged scratch value. The SACRED STRUCTURE is NEVER overridable — the 10
# sections, their order, the 24 named signature closes, and the 7 StoryBrand beats
# have no override channel; only the numeric quantity bands do. Mirrors Skill 57
# prove_bands._resolve (the logged-override-wins-and-is-recorded pattern).
AF_OVERRIDE_UNLOGGED = "AF-PB-OVERRIDE-UNLOGGED"

# Locked-brief keys that carry a logged override.
WORD_OVERRIDE_KEY = "word_count_override"        # a band for the whole-bio word floor
SECTION_OVERRIDE_KEY = "section_count_overrides"  # {section_id: band} for COUNT_BANDS


def parse_band(spec):
    """Normalize an override spec into an (lo, hi) int tuple, or None when the spec
    is absent/malformed. Accepts [lo, hi], {"min": lo, "max": hi}, {"exact": n}, or
    a bare int n (an exact target). A malformed spec returns None (no override), so
    a garbage value can never silently widen a band."""
    if spec is None or isinstance(spec, bool):
        return None
    if isinstance(spec, (int, float)):
        n = int(spec)
        return (n, n)
    if isinstance(spec, (list, tuple)) and len(spec) == 2 \
            and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in spec):
        return (int(spec[0]), int(spec[1]))
    if isinstance(spec, dict):
        ex = spec.get("exact")
        if isinstance(ex, (int, float)) and not isinstance(ex, bool):
            n = int(ex)
            return (n, n)
        lo, hi = spec.get("min"), spec.get("max")
        if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) \
                and not isinstance(lo, bool) and not isinstance(hi, bool):
            return (int(lo), int(hi))
    return None


def resolve_band(default_lo, default_hi, logged_spec, applied_spec=None):
    """Return (lo, hi, overridden, unlogged) for a numeric band.

    - no applied + no logged  -> the DEFAULT band (overridden=False).
    - logged only             -> the logged band (the sanctioned path: reading the
                                 override straight from the locked brief means it is
                                 logged and applied by construction).
    - applied == logged       -> the override band (overridden=True).
    - applied with no matching logged band -> the DEFAULT band + unlogged=True, so
                                 the caller raises AF-PB-OVERRIDE-UNLOGGED and still
                                 measures against the untouched SACRED floor.
    """
    logged = parse_band(logged_spec)
    applied = parse_band(applied_spec)
    if applied is not None:
        if logged is None or applied != logged:
            return default_lo, default_hi, False, True
        return applied[0], applied[1], True, False
    if logged is not None:
        return logged[0], logged[1], True, False
    return default_lo, default_hi, False, False


def load_intake(intake_path):
    """Read the locked brief (the ONE logged override channel). Returns the intake
    dict, or {} when the path is absent/unreadable — an absent brief is not itself a
    failure here (it just means no override is logged, so the default band stands);
    P0 already gated intake presence fail-closed via prove_pb_intake."""
    if not intake_path:
        return {}
    try:
        obj = json.loads(Path(intake_path).read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except (OSError, ValueError):
        return {}


def resolved_word_band(intake, applied_spec=None):
    """Convenience: resolve the whole-bio word band from a locked-brief dict."""
    return resolve_band(WORDCOUNT_MIN, WORDCOUNT_MAX,
                        intake.get(WORD_OVERRIDE_KEY) if isinstance(intake, dict) else None,
                        applied_spec)

# ---- regexes ----------------------------------------------------------------
_HEADER_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*\S)\s*$")          # markdown ATX header
_BOLD_HEADER_RE = re.compile(r"^\s*\*\*(.+?)\*\*\s*:?\s*$")       # a bold-only line acting as a header
_NUM_ITEM_RE = re.compile(r"^\s*\d+[\.\)]\s+\S")                  # "1. ..." / "1) ..."
_BULLET_ITEM_RE = re.compile(r"^\s*[-*+•]\s+\S")                  # "- ..." / "* ..." / "• ..."
_MD_INLINE_RE = re.compile(r"[*_`~#>|]")                          # inline markdown punctuation
_CODEFENCE_RE = re.compile(r"^\s*```")
_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?")


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
    """Reduce markdown/prose to bare words + newlines. Code fences dropped,
    inline markdown punctuation removed, each line trimmed. This is what every
    counter measures — never the raw bytes, so whitespace padding is inert."""
    out_lines = []
    in_fence = False
    for line in text.splitlines():
        if _CODEFENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        stripped = _MD_INLINE_RE.sub("", line)
        out_lines.append(stripped.strip())
    return "\n".join(out_lines)


def word_count(text: str) -> int:
    """Deterministic STRIPPED word count. Collapses all whitespace to single
    tokens, so blank-line / space padding cannot inflate the number. The model's
    self-reported count is irrelevant here — this is the measured truth."""
    return len(_WORD_RE.findall(strip_markdown(text)))


def normalized_tokens(text: str, min_len: int = 1) -> list:
    """Lowercased alnum tokens of the STRIPPED text (for content-loss diffing)."""
    return [t for t in _WORD_RE.findall(strip_markdown(text).lower()) if len(t) >= min_len]


# ---- section parsing --------------------------------------------------------
def header_lines(text: str):
    """Yield (line_index, header_text) for every line that acts as a header:
    a markdown ATX header (#..######) or a bold-only line. Prose never matches,
    so a section keyword appearing mid-paragraph is NOT counted as the section."""
    for i, line in enumerate(text.splitlines()):
        m = _HEADER_RE.match(line)
        if m:
            yield i, m.group(1)
            continue
        m = _BOLD_HEADER_RE.match(line)
        if m:
            yield i, m.group(1)


def find_sections(text: str) -> dict:
    """Return {section_id: (first_header_line_index, header_text)} for each of
    the 10 sections found, matched ONLY against header lines. First match wins."""
    heads = list(header_lines(text))
    found = {}
    for sid, _title, patterns in SECTIONS:
        for idx, htext in heads:
            hl = htext.lower()
            if any(re.search(p, hl) for p in patterns):
                found[sid] = (idx, htext)
                break
    return found


def section_body_lines(text: str, sid: str) -> list:
    """The raw lines belonging to a section: from its header line (exclusive) up
    to the next of ANY of the 10 section headers (exclusive)."""
    lines = text.splitlines()
    found = find_sections(text)
    if sid not in found:
        return []
    start = found[sid][0]
    boundaries = sorted(i for (i, _h) in found.values() if i > start)
    end = boundaries[0] if boundaries else len(lines)
    return lines[start + 1:end]


def count_enumerated_items(lines) -> int:
    """Count enumerated items (numbered OR bulleted top-level list items)."""
    n = 0
    for line in lines:
        if _NUM_ITEM_RE.match(line) or _BULLET_ITEM_RE.match(line):
            n += 1
    return n


def count_numbered_items(lines) -> int:
    """Count strictly numbered items ('1.' / '1)') — used where the source is an
    explicitly numbered list (intros, adjectives, objections, FAQs, social proof)."""
    return sum(1 for line in lines if _NUM_ITEM_RE.match(line))


# ---- close-style + storybrand detection -------------------------------------
def closes_found(text: str) -> list:
    """The distinct canonical close-style names present anywhere in the STRIPPED
    text (matched case-insensitively, accent/punctuation tolerant)."""
    hay = strip_markdown(text).lower()
    present = []
    for name in CLOSE_STYLES:
        if re.search(_CLOSE_PATTERNS[name], hay):
            present.append(name)
    return present


def storybrand_beats_found(text: str) -> list:
    hay = strip_markdown(text).lower()
    present = []
    for beat, pats in STORYBRAND_BEATS.items():
        if any(re.search(p, hay) for p in pats):
            present.append(beat)
    return present


# ---- result plumbing --------------------------------------------------------
class Result:
    """Accumulates AF-PB-* violations; decides the exit code fail-closed."""

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
