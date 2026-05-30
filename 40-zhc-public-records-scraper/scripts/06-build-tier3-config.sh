#!/usr/bin/env bash
# 06-build-tier3-config.sh — Skill 40
# Interactive builder for an operator Tier-3 scraper CONFIG. Prompts for the
# portal URL, search-form fields, and result selectors, writes a config from the
# template, then VALIDATES it (via 05-validate-target.sh --tier3) before it can
# be used live. NEVER scrapes during the build. Idempotent (re-running rebuilds
# the named config). Supports a non-interactive mode for tests/automation.
#
# Interactive:    ./06-build-tier3-config.sh
# Non-interactive ./06-build-tier3-config.sh --slug my-county --portal https://... \
#                    --search-path /search --tos https://.../terms --county-fips 06037 --state 06

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEMPLATE="$SKILL_ROOT/templates/tier3-config.template.json"
P="[skill 40][tier3-build]"

command -v jq >/dev/null 2>&1 || { echo "$P BLOCKED: jq required"; exit 1; }
[ -f "$TEMPLATE" ] || { echo "$P BLOCKED: template missing: $TEMPLATE"; exit 1; }

OS="$(uname -s)"
case "$OS" in Darwin) DEFMFD="$HOME/Downloads" ;; *) DEFMFD="/data" ;; esac
STATE_FILE="$HOME/.openclaw/.skill-40-master-files-dir"
MFD="${MASTER_FILES_DIR:-}"
[ -z "$MFD" ] && [ -f "$STATE_FILE" ] && MFD="$(tr -d '[:space:]' < "$STATE_FILE" 2>/dev/null || true)"
[ -z "$MFD" ] && MFD="$DEFMFD"
DEST="$MFD/public-records-tier3"
mkdir -p "$DEST" 2>/dev/null || true

SLUG=""; PORTAL=""; SEARCH_PATH="/"; TOS=""; FIPS=""; STATE=""; NONINTERACTIVE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --slug) SLUG="$2"; NONINTERACTIVE=1; shift 2 ;;
    --portal) PORTAL="$2"; shift 2 ;;
    --search-path) SEARCH_PATH="$2"; shift 2 ;;
    --tos) TOS="$2"; shift 2 ;;
    --county-fips) FIPS="$2"; shift 2 ;;
    --state) STATE="$2"; shift 2 ;;
    -h|--help) sed -n '1,16p' "$0"; exit 0 ;;
    *) echo "$P unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ "$NONINTERACTIVE" -eq 0 ]; then
  echo "$P Build a Tier-3 scraper config. (You acknowledge you are responsible for the target's ToS + lawful use.)"
  printf 'Target slug (e.g. my-county-st): '; read -r SLUG
  printf 'Portal base URL (https://...): '; read -r PORTAL
  printf 'Search path (default /): '; read -r SP; [ -n "$SP" ] && SEARCH_PATH="$SP"
  printf 'ToS URL: '; read -r TOS
  printf 'County FIPS (5-digit, optional): '; read -r FIPS
  printf 'State FIPS (2-digit, optional): '; read -r STATE
fi

[ -n "$SLUG" ] || { echo "$P BLOCKED: slug required"; exit 1; }
[ -n "$PORTAL" ] || { echo "$P BLOCKED: portal URL required"; exit 1; }
[ -n "$TOS" ] || { echo "$P BLOCKED: tos_url required (you must reference the target's Terms of Service)"; exit 1; }

OUT="$DEST/$SLUG.json"
jq \
  --arg slug "$SLUG" --arg portal "$PORTAL" --arg sp "$SEARCH_PATH" \
  --arg tos "$TOS" --arg fips "$FIPS" --arg state "$STATE" \
  '.slug=$slug | .portal_url=$portal | .search_path=$sp | .tos_url=$tos
   | .county_fips=$fips | .state=$state | .tier="tier3"' \
  "$TEMPLATE" > "$OUT"
echo "$P wrote Tier-3 config → $OUT"
echo "$P NOTE: fill in .search_form_fields + .selectors in that file (the template has the keys), then validating below."

echo "$P validating the new config (robots + ToS + liveness; NO scrape)…"
if bash "$SCRIPT_DIR/05-validate-target.sh" --tier3 "$OUT"; then
  echo "$P Tier-3 config '$SLUG' VALIDATED — safe to use live (subject to cost caps)."
  exit 0
else
  echo "$P Tier-3 config '$SLUG' did NOT validate — fix it (or treat the target as a Tier-4 honest gap). NEVER fabricate."
  exit 1
fi
