#!/usr/bin/env bash
# council-access-autoprovision.sh [--apply] [--dry-run]
#
# Council of Wise Elders (skill 77) - OPERATOR-SIDE unattended wrapper around
# provision-council-access.sh --all --json. Run it on a timer (see
# launchd/ai.blackceo.council-access-autoprovision.plist.template and
# install-council-access-job.sh) so every client's Command Center host gets its
# <slug>-council address automatically, including clients added later.
#
# Hosts are rediscovered from the Cloudflare zone on EVERY run, so a client whose
# Command Center appears later is simply picked up by the next run. A host that is
# not ready yet (NOT_PROVISIONED, PENDING_LOCAL_TUNNEL, TUNNEL_DOWN, CONNECTOR_DOWN,
# CONNECTOR_PENDING, ORIGIN_NOT_LOOPBACK) is reported in the receipt under
# "refused" and retried next run; it does not fail the run. A host that is not a
# Command Center (SKIPPED_NOT_CC) or whose tunnel no longer exists (SKIPPED_ORPHAN) is
# named under "skipped" and never fails the run. A Council login page brought back in
# line with its Command Center login page (SYNCED) is counted and named under "synced".
# Nothing here depends on a box,
# the AI Workforce Interview, or .workforce-build-state.json.
#
# Dry-run (GET only) is the default. --apply is the only way a write can happen.
#
# CREDENTIALS (names only are ever printed, never values):
#   CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID, from the environment, else
#   loaded from the operator env file COUNCIL_ACCESS_ENV_FILE
#   (default $HOME/.openclaw/.env, the operator secret store). Exit 3 if absent.
#
# ENV:
#   COUNCIL_ACCESS_STATE_DIR   receipts dir (default $HOME/.claude/state/council-elders/access-provision)
#   COUNCIL_ACCESS_ENV_FILE    operator env file (default $HOME/.openclaw/.env).
#                              Sourced only when a credential is missing; its
#                              COUNCIL_ACCESS_EXCLUDE line is parsed (never executed)
#                              on EVERY run, even when the credentials are already in
#                              the environment, so both steps honor the same exclude
#                              list (the environment's COUNCIL_ACCESS_EXCLUDE wins)
#   COUNCIL_ACCESS_STALE_MIN   lock considered stale after this many minutes (default 120)
#   COUNCIL_ACCESS_PROVISION   provision script path (default: sibling provision-council-access.sh)
#   COUNCIL_ACCESS_ENSURE_CC   ensure script path (default: sibling ensure-cc-access.sh)
#   (every provision-council-access.sh variable passes through unchanged)
#
# RECEIPTS in the state dir: last-run.json (overwritten) and runs.log (append-only,
# one line per run) with the time, mode, counts, and every refusal as host:REASON
# (skipped hosts are counted on the line and named in last-run.json).
#
# STEP 1 each run is ensure-cc-access.sh (same mode, so --apply only when this job
# has --apply): it gives every new client's Command Center host its login-gated
# Access application so step 2 (provision-council-access.sh) finds it, and adds any
# missing operator or client email to an existing one (RECONCILED). It keeps its
# own receipts (cc-access-last-run.json, cc-access-runs.log) in the same state dir.
# Its outcome is also summarised here as "cc_access" in last-run.json and as
# cc_reconciled / cc_needs_email / cc_drift / cc_orphans / cc_failed on the runs.log line. NEEDS_EMAIL (no verified
# client email yet), DRIFT (existing app differs), a refusal or any failure of this
# step is reported but NEVER fails the run; the next run retries it.
#
# EXIT: 0 when every host is provisioned, already provisioned, skipped as not a
#       Command Center, or merely not ready yet (also 0 when another run holds the
#       lock); 1 on a real failure (API error, FAILED, CONFLICT); 2 usage; 3
#       credentials or tools missing.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROVISION="${COUNCIL_ACCESS_PROVISION:-$HERE/provision-council-access.sh}"
ENSURE="${COUNCIL_ACCESS_ENSURE_CC:-$HERE/ensure-cc-access.sh}"
STATE_DIR="${COUNCIL_ACCESS_STATE_DIR:-$HOME/.claude/state/council-elders/access-provision}"
ENV_FILE="${COUNCIL_ACCESS_ENV_FILE:-$HOME/.openclaw/.env}"
STALE_MIN="${COUNCIL_ACCESS_STALE_MIN:-120}"
# launchd hands jobs a bare PATH; jq and bash 4 live in Homebrew.
PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"; export PATH

