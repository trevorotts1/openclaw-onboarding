#!/usr/bin/env bash
# 04-register-crons.sh
# Registers the recurring OpenClaw cron jobs for the Conversational AI System.
# Idempotent: each job is gated by name via `openclaw cron list`.
# Playbook v5.14 — Step 9 + Step 3.5H.
#
# CRON REGISTRATION (2026-05-29): the legacy `cron.jobs` JSON config block does NOT
# validate on openclaw 2026.5.27 — writing it makes `openclaw config validate` FAIL and
# the gateway never runs the jobs. Crons MUST be registered through the gateway cron
# store via the `openclaw cron add` CLI (see references/GHL-INBOUND-AND-PLAYBOOKS.md §13).
# This script no longer touches openclaw.json at all.
set -euo pipefail

ROUTING_AGENT_ID="${ROUTING_AGENT_ID:-main}"

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

# Append a cron job via the gateway cron store. Idempotent by name.
# Args: <name> <cron-expr> <message>
register_cron() {
  local name="$1" cron_expr="$2" message="$3"
  if openclaw cron list 2>/dev/null | grep -q "$name"; then
    echo "cron $name already registered — skipping" >&2
    return 0
  fi
  if openclaw cron add \
      --name "$name" \
      --cron "$cron_expr" \
      --agent "$ROUTING_AGENT_ID" \
      --light-context \
      --best-effort-deliver \
      --message "$message" >&2; then
    echo "registered cron: $name ($cron_expr)" >&2
  else
    echo "ERROR: 'openclaw cron add $name' failed — register it manually (cron.jobs JSON is invalid on 2026.5.27)" >&2
    return 1
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
  "Run the Monthly Comprehensive Review per protocols/monthly-comprehensive-review-protocol.md — 30-day audit across (1) all Conversation Playbooks (performance, outdated refs, scope overlap, retirement candidates), (2) all GHL workflows (firing volume, webhook health, split candidates), (3) Typed Knowledge Bases (last updated, hit rate, stale sources, Dreaming consolidation pace), (4) model configurations (latency trends, fallback hit rates, cost), (5) accumulated weekly tune-ups (acceptance follow-through, deferred items ready, ignored-but-recurring patterns), (6) bug log (recurring failures, new error types). Save report to <MASTER_FILES_DIR>/tune-ups/comprehensive-review.md. Notify operator per notification-routing-protocol.md. Operator approves YES/DEFER/IGNORE per item."

echo "OK: 5 crons registered via 'openclaw cron add' (conversation-log-summarizer, analytics-weekly-digest, weekly-tune-up, proactive-suggestions-scan, system-health-heartbeat)." >&2
