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
#      council CNAME already points elsewhere        (-> CONFLICT)
#   b. the CC host's Access app + allow rules        (none -> NOT_PROVISIONED)
#   c. tunnel configuration is remote-managed        (local -> PENDING_LOCAL_TUNNEL)
#      and routes the host to a Command Center :4000 (else -> SKIPPED_NOT_CC)
#   d. create/reuse Access app 'Council - <slug>', read it back, diff the rules
#      against the CC app (mismatch -> FAILED before any routing)
#   e. merge the ingress rule (GET -> merge -> PUT, CC rule asserted unchanged)
#   f. proxied CNAME -> <tunnel-id>.cfargotunnel.com
#   g. edge gate: GET the host, no redirects; it must 302 to *.cloudflareaccess.com.
#      Fail -> roll back what THIS run created, print FAILED.
# Every refusal (NOT_PROVISIONED, PENDING_LOCAL_TUNNEL, SKIPPED_NOT_CC, CONFLICT) sends zero writes.
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
#   COUNCIL_ACCESS_EXCLUDE          --all: comma list of hosts to skip
#                                   (default council.zerohumanworkforce.com)
#   COUNCIL_EDGE_URL_TEMPLATE       default https://%s/   (%s = council host)
#   COUNCIL_EDGE_TRIES / COUNCIL_EDGE_SLEEP   edge gate retries (default 5 / 4s)
#
# OUTPUT: one line per host: COUNCIL_ACCESS: <cc-host> <STATUS> [detail]
#   STATUS = PROVISIONED | ALREADY_PROVISIONED | PENDING_LOCAL_TUNNEL |
#            NOT_PROVISIONED | CONFLICT | FAILED | PLANNED (dry-run, writes needed) |
#            SKIPPED_NOT_CC (the host's ingress is not a Command Center on :4000)
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
EXCLUDE="${COUNCIL_ACCESS_EXCLUDE:-council.zerohumanworkforce.com}"
EDGE_TPL="${COUNCIL_EDGE_URL_TEMPLATE:-https://%s/}"
EDGE_TRIES="${COUNCIL_EDGE_TRIES:-5}"
EDGE_SLEEP="${COUNCIL_EDGE_SLEEP:-4}"
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

edge_gate() {  # COUNCIL_HOST -> 0 when the host answers 302 to *.cloudflareaccess.com
  local url="${EDGE_TPL//%s/$1}" i hdrs code loc
  for ((i = 1; i <= EDGE_TRIES; i++)); do
    hdrs="$(curl -sS -o /dev/null -D - --max-time 15 "$url" 2>/dev/null | tr -d '\r')" || hdrs=""
    code="$(printf '%s\n' "$hdrs" | sed -n '1s#^HTTP/[0-9.]* \([0-9]*\).*#\1#p')"
    loc="$(printf '%s\n' "$hdrs" | sed -n 's/^[Ll]ocation: *//p' | head -n1)"
    if [ "$code" = "302" ] && printf '%s' "$loc" | grep -Eiq '^https://[^/]*\.cloudflareaccess\.com(/|$)'; then return 0; fi
    [ "$i" -lt "$EDGE_TRIES" ] && sleep "$EDGE_SLEEP"
  done
  EDGE_WHY="HTTP ${code:-none}, Location ${loc:-none}"
  return 1
}

