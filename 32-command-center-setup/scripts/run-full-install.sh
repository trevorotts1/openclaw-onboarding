#!/usr/bin/env bash
# run-full-install.sh — Skill 32 top-level orchestrator (v10.14.21).
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

# ─── INTERVIEW-COMPLETE PRECONDITION (binding) ────────────────────────────────
# RULE: a client gets a Command Center + zero-human company ONLY after their AI
# Workforce interview is COMPLETE. If it is not, REPORT "interview not completed
# yet" and EXIT CLEAN — do NOT seed workspaces, materialize agents, or scaffold
# the default department floor onto a 'default' company. (See SKILL.md
# "Interview-Complete Precondition" + PREREQS.json interview-complete entry.)
#
# --update-only is EXEMPT: it only refreshes an ALREADY-built CC (git pull / npm /
# db:push) and must keep working for provisioned boxes whose flag predates this gate.
if [[ "$UPDATE_ONLY" != "true" ]]; then
  if [[ ! -f "$STATE_FILE" ]]; then
    log "INFO" "interview-gate: no .workforce-build-state.json — interview not started; REPORTING not-completed and exiting clean (no scaffolding)."
    echo "INTERVIEW_NOT_COMPLETE: no workforce-build state on this box — AI Workforce interview not completed yet. Command Center NOT built." >&2
    exit 0
  fi
  # FAST PRE-CHECK: the bare flag. Necessary but NOT sufficient (SKILL.md demands
  # multi-signal corroboration — the flag alone is set even on the fabricating path).
  INTERVIEW_COMPLETE=$(state_get '.interviewComplete')
  if [[ "$INTERVIEW_COMPLETE" != "true" ]]; then
    log "INFO" "interview-gate: interviewComplete=${INTERVIEW_COMPLETE:-<unset>} — REPORTING 'interview not completed yet' and exiting clean. NOT seeding/scaffolding."
    state_set '.commandCenterStatus = "interview-pending" | .commandCenterGateReason = "AI Workforce interview not completed (interviewComplete != true) — Command Center build is gated until the owner finishes their interview."'
    echo "INTERVIEW_NOT_COMPLETE: interviewComplete != true — AI Workforce interview not completed yet. Command Center NOT built (this is expected, not an error)." >&2
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
    echo "INTERVIEW_QC_UNVERIFIED: qc-interview-completion.py not found — cannot corroborate the interviewComplete flag. Command Center NOT built (fail-closed; fix the Skill 23 install)." >&2
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
    echo "INTERVIEW_PENDING: interviewComplete=true but qc-interview-completion.py rc=$QC_RC (not PASS) — interview not corroborated complete. Command Center NOT built (gated; expected until QC passes)." >&2
    exit 0
  fi
  log "INFO" "interview-gate: qc-interview-completion.py PASS (rc=0) — interview corroborated. Proceeding with Command Center install."
fi

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
# PHASE 6 — Dashboard deploy / update
# ----------------------------------------------------------------------
log "INFO" "phase=6 dashboard-deploy: starting"
if [[ "$UPDATE_ONLY" == "true" ]]; then
  # --update-only: git pull --ff-only + npm install + db:push + pm2 restart.
  # Skips db:seed (protects client-customized rows).
  # Skips git-clone (we already verified .git exists before invoking this flag).
  log "INFO" "phase=6 dashboard-update: --update-only — git pull + npm install + db:push + pm2 restart (no db:seed)"
  if [[ ! -d "$DASHBOARD_DIR/.git" ]]; then
    log "WARN" "phase=6 dashboard-update: $DASHBOARD_DIR/.git not found — run full install first (skipping refresh)"
  else
    ( cd "$DASHBOARD_DIR" && git pull --ff-only >>"$LOG_FILE" 2>&1 ) \
      && log "INFO" "phase=6: git pull --ff-only done" \
      || log "WARN" "phase=6: git pull non-clean — continuing with existing checkout"
    ( cd "$DASHBOARD_DIR" && npm install >>"$LOG_FILE" 2>&1 ) \
      && log "INFO" "phase=6: npm install done" \
      || log "WARN" "phase=6: npm install reported errors (continuing)"
    ( cd "$DASHBOARD_DIR" && npm run db:push >>"$LOG_FILE" 2>&1 ) \
      && log "INFO" "phase=6: db:push done (idempotent drizzle migrations; no data wipe)" \
      || log "WARN" "phase=6: db:push reported errors (continuing)"
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

  log "INFO" "phase=6: npm run db:push"
  if ! ( cd "$DASHBOARD_DIR" && npm run db:push >>"$LOG_FILE" 2>&1 ); then
    fail_install "phase=6: npm run db:push failed"
  fi

  log "INFO" "phase=6: npm run db:seed"
  if ! ( cd "$DASHBOARD_DIR" && npm run db:seed >>"$LOG_FILE" 2>&1 ); then
    log "WARN" "phase=6: npm run db:seed failed — dashboard will still start but workspace selector may be empty"
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
# RED-FIRST CONTRACT (plan §6 / spec §1): the prover only goes fully green once
# W5/W6/W7 stamp the persona-reflex / full-context-handoff / reporting /
# platform-facts markers into AGENTS.md. Until then it reports FAIL loud and
# records the verdict, but only HARD-FAILS the install when ZHE_ENFORCE=1 — so the
# gate is wired now and becomes blocking by flipping one env var at the "flip green"
# milestone, without breaking in-flight builds. A hard fail marks the install
# failed so the resume cron re-proves on the next update (auto-repair).
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
    if [[ "${ZHE_ENFORCE:-0}" == "1" ]]; then
      fail_install "phase=7z: ZERO HUMAN EXPERIENCE acceptance gate failed (ZHE_ENFORCE=1, prove-zhe rc=$ZHE_RC)"
    else
      log "WARN" "phase=7z zhe-gate: NOT blocking install (ZHE_ENFORCE!=1, RED-first); resume cron re-proves on next update"
    fi
  fi
fi

# ----------------------------------------------------------------------
# FINAL — Mark commandCenterStatus = done (always set on reaching here)
# ----------------------------------------------------------------------
# Even if remote verification failed, we mark done because the dashboard is
# locally up and the cron resume layer will retry the tunnel + verification.
# The state captures exactly what worked so the next pass is informed.
if [[ -f "$STATE_FILE" ]]; then
  if [[ -z "$(state_get '.commandCenterUrl')" || "$(state_get '.commandCenterUrl')" == "null" ]]; then
    state_set ".commandCenterUrl = \"http://127.0.0.1:$DASHBOARD_PORT/\""
  fi
  state_set ".commandCenterStatus = \"done\" | .commandCenterCompletedAt = \"$(now_iso)\""
fi
log "INFO" "run-full-install complete: update_only=$UPDATE_ONLY commandCenterStatus=done local=$LOCAL_OK remote=$REMOTE_OK"
exit 0
