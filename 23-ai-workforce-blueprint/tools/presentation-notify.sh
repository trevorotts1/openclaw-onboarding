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
if [ -t 0 ]; then
  MSG="${1:-}"
  KIND="${2:-progress}"
  if [ -z "$MSG" ]; then
    echo "ERROR: no message text (stdin JSON or positional args required)" >&2
    exit 1
  fi
  _KIND_JSON="$(printf '%s' "$KIND" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read())[1:-1])')"
  _MSG_JSON="$(printf '%s' "$MSG" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read())[1:-1])')"
  export _KIND_JSON _MSG_JSON
  python3 -c 'import json, os, sys
payload = json.dumps({"chat_id": os.environ.get("OWNER_CHAT_ID", ""),
                      "kind": os.environ["_KIND_JSON"],
                      "message": os.environ["_MSG_JSON"]})
sys.stdout.write(payload)
' | python3 "$CANONICAL"
  exit $?
fi

# stdin path: forward verbatim.
exec python3 "$CANONICAL"
