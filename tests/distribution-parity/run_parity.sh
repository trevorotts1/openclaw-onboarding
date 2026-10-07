#!/usr/bin/env bash
# Cross-distribution parity driver (unit W3-06-U1).
#
# Shared-fixture parity suite over BOTH distributions of the drama-song ad
# factory:
#   A  onboarding/75-drama-song-ad-factory                (OpenClaw twin)
#   B  999-setup/.claude/skills/drama-song-ad-factory     (Claude-Nine/Claude Code)
#
# Six families, each printed as PASS or FAIL:
#   cli-exit-codes, envelope-schema-version, acceptance-qc-byte-parity,
#   core-sha256-parity, department-wiring-equality,
#   skillmd-contract-equivalence
#
# Usage:
#   bash tests/distribution-parity/run_parity.sh
#
# Overrides (all optional):
#   DSAF_OPENCLAW_SKILL  path to the OpenClaw skill folder
#   DSAF_999_SKILL       path to the 999 skill folder
#   DSAF_STAGING_SKILL   path to the build-tree staging copy of A
#   DSAF_DEPT_MAP        path to skill-department-map.json
#   BOX_SLUG             box slug used to prefix temp files (default: local)
#
# Exit: 0 all families PASS, 1 any family FAIL, 2 resolve/tooling failure.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_ID="W3-06-U1"
export BOX_SLUG="${BOX_SLUG:-local}"
export DSAF_TMP_PREFIX="${BOX_SLUG}-${UNIT_ID}-"
export TMPDIR="${TMPDIR:-/tmp}"

PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then
  echo "tooling-failure: python3 not found on PATH" >&2
  exit 2
fi
if [ ! -f "$HERE/parity_check.py" ]; then
  echo "tooling-failure: missing $HERE/parity_check.py" >&2
  exit 2
fi

set +e
"$PY" "$HERE/parity_check.py"
rc=$?
set -e

if [ "$rc" -eq 2 ]; then
  echo "run_parity.sh: resolve/tooling failure (nothing was compared)" >&2
elif [ "$rc" -ne 0 ]; then
  echo "run_parity.sh: at least one family FAILED — evidence only, not an approval" >&2
else
  echo "run_parity.sh: every family PASS"
fi
exit "$rc"
