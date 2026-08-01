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
#   - STEP A2 (fleet approval gate, SPEC Item 10): immediately after the
#     Cloudflare key check (Rule 10 requires that check stay first among
#     prerequisites), asks the Item 1 fleet-wide standing endpoint whether THIS
#     box is approved for the conversational_ai system at all
#     (fleet_standing.good_standing && conversational_ai_approved). FAILS
#     CLOSED on any unreachable/non-200/malformed/unrecognised response. See
#     the step's own inline comment for the full contract and why it is a
#     shell-native equivalent of 59-anthology-engine/scripts/standing_gate.py
#     rather than an import of it.
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
# STEP A2 — Fleet approval gate (SPEC Item 10): conversational_ai standing
# ----------------------------------------------------------------------------
# WHAT: refuses to proceed past this point when THIS box's fleet_standing row
# is not approved for the conversational_ai system
# (good_standing===true && conversational_ai_approved===true, computed at
# read time by the Item 1 endpoint — never stored, never guessed here). Runs
# immediately after the Cloudflare key check (Rule 10 requires that check
# stay first among prerequisites) and BEFORE every other check below (skills
# 05/10/19/29 presence + version + connectivity, the caf/Kie preflights, and
# the Command Center task card) — nothing past this point has spent anything
# yet, so a refusal here costs nothing.
#
# WHY: conversational_ai_approved is a real column on every fleet_standing
# row and, before this step, nothing in Skill 38 ever read it — the operator
# ratified this system as gated ("we want to get that skill set also if
# they're not in good standing").
#
# THIS IS A SHELL-NATIVE EQUIVALENT of 59-anthology-engine/scripts/
# standing_gate.py (Item 2's proven gate), NOT an import of it: this file
# must not assume 59-anthology-engine is installed on this box — STEP B below
# is this file's OWN existing model for a cross-skill dependency (it checks
# another skill's directory is present before relying on it); Skill 38 has no
# such dependency on Skill 59 today and this item does not create one. A box
# that has only ever had Skill 38 rolled onto it (no anthology engine folder
# on disk at all) must still be able to run this check. The CONTRACT matches
# standing_gate.py exactly: identical env var names and defaults, identical
# curl-config-on-stdin secret hygiene (the header value never touches argv, a
# log line, or an error message), identical fail-closed matrix (unreachable
# endpoint, non-200, a missing credential, an unparseable body, or an
# unrecognised reason_code are ALL treated as NOT approved), and the same
# never-guess-a-reason rule — reason_code is passed through byte-for-byte
# from the endpoint's own response, or left empty when the gate itself could
# not be evaluated (an infra failure is never dressed up as a specific
# business reason).
#
# CREDENTIAL MODEL: reuses the SAME already-fleet-propagated env vars the
# legacy roster gate and standing_gate.py both use —
# FLEET_STANDING_GATE_HEADER / FLEET_STANDING_GATE_SECRET /
# FLEET_STANDING_BOX_SLUG (seeded fleet-wide by
# scripts/fleet-standing/propagate-fleet-standing-gate.sh) — the SAME n8n
# httpHeaderAuth credential that authenticates system-standing-check. No new
# secret needs provisioning on any box that already has the legacy
# propagation.
#
# URL RESOLUTION (deliberately NO hardcoded literal endpoint in this file —
# Skill 38 is the UNIVERSAL skill and scripts/qc-no-personal-data.sh machine-
# enforces that no operator-specific hostname is ever baked into its source):
# an explicit FLEET_SYSTEM_STANDING_CHECK_URL / FLEET_SYSTEM_ACCESS_REJECTION_
# NOTIFY_URL env var wins if set; otherwise the origin (scheme+host) is
# derived at RUNTIME from the already-fleet-propagated FLEET_STANDING_GATE_URL
# (the legacy roster gate's own endpoint, seeded onto every box by the same
# propagate-fleet-standing-gate.sh) with the correct webhook path appended —
# so a box with the existing legacy propagation needs nothing new to reach
# the Item 1 endpoint. If neither resolves, the gate fails closed (a missing
# URL is treated exactly like an unreachable endpoint), never guesses.
#
# FAIL CLOSED, always. Idempotent (read-only network calls; never writes).
STANDING_SYSTEM="conversational_ai"

