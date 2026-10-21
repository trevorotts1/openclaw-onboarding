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
# Center host in the zone has a Cloudflare Access application, so a NEW fleet
# client gets a login-gated address with no human running setup-access-app.sh.
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
# Center: its tunnel is remote-managed and has an ingress rule for that exact host
# on :4000. rescue-<slug>, <slug>-gw, webhook hosts and locally managed tunnels are
# SKIPPED (zero writes): gating a non-Command-Center host could break it.
#
# WHO MAY LOG IN. Exactly: the operator emails + the client's verified owner
# email(s). Never everyone, never a service token. Sources, in order:
#   operator   COUNCIL_CC_OPERATOR_EMAILS (comma list) and/or "operator" in the emails file
#   client     "clients"."<slug>" in the emails file (COUNCIL_CC_EMAILS_FILE, default
#              $HOME/.claude/state/council-elders/cc-access-emails.json), shape
#                {"operator":["a@x"],"clients":{"<slug>":["b@y"]}}
#              else the emails already on that client's own rescue-<slug> Access app
#              (the fleet onboarding doc puts the client's own email there next to the
#              operator emails): the allow-list emails minus the operator emails, only
#              when that leaves 1 or 2 addresses, otherwise ambiguous.
#   No verified client email -> NEEDS_EMAIL, zero writes, retried every run.
#   Placeholder addresses (pending+...) and malformed addresses never count.
# Emails are NEVER printed, logged or put in receipts (counts only).
#
# MODES. Dry-run (GET only) is the default; --apply is the only way a write leaves
# this script. A host whose app already exists is never modified: matching rules ->
# ALREADY_PRESENT, different rules -> DRIFT (reported, not overwritten).
#
# ENV (token and account id never printed):
#   CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID   required (else loaded from
#                                   COUNCIL_ACCESS_ENV_FILE, default $HOME/.openclaw/.env)
#   CF_API_BASE, COUNCIL_ZONE_NAME, COUNCIL_ACCESS_EXCLUDE   as provision-council-access.sh
#   COUNCIL_ACCESS_STATE_DIR   receipts dir, same as the autoprovision job
#                              (default $HOME/.claude/state/council-elders/access-provision)
#   COUNCIL_CC_EMAILS_FILE, COUNCIL_CC_OPERATOR_EMAILS   see above
#
# OUTPUT: one line per host: CC_ACCESS: <host> <STATUS> [detail]  (SKIPPED hosts are
#   counted in the summary line and listed only in --json)
#   STATUS = CREATED | PLANNED (dry-run) | ALREADY_PRESENT | NEEDS_EMAIL | DRIFT |
#            FAILED | SKIPPED
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
if [ -z "${CLOUDFLARE_API_TOKEN:-}" ] || [ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]; then
  # shellcheck source=/dev/null
  if [ -r "$ENV_FILE" ]; then set -a; . "$ENV_FILE" >/dev/null 2>&1; set +a; fi
fi
if [ -z "${CLOUDFLARE_API_TOKEN:-}" ] || [ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]; then
  echo "REFUSED: CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID must both be set (environment or the operator env file)." >&2
  exit 3
fi
unset CLOUDFLARE_ZONE_ID 2>/dev/null || true   # known trap: points at the wrong zone

API="${CF_API_BASE:-https://api.cloudflare.com/client/v4}"
ACCT="$CLOUDFLARE_ACCOUNT_ID"
ZONE_NAME="${COUNCIL_ZONE_NAME:-zerohumanworkforce.com}"
EXCLUDE="${COUNCIL_ACCESS_EXCLUDE:-council.zerohumanworkforce.com}"
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

# ---- Cloudflare plumbing (same token handling as provision-council-access.sh)
umask 077
CURL_CFG="$(mktemp "${TMPDIR:-/tmp}/cc-access-curl.XXXXXX")" || { echo "cannot create temp file" >&2; exit 3; }
trap 'rm -f "$CURL_CFG"; rm -rf "${LOCK:-}"' EXIT
trap 'exit 130' INT TERM HUP
printf 'header = "Authorization: Bearer %s"\n' "$CLOUDFLARE_API_TOKEN" > "$CURL_CFG"

