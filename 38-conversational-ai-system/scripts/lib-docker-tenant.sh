#!/usr/bin/env bash
# lib-docker-tenant.sh — Skill 38 shared helpers (source it; defines functions only).
#
# WHY: on a Contabo/VPS docker tenant the box's public hostname is served by the
# OPERATOR's cloudflared on the HOST, not by a tunnel inside the container. An
# agent inside the container cannot see that tunnel, so before this lib it
# concluded "no tunnel" and asked the client for a Cloudflare API token — in one
# case a token on the OPERATOR's own zone, which would hand a client box edit
# rights over every other client's DNS. These helpers let the install scripts
# recognise that box shape and wire the inbound hook correctly:
#   s38_in_container           0 if running inside a container
#   s38_config_path            prints the live openclaw.json path
#   s38_default_secrets_env    prints the secrets env file to use
#   s38_env_file_value KEY     prints KEY's value from the secrets env files
#   s38_trusted_proxies        prints the proxy IP(s) the gateway must trust
#   s38_resolve_routing_agent  prints the configured agent that answers GHL inbound
#
# The operator zone's Cloudflare token is NEVER given to a client box.

# PBB-017: the mandatory send-directive and conversation-memory needles now live
# in ONE place — scripts/lib-hook-mapping-contract.sh — and this file merely
# prints them. FAIL CLOSED when it is missing: falling back to a duplicated
# literal list here is exactly what let the writer and the two gates drift apart,
# so an install without the contract is refused rather than silently guessed.
_S38_CONTRACT="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)/lib-hook-mapping-contract.sh"
if [ ! -f "$_S38_CONTRACT" ]; then
  echo "REFUSED: lib-hook-mapping-contract.sh not found at $_S38_CONTRACT — the directive needles have no source of truth. Install the full skill." >&2
  return 1 2>/dev/null || exit 1
fi
# shellcheck source=/dev/null
. "$_S38_CONTRACT"
unset _S38_CONTRACT

s38_in_container() {
  [ -f /.dockerenv ] || [ -f /run/.containerenv ] \
    || grep -qaE 'docker|containerd|kubepods|libpod' /proc/1/cgroup 2>/dev/null
}

s38_config_path() {
  local c
  for c in "${OPENCLAW_CONFIG:-}" "${CONFIG_FILE:-}" "$HOME/.openclaw/openclaw.json" "/data/.openclaw/openclaw.json"; do
    [ -n "$c" ] && [ -f "$c" ] && { printf '%s\n' "$c"; return 0; }
  done
  printf '%s\n' "$HOME/.openclaw/openclaw.json"
}

# Order: the path 18-locate-secrets-env.sh persisted, the legacy default if it
# exists, then the stores docker tenants and Macs actually use, then the legacy
# default (created on first write by the caller).
s38_default_secrets_env() {
  local state="$HOME/.openclaw/.skill-38-secrets-env-path" c
  if [ -f "$state" ]; then
    c="$(tr -d '[:space:]' < "$state" 2>/dev/null)"
    [ -n "$c" ] && [ -f "$c" ] && { printf '%s\n' "$c"; return 0; }
  fi
  for c in "$HOME/.openclaw/secrets.env" "$HOME/.openclaw/secrets/.env" "/data/.openclaw/secrets/.env" "$HOME/.openclaw/.env"; do
    [ -f "$c" ] && { printf '%s\n' "$c"; return 0; }
  done
  printf '%s\n' "$HOME/.openclaw/secrets.env"
}

s38_env_file_value() {
  local key="$1" f v
  for f in "$(s38_default_secrets_env)" "$HOME/.openclaw/secrets/.env" "/data/.openclaw/secrets/.env" \
           "$HOME/.openclaw/.env" "$HOME/.openclaw/secrets.env"; do
    [ -f "$f" ] || continue
    v="$(grep -E "^[[:space:]]*(export[[:space:]]+)?${key}=" "$f" 2>/dev/null | tail -1 \
         | sed -E "s/^[[:space:]]*(export[[:space:]]+)?${key}=//; s/^\"(.*)\"\$/\\1/; s/^'(.*)'\$/\\1/")"
    [ -n "$v" ] && { printf '%s\n' "$v"; return 0; }
  done
  return 1
}

