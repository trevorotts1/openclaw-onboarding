#!/usr/bin/env bash
# qc-no-personal-data.sh — machine-enforce that the UNIVERSAL Skill 39 contains
# ZERO real personal / client identifiers anywhere in its source tree.
#
# A UNIVERSAL skill must be free of every real person, business, hostname,
# token, location id, phone, and email. Replace each with a generic placeholder
# (<CLIENT_BUSINESS_NAME> / <PUBLIC_HOSTNAME> / <ST> / <FIPS> / "the operator").
#
# Exit codes: 0 = clean; 1 = one or more banned identifiers found.
# BASH only (grep core). This file is excluded from the scan, so it may name the
# banned identifiers in its patterns.
#
# Usage: bash scripts/qc-no-personal-data.sh [--skill-dir DIR]

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SELF_NAME="$(basename "$0")"

while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    -h|--help) sed -n '1,15p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

# Banned identifiers (ERE alternation). The real client roster is EXTERNALIZED to
# an operator-local, gitignored file ($OPENCLAW_CLIENT_ROSTER or
# ~/.openclaw/client-roster.txt; template scripts/client-roster.example.txt) so no
# real client name ships in this repo. Operator-static tokens (brand, chat id,
# email handle, home paths) and the .example placeholders stay inline and are
# ALWAYS scanned, so the gate never fails open when the roster is absent.
# NOTE: keep a trailing word boundary on short client tokens (e.g. a "Foo\b"
# pattern) in the roster so they catch the client but NOT a public entity that
# merely starts with the same letters (e.g. "Foo\b" must not match "Fooville County").
OPERATOR_BANNED='blackceo|5252140759|trevelynotts|Trevor|/Users/christy|/Users/blackceomacmini|/Users/client'
PLACEHOLDER_BANNED='ExampleClientAlpha|ExampleClientBeta|PlaceholderCo|Testclient Sentinel'

_roster_path() {
  if [ -n "${OPENCLAW_CLIENT_ROSTER:-}" ]; then printf '%s\n' "$OPENCLAW_CLIENT_ROSTER"
  else printf '%s\n' "${HOME:-/root}/.openclaw/client-roster.txt"; fi
}
_roster_regex() {
  local f; f="$(_roster_path)"
  [ -f "$f" ] || return 1
  local out; out="$(grep -vE '^[[:space:]]*(#|$)' "$f" | paste -sd'|' -)"
  [ -n "$out" ] || return 1
  printf '%s\n' "$out"
}

BANNED="$OPERATOR_BANNED|$PLACEHOLDER_BANNED"
if CLIENT_REGEX="$(_roster_regex)"; then
  BANNED="$BANNED|$CLIENT_REGEX"
else
  echo "WARNING: client-name roster not found (looked in \$OPENCLAW_CLIENT_ROSTER," \
       "then $(_roster_path)); SKIPPING the roster-specific client-name scan. Operator" \
       "and .example placeholder tokens are still enforced. See" \
       "scripts/client-roster.example.txt to enable the full check." >&2
fi

echo "=== qc-no-personal-data (Skill 39): UNIVERSAL-skill identifier gate ==="
echo "skill dir : $SKILL_DIR"
echo ""

HITS=0
TREE_HITS="$(
  grep -rinE "$BANNED" "$SKILL_DIR" \
    --exclude-dir='.git' \
    --exclude="$SELF_NAME" \
    2>/dev/null || true
)"
if [ -n "$TREE_HITS" ]; then
  echo "Banned identifiers found in the skill tree:"
  printf '%s\n' "$TREE_HITS" | sed 's/^/  [HIT] /'
  HITS=$(printf '%s\n' "$TREE_HITS" | grep -c .)
fi

# SK1-20: the F52 event emitter (property-lookup.sh) MUST be PII-free — it may
# log only an opaque address_hash + coarse city/state/zip. Fail if it is ever
# changed back to persisting a raw "address" or "street" field.
_plookup="$SKILL_DIR/scripts/property-lookup.sh"
if [ -f "$_plookup" ]; then
  PII_EMITTER_HITS="$(grep -nE '"(address|street)"[[:space:]]*:' "$_plookup" || true)"
  if [ -n "$PII_EMITTER_HITS" ]; then
    echo ""
    echo "Raw-PII field(s) in the F52 event emitter (must be address_hash + city/state/zip only):"
    printf '%s\n' "$PII_EMITTER_HITS" | sed 's/^/  [PII] /'
    HITS=$(( HITS + $(printf '%s\n' "$PII_EMITTER_HITS" | grep -c .) ))
  fi
fi

echo ""
if [ "$HITS" -eq 0 ]; then
  echo "RESULT: PASS — no real personal/client identifiers in Skill 39 (UNIVERSAL)."
  exit 0
else
  echo "RESULT: FAIL — $HITS banned-identifier occurrence(s). Replace each with a generic placeholder."
  exit 1
fi
