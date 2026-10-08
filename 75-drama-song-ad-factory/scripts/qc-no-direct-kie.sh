#!/usr/bin/env bash
# qc-no-direct-kie.sh — F14 static check (manual Part F F14, Critical).
# Fails when a non-test file under scripts/core/ contacts KIE endpoints
# outside kie_dispatch/. Builders may never call KIE directly: all paid
# jobs go through the skill's dispatcher (a hand-written request file is
# a QC fail). Scope: this skill tree (onboarding). The 999 copy is
# W3-A's — run this script there is their unit's job, not ours.
#
# Env: DRAMA75_CORE=<scripts/core dir> (default: resolve from this file).
# Exit 0 = clean; exit 2 = direct-KIE call found (paths printed); exit 1 =
# usage error.
set -u

here="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"
core="${DRAMA75_CORE:-$here/core}"
if [ ! -d "$core" ]; then
  echo "qc-no-direct-kie: no core dir at $core (set DRAMA75_CORE)" >&2
  exit 1
fi

# Dispatch module + its own tests + the resolver are the ONLY allowed
# mentioners of KIE endpoints. Tests are excluded from scope everywhere.
hits="$(mktemp /tmp/qcndk-hits.XXXXXX)"
trap 'rm -f "$hits"' EXIT

if command -v grep >/dev/null 2>&1; then
  # -r over core/, skip tests + pycache; endpoint = kie.ai host or KIE job
  # submit path appearing in a non-dispatch module.
  # shellcheck disable=SC2086
  grep -rInE \
    --exclude-dir=__pycache__ \
    --exclude-dir=.git \
    --exclude='test_*.py' \
    --exclude='*_test.py' \
    --exclude='conftest.py' \
    -e '(https?://)?(api\.)?kie\.ai' \
    "$core" 2>/dev/null \
  | grep -vE '/kie_dispatch/(kie_dispatch|model_lock|unknown_resolution/|test_)' \
  | awk -F: '{print $1}' | sort -u > "$hits" || true
else
  echo "qc-no-direct-kie: grep unavailable" >&2
  exit 1
fi

if [ -s "$hits" ]; then
  echo "qc-no-direct-kie: DIRECT KIE CALLS OUTSIDE kie_dispatch — FAIL" >&2
  while IFS= read -r f; do
    echo "  offender: $f" >&2
  done < "$hits"
  exit 2
fi
echo "qc-no-direct-kie: clean — no KIE endpoint outside kie_dispatch/ ($core)"
exit 0