# Derive an origin (scheme://host) from FLEET_STANDING_GATE_URL and append a
# given webhook path. Prints nothing and returns 1 if the base var is unset.
_standing_derive_url() {
  local base="${FLEET_STANDING_GATE_URL:-}" scheme="" rest="" host=""
  [ -n "$base" ] || return 1
  scheme="${base%%://*}"
  rest="${base#*://}"
  [ "$scheme" != "$base" ] || return 1
  host="${rest%%/*}"
  [ -n "$host" ] || return 1
  printf '%s://%s/%s' "$scheme" "$host" "$1"
}

STANDING_CHECK_URL="${FLEET_SYSTEM_STANDING_CHECK_URL:-}"
if [ -z "$STANDING_CHECK_URL" ]; then
  STANDING_CHECK_URL="$(_standing_derive_url "webhook/system-standing-check")" || STANDING_CHECK_URL=""
fi
STANDING_NOTIFY_URL="${FLEET_SYSTEM_ACCESS_REJECTION_NOTIFY_URL:-}"
if [ -z "$STANDING_NOTIFY_URL" ]; then
  STANDING_NOTIFY_URL="$(_standing_derive_url "webhook/system-access-rejection-notify")" || STANDING_NOTIFY_URL=""
fi
STANDING_HEADER_NAME="${FLEET_STANDING_GATE_HEADER:-X-Fleet-Standing-Secret}"
STANDING_HEADER_VALUE="${FLEET_STANDING_GATE_SECRET:-}"

# box_slug resolution: 1. explicit env  2. openclaw.json env.vars  3. hostname
# — identical in spirit to standing_gate.py's resolve_box_slug() / update-
# skills.sh's fleet_standing_resolve_slug(), so a box already provisioned for
# the legacy gate needs nothing new to answer this question either.
_standing_resolve_box_slug() {
  if [ -n "${FLEET_STANDING_BOX_SLUG:-}" ]; then
    printf '%s' "$FLEET_STANDING_BOX_SLUG"
    return 0
  fi
  local oc_json=""
  if [ -n "${OC_JSON:-}" ] && [ -f "${OC_JSON:-}" ]; then
    oc_json="$OC_JSON"
  elif [ -f "$HOME/.openclaw/openclaw.json" ]; then
    oc_json="$HOME/.openclaw/openclaw.json"
  elif [ -f "/data/.openclaw/openclaw.json" ]; then
    oc_json="/data/.openclaw/openclaw.json"
  fi
  if [ -n "$oc_json" ] && command -v python3 >/dev/null 2>&1; then
    local v=""
    v="$(python3 -c '
import json, sys
try:
    d = json.load(open(sys.argv[1], encoding="utf-8"))
    v = ((d.get("env") or {}).get("vars") or {}).get("FLEET_STANDING_BOX_SLUG", "")
    print(str(v).strip())
except Exception:
    print("")
' "$oc_json" 2>/dev/null)" || v=""
    if [ -n "$v" ]; then
      printf '%s' "$v"
      return 0
    fi
  fi
  hostname -s 2>/dev/null | cut -d. -f1 || true
}
STANDING_BOX_SLUG="$(_standing_resolve_box_slug)"

# is_transient: mirrors standing_gate.py's _is_transient() exactly (empty/000
# or any 5xx is a transient failure worth one retry; anything else is not).
_standing_is_transient() {
  case "$1" in
    ""|"000") return 0 ;;
    5??) return 0 ;;
    *) return 1 ;;
  esac
}

# POST a JSON body via curl; the header value rides a curl config on STDIN
# (`curl -K -`), never argv, never disk — mirrors podbean_publish.sh's and
# standing_gate.py's proven secret-hygiene idiom exactly. One bounded retry on
# a transient failure only. Prints "BODY\nHTTPCODE"; never raises.
_standing_curl_post() {
  local url="$1" body="$2" cfg="" attempt=1 raw="" code=""
  cfg="$(mktemp 2>/dev/null)" || { printf '\n'; return 0; }
  {
    printf 'request = "POST"\n'
    printf 'url = "%s"\n' "$url"
    printf 'silent\nshow-error\nlocation\n'
    printf 'max-time = 10\n'
    printf 'header = "Content-Type: application/json"\n'
    if [ -n "$STANDING_HEADER_NAME" ] && [ -n "$STANDING_HEADER_VALUE" ]; then
      printf 'header = "%s: %s"\n' "$STANDING_HEADER_NAME" "$STANDING_HEADER_VALUE"
    fi
  } > "$cfg"
  while :; do
    raw="$(curl -K "$cfg" --data-binary "$body" -w '\n%{http_code}' 2>/dev/null)" || raw=""
    code="${raw##*$'\n'}"
    if _standing_is_transient "$code" && [ "$attempt" -lt 2 ]; then
      attempt=$((attempt + 1))
      continue
    fi
    break
  done
  rm -f "$cfg" 2>/dev/null || true
  printf '%s' "$raw"
}