# ---- one Command Center host ---------------------------------------------------
provision_host() {
  local cc="$1"
  CC_HOST="$cc"; PLAN=()
  local slug="${cc%%.*}" rest="${cc#*.}"
  COUNCIL_HOST="${slug}-council.${rest}"
  say "== $cc -> $COUNCIL_HOST ($([ "$APPLY" = 1 ] && echo apply || echo dry-run))"
  [ "${#slug}" -le 56 ] || { finish FAILED "slug too long for a DNS label"; return; }

  # a. tunnel id from the CC CNAME; refuse a council CNAME that points elsewhere
  local r tunnel_id expected rec_id rec_type rec_content
  r="$(cf GET "/zones/${ZONE_ID}/dns_records?type=CNAME&name=${cc}")"
  [ "$(ok_of "$r")" = "true" ] || { finish FAILED "could not read DNS for $cc: $(err_of "$r")"; return; }
  tunnel_id="$(jq -r '.result[0].content // empty | select(endswith(".cfargotunnel.com")) | sub("\\.cfargotunnel\\.com$"; "")' <<<"$r")"
  [ -n "$tunnel_id" ] || { finish NOT_PROVISIONED "$cc has no CNAME to a tunnel (no Command Center tunnel to ride)"; return; }
  expected="${tunnel_id}.cfargotunnel.com"
  r="$(cf GET "/zones/${ZONE_ID}/dns_records?name=${COUNCIL_HOST}")"
  [ "$(ok_of "$r")" = "true" ] || { finish FAILED "could not read DNS for $COUNCIL_HOST: $(err_of "$r")"; return; }
  rec_id="$(jq -r '.result[0].id // empty' <<<"$r")"
  rec_type="$(jq -r '.result[0].type // empty' <<<"$r")"
  rec_content="$(jq -r '.result[0].content // empty' <<<"$r")"
  if [ -n "$rec_id" ] && { [ "$rec_type" != "CNAME" ] || [ "$rec_content" != "$expected" ]; }; then
    finish CONFLICT "$COUNCIL_HOST already exists as $rec_type -> $rec_content, not $expected; nothing changed"; return
  fi

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

  # c. tunnel configuration (read-only here; local tunnels are a box-side job)
  local cfg src
  cfg="$(cf GET "/accounts/${ACCT}/cfd_tunnel/${tunnel_id}/configurations")"
  [ "$(ok_of "$cfg")" = "true" ] || { finish FAILED "could not read tunnel configuration for $tunnel_id: $(err_of "$cfg")"; return; }
  src="$(jq -r '.result.source // "cloudflare"' <<<"$cfg")"
  if [ "$src" != "cloudflare" ]; then
    say "  Locally managed tunnel. On the box, add to the cloudflared config.yml ingress list (above the final http_status:404 rule), then restart cloudflared:"
    say "    - hostname: $COUNCIL_HOST"
    say "      service: $COUNCIL_SERVICE"
    finish PENDING_LOCAL_TUNNEL "$cc rides a locally managed tunnel; add the ingress lines above on the box. No Cloudflare change made (the Access app and CNAME are created on a re-run once routing exists)"
    return
  fi
  # A zone CNAME whose own ingress rule is not a Command Center on :4000 (rescue-<slug>
  # SSH tunnels, gateway hosts) is not a Command Center: skip it, never a failure.
  cc_ingress_assert_cc_port "$cfg" "$cc" 1 2>/dev/null || { finish SKIPPED_NOT_CC "$cc routes to '$(cc_ingress_service_for_host "$cfg" "$cc")', not a Command Center on :4000; nothing changed"; return; }

  # d. Access app first
  local app app_id app_pol created_app=0 body inc
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

  # e. ingress: GET -> merge -> PUT, CC rule asserted unchanged
  local prior_svc ing_changed=0 new_body
  prior_svc="$(cc_ingress_service_for_host "$cfg" "$COUNCIL_HOST")"
  if [ "$prior_svc" = "$COUNCIL_SERVICE" ]; then
    step "[ok] ingress rule $COUNCIL_HOST -> $COUNCIL_SERVICE present"
  else
    new_body="$(cc_ingress_merge "$cfg" "$COUNCIL_HOST" "$COUNCIL_SERVICE")" || { finish FAILED "ingress merge failed"; return; }
    cc_ingress_assert_cc_port "$new_body" "$cc" 1 \
      && [ "$(cc_ingress_service_for_host "$new_body" "$cc")" = "$(cc_ingress_service_for_host "$cfg" "$cc")" ] \
      || { finish FAILED "merge would change the Command Center ingress rule; nothing written"; return; }
    w PUT "/accounts/${ACCT}/cfd_tunnel/${tunnel_id}/configurations" "$new_body"; r="$WRESP"
    [ "$(ok_of "$r")" = "true" ] || { finish FAILED "ingress PUT failed: $(err_of "$r")"; return; }
    ing_changed=1
  fi

  # f. DNS (an existing correct record is reused)
  local dns_created=0 new_dns_id=""
  if [ -n "$rec_id" ]; then
    step "[ok] CNAME $COUNCIL_HOST -> $expected present"
  else
    w POST "/zones/${ZONE_ID}/dns_records" \
      "$(jq -cn --arg n "$COUNCIL_HOST" --arg c "$expected" '{type:"CNAME", name:$n, content:$c, proxied:true, ttl:1}')"; r="$WRESP"
    if [ "$(ok_of "$r")" != "true" ]; then
      rollback "$tunnel_id" "$ing_changed" "$prior_svc" "" "DNS create failed: $(err_of "$r")"; return
    fi
    new_dns_id="$(jq -r '.result.id // empty' <<<"$r")"; dns_created=1
  fi

  # g. edge gate (dry-run only runs it when nothing would be written)
  local wrote=$((created_app + ing_changed + dns_created))
  if [ "$APPLY" = "1" ] || [ "$wrote" = "0" ]; then
    EDGE_WHY=""
    if edge_gate "$COUNCIL_HOST"; then
      step "[ok] edge gate: $COUNCIL_HOST answers 302 to Cloudflare Access"
    elif [ "$wrote" = "0" ]; then
      finish FAILED "edge gate failed on an existing setup ($EDGE_WHY); this run created nothing, so nothing was rolled back"; return
    else
      rollback "$tunnel_id" "$ing_changed" "$prior_svc" "$new_dns_id" "edge gate failed ($EDGE_WHY)"; return
    fi
  fi

  if [ "$wrote" = "0" ]; then finish ALREADY_PROVISIONED
  elif [ "$APPLY" = "1" ]; then finish PROVISIONED
  else finish PLANNED "dry-run: pass --apply to make the writes listed above"; fi
}

