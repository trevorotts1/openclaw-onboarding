#!/usr/bin/env bash
# cc-tunnel-ingress.sh
# ─────────────────────────────────────────────────────────────────────────────
# THE single authoritative source for the Command Center (CC) tunnel-ingress
# port, plus the merge + guard helpers every ingress writer must use.
#
# WHY THIS EXISTS (root cause of "CC public link 502s / CF 1303 no-route"):
#   The fleet runs ONE cloudflared tunnel per box carrying MULTIPLE ingress
#   hostnames on a SINGLE ingress array:
#       <client>.zerohumanworkforce.com         -> http://localhost:4000   (CC dashboard)
#       <client>-hooks.zerohumanworkforce.com   -> http://127.0.0.1:18789  (OpenClaw gateway)
#       <client>-podcast.zerohumanworkforce.com -> http://localhost:4010   (podcast board)
#   Cloudflare's PUT /cfd_tunnel/<id>/configurations REPLACES the whole ingress
#   array. Any writer that PUTs a freshly-built array (a "full-replace") instead
#   of GET->merge->PUT silently DELETES every sibling rule it did not re-list:
#     * If the CC's <client>.zerohumanworkforce.com rule is dropped  -> CF 1303
#       "no route to your origin" for the public dashboard link.
#     * If a rule that CF still routes to that tunnel is re-pointed at :18789
#       (the gateway) or another port -> the CC public link 502s (nothing on
#       that port serves the dashboard). This is the "ingress points at the
#       WRONG localhost port (not the CC's actual port)" symptom.
#   The two known full-replace writers were the Skill-38 gateway tunnel script
#   (13-create-cloudflare-tunnel.sh) and the n8n command-center-register
#   workflow. Skill-58 (podcast) already merges correctly; this lib generalizes
#   that safe pattern and adds a fail-loud guard so a wrong CC port can never be
#   PUT again.
#
# USAGE (source it):
#   source "<repo>/shared-utils/cc-tunnel-ingress.sh"
#   NEW_BODY="$(cc_ingress_merge "$CURRENT_CFG_JSON" "$HOST" "$SERVICE" "$OPTIONAL_PATH")"
#   cc_ingress_assert_cc_port "$NEW_BODY" "<client>.zerohumanworkforce.com" || exit 7
#
# Pure bash + jq. Network-free (the caller does the GET/PUT). bash 3.2-safe.
# ─────────────────────────────────────────────────────────────────────────────

# The CC dashboard's ONE true local port. Uniform fleet-wide (see
# 32-command-center-setup/scripts/run-full-install.sh DASHBOARD_PORT=4000 and
# qc-command-center-setup.sh CC_PORT=4000). Overridable ONLY for tests via env.
: "${CC_INGRESS_PORT:=4000}"
# The CC's authoritative ingress service string. Every writer that touches a CC
# hostname rule MUST use exactly this — never a re-derived or hardcoded value.
CC_INGRESS_SERVICE="http://localhost:${CC_INGRESS_PORT}"
export CC_INGRESS_PORT CC_INGRESS_SERVICE

# cc_ingress_port_of <service-string>  ->  echoes the numeric port (empty if none)
#   "http://localhost:4000" -> 4000 ; "http://127.0.0.1:18789" -> 18789
#   "http_status:404" -> (empty)
cc_ingress_port_of() {
  printf '%s' "${1:-}" | sed -n -E 's#^https?://[^:/]+:([0-9]+).*$#\1#p'
}

# cc_ingress_of <json>  ->  echoes the ingress array as compact JSON.
# Accepts any of: a CF GET response ({result:{config:{ingress:[]}}}), a PUT body
# ({config:{ingress:[]}}), or a bare {ingress:[]}. Echoes "[]" when absent.
cc_ingress_of() {
  printf '%s' "${1:-}" | jq -c '
    (.result.config.ingress // .config.ingress // .ingress // [])' 2>/dev/null \
    || printf '[]'
}

# cc_ingress_service_for_host <json> <host>  ->  echoes the matching service (or empty)
cc_ingress_service_for_host() {
  cc_ingress_of "$1" | jq -r --arg h "$2" \
    'map(select(.hostname? == $h)) | (.[0].service // "")' 2>/dev/null
}

# cc_ingress_merge <current-cfg-json> <host> <service> [path]
#   Produce a PUT body ({config:{ingress:[...]}}) that ADDS/UPDATES the <host>
#   rule while PRESERVING every other host rule already on the tunnel and keeping
#   exactly ONE catch-all (http_status:404) last. This is the anti-clobber core:
#   a writer built on this can never delete the CC's :4000 rule (or any sibling).
#   <current-cfg-json> is the raw CF GET /configurations response.
cc_ingress_merge() {
  local cur="$1" host="$2" svc="$3" path="${4:-}"
  printf '%s' "$cur" | jq \
    --arg host "$host" --arg svc "$svc" --arg path "$path" '
    (.result.config // .config // {}) as $cfg
    | ($cfg.ingress // []) as $ing
    # keep every hostname rule EXCEPT the one we are (re)writing
    | ($ing | map(select(has("hostname") and (.hostname != $host)))) as $hosts
    | {config: ($cfg | .ingress = (
          $hosts
          + [ (if $path != "" then {hostname:$host, service:$svc, path:$path}
                              else {hostname:$host, service:$svc} end) ]
          + [ {service:"http_status:404"} ]
        ))}'
}

# cc_ingress_assert_cc_port <json> <cc-host> [require-present]
#   FAIL LOUDLY (return 1 + stderr) if the CC hostname rule in <json> does not
#   point at the authoritative CC port. Two failure modes, both = a broken public
#   dashboard link:
#     * rule present but service port != CC_INGRESS_PORT  -> would 502 (wrong port)
#     * rule ABSENT and require-present=1                 -> would CF 1303 (no route)
#   Pass require-present=1 when <json> is destined for the tunnel that MUST serve
#   the CC (i.e. a full ingress you are about to PUT for that box). Default 0 lets
#   the guard no-op on tunnels that legitimately do not carry the CC host.
cc_ingress_assert_cc_port() {
  local json="$1" cc_host="$2" require_present="${3:-0}" svc port
  svc="$(cc_ingress_service_for_host "$json" "$cc_host")"
  if [ -z "$svc" ]; then
    if [ "$require_present" = "1" ]; then
      echo "CC-INGRESS-GUARD FAIL: '$cc_host' has NO ingress rule in the config about to be written." >&2
      echo "  -> Cloudflare would return 1303 'no route to your origin' for the CC dashboard." >&2
      echo "  -> A full-replace ingress PUT dropped the CC rule. Use cc_ingress_merge (GET->merge->PUT)." >&2
      return 1
    fi
    return 0
  fi
  port="$(cc_ingress_port_of "$svc")"
  if [ "$port" != "$CC_INGRESS_PORT" ]; then
    echo "CC-INGRESS-GUARD FAIL: '$cc_host' -> '$svc' (port ${port:-none}), expected :${CC_INGRESS_PORT}." >&2
    echo "  -> The CC public link would 502: the tunnel routes it to a port the dashboard does not serve." >&2
    echo "  -> Fix the writer to emit the authoritative CC service '$CC_INGRESS_SERVICE' for the CC host." >&2
    return 1
  fi
  return 0
}
