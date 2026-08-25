#!/usr/bin/env bash
# 65-rescue-receiver/wire.sh — idempotent box-side wiring for the RR coaching poll.
# Registers the */2-minute command cron ONLY when the box is enrolled
# (RR_RECEIVER_URL + RR_BOX_TOKEN present in <ocroot>/secrets/.env).
set -u

_OCROOT=""
[ -d /data/.openclaw ] && _OCROOT="/data/.openclaw"
[ -z "$_OCROOT" ] && [ -d "$HOME/.openclaw" ] && _OCROOT="$HOME/.openclaw"
[ -n "$_OCROOT" ] || { echo "65-rescue-receiver: no openclaw root; nothing to wire" >&2; exit 0; }
_SECRETS="$_OCROOT/secrets/.env"
_POLL="$_OCROOT/skills/65-rescue-receiver/rescue-poll.sh"

if [ ! -f "$_SECRETS" ] || [ ! -f "$_POLL" ]; then
  echo "65-rescue-receiver: secrets file or rescue-poll.sh missing; nothing to wire" >&2
  exit 0
fi

set -a; . "$_SECRETS" 2>/dev/null; set +a
if [ -z "${RR_RECEIVER_URL:-}" ] || [ -z "${RR_BOX_TOKEN:-}" ]; then
  echo "65-rescue-receiver: box not enrolled (RR_RECEIVER_URL / RR_BOX_TOKEN absent) — poll cron NOT registered" >&2
  exit 0
fi

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
