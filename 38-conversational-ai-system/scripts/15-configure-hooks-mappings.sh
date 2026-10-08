#!/usr/bin/env bash
# 15-configure-hooks-mappings.sh
# Step 3 (hooks.mappings) + 3.1 (trusted proxy) + Step 3.5 (Model Selection Wizard) + Step 4 (reachability probe, no agent run).
# Playbook v5.14 lines 1089-1395. Idempotent.
# Safe env reader: parses KEY=VALUE, never sources a client-owned file.
_ENVLOAD="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)/../../shared-utils/env-load.sh"
[ -f "$_ENVLOAD" ] || _ENVLOAD="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)/../shared-utils/env-load.sh"
# shellcheck source=/dev/null
[ -f "$_ENVLOAD" ] && . "$_ENVLOAD"
_env_read() { if declare -F env_load >/dev/null 2>&1; then env_load "$1"; else [ -f "$1" ] && { set -a; . "$1"; set +a; }; fi; }

set -euo pipefail

# shellcheck source=/dev/null
. "$(dirname "${BASH_SOURCE[0]}")/lib-docker-tenant.sh"
SECRETS_ENV_FILE="${SECRETS_ENV_FILE:-$(s38_default_secrets_env)}"
CONFIG_FILE="${CONFIG_FILE:-$(s38_config_path)}"
GATEWAY_PORT="${GATEWAY_PORT:-18789}"

_env_read "$SECRETS_ENV_FILE" || true
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

# Validate-then-commit: the candidate is validated as its own file BEFORE it
# replaces the live config, so a key the installed OpenClaw rejects (e.g.
# 2026.9.x `hooks: Unrecognized key "maxBodyBytes"`) is never left live for
# the gateway's hot-reload to trip on.
write_config() {
  local new="$1" tmp="${CONFIG_FILE}.tmp"
  echo "$new" | jq '.' > "$tmp"
  chmod 600 "$tmp" 2>/dev/null || true
  if command -v openclaw >/dev/null 2>&1 && ! OPENCLAW_CONFIG_PATH="$tmp" openclaw config validate >&2; then
    rm -f "$tmp"
    echo "REFUSED: candidate config failed 'openclaw config validate' — live config left unchanged." >&2
    exit 5
  fi
  mv "$tmp" "$CONFIG_FILE"
}

# =============================================================================
# STEP 3 — hooks.mappings (idempotent)
# =============================================================================
echo "==> Step 3: hooks.mappings for route_id=$ROUTE_ID" >&2

# Routing agent must be a CONFIGURED agent (2026.9.x often has no `main`).
ROUTING_AGENT_ID="$(s38_resolve_routing_agent "$CONFIG_FILE")" || exit 10
echo "routing agent: $ROUTING_AGENT_ID" >&2

