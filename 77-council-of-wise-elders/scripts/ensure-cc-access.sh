#!/usr/bin/env bash
# bash 3.2 re-exec guard (macOS /bin/bash is 3.2; this script uses bash-4 arrays).
if [ "${BASH_VERSINFO[0]:-0}" -lt 4 ] && [ -z "${_OC_BASH_REEXEC:-}" ]; then
  for _b in /opt/homebrew/bin/bash /usr/local/bin/bash; do
    [ -x "$_b" ] && _OC_BASH_REEXEC=1 exec "$_b" "$0" "$@"
  done
  echo "FATAL: bash >= 4 required (macOS ships 3.2): brew install bash" >&2; exit 3
fi
# ensure-cc-access.sh [--apply] [--json]
#
# Council of Wise Elders (skill 77) - OPERATOR-SIDE. Makes sure every Command
# Center host in the zone has a Cloudflare Access application (its login page),
# so a NEW fleet client gets a login-gated address with no human running
# setup-access-app.sh, and that EVERY login page, new or old, lets in the operator
# emails and every verified client email (RECONCILE, below).
# provision-council-access.sh refuses (NOT_PROVISIONED) any host with no Command
# Center Access app, so this runs just before it. The settings below mirror
# blackceo-command-center scripts/cloudflare/setup-access-app.sh (read, not run):
#   type self_hosted, session_duration 720h, allowed_idps = One-Time PIN plus
#   Google when the account has one, one policy "Allowed users" (allow, email
#   includes, no login_method require). Only the app NAME differs, by request:
#   'Command Center - <slug>'. Existing apps are matched by DOMAIN, never by name.
#
# WHICH HOSTS. Same discovery as provision-council-access.sh --all (proxied CNAMEs
# to *.cfargotunnel.com, <slug>.<zone> labels, no -hooks/-podcast/-council, the
# COUNCIL_ACCESS_EXCLUDE list), then kept only with POSITIVE proof it is a Command
# Center: its tunnel has an ingress rule for that exact host on :4000. A locally
# managed tunnel is proven the same way whenever its connector-reported config is
# readable, so a local-managed Command Center gets its login page too;
# provision-council-access.sh refuses to publish a Council address for a host with
# no login page, so skipping every local tunnel left local-tunnel clients with no
# address forever. rescue-<slug>, <slug>-gw, webhook hosts, and any host with no
# readable :4000 rule (including a local-managed tunnel whose config the API cannot
# show) are SKIPPED (zero writes): gating a non-Command-Center host could break it. A host whose
# tunnel or tunnel configuration no longer exists (HTTP 404, "Configuration for tunnel
# not found") is an orphan record: SKIPPED_ORPHAN, zero writes, exit 0, named in the
# receipt. A transient read error (5xx, timeout, auth) stays FAILED, and so does a
# healthy, not-deleted tunnel whose configuration is missing: a live tunnel is never
# an orphan.
#
# WHO MAY LOG IN. The operator emails + the client's verified email(s). Never
# everyone, never a service token. The emails file (COUNCIL_CC_EMAILS_FILE, default
# $HOME/.claude/state/council-elders/cc-access-emails.json) has the shape
#     {"operator":["a@x"],"clients":{"<slug>":["b@y"]},"ghl":{"location_id":"<id>"}}
# (every key optional).
#   operator   COUNCIL_CC_OPERATOR_EMAILS (comma list) and/or "operator" in the emails file
#   client     the union of, in this order:
#              1. "clients"."<slug>" in the emails file;
#              2. the non-operator emails already on that client's own Command Center
#                 Access app (an existing login page), and on its rescue-<slug> Access
#                 app (the fleet onboarding doc puts the client's own email there): for
#                 the rescue app only when that leaves 1 or 2 addresses (otherwise
#                 ambiguous) and only when its allow rules are emails alone (otherwise
#                 unverified). The rescue app is matched by the EXACT slug;
#              3. GoHighLevel (Convert and Flow), READ ONLY, via ghl-client-emails.py:
#                 contacts of the Black CEO LLC location that carry one of the emails
#                 above, or whose company name IS the slug read as a business name
#                 (eddie-otts-trading = "Eddie Otts Trading LLC"), plus the same person's
#                 duplicate contacts (same full name AND same phone). Strict: never a
#                 first or full name alone (no one-word slug, no company that is only the
#                 contact's own name), never fuzzy; two different people matched =
#                 "ambiguous", nothing added. Skipped silently (one counts line) when
#                 GOHIGHLEVEL_API_KEY or the location id is not configured. Location id:
#                 COUNCIL_GHL_LOCATION_ID, else "ghl"."location_id" in the emails file
#                 (the GHL location variables in the env files name another location).
#   No verified client email and no app -> NEEDS_EMAIL, zero writes, retried every run.
#   Placeholder addresses (pending+...) and malformed addresses never count.
# Emails are NEVER printed, logged or put in receipts (counts only).
#
# RECONCILE. A host whose app already exists gets every missing operator and client
# email ADDED to its app-scoped allow policy (the lowest precedence one): the live
# policy is read, every existing include rule is kept untouched and in order
# (emails, service tokens, anything else), one {"email":{"email":...}} rule is
# appended per missing address (case-insensitive compare), the full policy minus
# read-only fields is PUT, and it is read back to prove only that include list grew.
# Nothing is ever removed or reordered. Nothing to add -> ALREADY_PRESENT, zero
# writes. Never edited, reported as DRIFT instead: an app with no allow policy, an
# allow policy that admits everyone, or an allow policy that is a reusable (shared)
# policy; non_identity, bypass and deny policies are never touched.
#
# MODES. Dry-run (GET only) is the default; --apply is the only way a write leaves
# this script. Dry-run prints what --apply would create or add (counts only).
#
# ENV (token and account id never printed):
#   CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID   required (else BOTH read from
#                                   COUNCIL_ACCESS_ENV_FILE, default $HOME/.openclaw/.env;
#                                   that file is parsed for those two keys, never sourced)
#   CF_API_BASE, COUNCIL_ZONE_NAME   as provision-council-access.sh
#   COUNCIL_ACCESS_EXCLUDE   as provision-council-access.sh: the environment, else
#                            the COUNCIL_ACCESS_EXCLUDE line of COUNCIL_ACCESS_ENV_FILE
#                            (parsed like the two credentials above, even when the
#                            credentials come from the environment), else the default
#   COUNCIL_ACCESS_STATE_DIR   receipts dir, same as the autoprovision job
#                              (default $HOME/.claude/state/council-elders/access-provision)
#   COUNCIL_CC_EMAILS_FILE, COUNCIL_CC_OPERATOR_EMAILS, COUNCIL_GHL_LOCATION_ID   see above
#   COUNCIL_GHL_ENV_FILE, COUNCIL_GHL_API_BASE   GoHighLevel token file and API base
#                              (tests; see ghl-client-emails.py). The token is never printed.
#
# OUTPUT: one line per host: CC_ACCESS: <host> <STATUS> [detail]  (SKIPPED hosts are
#   counted in the summary line and listed only in --json)
#   STATUS = CREATED | RECONCILED | PLANNED (dry-run) | ALREADY_PRESENT | NEEDS_EMAIL |
#            DRIFT | FAILED | SKIPPED | SKIPPED_ORPHAN
#   then the summary line, then one GoHighLevel counts line ("ghl: ...").
# RECEIPTS in the state dir: cc-access-last-run.json (replaced) and
#   cc-access-runs.log (append-only, one line per run).
# EXIT: 0 unless a host is FAILED (1); 2 usage; 3 missing env/tool/operator email; 4 zone.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
. "$HERE/../../shared-utils/cc-tunnel-ingress.sh"
PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"; export PATH