MODE=dry-run
while [ $# -gt 0 ]; do
  case "$1" in
    --apply) MODE=apply ;;
    --dry-run) MODE=dry-run ;;
    -h|--help) sed -n '/^# council-access-autoprovision.sh/,/^set -uo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $1 (use --apply or --dry-run)" >&2; exit 2 ;;
  esac
  shift
done

command -v jq >/dev/null 2>&1 || { echo "missing dependency: jq" >&2; exit 3; }
mkdir -p "$STATE_DIR" || { echo "cannot create state dir $STATE_DIR" >&2; exit 3; }
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# write_receipt JSON LOGLINE : last-run.json replaced atomically, runs.log appended
write_receipt() {
  printf '%s\n' "$1" > "$STATE_DIR/.last-run.tmp" && mv "$STATE_DIR/.last-run.tmp" "$STATE_DIR/last-run.json"
  printf '%s\n' "$2" >> "$STATE_DIR/runs.log"
}

# Credentials: use the environment as is; only when one is missing, load the operator env file.
if [ -z "${CLOUDFLARE_API_TOKEN:-}" ] || [ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]; then
  if [ -r "$ENV_FILE" ]; then set -a; . "$ENV_FILE" >/dev/null 2>&1; set +a; fi
fi
if [ -z "${CLOUDFLARE_API_TOKEN:-}" ] || [ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]; then
  MSG="CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID must both be set (environment or $ENV_FILE)"
  echo "REFUSED: $MSG" >&2
  write_receipt "$(jq -cn --arg t "$TS" --arg m "$MODE" --arg e "$MSG" '{timestamp:$t, mode:$m, exit:3, error:$e}')" \
    "$TS mode=$MODE exit=3 error=missing-credentials"
  exit 3
fi
export CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID
# COUNCIL_ACCESS_EXCLUDE: the same exclude source in every entry path. The env-file
# line is read even when the credentials came from the environment (the file is
# parsed for that one key, never executed), so an excluded host (karen-vaughn) is
# skipped by step 1 and step 2 alike; the environment still wins when set.
if [ -z "${COUNCIL_ACCESS_EXCLUDE:-}" ] && [ -r "$ENV_FILE" ]; then
  _ex="$(sed -n -E "s/^[[:space:]]*(export[[:space:]]+)?COUNCIL_ACCESS_EXCLUDE=//p" "$ENV_FILE" | tail -n1 | tr -d '\r')"
  _ex="${_ex#\"}"; _ex="${_ex%\"}"; _ex="${_ex#\'}"; _ex="${_ex%\'}"
  [ -n "$_ex" ] && COUNCIL_ACCESS_EXCLUDE="$_ex"
  unset _ex
fi
export COUNCIL_ACCESS_EXCLUDE

# Lock: mkdir is atomic. A lock older than STALE_MIN minutes is a dead run; take it over.
LOCK="$STATE_DIR/run.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +"$STALE_MIN" 2>/dev/null)" ]; then
    rm -rf "$LOCK"; mkdir "$LOCK" 2>/dev/null || { echo "lock race lost; another run won" >&2; exit 0; }
  else
    echo "another run holds $LOCK; skipping" >&2
    printf '%s mode=%s skipped=locked\n' "$TS" "$MODE" >> "$STATE_DIR/runs.log"
    exit 0
  fi
fi
OUT="$(mktemp "${TMPDIR:-/tmp}/council-autoprov.XXXXXX")"; ERR="$(mktemp "${TMPDIR:-/tmp}/council-autoprov.XXXXXX")"
trap 'rm -rf "$LOCK"; rm -f "$OUT" "$ERR" "${CCOUT:-}"' EXIT
trap 'exit 130' INT TERM HUP

# Step 1: make sure each Command Center host has its Access app (before step 2 looks for it).
CC_ARGS="--json"; [ "$MODE" = apply ] && CC_ARGS="$CC_ARGS --apply"
CCOUT="$(mktemp "${TMPDIR:-/tmp}/council-autoprov.XXXXXX")"
if [ -x "$ENSURE" ]; then
  # shellcheck disable=SC2086
  "$ENSURE" $CC_ARGS >"$CCOUT" 2>/dev/null; CC_RC=$?   # 0 ok, 1 a host FAILED, 3 refused (e.g. no operator email), 4 zone
else
  CC_RC=127; : > "$CCOUT"
