#!/usr/bin/env bash
# 04-register-crons.sh
# Registers the recurring OpenClaw cron jobs for the Conversational AI System.
# Idempotent: each job is gated by name via an exact JSON match (see IDEMPOTENCY
# note below) — NEVER a text-table grep.
# Playbook v5.14 — Step 9 + Step 3.5H.
#
# CRON REGISTRATION (2026-05-29): the legacy `cron.jobs` JSON config block does NOT
# validate on openclaw 2026.5.27 — writing it makes `openclaw config validate` FAIL and
# the gateway never runs the jobs. Crons MUST be registered through the gateway cron
# store via the `openclaw cron add` CLI (see references/GHL-INBOUND-AND-PLAYBOOKS.md §13).
# This script no longer touches openclaw.json at all.
#
# IDEMPOTENCY (fix/industry-gate-and-idempotent-crons, 2026-07-11 — BUG FIX): this
# script used to guard every add with `openclaw cron list | grep -q "$name"` — a
# TEXT-TABLE match. `cron list`'s text table truncates names longer than ~22 chars
# (appends "..."). Four of this file's cron names exceed that
# (conversation-log-summarizer=27, proactive-suggestions-scan=26,
# analytics-weekly-digest=23, system-health-heartbeat=23), so the guard could
# false-negative on a truncated row and re-add a duplicate on every re-run. Replaced
# with oc_cron_present() (shared-utils/cron-lib.sh) — the same exact JSON name-match
# fix scripts/ensure-pipeline-crons.sh already shipped (v13.0.2) for its own crons.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROUTING_AGENT_ID="${ROUTING_AGENT_ID:-main}"

# ---- JSON-idempotency helper (oc_cron_present) -----------------------------
_CRON_LIB=""
for _cand in \
  "$SCRIPT_DIR/../../shared-utils/cron-lib.sh" \
  "$(cd "$SCRIPT_DIR/../.." 2>/dev/null && pwd)/shared-utils/cron-lib.sh" \
  "${OPENCLAW_SKILLS_DIR:-$HOME/.openclaw/skills}/shared-utils/cron-lib.sh" \
  "/data/.openclaw/skills/shared-utils/cron-lib.sh"; do
  if [ -f "$_cand" ]; then
    _CRON_LIB="$_cand"
    break
  fi
done
if [ -n "$_CRON_LIB" ]; then
  # shellcheck source=/dev/null
  . "$_CRON_LIB"
else
  echo "WARN: shared-utils/cron-lib.sh not found — falling back to an inline exact-JSON-match (no text-table grep)." >&2
  oc_cron_present() {
    local name="$1" raw
    raw=$(openclaw cron list --json 2>/dev/null) || raw=""
    [ -n "$raw" ] && command -v jq >/dev/null 2>&1 || return 1
    printf '%s' "$raw" | jq -e --arg n "$name" '
      ( if type == "array" then . else .jobs // [] end ) | map(select(.name == $n)) | length > 0
    ' >/dev/null 2>&1
  }
fi

# Resolve the batch model the Model Wizard (15-configure-hooks-mappings.sh) saved to
# the secrets env file, falling back to env, then to a sane default. (Crons run on the
# batch tier; the tier choice lives in secrets.env — never in an invalid config key.)
SECRETS_ENV_FILE="${SECRETS_ENV_FILE:-$HOME/.openclaw/secrets.env}"
if [[ -z "${BATCH_MODEL:-}" && -f "$SECRETS_ENV_FILE" ]]; then
  BATCH_MODEL="$(grep -E '^BATCH_MODEL=' "$SECRETS_ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- || true)"
fi
BATCH_MODEL="${BATCH_MODEL:-openrouter/free}"

command -v openclaw >/dev/null 2>&1 || {
  echo "openclaw CLI not on PATH — cannot register crons. DO NOT write cron.jobs JSON (invalid on 2026.5.27)." >&2
  echo "Install/expose the openclaw CLI and re-run this script." >&2
  exit 2
}

