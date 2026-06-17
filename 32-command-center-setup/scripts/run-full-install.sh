#!/usr/bin/env bash
# run-full-install.sh — Skill 32 top-level orchestrator (v10.14.20).
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
#   bash run-full-install.sh <client-slug> <company-name> <contact-email>
#
# Exit codes:
#   0 — all phases succeeded (or were already done)
#   1 — fatal error in a phase that cannot be auto-resumed; state file is
#       updated with commandCenterStatus=failed and the failure reason.

set -u

CLIENT_SLUG="${1:?Usage: run-full-install.sh <client-slug> <company-name> <contact-email>}"
COMPANY_NAME="${2:?Missing company name}"
CONTACT_EMAIL="${3:?Missing contact email}"

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

log() {
  printf '%s [%-5s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" >> "$LOG_FILE"
  printf '%s [%-5s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2"
}

state_get() {
  jq -r "$1 // empty" "$STATE_FILE" 2>/dev/null
}

state_set() {
  # Usage: state_set '.field = value | .other = value'
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

now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }

fail_install() {
  local reason="$1"
  log "ERROR" "marking commandCenterStatus failed: $reason"
  state_set ".commandCenterStatus = \"failed\" | .commandCenterFailureReason = \"$reason\""
  exit 1
}

# ---- preflight ----
if [[ ! -f "$STATE_FILE" ]]; then
  log "ERROR" "no state file at $STATE_FILE — refusing to run"
  exit 1
fi
for cmd in jq curl git npm python3; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    fail_install "preflight: missing required command: $cmd"
  fi
done

log "INFO" "run-full-install starting: slug=$CLIENT_SLUG company=$COMPANY_NAME email=$CONTACT_EMAIL"
state_set '.commandCenterStatus = "building"'

# ----------------------------------------------------------------------
# PHASE 1 — Prerequisites (pm2 + openclaw doctor --fix)
# ----------------------------------------------------------------------
log "INFO" "phase=1 prereqs: starting"
if [[ "$(state_get '.commandCenterPhase1Done')" == "true" ]]; then
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

# ----------------------------------------------------------------------
# PHASE 3 — Workspace department folders
# ----------------------------------------------------------------------
# Skill 23 writes departments to $OC_ROOT/workspace/departments/<slug>/.
# Skill 32 INSTALL.md Phase 3 requires those exist also under
# $OC_ROOT/workspaces/command-center/<slug>/. We mirror by creating the
# parallel tree if missing. Idempotent — symlinks/mkdir -p, no overwrites.
log "INFO" "phase=3 workspace-folders: starting"
if [[ "$(state_get '.commandCenterPhase3Done')" == "true" ]]; then
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
if [[ "$(state_get '.commandCenterPhase4Done')" == "true" ]]; then
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
# Creating Telegram topics requires the supergroup to exist + the bot to
# be admin with Manage Topics. Both require physical actions on the owner's
# phone (Phase 2 in INSTALL.md). We log a TODO line, mark the phase as
# skipped-manual, and proceed — Phase 6 doesn't depend on topics being live.
log "INFO" "phase=5 telegram-topics: SKIPPED (manual step required)"
log "INFO" "phase=5 TODO: owner must create topics in supergroup per INSTALL.md Phase 5, then bind each topic to its dept agent in openclaw.json (bindings[] array)"
state_set '.commandCenterPhase5Status = "manual-todo"'

