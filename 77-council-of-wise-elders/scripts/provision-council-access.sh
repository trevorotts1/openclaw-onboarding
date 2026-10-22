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
# own self-hosted Access app that copies the Command Center app's allow rules and
# then follows its email list (SYNCED, step d), so the same people (client emails +
# operator) can open it and nobody else.
# A box holds no Cloudflare API token, so this runs from the operator side only.
#
# ORDER (per host). Nothing is routed or published before the login exists:
#   a. tunnel id from the CC host's CNAME            (none -> NOT_PROVISIONED)
#   b. the CC host's Access app + allow rules        (none -> NOT_PROVISIONED)
#   c. the CC tunnel exists (HTTP 404 on the tunnel, or a deleted tunnel -> SKIPPED_ORPHAN:
#      an orphan record, zero writes, exit 0; a 5xx, timeout or auth error stays FAILED)
#      and is healthy (GET cfd_tunnel/<id>) (not healthy -> TUNNEL_DOWN); a healthy tunnel
#      whose configuration cannot be read (404 included) is FAILED, never an orphan
#      remote-managed CC tunnel: the CC rule's origin is loopback (else ORIGIN_NOT_LOOPBACK)
#        and the tunnel has an active connector     (none  -> CONNECTOR_DOWN)
#        CONTAINER-HOST SHAPE (a remote-managed CC tunnel whose CC rule origin is a
#        private bridge address: 10.x, 172.16-31.x, 192.168.x or host.docker.internal,
#        on the CC port): the Council takes the dedicated-tunnel path
#        below unchanged (tunnel council-<slug>, route <slug>-council ->
#        http://127.0.0.1:8787 -- the connector runs where that loopback
#        lives), token file, CONNECTOR_PENDING, DNS only after the connector.
#        The IN-CONTAINER wording (the connector runs INSIDE the client's
#        container) fires only with POSITIVE container evidence the operator
#        side can gather: COUNCIL_CONTAINER_HOSTS names the host (comma list of
#        slugs), or the tunnel's other ingress rules use a container-bridge
#        pattern. The private-bridge shape alone is never evidence; without
#        evidence the path and every write stay identical and the message says
#        the connector runs ON THE HOST. A bridge origin on any other port
#        stays ORIGIN_NOT_LOOPBACK.
#      local-managed CC tunnel, RESCUE RIDE first: the Council rides the client's own
#        rescue tunnel exactly like the remote path (detail "rides rescue tunnel <name>")
#        when ALL hold: the CC tunnel reports this host at http://localhost:4000 or
#        http://127.0.0.1:4000; exactly one tunnel is named rescue-<slug> (or
#        rescue-<slug>-..., the slug as a whole word); it is healthy, remote-managed and
#        has an ssh:// rule for rescue-<slug>.<zone>; the active connectors of both tunnels report origin_ip sets
#        that are non-empty and overlap (same machine); no <slug>-council record points at
#        another tunnel; and COUNCIL_TUNNEL_OVERRIDES has no entry for the slug. No new
#        tunnel, no token file, no connector delivery.
#      otherwise: the Council rides a DEDICATED remote-managed tunnel
#        named council-<slug> (or the COUNCIL_TUNNEL_OVERRIDES name), created or reused
#        (that tunnel local-managed -> PENDING_LOCAL_TUNNEL). The container-host shape
#        (a.) reaches this same dedicated path: no rescue ride, no CC-tunnel ride.
#      council CNAME already points at a healthy tunnel that already routes
#        the exact PATH-LESS rule <slug>-council.<zone> -> http://127.0.0.1:8787 (any
#        equivalent loopback form the code matches elsewhere counts; a
#        path-scoped rule does not count): this host
#        is ADOPTED by that tunnel. Report ALREADY_PROVISIONED with the detail
#        "Council address already wired via tunnel <name>", zero writes, exit 0,
#        and never re-plan a dedicated tunnel for it. The Access app
#        'Council - <slug>' and the edge 302 check still apply to the adopted route.
#      council CNAME points anywhere else (a dead tunnel, a non-CNAME record,
#        or a healthy tunnel with NO such rule -- a genuinely foreign or broken
#        claim)                        (-> CONFLICT)
#   d. create/reuse Access app 'Council - <slug>', read it back, compare the rules with
#      the CC app (exclude/require rules that differ are refused, never synced). An existing app whose rules differ is SYNCED: its allow EMAILS are made
#      equal to the CC app's (missing ones added, ones the CC no longer lists removed, so
#      a revocation on the CC login page also revokes the Council address) by GET-merge-PUT
#      of its own app-scoped allow policy only, non-email rules untouched, then read back.
#      The CC app is never written. Refused (FAILED, zero writes, before any routing) when
#      the app is not 'Council - <slug>' on <slug>-council.<zone>, an email to remove sits
#      on a reusable or non-allow policy (or the app has no app-scoped allow policy), the
#      CC allow policy has a rule other than an email or a service token (everyone, email
#      domain, group), or the Council app admits such a rule.
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
# PENDING_LOCAL_TUNNEL, CONFLICT, SKIPPED_ORPHAN) sends zero writes.
#
# TUNNEL_DOWN: the CC tunnel's status is not "healthy" (down, inactive, degraded).
# A link published now would pass the Access login and then 502, so nothing is
# written; retried every run. ORIGIN_NOT_LOOPBACK: the CC rule's origin is not
# localhost/127.x/[::1] (e.g. a docker bridge IP) and not the container-host shape
# (private bridge address on the CC port), so the connector runs outside the
# box's loopback and cannot reach the Council on 127.0.0.1:8787.
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
# A host adopted by another tunnel that already routes the exact council rule prints
# ALREADY_PROVISIONED with the detail "Council address already wired via tunnel
# <name>" (see ORDER c.), zero writes.
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
#   COUNCIL_ACCESS_EXCLUDE          comma list of hosts to skip, honored in EVERY
#                                   entry path (single-host and --all): the host is
#                                   dropped silently (not an alert) with zero writes.
#                                   Resolved from the environment, else the
#                                   COUNCIL_ACCESS_EXCLUDE line of the operator env
#                                   file COUNCIL_ACCESS_ENV_FILE (parsed, never
#                                   executed), else the default: the operator council
#                                   host and the test tenants
#                                   council, acme-dental-c436, smoke, probe .<zone>)
#   COUNCIL_ACCESS_ENV_FILE         operator env file for the exclude line only
#                                   (default $HOME/.openclaw/.env; credentials come
#                                   from the environment only)
#   COUNCIL_CONTAINER_HOSTS         comma list of slugs that run the Council inside a
#                                   docker container: the explicit operator override
#                                   that turns the private-bridge CC origin into the
#                                   in-container connector wording (see the
#                                   CONTAINER-HOST SHAPE above; absent evidence the
#                                   same dedicated path runs with ON THE HOST wording)
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
#   STATUS = PROVISIONED | ALREADY_PROVISIONED | SYNCED (only the login page emails
#            changed; counts only) | CONNECTOR_PENDING | TUNNEL_DOWN |
#            ORIGIN_NOT_LOOPBACK | PENDING_LOCAL_TUNNEL | CONNECTOR_DOWN |
#            NOT_PROVISIONED | SKIPPED_NOT_CC | SKIPPED_ORPHAN | CONFLICT | FAILED |
#            PLANNED (dry-run, writes needed; a sync is listed as counts to add/remove)
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
ENV_FILE="${COUNCIL_ACCESS_ENV_FILE:-$HOME/.openclaw/.env}"
env_file_val() {  # KEY -> last KEY=value in ENV_FILE, quotes stripped. The file is parsed, never executed.
  local v
  v="$(sed -n -E "s/^[[:space:]]*(export[[:space:]]+)?$1=//p" "$ENV_FILE" 2>/dev/null | tail -n1 | tr -d '\r')"
  v="${v#\"}"; v="${v%\"}"; v="${v#\'}"; v="${v%\'}"
  printf '%s' "$v"
}
# COUNCIL_ACCESS_EXCLUDE: the environment, else the env-file line, else the default.
# One exclude source everywhere (the wrapper and ensure-cc-access.sh resolve it the
# same way), so an excluded host is skipped in every entry path.
EXCLUDE="${COUNCIL_ACCESS_EXCLUDE:-}"
[ -n "$EXCLUDE" ] || EXCLUDE="$(env_file_val COUNCIL_ACCESS_EXCLUDE)"
EXCLUDE="${EXCLUDE:-council.$ZONE_NAME,acme-dental-c436.$ZONE_NAME,smoke.$ZONE_NAME,probe.$ZONE_NAME}"
CONTAINER_HOSTS="${COUNCIL_CONTAINER_HOSTS:-}"
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
  local m="$1" p="$2" d="${3:-}" out code
  if [ -n "$d" ]; then
    out="$(curl -sS --max-time 30 -K "$CURL_CFG" -X "$m" -H 'Content-Type: application/json' --data "$d" -w '\n%{http_code}' "$API$p" 2>/dev/null)"
  else
    out="$(curl -sS --max-time 30 -K "$CURL_CFG" -X "$m" -w '\n%{http_code}' "$API$p" 2>/dev/null)"
  fi
  # The HTTP status rides along as ._http (a string, "000" = no response) so gone_of can tell
  # a tunnel that no longer exists (404) from a transient error (5xx, timeout, auth).
  code="${out##*$'\n'}"; out="${out%$'\n'*}"
  [ "$code" != "$out" ] || out=""
  out="$(printf '%s' "$out" | jq -c --arg c "$code" 'if type == "object" then . + {_http:$c} else error end' 2>/dev/null)" || out=""
  [ -n "$out" ] || out="$(jq -cn --arg c "${code:-000}" '{success:false, errors:[{message:"no response from the API"}], _http:$c}')"
  printf '%s' "$out"
}
# gone_of RESPONSE -> 0 when a tunnel read says the tunnel or its configuration no longer
# exists: HTTP 404 (not a "No route" URL error), or another 4xx (not 401/403/429) whose error
# says "not found". A 5xx, a timeout ("000") or an auth error is never "gone".
gone_of() {
  jq -e '(._http // "") as $c | [.errors[]?.message // "" | strings] as $m
         | ($c == "404" and ($m | any(test("no route"; "i")) | not))
           or (($c | test("^4[0-9][0-9]$")) and ($c | IN("401","403","429") | not) and ($m | any(test("not found"; "i"))))' <<<"$1" >/dev/null 2>&1
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

# container_evidence SLUG CFG -> 0 when the operator side holds POSITIVE evidence the
# box runs the Council inside a docker container; sets EVIDENCE_WHY. The private-bridge
# origin alone is never evidence (a host-run service can sit on a bridge address too).
# ponytail: two signals only (COUNCIL_CONTAINER_HOSTS, bridge-pattern sibling rule);
# add a tunnel-name convention here when one is actually deployed.
container_evidence() {
  local slug="$1" cfg="$2" kv n
  EVIDENCE_WHY=""
  for kv in ${CONTAINER_HOSTS//,/ }; do
    kv="${kv#"${kv%%[![:space:]]*}"}"; kv="${kv%"${kv##*[![:space:]]}"}"
    if [ "$kv" = "$slug" ] || [ "$kv" = "$CC_HOST" ]; then
      EVIDENCE_WHY="COUNCIL_CONTAINER_HOSTS names $slug"; return 0
    fi
  done
  n="$(cc_ingress_of "$cfg" | jq --arg h "$CC_HOST" \
      '[.[] | select(has("hostname") and ((.hostname // "" | ascii_downcase) != ($h | ascii_downcase)))
        | .service // "" | select(test("^https?://(10\\.|172\\.(1[6-9]|2[0-9]|3[01])\\.|192\\.168\\.|host\\.docker\\.internal)([:/]|$)"))] | length' 2>/dev/null)"
  if [ -n "$n" ] && [ "$n" != "0" ]; then
    EVIDENCE_WHY="the tunnel's other ingress rules use a container-bridge address"; return 0
  fi
  return 1
}

# active_conns TUNNEL_ID -> number of active connections ("ERR" when unreadable)
active_conns() {
  local r; r="$(cf GET "/accounts/${ACCT}/cfd_tunnel/${1}/connections")"
  [ "$(ok_of "$r")" = "true" ] || { printf 'ERR'; return; }
  jq -r '[.result[]?.conns[]? | select((.is_pending_reconnect // false) | not)] | length' <<<"$r" 2>/dev/null || printf 'ERR'
}

# conn_ips TUNNEL_ID -> JSON array of the active connections' origin_ip (the public address
# each cloudflared connects from; Cloudflare's TunnelConnection field), "ERR" when unreadable
conn_ips() {
  local r; r="$(cf GET "/accounts/${ACCT}/cfd_tunnel/${1}/connections")"
  [ "$(ok_of "$r")" = "true" ] || { printf 'ERR'; return; }
  jq -c '[.result[]?.conns[]? | select((.is_pending_reconnect // false) | not) | .origin_ip // empty | strings] | unique' <<<"$r" 2>/dev/null || printf 'ERR'
}

# orphan_why TUNNEL_ID RESPONSE [WHY] -> SKIPPED_ORPHAN detail naming the evidence
orphan_why() {
  printf 'the CNAME for %s points at tunnel %s, which no longer exists (%s); an orphan record, not a Command Center to ride. Zero writes; nothing deleted' \
    "$CC_HOST" "$1" "${3:-HTTP $(jq -r '._http // "?"' <<<"$2") $(err_of "$2")}"
}

# rescue_ride SLUG CC_CFG CC_TID -> 0 and RIDE_TID/RIDE_NAME/RIDE_CFG when the Council can ride
# the client's own remote-managed rescue tunnel on the same machine; 1 and RIDE_WHY otherwise.
# All reads. Every condition must hold:
#   the local CC tunnel reports this host on loopback :4000 (Contabo's 19003-19005 never match);
#   exactly one tunnel named rescue-<slug> or rescue-<slug><non-alphanumeric>..., healthy,
#   remote-managed, with an ssh:// rule for rescue-<slug>.<zone>; both tunnels' active connector origin_ip sets are
#   non-empty and overlap (same site); no <slug>-council record points at another tunnel.
TUNNELS=""   # tunnel list, read once per run
rescue_ride() {
  local slug="$1" cccfg="$2" cctid="$3" svc cands n rcfg cips rips r cur
  RIDE_TID=""; RIDE_NAME=""; RIDE_CFG=""; RIDE_WHY=""
  svc="$(cc_ingress_service_for_host "$cccfg" "$CC_HOST")"
  case "$svc" in
    http://localhost:4000|http://localhost:4000/|http://127.0.0.1:4000|http://127.0.0.1:4000/) ;;
    *) RIDE_WHY="the Command Center tunnel reports ${svc:-no rule} for $CC_HOST, not loopback :4000"; return 1 ;;
  esac
  if [ -z "$TUNNELS" ]; then
    TUNNELS="$(cf_all "/accounts/${ACCT}/cfd_tunnel?is_deleted=false")" || { TUNNELS=""; RIDE_WHY="could not list tunnels"; return 1; }
  fi
  cands="$(jq -c --arg p "rescue-$slug" '[.[] | select(.deleted_at == null)
            | select((.name // "" | ascii_downcase) as $n | $n == $p or (($n | startswith($p)) and ($n[($p | length):] | test("^[^a-z0-9]"))))]' <<<"$TUNNELS")"
  n="$(jq 'length' <<<"$cands")"
  [ "$n" = 1 ] || { RIDE_WHY="$n tunnels named rescue-$slug* (exactly one is needed)"; return 1; }
  RIDE_TID="$(jq -r '.[0].id' <<<"$cands")"; RIDE_NAME="$(jq -r '.[0].name' <<<"$cands")"
  [ "$(jq -r '.[0].status // "unknown"' <<<"$cands")" = "healthy" ] || { RIDE_WHY="rescue tunnel $RIDE_NAME is $(jq -r '.[0].status // "unknown"' <<<"$cands"), not healthy"; return 1; }
  rcfg="$(cf GET "/accounts/${ACCT}/cfd_tunnel/${RIDE_TID}/configurations")"
  [ "$(ok_of "$rcfg")" = "true" ] || { RIDE_WHY="could not read rescue tunnel $RIDE_NAME configuration"; return 1; }
  [ "$(jq -r '.result.source // "cloudflare"' <<<"$rcfg")" = "cloudflare" ] || { RIDE_WHY="rescue tunnel $RIDE_NAME is locally managed"; return 1; }
  # bound to THIS slug: a name like rescue-<slug>-x can be another client's (slug <slug>-x)
  [ "$(cc_ingress_of "$rcfg" | jq --arg h "rescue-$slug.${CC_HOST#*.}" '[.[] | select((.hostname // "" | ascii_downcase) == $h) | .service // "" | select(startswith("ssh://"))] | length')" != "0" ] \
    || { RIDE_WHY="rescue tunnel $RIDE_NAME has no ssh:// rule for rescue-$slug.${CC_HOST#*.}"; return 1; }
  cips="$(conn_ips "$cctid")"; rips="$(conn_ips "$RIDE_TID")"
  if [ "$cips" = "ERR" ] || [ "$rips" = "ERR" ] \
     || [ "$(jq -n --argjson a "$cips" --argjson b "$rips" '($a | length) > 0 and ($b | length) > 0 and (($a - ($a - $b)) | length) > 0')" != "true" ]; then
    RIDE_WHY="the Command Center and rescue $RIDE_NAME connectors share no origin address (not provably the same machine)"; return 1
  fi
  r="$(cf GET "/zones/${ZONE_ID}/dns_records?name=${COUNCIL_HOST}")"
  [ "$(ok_of "$r")" = "true" ] || { RIDE_WHY="could not read DNS for $COUNCIL_HOST"; return 1; }
  cur="$(jq -r '.result[0].content // empty' <<<"$r")"
  if [ -n "$cur" ] && [ "$cur" != "${RIDE_TID}.cfargotunnel.com" ]; then
    RIDE_WHY="$COUNCIL_HOST already points at $cur"; return 1
  fi
  RIDE_CFG="$rcfg"
}

# SYNC_JQ ($cc = CC policies response, $co = Council policies response) -> {refuse} or
# {add, remove, pid, want, include, body}: the Council's app-scoped allow policy (lowest
# precedence) with every email the CC lacks dropped and every CC email it lacks appended,
# every other rule kept in order. Emails compare case-insensitively.
SYNC_JQ='def em: select(has("email")) | .email.email | strings | ascii_downcase;
  def safe: has("email") or has("service_token");
  def drop($w): has("email") and ((.email.email // "" | tostring | ascii_downcase) as $e | $w | any(. == $e) | not);
  def xr: {exclude: ([.[].exclude[]?] | map(tojson) | unique), require: ([.[].require[]?] | map(tojson) | unique)};
  [$cc.result[]? | select(.decision == "allow")] as $ca
  | [$co.result[]?] as $cp
  | ([$ca[].include[]? | em] | unique) as $want
  | ([$ca[].include[]? | select(safe | not) | keys[]] | unique) as $ccbad
  | ([$cp[] | select(.decision == "allow") | .include[]? | select(safe | not) | keys[]] | unique) as $cobad
  | ([$cp[] | select(.decision == "allow") | .include[]? | em] | unique) as $have
  | ([$cp[] | select(.decision == "allow" and (.reusable != true))] | sort_by(.precedence // 0) | .[0] // null) as $t
  | if ($ccbad | length) > 0 then {refuse: ("the Command Center allow policy has " + ($ccbad | join(", ")) + " rule(s); mirroring a rule that is not an email is not safe")}
    elif ($cobad | length) > 0 then {refuse: ("the Council app admits " + ($cobad | join(", ")) + " rule(s) the Command Center does not")}
    elif ($ca | xr) != ([$cp[] | select(.decision == "allow")] | xr) then {refuse: "the exclude/require rules differ from the Command Center allow policy (a revocation by exclude must reach the Council too); only emails are synced"}
    elif $t == null then {refuse: "the Council app has no app-scoped allow policy to edit (it is reusable or missing)"}
    else
      ([$cp[] | select(.id != $t.id and .decision != "deny") | select(([.include[]? | em] - $want) | length > 0)
        | "policy \(.name // .id | tojson) (\(.decision)\(if .reusable == true then ", reusable" else "" end))"]) as $others
      | (($t.include // []) | map(select(drop($want) | not))
         + (($want - $have) | map({email: {email: .}}))) as $ni
      | if ($others | length) > 0 then {refuse: ("an email the Command Center does not list is on " + ($others | join(", ")) + ", which this script never edits")}
        elif ($ni | length) == 0 then {refuse: "the edit would leave the Council allow policy empty"}
        else {add: ($want - $have | length), remove: ($have - $want | length), pid: $t.id, want: $want, include: $ni,
              body: ($t | del(.id, .created_at, .updated_at, .reusable, .app_count, .uid) | .include = $ni)} end
    end'

# sync_access APP_JSON APP_ID CC_POLICIES COUNCIL_POLICIES: keep the Council app's allow emails
# equal to the CC app's (add and remove), editing only its app-scoped allow policy. The CC app is
# never written. Sets SYNCED (1 = written, or planned in dry-run) and SYNC_NOTE; on a refusal it
# reports FAILED (zero writes) and returns 1.
sync_access() {
  local app="$1" aid="$2" ccp="$3" cop="$4" plan nadd nrm pid back
  SYNCED=0; SYNC_NOTE=""
  if [ "$(jq -r '.name // ""' <<<"$app")" != "Council - $slug" ] || [ "$(jq -r '.domain // ""' <<<"$app")" != "$COUNCIL_HOST" ]; then
    finish FAILED "the Access app on $COUNCIL_HOST is not the one this script makes ('Council - $slug' on $COUNCIL_HOST) and its rules differ from the Command Center app; not edited, no routing touched"; return 1
  fi
  plan="$(jq -cn --argjson cc "$ccp" --argjson co "$cop" "$SYNC_JQ")" || { finish FAILED "could not compare the Council and Command Center Access rules; no routing touched"; return 1; }
  if [ "$(jq -r 'has("refuse")' <<<"$plan")" = "true" ]; then
    finish FAILED "Access rules on $COUNCIL_HOST differ from the Command Center app and cannot be synced: $(jq -r '.refuse' <<<"$plan"). Zero writes, no routing touched"; return 1
  fi
  nadd="$(jq -r '.add' <<<"$plan")"; nrm="$(jq -r '.remove' <<<"$plan")"; pid="$(jq -r '.pid' <<<"$plan")"
  if [ "$nadd" = "0" ] && [ "$nrm" = "0" ]; then
    step "[ok] Council login page emails equal the Command Center's (its other rules are left untouched)"; return 0
  fi
  SYNCED=1
  if [ "$APPLY" != "1" ]; then
    step "[plan] PUT /accounts/${ACCT}/access/apps/${aid}/policies/${pid} (add $nadd, remove $nrm email(s))"
    SYNC_NOTE="would add $nadd and remove $nrm email(s) on the Council login page to match the Command Center"; return 0
  fi
  w PUT "/accounts/${ACCT}/access/apps/${aid}/policies/${pid}" "$(jq -c '.body' <<<"$plan")"
  [ "$(ok_of "$WRESP")" = "true" ] || { finish FAILED "Council allow policy update failed (nothing changed): $(err_of "$WRESP"); no routing touched"; return 1; }
  back="$(cf GET "/accounts/${ACCT}/access/apps/${aid}/policies")"
  # Proof: every policy reads back as before except the target's include list, and the allow emails equal the CC's.
  if [ "$(ok_of "$back")" != "true" ] || [ "$(jq -n --argjson b "$cop" --argjson a "$back" --argjson p "$plan" '
        def norm: [.result[]? | del(.created_at, .updated_at, .app_count, .uid)] | sort_by(.id);
        (($b | norm | map(if .id == $p.pid then .include = $p.include else . end)) == ($a | norm))
        and (([$a.result[]? | select(.decision == "allow") | .include[]? | select(has("email")) | .email.email | strings | ascii_downcase] | unique) == $p.want)')" != "true" ]; then
    finish FAILED "Council allow policy updated but the read-back does not match the Command Center emails; check it in the Access dashboard. No routing touched"; return 1
  fi
  SYNC_NOTE="Council login page now matches the Command Center: added $nadd, removed $nrm email(s); non-email rules untouched"
}

# ---- one Command Center host ---------------------------------------------------
provision_host() {
  local cc="$1"
  CC_HOST="$cc"; PLAN=(); SYNCED=0; SYNC_NOTE=""; RIDE_WHY=""
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
  if [ "$(ok_of "$th")" != "true" ]; then
    gone_of "$th" && { finish SKIPPED_ORPHAN "$(orphan_why "$tunnel_id" "$th")"; return; }
    finish FAILED "could not read tunnel $tunnel_id (HTTP $(jq -r '._http // "?"' <<<"$th")): $(err_of "$th")"; return
  fi
  if [ "$(jq -r '.result.deleted_at // empty' <<<"$th")" != "" ]; then
    finish SKIPPED_ORPHAN "$(orphan_why "$tunnel_id" "$th" "the tunnel was deleted at $(jq -r '.result.deleted_at' <<<"$th")")"; return
  fi
  tstatus="$(jq -r '.result.status // "unknown"' <<<"$th")"
  if [ "$tstatus" != "healthy" ]; then
    finish TUNNEL_DOWN "tunnel $tunnel_id for $cc is $tstatus, not healthy; a link now would pass the login and then fail. No Cloudflare change made; retried next run"; return
  fi
  cfg="$(cf GET "/accounts/${ACCT}/cfd_tunnel/${tunnel_id}/configurations")"
  if [ "$(ok_of "$cfg")" != "true" ]; then
    # the tunnel was just read as existing and healthy, so a 404 here is never an orphan
    finish FAILED "could not read tunnel configuration for $tunnel_id (HTTP $(jq -r '._http // "?"' <<<"$cfg")): $(err_of "$cfg")"; return
  fi
  src="$(jq -r '.result.source // "cloudflare"' <<<"$cfg")"

  local ride_tid ride_cfg ride_name="" ride_new=0 token_file="" dedicated=0 rescue=0 container=0 evidenced=0 adopted=0 note=""
  if [ "$src" = "cloudflare" ]; then
    cc_ingress_assert_cc_port "$cfg" "$cc" 1 || { finish FAILED "tunnel $tunnel_id has no valid Command Center rule for $cc; refusing to write"; return; }
    local cc_svc origin
    cc_svc="$(cc_ingress_service_for_host "$cfg" "$cc")"
    origin="$(printf '%s' "$cc_svc" | sed -n -E 's#^[a-z]+://(\[[^]]*\]|[^]/:[]+).*#\1#p')"
    case "$origin" in
      localhost|127.*|"[::1]") ;;
      host.docker.internal|10.*|172.1[6-9].*|172.2[0-9].*|172.30.*|172.31.*|192.168.*)
        # Container-host SHAPE only (the CC rule points at a private bridge address
        # on the CC port): the dedicated path applies unchanged. WHICH connector the
        # message names needs positive container evidence (container_evidence); with
        # no evidence the same dedicated path runs and the message says ON THE HOST.
        # Any other non-loopback origin keeps the refusal.
        local origin_port; origin_port="$(cc_ingress_port_of "$cc_svc")"
        if [ "$origin_port" != "$CC_INGRESS_PORT" ]; then
          finish ORIGIN_NOT_LOOPBACK "the Command Center rule for $cc points at $cc_svc, not loopback and not the Command Center port $CC_INGRESS_PORT; that connector cannot reach the Council on $COUNCIL_SERVICE. No Cloudflare change made"; return
        fi
        container=1
        if container_evidence "$slug" "$cfg"; then
          evidenced=1
          step "[ok] container host ($EVIDENCE_WHY): the Command Center rule for $cc points at the container bridge $cc_svc, and the Council rides a dedicated tunnel whose connector runs inside the client's container"
        else
          step "[info] the Command Center rule for $cc points at the private bridge $cc_svc but no container evidence names $slug (COUNCIL_CONTAINER_HOSTS or a bridge-pattern sibling rule): the Council takes the dedicated path and the connector runs ON THE HOST"
        fi
        ;;
      *) finish ORIGIN_NOT_LOOPBACK "the Command Center rule for $cc points at $cc_svc, not loopback; that connector cannot reach the Council on $COUNCIL_SERVICE (it binds the box's IPv4 loopback only). No Cloudflare change made"; return ;;
    esac
  fi
  if [ "$container" = "0" ]; then
    if [ "$src" = "cloudflare" ]; then
      # read-only: does the tunnel have a live connector? (Access answering 302 proves only the edge.)
      local nconn; nconn="$(active_conns "$tunnel_id")"
      [ "$nconn" != "ERR" ] || { finish FAILED "could not read tunnel connections for $tunnel_id"; return; }
      if [ "$nconn" = "0" ]; then
        finish CONNECTOR_DOWN "tunnel $tunnel_id for $cc has no active connector; not ready, retry later. No Cloudflare change made"; return
      fi
      ride_tid="$tunnel_id"; ride_cfg="$cfg"
    elif [ "$(council_tunnel_name "$slug")" = "council-$slug" ] && rescue_ride "$slug" "$cfg" "$tunnel_id"; then
      # The CC tunnel is locally managed, but the same machine already runs the client's
      # remote-managed rescue tunnel: the Council rides it like the remote path (no new
      # tunnel, no token, no connector delivery). COUNCIL_TUNNEL_OVERRIDES never rides.
      rescue=1; ride_tid="$RIDE_TID"; ride_name="$RIDE_NAME"; ride_cfg="$RIDE_CFG"; note="rides rescue tunnel $ride_name"
      say "  Tunnel $tunnel_id (serving $cc) is locally managed (source=$src); the Council rides rescue tunnel $ride_name ($ride_tid) on the same machine."
      step "[ok] rescue tunnel $ride_name: healthy, remote-managed, ssh:// rule, shares a connector origin address with $tunnel_id"
    else
      # The CC tunnel's ingress lives in a config.yml on whichever machine runs it, so
      # the API cannot add a rule there. The Council gets its own remote-managed tunnel.
      dedicated=1
      ride_name="$(council_tunnel_name "$slug")"
      token_file="$TOKEN_DIR/${ride_name}.token"
      say "  Tunnel $tunnel_id (serving $cc) is locally managed (source=$src); the Council rides its own remote-managed tunnel $ride_name."
      [ -z "$RIDE_WHY" ] || step "[info] not riding a rescue tunnel: $RIDE_WHY"
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
  else
    # Container host: the Council cannot ride the CC tunnel (a connector on the host
    # cannot reach the container's loopback), so it takes the same dedicated path as
    # a local-managed CC tunnel, unchanged in every other respect.
    dedicated=1
    ride_name="$(council_tunnel_name "$slug")"
    token_file="$TOKEN_DIR/${ride_name}.token"
    if [ "$evidenced" = "1" ]; then
      say "  Tunnel $tunnel_id (serving $cc) is remote-managed and the Command Center runs inside a container (bridge origin, $EVIDENCE_WHY); the Council rides its own remote-managed tunnel $ride_name, whose connector must run INSIDE the client's container."
    else
      say "  Tunnel $tunnel_id (serving $cc) reports the Command Center at $cc_svc (a private bridge address) with no container evidence; the Council rides its own remote-managed tunnel $ride_name and the connector runs ON THE HOST."
    fi
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

  # council CNAME: an existing record must already point at the tunnel the Council rides,
  # or at a healthy tunnel that already routes the exact council rule (ADOPT, below)
  local expected="${ride_tid:-new}.cfargotunnel.com" rec_id rec_type rec_content
  r="$(cf GET "/zones/${ZONE_ID}/dns_records?name=${COUNCIL_HOST}")"
  [ "$(ok_of "$r")" = "true" ] || { finish FAILED "could not read DNS for $COUNCIL_HOST: $(err_of "$r")"; return; }
  rec_id="$(jq -r '.result[0].id // empty' <<<"$r")"
  rec_type="$(jq -r '.result[0].type // empty' <<<"$r")"
  rec_content="$(jq -r '.result[0].content // empty' <<<"$r")"
  if [ -n "$rec_id" ] && { [ "$ride_new" = "1" ] || [ "$rec_type" != "CNAME" ] || [ "$rec_content" != "$expected" ]; }; then
    # ADOPT NOT CONFLICT: the record already claims a healthy tunnel that routes the
    # exact rule <slug>-council.<zone> -> $COUNCIL_SERVICE. That is a completed
    # wire-up (the live platinum-pearls shape), not a foreign claim: ride the adopting
    # tunnel, never re-plan a dedicated tunnel, and let the Access app + edge gate run.
    local atid="${rec_content%.cfargotunnel.com}"
    if [ "$rec_type" = "CNAME" ] && [ -n "$atid" ] && [ "$atid" != "$rec_content" ] && [ "$atid" != "${ride_tid:-}" ]; then
      local ath acfg asvc
      ath="$(cf GET "/accounts/${ACCT}/cfd_tunnel/${atid}")"
      acfg=""
      if [ "$(ok_of "$ath")" = "true" ] && [ -z "$(jq -r '.result.deleted_at // empty' <<<"$ath")" ] \
         && [ "$(jq -r '.result.status // "unknown"' <<<"$ath")" = "healthy" ]; then
        acfg="$(cf GET "/accounts/${ACCT}/cfd_tunnel/${atid}/configurations")"
      fi
      if [ -n "$acfg" ] && [ "$(ok_of "$acfg")" = "true" ]; then
        # The EXACT rule only: a PATH-LESS <COUNCIL_HOST> rule. A path-scoped rule is
        # not the council wire-up (the host root would still fall to the catch-all),
        # and cc_ingress_service_for_host's first-rule fallback would wrongly count one.
        asvc="$(cc_ingress_of "$acfg" | jq -r --arg h "$COUNCIL_HOST" \
          '[.[] | select(.hostname? == $h and ((.path // "") == "")) | .service // ""] | .[0] // ""' 2>/dev/null)"
        # The IPv6 forms are QUOTED: an unquoted [::1] is a glob bracket expression and
        # would bless a foreign origin like http://1:8787 as loopback.
        case "$asvc" in
          http://localhost:8787|http://localhost:8787/|http://127.0.0.1:8787|http://127.0.0.1:8787/|"http://[::1]:8787"|"http://[::1]:8787/")
            ride_new=0; dedicated=0; rescue=0; token_file=""; adopted=1
            ride_tid="$atid"; ride_cfg="$acfg"; ride_name="$(jq -r '.result.name // empty' <<<"$ath")"
            expected="$rec_content"
            note="Council address already wired via tunnel $ride_name"
            say "  ADOPTED: $COUNCIL_HOST is already wired via tunnel $ride_name ($ride_tid); no dedicated tunnel planned, zero routing writes"
            step "[ok] adopted: tunnel $ride_name already routes $COUNCIL_HOST -> $asvc"
            ;;
        esac
      fi
    fi
  fi
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
    if [ "$(canon_rules "$app_pol")" = "$cc_rules" ]; then
      step "[ok] Council Access rules equal the Command Center rules"
    elif [ "$created_app" = "1" ]; then
      finish FAILED "Access rules on the new $COUNCIL_HOST app differ from the Command Center app; no routing touched. Fix the app in the Access dashboard and re-run"; return
    else
      sync_access "$app" "$app_id" "$cc_pol" "$app_pol" || return
    fi
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

  # f. ingress: an existing council rule is preserved byte-identical (any port); only
  # an absent rule is created - GET -> merge -> PUT at $COUNCIL_SERVICE, CC rule
  # asserted unchanged when it shares the tunnel
  local prior_svc ing_changed=0 new_body
  prior_svc="$(cc_ingress_service_for_host "$ride_cfg" "$COUNCIL_HOST")"
  # An existing council rule is authoritative on its own port (the box owns it -
  # adopted routes and custom ports alike): it is NEVER rewritten. Only an absent
  # rule is created, and it is created on $COUNCIL_SERVICE.
  if [ -n "$prior_svc" ]; then
    if [ "$prior_svc" = "$COUNCIL_SERVICE" ]; then
      step "[ok] ingress rule $COUNCIL_HOST -> $COUNCIL_SERVICE present"
    else
      step "[ok] ingress rule $COUNCIL_HOST -> $prior_svc preserved (the box owns this port; never rewritten)"
    fi
  else
    new_body="$(cc_ingress_merge "$ride_cfg" "$COUNCIL_HOST" "$COUNCIL_SERVICE")" || { finish FAILED "ingress merge failed"; return; }
    if [ "$rescue" = "1" ]; then
      [ "$(jq -c --arg h "$COUNCIL_HOST" '.config.ingress | map(select(.hostname != $h))' <<<"$new_body")" \
        = "$(cc_ingress_of "$ride_cfg" | jq -c --arg h "$COUNCIL_HOST" 'map(select(.hostname != $h))')" ] \
        || { finish FAILED "merge would change an existing rule on rescue tunnel $ride_name; nothing written"; return; }
    elif [ "$dedicated" = "0" ]; then
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
    # The CONNECTOR_PENDING message names BOTH delivery paths, never one impossible step.
    local deliver="deliver the connector token to the in-container path \$OPENCLAW_ROOT/secrets/tunnel-council.token (OPENCLAW_ROOT resolves to /data/.openclaw or ~/.openclaw as wire.sh does) for container hosts, or the host path ~/.openclaw/secrets/tunnel-council.token for host-run connectors"
    local where_note="The connector runs ON THE HOST ($deliver)"
    [ "$evidenced" = "1" ] && where_note="The connector must run INSIDE the client's container (the Council binds the container's loopback, not the host's; $deliver)"
    if [ "$APPLY" = "1" ] || [ "$wrote" = "0" ]; then
      local tok_note="token saved operator side at $token_file"
      [ -s "$token_file" ] || tok_note="token NOT saved yet at $token_file; $([ "$APPLY" = 1 ] && echo "retried next run" || echo "--apply saves it")"
      finish CONNECTOR_PENDING "$COUNCIL_HOST rides tunnel $ride_name ($ride_tid), which has no active connection yet; no DNS record created (zero DNS writes), so no link can open. $where_note ($tok_note); the next run that sees it creates the record${SYNC_NOTE:+. $SYNC_NOTE}"
    else
      finish PLANNED "dry-run: pass --apply to make the writes listed above; no DNS write until tunnel $ride_name has an active connection, so apply ends CONNECTOR_PENDING ($where_note)${SYNC_NOTE:+. $SYNC_NOTE}"
    fi
    return
  fi

  [ -z "$SYNC_NOTE" ] || note="${note:+$note; }$SYNC_NOTE"
  if [ "$wrote" = "0" ] && [ "$SYNCED" = "0" ]; then finish ALREADY_PROVISIONED "$note"
  elif [ "$wrote" = "0" ] && [ "$APPLY" = "1" ]; then finish SYNCED "$note"
  elif [ "$APPLY" = "1" ]; then finish PROVISIONED "$note"
  else finish PLANNED "dry-run: pass --apply to make the writes listed above${note:+; $note}"; fi
}

# rollback TUNNEL ING_CHANGED PRIOR_SVC NEW_DNS_ID WHY: undo what THIS run created.
# The Access app and a newly created Council tunnel are kept (harmless: a login, an unrouted tunnel).
rollback() {
  local tid="$1" ing="$2" prior="$3" dns="$4" why="$5" bad=0 cur body r
  if [ "$ing" = "1" ]; then
    cur="$(cf GET "/accounts/${ACCT}/cfd_tunnel/${tid}/configurations")"
    # A failed read would rebuild the ingress from nothing and drop every other rule
    # (the rescue tunnel's ssh rule, the CC rule): no PUT, report INCOMPLETE instead.
    if [ "$(ok_of "$cur")" != "true" ]; then bad=1
    elif [ -n "$prior" ]; then body="$(cc_ingress_merge "$cur" "$COUNCIL_HOST" "$prior")"
    else
      body="$(jq -c --arg h "$COUNCIL_HOST" '(.result.config // {}) as $c
        | {config: ($c | .ingress = (($c.ingress // []) | map(select(has("hostname") and .hostname != $h))) + [{service:"http_status:404"}])}' <<<"$cur")"
    fi
    if [ "$bad" = "0" ]; then
      w PUT "/accounts/${ACCT}/cfd_tunnel/${tid}/configurations" "$body"; r="$WRESP"
      [ "$(ok_of "$r")" = "true" ] || bad=1
    fi
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
  # COUNCIL_ACCESS_EXCLUDE is honored here exactly as in --all: a silent skip
  # (not an alert), zero writes.
  case ",$EXCLUDE," in *",$TARGET,"*) ;; *) HOSTS=("$TARGET") ;; esac
fi

say "provision-council-access: zone=$ZONE_NAME ($ZONE_ID) hosts=${#HOSTS[@]} mode=$([ "$APPLY" = 1 ] && echo apply || echo dry-run)"
for sk in ${SKIPPED[@]+"${SKIPPED[@]}"}; do CC_HOST="${sk%%|*}"; COUNCIL_HOST=""; PLAN=(); finish SKIPPED_NOT_CC "${sk#*|}"; done
for h in ${HOSTS[@]+"${HOSTS[@]}"}; do provision_host "$h"; done

[ "$JSON" = "1" ] && jq . <<<"$RESULTS"
[ "$ANY_BAD" = "0" ]
