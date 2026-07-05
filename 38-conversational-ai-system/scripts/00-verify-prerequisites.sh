#!/usr/bin/env bash
# 00-verify-prerequisites.sh — Skill 38 (Conversational AI System)
# Verifies all install prerequisites BEFORE any v5.14 step runs.
#
# Governed by Sub-Agent Handoff and Mandatory QC Protocol (see ../../QC-PROTOCOL.md):
#   - Part 3 Rules 10-15: Cloudflare API key check (must come FIRST)
#   - Category 10 = 10 rubric: presence + version + functional state checks
#                              for skills 05, 10, 19, 29 (hard prereqs); halt with
#                              a clear error naming the failure; never auto-update
#                              skill 10.
#   - STEP F (non-fatal): Skill 44 (convert-and-flow-operator) is the Tier-0
#     "caf-direct" workflow BUILD path (Option 1). We PREFLIGHT caf + the Firebase
#     token and REPORT the active build path (Option 1 caf-direct vs Option 2
#     manual Build-with-AI paste). Skill 44 is required for Option 1 but is NOT a
#     hard prereq — Skill 29 (the runtime GHL connection) is.
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

The walk-through content lives in the guide shipped INSIDE this skill:

  references/fleet-onboarding-tunnel-provisioning-field-guide.md

(That guide is the verbatim School of AI step-by-step: 4 parts, ~30 minutes,
walks you through the Cloudflare account, GoDaddy nameservers, and the
9-permission API token creation. The Google Doc version
https://docs.google.com/document/d/1A_U-H-MMLh2mQ_zhzLxK_tKmFyPNb7i0FNvxjJ4SVpo/edit?usp=sharing
is the canonical source if you prefer to view it in Google Docs.)

>>> AGENT — DO NOT just dump a `cat` of the guide. When the client has NO
>>> Cloudflare API token, PROACTIVELY OFFER the client a choice of TWO paths,
>>> then act on whichever they pick:
>>>
>>>   (a) NOTION DOC — create a NEW Notion doc IN THE CLIENT'S OWN Notion
>>>       workspace (never another client's, never a shared/operator
>>>       workspace) containing the full content of
>>>       references/fleet-onboarding-tunnel-provisioning-field-guide.md, then send the client
>>>       the link so they can follow it at their own pace; OR
>>>
>>>   (b) MANUAL WALKTHROUGH — walk the client through the guide step by step,
>>>       live, answering questions as they go.
>>>
>>> Ask which they prefer, then do it. Only fall back to printing the guide
>>> inline if the client explicitly asks for the raw text.

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
# first; this skill REFUSES to auto-update skill 10 (per the operator's rules).
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

# Accept the CANONICAL cred names (GOHIGHLEVEL_API_KEY / GOHIGHLEVEL_LOCATION_ID)
# AND the legacy/PIT aliases so a box that has drifted to either naming passes.
# Key = the GHL API key or Private Integration Token; Loc = the sub-account id.
GHL_KEY_NAMES="GOHIGHLEVEL_API_KEY GHL_PRIVATE_INTEGRATION_TOKEN GHL_API_KEY GOHIGHLEVEL_AGENCY_PIT GHL_PIT_TOKEN"
GHL_LOC_NAMES="GOHIGHLEVEL_LOCATION_ID GHL_LOCATION_ID"

# 0 if the file defines ANY of the given var names as KEY=... (export-aware).
_file_has_any() {
  local f="$1"; shift
  local n
  for n in $1; do
    grep -qE "^[[:space:]]*(export[[:space:]]+)?${n}[[:space:]]*=" "$f" 2>/dev/null && return 0
  done
  return 1
}

ghl_ok=""
# Search the canonical secrets stores too (secrets/.env subdir, VPS /data path).
for f in "$HOME/.openclaw/secrets/.env" "$HOME/.openclaw/.env" "$HOME/.openclaw/secrets.env" "$HOME/.openclaw/openclaw.env" "$MFD/.env" "$MFD/secrets.env" "/data/.openclaw/secrets/.env"; do
  [ -f "$f" ] || continue
  if _file_has_any "$f" "$GHL_KEY_NAMES" && _file_has_any "$f" "$GHL_LOC_NAMES"; then
    ghl_ok="$f"; break
  fi
