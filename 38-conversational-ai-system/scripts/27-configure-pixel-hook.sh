#!/usr/bin/env bash
# 27-configure-pixel-hook.sh — ZHC Pixel (Feature 49).
# Registers the `pixel-visitor-signal` hooks.mappings entry and the scoped
# Pixel Concierge agent in openclaw.json. Idempotent. jq-1.7-safe.
#
# Mirrors the config-merge discipline of 15-configure-hooks-mappings.sh:
#   • uses `.x = (.x // {})` (NOT the jq-1.7-invalid `//= ;` top-level form)
#   • reuses HOOKS_TOKEN (never the gateway token)
#   • deliver:false, a real model, an allowed sessionKey prefix
#   • runs `openclaw config validate` if the CLI is present
#
# The Pixel Concierge is a SEPARATE agent with a scoped allow-list — it acts only on
# its own hook:pixel:* sessions, never as a general operator agent. Its behavior lives
# in AGENTS.md Step 1.45 (STEP_1_45_PIXEL_CONCIERGE, inserted by 05-update-agents-md.sh)
# + protocols/zhc-pixel-protocol.md.
#
# UNIVERSAL. BASH only. Never echoes the hooks token.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

SECRETS_ENV_FILE="${SECRETS_ENV_FILE:-$HOME/.openclaw/secrets.env}"
CONFIG_FILE="${CONFIG_FILE:-$HOME/.openclaw/openclaw.json}"

[ -f "$SECRETS_ENV_FILE" ] && { set -a; . "$SECRETS_ENV_FILE"; set +a; } || true
[ -f "$CONFIG_FILE" ] || { echo "openclaw config not found: $CONFIG_FILE" >&2; exit 2; }
command -v jq >/dev/null 2>&1 || { echo "jq required" >&2; exit 3; }

HOOK_ID="pixel-visitor-signal"
PIXEL_AGENT_ID="${ZHC_PIXEL_AGENT_ID:-pixel-concierge}"
# A cheap real-time model — most signals are dropped before any reasoning. Operator
# may override; default mirrors the e2e test default used elsewhere in the skill.
PIXEL_MODEL="${ZHC_PIXEL_MODEL:-ollama/deepseek-v4-flash:cloud}"

append_secret() {
  local k="$1" v="$2"
  [ -f "$SECRETS_ENV_FILE" ] || { mkdir -p "$(dirname "$SECRETS_ENV_FILE")"; : > "$SECRETS_ENV_FILE"; chmod 600 "$SECRETS_ENV_FILE"; }
  grep -qE "^${k}=" "$SECRETS_ENV_FILE" 2>/dev/null && return 0
  printf '%s=%s\n' "$k" "$v" >> "$SECRETS_ENV_FILE"
}
backup_config() { cp "$CONFIG_FILE" "${CONFIG_FILE}.bak.$(date +%Y%m%d-%H%M%S)"; echo "config backup written" >&2; }
write_config() { echo "$1" | jq '.' > "${CONFIG_FILE}.tmp" && mv "${CONFIG_FILE}.tmp" "$CONFIG_FILE"; }

# -------- HOOKS_TOKEN (reuse; never the gateway token) --------
if [ -z "${HOOKS_TOKEN:-}" ]; then
  HOOKS_TOKEN="$(jq -r '.hooks.token // empty' "$CONFIG_FILE" 2>/dev/null || true)"
fi
if [ -z "${HOOKS_TOKEN:-}" ]; then
  HOOKS_TOKEN="$(openssl rand -base64 32 | tr -d '\n=' | head -c 43)"
  append_secret "HOOKS_TOKEN" "$HOOKS_TOKEN"
  echo "generated HOOKS_TOKEN (length=${#HOOKS_TOKEN})" >&2
fi
GATEWAY_TOKEN="$(jq -r '.gateway.auth.token // empty' "$CONFIG_FILE" 2>/dev/null || true)"
if [ -n "$GATEWAY_TOKEN" ] && [ "$GATEWAY_TOKEN" = "$HOOKS_TOKEN" ]; then
  echo "HOOKS_TOKEN equals gateway.auth.token — refused." >&2; exit 4
fi

# -------- Is the mapping already present? --------
HAS_MAPPING="$(jq --arg id "$HOOK_ID" '.hooks.mappings? // [] | map(.id == $id) | any' "$CONFIG_FILE")"
if [ "$HAS_MAPPING" = "true" ]; then
  echo "hooks.mappings entry id=$HOOK_ID already present — skipping merge" >&2
