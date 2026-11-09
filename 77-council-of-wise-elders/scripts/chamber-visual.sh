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
# It also delivers the visual pop (open <url> in the box's default browser)
# when a desktop session can be reached, and reports what it did on stderr:
#   pop: opened | pop: skipped (<why>) | pop: failed (<why>) | pop: disabled
# The link line is printed no matter what, and the exit code is always 0: a
# missing URL source or a failed pop must never break a convene.
#
# Pop delivery ladder (this is the CTR-103 repair of the old rule, which
# required `launchctl managername` = Aqua in THIS process and therefore never
# popped from a gateway/service subprocess):
#   1. COUNCIL_CHAMBER_OPEN=0 (or --no-open) disables the pop.
#   2. COUNCIL_CHAMBER_GUI=1|0 is an explicit operator override.
#   3. managername Aqua: the process is already in the user's GUI session.
#   4. Otherwise, if the user's GUI session EXISTS (launchctl print gui/<uid>):
#      deliver through that session - `launchctl asuser` when this process can
#      (root), else one direct `open` attempt, reporting the real result.
#   5. No GUI session: pop: skipped, link still printed.
# A gateway that runs as a LaunchAgent in gui/<uid> reports Aqua and pops
# directly; one that runs in a non-GUI domain gets the bridge attempt instead
# of a silent skip.
#
# URL source, best first (this is the authoritative runtime source):
#   1. env COUNCIL_PUBLIC_URL
#   2. env WISE_ELDERS_PUBLIC_ORIGIN  (baked by wire.sh into the CLI shim)
#   3. public_origin in the box's own service.json (env WISE_ELDERS_SERVICE_JSON,
#      else $OPENCLAW_ROOT/council-runtime/service.json)
#   4. the loopback service origin, so the box's own screen always gets the
#      visual even before a public address is provisioned.
#
# Usage: chamber-visual.sh [--session SESSION_ID] [--no-open]
# Test hooks: COUNCIL_CHAMBER_GUI=1 forces a desktop session, =0 forces
# headless; COUNCIL_CHAMBER_OPEN=0 disables the pop; the opener and the GUI
# probes resolve from PATH so tests can stub them.
set -u

session=""
open_disabled=0
while [ $# -gt 0 ]; do
  case "$1" in
    --session) session="${2:-}"; shift 2 ;;
    --session=*) session="${1#--session=}"; shift ;;
    --no-open) open_disabled=1; shift ;;
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

pop_status() { printf 'pop: %s\n' "$1" >&2; }

gui_domain_present() { # 0 when this user's GUI session exists
  command -v launchctl >/dev/null 2>&1 || return 1
  launchctl print "gui/$(id -u)" >/dev/null 2>&1
}

console_uid() { # the login user currently owning the console, or empty
  [ "$(uname -s 2>/dev/null)" = "Darwin" ] || return 0
  _cu="$(stat -f %Su /dev/console 2>/dev/null)"
  case "$_cu" in ''|root|loginwindow) return 0 ;; esac
  id -u "$_cu" 2>/dev/null
}

deliver_pop() { # <url>
  _url="$1"
  if [ "$open_disabled" = 1 ]; then pop_status "disabled (--no-open)"; return 0; fi
  case "${COUNCIL_CHAMBER_OPEN:-}" in
    0|no|off|false|disabled) pop_status "disabled (COUNCIL_CHAMBER_OPEN=0)"; return 0 ;;
  esac
  if ! command -v open >/dev/null 2>&1; then pop_status "skipped (no opener on PATH)"; return 0; fi

  _gui="${COUNCIL_CHAMBER_GUI:-}"
  _mgr="$(launchctl managername 2>/dev/null || true)"
  case "$_gui" in
    0|no|absent) pop_status "skipped (COUNCIL_CHAMBER_GUI=0)"; return 0 ;;
    1|yes|present) _mode="aqua" ;;
    *) if [ "$_mgr" = "Aqua" ]; then _mode="aqua"
       elif gui_domain_present; then _mode="bridge"
       else pop_status "skipped (no GUI session for uid $(id -u); manager ${_mgr:-unknown})"; return 0
       fi ;;
  esac

  if [ "$_mode" = "bridge" ] && [ "$(id -u)" = "0" ]; then
    _cuid="$(console_uid)"
    if [ -n "$_cuid" ] && launchctl asuser "$_cuid" open "$_url" >/dev/null 2>&1; then
      pop_status "opened (via gui session of uid $_cuid)"; return 0
    fi
    pop_status "failed (could not reach the GUI session of uid ${_cuid:-unknown})"; return 0
  fi

  # `open` hands the URL to LaunchServices and returns immediately; it never
  # waits for the browser, so the reply is not blocked on the pop.
  if open "$_url" >/dev/null 2>&1; then
    pop_status "opened"
  else
    pop_status "failed (opener rc=$?; manager ${_mgr:-unknown}; the gateway is not in a GUI session)"
  fi
  return 0
}

printf 'Chamber link: %s\n' "$url"
deliver_pop "$url"
exit 0
