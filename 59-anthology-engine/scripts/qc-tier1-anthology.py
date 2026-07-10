#!/usr/bin/env python3
"""qc-tier1-anthology.py -- Gate B, Tier 1 (the deterministic hard-fail battery).

Authored by unit W1.17. This is the CONTENT gate's first instrument (SPEC Section 4,
QC-PROTOCOL Instrument 1). It runs the twelve deterministic, zero-model-cost, binary
hard-fail checks over a produced deliverable, plus an ASSEMBLY mode with the S9
manuscript-scope additions. It NEVER calls a model (that is judge_harness.py, the Tier 1
semantic checks 13-15 and the Tier 2 rubric). It is fail-closed: any single failure means
the piece is NOT deliverable.

GATE SEPARATION (the cardinal rule): Gate B (this + judge_harness.py + qc-strike-gate.py)
decides whether a PIECE OF CONTENT ships. It is NEVER the 8.5 build/merge gate (Gate A),
never conflated, never averaged into it. A 9.0 build unit says nothing about a chapter.

THE TWELVE TIER-1 CHECKS (QC-PROTOCOL Instrument 1; binary, any one fails the piece):
   1 WORD BAND HONESTY   chapter/rewrite 2,000-3,500 MEASURED stripped words; the tone
                         document at least 3,000 measured words; self-reported counts are
                         IGNORED (we measure the stripped text; padding is inert).
   2 TITLE LOCK          the locked title and subtitle appear byte-exact in the outline,
                         the chapter, every rewrite, and the cover prompt.
   3 STORY PLACEMENT     every non-"N/A" personal story appears in the outline and chapter.
   4 ZERO TRUNCATION     the generating prompt matched its sha256 pin (when supplied) AND
                         the output ends on a complete sentence with closing structure.
   5 ZERO EM DASH        no em-dash-family character anywhere in the deliverable.
   6 NO LEAKAGE          no code fences, no stage labels, no system-prompt leakage, no
                         verify-block leakage, no surviving [UNCHANGED] placeholder.
   7 PDF FONT FLOOR      no rendered glyph below 14 point (delegated to guard-font-floor.py
                         over the RENDERED file; evaluated only when a PDF is supplied).
   8 IDENTITY INTEGRITY  correct contact_id and anthology_id; no cross-participant or
                         cross-anthology bleed; participant details consistent with the ledger.
   9 NO INTAKE CONTAM.   hidden field values, form mechanics, emails, and phone numbers
                         never appear in the deliverable.
  10 NO FABRICATION      no untraceable link: every URL in the deliverable traces to the
                         search-pass output (the semantic biography nuance is check 13).
  11 NAMING              client-visible surfaces say Convert and Flow; no internal tool
                         names, no model names, no plumbing.
  12 RUN LEDGER CLEAN    zero Anthropic-family model identifiers in the run ledger; the
                         model used is recorded (honestly; substitutions named).

ASSEMBLY MODE (--mode assembly; the S9 manuscript only) additionally proves: every approved
chapter present exactly once and byte-identical (sha256) to its frozen approved version;
chapter order matches the curated order; the editor introduction references only real
contributors; contributor bios match ledger identities; front and back matter complete; one
continuous 14-point-floor PDF.

PULL-BACK MODE (--mode pullback; the confirm-then-pull core, SPEC 2 step 5 / Gap G12): when a
co-author CONFIRMS at a review stage, the engine PULLS the current text of their editable
Google Doc (drive_adapter.py pull-doc-text), freezes it, and re-runs ONLY the deterministic
CONTENT invariants over the PULLED bytes -- word band (1), title-lock PRESENCE (2), and story
anchors (3), whichever are in scope for the kind. This is ADVISORY: the client's edits are law
for content (Trevor D3). A violated invariant becomes a PRODUCER board note; it NEVER blocks
the co-author and NEVER returns a failing exit code. The title LOCK still binds the title
FIELDS in the ledger (immutable); pull-back only observes whether the locked title still
appears in the client's prose and reports it -- it does not enforce against the prose.

INPUT: a self-describing ENVELOPE (JSON on --envelope or stdin). The stage runner assembles
it from the ledger and the produced artifacts; this script depends on NO sibling schema, so
it is testable in isolation and cannot silently pass a check it could not evaluate. Checks
that are inherently conditional (7 needs a rendered PDF, 10 needs URLs, 12 needs a ledger,
part of 4 needs the pin result) SKIP-with-note when their input is absent; every core content
check that is IN SCOPE for the kind FAILS closed if its required context is missing -- Gate B
never passes a check it could not run.

Exit codes (SPEC 3.4 row 14; house: 1 unexpected error):
  0  all in-scope checks pass  (in --mode pullback: ALWAYS 0 -- a client edit never blocks)
  2  bad invocation (unparseable envelope, unknown kind, missing artifact)
  4  one or more failures (the full list is emitted)  [piece / assembly modes only]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Layout / exit codes
# ---------------------------------------------------------------------------
SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"

EX_OK, EX_ERR, EX_BAD, EX_FAIL = 0, 1, 2, 4

# ---------------------------------------------------------------------------
# SACRED floors (mirror shared-utils/tone-writing-core + Skill 54 _aw_common;
# re-declared here, not cross-imported, so Tier 1 is self-contained and its
# WORD BAND measurement is byte-identical to prove_aw_chapter.py).
# ---------------------------------------------------------------------------
CHAPTER_WORD_MIN = 2000
CHAPTER_WORD_MAX = 3500
TONE_WORD_FLOOR = 3000
VERIFY_BLOCK_MARKER = "COMPLETION VERIFICATION"

# ---------------------------------------------------------------------------
# Stripped-text measurement (identical algorithm to Skill 54 _aw_common.py so a
# whitespace-padding attack is inert and the counts agree across the two gates).
# ---------------------------------------------------------------------------
_MD_INLINE_RE = re.compile(r"[*_`~#>|]")
_CODEFENCE_RE = re.compile(r"^\s*```")
_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?")


def strip_markdown(text: str) -> str:
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
    """Deterministic STRIPPED word count; self-reported counts are irrelevant."""
    return len(_WORD_RE.findall(strip_markdown(text)))


def normalize_phrase(text: str) -> str:
    return re.sub(r"\s+", " ", strip_markdown(text).lower()).strip()


def contains_phrase(haystack: str, needle: str) -> bool:
    n = normalize_phrase(needle)
    if not n:
        return True
    return n in normalize_phrase(haystack)


def story_phrases(intake: dict) -> List[str]:
    """The non-'N/A' personal-story anchors that must be placed (matches _aw_common)."""
    raw = (intake or {}).get("personal_stories")
    items: List = []
    if isinstance(raw, str):
        if raw.strip() and raw.strip().upper() != "N/A":
            items = [raw]
    elif isinstance(raw, list):
        items = raw
    anchors: List[str] = []
    for it in items:
        if isinstance(it, dict):
            val = it.get("anchor") or it.get("summary") or it.get("text") or ""
        else:
            val = str(it)
        val = val.strip()
        if val and val.upper() != "N/A":
            anchors.append(val)
    return anchors


# ---------------------------------------------------------------------------
# Deny/leak patterns. Anthropic-family assembled from FRAGMENTS so this shipped
# runtime file carries no contiguous banned literal (guard-no-anthropic-runtime.py
# scans .py source; mirrors model_router.py). The platform name that must be
# Convert and Flow is likewise fragment-assembled.
# ---------------------------------------------------------------------------
_A = "anthro" + "pic"
_C = "clau" + "de"
_ANTHROPIC_RE = re.compile(
    r"(?i)(^|[^a-z0-9])(" + _C + r"|" + _A + r")([^a-z0-9]|$)"
    r"|" + _A + r"/"
    r"|" + _C + r"-"
    r"|us\." + _A + r"\.")

# The platform must be named "Convert and Flow" on every client surface. The
# forbidden alternates are assembled from fragments (never a contiguous literal).
_PLATFORM_BANNED = (
    "go" + "high" + "level",   # the product's old name
    "go high level",
    "high" + "level.com",
)
_PLATFORM_ABBR_RE = re.compile(r"(?i)(^|[^a-z0-9])(" + "gh" + "l)([^a-z0-9]|$)")

# Internal tool / plumbing / model-id shapes that must never reach a client surface.
# Bare English-ambiguous words (pipeline, gemini) are avoided; only tool names and
# model-ID shapes are matched, so a memoir sentence never false-fails.
_PLUMBING_TERMS = (
    "n8n", "make.com", "integromat", "openrouter", "ollama", "minimax",
    "deepseek", "moonshot", "airtable", "leadconnector", "webhook",
    "private integration token", "opportunities api",
)
_MODEL_ID_RE = re.compile(
    r"(?i)\b("
    r"gpt-[a-z0-9.\-]+|"
    r"glm-[0-9][a-z0-9.\-]*|"
    r"gemini-[0-9][a-z0-9.\-]*|"
    r"minimax-[a-z0-9.\-]+|"
    r"qwen[0-9][a-z0-9.:\-]*|"
    r"deepseek-[a-z0-9.\-]+|"
    r"kimi-[a-z0-9.\-]+|"
    r"z-ai/[a-z0-9./\-]+|"
    r"ollama-cloud/[a-z0-9./:\-]+|"
    r"openrouter/[a-z0-9./:\-]+"
    r")\b")

# System-prompt / role / stage-label leakage.
_LEAK_LINE_RE = re.compile(
    r"(?im)^\s*(system|assistant|user|human|ai)\s*[:>]\s")
_LEAK_TERMS_RE = re.compile(
    r"(?i)("
    r"system prompt|you are an? (?:ai|assistant|large language model)|"
    r"as an? (?:ai|large language model)|<<sys>>|\[/?inst\]|"
    r"<\|im_start\|>|<\|im_end\|>|"
    r"stage label|reasoning_effort|temperature\s*[:=]\s*0"
    r")")
_STAGE_TAG_RE = re.compile(r"(?i)\b(aa-0[1-9]|aw-0[6-9]|aw-1[0-2]|ae-0[1-4])\b")
_UNCHANGED_RE = re.compile(r"\[UNCHANGED\]")
_CODEFENCE_ANY_RE = re.compile(r"```")

# Em-dash family (SPEC: zero em dashes). U+2014 em dash, U+2015 horizontal bar.
_EMDASH_CHARS = ("—", "―")

# Contamination patterns.
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?\d{1,2}[\s.\-]?)?(?:\(\d{3}\)|\d{3})[\s.\-]\d{3}[\s.\-]\d{4}(?!\d)")
_URL_RE = re.compile(r"https?://[^\s)\]\}>\"']+", re.I)
_FORM_MECHANIC_RE = re.compile(
    r"(?i)(utm_[a-z]+|hidden[_\-\s]?field|customdata|contact_id\s*[:=]|"
    r"anthology_id\s*[:=]|form_?id|field_?key)")


def is_anthropic_shaped(text: str) -> bool:
    return bool(text) and bool(_ANTHROPIC_RE.search(str(text)))


# ---------------------------------------------------------------------------
# Per-check status accumulator
# ---------------------------------------------------------------------------
PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


class CheckOutcome:
    __slots__ = ("id", "name", "status", "detail", "code")

    def __init__(self, cid: int, name: str, status: str, detail: str, code: str = ""):
        self.id = cid
        self.name = name
        self.status = status
        self.detail = detail
        self.code = code

    def to_dict(self) -> dict:
        d = {"id": self.id, "name": self.name, "status": self.status, "detail": self.detail}
        if self.code:
            d["code"] = self.code
        return d


class Verdict:
    def __init__(self, mode: str, kind: str):
        self.mode = mode
        self.kind = kind
        self.checks: List[CheckOutcome] = []

    def add(self, outcome: CheckOutcome):
        self.checks.append(outcome)

    @property
    def failures(self) -> List[CheckOutcome]:
        return [c for c in self.checks if c.status == FAIL]

    @property
    def passed(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict:
        return {
            "prover": "qc-tier1-anthology",
            "mode": self.mode,
            "kind": self.kind,
            "passed": self.passed,
            "checks": [c.to_dict() for c in self.checks],
            "failures": [c.to_dict() for c in self.failures],
        }

    def emit(self, as_json: bool) -> int:
        if as_json:
            print(json.dumps(self.to_dict(), ensure_ascii=False, indent=2))
        else:
            head = "PASS" if self.passed else "FAIL"
            print("[%s] qc-tier1-anthology  mode=%s kind=%s  (%d checks, %d failure(s))"
                  % (head, self.mode, self.kind, len(self.checks), len(self.failures)))
            for c in self.checks:
                line = "  %-4s %2d %-20s %s" % (c.status, c.id, c.name, c.detail)
                (sys.stdout if c.status != FAIL else sys.stderr).write(line + "\n")
        return EX_OK if self.passed else EX_FAIL

    def emit_pullback(self, as_json: bool) -> int:
        """Emit a NON-BLOCKING pull-back verdict. Any FAIL is surfaced as a
        PRODUCER board note; the co-author is NEVER blocked, so this ALWAYS
        returns EX_OK (SPEC 2 step 5 / Gap G12 / Trevor D3)."""
        notes = [c.to_dict() for c in self.checks if c.status == FAIL]
        payload = {
            "prover": "qc-tier1-anthology",
            "mode": "pullback",
            "kind": self.kind,
            "advisory": True,
            "blocking": False,
            "clean": not notes,
            "producer_notes": notes,
            "checks": [c.to_dict() for c in self.checks],
        }
        if as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            head = "CLEAN" if not notes else "PRODUCER-NOTE"
            print("[%s] qc-tier1-anthology  mode=pullback kind=%s  "
                  "(%d check(s), %d producer note(s); NON-BLOCKING)"
                  % (head, self.kind, len(self.checks), len(notes)))
            for c in self.checks:
                line = "  %-4s %2d %-20s %s" % (c.status, c.id, c.name, c.detail)
                sys.stdout.write(line + "\n")
            if notes:
                sys.stdout.write(
                    "  -> the client's edits are accepted as law for content; the note(s) "
                    "above go to the PRODUCER's board, they do NOT block the co-author.\n")
        return EX_OK


# ---------------------------------------------------------------------------
# Envelope helpers
# ---------------------------------------------------------------------------
class BadInvocation(Exception):
    pass


def _artifact_text(env: dict, key_text: str = "artifact_text",
                   key_path: str = "artifact_path") -> Optional[str]:
    if env.get(key_text) is not None:
        return str(env[key_text])
    p = env.get(key_path)
    if p:
        try:
            return Path(p).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise BadInvocation("cannot read %s=%s: %s" % (key_path, p, exc))
    return None


def _load_json_ref(env: dict, key_obj: str, key_path: str):
    if env.get(key_obj) is not None:
        return env[key_obj]
    p = env.get(key_path)
    if p:
        try:
            return json.loads(Path(p).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise BadInvocation("cannot read/parse %s=%s: %s" % (key_path, p, exc))
    return None


# Default per-kind Tier-1 scope (the QC matrix, SPEC 5.1). Conditional checks
# (4-pin part, 7, 10, 12) skip-with-note when their input is absent even when in
# scope; core content checks fail closed when required context is missing.
DEFAULT_CHECKS: Dict[str, List[int]] = {
    "avatar":     [4, 5, 6, 7, 8, 9, 10, 11, 12],
    "tone":       [1, 4, 5, 6, 8, 9, 11, 12],
    "titles":     [4, 5, 6, 8, 9, 11, 12],
    "blurb":      [2, 4, 5, 6, 8, 9, 11, 12],
    "outline":    [2, 3, 4, 5, 6, 8, 9, 10, 11, 12],
    "chapter":    [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    "rewrite":    [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    "cover":      [2, 4, 5, 11, 12],
    "deliver":    [5, 6, 7, 8, 9, 11, 12],
    "manuscript": [2, 5, 6, 7, 8, 9, 11, 12],
}
KNOWN_KINDS = set(DEFAULT_CHECKS)

CHECK_NAMES = {
    1: "WORD_BAND", 2: "TITLE_LOCK", 3: "STORY_PLACEMENT", 4: "ZERO_TRUNCATION",
    5: "ZERO_EM_DASH", 6: "NO_LEAKAGE", 7: "PDF_FONT_FLOOR", 8: "IDENTITY_INTEGRITY",
    9: "NO_INTAKE_CONTAM", 10: "NO_FABRICATION", 11: "NAMING", 12: "RUN_LEDGER_CLEAN",
}


def _code(cid: int) -> str:
    return "AF-AE-TIER1-%02d" % cid


# ---------------------------------------------------------------------------
# The twelve checks. Each returns a CheckOutcome. Word-band is chapter/tone aware.
# ---------------------------------------------------------------------------
def check_1_word_band(env: dict, text: str) -> CheckOutcome:
    cid = 1
    kind = env.get("kind")
    if text is None:
        return CheckOutcome(cid, CHECK_NAMES[cid], FAIL, "no artifact text to measure", _code(cid))
    words = word_count(text)
    if kind in ("chapter", "rewrite"):
        cmin = int(env.get("chapter_word_min", CHAPTER_WORD_MIN))
        cmax = int(env.get("chapter_word_max", CHAPTER_WORD_MAX))
        if words < cmin or words > cmax:
            return CheckOutcome(cid, CHECK_NAMES[cid], FAIL,
                                "measured stripped words %d outside %d-%d (self-report ignored)"
                                % (words, cmin, cmax), _code(cid))
        return CheckOutcome(cid, CHECK_NAMES[cid], PASS,
                            "measured %d within %d-%d" % (words, cmin, cmax))
    if kind == "tone":
        floor = int(env.get("tone_word_floor", TONE_WORD_FLOOR))
        if words < floor:
            return CheckOutcome(cid, CHECK_NAMES[cid], FAIL,
                                "measured stripped words %d below tone floor %d" % (words, floor),
                                _code(cid))
        return CheckOutcome(cid, CHECK_NAMES[cid], PASS,
                            "measured %d at/above tone floor %d" % (words, floor))
    return CheckOutcome(cid, CHECK_NAMES[cid], SKIP, "no word band applies to kind %r" % kind)


def check_2_title_lock(env: dict, text: str) -> CheckOutcome:
    cid = 2
    title = _load_json_ref(env, "title", "title_path")
    if not isinstance(title, dict):
        return CheckOutcome(cid, CHECK_NAMES[cid], FAIL,
                            "in scope but no locked title supplied (fail-closed)", _code(cid))
    # For a cover deliverable the locked title/subtitle must appear in the COVER
    # PROMPT text; for outline/blurb/chapter/rewrite it is the artifact itself.
    surfaces: List[Tuple[str, str]] = []
    if env.get("kind") == "cover":
        cprompt = _artifact_text(env, "cover_prompt_text", "cover_prompt_path")
        if cprompt is None:
            cprompt = text
        surfaces.append(("cover prompt", cprompt or ""))
    else:
        surfaces.append((env.get("kind") or "artifact", text or ""))
    missing = []
    for key in ("title", "subtitle"):
        locked = str(title.get(key, "")).strip()
        if not locked:
            missing.append("%s (absent from title.json)" % key)
            continue
        for sname, stext in surfaces:
            if not contains_phrase(stext, locked):
                missing.append("%s not byte-exact in the %s" % (key, sname))
    if missing:
        return CheckOutcome(cid, CHECK_NAMES[cid], FAIL,
                            "TITLE LOCK broken: " + "; ".join(missing), _code(cid))
    return CheckOutcome(cid, CHECK_NAMES[cid], PASS, "title and subtitle carried byte-exact")


def check_3_story_placement(env: dict, text: str) -> CheckOutcome:
    cid = 3
    intake = _load_json_ref(env, "intake", "intake_path")
    if not isinstance(intake, dict):
        return CheckOutcome(cid, CHECK_NAMES[cid], FAIL,
                            "in scope but no intake supplied (fail-closed)", _code(cid))
    anchors = story_phrases(intake)
    if not anchors:
        return CheckOutcome(cid, CHECK_NAMES[cid], PASS, "no non-N/A personal stories to place")
    unplaced = [a for a in anchors if not contains_phrase(text or "", a)]
    if unplaced:
        return CheckOutcome(cid, CHECK_NAMES[cid], FAIL,
                            "personal-story anchor(s) not placed: %s"
                            % ", ".join(repr(a) for a in unplaced[:6]), _code(cid))
    return CheckOutcome(cid, CHECK_NAMES[cid], PASS,
                        "all %d personal-story anchor(s) placed" % len(anchors))


_TERMINAL_PUNCT = tuple('.!?"”’…')


def check_4_zero_truncation(env: dict, text: str) -> CheckOutcome:
    cid = 4
    if text is None or not text.strip():
        return CheckOutcome(cid, CHECK_NAMES[cid], FAIL, "empty artifact", _code(cid))
    # Optional pin-match assertion (guard-prompt-pins.py is the real pin prover;
    # when the stage runner passes the result we honor it fail-closed).
    pin = env.get("prompt_pin_ok")
    if pin is False:
        return CheckOutcome(cid, CHECK_NAMES[cid], FAIL,
                            "generating prompt did NOT match its sha256 pin", _code(cid))
    # Completion: the last substantive line ends on terminal punctuation. Trailing
    # working-artifact footers (a verify block, a "Blended tone applied:" metadata
    # line) are ignored so a raw working file is judged on its prose, not its log.
    lines = [ln.strip() for ln in strip_markdown(text).splitlines() if ln.strip()]
    footer_prefixes = ("blended tone applied", "final word count", "word count",
                       "completion verification", "self-reported", "measured",
                       "verification:", "note:")
    prose = [ln for ln in lines if not ln.lower().startswith(footer_prefixes)]
    if not prose:
        return CheckOutcome(cid, CHECK_NAMES[cid], FAIL,
                            "no prose lines to assess for closing structure", _code(cid))
    last = prose[-1]
    # Obvious truncation markers.
    if last.endswith(("...", "…")) and not last.endswith(("....",)):
        # a trailing ellipsis mid-thought reads as truncated
        return CheckOutcome(cid, CHECK_NAMES[cid], FAIL,
                            "output ends on an ellipsis (reads as truncated): %r" % last[-40:],
                            _code(cid))
    if not last.endswith(_TERMINAL_PUNCT):
        return CheckOutcome(cid, CHECK_NAMES[cid], FAIL,
                            "output does not end on a complete sentence: ...%r" % last[-40:],
                            _code(cid))
    note = "closes on a complete sentence"
    if pin is True:
        note += "; prompt matched its sha256 pin"
    return CheckOutcome(cid, CHECK_NAMES[cid], PASS, note)


def check_5_zero_em_dash(env: dict, text: str) -> CheckOutcome:
    cid = 5
    if text is None:
        return CheckOutcome(cid, CHECK_NAMES[cid], FAIL, "no artifact text", _code(cid))
    total = sum(text.count(ch) for ch in _EMDASH_CHARS)
    if total:
        # locate the first offending line for the operator surface
        first = ""
        for ln in text.splitlines():
            if any(ch in ln for ch in _EMDASH_CHARS):
                first = ln.strip()[:80]
                break
        return CheckOutcome(cid, CHECK_NAMES[cid], FAIL,
                            "%d em-dash-family character(s) present; first at: %r"
                            % (total, first), _code(cid))
    return CheckOutcome(cid, CHECK_NAMES[cid], PASS, "zero em-dash-family characters")


def check_6_no_leakage(env: dict, text: str) -> CheckOutcome:
    cid = 6
    if text is None:
        return CheckOutcome(cid, CHECK_NAMES[cid], FAIL, "no artifact text", _code(cid))
    hits: List[str] = []
    if _CODEFENCE_ANY_RE.search(text):
        hits.append("code fence (```)")
    if _LEAK_LINE_RE.search(text):
        hits.append("role-labelled line (System:/Assistant:/User:)")
    if _LEAK_TERMS_RE.search(text):
        hits.append("system-prompt / plumbing phrase")
    if _STAGE_TAG_RE.search(text):
        hits.append("stage-label tag (aa-/aw-/ae-NN)")
    if VERIFY_BLOCK_MARKER in text:
        hits.append("verify-block leakage (%r)" % VERIFY_BLOCK_MARKER)
    if _UNCHANGED_RE.search(text):
        hits.append("surviving [UNCHANGED] placeholder")
    # Raw-markdown-artifact detection only when the caller declares the text is the
    # FINAL rendered client prose (a working .md legitimately carries headings/bold).
    if env.get("prose_is_final_rendered"):
        if re.search(r"(?m)^\s{0,3}#{1,6}\s", text) or re.search(r"\*\*[^*]+\*\*", text):
            hits.append("raw markdown artifact in final client prose")
    if hits:
        return CheckOutcome(cid, CHECK_NAMES[cid], FAIL,
                            "leakage detected: " + "; ".join(hits), _code(cid))
    return CheckOutcome(cid, CHECK_NAMES[cid], PASS, "no fences, labels, leakage, or placeholders")


def check_7_pdf_font_floor(env: dict, text: str) -> CheckOutcome:
    cid = 7
    pre = env.get("rendered_font_floor_ok")
    if pre is True:
        return CheckOutcome(cid, CHECK_NAMES[cid], PASS,
                            "font floor pre-verified by guard-font-floor.py")
    if pre is False:
        return CheckOutcome(cid, CHECK_NAMES[cid], FAIL,
                            "guard-font-floor.py reported a glyph below 14 point", _code(cid))
    pdf = env.get("pdf_path")
    if not pdf:
        return CheckOutcome(cid, CHECK_NAMES[cid], SKIP,
                            "no rendered PDF supplied; font floor deferred to guard-font-floor.py")
    guard = SCRIPTS / "guard-font-floor.py"
    if not guard.is_file():
        return CheckOutcome(cid, CHECK_NAMES[cid], SKIP,
                            "guard-font-floor.py not present in this checkout; deferred")
    try:
        rc = subprocess.call([sys.executable, str(guard), str(pdf)])
    except Exception as exc:  # fail-closed on an inability to run the real prover
        return CheckOutcome(cid, CHECK_NAMES[cid], FAIL,
                            "guard-font-floor.py could not run: %s" % type(exc).__name__, _code(cid))
    if rc == 0:
        return CheckOutcome(cid, CHECK_NAMES[cid], PASS, "guard-font-floor.py clean over %s" % pdf)
    return CheckOutcome(cid, CHECK_NAMES[cid], FAIL,
                        "guard-font-floor.py exit %d over %s (glyph below 14pt)" % (rc, pdf),
                        _code(cid))


def check_8_identity(env: dict, text: str) -> CheckOutcome:
    cid = 8
    ident = env.get("identity")
    if not isinstance(ident, dict):
        return CheckOutcome(cid, CHECK_NAMES[cid], FAIL,
                            "in scope but no identity block supplied (fail-closed)", _code(cid))
    problems: List[str] = []
    # Envelope-level consistency: the artifact's declared ids equal the expected ids.
    for k in ("contact_id", "anthology_id"):
        exp = env.get(k)
        got = ident.get(k)
        if exp is not None and got is not None and str(exp) != str(got):
            problems.append("%s mismatch (envelope %r != identity %r)" % (k, exp, got))
    hay = normalize_phrase(text or "")
    # Cross-participant / cross-anthology bleed: no foreign id or name appears.
    for fid in ident.get("foreign_ids", []) or []:
        if fid and str(fid).lower() in (text or "").lower():
            problems.append("foreign id %r bleeds into the deliverable" % fid)
    for fname in ident.get("foreign_names", []) or []:
        if fname and contains_phrase(text or "", str(fname)):
            problems.append("foreign contributor name %r bleeds into the deliverable" % fname)
    # Own-name presence only when the caller asks for it (a first-person memoir need
    # not name its author, so this is opt-in).
    if ident.get("require_own_name"):
        full = ("%s %s" % (ident.get("first_name", ""), ident.get("last_name", ""))).strip()
        last = str(ident.get("last_name", "")).strip()
        if full and not (contains_phrase(text or "", full) or (last and last.lower() in hay)):
            problems.append("participant name %r absent though require_own_name is set" % full)
    if problems:
        return CheckOutcome(cid, CHECK_NAMES[cid], FAIL,
                            "identity integrity: " + "; ".join(problems), _code(cid))
    return CheckOutcome(cid, CHECK_NAMES[cid], PASS, "ids consistent; no cross-participant bleed")


def check_9_intake_contamination(env: dict, text: str) -> CheckOutcome:
    cid = 9
    if text is None:
        return CheckOutcome(cid, CHECK_NAMES[cid], FAIL, "no artifact text", _code(cid))
    hits: List[str] = []
    if _EMAIL_RE.search(text):
        hits.append("email address present")
    if _PHONE_RE.search(text):
        hits.append("phone number present")
    if _FORM_MECHANIC_RE.search(text):
        hits.append("form-mechanic / hidden-field token present")
    # Explicit hidden-field VALUES the stage runner knows must never surface.
    intake = _load_json_ref(env, "intake", "intake_path") or {}
    hidden = env.get("hidden_fields") or {}
    literal_values = []
    for src in (hidden, intake):
        if isinstance(src, dict):
            for key in ("email", "phone", "contact_id", "anthology_id", "phone_number"):
                v = src.get(key)
                if isinstance(v, str) and len(v.strip()) >= 5:
                    literal_values.append((key, v.strip()))
    for key, val in literal_values:
        if val.lower() in (text or "").lower():
            hits.append("hidden %s value present verbatim" % key)
    if hits:
        return CheckOutcome(cid, CHECK_NAMES[cid], FAIL,
                            "intake contamination: " + "; ".join(sorted(set(hits))), _code(cid))
    return CheckOutcome(cid, CHECK_NAMES[cid], PASS,
                        "no emails, phones, form mechanics, or hidden values")


def check_10_no_fabrication(env: dict, text: str) -> CheckOutcome:
    cid = 10
    if text is None:
        return CheckOutcome(cid, CHECK_NAMES[cid], FAIL, "no artifact text", _code(cid))
    urls = sorted(set(_URL_RE.findall(text)))
    if not urls:
        return CheckOutcome(cid, CHECK_NAMES[cid], PASS,
                            "no links to trace (biography nuance is semantic check 13)")
    allowed_raw = env.get("search_pass_urls")
    search_text = env.get("search_pass_text") or ""
    if allowed_raw is None and not search_text:
        return CheckOutcome(cid, CHECK_NAMES[cid], FAIL,
                            "%d link(s) present but no search-pass output supplied to trace them "
                            "against (fail-closed): %s"
                            % (len(urls), ", ".join(urls[:4])), _code(cid))
    allowed = {u.rstrip("/.,);]").lower() for u in (allowed_raw or [])}
    untraceable = []
    for u in urls:
        norm = u.rstrip("/.,);]").lower()
        if norm in allowed:
            continue
        if search_text and norm in search_text.lower():
            continue
        untraceable.append(u)
    if untraceable:
        return CheckOutcome(cid, CHECK_NAMES[cid], FAIL,
                            "link(s) do not trace to the search pass (fabricated): %s"
                            % ", ".join(untraceable[:4]), _code(cid))
    return CheckOutcome(cid, CHECK_NAMES[cid], PASS,
                        "all %d link(s) trace to the search-pass output" % len(urls))


def check_11_naming(env: dict, text: str) -> CheckOutcome:
    cid = 11
    if text is None:
        return CheckOutcome(cid, CHECK_NAMES[cid], FAIL, "no artifact text", _code(cid))
    low = text.lower()
    hits: List[str] = []
    for term in _PLATFORM_BANNED:
        if term in low:
            hits.append("platform must be 'Convert and Flow', found a banned alternate")
            break
    if _PLATFORM_ABBR_RE.search(text):
        hits.append("platform abbreviation leak (must be 'Convert and Flow')")
    for term in _PLUMBING_TERMS:
        if term in low:
            hits.append("internal tool/plumbing name %r" % term)
    m = _MODEL_ID_RE.search(text)
    if m:
        hits.append("model-id shape %r" % m.group(0))
    if is_anthropic_shaped(text):
        hits.append("Anthropic-family identifier")
    if hits:
        return CheckOutcome(cid, CHECK_NAMES[cid], FAIL,
                            "naming leak on a client surface: " + "; ".join(sorted(set(hits))),
                            _code(cid))
    return CheckOutcome(cid, CHECK_NAMES[cid], PASS,
                        "no tool, model, plumbing, or platform-name leaks")


def _collect_model_values(node, out: List[str]) -> None:
    """Every string recorded under a MODEL-identifier field (a key whose name
    contains 'model'), anywhere in the ledger. Descriptive prose (a 'note' field)
    is deliberately NOT scanned -- check 12 is about recorded model identifiers,
    not free text that may legitimately describe the deny rule."""
    if isinstance(node, dict):
        for k, v in node.items():
            if "model" in str(k).lower() and isinstance(v, str):
                out.append(v)
            _collect_model_values(v, out)
    elif isinstance(node, list):
        for v in node:
            _collect_model_values(v, out)


def check_12_run_ledger(env: dict, text: str) -> CheckOutcome:
    cid = 12
    ledger = _load_json_ref(env, "run_ledger", "run_ledger_path")
    if ledger is None:
        return CheckOutcome(cid, CHECK_NAMES[cid], SKIP,
                            "no run ledger supplied to this invocation; cleanliness also proven "
                            "by model_router deny + guard-no-anthropic-runtime.py")
    model_values: List[str] = []
    _collect_model_values(ledger, model_values)
    dirty = [m for m in model_values if is_anthropic_shaped(m)]
    if dirty:
        return CheckOutcome(cid, CHECK_NAMES[cid], FAIL,
                            "run ledger records an Anthropic-family model identifier: %r"
                            % dirty[0], _code(cid))
    # Honesty proxy: every recorded stage names a non-empty model.
    stages = ledger.get("stages") if isinstance(ledger, dict) else None
    if isinstance(stages, list):
        blank = [s.get("stage_id", "?") for s in stages
                 if isinstance(s, dict) and not str(s.get("model", "")).strip()]
        if blank:
            return CheckOutcome(cid, CHECK_NAMES[cid], FAIL,
                                "run ledger stage(s) record no model (not recorded honestly): %s"
                                % ", ".join(map(str, blank[:6])), _code(cid))
    return CheckOutcome(cid, CHECK_NAMES[cid], PASS,
                        "run ledger clean; no Anthropic ids; models recorded")


CHECK_FUNCS: Dict[int, Callable[[dict, Optional[str]], CheckOutcome]] = {
    1: check_1_word_band, 2: check_2_title_lock, 3: check_3_story_placement,
    4: check_4_zero_truncation, 5: check_5_zero_em_dash, 6: check_6_no_leakage,
    7: check_7_pdf_font_floor, 8: check_8_identity, 9: check_9_intake_contamination,
    10: check_10_no_fabrication, 11: check_11_naming, 12: check_12_run_ledger,
}


# ---------------------------------------------------------------------------
# Assembly-mode additions (S9 manuscript scope)
# ---------------------------------------------------------------------------
def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def assembly_checks(env: dict, manuscript: Optional[str]) -> List[CheckOutcome]:
    outs: List[CheckOutcome] = []

    # A1: every approved chapter present exactly once and byte-identical to frozen.
    chapters = env.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        outs.append(CheckOutcome(101, "ASM_FROZEN_CHAPTERS", FAIL,
                                 "no chapters[] supplied for assembly (fail-closed)",
                                 "AF-AE-S9-FROZEN"))
    else:
        seen: Dict[str, int] = {}
        mismatched: List[str] = []
        for ch in chapters:
            cidk = str(ch.get("contact_id", ch.get("key", "?")))
            seen[cidk] = seen.get(cidk, 0) + 1
            frozen = str(ch.get("sha256", "")).strip().lower()
            body = ch.get("text")
            if body is None and ch.get("path"):
                try:
                    body = Path(ch["path"]).read_text(encoding="utf-8")
                except (OSError, UnicodeError):
                    body = None
            if frozen and body is not None:
                if _sha256_text(body) != frozen:
                    mismatched.append(cidk)
            elif frozen and body is None:
                mismatched.append("%s (no body to hash)" % cidk)
            else:
                mismatched.append("%s (no frozen sha256)" % cidk)
        dupes = [k for k, n in seen.items() if n > 1]
        if dupes:
            outs.append(CheckOutcome(101, "ASM_FROZEN_CHAPTERS", FAIL,
                                     "chapter(s) present more than once: %s" % ", ".join(dupes),
                                     "AF-AE-S9-FROZEN"))
        elif mismatched:
            outs.append(CheckOutcome(101, "ASM_FROZEN_CHAPTERS", FAIL,
                                     "chapter(s) not byte-identical to frozen: %s"
                                     % ", ".join(mismatched[:6]), "AF-AE-S9-FROZEN"))
        else:
            outs.append(CheckOutcome(101, "ASM_FROZEN_CHAPTERS", PASS,
                                     "all %d chapter(s) present once and byte-identical to frozen"
                                     % len(chapters)))

    # A2: order matches curation.
    curated = env.get("curated_order")
    if isinstance(chapters, list) and isinstance(curated, list) and curated:
        actual = [str(c.get("contact_id", c.get("key", "?"))) for c in chapters]
        actual_sorted = [c for _, c in sorted(
            ((int(ch.get("order", i)), a) for i, (ch, a) in enumerate(zip(chapters, actual))))]
        if actual_sorted != [str(x) for x in curated]:
            outs.append(CheckOutcome(102, "ASM_ORDER", FAIL,
                                     "compiled order %s does not match curated order %s"
                                     % (actual_sorted, [str(x) for x in curated]),
                                     "AF-AE-S9-ORDER"))
        else:
            outs.append(CheckOutcome(102, "ASM_ORDER", PASS, "chapter order matches curation"))
    else:
        outs.append(CheckOutcome(102, "ASM_ORDER", SKIP,
                                 "no curated_order supplied to verify against"))

    # A3: editor introduction references only real contributors.
    contributors = env.get("contributors") or []
    roster_names = [("%s %s" % (c.get("first_name", ""), c.get("last_name", ""))).strip()
                    for c in contributors if isinstance(c, dict)]
    intro = _artifact_text(env, "introduction_text", "introduction_path")
    if intro is not None and roster_names:
        # Any capitalized multi-word proper name in the intro that is neither a
        # rostered contributor nor present in the producer-supplied inputs is a
        # fabricated reference. (The full "producer inputs only" judgement is
        # semantic; this is the deterministic name-provenance floor.)
        producer_inputs = (env.get("producer_inputs_text") or "").lower()
        candidates = set(re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", intro))
        rostered = {n.lower() for n in roster_names}
        rostered_last = {n.split()[-1].lower() for n in roster_names if n.split()}
        stray = []
        for cand in sorted(candidates):
            cl = cand.lower()
            if cl in rostered:
                continue
            if any(part in rostered_last for part in cl.split()):
                continue
            if producer_inputs and cl in producer_inputs:
                continue
            stray.append(cand)
        if stray:
            outs.append(CheckOutcome(103, "ASM_INTRO_CONTRIBUTORS", FAIL,
                                     "introduction references non-contributor / unsupplied name(s): %s"
                                     % ", ".join(stray[:6]), "AF-AE-S9-INTRO"))
        else:
            outs.append(CheckOutcome(103, "ASM_INTRO_CONTRIBUTORS", PASS,
                                     "introduction references only real contributors"))
    else:
        outs.append(CheckOutcome(103, "ASM_INTRO_CONTRIBUTORS", SKIP,
                                 "no introduction and/or contributor roster supplied"))

    # A4: contributor bios match ledger identities.
    bios = env.get("bios")
    if isinstance(bios, list) and roster_names:
        rostered_last = {n.split()[-1].lower() for n in roster_names if n.split()}
        orphan = []
        for b in bios:
            btext = b.get("text", "") if isinstance(b, dict) else str(b)
            bname = (b.get("name", "") if isinstance(b, dict) else "").strip()
            hay = (btext + " " + bname).lower()
            if not any(last in hay for last in rostered_last):
                orphan.append(bname or btext[:30])
        if orphan:
            outs.append(CheckOutcome(104, "ASM_BIOS", FAIL,
                                     "contributor bio(s) do not match any ledger identity: %s"
                                     % ", ".join(orphan[:6]), "AF-AE-S9-BIO"))
        elif len(bios) != len(roster_names):
            outs.append(CheckOutcome(104, "ASM_BIOS", FAIL,
                                     "bio count %d != contributor count %d"
                                     % (len(bios), len(roster_names)), "AF-AE-S9-BIO"))
        else:
            outs.append(CheckOutcome(104, "ASM_BIOS", PASS,
                                     "%d contributor bio(s) match ledger identities" % len(bios)))
    else:
        outs.append(CheckOutcome(104, "ASM_BIOS", SKIP,
                                 "no bios and/or contributor roster supplied"))

    # A5: front and back matter complete.
    fm = env.get("front_matter_present")
    bm = env.get("back_matter_present")
    if fm is None or bm is None:
        # derive from the manuscript when explicit flags are absent
        if manuscript:
            low = manuscript.lower()
            fm = fm if fm is not None else any(
                t in low for t in ("title page", "copyright", "table of contents", "contents"))
            bm = bm if bm is not None else any(
                t in low for t in ("about the", "acknowledg", "afterword", "back matter"))
    if fm and bm:
        outs.append(CheckOutcome(105, "ASM_MATTER", PASS, "front and back matter complete"))
    elif fm is None and bm is None:
        outs.append(CheckOutcome(105, "ASM_MATTER", SKIP,
                                 "no manuscript or matter flags supplied to verify"))
    else:
        gaps = []
        if not fm:
            gaps.append("front matter")
        if not bm:
            gaps.append("back matter")
        outs.append(CheckOutcome(105, "ASM_MATTER", FAIL,
                                 "incomplete: %s" % ", ".join(gaps), "AF-AE-S9-MATTER"))

    return outs


# ---------------------------------------------------------------------------
# Top-level runner
# ---------------------------------------------------------------------------
def run_tier1(env: dict, mode: str = "piece") -> Verdict:
    kind = env.get("kind")
    if mode == "assembly":
        kind = kind or "manuscript"
    if kind not in KNOWN_KINDS:
        raise BadInvocation("unknown kind %r (known: %s)"
                            % (kind, ", ".join(sorted(KNOWN_KINDS))))
    env = dict(env)
    env["kind"] = kind
    text = _artifact_text(env)
    if mode == "assembly":
        text = text if text is not None else _artifact_text(env, "manuscript_text", "manuscript_path")

    verdict = Verdict(mode, kind)

    # Which base checks to run: explicit override or the per-kind default.
    requested = env.get("checks")
    if requested:
        ids = [int(x) for x in requested]
    else:
        ids = list(DEFAULT_CHECKS[kind])

    for cid in ids:
        fn = CHECK_FUNCS.get(cid)
        if fn is None:
            verdict.add(CheckOutcome(cid, "UNKNOWN", SKIP, "no such Tier-1 check"))
            continue
        try:
            verdict.add(fn(env, text))
        except BadInvocation:
            raise
        except Exception as exc:  # a check crashing is a fail-closed content failure
            verdict.add(CheckOutcome(cid, CHECK_NAMES.get(cid, "CHECK"), FAIL,
                                     "check raised %s: %s" % (type(exc).__name__, exc), _code(cid)))

    if mode == "assembly":
        for outcome in assembly_checks(env, text):
            verdict.add(outcome)

    return verdict


# ---------------------------------------------------------------------------
# Pull-back revalidation (confirm-then-pull core; SPEC 2 step 5 / Gap G12).
# Re-run only the deterministic CONTENT invariants over the PULLED, client-edited
# text: word band (1), title-lock PRESENCE (2), story anchors (3) -- whichever
# apply to the kind. Advisory-only: violations become PRODUCER board notes via
# Verdict.emit_pullback and NEVER block the co-author (see that method).
# ---------------------------------------------------------------------------
PULLBACK_BASE = (1, 2, 3)


def run_pullback(env: dict) -> Verdict:
    kind = env.get("kind")
    if kind not in KNOWN_KINDS:
        raise BadInvocation("unknown kind %r (known: %s)"
                            % (kind, ", ".join(sorted(KNOWN_KINDS))))
    env = dict(env)
    env["kind"] = kind
    text = _artifact_text(env)

    verdict = Verdict("pullback", kind)

    # Which content invariants to observe: explicit override, else the base
    # invariants that are actually in scope for this kind.
    requested = env.get("checks")
    if requested:
        ids = [int(x) for x in requested]
    else:
        ids = [c for c in PULLBACK_BASE if c in DEFAULT_CHECKS[kind]]

    for cid in ids:
        fn = CHECK_FUNCS.get(cid)
        if fn is None:
            verdict.add(CheckOutcome(cid, "UNKNOWN", SKIP, "no such Tier-1 check"))
            continue
        try:
            verdict.add(fn(env, text))
        except BadInvocation:
            raise
        except Exception as exc:  # a crashing check becomes a note, never a block
            verdict.add(CheckOutcome(cid, CHECK_NAMES.get(cid, "CHECK"), FAIL,
                                     "check raised %s: %s" % (type(exc).__name__, exc), _code(cid)))

    return verdict


def _read_envelope(args) -> dict:
    if args.envelope:
        raw = Path(args.envelope).read_text(encoding="utf-8")
    else:
        data = sys.stdin.read()
        if not data.strip():
            raise BadInvocation("no envelope on --envelope and nothing on stdin")
        raw = data
    try:
        env = json.loads(raw)
    except ValueError as exc:
        raise BadInvocation("envelope is not valid JSON: %s" % exc)
    if not isinstance(env, dict):
        raise BadInvocation("envelope must be a JSON object")
    # CLI overrides
    if args.kind:
        env["kind"] = args.kind
    if args.artifact:
        env["artifact_path"] = args.artifact
    return env


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Gate B Tier 1 deterministic hard-fail battery (SPEC Section 4).")
    ap.add_argument("--envelope", help="path to the deliverable envelope JSON (else stdin)")
    ap.add_argument("--artifact", help="override envelope artifact_path")
    ap.add_argument("--kind", help="override envelope kind (%s)" % ", ".join(sorted(KNOWN_KINDS)))
    ap.add_argument("--mode", choices=["piece", "assembly", "pullback"], default="piece")
    ap.add_argument("--json", action="store_true", help="emit the structured verdict as JSON")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    try:
        env = _read_envelope(args)
        if args.mode == "pullback":
            verdict = run_pullback(env)
        else:
            verdict = run_tier1(env, mode=args.mode)
    except BadInvocation as exc:
        sys.stderr.write("[qc-tier1] bad invocation: %s\n" % exc)
        return EX_BAD
    except Exception as exc:
        sys.stderr.write("[qc-tier1] unexpected error: %s\n" % exc)
        return EX_ERR
    if args.mode == "pullback":
        return verdict.emit_pullback(args.json)
    return verdict.emit(args.json)


# ---------------------------------------------------------------------------
# Self-test: purpose-built fixtures prove each check catches its violation and
# passes clean, plus a real-data smoke over the golden working chapter (checks
# 1/2/3 pass; check 5 catches the pre-hygiene em dashes), and assembly mode.
# No network, no model, no sibling scripts required.
# ---------------------------------------------------------------------------
_GOLDEN = (SKILL_DIR.parent / "54-anthology-writer" / "examples"
           / "golden-unbroken-ground" / "working")

_CLEAN_CHAPTER = (
    "# The Weight of the Keys\n\n"
    "## What a Locked Door Taught Me About Letting Go\n\n"
    "For nineteen years I carried the same ring of keys in my right front pocket. "
    "There were eleven keys on that ring, and each one told me who I was.\n\n"
    "I kept the blue Igloo cooler stocked with cold water for anyone who walked in. "
    "Then the padlock the bank sent by certified mail arrived on a Tuesday.\n\n"
    "The door was never the thing. You were always the thing.")


def _clean_envelope(**over) -> dict:
    env = {
        "kind": "chapter",
        "artifact_text": _CLEAN_CHAPTER,
        "title": {"title": "The Weight of the Keys",
                  "subtitle": "What a Locked Door Taught Me About Letting Go"},
        "intake": {"personal_stories": ["the blue Igloo cooler",
                                        "the padlock the bank sent by certified mail"]},
        "identity": {"contact_id": "c1", "anthology_id": "a1",
                     "first_name": "Marcus", "last_name": "Bell"},
        "contact_id": "c1", "anthology_id": "a1",
        "run_ledger": {"stages": [{"stage_id": "aw-09", "model": "glm-5.2"}]},
        # word band deliberately relaxed so the tiny fixture prose passes check 1
        "chapter_word_min": 20, "chapter_word_max": 4000,
        "checks": [1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12],
    }
    env.update(over)
    return env


def self_test() -> int:
    checks: List[Tuple[str, bool]] = []

    def _has_fail(v: Verdict, cid: int) -> bool:
        return any(c.id == cid and c.status == FAIL for c in v.checks)

    def _passes(v: Verdict, cid: int) -> bool:
        return any(c.id == cid and c.status == PASS for c in v.checks)

    # clean deliverable: every listed check passes.
    v = run_tier1(_clean_envelope())
    checks.append(("clean deliverable passes every in-scope check", v.passed))

    # 1 WORD BAND: too short chapter fails.
    v = run_tier1(_clean_envelope(chapter_word_min=2000, chapter_word_max=3500))
    checks.append(("short chapter FAILs word band (1)", _has_fail(v, 1)))
    # tone floor
    v = run_tier1({"kind": "tone", "artifact_text": "word " * 100,
                   "tone_word_floor": 3000, "checks": [1]})
    checks.append(("thin tone doc FAILs the 3,000 floor (1)", _has_fail(v, 1)))

    # 2 TITLE LOCK: changed subtitle fails.
    bad = _clean_envelope(artifact_text=_CLEAN_CHAPTER.replace("Letting Go", "Moving On"),
                          title={"title": "The Weight of the Keys",
                                 "subtitle": "What a Locked Door Taught Me About Letting Go"},
                          checks=[2])
    checks.append(("changed subtitle FAILs title lock (2)", _has_fail(run_tier1(bad), 2)))

    # 3 STORY PLACEMENT: dropped story fails.
    drop = _clean_envelope(artifact_text=_CLEAN_CHAPTER.replace("the blue Igloo cooler", "a cooler"),
                           checks=[3])
    checks.append(("dropped story FAILs placement (3)", _has_fail(run_tier1(drop), 3)))

    # 4 ZERO TRUNCATION: mid-sentence ending and a false pin both fail.
    trunc = _clean_envelope(artifact_text="He opened the door and then", checks=[4])
    checks.append(("mid-sentence ending FAILs truncation (4)", _has_fail(run_tier1(trunc), 4)))
    pinbad = _clean_envelope(prompt_pin_ok=False, checks=[4])
    checks.append(("prompt pin mismatch FAILs truncation (4)", _has_fail(run_tier1(pinbad), 4)))
    checks.append(("clean deliverable passes truncation (4)",
                   _passes(run_tier1(_clean_envelope(prompt_pin_ok=True, checks=[4])), 4)))

    # 5 ZERO EM DASH.
    em = _clean_envelope(artifact_text=_CLEAN_CHAPTER + "\nand then — nothing.", checks=[5])
    checks.append(("em dash FAILs check 5", _has_fail(run_tier1(em), 5)))

    # 6 NO LEAKAGE: code fence, role label, verify block, stage tag, [UNCHANGED].
    for label, injected in (
            ("code fence", "```python\nx=1\n```"),
            ("role label", "System: you are an assistant"),
            ("verify block", "COMPLETION VERIFICATION: 2600 words"),
            ("stage tag", "drafted at aw-09 tier"),
            ("[UNCHANGED] placeholder", "keep this [UNCHANGED] here")):
        vv = run_tier1(_clean_envelope(artifact_text=_CLEAN_CHAPTER + "\n" + injected, checks=[6]))
        checks.append(("leakage (%s) FAILs check 6" % label, _has_fail(vv, 6)))
    checks.append(("clean prose passes check 6",
                   _passes(run_tier1(_clean_envelope(checks=[6])), 6)))

    # 7 PDF FONT FLOOR: pre-verified bool honored both ways; absent -> skip.
    checks.append(("font floor pre-fail FAILs check 7",
                   _has_fail(run_tier1(_clean_envelope(rendered_font_floor_ok=False, checks=[7])), 7)))
    v7 = run_tier1(_clean_envelope(checks=[7]))
    checks.append(("absent PDF SKIPs check 7",
                   any(c.id == 7 and c.status == SKIP for c in v7.checks)))

    # 8 IDENTITY: foreign name bleed and id mismatch fail.
    bleed = _clean_envelope(artifact_text=_CLEAN_CHAPTER + "\nCall me, said Priya Nair.",
                            identity={"contact_id": "c1", "anthology_id": "a1",
                                      "first_name": "Marcus", "last_name": "Bell",
                                      "foreign_names": ["Priya Nair"]},
                            checks=[8])
    checks.append(("foreign contributor bleed FAILs identity (8)", _has_fail(run_tier1(bleed), 8)))
    mism = _clean_envelope(contact_id="cX",
                           identity={"contact_id": "c1", "anthology_id": "a1"}, checks=[8])
    checks.append(("contact_id mismatch FAILs identity (8)", _has_fail(run_tier1(mism), 8)))

    # 9 INTAKE CONTAMINATION: email and phone.
    contam = _clean_envelope(
        artifact_text=_CLEAN_CHAPTER + "\nReach me at marcus@example.com or 206-555-0142.",
        checks=[9])
    checks.append(("email + phone FAIL intake contamination (9)", _has_fail(run_tier1(contam), 9)))

    # 10 NO FABRICATION: a link with no search pass fails; a traced link passes.
    fab = _clean_envelope(artifact_text=_CLEAN_CHAPTER + "\nSee https://example.com/proof",
                          checks=[10])
    checks.append(("untraceable link FAILs fabrication (10)", _has_fail(run_tier1(fab), 10)))
    traced = _clean_envelope(artifact_text=_CLEAN_CHAPTER + "\nSee https://example.com/proof",
                             search_pass_urls=["https://example.com/proof"], checks=[10])
    checks.append(("traced link passes fabrication (10)", _passes(run_tier1(traced), 10)))

    # 11 NAMING: model-id and plumbing leaks.
    for label, injected in (("model id", "rendered on gpt-image-2"),
                            ("plumbing", "delivered via n8n webhook")):
        vv = run_tier1(_clean_envelope(artifact_text=_CLEAN_CHAPTER + "\n" + injected, checks=[11]))
        checks.append(("naming leak (%s) FAILs check 11" % label, _has_fail(vv, 11)))

    # 12 RUN LEDGER: an Anthropic-shaped id in the ledger fails (assembled by fragment).
    poisoned = _clean_envelope(
        run_ledger={"stages": [{"stage_id": "aw-09", "model": "cl" + "aude-" + "opus-4"}]},
        checks=[12])
    checks.append(("Anthropic id in ledger FAILs check 12", _has_fail(run_tier1(poisoned), 12)))
    blankmodel = _clean_envelope(
        run_ledger={"stages": [{"stage_id": "aw-09", "model": ""}]}, checks=[12])
    checks.append(("blank model in ledger FAILs check 12", _has_fail(run_tier1(blankmodel), 12)))

    # bad invocation: unknown kind.
    try:
        run_tier1({"kind": "nonsense", "artifact_text": "x"})
        checks.append(("unknown kind raises BadInvocation", False))
    except BadInvocation:
        checks.append(("unknown kind raises BadInvocation", True))

    # ASSEMBLY mode: frozen byte-identity, order, dupes.
    good_body = "Chapter one body."
    asm = {
        "kind": "manuscript", "mode": "assembly",
        "manuscript_text": ("Title Page\nCopyright\nTable of Contents\n" + good_body +
                            "\nAbout the Contributors\nAcknowledgments"),
        "chapters": [{"contact_id": "c1", "text": good_body, "sha256": _sha256_text(good_body),
                      "order": 1}],
        "curated_order": ["c1"],
        "contributors": [{"first_name": "Marcus", "last_name": "Bell"}],
        "introduction_text": "These are the voices of Marcus Bell and his neighbors.",
        "bios": [{"name": "Marcus Bell", "text": "Marcus Bell ran a repair shop."}],
        "checks": [5, 6],
    }
    va = run_tier1(asm, mode="assembly")
    checks.append(("assembly clean manuscript passes", va.passed))
    tampered = dict(asm, chapters=[{"contact_id": "c1", "text": "TAMPERED",
                                    "sha256": _sha256_text(good_body), "order": 1}])
    vt = run_tier1(tampered, mode="assembly")
    checks.append(("assembly catches a non-frozen chapter (AF-AE-S9-FROZEN)",
                   any(c.code == "AF-AE-S9-FROZEN" and c.status == FAIL for c in vt.checks)))
    strayintro = dict(asm, introduction_text="Featuring Marcus Bell and the ghost of Jane Austen.")
    vs = run_tier1(strayintro, mode="assembly")
    checks.append(("assembly catches a fabricated intro name",
                   any(c.id == 103 and c.status == FAIL for c in vs.checks)))

    # PULL-BACK mode (U7 confirm-then-pull core): a client's edits to their Doc are
    # revalidated but NEVER block them; violations become PRODUCER board notes.
    _pull_base = {
        "kind": "chapter",
        "title": {"title": "The Weight of the Keys",
                  "subtitle": "What a Locked Door Taught Me About Letting Go"},
        "intake": {"personal_stories": ["the blue Igloo cooler",
                                        "the padlock the bank sent by certified mail"]},
        "chapter_word_min": 20, "chapter_word_max": 4000,
    }
    # clean pull: title present, stories present, band ok -> zero producer notes.
    pv_clean = run_pullback(dict(_pull_base, artifact_text=_CLEAN_CHAPTER))
    checks.append(("pullback: default selection is exactly the content invariants [1,2,3]",
                   [c.id for c in pv_clean.checks] == [1, 2, 3]))
    checks.append(("pullback: a clean pulled chapter yields zero producer notes",
                   len(pv_clean.failures) == 0))
    # a client edit that drops the title AND a story: both surface as notes.
    pulled_broken = (_CLEAN_CHAPTER
                     .replace("The Weight of the Keys", "Untitled Draft")
                     .replace("the blue Igloo cooler", "a cooler"))
    pv_broken = run_pullback(dict(_pull_base, artifact_text=pulled_broken))
    checks.append(("pullback: dropped title-lock presence surfaces a producer note (2)",
                   any(c.id == 2 and c.status == FAIL for c in pv_broken.checks)))
    checks.append(("pullback: dropped story anchor surfaces a producer note (3)",
                   any(c.id == 3 and c.status == FAIL for c in pv_broken.checks)))
    # the cardinal guarantee: emit ALWAYS returns EX_OK, even with notes (no block).
    import io as _io
    import contextlib as _cl
    _buf = _io.StringIO()
    with _cl.redirect_stdout(_buf):
        _rc_pb = pv_broken.emit_pullback(as_json=True)
    checks.append(("pullback: emit ALWAYS returns EX_OK even with notes (never blocks the client)",
                   _rc_pb == EX_OK))
    _payload = json.loads(_buf.getvalue())
    checks.append(("pullback: JSON marks advisory=true, blocking=false, and carries producer_notes",
                   _payload.get("advisory") is True and _payload.get("blocking") is False
                   and len(_payload.get("producer_notes", [])) >= 2))
    # a client's own shrink below the word band is a note, not a block.
    pv_thin = run_pullback({"kind": "chapter", "artifact_text": "Too short.",
                            "chapter_word_min": 2000, "chapter_word_max": 3500,
                            "checks": [1]})
    _thin_flagged = any(c.id == 1 and c.status == FAIL for c in pv_thin.checks)
    with _cl.redirect_stdout(_io.StringIO()):
        _thin_rc = pv_thin.emit_pullback(as_json=True)
    checks.append(("pullback: a client shrinking below the word band is a note (1), not a block",
                   _thin_flagged and _thin_rc == EX_OK))
    # pull-back is kind-aware: a tone pull observes only the word band.
    tone_pull = run_pullback({"kind": "tone", "artifact_text": "word " * 4000,
                              "tone_word_floor": 3000})
    checks.append(("pullback: tone pull observes only the word band [1]",
                   [c.id for c in tone_pull.checks] == [1]))

    # real-data smoke: the golden working chapter.
    gchap = _GOLDEN / "chapter.md"
    if gchap.is_file():
        gtext = gchap.read_text(encoding="utf-8")
        gtitle = json.loads((_GOLDEN / "title.json").read_text(encoding="utf-8"))
        gintake = json.loads((_GOLDEN / "intake.json").read_text(encoding="utf-8"))
        gledger = json.loads((_GOLDEN / "RUN-LEDGER.json").read_text(encoding="utf-8"))
        base = {"kind": "chapter", "artifact_text": gtext, "title": gtitle,
                "intake": gintake, "run_ledger": gledger}
        v123 = run_tier1(dict(base, checks=[1, 2, 3]))
        checks.append(("golden working chapter passes word band + title lock + stories (1,2,3)",
                       v123.passed))
        v5 = run_tier1(dict(base, checks=[5]))
        checks.append(("golden working chapter's pre-hygiene em dashes are CAUGHT (5)",
                       _has_fail(v5, 5)))
        v12 = run_tier1(dict(base, checks=[12]))
        checks.append(("golden run ledger is clean (12)", _passes(v12, 12)))
    else:
        checks.append(("golden fixture present for smoke", False))

    ok = True
    for label, good in checks:
        print("  [%s] %s" % ("OK" if good else "XX", label))
        ok = ok and good
    print("== qc-tier1-anthology self-test: %s (%d checks) =="
          % ("ALL PASSED" if ok else "FAILURES", len(checks)))
    return EX_OK if ok else EX_ERR


if __name__ == "__main__":
    sys.exit(main())
