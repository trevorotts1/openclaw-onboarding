#!/usr/bin/env python3
"""
qc-interview-completion.py — PRD-2.15 + PRD-2.16: Interview Completion QC Gate.

Checks that a completed interview transcript meets quality standards before
the build pipeline is allowed to proceed. Five checks:

  1. Question count: 25-35 answered questions in the transcript.
     LEGACY/PRE-STANDARD EXEMPTION (v12.4.0): a genuine, owner-authored interview
     that PREDATES the 25-35 question standard is accepted as complete WITHOUT
     meeting the count floor — but ONLY when (a) it is explicitly flagged as a
     verified pre-standard/legacy interview AND (b) it passes an anti-fabrication
     substance floor (real questions + real owner-authored answers). NEW interviews
     (no legacy flag) still MUST meet 25-35. See is_legacy_interview() and
     legacy_substance_ok() below. The exemption lifts ONLY the count floor; jargon,
     mandatory fields, and no-fabrication (checks 2/3/5) still apply in full.
     STRUCTURED-WEB COVERAGE STANDARD (2026-07-30 fix, 4th defect of this shape in
     this file, follow-on to the transcript-path/PR#772, mandatory-fields/PR#775,
     and nudge-cadence/PR#777 fixes): the 25-35 RAW BLOCK COUNT is the wrong proxy
     for an interview conducted through the Command Center's STRUCTURED WEB DECK —
     that deck's entire canonical question set is only ~11 questions (2 identity +
     up to 8 branding + 1 operations), so a client who substantively answers EVERY
     one of them can never reach 25 raw blocks without the interviewer drilling an
     already-answered question again for zero new coverage. Verified on a real
     client transcript (rescue-cassandra-henriquez): 11/11 canonical questions
     matched, every required branding field answered with 534-921 real characters,
     yet only 18-19 raw blocks — HARD-FAILED as "too shallow" on an interview that
     was, by every other measure, complete. For an interview identified as
     structured-web (see is_structured_web_interview()), check #1 becomes coverage
     + substance of the canonical set (see check_structured_coverage()) instead of
     raw count. The conversational path's 25-35 standard (and its legacy/tailored
     exemptions above) is completely UNCHANGED — this is an ADDITIONAL path,
     selected by a real, already-existing signal, never a replacement.
     EDIT-MODE EXEMPTION (standard-first redesign, PHASE 7): under
     buildType == "standard-first" the canonical department floor is ALREADY
     prebuilt before the interview begins (prebuild-standard-workforce.sh), so
     the interview EDITS the built set (walk the prebuilt departments: KEEP /
     TUNE / REMOVE) instead of pitching a missing set. A substantive edit-mode
     review can legitimately complete well under 25 questions, so check #1
     gains an edit-mode exemption: it applies when the build-state records a
     standard-first edit-mode interview (see is_edit_mode_interview()) AND the
     transcript passes the anti-fabrication substance floor (see
     edit_mode_substance_ok()). The exemption lifts ONLY the 25-35 count
     floor — the >36 ceiling, jargon, mandatory-field, and no-fabrication
     checks still apply in full, and the flag can never launder an empty or
     faked transcript (same shape as the legacy exemption). It never applies
     to a legacy box (absent buildType): those keep the 25-35 bar.
  2. Zero forbidden-jargon hits in AI-authored text (loads from forbidden-jargon.json).
  3. Every mandatory data field populated (branding required:true + structural fields).
     (2026-07-30 fix, client Mac mini box / its rescue agent incident): a
     branding field is populated when EITHER build-state records it OR the transcript
     has a matching answered Q/A block — see check_mandatory_fields() /
     compute_answered_ids() below. Previously this check consulted build-state ONLY,
     which the normal interview flow never populates for free-text branding answers
     (those are logged solely to the transcript), so it reported these five fields
     "missing" for every client, always: brand_evokes, customer_feeling,
     brand_descriptors, ideal_customer, unique_differentiator.
  4. Nudge cadence wired: interview-nudge-cron.sh exists + ensure-pipeline-crons.sh
     (the shared registrar BOTH install.sh and update-skills.sh call) wires it.
     (2026-07-30 fix, hot-patched-box false-failure): a SOFT/advisory finding, not
     a hard block — see build_verdict() below and check_nudges_wired() docstring.
  5. NO-FABRICATION (v12.3.4): if interview-context-map.json exists, every answer whose
     text is a verbatim copy of a context snippet WITHOUT a 'confirmed-from-context:'
     provenance note is flagged as HARD FAIL (exit 3, reason 'unconfirmed-context-as-answer').
     Answers that DO carry the provenance note PASS check #5.

TRANSCRIPT ENCRYPTION (U048, 2026-07-30 fix): the Command Center encrypts the
transcript at rest (workforce-interview-answers.md.enc, chacha20-poly1305 — see
blackceo-command-center src/lib/interview/crypto.ts). This gate resolves and
decrypts it IN-MEMORY via the shared _interview_transcript.py reader (never
writes plaintext to disk, never logs its content) so a genuinely-complete
encrypted interview is scored exactly as a plaintext one would be. If the
transcript is genuinely absent, or present but undecryptable (no key material /
tampered envelope), the gate still fails closed — see
resolve_and_load_transcript(). This is the SAME shared reader
build-workforce.py's _genuine_interview_answers_file() and
verify_interview_complete() use, so the QC gate and the builder's own
corroboration gate can never disagree about whether a transcript exists.

EXIT CODES (mirror qc-completeness.sh):
  0 — PASS (all five checks pass)
  1 — Error (bad input, unreadable state, missing required file)
  2 — SOFT FAIL / needs human review (borderline count: 24 or 36)
  3 — HARD FAIL (jargon hit, missing mandatory field, count way off,
                 or unconfirmed-context-as-answer)

Nudge cadence wiring (check 4) is reported (nudgesWired / nudgeIssues) but is a
WARNING, not a HARD FAIL (2026-07-30): it is box/infrastructure plumbing for a
DIFFERENT, already-past lifecycle stage (nudging an owner who has not yet
finished) — unlike checks 1/2/3/5/6/7, it says nothing about whether THIS
transcript or these decisions are legitimate/complete. Blocking a client's
already-complete, substantively-valid interview over an operator-facing cron
gap is the wrong trade — see check_nudges_wired() and build_verdict() below.

LEGACY/PRE-STANDARD INTERVIEW EXEMPTION (v12.4.0)
  Why: real, owner-authored interviews that were conducted BEFORE the 25-35 question
  standard existed (e.g. a genuine 20-question owner intake) are valid and must NOT be
  blocked from closeout — "don't re-interview real clients". This exemption lets a
  VERIFIED pre-standard interview pass check #1 without re-interviewing, while keeping
  the full count bar for NEW interviews.

  How an interview is detected as legacy/pre-standard (any ONE is sufficient):
    (a) Operator flag:  --legacy-interview on the command line.
    (b) State flag:     state.legacyInterview.preStandard == true
                        (with optional ownerConfirmed / confirmedBy / confirmedAt /
                        standardVersion / reason for the audit trail).
    (c) Transcript marker: a fenced marker line in the transcript, case-insensitive:
                        <!-- LEGACY-INTERVIEW: pre-standard ... -->
                        or a line containing  "legacy-interview: pre-standard".

  Anti-fabrication guard (NO exemption for empty/faked interviews):
    Even when flagged, the exemption ONLY applies if the interview shows real substance:
      - at least LEGACY_MIN_QUESTIONS real questions, AND
      - at least LEGACY_MIN_ANSWERED_QUESTIONS questions that carry a non-trivial,
        owner-authored answer (a real answer line, not just the Q-line).
    An empty or near-empty transcript that merely carries the legacy flag is treated
    as a HARD FAIL (reason 'legacy-flag-without-substance') — the flag cannot launder
    a fabricated/empty interview past the gate.

EDIT-MODE INTERVIEW EXEMPTION (standard-first redesign, PHASE 7)
  Why: under buildType == "standard-first" the 29-department canonical floor is
  ALREADY prebuilt before the interview begins, so the interview becomes an
  EDIT pass over the built set (per department: KEEP / TUNE / REMOVE) instead
  of a from-scratch intake. A substantive review of the prebuilt set can
  legitimately complete well under 25 questions. The exemption (see
  is_edit_mode_interview() + edit_mode_substance_ok()) mirrors the legacy one:
  it lifts ONLY the 25-35 count floor, never the >36 ceiling, and never the
  jargon / mandatory-field / no-fabrication checks. An edit-mode CLAIM without
  real owner substance is a HARD FAIL ('edit-mode-flag-without-substance') —
  the flag cannot launder a fabricated interview. It never applies to a legacy
  box (buildType absent).

TRANSCRIPT FORMAT ASSUMPTIONS:
  The transcript (workforce-interview-answers.md) is written per SKILL.md protocol
  with blocks like:
      **Q** <question text>
      <client answer>
  AI-authored lines are the Q-lines and any prose the agent sends (lines NOT in
  client-answer blocks). Client answer lines follow the Q-line until the next Q-block.
  If format is ambiguous, the scanner is CONSERVATIVE: AI-authored prose lines that
  begin with "**Q**", "**A:**", or "Q-" markers are scanned; lines that immediately
  follow an answer-marker are treated as client text and exempted from the jargon scan.
  False-negatives (client says 'agent') are acceptable; false-positives on client
  words are NOT. See implementation in _is_ai_authored() below.

NO-FABRICATION: this script reads and reports; it never writes answers.

PRD-2.15 + PRD-2.16 / v13.2.0 (unified short-interview exemption:
legacy/pre-standard + tailored/founder-self-build)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── SHARED DECLINE READER (Issue #2/#3 / Bulletproofing a) ───────────────────
# This gate mirrors the enforcer's REJECT branches; importing the ONE shared
# reader guarantees it and build-workforce.py / department-floor.py can never
# drift. Add this script's dir to sys.path so the import resolves under importlib
# too. Falls back gracefully if the module is unavailable (defensive).
_QC_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _QC_SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _QC_SCRIPTS_DIR)
try:
    from canonical_decline import decline_rejections as _shared_decline_rejections
except Exception:  # noqa: BLE001
    _shared_decline_rejections = None

# ── SHARED TRANSCRIPT READER (2026-07-30, U048 encrypted-transcript fix) ────
# The Command Center encrypts the transcript at rest (workforce-interview-
# answers.md.enc, chacha20-poly1305). This is the ONE shared reader — also
# used by build-workforce.py's _genuine_interview_answers_file() /
# verify_interview_complete() — so path-resolution + in-memory decrypt logic
# can never drift between the QC gate and the builder's own corroboration
# gate. Imported defensively: if unavailable, falls back to the ORIGINAL
# plaintext-only behavior (see load_transcript()) rather than crashing.
try:
    import _interview_transcript as _transcript_reader
except Exception:  # noqa: BLE001
    _transcript_reader = None

# ── WG-10c: no-web-only-store assertion (Check #7) ───────────────────────────
# The Command Center / dashboard DB is ONLY a downstream mirror of the canonical
# files. This sibling check proves the store never holds a department decision or an
# interview answer the files do not (and never contradicts a decision value the files
# own). Imported defensively so the rest of the gate still runs if it is unavailable.
try:
    from _qc_no_web_store import check_no_web_store as _check_no_web_store
except Exception:  # noqa: BLE001
    _check_no_web_store = None

# ── Path resolution (no tildes; mirrors detect_platform.py pattern) ──────────
def _resolve_openclaw_root() -> Path:
    """Resolve OpenClaw root: VPS=/data/.openclaw, Mac=$HOME/.openclaw."""
    vps = Path("/data/.openclaw")
    if vps.is_dir():
        return vps
    mac = Path(os.environ.get("HOME", "~")).expanduser() / ".openclaw"
    if mac.is_dir():
        return mac
    # Fallback: create path even if not yet present (for testing with --state flag)
    return mac


def _default_state_path() -> Path:
    return _resolve_openclaw_root() / "workspace" / ".workforce-build-state.json"


def _default_transcript_path() -> Path:
    root = _resolve_openclaw_root()
    return root / "workspace" / "workforce-interview-answers.md"


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_json(path: Path, label: str) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"[ERROR] {label} not found: {path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"[ERROR] {label} is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(1)


def load_transcript(path: Path) -> str:
    """
    ORIGINAL plaintext-only reader. Kept as the fallback path when
    _interview_transcript is unavailable (defensive import failure) so the
    gate degrades to its pre-encryption behavior instead of crashing.
    """
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"[ERROR] Transcript not found: {path}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"[ERROR] Cannot read transcript: {exc}", file=sys.stderr)
        sys.exit(1)


def resolve_and_load_transcript(explicit_path, state: dict, root: Path) -> str:
    """
    Resolve the transcript — plaintext OR encrypted (U048) — and return its
    decrypted/plain content as a string. Exits (fail-closed) with a
    diagnostic message on any failure; never returns None.

    Probe order (via _interview_transcript.candidate_bases, shared with
    build-workforce.py so the two gates can never disagree about WHERE the
    transcript lives):
      1. --transcript, if the operator passed one explicitly (tried as
         plaintext, then its .enc sibling — or decrypted directly if the
         operator passed a .enc path).
      2. state.interviewProgress.answersFilePath, if recorded.
      3. <root>/workspace/company-discovery/workforce-interview-answers.md(.enc)
      4. /data/.openclaw/workspace/company-discovery/workforce-interview-answers.md(.enc)
      5. $HOME/.openclaw/workspace/company-discovery/workforce-interview-answers.md(.enc)
      6. <root>/workspace/workforce-interview-answers.md(.enc)  — the ORIGINAL
         flat default this script used before this fix, kept so nothing that
         worked before regresses.

    NEVER writes plaintext to disk. NEVER logs transcript content — only
    paths, byte counts, and pass/fail status are ever printed.
    """
    if _transcript_reader is None:
        # Defensive fallback: module failed to import for some reason. Degrade
        # to the ORIGINAL plaintext-only behavior rather than hard-failing on
        # a dependency problem unrelated to the interview itself.
        path = Path(explicit_path) if explicit_path else _default_transcript_path()
        print(
            "[WARN] _interview_transcript module unavailable — falling back to "
            "plaintext-only transcript resolution (encrypted transcripts will "
            "NOT be found in this mode).",
            file=sys.stderr,
        )
        return load_transcript(path)

    if explicit_path:
        candidates = [str(Path(explicit_path))]
    else:
        recorded = (state.get("interviewProgress") or {}).get("answersFilePath")
        candidates = _transcript_reader.candidate_bases(
            recorded_path=recorded,
            company_discovery_dir=str(root / "workspace" / "company-discovery"),
        )
        # Original flat default (pre-company-discovery convention) as a final
        # fallback candidate, so an older install that only ever used it keeps
        # working exactly as it did before this fix.
        flat_default = str(_default_transcript_path())
        if flat_default not in candidates:
            candidates.append(flat_default)

    result = _transcript_reader.read_transcript(candidates)
    if not result.ok:
        print(
            f"[ERROR] Transcript not found or unreadable. Tried {len(result.tried)} "
            f"location(s):\n{_transcript_reader.format_tried(result.tried)}",
            file=sys.stderr,
        )
        print(f"[ERROR] {result.reason}", file=sys.stderr)
        sys.exit(1)

    if result.encrypted:
        print(
            f"[INFO] Transcript decrypted in-memory from {result.source_path} "
            f"({len(result.content)} chars). Plaintext was never written to disk.",
            file=sys.stderr,
        )
    return result.content


# ── G1-FAB-ENFORCE: owner-consent provenance (mirrors build-workforce.py) ───────
# Header that build_from_config() stamps onto a synthetically-built (non-interactive)
# transcript. A transcript bearing this header was assembled FROM CONFIG, not from
# live client turns — it is a fabricated transcript UNLESS an explicit owner consent
# record (self-setup / fast opt-in) is present in build-state.
NON_INTERACTIVE_ANSWERS_HEADER = "# Workforce Interview Answers (Non-Interactive)"

# Decision tokens that count as an EXPLICIT owner opt-in to a self-setup / fast build.
_CONSENT_OPT_IN_DECISIONS = frozenset({
    "self-setup", "self_setup", "selfsetup",
    "fast", "fast-mode", "fast_mode", "fastmode",
    "decline-interview", "decline_interview", "skip-interview", "skip_interview",
    "opt-in", "opt_in", "optin",
})


def _validate_owner_consent(state: dict | None) -> tuple:
    """
    Validate a session-bound ownerConsent record using the SAME provenance rule as
    the build-workforce.py decline/consent validators: every required field must be
    present and truthy, and the decision must be an explicit self-setup/fast opt-in.

    Required: decision, source, decidedAt, decidedBy, sessionId (read from
    state["ownerConsent"]). Returns (ok: bool, reason: str, consent: dict|None).
    Never raises.
    """
    required = ("decision", "source", "decidedAt", "decidedBy", "sessionId")
    consent = (state or {}).get("ownerConsent")
    if not isinstance(consent, dict):
        return (False,
                "no ownerConsent record in build-state "
                "(need {decision,source,decidedAt,decidedBy,sessionId})",
                None)
    missing = [k for k in required if not consent.get(k)]
    if missing:
        return (False, f"ownerConsent missing/empty fields: {', '.join(missing)}", consent)
    decision = str(consent.get("decision", "")).strip().lower()
    if decision not in _CONSENT_OPT_IN_DECISIONS:
        return (False,
                f"ownerConsent.decision='{decision}' is not an explicit self-setup/fast opt-in",
                consent)
    return (True, "ok", consent)


# ── Check 1: Question count ───────────────────────────────────────────────────

def count_questions(transcript: str, state: dict) -> dict:
    """
    Count answered questions from the transcript.
    Primary: count Q-blocks in the transcript.
    Cross-check against interviewProgress.lastQuestionNumber from state.
    """
    # Count Q-blocks: lines starting with **Q** or Q- or a numbered Q pattern
    q_patterns = [
        r"^\*\*Q\*\*",            # **Q** <text>
        r"^\*\*Q-\w+",            # **Q-D5** <text>
        r"^Q-\w+[:.]",            # Q-D5: <text>
        r"^#+\s*Question\s+\d+",  # ## Question 12
        r"^\d+\.\s+\*\*Q",       # 12. **Q<something>
    ]
    combined = "|".join(q_patterns)
    transcript_count = sum(
        1 for line in transcript.splitlines()
        if re.match(combined, line.strip(), re.IGNORECASE)
    )

    # Also count lines that are the AI's numbered questions in a simpler format
    # e.g. "**Question 14:**" or just "**Q14:**"
    transcript_count += sum(
        1 for line in transcript.splitlines()
        if re.match(r"^\*\*Q(?:uestion)?\s*\d+", line.strip(), re.IGNORECASE)
    ) if transcript_count < 5 else 0

    # If we found too few with strict patterns, fall back to counting answer separators
    if transcript_count < 10:
        # Count answer sections (--- separator between Q-A blocks)
        sep_count = len(re.findall(r"^---+\s*$", transcript, re.MULTILINE))
        if sep_count > transcript_count:
            transcript_count = sep_count

    # State cross-check
    state_qnum = (
        (state.get("interviewProgress") or {}).get("lastQuestionNumber")
        or state.get("lastQuestionNumber")  # legacy fallback
    )

    disagree_warning = None
    if state_qnum is not None and abs(transcript_count - state_qnum) > 3:
        disagree_warning = (
            f"Transcript count ({transcript_count}) and state.interviewProgress.lastQuestionNumber "
            f"({state_qnum}) disagree by >{abs(transcript_count - state_qnum)} questions. "
            f"Using transcript count as authoritative. "
            f"A frozen lastQuestionNumber is the v10.15.0 bug class — check update-interview-state.sh invocations."
        )

    return {
        "transcriptCount": transcript_count,
        "stateCount": state_qnum,
        "disagreeWarning": disagree_warning,
    }


# ── Legacy / pre-standard exemption (v12.4.0) ─────────────────────────────────

# Anti-fabrication substance floor for legacy interviews. The legacy flag lifts the
# 25-35 count floor ONLY; it never lifts the requirement that the interview be REAL.
# These floors are deliberately modest so a genuine pre-standard intake (e.g. a real
# 20-question owner interview) passes, while an empty/near-empty transcript that merely
# carries the flag does NOT.
LEGACY_MIN_QUESTIONS = 8           # at least this many Q-blocks must be present
LEGACY_MIN_ANSWERED_QUESTIONS = 8  # at least this many must carry a real owner answer
LEGACY_MIN_ANSWER_CHARS = 12       # an "answer" must be at least this many chars to count


# Transcript marker forms that mark a verified pre-standard interview.
_LEGACY_MARKER_PATTERNS = [
    r"<!--\s*legacy-interview\s*:\s*pre-standard",  # <!-- LEGACY-INTERVIEW: pre-standard ... -->
    r"\blegacy-interview\s*:\s*pre-standard\b",      # legacy-interview: pre-standard
]


def is_legacy_interview(transcript: str, state: dict, cli_flag: bool) -> dict:
    """
    Determine whether this interview is a VERIFIED pre-standard / legacy interview
    that is exempt from the 25-35 count floor.

    Detected via ANY of (in precedence order, all equally sufficient):
      (a) cli_flag (--legacy-interview) — operator asserts it for a verified real interview.
      (b) state.legacyInterview.preStandard == true.
      (c) a transcript marker line ('<!-- LEGACY-INTERVIEW: pre-standard -->' or
          'legacy-interview: pre-standard').

    Returns {"legacy": bool, "sources": [...], "meta": {...}}.
    Reads only. Does NOT decide whether the exemption is GRANTED — that requires the
    anti-fabrication substance check (legacy_substance_ok) to also pass. This function
    only answers "was it CLAIMED to be legacy, and by what evidence".
    """
    sources = []
    meta = {}

    if cli_flag:
        sources.append("cli:--legacy-interview")

    legacy_obj = state.get("legacyInterview")
    if isinstance(legacy_obj, dict) and legacy_obj.get("preStandard") is True:
        sources.append("state:legacyInterview.preStandard")
        # Capture audit-trail fields if present (none are required).
        for k in ("ownerConfirmed", "confirmedBy", "confirmedAt", "standardVersion", "reason"):
            if k in legacy_obj:
                meta[k] = legacy_obj[k]

    lowered = transcript.lower()
    for pat in _LEGACY_MARKER_PATTERNS:
        if re.search(pat, lowered):
            sources.append("transcript:legacy-marker")
            break

    return {"legacy": len(sources) > 0, "sources": sources, "meta": meta}


def legacy_substance_ok(transcript: str, count_result: dict) -> dict:
    """
    Anti-fabrication substance floor for the legacy exemption.

    A legacy/pre-standard interview is only EXEMPT from the count floor if it is a
    REAL, owner-authored interview — never an empty or faked one. We require:
      - at least LEGACY_MIN_QUESTIONS real questions (Q-blocks), AND
      - at least LEGACY_MIN_ANSWERED_QUESTIONS questions that carry a non-trivial
        owner-authored answer line (>= LEGACY_MIN_ANSWER_CHARS of real text after the
        Q-line, not itself a Q-line / heading / separator).

    Returns {"ok": bool, "questions": int, "answered": int, "reason": str|None}.
    Reads only.
    """
    questions = count_result.get("transcriptCount", 0)

    # Count "answered" questions: a Q-block line followed (before the next Q-block /
    # separator) by at least one substantive client/answer line.
    lines = transcript.splitlines()
    answered = 0
    in_block = False
    block_has_answer = False

    def _is_q_line(s: str) -> bool:
        s = s.strip()
        return bool(
            re.match(r"^\*\*Q", s, re.IGNORECASE)
            or re.match(r"^Q-\w+", s)
            or re.match(r"^#+\s*Question\s+\d+", s, re.IGNORECASE)
            or re.match(r"^\d+\.\s+\*\*Q", s, re.IGNORECASE)
        )

    def _is_structural(s: str) -> bool:
        s = s.strip()
        return (not s) or bool(re.match(r"^---+$", s)) or bool(re.match(r"^#+\s", s))

    def _close_block():
        nonlocal answered, block_has_answer
        if in_block and block_has_answer:
            answered += 1

    for raw in lines:
        if _is_q_line(raw):
            _close_block()
            in_block = True
            block_has_answer = False
            continue
        if not in_block:
            continue
        if _is_structural(raw):
            continue
        # A candidate answer line. Strip common answer markers for the length test.
        text = raw.strip()
        text = re.sub(r"^>+\s*", "", text)
        text = re.sub(r"^\*\*A[:\*]\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"^A:\s*", "", text, flags=re.IGNORECASE)
        if len(text.strip()) >= LEGACY_MIN_ANSWER_CHARS:
            block_has_answer = True
    _close_block()

    ok = (questions >= LEGACY_MIN_QUESTIONS) and (answered >= LEGACY_MIN_ANSWERED_QUESTIONS)
    reason = None
    if not ok:
        if questions < LEGACY_MIN_QUESTIONS:
            reason = (
                f"legacy-flag-without-substance: only {questions} question(s) "
                f"(need >= {LEGACY_MIN_QUESTIONS}). A legacy flag cannot exempt an "
                f"empty/near-empty interview from the count floor."
            )
        else:
            reason = (
                f"legacy-flag-without-substance: only {answered} answered question(s) "
                f"with real owner text (need >= {LEGACY_MIN_ANSWERED_QUESTIONS}). "
                f"A legacy flag cannot exempt a transcript with no real answers."
            )

    return {"ok": ok, "questions": questions, "answered": answered, "reason": reason}


# ── Edit-mode exemption (standard-first redesign, PHASE 7) ────────────────────
#
# Under buildType == "standard-first" the canonical department floor is ALREADY
# prebuilt before the interview begins (prebuild-standard-workforce.sh), so the
# interview EDITS the built set — for each prebuilt department the owner
# decides KEEP (implicit), TUNE (content), or REMOVE (confirmed decline with
# loss warning) — instead of sitting through a from-scratch intake. A
# substantive edit-mode review can legitimately complete well under 25
# questions, so the 25-35 count floor needs an edit-mode exemption.
#
# The exemption mirrors the legacy one above in every protective detail:
#   - it lifts ONLY the 25-35 count floor (the >36 ceiling, jargon,
#     mandatory-field, decline-provenance, and no-fabrication checks still
#     apply in full);
#   - it is gated by an anti-fabrication substance floor
#     (edit_mode_substance_ok) — an edit-mode CLAIM with no real owner
#     answers is a HARD FAIL ('edit-mode-flag-without-substance');
#   - it never applies to a legacy box (absent buildType): those keep the
#     25-35 bar exactly as before.

# Anti-fabrication substance floor for edit-mode interviews. An edit-mode
# interview that merely reviews the prebuilt set still needs REAL owner input —
# a handful of genuine questions/answers plus a recorded department-review
# pass — so the floors below the legacy ones would be too permissive, but the
# legacy floors (8/8) would demand re-asking departments the owner already
# decided on in the review board. The substance bar here: at least 5 real
# Q-blocks, at least 5 with genuine owner-authored answers.
EDIT_MODE_MIN_QUESTIONS = 5
EDIT_MODE_MIN_ANSWERED_QUESTIONS = 5


def is_edit_mode_interview(state: dict | None) -> dict:
    """
    Determine whether this interview is a standard-first EDIT-MODE interview:
    the canonical floor was prebuilt before the interview began, so the
    interview reviews/edits the built set instead of gathering intake from
    scratch.

    Detection (fail-safe — absent/garbage state returns not-edit-mode):
      buildType == "standard-first"                       (REQUIRED)
      AND at least ONE of:
        - standardPrebuild.status == "done"               (prebuild ran), or
        - interviewMode == "edit"                          (recorded mode), or
        - interviewProgress.interviewMode == "edit".

    Returns {"editMode": bool, "basis": str, "prebuildStatus": str|None}.
    Reads only. A bare buildType without any prebuild/mode corroboration is
    NOT edit-mode — the exemption requires the prebuilt-set claim to be
    corroborated by the prebuild record or an explicit recorded mode.
    """
    st = state or {}
    build_type = str(st.get("buildType") or "").strip().lower()
    if build_type != "standard-first":
        return {"editMode": False, "basis": "", "prebuildStatus": None}

    prebuild = st.get("standardPrebuild")
    prebuild_status = None
    if isinstance(prebuild, dict):
        prebuild_status = prebuild.get("status")

    if prebuild_status == "done":
        return {
            "editMode": True,
            "basis": "buildType=standard-first + standardPrebuild.status=done",
            "prebuildStatus": prebuild_status,
        }
    if str(st.get("interviewMode") or "").strip().lower() == "edit":
        return {
            "editMode": True,
            "basis": "buildType=standard-first + interviewMode=edit",
            "prebuildStatus": prebuild_status,
        }
    prog_mode = (st.get("interviewProgress") or {}).get("interviewMode")
    if str(prog_mode or "").strip().lower() == "edit":
        return {
            "editMode": True,
            "basis": "buildType=standard-first + interviewProgress.interviewMode=edit",
            "prebuildStatus": prebuild_status,
        }
    return {"editMode": False, "basis": "", "prebuildStatus": prebuild_status}


def edit_mode_substance_ok(transcript: str, count_result: dict) -> dict:
    """
    Anti-fabrication substance floor for the edit-mode exemption.

    An edit-mode interview is only EXEMPT from the 25-35 count floor if it is
    a REAL, owner-participated review — never an empty or faked one. We
    require:
      - at least EDIT_MODE_MIN_QUESTIONS real questions (Q-blocks), AND
      - at least EDIT_MODE_MIN_ANSWERED_QUESTIONS questions that carry a
        non-trivial owner-authored answer line (same line-shape test as
        legacy_substance_ok()).

    Returns {"ok": bool, "questions": int, "answered": int, "reason": str|None}.
    Reads only.
    """
    questions = count_result.get("transcriptCount", 0)

    lines = transcript.splitlines()
    answered = 0
    in_block = False
    block_has_answer = False

    def _is_q_line(s: str) -> bool:
        s = s.strip()
        return bool(
            re.match(r"^\*\*Q", s, re.IGNORECASE)
            or re.match(r"^Q-\w+", s)
            or re.match(r"^#+\s*Question\s+\d+", s, re.IGNORECASE)
            or re.match(r"^\d+\.\s+\*\*Q", s, re.IGNORECASE)
        )

    def _is_structural(s: str) -> bool:
        s = s.strip()
        return (not s) or bool(re.match(r"^---+$", s)) or bool(re.match(r"^#+\s", s))

    def _close_block():
        nonlocal answered, block_has_answer
        if in_block and block_has_answer:
            answered += 1

    for raw in lines:
        if _is_q_line(raw):
            _close_block()
            in_block = True
            block_has_answer = False
            continue
        if not in_block:
            continue
        if _is_structural(raw):
            continue
        text = raw.strip()
        text = re.sub(r"^>+\s*", "", text)
        text = re.sub(r"^\*\*A[:\*]\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"^A:\s*", "", text, flags=re.IGNORECASE)
        if len(text.strip()) >= LEGACY_MIN_ANSWER_CHARS:
            block_has_answer = True
    _close_block()

    ok = (questions >= EDIT_MODE_MIN_QUESTIONS) and (answered >= EDIT_MODE_MIN_ANSWERED_QUESTIONS)
    reason = None
    if not ok:
        if questions < EDIT_MODE_MIN_QUESTIONS:
            reason = (
                f"edit-mode-flag-without-substance: only {questions} question(s) "
                f"(need >= {EDIT_MODE_MIN_QUESTIONS}). An edit-mode flag cannot exempt an "
                f"empty/near-empty interview from the count floor."
            )
        else:
            reason = (
                f"edit-mode-flag-without-substance: only {answered} answered question(s) "
                f"with real owner text (need >= {EDIT_MODE_MIN_ANSWERED_QUESTIONS}). "
                f"An edit-mode flag cannot exempt a transcript with no real answers."
            )

    return {"ok": ok, "questions": questions, "answered": answered, "reason": reason}


# ── Structured-web coverage standard (2026-07-30 fix) ─────────────────────────
#
# WHICH STANDARD APPLIES: not a new config flag. is_structured_web_interview()
# below reads state.interviewProgress.lastQuestionAskedBy — a field that
# ALREADY exists for an unrelated reason (rate-limit bucketing —
# lib-interview-rate-limit.sh's INTERVIEW_RATE_LIMIT_SHARED_LITERAL_SENTINEL /
# update-interview-state.sh's --asked-by). The Command Center's
# /api/interview/answer route — the structured web deck's OWN submission
# endpoint, the "STRUCTURED-CARD write path" per its own header comment — is the
# ONLY caller that ever invokes update-interview-state.sh without an explicit
# --asked-by, and it defaults askedBy to the EXACT literal "interview-web"
# whenever the request carries no authenticated-operator identity
# (Cf-Access-Authenticated-User-Email / x-operator-email / an explicit
# askedBy) — the normal case for a client filling out cards themselves. The
# conversational path (SKILL.md's Telegram-agent flow) always calls
# update-interview-state.sh with --asked-by "$AGENT_NAME" — a real agent
# identity, never this literal. A missing/unknown value defaults to False (NOT
# structured), which routes to the EXISTING, STRICTER raw-count standard — an
# unknown signal can only ever raise the bar an interview must clear, never
# lower it.

def is_structured_web_interview(state: dict | None) -> bool:
    """
    True when this interview's most recently recorded answer arrived through
    the Command Center's structured web deck (the QuestionCard flow), rather
    than the conversational Telegram-agent flow. See the module comment above
    for the signal and why it reliably distinguishes the two. Fail-safe:
    absent/garbage state -> False (routes to the existing, stricter
    conversational/raw-count standard — never the reverse).
    """
    progress = (state or {}).get("interviewProgress") or {}
    asked_by = str(progress.get("lastQuestionAskedBy") or "").strip().lower()
    return asked_by == "interview-web"


# The two CC-owned (non-branding) sections of the structured deck's canonical
# question set. Byte-identical port (id/prompt/required only — the fields this
# gate needs) of blackceo-command-center's src/lib/interview/base-questions.ts
# IDENTITY_QUESTIONS / OPERATIONS_QUESTIONS. This is DATA, not logic: a future
# drift here can only ever make coverage MISS a genuinely-asked canonical
# question (undercount -> more scrutiny, never less) — it can never invent
# coverage for a question the client was never actually asked, because a match
# still requires a real transcript **Q:**/**A:** block whose question text
# normalizes (norm_prompt) to this exact prompt (see check_structured_coverage()
# below, which reuses parse_answer_blocks()/norm_prompt() from check #3 above).
IDENTITY_QUESTIONS_CANONICAL = [
    {"id": "company_name", "prompt": "What is your company name?", "required": True},
    {"id": "industry", "prompt": "What industry are you in?", "required": True},
]
OPERATIONS_QUESTIONS_CANONICAL = [
    {
        "id": "command_center_name",
        "prompt": "What would you like to name your company's home base?",
        "required": False,
    },
]

# Substance floors — REUSED, not invented:
#   - STRUCTURED_SUBSTANCE_MIN_CHARS reuses the EXACT numeric floor
#     check_no_fabrication() above already uses for "a snippet long enough to
#     be meaningful, not a tiny/coincidental match" (its context_snippets
#     filter: `len(snippet) >= 30`). Applied here to any canonical question the
#     branding JSON itself flags as needing a specific, non-generic answer (a
#     non-empty `interviewGuidance` field) — brand_evokes, customer_feeling,
#     brand_descriptors, brand_voice, ideal_customer, unique_differentiator.
#     This floor is exactly what catches that guidance's OWN worked examples of
#     an insufficient answer: "'Professional' is NOT an answer" (12 chars),
#     "'Happy' is not specific enough" (5 chars), "'Small business owners' ...
#     re-drill" (22 chars) — all below 30.
#   - STRUCTURED_EXISTENCE_MIN_CHARS reuses LEGACY_MIN_ANSWER_CHARS as-is (the
#     SAME "is this a real, non-empty answer line" floor legacy_substance_ok()
#     above already applies) for canonical questions the branding JSON does NOT
#     flag as needing drilled specificity (company name, industry, hex color,
#     logo URL, command-center name) — a short factual answer to these is
#     normal and correct, not shallow.
STRUCTURED_SUBSTANCE_MIN_CHARS = 30
STRUCTURED_EXISTENCE_MIN_CHARS = LEGACY_MIN_ANSWER_CHARS


def load_canonical_structured_questions(branding_questions_path: Path) -> list:
    """
    Assemble the FULL structured-web-deck canonical question set: identity ->
    branding -> operations — same order and content as blackceo-command-center's
    src/lib/interview-questions.ts:
        INTERVIEW_QUESTIONS = [...IDENTITY_QUESTIONS, ...BRANDING_QUESTIONS, ...OPERATIONS_QUESTIONS]
    Branding questions are loaded from branding-questions.json — the SAME single
    canonical source check_mandatory_fields() above already loads (never
    duplicated/hand-copied here). Each item is normalized to
    {id, prompt, required, needsSubstance, kind}, where needsSubstance is True
    only when the branding JSON itself carries a non-empty `interviewGuidance`
    for that question, and `kind` is the branding JSON's own answer-kind
    ("text" | "color" | "url" | "choice") — used below to exempt structurally
    short-but-correct answers (a hex color, a URL) from the prose substance
    floor; identity/operations questions are all kind "text".
    """
    bq = load_json(branding_questions_path, "branding-questions.json")
    branding_questions = bq.get("questions", [])

    combined = []
    for q in IDENTITY_QUESTIONS_CANONICAL:
        combined.append(dict(q, needsSubstance=False, kind="text"))
    for q in branding_questions:
        combined.append({
            "id": q["id"],
            "prompt": q["prompt"],
            "required": bool(q.get("required", False)),
            "needsSubstance": bool(q.get("interviewGuidance")),
            "kind": q.get("kind", "text"),
        })
    for q in OPERATIONS_QUESTIONS_CANONICAL:
        combined.append(dict(q, needsSubstance=False, kind="text"))
    return combined


def check_structured_coverage(transcript: str, branding_questions_path: Path) -> dict:
    """
    Check #1 (structured-web path): coverage + substance of the FULL canonical
    structured question set, using the SAME transcript-matching machinery as
    check #3 (parse_answer_blocks() / norm_prompt() — byte-identical ports of
    the Command Center's seam.ts / structured-progress.ts) so this gate and the
    Command Center's own "is this question answered" notion can never drift.

    For each canonical question, the LONGEST answer across ALL transcript
    blocks that matched it is used — an interview may drill/re-ask the SAME
    canonical question several times (the proven real fixture drilled
    customer_feeling x6); the BEST substantive answer is what counts, not how
    many rounds it took to get there:
      - no matching block at all               -> MISSING
      - matched, but below its substance floor  -> SHALLOW (see the floor
        constants above)
      - matched, at/above its floor              -> ANSWERED

    `complete` is True only when NO required canonical question is missing or
    shallow (optional questions — brand_primary_color, brand_logo, brand_voice,
    command_center_name — never block completeness, mirroring
    check_mandatory_fields()'s required-only gate). Read-only; never raises —
    a malformed/absent transcript degrades to every question MISSING
    (fail-closed).
    """
    questions = load_canonical_structured_questions(branding_questions_path)
    idx = {}
    for q in questions:
        key = norm_prompt(q["prompt"])
        if key and key not in idx:
            idx[key] = q

    blocks = parse_answer_blocks(transcript or "")
    best_len: dict = {}
    for b in blocks:
        ans = (b.get("answer") or "").strip()
        if not ans:
            continue
        q = idx.get(norm_prompt(b.get("question", "")))
        if not q:
            continue
        qid = q["id"]
        if len(ans) > best_len.get(qid, -1):
            best_len[qid] = len(ans)

    answered_ids, missing_ids, shallow_ids = [], [], []
    for q in questions:
        qid = q["id"]
        length = best_len.get(qid)
        if length is None:
            missing_ids.append(qid)
            continue
        if q.get("kind", "text") != "text":
            # A structurally short-form value (hex color, URL) is correct at
            # any non-empty length -- the prose substance floors below don't
            # apply. Any matched, non-empty answer counts (parse_answer_blocks
            # already guarantees non-empty via the best_len collection above).
            floor = 1
        elif q.get("needsSubstance"):
            floor = STRUCTURED_SUBSTANCE_MIN_CHARS
        else:
            floor = STRUCTURED_EXISTENCE_MIN_CHARS
        if length < floor:
            shallow_ids.append(qid)
        else:
            answered_ids.append(qid)

    required_ids = [q["id"] for q in questions if q.get("required")]
    required_set = set(required_ids)
    missing_required_ids = [i for i in missing_ids if i in required_set]
    shallow_required_ids = [i for i in shallow_ids if i in required_set]

    return {
        "total": len(questions),
        "requiredTotal": len(required_ids),
        "answeredIds": answered_ids,
        "missingIds": missing_ids,
        "shallowIds": shallow_ids,
        "missingRequiredIds": missing_required_ids,
        "shallowRequiredIds": shallow_required_ids,
        "complete": not missing_required_ids and not shallow_required_ids,
    }


# ── Check 2: Forbidden jargon ─────────────────────────────────────────────────

def _is_ai_authored(line: str, prev_was_ai: bool) -> bool:
    """
    Heuristic: determine whether a transcript line is AI-authored (vs client answer).

    AI-authored lines:
      - Start with **Q**, Q-, Question, ## / ### headings, or are the agent's
        framing/context prose (no leading ">" or "A:" marker).
      - Are immediately after a separator line (---).

    Client answer lines:
      - Follow a Q-block until the next Q-block / separator.
      - May start with ">", "**A**", "A:", or just be plain response text.

    Conservative approach: when ambiguous, treat as client text (avoid false-positives).
    """
    stripped = line.strip()
    if not stripped:
        return False

    # Strong AI signals
    if re.match(r"^\*\*Q", stripped, re.IGNORECASE):
        return True
    if re.match(r"^Q-\w+", stripped):
        return True
    if re.match(r"^#+\s*(Question|Phase|Interview)", stripped, re.IGNORECASE):
        return True
    if re.match(r"^---+$", stripped):
        return True  # separator line itself is AI-structural

    # Strong client signals — exempt these
    if re.match(r"^>", stripped):
        return False
    if re.match(r"^\*\*A[:\*]", stripped, re.IGNORECASE):
        return False
    if re.match(r"^A:\s", stripped, re.IGNORECASE):
        return False

    # For unlabeled lines: treat as client text (conservative false-negative preference)
    return False


def scan_jargon(transcript: str, jargon_list: list) -> list:
    """
    Scan AI-authored lines in the transcript for forbidden jargon terms.
    Returns list of {term, line, lineNumber, variant} dicts for each hit.
    Exempt: client answer spans (lines that are NOT AI-authored per _is_ai_authored).
    """
    hits = []
    lines = transcript.splitlines()
    prev_was_ai = False

    for lineno, raw_line in enumerate(lines, start=1):
        ai_authored = _is_ai_authored(raw_line, prev_was_ai)
        if not ai_authored:
            prev_was_ai = False
            continue
        prev_was_ai = True

        line_lower = raw_line.lower()

        for entry in jargon_list:
            # Skip terms with clientAnswerExempt only (still scan AI text)
            check_term = entry["term"]
            all_variants = [check_term] + entry.get("variants", [])

            for variant in all_variants:
                # Word-boundary, case-insensitive match
                pattern = r"\b" + re.escape(variant.lower()) + r"\b"
                if re.search(pattern, line_lower):
                    hits.append({
                        "term": check_term,
                        "matchedVariant": variant,
                        "line": lineno,
                        "text": raw_line.strip()[:120],
                    })
                    break  # one hit per term per line

    return hits


# ── Structured transcript matching (2026-07-30 fix, U048-follow-on) ──────────
# Client Mac mini box / rescue-agent incident: check_mandatory_fields()
# below used to look ONLY at build-state (state[fid] / state["brandingAnswers"][fid] /
# state["interview"][fid]) for the five branding required fields. The normal interview
# flow NEVER writes those keys to build-state — per SKILL.md, a free-text branding
# answer is logged ONLY to workforce-interview-answers.md via log_answer(). A verified
# real client transcript had all 11 canonical structured questions answered (each
# 534-921 chars) and a 90-key build-state with none of the five branding keys anywhere
# in it — so this check reported all five "missing" for EVERY client, unconditionally,
# regardless of what they actually answered. She was told (wrongly) that she still had
# ~10 questions outstanding, after already being told (also wrongly) that she was done.
#
# The functions below are byte-identical ports of the Command Center's OWN matching
# semantics (blackceo-command-center src/lib/interview/seam.ts:parseAnswerBlocks() and
# src/lib/interview/structured-progress.ts:normPrompt()/computeAnsweredIds()) — the
# same code the Command Center's /api/interview/state route and the client's resume
# logic use to decide "is this question answered". Reusing it here (rather than
# inventing a looser comparison) guarantees this QC gate can never disagree with the
# Command Center about whether a branding field was actually answered.
#
# FAIL-CLOSED: this is an ADDITIONAL source, never a replacement. A field is present
# if EITHER the (pre-existing) build-state locations OR the transcript match says so.
# A field with no match in state AND no matching answered transcript block is STILL
# reported missing — this can only ever recognize MORE genuinely-answered fields, never
# fewer; it cannot turn a real gap into a false pass.

def norm_prompt(s: str) -> str:
    """
    Byte-identical port of structured-progress.ts normPrompt(): lowercase, collapse
    all whitespace runs to a single space, strip. Used to tolerantly match a
    transcript's recorded question text against a canonical question prompt.
    """
    return re.sub(r"\s+", " ", s.lower()).strip()


# Chunk boundary: a line consisting only of 3+ dashes, with a newline on each side.
# Byte-identical to seam.ts parseAnswerBlocks()'s `text.split(/\n\s*-{3,}\s*\n/)`.
_ANSWER_BLOCK_SPLIT_RE = re.compile(r"\n\s*-{3,}\s*\n")
# Byte-identical to seam.ts's qMatch / aMatch regexes (note the REQUIRED colon —
# this is the format build-workforce.py's own log_answer() writes: "**Q:** ... **A:** ...").
_Q_BLOCK_RE = re.compile(r"\*\*Q:\*\*\s*([\s\S]*?)(?=\n\*\*A:\*\*)")
_A_BLOCK_RE = re.compile(r"\*\*A:\*\*\s*([\s\S]*?)(?=\n\*\*(?:Provenance|Logged|Updated)\b|$)")


def parse_answer_blocks(text: str) -> list:
    """
    Byte-identical port of seam.ts parseAnswerBlocks(): split the transcript into
    content-level Q/A blocks on '---' separator lines, then extract the **Q:** /
    **A:** pair from each chunk. A chunk with no Q, no A, or an empty question is
    skipped (same semantics as the TS regexes simply not matching). Read-only;
    never raises — a malformed/absent transcript degrades to an empty list.
    Returns a list of {"question": str, "answer": str} dicts.
    """
    if not text:
        return []
    blocks = []
    for chunk in _ANSWER_BLOCK_SPLIT_RE.split(text):
        qm = _Q_BLOCK_RE.search(chunk)
        am = _A_BLOCK_RE.search(chunk)
        if not qm or not am:
            continue
        question = qm.group(1).strip()
        if not question:
            continue
        answer = am.group(1).strip()
        blocks.append({"question": question, "answer": answer})
    return blocks


def compute_answered_ids(blocks: list, questions: list) -> set:
    """
    Byte-identical port of structured-progress.ts computeAnsweredIds(): index the
    canonical question set by normPrompt(prompt) (first definition wins), then for
    every transcript block with a non-empty answer, look up normPrompt(block
    question) in that index. A hit marks that question id answered. Blocks that
    match no canonical prompt (free-form/conversational depth) are ignored, and a
    block whose answer is empty/whitespace-only is never counted as answered —
    identical to the TS original. Read-only. Returns the set of answered question ids.
    """
    idx = {}
    for q in questions:
        key = norm_prompt(q.get("prompt", ""))
        if key and key not in idx:
            idx[key] = q.get("id")

    answered = set()
    for b in blocks:
        if not b.get("answer") or not b["answer"].strip():
            continue
        qid = idx.get(norm_prompt(b.get("question", "")))
        if qid:
            answered.add(qid)
    return answered


# ── Check 3: Mandatory fields ─────────────────────────────────────────────────

def check_mandatory_fields(state: dict, branding_questions_path: Path,
                            transcript: str = "") -> dict:
    """
    Load branding required:true fields from branding-questions.json (single source).
    Also check structural build-state requireds.

    A branding field is PRESENT when EITHER:
      (a) it is recorded in build-state (state[fid] / state["brandingAnswers"][fid] /
          state["interview"][fid]) — the pre-2026-07-30 check, kept as-is so any flow
          that DOES mirror answers into build-state keeps working unchanged; OR
      (b) the transcript has an answered Q/A block whose question text matches the
          field's canonical prompt (see compute_answered_ids() above) — the FIX: this
          is where the real interview actually logs branding answers.
    Fail-closed: a field with neither is still reported missing.

    Returns {"missing": [...], "checked": [...]}
    """
    # Load branding requireds dynamically
    try:
        bq = load_json(branding_questions_path, "branding-questions.json")
        branding_questions = bq.get("questions", [])
        branding_required = [
            q["id"]
            for q in branding_questions
            if q.get("required", False)
        ]
    except SystemExit:
        # branding-questions.json must be readable — if not, hard fail
        raise

    # Structural build-state requireds.
    #
    # D3 FIX — this gate was UNSATISFIABLE on the web lane, the only lane
    # clients actually use. `ownerChat` and `agentName` are BOX PLUMBING, not
    # interview answers: the owner is never asked for either one, and nothing on
    # the web path populates them (the Command Center has no Telegram chat id to
    # record). Worse, `ownerChat` is seeded as the integer 0 (see
    # backfill-build-state.py), and `0` is FALSY — so `not state.get("ownerChat")`
    # read a field that WAS present as missing. The result: a client could answer
    # every single question and still hard-fail "Missing mandatory fields:
    # ownerChat, agentName", which makes update-interview-state.sh --complete
    # refuse with exit 87 forever, on evidence that was never the client's to
    # provide.
    #
    # They are NOT dropped — they move to `plumbingMissing`, which build_verdict()
    # surfaces as a WARNING so a genuinely unconfigured box still gets named for
    # operator follow-up. Only the two fields that ARE real interview content
    # remain hard requirements.
    structural_required = ["companyName", "industry"]
    plumbing_required = ["ownerChat", "agentName"]

    # Transcript-sourced answers (2026-07-30 fix): match the transcript's Q/A blocks
    # against the FULL branding question set (not just the required ones) using the
    # exact same prompt-normalization + matching semantics as the Command Center's
    # structured-progress.ts, so this gate and the CC's own "answered" notion can
    # never drift apart.
    # v22.0.29 FOLLOW-UP: match against the FULL canonical set (identity +
    # branding + operations), not branding alone. `company_name` and `industry`
    # are IDENTITY questions (IDENTITY_QUESTIONS_CANONICAL), NOT branding ones —
    # branding-questions.json contains only the eight brand_* / customer_* ids.
    # The structural companyName/industry checks below accept answered-transcript
    # evidence, but that acceptance was DEAD CODE while this list was built from
    # branding_questions alone: `"company_name" in transcript_answered_ids` could
    # never be true, so a pure web-lane interview that genuinely answered both
    # still hard-failed "Missing mandatory fields: companyName, industry" — the
    # exact D3 symptom the structural fix was meant to remove.
    _all_canonical = (
        list(IDENTITY_QUESTIONS_CANONICAL)
        + list(branding_questions)
        + list(OPERATIONS_QUESTIONS_CANONICAL)
    )
    transcript_answered_ids = compute_answered_ids(
        parse_answer_blocks(transcript or ""), _all_canonical
    )

    missing = []

    def field_present(key: str) -> bool:
        if key in transcript_answered_ids:
            return True
        # Check multiple possible state locations for branding answers
        v = (
            state.get(key)
            or (state.get("brandingAnswers") or {}).get(key)
            or (state.get("interview") or {}).get(key)
        )
        return bool(v)

    for fid in branding_required:
        if not field_present(fid):
            missing.append(fid)

    # Structural. D3 FIX: these two ARE real interview content — the branding
    # deck asks them as `company_name` and `industry` — so they are satisfiable
    # by ANSWERED TRANSCRIPT EVIDENCE exactly like every branding field above,
    # not only by a build-state mirror. A client who answered them in the
    # interview must not be reported missing merely because no flow copied the
    # value into build-state. Fail-closed is preserved: neither source present
    # is still missing.
    if not (
        state.get("companyName")
        or state.get("company_name")
        or "company_name" in transcript_answered_ids
    ):
        missing.append("companyName")
    if not (state.get("industry") or "industry" in transcript_answered_ids):
        missing.append("industry")

    # Box plumbing — WARNING-level only (see structural_required above). Reported
    # separately so a genuinely unconfigured box is still named, without letting
    # a field the owner was never asked for block a complete interview.
    plumbing_missing = []
    if not state.get("ownerChat") and not state.get("owner_chat"):
        plumbing_missing.append("ownerChat")
    if not state.get("agentName") and not state.get("agent_name"):
        plumbing_missing.append("agentName")

    # At least one locked department
    departments = state.get("departments", [])
    locked = []
    if isinstance(departments, list):
        # "prebuilt" (standard-first, PHASE 7): a department materialized by the
        # operator-triggered prebuild-standard-workforce.sh BEFORE the interview
        # began. It is MORE locked than "pending" (already on disk + chosen
        # artifact + board lane), so it satisfies this field exactly like a
        # planned department. Legacy boxes never carry this status, so the
        # legacy lane is byte-identical.
        locked = [
            d for d in departments
            if isinstance(d, dict) and d.get("status") in ("done", "building", "pending", "prebuilt")
        ]

    # D3 FIX: departments[] is not the only place a locked department is
    # recorded. record-dept-decision.sh writes the owner's per-department
    # choices to `canonicalReconciliation.decisions`, and on the standard-first
    # / web lane departments[] is deliberately NOT materialized until the
    # apply-diff build runs (update-interview-state.sh --complete only seeds it
    # as an EMPTY array sentinel, and refuses to fabricate entries). So an owner
    # who explicitly kept departments during the interview still presented an
    # empty departments[] to this check and hard-failed
    # "departments[at-least-one]" — for a decision they had in fact made. A
    # recorded `yes` decision is direct evidence of a locked department, so it
    # satisfies this check exactly like a departments[] entry. `no` (a decline)
    # and `later` (deferred) deliberately do NOT count.
    reconciliation = state.get("canonicalReconciliation") or {}
    decisions = reconciliation.get("decisions") or {}
    kept_decisions = []
    if isinstance(decisions, dict):
        kept_decisions = [
            dept_id for dept_id, rec in decisions.items()
            if isinstance(rec, dict) and rec.get("decision") == "yes"
        ]

    if not locked and not kept_decisions:
        missing.append("departments[at-least-one]")

    return {
        "missing": list(dict.fromkeys(missing)),  # dedup, preserve order
        "plumbingMissing": list(dict.fromkeys(plumbing_missing)),
        "checked": branding_required + structural_required + ["departments[at-least-one]"],
        "plumbingChecked": plumbing_required,
    }


# ── Check 4: Nudge cadence wired ─────────────────────────────────────────────

def check_nudges_wired(repo_root: Path) -> dict:
    """
    Static "is it wired" check — does not require a live cron or gateway.
      (a) interview-nudge-cron.sh exists and is executable
      (b) the box's shared cron REGISTRAR (ensure-pipeline-crons.sh) actually
          wires interview-nudge-cron.sh into the "interview-nudge" cron
      (c) nudge-incomplete-interviews.py has NUDGE_CONFIG with 24/72/168h

    (b) — 2026-07-30 fix (hot-patched-box false-HARD-FAIL, third defect of this
    shape in this file after the transcript-path fix / PR #772 and the
    mandatory-fields fix / PR #775): this USED to grep repo_root/"install.sh"
    for the string "interview-nudge-cron". install.sh is a PROVISIONING-TIME
    script — it runs once during a full install and is NEVER copied into the
    skills tree. Verified live on a hot-patched box (rescue-cassandra-henriquez):
    install.sh is absent from ~/.openclaw entirely. Every box patched via
    update-skills.sh (the fleet hot-patch path) therefore hard-failed this
    check permanently, for a reason with nothing to do with the client's
    interview.

    ensure-pipeline-crons.sh is the ACTUAL, current source of truth: per its
    own header, it is "the SHARED, IDEMPOTENT registrar/backfiller ... called
    by BOTH install.sh (end of run) and update-skills.sh (after the wiring
    phase) so files AND triggers always land together" — its _ensure_
    interview_nudge() function is what registers cron name "interview-nudge"
    (`openclaw cron add`) pointed at interview-nudge-cron.sh. It is persisted
    to <openclaw-root>/scripts/ensure-pipeline-crons.sh on EVERY successful
    run of either install.sh (canonical-scripts copy step) OR update-skills.sh
    (deliver_canonical_scripts_tree(), which runs before that script's
    same-version early-exit) — so, unlike install.sh, it is present on a
    hot-patched box.

    Deliberately NOT a live `openclaw cron list` check: interview-nudge is a
    LIFECYCLE cron. ensure-pipeline-crons.sh's own _ensure_interview_nudge()
    refuses to (re-)register it once state.interviewComplete==true, and
    _sweep_stale_lifecycle_crons() ACTIVELY REMOVES it once that flag flips.
    Since THIS gate runs at/after interview completion, a live "is the cron
    currently present" check would be checking for something a healthy box is
    expected to have already torn down — that would trade this false failure
    for a new one of the identical shape (checking a signal that is correct
    when negative). Checking the REGISTRAR's own wiring (capability) rather
    than a lifecycle-dependent live snapshot avoids that trap while still
    proving the mechanism is genuinely present and correctly configured.

    Two candidate locations are checked for the registrar, matching this
    script's two real call shapes: repo_root may be a live deployed skills
    tree (default; no --repo-root — ensure-pipeline-crons.sh lives at the
    SIBLING <openclaw-root>/scripts/, found via _resolve_openclaw_root()) or
    an explicit full repo checkout (--repo-root; scripts/ is a direct child
    of repo_root, as used by this script's own test suite / CI).
    """
    issues = []

    nudge_cron = repo_root / "23-ai-workforce-blueprint" / "scripts" / "interview-nudge-cron.sh"
    if not nudge_cron.exists():
        issues.append(f"interview-nudge-cron.sh not found at {nudge_cron}")
    elif not os.access(nudge_cron, os.X_OK):
        issues.append(f"interview-nudge-cron.sh exists but is not executable: {nudge_cron}")

    registrar_candidates = [
        repo_root / "scripts" / "ensure-pipeline-crons.sh",
        _resolve_openclaw_root() / "scripts" / "ensure-pipeline-crons.sh",
    ]
    registrar = next((p for p in registrar_candidates if p.exists()), None)
    if registrar is None:
        issues.append(
            "ensure-pipeline-crons.sh (the shared cron registrar run by BOTH "
            "install.sh and update-skills.sh) not found at any of: "
            + ", ".join(str(p) for p in registrar_candidates)
        )
    else:
        content = registrar.read_text(encoding="utf-8", errors="replace")
        if "interview-nudge-cron.sh" not in content or '"interview-nudge"' not in content:
            issues.append(
                f"{registrar} does not register the interview-nudge cron "
                "(expected both a reference to interview-nudge-cron.sh and "
                "the cron name \"interview-nudge\")"
            )

    nudge_worker = repo_root / "shared-utils" / "nudge-incomplete-interviews.py"
    if nudge_worker.exists():
        worker_text = nudge_worker.read_text(encoding="utf-8", errors="replace")
        for expected_h in [24, 72, 168]:
            if f'"hours_idle": {expected_h}' not in worker_text and f"'hours_idle': {expected_h}" not in worker_text and f"hours_idle: {expected_h}" not in worker_text:
                issues.append(f"nudge-incomplete-interviews.py: missing {expected_h}h nudge cadence in NUDGE_CONFIG")
    else:
        issues.append(f"nudge-incomplete-interviews.py not found at {nudge_worker}")

    return {
        "wired": len(issues) == 0,
        "issues": issues,
    }


# ── Check 5: No-fabrication (v12.3.4) ────────────────────────────────────────

def check_no_fabrication(transcript: str, context_map_path: Path | None,
                         state: dict | None = None) -> dict:
    """
    Check #5 (v12.3.4 + G1-FAB-ENFORCE): NO-FABRICATION guardrail.

    (G1) SYNTHETIC-TRANSCRIPT gate: if the transcript bears the non-interactive
    synthetic header (i.e. it was assembled FROM CONFIG by build_from_config, not from
    live client turns) it is a FABRICATED transcript and HARD-FAILS (exit 3) UNLESS an
    explicit ownerConsent self-setup/fast record is present in build-state. This closes
    the silent-pass hole where a synthetic transcript with no context-map slipped
    through the old early skip below.

    If interview-context-map.json exists and a known/partial context snippet appears
    verbatim in workforce-interview-answers.md WITHOUT a 'confirmed-from-context:'
    provenance note in the same answer block, that is an UNCONFIRMED-CONTEXT-AS-ANSWER
    violation → HARD FAIL (exit 3).

    An answer block that DOES contain 'confirmed-from-context: <source>' PASSES — the
    client confirmed it live and the agent tagged it correctly.

    If context-map is absent (and no synthetic header) → check skips (returns pass).
    This is intentional: on a fresh install or when context-ingest was not run, there
    is nothing to verify.

    Reads only. Never writes.
    """
    # (G1) Synthetic non-interactive transcript without consent = fabrication.
    if NON_INTERACTIVE_ANSWERS_HEADER in (transcript or ""):
        consent_ok, consent_reason, _consent = _validate_owner_consent(state)
        if not consent_ok:
            return {
                "violations": [{
                    "theme_id": "non-interactive-synthetic-transcript",
                    "source": "build_from_config",
                    "snippet_preview": NON_INTERACTIVE_ANSWERS_HEADER,
                    "reason": (
                        "Transcript bears the non-interactive synthetic header but no "
                        "valid ownerConsent record is present in build-state. This is a "
                        "fabricated transcript (config recorded as client answers without "
                        "an explicit self-setup/fast opt-in). " + consent_reason
                    ),
                }],
                "skipped": False,
                "note": "Synthetic non-interactive transcript without consent — HARD FAIL.",
            }
        # Consent present: a synthetic transcript is legitimate here. Do not silently
        # skip — note it and continue to the context-map check below.

    if context_map_path is None or not context_map_path.exists():
        return {"violations": [], "skipped": True,
                "note": "interview-context-map.json not found; check #5 skipped (not a failure)."}

    try:
        context_map = json.loads(context_map_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"violations": [], "skipped": True,
                "note": f"Could not read context map ({exc}); check #5 skipped."}

    themes = context_map.get("themes", [])
    violations = []

    # Build a list of (theme_id, snippet) pairs where status is known or partial
    # and the snippet is long enough to be meaningful (avoid 1-word false positives)
    context_snippets = []
    for t in themes:
        if t.get("status") in ("known", "partial") and t.get("snippet"):
            snippet = t["snippet"].strip()
            if len(snippet) >= 30:  # Only check snippets >= 30 chars (avoid tiny matches)
                context_snippets.append({
                    "theme_id": t["theme_id"],
                    "source": t.get("source", "unknown"),
                    "snippet": snippet,
                })

    if not context_snippets:
        return {"violations": [], "skipped": False,
                "note": "No substantial known-context snippets to verify."}

    # Parse answer blocks from transcript: each block is between --- separators
    # or a Q-block start. We look for blocks that contain a verbatim snippet
    # but lack 'confirmed-from-context:'.
    # Split by answer block boundaries (--- or **Q** lines)
    answer_blocks = re.split(
        r"(?:^---+\s*$)|(?=^\*\*Q[\*\s])",
        transcript,
        flags=re.MULTILINE,
    )

    for cs in context_snippets:
        snippet_lower = cs["snippet"].lower()
        # Find blocks that contain this snippet verbatim (case-insensitive)
        for block in answer_blocks:
            block_lower = block.lower()
            if snippet_lower in block_lower:
                # Check for provenance note in the same block
                if "confirmed-from-context:" not in block.lower():
                    # This is a violation: verbatim context copied without confirmation tag
                    preview = cs["snippet"][:100].replace("\n", " ")
                    violations.append({
                        "theme_id": cs["theme_id"],
                        "source": cs["source"],
                        "snippet_preview": preview,
                        "reason": (
                            f"Context snippet from '{cs['source']}' appears verbatim in "
                            f"answer block without 'confirmed-from-context:' provenance note. "
                            f"This answer must be confirmed live by the client before logging."
                        ),
                    })
                    break  # One violation per theme is enough

    return {
        "violations": violations,
        "skipped": False,
        "note": f"Checked {len(context_snippets)} context snippets against {len(answer_blocks)} answer blocks.",
    }


# ── Verdict assembly ──────────────────────────────────────────────────────────

def is_tailored_short_interview(state: dict | None) -> tuple:
    """
    A LEGITIMATELY-SHORT, fully-grounded interview is NOT a shallow/generic one.

    Some owners (notably a founder running their OWN self-build) already have most
    discovery blocks grounded from a prior corpus, so a real, complete interview can
    be a deliberately short "gap-only" pass (e.g. 9 questions) instead of 25-35.
    Hard-failing those on the raw count is a FALSE NEGATIVE: it reads a genuinely
    complete interview as "not done" and can trigger an erroneous re-interview.

    This returns (is_tailored, basis_str) when the build-state EXPLICITLY records
    such a tailored interview. It NEVER fabricates: it only trusts a signal the
    interview engine itself wrote. Recognized signals (any one):
      - interviewQc.overrideReason contains "tailored" or "founder" or "self-build"
      - scope / interviewProgress.scope mentions founder self-build / gap-only
      - interviewProgress.questionCountPlanned is a small positive int (< 24) AND
        interviewComplete is true (a planned-short interview that genuinely finished)
    """
    if not state:
        return (False, "")
    prog = state.get("interviewProgress") or {}
    qc = state.get("interviewQc") or {}
    override = str(qc.get("overrideReason") or "").lower()
    scope = (str(state.get("scope") or "") + " " + str(prog.get("scope") or "")).lower()
    planned = prog.get("questionCountPlanned") or state.get("questionCountPlanned")
    complete = bool(state.get("interviewComplete"))

    for token in ("tailored", "founder", "self-build", "gap-only", "gap only"):
        if token in override:
            return (True, f"interviewQc.overrideReason={qc.get('overrideReason')!r}")
        if token in scope:
            return (True, f"scope={scope.strip()!r}")
    # G1-FAB-ENFORCE: a bare questionCountPlanned<24 + interviewComplete=true is
    # EXACTLY what the fabricating path sets, so it can self-grant this exemption.
    # Require explicit consent provenance (a session-bound ownerConsent self-setup/
    # fast opt-in) before honoring the planned-short signal. The override/scope text
    # paths above already carry their own provenance and are unaffected.
    if isinstance(planned, int) and 0 < planned < 24 and complete:
        consent_ok, _creason, _consent = _validate_owner_consent(state)
        if consent_ok:
            return (True,
                    f"questionCountPlanned={planned} with interviewComplete=true and "
                    f"ownerConsent(sessionId={_consent.get('sessionId')})")
        # No consent provenance → do NOT grant the tailored exemption (fail-safe).
    return (False, "")


def check_decline_provenance(state: dict | None) -> list:
    """
    PRD P0-2 / P1-1: catch owner opt-outs (declines) that the build enforcer would
    SILENTLY DISCARD, at interview-QC time (pre-build) instead of at build time
    (where the drop is invisible).

    A decline is only HONORED by the build enforcer (build-workforce._canonical_decline_set
    and the mirror department-floor.declined_set) when it carries provenance. Anything
    else that expresses a "no" is ignored and the department is force-added back -- a
    smaller shop gets OVER-BUILT and the owner's opt-out vanishes with no error. This
    check mirrors the enforcer's REJECT branches EXACTLY and turns each rejected
    decline into a HARD FAIL so a stale/bare decline is fixed before the build runs.

    HONORED (not a violation):
      - decisions[cid] object form with decision=="no" AND all of
        source / decidedAt / decidedBy present (the shape record-dept-decision.sh writes), OR
      - decisions[cid]=="no" (bare string) or a declinedDepartments[] entry WITH
        canonicalReconciliation.ownerDeclineConfirmed == true.

    Only "no" declines are inspected -- a "yes"/"later" never shrinks the floor, so it
    can never over-build and is not a provenance concern.

    Returns a list of human-readable violation strings (empty when clean).
    """
    violations = []
    st = state or {}
    recon = st.get("canonicalReconciliation", {})
    if not isinstance(recon, dict):
        recon = {}
    owner_confirmed = bool(recon.get("ownerDeclineConfirmed"))

    decisions = recon.get("decisions", {})
    if isinstance(decisions, dict):
        for cid, decision in decisions.items():
            _cid = str(cid).strip()
            if isinstance(decision, dict):
                if str(decision.get("decision", "")).strip().lower() == "no":
                    required = ("decision", "source", "decidedAt", "decidedBy")
                    missing = [k for k in required if not decision.get(k)]
                    if missing:
                        violations.append(
                            f"decisions['{_cid}'] is an object 'no' missing provenance "
                            f"field(s) {missing}; the enforcer drops it and force-adds the "
                            f"department back (over-build). Re-record via "
                            f"scripts/record-dept-decision.sh."
                        )
            elif str(decision).strip().lower() == "no":
                if not owner_confirmed:
                    violations.append(
                        f"decisions['{_cid}'] is a BARE STRING 'no' with no "
                        f"canonicalReconciliation.ownerDeclineConfirmed gate; the enforcer "
                        f"drops it and force-adds the department back (over-build). Re-record "
                        f"via scripts/record-dept-decision.sh (writes the provenanced object form)."
                    )

    flat_list = st.get("declinedDepartments", []) or []
    if flat_list and not owner_confirmed:
        violations.append(
            f"declinedDepartments[] has {len(flat_list)} entr(ies) but "
            f"canonicalReconciliation.ownerDeclineConfirmed is not true; the enforcer "
            f"ignores ALL of them (over-build). Re-record each via "
            f"scripts/record-dept-decision.sh."
        )

    return violations


def build_verdict(
    count_result: dict,
    jargon_hits: list,
    field_result: dict,
    nudge_result: dict,
    fabrication_result: dict | None = None,
    legacy_result: dict | None = None,
    legacy_substance: dict | None = None,
    state: dict | None = None,
    web_store_result: dict | None = None,
    structured_coverage: dict | None = None,
    edit_mode_result: dict | None = None,
) -> tuple:
    """
    Returns (verdict_str, exit_code, details_dict).
    PASS=0, SOFT FAIL=2, HARD FAIL=3.
    Checks: 1=count, 2=jargon, 3=fields, 4=nudges, 5=no-fabrication (v12.3.4).

    STRUCTURED-WEB COVERAGE STANDARD (2026-07-30 fix): when
    is_structured_web_interview(state) is True, check #1 is decided ENTIRELY by
    `structured_coverage` (the result of check_structured_coverage() — coverage +
    substance of the ~11-question canonical structured deck) instead of the raw
    **Q:** block count. Neither the 25-35 floor NOR the >36 ceiling applies to
    this path — see check_structured_coverage()'s docstring for why raw count is
    the wrong axis for it. The legacy/tailored exemptions below are UNCHANGED and
    apply ONLY on the conversational (non-structured) path, exactly as before.

    The 25-35 count floor (PRD-2.15) is lifted ONLY through the unified short-interview
    exemption path, which covers TWO genuine cohorts (v13.2.0):

      (A) LEGACY / pre-standard (v12.4.0): a VERIFIED owner-authored interview that
          predates the 25-35 standard. Detected by is_legacy_interview() and gated by
          the anti-fabrication substance floor (legacy_substance_ok). When the flag is
          claimed but substance fails, it HARD-FAILS (a flag cannot launder a faked
          interview). A granted legacy interview is treated as a PASS on the count
          dimension (warning only).

      (B) TAILORED / founder-self-build / gap-only (v13.2.0): a build-state that
          EXPLICITLY records a tailored interview (see is_tailored_short_interview),
          e.g. a founder running their own self-build with most blocks pre-grounded.
          A low count here is DOWNGRADED to NEEDS-REVIEW (soft fail / exit 2), not a
          hard fail, so a genuinely-complete short interview is never misread as
          "not done".

      (C) EDIT-MODE / standard-first (PHASE 7): under buildType == "standard-first"
          the canonical floor was prebuilt before the interview began, so the
          interview reviews/edits the built set instead of gathering intake from
          scratch (see is_edit_mode_interview()). Detected via build-state
          (buildType + standardPrebuild.status=="done" or a recorded edit mode) and
          gated by the anti-fabrication substance floor (edit_mode_substance_ok).
          When granted, the interview is treated as a PASS on the count dimension
          (warning only), exactly like a granted legacy exemption. A claimed
          edit-mode interview WITHOUT real substance HARD-FAILS
          ('edit-mode-flag-without-substance').

    Strictness is preserved for everyone else: an ORDINARY client with a short
    interview and NO recorded legacy/tailored/edit-mode signal STILL hard-fails
    (exit 3), and an over-long interview (count > 36) STILL hard-fails regardless
    of any exemption.
    """
    hard_failures = []
    soft_failures = []
    warnings = []

    # Count check
    count = count_result["transcriptCount"]

    # ── Unified short-interview exemption (v13.2.0) ───────────────────────────
    # The count floor is lifted for a low count ONLY when one of two genuine signals
    # is present: a verified LEGACY/pre-standard interview (Edit A, v12.4.0) OR a
    # build-state-recorded TAILORED/founder-self-build/gap-only interview (Edit B).

    # (A) Legacy / pre-standard exemption (v12.4.0): a VERIFIED pre-standard interview
    # is exempt from the 25-35 count floor, but ONLY if it passes the anti-fabrication
    # substance floor. The flag NEVER launders an empty/faked interview.
    legacy_claimed = bool(legacy_result and legacy_result.get("legacy"))
    legacy_granted = False
    if legacy_claimed:
        if legacy_substance and legacy_substance.get("ok"):
            legacy_granted = True
            warnings.append(
                f"[legacy-exemption GRANTED] Pre-standard owner-authored interview "
                f"({count} questions, {legacy_substance.get('answered')} answered) is "
                f"EXEMPT from the 25-35 count floor. "
                f"Evidence: {', '.join(legacy_result.get('sources', []))}. "
                f"Jargon, mandatory-field, and no-fabrication checks STILL applied."
            )
        else:
            # Flag present but no real substance → HARD FAIL. The flag cannot launder
            # an empty/fabricated interview past the gate.
            sub_reason = (legacy_substance or {}).get(
                "reason", "legacy-flag-without-substance: insufficient real content."
            )
            hard_failures.append(
                f"[legacy-flag-without-substance] Legacy/pre-standard exemption CLAIMED "
                f"(evidence: {', '.join(legacy_result.get('sources', []))}) but the "
                f"interview does not show real owner-authored substance. {sub_reason}"
            )

    # (A2) Edit-mode exemption (standard-first, PHASE 7): under
    # buildType == "standard-first" the floor was prebuilt before the interview
    # began, so the interview EDITS the built set. Detected via build-state
    # (is_edit_mode_interview) and gated by the anti-fabrication substance floor
    # (edit_mode_substance_ok). The claim NEVER launders an empty/faked interview.
    edit_mode = bool(edit_mode_result and edit_mode_result.get("editMode"))
    edit_mode_granted = False
    if edit_mode:
        edit_substance = edit_mode_result.get("substance") or {}
        if edit_substance.get("ok"):
            edit_mode_granted = True
            warnings.append(
                f"[edit-mode-exemption GRANTED] Standard-first edit-mode interview "
                f"({count} questions, {edit_substance.get('answered')} answered) is "
                f"EXEMPT from the 25-35 count floor — the canonical floor was "
                f"prebuilt before this interview began, so the interview reviewed/"
                f"edited the built set. Basis: {edit_mode_result.get('basis')}. "
                f"Jargon, mandatory-field, decline-provenance, and no-fabrication "
                f"checks STILL applied."
            )
        else:
            sub_reason = edit_substance.get(
                "reason", "edit-mode-flag-without-substance: insufficient real content."
            )
            hard_failures.append(
                f"[edit-mode-flag-without-substance] Edit-mode exemption CLAIMED "
                f"(basis: {edit_mode_result.get('basis')}) but the interview does "
                f"not show real owner substance. {sub_reason}"
            )

    # (B) Tailored / founder-self-build / gap-only (v13.2.0): a build-state that
    # explicitly records a tailored interview downgrades a LOW count to NEEDS-REVIEW.
    tailored, tailored_basis = is_tailored_short_interview(state)

    # (C) Structured-web coverage standard (2026-07-30 fix): an interview conducted
    # through the Command Center's structured web deck is graded ENTIRELY on
    # coverage of the canonical question set, not raw count — see
    # is_structured_web_interview() / check_structured_coverage() above. This
    # branch REPLACES the raw-count floor/ceiling/borderline decision below for
    # this path only; the conversational path (elif chain below) is unchanged.
    is_structured = is_structured_web_interview(state)
    sc = structured_coverage or {}
    coverage_complete = bool(sc.get("complete"))

    # D4 FIX — MIXED-CHANNEL INTERVIEWS. Which standard applied used to be chosen
    # by is_structured_web_interview() ALONE, and that function reads exactly one
    # thing: interviewProgress.lastQuestionAskedBy, i.e. WHO STAMPED THE LAST
    # QUESTION. A single field about the final answer decided how the whole
    # interview was graded, so an owner who answered everything hard-failed in
    # BOTH directions whenever the channel changed mid-interview:
    #
    #   • web deck fully covered, but the last question came back through the
    #     Telegram/agent lane -> is_structured False -> graded on RAW COUNT, and a
    #     complete ~11-question canonical deck is only ~19 raw blocks, i.e. below
    #     the 25 floor -> HARD FAIL on a complete interview.
    #   • rich conversational interview (25-35 real questions), but the last
    #     stamp happened to be 'interview-web' -> is_structured True -> graded on
    #     DECK COVERAGE, which a conversational transcript does not match id-for-
    #     id -> HARD FAIL on a complete interview.
    #
    # The fix grades on EITHER SATISFIED STANDARD: an interview passes check #1
    # if the canonical deck is fully covered with substance OR the raw-count
    # standard is met. It hard-fails only when NEITHER is satisfied. Both
    # standards keep their full strength — coverage still demands every REQUIRED
    # canonical question answered with real substance (check_structured_coverage
    # does the judging, not a flag), and the conversational chain below is
    # untouched, including the ABSOLUTE >36 ceiling and the 25-35 band.
    conversational_satisfied = 24 <= count <= 36

    if coverage_complete:
        channel_note = (
            "interviewProgress.lastQuestionAskedBy=='interview-web' (structured web deck)"
            if is_structured
            else f"lastQuestionAskedBy=='{(state or {}).get('interviewProgress', {}).get('lastQuestionAskedBy', '?')}' "
                 f"(MIXED CHANNEL: the last answer came back outside the web deck, but the "
                 f"canonical deck is fully covered, so the coverage standard is the one this "
                 f"interview satisfies)"
        )
        warnings.append(
            f"[structured-coverage GRANTED] {channel_note}. "
            f"{len(sc.get('answeredIds', []))}/{sc.get('total', 0)} canonical questions "
            f"covered with substance ({sc.get('requiredTotal', 0)} required, all present). "
            f"The 25-35 raw-**Q:**-block standard does not apply to this path — see "
            f"check_structured_coverage(). Raw count was {count}. Jargon, mandatory-field, "
            f"and no-fabrication checks STILL applied in full."
        )
    elif is_structured and conversational_satisfied:
        # Deck incomplete, but this interview satisfies the RAW-COUNT standard.
        # Fall through to the conversational chain below rather than hard-failing
        # on a standard this interview was never really conducted under.
        warnings.append(
            f"[mixed-channel] lastQuestionAskedBy=='interview-web' but the canonical deck is "
            f"NOT fully covered ("
            + "; ".join(
                p for p in (
                    (f"never answered: {', '.join(sc.get('missingRequiredIds', []))}"
                     if sc.get("missingRequiredIds") else ""),
                    (f"answered but too shallow/generic: {', '.join(sc.get('shallowRequiredIds', []))}"
                     if sc.get("shallowRequiredIds") else ""),
                ) if p
            )
            + f"). Grading on the raw-count standard instead, which this interview DOES satisfy "
            f"({count} questions). Both standards were evaluated; neither was waived."
        )
        # The raw-count standard's own borderline rule still applies here — this
        # branch grades BY that standard, so it inherits its soft fail too.
        if count == 24 or count == 36:
            soft_failures.append(
                f"Question count {count} is borderline (target 25-35). Human review required."
            )
    elif is_structured:
        # Neither standard satisfied — the original structured hard fail, intact.
        missing_named = sc.get("missingRequiredIds", [])
        shallow_named = sc.get("shallowRequiredIds", [])
        parts = []
        if missing_named:
            parts.append(f"never answered: {', '.join(missing_named)}")
        if shallow_named:
            parts.append(f"answered but too shallow/generic: {', '.join(shallow_named)}")
        hard_failures.append(
            "[structured-coverage] Structured web-deck interview (askedBy=interview-web) "
            "does not cover every REQUIRED canonical question with real substance"
            + (f" — {'; '.join(parts)}" if parts else "")
            + f". Raw count ({count}) does not satisfy the raw-count standard either, so "
            f"NEITHER standard is met; coverage of the "
            f"{sc.get('total', '?')}-question canonical deck is the standard for this path."
        )
    # The over-long ceiling is ABSOLUTE — no exemption lifts it. (Conversational
    # path only; a fully-covered structured interview is granted above.)
    elif count > 36:
        hard_failures.append(
            f"Question count {count} is outside the acceptable range (25-35). "
            f"Too many — interview may have drifted long."
        )
    elif legacy_granted:
        # Count floor lifted for this verified pre-standard interview. We still record
        # the count, and we still surface an unusually tiny interview as a soft note.
        if count < LEGACY_MIN_QUESTIONS:
            # Should be unreachable (substance floor would have failed) — defensive.
            soft_failures.append(
                f"Legacy interview question count {count} is unexpectedly low; review."
            )
    elif edit_mode_granted:
        # Count floor lifted for this verified standard-first edit-mode interview.
        # We still record the count, and still surface an unusually tiny interview
        # as a soft note.
        if count < EDIT_MODE_MIN_QUESTIONS:
            # Should be unreachable (substance floor would have failed) — defensive.
            soft_failures.append(
                f"Edit-mode interview question count {count} is unexpectedly low; review."
            )
    elif count < 24:
        if tailored:
            # Tailored/founder-self-build: downgrade low count to NEEDS-REVIEW (exit 2).
            soft_failures.append(
                f"Question count {count} is below the standard range (25-35) but the "
                f"build-state records a tailored/founder-self-build interview "
                f"({tailored_basis}); treating as NEEDS-REVIEW, not a hard fail. "
                f"Verify the short interview is genuinely complete before building."
            )
        else:
            # Ordinary client, no recorded signal → strictness preserved: HARD FAIL.
            hard_failures.append(
                f"Question count {count} is outside the acceptable range (25-35). "
                f"Too few — interview may be too shallow / generic."
            )
    elif count == 24 or count == 36:
        soft_failures.append(
            f"Question count {count} is borderline (target 25-35). Human review required."
        )
    if count_result.get("disagreeWarning"):
        # HARD FAIL (2026-07-30 fix, a client Mac mini box incident): a
        # lastQuestionNumber that disagrees with the transcript's real Q-block
        # count by more than 3 questions used to be a WARNING ONLY — the count
        # check above still used the (correct) transcript count, so a genuinely
        # complete interview could pass check #1 even while the disagreement
        # itself, which is direct evidence the progress-counter write path is
        # broken, sat in `warnings[]` where nothing reads it before marking
        # complete. In the incident this covers, the transcript held 19
        # questions while state.interviewProgress.lastQuestionNumber was frozen
        # at 11 (a gap of 8) — the interview was ALSO short on count and
        # mandatory fields, but the disagreement itself must independently
        # refuse: "a completion claim that disagrees with the transcript by 8
        # questions should refuse, not warn." A stale counter is evidence the
        # write pipeline lost data even when unrelated checks would pass.
        hard_failures.append(count_result["disagreeWarning"])

    # Jargon check
    if jargon_hits:
        hard_failures.append(
            f"{len(jargon_hits)} forbidden jargon hit(s) in AI-authored transcript text: "
            + ", ".join(f"'{h['term']}' at line {h['line']}" for h in jargon_hits)
        )

    # Fields check
    missing_fields = field_result.get("missing", [])
    if missing_fields:
        hard_failures.append(
            f"Missing mandatory fields: {', '.join(missing_fields)}"
        )

    # Box-plumbing fields (D3): WARNING, never a hard fail. ownerChat/agentName
    # are not interview answers — the owner is never asked for them and the web
    # lane has no value to record — so their absence says nothing about whether
    # THIS interview is complete. It is still surfaced by name so a genuinely
    # unconfigured box gets operator follow-up instead of silence.
    plumbing_missing = field_result.get("plumbingMissing", [])
    if plumbing_missing:
        warnings.append(
            "[plumbing] Box plumbing not populated in build-state: "
            + ", ".join(plumbing_missing)
            + ". These are NOT interview answers and do not block completion; "
            "configure them on the box (ownerChat is the owner's Telegram chat "
            "id, agentName the box's agent) so owner-facing sends and the "
            "build-kick can address the right recipient."
        )

    # Nudge wiring check (2026-07-30: WARNING, not a HARD FAIL — see the
    # check_nudges_wired() docstring and the EXIT CODES note at the top of this
    # file. Unlike checks 1/2/3/5/6/7, this says nothing about whether THIS
    # transcript/decision set is legitimate — it is box plumbing for nudging an
    # owner who has ALREADY finished the interview by the time this gate runs.
    # Still fail-closed at the detection level: a genuine wiring gap is still
    # named here and surfaced in nudgesWired/nudgeIssues for operational
    # follow-up (ensure-pipeline-crons.sh backfill / fleet sweep) — it just no
    # longer blocks recognizing a substantively-complete interview.)
    if not nudge_result["wired"]:
        warnings.append(
            "[nudge-cadence] Nudge cadence not fully wired: " + "; ".join(nudge_result["issues"])
        )

    # Check #5: No-fabrication (v12.3.4)
    fabrication_violations = []
    if fabrication_result and not fabrication_result.get("skipped"):
        fabrication_violations = fabrication_result.get("violations", [])
        if fabrication_violations:
            hard_failures.append(
                f"[unconfirmed-context-as-answer] {len(fabrication_violations)} answer(s) "
                f"contain verbatim context snippets without a 'confirmed-from-context:' "
                f"provenance note. These answers must originate from a live client turn. "
                f"Themes affected: {', '.join(v['theme_id'] for v in fabrication_violations)}"
            )
        if fabrication_result.get("note"):
            warnings.append(f"[check-5] {fabrication_result['note']}")
    elif fabrication_result and fabrication_result.get("skipped"):
        warnings.append(f"[check-5 skipped] {fabrication_result.get('note','context map absent')}")

    # Check #6: Decline-provenance gate (PRD P0-2 / P1-1). A department opt-out the
    # build enforcer would silently drop (bare string 'no' without ownerDeclineConfirmed,
    # an object 'no' missing provenance, or a declinedDepartments[] without the gate) is
    # a HARD FAIL here, pre-build, so an unhonored owner decline never over-builds the
    # workforce invisibly.
    decline_violations = check_decline_provenance(state)
    if decline_violations:
        hard_failures.append(
            f"[unprovenanced-decline] {len(decline_violations)} department opt-out(s) "
            f"lack the provenance the build enforcer requires and would be silently "
            f"discarded (department force-added back -> over-build): "
            + "; ".join(decline_violations)
        )

    # Check #7: No-web-only-store (WG-10c). The web/DB mirror must be a SUBSET/derivative
    # of the canonical files — it may never hold a department decision or interview answer
    # the files do not, nor contradict a decision value the files own. A store that adds
    # authority is a HARD FAIL, so the files stay the sole source of truth. Skips (warning
    # only) when no mirror store was supplied — a box with no dashboard yet has nothing to
    # verify.
    web_store_violations = []
    if web_store_result and not web_store_result.get("skipped"):
        web_store_violations = web_store_result.get("violations", [])
        if web_store_violations:
            hard_failures.append(
                f"[web-only-store] {len(web_store_violations)} record(s) exist only in "
                f"(or contradict) the canonical files via the web/DB mirror — the store is "
                f"acting as a source of authority instead of a downstream mirror: "
                + "; ".join(f"{v['kind']}:{v['key']}" for v in web_store_violations)
            )
        if web_store_result.get("note"):
            warnings.append(f"[check-7] {web_store_result['note']}")
    elif web_store_result and web_store_result.get("skipped"):
        warnings.append(f"[check-7 skipped] {web_store_result.get('note','no mirror store supplied')}")

    # Determine verdict
    if hard_failures:
        verdict = "FAIL"
        exit_code = 3
    elif soft_failures:
        verdict = "NEEDS-REVIEW"
        exit_code = 2
    else:
        verdict = "PASS"
        exit_code = 0

    details = {
        "verdict": verdict,
        "questionCount": count,
        "questionCountStateValue": count_result.get("stateCount"),
        "legacyExemption": {
            "claimed": legacy_claimed,
            "granted": legacy_granted,
            "sources": (legacy_result or {}).get("sources", []),
            "meta": (legacy_result or {}).get("meta", {}),
            "substance": legacy_substance or {},
        },
        "editModeExemption": {
            "claimed": edit_mode,
            "granted": edit_mode_granted,
            "basis": (edit_mode_result or {}).get("basis", ""),
            "prebuildStatus": (edit_mode_result or {}).get("prebuildStatus"),
            "substance": (edit_mode_result or {}).get("substance") or {},
        },
        "tailoredExemption": {
            "recorded": tailored,
            "basis": tailored_basis,
            "applied": bool(tailored and not is_structured and count < 24 and count <= 36 and not legacy_granted and not edit_mode_granted),
        },
        "structuredCoverage": {
            "isStructuredWebInterview": is_structured,
            "lastQuestionAskedBy": ((state or {}).get("interviewProgress") or {}).get("lastQuestionAskedBy"),
            "applied": is_structured,
            "result": structured_coverage or {},
        },
        "jargonHits": jargon_hits,
        "missingFields": missing_fields,
        "checkedFields": field_result.get("checked", []),
        "nudgesWired": nudge_result["wired"],
        "nudgeIssues": nudge_result.get("issues", []),
        "fabricationViolations": fabrication_violations,
        "declineProvenanceViolations": decline_violations,
        # Check #7 (WG-10c): no-web-only-store. Machine-readable summary; a non-empty
        # violations list is a HARD FAIL above.
        "webStoreCheck": {
            "skipped": bool(web_store_result.get("skipped")) if web_store_result else True,
            "violations": web_store_violations,
            "note": (web_store_result or {}).get("note", ""),
        },
        # Issue #3: decisionCoverage verdict so the run-full-install interview gate
        # surfaces un-honorable declines (which the build enforcer would silently
        # drop -> over-build) alongside the other checks. A non-empty list is a
        # HARD FAIL above; this field is the machine-readable summary.
        "decisionCoverage": {
            "clean": not decline_violations,
            "declineProvenanceViolationCount": len(decline_violations),
            "rejectedDeclines": (
                _shared_decline_rejections(state) if _shared_decline_rejections and state else []
            ),
        },
        "hardFailures": hard_failures,
        "softFailures": soft_failures,
        "warnings": warnings,
        "ranAt": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rubricVerdict": (
            (
                f"PASS: {count} questions"
                + (" [legacy/pre-standard exemption GRANTED]" if legacy_granted else "")
                + (" [edit-mode exemption GRANTED]" if edit_mode_granted else "")
                + (" [structured-web coverage standard applied]" if is_structured else "")
                + ", 0 jargon hits, all fields present"
                + (
                    ", nudges wired" if nudge_result["wired"]
                    else " [nudge cadence NOT wired — see warnings, not blocking]"
                )
            )
            if verdict == "PASS" else
            f"{verdict}: " + "; ".join(hard_failures + soft_failures)
        ),
    }
    return verdict, exit_code, details


# ── State writer (--write-state) ──────────────────────────────────────────────

def write_state_qc(state_path: Path, details: dict) -> None:
    """Atomically write interviewQc verdict into the build state file."""
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[ERROR] Cannot read state file for --write-state: {exc}", file=sys.stderr)
        sys.exit(1)

    verdict_str = details["verdict"].lower()
    qc_status_map = {
        "pass": "pass",
        "needs-review": "needs-review",
        "fail": "fail",
    }

    _legacy = details.get("legacyExemption", {})
    _em = details.get("editModeExemption", {})
    _sc = details.get("structuredCoverage", {})
    _sc_result = _sc.get("result", {}) or {}
    state["interviewQc"] = {
        "status": qc_status_map.get(verdict_str, "fail"),
        "questionCount": details["questionCount"],
        "legacyExemption": {
            "claimed": bool(_legacy.get("claimed")),
            "granted": bool(_legacy.get("granted")),
            "sources": _legacy.get("sources", []),
        },
        "editModeExemption": {
            "claimed": bool(_em.get("claimed")),
            "granted": bool(_em.get("granted")),
            "basis": _em.get("basis", ""),
        },
        "structuredCoverage": {
            "applied": bool(_sc.get("applied")),
            "total": _sc_result.get("total"),
            "answered": len(_sc_result.get("answeredIds", [])),
            "complete": bool(_sc_result.get("complete")),
        },
        "jargonHits": [
            {"term": h["term"], "line": h["line"]}
            for h in details["jargonHits"]
        ],
        "missingFields": details["missingFields"],
        "nudgesWired": details["nudgesWired"],
        "ranAt": details["ranAt"],
        "rubricVerdict": details.get("rubricVerdict"),
        # "reasons" (2026-07-30 fix): blackceo-command-center's
        # extractQcReasons() (src/lib/interview/... POST /api/interview/complete
        # route) looks for one of reasons/failures/issues/findings/errors/notes
        # on interviewQc to surface WHY a completion was refused — none of
        # those keys were ever written here, so a refused/failed completion
        # showed the owner/operator an empty reasons list even though
        # hardFailures/softFailures were fully populated in-process. Persist
        # them under the key the web route already reads.
        "reasons": list(details.get("hardFailures", [])) + list(details.get("softFailures", [])),
    }

    tmp = Path(str(state_path) + f".tmp.{os.getpid()}")
    try:
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp.replace(state_path)
        print(f"[INFO] Wrote interviewQc to {state_path}", file=sys.stderr)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        print(f"[ERROR] Failed to write state: {exc}", file=sys.stderr)
        sys.exit(1)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=(
            "PRD-2.15 + PRD-2.16 interview completion QC gate. "
            "Checks question count, jargon, mandatory fields, nudge wiring, "
            "and no-fabrication (check #5, v12.3.4)."
        )
    )
    parser.add_argument(
        "--transcript",
        help=(
            "Path to workforce-interview-answers.md, its encrypted .enc sibling "
            "(U048), or the .enc file itself. Defaults to auto-discovery across "
            "company-discovery + flat workspace locations, plaintext or encrypted."
        ),
    )
    parser.add_argument(
        "--state",
        help="Path to .workforce-build-state.json. Defaults to workspace path.",
    )
    parser.add_argument(
        "--jargon-list",
        help="Path to forbidden-jargon.json. Defaults to skill directory.",
    )
    parser.add_argument(
        "--instructions",
        help="Path to INSTRUCTIONS.md (used for behavioral contract assertion).",
    )
    parser.add_argument(
        "--branding-questions",
        help="Path to branding-questions.json. Defaults to skill interview/ directory.",
    )
    parser.add_argument(
        "--repo-root",
        help="Repo root for checking nudge wiring. Defaults to auto-detected.",
    )
    parser.add_argument(
        "--format",
        choices=["json", "human"],
        default="human",
        help="Output format.",
    )
    parser.add_argument(
        "--write-state",
        action="store_true",
        help="Write the interviewQc verdict back into the state file (atomic).",
    )
    parser.add_argument(
        "--context-map",
        help=(
            "Path to interview-context-map.json (check #5 no-fabrication). "
            "Defaults to [ZHC]/[slug]/interview-context-map.json auto-detected from state. "
            "Pass --no-context-map to skip check #5 explicitly."
        ),
        default=None,
    )
    parser.add_argument(
        "--no-context-map",
        action="store_true",
        help="Skip check #5 (no-fabrication) even if a context map is present.",
    )
    parser.add_argument(
        "--legacy-interview",
        action="store_true",
        help=(
            "Mark this as a VERIFIED pre-standard / legacy interview (predates the "
            "25-35 question standard). Lifts the count floor (check #1) ONLY, and ONLY "
            "if the interview passes the anti-fabrication substance floor. Jargon, "
            "mandatory-field, and no-fabrication checks still apply. The same exemption "
            "is also triggered by state.legacyInterview.preStandard==true or a "
            "'<!-- LEGACY-INTERVIEW: pre-standard -->' marker in the transcript."
        ),
    )
    parser.add_argument(
        "--mirror-store",
        help=(
            "Path to a JSON mirror export of the web/DB store (check #7 no-web-only-store): "
            '{"decisions": {dept: token}, "answers": {field: value}}. When supplied, the '
            "store must be a SUBSET/derivative of the canonical files (no decision or answer "
            "that lives only in the store; no store value that contradicts the files)."
        ),
        default=None,
    )
    parser.add_argument(
        "--mirror-db",
        help=(
            "Path to a sqlite mission-control.db mirror (check #7). Reads department_decisions/"
            "decisions and interview_answers/answers tables read-only; a missing table means "
            "that datum is not mirrored yet (empty store)."
        ),
        default=None,
    )
    args = parser.parse_args()

    # Resolve paths
    script_dir = Path(__file__).resolve().parent
    skill_dir = script_dir.parent

    state_path = Path(args.state) if args.state else _default_state_path()

    jargon_path = (
        Path(args.jargon_list)
        if args.jargon_list
        else skill_dir / "interview" / "forbidden-jargon.json"
    )
    branding_path = (
        Path(args.branding_questions)
        if args.branding_questions
        else skill_dir / "interview" / "branding-questions.json"
    )

    # Repo root: go up from skill_dir
    if args.repo_root:
        repo_root = Path(args.repo_root)
    else:
        repo_root = skill_dir.parent  # skill_dir is 23-ai-workforce-blueprint/

    # Load inputs. State is loaded FIRST so transcript resolution can consult
    # state.interviewProgress.answersFilePath (U048: transcript may be
    # plaintext or an encrypted .enc envelope; resolve_and_load_transcript
    # tries both via the shared _interview_transcript reader).
    state = load_json(state_path, ".workforce-build-state.json")
    transcript = resolve_and_load_transcript(args.transcript, state, _resolve_openclaw_root())
    jargon_data = load_json(jargon_path, "forbidden-jargon.json")
    jargon_terms = jargon_data.get("terms", [])

    # Resolve context map path for check #5
    context_map_path = None
    if not args.no_context_map:
        if args.context_map:
            context_map_path = Path(args.context_map)
        else:
            # Auto-detect: try to locate [ZHC]/[slug]/interview-context-map.json
            # by reading companySlug from state
            try:
                company_slug = state.get("companySlug") or state.get("companyName")
                if company_slug:
                    import re as _re
                    slug = _re.sub(r"[^a-z0-9]+", "-", company_slug.lower()).strip("-")
                    # Try canonical ZHC roots
                    for zhc_base in [
                        Path("/data/openclaw-master-files/zero-human-company"),
                        Path(os.environ.get("HOME", "~")).expanduser()
                        / "Downloads" / "openclaw-master-files" / "zero-human-company",
                    ]:
                        candidate = zhc_base / slug / "interview-context-map.json"
                        if candidate.exists():
                            context_map_path = candidate
                            break
            except Exception:
                pass

    # Run checks
    count_result = count_questions(transcript, state)
    jargon_hits = scan_jargon(transcript, jargon_terms)
    field_result = check_mandatory_fields(state, branding_path, transcript)
    nudge_result = check_nudges_wired(repo_root)
    fabrication_result = check_no_fabrication(transcript, context_map_path, state)
    # Structured-web coverage standard (2026-07-30 fix): computed unconditionally
    # (cheap — same transcript, same branding_path already loaded above); only
    # USED by build_verdict() when is_structured_web_interview(state) is True.
    structured_coverage_result = check_structured_coverage(transcript, branding_path)

    # Legacy / pre-standard exemption (v12.4.0): detect claim, then verify substance.
    legacy_result = is_legacy_interview(transcript, state, args.legacy_interview)
    legacy_substance = (
        legacy_substance_ok(transcript, count_result)
        if legacy_result["legacy"]
        else None
    )

    # Edit-mode exemption (standard-first, PHASE 7): detect via build-state, then
    # verify substance. Never applies to a legacy box (buildType absent).
    edit_mode_detect = is_edit_mode_interview(state)
    edit_mode_result = None
    if edit_mode_detect.get("editMode"):
        edit_mode_result = dict(edit_mode_detect)
        edit_mode_result["substance"] = edit_mode_substance_ok(transcript, count_result)

    # Check #7 (WG-10c): no-web-only-store. Only runs when a mirror store is supplied;
    # otherwise it skips (a box with no dashboard mirror yet has nothing to verify).
    web_store_result = None
    if _check_no_web_store is not None and (args.mirror_store or args.mirror_db):
        mirror_json = None
        if args.mirror_store:
            mirror_json = load_json(Path(args.mirror_store), "mirror-store JSON")
        web_store_result = _check_no_web_store(
            state, transcript,
            mirror=mirror_json,
            mirror_db=Path(args.mirror_db) if args.mirror_db else None,
        )

    # Assemble verdict
    verdict, exit_code, details = build_verdict(
        count_result, jargon_hits, field_result, nudge_result, fabrication_result,
        legacy_result, legacy_substance, state=state,
        web_store_result=web_store_result,
        structured_coverage=structured_coverage_result,
        edit_mode_result=edit_mode_result,
    )

    # Output
    if args.format == "json":
        print(json.dumps(details, indent=2))
    else:
        # Human-readable
        status_icon = {"PASS": "[PASS]", "NEEDS-REVIEW": "[NEEDS-REVIEW]", "FAIL": "[FAIL]"}.get(verdict, "[FAIL]")
        print(f"\n{status_icon} Interview QC Gate — PRD-2.15 + PRD-2.16 (v12.3.4)")
        _legacy = details.get("legacyExemption", {})
        _legacy_tag = ""
        if _legacy.get("granted"):
            _legacy_tag = " [LEGACY/pre-standard count floor EXEMPT]"
        elif _legacy.get("claimed"):
            _legacy_tag = " [LEGACY claimed — substance check FAILED]"
        print(f"  Question count : {details['questionCount']}"
              + (f" (state: {details['questionCountStateValue']})" if details['questionCountStateValue'] else "")
              + _legacy_tag)
        _em = details.get("editModeExemption", {})
        if _em.get("granted"):
            print(f"  Edit-mode      : GRANTED (standard-first edit-mode interview; count floor exempt — {_em.get('basis')})")
        elif _em.get("claimed"):
            print("  Edit-mode      : CLAIMED — substance check FAILED (HARD FAIL)")
        _sc = details.get("structuredCoverage", {})
        if _sc.get("isStructuredWebInterview"):
            _scr = _sc.get("result", {}) or {}
            print(f"  Structured cov.: {len(_scr.get('answeredIds', []))}/{_scr.get('total', 0)} canonical "
                  f"questions covered with substance ({_scr.get('requiredTotal', 0)} required) "
                  f"[askedBy=interview-web — 25-35 raw count standard N/A]")
        print(f"  Jargon hits    : {len(details['jargonHits'])}")
        print(f"  Missing fields : {len(details['missingFields'])}")
        print(f"  Nudges wired   : {'yes' if details['nudgesWired'] else 'NO'}")
        fab_violations = details.get("fabricationViolations", [])
        print(f"  No-fabrication : {'PASS' if not fab_violations else f'FAIL ({len(fab_violations)} violation(s))'}")
        decline_viol = details.get("declineProvenanceViolations", [])
        print(f"  Decline prov.  : {'PASS' if not decline_viol else f'FAIL ({len(decline_viol)} unprovenanced decline(s))'}")
        _ws = details.get("webStoreCheck", {})
        _ws_viol = _ws.get("violations", [])
        print(f"  No-web-store   : {'SKIP' if _ws.get('skipped') else ('PASS' if not _ws_viol else f'FAIL ({len(_ws_viol)} web-only/override)')}")

        if details["warnings"]:
            print("\n  WARNINGS:")
            for w in details["warnings"]:
                print(f"    ! {w}")

        if details["hardFailures"] or details["softFailures"]:
            print("\n  FAILURES:")
            for f in details["hardFailures"]:
                print(f"    [HARD] {f}")
            for f in details["softFailures"]:
                print(f"    [SOFT] {f}")

        if details["jargonHits"]:
            print("\n  JARGON HITS (AI-authored lines only):")
            for h in details["jargonHits"]:
                print(f"    Line {h['line']}: term='{h['term']}' | text: {h.get('text','')[:80]}")

        if details["missingFields"]:
            print(f"\n  MISSING FIELDS: {', '.join(details['missingFields'])}")

        if not details["nudgesWired"] and details["nudgeIssues"]:
            print("\n  NUDGE ISSUES:")
            for iss in details["nudgeIssues"]:
                print(f"    - {iss}")

        if fab_violations:
            print("\n  NO-FABRICATION VIOLATIONS (unconfirmed-context-as-answer):")
            for v in fab_violations:
                print(f"    theme={v['theme_id']} source={v['source']}")
                print(f"    snippet: {v['snippet_preview'][:80]}")
                print(f"    fix: add 'confirmed-from-context: {v['source']}' to this answer block")

        print(f"\n  Ran at: {details['ranAt']}")
        print(f"  Summary: {details['rubricVerdict']}")
        print()

    # Optionally write back to state
    if args.write_state:
        write_state_qc(state_path, details)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
