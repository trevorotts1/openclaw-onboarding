#!/usr/bin/env bash
# bash 3.2 re-exec guard. macOS ships bash 3.2 as /bin/bash, and this script
# uses bash-4 constructs. Hand off to a real bash >= 4 when one is installed
# rather than failing halfway through with a syntax error.
if [ "${BASH_VERSINFO[0]:-0}" -lt 4 ] && [ -z "${_OC_BASH_REEXEC:-}" ]; then
  for _b in /opt/homebrew/bin/bash /usr/local/bin/bash; do
    [ -x "$_b" ] && _OC_BASH_REEXEC=1 exec "$_b" "$0" "$@"
  done
  echo "FATAL: bash >= 4 required (macOS ships 3.2): brew install bash" >&2; exit 3
fi
# provision-council-access.sh <cc-host>|--all [--apply] [--json]
#
# Council of Wise Elders (skill 77) - OPERATOR-SIDE per-box chamber hostname.
# Gives a client box an authenticated web address for the Roast Room:
#
#     <slug>.zerohumanworkforce.com          (Command Center, :4000)
#  -> <slug>-council.zerohumanworkforce.com  (Council chamber, 127.0.0.1:8787)
#
# The new hostname rides the box's ONE existing cloudflared tunnel and gets its
# own self-hosted Access app that copies the Command Center app's allow rules,
# so the same people (client emails + operator) can open it and nobody else.
# A box holds no Cloudflare API token, so this runs from the operator side only.
#
# ORDER (per host). Nothing is routed or published before the login exists:
#   a. tunnel id from the CC host's CNAME            (none -> NOT_PROVISIONED)
#   b. the CC host's Access app + allow rules        (none -> NOT_PROVISIONED)
#   c. the CC tunnel is healthy (GET cfd_tunnel/<id>) (not healthy -> TUNNEL_DOWN)
#      remote-managed CC tunnel: the CC rule's origin is loopback (else ORIGIN_NOT_LOOPBACK)
#        and the tunnel has an active connector     (none  -> CONNECTOR_DOWN)
#      local-managed CC tunnel: the Council rides a DEDICATED remote-managed tunnel
#        named council-<slug> (or the COUNCIL_TUNNEL_OVERRIDES name), created or reused
#        (that tunnel local-managed -> PENDING_LOCAL_TUNNEL)
#      council CNAME already points elsewhere        (-> CONFLICT)
#   d. create/reuse Access app 'Council - <slug>', read it back, diff the rules
#      against the CC app (mismatch -> FAILED before any routing)
#   e. dedicated path only: create the council tunnel (config_src=cloudflare)
#   f. merge the ingress rule (GET -> merge -> PUT, CC rule asserted unchanged)
#   g. proxied CNAME -> <tunnel-id>.cfargotunnel.com, only once the tunnel the
#      Council rides has an active connection read in THIS run (remote path: the
#      health + connector reads in c; dedicated path: GET council tunnel connections).
#      Cloudflare's login page answers 302 at the edge even when the tunnel behind
#      it is down, and a box announces its link on that 302, so no record may exist
#      before the connector does.
#      dedicated path, no connection yet: NO DNS write -> CONNECTOR_PENDING; the
#        first run that sees the connector creates the record -> PROVISIONED
#      dedicated path, record exists but the connector is gone -> CONNECTOR_DOWN,
#        zero writes, nothing deleted
#   h. dedicated path only: save the tunnel's connector token (GET .../token) to
#      COUNCIL_TUNNEL_TOKEN_DIR/<tunnel-name>.token, mode 600, never printed
#   i. edge gate (skipped while the DNS record is held back): GET the host, no
#      redirects; it must 302 to *.cloudflareaccess.com.
#      Fail -> roll back what THIS run created, print FAILED.
# Every refusal (NOT_PROVISIONED, TUNNEL_DOWN, ORIGIN_NOT_LOOPBACK, CONNECTOR_DOWN,
# PENDING_LOCAL_TUNNEL, CONFLICT) sends zero writes.
#
# TUNNEL_DOWN: the CC tunnel's status is not "healthy" (down, inactive, degraded).
# A link published now would pass the Access login and then 502, so nothing is
# written; retried every run. ORIGIN_NOT_LOOPBACK: the CC rule's origin is not
# localhost/127.x/[::1] (e.g. a docker bridge IP), so the connector runs outside
# the box's loopback and cannot reach the Council on 127.0.0.1:8787.
#
# --all classifies by SERVICE, the hostname's own ingress rule (path-scoped rules
# do not hide the host's path-less rule): ssh:// (rescue), anything not on :4000,
# or no rule at all is SKIPPED_NOT_CC (exit 0, named in the output). Names marking
# a gateway dashboard / rescue / webhook / n8n host (*-openclawdashboard, rescue-*,
# *-gw, *webhook*, n8n-*, *-n8n) are skipped too, which is the only check possible
# for a host on a local-managed tunnel. A <x>-openclawdashboard-council host is
# never created.
#
# CONNECTOR_DOWN means the tunnel has no active cloudflared connection right now
# (GET .../cfd_tunnel/<id>/connections is empty). It is a retryable not-ready
# state, exit 0, zero writes: a 302 from Cloudflare Access proves only that the
# edge answers, not that the client's connector and Council service are up. The
# check cannot see the Council service itself, only the tunnel connector.
# An already provisioned host makes zero writes and prints ALREADY_PROVISIONED.
#
# Dry-run is the default and sends GET requests only. --apply is the only way a
# write leaves this script. The ingress path is a sibling HOSTNAME, never a path
# on the Command Center host (cc_ingress_merge drops same-hostname rules and the
# Command Center owns /council). The service is http://127.0.0.1:8787, never
# localhost: it binds IPv4 loopback only.
#
# ENV (token and account id come from the environment only, never printed):
#   CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID   required (exit 3 when missing)
#   CF_API_BASE                     default https://api.cloudflare.com/client/v4
#   COUNCIL_ZONE_NAME               default zerohumanworkforce.com (zone resolved BY NAME;
#                                   CLOUDFLARE_ZONE_ID points at the wrong zone and is ignored)
#   COUNCIL_ACCESS_EXCLUDE          --all: comma list of hosts to skip (default: the
#                                   operator council host and the test tenants
#                                   council, acme-dental-c436, smoke, probe .<zone>)
#   COUNCIL_TUNNEL_OVERRIDES        slug=tunnel-name list for the dedicated path
#                                   (default trevor=council-desktop; set empty to disable)
#   COUNCIL_TUNNEL_TOKEN_DIR        connector token store, mode 700 dir / 600 files
#                                   (default $HOME/.openclaw/secrets/council-tunnels)
#   COUNCIL_EDGE_URL_TEMPLATE       default https://%s/   (%s = council host)
#   COUNCIL_EDGE_TRIES / COUNCIL_EDGE_SLEEP   edge gate retries (default 5 / 4s)
#   COUNCIL_EDGE_RESOLVE            auth (default): every edge gate try asks the zone's
#                                   AUTHORITATIVE nameservers (zone name_servers from the
#                                   API, else dig NS) for the host's A/AAAA and pins curl
#                                   with --resolve, so a recursive resolver's cached "no
#                                   such name" (zone negative TTL) from a lookup before the
#                                   record existed cannot fail the gate; https://<host>/
#                                   URLs only; no dig or no answer -> plain curl.
#                                   system: plain curl through the system resolver
#
# OUTPUT: one line per host: COUNCIL_ACCESS: <cc-host> <STATUS> [detail]
#   STATUS = PROVISIONED | ALREADY_PROVISIONED | CONNECTOR_PENDING | TUNNEL_DOWN |
#            ORIGIN_NOT_LOOPBACK | PENDING_LOCAL_TUNNEL | CONNECTOR_DOWN |
#            NOT_PROVISIONED | SKIPPED_NOT_CC | CONFLICT | FAILED |
#            PLANNED (dry-run, writes needed)
# EXIT: 0 unless a host is FAILED or CONFLICT (1); 2 usage; 3 missing env/tool; 4 zone.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
. "$HERE/../../shared-utils/cc-tunnel-ingress.sh"

