#!/usr/bin/env bash
# 65-rescue-receiver/wire.sh — idempotent box-side wiring for the RR coaching poll.
# Registers the */2-minute command cron ONLY when the box is enrolled
# (RR_RECEIVER_URL + RR_BOX_TOKEN present in <ocroot>/secrets/.env).
#
# RR-027 credential hygiene: enrollment values are PARSED out of the store
# with the SHARED dotenv parser (shared-utils/rescue-env.sh) — this script
# no longer executes the store as shell and no longer exports it (`set -a;
# . file` put every credential in the file into this process's exported
# env, inherited by every child from `cron list` onward). Only the two
# required enrollment values are read, into NON-exported variables; nothing
# else in the store is touched. Malformed config fails visibly (rc from the
# parser, reason on stderr) instead of a silent empty value.
set -u

_OCROOT=""
[ -d /data/.openclaw ] && _OCROOT="/data/.openclaw"
[ -z "$_OCROOT" ] && [ -d "$HOME/.openclaw" ] && _OCROOT="$HOME/.openclaw"

# Locate the shared helper beside the skills tree (installed copy) or beside
# this script in the repo tree (repo-side runs / self-tests). Sourced, never
# executed; it defines only functions and exports nothing.
_SHARED_HELPERS=""
for _cand in "$_OCROOT/skills/shared-utils/rescue-env.sh" \
             "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/shared-utils/rescue-env.sh" \
             "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../shared-utils/rescue-env.sh"; do
  [ -n "$_cand" ] && [ -f "$_cand" ] && { _SHARED_HELPERS="$_cand"; break; }
done
[ -n "$_SHARED_HELPERS" ] || { echo "65-rescue-receiver: shared-utils/rescue-env.sh not found (required helper missing)" >&2; exit 0; }
# shellcheck disable=SC1090
. "$_SHARED_HELPERS"

[ -n "$_OCROOT" ] || { echo "65-rescue-receiver: no openclaw root; nothing to wire" >&2; exit 0; }
_SECRETS="$_OCROOT/secrets/.env"
_POLL="$_OCROOT/skills/65-rescue-receiver/rescue-poll.sh"

if [ ! -f "$_SECRETS" ] || [ ! -f "$_POLL" ]; then
  echo "65-rescue-receiver: secrets file or rescue-poll.sh missing; nothing to wire" >&2
  exit 0
fi

# Parse ONLY the required enrollment values — never the whole store, never
# an execution, never an export. rc=2 file missing/unreadable, rc=1/3
# malformed lines (fail visibly per RR-027).
RR_RECEIVER_URL=""
RR_BOX_TOKEN=""
_rc_url=0; _rc_tok=0
RR_RECEIVER_URL=$(rescue_env_get "$_SECRETS" RR_RECEIVER_URL); _rc_url=$?
RR_BOX_TOKEN=$(rescue_env_get "$_SECRETS" RR_BOX_TOKEN); _rc_tok=$?
case "$_rc_url$_rc_tok" in
  22)
    echo "65-rescue-receiver: secrets store unreadable ($_SECRETS) — poll cron NOT registered" >&2
    exit 0
    ;;
  *)
    if [ "$_rc_url" = 3 ] || [ "$_rc_tok" = 3 ] || [ "$_rc_url" = 1 ] || [ "$_rc_tok" = 1 ]; then
      # malformed store lines OR missing required value: both fail visibly.
      # Absence keeps the historical unenrolled behavior (dark, no cron);
      # malformed lines are a NEW visible failure with the reason already on
      # stderr from the parser (line numbers named, values never printed).
      if [ "$_rc_url" = 3 ] || [ "$_rc_tok" = 3 ]; then
        echo "65-rescue-receiver: malformed enrollment config in $_SECRETS (see rescue-env lines above) — poll cron NOT registered" >&2
        exit 1
      fi
    fi
    ;;