# -----------------------------------------------------------------------------
# SILENCE DOCTRINE (FIX-XC-08b)
# -----------------------------------------------------------------------------
# On CLI 2026.6.8+ `openclaw cron add` FALLBACK-DELIVERS a job's final text to the
# LAST chat (the client's) on every fire — so an unsilenced maintenance cron spams
# the client's Telegram on its schedule. These crons are headless housekeeping
# (log summaries, digests, tune-ups, monthly review); they notify the OPERATOR
# from INSIDE their own prompt via notification-routing-protocol.md and must never
# surface in the client conversation. So every cron is registered with:
#   * --no-deliver        disable the runner's fallback delivery (no client spam)
#   * --session isolated  run in an isolated operator-side session for agent-message
#                         crons — never the client-facing main conversation
# Both flags are FEATURE-DETECTED against `cron add --help` (older CLIs lack them);
# when a flag is absent we register WITHOUT it (no-flag retry) rather than fail.
_cron_add_help="$(openclaw cron add --help 2>&1 || true)"
_cli_has_flag() { printf '%s' "$_cron_add_help" | grep -qE -- "(^|[[:space:]])$1([[:space:]<=]|\$)"; }

# Agent-message crons: silence delivery AND isolate the session off the client chat.
SILENCE_ARGS=()
_cli_has_flag '--no-deliver' && SILENCE_ARGS+=(--no-deliver)
_cli_has_flag '--session'    && SILENCE_ARGS+=(--session isolated)
# Command crons run a shell payload (not an agent session) — only silence delivery.
CMD_SILENCE_ARGS=()
_cli_has_flag '--no-deliver' && CMD_SILENCE_ARGS+=(--no-deliver)
if [ "${#SILENCE_ARGS[@]}" -eq 0 ]; then
  echo "WARN: this openclaw CLI exposes neither --no-deliver nor --session — registered crons may fallback-deliver their output to the last (client) chat. Upgrade the CLI to honor the silence doctrine." >&2
fi

# Register an AGENT-MESSAGE cron, silenced when the CLI supports it, with a
# no-flag retry if the CLI rejects the silence flags outright. Returns the add rc.
# NOTE: ${SILENCE_ARGS[@]+"${SILENCE_ARGS[@]}"} is the stock-bash-3.2 safe empty-
# array expansion (a bare "${arr[@]}" on an empty array aborts under `set -u`).
_add_agent_cron() {
  local name="$1" cron_expr="$2" message="$3"
  if openclaw cron add --name "$name" --cron "$cron_expr" \
       --agent "$ROUTING_AGENT_ID" --light-context \
       ${SILENCE_ARGS[@]+"${SILENCE_ARGS[@]}"} --message "$message" >&2; then
    return 0
  fi
  if [ "${#SILENCE_ARGS[@]}" -gt 0 ]; then
    echo "WARN: '$name' add with silence flags failed — retrying WITHOUT them (cron may fallback-deliver; verify manually)." >&2
    openclaw cron add --name "$name" --cron "$cron_expr" \
      --agent "$ROUTING_AGENT_ID" --light-context --message "$message" >&2
    return $?
  fi
  return 1
}

# Soft-assert (NEVER fatal) that a just-registered cron landed and is not set to
# fallback-deliver. Pure bash (no python/jq — stock-bash-3.2 safe). We already
# passed --no-deliver at add time; this cross-checks via `cron list`.
_assert_cron_silent() {
  local name="$1" js
  if ! oc_cron_present "$name"; then
    echo "WARN: cron '$name' not visible in 'openclaw cron list --json' after add — verify manually." >&2
    return 0
  fi
  js="$(openclaw cron list --json 2>/dev/null || true)"
  if printf '%s' "$js" | grep -qE '"(deliver|announce)"[[:space:]]*:[[:space:]]*true'; then
    echo "NOTE: cron '$name' registered; the cron store shows a job with delivery enabled — confirm '$name' itself carries no deliver/announce via 'openclaw cron list --json'." >&2
  else
    echo "verified: cron '$name' present and no job in the store shows fallback delivery (silence doctrine holds)." >&2
  fi
}

