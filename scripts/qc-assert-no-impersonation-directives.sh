#!/bin/bash
# Hard-fail: no agent identity file or generator may contain the legacy
# impersonation directive "Act AS IF you ARE the persona" or equivalent
# phrasings that instruct the agent to assume a persona's identity.
#
# LIMITATION: The check uses fixed-string matching (grep -F). Simple
# rewordings (e.g. "Act as if you were the persona", "act like the persona")
# will NOT be caught. The sentinel list must be maintained as new equivalent
# phrasings are discovered during code review.
#
# Set QC_IMPERSONATION_SCAN_ROOT to override the scan root (for testing).
set -euo pipefail
ROOT="${QC_IMPERSONATION_SCAN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SENTINELS=(
  "Act AS IF you ARE the persona"
  "act AS that persona"
  "You ARE the persona"
)
VIOLATIONS=""
while IFS= read -r -d '' file; do
  case "$file" in */templates/role-library/*|*/templates/universal*|*/.git/*|*/node_modules/*) continue ;; esac
  for sentinel in "${SENTINELS[@]}"; do
    if grep -qF "$sentinel" "$file" 2>/dev/null; then
      VIOLATIONS+="$file"$'\n'
      break
    fi
  done
done < <(find "$ROOT" -type f \( -name "*.md" -o -name "*.py" \) -not -path "*/.git/*" -not -path "*/templates/role-library/*" -not -path "*/templates/universal*" -not -path "*/node_modules/*" -print0 2>/dev/null)
if [[ -z "$VIOLATIONS" ]]; then
  echo "OK: No impersonation directives (\"Act AS IF you ARE the persona\" or equivalents) found."; exit 0
else
  echo "INVARIANT VIOLATED — Impersonation directive(s) found:"; echo "$VIOLATIONS"
  echo "REMEDY: Replace legacy impersonation directive with anti-impersonation framework per U124."; exit 1
fi
