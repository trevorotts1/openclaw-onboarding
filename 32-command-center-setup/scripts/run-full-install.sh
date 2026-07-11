#!/usr/bin/env bash
# run-full-install.sh — Skill 32 top-level orchestrator (v12.9.27).
#
# OQ-1 shell-first FLIP (v12.9.27): the LOCKED Command Center shell (BLOCK A —
# Phase 1 prereqs → lock-assert → Phase 6 dashboard deploy → Phase 6h tunnel) now
# deploys BEFORE the interview-complete gate, so the client immediately has a
# /interview surface. The REAL zero-human workforce (BLOCK B — Phase 3/4/5/6b-6f
# seeding, verification, ZHE gate) stays gated on interviewComplete. Safety rests on
# the LOCK-BEFORE-REACHABLE invariant documented in the BLOCK A header: the P0-5
# interview-mode middleware (command-center v4.60.0+) derives its lock purely from
# the build-state file (interviewComplete / buildCompletedAt) this installer already
# writes, so the shell serves LOCKED from its very first request — there is no
# unlocked-empty-board window. Do NOT reorder BLOCK A after the gate.
#
# Why this exists:
#   Skill 32 INSTALL.md describes an 8-phase Command Center activation
#   (prerequisites → Telegram → workspaces → agent config → topics →
#   dashboard deploy → tunnel → verification). For four versions running
#   (v10.14.16 → v10.14.19) that 8-phase doc was PROSE, not code. Skill 37's
#   STEP 1 — Command Center invoked only materialize-dept-agents.sh (Phase 4)
#   and then marked commandCenterStatus=done. Phases 6 (dashboard deploy on
#   :4000), 6b (n8n webhook + cloudflared tunnel), and 7 (verification) never
#   ran on any client. That's why no BlackCEO Command Center dashboard ever
#   came up + Trevor never got n8n notifications for completed builds.
#
# This script is the missing orchestrator. Skill 37 (run-closeout.sh) invokes
# it with client metadata pulled from .workforce-build-state.json. Each phase
# is idempotent (checks "already done" before re-running) and writes its
# result atomically back into the state file so the resume cron can pick up
# from the first un-completed step on any failure or retry.
#
# Usage:
#   bash run-full-install.sh [--update-only] <client-slug> <company-name> <contact-email>
#
#   --update-only  Skip phases already done on a prior full install
#                  (prereqs, workspace folders, agent materialize, tunnel,
#                  Telegram topics). Only runs: git pull + npm install +
#                  CC .env.local provisioning + freshness-gated `next build` +
#                  db:push + sync-departments-from-build-state.py + pm2 restart.
#                  Skips db:seed (protects client-customized rows).
#                  Does NOT re-embed the persona index (live index stays
#                  untouched; honors "client uses own keys").
#
#   In --update-only mode, <client-slug>/<company-name>/<contact-email> are
#   read from .workforce-build-state.json when not supplied on the command line.
#
# Exit codes:
#   0 — all phases succeeded (or were already done)
#   1 — fatal error in a phase that cannot be auto-resumed; state file is
#       updated with commandCenterStatus=failed and the failure reason.

set -u

# ---- --update-only flag parsing ----
# Must happen BEFORE positional args so $@ is clean for the slug/name/email
# assignments below.  The flag may appear in any position.
UPDATE_ONLY=false
_POSITIONAL=()
for _arg in "$@"; do
  case "$_arg" in
    --update-only) UPDATE_ONLY=true ;;
    *) _POSITIONAL+=("$_arg") ;;
  esac
done
set -- "${_POSITIONAL[@]+"${_POSITIONAL[@]}"}"

CLIENT_SLUG="${1:-}"
COMPANY_NAME="${2:-}"
CONTACT_EMAIL="${3:-}"

# In full-install mode all three args are required.
# In --update-only mode they are read from the state file when absent.
if [[ "$UPDATE_ONLY" != "true" ]]; then
  if [[ -z "$CLIENT_SLUG" ]]; then
    echo "Usage: run-full-install.sh [--update-only] <client-slug> <company-name> <contact-email>" >&2; exit 1
  fi
  if [[ -z "$COMPANY_NAME" ]]; then
    echo "run-full-install.sh: missing company name" >&2; exit 1
  fi
  if [[ -z "$CONTACT_EMAIL" ]]; then
    echo "run-full-install.sh: missing contact email" >&2; exit 1
  fi
fi

# ---- platform detection (VPS first, Mac fallback) ----
if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[run-full-install] FATAL: no OpenClaw root found" >&2
  exit 1
fi

STATE_FILE="$OC_ROOT/workspace/.workforce-build-state.json"
LOG_FILE="$OC_ROOT/workspace/.command-center-install.log"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DASHBOARD_REPO="https://github.com/trevorotts1/blackceo-command-center.git"
DASHBOARD_DIR="${HOME}/projects/command-center"
DASHBOARD_PORT=4000
# Box-own OpenClaw config — the ONLY source for this box's gateway auth token
# (fix #2) and its own primary TEXT model (fix #3). Per-box + per-client: never a
# shared/operator value. Read-only here; the token value is never logged/printed.
OC_CONFIG="$OC_ROOT/openclaw.json"

log() {
  printf '%s [%-5s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" >> "$LOG_FILE"
  printf '%s [%-5s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2"
}

state_get() {
  jq -r "$1 // empty" "$STATE_FILE" 2>/dev/null
}

state_set() {
  # Usage: state_set '.field = value | .other = value'
  # NOTE: never bake a free-form/user-derived REASON string into $1 — a reason
  # containing a double-quote or newline would corrupt the state file or inject jq.
  # Use state_set_arg for any value that is not a literal you fully control.
  local tmp
  tmp=$(mktemp)
  if jq "$1" "$STATE_FILE" > "$tmp"; then
    mv "$tmp" "$STATE_FILE"
  else
    rm -f "$tmp"
    log "ERROR" "state_set failed for expr: $1"
    return 1
  fi
}

# state_set_arg — write a jq program that references a single string VALUE passed
# safely via `--arg val` (P3-2). This is the ONLY sanctioned way to persist a
# free-form reason: the value is bound as data, never interpolated into the jq
# program string. Usage: state_set_arg '.field = $val | .other = "lit"' "$reason"
# No-op (returns 0) when the state file is absent, so callers stay simple.
state_set_arg() {
  local prog="$1" val="$2" tmp
  [[ -f "$STATE_FILE" ]] || return 0
  tmp=$(mktemp)
  if jq --arg val "$val" "$prog" "$STATE_FILE" > "$tmp"; then
    mv "$tmp" "$STATE_FILE"
  else
    rm -f "$tmp"
    log "ERROR" "state_set_arg failed for expr: $prog"
    return 1
  fi
}

now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }

fail_install() {
  local reason="$1"
  log "ERROR" "marking commandCenterStatus failed: $reason"
  # P3-2: pass the reason via jq --arg (state_set_arg) instead of interpolating it
  # into the jq program — a reason with a quote/newline no longer corrupts state.
  state_set_arg '.commandCenterStatus = "failed" | .commandCenterFailureReason = $val' "$reason"
  exit 1
}

# ----------------------------------------------------------------------
# Command Center pm2 app-name contract (v16.1.7 — two-CC-on-:4000 root fix)
# ----------------------------------------------------------------------
# The Command Center MUST run under exactly ONE pm2 app name across the whole
# fleet. The fleet-canonical name is "blackceo-command-center" — what this
# installer starts, what every per-box dedup standardizes on, and what the CC
# repo now declares everywhere (ecosystem.config.cjs / scripts/deploy.sh /
# scripts/watchdog-cc.sh / the bootstrap templates, blackceo-command-center
# v4.55.4+). "mission-control" is a LEGACY alias earlier CC revisions used.
#
# Historically, if a box still ran the board under "mission-control" (or the
# older "command-center"), this installer's `pm2 restart blackceo-command-center`
# missed it and the fallback `pm2 start blackceo-command-center` left TWO pm2
# apps both binding :4000, whose `next start` children mutually killed each other
# through cc-start.sh's orphan-port killer — an endless restart loop (47k+
# restarts) that wedged the gateway on a client box.
#
# The fix: reconcile every legacy alias away BEFORE (re)starting, so exactly ONE
# canonical "blackceo-command-center" results regardless of which name the box
# currently runs.
CC_PM2_NAME="blackceo-command-center"
# Every NON-canonical alias the CC has shipped under historically. Deleted before
# each (re)start so a box can never keep a second competing CC on :4000.
CC_PM2_LEGACY_ALIASES="mission-control command-center"

# cc_reconcile_pm2_names — delete every non-canonical CC alias so at most ONE CC
# app (the canonical "$CC_PM2_NAME") can survive the (re)start below. Idempotent:
# a missing app makes `pm2 delete` a harmless no-op.
cc_reconcile_pm2_names() {
  local alias_name
  for alias_name in $CC_PM2_LEGACY_ALIASES; do
    if pm2 delete "$alias_name" >/dev/null 2>&1; then
      log "INFO" "phase=6: reconciled — deleted non-canonical CC pm2 app '$alias_name'"
    fi
  done
}

# cc_pm2_start_canonical — start the board under the canonical name. An explicit
# --name guarantees the canonical regardless of the cloned CC checkout's
# ecosystem.config.cjs (an older pinned CC tag may still name the app
# differently until the CC version is rolled fleet-wide). CC_PORT is pinned so
# cc-start.sh (npm start -> bash scripts/cc-start.sh) strips any ambient PORT and
# binds :4000. Returns the launcher's exit status.
cc_pm2_start_canonical() {
  ( cd "$DASHBOARD_DIR" && CC_PORT="$DASHBOARD_PORT" pm2 start npm --name "$CC_PM2_NAME" -- start >>"$LOG_FILE" 2>&1 )
}

# ======================================================================
# CC CONVERGE DURABLE GUARDS — Kanban-dead recurrence fix (v12.9.31)
# ======================================================================
# ROOT CAUSE (proven on a client box): Phase 6 pulled fresh CC source and ran
# `npm install` — whose `postinstall` only `npm rebuild`s the better-sqlite3
# native addon — then restarted pm2. It NEVER ran `next build`. `npm start` ->
# scripts/cc-start.sh -> `next start` serves the pre-existing `.next` bundle,
# which predates the pulled source. The Next.js instrumentation hook
# (src/instrumentation.ts -> registerCronJobs) that registers the
# intake-advance + backlog-redispatch sweeps is compiled INTO `.next`; a stale
# bundle omits them, so nothing polls the backlog and cards stick in Backlog
# (dispatch_attempts stays 0). Three runtime env vars were also never
# provisioned, so even a fresh build fails closed:
#   * OPENCLAW_GATEWAY_TOKEN empty  -> the Bridge cannot auth to the local
#     gateway (auth.mode=token boxes).
#   * SOVEREIGN_DEFAULT_MODEL unset -> AF-MODEL-SOVEREIGNTY blocks every text
#     dispatch when nothing else resolves a model (null model_id root cause).
#   * MC_API_TOKEN / WEBHOOK_SECRET unset -> newer CC middleware REJECTS the
#     ingest + agent-completion webhooks (fail-closed) unless
#     ALLOW_INSECURE_OPEN_API=true.
#
# The two guards below make a converge self-healing + idempotent:
#   (1) cc_ensure_fresh_build  — rebuild `.next` IFF it is stale vs source.
#   (2)+(3)+(4) cc_write_env_local — additively provision the three env families
#       into CC .env.local (0600) from the box's OWN gateway token + primary TEXT
#       model. Existing operator values are ALWAYS preserved; generated secrets
#       are written once and reused (never rotated). Secret VALUES are never
#       logged/printed — only the key name + a SET/preserved/skipped label.
# ----------------------------------------------------------------------

# _cc_mtime — epoch mtime of a file, portable across BSD (Mac) and GNU (Linux).
_cc_mtime() { stat -f %m "$1" 2>/dev/null || stat -c %Y "$1" 2>/dev/null || echo 0; }

# _cc_gen_secret — a strong random hex secret (openssl -> python3 -> urandom).
_cc_gen_secret() {
  if command -v openssl >/dev/null 2>&1; then openssl rand -hex 32 2>/dev/null && return 0; fi
  if command -v python3 >/dev/null 2>&1; then python3 -c 'import secrets;print(secrets.token_hex(32))' 2>/dev/null && return 0; fi
  head -c 32 /dev/urandom 2>/dev/null | od -An -tx1 | tr -d ' \n'
}

# _cc_model_is_sovereign — exit 0 when the model id is a valid sovereign DEFAULT
# for a TEXT task: non-empty, NOT a free default, and NOT Anthropic-forbidden.
# Mirrors the CC model-selector rules (FORBIDDEN_PREFIXES + `:free`/openrouter
# free) so the value we write is actually HONOURED by resolveSovereignDefault
# rather than silently dropped. Case-insensitive.
_cc_model_is_sovereign() {
  local m
  m="$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')"
  [[ -n "$m" ]] || return 1
  case "$m" in
    openrouter/free|*:free) return 1 ;;                # free default — forbidden
  esac
  case "$m" in
    # Anthropic in any form (never in a client runtime): provider-prefixed routes
    # and BARE claude-* families that carry no `anthropic/` prefix.
    *anthropic*|*claude*) return 1 ;;
  esac
  return 0
}

