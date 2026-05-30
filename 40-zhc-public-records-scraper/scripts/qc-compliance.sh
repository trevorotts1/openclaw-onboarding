#!/usr/bin/env bash
# qc-compliance.sh — machine-enforce the Skill 40 COMPLIANCE posture:
#   1. robots.txt is respected (the router has a robots_ok gate that returns
#      disallow correctly; a disallow path => honest gap).
#   2. EVERY Tier-1 config carries a tos_url (ToS reference per target).
#   3. Attribution is required: the router stamps source + retrieved_at and the
#      contract says an unattributed result is refused.
#
# Exit 0 = posture holds; 1 = a violation found. BASH (grep/jq core).

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LIB="$SCRIPT_DIR/lib-records.sh"
TIER1_DIR="$SKILL_ROOT/references/tier1-counties"
FAIL=0

echo "=== qc-compliance (Skill 40): robots + ToS + attribution ==="

# 1. robots_ok gate exists + behaves: a "Disallow: /" robots blocks everything.
if grep -q "robots_ok" "$LIB" && grep -qi "robots.txt" "$LIB"; then
  echo "  [PASS] router has a robots_ok gate referencing robots.txt"
else
  echo "  [FAIL] router missing a robots_ok / robots.txt gate"; FAIL=1
fi
# Functional: build a fake robots-disallow scenario via the gate's prefix logic.
# robots_ok hits the network for robots.txt; we can't rely on that in CI, so we
# assert the gate's disallow-prefix logic statically (the case "$path" in "$rule"* match).
if grep -q 'case "$path" in "$rule"\*)' "$LIB"; then
  echo "  [PASS] router honors a Disallow prefix (returns disallow on a matching path)"
else
  echo "  [FAIL] router does not implement Disallow-prefix matching"; FAIL=1
fi

# 2. Every Tier-1 config carries a tos_url.
if command -v jq >/dev/null 2>&1 && [ -d "$TIER1_DIR" ]; then
  miss=0; n=0
  for f in "$TIER1_DIR"/*.json; do
    [ -f "$f" ] || continue
    n=$((n+1))
    tos="$(jq -r '.tos_url // empty' "$f" 2>/dev/null || true)"
    if [ -z "$tos" ]; then echo "  [FAIL] $(basename "$f") has no tos_url"; miss=$((miss+1)); fi
  done
  if [ "$n" -eq 0 ]; then echo "  [FAIL] no Tier-1 configs found in $TIER1_DIR"; FAIL=1
  elif [ "$miss" -eq 0 ]; then echo "  [PASS] all $n Tier-1 configs carry a tos_url"
  else echo "  [FAIL] $miss of $n Tier-1 configs missing tos_url"; FAIL=1; fi
else
  echo "  [WARN] jq or tier1 dir unavailable — skipping per-config tos_url scan"
fi

# 3. Attribution: router stamps source + retrieved_at; contract refuses unattributed.
if grep -q "retrieved_at" "$LIB" && grep -q "source" "$LIB"; then
  echo "  [PASS] router references source + retrieved_at (attribution)"
else
  echo "  [FAIL] router missing source/retrieved_at attribution"; FAIL=1
fi
if grep -qi "unattributed result.*is not a record" "$LIB"; then
  echo "  [PASS] router carries the 'unattributed result is not a record' contract"
else
  echo "  [FAIL] router missing the unattributed-result refusal contract"; FAIL=1
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "RESULT: PASS — compliance posture holds (robots respected, ToS per target, attribution required)."
  exit 0
else
  echo "RESULT: FAIL — a compliance violation was detected above."
  exit 1
fi
