#!/usr/bin/env python3
# =============================================================================
# SKILL 54 — ANTHOLOGY WRITER :: SHARED PROVER PRIMITIVES
# -----------------------------------------------------------------------------
# Deterministic, stdlib-only helpers shared by the Anthology Writer provers
# (prove_aw_intake / prove_aw_fidelity / prove_aw_tone / prove_aw_chapter /
# aw_build_check). No network, no model judgement, no third-party imports.
# Runs identically on every box (operator or client).
#
# DESIGN LAW: enforcement, not description. Every measurer here works on the
# STRIPPED text of the artifact — markdown syntax, list bullets, code fences,
# and collapsed whitespace are removed before anything is counted. A model's
# SELF-REPORTED count (a "Final word count: 2600 words" line, a COMPLETION
# VERIFICATION number) is NEVER trusted; we measure the real words. A
# whitespace-padding attack (pad a short chapter with blank lines/spaces to look
# long) cannot fool a floor: whitespace collapses to nothing.
#
# EXIT CODE CONTRACT (every prover):
#   0  PASS      — every rule satisfied.
#   2  AUTOFAIL  — one or more AF-AW-* violations (fail-closed).
#   3  USAGE/IO  — missing file / unreadable / invalid input (still fail-closed).
# =============================================================================
"""Shared deterministic primitives for the Skill 54 Anthology Writer provers."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# ---- exit codes (shared by every prover) ------------------------------------
EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3

# ---- SACRED floors (PRD §3.5 — anthology chapter contract) ------------------
# One chapter per contributor, stripped-word band; the tone doc is the blended
# "The {First} {Last} Tone" with its own stripped-word floor (tone-core R7).
CHAPTER_WORD_MIN = 2000
CHAPTER_WORD_MAX = 3500
TONE_WORD_FLOOR = 3000            # shared-utils/tone-writing-core 08-blended-tone
TONE_INFLUENCES_REQUIRED = 4      # blended tone is built from EXACTLY 4 analyses

# The mandatory self-attestation footer every finalized long-form artifact ends
# with. Its numbers are IGNORED (we measure); only its PRESENCE is required, so a
# stripped chapter can never masquerade as complete without it.
VERIFY_BLOCK_MARKER = "COMPLETION VERIFICATION"

# The four required intake fields the anthology pipeline actually consumes
# (PRD §3.3). personal_stories is captured but may be the literal string "N/A".
INTAKE_REQUIRED = ("anthology_title", "first_name", "last_name", "chapter_premise")
INTAKE_OPTIONAL = ("personal_stories", "client_folder_name", "email", "phone",
                   "subtitle_hint", "target_reader")

# Credential-shaped intake keys are FORBIDDEN (D7): a client's provider keys are
# resolved per box from the client's own OpenClaw config — never taken through
# intake, never the operator's. Any key that looks like a secret fails closed.
_CREDENTIAL_KEY_RE = re.compile(
    r"(api[_-]?key|apikey|secret|token|bearer|password|passwd|"
    r"openrouter|anthropic|openai|access[_-]?key|private[_-]?key|"
    r"credential|auth[_-]?token)",
    re.I,
)

# ---- regexes ----------------------------------------------------------------
_MD_INLINE_RE = re.compile(r"[*_`~#>|]")                          # inline markdown punctuation
_CODEFENCE_RE = re.compile(r"^\s*```")
_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?")
_HEADER_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*\S)\s*$")           # markdown ATX header
_BOLD_HEADER_RE = re.compile(r"^\s*\*\*(.+?)\*\*\s*:?\s*$")       # a bold-only header line
# Unresolved template placeholders that must never survive into a final artifact.
_PLACEHOLDER_RE = re.compile(r"\{\{[^}]+\}\}|\[\[[^\]]+\]\]|<[A-Z][A-Z0-9_]{2,}>")


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
    self-reported count is irrelevant — this is the measured truth."""
    return len(_WORD_RE.findall(strip_markdown(text)))


def normalized_tokens(text: str, min_len: int = 1) -> list:
    """Lowercased alnum tokens of the STRIPPED text (for placement/coverage)."""
    return [t for t in _WORD_RE.findall(strip_markdown(text).lower()) if len(t) >= min_len]


def normalize_phrase(text: str) -> str:
    """A whitespace/case-normalized form of a short phrase for byte-exact-ish
    lock comparisons (collapses runs of whitespace, lowercases). Used so a
    locked title matches regardless of incidental spacing, but a CHANGED word
    still breaks the lock."""
    return re.sub(r"\s+", " ", strip_markdown(text).lower()).strip()


def contains_phrase(haystack: str, needle: str) -> bool:
    """True iff the normalized needle phrase occurs in the normalized haystack."""
    n = normalize_phrase(needle)
    if not n:
        return True
    return n in normalize_phrase(haystack)


def unresolved_placeholders(text: str) -> list:
    """Every unresolved template placeholder ({{..}}, [[..]], <ALLCAPS>) left in
    a finalized artifact. A non-empty list is a hard fail (AF-AW-PLACEHOLDER)."""
    return sorted(set(_PLACEHOLDER_RE.findall(text)))


# ---- section / header parsing -----------------------------------------------
def header_lines(text: str):
    """Yield (line_index, header_text) for every line that acts as a header:
    a markdown ATX header (#..######) or a bold-only line."""
    for i, line in enumerate(text.splitlines()):
        m = _HEADER_RE.match(line)
        if m:
            yield i, m.group(1)
            continue
        m = _BOLD_HEADER_RE.match(line)
        if m:
            yield i, m.group(1)


def credential_shaped_keys(obj) -> list:
    """Return the intake keys whose NAME looks like a secret (fail-closed D7)."""
    if not isinstance(obj, dict):
        return []
    return sorted(k for k in obj if _CREDENTIAL_KEY_RE.search(str(k)))


def story_phrases(intake: dict) -> list:
    """The non-'N/A' personal-story anchor phrases the chapter must place. Each
    story item may be a string or an object with a 'summary'/'anchor' field; a
    literal 'N/A' (any case) means the contributor has no personal story and the
    placement check is vacuously satisfied for that slot."""
    raw = intake.get("personal_stories")
    items = []
    if isinstance(raw, str):
        if raw.strip() and raw.strip().upper() != "N/A":
            items = [raw]
    elif isinstance(raw, list):
        items = raw
    anchors = []
    for it in items:
        if isinstance(it, dict):
            val = it.get("anchor") or it.get("summary") or it.get("text") or ""
        else:
            val = str(it)
        val = val.strip()
        if val and val.upper() != "N/A":
            anchors.append(val)
    return anchors


# ---- result plumbing --------------------------------------------------------
class Result:
    """Accumulates AF-AW-* violations; decides the exit code fail-closed."""

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