usage() { sed -n '/^# ensure-cc-access.sh/,/^set -uo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//' >&2; }

APPLY=0; JSON=0
while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --json)  JSON=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

for _t in curl jq; do command -v "$_t" >/dev/null 2>&1 || { echo "missing dependency: $_t" >&2; exit 3; }; done

STATE_DIR="${COUNCIL_ACCESS_STATE_DIR:-$HOME/.claude/state/council-elders/access-provision}"
ENV_FILE="${COUNCIL_ACCESS_ENV_FILE:-$HOME/.openclaw/.env}"
EMAILS_FILE="${COUNCIL_CC_EMAILS_FILE:-$HOME/.claude/state/council-elders/cc-access-emails.json}"
env_file_val() {  # KEY -> last KEY=value in ENV_FILE, quotes stripped. The file is parsed, never executed.
  local v
  v="$(sed -n -E "s/^[[:space:]]*(export[[:space:]]+)?$1=//p" "$ENV_FILE" 2>/dev/null | tail -n1 | tr -d '\r')"
  v="${v#\"}"; v="${v%\"}"; v="${v#\'}"; v="${v%\'}"
  printf '%s' "$v"
}
if { [ -z "${CLOUDFLARE_API_TOKEN:-}" ] || [ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]; } && [ -r "$ENV_FILE" ]; then
  # Take the pair from the file together so a token and an account id never come from two places.
  _tok="$(env_file_val CLOUDFLARE_API_TOKEN)"; _acc="$(env_file_val CLOUDFLARE_ACCOUNT_ID)"
  if [ -n "$_tok" ] && [ -n "$_acc" ]; then CLOUDFLARE_API_TOKEN="$_tok"; CLOUDFLARE_ACCOUNT_ID="$_acc"; fi
  unset _tok _acc
