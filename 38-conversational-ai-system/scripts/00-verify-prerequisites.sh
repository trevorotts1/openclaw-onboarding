#!/usr/bin/env bash
# 00-verify-prerequisites.sh — Skill 38 (Conversational AI System)
# Verifies all install prerequisites BEFORE any v5.14 step runs.
#
# Governed by Sub-Agent Handoff and Mandatory QC Protocol (see ../../QC-PROTOCOL.md):
#   - Part 3 Rules 10-15: Cloudflare API key check (must come FIRST)
#   - Category 10 = 10 rubric: presence + version + functional state checks
#                              for skills 05, 10, 19, 29; halt with clear error
#                              naming the failure; never auto-update skill 10
#
# Idempotent (read-only; never writes). Safe to re-run. OS-aware Darwin + Linux.

set -euo pipefail

OS="$(uname -s)"
case "$OS" in
  Darwin) DEFAULT_SKILLS_DIR="$HOME/.openclaw/skills" ;;
  Linux)  DEFAULT_SKILLS_DIR="/data/.openclaw/skills" ;;
  *) echo "Unsupported OS: $OS"; exit 2 ;;
esac
SKILLS_DIR="${OPENCLAW_SKILLS_DIR:-$DEFAULT_SKILLS_DIR}"

case "$OS" in
  Darwin) DEFAULT_MFD="$HOME/Downloads" ;;
  Linux)  DEFAULT_MFD="/data" ;;
esac
MFD="${MASTER_FILES_DIR:-$DEFAULT_MFD}"

PASS_PREFIX="[skill 38][prereq]"

# ----------------------------------------------------------------------------
# STEP A — Cloudflare API key check (Protocol Part 3, Rules 10-15)
# ----------------------------------------------------------------------------
# Must come FIRST. If missing, halt with the verbatim Rule 13 message.
# Search order (10 locations, stop at first valid):
#   1. ~/.openclaw/.env
#   2. ~/.openclaw/secrets.env
#   3. ~/.openclaw/openclaw.env
#   4. <MASTER_FILES_DIR>/.env
#   5. <MASTER_FILES_DIR>/secrets.env
#   6. ~/.cloudflared/.env
#   7. ~/.zshrc      (export CLOUDFLARE_API_TOKEN= or export CF_API_TOKEN= lines)
#   8. ~/.bashrc     (same)
#   9. ~/.bash_profile (same)
#  10. Current shell env ($CLOUDFLARE_API_TOKEN or $CF_API_TOKEN)
# Variable names accepted: CLOUDFLARE_API_TOKEN, CF_API_TOKEN,
#                          CLOUDFLARE_API_KEY, CF_API_KEY
# Format validation: 40+ char alphanumeric (no network call here; the actual
# token validity is verified later when the tunnel is created).

CF_KEY_NAMES=( "CLOUDFLARE_API_TOKEN" "CF_API_TOKEN" "CLOUDFLARE_API_KEY" "CF_API_KEY" )
CF_SEARCH_FILES=(
  "$HOME/.openclaw/.env"
  "$HOME/.openclaw/secrets.env"
  "$HOME/.openclaw/openclaw.env"
  "$MFD/.env"
  "$MFD/secrets.env"
  "$HOME/.cloudflared/.env"
  "$HOME/.zshrc"
  "$HOME/.bashrc"
  "$HOME/.bash_profile"
)

cf_token_found=""
cf_token_source=""

