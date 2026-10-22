#!/bin/bash
# chamber-visual.sh (W73) - the Roast Room link and the visual pop on every
# convene, no matter how the client called the council (terminal or chat).
#
# Prints exactly one line to stdout:
#   Chamber link: <url>
# ALWAYS copy that exact line into the reply to the client. The URL is
# resolved at runtime from the box's own configuration - never hardcoded,
# never guessed.
#
# On a desktop (GUI) session it also opens <url> in the default browser:
# fire-and-forget, it never blocks the reply. On a headless box (CI, cron,
# server) it opens nothing and still prints the link.
#
# URL source, best first (this is the authoritative runtime source):
#   1. env COUNCIL_PUBLIC_URL
#   2. env WISE_ELDERS_PUBLIC_ORIGIN  (baked by wire.sh into the CLI shim)
#   3. public_origin in the box's own service.json (env WISE_ELDERS_SERVICE_JSON,
#      else $OPENCLAW_ROOT/council-runtime/service.json)
#   4. the loopback service origin, so the box's own screen always gets the
#      visual even before a public address is provisioned.
#
# Usage: chamber-visual.sh [--session SESSION_ID]
# Test hooks: COUNCIL_CHAMBER_GUI=1 forces a desktop session, =0 forces
# headless; the opener and GUI probe resolve from PATH so tests can stub them.
#
# Exit code is always 0: a missing URL source or a failed pop must never
# break a convene.
set -u

session=""
while [ $# -gt 0 ]; do
  case "$1" in
    --session) session="${2:-}"; shift 2 ;;
    --session=*) session="${1#--session=}"; shift ;;
    *) shift ;;
  esac
done

json_public_origin() {
  # service.json is machine-written with a flat "public_origin" key; a plain
  # text extraction keeps this script dependency-free. ponytail: if the shape
  # ever nests, replace with jq/node.
  [ -f "$1" ] || return 0
  sed -n 's/.*"public_origin"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$1" 2>/dev/null | head -n 1
}

base="${COUNCIL_PUBLIC_URL:-${WISE_ELDERS_PUBLIC_ORIGIN:-}}"
if [ -z "$base" ]; then
  _sj="${WISE_ELDERS_SERVICE_JSON:-}"
  if [ -z "$_sj" ]; then
    _oc="${OPENCLAW_ROOT:-${WISE_ELDERS_OPENCLAW_ROOT:-$HOME/.openclaw}}"
    if [ -d /data/.openclaw ] && [ ! -d "$_oc" ]; then _oc=/data/.openclaw; fi
    _sj="$_oc/council-runtime/service.json"
  fi
  base="$(json_public_origin "$_sj")"
fi
if [ -z "$base" ]; then
  base="${WISE_ELDERS_SERVICE_ORIGIN:-http://127.0.0.1:${COUNCIL_SERVICE_PORT:-8787}}"
fi

url="${base%/}/chamber/"
[ -n "$session" ] && url="$url#session=$session"

gui_present() {
  case "${COUNCIL_CHAMBER_GUI:-}" in
    1|yes|present) return 0 ;;
    0|no|absent) return 1 ;;
  esac
  [ "$(uname -s 2>/dev/null)" = "Darwin" ] || return 1
  [ "$(launchctl managername 2>/dev/null)" = "Aqua" ]
}

printf 'Chamber link: %s\n' "$url"

if gui_present && command -v open >/dev/null 2>&1; then
  # Fire-and-forget: never block the reply on LaunchServices.
  open "$url" >/dev/null 2>&1 &
fi

exit 0