usage() { sed -n '/^# provision-council-access.sh/,/^set -uo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//' >&2; }

APPLY=0; JSON=0; TARGET=""
while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1; shift ;;
    --json)  JSON=1; shift ;;
    --all)   TARGET="--all"; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "Unknown flag: $1" >&2; usage; exit 2 ;;
    *)  [ -z "$TARGET" ] || { echo "only one host (or --all)" >&2; exit 2; }; TARGET="$1"; shift ;;
  esac
done
[ -n "$TARGET" ] || { usage; exit 2; }

for _t in curl jq; do command -v "$_t" >/dev/null 2>&1 || { echo "missing dependency: $_t" >&2; exit 3; }; done
if [ -z "${CLOUDFLARE_API_TOKEN:-}" ] || [ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]; then
  echo "REFUSED: CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID must both be set in the environment (operator side only)." >&2
  exit 3
fi
unset CLOUDFLARE_ZONE_ID 2>/dev/null || true   # known trap: points at the wrong zone

API="${CF_API_BASE:-https://api.cloudflare.com/client/v4}"
ACCT="$CLOUDFLARE_ACCOUNT_ID"
ZONE_NAME="${COUNCIL_ZONE_NAME:-zerohumanworkforce.com}"
EXCLUDE="${COUNCIL_ACCESS_EXCLUDE:-council.$ZONE_NAME,acme-dental-c436.$ZONE_NAME,smoke.$ZONE_NAME,probe.$ZONE_NAME}"
TUNNEL_OVERRIDES="${COUNCIL_TUNNEL_OVERRIDES-trevor=council-desktop}"
TOKEN_DIR="${COUNCIL_TUNNEL_TOKEN_DIR:-$HOME/.openclaw/secrets/council-tunnels}"
EDGE_TPL="${COUNCIL_EDGE_URL_TEMPLATE:-https://%s/}"
EDGE_TRIES="${COUNCIL_EDGE_TRIES:-5}"
EDGE_SLEEP="${COUNCIL_EDGE_SLEEP:-4}"
EDGE_RESOLVE="${COUNCIL_EDGE_RESOLVE:-auth}"
case "$EDGE_RESOLVE" in auth|system) ;; *) echo "COUNCIL_EDGE_RESOLVE must be auth or system" >&2; exit 2 ;; esac
COUNCIL_SERVICE="http://127.0.0.1:8787"

# The token reaches curl only through a mode-600 config file that is removed on
# exit. It is never on a command line, in stdout/stderr, or left in $TMPDIR.
umask 077
CURL_CFG="$(mktemp "${TMPDIR:-/tmp}/council-access-curl.XXXXXX")" || { echo "cannot create temp file" >&2; exit 3; }
trap 'rm -f "$CURL_CFG"' EXIT
trap 'exit 130' INT TERM HUP
printf 'header = "Authorization: Bearer %s"\n' "$CLOUDFLARE_API_TOKEN" > "$CURL_CFG"

