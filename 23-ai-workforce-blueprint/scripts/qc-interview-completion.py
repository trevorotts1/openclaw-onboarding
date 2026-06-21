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
  2. Zero forbidden-jargon hits in AI-authored text (loads from forbidden-jargon.json).
  3. Every mandatory data field populated (branding required:true + structural fields).
  4. Nudge cadence wired: interview-nudge-cron.sh exists + install.sh registers it.
  5. NO-FABRICATION (v12.3.4): if interview-context-map.json exists, every answer whose
     text is a verbatim copy of a context snippet WITHOUT a 'confirmed-from-context:'
     provenance note is flagged as HARD FAIL (exit 3, reason 'unconfirmed-context-as-answer').
     Answers that DO carry the provenance note PASS check #5.

EXIT CODES (mirror qc-completeness.sh):
  0 — PASS (all five checks pass)
  1 — Error (bad input, unreadable state, missing required file)
  2 — SOFT FAIL / needs human review (borderline count: 24 or 36)
  3 — HARD FAIL (jargon hit, missing mandatory field, count way off, nudges not wired,
                 or unconfirmed-context-as-answer)

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
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"[ERROR] Transcript not found: {path}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"[ERROR] Cannot read transcript: {exc}", file=sys.stderr)
        sys.exit(1)


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


# ── Check 3: Mandatory fields ─────────────────────────────────────────────────

def check_mandatory_fields(state: dict, branding_questions_path: Path) -> dict:
    """
    Load branding required:true fields from branding-questions.json (single source).
    Also check structural build-state requireds.
    Returns {"missing": [...], "checked": [...]}
    """
    # Load branding requireds dynamically
    try:
        bq = load_json(branding_questions_path, "branding-questions.json")
        branding_required = [
            q["id"]
            for q in bq.get("questions", [])
            if q.get("required", False)
        ]
    except SystemExit:
        # branding-questions.json must be readable — if not, hard fail
        raise

    # Structural build-state requireds
    structural_required = ["companyName", "industry", "ownerChat", "agentName"]

    # Check branding fields — they may be in the state or in the transcript (we check state)
    # The state doesn't directly hold branding answers in structured fields by default,
    # but as per SKILL.md the interview must populate identifiable keys.
    # We look for them under a "brandingAnswers" map or top-level or under "interview" sub-object.
    missing = []

    def field_present(key: str) -> bool:
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

    # Structural
    if not state.get("companyName") and not state.get("company_name"):
        missing.append("companyName")
    if not state.get("industry"):
        missing.append("industry")
    if not state.get("ownerChat") and not state.get("owner_chat"):
        missing.append("ownerChat")
    if not state.get("agentName") and not state.get("agent_name"):
        missing.append("agentName")

    # At least one locked department
    departments = state.get("departments", [])
    if isinstance(departments, list):
        locked = [d for d in departments if d.get("status") in ("done", "building", "pending")]
        if not locked:
            missing.append("departments[at-least-one]")

    return {
        "missing": list(dict.fromkeys(missing)),  # dedup, preserve order
        "checked": branding_required + structural_required + ["departments[at-least-one]"],
    }


# ── Check 4: Nudge cadence wired ─────────────────────────────────────────────

def check_nudges_wired(repo_root: Path) -> dict:
    """
    Static "is it wired" check — does not require a live cron or gateway.
      (a) interview-nudge-cron.sh exists and is executable
      (b) install.sh registers it (grep for the cron registration)
      (c) nudge-incomplete-interviews.py has NUDGE_CONFIG with 24/72/168h
    """
    issues = []

    nudge_cron = repo_root / "23-ai-workforce-blueprint" / "scripts" / "interview-nudge-cron.sh"
    if not nudge_cron.exists():
        issues.append(f"interview-nudge-cron.sh not found at {nudge_cron}")
    elif not os.access(nudge_cron, os.X_OK):
        issues.append(f"interview-nudge-cron.sh exists but is not executable: {nudge_cron}")

    install_sh = repo_root / "install.sh"
    if install_sh.exists():
        content = install_sh.read_text(encoding="utf-8", errors="replace")
        if "interview-nudge-cron" not in content:
            issues.append("install.sh does not register interview-nudge-cron.sh (grep for 'interview-nudge-cron' found nothing)")
    else:
        issues.append(f"install.sh not found at {install_sh}")

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

def check_no_fabrication(transcript: str, context_map_path: Path | None) -> dict:
    """
    Check #5 (v12.3.4): NO-FABRICATION guardrail.

    If interview-context-map.json exists and a known/partial context snippet appears
    verbatim in workforce-interview-answers.md WITHOUT a 'confirmed-from-context:'
    provenance note in the same answer block, that is an UNCONFIRMED-CONTEXT-AS-ANSWER
    violation → HARD FAIL (exit 3).

    An answer block that DOES contain 'confirmed-from-context: <source>' PASSES — the
    client confirmed it live and the agent tagged it correctly.

    If context-map is absent → check skips (returns pass). This is intentional:
    on a fresh install or when context-ingest was not run, there is nothing to verify.

    Reads only. Never writes.
    """
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
    if isinstance(planned, int) and 0 < planned < 24 and complete:
        return (True, f"questionCountPlanned={planned} with interviewComplete=true")
    return (False, "")


