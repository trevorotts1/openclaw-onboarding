#!/usr/bin/env bash
# ============================================================
# wire-ghl-env.sh — Skill 44 GHL credential env-wiring (single source)
# ============================================================
#
# WHY THIS EXISTS (VPS env-inheritance bug reproduction, 2026-06-11):
#   The skill-44 installer left the GOHIGHLEVEL_* creds ONLY in
#   /data/.openclaw/secrets/.env — a file the OpenClaw gateway/agent PROCESS
#   never loads. When the agent invoked `caf`, the gateway's process env had
#   no GOHIGHLEVEL_LOCATION_ID, so the engine died at:
#       "Error: GHL_LOCATION_ID environment variable is not set."
#   while the install had already reported success.
#
#   Worse, on the Hostinger VPS the docker-compose `env_file`
#   (/docker/<project>/.env) carried EMPTY placeholder lines —
#   `GOHIGHLEVEL_API_KEY=` with no value, and no FIREBASE line at all.
#   docker-compose injects an empty `env_file` value as an EMPTY STRING into
#   the container process env. An empty string still "wins" against the secrets
#   file for any consumer that reads os.environ directly, so it MASKED the real
#   value even after it was added elsewhere. Empty placeholders must be REPLACED,
#   not merely appended-after.
#
# WHAT THIS SCRIPT DOES (idempotent):
#   1. Wires all 5 canonical GHL vars into openclaw.json `env.vars` (the block
#      the gateway inherits at process start). Uses `openclaw config set` first,
#      and FALLS BACK to a direct JSON deep-merge into openclaw.json when
#      `config set` rejects the nested key — the supported pattern on
#      OpenClaw 2026.5.20+ (see 31-upgraded-memory-system/scripts/activate-memory-stack.sh).
#   2. VPS ONLY: ALSO populates the host docker-compose env_file
#      (/docker/<project>/.env), REPLACING any empty `GOHIGHLEVEL_*=` placeholder
#      lines in place (they override real values with empty strings). Reachable
#      only from the host — skipped automatically when /docker is not visible
#      (e.g. when running inside the container).
#   3. MAC ONLY: wires env.vars but does NOT restart the gateway (rescue-Mac
#      rule). Prints a note that a `launchctl kickstart` may be needed for the
#      running gateway to inherit the new env.vars.
#
# The 5 canonical vars (engine wrapper maps GOHIGHLEVEL_* -> GHL_*):
#   GOHIGHLEVEL_API_KEY                 (PIT — required)
#   GOHIGHLEVEL_LOCATION_ID             (required)
#   GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN  (optional — workflow writes only)
#   GOHIGHLEVEL_ALLOWED_LOCATION_IDS    (write-location whitelist)
#   GOHIGHLEVEL_DRAFT_ONLY              (write-safety default)
#
# Inputs (read from process env OR the canonical secrets file):
#   GOHIGHLEVEL_API_KEY / GOHIGHLEVEL_LOCATION_ID / GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN
#   GOHIGHLEVEL_ALLOWED_LOCATION_IDS (defaults to GOHIGHLEVEL_LOCATION_ID)
#   GOHIGHLEVEL_DRAFT_ONLY (defaults to "true")
#
# Env overrides:
#   OC_JSON           — path to openclaw.json (auto-detected otherwise)
#   OC_SECRETS_ENV    — path to secrets/.env  (auto-detected otherwise)
#   DOCKER_ENV_FILE   — explicit host docker-compose env_file path (VPS)
#   SKILL44_NO_DOCKER_ENV=1 — skip the docker env_file step entirely
#
# Exit codes:
#   0 — wired what was present (a missing OPTIONAL var is not a failure)
#   2 — a REQUIRED var (API_KEY or LOCATION_ID) was absent everywhere; the
#       caller should mark the skill installed-with-missing-prereqs.
# ============================================================

set -euo pipefail

log() { echo "[wire-ghl-env] $*"; }

# ─── Path detection (VPS container layout vs Mac) ────────────────────────────
if [ -z "${OC_JSON:-}" ]; then
  if [ -f /data/.openclaw/openclaw.json ]; then
    OC_JSON="/data/.openclaw/openclaw.json"
  else
    OC_JSON="$HOME/.openclaw/openclaw.json"
  fi
fi
if [ -z "${OC_SECRETS_ENV:-}" ]; then
  if [ -d /data/.openclaw ]; then
    OC_SECRETS_ENV="/data/.openclaw/secrets/.env"
  else
    OC_SECRETS_ENV="$HOME/.openclaw/secrets/.env"
  fi
fi