# cc_resolve_sovereign_model — echo the box's OWN primary TEXT model id (or empty
# when none qualifies). Precedence, first sovereign candidate wins:
#   1. CC_SOVEREIGN_DEFAULT_MODEL env  (explicit operator override, per client)
#   2. .agents.defaults.model.primary  (box-wide default text model)
#   3. main/head agent .model.primary  (list entry named Main/main, else list[0])
#   4. .agents.defaults.model.fallbacks[]  (first sovereign fallback)
#   5. .agents.defaults.model            (plain-string form, if used)
# NEVER a hardcoded shared model — everything is read from THIS box's config.
cc_resolve_sovereign_model() {
  if [[ -n "${CC_SOVEREIGN_DEFAULT_MODEL:-}" ]] && _cc_model_is_sovereign "$CC_SOVEREIGN_DEFAULT_MODEL"; then
    printf '%s' "$CC_SOVEREIGN_DEFAULT_MODEL"; return 0
  fi
  [[ -f "$OC_CONFIG" ]] || { printf ''; return 0; }
  command -v jq >/dev/null 2>&1 || { printf ''; return 0; }
  local candidates cand
  candidates="$(jq -r '
    [ .agents.defaults.model.primary?,
      ( (.agents.list // []) | map(select(.name=="Main" or .name=="main")) | .[0].model.primary? ),
      .agents.list[0].model.primary?,
      ( (.agents.defaults.model.fallbacks? // [])[] ),
      .agents.defaults.model?
    ] | map(select(type=="string" and . != "")) | .[]
  ' "$OC_CONFIG" 2>/dev/null)"
  while IFS= read -r cand; do
    [[ -z "$cand" ]] && continue
    if _cc_model_is_sovereign "$cand"; then printf '%s' "$cand"; return 0; fi
  done <<< "$candidates"
  printf ''
}

# _cc_model_is_ollama_cloud — exit 0 when the id targets the client's Ollama
# Cloud provider (the ONLY sanctioned QC-judge provider). Mirrors the CC
# qc-scorer isOllamaCloudModel(): the registry form ollama-cloud/<m>, the legacy
# ollama/<m>:cloud shape, and a bare <m>:cloud tag (the ':cloud' suffix is
# authoritative). Case-insensitive.
_cc_model_is_ollama_cloud() {
  local m
  m="$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')"
  [[ -n "$m" ]] || return 1
  case "$m" in
    ollama-cloud/*) return 0 ;;
  esac
  [[ "$m" == *":cloud"* ]] && return 0
  return 1
}

# _cc_model_is_reasoning_judge — exit 0 when the id is an ELIGIBLE QC judge:
# a client-owned Ollama Cloud model (above) from a strong GENERAL-REASONING
# family and NOT a code model. QC-08 operator decision (Trevor): the judge must
# be a strong general reasoner — deepseek / glm / qwen3 / gpt-oss / mistral — and
# NEVER a *-code / *-coder model (rejected outright), nor an embedding model.
# Case-insensitive.
_cc_model_is_reasoning_judge() {
  local m
  m="$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')"
  _cc_model_is_ollama_cloud "$m" || return 1
  case "$m" in
    *coder*|*-code*|*code-*|*:code*|*embed*) return 1 ;;   # never a code/embedding model
  esac
  case "$m" in
    *deepseek*|*glm*|*qwen3*|*gpt-oss*|*mistral*|*ministral*|*mixtral*) return 0 ;;
  esac
  return 1
}

# _cc_normalize_judge_id — return the QC_JUDGE_MODEL value from a client model id,
# PRESERVING the client's own naming (the ':cloud' tag) and stripping only a
# leading provider prefix (ollama/ or ollama-cloud/). The CC qc-scorer accepts
# the bare '<m>:cloud' form directly (isOllamaCloudModel matches ':cloud') and
# sends it VERBATIM to the box's Ollama Cloud endpoint — so the judge uses the
# SAME model naming the client's own agents already route through (whatever that
# endpoint is). We deliberately do NOT rewrite '<m>:cloud' -> 'ollama-cloud/<m>':
# that would strip the ':cloud' tag some endpoints require (verified on the
# operator canary — the local Ollama proxy 404s on the bare id, 200s on <m>:cloud).
_cc_normalize_judge_id() {
  local id="${1:-}"
  id="${id#ollama-cloud/}"
  id="${id#ollama/}"
  printf '%s' "$id"
}

# cc_resolve_judge_model — echo a client-owned Ollama Cloud GENERAL-REASONING
# model id to use as the Command Center QC judge (QC-08), or empty when the
# client has none eligible.
#
# ⛔ Sovereignty: the judge MUST be one of THIS client's OWN models — never a
# hardcoded fleet default that could point at another client's key. Source is the
# box's OWN openclaw.json (the same store cc_resolve_sovereign_model reads): the
# ollama / ollama-cloud provider model lists plus the agent model
# defaults/fallbacks. When the client has NO eligible general-reasoning cloud
# model we return EMPTY and the caller leaves QC_JUDGE_MODEL UNSET (fail-closed is
# correct — the CC scorer holds tasks for human review) and logs a clear "judge
# not provisioned — needs a client model" line. We never guess or borrow.
#
# Family precedence (Trevor's decision): deepseek > glm > qwen3 > gpt-oss >
# mistral/ministral. A *-code model is never eligible. An explicit per-client
# operator override (CC_QC_JUDGE_MODEL) still must be a client-owned reasoning
# cloud model.
cc_resolve_judge_model() {
  if [[ -n "${CC_QC_JUDGE_MODEL:-}" ]] && _cc_model_is_reasoning_judge "$CC_QC_JUDGE_MODEL"; then
    _cc_normalize_judge_id "$CC_QC_JUDGE_MODEL"; return 0
  fi
  [[ -f "$OC_CONFIG" ]] || { printf ''; return 0; }
  command -v jq >/dev/null 2>&1 || { printf ''; return 0; }
  local ids
  ids="$(jq -r '
    [ (.models.providers["ollama-cloud"].models[]?.id),
      (.models.providers["ollama"].models[]?.id),
      (.agents.defaults.model.primary?),
      ((.agents.defaults.model.fallbacks? // [])[]),
      ((.agents.list // []) | map(.model.primary?) | .[]),
      ((.agents.list // []) | map(.model.fallbacks? // []) | add // [] | .[])
    ] | map(select(type=="string" and . != "")) | unique | .[]
  ' "$OC_CONFIG" 2>/dev/null)"
  local fam id lid
  for fam in deepseek glm qwen3 gpt-oss mistral ministral; do
    while IFS= read -r id; do
      [[ -z "$id" ]] && continue
      _cc_model_is_reasoning_judge "$id" || continue
      lid="$(printf '%s' "$id" | tr '[:upper:]' '[:lower:]')"
      case "$lid" in
        *"$fam"*) _cc_normalize_judge_id "$id"; return 0 ;;
      esac
    done <<< "$ids"
  done
  printf ''
}

# cc_env_has_nonempty — exit 0 when KEY exists in the env file with a non-empty
# value. (KEY is [A-Z_]+ here, so it carries no regex metacharacters.)
cc_env_has_nonempty() {
  local file="$1" key="$2"
  [[ -f "$file" ]] || return 1
  grep -qE "^[[:space:]]*${key}=[^[:space:]]" "$file" 2>/dev/null
}

# cc_env_set_if_absent — additive + idempotent env writer. Sets KEY=VALUE only
# when KEY is absent or empty; a pre-existing non-empty value is PRESERVED (never
# overwrite an operator's setting, never rotate a secret). Atomic (temp+mv),
# 0600. The VALUE is never echoed to a log. Returns 0=newly set, 2=preserved,
# 1=write error.
cc_env_set_if_absent() {
  local file="$1" key="$2" val="$3" tmp
  cc_env_has_nonempty "$file" "$key" && return 2
  tmp="$(mktemp)" || return 1
  if [[ -f "$file" ]]; then
    # Drop any empty or commented placeholder for KEY; keep every other line.
    grep -vE "^[[:space:]]*#?[[:space:]]*${key}=" "$file" > "$tmp" 2>/dev/null || true
  fi
  printf '%s=%s\n' "$key" "$val" >> "$tmp"
  if mv "$tmp" "$file"; then
    chmod 600 "$file" 2>/dev/null || true
    return 0
  fi
  rm -f "$tmp" 2>/dev/null || true
  return 1
}

# cc_env_get — echo KEY's value from an env file (empty when absent). Reads the
# LAST assignment (matching cc_env_set_if_absent's append semantics) and strips a
# single layer of surrounding quotes. The value is returned on stdout for capture
# only — NEVER logged. (KEY is [A-Z_]+ here, so it carries no regex metacharacters.)
cc_env_get() {
  local file="$1" key="$2" line
  [[ -f "$file" ]] || return 0
  line="$(grep -E "^[[:space:]]*${key}=" "$file" 2>/dev/null | tail -n1)" || return 0
  line="${line#*=}"
  line="${line%\"}"; line="${line#\"}"
  line="${line%\'}"; line="${line#\'}"
  printf '%s' "$line"
}

# cc_mirror_api_auth_to_agent_secrets — WRITE-BACK-401 durable fix.
#
# A dispatched DEPARTMENT agent writes its result back to the Command Center task
# API (POST /api/tasks/:id/activities, /deliverables, PATCH :id status). Those
# calls must present `Authorization: Bearer $MC_API_TOKEN` (and, for the signed
# ingest/status routes, an HMAC over WEBHOOK_SECRET) or the fail-closed middleware
# rejects them 401 and the finished task freezes in_progress. But dept agents read
# those secrets from their OpenClaw RUNTIME env ($OC_ROOT/secrets/.env — the same
# file the GHL keys live in), NOT from the CC server's .env.local that
# cc_write_env_local provisions. This mirrors the SAME values into the agent
# secrets env so `$MC_API_TOKEN` actually resolves agent-side and the write-back
# authenticates instead of 401ing.
#
# Additive + idempotent: an existing agent-side value is PRESERVED (never rotated),
# the secret VALUE is never echoed to a log, and the file is 0600.
cc_mirror_api_auth_to_agent_secrets() {
  local envf="$1" secrets_dir secrets_env tok whs t_status w_status
  secrets_dir="$OC_ROOT/secrets"
  secrets_env="$secrets_dir/.env"
  [[ -d "$secrets_dir" ]] || ( umask 077; mkdir -p "$secrets_dir" ) 2>/dev/null || true
  if [[ ! -d "$secrets_dir" ]]; then
    log "WARN" "cc-env: $secrets_dir missing — dept-agent MC_API_TOKEN mirror skipped (write-backs may 401)"
    return 0
  fi
  if [[ ! -f "$secrets_env" ]]; then ( umask 177; : > "$secrets_env" ) 2>/dev/null || true; fi
  chmod 600 "$secrets_env" 2>/dev/null || true

  tok="$(cc_env_get "$envf" MC_API_TOKEN)"
  whs="$(cc_env_get "$envf" WEBHOOK_SECRET)"

  t_status="skipped(no-token-in-.env.local; insecure-open posture?)"
  w_status="skipped(no-secret-in-.env.local)"
  if [[ -n "$tok" ]]; then
    if cc_env_has_nonempty "$secrets_env" MC_API_TOKEN; then
      t_status="preserved(existing-agent-value)"
    elif cc_env_set_if_absent "$secrets_env" MC_API_TOKEN "$tok" >/dev/null; then
      t_status="mirrored(from-cc-.env.local)"
    fi
  fi
  if [[ -n "$whs" ]]; then
    if cc_env_has_nonempty "$secrets_env" WEBHOOK_SECRET; then
      w_status="preserved(existing-agent-value)"
    elif cc_env_set_if_absent "$secrets_env" WEBHOOK_SECRET "$whs" >/dev/null; then
      w_status="mirrored(from-cc-.env.local)"
    fi
  fi
  tok=""; whs=""   # scrub from shell memory promptly
  chmod 600 "$secrets_env" 2>/dev/null || true
  log "INFO" "cc-env: dept-agent secrets MC_API_TOKEN ${t_status}; WEBHOOK_SECRET ${w_status} (dept agents can now auth CC task write-backs)"
  return 0
}

# cc_write_env_local — fixes (2)+(3)+(4). Provisions CC .env.local from the box's
# own config so a rebuild/reboot can never silently fail closed. Idempotent +
# additive; safe to re-run on every install/update/resume.
cc_write_env_local() {
  local dir="${DASHBOARD_DIR}" envf
  envf="${dir}/.env.local"
  if [[ ! -d "$dir" ]]; then
    log "WARN" "cc-env: $dir missing — skipping .env.local provisioning"
    return 0
  fi
  # Create the file with tight perms BEFORE any secret is written into it.
  if [[ ! -f "$envf" ]]; then ( umask 177; : > "$envf" ) 2>/dev/null || true; fi
  chmod 600 "$envf" 2>/dev/null || true

  # ---- (2) OPENCLAW_GATEWAY_TOKEN — box gateway token when auth.mode=token ----
  local gw_status="skipped" gw_mode gw_tok
  if cc_env_has_nonempty "$envf" OPENCLAW_GATEWAY_TOKEN; then
    gw_status="preserved(existing)"
  elif [[ -f "$OC_CONFIG" ]] && command -v jq >/dev/null 2>&1; then
    gw_mode="$(jq -r '.gateway.auth.mode // empty' "$OC_CONFIG" 2>/dev/null)"
    if [[ "$gw_mode" == "token" ]]; then
      gw_tok="$(jq -r '.gateway.auth.token // empty' "$OC_CONFIG" 2>/dev/null)"
      if [[ -n "$gw_tok" ]]; then
        if cc_env_set_if_absent "$envf" OPENCLAW_GATEWAY_TOKEN "$gw_tok" >/dev/null; then
          gw_status="set(from-box-gateway)"
        fi
        gw_tok=""   # scrub from shell memory promptly
      else
        gw_status="skipped(no-token-in-config)"
      fi
    else
      gw_status="skipped(auth.mode=${gw_mode:-unset})"
    fi
  else
    gw_status="skipped(no-openclaw-config-or-jq)"
  fi
  log "INFO" "cc-env: OPENCLAW_GATEWAY_TOKEN ${gw_status}"

  # ---- (3) SOVEREIGN_DEFAULT_MODEL — box's OWN primary TEXT model ----
  local sm_status model_id
  if cc_env_has_nonempty "$envf" SOVEREIGN_DEFAULT_MODEL; then
    sm_status="preserved(existing)"
  else
    model_id="$(cc_resolve_sovereign_model)"
    if [[ -n "$model_id" ]]; then
      cc_env_set_if_absent "$envf" SOVEREIGN_DEFAULT_MODEL "$model_id" >/dev/null \
        && sm_status="set(${model_id})"
    else
      sm_status="skipped(no-sovereign-text-model-in-box-config)"
    fi
  fi
  log "INFO" "cc-env: SOVEREIGN_DEFAULT_MODEL ${sm_status}"

  # ---- (3b) QC_JUDGE_MODEL — client-owned Ollama Cloud GENERAL-REASONING judge --
  # QC-08 (operator decision): the Command Center quality-review JUDGE runs on the
  # CLIENT's OWN Ollama Cloud model — NEVER an operator/shared paid key, and NEVER
  # a *-code model. Root cause this fixes: with NO QC_JUDGE_MODEL (and no dept-QC-
  # agent model column) the CC qc-scorer's resolveClientJudgeModel() returns null
  # and every review fails CLOSED to heuristic 'no-key' — the task sits in `review`
  # forever and the board silently completes NOTHING. We provision a general-
  # reasoning judge from THIS box's own models so review can actually pass.
  #
  # JUDGE != WRITER design note: the CC scorer only enforces judge!=writer when the
  # WRITER model is known (input.writerModel). Today every agents.model column is
  # blank fleet-wide (verified on the operator canary: 0 of 290 agents carry a
  # model), so writerModel is null and the equality guard is SKIPPED — therefore
  # ANY eligible client-owned reasoning model is a safe judge. When agent models
  # are later populated, cc_resolve_judge_model's family precedence still picks a
  # deepseek/glm/qwen3 judge that will differ from a kimi/other writer in practice.
  #
  # Idempotent: an operator-set QC_JUDGE_MODEL is PRESERVED, never overwritten.
  # NOTE (endpoint dependency, flagged separately): scoring ALSO requires the box's
  # Ollama Cloud connector to reach a working endpoint with the client's key. On
  # the operator canary the default https://ollama.com returned 401 for every
  # stored key and the working sovereign path was the box's local Ollama proxy
  # (OLLAMA_CLOUD_BASE_URL). Provisioning that endpoint is intentionally OUT OF
  # SCOPE here (per-box; never guess another box's endpoint) — this block sets
  # only the judge NAME, from the client's own models.
  local jm_status judge_id
  if cc_env_has_nonempty "$envf" QC_JUDGE_MODEL; then
    jm_status="preserved(existing)"
  else
    judge_id="$(cc_resolve_judge_model)"
    if [[ -n "$judge_id" ]]; then
      cc_env_set_if_absent "$envf" QC_JUDGE_MODEL "$judge_id" >/dev/null \
        && jm_status="set(${judge_id})"
    else
      jm_status="UNSET — judge not provisioned: this box's openclaw.json has no eligible client general-reasoning Ollama Cloud model (deepseek/glm/qwen3/gpt-oss/mistral, non-code). QC fail-closes to human review until one exists. (never guess/borrow a shared key)"
    fi
  fi
  log "INFO" "cc-env: QC_JUDGE_MODEL ${jm_status}"

  # ---- (4) API-auth posture — never leave the middleware silently fail-closed --
  # Preserve any posture already chosen. Otherwise DEFAULT to provisioning real
  # secrets (secure — webhooks authenticate). A Cloudflare-Access box may opt into
  # the legacy open posture (matching the proven CF-Access remediation) by setting
  # CC_ALLOW_INSECURE_OPEN_API=true (or CC_API_AUTH_MODE=insecure).
  local api_status
  if cc_env_has_nonempty "$envf" ALLOW_INSECURE_OPEN_API \
     || { cc_env_has_nonempty "$envf" MC_API_TOKEN && cc_env_has_nonempty "$envf" WEBHOOK_SECRET; }; then
    api_status="preserved(existing-posture)"
  elif [[ "${CC_ALLOW_INSECURE_OPEN_API:-}" == "true" || "${CC_API_AUTH_MODE:-}" == "insecure" ]]; then
    cc_env_set_if_absent "$envf" ALLOW_INSECURE_OPEN_API "true" >/dev/null
    api_status="set(ALLOW_INSECURE_OPEN_API=true; CF-Access box)"
  else
    cc_env_has_nonempty "$envf" MC_API_TOKEN   || cc_env_set_if_absent "$envf" MC_API_TOKEN   "$(_cc_gen_secret)" >/dev/null
    cc_env_has_nonempty "$envf" WEBHOOK_SECRET || cc_env_set_if_absent "$envf" WEBHOOK_SECRET "$(_cc_gen_secret)" >/dev/null
    api_status="set(MC_API_TOKEN+WEBHOOK_SECRET provisioned)"
  fi
  log "INFO" "cc-env: API-auth ${api_status}"

  # WRITE-BACK-401 durable fix: mirror MC_API_TOKEN + WEBHOOK_SECRET into the
  # dept-agent OpenClaw runtime secrets env so a dispatched agent's $MC_API_TOKEN
  # resolves and its task write-backs authenticate (else they 401 and finished
  # work freezes in_progress). Idempotent; preserves any existing agent value.
  cc_mirror_api_auth_to_agent_secrets "$envf"

  # STALE-CHECKOUT POST-CONDITION (loud): a box running an OLD on-box installer
  # (predating cc_mirror_api_auth_to_agent_secrets, Skill-32 v12.9.31) writes the
  # token to CC .env.local but never mirrors it to $OC_ROOT/secrets/.env — the
  # server is half-provisioned and dispatched dept agents 401 on write-back, so
  # the board silently stalls. This installer HAS the mirror, but we still assert
  # the post-condition so any future regression (or a bypassed mirror) screams
  # instead of failing silently. If .env.local carries a token but the agent
  # secrets env does not, say so LOUDLY and name the remedy.
  if cc_env_has_nonempty "$envf" MC_API_TOKEN \
     && ! cc_env_has_nonempty "$OC_ROOT/secrets/.env" MC_API_TOKEN; then
    log "ERROR" "cc-env: POST-CONDITION FAILED — MC_API_TOKEN is in CC .env.local but was NOT mirrored to $OC_ROOT/secrets/.env. Dept-agent write-backs will 401 and finished tasks freeze in_progress. Likely a STALE on-box Skill-32 checkout: update Skill 32 to current (>= v12.9.31) and re-run this installer."
  fi

  chmod 600 "$envf" 2>/dev/null || true
  [[ -f "$STATE_FILE" ]] && state_set '.commandCenterEnvLocalProvisioned = true' 2>/dev/null || true
  return 0
}

# cc_ensure_fresh_build — fix (1). Guarantee the served `.next` bundle matches the
# checked-out source, so `next start` runs the code that registers the
# intake-advance + backlog-redispatch sweeps. Idempotent: rebuilds ONLY when
# `.next/BUILD_ID` is missing or older than a build input; a no-change re-run does
# not rebuild. Returns 0=fresh bundle present, 1=build failed but a prior (stale)
# .next remains, 2=build failed and NO usable .next bundle exists.
cc_ensure_fresh_build() {
  local dir="${DASHBOARD_DIR}" nextid
  nextid="${dir}/.next/BUILD_ID"
  if [[ ! -d "$dir" ]]; then
    log "WARN" "cc-build: $dir missing — cannot build"
    return 2
  fi
  # Build inputs whose change must invalidate the bundle.
  local inputs=( src public config next.config.mjs next.config.js next.config.ts \
                 package.json package-lock.json tsconfig.json tailwind.config.ts \
                 postcss.config.mjs middleware.ts )
  local present=() p
  for p in "${inputs[@]}"; do [[ -e "$dir/$p" ]] && present+=("$dir/$p"); done

  local need_build=0
  if [[ ! -f "$nextid" ]]; then
    need_build=1
    log "INFO" "cc-build: no .next/BUILD_ID present — production build required"
  elif [[ ${#present[@]} -gt 0 ]] \
       && [[ -n "$(find "${present[@]}" -newer "$nextid" 2>/dev/null | head -n1)" ]]; then
    need_build=1
    log "INFO" "cc-build: source newer than .next/BUILD_ID — stale bundle, rebuild required"
  fi

  if [[ "$need_build" -eq 0 ]]; then
    log "INFO" "cc-build: .next bundle is fresh vs source — skipping rebuild (idempotent)"
    [[ -f "$STATE_FILE" ]] && state_set '.commandCenterBuildFresh = true' 2>/dev/null || true
    return 0
  fi

  local build_start; build_start="$(date +%s)"
  log "INFO" "cc-build: running 'npm run build' (next build) in $dir"
  if ( cd "$dir" && npm run build >>"$LOG_FILE" 2>&1 ); then
    # Verify a FRESH BUILD_ID landed (mtime >= build start) — guards against a
    # build that exits 0 yet produced no new output.
    if [[ -f "$nextid" ]] && [[ "$(_cc_mtime "$nextid")" -ge "$build_start" ]]; then
      log "INFO" "cc-build: next build done — fresh .next/BUILD_ID verified"
      [[ -f "$STATE_FILE" ]] && state_set '.commandCenterBuildFresh = true' 2>/dev/null || true
      return 0
    fi
    log "WARN" "cc-build: npm run build exited 0 but .next/BUILD_ID is missing/stale"
  else
    log "WARN" "cc-build: npm run build FAILED (see $LOG_FILE)"
  fi
  [[ -f "$STATE_FILE" ]] && state_set '.commandCenterBuildFresh = false' 2>/dev/null || true
  if [[ -f "$nextid" ]]; then return 1; else return 2; fi
}

# cc_verify_db_parity — DATA-08 decoy-DB guard, wired into deploy.
#
# shared-utils/resolve_db.py's find_dashboard_db() candidate list is what EVERY
# Skill 32 Python script (seed-workspaces.py, guard-department-runtime-parity.py,
# move-task.py, sync-md-content-to-db.py, ...) uses to locate mission-control.db.
# The Command Center APP resolves the SAME file independently, in TypeScript,
# via src/lib/db/index.ts: DATABASE_PATH env override, else
# process.cwd()/mission-control.db (cwd = $DASHBOARD_DIR under pm2 — see
# cc_pm2_start_canonical). If those two resolutions ever diverge — a stray
# DATABASE_PATH left in the shell env, a decoy DB from an old install layout,
# a script invoked from the wrong cwd — every Skill 32 script silently
# reads/writes a DIFFERENT file than the one the app actually serves. That is
# the DATA-08 decoy-DB class of bug: workspace edits, dept seeding, and
# persona-selector writes all land somewhere the board never shows.
#
# Runs resolve_db.py --verify-parity FROM the app's OWN cwd ($DASHBOARD_DIR) so
# its cwd-based default resolution is mirrored exactly — the same DATABASE_PATH
# (or absence of it) that both the app process and this shell inherit. Returns
# 0 on parity, non-zero (2, per resolve_db.py's argparse contract) on a genuine
# mismatch or an unresolvable script-side DB. Fail-CLOSED by design: the caller
# is expected to fail_install() on a non-zero return, exactly like the
# department-runtime-parity guard (Phase 6e2) it is modeled on — this is a
# regression class in the same family (silent per-box DB divergence), not a
# best-effort warning.
cc_verify_db_parity() {
  local script="$SKILL_DIR/../shared-utils/resolve_db.py"
  if [[ ! -f "$script" ]]; then
    log "WARN" "phase=6 db-parity (DATA-08): $script not found -- skipping (onboarding not at the version that ships resolve_db.py --verify-parity)"
    return 0
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    log "WARN" "phase=6 db-parity (DATA-08): python3 not found -- skipping"
    return 0
  fi
  local out rc
  out="$(cd "$DASHBOARD_DIR" && python3 "$script" --verify-parity 2>&1)"; rc=$?
  printf '%s\n' "$out" >> "$LOG_FILE"
  if [[ "$rc" -eq 0 ]]; then
    log "INFO" "phase=6 db-parity (DATA-08): PASS -- $out"
    [[ -f "$STATE_FILE" ]] && state_set '.commandCenterDbPathParity = true' 2>/dev/null || true
    return 0
  fi
  log "ERROR" "phase=6 db-parity (DATA-08): FAIL (rc=$rc) -- $out"
  [[ -f "$STATE_FILE" ]] && state_set '.commandCenterDbPathParity = false' 2>/dev/null || true
  return "$rc"
}

# ---- preflight ----
if [[ ! -f "$STATE_FILE" ]]; then
  if [[ "$UPDATE_ONLY" == "true" ]]; then
    log "WARN" "no state file at $STATE_FILE — update-only continuing without state tracking"
  else
    log "ERROR" "no state file at $STATE_FILE — refusing to run"
    exit 1
  fi
fi
for cmd in jq curl git npm python3; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    if [[ "$UPDATE_ONLY" == "true" ]]; then
      log "WARN" "preflight: missing $cmd — update-only continuing (some steps may fail)"
    else
      fail_install "preflight: missing required command: $cmd"
    fi
  fi
done

# ---- --update-only: read client metadata from state file when not passed on CLI ----
if [[ "$UPDATE_ONLY" == "true" ]] && [[ -z "$CLIENT_SLUG" ]] && [[ -f "$STATE_FILE" ]]; then
  # P1-3: read companySlug (canonical, written by build-workforce.py) with a
  # transition fallback to the legacy clientSlug alias. state_get appends `// empty`,
  # so this resolves companySlug → clientSlug → empty across both state generations.
  CLIENT_SLUG=$(state_get '.companySlug // .clientSlug')
  COMPANY_NAME=$(python3 -c "import json; d=json.load(open('$STATE_FILE')); print(d.get('companyName',''))" 2>/dev/null || echo "")
  CONTACT_EMAIL=$(python3 -c "import json; d=json.load(open('$STATE_FILE')); print(d.get('contactEmail',''))" 2>/dev/null || echo "")
  [[ -n "$CLIENT_SLUG" ]] && log "INFO" "update-only: read client slug from state file: $CLIENT_SLUG"
fi

log "INFO" "run-full-install starting: update_only=$UPDATE_ONLY slug=${CLIENT_SLUG:-?} company=${COMPANY_NAME:-?} email=${CONTACT_EMAIL:-?}"
if [[ -f "$STATE_FILE" ]]; then
  state_set '.commandCenterStatus = "building"'
fi

# ==============================================================================
# BLOCK A - LOCKED CC SHELL (deploys FIRST; OQ-1 shell-first flip, v12.9.27)
# ==============================================================================
# ORDERING INVARIANT - LOCK BEFORE REACHABLE (read this before reordering anything):
#   The Command Center shell is now deployed BEFORE the interview-complete gate so
#   the client immediately has a /interview surface to use. Safety is guaranteed by
#   the P0-5 interview-mode middleware (command-center v4.60.0+), which derives its
#   lock PURELY from the canonical build-state file this installer already writes
#   ($STATE_FILE == $OC_ROOT/workspace/.workforce-build-state.json):
#     * interviewComplete != true          -> 302 every non-/interview, non-/onboarding
#                                             request to /interview   (LOCKED)
#     * buildCompletedAt set (at closeout) -> full dashboard revealed  (UNLOCKED)
#   There is NO separate CC "unlock" env var; provisioning must not invent one.
#
#   Because a fresh / in-progress interview has interviewComplete=false and
#   buildCompletedAt unset, the lock signal is ALREADY on disk (at the path the
#   middleware reads) before Phase 6 binds :4000 and before Phase 6h exposes the
#   tunnel - so the very first request the shell ever serves is already redirected
#   to /interview. There is NO window in which an empty, unlocked board is
#   browsable. lock_assert (below) FAILS CLOSED in full-install mode when that lock
#   signal is absent, rather than start a shell the middleware cannot lock. Only the
#   REAL-workforce materialization in BLOCK B stays gated on interviewComplete.

# ----------------------------------------------------------------------
# PHASE 1 — Prerequisites (pm2 + openclaw doctor --fix)
# ----------------------------------------------------------------------
log "INFO" "phase=1 prereqs: starting"
if [[ "$UPDATE_ONLY" == "true" ]]; then
  log "INFO" "phase=1 prereqs: --update-only mode — skipping (pm2 already installed on prior run)"
elif [[ "$(state_get '.commandCenterPhase1Done')" == "true" ]]; then
  log "INFO" "phase=1 prereqs: already done — skipping"
else
  if ! command -v pm2 >/dev/null 2>&1; then
    log "INFO" "phase=1 prereqs: installing pm2 globally"
    if ! npm install -g pm2 >>"$LOG_FILE" 2>&1; then
      fail_install "phase=1: npm install -g pm2 failed"
    fi
  fi
  # Heal config before any gateway interaction (defends against the
  # telegram/whatsapp plugin deprecated-field crash observed on a client VPS).
  if command -v openclaw >/dev/null 2>&1; then
    openclaw doctor --fix >>"$LOG_FILE" 2>&1 || log "WARN" "phase=1: openclaw doctor --fix returned non-zero (continuing)"
  fi
  state_set '.commandCenterPhase1Done = true'
  log "INFO" "phase=1 prereqs: done"
fi

# ---- lock-assert: guarantee the P0-5 lock signal exists BEFORE the shell binds ----
# See the BLOCK A ordering-invariant comment. Full-install mode FAILS CLOSED when the
# build-state (the middleware's only lock source) is missing - never start a shell the
# middleware cannot lock. --update-only refreshes an already-tracked CC, so it is exempt.
if [[ "$UPDATE_ONLY" == "true" ]]; then
  log "INFO" "lock-assert: --update-only - refreshing an already-locked/unlocked CC; skipping fresh-deploy lock gate"
else
  if [[ ! -f "$STATE_FILE" ]]; then
    fail_install "lock-assert: no build-state at $STATE_FILE - refusing to deploy the CC shell (the P0-5 middleware would have no lock signal, risking an unlocked empty board). Complete the AI Workforce interview (Skill 23) first."
  fi
  _lock_ic="$(state_get '.interviewComplete')"
  _lock_bc="$(state_get '.buildCompletedAt')"
  if [[ -n "$_lock_bc" && "$_lock_bc" != "null" ]]; then
    log "INFO" "lock-assert: buildCompletedAt=$_lock_bc present - completed box; CC serves UNLOCKED (real workforce already built). Proceeding."
  elif [[ "$_lock_ic" == "true" ]]; then
    log "INFO" "lock-assert: interviewComplete=true, buildCompletedAt unset - build in progress; CC serves LOCKED until closeout. Proceeding."
  else
    log "INFO" "lock-assert: interviewComplete=${_lock_ic:-<unset>}, buildCompletedAt unset - CC will serve LOCKED (P0-5 302s to /interview). Deploying the locked shell first. Proceeding."
  fi
fi

# ----------------------------------------------------------------------
# PHASE 6 — Dashboard deploy / update
# ----------------------------------------------------------------------
log "INFO" "phase=6 dashboard-deploy: starting"
if [[ "$UPDATE_ONLY" == "true" ]]; then
  # --update-only: git pull --ff-only + npm install + db:push + pm2 restart.
  # Skips db:seed (protects client-customized rows).
  # Skips git-clone (we already verified .git exists before invoking this flag).
  log "INFO" "phase=6 dashboard-update: --update-only — git pull + npm install + .env.local + next build (freshness-gated) + db:push + pm2 restart (no db:seed)"
  if [[ ! -d "$DASHBOARD_DIR/.git" ]]; then
    log "WARN" "phase=6 dashboard-update: $DASHBOARD_DIR/.git not found — run full install first (skipping refresh)"
  else
    ( cd "$DASHBOARD_DIR" && git pull --ff-only >>"$LOG_FILE" 2>&1 ) \
      && log "INFO" "phase=6: git pull --ff-only done" \
      || log "WARN" "phase=6: git pull non-clean — continuing with existing checkout"
    ( cd "$DASHBOARD_DIR" && npm install >>"$LOG_FILE" 2>&1 ) \
      && log "INFO" "phase=6: npm install done" \
      || log "WARN" "phase=6: npm install reported errors (continuing)"
    # (2)+(3)+(4) provision CC .env.local BEFORE the build so both the fresh build
    # AND the fresh boot see the gateway token / sovereign model / API-auth posture.
    cc_write_env_local
    # (1) rebuild `.next` IFF it is stale vs the just-pulled source. This is the
    # Kanban-dead fix: without it `next start` keeps serving a bundle that predates
    # the intake-advance + backlog-redispatch sweep registration.
    cc_ensure_fresh_build; _bfrc=$?
    if [[ "$_bfrc" -ne 0 ]]; then
      log "WARN" "phase=6 (update-only): CC build not fresh (rc=$_bfrc) — board may serve a stale bundle until the resume cron rebuilds"
    fi
    ( cd "$DASHBOARD_DIR" && npm run db:push >>"$LOG_FILE" 2>&1 ) \
      && log "INFO" "phase=6: db:push done (runs migrations via getDb(); no demo seeding on client boxes)" \
      || log "WARN" "phase=6: db:push reported errors (continuing)"
    # DATA-08 decoy-DB guard — hard, deploy-blocking gate. db:push has just
    # created/migrated the real mission-control.db, so this is the earliest
    # point the app-side and scripts-side resolutions can be compared for real.
    if ! cc_verify_db_parity; then
      fail_install "phase=6 (update-only): DATA-08 decoy-DB guard failed -- shared-utils/resolve_db.py resolves a DIFFERENT mission-control.db than the app (see $LOG_FILE). Set/clear DATABASE_PATH so scripts and app agree, then re-run."
    fi
    # IDEMPOTENT + RECONCILING (v16.1.7): delete every non-canonical CC alias
    # (mission-control, command-center), then restart the canonical
    # "blackceo-command-center" (start fresh if it isn't registered yet). This
    # converges a box running under ANY name down to a single CC on :4000, so the
    # two-process mutual-kill loop can never recur.
    cc_reconcile_pm2_names
    if pm2 restart "$CC_PM2_NAME" >>"$LOG_FILE" 2>&1; then
      log "INFO" "phase=6: pm2 restart $CC_PM2_NAME done (reconciled to one canonical CC)"
    else
      log "WARN" "phase=6: pm2 restart $CC_PM2_NAME failed — starting fresh"
      pm2 delete "$CC_PM2_NAME" >/dev/null 2>&1 || true
      cc_pm2_start_canonical \
        && log "INFO" "phase=6: pm2 start $CC_PM2_NAME done (fresh)" \
        || log "WARN" "phase=6: pm2 start $CC_PM2_NAME failed — check: pm2 logs $CC_PM2_NAME"
    fi
    pm2 save >>"$LOG_FILE" 2>&1 || true
  fi
elif [[ "$(state_get '.commandCenterPhase6Done')" == "true" ]]; then
  log "INFO" "phase=6 dashboard-deploy: already done — skipping"
else
  mkdir -p "$(dirname "$DASHBOARD_DIR")"
  if [[ ! -d "$DASHBOARD_DIR/.git" ]]; then
    log "INFO" "phase=6: cloning $DASHBOARD_REPO → $DASHBOARD_DIR"
    if ! git clone "$DASHBOARD_REPO" "$DASHBOARD_DIR" >>"$LOG_FILE" 2>&1; then
      fail_install "phase=6: git clone failed"
    fi
  else
    log "INFO" "phase=6: dashboard repo already cloned — pulling latest"
    ( cd "$DASHBOARD_DIR" && git pull --ff-only >>"$LOG_FILE" 2>&1 ) || log "WARN" "phase=6: git pull non-clean (continuing with existing checkout)"
  fi

  log "INFO" "phase=6: npm install in $DASHBOARD_DIR"
  if ! ( cd "$DASHBOARD_DIR" && npm install >>"$LOG_FILE" 2>&1 ); then
    fail_install "phase=6: npm install failed in $DASHBOARD_DIR"
  fi

  # (2)+(3)+(4) provision CC .env.local BEFORE build/boot (gateway token +
  # sovereign text model + API-auth posture), from THIS box's own config.
  cc_write_env_local
  # (1) build the `.next` bundle so `next start` serves code matching the checkout
  # (registers the intake-advance + backlog-redispatch sweeps). A fresh full
  # install has NO `.next` at all — so a hard build failure with no usable bundle
  # is fatal here (next start would EADDR/no-build crash-loop otherwise).
  cc_ensure_fresh_build; _bfrc=$?
  if [[ "$_bfrc" -ge 2 ]]; then
    fail_install "phase=6: next build failed and no usable .next bundle exists — next start would crash-loop (see $LOG_FILE)"
  elif [[ "$_bfrc" -eq 1 ]]; then
    log "WARN" "phase=6: next build failed but a prior .next bundle exists — continuing (board may be stale; resume cron retries)"
  fi

  log "INFO" "phase=6: npm run db:push (runs migrations via getDb())"
  if ! ( cd "$DASHBOARD_DIR" && npm run db:push >>"$LOG_FILE" 2>&1 ); then
    fail_install "phase=6: npm run db:push failed"
  fi

  # db:seed initializes structural rows only; demo seeding is disabled by default
  # (DEMO_SEED is left unset, so seed.ts uses the no-demo default on client boxes)
  log "INFO" "phase=6: npm run db:seed (no demo content injected)"
  if ! ( cd "$DASHBOARD_DIR" && npm run db:seed >>"$LOG_FILE" 2>&1 ); then
    log "WARN" "phase=6: npm run db:seed failed — dashboard will still start but workspace selector may be empty"
  fi

  # DATA-08 decoy-DB guard — hard, deploy-blocking gate. db:push/db:seed have
  # just created/migrated the real mission-control.db, so this is the earliest
  # point the app-side and scripts-side resolutions can be compared for real.
  # A genuine mismatch here means every Skill 32 Python script (seeders,
  # dept-runtime-parity, persona-selector) would silently read/write a
  # DIFFERENT file than the one pm2 is about to start serving — fail BEFORE
  # that happens, not after a client reports "my edits vanished".
  if ! cc_verify_db_parity; then
    fail_install "phase=6: DATA-08 decoy-DB guard failed -- shared-utils/resolve_db.py resolves a DIFFERENT mission-control.db than the app (see $LOG_FILE). Set/clear DATABASE_PATH so scripts and app agree, then re-run."
  fi

  # Pin CC_PORT so the bind is deterministic on :4000 — cc-start.sh (npm start ->
  # bash scripts/cc-start.sh) strips any ambient/leaked PORT and binds CC_PORT.
  # Matches Phase 6.6 of INSTALL.md.
  #
  # IDEMPOTENT + RECONCILING (v16.1.7): delete every non-canonical CC alias
  # (mission-control, command-center) AND any stale canonical app, then start
  # exactly ONE canonical "blackceo-command-center". A box can never end up with
  # two CCs fighting over :4000.
  log "INFO" "phase=6: starting dashboard via pm2 as '$CC_PM2_NAME' on CC_PORT=$DASHBOARD_PORT"
  cc_reconcile_pm2_names
  pm2 delete "$CC_PM2_NAME" >/dev/null 2>&1 || true
  if ! cc_pm2_start_canonical; then
    fail_install "phase=6: pm2 start failed"
  fi
  pm2 save >>"$LOG_FILE" 2>&1 || true

  state_set '.commandCenterPhase6Done = true'
  log "INFO" "phase=6 dashboard-deploy: done"
fi

# ----------------------------------------------------------------------
# PHASE 6h — Tunnel (n8n webhook + cloudflared)
# ----------------------------------------------------------------------
# P3-2: this tunnel phase was previously mislabeled "PHASE 6b", colliding with the
# workspace-seed phase (also "6b"). Renamed to the next free letter (6b–6g are taken
# by seed/sync/md-sync/dashboard-content/kpi/ghl-preflight) so the log stream is
# unambiguous. The STATE FIELD is renamed commandCenterPhase6bStatus →
# commandCenterPhase6hStatus, but the READ falls back to the old key so the
# duplicate-CC re-POST guard keeps working on boxes whose state predates this rename.
log "INFO" "phase=6h tunnel: starting"
if [[ "$UPDATE_ONLY" == "true" ]]; then
  log "INFO" "phase=6h tunnel: --update-only mode — skipping (tunnel already established on prior run)"
else
  existing_url=$(state_get '.commandCenterUrl')
  # Backward-compat read: prefer the new key, fall back to the legacy 6b key.
  phase6h_status=$(state_get '.commandCenterPhase6hStatus // .commandCenterPhase6bStatus')
  # Re-POST guard: once we have registered (success OR a webhook failure that may
  # have already created a tunnel/notified Trevor), NEVER POST to the n8n
  # registration webhook again on resume. The webhook is the duplicate-CC source;
  # a failed POST can still have fired the Telegram/sheet side effects, so any
  # terminal phase status blocks re-POST. Operators clear
  # .commandCenterPhase6hStatus (or the legacy .commandCenterPhase6bStatus) to force
  # a fresh registration.
  if [[ "$phase6h_status" == "failed-webhook" || "$phase6h_status" == "done" \
     || "$phase6h_status" == "done-no-subdomain-recorded" \
     || "$phase6h_status" == "skipped-script-missing" ]]; then
    log "INFO" "phase=6h tunnel: prior registration attempt recorded (status=$phase6h_status) — NOT re-POSTing webhook (duplicate-CC guard)"
  elif [[ -n "$existing_url" && "$existing_url" != "null" && "$existing_url" != "http://127.0.0.1:4000/" ]]; then
    log "INFO" "phase=6h tunnel: commandCenterUrl already set ($existing_url) — skipping"
  else
    TUNNEL_SCRIPT="$SKILL_DIR/scripts/create-tunnel.sh"
    if [[ ! -x "$TUNNEL_SCRIPT" ]]; then
      log "WARN" "phase=6h: create-tunnel.sh not executable at $TUNNEL_SCRIPT — marking tunnel as todo"
      state_set '.commandCenterPhase6hStatus = "skipped-script-missing"'
    else
      log "INFO" "phase=6h: invoking create-tunnel.sh $CLIENT_SLUG $COMPANY_NAME $CONTACT_EMAIL"
      if ! bash "$TUNNEL_SCRIPT" "$CLIENT_SLUG" "$COMPANY_NAME" "$CONTACT_EMAIL" >>"$LOG_FILE" 2>&1; then
        log "WARN" "phase=6h: create-tunnel.sh exited non-zero — leaving commandCenterUrl unset, dashboard still reachable locally"
        state_set '.commandCenterPhase6hStatus = "failed-webhook"'
      else
        # Try to recover the subdomain from the .env file the tunnel script wrote
        SUBDOMAIN_HINT=""
        if [[ -f "$OC_ROOT/.env" ]]; then
          SUBDOMAIN_HINT="$CLIENT_SLUG.zerohumanworkforce.com"
        fi
        if [[ -n "$SUBDOMAIN_HINT" ]]; then
          # P3-2: the URL carries the client slug — pass it via jq --arg, not interpolation.
          state_set_arg '.commandCenterUrl = $val | .commandCenterPhase6hStatus = "done"' "https://$SUBDOMAIN_HINT"
          log "INFO" "phase=6h tunnel: done — https://$SUBDOMAIN_HINT"
        else
          state_set '.commandCenterPhase6hStatus = "done-no-subdomain-recorded"'
          log "INFO" "phase=6h tunnel: done (subdomain not recovered into state)"
        fi
      fi
    fi
  fi
fi

# ==============================================================================
# INTERVIEW-COMPLETE GATE (protects REAL-workforce materialization ONLY)
# ==============================================================================
# The LOCKED CC shell + tunnel (BLOCK A) are already up by this point, so every exit
# below leaves the client with a usable /interview surface - it just does NOT
# materialize/seed the REAL zero-human workforce until the interview is genuinely
# complete (corroborated). "interview not completed yet" here means "real workforce
# deferred", never "no Command Center".
# ─── INTERVIEW-COMPLETE PRECONDITION (binding) ────────────────────────────────
# RULE: a client's REAL zero-human company (departments, roles, step-by-step
# instructions) is materialized ONLY after their AI Workforce interview is COMPLETE.
# If it is not, REPORT "interview not completed yet" and EXIT CLEAN — do NOT seed
# workspaces, materialize agents, or scaffold the default department floor onto a
# 'default' company. (See SKILL.md "Interview-Complete Precondition + Locked
# Interview-Mode" + PREREQS.json interview-complete entry.)
#
# ★ LOCKED INTERVIEW-MODE IS BY DESIGN (ratified 2026-07-03, OQ-1). ★
# This gate protects the REAL-WORKFORCE SEEDING below — NOT the CC shell itself.
# By the time control reaches here the LOCKED CC shell + tunnel (BLOCK A) are ALREADY
# deployed, so every exit below leaves the client a usable /interview surface; it only
# defers the REAL zero-human workforce. Under OQ-1 the CC ships FIRST but LOCKED to the
# /interview surface: the CC
# middleware (P0-5) 302s every non-/interview, non-/onboarding page to /interview
# while build-state `interviewComplete` is false, and reveals the full dashboard
# once `buildCompletedAt` is set at closeout. The lock is STATE-DRIVEN off the
# canonical build-state fields (interviewComplete / buildCompletedAt) that this
# installer already reads/writes — there is NO separate CC "unlock" env var to set,
# and provisioning must NOT invent one. A future reader: the interview-only CC view
# in front of an empty board pre-closeout is the intended experience, NOT a bug —
# do not remove this gate or "unlock" the shell to make the board show early.
#
# --update-only is EXEMPT: it only refreshes an ALREADY-built CC (git pull / npm /
# db:push) and must keep working for provisioned boxes whose flag predates this gate.
if [[ "$UPDATE_ONLY" != "true" ]]; then
  if [[ ! -f "$STATE_FILE" ]]; then
    log "INFO" "interview-gate: no .workforce-build-state.json — interview not started; REPORTING not-completed and exiting clean (real workforce not seeded)."
    echo "INTERVIEW_NOT_COMPLETE: no workforce-build state on this box — AI Workforce interview not completed yet. The locked CC shell is already deployed (client can use /interview now); real workforce NOT materialized (the CC stays in locked interview-mode by design until closeout)." >&2
    exit 0
  fi
  # FAST PRE-CHECK: the bare flag. Necessary but NOT sufficient (SKILL.md demands
  # multi-signal corroboration — the flag alone is set even on the fabricating path).
  INTERVIEW_COMPLETE=$(state_get '.interviewComplete')
  if [[ "$INTERVIEW_COMPLETE" != "true" ]]; then
    log "INFO" "interview-gate: interviewComplete=${INTERVIEW_COMPLETE:-<unset>} — REPORTING 'interview not completed yet' and exiting clean. NOT seeding/scaffolding the real workforce."
    state_set '.commandCenterStatus = "interview-pending" | .commandCenterGateReason = "AI Workforce interview not completed (interviewComplete != true) — real-workforce materialization is gated until the owner finishes their interview. The CC stays in locked interview-mode (P0-5 middleware 302s to /interview) by design until buildCompletedAt at closeout."'
    echo "INTERVIEW_NOT_COMPLETE: interviewComplete != true — AI Workforce interview not completed yet. Real workforce NOT materialized (expected, not an error). The locked CC shell is already deployed (client can use /interview now); it remains in locked interview-mode by design until closeout." >&2
    exit 0
  fi
  log "INFO" "interview-gate: fast pre-check passed (interviewComplete=true) — now CORROBORATING with qc-interview-completion.py (multi-signal, per SKILL.md)."

  # ── MULTI-SIGNAL CORROBORATION (binding, P2-7) ──────────────────────────────
  # SKILL.md requires the interview to be corroborated by MORE than the bare flag.
  # qc-interview-completion.py implements the real gate (question count, forbidden
  # jargon, mandatory fields, nudge wiring, no-fabrication). We refuse to scaffold a
  # whole zero-human company unless it returns PASS. Its exit codes:
  #   0 = PASS   1 = error/unreadable   2 = needs-review (soft)   3 = hard-fail.
  # A MISSING qc script fails CLOSED with an explicit error — never a silent pass.
  QC_INTERVIEW=""
  for _qc_cand in \
    "$(dirname "$SKILL_DIR")/23-ai-workforce-blueprint/scripts/qc-interview-completion.py" \
    "$HOME/.openclaw/skills/23-ai-workforce-blueprint/scripts/qc-interview-completion.py" \
    "/data/.openclaw/skills/23-ai-workforce-blueprint/scripts/qc-interview-completion.py"; do
    if [[ -f "$_qc_cand" ]]; then QC_INTERVIEW="$_qc_cand"; break; fi
  done
  if [[ -z "$QC_INTERVIEW" ]]; then
    # FAIL CLOSED: cannot corroborate the flag ⇒ refuse to scaffold on a bare flag.
    log "ERROR" "interview-gate: qc-interview-completion.py NOT FOUND in any skill-23 location — failing CLOSED (refusing to scaffold on an un-corroborated interviewComplete flag)."
    state_set_arg '.commandCenterStatus = "interview-qc-unverified" | .commandCenterGateReason = $val' \
      "qc-interview-completion.py missing in every skill-23 location — the interviewComplete flag could not be corroborated; Command Center scaffolding refused (fail-closed). Repair the Skill 23 install."
    echo "INTERVIEW_QC_UNVERIFIED: qc-interview-completion.py not found — cannot corroborate the interviewComplete flag. Locked CC shell is up, but the REAL workforce is NOT materialized (fail-closed; fix the Skill 23 install)." >&2
    exit 1
  fi
  # Prefer the answers-file transcript build-workforce.py recorded (its default path
  # differs); fall back to the qc script's own auto-resolution when unrecorded.
  QC_ARGS=(--state "$STATE_FILE" --format human)
  _qc_transcript=$(state_get '.interviewProgress.answersFilePath')
  if [[ -n "$_qc_transcript" && -f "$_qc_transcript" ]]; then
    QC_ARGS+=(--transcript "$_qc_transcript")
  fi
  QC_OUT="$(python3 "$QC_INTERVIEW" "${QC_ARGS[@]}" 2>&1)"; QC_RC=$?
  printf '%s\n' "$QC_OUT" >> "$LOG_FILE"
  if [[ "$QC_RC" -ne 0 ]]; then
    # Flag says complete but QC disagrees ⇒ NOT corroborated. Gate the CC (do NOT
    # scaffold); this is the expected "interview not genuinely done yet" hold, so we
    # exit clean and let the interview resume/nudge loop drive it to PASS. The QC
    # summary is carried via jq --arg (P3-2) — never interpolated into the program.
    _qc_summary="$(printf '%s\n' "$QC_OUT" | grep -E 'Summary:|\[HARD\]|\[SOFT\]|Question count' | head -4 | tr '\n' ' ')"
    log "ERROR" "interview-gate: qc-interview-completion.py rc=$QC_RC (not PASS) — interview NOT corroborated. Gating Command Center. ${_qc_summary}"
    state_set_arg '.commandCenterStatus = "interview-pending" | .commandCenterGateReason = $val' \
      "interviewComplete flag is set but qc-interview-completion.py returned rc=${QC_RC} (not PASS) — interview not corroborated complete; Command Center gated until it passes QC. ${_qc_summary}"
    echo "INTERVIEW_PENDING: interviewComplete=true but qc-interview-completion.py rc=$QC_RC (not PASS) — interview not corroborated complete. Locked CC shell is up; REAL workforce NOT materialized (gated; expected until QC passes)." >&2
    exit 0
  fi
  log "INFO" "interview-gate: qc-interview-completion.py PASS (rc=0) — interview corroborated. Proceeding with Command Center install."
fi

# ==============================================================================
# BLOCK B - REAL ZERO-HUMAN WORKFORCE (gated on interviewComplete, above)
# ==============================================================================
# Everything below only runs once the interview is corroborated complete: it
# materializes the client's REAL departments/roles/agents and seeds the board's
# real content. Building any of it pre-interview would produce the DEFAULT floor
# under company 'default' - a false deliverable - which is exactly why it stays
# behind the gate while the shell (BLOCK A) does not.

# ----------------------------------------------------------------------
# PHASE 3 — Workspace department folders
# ----------------------------------------------------------------------
log "INFO" "phase=3 workspace-folders: starting"
if [[ "$UPDATE_ONLY" == "true" ]]; then
  log "INFO" "phase=3 workspace-folders: --update-only mode — skipping (already done on prior run)"
elif [[ "$(state_get '.commandCenterPhase3Done')" == "true" ]]; then
  log "INFO" "phase=3 workspace-folders: already done — skipping"
else
  CC_BASE="$OC_ROOT/workspaces/command-center"
  mkdir -p "$CC_BASE"
  DEPT_SRC="$OC_ROOT/workspace/departments"
  if [[ -d "$DEPT_SRC" ]]; then
    while IFS= read -r dept_path; do
      [[ -z "$dept_path" ]] && continue
      dept_slug="$(basename "$dept_path")"
      target="$CC_BASE/$dept_slug"
      mkdir -p "$target/memory"
      log "INFO" "phase=3: ensured $target/"
    done < <(find "$DEPT_SRC" -mindepth 1 -maxdepth 1 -type d 2>/dev/null)
  else
    log "WARN" "phase=3: $DEPT_SRC missing — no departments to materialize folders for"
  fi
  state_set '.commandCenterPhase3Done = true'
  log "INFO" "phase=3 workspace-folders: done"
fi

# ----------------------------------------------------------------------
# PHASE 4 — Materialize dept agents into agents.list[] (v10.14.19)
# ----------------------------------------------------------------------
log "INFO" "phase=4 materialize-agents: starting"
if [[ "$UPDATE_ONLY" == "true" ]]; then
  log "INFO" "phase=4 materialize-agents: --update-only mode — skipping (update-skills.sh already ran WIRING-ASSERT)"
elif [[ "$(state_get '.commandCenterPhase4Done')" == "true" ]]; then
  log "INFO" "phase=4 materialize-agents: already done — skipping"
else
  SKILL32_MATERIALIZE="$SKILL_DIR/scripts/materialize-dept-agents.sh"
  if [[ ! -x "$SKILL32_MATERIALIZE" ]]; then
    fail_install "phase=4: materialize-dept-agents.sh not executable at $SKILL32_MATERIALIZE"
  fi
  if ! bash "$SKILL32_MATERIALIZE" >>"$LOG_FILE" 2>&1; then
    fail_install "phase=4: materialize-dept-agents.sh exited non-zero (see $LOG_FILE)"
  fi
  AGENT_COUNT=$(python3 -c "import json,sys; sys.stdout.write(str(len(json.load(open('$OC_ROOT/openclaw.json'))['agents']['list'])))" 2>>"$LOG_FILE" || echo "0")
  if [[ -z "$AGENT_COUNT" || "$AGENT_COUNT" -lt 2 ]]; then
    fail_install "phase=4: agents.list[] has only ${AGENT_COUNT:-0} entries after materialize"
  fi
  state_set ".agentsMaterializedCount = $AGENT_COUNT | .commandCenterPhase4Done = true"
  log "INFO" "phase=4 materialize-agents: done (${AGENT_COUNT} agents in agents.list[])"
fi

# ----------------------------------------------------------------------
# PHASE 5 — Telegram topic creation (MANUAL — requires owner's phone)
# ----------------------------------------------------------------------
log "INFO" "phase=5 telegram-topics: SKIPPED (manual step required)"
log "INFO" "phase=5 TODO: owner must create topics in supergroup per INSTALL.md Phase 5, then bind each topic to its dept agent in openclaw.json (bindings[] array)"
if [[ -f "$STATE_FILE" ]]; then
  state_set '.commandCenterPhase5Status = "manual-todo"'
fi

# ----------------------------------------------------------------------
# PHASE 6b -- Seed the workspaces table from the client's REAL ZHC departments
# ----------------------------------------------------------------------
# F3 fix (CC board ships dead / prove-zhe check (c) RED): run-full-install
# previously relied ONLY on `npm run db:seed` (full path only; seeds from the
# dashboard's config/departments.json which ships EMPTY on purpose -> 0 rows)
# and Phase 6c's sync script (which lives INSIDE the external dashboard checkout
# and is WARN-only when missing). In --update-only mode db:seed is skipped
# entirely, so a missing sync script left the board with ZERO workspace rows.
# seed-workspaces.py is the AUTHORITATIVE seeder: it reads the client's real ZHC
# departments.json, resolves the SAME dashboard DB the dashboard/seeder use via
# resolve_db.find_dashboard_db(), and inserts with a pre-loop existing-set +
# INSERT OR IGNORE. It runs in BOTH the full and --update-only branches, AFTER
# Phase 6 db:push (DB guaranteed to exist) and BEFORE Phase 6c. Box-user,
# additive, idempotent — safe to re-run on every install/update/resume. This
# makes the board independent of the dashboard's empty config/departments.json
# and of whether the external sync-departments script shipped.
log "INFO" "phase=6b-seed: seeding workspaces table from client ZHC departments.json"
SEED_WS="$SKILL_DIR/scripts/seed-workspaces.py"
if [[ -f "$SEED_WS" ]] && command -v python3 >/dev/null 2>&1; then
  if COMPANY_SLUG="${CLIENT_SLUG:-}" COMPANY_NAME="${COMPANY_NAME:-}" \
       python3 "$SEED_WS" >>"$LOG_FILE" 2>&1; then
    log "INFO" "phase=6b-seed: workspaces seeded from ZHC departments.json (idempotent INSERT OR IGNORE)"
    if [[ -f "$STATE_FILE" ]]; then state_set '.commandCenterWorkspacesSeeded = true'; fi
  else
    log "WARN" "phase=6b-seed: seed-workspaces.py exited non-zero — board may be empty (check $LOG_FILE)"
    if [[ -f "$STATE_FILE" ]]; then state_set '.commandCenterWorkspacesSeeded = false'; fi
  fi
else
  log "WARN" "phase=6b-seed: seed-workspaces.py not found at $SEED_WS (or python3 missing) — skipping (board may be empty)"
  if [[ -f "$STATE_FILE" ]]; then state_set '.commandCenterWorkspacesSeeded = "script-missing"'; fi
fi

# ----------------------------------------------------------------------
# PHASE 6c -- Sync dashboard departments from the client's build-state
# ----------------------------------------------------------------------
# config/departments.json ships EMPTY on purpose so the stale 17-row template
# can never win. This phase regenerates it from the client's REAL ZHC
# departments.json + .workforce-build-state.json and re-seeds the workspaces
# table, so the dashboard always reflects what THIS client actually built.
# Idempotent -- safe to re-run on every install/resume/update.
# In --update-only mode this is the #109 fix: demo departments can never
# resurrect because the real build-state always wins.
log "INFO" "phase=6c sync-departments: starting"
SYNC_SCRIPT="$DASHBOARD_DIR/scripts/sync-departments-from-build-state.py"
if [[ -f "$SYNC_SCRIPT" ]]; then
  if ( cd "$DASHBOARD_DIR" && COMPANY_SLUG="${CLIENT_SLUG:-}" COMPANY_NAME="${COMPANY_NAME:-}" \
        python3 "$SYNC_SCRIPT" --company-slug "${CLIENT_SLUG:-}" >>"$LOG_FILE" 2>&1 ); then
    log "INFO" "phase=6c sync-departments: done -- dashboard synced from build-state (closes #109 on existing boxes)"
    if [[ -f "$STATE_FILE" ]]; then state_set '.commandCenterDepartmentsSynced = true'; fi
  else
    log "WARN" "phase=6c sync-departments: sync exited non-zero (dashboard will auto-seed from config/departments.json on next boot)"
    if [[ -f "$STATE_FILE" ]]; then state_set '.commandCenterDepartmentsSynced = false'; fi
  fi
else
  log "WARN" "phase=6c sync-departments: $SYNC_SCRIPT not found -- skipping (update the dashboard repo)"
  if [[ -f "$STATE_FILE" ]]; then state_set '.commandCenterDepartmentsSynced = "script-missing"'; fi
fi

# ----------------------------------------------------------------------
# PHASE 6d -- Populate agents.*_md columns from on-disk role folders
# v10.15.6 / v10.16.6 -- closes the NULL-columns gap (DB has NULLs for
# identity_md/soul_md/memory_md/how_to_md/heartbeat_md). Fallback for
# when the dashboard repo's own sync did not seed content columns.
# Idempotent via content_hash. Safe to re-run on every install/resume/update.
# ----------------------------------------------------------------------
log "INFO" "phase=6d sync-md-content: starting"
SYNC_MD_SCRIPT="$SKILL_DIR/scripts/sync-md-content-to-db.py"
if [[ -f "$SYNC_MD_SCRIPT" ]]; then
  if python3 "$SYNC_MD_SCRIPT" >>"$LOG_FILE" 2>&1; then
    log "INFO" "phase=6d sync-md-content: done -- agents.*_md columns populated from disk"
    if [[ -f "$STATE_FILE" ]]; then state_set '.commandCenterMdContentSynced = true'; fi
  else
    log "WARN" "phase=6d sync-md-content: exited non-zero (see $LOG_FILE) -- dashboard will keep showing NULLs"
    if [[ -f "$STATE_FILE" ]]; then state_set '.commandCenterMdContentSynced = false'; fi
  fi
else
  log "WARN" "phase=6d sync-md-content: $SYNC_MD_SCRIPT not found -- skipping (skill 32 not at v10.15.6/v10.16.6+)"
  if [[ -f "$STATE_FILE" ]]; then state_set '.commandCenterMdContentSynced = "script-missing"'; fi
fi

# ----------------------------------------------------------------------
# PHASE 6e -- Seed dashboard content (companies + head-agent row + starter task)
# ----------------------------------------------------------------------
# Wires the previously-orphaned seed-dashboard-content.py so the Kanban renders
# real cards on first load. The bug it fixes: every client board rendered five
# EMPTY columns because nothing wrote the companies/agents/tasks rows. Runs AFTER
# Phase 6b-seed (workspaces exist) in BOTH full and --update-only. Idempotent:
# only inserts agents/tasks for workspaces that have none yet, so a built box is
# never duplicated. WARN-only + state-recorded.
log "INFO" "phase=6e seed-dashboard-content: starting"
SEED_DASH="$SKILL_DIR/scripts/seed-dashboard-content.py"
if [[ -f "$SEED_DASH" ]] && command -v python3 >/dev/null 2>&1; then
  if COMPANY_NAME="${COMPANY_NAME:-}" python3 "$SEED_DASH" >>"$LOG_FILE" 2>&1; then
    log "INFO" "phase=6e seed-dashboard-content: done -- companies + head agents + starter tasks seeded (Kanban non-empty)"
    if [[ -f "$STATE_FILE" ]]; then state_set '.commandCenterDashboardContentSeeded = true'; fi
  else
    log "WARN" "phase=6e seed-dashboard-content: exited non-zero (see $LOG_FILE) -- board may render empty columns"
    if [[ -f "$STATE_FILE" ]]; then state_set '.commandCenterDashboardContentSeeded = false'; fi
  fi
else
  log "WARN" "phase=6e seed-dashboard-content: $SEED_DASH not found (or python3 missing) -- skipping (board may be empty)"
  if [[ -f "$STATE_FILE" ]]; then state_set '.commandCenterDashboardContentSeeded = "script-missing"'; fi
fi

# ----------------------------------------------------------------------
# PHASE 6e2 -- Department runtime parity guard (per-department reconciliation)
# ----------------------------------------------------------------------
# THE GAP THIS CLOSES: Phase 4's AGENT_COUNT check above is a blunt TOTAL COUNT
# floor over agents.list[] -- it passes as long as *some* two agents exist
# anywhere in agents.list[], and NEVER verifies that EVERY individual
# department seeded onto the board by 6b/6e (a `workspaces` row in
# mission-control.db) has ITS OWN matching runtime entry.
# materialize-dept-agents.sh (folder-scan of 3 hardcoded roots) and
# seed-workspaces.py (departments.json + its own separate folder-scan
# fallback) are two INDEPENDENT department-discovery mechanisms with NO
# cross-check between them. If N-2 departments wire correctly and 2 silently
# don't, the total-count floor still passes -- those 2 departments get a full
# board row (Kanban column, "<Name> Lead" agent row, starter task) and ZERO
# working OpenClaw runtime. That is exactly the `no_specialist_runtime`
# failure class blackceo-command-center's resolveSpecialistSessionKey()
# (src/lib/task-dispatcher.ts) documents: a task assigned to that
# department's dashboard agent can never resolve a runtime session key and is
# held "routed but not dispatched" forever -- invisible until a client
# notices nothing happens for that one department.
#
# Runs AFTER 6b (workspaces seeded) and 6e (dashboard agent rows exist) so
# every department this box currently knows about gets checked. Unlike
# 6b-6f (WARN-only), this IS a hard, install-blocking gate (fail-closed) --
# a genuine per-department mismatch calls fail_install, listing exactly which
# department(s) failed. A missing/empty mission-control.db (nothing seeded
# yet) is NOT a failure -- there is nothing to reconcile.
log "INFO" "phase=6e2 department-runtime-parity: starting"
DEPT_PARITY_GUARD="$SKILL_DIR/scripts/guard-department-runtime-parity.py"
if [[ -f "$DEPT_PARITY_GUARD" ]] && command -v python3 >/dev/null 2>&1; then
  DEPT_PARITY_OUT="$(python3 "$DEPT_PARITY_GUARD" --config "$OC_ROOT/openclaw.json" --json 2>&1)"; DEPT_PARITY_RC=$?
  printf '%s\n' "$DEPT_PARITY_OUT" >> "$LOG_FILE"
  if [[ "$DEPT_PARITY_RC" -eq 0 ]]; then
    DEPT_PARITY_CHECKED=$(printf '%s' "$DEPT_PARITY_OUT" | python3 -c "import json,sys; sys.stdout.write(str(json.load(sys.stdin).get('checked',0)))" 2>/dev/null || echo "0")
    log "INFO" "phase=6e2 department-runtime-parity: PASS (${DEPT_PARITY_CHECKED} department(s) checked, all have a matching runtime)"
    if [[ -f "$STATE_FILE" ]]; then state_set '.commandCenterDeptRuntimeParity = true'; fi
  else
    DEPT_PARITY_NAMES="$(printf '%s' "$DEPT_PARITY_OUT" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    names = [m.get('name', '?') for m in d.get('mismatches', [])]
    sys.stdout.write(', '.join(names) if names else '<unparseable guard output -- see log>')
except Exception:
    sys.stdout.write('<unparseable guard output -- see log>')
" 2>/dev/null || echo "<unparseable guard output -- see log>")"
    log "ERROR" "phase=6e2 department-runtime-parity: FAIL (rc=$DEPT_PARITY_RC) -- department(s) with no matching runtime: $DEPT_PARITY_NAMES"
    if [[ -f "$STATE_FILE" ]]; then state_set '.commandCenterDeptRuntimeParity = false'; fi
    fail_install "phase=6e2: department-runtime-parity guard found department(s) with a board row but NO matching OpenClaw runtime entry: ${DEPT_PARITY_NAMES} (rc=$DEPT_PARITY_RC; see $LOG_FILE for full detail; run materialize-dept-agents.sh then re-run install)"
  fi
else
  log "WARN" "phase=6e2 department-runtime-parity: $DEPT_PARITY_GUARD not found (or python3 missing) -- skipping (Skill 32 not at the version that ships this guard)"
  if [[ -f "$STATE_FILE" ]]; then state_set '.commandCenterDeptRuntimeParity = "script-missing"'; fi
fi

# ----------------------------------------------------------------------
# PHASE 6f -- CEO Performance Board KPI rollup (kpi-rollup.json)
# ----------------------------------------------------------------------
# Wires the previously-orphaned generate-kpi-rollup.py so the CEO Performance
# Board artifact (kpi-rollup.json) is written from the client's ZHC company +
# department configs. Non-fatal: exit 1 (no company config) / 2 (no dept configs)
# are expected on minimal boxes and recorded as WARN, never a hard fail. Runs in
# BOTH full and --update-only. WARN-only + state-recorded.
log "INFO" "phase=6f kpi-rollup: starting"
KPI_ROLLUP="$SKILL_DIR/scripts/generate-kpi-rollup.py"
if [[ -f "$KPI_ROLLUP" ]] && command -v python3 >/dev/null 2>&1; then
  _kpi_rc=0
  if [[ -n "${CLIENT_SLUG:-}" ]]; then
    python3 "$KPI_ROLLUP" --company-slug "$CLIENT_SLUG" >>"$LOG_FILE" 2>&1 || _kpi_rc=$?
  else
    python3 "$KPI_ROLLUP" >>"$LOG_FILE" 2>&1 || _kpi_rc=$?
  fi
  if [[ "$_kpi_rc" -eq 0 ]]; then
    log "INFO" "phase=6f kpi-rollup: done -- kpi-rollup.json written (CEO Performance Board)"
    if [[ -f "$STATE_FILE" ]]; then state_set '.commandCenterKpiRollupWritten = true'; fi
  else
    log "WARN" "phase=6f kpi-rollup: no ZHC company/department config to roll up yet (rc=$_kpi_rc, see $LOG_FILE) -- CEO board artifact deferred"
    if [[ -f "$STATE_FILE" ]]; then state_set '.commandCenterKpiRollupWritten = false'; fi
  fi
else
  log "WARN" "phase=6f kpi-rollup: $KPI_ROLLUP not found (or python3 missing) -- skipping"
  if [[ -f "$STATE_FILE" ]]; then state_set '.commandCenterKpiRollupWritten = "script-missing"'; fi
fi

# ----------------------------------------------------------------------
# PHASE 6g -- GHL credential preflight (operator-facing, NON-BLOCKING)
# ----------------------------------------------------------------------
# Skill 32 ingests GHL funnel/automation templates + stamps crm_platform, but it
# wires NO GHL credential (Skill 36/44 do). This preflight tells the OPERATOR
# (never the client -- WE MOVE IN SILENCE) when the GHL PIT is missing, so a CC
# whose GHL templates are discoverable-yet-unusable is never silent. Presence
# only -- the secret value is never read or printed. NEVER blocks the install
# (the board is valuable without GHL); NEVER silently no-ops.
log "INFO" "phase=6g ghl-preflight: starting"
GHL_SECRETS_ENV="$OC_ROOT/secrets/.env"
_ghl_pit=false; _ghl_loc=false
if [[ -f "$GHL_SECRETS_ENV" ]]; then
  grep -qE '^[[:space:]]*GOHIGHLEVEL_API_KEY=[^[:space:]]' "$GHL_SECRETS_ENV" 2>/dev/null && _ghl_pit=true
  grep -qE '^[[:space:]]*GOHIGHLEVEL_LOCATION_ID=[^[:space:]]' "$GHL_SECRETS_ENV" 2>/dev/null && _ghl_loc=true
fi
if [[ "$_ghl_pit" == "true" && "$_ghl_loc" == "true" ]]; then
  log "INFO" "phase=6g ghl-preflight: GOHIGHLEVEL_API_KEY (PIT) + GOHIGHLEVEL_LOCATION_ID present in secrets/.env -- department agents can act on GHL"
  [[ -f "$STATE_FILE" ]] && state_set '.commandCenterGhlCredPreflight = "present"'
else
  _ghl_missing=""
  [[ "$_ghl_pit" != "true" ]] && _ghl_missing="GOHIGHLEVEL_API_KEY (PIT)"
  [[ "$_ghl_loc" != "true" ]] && _ghl_missing="${_ghl_missing:+$_ghl_missing + }GOHIGHLEVEL_LOCATION_ID"
  log "WARN" "phase=6g ghl-preflight: MISSING $_ghl_missing in $GHL_SECRETS_ENV -- GHL funnel/automation templates are ingested but department agents CANNOT act on GHL until Skill 36 wires GOHIGHLEVEL_API_KEY (PIT) + GOHIGHLEVEL_LOCATION_ID into ~/.openclaw/secrets/.env. (Operator-only; CC + Kanban remain fully functional.)"
  # P3-2: carry the free-form missing-cred string via jq --arg, not interpolation.
  [[ -f "$STATE_FILE" ]] && state_set_arg '.commandCenterGhlCredPreflight = "missing" | .commandCenterGhlCredMissing = $val' "$_ghl_missing"
fi

# ----------------------------------------------------------------------
# PHASE 6i -- SOP V2 Library Ingestion (C2 fix: closes the CC SOP-library
# ghost)
# ----------------------------------------------------------------------
# THE GAP THIS CLOSES (finding C2): INSTALL.md has documented a "Phase 6c:
# SOP V2 Library Ingestion" step since v10.13.29 ("Agent Does This
# Automatically") but `run-full-install.sh` never actually called
# ingest-sop-library.sh -- confirmed live: `grep -c ingest-sop-library
# run-full-install.sh` == 0 before this phase existed. (Named 6i here, not
# 6c, because this file's Phase 6c is already the unrelated
# sync-departments-from-build-state step -- INSTALL.md's duplicate "Phase
# 6c" heading is renumbered to match.) Every install therefore ran on
# whatever CC's own autoSeedStarterSOPs boot-seed happened to write --
# observed live as 54 rows (30 test-dept residue + 24 stale legacy-alias
# rows) instead of the real ~2,555-row V2 library, silently starving
# dispatch_rules.sop_id matching + Triad routing. Two writers populate the
# SAME `sops` table and both are wired here: (1) ingest-sop-library.sh does
# the direct JSONL-asset upsert (its rows carry source NULL); (2) the CC
# converge(scope=sops) HTTP call runs importRoleLibrary() -- the on-disk
# departments/ role-library ingest that "never succeeded here" per the live
# evidence (rows carry source='role-library').
#
# BOTH are asserted, INDEPENDENTLY, by assert-sop-library-populated.py:
# --min-total (all rows) AND --min-role-library (source='role-library' rows).
# A single COUNT(*) conflates the two writers -- a perfect 2,555-row JSONL
# ingest with a FAILED converge yields ZERO role-library rows and sails
# through a bare count. That is precisely the live C2 shape, so it gets its
# own floor.
#
# The whole phase is FAIL-CLOSED: a failed ingest, an unparseable download
# count, a missing gate script, or ANY non-zero gate rc is a fail_install --
# never a degrade to a permissive floor. The CC boot-seed guarantees `sops`
# is non-empty by Phase 6, so every "just check it's not empty" fallback is a
# rubber stamp for the ghost. A gate that fails open is not a gate.
#
# Idempotent (both writers are upsert-only) -- safe to re-run on every
# install/resume/update, so it runs in BOTH full and --update-only mode
# (matching 6b/6c/6d/6e/6f/6g).
log "INFO" "phase=6i sop-library-ingestion: starting"
INGEST_SOP_SH="$SKILL_DIR/scripts/ingest-sop-library.sh"
ASSERT_SOP_PY="$SKILL_DIR/scripts/assert-sop-library-populated.py"

# NOTE ON THE STATE CONTRACT: .commandCenterSopLibraryIngested is a BOOLEAN.
# It was briefly a string on the skip paths ("script-missing" / "no-client-slug"),
# which is a fail-open in disguise: a non-empty string is TRUTHY, so every
# consumer doing `if (state.commandCenterSopLibraryIngested)` read a SKIPPED
# ingest as a SUCCESSFUL one -- the same "a state field actively asserts health
# it does not have" defect this whole phase exists to kill. Skips now write
# `false` and put the reason in .commandCenterSopLibrarySkipReason.
if [[ ! -f "$INGEST_SOP_SH" ]]; then
  # The ingester ships in THIS skill dir, next to this very script -- if it is
  # missing, the Skill 32 install is corrupt/partial. Fatal, exactly like the
  # missing row-count gate below: a Command Center whose SOP library was never
  # even attempted is the C2 ghost, and it must never ship with a green check.
  if [[ -f "$STATE_FILE" ]]; then state_set '.commandCenterSopLibraryIngested = false | .commandCenterSopLibrarySkipReason = "ingest-script-missing"'; fi
  fail_install "phase=6i: $INGEST_SOP_SH not found -- the SOP V2 library ingester is missing from this Skill 32 install, so the library would never be ingested and the Command Center would ship the boot-seed ghost. Re-run update-skills.sh to repair the skill dir, then re-run install."
elif [[ -z "${CLIENT_SLUG:-}" ]]; then
  # Reachable ONLY in --update-only mode (a full install hard-exits on a missing
  # slug during arg parsing) on a box whose state file records no companySlug.
  # Left non-fatal: this is a pre-existing box-state anomaly, not a library
  # defect, and hard-failing every slug-less update-only re-run is out of C2's
  # scope. It is recorded FALSY + with a reason, so nothing downstream can read
  # it as a successful ingest.
  log "WARN" "phase=6i sop-library-ingestion: no CLIENT_SLUG resolved -- SKIPPING the SOP library ingest (ingest-sop-library.sh requires a client slug). The SOP library is NOT verified on this run; re-run with the slug once known."
  if [[ -f "$STATE_FILE" ]]; then state_set '.commandCenterSopLibraryIngested = false | .commandCenterSopLibrarySkipReason = "no-client-slug"'; fi
else
  # ---- (1) direct JSONL-asset ingest -> `sops` table -------------------
  # FAIL-CLOSED. ingest-sop-library.sh runs under `set -euo pipefail` and only
  # prints its "downloaded N SOP records" line AFTER curl+gunzip both succeed.
  # So on ANY network failure / GitHub outage / rate-limit / asset removal /
  # gunzip error it aborts BEFORE that line: rc != 0 and NO count to parse.
  # The first cut of this phase then dropped --expected AND --min-total from
  # the gate below and let it fall back to its old floor of 1 -- but the CC
  # boot-seed (autoSeedStarterSOPs) has ALREADY filled `sops` by Phase 6, so
  # the table is never empty and the gate returned "healthy: 54 row(s) >= floor
  # 1" over the exact ghost it exists to catch, then stamped
  # commandCenterSopLibraryIngested=true. A gate that fails open is not a gate.
  # A failed ingest, or an ingest whose count we cannot read, means we have NO
  # trustworthy floor -- so we do not guess one, we FAIL THE INSTALL. Both
  # writers are idempotent upserts, so the operator just re-runs once the
  # asset/network is reachable again.
  SOP_INGEST_OUT="$(bash "$INGEST_SOP_SH" "$CLIENT_SLUG" 2>&1)"; SOP_INGEST_RC=$?
  printf '%s\n' "$SOP_INGEST_OUT" >> "$LOG_FILE"
  SOP_INGEST_TAIL="$(printf '%s' "$SOP_INGEST_OUT" | tail -n 3 | tr '\n' ' ')"

  if [[ "$SOP_INGEST_RC" -ne 0 ]]; then
    if [[ -f "$STATE_FILE" ]]; then state_set '.commandCenterSopLibraryIngested = false | .commandCenterSopConvergeStatus = "not-reached"'; fi
    fail_install "phase=6i: ingest-sop-library.sh FAILED (rc=$SOP_INGEST_RC) -- the SOP V2 library was NOT downloaded/ingested. Refusing to degrade to a not-empty floor: the CC boot-seed already populated \`sops\`, so any relaxed gate would rubber-stamp a ghost library. Fix the ingest (network/GitHub release asset/DB path), then re-run install (the ingest is an idempotent upsert). Last output: ${SOP_INGEST_TAIL} -- full log: $LOG_FILE"
  fi
  log "INFO" "phase=6i sop-library-ingestion: ingest-sop-library.sh completed (rc=0)"

  # The script's own "[sop-library] downloaded N SOP records" line is the ONLY
  # trustworthy floor for this run (never a hardcoded 2555, which would rot as
  # the library grows/shrinks across releases). No count parsed => no floor =>
  # FAIL, never a silent degrade.
  SOP_DOWNLOADED_COUNT="$(printf '%s' "$SOP_INGEST_OUT" | grep -oE 'downloaded [0-9]+ SOP records' | grep -oE '[0-9]+' | head -n1 || true)"
  if [[ -z "$SOP_DOWNLOADED_COUNT" ]]; then
    if [[ -f "$STATE_FILE" ]]; then state_set '.commandCenterSopLibraryIngested = false | .commandCenterSopConvergeStatus = "not-reached"'; fi
    fail_install "phase=6i: ingest-sop-library.sh exited 0 but printed NO 'downloaded N SOP records' line -- there is no trustworthy row floor for this run, and a relaxed gate would rubber-stamp the CC boot-seed ghost as a healthy library. This means the ingester changed its output contract or half-completed. See $LOG_FILE, then re-run install. Last output: ${SOP_INGEST_TAIL}"
  fi
  if [[ "$SOP_DOWNLOADED_COUNT" -lt 1 ]]; then
    if [[ -f "$STATE_FILE" ]]; then state_set '.commandCenterSopLibraryIngested = false | .commandCenterSopConvergeStatus = "not-reached"'; fi
    fail_install "phase=6i: ingest-sop-library.sh reported 'downloaded 0 SOP records' -- the release asset is empty or gunzip produced an empty file. The SOP V2 library would ship as a ghost. See $LOG_FILE, then re-run install."
  fi
  log "INFO" "phase=6i sop-library-ingestion: ingest reported $SOP_DOWNLOADED_COUNT SOP record(s) downloaded"

  # ---- (2) CC converge(scope=sops) -> importRoleLibrary() role rows ----
  # MC_API_TOKEN is provisioned into $DASHBOARD_DIR/.env.local by
  # cc_write_env_local (Phase 6, above) and CC is already running locally on
  # $DASHBOARD_PORT by this point in the sequence. Mirrors sync-extensions.sh's
  # existing converge call (same route, same scope contract).
  #
  # This call is the ONLY writer of role-library rows (source='role-library').
  # It is NOT best-effort: its outcome is ENFORCED BY DATA in step (3) via
  # --min-role-library, because the live C2 evidence is exactly "JSONL ingest
  # fine, ZERO role-library rows -- converge/importRoleLibrary never succeeded
  # here". A converge miss is a ghost role library (Triad routing starves), so
  # a non-ok status here does not fail the phase on its own -- the row assert
  # does, on evidence rather than on an HTTP status. The status is persisted to
  # the state file either way so the miss is durably recorded, not just logged.
  SOP_CONVERGE_STATUS="skipped"
  if [[ -f "$DASHBOARD_DIR/.env.local" ]]; then
    SOP_MC_TOKEN="$(cc_env_get "$DASHBOARD_DIR/.env.local" MC_API_TOKEN)"
    if [[ -n "$SOP_MC_TOKEN" ]]; then
      if curl -sf -X POST "http://127.0.0.1:$DASHBOARD_PORT/api/system/converge" \
          -H "Authorization: Bearer $SOP_MC_TOKEN" \
          -H "Content-Type: application/json" \
          -d '{"scope":"sops"}' \
          --max-time 60 >>"$LOG_FILE" 2>&1; then
        SOP_CONVERGE_STATUS="ok"
        log "INFO" "phase=6i sop-library-ingestion: CC converge(scope=sops) succeeded (role-library rows imported)"
      else
        SOP_CONVERGE_STATUS="failed"
        log "WARN" "phase=6i sop-library-ingestion: CC converge(scope=sops) failed (see $LOG_FILE) -- role-library rows are almost certainly missing; the row-count gate below asserts them and will fail the install"
      fi
      SOP_MC_TOKEN=""   # scrub from shell memory promptly
    else
      SOP_CONVERGE_STATUS="no-token"
      log "WARN" "phase=6i sop-library-ingestion: MC_API_TOKEN not found in $DASHBOARD_DIR/.env.local -- cannot call CC converge(scope=sops); the role-library assert below will fail the install"
    fi
  else
    SOP_CONVERGE_STATUS="no-env-local"
    log "WARN" "phase=6i sop-library-ingestion: $DASHBOARD_DIR/.env.local not found -- cannot call CC converge(scope=sops); the role-library assert below will fail the install"
  fi
  # Durably record the converge outcome BEFORE the gate runs, so the state file
  # carries the reason even when the gate then fail_install()s on it.
  state_set_arg '.commandCenterSopConvergeStatus = $val' "$SOP_CONVERGE_STATUS"

  # ---- (3) fail-loud row-count gate (BOTH writers, independently) -------
  # The gate script itself is now fail-closed (--min-total has no default: it
  # exits 3 rather than assume a floor). Belt AND braces: this phase must never
  # invoke it without a floor, and treats EVERY non-zero rc as a hard failure --
  # there is deliberately no "WARN + degrade" branch left for any rc, because
  # every such branch is a way for a ghost library to ship with a green check.
  if [[ ! -f "$ASSERT_SOP_PY" ]] || ! command -v python3 >/dev/null 2>&1; then
    if [[ -f "$STATE_FILE" ]]; then state_set '.commandCenterSopLibraryIngested = false'; fi
    fail_install "phase=6i: row-count gate unavailable ($ASSERT_SOP_PY missing, or python3 not on PATH) -- the SOP V2 library cannot be verified, and an unverified library is exactly the C2 ghost. Install python3 / update Skill 32 to the version shipping assert-sop-library-populated.py, then re-run install."
  fi

  # Floor scales with what THIS run's asset actually reported downloading
  # (>=1 guaranteed above). Half the downloaded count tolerates the upsert
  # errors / legacy-slug overlap the ingester itself reports, while still
  # sitting far above any boot-seed ghost (the live ghost was 54 rows vs a
  # ~1,277 floor for a 2,555-record asset).
  SOP_MIN_TOTAL=$(( SOP_DOWNLOADED_COUNT / 2 ))
  if [[ "$SOP_MIN_TOTAL" -lt 1 ]]; then SOP_MIN_TOTAL=1; fi
  SOP_ASSERT_OUT="$(python3 "$ASSERT_SOP_PY" --json \
      --expected "$SOP_DOWNLOADED_COUNT" \
      --min-total "$SOP_MIN_TOTAL" \
      --min-role-library 1 2>&1)"; SOP_ASSERT_RC=$?
  printf '%s\n' "$SOP_ASSERT_OUT" >> "$LOG_FILE"
  SOP_TOTAL="$(printf '%s' "$SOP_ASSERT_OUT" | python3 -c "import json,sys; sys.stdout.write(str(json.load(sys.stdin).get('total',0)))" 2>/dev/null || echo "0")"
  SOP_ROLE_TOTAL="$(printf '%s' "$SOP_ASSERT_OUT" | python3 -c "import json,sys; sys.stdout.write(str(json.load(sys.stdin).get('role_library_total',0)))" 2>/dev/null || echo "0")"
  SOP_MISMATCH="$(printf '%s' "$SOP_ASSERT_OUT" | python3 -c "import json,sys; sys.stdout.write('true' if json.load(sys.stdin).get('row_count_mismatch') else 'false')" 2>/dev/null || echo "false")"
  SOP_ASSERT_REASON="$(printf '%s' "$SOP_ASSERT_OUT" | python3 -c "import json,sys; sys.stdout.write(str(json.load(sys.stdin).get('reason','')))" 2>/dev/null || echo "$SOP_ASSERT_OUT")"

  if [[ "$SOP_ASSERT_RC" -eq 0 ]]; then
    log "INFO" "phase=6i sop-library-ingestion: PASS -- sops table has $SOP_TOTAL row(s) incl. $SOP_ROLE_TOTAL role-library row(s) (floor=$SOP_MIN_TOTAL, converge=$SOP_CONVERGE_STATUS)"
    if [[ -f "$STATE_FILE" ]]; then state_set ".commandCenterSopLibraryIngested = true | .commandCenterSopLibraryTotal = $SOP_TOTAL | .commandCenterSopLibraryRoleLibraryTotal = $SOP_ROLE_TOTAL"; fi
    if [[ "$SOP_MISMATCH" == "true" ]]; then
      # fail-WARN per the C2 spec (row-count != downloaded count is NOT a
      # ghost by itself -- upsert errors / legacy overlap are expected).
      log "WARN" "phase=6i sop-library-ingestion: row-count mismatch vs downloaded count ($SOP_DOWNLOADED_COUNT) -- non-blocking, see $LOG_FILE"
    fi
  else
    # ANY non-zero rc is a hard failure: 1=GHOST (total below floor / no table),
    # 2=no mission-control.db, 3=NO FLOOR (gate invoked without --min-total --
    # unreachable from here, kept fatal so it can never regress into a rubber
    # stamp), 4=NO ROLE LIBRARY (converge/importRoleLibrary never landed a
    # single source='role-library' row: the JSONL ingest can be perfectly
    # healthy and the role library still be a ghost -- the live C2 shape).
    # C2 is P0 precisely because a fresh install silently claiming success over
    # a ghost SOP library is the bug. FAIL LOUD -- never a silent degrade.
    if [[ -f "$STATE_FILE" ]]; then state_set ".commandCenterSopLibraryIngested = false | .commandCenterSopLibraryTotal = $SOP_TOTAL | .commandCenterSopLibraryRoleLibraryTotal = $SOP_ROLE_TOTAL"; fi
    fail_install "phase=6i: SOP V2 library gate FAILED (rc=$SOP_ASSERT_RC) after ingest-sop-library.sh (downloaded=$SOP_DOWNLOADED_COUNT) + CC converge(scope=sops) (status=$SOP_CONVERGE_STATUS): ${SOP_ASSERT_REASON} -- the Command Center SOP library would ship as a ghost (dispatch_rules.sop_id matching + Triad routing starved). See $LOG_FILE for the ingest/converge/assert output, then re-run install."
  fi
fi

# ----------------------------------------------------------------------
# PHASE 7 — Verification (local :4000 + subdomain)
# ----------------------------------------------------------------------
log "INFO" "phase=7 verification: starting"
LOCAL_OK=0
REMOTE_OK=0

if [[ "$UPDATE_ONLY" == "true" ]]; then
  # Quick health check: just verify the local dashboard is responding
  LOCAL_CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "http://127.0.0.1:$DASHBOARD_PORT/" 2>/dev/null || echo "000")
  if [[ "$LOCAL_CODE" =~ ^2 ]]; then
    LOCAL_OK=1
    log "INFO" "phase=7 (update-only): dashboard responding $LOCAL_CODE on :$DASHBOARD_PORT"
  else
    log "WARN" "phase=7 (update-only): dashboard returned $LOCAL_CODE — check: pm2 logs blackceo-command-center"
  fi
else
  # Local check (Next.js dev/start server on :4000)
  LOCAL_CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "http://127.0.0.1:$DASHBOARD_PORT/" 2>/dev/null || echo "000")
  if [[ "$LOCAL_CODE" =~ ^2 ]]; then
    LOCAL_OK=1
    log "INFO" "phase=7: local dashboard responding $LOCAL_CODE on :$DASHBOARD_PORT"
  else
    log "WARN" "phase=7: local dashboard returned $LOCAL_CODE on :$DASHBOARD_PORT — check pm2 logs blackceo-command-center"
  fi

  # Remote check (cloudflared tunnel subdomain)
  REMOTE_URL=$(state_get '.commandCenterUrl')
  if [[ -n "$REMOTE_URL" && "$REMOTE_URL" != "null" && "$REMOTE_URL" != "http://127.0.0.1:4000/" ]]; then
    REMOTE_CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$REMOTE_URL" 2>/dev/null || echo "000")
    if [[ "$REMOTE_CODE" =~ ^2 ]]; then
      REMOTE_OK=1
      log "INFO" "phase=7: remote dashboard responding $REMOTE_CODE at $REMOTE_URL"
    else
      log "WARN" "phase=7: remote dashboard returned $REMOTE_CODE at $REMOTE_URL — cloudflared still warming up?"
    fi
  fi
fi

if [[ -f "$STATE_FILE" ]]; then
  state_set ".commandCenterVerification = { local: ${LOCAL_OK}, remote: ${REMOTE_OK}, checkedAt: \"$(now_iso)\" }"
fi

# ----------------------------------------------------------------------
# PHASE 7z — ZERO HUMAN EXPERIENCE acceptance gate (ZHE_SEQUENCE_V1 / plan W1.2)
# ----------------------------------------------------------------------
# The single post-interview acceptance gate. After the full provisioning above
# (dept agents registered, personas section-tagged, CC board + Kanban, AGENTS.md
# stamped), prove-zhe.py asserts the WHOLE Zero Human Experience landed for THIS
# box, with a receipt. Doctrine: 23-ai-workforce-blueprint/ZERO-HUMAN-EXPERIENCE.md.
#
# An interview that did NOT complete is EXEMPT (prover passes, exit 0). A missing
# prover is a WARN (recorded, never silently green).
#
# BLOCKING BY DEFAULT (Issue #6, v17.0.11): the RED-first precondition has landed
# (apply-fleet-standards.sh stamps the persona-reflex / full-context-handoff /
# reporting / platform-facts markers into AGENTS.md), so this gate now HARD-FAILS
# the install by default when the prover reports FAIL. The default is safe for
# fresh builds because an interview that did NOT complete is EXEMPT (prover exits
# 0). An explicit ZHE_ENFORCE=0 escape hatch is retained to unblock a box while a
# genuine prover regression is triaged. A hard fail marks the install failed so the
# resume cron re-proves on the next update (auto-repair).
log "INFO" "phase=7z zhe-gate: starting"
ZHE_PROVER=""
for _cand in \
  "$(dirname "$SKILL_DIR")/23-ai-workforce-blueprint/scripts/prove-zhe.py" \
  "$HOME/.openclaw/skills/23-ai-workforce-blueprint/scripts/prove-zhe.py" \
  "/data/.openclaw/skills/23-ai-workforce-blueprint/scripts/prove-zhe.py"; do
  if [[ -f "$_cand" ]]; then ZHE_PROVER="$_cand"; break; fi
done
if [[ -z "$ZHE_PROVER" ]]; then
  log "WARN" "phase=7z zhe-gate: prove-zhe.py not found in any skill-23 location — skipping ZHE acceptance gate"
  [[ -f "$STATE_FILE" ]] && state_set ".zheGateStatus = \"prover-missing\" | .zheGateCheckedAt = \"$(now_iso)\""
else
  ZHE_OUT="$(python3 "$ZHE_PROVER" --local "$OC_ROOT" 2>&1)"; ZHE_RC=$?
  printf '%s\n' "$ZHE_OUT" >> "$LOG_FILE"
  if [[ "$ZHE_RC" -eq 0 ]]; then
    log "INFO" "phase=7z zhe-gate: PASS — full ZERO HUMAN EXPERIENCE landed (or box exempt)"
    [[ -f "$STATE_FILE" ]] && state_set ".zheGateStatus = \"pass\" | .zheGateCheckedAt = \"$(now_iso)\""
  else
    log "ERROR" "phase=7z zhe-gate: FAIL — a ZHE step did not land (prove-zhe rc=$ZHE_RC)"
    printf '%s\n' "$ZHE_OUT" | grep -E '\[FAIL\]|OVERALL' | sed 's/^/  [zhe] /'
    [[ -f "$STATE_FILE" ]] && state_set ".zheGateStatus = \"failed\" | .zheGateRc = $ZHE_RC | .zheGateCheckedAt = \"$(now_iso)\""
    # Blocking BY DEFAULT (Issue #6): ZHE_ENFORCE unset behaves as =1. The only way
    # to reach the FINAL block with a failed ZHE gate is the explicit ZHE_ENFORCE=0
    # escape hatch — the FINAL fail-closed stamp then surfaces it as done-degraded.
    if [[ "${ZHE_ENFORCE:-1}" == "1" ]]; then
      fail_install "phase=7z: ZERO HUMAN EXPERIENCE acceptance gate failed (ZHE_ENFORCE=1 default, prove-zhe rc=$ZHE_RC)"
    else
      log "WARN" "phase=7z zhe-gate: NOT blocking install (ZHE_ENFORCE=0 escape hatch); resume cron re-proves on next update"
    fi
  fi
fi

# ----------------------------------------------------------------------
# FINAL — Mark commandCenterStatus (FAIL-CLOSED: done only when the board built)
# ----------------------------------------------------------------------
# Issue #6 fail-closed stamping: a remote-verification miss is still "done"
# (dashboard is locally up; the cron resume layer retries the tunnel). BUT a box
# whose REQUIRED board-provisioning sub-phases did not land must NOT report "done"
# — that is the "no false done" violation. Required sub-phases each record
# true | false | "script-missing":
#   6b .commandCenterWorkspacesSeeded       (empty board otherwise)
#   6c .commandCenterDepartmentsSynced      (dashboard shows stale/empty depts)
#   6d .commandCenterMdContentSynced        (agents.*_md columns stay NULL)
#   6e .commandCenterDashboardContentSeeded (Kanban renders empty columns)
# 6f (kpi rollup) is DELIBERATELY EXCLUDED: rc 1/2 is EXPECTED on minimal boxes
# (WARN-only by design), so it must never withhold "done". We also fold in a
# FAILED ZHE acceptance gate (only reachable here via the ZHE_ENFORCE=0 escape
# hatch — the default hard-fails at Phase 7z). When any required sub-phase did not
# reach true we stamp commandCenterStatus="done-degraded" (never a hard install
# fail — exit 0, board is locally up) so the resume cron revisits it: run-closeout
# step 1 only skips when status == "done", so done-degraded re-invokes
# run-full-install on the next pass (idempotent auto-repair) instead of falsely
# reporting done.
FINAL_STATUS="done"
if [[ -f "$STATE_FILE" ]]; then
  if [[ -z "$(state_get '.commandCenterUrl')" || "$(state_get '.commandCenterUrl')" == "null" ]]; then
    state_set ".commandCenterUrl = \"http://127.0.0.1:$DASHBOARD_PORT/\""
  fi
  # A required sub-phase counts as degraded only when its key is PRESENT and not
  # `true` (false or "script-missing"). An absent key (older state) is not treated
  # as a regression. jq's `//` collapses false→empty, so this membership test is
  # done in one jq pass rather than via state_get.
  DEGRADED_PHASES="$(jq -r '
    [ {k:"ccBuildFresh(6)",            v:.commandCenterBuildFresh},
      {k:"workspacesSeeded(6b)",       v:.commandCenterWorkspacesSeeded},
      {k:"departmentsSynced(6c)",      v:.commandCenterDepartmentsSynced},
      {k:"mdContentSynced(6d)",        v:.commandCenterMdContentSynced},
      {k:"dashboardContentSeeded(6e)", v:.commandCenterDashboardContentSeeded},
      {k:"deptRuntimeParity(6e2)",     v:.commandCenterDeptRuntimeParity} ]
    | map(select(.v != null and .v != true) | .k) | join(", ")
  ' "$STATE_FILE" 2>/dev/null || echo "")"
  if [[ "$(state_get '.zheGateStatus')" == "failed" ]]; then
    DEGRADED_PHASES="${DEGRADED_PHASES:+$DEGRADED_PHASES, }zheGate(failed)"
  fi

  if [[ -n "$DEGRADED_PHASES" ]]; then
    FINAL_STATUS="done-degraded"
    # Operator-only surface (WE MOVE IN SILENCE — never client). The board is up but
    # incomplete; do not claim done.
    log "WARN" "FINAL: Command Center provisioning DEGRADED — withholding 'done'. Incomplete/failed required sub-phases: $DEGRADED_PHASES. Stamping commandCenterStatus=done-degraded so the resume cron revisits (dashboard is locally up on :$DASHBOARD_PORT)."
    # now_iso() is a fixed-format literal (safe to interpolate); the free-form phase
    # list is bound via --arg (state_set_arg) so it can never corrupt/inject state.
    state_set_arg ".commandCenterStatus = \"done-degraded\" | .commandCenterDegradedPhases = \$val | .commandCenterCompletedAt = \"$(now_iso)\"" "$DEGRADED_PHASES"
  else
    state_set ".commandCenterStatus = \"done\" | .commandCenterDegradedPhases = null | .commandCenterCompletedAt = \"$(now_iso)\""
  fi
fi
log "INFO" "run-full-install complete: update_only=$UPDATE_ONLY commandCenterStatus=$FINAL_STATUS local=$LOCAL_OK remote=$REMOTE_OK"
exit 0