# ----------------------------------------------------------------------
# PHASE 6 — Dashboard deploy (the missing piece that never ran)
# ----------------------------------------------------------------------
log "INFO" "phase=6 dashboard-deploy: starting"
if [[ "$(state_get '.commandCenterPhase6Done')" == "true" ]]; then
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

  log "INFO" "phase=6: npm run db:push"
  if ! ( cd "$DASHBOARD_DIR" && npm run db:push >>"$LOG_FILE" 2>&1 ); then
    fail_install "phase=6: npm run db:push failed"
  fi

  log "INFO" "phase=6: npm run db:seed"
  if ! ( cd "$DASHBOARD_DIR" && npm run db:seed >>"$LOG_FILE" 2>&1 ); then
    log "WARN" "phase=6: npm run db:seed failed — dashboard will still start but workspace selector may be empty"
  fi

  # Explicit PORT=4000 is the fix for the EADDRINUSE / random-port bug that
  # hit a client box. Some upstream env was leaking a different PORT which
  # caused Next.js to bind somewhere unpredictable. Pinning it here makes
  # the bind deterministic and matches Phase 6.6 of INSTALL.md.
  log "INFO" "phase=6: starting dashboard via pm2 on PORT=$DASHBOARD_PORT"
  pm2 delete blackceo-command-center >/dev/null 2>&1 || true
  if ! ( cd "$DASHBOARD_DIR" && PORT=$DASHBOARD_PORT pm2 start npm --name blackceo-command-center -- start >>"$LOG_FILE" 2>&1 ); then
    fail_install "phase=6: pm2 start failed"
  fi
  pm2 save >>"$LOG_FILE" 2>&1 || true

  state_set '.commandCenterPhase6Done = true'
  log "INFO" "phase=6 dashboard-deploy: done"
fi

# ----------------------------------------------------------------------
# PHASE 6c -- Sync dashboard departments from the client's build-state
# ----------------------------------------------------------------------
# config/departments.json ships EMPTY on purpose so the stale 17-row template
# can never win. This phase regenerates it from the client's REAL ZHC
# departments.json + .workforce-build-state.json and re-seeds the workspaces
# table, so the dashboard always reflects what THIS client actually built.
# Idempotent -- safe to re-run on every install/resume.
log "INFO" "phase=6c sync-departments: starting"
SYNC_SCRIPT="$DASHBOARD_DIR/scripts/sync-departments-from-build-state.py"
if [[ -f "$SYNC_SCRIPT" ]]; then
  if ( cd "$DASHBOARD_DIR" && COMPANY_SLUG="$CLIENT_SLUG" COMPANY_NAME="$COMPANY_NAME" \
        python3 "$SYNC_SCRIPT" --company-slug "$CLIENT_SLUG" >>"$LOG_FILE" 2>&1 ); then
    log "INFO" "phase=6c sync-departments: done -- dashboard synced from build-state"
    state_set '.commandCenterDepartmentsSynced = true'
  else
    log "WARN" "phase=6c sync-departments: sync exited non-zero (dashboard will auto-seed from config/departments.json on next boot)"
    state_set '.commandCenterDepartmentsSynced = false'
  fi
else
  log "WARN" "phase=6c sync-departments: $SYNC_SCRIPT not found -- skipping (update the dashboard repo)"
  state_set '.commandCenterDepartmentsSynced = "script-missing"'
fi

# ----------------------------------------------------------------------
# PHASE 6d -- Populate agents.*_md columns from on-disk role folders
# v10.15.6 / v10.16.6 -- closes the NULL-columns gap (DB has NULLs for
# identity_md/soul_md/memory_md/how_to_md/heartbeat_md). Fallback for
# when the dashboard repo's own sync did not seed content columns.
# Idempotent via content_hash. Safe to re-run on every install/resume.
# ----------------------------------------------------------------------
log "INFO" "phase=6d sync-md-content: starting"
SYNC_MD_SCRIPT="$SKILL_DIR/scripts/sync-md-content-to-db.py"
if [[ -f "$SYNC_MD_SCRIPT" ]]; then
  if python3 "$SYNC_MD_SCRIPT" >>"$LOG_FILE" 2>&1; then
    log "INFO" "phase=6d sync-md-content: done -- agents.*_md columns populated from disk"
    state_set '.commandCenterMdContentSynced = true'
  else
    log "WARN" "phase=6d sync-md-content: exited non-zero (see $LOG_FILE) -- dashboard will keep showing NULLs"
    state_set '.commandCenterMdContentSynced = false'
  fi
