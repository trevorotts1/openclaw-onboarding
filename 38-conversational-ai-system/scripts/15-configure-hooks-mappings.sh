#!/usr/bin/env bash
# 15-configure-hooks-mappings.sh
# Step 3 (hooks.mappings) + Step 3.5 (Model Selection Wizard) + Step 4 (E2E test).
# Playbook v5.14 lines 1089-1395. Idempotent.
set -euo pipefail

SECRETS_ENV_FILE="${SECRETS_ENV_FILE:-$HOME/.openclaw/secrets.env}"
CONFIG_FILE="${CONFIG_FILE:-$HOME/.openclaw/openclaw.json}"
GATEWAY_PORT="${GATEWAY_PORT:-18789}"

[[ -f "$SECRETS_ENV_FILE" ]] && set -a && . "$SECRETS_ENV_FILE" && set +a || true
[[ -f "$CONFIG_FILE" ]] || { echo "openclaw config not found: $CONFIG_FILE" >&2; exit 2; }

: "${ROUTE_ID:?ROUTE_ID missing — set in env or in secrets.env}"
: "${PUBLIC_HOSTNAME:?PUBLIC_HOSTNAME missing — run 13-create-cloudflare-tunnel.sh first}"
# CORRECTED GHL HOOK STRUCTURE (2026-05-29): the GHL body sends a FLAT `session_key`
# (e.g. "hook:ghl:sms:<contact-id>"); the mapping just references it as {{session_key}}.
# Do NOT template channel/contact.id into the sessionKey here — those are nested merge
# tokens that the flat body already resolved before sending.
SESSION_KEY="${SESSION_KEY:-{{session_key}}}"

command -v jq >/dev/null 2>&1 || { echo "jq required" >&2; exit 3; }

append_secret() {
  local k="$1" v="$2"
  [[ -f "$SECRETS_ENV_FILE" ]] || { mkdir -p "$(dirname "$SECRETS_ENV_FILE")"; : > "$SECRETS_ENV_FILE"; chmod 600 "$SECRETS_ENV_FILE"; }
  if grep -qE "^${k}=" "$SECRETS_ENV_FILE" 2>/dev/null; then return 0; fi
  printf '%s=%s\n' "$k" "$v" >> "$SECRETS_ENV_FILE"
}

backup_config() {
  local ts
  ts="$(date +%Y%m%d-%H%M%S)"
  cp "$CONFIG_FILE" "${CONFIG_FILE}.bak.${ts}"
  echo "config backup: ${CONFIG_FILE}.bak.${ts}" >&2
}

write_config() {
  local new="$1"
  echo "$new" | jq '.' > "${CONFIG_FILE}.tmp"
  mv "${CONFIG_FILE}.tmp" "$CONFIG_FILE"
}

# =============================================================================
# STEP 3 — hooks.mappings (idempotent)
# =============================================================================
echo "==> Step 3: hooks.mappings for route_id=$ROUTE_ID" >&2

# Generate / reuse HOOKS_TOKEN
if [[ -z "${HOOKS_TOKEN:-}" ]]; then
  HOOKS_TOKEN="$(openssl rand -base64 32 | tr -d '\n=' | head -c 43)"
  append_secret "HOOKS_TOKEN" "$HOOKS_TOKEN"
  echo "generated HOOKS_TOKEN (length=${#HOOKS_TOKEN})" >&2
else
  echo "reusing existing HOOKS_TOKEN" >&2
fi

# Refuse to reuse gateway token
GATEWAY_TOKEN="$(jq -r '.gateway.auth.token // empty' "$CONFIG_FILE" 2>/dev/null || true)"
if [[ -n "$GATEWAY_TOKEN" && "$GATEWAY_TOKEN" == "$HOOKS_TOKEN" ]]; then
  echo "HOOKS_TOKEN equals gateway.auth.token — refused (per OpenClaw config-reference)." >&2
  exit 4
fi

# Is a mapping with this id already in place?
HAS_MAPPING="$(jq --arg id "$ROUTE_ID" '.hooks.mappings? // [] | map(.id == $id) | any' "$CONFIG_FILE")"

