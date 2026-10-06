#!/usr/bin/env bash
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SELF_NAME="$(basename "$0")"
while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    -h|--help) sed -n '1,12p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done
# Operator chat ids — loaded from the single authority (id-removal v25.3.19):
# shared-utils/resolve-owner-chat.sh declares OPERATOR_CHAT_IDS_SH; never
# hardcode ids here.
_operator_chat_ids_sh() {
  local resolver="" d t
  if [ -d /data/.openclaw ]; then resolver="/data/.openclaw/skills/shared-utils/resolve-owner-chat.sh"
  else resolver="${HOME:-/root}/.openclaw/skills/shared-utils/resolve-owner-chat.sh"; fi
  if [ ! -r "$resolver" ]; then
    d="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd 2>/dev/null || true)"
    for t in "$d/../../shared-utils/resolve-owner-chat.sh" \
             "$d/../../../shared-utils/resolve-owner-chat.sh"; do
      if [ -r "$t" ]; then resolver="$t"; break; fi
    done
  fi
  [ -r "$resolver" ] || return 1
  sed -nE 's/^OPERATOR_CHAT_IDS_SH="([^"]*)".*/\1/p' "$resolver" | head -1
}
OPERATOR_CHAT_IDS_SH="$(_operator_chat_ids_sh || true)"
OPERATOR_BANNED='blackceo|trevelynotts|Trevor|/Users/christy|/Users/blackceomacmini|/Users/client'
if [ -n "${OPERATOR_CHAT_IDS_SH:-}" ]; then
  OPERATOR_BANNED="$OPERATOR_BANNED|$(printf '%s' "$OPERATOR_CHAT_IDS_SH" | tr ' ' '|')"
else
  echo "WARNING: operator chat-id authority (shared-utils/resolve-owner-chat.sh) not readable; the operator chat ids are NOT scanned this run." >&2
fi

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
  # TWO-MODE contract, matching the sanctioned behaviour already shipped in
  # 38-conversational-ai-system/scripts/qc-no-personal-data.sh: with the roster
  # present (operator box / pre-commit) the full client roster is scanned; with it
  # absent (CI has no roster, by design — the roster is gitignored so no real client
  # name ever enters the repo) the roster-specific alternation is SKIPPED while the
  # always-on operator + placeholder token scan still runs and still fails the build
  # on a hit. Hard-failing on "no roster" made this gate un-runnable in CI: the
  # path-filtered workflow that calls it turned red on ANY change under this skill,
  # regardless of content, because there is literally no roster to scan against.
  echo "WARNING: client-name roster not found (looked in \$OPENCLAW_CLIENT_ROSTER," \
       "then $(_roster_path)); SKIPPING the roster-specific client-name scan." \
       "Operator and placeholder tokens are still enforced. See" \
       "scripts/client-roster.example.txt to enable the full check." >&2
fi
echo "=== qc-no-personal-data (Skill 40) ==="
echo "skill dir : $SKILL_DIR"
echo ""
HITS=0
TREE_HITS="$(grep -rinE "$BANNED" "$SKILL_DIR" --exclude-dir='.git' --exclude="$SELF_NAME" 2>/dev/null || true)"
if [ -n "$TREE_HITS" ]; then
  echo "Banned identifiers found:"
  printf '%s\n' "$TREE_HITS" | sed 's/^/  [HIT] /'
  HITS=$(printf '%s\n' "$TREE_HITS" | grep -c .)
fi
echo ""
if [ "$HITS" -eq 0 ]; then
  [ "$ROSTER_LOADED" -eq 0 ] && echo "(roster absent — operator/placeholder tokens enforced, roster-specific scan skipped)"
  echo "RESULT: PASS — no real personal/client identifiers in Skill 40."
  exit 0
else
  echo "RESULT: FAIL — $HITS banned-identifier occurrence(s)."
  exit 1
fi
