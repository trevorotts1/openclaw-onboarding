#!/bin/bash
# Hard-fail: no agent identity file or generator may contain the legacy
# impersonation directive "Act AS IF you ARE the persona".
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SENTINEL1="Act AS IF you ARE the persona"
VIOLATIONS=""
while IFS= read -r -d '' file; do
  case "$file" in */templates/role-library/*|*/templates/universal*|*/.git/*|*/node_modules/*) continue ;; esac
  if grep -qF "$SENTINEL1" "$file" 2>/dev/null; then
    VIOLATIONS+="$file"$'\n'
  fi
done < <(find "$ROOT" -type f \( -name "*.md" -o -name "*.py" \) -not -path "*/.git/*" -not -path "*/templates/role-library/*" -not -path "*/templates/universal*" -not -path "*/node_modules/*" -print0 2>/dev/null)
if [[ -z "$VIOLATIONS" ]]; then
  echo "OK: No impersonation directives (\"Act AS IF you ARE the persona\") found."; exit 0
else
  echo "INVARIANT VIOLATED — Impersonation directive(s) found:"; echo "$VIOLATIONS"
  echo "REMEDY: Replace legacy impersonation directive with anti-impersonation framework per U124."; exit 1
fi
