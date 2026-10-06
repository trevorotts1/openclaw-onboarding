#!/usr/bin/env bash
# lib-docker-tenant.test.sh — hermetic checks for lib-docker-tenant.sh and the
# Step 3.1 config edit in 15-configure-hooks-mappings.sh. No network, no box.
set -uo pipefail
cd "$(dirname "$0")" || exit 2
# shellcheck source=/dev/null
. ./lib-docker-tenant.sh
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
fails=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: got '$2' want '$3'"; fails=$((fails+1)); fi; }

command -v jq >/dev/null 2>&1 || { echo "SKIP: jq not installed"; exit 0; }

# --- routing agent resolution -------------------------------------------------
echo '{"agents":{"entries":{"dept-communications":{},"dept-sales":{}}}}' > "$T/a.json"
check "no main: falls to dept-communications" "$(ROUTING_AGENT_ID= s38_resolve_routing_agent "$T/a.json")" "dept-communications"
check "explicit configured id wins" "$(ROUTING_AGENT_ID=dept-sales s38_resolve_routing_agent "$T/a.json")" "dept-sales"
ROUTING_AGENT_ID=main s38_resolve_routing_agent "$T/a.json" >/dev/null 2>&1; check "explicit missing id fails" "$?" "1"

echo '{"agents":{"entries":{"dept-communications":{},"dept-sales":{}}},"hooks":{"mappings":[{"agentId":"dept-sales"}]}}' > "$T/b.json"
check "existing mapping agent wins over default" "$(ROUTING_AGENT_ID= s38_resolve_routing_agent "$T/b.json")" "dept-sales"

echo '{"agents":{"list":[{"id":"main"}]}}' > "$T/c.json"
check "legacy agents.list main" "$(ROUTING_AGENT_ID= s38_resolve_routing_agent "$T/c.json")" "main"

echo '{"agents":{"entries":{"x":{}}}}' > "$T/d.json"
ROUTING_AGENT_ID= s38_resolve_routing_agent "$T/d.json" >/dev/null 2>&1; check "no candidate fails loudly" "$?" "1"

echo '{}' > "$T/e.json"
check "no roster: legacy main" "$(ROUTING_AGENT_ID= s38_resolve_routing_agent "$T/e.json")" "main"

# --- trusted proxies ----------------------------------------------------------
check "TRUSTED_PROXIES override" "$(TRUSTED_PROXIES='10.0.0.1,10.0.0.2' s38_trusted_proxies | paste -sd, -)" "10.0.0.1,10.0.0.2"

# --- Step 3.1 edit: merge proxies, drop maxBodyBytes, keep existing entries ---
echo '{"gateway":{"trustedProxies":["10.9.9.9"]},"hooks":{"enabled":true,"maxBodyBytes":262144}}' > "$T/f.json"
out="$(jq --argjson p '["172.19.0.1"]' '.gateway = (.gateway // {}) |
  .gateway.trustedProxies = ((.gateway.trustedProxies // []) + $p | unique) | del(.hooks.maxBodyBytes)' "$T/f.json")"
check "proxies merged" "$(jq -c '.gateway.trustedProxies' <<<"$out")" '["10.9.9.9","172.19.0.1"]'
check "maxBodyBytes removed" "$(jq -c '.hooks | has("maxBodyBytes")' <<<"$out")" "false"
check "15 no longer writes maxBodyBytes" "$(grep -c '\.hooks\.maxBodyBytes = ' 15-configure-hooks-mappings.sh)" "0"
check "15 no longer adds a hardcoded main" "$(grep -c '\[\$agent, "main"\]' 15-configure-hooks-mappings.sh)" "0"

[ "$fails" -eq 0 ] && echo "ALL PASS" || { echo "$fails FAILED"; exit 1; }