_standing_approved="0"
_standing_reason_code=""
_standing_note=""

if [ -z "$STANDING_BOX_SLUG" ]; then
  _standing_note="box_slug could not be resolved"
elif [ -z "$STANDING_CHECK_URL" ] || [ -z "$STANDING_NOTIFY_URL" ]; then
  _standing_note="standing-check URL could not be resolved (set FLEET_SYSTEM_STANDING_CHECK_URL / FLEET_SYSTEM_ACCESS_REJECTION_NOTIFY_URL, or ensure FLEET_STANDING_GATE_URL is propagated on this box)"
elif [ -z "$STANDING_HEADER_VALUE" ]; then
  _standing_note="FLEET_STANDING_GATE_SECRET not set on this box"
else
  _standing_body="$(printf '{"system":"%s","box_slug":"%s"}' "$STANDING_SYSTEM" "$STANDING_BOX_SLUG")"
  _standing_raw="$(_standing_curl_post "$STANDING_CHECK_URL" "$_standing_body")"
  _standing_code="${_standing_raw##*$'\n'}"
  _standing_resp="${_standing_raw%$'\n'*}"
  if [ "$_standing_code" != "200" ]; then
    _standing_note="standing-check returned HTTP ${_standing_code:-<none>}"
  elif ! command -v python3 >/dev/null 2>&1; then
    _standing_note="python3 not available to parse standing-check response — refusing (fail closed)"
  else
    _standing_verdict="$(printf '%s' "$_standing_resp" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    if not isinstance(d, dict) or d.get("ok") is not True or "approved" not in d:
        print("MALFORMED")
    elif d.get("approved") is True:
        print("APPROVED")
    else:
        rc = d.get("reason_code") or ""
        if rc in ("standing", "not_enrolled"):
            print("REFUSED:" + rc)
        else:
            print("REFUSED:")
except Exception:
    print("MALFORMED")
' 2>/dev/null)" || _standing_verdict="MALFORMED"
    case "$_standing_verdict" in
      APPROVED) _standing_approved="1" ;;
      REFUSED:*)
        _standing_reason_code="${_standing_verdict#REFUSED:}"
        _standing_note="not approved (${_standing_reason_code:-reason_code unrecognized})"
        ;;
      *) _standing_note="unexpected response shape from standing-check" ;;
    esac
  fi
fi

if [ "$_standing_approved" != "1" ]; then
  echo "$PASS_PREFIX BLOCKED: this box is not currently approved for the conversational_ai system."
  case "$_standing_reason_code" in
    standing)
      echo "  reason: there is a standing matter to resolve (fleet_standing.good_standing is false)." ;;
    not_enrolled)
      echo "  reason: the account is in good standing; conversational_ai has not been added yet (fleet_standing.conversational_ai_approved is false)." ;;
    *)
      echo "  reason: could not be determined — ${_standing_note:-standing-check unavailable}." ;;
  esac
  echo "  Skill 38 will NOT proceed. This is a fleet approval-gate refusal (Item 10), not a technical error to work around."
  # Best-effort notify; NEVER changes the refusal decision above and never
  # blocks on a failure — mirrors standing_gate.py's notify_rejection().
  _standing_notify_body="$(printf '{"system":"%s","box_slug":"%s","reason":"%s"}' \
    "$STANDING_SYSTEM" "$STANDING_BOX_SLUG" "$_standing_reason_code")"
  _standing_notify_raw="$(_standing_curl_post "$STANDING_NOTIFY_URL" "$_standing_notify_body")"
  _standing_notify_code="${_standing_notify_raw##*$'\n'}"
  echo "  rejection notifier called (HTTP ${_standing_notify_code:-<none>})"
  exit 1
fi
echo "$PASS_PREFIX conversational_ai standing check OK (box approved). Proceeding."

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
