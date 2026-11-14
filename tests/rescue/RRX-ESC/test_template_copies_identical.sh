#!/usr/bin/env bash
# tests/rescue/RRX-ESC/test_template_copies_identical.sh   (RRX-028)
# The escalation section template ships twice: the canonical copy under
# scripts/ and the role-library copy under
# 23-ai-workforce-blueprint/templates/role-library/rescue-rangers/scripts/.
# Every writer reads one of the two, so the two must be byte-identical.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CANON="$REPO_ROOT/scripts/rescue-escalation-section.md.tpl"
COPY="$REPO_ROOT/23-ai-workforce-blueprint/templates/role-library/rescue-rangers/scripts/rescue-escalation-section.md.tpl"

[ -f "$CANON" ] || { echo "FATAL: $CANON not found"; exit 2; }
[ -f "$COPY" ] || { echo "FATAL: $COPY not found"; exit 2; }

if ! cmp -s "$CANON" "$COPY"; then
  echo "the role-library copy of the escalation template differs from scripts/rescue-escalation-section.md.tpl; copy the scripts/ file over it" >&2
  exit 1
fi

echo "ok: the two escalation template copies are byte-identical"
exit 0
