#!/usr/bin/env bash
# bump-agent-browser-cli-pin.sh — GK-28/U90 step (b): the ONLY sanctioned way
# to change the pinned agent-browser CLI version. Updates agent-browser-cli.pin
# AND CLI-VERSION-PIN.md's pinned-version line + appends a dated bump-log row,
# in one atomic edit, so the two can never drift (mirrors
# ../../scripts/bump-version.sh's single-source-of-truth pattern for the
# repo's own version markers).
#
# USAGE
#   bump-agent-browser-cli-pin.sh <new-version> ["reason"]
#       Bump the pin. <new-version> must be X.Y.Z (no leading "v" — this is an
#       npm package version, not a repo release tag).
#   bump-agent-browser-cli-pin.sh --check
#       Exit 1 if agent-browser-cli.pin and CLI-VERSION-PIN.md's pinned-version
#       line disagree. Never writes.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PIN_FILE="$SKILL_DIR/agent-browser-cli.pin"
DOC_FILE="$SKILL_DIR/CLI-VERSION-PIN.md"

_current_pin() {
  if [ -f "$PIN_FILE" ]; then
    tr -d '[:space:]' < "$PIN_FILE"
  else
    echo ""
  fi
}

_doc_pin() {
  if [ ! -f "$DOC_FILE" ]; then
    echo ""
    return
  fi
  python3 -c "
import re
t = open('$DOC_FILE').read()
m = re.search(r'^## Pinned version\s*\n\s*\n([0-9]+\.[0-9]+\.[0-9]+)', t, re.MULTILINE)
print(m.group(1) if m else '')
"
}

if [ "${1:-}" = "--check" ]; then
  P="$(_current_pin)"
  D="$(_doc_pin)"
  if [ -z "$P" ] || [ -z "$D" ] || [ "$P" != "$D" ]; then
    echo "FAIL — agent-browser-cli.pin ('$P') and CLI-VERSION-PIN.md pinned-version ('$D') disagree" >&2
    exit 1
  fi
  echo "PASS — CLI version pin ($P) agrees across agent-browser-cli.pin and CLI-VERSION-PIN.md"
  exit 0
fi

NEW="${1:-}"
REASON="${2:-no reason given}"
if [ -z "$NEW" ]; then
  echo "Usage: $0 <new-version> [\"reason\"]" >&2
  echo "       $0 --check" >&2
  exit 2
fi
if ! echo "$NEW" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
  echo "ERROR: version must be X.Y.Z (got '$NEW')" >&2
  exit 2
fi

OLD="$(_current_pin)"
[ -z "$OLD" ] && OLD="(none — first pin)"

if [ ! -f "$DOC_FILE" ]; then
  echo "ERROR: $DOC_FILE not found — cannot bump without the doc to update alongside the pin" >&2
  exit 2
fi

echo "$NEW" > "$PIN_FILE"

TODAY="$(date -u +%Y-%m-%d)"
python3 - "$DOC_FILE" "$NEW" "$OLD" "$TODAY" "$REASON" <<'PYEOF'
import re, sys
path, new, old, today, reason = sys.argv[1:6]
t = open(path).read()

t2, n = re.subn(r'(## Pinned version\s*\n\s*\n)[0-9]+\.[0-9]+\.[0-9]+',
                 r'\g<1>' + new, t, count=1)
if n == 0:
    print(f"ERROR: '## Pinned version' line not found in {path}", file=sys.stderr)
    sys.exit(1)

marker = "| Date | From | To | Who/why |\n|---|---|---|---|\n"
idx = t2.find(marker)
if idx == -1:
    print(f"ERROR: bump-log table header not found in {path}", file=sys.stderr)
    sys.exit(1)
insert_at = idx + len(marker)
row = f"| {today} | {old} | {new} | {reason} |\n"
t2 = t2[:insert_at] + row + t2[insert_at:]

open(path, "w").write(t2)
PYEOF
RC=$?
if [ "$RC" -ne 0 ]; then
  echo "ERROR: doc update failed — reverting $PIN_FILE" >&2
  if echo "$OLD" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
    echo "$OLD" > "$PIN_FILE" 2>/dev/null || true
  else
    rm -f "$PIN_FILE" 2>/dev/null || true
  fi
  exit 1
fi

echo "OK — CLI version pin bumped: $OLD -> $NEW (dated $TODAY, reason: $REASON)"
