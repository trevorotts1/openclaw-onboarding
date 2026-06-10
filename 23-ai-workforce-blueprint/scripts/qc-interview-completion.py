#!/usr/bin/env python3
"""
qc-interview-completion.py — PRD-2.15: Interview Completion QC Gate.

Checks that a completed interview transcript meets quality standards before
the build pipeline is allowed to proceed. Four checks:

  1. Question count: 25-35 answered questions in the transcript.
  2. Zero forbidden-jargon hits in AI-authored text (loads from forbidden-jargon.json).
  3. Every mandatory data field populated (branding required:true + structural fields).
  4. Nudge cadence wired: interview-nudge-cron.sh exists + install.sh registers it.

EXIT CODES (mirror qc-completeness.sh):
  0 — PASS (all four checks pass)
  1 — Error (bad input, unreadable state, missing required file)
  2 — SOFT FAIL / needs human review (borderline count: 24 or 36)
  3 — HARD FAIL (jargon hit, missing mandatory field, count way off, nudges not wired)

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

PRD-2.15 / v11.11.0
"""

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


# ── Verdict assembly ──────────────────────────────────────────────────────────

def build_verdict(
    count_result: dict,
    jargon_hits: list,
    field_result: dict,
    nudge_result: dict,
) -> tuple:
    """
    Returns (verdict_str, exit_code, details_dict).
    PASS=0, SOFT FAIL=2, HARD FAIL=3.
    """
    hard_failures = []
    soft_failures = []
    warnings = []

    # Count check
    count = count_result["transcriptCount"]
    if count < 24 or count > 36:
        hard_failures.append(
            f"Question count {count} is outside the acceptable range (25-35). "
            f"{'Too few — interview may be too shallow / generic.' if count < 24 else 'Too many — interview may have drifted long.'}"
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
        "jargonHits": jargon_hits,
        "missingFields": missing_fields,
        "checkedFields": field_result.get("checked", []),
        "nudgesWired": nudge_result["wired"],
        "nudgeIssues": nudge_result.get("issues", []),
        "hardFailures": hard_failures,
        "softFailures": soft_failures,
        "warnings": warnings,
        "ranAt": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rubricVerdict": (
            f"PASS: {count} questions, 0 jargon hits, all fields present, nudges wired"
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

    state["interviewQc"] = {
        "status": qc_status_map.get(verdict_str, "fail"),
        "questionCount": details["questionCount"],
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
        description="PRD-2.15 interview completion QC gate. Checks question count, "
                    "jargon, mandatory fields, and nudge wiring."
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

    # Run checks
    count_result = count_questions(transcript, state)
    jargon_hits = scan_jargon(transcript, jargon_terms)
    field_result = check_mandatory_fields(state, branding_path)
    nudge_result = check_nudges_wired(repo_root)

    # Assemble verdict
    verdict, exit_code, details = build_verdict(count_result, jargon_hits, field_result, nudge_result)

    # Output
    if args.format == "json":
        print(json.dumps(details, indent=2))
    else:
        # Human-readable
        status_icon = {"PASS": "[PASS]", "NEEDS-REVIEW": "[NEEDS-REVIEW]", "FAIL": "[FAIL]"}.get(verdict, "[FAIL]")
        print(f"\n{status_icon} Interview QC Gate — PRD-2.15")
        print(f"  Question count : {details['questionCount']}"
              + (f" (state: {details['questionCountStateValue']})" if details['questionCountStateValue'] else ""))
        print(f"  Jargon hits    : {len(details['jargonHits'])}")
        print(f"  Missing fields : {len(details['missingFields'])}")
        print(f"  Nudges wired   : {'yes' if details['nudgesWired'] else 'NO'}")

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

        print(f"\n  Ran at: {details['ranAt']}")
        print(f"  Summary: {details['rubricVerdict']}")
        print()

    # Optionally write back to state
    if args.write_state:
        write_state_qc(state_path, details)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
