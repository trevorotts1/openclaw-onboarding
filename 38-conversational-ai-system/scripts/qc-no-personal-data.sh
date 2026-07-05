#!/usr/bin/env bash
# qc-no-personal-data.sh — machine-enforce that the UNIVERSAL Skill 38 contains
# ZERO real personal / client identifiers, anywhere — in the skill source OR in
# the output it generates.
#
# ROOT CAUSE this gate kills: the templates + source playbook were originally
# authored using the operator + a live client as the worked example, so real
# names leaked into client-facing Notion docs. A UNIVERSAL skill must be free of
# every real person, business, hostname, token, location id, phone, and email.
#
# WHAT IT SCANS:
#   1. The ENTIRE skill tree (every text file under the skill root) EXCEPT this
#      gate itself (which must name the banned identifiers in its patterns).
#   2. The GENERATED client reference sheet — it drives
#      scripts/21-generate-client-reference-sheet.sh in an offline sandbox
#      (Layer-3 markdown) and scans the rendered output too, so a regression that
#      reintroduces a name into generated output fails the build.
#
# BANNED IDENTIFIERS (case-insensitive, word-ish boundaries where it matters):
#   client names/businesses ... EXTERNALIZED. The real client roster is loaded at
#                       runtime from $OPENCLAW_CLIENT_ROSTER or
#                       ~/.openclaw/client-roster.txt (gitignored; template at
#                       scripts/client-roster.example.txt). No real client name is
#                       hardcoded here anymore.
#   operator-static tokens (NOT client data — kept inline, always scanned):
#                       the operating brand token, the operator chat id, operator
#                       email handle, and operator home paths.
#   placeholder tokens (always scanned) ... the obviously-fake names from
#                       client-roster.example.txt; if any appear in tracked
#                       content they are a template leak → hard fail.
#   (NOTE: the client-domain token "zerohumanworkforce" is intentionally NOT
#    banned — it is used inside a leak-DETECTION regex in another gate, so banning
#    it here would false-positive against our own tooling.)
#
# TWO MODES: with the roster present (operator box / pre-commit) the full client
# roster is scanned; with it absent (e.g. CI) the roster-specific scan is SKIPPED
# with a WARNING but the operator-static + placeholder tokens are STILL scanned,
# so the gate never fails open.
#
# A generic placeholder (<CLIENT_BUSINESS_NAME>, <PUBLIC_HOSTNAME>, <HOOKS_TOKEN>,
# <LOCATION_ID>, <OPERATOR_TELEGRAM_CHAT_ID>, "the operator", "your setup admin",
# "a live client") is what every real identifier must be replaced with.
#
# Exit codes: 0 = clean (no banned identifier anywhere);
#             1 = one or more banned identifiers found.
#
# BASH only (grep core) — respects qc-static's .py claude-/anthropic ban.
#
# Usage:
#   bash scripts/qc-no-personal-data.sh
#   bash scripts/qc-no-personal-data.sh --skill-dir DIR
#   bash scripts/qc-no-personal-data.sh --no-gen   # skip the generator sandbox scan

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SCAN_GEN=1
SELF_NAME="$(basename "$0")"

while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    --no-gen)    SCAN_GEN=0; shift ;;
    -h|--help)   sed -n '1,46p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

# ─── Externalized client roster + always-on operator/placeholder tokens ───────
# Operator-static tokens (NOT client data): the operating brand token, operator
# chat id, operator email handle, operator home paths. Always scanned.
OPERATOR_BANNED='blackceo|5252140759|trevelynotts|Trevor|/Users/christy|/Users/blackceomacmini|/Users/client'
# Placeholder names from client-roster.example.txt — always scanned; a hit means
# the tracked template leaked into real content.
PLACEHOLDER_BANNED='ExampleClientAlpha|ExampleClientBeta|PlaceholderCo|Testclient Sentinel'

_roster_path() {
  if [ -n "${OPENCLAW_CLIENT_ROSTER:-}" ]; then printf '%s\n' "$OPENCLAW_CLIENT_ROSTER"
  else printf '%s\n' "${HOME:-/root}/.openclaw/client-roster.txt"; fi
}
# Join the roster's non-comment lines with '|' into an ERE alternation.
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

