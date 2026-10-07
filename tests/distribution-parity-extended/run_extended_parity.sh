#!/usr/bin/env bash
# Extended cross-distribution parity driver (unit PKG-01-U1).
#
# Enumerates BOTH packaged skill folders and diffs every packaged module + doc:
#   A  OpenClaw distribution    75-drama-song-ad-factory
#   B  Claude-Nine/Claude Code  999-setup/.claude/skills/drama-song-ad-factory
#   C  canonical staging        onboarding/75-drama-song-ad-factory (witness)
#
# Five families, each printed as PASS or FAIL:
#   packaged-inventory, module-parity, shared-doc-byte-parity,
#   skillmd-doc-contract, packaged-claims
#
# Usage:
#   bash tests/distribution-parity-extended/run_extended_parity.sh
#
# Overrides (all optional):
#   DSAFX_OPENCLAW_SKILL  path to distribution A
#   DSAFX_999_SKILL       path to distribution B
#   DSAFX_CANON_SKILL     path to canonical staging C
#   DTS_BUILD_ROOT        alternate build root (run from a repo checkout)
#   BOX_SLUG              box slug for temp-file prefixes (default: hostname)
#
# Exit: 0 no family FAIL, 1 any family FAIL, 2 resolve/tooling failure.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_ID="PKG-01-U1"
export BOX_SLUG="${BOX_SLUG:-$(hostname -s 2>/dev/null || echo local)}"
export DSAF_TMP_PREFIX="${BOX_SLUG}-${UNIT_ID}-"
export TMPDIR="${TMPDIR:-/tmp}"

PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then
  echo "tooling-failure: python3 not found on PATH" >&2
  exit 2
fi
if [ ! -f "$HERE/extended_parity_check.py" ]; then
  echo "tooling-failure: missing $HERE/extended_parity_check.py" >&2
  exit 2
fi

set +e
"$PY" "$HERE/extended_parity_check.py"
rc=$?
set -e

if [ "$rc" -eq 2 ]; then
  echo "run_extended_parity.sh: resolve/tooling failure (nothing was compared)" >&2
elif [ "$rc" -ne 0 ]; then
  echo "run_extended_parity.sh: at least one family FAILED — evidence only, not an approval" >&2
else
  echo "run_extended_parity.sh: every family PASS (zero byte drift between distributions)"
fi
exit "$rc"