# rollback TUNNEL ING_CHANGED PRIOR_SVC NEW_DNS_ID WHY: undo what THIS run created.
# The Access app is kept (harmless: it only adds a login).
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
  else finish FAILED "$why; rolled back what this run created (Access app kept)"; fi
}

# ---- zone, then hosts -------------------------------------------------------------
zr="$(cf GET "/zones?name=${ZONE_NAME}")"
ZONE_ID="$(jq -r --arg n "$ZONE_NAME" '[.result[]? | select(.name == $n)][0].id // empty' <<<"$zr")"
[ -n "$ZONE_ID" ] || { echo "REFUSED: zone '$ZONE_NAME' not found by name: $(err_of "$zr")" >&2; exit 4; }

HOSTS=()
valid_host() { [[ "$1" == *".$ZONE_NAME" ]] && [[ "${1%".$ZONE_NAME"}" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]]; }
if [ "$TARGET" = "--all" ]; then
  recs="$(cf_all "/zones/${ZONE_ID}/dns_records?type=CNAME")" || { echo "REFUSED: could not list zone CNAMEs" >&2; exit 4; }
  while IFS= read -r n; do
    [ -n "$n" ] || continue
    valid_host "$n" || continue
    case "$n" in *-hooks.*|*-podcast.*|*-council.*) continue ;; esac
    case ",$EXCLUDE," in *",$n,"*) continue ;; esac
    HOSTS+=("$n")
  done < <(jq -r '.[] | select((.content // "") | endswith(".cfargotunnel.com")) | .name' <<<"$recs" | sort -u)
else
  valid_host "$TARGET" || { echo "host must be <slug>.$ZONE_NAME" >&2; exit 2; }
  case "$TARGET" in *-hooks.*|*-podcast.*|*-council.*) echo "give the Command Center host, not a -hooks/-podcast/-council host" >&2; exit 2 ;; esac
  HOSTS=("$TARGET")
fi

say "provision-council-access: zone=$ZONE_NAME ($ZONE_ID) hosts=${#HOSTS[@]} mode=$([ "$APPLY" = 1 ] && echo apply || echo dry-run)"
for h in ${HOSTS[@]+"${HOSTS[@]}"}; do provision_host "$h"; done

[ "$JSON" = "1" ] && jq . <<<"$RESULTS"
[ "$ANY_BAD" = "0" ]
