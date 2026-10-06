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
# silently falls back or fails, so an unknown id is a hard error here.
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
         else error("ROUTING_AGENT_ID \"\($w)\" is not a configured agent") end)
      else
        ([(.hooks.mappings // [])[] | .agentId? // empty | select(. as $a | ($ids | index($a)) != null)][0]
         // (if ($ids | index("dept-communications")) != null then "dept-communications" else null end)
         // (if ($ids | index("main")) != null then "main" else null end)
         // error("no routing agent found: set ROUTING_AGENT_ID to a configured agent id"))
      end' "$cfg" 2>&1)" || { echo "[skill 38] $out" >&2; return 1; }
  printf '%s\n' "$out"
}