# A docker tenant's tunnel traffic arrives from the container's default-route
# gateway (the host side of the bridge, via docker-proxy). A host/Mac cloudflared
# connects from loopback. TRUSTED_PROXIES (comma list) overrides. Never a wildcard.
s38_trusted_proxies() {
  if [ -n "${TRUSTED_PROXIES:-}" ]; then
    printf '%s\n' "$TRUSTED_PROXIES" | tr ',' '\n' | sed '/^[[:space:]]*$/d'
    return 0
  fi
  if s38_in_container; then
    local gw=""
    gw="$(ip route 2>/dev/null | awk '/^default/{print $3; exit}')"
    if [ -z "$gw" ] && [ -r /proc/net/route ]; then
      local hex
      hex="$(awk '$2=="00000000"{print $3; exit}' /proc/net/route)"
      [ -n "$hex" ] && gw="$(printf '%d.%d.%d.%d' "0x${hex:6:2}" "0x${hex:4:2}" "0x${hex:2:2}" "0x${hex:0:2}")"
    fi
    [ -n "$gw" ] || return 1
    printf '%s\n' "$gw"
  else
    printf '127.0.0.1\n::1\n'
  fi
}

# Precedence: ROUTING_AGENT_ID (must exist) > the agent an existing hooks mapping
# already uses > dept-communications > main. OpenClaw 2026.9.x keeps agents in
# `agents.entries` (keyed by id) and often has NO `main`; routing to a missing id
# silently falls back or fails, so an unknown id is a hard error here. Every
# failure NAMES the configured candidates, so the operator can set
# ROUTING_AGENT_ID to one of them instead of hunting the roster (the repair
# script reports the same list).
s38_resolve_routing_agent() {
  local cfg="${1:-$(s38_config_path)}"
  if ! command -v jq >/dev/null 2>&1 || [ ! -f "$cfg" ]; then
    printf '%s\n' "${ROUTING_AGENT_ID:-main}"   # cannot inspect: legacy behaviour
    return 0
  fi
  local out
  out="$(jq -er --arg w "${ROUTING_AGENT_ID:-}" '
    ([(.agents.entries // {} | keys[]), ((.agents.list // [])[] | .id? // empty)]) as $ids
    | if ($ids | length) == 0 then (if $w != "" then $w else "main" end)
      elif $w != "" then
        (if ($ids | index($w)) != null then $w
         else error("ROUTING_AGENT_ID \"\($w)\" is not a configured agent — configured agents: \($ids | join(", "))") end)
      else
        ([(.hooks.mappings // [])[] | .agentId? // empty | select(. as $a | ($ids | index($a)) != null)][0]
         // (if ($ids | index("dept-communications")) != null then "dept-communications" else null end)
         // (if ($ids | index("main")) != null then "main" else null end)
         // error("no routing agent found: set ROUTING_AGENT_ID to one of \($ids | join(", "))"))
      end' "$cfg" 2>&1)" || { echo "[skill 38] $out" >&2; return 1; }
  printf '%s\n' "$out"
}

# =============================================================================
# hooks.mappings — canonical shape + content-addressed idempotent migration
# =============================================================================
# G-01: before v2.0.24 an upgraded box kept its PRE-UPGRADE mapping body
# forever, because the installer only merged a mapping when the id was absent
# ("skipping merge"). Nested sessionKey merge tokens, a messageTemplate with no
# send-directive and no conversation-log read/append then survived every
# re-run. These helpers make the mapping CONTENT-ADDRESSED instead: the
# required shape is built once, compared key-by-key against what is live, and
# only the DIVERGENT keys are upgraded. A second run reports no changes and
# writes nothing.
#
# The canonical messageTemplate lives HERE (a .sh under scripts/) on purpose:
# qc-send-directive.sh and qc-conversation-memory.sh lint it by scanning
# references/ + templates/ + scripts/ for .md/.sh/.txt messageTemplate text.

# Canonical GHL inbound SERVER mapping for one route.
#   s38_canonical_mapping <id> <match.path> <agentId> <sessionKey>
s38_canonical_mapping() {
  jq -n --arg id "$1" --arg path "$2" --arg agent "$3" --arg sk "$4" \
    '{
      id:$id, match:{path:$path}, action:"agent", agentId:$agent,
      wakeMode:"now", name:"GHL Inbound", sessionKey:$sk,
      messageTemplate:"INBOUND MESSAGE FROM GOHIGHLEVEL — {{channel}} channel From: {{first_name}} {{last_name}} Phone: {{phone}} Email: {{email}} Contact ID: {{contact_id}} Location ID: {{location_id}} Location name: {{location_name}} Customer message subject: {{subject}} Customer message body: {{message_body}} CONVERSATION MEMORY — THIS HOOK SESSION IS SINGLE-TURN AND STATELESS, your only memory of this contact is the log file. FIRST, before drafting anything, READ this contact'\''s conversation log at <MASTER_FILES_DIR>/conversational-logs/{{contact_id}}__<name>.md for the full prior conversation and any in-progress booking/context (see AGENTS.md Conversation Memory Protocol); if the file is missing, treat this as a new contact. CONTINUE any in-progress topic/booking from the log instead of restarting. To pull deeper prior thread history when the log is thin, READ it from GHL: GET conversations/search?locationId={{location_id}}&contactId={{contact_id}} to find the conversationId, then GET conversations/{conversationId}/messages — conversationId is a READ key only, never a send field. Also check the matching playbook in conversation-workflows. MANDATORY — SEND on the SAME channel the message arrived on, do not just draft, and ONLY through the one chokepoint: FIRST run python3 tools/pb_send.py admit --tenant {{location_id}} --message-id {{message_id}} --contact {{contact_id}} — exit code 3 means a duplicate delivery, END YOUR TURN with no reply. THEN send only via python3 tools/pb_send.py reply --tenant {{location_id}} --contact {{contact_id}} --inbound-message-id {{message_id}} --channel <the MIRRORED inbound {{channel}} value: SMS->sms, Email->email, Facebook->fb, Instagram->instagram, WhatsApp->whatsapp, Live Chat->live_chat> --text \"<your reply>\" — do NOT hardcode SMS; the tool maps the mirror to the GHL send type and threads BY contactId. The tool composes consent, the human-handoff fence and the answer-duty gate, then sends through the GHL Conversations sender; a SUPPRESSED, QUARANTINED or WAIT_UNTIL answer means DO NOT SEND and never work around it. Per TOOLS.md. Composing or drafting a reply is NOT sending — the customer receives nothing unless pb_send.py reply returns a messageId. Do NOT end your turn until pb_send.py reply returns a messageId. AFTER the send returns a messageId, APPEND both this inbound message and your reply to <MASTER_FILES_DIR>/conversational-logs/{{contact_id}}__<name>.md (create the file if it is missing) — a reply that does not update the log loses this contact'\''s memory and is a failure.",
      deliver:false, timeoutSeconds:300
    }'
}

# Mandatory send-directive elements (qc-send-directive.sh Layer 3 enforces the
# same list) and conversation-memory elements (qc-conversation-memory.sh).
# PBB-017: the lists themselves live in lib-hook-mapping-contract.sh and are
# SOURCED at the top of this file — these are printers over that one source, so
# the installer guard, the mapping migration and the two gates cannot drift.
s38_send_directive_needles() {
  printf '%s\n' "$HOOK_MAPPING_SEND_DIRECTIVE_NEEDLES"
}

s38_conversation_memory_needles() {
  printf '%s\n' "$HOOK_MAPPING_CONVERSATION_MEMORY_NEEDLES"
}

# Every needle a valid messageTemplate must carry.
s38_required_template_needles() {
  printf '%s\n' "$HOOK_MAPPING_DIRECTIVE_NEEDLES"
}

# True when the template carries every required needle.
#   s38_template_is_current <messageTemplate>
s38_template_is_current() {
  local t needle
  t="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  while IFS= read -r needle; do
    [ -n "$needle" ] || continue
    nl="$(printf '%s' "$needle" | tr '[:upper:]' '[:lower:]')"
    case "$t" in
      *"$nl"*) ;;
      *) return 1 ;;
    esac
  done < <(s38_required_template_needles)
  return 0
}

# Key-level, content-addressed merge of the live mapping body onto the required
# shape. Only keys that DIVERGE are upgraded:
#   id, action, deliver, match.path  -> forced to the required value (fail-closed)
#   agentId      -> kept when it names a configured agent, else rebound to the
#                   required routing agent (G-02: a stale id used to be reported
#                   and never rebound)
#   sessionKey   -> kept unless it is empty or carries a nested {{a.b}} merge
#                   token (the GHL body sends a FLAT session_key)
#   messageTemplate -> kept unless it is missing a required directive element
#   name, wakeMode, timeoutSeconds   -> operator values kept while still valid
#   every other operator key         -> left untouched
#   s38_merge_mapping_body <have-json> <want-json> <configured-agent-ids-json>
s38_merge_mapping_body() {
  jq -c -n --argjson have "$1" --argjson want "$2" --argjson keep "$3" \
    --argjson needles "$(s38_required_template_needles | jq -R . | jq -sc .)" '
    def nonempty_str: (type == "string") and (length > 0);
    def pos_int: (type == "number") and (. > 0) and ((. | floor) == .);
    ($want.messageTemplate // "") as $wmt
    | (($have | if type == "object" then . else {} end)) as $h
    | (($h.messageTemplate // "") | ascii_downcase) as $ht
    | ([ $needles[] as $n | select(($ht | contains($n | ascii_downcase)) | not) ]) as $miss
    | (if (($h.agentId? | nonempty_str) and (($keep | index($h.agentId)) != null))
       then $h.agentId else $want.agentId end) as $aid
    | (if (($h.sessionKey? | nonempty_str) and
           (($h.sessionKey | test("\\{\\{[^}]*\\.[^}]*\\}\\}")) | not))
       then $h.sessionKey else $want.sessionKey end) as $sk
    | (if (($h.messageTemplate? | nonempty_str) and ($miss | length) == 0)
       then $h.messageTemplate else $wmt end) as $mt
    | ($want
       | .id = $want.id
       | .action = $want.action
       | .match = ((if ($h.match? | type) == "object" then $h.match else {} end) + ($want.match // {}))
       | .agentId = $aid
       | .wakeMode = (if ($h.wakeMode? | nonempty_str) then $h.wakeMode else $want.wakeMode end)
       | .name = (if ($h.name? | nonempty_str) then $h.name else $want.name end)
       | .sessionKey = $sk
       | .messageTemplate = $mt
       | .deliver = false
       | .timeoutSeconds = (if ($h.timeoutSeconds? | pos_int) then $h.timeoutSeconds
                             else $want.timeoutSeconds end)) as $base
    | ($h | with_entries(select(.key as $k | ($base | has($k)) | not))) + $base
  '
}

# Keys whose value the merge would actually change.
#   s38_mapping_changed_keys <have-json> <merged-json>
s38_mapping_changed_keys() {
  jq -r -n --argjson have "$1" --argjson merged "$2" '
    (($have | if type == "object" then . else {} end) | keys_unsorted)
    + (($merged | if type == "object" then . else {} end) | keys_unsorted)
    | unique[] as $k
    | select(($have[$k] // null) != ($merged[$k] // null))
    | $k'
}

# One call for the repair script: resolve the routing agent, rebuild the
# required shape for THIS mapping, merge, and report what changed.
# Prints {"mapping": {...}, "changedKeys": [...]}. Stderr on failure.
#   s38_migrate_mapping <config-path> <mapping-json> <configured-agent-ids-json>
s38_migrate_mapping() {
  local cfg="$1" mapping="$2" keep="$3" id path agent want merged changed
  command -v jq >/dev/null 2>&1 || { echo "jq required" >&2; return 1; }
  id="$(printf '%s' "$mapping" | jq -r '.id // empty')"
  [ -n "$id" ] || { echo "mapping has no id" >&2; return 1; }
  path="$(printf '%s' "$mapping" | jq -r '.match.path // empty')"
  [ -n "$path" ] || path="$id"
  if ! agent="$(s38_resolve_routing_agent "$cfg" 2>/dev/null)"; then
    # No routing agent could be resolved. Rebind only when the box has exactly
    # one configured agent (then it is unambiguous); with several, leave the body
    # alone and name the candidates rather than guess which agent answers GHL
    # inbound.
    if [ "$(printf '%s' "$keep" | jq 'length')" = "1" ]; then
      agent="$(printf '%s' "$keep" | jq -r '.[0]')"
    else
      echo "no routing agent resolvable and $(printf '%s' "$keep" | jq 'length') configured agents exist — set ROUTING_AGENT_ID to one of $(printf '%s' "$keep" | jq -r 'join(", ")')" >&2
      return 1
    fi
  fi
  want="$(s38_canonical_mapping "$id" "$path" "$agent" "{{session_key}}")" || return 1
  merged="$(s38_merge_mapping_body "$mapping" "$want" "$keep")" || return 1
  changed="$(s38_mapping_changed_keys "$mapping" "$merged" | jq -R . | jq -sc .)" || return 1
  jq -c -n --argjson m "$merged" --argjson c "$changed" '{mapping:$m, changedKeys:$c}'
}