# Generate / reuse HOOKS_TOKEN (the live hooks.token wins over a fresh one, so
# a re-run never splits the config token from the one the probe and GHL use).
HOOKS_TOKEN="${HOOKS_TOKEN:-$(jq -r '.hooks.token // empty' "$CONFIG_FILE" 2>/dev/null || true)}"
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
     .hooks.defaultSessionKey = (.hooks.defaultSessionKey // "hook:ghl:default") |
     .hooks.allowRequestSessionKey = true |
     .hooks.allowedSessionKeyPrefixes = ((.hooks.allowedSessionKeyPrefixes // []) + ["hook:ghl:"] | unique) |
     .hooks.allowedAgentIds = ((.hooks.allowedAgentIds // []) + [$agent] | unique) |
     .hooks.mappings = ((.hooks.mappings // []) + [$mapping])' "$CONFIG_FILE")"
  write_config "$UPDATED"
  echo "hooks.mappings entry id=$ROUTE_ID merged into config" >&2
fi

# =============================================================================
# STEP 3.1 — Trust the tunnel proxy (idempotent, runs even when the mapping exists)
# =============================================================================
# cloudflared adds X-Forwarded-For. Without gateway.trustedProxies naming the hop
# it connects from, OpenClaw 2026.9.x answers EVERY tunneled request with
# 403 proxy_attribution_required — the hook is unreachable from GHL even though
# it works on localhost. Docker tenant: the bridge gateway (docker-proxy); host or
# Mac cloudflared: loopback. Also heals `hooks.maxBodyBytes`, which earlier
# versions of this script wrote and the 2026.9.x schema rejects.
PROXIES_JSON="$(s38_trusted_proxies | jq -R . | jq -sc .)" || PROXIES_JSON="[]"
if [[ "$PROXIES_JSON" == "[]" ]]; then
  echo "WARN: could not determine the tunnel proxy address — set TRUSTED_PROXIES=<ip> and re-run, or tunneled requests will get 403 proxy_attribution_required." >&2
fi
NEEDS_PROXY_FIX="$(jq --argjson p "$PROXIES_JSON" \
  '((.gateway.trustedProxies // []) as $have | ($p - $have | length) > 0) or (.hooks.maxBodyBytes? != null)' "$CONFIG_FILE")"
if [[ "$NEEDS_PROXY_FIX" == "true" ]]; then
  backup_config
  write_config "$(jq --argjson p "$PROXIES_JSON" \
    '.gateway = (.gateway // {}) |
     .gateway.trustedProxies = ((.gateway.trustedProxies // []) + $p | unique) |
     del(.hooks.maxBodyBytes)' "$CONFIG_FILE")"
  echo "gateway.trustedProxies now includes $PROXIES_JSON (the gateway restarts itself to apply this; expect a short 502 window)" >&2
else
  echo "gateway.trustedProxies already includes $PROXIES_JSON" >&2
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
# The real-time model is the ROUTING agent's own model (string or {primary,...}).
RT_SET="$(jq -r --arg a "$ROUTING_AGENT_ID" '(.agents.entries[$a].model? // ((.agents.list // []) | map(select(.id==$a)) | .[0].model)) // empty | if type=="object" then (.primary // empty) else . end' "$CONFIG_FILE")"
RT_WAS="$RT_SET"
ASYNC_SET="$( { grep -E '^ASYNC_MODEL=' "$SECRETS_ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- ; } || true)"
ASYNC_SET="${ASYNC_SET:-${ASYNC_MODEL:-}}"
BATCH_SET="$( { grep -E '^BATCH_MODEL=' "$SECRETS_ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- ; } || true)"
BATCH_SET="${BATCH_SET:-${BATCH_MODEL:-}}"

if [[ -n "$RT_SET" && -n "$ASYNC_SET" && -n "$BATCH_SET" ]]; then
  echo "all three tiers already configured — skipping wizard (rt=$RT_SET async=$ASYNC_SET batch=$BATCH_SET)" >&2
elif [[ ! -t 0 || -n "${SKILL38_NONINTERACTIVE:-}" ]]; then
  # No terminal (agent exec, cron, CI): never block on /dev/tty and never change
  # a client's model unasked. The routing agent keeps its configured model and
  # async/batch follow it.
  echo "non-interactive run: model wizard skipped — $ROUTING_AGENT_ID keeps ${RT_SET:-its default model}; async/batch follow it. Re-run in a terminal to choose tiers." >&2
  if [[ -n "$RT_SET" ]]; then
    append_secret "ASYNC_MODEL" "${ASYNC_SET:-$RT_SET}"
    append_secret "BATCH_MODEL" "${BATCH_SET:-$RT_SET}"
  fi
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
    "deepseek/deepseek-v4.1-flash:thinking-max — highest-reasoning real-time"
    "google/gemini-3.1-flashlight — fast + near-free (RECOMMENDED for high volume)"
    "kimi/kimi-2.6 — strong long-context reasoning"
    "openai/gpt-5.5 — balanced"
    "openrouter/free — cheapest, slower"
  )
  ASYNC_OPTS=(
    "deepseek/deepseek-v4.1-flash:thinking-max — highest-reasoning"
    "google/gemini-3.1-flashlight — balanced"
    "openrouter/free — free + perfect for email"
    "ollama/deepseek-v4.1-flash:cloud — premium quality (Ollama Cloud)"
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

  # SK1-01: clients NEVER use Anthropic. Hard-reject any Anthropic-family model id
  # (anthropic/*, *claude*, us.anthropic.*) with a nonzero exit BEFORE any key check.
  # Anthropic is deliberately absent from needs_key() so it can never resolve to a
  # provider key on a client box.
  reject_anthropic() {
    local lc
    lc="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
    case "$lc" in
      anthropic/*|*claude*|us.anthropic.*)
        echo "STOP: model '$1' is an Anthropic-family id — clients never use Anthropic. Choose a client-owned provider model and re-run." >&2
        exit 7 ;;
    esac
  }
  # Verify provider key
  needs_key() {
    case "$1" in
      openrouter/*|google/*|deepseek/*|kimi/*|openai/gpt-*|qwen/*) echo "OPENROUTER_API_KEY" ;;
      ollama-cloud/*) echo "OLLAMA_API_KEY" ;;
      *) echo "" ;;
    esac
  }
  for m in "$RT_SET" "$ASYNC_SET" "$BATCH_SET"; do
    reject_anthropic "$m"
    k="$(needs_key "$m")"
    [[ -z "$k" ]] && continue
    if ! grep -qE "^${k}=" "$SECRETS_ENV_FILE" 2>/dev/null && [[ -z "${!k:-}" ]]; then
      echo "STOP: model $m needs $k — add it to $SECRETS_ENV_FILE and re-run." >&2
      exit 6
    fi
  done

  # SCHEMA-SAFE WRITE (2026-05-29): only the real-time model goes into openclaw.json
  # (on the ROUTING agent's model — never an invented `main`; an object model keeps
  # its fallbacks and only `primary` changes). Skipped when the model is unchanged. We DO NOT write
  # `agents.defaults.async`/`agents.defaults.batch` — those keys are rejected by the
  # 2026.5.27 .strict() schema and would make `openclaw config validate` FAIL. The
  # async/batch tier choices are persisted to SECRETS_ENV_FILE instead (read by crons).
  # `.agents = (.agents // {})` / `.agents.list = (.agents.list // [])` replace the
  # jq-1.7-invalid `//=` top-level form (see the hooks-merge note above).
  # ROSTER SHAPE: OpenClaw 2026.9.x keeps agents in `agents.entries` (keyed by
  # id); writing `agents.list` there is `agents: Unrecognized key "list"` and the
  # gateway will not start. Write into whichever shape the box already has.
  if [[ "$RT_SET" != "$RT_WAS" ]]; then
  backup_config
  UPDATED="$(jq \
    --arg rt "$RT_SET" --arg a "$ROUTING_AGENT_ID" \
    'def setm: if (.model | type) == "object" then .model.primary = $rt else .model = $rt end;
     .agents = (.agents // {}) |
     if (.agents.entries | type) == "object" then
       .agents.entries[$a] = ((.agents.entries[$a] // {}) | setm)
     else
       .agents.list = (.agents.list // []) |
       (if (.agents.list | map(.id == $a) | any) then
          .agents.list |= map(if .id == $a then setm else . end)
        else
          .agents.list += [{id:$a, model:$rt}]
        end)
     end' "$CONFIG_FILE")"
  write_config "$UPDATED"
  fi
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
# references/GHL-INBOUND-AND-PLAYBOOKS.md §13). Idempotency is by an EXACT JSON
# name-match (see IDEMPOTENCY note below) — NEVER a text-table grep. If the CLI
# is absent, we skip (non-fatal) rather than write an invalid config block.
#
# IDEMPOTENCY (fix/industry-gate-and-idempotent-crons, 2026-07-11 — BUG FIX):
# "system-health-heartbeat" is 23 chars — over the ~22-char threshold at which
# `openclaw cron list`'s text table truncates names — so a text-grep presence
# gate here false-negatives and re-adds a duplicate on every re-run (same
# defect confirmed + fixed in this skill's own 04-register-crons.sh). Sourcing
# oc_cron_present() from shared-utils/cron-lib.sh, with an inline fallback.
command -v oc_cron_present >/dev/null 2>&1 || {
  _lib_cron_present_15="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/shared-utils/cron-lib.sh"
  if [ -f "$_lib_cron_present_15" ]; then
    # shellcheck source=/dev/null
    . "$_lib_cron_present_15"
  fi
}
command -v oc_cron_present >/dev/null 2>&1 || oc_cron_present() {
  local _name="$1" _raw
  _raw=$(openclaw cron list --json 2>/dev/null) || _raw=""
  if [ -n "$_raw" ] && command -v jq >/dev/null 2>&1; then
    printf '%s' "$_raw" | jq -e --arg n "$_name" '
      ( if type == "array" then . else .jobs // [] end ) | map(select(.name == $n)) | length > 0
    ' >/dev/null 2>&1
    return $?
  fi
  return 1
}
# DURABLE TOMBSTONE fallback (fix/industry-gate-and-idempotent-crons, live-VPS
# finding): fail OPEN (never tombstoned) if the shared lib wasn't found above.
command -v oc_cron_tombstoned >/dev/null 2>&1 || oc_cron_tombstoned() { return 1; }
if command -v openclaw >/dev/null 2>&1; then
  if oc_cron_tombstoned "system-health-heartbeat"; then
    echo "cron system-health-heartbeat is TOMBSTONED (deliberately removed) — NOT re-registering. Un-tombstone: bash scripts/tombstone-cron.sh --remove system-health-heartbeat" >&2
  elif oc_cron_present "system-health-heartbeat"; then
    echo "cron system-health-heartbeat already registered — skipping" >&2
  else
    # SILENCE DOCTRINE (FIX-XC-08b): 2026.6.8+ `cron add` fallback-delivers the
    # job's final text to the last (client) chat every fire. This monthly review
    # is headless operator housekeeping and notifies the operator from inside its
    # own prompt — it must NOT surface in the client conversation. Register it
    # silenced (--no-deliver) in an isolated operator-side session (--session
    # isolated). Both flags are feature-detected with a no-flag retry.
    _sh_cron_help="$(openclaw cron add --help 2>&1 || true)"
    _sh_has_flag() { printf '%s' "$_sh_cron_help" | grep -qE -- "(^|[[:space:]])$1([[:space:]<=]|\$)"; }
    SH_SILENCE_ARGS=()
    _sh_has_flag '--no-deliver' && SH_SILENCE_ARGS+=(--no-deliver)
    _sh_has_flag '--session'    && SH_SILENCE_ARGS+=(--session isolated)
    _sh_msg="Run the Monthly Comprehensive Review per protocols/monthly-comprehensive-review-protocol.md — 30-day audit across playbooks, GHL workflows, knowledge bases, model configs, tune-ups, bug log."
    if openclaw cron add --name system-health-heartbeat --cron "0 9 1 * *" \
         --agent "$ROUTING_AGENT_ID" --light-context \
         ${SH_SILENCE_ARGS[@]+"${SH_SILENCE_ARGS[@]}"} --message "$_sh_msg" >&2 \
       || openclaw cron add --name system-health-heartbeat --cron "0 9 1 * *" \
         --agent "$ROUTING_AGENT_ID" --light-context --message "$_sh_msg" >&2; then
      echo "registered cron: system-health-heartbeat (0 9 1 * *) via openclaw cron add [delivery silenced]" >&2
    else
      echo "WARN: 'openclaw cron add system-health-heartbeat' failed — register it manually (cron.jobs JSON is invalid on 2026.5.27)" >&2
    fi
  fi
else
  echo "WARN: openclaw CLI not on PATH — cannot register system-health-heartbeat cron (do NOT write cron.jobs JSON; it is invalid on 2026.5.27)" >&2
fi

# =============================================================================
# STEP 4 — Reachability probe through the public tunnel (NO agent run)
# =============================================================================
# This step proves tunnel -> trusted proxy -> hook auth -> mapping match WITHOUT
# dispatching the agent. (The old step POSTed a full body at a fake contact,
# which started a real agent run that tried to message a non-existent contact.)
#   1. no token                                  -> 401 (hooks live behind auth)
#   2. real token + session_key outside the allowed "hook:ghl:" prefix
#                                                -> 400 "sessionKey must start with"
#      i.e. the route matched and the request was refused BEFORE admission.
# 403 proxy_attribution_required = gateway.trustedProxies is wrong; 502/000 while
# the gateway restarts to apply it, so those are retried for up to ~5 minutes.
# The full inbound->reply ground-truth test is scripts/24-self-test-hook.sh.
echo "==> Step 4: reachability probe (no agent run)" >&2
URL="https://${PUBLIC_HOSTNAME}/hooks/${ROUTE_ID}"
probe() {  # $1 = auth header value or "" ; prints "CODE BODY"
  local out
  out="$(curl -sS --max-time 20 -X POST "$URL" -H "Content-Type: application/json" \
    ${1:+-H "Authorization: Bearer $1"} \
    -d '{"session_key":"skill38-probe:not-allowed","message_body":"probe"}' \
    -w $'\n%{http_code}' 2>/dev/null)" || out=$'\n000'
  printf '%s %s' "${out##*$'\n'}" "${out%$'\n'*}"
}
for _i in $(seq 1 30); do
  R1="$(probe "")"
  case "${R1%% *}" in 000|502|503|403) sleep 10 ;; *) break ;; esac
done
R2="$(probe "$HOOKS_TOKEN")"
if [[ "${R1%% *}" == "401" && "${R2%% *}" == "400" && "$R2" == *"sessionKey must start with"* ]]; then
  echo "PROBE PASS — no token: 401; real token: 400 (route matched, refused before admission)" >&2
else
  echo "PROBE FAIL — no token: ${R1:0:200} | real token: ${R2:0:200}" >&2
  [[ "$R1" == *proxy_attribution_required* ]] && echo "  fix: gateway.trustedProxies must name the hop cloudflared connects from (TRUSTED_PROXIES=<ip>, re-run)." >&2
  [[ "${R2%% *}" == "404" ]] && echo "  fix: no hooks mapping matched /hooks/${ROUTE_ID} — hooks.enabled / hooks.mappings not live yet." >&2
  exit 7
fi

echo "OK: hooks + proxy + models + cron configured; probe pass. Next: scripts/24-self-test-hook.sh for the full inbound->reply test." >&2