# Append a cron job via the gateway cron store. Idempotent by name.
# Args: <name> <cron-expr> <message>
register_cron() {
  local name="$1" cron_expr="$2" message="$3"
  if oc_cron_present "$name"; then
    echo "cron $name already registered — skipping" >&2
    return 0
  fi
  if _add_agent_cron "$name" "$cron_expr" "$message"; then
    echo "registered cron: $name ($cron_expr) [delivery silenced]" >&2
    _assert_cron_silent "$name"
  else
    echo "ERROR: 'openclaw cron add $name' failed — register it manually (cron.jobs JSON is invalid on 2026.5.27)" >&2
    return 1
  fi
}

# Register a COMMAND-style cron that runs a bash SCRIPT (not an agent message),
# in a CLI-portable way — mirrors ~/.openclaw/scripts/ensure-pipeline-crons.sh:
#   * 2026.6.x+ `openclaw cron add` supports `--command "<shell>"` (native).
#   * 2026.5.x has NO --command → fall back to an AGENT MESSAGE job that runs the
#     SAME script via the shell. Both register a cron under the same name, so the
#     `openclaw cron list | grep <name>` idempotency check passes either way.
# Idempotent by name. Args: <name> <cron-expr> <absolute-script-path>
_cli_supports_command() {
  local help
  help="$(openclaw cron add --help 2>&1 || true)"
  printf '%s' "$help" | grep -qE '^[[:space:]]*--command[[:space:]<]'
}
register_command_cron() {
  local name="$1" cron_expr="$2" script="$3"
  if oc_cron_present "$name"; then
    echo "cron $name already registered — skipping" >&2
    return 0
  fi
  if [ ! -f "$script" ]; then
    echo "ERROR: $name — script not found at $script; skipping registration" >&2
    return 1
  fi
  if _cli_supports_command; then
    # --no-deliver stops the RUNNER from dumping the script's stdout into a chat;
    # it does NOT stop the script's own deliberate `openclaw message send` (e.g.
    # ghl-pit-liveness notifying the client on a 401). No-flag retry if rejected.
    if openclaw cron add --name "$name" --cron "$cron_expr" \
         ${CMD_SILENCE_ARGS[@]+"${CMD_SILENCE_ARGS[@]}"} --command "bash $script" >&2 \
       || openclaw cron add --name "$name" --cron "$cron_expr" --command "bash $script" >&2; then
      echo "registered command-cron: $name ($cron_expr) -> bash $script [delivery silenced]" >&2
      _assert_cron_silent "$name"
    else
      echo "ERROR: 'openclaw cron add $name --command' failed — register it manually" >&2
      return 1
    fi
  else
    # 2026.5.x: no --command. Run the SAME script via a silent agent-message job.
    local msg="[SKILL38-CRON $name] Run this exact shell command now and report only on failure: bash $script"
    if _add_agent_cron "$name" "$cron_expr" "$msg"; then
      echo "registered agent-message cron (5.x fallback): $name ($cron_expr) -> bash $script [delivery silenced]" >&2
      _assert_cron_silent "$name"
    else
      echo "ERROR: 'openclaw cron add $name' (agent-message fallback) failed — register it manually" >&2
      return 1
    fi
  fi
}

# -----------------------------------------------------------------------------
# Cron 1 — conversation-log-summarizer  (nightly 11:30 PM)
# Summarizes the day's per-contact conversation logs into rolling summaries.
# Playbook Step 9 (Step 3.5G references this cron).
# -----------------------------------------------------------------------------
register_cron "conversation-log-summarizer" "30 23 * * *" \
  "Run the daily conversation log summarization on the batch model ($BATCH_MODEL). For each file under <MASTER_FILES_DIR>/conversational-logs/ touched today, append a rolling 5-bullet summary to the top of the file. Skip files unchanged since yesterday."

# -----------------------------------------------------------------------------
# Cron 2 — analytics-weekly-digest  (Mondays 8 AM)
# Per Step 9.17 analytics-dashboard-protocol.md.
# -----------------------------------------------------------------------------
register_cron "analytics-weekly-digest" "0 8 * * 1" \
  "Generate the weekly analytics digest per protocols/analytics-dashboard-protocol.md — volume by channel, top topics, sentiment distribution, escalation rate, safeguard activations. Notify the operator per notification-routing-protocol.md."