if [[ "$HAS_MAPPING" == "true" ]]; then
  echo "hooks.mappings entry id=$ROUTE_ID already present — skipping merge" >&2
else
  backup_config
  ROUTING_AGENT_ID="${ROUTING_AGENT_ID:-main}"
  # CORRECTED GHL HOOK STRUCTURE (2026-05-29) — verified live on a live client (OpenClaw 2026.5.27):
  #  - messageTemplate references the FLAT body key names ({{contact_id}}, {{message_body}}, {{channel}}, etc.)
  #    that the FLAT GHL body sends — NOT nested {{contact.id}}/{{customer_message.body}} (those arrive empty).
  #  - messageTemplate MUST include the MANDATORY SEND-DIRECTIVE (the canonical clause below) or the agent
  #    drafts but never sends (zero GHL API calls => customer gets nothing). Drafting is NOT sending. This is
  #    LAYER 1 of the 3-layer send enforcement (Layer 2 = AGENTS.md standing rule; Layer 3 = qc-send-directive.sh).
  #  - messageTemplate MUST ALSO include the CONVERSATION-MEMORY read-before/append-after steps. GHL inbound hook
  #    sessions are SINGLE-TURN / stateless — every hook run is a fresh session, so the agent's ONLY memory of a
  #    contact across messages is the per-contact conversation log (conversational-logs/<contact_id>__<name>.md).
  #    The template orders the agent to READ that log BEFORE replying (continue any in-progress booking/topic) and
  #    APPEND inbound+reply AFTER sending. Without it the agent has zero memory mid-conversation — the exact
  #    regression that left a live client mid-booking with "no memory." Enforced like the send-directive: fail-closed
  #    guard below + qc-conversation-memory.sh (Layer 3, CI + pre-handoff QC).
  #  - deliver MUST be false (deliver:true makes OpenClaw ALSO push to a channel, conflicting with the agent's
  #    own GHL-API reply).
  #  - NO `fallbacks` key (schema is .strict() and rejects it; fallbacks belong on a model-routing config only).
  #  NOTE: the SEND-DIRECTIVE lives ONLY on this SERVER mapping's messageTemplate (object-B, where {{…}}
  #  placeholders resolve). It must NEVER appear in the in-GHL-body messageTemplate — that one stays
  #  placeholder-free per the 23-key rule (qc-23-key-bodies.sh).
  NEW_MAPPING="$(jq -n \
    --arg id "$ROUTE_ID" \
    --arg path "$ROUTE_ID" \
    --arg agent "$ROUTING_AGENT_ID" \
    --arg sk "$SESSION_KEY" \
    '{
      id:$id, match:{path:$path}, action:"agent", agentId:$agent,
      wakeMode:"now", name:"GHL Inbound", sessionKey:$sk,
      messageTemplate:"INBOUND MESSAGE FROM GOHIGHLEVEL — {{channel}} channel From: {{first_name}} {{last_name}} Phone: {{phone}} Email: {{email}} Contact ID: {{contact_id}} Location ID: {{location_id}} Location name: {{location_name}} Customer message subject: {{subject}} Customer message body: {{message_body}} CONVERSATION MEMORY — THIS HOOK SESSION IS SINGLE-TURN AND STATELESS, your only memory of this contact is the log file. FIRST, before drafting anything, READ this contact'\''s conversation log at <MASTER_FILES_DIR>/conversational-logs/{{contact_id}}__<name>.md for the full prior conversation and any in-progress booking/context (see AGENTS.md Conversation Memory Protocol); if the file is missing, treat this as a new contact. CONTINUE any in-progress topic/booking from the log instead of restarting. To pull deeper prior thread history when the log is thin, READ it from GHL: GET conversations/search?locationId={{location_id}}&contactId={{contact_id}} to find the conversationId, then GET conversations/{conversationId}/messages — conversationId is a READ key only, never a send field. Also check the matching playbook in conversation-workflows. MANDATORY — SEND on the SAME channel the message arrived on, do not just draft: read the inbound channel ({{channel}}) and SEND your reply via the GHL Conversations API (POST conversations/messages) with type = the MIRRORED channel value (SMS->SMS, Email->Email, Facebook->FB, Instagram->IG, WhatsApp->WhatsApp, Live Chat->Live_Chat); do NOT hardcode SMS. Send body = {type:<mirrored>, contactId:{{contact_id}}, locationId:{{location_id}}, message:<your reply>} (for Email also subject+html+emailFrom+emailTo). GHL threads the reply into this contact'\''s conversation BY contactId — do NOT put conversationId in the send body. Per TOOLS.md. Composing or drafting a reply is NOT sending — the customer receives nothing unless you make the API call. Do NOT end your turn until the send call returns a messageId/conversationId. AFTER the send returns a messageId, APPEND both this inbound message and your reply to <MASTER_FILES_DIR>/conversational-logs/{{contact_id}}__<name>.md (create the file if it is missing) — a reply that does not update the log loses this contact'\''s memory and is a failure.",
      deliver:false, timeoutSeconds:300
    }')"

  # FAIL-CLOSED GUARD: the messageTemplate we just built MUST carry the mandatory send-directive elements.
  # It must NOT be possible to install a GHL hook whose messageTemplate lacks the send-directive (Layer 1).
  #  - messageTemplate MUST be CHANNEL-MIRRORING (reply on the SAME channel the message arrived on — the
  #    mirrored `type` values, NOT a hardcoded SMS reply), MUST thread the send BY contactId (NOT
  #    conversationId on the send), and MUST reference the GET conversations/search READ path for prior
  #    history. Enforced both here (guard) and by qc-send-directive.sh (Layer 3).
  GUARD_MT="$(printf '%s' "$NEW_MAPPING" | jq -r '.messageTemplate')"
  for needle in "MANDATORY" "SEND" "GHL Conversations API" "drafting" "NOT sending" "messageId" "SAME channel" "do NOT hardcode SMS" "conversations/search"; do
    if ! printf '%s' "$GUARD_MT" | grep -qi -- "$needle"; then
      echo "REFUSED: installer messageTemplate is missing send-directive element '$needle' — refusing to write a hook that lets the agent draft-but-not-send (or hardcode SMS / drop the read path)." >&2
      exit 8
    fi
  done
  # FAIL-CLOSED GUARD (conversation memory): GHL inbound hook sessions are single-turn/stateless — the agent's
  # only memory across messages is the per-contact conversation log. The messageTemplate MUST tell the agent to
  # READ the log BEFORE replying AND APPEND to it AFTER replying. It must NOT be possible to install a GHL hook
  # whose messageTemplate lacks the conversation-log read-before OR append-after step (otherwise the agent has
  # zero memory mid-conversation — this is the exact regression that broke a live client). The read+append
  # directive lives ONLY on this SERVER mapping (the in-GHL-body messageTemplate stays placeholder-free per the
  # 23-key rule).
  for needle in "conversational-logs" "read" "append"; do
    if ! printf '%s' "$GUARD_MT" | grep -qi -- "$needle"; then
      echo "REFUSED: installer messageTemplate is missing conversation-log element '$needle' — refusing to write a hook whose agent cannot read-before/append-after and would lose this contact's memory." >&2
      exit 9
    fi
  done
  # NOTE (2026-05-29): jq 1.7+ REJECTS the `.hooks //= {};` update-assignment as
  # a TOP-LEVEL statement (the trailing `;` is parsed as a program separator and
  # jq errors "syntax error, unexpected ';'"). Use the valid `.hooks = (.hooks // {})`
  # form piped into the rest of the program — same semantics (ensure .hooks is an
  # object before mutating it), valid on jq 1.6 AND jq 1.7+.
  UPDATED="$(jq \
    --arg tok "$HOOKS_TOKEN" \
    --arg agent "$ROUTING_AGENT_ID" \
    --argjson mapping "$NEW_MAPPING" \
    '.hooks = (.hooks // {}) |
     .hooks.enabled = true |
     .hooks.token = $tok |
     .hooks.path = (.hooks.path // "/hooks") |
     .hooks.maxBodyBytes = (.hooks.maxBodyBytes // 262144) |
     .hooks.defaultSessionKey = (.hooks.defaultSessionKey // "hook:ghl:default") |
     .hooks.allowRequestSessionKey = true |
     .hooks.allowedSessionKeyPrefixes = ((.hooks.allowedSessionKeyPrefixes // []) + ["hook:ghl:"] | unique) |
     .hooks.allowedAgentIds = ((.hooks.allowedAgentIds // []) + [$agent, "main"] | unique) |
     .hooks.mappings = ((.hooks.mappings // []) + [$mapping])' "$CONFIG_FILE")"
  write_config "$UPDATED"
  echo "hooks.mappings entry id=$ROUTE_ID merged into config" >&2
fi

# Validate (best-effort — non-fatal if CLI absent)
if command -v openclaw >/dev/null 2>&1; then
  openclaw config validate || { echo "openclaw config validate FAILED — restore from .bak.*" >&2; exit 5; }
fi

# =============================================================================
# STEP 3.5 — Model Selection Wizard
# =============================================================================
echo "==> Step 3.5: Model Selection Wizard" >&2

# Skip if all three tiers already set.
# SCHEMA NOTE (2026-05-29): `agents.defaults.async.model` and `agents.defaults.batch.model`
# are NOT valid keys in the 2026.5.27 config schema (.strict() — writing them makes
# `openclaw config validate` FAIL). The real-time model is the only one that lives in
# openclaw.json (on the agent's `agents.list[].model`). The async + batch tier CHOICES are
# persisted to SECRETS_ENV_FILE as ASYNC_MODEL / BATCH_MODEL so downstream consumers
# (e.g. 04-register-crons.sh, which reads $BATCH_MODEL) honor the operator's selection
# WITHOUT writing an invalid config key.
RT_SET="$(jq -r '(.agents.list // []) | map(select(.id=="main")) | .[0].model // empty' "$CONFIG_FILE")"
ASYNC_SET="$( { grep -E '^ASYNC_MODEL=' "$SECRETS_ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- ; } || true)"
ASYNC_SET="${ASYNC_SET:-${ASYNC_MODEL:-}}"
BATCH_SET="$( { grep -E '^BATCH_MODEL=' "$SECRETS_ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- ; } || true)"
BATCH_SET="${BATCH_SET:-${BATCH_MODEL:-}}"

if [[ -n "$RT_SET" && -n "$ASYNC_SET" && -n "$BATCH_SET" ]]; then
  echo "all three tiers already configured — skipping wizard (rt=$RT_SET async=$ASYNC_SET batch=$BATCH_SET)" >&2
else
  pick_model() {
    local tier="$1"; shift
    local prompt="$1"; shift
    local default="$1"; shift
    local -a opts=("$@")
    {
      echo ""
      echo "── $tier tier ──"
      echo "$prompt"
      local i=1
      for opt in "${opts[@]}"; do echo "  $i) $opt"; ((i++)); done
      echo "  (Enter = $default)"
      printf "Choice: "
    } >&2
    local choice
    read -r choice </dev/tty || choice=""
    if [[ -z "$choice" ]]; then echo "$default"; return; fi
    if [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= ${#opts[@]} )); then
      # Strip trailing " — comment" if present
      echo "${opts[choice-1]%% — *}"
    else
      echo "$choice"
    fi
  }

  RT_OPTS=(
    "deepseek/deepseek-v4-pro:thinking-max — highest-reasoning real-time"
    "google/gemini-3.1-flashlight — fast + near-free (RECOMMENDED for high volume)"
    "kimi/kimi-2.6 — strong long-context reasoning"
    "openai/gpt-5.5 — balanced"
    "openrouter/free — cheapest, slower"
  )
  ASYNC_OPTS=(
    "deepseek/deepseek-v4-pro:thinking-max — highest-reasoning"
    "google/gemini-3.1-flashlight — balanced"
    "openrouter/free — free + perfect for email"
    "anthropic/claude-opus-4-7 — premium quality"
    "same-as-realtime"
  )
  BATCH_OPTS=(
    "openrouter/free — free, batch-only (RECOMMENDED)"
    "deepseek/deepseek-v4-flash — small cost, better quality"
    "google/gemini-3.1-flashlight — balanced"
    "same-as-realtime"
  )

  if [[ -z "$RT_SET" ]]; then
    RT_SET="$(pick_model "REAL-TIME" "SMS / Messenger / IG / Live Chat — speed matters" \
      "google/gemini-3.1-flashlight" "${RT_OPTS[@]}")"
  fi
  if [[ -z "$ASYNC_SET" ]]; then
    ASYNC_SET="$(pick_model "ASYNC" "Email / LinkedIn — minutes are fine" \
      "openrouter/free" "${ASYNC_OPTS[@]}")"
    [[ "$ASYNC_SET" == "same-as-realtime" ]] && ASYNC_SET="$RT_SET"
  fi
  if [[ -z "$BATCH_SET" ]]; then
    BATCH_SET="$(pick_model "BATCH" "Nightly summarization — no real-time pressure" \
      "openrouter/free" "${BATCH_OPTS[@]}")"
    [[ "$BATCH_SET" == "same-as-realtime" ]] && BATCH_SET="$RT_SET"
  fi

  # Verify provider key
  needs_key() {
    case "$1" in
      openrouter/*|google/*|deepseek/*|kimi/*|openai/gpt-*|qwen/*) echo "OPENROUTER_API_KEY" ;;
      anthropic/*) echo "ANTHROPIC_API_KEY" ;;
      ollama-cloud/*) echo "OLLAMA_API_KEY" ;;
      *) echo "" ;;
    esac
  }
  for m in "$RT_SET" "$ASYNC_SET" "$BATCH_SET"; do
    k="$(needs_key "$m")"
    [[ -z "$k" ]] && continue
    if ! grep -qE "^${k}=" "$SECRETS_ENV_FILE" 2>/dev/null && [[ -z "${!k:-}" ]]; then
      echo "STOP: model $m needs $k — add it to $SECRETS_ENV_FILE and re-run." >&2
      exit 6
    fi
  done

  backup_config
  # SCHEMA-SAFE WRITE (2026-05-29): only the real-time model goes into openclaw.json
  # (on the main agent's `agents.list[].model`). We DO NOT write
  # `agents.defaults.async`/`agents.defaults.batch` — those keys are rejected by the
  # 2026.5.27 .strict() schema and would make `openclaw config validate` FAIL. The
  # async/batch tier choices are persisted to SECRETS_ENV_FILE instead (read by crons).
  # `.agents = (.agents // {})` / `.agents.list = (.agents.list // [])` replace the
  # jq-1.7-invalid `//=` top-level form (see the hooks-merge note above).
  UPDATED="$(jq \
    --arg rt "$RT_SET" \
    '.agents = (.agents // {}) |
     .agents.list = (.agents.list // []) |
     (if (.agents.list | map(.id == "main") | any) then
        .agents.list |= map(if .id == "main" then .model = $rt else . end)
      else
        .agents.list += [{id:"main", model:$rt}]
      end)' "$CONFIG_FILE")"
  write_config "$UPDATED"
  # Persist the async + batch tier choices to the secrets env file (NOT to the
  # config) so 04-register-crons.sh and other consumers honor them.
  append_secret "ASYNC_MODEL" "$ASYNC_SET"
  append_secret "BATCH_MODEL" "$BATCH_SET"
  echo "models saved: realtime=$RT_SET (config)  async=$ASYNC_SET batch=$BATCH_SET (secrets.env, not config — invalid schema keys)" >&2
fi

# System Health Heartbeat cron (idempotent).
# CRON REGISTRATION (2026-05-29): the legacy `cron.jobs` JSON config block does NOT
# validate on 2026.5.27 (writing it makes `openclaw config validate` FAIL). Register
# crons through the gateway cron store via `openclaw cron add` (see
# references/GHL-INBOUND-AND-PLAYBOOKS.md §13). Idempotency is by name via
# `openclaw cron list`. If the CLI is absent, we skip (non-fatal) rather than write an
# invalid config block.
if command -v openclaw >/dev/null 2>&1; then
  if openclaw cron list 2>/dev/null | grep -q "system-health-heartbeat"; then
    echo "cron system-health-heartbeat already registered — skipping" >&2
  else
    if openclaw cron add \
        --name system-health-heartbeat \
        --cron "0 9 1 * *" \
        --agent main \
        --light-context \
        --best-effort-deliver \
        --message "Run the Monthly Comprehensive Review per protocols/monthly-comprehensive-review-protocol.md — 30-day audit across playbooks, GHL workflows, knowledge bases, model configs, tune-ups, bug log." >&2; then
      echo "registered cron: system-health-heartbeat (0 9 1 * *) via openclaw cron add" >&2
    else
      echo "WARN: 'openclaw cron add system-health-heartbeat' failed — register it manually (cron.jobs JSON is invalid on 2026.5.27)" >&2
    fi
  fi
else
  echo "WARN: openclaw CLI not on PATH — cannot register system-health-heartbeat cron (do NOT write cron.jobs JSON; it is invalid on 2026.5.27)" >&2
fi

# =============================================================================
# STEP 4 — End-to-end test through the public tunnel
# =============================================================================
echo "==> Step 4: end-to-end test" >&2
# CORRECTED GHL HOOK STRUCTURE (2026-05-29): FLAT body, no nested objects, ALL 23 keys (owner directive —
# 23 is the minimum, no stripped bodies). session_key is flat and starts with the allowed "hook:ghl:" prefix;
# the mapping reads contact_id/message_body/etc. directly. The body's messageTemplate is placeholder-free so
# GHL never mangles it. 23 keys: id, match, action, agent_id, model, wakeMode, name, session_key,
# messageTemplate, deliver, timeoutSeconds, channel, to, thinking, contact_id, first_name, last_name, email,
# phone, subject, message_body, location_id, location_name.
ROUTING_AGENT_ID="${ROUTING_AGENT_ID:-main}"  # may be unset if the mapping already existed (set -u guard)
PAYLOAD='{"id":"'"$ROUTE_ID"'","match":"'"$ROUTE_ID"'","action":"agent","agent_id":"'"$ROUTING_AGENT_ID"'","model":"ollama/deepseek-v4-flash:cloud","wakeMode":"now","name":"GHL Sales Inbound","session_key":"hook:ghl:sms:e2e-test-001","messageTemplate":"Respond as the Sales agent and reply to this contact via the GHL Conversations API per TOOLS.md","deliver":false,"timeoutSeconds":300,"channel":"sms","to":"+15555550100","thinking":"medium","contact_id":"e2e-test-001","first_name":"E2E","last_name":"Test","email":"e2e@example.com","phone":"+15555550100","subject":"","message_body":"End-to-end setup verification.","location_id":"e2e-loc-001","location_name":"E2E Test Location"}'

HTTP_CODE="$(curl -sS -o /tmp/.hooks-e2e-body.$$ -w '%{http_code}' \
  --max-time 30 \
  -X POST "https://${PUBLIC_HOSTNAME}/hooks/${ROUTE_ID}" \
  -H "Authorization: Bearer ${HOOKS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" || echo "000")"
BODY="$(cat /tmp/.hooks-e2e-body.$$ 2>/dev/null || true)"
rm -f /tmp/.hooks-e2e-body.$$

case "$HTTP_CODE" in
  2*) echo "E2E PASS — HTTP $HTTP_CODE" >&2; echo "$BODY" | head -c 400 >&2; echo >&2 ;;
  *)  echo "E2E FAIL — HTTP $HTTP_CODE" >&2; echo "$BODY" | head -c 400 >&2; echo >&2; exit 7 ;;
esac

echo "OK: hooks + models + cron configured; E2E pass." >&2
