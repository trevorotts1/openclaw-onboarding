#!/usr/bin/env bash
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
ROSTER_LOADED=0
if CLIENT_REGEX="$(_roster_regex)"; then
  BANNED="$BANNED|$CLIENT_REGEX"
  ROSTER_LOADED=1
else
  echo "FAIL: roster not found" >&2
fi
echo "=== qc-no-personal-data (Skill 39) ==="
echo "skill dir : $SKILL_DIR"
echo ""
HITS=0
TREE_HITS="$(grep -rinE "$BANNED" "$SKILL_DIR" --exclude-dir='.git' --exclude="$SELF_NAME" 2>/dev/null || true)"
if [ -n "$TREE_HITS" ]; then
  echo "Banned identifiers found:"
  printf '%s\n' "$TREE_HITS" | sed 's/^/  [HIT] /'
  HITS=$(printf '%s\n' "$TREE_HITS" | grep -c .)
fi
_plookup="$SKILL_DIR/scripts/property-lookup.sh"
if [ -f "$_plookup" ]; then
  PII_EMITTER_HITS="$(grep -nE '"(address|street)"[[:space:]]*:' "$_plookup" || true)"
  if [ -n "$PII_EMITTER_HITS" ]; then
    echo ""
    echo "Raw-PII field(s) in F52 event emitter:"
    printf '%s\n' "$PII_EMITTER_HITS" | sed 's/^/  [PII] /'
    HITS=$(( HITS + $(printf '%s\n' "$PII_EMITTER_HITS" | grep -c .) ))
  fi
fi
echo ""
if [ "$ROSTER_LOADED" -eq 0 ]; then
  echo "RESULT: FAIL — roster was NOT loaded."
  exit 1
elif [ "$HITS" -eq 0 ]; then
  echo "RESULT: PASS — no real personal/client identifiers in Skill 39."
  exit 0
else
  echo "RESULT: FAIL — $HITS banned-identifier occurrence(s)."
  exit 1
fi