else
  backup_config
  # The pixel hook session is per (site, visitor). deliver:false — the agent acts via
  # GHL / the chat widget, it never echoes the signal back to the browser. The
  # messageTemplate orders the agent to: (1) drop bot-like traffic with ZERO model
  # spend FIRST, (2) append events to the F52 JSONL, (3) evaluate the trigger rules,
  # (4) only engage on a firing rule (least-intrusive action), all per the protocol.
  NEW_MAPPING="$(jq -n \
    --arg id "$HOOK_ID" \
    --arg agent "$PIXEL_AGENT_ID" \
    --arg model "$PIXEL_MODEL" \
    '{
      id:$id, match:{path:$id}, action:"agent", agentId:$agent, model:$model,
      wakeMode:"now", name:"ZHC Pixel Visitor Signal",
      sessionKey:"hook:pixel:{{site_id}}:{{visitor_id}}",
      messageTemplate:"ZHC PIXEL VISITOR SIGNAL — site={{site_id}} visitor={{visitor_id}}. This is an anonymous-or-known website visitor behavior batch, NOT a chat message. STEP 1 (bot gate, do this FIRST, spend ZERO further reasoning if it fires): if the signal is bot-like (sub-2-second pageview cadence, impossible scroll velocity, headless/known-bot user agent) then DROP it — append nothing, engage no one, end the turn. STEP 2: append every event in this batch to <MASTER_FILES_DIR>/pixel-events/YYYY-MM-DD.jsonl (one JSON object per line; timestamp + event_type + data) per protocols/zhc-pixel-protocol.md section 7. STEP 3: evaluate the behavioral trigger rules in protocols/zhc-pixel-protocol.md section 4 against this visitor (pricing dwell, contact-click preempt, 4th-return soft outreach, cart-abandonment +1h email, comparison-shopping consultation, known-customer-on-account = no engagement). NEVER fabricate a visitor identity — if anonymous, you only know behavior; resolve identity ONLY by first-party form linkage (section 2). STEP 4: only if a rule fires, take the LEAST-INTRUSIVE action (chat widget directive / GHL tag+field write with ZHC- / ZHC_ prefixes / scheduled follow-up), respecting quiet hours (Step 0.5), compliance keywords (Step 0.7) and the honesty floor. You are the Pixel Concierge — you act only on these pixel sessions, never as a general operator agent.",
      deliver:false, timeoutSeconds:120
    }')"

  # FAIL-CLOSED GUARD: the messageTemplate must carry the bot-gate-first, the JSONL
  # append, the no-fabrication rule, and the least-intrusive directive. Refuse to write
  # a pixel hook that would burn tokens on bots or fabricate identities.
  GUARD_MT="$(printf '%s' "$NEW_MAPPING" | jq -r '.messageTemplate')"
  for needle in "bot" "ZERO further reasoning" "pixel-events" "NEVER fabricate" "first-party form" "LEAST-INTRUSIVE"; do
    if ! printf '%s' "$GUARD_MT" | grep -qi -- "$needle"; then
      echo "REFUSED: pixel messageTemplate missing element '$needle'." >&2; exit 8
    fi
  done

  UPDATED="$(jq \
    --arg tok "$HOOKS_TOKEN" \
    --arg agent "$PIXEL_AGENT_ID" \
    --argjson mapping "$NEW_MAPPING" \
    '.hooks = (.hooks // {}) |
     .hooks.enabled = true |
     .hooks.token = $tok |
     .hooks.path = (.hooks.path // "/hooks") |
     .hooks.maxBodyBytes = (.hooks.maxBodyBytes // 262144) |
     .hooks.allowRequestSessionKey = true |
     .hooks.allowedSessionKeyPrefixes = ((.hooks.allowedSessionKeyPrefixes // []) + ["hook:pixel:"] | unique) |
     .hooks.allowedAgentIds = ((.hooks.allowedAgentIds // []) + [$agent] | unique) |
     .hooks.mappings = ((.hooks.mappings // []) + [$mapping])' "$CONFIG_FILE")"
  write_config "$UPDATED"
  echo "hooks.mappings entry id=$HOOK_ID merged (agent=$PIXEL_AGENT_ID, deliver:false, model set)" >&2
fi

# -------- Register the scoped Pixel Concierge agent (idempotent) --------
HAS_AGENT="$(jq --arg id "$PIXEL_AGENT_ID" '(.agents.list // []) | map(.id == $id) | any' "$CONFIG_FILE")"
if [ "$HAS_AGENT" = "true" ]; then
  echo "agent $PIXEL_AGENT_ID already present in agents.list — skipping" >&2
else
  backup_config
  # SCHEMA-SAFE: only add the agent to agents.list with an id + model. The behavioral
  # allow-list is enforced via hooks.allowedAgentIds + allowedSessionKeyPrefixes above
  # and the AGENTS.md Step 1.45 protocol — we do NOT write any .strict()-rejected key.
  UPDATED="$(jq \
    --arg id "$PIXEL_AGENT_ID" \
    --arg model "$PIXEL_MODEL" \
    '.agents = (.agents // {}) |
     .agents.list = (.agents.list // []) |
     .agents.list += [{id:$id, model:$model, name:"Pixel Concierge"}]' "$CONFIG_FILE")"
  write_config "$UPDATED"
  echo "registered scoped agent: $PIXEL_AGENT_ID (model=$PIXEL_MODEL)" >&2
fi

# Ensure the pixel-events dir exists + is writable (F52 data contract).
MASTER_FILES_POINTER="${HOME}/.openclaw/.skill-38-master-files-dir"
if [ -z "${MASTER_FILES_DIR:-}" ] && [ -f "$MASTER_FILES_POINTER" ]; then
  MASTER_FILES_DIR="$(head -n1 "$MASTER_FILES_POINTER")"
fi
if [ -n "${MASTER_FILES_DIR:-}" ]; then
  mkdir -p "$MASTER_FILES_DIR/pixel-events"
  echo "ensured F52 data-contract dir: $MASTER_FILES_DIR/pixel-events/" >&2
fi

# -------- Validate --------
if command -v openclaw >/dev/null 2>&1; then
  openclaw config validate >/dev/null 2>&1 \
    && echo "openclaw config validate: OK" >&2 \
    || { echo "openclaw config validate FAILED — restore from .bak.*" >&2; exit 5; }
fi

echo "OK: pixel-visitor-signal hook + Pixel Concierge agent configured." >&2
echo "Next: scripts/25-verify-pixel-prerequisites.sh then scripts/28-deploy-pixel-cloudflare.sh (scope-gated)." >&2