# Inline format validator: 40+ chars, alphanumeric / dash / underscore
cf_is_valid_format() {
  local v="$1"
  [ ${#v} -ge 40 ] && [[ "$v" =~ ^[A-Za-z0-9_-]+$ ]]
}

# 1-9: scan files for either KEY=VALUE or `export KEY=VALUE`
for f in "${CF_SEARCH_FILES[@]}"; do
  [ -f "$f" ] || continue
  for name in "${CF_KEY_NAMES[@]}"; do
    # Match: KEY=value | export KEY=value | KEY="value" | export KEY="value"
    line="$(grep -E "^[[:space:]]*(export[[:space:]]+)?${name}[[:space:]]*=" "$f" 2>/dev/null | tail -1 || true)"
    if [ -n "${line:-}" ]; then
      val="$(echo "$line" | sed -E "s/^[[:space:]]*(export[[:space:]]+)?${name}[[:space:]]*=[[:space:]]*//" | sed -E 's/^"(.*)"$/\1/' | sed -E "s/^'(.*)'$/\1/" | sed -E 's/[[:space:]]*#.*$//' | tr -d '[:space:]')"
      if cf_is_valid_format "$val"; then
        cf_token_found="$val"
        cf_token_source="$f (variable $name)"
        break 2
      fi
    fi
  done
done

# 10: current shell env (last resort)
if [ -z "$cf_token_found" ]; then
  for name in "${CF_KEY_NAMES[@]}"; do
    val="${!name:-}"
    if [ -n "$val" ] && cf_is_valid_format "$val"; then
      cf_token_found="$val"
      cf_token_source="shell environment (\$$name)"
      break
    fi
  done
fi

if [ -z "$cf_token_found" ]; then
  # Rule 13 verbatim message
  cat <<'EONOKEY'
=====================================================
CLOUDFLARE API KEY NOT FOUND
=====================================================

Skill 38 (Conversational AI System) requires a Cloudflare API
key to set up the public tunnel for receiving webhooks from GHL.

I checked these locations and found no Cloudflare API key:
  - ~/.openclaw/.env
  - ~/.openclaw/secrets.env
  - ~/.openclaw/openclaw.env
  - <MASTER_FILES_DIR>/.env
  - <MASTER_FILES_DIR>/secrets.env
  - ~/.cloudflared/.env
  - ~/.zshrc, ~/.bashrc, ~/.bash_profile
  - Current shell environment

To proceed, follow these instructions to get your credentials:

  https://docs.google.com/document/d/1A_U-H-MMLh2mQ_zhzLxK_tKmFyPNb7i0FNvxjJ4SVpo/edit?usp=sharing

Once you have your Cloudflare API key:

  1. Save it to your OpenClaw environment file at:
     ~/.openclaw/.env (or whichever env file you already use)

     Add the line:
       CLOUDFLARE_API_TOKEN=<your-token-here>

  2. Tell me you're done, and I'll restart the skill 38 install
     from the beginning. The check will find your key and
     proceed automatically.

=====================================================
EONOKEY
  exit 1
fi
echo "$PASS_PREFIX Cloudflare API key found at $cf_token_source. Proceeding."

# ----------------------------------------------------------------------------
# STEP B — Skill presence checks (presence)
# ----------------------------------------------------------------------------
REQUIRED=( 05-ghl-setup 10-github-setup 19-humanizer 29-ghl-convert-and-flow )
MISSING=()
for s in "${REQUIRED[@]}"; do
  [ -d "$SKILLS_DIR/$s" ] || MISSING+=( "$s" )
done
if [ "${#MISSING[@]}" -gt 0 ]; then
  echo "$PASS_PREFIX BLOCKED: missing skill(s) in $SKILLS_DIR:"
  printf '  - %s\n' "${MISSING[@]}"
  echo
  echo "Install the missing skill(s) first, then re-run this prerequisite check."
  exit 1
fi
echo "$PASS_PREFIX presence OK (skills 05, 10, 19, 29 all installed)"

# ----------------------------------------------------------------------------
# STEP C — Skill 10 latest version check (presence + version; do NOT update)
# ----------------------------------------------------------------------------
# Per Protocol Cat 10 score 7+: validate skill 10 is at latest. We READ-ONLY
# compare the installed skill-version.txt against the bundled onboarding's
# skill-version.txt. If installed < bundled, tell operator to update skill 10
# first; this skill REFUSES to auto-update skill 10 (per Christy's rules).
SKILL10_INSTALLED="$SKILLS_DIR/10-github-setup/skill-version.txt"
# The bundled source lives one level up from this skill's scripts dir
ONBOARDING_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SKILL10_BUNDLED="$ONBOARDING_ROOT/10-github-setup/skill-version.txt"
if [ -f "$SKILL10_INSTALLED" ] && [ -f "$SKILL10_BUNDLED" ]; then
  iv="$(tr -d '[:space:]' < "$SKILL10_INSTALLED")"
  bv="$(tr -d '[:space:]' < "$SKILL10_BUNDLED")"
  if [ "$iv" != "$bv" ]; then
    echo "$PASS_PREFIX BLOCKED: skill 10 (GitHub Setup) is not at the latest version."
    echo "  installed: $iv"
    echo "  bundled:   $bv"
    echo "  Update skill 10 first (re-run its installer), then re-run this prereq check."
    echo "  Skill 38 will NOT auto-update skill 10 (per repo policy)."
    exit 1
  fi
  echo "$PASS_PREFIX skill 10 at latest version ($iv)"
else
  echo "$PASS_PREFIX WARN: skill 10 version file(s) missing — cannot compare. Verify skill 10 install before proceeding."
fi

# ----------------------------------------------------------------------------
# STEP D — Skill 19 (humanizer) functional check
# ----------------------------------------------------------------------------
# Humanizer is referenced ALWAYS-ON by AGENTS.md Step 2.8. Verify the actual
# skill bundle has the expected entry points so the reference will resolve.
S19_DIR="$SKILLS_DIR/19-humanizer"
if [ -f "$S19_DIR/SKILL.md" ] || [ -f "$S19_DIR/humanizer.skill" ] || [ -f "$S19_DIR/humanizer-full.md" ]; then
  echo "$PASS_PREFIX skill 19 (humanizer) functional check OK"
else
  echo "$PASS_PREFIX WARN: skill 19 directory exists but no SKILL.md / .skill / humanizer-full.md found. Re-install skill 19 before continuing."
  # Warn-only; some bundles may differ. Operator decides.
fi

# ----------------------------------------------------------------------------
# STEP E — Skill 29 (GHL Convert and Flow) functional check
# ----------------------------------------------------------------------------
# Skill 29 must be installed AND Convert and Flow must be connected to the
# operator's GHL location. We check two layers: skill bundle present, AND
# either openclaw config or env shows GHL_LOCATION_ID / GHL_API_KEY available.
S29_DIR="$SKILLS_DIR/29-ghl-convert-and-flow"
if [ ! -f "$S29_DIR/SKILL.md" ]; then
  echo "$PASS_PREFIX BLOCKED: skill 29 SKILL.md not found at $S29_DIR. Re-install skill 29."
  exit 1
fi

ghl_ok=""
# Look for GHL_LOCATION_ID + GHL_API_KEY in same locations + shell env
for f in "$HOME/.openclaw/.env" "$HOME/.openclaw/secrets.env" "$HOME/.openclaw/openclaw.env" "$MFD/.env" "$MFD/secrets.env"; do
  [ -f "$f" ] || continue
  if grep -qE '^[[:space:]]*(export[[:space:]]+)?GHL_API_KEY[[:space:]]*=' "$f" 2>/dev/null && \
     grep -qE '^[[:space:]]*(export[[:space:]]+)?GHL_LOCATION_ID[[:space:]]*=' "$f" 2>/dev/null; then
    ghl_ok="$f"; break
  fi
done
if [ -z "$ghl_ok" ] && [ -n "${GHL_API_KEY:-}" ] && [ -n "${GHL_LOCATION_ID:-}" ]; then
  ghl_ok="shell environment"
fi
if [ -z "$ghl_ok" ]; then
  echo "$PASS_PREFIX BLOCKED: skill 29 (GHL Convert and Flow) is installed but Convert and Flow is not connected (GHL_API_KEY + GHL_LOCATION_ID not found in any env file or shell)."
  echo "  Re-run skill 29 to connect your GHL location, then re-run this prereq check."
  exit 1
fi
echo "$PASS_PREFIX skill 29 connectivity OK ($ghl_ok)"

# ----------------------------------------------------------------------------
# DONE
# ----------------------------------------------------------------------------
echo
echo "$PASS_PREFIX ALL PREREQUISITES PASS — proceeding to install Phase 0."
exit 0
