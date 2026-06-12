#!/usr/bin/env bash
# qc-prereqs-json.sh -- CI lint: validate every PREREQS.json in the repo.
#
# Fails the build if:
#   - Any PREREQS.json cannot be parsed as valid JSON
#   - Any entry with severity="required" has an empty or missing "satisfy" field
#   - Any entry is missing required schema fields (id, type, label, check, severity)
#
# Per INSTALL-CONTRACT.md Rule 16.
#
# Usage (from repo root):
#   bash scripts/qc-prereqs-json.sh
#   bash scripts/qc-prereqs-json.sh --verbose
#
# Exit codes:
#   0 -- all PREREQS.json files pass
#   1 -- one or more violations found

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERBOSE=0
[[ "${1:-}" == "--verbose" ]] && VERBOSE=1

if ! command -v python3 >/dev/null 2>&1; then
  echo "[qc-prereqs] ERROR: python3 not on PATH" >&2
  exit 1
fi

export OC_REPO_ROOT="$REPO_ROOT"
export OC_VERBOSE="$VERBOSE"

python3 <<'PYEOF'
import json
import os
import sys

REPO_ROOT = os.environ["OC_REPO_ROOT"]
VERBOSE = os.environ.get("OC_VERBOSE", "0") == "1"

REQUIRED_FIELDS = {"id", "type", "label", "check", "severity"}
VALID_TYPES = {"credential", "skill", "binary", "config", "mcp"}
VALID_SEVERITIES = {"required", "optional"}

errors = []
warnings = []
files_checked = 0


def check_prereqs_json(path):
    rel = os.path.relpath(path, REPO_ROOT)
    try:
        with open(path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        errors.append(f"{rel}: invalid JSON -- {e}")
        return

    prereqs = data.get("prerequisites", [])
    if not isinstance(prereqs, list):
        errors.append(f"{rel}: 'prerequisites' must be a list")
        return

    for i, prereq in enumerate(prereqs):
        if not isinstance(prereq, dict):
            errors.append(f"{rel}: prerequisites[{i}] must be an object")
            continue

        p_id = prereq.get("id", f"[index {i}]")
        missing_fields = REQUIRED_FIELDS - set(prereq.keys())
        if missing_fields:
            errors.append(f"{rel}: {p_id}: missing required fields: {sorted(missing_fields)}")

        p_type = prereq.get("type", "")
        if p_type and p_type not in VALID_TYPES:
            errors.append(f"{rel}: {p_id}: unknown type '{p_type}' (valid: {sorted(VALID_TYPES)})")

        p_severity = prereq.get("severity", "")
        if p_severity and p_severity not in VALID_SEVERITIES:
            errors.append(f"{rel}: {p_id}: unknown severity '{p_severity}' (valid: required, optional)")

        if p_severity == "required":
            satisfy = prereq.get("satisfy", "")
            if not satisfy or not satisfy.strip():
                errors.append(
                    f"{rel}: {p_id}: severity=required but 'satisfy' is empty or missing "
                    f"(INSTALL-CONTRACT.md Rule 16 violation)"
                )

        # check field must have exactly one populated key
        check = prereq.get("check", {})
        if isinstance(check, dict) and len(check) == 0:
            errors.append(f"{rel}: {p_id}: 'check' object is empty -- must have exactly one key")

    if VERBOSE:
        print(f"  OK  {rel} ({len(prereqs)} prereqs)")


# Walk repo and find all PREREQS.json files
for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
    # Skip hidden dirs and node_modules
    dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "node_modules"]
    for fname in filenames:
        if fname == "PREREQS.json":
            files_checked += 1
            check_prereqs_json(os.path.join(dirpath, fname))

print(f"[qc-prereqs] checked {files_checked} PREREQS.json file(s)")

if errors:
    print(f"[qc-prereqs] FAIL: {len(errors)} violation(s) found:")
    for err in errors:
        print(f"  ERROR: {err}")
    sys.exit(1)
else:
    print(f"[qc-prereqs] PASS: all PREREQS.json files are valid")
    sys.exit(0)
PYEOF

exit $?