else
  log "WARN" "phase=6d sync-md-content: $SYNC_MD_SCRIPT not found -- skipping (skill 32 not at v10.15.6/v10.16.6+)"
  state_set '.commandCenterMdContentSynced = "script-missing"'
fi

# ----------------------------------------------------------------------
# PHASE 6b — Tunnel (n8n webhook + cloudflared)
# ----------------------------------------------------------------------
log "INFO" "phase=6b tunnel: starting"
existing_url=$(state_get '.commandCenterUrl')
if [[ -n "$existing_url" && "$existing_url" != "null" && "$existing_url" != "http://127.0.0.1:4000/" ]]; then
  log "INFO" "phase=6b tunnel: commandCenterUrl already set ($existing_url) — skipping"
else
  TUNNEL_SCRIPT="$SKILL_DIR/scripts/create-tunnel.sh"
  if [[ ! -x "$TUNNEL_SCRIPT" ]]; then
    log "WARN" "phase=6b: create-tunnel.sh not executable at $TUNNEL_SCRIPT — marking tunnel as todo"
    state_set '.commandCenterPhase6bStatus = "skipped-script-missing"'
  else
    log "INFO" "phase=6b: invoking create-tunnel.sh $CLIENT_SLUG $COMPANY_NAME $CONTACT_EMAIL"
    if ! bash "$TUNNEL_SCRIPT" "$CLIENT_SLUG" "$COMPANY_NAME" "$CONTACT_EMAIL" >>"$LOG_FILE" 2>&1; then
      log "WARN" "phase=6b: create-tunnel.sh exited non-zero — leaving commandCenterUrl unset, dashboard still reachable locally"
      state_set '.commandCenterPhase6bStatus = "failed-webhook"'
    else
      # Try to recover the subdomain from the .env file the tunnel script wrote
      SUBDOMAIN_HINT=""
      if [[ -f "$OC_ROOT/.env" ]]; then
        SUBDOMAIN_HINT="$CLIENT_SLUG.zerohumanworkforce.com"
      fi
      if [[ -n "$SUBDOMAIN_HINT" ]]; then
        state_set ".commandCenterUrl = \"https://$SUBDOMAIN_HINT\" | .commandCenterPhase6bStatus = \"done\""
        log "INFO" "phase=6b tunnel: done — https://$SUBDOMAIN_HINT"
      else
        state_set '.commandCenterPhase6bStatus = "done-no-subdomain-recorded"'
        log "INFO" "phase=6b tunnel: done (subdomain not recovered into state)"
      fi
    fi
  fi
fi

# ----------------------------------------------------------------------
# PHASE 7 — Verification (local :4000 + subdomain)
# ----------------------------------------------------------------------
log "INFO" "phase=7 verification: starting"
LOCAL_OK=0
REMOTE_OK=0

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

state_set ".commandCenterVerification = { local: ${LOCAL_OK}, remote: ${REMOTE_OK}, checkedAt: \"$(now_iso)\" }"

# ----------------------------------------------------------------------
# FINAL — Mark commandCenterStatus = done (always set on reaching here)
# ----------------------------------------------------------------------
# Even if remote verification failed, we mark done because the dashboard is
# locally up and the cron resume layer will retry the tunnel + verification.
# The state captures exactly what worked so the next pass is informed.
if [[ -z "$(state_get '.commandCenterUrl')" || "$(state_get '.commandCenterUrl')" == "null" ]]; then
  state_set ".commandCenterUrl = \"http://127.0.0.1:$DASHBOARD_PORT/\""
fi
state_set ".commandCenterStatus = \"done\" | .commandCenterCompletedAt = \"$(now_iso)\""
log "INFO" "run-full-install complete: commandCenterStatus=done commandCenterUrl=$(state_get '.commandCenterUrl') local=$LOCAL_OK remote=$REMOTE_OK"
exit 0
