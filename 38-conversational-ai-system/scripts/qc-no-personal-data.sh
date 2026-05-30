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
#   real names ........ Trevor, Teresa, Keez, Christy, Corey, Maria, Angeleen,
#                       Beverly, Evelyn, Monique, Lyric, Kofi, Pelham, Candace,
#                       Marico, Sir Jordan
#   businesses ........ Grants Boutique, Explore Growth, "The Winning Formula
#                       Course", Winning Formula
#   hostnames/domains . thewinningformulacourse, growthriveprosper, blackceo
#   (NOTE: the client-domain token "zerohumanworkforce" is intentionally NOT in the
#    BANNED list — it is a string that the qc-tools-md-ghl-ref.sh gate uses inside a
#    leak-DETECTION regex, so banning it here would false-positive against our own
#    tooling; the operator-domain space is already covered by blackceo/growthriveprosper.)
#   operator chat id .. 5252140759
#   operator emails ... trevelynotts
#   real home paths ... /Users/christy, /Users/blackceomacmini, /Users/client
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

# The banned patterns. Kept as an ERE alternation. Each token here is a REAL
# identifier that must never appear in a universal skill. (This file is excluded
# from the scan, so naming them here is fine.)
BANNED='Trevor|Teresa|Keez|Christy|Corey|Maria|Angeleen|Beverly|Evelyn|Monique|Lyric|Kofi|Pelham|Candace|Marico|Sir Jordan|Grants Boutique|Explore Growth|The Winning Formula Course|Winning Formula|thewinningformulacourse|growthriveprosper|blackceo|5252140759|trevelynotts|/Users/christy|/Users/blackceomacmini|/Users/client'

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
  grep -rinE "$BANNED" "$SKILL_DIR" \
    --exclude-dir='.git' \
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
  GEN_HITS="$(grep -rinE "$BANNED" "$MFD" 2>/dev/null || true)"
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