esac
if [ -z "${RR_RECEIVER_URL:-}" ] || [ -z "${RR_BOX_TOKEN:-}" ]; then
  echo "65-rescue-receiver: box not enrolled (RR_RECEIVER_URL / RR_BOX_TOKEN absent) — poll cron NOT registered" >&2
  exit 0
fi
# Enrollment values stay NON-exported for the rest of this script: they are
# only existence-checked here, and the poll re-reads the store itself at
# every fire (the cron carries no credential — the cron command is just the
# poll script path).
unset RR_RECEIVER_URL RR_BOX_TOKEN

_NAME="rescue-rr-box-poll"
_LEGACY_NAME="rescue-rangers-poll"
# The updater invokes installers with a stripped environment; on Mac boxes
# /opt/homebrew/bin is NOT on that PATH, so `command -v openclaw` fails even
# though the CLI exists. Fall back to the standard install locations before
# giving up (a hard exit here withholds the .wired sentinel forever).
_OC_BIN=""
if command -v openclaw >/dev/null 2>&1; then
  _OC_BIN="openclaw"
elif [ -x /opt/homebrew/bin/openclaw ]; then
  _OC_BIN="/opt/homebrew/bin/openclaw"
elif [ -x /usr/local/bin/openclaw ]; then
  _OC_BIN="/usr/local/bin/openclaw"
elif [ -x "$HOME/.local/bin/openclaw" ]; then
  _OC_BIN="$HOME/.local/bin/openclaw"
fi
[ -n "$_OC_BIN" ] || { echo "65-rescue-receiver: openclaw CLI not found" >&2; exit 1; }
# The CLI is a node script with a `#!/usr/bin/env node` shebang. Under the
# updater's stripped PATH, `env` cannot resolve node even when the CLI path
# is absolute — so prepend the CLI's own directory (where the toolchain's
# node symlink lives) to PATH before invoking it.
case "$_OC_BIN" in
  */*) _BIN_DIR="${_OC_BIN%/*}"; [ -d "$_BIN_DIR" ] && PATH="$_BIN_DIR:$PATH";;
esac
# Legacy cleanup MUST precede the canonical early-exit below, or boxes wired
# under the old name accumulate a second poller every time this script runs
# (both crons firing = double delivery).
if "$_OC_BIN" cron list --json 2>/dev/null | grep -q "\"name\": *\"$_LEGACY_NAME\""; then
  _LEGACY_ID="$("$_OC_BIN" cron list --json 2>/dev/null | python3 -c 'import json,sys; jobs=json.load(sys.stdin).get("jobs",[]); print(next((j["id"] for j in jobs if j.get("name")=="'"$_LEGACY_NAME"'"), ""))')"
  if [ -n "$_LEGACY_ID" ]; then
    if "$_OC_BIN" cron rm "$_LEGACY_ID" >&2; then
      echo "65-rescue-receiver: removed legacy cron $_LEGACY_NAME (id $_LEGACY_ID)"
    else
      echo "65-rescue-receiver: legacy cron $_LEGACY_NAME rm FAILED (id $_LEGACY_ID); left in place" >&2
    fi
  else
    echo "65-rescue-receiver: legacy cron $_LEGACY_NAME seen in list but id not resolvable; skipping removal" >&2
  fi
fi
if "$_OC_BIN" cron list --json 2>/dev/null | grep -q "\"name\": *\"$_NAME\""; then
  echo "65-rescue-receiver: cron $_NAME already registered"
  exit 0
fi
if "$_OC_BIN" cron add --name "$_NAME" --cron "*/2 * * * *" --no-deliver --command "sh $_POLL" >&2; then
  :
elif "$_OC_BIN" cron add --name "$_NAME" --cron "*/2 * * * *" --command "sh $_POLL" >&2; then
  :
else
  echo "65-rescue-receiver: cron add FAILED" >&2; exit 1
fi
echo "65-rescue-receiver: registered cron $_NAME (*/2) -> sh $_POLL"