done
if [ -z "$ghl_ok" ]; then
  key_env=""; loc_env=""
  for n in $GHL_KEY_NAMES; do [ -n "${!n:-}" ] && { key_env=1; break; }; done
  for n in $GHL_LOC_NAMES; do [ -n "${!n:-}" ] && { loc_env=1; break; }; done
  [ -n "$key_env" ] && [ -n "$loc_env" ] && ghl_ok="shell environment"
fi
if [ -z "$ghl_ok" ]; then
  echo "$PASS_PREFIX BLOCKED: skill 29 (GHL Convert and Flow) is installed but Convert and Flow is not connected."
  echo "  Need a GHL API key/PIT (GOHIGHLEVEL_API_KEY or GHL_PRIVATE_INTEGRATION_TOKEN or GHL_API_KEY) AND a location id (GOHIGHLEVEL_LOCATION_ID or GHL_LOCATION_ID) in an env file or the shell."
  echo "  Re-run skill 29 to connect your GHL location, then re-run this prereq check."
  exit 1
fi
echo "$PASS_PREFIX skill 29 connectivity OK ($ghl_ok)"

# ----------------------------------------------------------------------------
# STEP F — Skill 44 (caf) build-path preflight + ACTIVE BUILD PATH report
# ----------------------------------------------------------------------------
# NON-FATAL / informational. Skill 44 (convert-and-flow-operator) is the Tier-0
# "caf-direct" workflow BUILD path (Option 1). When caf + a Firebase refresh
# token are present, builds run through Skill 44 directly; otherwise builds fall
# back to the manual Build-with-AI paste (Option 2). This NEVER blocks — Skill 29
# (the runtime GHL connection, STEP E) is the hard prerequisite. We only REPORT
# which build path is active so a client is never SILENTLY stuck on Option 2.
FIREBASE_TOKEN_NAMES="GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN CAF_FIREBASE_REFRESH_TOKEN GHL_FIREBASE_REFRESH_TOKEN"

caf_present=""
if command -v caf >/dev/null 2>&1; then
  caf_present="caf on PATH"
elif [ -x "$HOME/.openclaw/tools/convert-and-flow-cli/caf" ]; then
  caf_present="$HOME/.openclaw/tools/convert-and-flow-cli/caf"
elif [ -d "$SKILLS_DIR/44-convert-and-flow-operator" ]; then
  caf_present="skill 44 installed ($SKILLS_DIR/44-convert-and-flow-operator)"
fi

fb_present=""
for f in "$HOME/.openclaw/secrets/.env" "$HOME/.openclaw/.env" "$HOME/.openclaw/secrets.env" "$HOME/.openclaw/openclaw.env" "$MFD/.env" "$MFD/secrets.env" "/data/.openclaw/secrets/.env"; do
  [ -f "$f" ] || continue
  if _file_has_any "$f" "$FIREBASE_TOKEN_NAMES"; then fb_present="$f"; break; fi
done
if [ -z "$fb_present" ]; then
  for n in $FIREBASE_TOKEN_NAMES; do [ -n "${!n:-}" ] && { fb_present="shell environment"; break; }; done
fi

if [ -n "$caf_present" ] && [ -n "$fb_present" ]; then
  echo "$PASS_PREFIX BUILD PATH = Option 1 (caf-direct, Skill 44 Tier 0) ACTIVE — caf found ($caf_present) + Firebase token present ($fb_present). Workflow builds run through Skill 44 directly."
elif [ -n "$caf_present" ]; then
  echo "$PASS_PREFIX BUILD PATH = Option 2 (manual Build-with-AI paste) — caf found ($caf_present) but NO Firebase refresh token (checked GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN). Grab the Convert-and-Flow token to enable the reliable caf-direct Option 1."