# Platform: vps when the container /data layout is present, else mac.
if [ -d /data/.openclaw ]; then
  PLATFORM="vps"
else
  PLATFORM="mac"
fi

log "platform: $PLATFORM"
log "openclaw.json: $OC_JSON"
log "secrets/.env:  $OC_SECRETS_ENV"

# ─── Load values from the canonical secrets file if not already in env ───────
# We do NOT `set -a; source` the whole file (it may contain syntactically odd
# lines); we grep each var by name (last hit wins, like the engine wrapper).
read_secret() {
  local var="$1"
  [ -f "$OC_SECRETS_ENV" ] || { echo ""; return 0; }
  # grep may find nothing (exit 1) — that is fine, we want an empty string, not
  # a non-zero return that would trip `set -e` in the calling `VAR=$(read_secret)`.
  local out
  out="$(grep -E "^[[:space:]]*(export[[:space:]]+)?${var}=" "$OC_SECRETS_ENV" 2>/dev/null \
    | tail -1 | sed -E "s/^[[:space:]]*(export[[:space:]]+)?${var}=//" \
    | sed -E 's/^"(.*)"$/\1/; s/^'\''(.*)'\''$/\1/' || true)"
  echo "$out"
  return 0
}

# ─── Full 11-alias PIT resolver (first match wins; covers all legacy alias names) ─
_resolve_any_pit() { for _v in GOHIGHLEVEL_API_KEY GHL_API_KEY GHL_PIT GHL_TOKEN GHL_PRIVATE_INTEGRATION_TOKEN PRIVATE_INTEGRATION_TOKEN GHL_PRIVATE_TOKEN PIT_TOKEN GHL_PIT_TOKEN GOHIGHLEVEL_LOCATION_PIT GHL_LOCATION_PIT; do local _val="${!_v:-}"; [ -z "$_val" ] && _val="$(read_secret "$_v")"; [ -n "$_val" ] && printf '%s' "$_val" && return; done; return 0; }

API_KEY="${GOHIGHLEVEL_API_KEY:-$(read_secret GOHIGHLEVEL_API_KEY)}"
[ -z "$API_KEY" ] && API_KEY="$(_resolve_any_pit)"
LOCATION_ID="${GOHIGHLEVEL_LOCATION_ID:-$(read_secret GOHIGHLEVEL_LOCATION_ID)}"
FIREBASE="${GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN:-$(read_secret GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN)}"
ALLOWED="${GOHIGHLEVEL_ALLOWED_LOCATION_IDS:-$(read_secret GOHIGHLEVEL_ALLOWED_LOCATION_IDS)}"
DRAFT_ONLY="${GOHIGHLEVEL_DRAFT_ONLY:-$(read_secret GOHIGHLEVEL_DRAFT_ONLY)}"

# Sensible defaults: whitelist seeds from the client's own location; draft-only on.
[ -z "$ALLOWED" ] && ALLOWED="$LOCATION_ID"
[ -z "$DRAFT_ONLY" ] && DRAFT_ONLY="true"

# ─── Required-var gate ───────────────────────────────────────────────────────
MISSING=""
[ -z "$API_KEY" ]     && MISSING="$MISSING GOHIGHLEVEL_API_KEY"
[ -z "$LOCATION_ID" ] && MISSING="$MISSING GOHIGHLEVEL_LOCATION_ID"
if [ -n "$MISSING" ]; then
  log "MISSING-PREREQS: required var(s) absent everywhere:${MISSING}"
  log "  Skill 44 is installed-with-missing-prereqs. Add the value(s) to"
  log "  $OC_SECRETS_ENV (and re-run this script) before caf can reach GHL."
  exit 2
fi

# ─── 1. Wire into openclaw.json env.vars (gateway-inherited) ─────────────────
# Try `openclaw config set` first; fall back to a direct JSON deep-merge if it
# rejects the nested key ("Invalid input" on 2026.5.20+ when env.vars is absent).
wire_var() {
  local var="$1"; local val="$2"
  [ -z "$val" ] && return 0   # skip optional vars with no value
  if command -v openclaw >/dev/null 2>&1 \
     && openclaw config set "env.vars.$var" "$val" >/dev/null 2>&1; then
    log "config set env.vars.$var (via openclaw config set)"
    return 0
  fi
  # Fallback: direct JSON deep-merge.
  VAR="$var" VAL="$val" OC_JSON="$OC_JSON" python3 - <<'PYEOF'
import json, os
from pathlib import Path
p = Path(os.environ['OC_JSON'])
try:
    d = json.loads(p.read_text())
except Exception:
    d = {}
d.setdefault('env', {}).setdefault('vars', {})[os.environ['VAR']] = os.environ['VAL']
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(d, indent=2) + "\n")
print("[wire-ghl-env] env.vars.%s (via JSON deep-merge fallback)" % os.environ['VAR'])
PYEOF
}

