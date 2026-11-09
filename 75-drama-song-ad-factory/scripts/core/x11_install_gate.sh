#!/bin/bash
# S75-X11 installer/updater call site. install.sh and update-skills.sh run this
# for skill 75 BEFORE they touch the installed copy. It wraps release_gate_cli.py
# (the merged manifest / tar-member / per-file-sha / deletion guard).
#
#   x11_install_gate.sh                 run the gate, exit code below
#   x11_install_gate.sh preserve-list   print the (safe, relative) paths named in
#                                       <records>/reviewed-manifest.json, one per
#                                       line; empty when there is no manifest
#
# Exit codes (the only ones this script emits):
#   0   gate ALLOWED the apply (authorized, targeted backup verified)
#   10  warn-and-preserve: no s75.x11.backup-authorization/v1 record and no
#       explicit refuse flag. Logged only; the caller must NOT fail, and must
#       keep every file in `preserve-list` (the manifest's targeted files) even
#       if the new release does not ship it. With no manifest the list is empty
#       and the update behaves exactly as it always did.
#   20  REFUSED: refuse mode is on and the gate said no (or could not run).
#
# Refuse mode is on only when <records>/backup-authorization.json exists or
# S75_X11_GATE_MODE=refuse. Default is warn-and-preserve so fleet rolls never
# break an existing install. Records dir: S75_X11_RECORDS_DIR, else
# ${OPENCLAW_HOME:-$HOME/.openclaw}/s75-x11-records. This script never creates
# a backup, never deletes, never writes.
HERE="$(cd "$(dirname "$0")" && pwd)"
RECORDS="${S75_X11_RECORDS_DIR:-${OPENCLAW_HOME:-$HOME/.openclaw}/s75-x11-records}"
CLI="${S75_X11_GATE_CLI:-$HERE/release_gate_cli.py}"

if [ "${1:-}" = "preserve-list" ]; then
  python3 -I -c '
import json, sys
try:
    files = json.load(open(sys.argv[1])).get("files", [])
except Exception:
    files = []
for f in files if isinstance(files, list) else []:
    p = f.get("path") if isinstance(f, dict) else None
    if isinstance(p, str) and p and not p.startswith("/") and ".." not in p.split("/") and "\n" not in p:
        print(p)
' "$RECORDS/reviewed-manifest.json" 2>/dev/null
  exit 0
fi

mode=warn
[ "${S75_X11_GATE_MODE:-}" = "refuse" ] && mode=refuse
[ -f "$RECORDS/backup-authorization.json" ] && mode=refuse

say() { echo "  [x11-gate] $*"; }

fail() {  # $1 = reason
  if [ "$mode" = "refuse" ]; then
    say "REFUSED (refuse mode): $1 -- skill 75 left untouched"
    exit 20
  fi
  say "WARN (warn-and-preserve; no backup-authorization record): $1"
  say "WARN: manifest-targeted skill-75 files are kept, never deleted; the roll continues"
  exit 10
}

command -v python3 >/dev/null 2>&1 || fail "python3 not on PATH, gate cannot run"
[ -f "$CLI" ] || fail "release_gate_cli.py not found at $CLI"

out="$(python3 -I "$CLI" apply --records "$RECORDS" 2>&1)"
rc=$?
if [ "$rc" -eq 0 ]; then
  say "ALLOW: gate passed for $RECORDS"
  exit 0
fi
fail "gate said no (rc=$rc): $(echo "$out" | tr '\n' ' ' | cut -c1-300)"