# cf METHOD PATH [JSON]  -> response body on stdout (synthetic failure body if none)
cf() {
  local m="$1" p="$2" d="${3:-}" out
  if [ -n "$d" ]; then
    out="$(curl -sS --max-time 30 -K "$CURL_CFG" -X "$m" -H 'Content-Type: application/json' --data "$d" "$API$p" 2>/dev/null)" || out=""
  else
    out="$(curl -sS --max-time 30 -K "$CURL_CFG" -X "$m" "$API$p" 2>/dev/null)" || out=""
  fi
  [ -n "$out" ] || out='{"success":false,"errors":[{"message":"no response from the API"}]}'
  printf '%s' "$out"
}
ok_of()  { printf '%s' "$1" | jq -r '.success // false' 2>/dev/null; }
err_of() { printf '%s' "$1" | jq -c '[.errors[]?.message // empty]' 2>/dev/null || printf '[unparseable response]'; }

# cf_all PATH_WITH_QUERY -> every result item of a paginated list, as a JSON array
cf_all() {
  local p="$1" pg=1 acc="[]" r n
  while [ "$pg" -le 50 ]; do
    r="$(cf GET "${p}&per_page=100&page=${pg}")"
    [ "$(ok_of "$r")" = "true" ] || { printf 'ERR'; return 1; }
    acc="$(jq -cn --argjson a "$acc" --argjson b "$(printf '%s' "$r" | jq -c '.result // []')" '$a + $b')"
    n="$(printf '%s' "$r" | jq -r '.result_info.total_pages // 1')"
    [ "$pg" -lt "$n" ] || break
    pg=$((pg + 1))
  done
  printf '%s' "$acc"
}

# ---- per-host report plumbing ------------------------------------------------
RESULTS="[]"; ANY_BAD=0
say() { [ "$JSON" = "1" ] || printf '%s\n' "$*"; }
PLAN=()
step() { PLAN+=("$*"); say "  $*"; }

# w METHOD PATH [JSON]: a write; response lands in $WRESP (not a subshell, so the
# step log survives). Dry-run records the plan and sends nothing.
WRESP=""
w() {
  if [ "$APPLY" != "1" ]; then
    step "[plan] $1 $2"; WRESP='{"success":true,"result":{"id":"dry-run"}}'; return 0
  fi
  step "[write] $1 $2"
  WRESP="$(cf "$@")"
}

canon_rules() {  # policies JSON -> canonical allow rules {include,exclude,require}
  jq -c '[.result[]? | select(.decision == "allow")] as $p
         | {include: ([$p[].include[]?] | map(tojson) | unique),
            exclude: ([$p[].exclude[]?] | map(tojson) | unique),
            require: ([$p[].require[]?] | map(tojson) | unique)}' <<<"$1"
}

finish() {  # STATUS DETAIL
  local status="$1" detail="${2:-}"
  case "$status" in FAILED|CONFLICT) ANY_BAD=1 ;; esac
  say "COUNCIL_ACCESS: $CC_HOST $status${detail:+ $detail}"
  RESULTS="$(jq -c --arg cc "$CC_HOST" --arg ch "$COUNCIL_HOST" --arg s "$status" --arg d "$detail" \
    --argjson plan "$(printf '%s\n' "${PLAN[@]+"${PLAN[@]}"}" | jq -R . | jq -sc 'map(select(length>0))')" \
    '. + [{cc_host:$cc, council_host:$ch, status:$s, detail:$d, steps:$plan}]' <<<"$RESULTS")"
}

# edge_ns: the zone's authoritative nameservers into EDGE_NS (one per line, cached for
# the run): name_servers of the zone object from the API lookup, else `dig NS <zone>`.
EDGE_NS=""
edge_ns() {
  [ -z "$EDGE_NS" ] || return 0
  EDGE_NS="$(jq -r --arg n "$ZONE_NAME" '[.result[]? | select(.name == $n)][0].name_servers[]? // empty' <<<"$zr" 2>/dev/null)"
  [ -n "$EDGE_NS" ] || EDGE_NS="$(dig +short +time=3 +tries=1 NS "$ZONE_NAME" 2>/dev/null)"
  EDGE_NS="$(printf '%s\n' "$EDGE_NS" | sed 's/\.$//' | grep -E '^[A-Za-z0-9][A-Za-z0-9.-]*$')"
}

# edge_addrs HOST -> 0 and EDGE_ADDRS="v4,...,[v6],..." (curl --resolve form) from the first
# authoritative nameserver that answers; EDGE_FROM names it. 1 when dig or every server
# gives nothing. Authoritative servers keep no negative cache, so a new record shows at once.
edge_addrs() {
  local ns a6
  EDGE_ADDRS=""; EDGE_FROM=""
  command -v dig >/dev/null 2>&1 || return 1
  edge_ns
  for ns in $EDGE_NS; do
    EDGE_ADDRS="$(dig +short +norecurse +time=3 +tries=1 "@$ns" "$1" A 2>/dev/null | grep -E '^[0-9]{1,3}(\.[0-9]{1,3}){3}$')"
    a6="$(dig +short +norecurse +time=3 +tries=1 "@$ns" "$1" AAAA 2>/dev/null | grep -Ei '^[0-9a-f]*:[0-9a-f:]*$' | sed 's/.*/[&]/')"
    EDGE_ADDRS="$(printf '%s\n%s\n' "$EDGE_ADDRS" "$a6" | grep . | tr '\n' ',' | sed 's/,$//')"
    [ -z "$EDGE_ADDRS" ] || { EDGE_FROM="$ns"; return 0; }
  done
  return 1
}

