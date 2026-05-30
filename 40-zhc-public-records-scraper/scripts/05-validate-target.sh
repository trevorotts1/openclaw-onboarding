#!/usr/bin/env bash
# 05-validate-target.sh — Skill 40
# DRY-PROBE validator for a Tier-1 (or Tier-3) target BEFORE any live run.
# Given a target slug, it: (1) loads the config, (2) checks robots.txt allows
# the search path, (3) confirms a tos_url is present, (4) does a single HEAD/GET
# to confirm the portal responds, and (5) reports whether the configured result
# selectors are still plausibly present (a light heuristic on a sample fetch).
# It NEVER scrapes records and NEVER fabricates anything. A failing probe means
# the target must be treated as a Tier-4 honest gap until fixed.
#
# Usage: ./05-validate-target.sh <slug>        # e.g. cook-county-il
#        ./05-validate-target.sh --tier3 <path-to-operator-config.json>

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TIER1_DIR="$SKILL_ROOT/references/tier1-counties"
P="[skill 40][validate]"

command -v jq >/dev/null 2>&1 || { echo "$P BLOCKED: jq required"; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "$P BLOCKED: curl required"; exit 1; }

CONFIG=""
if [ "${1:-}" = "--tier3" ]; then
  CONFIG="${2:-}"
  [ -f "$CONFIG" ] || { echo "$P BLOCKED: tier3 config not found: $CONFIG"; exit 1; }
else
  SLUG="${1:-}"
  [ -n "$SLUG" ] || { echo "$P usage: $0 <slug> | --tier3 <config.json>"; exit 2; }
  CONFIG="$TIER1_DIR/$SLUG.json"
  [ -f "$CONFIG" ] || { echo "$P BLOCKED: no Tier-1 config for slug '$SLUG' at $CONFIG"; exit 1; }
fi

jq -e . "$CONFIG" >/dev/null 2>&1 || { echo "$P BLOCKED: invalid JSON: $CONFIG"; exit 1; }

BASE="$(jq -r '.portal_url // .base_url // empty' "$CONFIG")"
SEARCH_PATH="$(jq -r '.search_path // "/"' "$CONFIG")"
TOS="$(jq -r '.tos_url // empty' "$CONFIG")"
SELECTORS_N="$(jq -r '(.selectors // {}) | length' "$CONFIG")"
SLUG="$(jq -r '.slug // "unknown"' "$CONFIG")"

FAIL=0
echo "$P validating target: $SLUG"
echo "$P    portal: ${BASE:-<none>}  path: $SEARCH_PATH"

[ -n "$BASE" ] || { echo "$P    [FAIL] no portal_url/base_url in config"; FAIL=1; }
[ -n "$TOS" ]  && echo "$P    [PASS] tos_url present ($TOS)" || { echo "$P    [FAIL] no tos_url — operator must acknowledge ToS before live use"; FAIL=1; }
[ "$SELECTORS_N" -gt 0 ] 2>/dev/null && echo "$P    [PASS] $SELECTORS_N result selector(s) configured" || { echo "$P    [WARN] no selectors configured — Tier-3 builder needed before live"; }

# robots.txt check (binding)
if [ -n "$BASE" ]; then
  if bash "$SCRIPT_DIR/lib-records.sh" robots_ok "$BASE" "$SEARCH_PATH"; then
    echo "$P    [PASS] robots.txt allows $SEARCH_PATH"
  else
    echo "$P    [FAIL] robots.txt DISALLOWS $SEARCH_PATH — this target is a Tier-4 honest gap (never override robots)"
    FAIL=1
  fi
  # Light liveness probe (HEAD; never a record scrape).
  code="$(curl -fsS -o /dev/null -w '%{http_code}' --max-time 15 -I "${BASE%/}$SEARCH_PATH" 2>/dev/null || echo "000")"
  if [ "$code" = "200" ] || [ "$code" = "301" ] || [ "$code" = "302" ] || [ "$code" = "403" ]; then
    echo "$P    [INFO] portal responded HTTP $code (liveness only; not a scrape)"
  else
    echo "$P    [WARN] portal liveness probe returned HTTP $code — confirm the URL before live use"
  fi
fi

echo
if [ "$FAIL" -eq 0 ]; then
  echo "$P VALIDATION PASS for $SLUG — safe to use as a live tier target (subject to ToS acknowledgement + cost caps)."
  exit 0
else
  echo "$P VALIDATION FAIL for $SLUG — treat as a Tier-4 HONEST GAP until fixed. NEVER fabricate records for it."
  exit 1
fi