fi
if [ -z "${CLOUDFLARE_API_TOKEN:-}" ] || [ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]; then
  echo "REFUSED: CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID must both be set (environment or the operator env file)." >&2
  exit 3
fi
unset CLOUDFLARE_ZONE_ID 2>/dev/null || true   # known trap: points at the wrong zone

API="${CF_API_BASE:-https://api.cloudflare.com/client/v4}"
ACCT="$CLOUDFLARE_ACCOUNT_ID"
ZONE_NAME="${COUNCIL_ZONE_NAME:-zerohumanworkforce.com}"
# COUNCIL_ACCESS_EXCLUDE resolves from the environment, else the env-file line, else
# the default - the same exclude source as provision-council-access.sh and the
# autoprovision job. An excluded host is skipped silently, zero writes.
EXCLUDE="${COUNCIL_ACCESS_EXCLUDE:-}"
[ -n "$EXCLUDE" ] || EXCLUDE="$(env_file_val COUNCIL_ACCESS_EXCLUDE)"
EXCLUDE="${EXCLUDE:-council.zerohumanworkforce.com}"
SESSION="720h"            # setup-access-app.sh: 30-day session
RESCUE_MAX_CLIENT_EMAILS=2  # ponytail: more non-operator emails on a rescue app than this = ambiguous; raise only with the file source

# ---- emails (jq does all the handling; values never reach a command line or output)
# clean: array of strings -> lowercase, trimmed, well-formed, non-placeholder, unique
CLEAN='[.[]? | strings | ascii_downcase | gsub("^\\s+|\\s+$"; "")
        | select(test("^[a-z0-9._%+-]+@[a-z0-9-]+(\\.[a-z0-9-]+)*\\.[a-z]{2,}$"))
        | select(startswith("pending+") | not)] | unique'

FILE_JSON='{}'
if [ -r "$EMAILS_FILE" ]; then
  FILE_JSON="$(jq -c 'if type == "object" then . else {} end' "$EMAILS_FILE" 2>/dev/null)" || FILE_JSON='{}'
  [ -n "$FILE_JSON" ] || FILE_JSON='{}'