cf() {  # METHOD PATH [JSON] -> response body (synthetic failure body when none)
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
  RESULTS="$(jq -c --arg h "$host" --arg s "$status" --arg d "$detail" '. + [{host:$h, status:$s, detail:$d}]' <<<"$RESULTS")"
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
allow_emails() {  # POLICIES_RESPONSE -> {n, emails, other}: allow policies, email includes, other include kinds
  jq -c '[.result[]? | select(.decision == "allow")] as $p
         | {n: ($p | length),
            emails: ([$p[].include[]? | select(has("email")) | .email.email] | map(ascii_downcase) | unique),
            other: ([$p[].include[]? | select(has("email") | not)] | length)}' <<<"$1"
}

declare -A CFG      # tunnel id -> configuration response (several hosts can share a tunnel)
IDPS=""; IDPS_OK=   # allowed_idps JSON array + 0/1 result, resolved once and only when an app must be created

CLIENT_JSON="[]"; CLIENT_SRC=""
resolve_client_emails() {  # SLUG -> sets CLIENT_JSON (array) and CLIENT_SRC (file|rescue-app|none|ambiguous|error)
  local slug="$1" rapp rpol info
  CLIENT_SRC=none
  CLIENT_JSON="$(jq -c --arg s "$slug" "((\$f.clients[\$s] // []) | if type == \"array\" then . else [.] end) | $CLEAN" --argjson f "$FILE_JSON" <<<"null")"
  if [ "$(jq 'length' <<<"$CLIENT_JSON")" != "0" ]; then CLIENT_SRC="file"; return; fi
  rapp="$(app_for "rescue-${slug}.${ZONE_NAME}")"
  [ -n "$rapp" ] || return
  rpol="$(cf GET "/accounts/${ACCT}/access/apps/$(jq -r '.id' <<<"$rapp")/policies")"
  [ "$(ok_of "$rpol")" = "true" ] || { CLIENT_SRC=error; return; }
  info="$(allow_emails "$rpol")"
  CLIENT_JSON="$(jq -c --argjson op "$OP_JSON" "(.emails | $CLEAN) - \$op" <<<"$info")"
  case "$(jq 'length' <<<"$CLIENT_JSON")" in
    0) CLIENT_JSON="[]" ;;
    *) if [ "$(jq 'length' <<<"$CLIENT_JSON")" -le "$RESCUE_MAX_CLIENT_EMAILS" ]; then CLIENT_SRC=rescue-app
       else CLIENT_JSON="[]"; CLIENT_SRC=ambiguous; fi ;;
  esac
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
  tid="$(jq -r --arg h "$h" '[.[] | select(.name == $h)][0].content // empty | sub("\\.cfargotunnel\\.com$"; "")' <<<"$RECS")"
  [ -n "$tid" ] || { finish "$h" SKIPPED "no tunnel CNAME"; return; }

  # positive proof this is a Command Center: remote-managed tunnel, this host on :4000
  if [ -z "${CFG[$tid]+x}" ]; then CFG[$tid]="$(cf GET "/accounts/${ACCT}/cfd_tunnel/${tid}/configurations")"; fi
  cfgr="${CFG[$tid]}"
  [ "$(ok_of "$cfgr")" = "true" ] || { finish "$h" FAILED "could not read tunnel configuration for $tid: $(err_of "$cfgr")"; return; }
  src="$(jq -r '.result.source // "cloudflare"' <<<"$cfgr")"
  [ "$src" = "cloudflare" ] || { finish "$h" SKIPPED "tunnel is locally managed; cannot confirm this is the Command Center host"; return; }
  svc="$(cc_ingress_service_for_host "$cfgr" "$h")"; port="$(cc_ingress_port_of "$svc")"
  [ "$port" = "$CC_INGRESS_PORT" ] || { finish "$h" SKIPPED "not a Command Center host (no :${CC_INGRESS_PORT} ingress rule)"; return; }

  resolve_client_emails "$slug"
  local have_client=0; [ "$(jq 'length' <<<"$CLIENT_JSON")" != "0" ] && have_client=1
  local exp; exp="$(jq -cn --argjson o "$OP_JSON" --argjson c "$CLIENT_JSON" '$o + $c | unique')"

  local app; app="$(app_for "$h")"
  if [ -n "$app" ]; then
    local aid pol info n other missing extra
    aid="$(jq -r '.id' <<<"$app")"
    pol="$(cf GET "/accounts/${ACCT}/access/apps/${aid}/policies")"
    [ "$(ok_of "$pol")" = "true" ] || { finish "$h" FAILED "could not read the Access app policies: $(err_of "$pol")"; return; }
    info="$(allow_emails "$pol")"
    n="$(jq -r '.n' <<<"$info")"; other="$(jq -r '.other' <<<"$info")"
    if [ "$other" != "0" ]; then finish "$h" DRIFT "existing Access app has $other non-email allow rule(s) (open or custom); not modified"; return; fi
    if [ "$n" = "0" ] || [ "$(jq '.emails | length' <<<"$info")" = "0" ]; then finish "$h" DRIFT "existing Access app has no email allow rule; not modified"; return; fi
    if [ "$have_client" = "1" ]; then
      missing="$(jq --argjson e "$exp" '$e - .emails | length' <<<"$info")"; extra="$(jq --argjson e "$exp" '.emails - $e | length' <<<"$info")"
      if [ "$missing" != "0" ] || [ "$extra" != "0" ]; then
        finish "$h" DRIFT "existing Access app allow-list differs from the expected one ($missing expected email(s) missing, $extra unexpected); not modified"; return
      fi
      finish "$h" ALREADY_PRESENT; return
    fi
    finish "$h" ALREADY_PRESENT "allow rules not compared: no verified client email on file"; return
  fi

  # no app: create one, only with a verified client email
  if [ "$have_client" = "0" ]; then
    case "$CLIENT_SRC" in
      ambiguous) finish "$h" NEEDS_EMAIL "rescue-${slug} Access app lists more than $RESCUE_MAX_CLIENT_EMAILS non-operator emails; add \"$slug\" to the emails file. No app created" ;;
      error)     finish "$h" NEEDS_EMAIL "could not read the rescue-${slug} Access app; no verified client email. No app created" ;;
      *)         finish "$h" NEEDS_EMAIL "no verified client email for $slug (emails file or rescue-${slug} Access app). No app created" ;;
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
RECEIPT="$(jq -c --arg t "$TS" --arg m "$MODE" --argjson bad "$ANY_BAD" '
  . as $r
  | (reduce ("CREATED","PLANNED","ALREADY_PRESENT","NEEDS_EMAIL","DRIFT","FAILED","SKIPPED") as $s
       ({}; .[$s] = ([$r[] | select(.status == $s)] | length))) as $c
  | {timestamp:$t, mode:$m, exit:$bad, total:($r | length), counts:$c,
     needs_email:[$r[] | select(.status == "NEEDS_EMAIL") | .host],
     drift:[$r[] | select(.status == "DRIFT") | .host],
     failed:[$r[] | select(.status == "FAILED") | {host:.host, detail:.detail}],
     created:[$r[] | select(.status == "CREATED") | .host]}' <<<"$RESULTS")"
LINE="$(jq -r '"\(.timestamp) cc-access mode=\(.mode) exit=\(.exit) created=\(.counts.CREATED) planned=\(.counts.PLANNED) already=\(.counts.ALREADY_PRESENT) needs_email=\(.counts.NEEDS_EMAIL) drift=\(.counts.DRIFT) failed=\(.counts.FAILED) skipped=\(.counts.SKIPPED)"' <<<"$RECEIPT")"
printf '%s\n' "$RECEIPT" > "$STATE_DIR/.cc-access-last-run.tmp" && mv "$STATE_DIR/.cc-access-last-run.tmp" "$STATE_DIR/cc-access-last-run.json"
printf '%s\n' "$LINE" >> "$STATE_DIR/cc-access-runs.log"
if [ "$JSON" = "1" ]; then jq . <<<"$RESULTS"; else say "$LINE"; fi
[ "$ANY_BAD" = "0" ]