def build_verdict(
    count_result: dict,
    jargon_hits: list,
    field_result: dict,
    nudge_result: dict,
    fabrication_result: dict | None = None,
    legacy_result: dict | None = None,
    legacy_substance: dict | None = None,
    state: dict | None = None,
) -> tuple:
    """
    Returns (verdict_str, exit_code, details_dict).
    PASS=0, SOFT FAIL=2, HARD FAIL=3.
    Checks: 1=count, 2=jargon, 3=fields, 4=nudges, 5=no-fabrication (v12.3.4).

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

    Strictness is preserved for everyone else: an ORDINARY client with a short
    interview and NO recorded legacy/tailored signal STILL hard-fails (exit 3), and an
    over-long interview (count > 36) STILL hard-fails regardless of any exemption.
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

    # (B) Tailored / founder-self-build / gap-only (v13.2.0): a build-state that
    # explicitly records a tailored interview downgrades a LOW count to NEEDS-REVIEW.
    tailored, tailored_basis = is_tailored_short_interview(state)

    # The over-long ceiling is ABSOLUTE — no exemption lifts it.
    if count > 36:
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
        warnings.append(count_result["disagreeWarning"])

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

    # Nudge wiring check
    if not nudge_result["wired"]:
        hard_failures.append(
            "Nudge cadence not fully wired: " + "; ".join(nudge_result["issues"])
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
        "tailoredExemption": {
            "recorded": tailored,
            "basis": tailored_basis,
            "applied": bool(tailored and count < 24 and count <= 36 and not legacy_granted),
        },
        "jargonHits": jargon_hits,
        "missingFields": missing_fields,
        "checkedFields": field_result.get("checked", []),
        "nudgesWired": nudge_result["wired"],
        "nudgeIssues": nudge_result.get("issues", []),
        "fabricationViolations": fabrication_violations,
        "hardFailures": hard_failures,
        "softFailures": soft_failures,
        "warnings": warnings,
        "ranAt": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rubricVerdict": (
            (
                f"PASS: {count} questions"
                + (" [legacy/pre-standard exemption GRANTED]" if legacy_granted else "")
                + ", 0 jargon hits, all fields present, nudges wired"
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
    state["interviewQc"] = {
        "status": qc_status_map.get(verdict_str, "fail"),
        "questionCount": details["questionCount"],
        "legacyExemption": {
            "claimed": bool(_legacy.get("claimed")),
            "granted": bool(_legacy.get("granted")),
            "sources": _legacy.get("sources", []),
        },
        "jargonHits": [
            {"term": h["term"], "line": h["line"]}
            for h in details["jargonHits"]
        ],
        "missingFields": details["missingFields"],
        "nudgesWired": details["nudgesWired"],
        "ranAt": details["ranAt"],
        "rubricVerdict": details.get("rubricVerdict"),
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
        help="Path to workforce-interview-answers.md. Defaults to workspace path.",
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
    args = parser.parse_args()

    # Resolve paths
    script_dir = Path(__file__).resolve().parent
    skill_dir = script_dir.parent

    transcript_path = Path(args.transcript) if args.transcript else _default_transcript_path()
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

    # Load inputs
    state = load_json(state_path, ".workforce-build-state.json")
    transcript = load_transcript(transcript_path)
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
    field_result = check_mandatory_fields(state, branding_path)
    nudge_result = check_nudges_wired(repo_root)
    fabrication_result = check_no_fabrication(transcript, context_map_path)

    # Legacy / pre-standard exemption (v12.4.0): detect claim, then verify substance.
    legacy_result = is_legacy_interview(transcript, state, args.legacy_interview)
    legacy_substance = (
        legacy_substance_ok(transcript, count_result)
        if legacy_result["legacy"]
        else None
    )

    # Assemble verdict
    verdict, exit_code, details = build_verdict(
        count_result, jargon_hits, field_result, nudge_result, fabrication_result,
        legacy_result, legacy_substance, state=state,
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
        print(f"  Jargon hits    : {len(details['jargonHits'])}")
        print(f"  Missing fields : {len(details['missingFields'])}")
        print(f"  Nudges wired   : {'yes' if details['nudgesWired'] else 'NO'}")
        fab_violations = details.get("fabricationViolations", [])
        print(f"  No-fabrication : {'PASS' if not fab_violations else f'FAIL ({len(fab_violations)} violation(s))'}")

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