edge_gate() {  # COUNCIL_HOST -> 0 when the host answers 302 to *.cloudflareaccess.com
  local url="${EDGE_TPL//%s/$1}" i hdrs code loc pin
  for ((i = 1; i <= EDGE_TRIES; i++)); do
    pin=()
    # Asked again on every try. Only for a plain https://<host>/ URL (the default template).
    if [ "$EDGE_RESOLVE" = "auth" ] && case "$url" in "https://$1"|"https://$1/"*) true ;; *) false ;; esac; then
      if edge_addrs "$1"; then
        pin=(--resolve "$1:443:$EDGE_ADDRS")
        step "[info] edge gate try $i: $1 -> $EDGE_ADDRS (authoritative $EDGE_FROM)"
      else
        step "[info] edge gate try $i: no authoritative answer for $1 (dig or nameservers unavailable); using the system resolver"
      fi
    fi
    hdrs="$(curl -sS -o /dev/null -D - --max-time 15 ${pin[@]+"${pin[@]}"} "$url" 2>/dev/null | tr -d '\r')" || hdrs=""
    code="$(printf '%s\n' "$hdrs" | sed -n '1s#^HTTP/[0-9.]* \([0-9]*\).*#\1#p')"
    loc="$(printf '%s\n' "$hdrs" | sed -n 's/^[Ll]ocation: *//p' | head -n1)"
    if [ "$code" = "302" ] && printf '%s' "$loc" | grep -Eiq '^https://[^/]*\.cloudflareaccess\.com(/|$)'; then return 0; fi
    [ "$i" -lt "$EDGE_TRIES" ] && sleep "$EDGE_SLEEP"
  done
  EDGE_WHY="HTTP ${code:-none}, Location ${loc:-none}${pin[0]+, pinned to $EDGE_ADDRS}"
  return 1
}

# not_cc_name HOST: the name marks a gateway dashboard / rescue / webhook / n8n host
not_cc_name() {
  case "${1%%.*}" in rescue-*|*-gw|*webhook*|*-openclawdashboard|n8n-*|*-n8n) return 0 ;; esac
  return 1
}

