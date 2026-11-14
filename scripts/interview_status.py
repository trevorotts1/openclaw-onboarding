#!/usr/bin/env python3
"""One reader for "is the interview complete" (interface contract, 01-BUILD-SPEC.md 2.3).

Every consumer that needs to know where an owner is in the interview asks this
program, or the TypeScript port of the same table (interview-status.ts), so no
two surfaces can disagree about the same file. The states, in the order they are
decided:

  BUILT        completionVerification.status == "verified"
  BUILDING     interviewComplete true and the build has started (confirmationsComplete
               true, or a departments[] entry is pending/building/done)
  COMPLETE     interviewComplete true
  PLACEHOLDER  companyMode "standard-placeholder" and standardPlaceholder.status "active"
  DECLARED     the caller passed --declared (its own declarations table has a row)
  READY        the gate's complete-check passes (<workspace>/company-discovery
               interview-gate-state.json against the question registry)
  IN_PROGRESS  the gate state holds at least one answer, or
               interviewProgress.lastQuestionNumber is above 0
  NOT_STARTED  none of the above
  UNDETERMINED the state file (or a gate fact READY needs) could not be read

UNDETERMINED is never reported as NOT_STARTED: "I could not read it" and "nothing
has happened yet" are different answers, and only one of them closes a prompt.
The COMPLETE / BUILDING / BUILT split is for reports only; no consumer treats
them differently.

Exit codes
  0  a state was computed and printed
  1  UNDETERMINED (unreadable build-state, or the registry the READY rule needs)

Usage
  interview_status.py --state FILE [--declared] [--json]
                      [--gate-state FILE] [--registry FILE]
--gate-state defaults to <dir of --state>/company-discovery/interview-gate-state.json.
--registry defaults to <repo root>/23-ai-workforce-blueprint/interview/questions.v2.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

STATES = (
    "NOT_STARTED", "IN_PROGRESS", "READY", "COMPLETE",
    "BUILDING", "BUILT", "PLACEHOLDER", "DECLARED", "UNDETERMINED",
)
# The four states decided from build-state alone. Everything else needs the gate.
BUILD_STATE_ONLY = ("BUILT", "BUILDING", "COMPLETE", "PLACEHOLDER", "DECLARED")
SHELL_LOCK_STATES = ("COMPLETE", "BUILDING", "BUILT", "PLACEHOLDER", "DECLARED")
BUILDING_DEPARTMENT_STATUSES = ("pending", "building", "done")
GATE_STATE_NAME = "interview-gate-state.json"
REGISTRY_RELATIVE = Path("23-ai-workforce-blueprint") / "interview" / "questions.v2.json"


def _mapping(value) -> dict:
    return value if isinstance(value, dict) else {}


def _count(value) -> int:
    """Mirror the TypeScript port's `count` exactly: bool 0, integers as-is,
    finite floats truncated, strings by their leading integer, anything else 0."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value == value and abs(value) != float("inf") else 0
    text = str(value).strip() if value is not None else ""
    digits = ""
    for index, character in enumerate(text):
        if character in "+-" and index == 0:
            digits += character
        elif character.isdigit():
            digits += character
        else:
            break
    try:
        return int(digits)
    except ValueError:
        return 0


def state_of(build_state, *, declared: bool = False, gate=None, unreadable: bool = False) -> str:
    """Return exactly one of STATES.

    `gate` is {"answers": int, "missingRequired": [question ids]} or None. With
    None the READY rule cannot be evaluated, so a started interview answers
    IN_PROGRESS and an untouched one answers NOT_STARTED. Callers that must tell
    READY from IN_PROGRESS (the CLI does) supply the gate facts.
    """
    if unreadable:
        return "UNDETERMINED"
    build = _mapping(build_state)
    if _mapping(build.get("completionVerification")).get("status") == "verified":
        return "BUILT"
    complete = build.get("interviewComplete") is True or build.get("interview_complete") is True
    if complete:
        departments = build.get("departments")
        started = build.get("confirmationsComplete") is True or (
            isinstance(departments, list)
            and any(_mapping(entry).get("status") in BUILDING_DEPARTMENT_STATUSES for entry in departments)
        )
        return "BUILDING" if started else "COMPLETE"
    if (build.get("companyMode") == "standard-placeholder"
            and _mapping(build.get("standardPlaceholder")).get("status") == "active"):
        return "PLACEHOLDER"
    if declared:
        return "DECLARED"
    facts = _mapping(gate)
    missing = facts.get("missingRequired")
    answers = facts.get("answers")
    if (isinstance(missing, list) and not missing
            and isinstance(answers, (int, float)) and not isinstance(answers, bool)):
        return "READY"
    if _count(facts.get("answers")) > 0 or _count(_mapping(build.get("interviewProgress")).get("lastQuestionNumber")) > 0:
        return "IN_PROGRESS"
    return "NOT_STARTED"


def gate_facts(gate_state_path: Path, registry_path: Path) -> dict:
    """Read the gate's own answers with the gate's own code (no second rule set)."""
    here = Path(__file__).resolve()
    # The gate ships in the blueprint scripts folder next to the registry, not
    # beside this reader; import it from whichever folder actually holds it.
    for directory in (here.parent,
                      registry_path.resolve().parent.parent / "scripts",
                      here.parent.parent / "23-ai-workforce-blueprint" / "scripts"):
        if (directory / "interview_gate.py").is_file() and str(directory) not in sys.path:
            sys.path.insert(0, str(directory))
    import interview_gate

    if gate_state_path.name != interview_gate.STATE_NAME:
        raise ValueError(f"not a gate state file: {gate_state_path.name}")
    if not registry_path.is_file():
        raise FileNotFoundError(f"question registry missing: {registry_path}")
    gate = interview_gate.Gate(registry_path, gate_state_path.parent)
    return {"answers": len(gate.state["answers"]), "missingRequired": gate.missing_required()}


def _emit(state: str, as_json: bool) -> int:
    if as_json:
        print(json.dumps({"status": state}))
    else:
        print(state)
    return 1 if state == "UNDETERMINED" else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="One reader for interview completion.")
    parser.add_argument("--state", required=True, help="path to .workforce-build-state.json")
    parser.add_argument("--gate-state", help="path to interview-gate-state.json")
    parser.add_argument("--registry", help="path to questions.v2.json")
    parser.add_argument("--declared", action="store_true",
                        help="the caller's declarations table holds a row for this company")
    parser.add_argument("--json", action="store_true", help="print {\"status\": STATE}")
    args = parser.parse_args(argv)

    state_path = Path(args.state).expanduser()
    try:
        build_state = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(build_state, dict):
            raise ValueError("build-state is not a JSON object")
    except (OSError, ValueError):
        return _emit("UNDETERMINED", args.json)

    state = state_of(build_state, declared=args.declared)
    if state in BUILD_STATE_ONLY:
        return _emit(state, args.json)

    gate_state_path = Path(args.gate_state).expanduser() if args.gate_state else (
        state_path.parent / "company-discovery" / GATE_STATE_NAME)
    registry_path = Path(args.registry).expanduser() if args.registry else (
        Path(__file__).resolve().parent.parent / REGISTRY_RELATIVE)
    try:
        gate = gate_facts(gate_state_path, registry_path)
    except Exception:  # tooling: the registry or the gate state cannot be read
        return _emit("UNDETERMINED", args.json)
    return _emit(state_of(build_state, declared=args.declared, gate=gate), args.json)


if __name__ == "__main__":
    sys.exit(main())