HITS=0

scan_file() {
  # scan a single file; print + count any banned-identifier hits.
  local f="$1"
  local out
  out="$(grep -rinE "$BANNED" "$f" 2>/dev/null || true)"
  if [ -n "$out" ]; then
    printf '%s\n' "$out" | while IFS= read -r line; do echo "  [HIT] $line"; done
    HITS=$((HITS + $(printf '%s\n' "$out" | grep -c .)))
  fi
}

echo "=== qc-no-personal-data: UNIVERSAL-skill identifier gate ==="
echo "skill dir : $SKILL_DIR"
echo ""

# ---- 1. scan the skill tree (exclude .git + this gate file) ----
TREE_HITS="$(
  grep -rIinE "$BANNED" "$SKILL_DIR" \
    --exclude-dir='.git' \
    --exclude-dir='__pycache__' \
    --exclude='*.pyc' \
    --exclude="$SELF_NAME" \
    2>/dev/null || true
)"
if [ -n "$TREE_HITS" ]; then
  echo "Banned identifiers found in the skill tree:"
  printf '%s\n' "$TREE_HITS" | sed 's/^/  [HIT] /'
  HITS=$((HITS + $(printf '%s\n' "$TREE_HITS" | grep -c .)))
fi

# ---- 2. scan the GENERATED client reference sheet (offline sandbox) ----
GEN_SCRIPT="$SKILL_DIR/scripts/21-generate-client-reference-sheet.sh"
if [ "$SCAN_GEN" = "1" ] && [ -f "$GEN_SCRIPT" ]; then
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  MFD="$TMP/master-files"; mkdir -p "$MFD"
  # PATH without openclaw so the generator stays offline (Layer-3 markdown).
  SANDBOX_PATH=""; IFS=':' read -ra _p <<< "$PATH"
  for p in "${_p[@]}"; do [ -x "$p/openclaw" ] && continue
    if [ -z "$SANDBOX_PATH" ]; then SANDBOX_PATH="$p"; else SANDBOX_PATH="$SANDBOX_PATH:$p"; fi; done
  [ -n "$SANDBOX_PATH" ] || SANDBOX_PATH="$PATH"
  env -i HOME="$TMP" PATH="$SANDBOX_PATH" \
    MASTER_FILES_DIR="$MFD" \
    PUBLIC_HOSTNAME="claw.example.com" \
    ROUTE_ID="HOOKID" HOOK_NAME="HOOKID" AGENT_ID="main" ROUTING_AGENT_ID="main" \
    HOOKS_TOKEN="hooks_qc_no_pii_dummy_token" \
    CLIENT_BUSINESS_NAME="QC No-PII Test Co" \
    CLIENT_TELEGRAM_CHAT_ID="0" \
    SKILL38_TEMPLATES_DIR="$SKILL_DIR/templates" \
    bash "$GEN_SCRIPT" >"$TMP/gen.log" 2>&1 || true
  GEN_HITS="$(grep -rIinE "$BANNED" "$MFD" 2>/dev/null || true)"
  if [ -n "$GEN_HITS" ]; then
    echo ""
    echo "Banned identifiers found in GENERATED client output:"
    printf '%s\n' "$GEN_HITS" | sed 's/^/  [HIT] /'
    HITS=$((HITS + $(printf '%s\n' "$GEN_HITS" | grep -c .)))
  fi
fi

echo ""
if [ "$HITS" -eq 0 ]; then
  echo "RESULT: PASS — no real personal/client identifiers in the skill or its generated output (UNIVERSAL)."
  exit 0
else
  echo "RESULT: FAIL — $HITS banned-identifier occurrence(s). Replace each with a generic placeholder"
  echo "        (<CLIENT_BUSINESS_NAME> / <PUBLIC_HOSTNAME> / <HOOKS_TOKEN> / <LOCATION_ID> /"
  echo "        <OPERATOR_TELEGRAM_CHAT_ID> / \"the operator\" / \"your setup admin\" / \"a live client\")."
  exit 1
fi