log "wiring env.vars into $OC_JSON ..."
# ── Canonical LOCATION-PIT alias set (all mean the same credential; first hit wins) ──
# Wiring all aliases ends the wiring↔engine mismatch: wire-ghl-env.sh previously wrote
# only GOHIGHLEVEL_* names, but ghl_client.py read only GHL_API_KEY → resolved to empty
# → 401 crash-loop (root cause: a client-box GHL-MCP crash-loop, 2026-06).
# GHL PIT aliases: see TERMINOLOGY.md for the canonical alias set.
wire_var GOHIGHLEVEL_API_KEY                "$API_KEY"    # preferred canonical name
wire_var GHL_API_KEY                        "$API_KEY"    # legacy short alias
wire_var GHL_PIT                            "$API_KEY"    # short alias
wire_var GHL_TOKEN                          "$API_KEY"    # alternate alias
wire_var GHL_PRIVATE_INTEGRATION_TOKEN      "$API_KEY"    # explicit full-name alias
wire_var PRIVATE_INTEGRATION_TOKEN          "$API_KEY"    # bare PIT alias
wire_var GHL_PRIVATE_TOKEN                  "$API_KEY"    # shortened private-token alias
wire_var PIT_TOKEN                          "$API_KEY"    # short PIT alias
wire_var GHL_PIT_TOKEN                      "$API_KEY"    # combined PIT alias
wire_var GOHIGHLEVEL_LOCATION_PIT           "$API_KEY"    # explicit LOCATION-PIT name
wire_var GHL_LOCATION_PIT                   "$API_KEY"    # explicit LOCATION-PIT short alias
wire_var GOHIGHLEVEL_LOCATION_ID            "$LOCATION_ID"
wire_var GOHIGHLEVEL_ALLOWED_LOCATION_IDS   "$ALLOWED"
wire_var GOHIGHLEVEL_DRAFT_ONLY             "$DRAFT_ONLY"
wire_var GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN "$FIREBASE"   # no-op when absent

# ─── 1b. Wire the FUNNEL + AUTOMATION matcher catalog/index/link env vars ────
# Without these, the Skill-6 STEP-0 funnel matcher (v2_dispatcher) and the Skill-44
# Step-0.4 automation matcher stay DARK on a real box (env-gated, never activated).
# Resolve relative to the installed skills (06 and 44 are siblings under the skills
# dir). Wire each var ONLY when its target exists — a stale path would just be a safe
# no-op for the matchers, but we keep openclaw.json clean.
ENGINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL44_DIR="$(cd "$ENGINE_DIR/../.." && pwd)"            # 44-convert-and-flow-operator
SKILLS_ROOT="$(cd "$SKILL44_DIR/.." && pwd)"              # skills dir (06 & 44 are siblings)
SKILL06_DIR="$SKILLS_ROOT/06-ghl-install-pages"
FUNNEL_CATALOG="$SKILL06_DIR/funnel-templates"
FUNNEL_INDEX="$SKILL06_DIR/tools/catalog-index.json"
AUTO_CATALOG="$SKILL44_DIR/automation-templates"
AUTO_INDEX="$SKILL44_DIR/automation-templates/_matcher/catalog-index.json"
LINK_MAP="$SKILL44_DIR/automation-templates/_links/funnel-to-automation.json"

wire_var_if_exists() {  # $1=VAR  $2=path  ($3=dir|file, default file)
  local var="$1" path="$2" kind="${3:-file}"
  if { [ "$kind" = "dir" ] && [ -d "$path" ]; } || { [ "$kind" = "file" ] && [ -f "$path" ]; }; then
    wire_var "$var" "$path"
  else
    log "skip $var — target not present ($path)"
  fi
}

wire_var_if_exists GHL_FUNNEL_CATALOG            "$FUNNEL_CATALOG" dir
wire_var_if_exists GHL_FUNNEL_INDEX              "$FUNNEL_INDEX"   file
wire_var_if_exists GHL_FUNNEL_AUTOMATION_LINKS   "$LINK_MAP"       file
wire_var_if_exists CAF_AUTOMATION_CATALOG        "$AUTO_CATALOG"   dir
wire_var_if_exists CAF_AUTOMATION_INDEX          "$AUTO_INDEX"     file
wire_var_if_exists CAF_FUNNEL_AUTOMATION_LINKS   "$LINK_MAP"       file

