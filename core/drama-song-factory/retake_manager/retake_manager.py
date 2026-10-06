#!/usr/bin/env python3
"""Retake manager: retake only the failed artifact and its real dependents.

Directive sections 24.5 (enforced handoffs, bounded work, targeted repair)
+ 18 rule 6 + 17.8 (acceptance profile repair caps + verdict values).
Stdlib only. No network, no secrets.

Contract:
- Every repair gets its own attempt ID and refers to the failed
  artifact/check. Retry limits persist across restarts: the caller passes the
  durable attempt history (a JSON list of prior retake records); nothing is
  kept in process memory.
- Retry bounds come from the acceptance profile (17.8): the profile may name
  a repair cap (nested under any key containing "repair" or "retry"); when
  the profile carries none, DEFAULT_REPAIR_CAP holds (marked
  profile_unspecified).
- Retake-only-failed-artifact: the plan lists exactly the failed artifact +
  its listed real dependents. Approved assets are never touched: dependents
  that name an artifact with an accepted (PASS) record are excluded with a
  reason; shots not in the dependent graph are never regenerated.
- Failed dependents fail with the retake only when their listed prerequisite
  is the failed artifact (chain retakes); a dependent on a passing artifact
  is untouched.
- Repair isolation: one bad shot never regenerates sibling shots. Shots list
  any number of artifact IDs; the plan emits entries ONLY for failed ones.
- Exit-per-artifact verdicts use the acceptance-profile vocabulary:
  FAIL / PASS / UNAVAILABLE. UNVERIFIED prerequisites park, never pass.

Exit codes (EXIT): ok 0 (plan with items or empty plan), error 1,
waiting 3, parked 4, rejected 5 (invalid input / cap exhausted).
Output: single JSON object on stdout.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

TOOL_NAME = "retake_manager"
TOOL_VERSION = "1.0.0"
EXIT = {"ok": 0, "error": 1, "waiting": 3, "parked": 4, "rejected": 5}

# ponytail: fixed ceiling until acceptance-profile.json names repair caps;
# upgrade path: read cap from the published versioned profile per run.
DEFAULT_REPAIR_CAP = 2

DEFAULT_PROFILE = os.environ.get("DRAMA_SONG_PROFILE") or os.path.join(
    os.environ.get("DRAMA_SONG_BUILD_ROOT",
                   str(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))),
    "core", "acceptance-profile.json")

VERDICTS = ("FAIL", "PASS", "UNAVAILABLE")


def _reject(code, reason):
    return {"outcome": "rejected", "code": code, "reason": reason,
            "tool": TOOL_NAME, "tool_version": TOOL_VERSION}


def load_profile(path):
    """(profile, repair_cap, cap_source, error): read acceptance profile."""
    if path is None:
        return {}, DEFAULT_REPAIR_CAP, "default", None
    p = Path(os.path.expanduser(str(path)))
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except OSError as exc:
        return None, None, None, (
            "acceptance profile not readable at %s (%s)"
            % (p, exc.strerror or exc))
    except ValueError as exc:
        return None, None, None, (
            "acceptance profile at %s is not valid JSON: %s" % (p, exc))
    if not isinstance(data, dict):
        return None, None, None, (
            "acceptance profile at %s is not a JSON object" % p)
    cap, source = _find_repair_cap(data)
    return data, cap, source, None


def _find_repair_cap(node):
    """(cap, source): repair cap from profile; None when the profile is silent."""
    if isinstance(node, dict):
        for key, value in node.items():
            lowered = str(key).lower()
            if ("repair" in lowered or "retry" in lowered) and (
                    "cap" in lowered or "max" in lowered or "limit" in lowered):
                if isinstance(value, int) and not isinstance(value, bool) \
                        and value >= 0:
                    return value, "profile"
        for value in node.values():
            found, source = _find_repair_cap(value)
            if found is not None:
                return found, source
    elif isinstance(node, list):
        for item in node:
            found, source = _find_repair_cap(item)
            if found is not None:
                return found, source
    return None, None


def _prior_attempts(history):
    """(counts, errors): per-artifact prior attempt counts from durable history."""
    counts = {}
    if history is None:
        return counts, []
    if not isinstance(history, list):
        return None, ["attempt_history must be a JSON list of retake records"]
    for index, record in enumerate(history):
        if not isinstance(record, dict):
            return None, ["attempt_history[%d] must be an object" % index]
        artifacts = record.get("artifacts")
        if artifacts is None and "artifact_id" in record:
            artifacts = [record["artifact_id"]]
        if not isinstance(artifacts, list) or not artifacts:
            return None, [
                "attempt_history[%d] must name artifacts (list) or "
                "artifact_id" % index]
        for artifact_id in artifacts:
            if not isinstance(artifact_id, str) or not artifact_id:
                return None, [
                    "attempt_history[%d] artifact IDs must be non-empty "
                    "strings" % index]
            counts[artifact_id] = counts.get(artifact_id, 0) + 1
    return counts, []


def plan(req, profile_path=None):
    """Plan one targeted retake. Returns the JSON envelope (see module doc)."""
    if not isinstance(req, dict):
        return _reject("INVALID_REQUEST", "request must be a JSON object")
    errors = []
    failed = req.get("failed_artifact_id")
    if not isinstance(failed, str) or not failed:
        errors.append("failed_artifact_id must be a non-empty string")
    check = req.get("check")
    if not isinstance(check, str) or not check:
        errors.append("check must name the failed artifact/check (non-empty)")
    shots = req.get("shots")
    if not isinstance(shots, list) or not shots:
        errors.append("shots must be a non-empty list of artifact IDs")
    elif any(not isinstance(s, str) or not s for s in shots):
        errors.append("shots must be non-empty strings")
    dependents = req.get("dependents", {})
    if not isinstance(dependents, dict):
        errors.append("dependents must be a map artifact_id -> [prereqs]")
    else:
        for key, prereqs in dependents.items():
            if not isinstance(prereqs, list) or any(
                    not isinstance(p, str) for p in prereqs):
                errors.append(
                    "dependents[%r] must be a list of artifact-ID strings"
                    % key)
    accepted = req.get("accepted", [])
    if not isinstance(accepted, list) or any(
            not isinstance(a, str) for a in accepted):
        errors.append("accepted must be a list of artifact-ID strings")
    states = req.get("artifact_states", {})
    if not isinstance(states, dict):
        errors.append("artifact_states must be a map artifact_id -> verdict")
    else:
        for key, verdict in states.items():
            if verdict not in VERDICTS:
                errors.append(
                    "artifact_states[%r] must be one of %s" % (key, VERDICTS))
    history = req.get("attempt_history")
    counts, history_errors = _prior_attempts(history)
    errors.extend(history_errors)
    reason = req.get("reason")
    if reason is not None and (not isinstance(reason, str) or not reason):
        errors.append("reason must be a non-empty string when present")
    if errors:
        return _reject("INVALID_REQUEST", "; ".join(errors))

    prof_path = (profile_path or req.get("profile")
                 or os.environ.get("ACCEPTANCE_PROFILE_JSON")
                 or DEFAULT_PROFILE)
    profile, cap, cap_source, profile_error = load_profile(prof_path)
    if profile_error:
        return {"outcome": "error", "code": "PROFILE_UNAVAILABLE",
                "reason": profile_error, "tool": TOOL_NAME,
                "tool_version": TOOL_VERSION,
                "recovery": "publish the versioned acceptance-profile.json "
                            "before generation (directive 17.8)"}
    if cap is None:
        cap, cap_source = DEFAULT_REPAIR_CAP, "default"
    profile_version = profile.get("profile_version", "unspecified")

    accepted_set = set(accepted)
    failed_states = {k for k, v in states.items() if v == "FAIL"}
    if failed not in shots:
        return _reject(
            "UNKNOWN_ARTIFACT",
            "failed_artifact_id %r is not in shots %r" % (failed, shots))
    if failed in accepted_set:
        return _reject(
            "ACCEPTED_ARTIFACT",
            "failed_artifact_id %r carries an accepted (PASS) record; "
            "retakes never regenerate approved assets" % failed)
    if states.get(failed) == "PASS":
        return _reject(
            "ACCEPTED_ARTIFACT",
            "failed_artifact_id %r has artifact_states PASS; do not "
            "regenerate approved assets" % failed)

    # Target set: failed artifact + real dependents whose prereqs include it
    # (transitively), minus anything accepted. Siblings are never included.
    blocked = []
    targets = [failed]
    queue = [failed]
    seen = {failed}
    while queue:
        current = queue.pop(0)
        for artifact_id, prereqs in dependents.items():
            if artifact_id in seen or current not in prereqs:
                continue
            if artifact_id in accepted_set or states.get(artifact_id) == "PASS":
                blocked.append({
                    "artifact_id": artifact_id,
                    "excluded": True,
                    "reason": "accepted (PASS) record exists; approved assets "
                              "are never regenerated",
                })
                continue
            seen.add(artifact_id)
            targets.append(artifact_id)
            queue.append(artifact_id)

    # Repair bounds: per-artifact attempt counts from durable history.
    exhausted = [a for a in targets if counts.get(a, 0) >= cap]
    if exhausted:
        detail = ", ".join(
            "%s (%d attempts, cap %d)" % (a, counts.get(a, 0), cap)
            for a in exhausted)
        return {
            "outcome": "parked", "code": "REPAIR_CAP_EXHAUSTED",
            "reason": "repair cap reached (%s %s=%d): %s; "
                      "park/escalate after the configured budget is spent"
                      % ("profile" if cap_source == "profile" else "default",
                         "repair_cap", cap, detail),
            "targets": targets, "attempt_counts": dict(counts),
            "repair_cap": cap, "repair_cap_source": cap_source,
            "profile_version": profile_version,
            "tool": TOOL_NAME, "tool_version": TOOL_VERSION,
            "recovery": "escalate to the orchestrator; do not reset counters "
                        "to force another attempt",
        }

    attempts = []
    for artifact_id in targets:
        attempt_no = counts.get(artifact_id, 0) + 1
        attempts.append({
            "artifact_id": artifact_id,
            "attempt_id": "%s-r%d-%s" % (
                artifact_id, attempt_no, uuid.uuid4().hex[:8]),
            "attempt_no": attempt_no,
            "refers_to": {"failed_artifact_id": failed, "check": check},
            "reason": (reason or
                       "retake of %s for failed check %s" % (artifact_id, check)),
        })
    untouched = sorted(set(shots) - seen)
    return {
        "outcome": "ok",
        "targets": targets,
        "attempts": attempts,
        "untouched": untouched,
        "excluded_accepted": blocked,
        "repair_cap": cap,
        "repair_cap_source": cap_source,
        "profile_version": profile_version,
        "attempt_counts": dict(counts),
        "checks": {a: "FAIL" for a in targets},
        "tool": TOOL_NAME, "tool_version": TOOL_VERSION,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Targeted retake planner (directive 24.5)")
    parser.add_argument("--request", required=True,
                        help="retake request JSON file, or - for stdin")
    parser.add_argument("--profile", default=None,
                        help="path to acceptance-profile.json "
                             "(default: run core profile or "
                             "$ACCEPTANCE_PROFILE_JSON)")
    args = parser.parse_args(argv)
    try:
        if args.request == "-":
            req = json.load(sys.stdin)
        else:
            req = json.loads(Path(args.request).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        payload = _reject("INVALID_REQUEST", "cannot read request: %s" % exc)
        print(json.dumps(payload, sort_keys=True))
        return EXIT["rejected"]
    payload = plan(req, profile_path=args.profile)
    print(json.dumps(payload, sort_keys=True))
    return EXIT.get(payload.get("outcome"), EXIT["error"])


if __name__ == "__main__":
    sys.exit(main())
