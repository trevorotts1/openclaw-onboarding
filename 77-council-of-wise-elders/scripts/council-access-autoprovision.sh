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
# not ready yet (NOT_PROVISIONED, PENDING_LOCAL_TUNNEL) or not a Command Center
# (SKIPPED_NOT_CC, e.g. rescue-<slug>) is reported in the receipt and retried next
# run; it does not fail the run. Nothing here depends on a box,
# the AI Workforce Interview, or .workforce-build-state.json.
#
# Dry-run (GET only) is the default. --apply is the only way a write can happen.
#
# CREDENTIALS (names only are ever printed, never values):
#   CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID, from the environment, else
#   read (those two keys only, never sourced) from the operator env file
#   COUNCIL_ACCESS_ENV_FILE (default $HOME/.openclaw/.env). Exit 3 if absent.
#
# ENV:
#   COUNCIL_ACCESS_STATE_DIR   receipts dir (default $HOME/.claude/state/council-elders/access-provision)
#   COUNCIL_ACCESS_ENV_FILE    operator env file (default $HOME/.openclaw/.env)
#   COUNCIL_ACCESS_STALE_MIN   lock considered stale after this many minutes (default 120)
#   COUNCIL_ACCESS_PROVISION   provision script path (default: sibling provision-council-access.sh)
#   (every provision-council-access.sh variable passes through unchanged)
#
# RECEIPTS in the state dir: last-run.json (overwritten) and runs.log (append-only,
# one line per run) with the time, mode, counts, and every refusal as host:REASON.
#
# EXIT: 0 when every host is provisioned, already provisioned, or merely not ready
#       yet (also 0 when another run holds the lock); 1 on a real failure (API
#       error, FAILED, CONFLICT); 2 usage; 3 credentials or tools missing.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROVISION="${COUNCIL_ACCESS_PROVISION:-$HERE/provision-council-access.sh}"
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
# The file is parsed for these two keys only, never sourced: other lines are never run or exported.
env_key() { # <KEY> : last KEY=value in ENV_FILE, quotes stripped
  sed -n -E "s/^[[:space:]]*(export[[:space:]]+)?$1=//p" "$ENV_FILE" 2>/dev/null | tail -n1 \
    | sed -E -e 's/^[[:space:]]+|[[:space:]]+$//g' -e 's/^"(.*)"$/\1/' -e "s/^'(.*)'$/\1/"
}
if [ -z "${CLOUDFLARE_API_TOKEN:-}" ] || [ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]; then
  if [ -r "$ENV_FILE" ]; then
    [ -n "${CLOUDFLARE_API_TOKEN:-}" ] || CLOUDFLARE_API_TOKEN="$(env_key CLOUDFLARE_API_TOKEN)"
    [ -n "${CLOUDFLARE_ACCOUNT_ID:-}" ] || CLOUDFLARE_ACCOUNT_ID="$(env_key CLOUDFLARE_ACCOUNT_ID)"
  fi
fi
if [ -z "${CLOUDFLARE_API_TOKEN:-}" ] || [ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]; then
  MSG="CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID must both be set (environment or $ENV_FILE)"
  echo "REFUSED: $MSG" >&2
  write_receipt "$(jq -cn --arg t "$TS" --arg m "$MODE" --arg e "$MSG" '{timestamp:$t, mode:$m, exit:3, error:$e}')" \
    "$TS mode=$MODE exit=3 error=missing-credentials"
  exit 3
fi
export CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID

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
trap 'rm -rf "$LOCK"; rm -f "$OUT" "$ERR"' EXIT
trap 'exit 130' INT TERM HUP

ARGS="--all --json"; [ "$MODE" = apply ] && ARGS="$ARGS --apply"
# shellcheck disable=SC2086
"$PROVISION" $ARGS >"$OUT" 2>"$ERR"; RC=$?

if jq -e 'type == "array"' "$OUT" >/dev/null 2>&1; then
  RECEIPT="$(jq -c --arg t "$TS" --arg m "$MODE" --argjson rc "$RC" '
    . as $r
    | (reduce ("PROVISIONED","ALREADY_PROVISIONED","PLANNED","NOT_PROVISIONED","PENDING_LOCAL_TUNNEL","SKIPPED_NOT_CC","CONFLICT","FAILED") as $s
         ({}; .[$s] = ([$r[] | select(.status == $s)] | length))) as $c
    | ($c.CONFLICT + $c.FAILED) as $bad
    | {timestamp:$t, mode:$m, exit:(if $bad > 0 or $rc != 0 then 1 else 0 end), total:($r | length),
       counts:$c,
       refused:   [$r[] | select(.status | IN("PROVISIONED","ALREADY_PROVISIONED","PLANNED") | not) | {host:.cc_host, reason:.status, detail:.detail}],
       provisioned:[$r[] | select(.status == "PROVISIONED") | .cc_host]}' "$OUT")"
  EXIT="$(jq -r .exit <<<"$RECEIPT")"
  LINE="$(jq -r '"\(.timestamp) mode=\(.mode) exit=\(.exit) total=\(.total) provisioned=\(.counts.PROVISIONED) already=\(.counts.ALREADY_PROVISIONED) planned=\(.counts.PLANNED) refused=\([.refused[]] | length)" + ([.refused[] | " \(.host):\(.reason)"] | join(""))' <<<"$RECEIPT")"
else
  # No host report at all: API/zone failure, or a missing tool. A real failure.
  EXIT=1; [ "$RC" = 3 ] && EXIT=3
  DETAIL="$(head -c 300 "$ERR" | tr '\n' ' ')"
  RECEIPT="$(jq -cn --arg t "$TS" --arg m "$MODE" --argjson e "$EXIT" --argjson rc "$RC" --arg d "$DETAIL" \
    '{timestamp:$t, mode:$m, exit:$e, error:("provision-council-access.sh exit " + ($rc|tostring) + ": " + $d)}')"
  LINE="$TS mode=$MODE exit=$EXIT error=provision-exit-$RC"
fi
write_receipt "$RECEIPT" "$LINE"
echo "$LINE"
exit "$EXIT"
