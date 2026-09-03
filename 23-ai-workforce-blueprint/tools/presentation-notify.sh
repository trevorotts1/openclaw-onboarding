#!/bin/bash
# presentation-notify.sh -- RETIRED (FIX 64, one notification transport).
#
# This script WAS a second, independent notification transport: it read the
# operator bot token and posted straight to api.telegram.org with curl --
# a duplicate of the canonical transport's job, with its own separate
# resolution logic, its own failure modes, and NO gateway-only guarantee.
# Two transports for one department means two places to fix, two places to
# drift, and no single answer to "where did this alert actually go".
#
# FIX 64 retires it. THE transport is now:
#
#     templates/role-library/presentations/scripts/presentation-notify.py
#
# which routes every send through `openclaw message send` (the fleet
# gateway), resolves subsystem labels ("watchdog"/"supervisor"/"capacity")
# to the numeric operator chat id at the transport boundary, and exits 4
# (undeliverable, queued for --sweep-undeliverable) when no numeric target
# can be resolved -- never a silent drop, never a fabricated id.
#
# WHAT THIS FILE DOES NOW: a thin delegation shim, kept only so an old
# PRESENTATION_NOTIFY_CMD on a box that still points here keeps working --
# it forwards the payload (stdin JSON or positional args) to the canonical
# python transport and exits with its code. It never touches a token, never
# talks to api.telegram.org, never makes a delivery decision of its own.
# When the canonical transport is absent (a box whose department scripts
# were never materialised) it exits 2 (transport misconfiguration) loudly,
# so the gap is visible in the log instead of silently un-delivered.
#
# wire.sh still installs this file to ~/.openclaw/tools/ (Darwin) or
# /data/.openclaw/tools/ (Linux) so the delegation stays reachable; the
# recommended PRESENTATION_NOTIFY_CMD now points at presentation-notify.py
# directly (see the watchdog plist template's PRESENTATION_NOTIFY_CMD
# default).
#
# Exit codes mirror the canonical transport's contract:
#   0  -- forwarded and delivered (canonical transport exited 0)
#   1  -- no message text supplied (same as the old protocol A/B contract)
#   2  -- canonical transport not found on this box (loud, visible gap)
#   3  -- canonical transport exists but is not executable
#   *  -- otherwise, the canonical transport's own exit code, passed through
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Canonical transport candidates, nearest-first: the department scripts dir
# beside tools/ (the materialised role-library layout), then the repo layout
# this file itself is committed under.
_CANDIDATES=(
  "${SCRIPT_DIR}/../templates/role-library/presentations/scripts/presentation-notify.py"
  "${SCRIPT_DIR}/../scripts/presentation-notify.py"
)

CANONICAL=""
for _c in "${_CANDIDATES[@]}"; do
  if [ -f "$_c" ]; then
    CANONICAL="$_c"
    break
  fi
done

if [ -z "$CANONICAL" ]; then
  echo "ERROR: tools/presentation-notify.sh is RETIRED (FIX 64) and its canonical replacement presentation-notify.py was not found -- searched:" >&2
  for _c in "${_CANDIDATES[@]}"; do
    echo "  $_c" >&2
  done
  echo "Set PRESENTATION_NOTIFY_CMD to the canonical presentation-notify.py path." >&2
  exit 2
fi

if [ ! -r "$CANONICAL" ]; then
  echo "ERROR: canonical transport $CANONICAL exists but is not readable" >&2
  exit 3
fi

# Protocol A (engine, stdin JSON): pipe through untouched -- the canonical
# transport reads the same payload shape this script used to parse.
# Protocol B (manual, positional "message" [kind]): re-encode as the same
# stdin JSON the engine path uses, so ONE payload shape reaches the
# canonical transport.
#
# FIX 64 (R-B03-B5): Protocol B was previously gated on `[ -t 0 ]` and passed
# the chat id through an ESCAPED heredoc expansion ("\${OWNER_CHAT_ID:-}") --
# the literal string "${OWNER_CHAT_ID:-}" reached the transport as the
# chat_id (proven live through the stub gateway), never the operator id, and
# any positional call from cron/launchd (no tty) fell through to the stdin
# path and died on "stdin is not valid JSON". Both defects are closed here:
#   - ONE protocol: positional args present -> JSON is BUILT by python
#     (correct quoting, no shell interpolation holes) and piped to the
#     transport; no positional args -> stdin is forwarded verbatim. No tty
#     sniffing: cron/launchd/manual all take the same path.
#   - chat_id: OWNER_CHAT_ID is expanded by the SHELL (not escaped in a
#     heredoc) and may legitimately be empty -- the canonical transport's
#     FIX 64 boundary resolves a non-numeric id (or an empty payload chat_id
#     via its own OWNER_CHAT_ID fallback tier) and exits 4 (undeliverable,
#     queued for --sweep-undeliverable) rather than ever fabricating a target.
_CHAT_ID="${OWNER_CHAT_ID:-}"
if [ -n "${1:-}" ]; then
  PAYLOAD="$(python3 -c 'import json,sys
kind = sys.argv[1]
message = sys.argv[2]
chat_id = sys.argv[3]
sys.stdout.write(json.dumps({"chat_id": chat_id, "kind": kind, "message": message}))' \
      "${2:-progress}" "$1" "$_CHAT_ID")" || {
    echo "ERROR: could not build the transport payload" >&2
    exit 1
  }
  printf '%s\n' "$PAYLOAD" | python3 "$CANONICAL"
  exit $?
fi

# stdin path: forward verbatim.
exec python3 "$CANONICAL"