fi
if jq -e 'type == "array"' "$CCOUT" >/dev/null 2>&1; then
  CC="$(jq -c --argjson rc "$CC_RC" '
    . as $r
    | {ran:true, exit:$rc,
       created:([$r[] | select(.status == "CREATED")] | length),
       planned:([$r[] | select(.status == "PLANNED")] | length),
       reconciled:([$r[] | select(.status == "RECONCILED")] | length),
       already:([$r[] | select(.status == "ALREADY_PRESENT")] | length),
       needs_email:[$r[] | select(.status == "NEEDS_EMAIL") | .host],
       drift:[$r[] | select(.status == "DRIFT") | .host],
       orphans:[$r[] | select(.status == "SKIPPED_ORPHAN") | .host],
       failed:[$r[] | select(.status == "FAILED") | .host]}' "$CCOUT")"
else
  CC="$(jq -cn --argjson rc "$CC_RC" '{ran:false, exit:$rc, created:0, planned:0, reconciled:0, already:0, needs_email:[], drift:[], orphans:[], failed:[]}')"
fi
CC_LINE="$(jq -r '" cc_exit=\(.exit) cc_created=\(.created) cc_reconciled=\(.reconciled) cc_needs_email=\(.needs_email|length) cc_drift=\(.drift|length) cc_orphans=\(.orphans|length) cc_failed=\(.failed|length)"' <<<"$CC")"
ARGS="--all --json"; [ "$MODE" = apply ] && ARGS="$ARGS --apply"
# shellcheck disable=SC2086
"$PROVISION" $ARGS >"$OUT" 2>"$ERR"; RC=$?

if jq -e 'type == "array"' "$OUT" >/dev/null 2>&1; then
  RECEIPT="$(jq -c --arg t "$TS" --arg m "$MODE" --argjson rc "$RC" --argjson cc "$CC" '
    . as $r
    | ["NOT_PROVISIONED","PENDING_LOCAL_TUNNEL","TUNNEL_DOWN","CONNECTOR_DOWN","CONNECTOR_PENDING","ORIGIN_NOT_LOOPBACK","CONFLICT","FAILED"] as $refusals
    | (reduce (["PROVISIONED","ALREADY_PROVISIONED","SYNCED","PLANNED","SKIPPED_NOT_CC","SKIPPED_ORPHAN"] + $refusals)[] as $s
         ({}; .[$s] = ([$r[] | select(.status == $s)] | length))) as $c
    | ($c.CONFLICT + $c.FAILED) as $bad
    | {timestamp:$t, mode:$m, exit:(if $bad > 0 or $rc != 0 then 1 else 0 end), total:($r | length),
       counts:$c, cc_access:$cc,
       refused:   [$r[] | select(.status | IN($refusals[])) | {host:.cc_host, reason:.status, detail:.detail}],
       skipped:   [$r[] | select(.status | IN("SKIPPED_NOT_CC","SKIPPED_ORPHAN")) | {host:.cc_host, reason:.status, detail:.detail}],
       provisioned:[$r[] | select(.status == "PROVISIONED") | .cc_host],
       synced:    [$r[] | select(.status == "SYNCED") | .cc_host]}' "$OUT")"
  EXIT="$(jq -r .exit <<<"$RECEIPT")"
  LINE="$(jq -r '"\(.timestamp) mode=\(.mode) exit=\(.exit) total=\(.total) provisioned=\(.counts.PROVISIONED) already=\(.counts.ALREADY_PROVISIONED) synced=\(.counts.SYNCED) planned=\(.counts.PLANNED) skipped=\(.counts.SKIPPED_NOT_CC) orphans=\(.counts.SKIPPED_ORPHAN) refused=\([.refused[]] | length)" + ([.refused[] | " \(.host):\(.reason)"] | join(""))' <<<"$RECEIPT")$CC_LINE"
else
  # No host report at all: API/zone failure, or a missing tool. A real failure.
  EXIT=1; [ "$RC" = 3 ] && EXIT=3
  DETAIL="$(head -c 300 "$ERR" | tr '\n' ' ')"
  RECEIPT="$(jq -cn --arg t "$TS" --arg m "$MODE" --argjson e "$EXIT" --argjson rc "$RC" --arg d "$DETAIL" --argjson cc "$CC" \
    '{timestamp:$t, mode:$m, exit:$e, cc_access:$cc, error:("provision-council-access.sh exit " + ($rc|tostring) + ": " + $d)}')"
  LINE="$TS mode=$MODE exit=$EXIT error=provision-exit-$RC$CC_LINE"
fi
write_receipt "$RECEIPT" "$LINE"
echo "$LINE"
exit "$EXIT"