# chown back to the runtime user on the VPS container layout.
if [ "$PLATFORM" = "vps" ] && [ "$OC_JSON" = "/data/.openclaw/openclaw.json" ]; then
  chown node:node "$OC_JSON" 2>/dev/null || true
fi

# ─── 2. VPS: populate the host docker-compose env_file, replacing placeholders ─
# docker-compose injects empty `env_file` values as empty strings into the
# container process env, which MASK the real value (VPS env-inheritance bug). So any empty
# `GOHIGHLEVEL_*=` line MUST be replaced in place, not appended-after.
wire_docker_env() {
  local envfile="$1"
  [ -f "$envfile" ] || return 0
  log "docker env_file: $envfile"

  # var=value pairs to enforce. Empty values are still written so an empty
  # placeholder gets overwritten with the real value (or removed below).
  _upsert() {
    local var="$1"; local val="$2"
    # If the value is empty AND there is an existing non-empty line, leave the
    # existing line. If the value is empty AND the existing line is an empty
    # placeholder, DELETE the placeholder (an absent var is far safer than an
    # empty-string override that masks env.vars / secrets).
    if [ -z "$val" ]; then
      if grep -qE "^[[:space:]]*${var}=[[:space:]]*$" "$envfile"; then
        log "  removing empty placeholder ${var}= (would mask real value as empty string)"
        grep -vE "^[[:space:]]*${var}=[[:space:]]*$" "$envfile" > "$envfile.tmp" && mv "$envfile.tmp" "$envfile"
      fi
      return 0
    fi
    # Non-empty value: replace any existing line (placeholder or stale) in place.
    if grep -qE "^[[:space:]]*${var}=" "$envfile"; then
      grep -vE "^[[:space:]]*${var}=" "$envfile" > "$envfile.tmp" && mv "$envfile.tmp" "$envfile"
      log "  replacing existing ${var}= line"
    fi
    printf '%s=%s\n' "$var" "$val" >> "$envfile"
  }

  _upsert GOHIGHLEVEL_API_KEY                "$API_KEY"
  _upsert GOHIGHLEVEL_LOCATION_ID            "$LOCATION_ID"
  _upsert GOHIGHLEVEL_ALLOWED_LOCATION_IDS   "$ALLOWED"
  _upsert GOHIGHLEVEL_DRAFT_ONLY             "$DRAFT_ONLY"
  _upsert GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN "$FIREBASE"

  log "  NOTE: apply with: docker compose -f $(dirname "$envfile")/docker-compose.yml up -d --force-recreate"
  log "        (a plain 'docker restart' does NOT re-read env_file)"
}

if [ "${SKILL44_NO_DOCKER_ENV:-0}" != "1" ]; then
  if [ -n "${DOCKER_ENV_FILE:-}" ]; then
    wire_docker_env "$DOCKER_ENV_FILE"
  elif [ -d /docker ]; then
    # Host context: find the project dir(s) under /docker that hold an OpenClaw
    # compose env_file. Only touch ones that already reference OpenClaw/GHL so we
    # never write into an unrelated project's env.
    _touched=0
    for _ef in /docker/*/.env; do
      [ -f "$_ef" ] || continue
      if grep -qE 'OPENCLAW|GOHIGHLEVEL|GHL_' "$_ef" 2>/dev/null; then
        wire_docker_env "$_ef"
        _touched=1
      fi
    done
    [ "$_touched" = "0" ] && log "no OpenClaw docker env_file found under /docker (running inside container? — env.vars wiring above is the gateway-inherited path)"
  else
    log "/docker not visible (likely running inside the container) — skipping host env_file; env.vars wiring above is the gateway-inherited path"
  fi
fi

# ─── 3. Validate + platform-specific restart guidance ────────────────────────
if command -v openclaw >/dev/null 2>&1; then
  if ! openclaw config validate >/dev/null 2>&1; then
    log "WARNING: 'openclaw config validate' reported an issue after wiring — run 'openclaw doctor --fix' and re-validate."
  else
    log "openclaw config validate: clean"
  fi
fi

if [ "$PLATFORM" = "mac" ]; then
  log "MAC: env.vars wired. NOT restarting the gateway (rescue-Mac rule)."
  log "     The RUNNING gateway will not inherit the new env.vars until it is"
  log "     restarted. If caf reports a missing var from inside the agent, run:"
  log "       launchctl kickstart -k gui/\$(id -u)/ai.openclaw.gateway"
else
  log "VPS: env.vars wired into $OC_JSON; host env_file updated (if reachable)."
  log "     Apply with a force-recreate so the container re-reads env_file."
fi

log "DONE."
exit 0
