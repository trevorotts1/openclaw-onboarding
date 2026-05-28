#!/usr/bin/env bash
# 04-register-crons.sh
# Registers the recurring OpenClaw cron jobs for the Conversational AI System.
# Idempotent: each job is gated by a config-presence marker check.
# Playbook v5.14 — Step 9 + Step 3.5H.
set -euo pipefail

CONFIG_FILE="${CONFIG_FILE:-$HOME/.openclaw/openclaw.json}"
ROUTING_AGENT_ID="${ROUTING_AGENT_ID:-main}"
BATCH_MODEL="${BATCH_MODEL:-openrouter/free}"

[[ -f "$CONFIG_FILE" ]] || { echo "openclaw config not found: $CONFIG_FILE" >&2; exit 2; }
command -v jq >/dev/null 2>&1 || { echo "jq required" >&2; exit 3; }

backup_config() {
  local ts; ts="$(date +%Y%m%d-%H%M%S)"
  cp "$CONFIG_FILE" "${CONFIG_FILE}.bak.${ts}"
  echo "config backup: ${CONFIG_FILE}.bak.${ts}" >&2
}

write_config() {
  echo "$1" | jq '.' > "${CONFIG_FILE}.tmp"
  mv "${CONFIG_FILE}.tmp" "$CONFIG_FILE"
}

# Idempotency marker: does a cron job with this id exist?
has_cron() {
  local id="$1"
  jq --arg id "$id" '(.cron.jobs // []) | map(.id == $id) | any' "$CONFIG_FILE" | grep -q true
}

# Append a cron job (object passed as one-line JSON string)
register_cron() {
  local id="$1" job_json="$2"
  if has_cron "$id"; then
    echo "cron $id already registered — skipping" >&2
    return 0
  fi
  backup_config
  local updated
  updated="$(jq --argjson job "$job_json" \
    '.cron //= {jobs: []} |
     .cron.jobs //= [] |
     .cron.jobs += [$job]' "$CONFIG_FILE")"
  write_config "$updated"
  echo "registered cron: $id" >&2
}

# -----------------------------------------------------------------------------
# Cron 1 — conversation-log-summarizer  (nightly 11:30 PM)
# Summarizes the day's per-contact conversation logs into rolling summaries.
# Playbook Step 9 (Step 3.5G references this cron).
# -----------------------------------------------------------------------------
register_cron "conversation-log-summarizer" "$(jq -n \
  --arg agent "$ROUTING_AGENT_ID" \
  --arg model "$BATCH_MODEL" \
  '{
    id:"conversation-log-summarizer",
    schedule:"30 23 * * *",
    agentId:$agent,
    model:$model,
    message:"Run the daily conversation log summarization. For each file under <MASTER_FILES_DIR>/conversational-logs/ touched today, append a rolling 5-bullet summary to the top of the file. Skip files unchanged since yesterday."
  }')"

# -----------------------------------------------------------------------------
# Cron 2 — analytics-weekly-digest  (Mondays 8 AM)
# Per Step 9.17 analytics-dashboard-protocol.md.
# -----------------------------------------------------------------------------
register_cron "analytics-weekly-digest" "$(jq -n \
  --arg agent "$ROUTING_AGENT_ID" \
  --arg model "$BATCH_MODEL" \
  '{
    id:"analytics-weekly-digest",
    schedule:"0 8 * * 1",
    agentId:$agent,
    model:$model,
    message:"Generate the weekly analytics digest per protocols/analytics-dashboard-protocol.md — volume by channel, top topics, sentiment distribution, escalation rate, safeguard activations. Notify the operator per notification-routing-protocol.md."
  }')"

# -----------------------------------------------------------------------------
# Cron 3 — weekly-tune-up  (Sundays 2 AM)
# Per Step 9.x weekly-tune-up-protocol.md.
# -----------------------------------------------------------------------------
register_cron "weekly-tune-up" "$(jq -n \
  --arg agent "$ROUTING_AGENT_ID" \
  --arg model "$BATCH_MODEL" \
  '{
    id:"weekly-tune-up",
    schedule:"0 2 * * 0",
    agentId:$agent,
    model:$model,
    message:"Run the weekly tune-up per protocols/weekly-tune-up-protocol.md — review last 7 days of bug log, classification corrections, deferred items; surface acceptance/ignore patterns; propose minor improvements for operator approval."
  }')"

# -----------------------------------------------------------------------------
# Cron 4 — proactive-suggestions-scan  (Saturdays 11 PM)
# Per Step 9.34 Proactive Features Suite. v5.14 also bundles Step 9.36
# Model Version Freshness Checker into this cron.
# -----------------------------------------------------------------------------
register_cron "proactive-suggestions-scan" "$(jq -n \
  --arg agent "$ROUTING_AGENT_ID" \
  --arg model "$BATCH_MODEL" \
  '{
    id:"proactive-suggestions-scan",
    schedule:"0 23 * * 6",
    agentId:$agent,
    model:$model,
    message:"Run the weekly proactive-suggestions-scan per protocols/proactive-features-suite-protocol.md — workflows, Knowledge Sources, tags, discount codes, workflow improvements, escalation patterns, sales opportunities. Also run the bundled Model Version Freshness Checker (Step 9.36) — Ollama Cloud catalog, Ollama local manifests, OpenRouter catalog, direct provider APIs, embedding-model freshness. Operator approves YES/DEFER/IGNORE/MODIFY. 30-day cool-down."
  }')"

# -----------------------------------------------------------------------------
# Cron 5 — system-health-heartbeat  (1st of each month, 9 AM)  [NEW in v5.14]
# Per protocols/monthly-comprehensive-review-protocol.md — Step 9.35.
# Deep 30-day audit: playbooks, GHL workflows, knowledge bases, model
# configs, accumulated tune-ups, bug log.
# -----------------------------------------------------------------------------
register_cron "system-health-heartbeat" "$(jq -n \
  --arg agent "$ROUTING_AGENT_ID" \
  --arg model "$BATCH_MODEL" \
  '{
    id:"system-health-heartbeat",
    schedule:"0 9 1 * *",
    agentId:$agent,
    model:$model,
    message:"Run the Monthly Comprehensive Review per protocols/monthly-comprehensive-review-protocol.md — 30-day audit across (1) all Conversation Playbooks (performance, outdated refs, scope overlap, retirement candidates), (2) all GHL workflows (firing volume, webhook health, split candidates), (3) Typed Knowledge Bases (last updated, hit rate, stale sources, Dreaming consolidation pace), (4) model configurations (latency trends, fallback hit rates, cost), (5) accumulated weekly tune-ups (acceptance follow-through, deferred items ready, ignored-but-recurring patterns), (6) bug log (recurring failures, new error types). Save report to <MASTER_FILES_DIR>/tune-ups/$(date +%Y-%m)-comprehensive.md. Notify operator per notification-routing-protocol.md. Operator approves YES/DEFER/IGNORE per item."
  }')"

# -----------------------------------------------------------------------------
# Validate (best-effort)
# -----------------------------------------------------------------------------
if command -v openclaw >/dev/null 2>&1; then
  openclaw config validate || { echo "openclaw config validate FAILED — restore from .bak.*" >&2; exit 5; }
fi

echo "OK: 5 crons registered (conversation-log-summarizer, analytics-weekly-digest, weekly-tune-up, proactive-suggestions-scan, system-health-heartbeat)." >&2