# -----------------------------------------------------------------------------
# Cron 3 — weekly-tune-up  (Sundays 2 AM)
# Per Step 9.x weekly-tune-up-protocol.md.
# -----------------------------------------------------------------------------
register_cron "weekly-tune-up" "0 2 * * 0" \
  "Run the weekly tune-up per protocols/weekly-tune-up-protocol.md — review last 7 days of bug log, classification corrections, deferred items; surface acceptance/ignore patterns; propose minor improvements for operator approval."

# -----------------------------------------------------------------------------
# Cron 4 — proactive-suggestions-scan  (Saturdays 11 PM)
# Per Step 9.34 Proactive Features Suite. v5.14 also bundles Step 9.36
# Model Version Freshness Checker into this cron.
# -----------------------------------------------------------------------------
register_cron "proactive-suggestions-scan" "0 23 * * 6" \
  "Run the weekly proactive-suggestions-scan per protocols/proactive-features-suite-protocol.md — workflows, Knowledge Sources, tags, discount codes, workflow improvements, escalation patterns, sales opportunities. Also run the bundled Model Version Freshness Checker (Step 9.36) — Ollama Cloud catalog, Ollama local manifests, OpenRouter catalog, direct provider APIs, embedding-model freshness. Operator approves YES/DEFER/IGNORE/MODIFY. 30-day cool-down."

# -----------------------------------------------------------------------------
# Cron 5 — system-health-heartbeat  (1st of each month, 9 AM)  [NEW in v5.14]
# Per protocols/monthly-comprehensive-review-protocol.md — Step 9.35.
# Deep 30-day audit: playbooks, GHL workflows, knowledge bases, model
# configs, accumulated tune-ups, bug log.
# -----------------------------------------------------------------------------
register_cron "system-health-heartbeat" "0 9 1 * *" \
  "Run the Monthly Comprehensive Review per protocols/monthly-comprehensive-review-protocol.md — 30-day audit across (1) all Conversation Playbooks (performance, outdated refs, scope overlap, retirement candidates), (2) all GHL workflows (firing volume, webhook health, split candidates) — for EVERY workflow built via caf (Skill 44), run 44-convert-and-flow-operator/qc-built-workflow.sh <workflow-id> --json and fold its PASS/FAIL result into this section of the audit (do not rely on agent prose alone for the structural half), (3) Typed Knowledge Bases (last updated, hit rate, stale sources, Dreaming consolidation pace), (4) model configurations (latency trends, fallback hit rates, cost), (5) accumulated weekly tune-ups (acceptance follow-through, deferred items ready, ignored-but-recurring patterns), (6) bug log (recurring failures, new error types). Save report to <MASTER_FILES_DIR>/tune-ups/comprehensive-review.md. Notify operator per notification-routing-protocol.md. Operator approves YES/DEFER/IGNORE per item."

# -----------------------------------------------------------------------------
# Cron 6 — ghl-pit-liveness  (daily 8:15 AM)  [runtime credential fallback]
# The RUNTIME-PIT twin of Skill 44's `ghl-token-liveness` (which watches the
# Firebase BUILD token). Runs scripts/check-ghl-pit-liveness.sh: probes the
# location PIT via the skill's own in-scope READ; on a clean 401 it notifies the
# CLIENT's own Telegram (never operator IDs) with plain-English refresh steps,
# idempotent once-per-day. Distinct name from Skill 44's cron — no collision.
# -----------------------------------------------------------------------------
register_command_cron "ghl-pit-liveness" "15 8 * * *" \
  "$SCRIPT_DIR/check-ghl-pit-liveness.sh" || \
  echo "WARN: ghl-pit-liveness cron not registered — register it manually (bash $SCRIPT_DIR/check-ghl-pit-liveness.sh, daily)." >&2

echo "OK: crons registered via 'openclaw cron add' [delivery silenced — --no-deliver + isolated session] — 5 agent-message crons (conversation-log-summarizer, analytics-weekly-digest, weekly-tune-up, proactive-suggestions-scan, system-health-heartbeat) + 1 command-cron (ghl-pit-liveness runtime credential watcher). Maintenance output never reaches the client chat; operator notifications go through notification-routing-protocol.md." >&2