fi
OP_JSON="$(jq -cn --argjson f "$FILE_JSON" --arg e "${COUNCIL_CC_OPERATOR_EMAILS:-}" \
  "(((\$f.operator // []) | if type == \"array\" then . else [.] end) + (\$e | split(\",\"))) | $CLEAN")"
if [ "$(jq 'length' <<<"$OP_JSON")" = "0" ]; then
  echo "REFUSED: no valid operator email configured (COUNCIL_CC_OPERATOR_EMAILS or \"operator\" in the emails file); an app is never created without the operator on its allow-list." >&2
  exit 3
fi

# GoHighLevel location (Black CEO LLC): the env override, else the emails file. No id = lookup skipped.
GHL_LOC="${COUNCIL_GHL_LOCATION_ID:-$(jq -r '(.ghl.location_id? // "") | strings' <<<"$FILE_JSON" 2>/dev/null)}"
GHL_OK=0; GHL_NONE=0; GHL_AMBIG=0; GHL_ERR=0; GHL_SKIP=0; GHL_EMAILS=0

# ---- Cloudflare plumbing (same token handling as provision-council-access.sh)
umask 077
CURL_CFG="$(mktemp "${TMPDIR:-/tmp}/cc-access-curl.XXXXXX")" || { echo "cannot create temp file" >&2; exit 3; }
trap 'rm -f "$CURL_CFG"; rm -rf "${LOCK:-}"' EXIT
trap 'exit 130' INT TERM HUP
printf 'header = "Authorization: Bearer %s"\n' "$CLOUDFLARE_API_TOKEN" > "$CURL_CFG"

cf() {  # METHOD PATH [JSON] -> response body (synthetic failure body when none)
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
cf_all() {  # PATH_WITH_QUERY -> every result item as a JSON array ("ERR" + rc 1 on failure)
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

# A second run (or the job) must not overlap this one. mkdir is atomic; a lock older
# than 120 minutes is a dead run. Distinct from the autoprovision job's run.lock,
# which is held while the job calls this script.
mkdir -p "$STATE_DIR" || { echo "cannot create state dir $STATE_DIR" >&2; exit 3; }
LOCK="$STATE_DIR/cc-access.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +120 2>/dev/null)" ]; then
    rm -rf "$LOCK"; mkdir "$LOCK" 2>/dev/null || { echo "lock race lost; another run won" >&2; LOCK=""; exit 0; }
  else
    echo "another run holds $LOCK; skipping" >&2; LOCK=""; exit 0
  fi
fi

# ---- per-host report plumbing
RESULTS="[]"; ANY_BAD=0
say() { [ "$JSON" = "1" ] || printf '%s\n' "$*"; }
finish() {  # HOST STATUS DETAIL
  local host="$1" status="$2" detail="${3:-}"
  [ "$status" != FAILED ] || ANY_BAD=1
  [ "$status" = SKIPPED ] || say "CC_ACCESS: $host $status${detail:+ $detail}"
  RESULTS="$(jq -c --arg h "$host" --arg s "$status" --arg d "$detail" --arg g "${GHL_STATE:-}" '. + [{host:$h, status:$s, detail:$d} + (if $g == "" then {} else {ghl:$g} end)]' <<<"$RESULTS")"
}

# ---- zone, hosts, shared lists
zr="$(cf GET "/zones?name=${ZONE_NAME}")"
ZONE_ID="$(jq -r --arg n "$ZONE_NAME" '[.result[]? | select(.name == $n)][0].id // empty' <<<"$zr")"
[ -n "$ZONE_ID" ] || { echo "REFUSED: zone '$ZONE_NAME' not found by name: $(err_of "$zr")" >&2; exit 4; }
RECS="$(cf_all "/zones/${ZONE_ID}/dns_records?type=CNAME")" || { echo "REFUSED: could not list zone CNAMEs" >&2; exit 4; }
APPS="$(cf_all "/accounts/${ACCT}/access/apps?x=1")" || { echo "REFUSED: could not list Access apps" >&2; exit 4; }

valid_host() { [[ "$1" == *".$ZONE_NAME" ]] && [[ "${1%".$ZONE_NAME"}" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]]; }
HOSTS=()
while IFS= read -r n; do
  [ -n "$n" ] || continue
  valid_host "$n" || continue
  case "$n" in *-hooks.*|*-podcast.*|*-council.*) continue ;; esac
  case ",$EXCLUDE," in *",$n,"*) continue ;; esac
  HOSTS+=("$n")
done < <(jq -r '.[] | select((.content // "") | endswith(".cfargotunnel.com")) | .name' <<<"$RECS" | sort -u)

app_for() {  # HOST -> the Access app (JSON) whose domain is HOST, or empty
  jq -c --arg h "$1" '[.[] | select(.domain == $h or ((.self_hosted_domains // []) | index($h)))][0] // empty' <<<"$APPS"
}
allow_emails() {  # POLICIES_RESPONSE -> {n, emails, other, open, target}
  # allow policies only (never non_identity/bypass/deny); target = the app-scoped (not reusable)
  # allow policy with the lowest precedence, the one RECONCILE may append to; null when none.
  jq -c '[.result[]? | select(.decision == "allow")] as $p
         | {n: ($p | length),
            emails: ([$p[].include[]? | select(has("email")) | .email.email | strings] | map(ascii_downcase) | unique),
            other: ([$p[].include[]? | select(has("email") | not)] | length),
            open: ([$p[].include[]? | select(has("everyone"))] | length),
            target: ([$p[] | select(.reusable != true)] | sort_by(.precedence // 0) | .[0] // null)}' <<<"$1"
}

declare -A CFG      # tunnel id -> configuration response (several hosts can share a tunnel)
IDPS=""; IDPS_OK=   # allowed_idps JSON array + 0/1 result, resolved once and only when an app must be created

CLIENT_JSON="[]"; CLIENT_SRC=""; RESC_STATE=""; GHL_STATE=""
resolve_client_emails() {  # SLUG [OWN_APP_EMAILS_JSON] -> CLIENT_JSON (union), CLIENT_SRC (sources joined by +, or none),
                           # RESC_STATE (rescue-app|none|ambiguous|unverified|error), GHL_STATE (helper status)
  local slug="$1" own="${2:-[]}" file rescue="[]" ghl="[]" rapp rpol info g n
  file="$(jq -c --arg s "$slug" "((\$f.clients[\$s]? // []) | if type == \"array\" then . else [.] end) | $CLEAN" --argjson f "$FILE_JSON" <<<"null")"
  own="$(jq -c --argjson op "$OP_JSON" "($CLEAN) - \$op" <<<"$own")"
  RESC_STATE=none
  rapp="$(app_for "rescue-${slug}.${ZONE_NAME}")"
  if [ -n "$rapp" ]; then
    rpol="$(cf GET "/accounts/${ACCT}/access/apps/$(jq -r '.id' <<<"$rapp")/policies")"
    if [ "$(ok_of "$rpol")" != "true" ]; then RESC_STATE=error
    else
      info="$(allow_emails "$rpol")"
      # An allow-list that also admits non-email rules (everyone, a domain, a token) is not a verified list.
      if [ "$(jq -r '.other' <<<"$info")" != "0" ]; then RESC_STATE=unverified
      else
        rescue="$(jq -c --argjson op "$OP_JSON" "(.emails | $CLEAN) - \$op" <<<"$info")"; n="$(jq 'length' <<<"$rescue")"
        if [ "$n" = 0 ]; then :
        elif [ "$n" -le "$RESCUE_MAX_CLIENT_EMAILS" ]; then RESC_STATE=rescue-app
        else rescue="[]"; RESC_STATE=ambiguous; fi
      fi
    fi
  fi
  GHL_STATE=skipped
  if [ -n "$GHL_LOC" ]; then
    # stdin carries the emails (never a command line); stdout carries emails back (captured, never printed)
    g="$(jq -cn --arg s "$slug" --argjson a "$file" --argjson b "$own" --argjson c "$rescue" --argjson op "$OP_JSON" --arg l "$GHL_LOC" \
         '{slug:$s, seeds:($a + $b + $c | unique), operator:$op, location_id:$l}' | python3 -I "$HERE/ghl-client-emails.py" 2>/dev/null)"
    GHL_STATE="$(jq -r '.status // "error"' <<<"$g" 2>/dev/null)" || GHL_STATE=error
    [ -n "$GHL_STATE" ] || GHL_STATE=error
    [ "$GHL_STATE" != ok ] || ghl="$(jq -c --argjson op "$OP_JSON" "(.emails | $CLEAN) - \$op" <<<"$g")"
  fi
  case "$GHL_STATE" in
    ok) GHL_OK=$((GHL_OK + 1)); GHL_EMAILS=$((GHL_EMAILS + $(jq 'length' <<<"$ghl"))) ;;
    none) GHL_NONE=$((GHL_NONE + 1)) ;; ambiguous) GHL_AMBIG=$((GHL_AMBIG + 1)) ;;
    skipped) GHL_SKIP=$((GHL_SKIP + 1)) ;; *) GHL_STATE=error; GHL_ERR=$((GHL_ERR + 1)) ;;
  esac
  CLIENT_JSON="$(jq -cn --argjson a "$file" --argjson b "$own" --argjson c "$rescue" --argjson d "$ghl" '$a + $b + $c + $d | unique')"
  CLIENT_SRC="$(jq -rn --argjson a "$file" --argjson b "$own" --argjson c "$rescue" --argjson d "$ghl" \
    '[(if ($a|length) > 0 then "file" else empty end), (if ($b|length) > 0 then "cc-app" else empty end),
      (if ($c|length) > 0 then "rescue-app" else empty end), (if ($d|length) > 0 then "ghl" else empty end)]
     | if length == 0 then "none" else join("+") end')"
}

resolve_idps() {  # sets IDPS (One-Time PIN, plus Google when present) and IDPS_OK; fails without One-Time PIN
  local r
  IDPS_OK=0
  r="$(cf GET "/accounts/${ACCT}/access/identity_providers")"
  [ "$(ok_of "$r")" = "true" ] || return 1
  IDPS="$(jq -c '[(.result[]? | select(.type == "onetimepin") | .id)][0:1] as $o | if ($o | length) == 0 then [] else $o + [(.result[]? | select(.type == "google") | .id)][0:1] end' <<<"$r")"
  [ "$(jq 'length' <<<"$IDPS")" -ge 1 ] || return 1
  IDPS_OK=1
}

ensure_host() {
  local h="$1" slug="${1%%.*}" tid cfgr src svc port
  GHL_STATE=""
  tid="$(jq -r --arg h "$h" '[.[] | select(.name == $h)][0].content // empty | sub("\\.cfargotunnel\\.com$"; "")' <<<"$RECS")"
  [ -n "$tid" ] || { finish "$h" SKIPPED "no tunnel CNAME"; return; }

  # positive proof this is a Command Center: remote-managed tunnel, this host on :4000
  if [ -z "${CFG[$tid]+x}" ]; then CFG[$tid]="$(cf GET "/accounts/${ACCT}/cfd_tunnel/${tid}/configurations")"; fi
  cfgr="${CFG[$tid]}"
  if [ "$(ok_of "$cfgr")" != "true" ]; then
    local tr=""
    gone_of "$cfgr" && tr="$(cf GET "/accounts/${ACCT}/cfd_tunnel/${tid}")"
    # a live (healthy, not deleted) tunnel is never an orphan, whatever its configuration says
    if [ -n "$tr" ] && [ "$(ok_of "$tr")" = "true" ] && [ -z "$(jq -r '.result.deleted_at // empty' <<<"$tr")" ] \
       && [ "$(jq -r '.result.status // ""' <<<"$tr")" = "healthy" ]; then
      finish "$h" FAILED "could not read tunnel configuration for $tid (HTTP $(jq -r '._http' <<<"$cfgr")), but the tunnel is healthy: not an orphan"
    elif [ -n "$tr" ] && { [ "$(ok_of "$tr")" = "true" ] || gone_of "$tr"; }; then
      finish "$h" SKIPPED_ORPHAN "the CNAME points at tunnel $tid, whose configuration no longer exists (HTTP $(jq -r '._http' <<<"$cfgr") $(err_of "$cfgr")); an orphan record. Zero writes; nothing deleted"
    else
      finish "$h" FAILED "could not read tunnel configuration for $tid (HTTP $(jq -r '._http // "?"' <<<"$cfgr")): $(err_of "$cfgr")"
    fi
    return
  fi
  src="$(jq -r '.result.source // "cloudflare"' <<<"$cfgr")"
  svc="$(cc_ingress_service_for_host "$cfgr" "$h")"; port="$(cc_ingress_port_of "$svc")"
  if [ "$port" != "$CC_INGRESS_PORT" ]; then
    # The same :4000 rule is the same positive proof for a locally managed
    # tunnel (the API shows the connector-reported config read-only), so a
    # local-managed Command Center gets its login page too. With no readable
    # rule there is no proof and zero writes either way.
    if [ "$src" = "cloudflare" ]; then
      finish "$h" SKIPPED "not a Command Center host (no :${CC_INGRESS_PORT} ingress rule)"; return
    fi
    finish "$h" SKIPPED "tunnel is locally managed and shows no :${CC_INGRESS_PORT} ingress rule for this host; cannot confirm this is the Command Center host"; return
  fi

  local app info="" present="[]"; app="$(app_for "$h")"
  if [ -n "$app" ]; then
    local aid pol
    aid="$(jq -r '.id' <<<"$app")"
    pol="$(cf GET "/accounts/${ACCT}/access/apps/${aid}/policies")"
    [ "$(ok_of "$pol")" = "true" ] || { finish "$h" FAILED "could not read the Access app policies: $(err_of "$pol")"; return; }
    info="$(allow_emails "$pol")"
    if [ "$(jq -r '.n' <<<"$info")" = "0" ]; then finish "$h" DRIFT "existing Access app has no allow policy; not modified"; return; fi
    if [ "$(jq -r '.open' <<<"$info")" != "0" ]; then finish "$h" DRIFT "existing Access app admits everyone (non-email allow rule); not modified"; return; fi
    if [ "$(jq -r '.target == null' <<<"$info")" = "true" ]; then
      finish "$h" DRIFT "existing Access app's allow policy is a reusable (shared) policy; not modified, add the emails in the Access dashboard"; return
    fi
    present="$(jq -c '.emails' <<<"$info")"
  fi

  resolve_client_emails "$slug" "$present"
  local have_client=0; [ "$(jq 'length' <<<"$CLIENT_JSON")" != "0" ] && have_client=1
  local exp; exp="$(jq -cn --argjson o "$OP_JSON" --argjson c "$CLIENT_JSON" '$o + $c | unique')"

  if [ -n "$app" ]; then
    local miss m mo add pid body r back
    miss="$(jq -cn --argjson e "$exp" --argjson p "$present" '$e - $p')"; m="$(jq 'length' <<<"$miss")"
    [ "$m" != "0" ] || { finish "$h" ALREADY_PRESENT; return; }
    mo="$(jq -n --argjson x "$miss" --argjson o "$OP_JSON" '[$x[] | select(. as $e | $o | index($e))] | length')"
    local what="$m email(s) ($mo operator, $((m - mo)) client; client source: $CLIENT_SRC)"
    if [ "$APPLY" != "1" ]; then
      finish "$h" PLANNED "dry-run: would add $what to the existing allow policy, removing nothing; pass --apply"; return
    fi
    add="$(jq -c 'map({email:{email:.}})' <<<"$miss")"
    pid="$(jq -r '.target.id' <<<"$info")"
    body="$(jq -c --argjson add "$add" '.target | del(.id, .created_at, .updated_at, .reusable, .app_count, .uid)
                                         | .include = ((.include // []) + $add)' <<<"$info")"
    r="$(cf PUT "/accounts/${ACCT}/access/apps/${aid}/policies/${pid}" "$body")"
    [ "$(ok_of "$r")" = "true" ] || { finish "$h" FAILED "allow policy update failed (nothing changed): $(err_of "$r")"; return; }
    back="$(cf GET "/accounts/${ACCT}/access/apps/${aid}/policies")"
    # Proof: every policy reads back exactly as before, except the target's include list grew by $add at its end.
    if [ "$(ok_of "$back")" = "true" ] && [ "$(jq -n --argjson b "$pol" --argjson a "$back" --arg pid "$pid" --argjson add "$add" '
          def norm: [.result[]? | del(.created_at, .updated_at)] | sort_by(.id);
          ($b | norm | map(if .id == $pid then .include = ((.include // []) + $add) else . end)) == ($a | norm)')" = "true" ]; then
      finish "$h" RECONCILED "added $what to the existing allow policy; nothing removed"
    else
      finish "$h" FAILED "allow policy updated but the read-back is not the additive change; check it in the Access dashboard"
    fi
    return
  fi

  # no app: create one, only with a verified client email
  if [ "$have_client" = "0" ]; then
    case "$RESC_STATE" in
      ambiguous) finish "$h" NEEDS_EMAIL "rescue-${slug} Access app lists more than $RESCUE_MAX_CLIENT_EMAILS non-operator emails; add \"$slug\" to the emails file. No app created" ;;
      unverified) finish "$h" NEEDS_EMAIL "rescue-${slug} Access app admits non-email rules, so its emails are not a verified list; add \"$slug\" to the emails file. No app created" ;;
      error)     finish "$h" NEEDS_EMAIL "could not read the rescue-${slug} Access app; no verified client email. No app created" ;;
      *)         finish "$h" NEEDS_EMAIL "no verified client email for $slug (emails file, rescue-${slug} Access app or GoHighLevel: $GHL_STATE). No app created" ;;
    esac
    return
  fi
  [ -n "$IDPS_OK" ] || resolve_idps
  [ "$IDPS_OK" = "1" ] || { finish "$h" FAILED "no One-Time PIN identity provider on the account (or it could not be read); no app created"; return; }
  local body; body="$(jq -cn --arg n "Command Center - $slug" --arg d "$h" --arg s "$SESSION" --argjson idps "$IDPS" --argjson e "$exp" '
    {name:$n, domain:$d, type:"self_hosted", session_duration:$s, allowed_idps:$idps,
     policies:[{name:"Allowed users", decision:"allow", precedence:1, include:($e | map({email:{email:.}}))}]}')"
  if [ "$APPLY" != "1" ]; then
    finish "$h" PLANNED "dry-run: would create Access app 'Command Center - $slug' for $(jq 'length' <<<"$exp") email(s) (client source: $CLIENT_SRC); pass --apply"
    return
  fi
  local r nid back
  r="$(cf POST "/accounts/${ACCT}/access/apps" "$body")"
  [ "$(ok_of "$r")" = "true" ] || { finish "$h" FAILED "Access app create failed: $(err_of "$r")"; return; }
  nid="$(jq -r '.result.id // empty' <<<"$r")"
  back="$(cf GET "/accounts/${ACCT}/access/apps/${nid}/policies")"
  if [ "$(ok_of "$back")" = "true" ] && [ "$(allow_emails "$back" | jq -c --argjson e "$exp" '(.emails == $e) and (.other == 0)')" = "true" ]; then
    finish "$h" CREATED "Access app 'Command Center - $slug' created for $(jq 'length' <<<"$exp") email(s) (client source: $CLIENT_SRC)"
  else
    finish "$h" FAILED "Access app created ($nid) but the read-back allow-list does not match; check it in the Access dashboard"
  fi
}

MODE=dry-run; [ "$APPLY" = 1 ] && MODE=apply
say "ensure-cc-access: zone=$ZONE_NAME ($ZONE_ID) hosts=${#HOSTS[@]} mode=$MODE"
for h in ${HOSTS[@]+"${HOSTS[@]}"}; do ensure_host "$h"; done

TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
GHL_SUM="$(jq -cn --argjson ok "$GHL_OK" --argjson none "$GHL_NONE" --argjson amb "$GHL_AMBIG" --argjson err "$GHL_ERR" \
  --argjson skip "$GHL_SKIP" --argjson em "$GHL_EMAILS" \
  'if ($ok + $none + $amb + $err) == 0 then {skipped:true}
   else {skipped:false, matched:$ok, none:$none, ambiguous:$amb, errors:$err, skipped_hosts:$skip, emails:$em} end')"
RECEIPT="$(jq -c --arg t "$TS" --arg m "$MODE" --argjson bad "$ANY_BAD" --argjson ghl "$GHL_SUM" '
  . as $r
  | (reduce ("CREATED","RECONCILED","PLANNED","ALREADY_PRESENT","NEEDS_EMAIL","DRIFT","FAILED","SKIPPED","SKIPPED_ORPHAN") as $s
       ({}; .[$s] = ([$r[] | select(.status == $s)] | length))) as $c
  | {timestamp:$t, mode:$m, exit:$bad, total:($r | length), counts:$c, ghl:$ghl,
     needs_email:[$r[] | select(.status == "NEEDS_EMAIL") | .host],
     drift:[$r[] | select(.status == "DRIFT") | .host],
     orphans:[$r[] | select(.status == "SKIPPED_ORPHAN") | {host:.host, detail:.detail}],
     failed:[$r[] | select(.status == "FAILED") | {host:.host, detail:.detail}],
     created:[$r[] | select(.status == "CREATED") | .host],
     reconciled:[$r[] | select(.status == "RECONCILED") | .host]}' <<<"$RESULTS")"
LINE="$(jq -r '"\(.timestamp) cc-access mode=\(.mode) exit=\(.exit) created=\(.counts.CREATED) reconciled=\(.counts.RECONCILED) planned=\(.counts.PLANNED) already=\(.counts.ALREADY_PRESENT) needs_email=\(.counts.NEEDS_EMAIL) drift=\(.counts.DRIFT) failed=\(.counts.FAILED) skipped=\(.counts.SKIPPED) orphans=\(.counts.SKIPPED_ORPHAN) " + (if .ghl.skipped then "ghl=skipped" else "ghl_matched=\(.ghl.matched) ghl_ambiguous=\(.ghl.ambiguous) ghl_errors=\(.ghl.errors)" end)' <<<"$RECEIPT")"
GHL_LINE="$(jq -r 'if .ghl.skipped then "ghl: skipped (no credentials/location)"
  else "ghl: matched=\(.ghl.matched) none=\(.ghl.none) ambiguous=\(.ghl.ambiguous) errors=\(.ghl.errors) skipped=\(.ghl.skipped_hosts) emails_found=\(.ghl.emails)" end' <<<"$RECEIPT")"
printf '%s\n' "$RECEIPT" > "$STATE_DIR/.cc-access-last-run.tmp" && mv "$STATE_DIR/.cc-access-last-run.tmp" "$STATE_DIR/cc-access-last-run.json"
printf '%s\n' "$LINE" >> "$STATE_DIR/cc-access-runs.log"
if [ "$JSON" = "1" ]; then jq . <<<"$RESULTS"; else say "$LINE"; say "$GHL_LINE"; fi
[ "$ANY_BAD" = "0" ]