# council_tunnel_name SLUG -> COUNCIL_TUNNEL_OVERRIDES entry for SLUG, else council-<slug>
council_tunnel_name() {
  local kv
  for kv in ${TUNNEL_OVERRIDES//,/ }; do
    [ "${kv%%=*}" = "$1" ] && [ -n "${kv#*=}" ] && { printf '%s' "${kv#*=}"; return; }
  done
  printf 'council-%s' "$1"
}

# active_conns TUNNEL_ID -> number of active connections ("ERR" when unreadable)
active_conns() {
  local r; r="$(cf GET "/accounts/${ACCT}/cfd_tunnel/${1}/connections")"
  [ "$(ok_of "$r")" = "true" ] || { printf 'ERR'; return; }
  jq -r '[.result[]?.conns[]? | select((.is_pending_reconnect // false) | not)] | length' <<<"$r" 2>/dev/null || printf 'ERR'
}

# ---- one Command Center host ---------------------------------------------------
provision_host() {
  local cc="$1"
  CC_HOST="$cc"; PLAN=()
  local slug="${cc%%.*}" rest="${cc#*.}"
  COUNCIL_HOST="${slug}-council.${rest}"
  say "== $cc -> $COUNCIL_HOST ($([ "$APPLY" = 1 ] && echo apply || echo dry-run))"
  # A DNS label holds at most 63 characters and "<slug>-council" adds 8, so the slug may be at most 55.
  [ "${#slug}" -le 55 ] || { finish FAILED "slug is ${#slug} characters; ${slug}-council would exceed the 63-character DNS label limit"; return; }

  # a. tunnel id from the CC CNAME
  local r tunnel_id
  r="$(cf GET "/zones/${ZONE_ID}/dns_records?type=CNAME&name=${cc}")"
  [ "$(ok_of "$r")" = "true" ] || { finish FAILED "could not read DNS for $cc: $(err_of "$r")"; return; }
  tunnel_id="$(jq -r '.result[0].content // empty | select(endswith(".cfargotunnel.com")) | sub("\\.cfargotunnel\\.com$"; "")' <<<"$r")"
  [ -n "$tunnel_id" ] || { finish NOT_PROVISIONED "$cc has no CNAME to a tunnel (no Command Center tunnel to ride)"; return; }

  # b. the CC app and its allow rules
  local apps cc_app cc_app_id session cc_pol cc_rules
  apps="$(cf_all "/accounts/${ACCT}/access/apps?x=1")" || { finish FAILED "could not list Access apps"; return; }
  cc_app="$(jq -c --arg h "$cc" '[.[] | select(.domain == $h or ((.self_hosted_domains // []) | index($h)))][0] // empty' <<<"$apps")"
  [ -n "$cc_app" ] || { finish NOT_PROVISIONED "$cc has no Access app; a host is never published without a login"; return; }
  cc_app_id="$(jq -r '.id' <<<"$cc_app")"
  session="$(jq -r '.session_duration // "24h"' <<<"$cc_app")"
  cc_pol="$(cf GET "/accounts/${ACCT}/access/apps/${cc_app_id}/policies")"
  [ "$(ok_of "$cc_pol")" = "true" ] || { finish FAILED "could not read the Command Center app policies: $(err_of "$cc_pol")"; return; }
  cc_rules="$(canon_rules "$cc_pol")"
  if [ "$(jq '.include | length' <<<"$cc_rules")" = "0" ]; then
    finish NOT_PROVISIONED "the Command Center app for $cc has no allow rules"; return
  fi
  if jq -e '.include | map(fromjson) | any(has("everyone") or has("any_valid_service_token"))' <<<"$cc_rules" >/dev/null; then
    finish NOT_PROVISIONED "the Command Center app for $cc allows everyone; not copying an open policy"; return
  fi

  # c. the CC tunnel: healthy, then which tunnel the Council rides (all read-only)
  local th tstatus cfg src
  th="$(cf GET "/accounts/${ACCT}/cfd_tunnel/${tunnel_id}")"
  [ "$(ok_of "$th")" = "true" ] || { finish FAILED "could not read tunnel $tunnel_id: $(err_of "$th")"; return; }
  tstatus="$(jq -r '.result.status // "unknown"' <<<"$th")"
  if [ "$tstatus" != "healthy" ]; then
    finish TUNNEL_DOWN "tunnel $tunnel_id for $cc is $tstatus, not healthy; a link now would pass the login and then fail. No Cloudflare change made; retried next run"; return
  fi
  cfg="$(cf GET "/accounts/${ACCT}/cfd_tunnel/${tunnel_id}/configurations")"
  [ "$(ok_of "$cfg")" = "true" ] || { finish FAILED "could not read tunnel configuration for $tunnel_id: $(err_of "$cfg")"; return; }
  src="$(jq -r '.result.source // "cloudflare"' <<<"$cfg")"

  local ride_tid ride_cfg ride_name="" ride_new=0 token_file="" dedicated=0
  if [ "$src" = "cloudflare" ]; then
    cc_ingress_assert_cc_port "$cfg" "$cc" 1 || { finish FAILED "tunnel $tunnel_id has no valid Command Center rule for $cc; refusing to write"; return; }
    local cc_svc origin
    cc_svc="$(cc_ingress_service_for_host "$cfg" "$cc")"
    origin="$(printf '%s' "$cc_svc" | sed -n -E 's#^[a-z]+://(\[[^]]*\]|[^]/:[]+).*#\1#p')"
    case "$origin" in
      localhost|127.*|"[::1]") ;;
      *) finish ORIGIN_NOT_LOOPBACK "the Command Center rule for $cc points at $cc_svc, not loopback; that connector cannot reach the Council on $COUNCIL_SERVICE (it binds the box's IPv4 loopback only). No Cloudflare change made"; return ;;
    esac
    # read-only: does the tunnel have a live connector? (Access answering 302 proves only the edge.)
    local nconn; nconn="$(active_conns "$tunnel_id")"
    [ "$nconn" != "ERR" ] || { finish FAILED "could not read tunnel connections for $tunnel_id"; return; }
    if [ "$nconn" = "0" ]; then
      finish CONNECTOR_DOWN "tunnel $tunnel_id for $cc has no active connector; not ready, retry later. No Cloudflare change made"; return
    fi
    ride_tid="$tunnel_id"; ride_cfg="$cfg"
  else
    # The CC tunnel's ingress lives in a config.yml on whichever machine runs it, so
    # the API cannot add a rule there. The Council gets its own remote-managed tunnel.
    dedicated=1
    ride_name="$(council_tunnel_name "$slug")"
    token_file="$TOKEN_DIR/${ride_name}.token"
    say "  Tunnel $tunnel_id (serving $cc) is locally managed (source=$src); the Council rides its own remote-managed tunnel $ride_name."
    r="$(cf GET "/accounts/${ACCT}/cfd_tunnel?name=${ride_name}&is_deleted=false")"
    [ "$(ok_of "$r")" = "true" ] || { finish FAILED "could not look up tunnel $ride_name: $(err_of "$r")"; return; }
    ride_tid="$(jq -r --arg n "$ride_name" '[.result[]? | select(.name == $n and (.deleted_at == null))][0].id // empty' <<<"$r")"
    if [ -n "$ride_tid" ]; then
      ride_cfg="$(cf GET "/accounts/${ACCT}/cfd_tunnel/${ride_tid}/configurations")"
      [ "$(ok_of "$ride_cfg")" = "true" ] || { finish FAILED "could not read tunnel configuration for $ride_name ($ride_tid): $(err_of "$ride_cfg")"; return; }
      src="$(jq -r '.result.source // "cloudflare"' <<<"$ride_cfg")"
      if [ "$src" != "cloudflare" ]; then
        finish PENDING_LOCAL_TUNNEL "the Council tunnel $ride_name ($ride_tid) for $cc is locally managed (source=$src); migrate it to remote-managed (Cloudflare Zero Trust, Networks, Tunnels, Configure), then re-run. No Cloudflare change made"
        return
      fi
      step "[ok] Council tunnel $ride_name exists ($ride_tid)"
    else
      ride_new=1; ride_cfg='{"result":{"config":{}}}'
    fi
  fi

  # council CNAME: an existing record must already point at the tunnel the Council rides
  local expected="${ride_tid:-new}.cfargotunnel.com" rec_id rec_type rec_content
  r="$(cf GET "/zones/${ZONE_ID}/dns_records?name=${COUNCIL_HOST}")"
  [ "$(ok_of "$r")" = "true" ] || { finish FAILED "could not read DNS for $COUNCIL_HOST: $(err_of "$r")"; return; }
  rec_id="$(jq -r '.result[0].id // empty' <<<"$r")"
  rec_type="$(jq -r '.result[0].type // empty' <<<"$r")"
  rec_content="$(jq -r '.result[0].content // empty' <<<"$r")"
  if [ -n "$rec_id" ] && { [ "$ride_new" = "1" ] || [ "$rec_type" != "CNAME" ] || [ "$rec_content" != "$expected" ]; }; then
    finish CONFLICT "$COUNCIL_HOST already exists as $rec_type -> $rec_content, not $([ "$ride_new" = 1 ] && echo "the new tunnel $ride_name" || echo "$expected"); nothing changed"; return
  fi

  # dedicated path: read the council tunnel's connector BEFORE any write. A brand-new
  # tunnel has none. A published record with no connector is a dead link: report, never delete.
  local cconn=0
  if [ "$dedicated" = "1" ] && [ "$ride_new" = "0" ]; then
    cconn="$(active_conns "$ride_tid")"
    [ "$cconn" != "ERR" ] || { finish FAILED "could not read tunnel connections for $ride_name ($ride_tid); no Cloudflare change made"; return; }
    if [ -n "$rec_id" ] && [ "$cconn" = "0" ]; then
      finish CONNECTOR_DOWN "$COUNCIL_HOST has its DNS record but tunnel $ride_name ($ride_tid) has no active connection; the link would open the login page and then fail. No Cloudflare change made, nothing deleted; the box must restart its connector. Retried next run"; return
    fi
  fi

  # d. Access app first
  local app app_id app_pol created_app=0 body
  app="$(jq -c --arg h "$COUNCIL_HOST" '[.[] | select(.domain == $h or ((.self_hosted_domains // []) | index($h)))][0] // empty' <<<"$apps")"
  if [ -n "$app" ]; then
    app_id="$(jq -r '.id' <<<"$app")"
    step "[ok] Access app 'Council - $slug' exists ($app_id)"
  else
    body="$(jq -cn --arg n "Council - $slug" --arg d "$COUNCIL_HOST" --arg s "$session" --argjson pols "$cc_pol" '
      [$pols.result[] | select(.decision == "allow")] as $allow
      | {name:$n, domain:$d, type:"self_hosted", session_duration:$s, app_launcher_visible:false,
         policies: ($allow | to_entries | map(
           if (.value.reusable // false) then {id:.value.id, precedence:(.key + 1)}
           else {name:("Council allow-list - " + $d), decision:"allow", precedence:(.key + 1),
                 include:(.value.include // [])}
                + (if ((.value.exclude // []) | length) > 0 then {exclude:.value.exclude} else {} end)
                + (if ((.value.require // []) | length) > 0 then {require:.value.require} else {} end) end))}')"
    w POST "/accounts/${ACCT}/access/apps" "$body"; r="$WRESP"
    [ "$(ok_of "$r")" = "true" ] || { finish FAILED "Access app create failed: $(err_of "$r"); no routing touched"; return; }
    app_id="$(jq -r '.result.id // empty' <<<"$r")"
    created_app=1
  fi
  if [ "$APPLY" = "1" ] || [ "$created_app" = "0" ]; then
    app_pol="$(cf GET "/accounts/${ACCT}/access/apps/${app_id}/policies")"
    [ "$(ok_of "$app_pol")" = "true" ] || { finish FAILED "could not read back the Council Access app: $(err_of "$app_pol"); no routing touched"; return; }
    if [ "$(canon_rules "$app_pol")" != "$cc_rules" ]; then
      finish FAILED "Access rules on $COUNCIL_HOST differ from the Command Center app; no routing touched. Fix the app in the Access dashboard and re-run"; return
    fi
    step "[ok] Council Access rules equal the Command Center rules"
  fi

  # e. dedicated path: create the Council tunnel (remote-managed)
  local created_tunnel=0
  if [ "$ride_new" = "1" ]; then
    [ "$APPLY" = "1" ] || step "[plan] would create tunnel $ride_name (remote-managed)"
    w POST "/accounts/${ACCT}/cfd_tunnel" "$(jq -cn --arg n "$ride_name" '{name:$n, config_src:"cloudflare"}')"; r="$WRESP"
    [ "$(ok_of "$r")" = "true" ] || { finish FAILED "tunnel $ride_name create failed: $(err_of "$r"); no routing touched (Access app kept)"; return; }
    ride_tid="$(jq -r '.result.id // empty' <<<"$r")"
    [ -n "$ride_tid" ] || { finish FAILED "tunnel $ride_name create returned no id; no routing touched (Access app kept)"; return; }
    [ "$APPLY" = "1" ] || ride_tid="<new $ride_name id>"
    expected="${ride_tid}.cfargotunnel.com"
    created_tunnel=1
  fi

  # f. ingress: GET -> merge -> PUT, CC rule asserted unchanged when it shares the tunnel
  local prior_svc ing_changed=0 new_body
  prior_svc="$(cc_ingress_service_for_host "$ride_cfg" "$COUNCIL_HOST")"
  if [ "$prior_svc" = "$COUNCIL_SERVICE" ]; then
    step "[ok] ingress rule $COUNCIL_HOST -> $COUNCIL_SERVICE present"
  else
    new_body="$(cc_ingress_merge "$ride_cfg" "$COUNCIL_HOST" "$COUNCIL_SERVICE")" || { finish FAILED "ingress merge failed"; return; }
    if [ "$dedicated" = "0" ]; then
      cc_ingress_assert_cc_port "$new_body" "$cc" 1 \
        && [ "$(cc_ingress_service_for_host "$new_body" "$cc")" = "$(cc_ingress_service_for_host "$cfg" "$cc")" ] \
        || { finish FAILED "merge would change the Command Center ingress rule; nothing written"; return; }
    fi
    w PUT "/accounts/${ACCT}/cfd_tunnel/${ride_tid}/configurations" "$new_body"; r="$WRESP"
    [ "$(ok_of "$r")" = "true" ] || { finish FAILED "ingress PUT failed: $(err_of "$r")"; return; }
    ing_changed=1
  fi

  # g. DNS (an existing correct record is reused; none is created before a connector)
  local dns_created=0 new_dns_id="" dns_held=0
  if [ -n "$rec_id" ]; then
    step "[ok] CNAME $COUNCIL_HOST -> $expected present"
  elif [ "$dedicated" = "1" ] && [ "$cconn" = "0" ]; then
    dns_held=1
    step "[hold] no DNS record for $COUNCIL_HOST: tunnel $ride_name has no active connection yet (zero DNS writes; the first run that sees the connector creates it)"
  else
    w POST "/zones/${ZONE_ID}/dns_records" \
      "$(jq -cn --arg n "$COUNCIL_HOST" --arg c "$expected" '{type:"CNAME", name:$n, content:$c, proxied:true, ttl:1}')"; r="$WRESP"
    if [ "$(ok_of "$r")" != "true" ]; then
      rollback "$ride_tid" "$ing_changed" "$prior_svc" "" "DNS create failed: $(err_of "$r")"; return
    fi
    new_dns_id="$(jq -r '.result.id // empty' <<<"$r")"; dns_created=1
  fi

  # h. dedicated path: the connector token for the box, saved operator side, never printed
  if [ -n "$token_file" ] && [ ! -s "$token_file" ]; then
    if [ "$APPLY" != "1" ]; then
      step "[plan] would save the connector token for $ride_name to $token_file (mode 600)"
    else
      local tok
      tok="$(cf GET "/accounts/${ACCT}/cfd_tunnel/${ride_tid}/token")"
      if [ "$(ok_of "$tok")" = "true" ] && tok="$(jq -r '.result // empty | strings' <<<"$tok")" && [ -n "$tok" ] \
        && mkdir -p "$TOKEN_DIR" && chmod 700 "$TOKEN_DIR" \
        && (umask 077; printf '%s\n' "$tok" > "$token_file.tmp") && chmod 600 "$token_file.tmp" && mv "$token_file.tmp" "$token_file"; then
        step "[write] saved the connector token for $ride_name to $token_file (mode 600)"
      else
        rm -f "$token_file.tmp"
        step "[warn] could not fetch or save the connector token for $ride_name; retried next run"
      fi
      tok=""
    fi
  fi

  # i. edge gate (dry-run only runs it when nothing would be written)
  local wrote=$((created_app + created_tunnel + ing_changed + dns_created))
  if [ "$dns_held" = "0" ] && { [ "$APPLY" = "1" ] || [ "$wrote" = "0" ]; }; then
    EDGE_WHY=""
    if edge_gate "$COUNCIL_HOST"; then
      step "[ok] edge gate: $COUNCIL_HOST answers 302 to Cloudflare Access"
    elif [ "$wrote" = "0" ]; then
      finish FAILED "edge gate failed on an existing setup ($EDGE_WHY); this run created nothing, so nothing was rolled back"; return
    else
      rollback "$ride_tid" "$ing_changed" "$prior_svc" "$new_dns_id" "edge gate failed ($EDGE_WHY)"; return
    fi
  fi

  # dedicated path: the box must run the tunnel's connector before the record exists
  if [ "$dns_held" = "1" ]; then
    if [ "$APPLY" = "1" ] || [ "$wrote" = "0" ]; then
      local tok_note="token saved operator side at $token_file"
      [ -s "$token_file" ] || tok_note="token NOT saved yet at $token_file; $([ "$APPLY" = 1 ] && echo "retried next run" || echo "--apply saves it")"
      finish CONNECTOR_PENDING "$COUNCIL_HOST rides tunnel $ride_name ($ride_tid), which has no active connection yet; no DNS record created (zero DNS writes), so no link can open. The box must run its connector ($tok_note); the next run that sees it creates the record"
    else
      finish PLANNED "dry-run: pass --apply to make the writes listed above; no DNS write until tunnel $ride_name has an active connection, so apply ends CONNECTOR_PENDING"
    fi
    return
  fi

  if [ "$wrote" = "0" ]; then finish ALREADY_PROVISIONED
  elif [ "$APPLY" = "1" ]; then finish PROVISIONED
  else finish PLANNED "dry-run: pass --apply to make the writes listed above"; fi
}

# rollback TUNNEL ING_CHANGED PRIOR_SVC NEW_DNS_ID WHY: undo what THIS run created.
# The Access app and a newly created Council tunnel are kept (harmless: a login, an unrouted tunnel).
rollback() {
  local tid="$1" ing="$2" prior="$3" dns="$4" why="$5" bad=0 cur body r
  if [ "$ing" = "1" ]; then
    cur="$(cf GET "/accounts/${ACCT}/cfd_tunnel/${tid}/configurations")"
    if [ -n "$prior" ]; then body="$(cc_ingress_merge "$cur" "$COUNCIL_HOST" "$prior")"
    else
      body="$(jq -c --arg h "$COUNCIL_HOST" '(.result.config // {}) as $c
        | {config: ($c | .ingress = (($c.ingress // []) | map(select(has("hostname") and .hostname != $h))) + [{service:"http_status:404"}])}' <<<"$cur")"
    fi
    w PUT "/accounts/${ACCT}/cfd_tunnel/${tid}/configurations" "$body"; r="$WRESP"
    [ "$(ok_of "$r")" = "true" ] || bad=1
  fi
  if [ -n "$dns" ]; then
    w DELETE "/zones/${ZONE_ID}/dns_records/${dns}"; r="$WRESP"
    [ "$(ok_of "$r")" = "true" ] || bad=1
  fi
  if [ "$bad" = "1" ]; then finish FAILED "$why; ROLLBACK INCOMPLETE, check the ingress rule and CNAME for $COUNCIL_HOST by hand"
  else finish FAILED "$why; rolled back what this run created (Access app and any new Council tunnel kept)"; fi
}

# ---- zone, then hosts -------------------------------------------------------------
zr="$(cf GET "/zones?name=${ZONE_NAME}")"
ZONE_ID="$(jq -r --arg n "$ZONE_NAME" '[.result[]? | select(.name == $n)][0].id // empty' <<<"$zr")"
[ -n "$ZONE_ID" ] || { echo "REFUSED: zone '$ZONE_NAME' not found by name: $(err_of "$zr")" >&2; exit 4; }

HOSTS=()
valid_host() { [[ "$1" == *".$ZONE_NAME" ]] && [[ "${1%".$ZONE_NAME"}" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]]; }
if [ "$TARGET" = "--all" ]; then
  recs="$(cf_all "/zones/${ZONE_ID}/dns_records?type=CNAME")" || { echo "REFUSED: could not list zone CNAMEs" >&2; exit 4; }
  declare -A CFG_OF
  SKIPPED=()   # "host|reason"
  while read -r n content; do
    [ -n "$n" ] || continue
    valid_host "$n" || continue
    case "$n" in *-hooks.*|*-podcast.*|*-council.*) continue ;; esac
    case ",$EXCLUDE," in *",$n,"*) continue ;; esac
    tid="${content%.cfargotunnel.com}"
    if [ -z "${CFG_OF[$tid]+x}" ]; then CFG_OF[$tid]="$(cf GET "/accounts/${ACCT}/cfd_tunnel/${tid}/configurations")"; fi
    # Classify by SERVICE: the hostname's own ingress rule on a readable remote config.
    # An unreadable config falls through to provision_host to report honestly; a
    # local-managed one cannot show its service, so only the name check applies.
    if [ "$(ok_of "${CFG_OF[$tid]}")" = "true" ] && [ "$(jq -r '.result.source // "cloudflare"' <<<"${CFG_OF[$tid]}")" = "cloudflare" ]; then
      svc="$(cc_ingress_service_for_host "${CFG_OF[$tid]}" "$n")"
      case "$svc" in
        ssh://*) SKIPPED+=("$n|tunnel $tid routes it to $svc (an SSH rescue host), not a Command Center"); continue ;;
      esac
      if [ "$(cc_ingress_port_of "$svc")" != "$CC_INGRESS_PORT" ]; then
        SKIPPED+=("$n|tunnel $tid routes it to ${svc:-no ingress rule}, not a Command Center on :$CC_INGRESS_PORT"); continue
      fi
    fi
    if not_cc_name "$n"; then
      SKIPPED+=("$n|the name marks a gateway dashboard, rescue, webhook or n8n host, not a Command Center"); continue
    fi
    HOSTS+=("$n")
  done < <(jq -r '.[] | select((.content // "") | endswith(".cfargotunnel.com")) | "\(.name) \(.content)"' <<<"$recs" | sort -u)
else
  valid_host "$TARGET" || { echo "host must be <slug>.$ZONE_NAME" >&2; exit 2; }
  case "$TARGET" in *-hooks.*|*-podcast.*|*-council.*) echo "give the Command Center host, not a -hooks/-podcast/-council host" >&2; exit 2 ;; esac
  not_cc_name "$TARGET" && { echo "give the Command Center host, not a gateway dashboard/rescue/webhook/n8n host" >&2; exit 2; }
  HOSTS=("$TARGET")
fi

say "provision-council-access: zone=$ZONE_NAME ($ZONE_ID) hosts=${#HOSTS[@]} mode=$([ "$APPLY" = 1 ] && echo apply || echo dry-run)"
for sk in ${SKIPPED[@]+"${SKIPPED[@]}"}; do CC_HOST="${sk%%|*}"; COUNCIL_HOST=""; PLAN=(); finish SKIPPED_NOT_CC "${sk#*|}"; done
for h in ${HOSTS[@]+"${HOSTS[@]}"}; do provision_host "$h"; done

[ "$JSON" = "1" ] && jq . <<<"$RESULTS"
[ "$ANY_BAD" = "0" ]