else
  echo "$PASS_PREFIX BUILD PATH = Option 2 (manual Build-with-AI paste) — Skill 44 (caf) not detected. Builds use the manual paste path. Install Skill 44 (convert-and-flow-operator) + grab the Firebase token for the reliable caf-direct Option 1."
fi
# NOTE: runtime conversational I/O (send/read/calendars) uses the location PIT
# regardless of the BUILD path above — the daily watcher is
# scripts/check-ghl-pit-liveness.sh (cron ghl-pit-liveness, registered by 04).

# ----------------------------------------------------------------------------
# STEP G - Kie.ai hero-visual preflight (U-11) + HERO PATH report
# ----------------------------------------------------------------------------
# NON-FATAL / informational. The U-11 workflow visual ships a FREE, deterministic
# Mermaid truth diagram on every build regardless. The stylized Kie HERO image is an
# optional extra that needs KIE_API_KEY (Skill 07). This never blocks the install: we
# only REPORT whether the hero path is ACTIVE or the build is Mermaid-only, so a client
# is never silently left wondering where the pretty picture went. Appended over the
# current file so the PR #511 Command Center ACTIVE/INACTIVE lines below stay intact.
KIE_KEY_NAMES="KIE_API_KEY"
kie_present=""
for f in "$HOME/.openclaw/secrets/.env" "$HOME/.openclaw/.env" "$HOME/.openclaw/secrets.env" "$HOME/.openclaw/openclaw.env" "$MFD/.env" "$MFD/secrets.env" "/data/.openclaw/secrets/.env"; do
  [ -f "$f" ] || continue
  if _file_has_any "$f" "$KIE_KEY_NAMES"; then kie_present="$f"; break; fi
done
if [ -z "$kie_present" ]; then
  for n in $KIE_KEY_NAMES; do [ -n "${!n:-}" ] && { kie_present="shell environment"; break; }; done
fi
if [ -n "$kie_present" ]; then
  echo "$PASS_PREFIX HERO VISUAL PATH = ACTIVE (KIE_API_KEY found at $kie_present). Builds ship the Mermaid truth diagram PLUS the Kie hero image (budget-capped; U-11)."
else
  echo "$PASS_PREFIX HERO VISUAL PATH = Mermaid-only (no KIE_API_KEY; checked the env stores + shell). The FREE truth diagram still ships on every build; the hero image is skipped until Skill 07 + KIE_API_KEY are present. See protocols/workflow-visual-protocol.md."
fi

# ----------------------------------------------------------------------------
# DONE
# ----------------------------------------------------------------------------
echo
echo "$PASS_PREFIX ALL PREREQUISITES PASS — proceeding to install Phase 0."

# Command Center Kanban: create-or-reuse the install task and move it to
# in_progress (install is starting). FAIL-SOFT — cc-task.sh always exits 0 and
# the `|| true` guarantees it can NEVER change this script's exit code. No-ops
# silently when the Command Center is absent.
#
# Report whether Command Center reporting is wired (FIX-S36-07): cc-task.sh no-ops
# unless MC_API_TOKEN is set, so the install task silently never lands on the board
# when it is missing. Print an explicit ACTIVE/INACTIVE line so the operator sees
# the state instead of guessing. (MC_API_TOKEN + the optional MC_SKILL38_SOP_ID /
# MC_SKILL38_AGENT_ID Triad are documented in INSTALL.md.)
if [ -n "${MC_API_TOKEN:-}" ]; then
  echo "$PASS_PREFIX Command Center reporting: ACTIVE (MC_API_TOKEN set — the install task will be carded to the board)."
else
  echo "$PASS_PREFIX Command Center reporting: INACTIVE (MC_API_TOKEN not set — install continues; set MC_API_TOKEN [+ MC_SKILL38_SOP_ID / MC_SKILL38_AGENT_ID] to card this install on the Command Center — see INSTALL.md)."
fi
bash "$(dirname "$0")/cc-task.sh" start || true

exit 0
