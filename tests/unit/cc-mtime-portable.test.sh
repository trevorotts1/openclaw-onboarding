#!/usr/bin/env bash
# cc-mtime-portable.test.sh — run-full-install.sh's _cc_mtime must print a plain
# integer under GNU (Linux) AND BSD (Mac) stat, and the installer's `-gt`
# comparison must survive `set -u`.
#
# THE LIVE BUG: `stat -f %m f || stat -c %Y f` on GNU prints six lines of
# FILESYSTEM status ("File: ... ID: ...") before failing over, so the
# post-update assertion's [[ "$build_id_mtime" -gt "$pull_ts" ]] died on
# "File: unbound variable" (rc 127) on every VPS box, ending the Command Center
# refresh before Phase 6i. Sources the REAL function from the installer.
set -uo pipefail
P="[cc-mtime-portable]"; PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "$P PASS: $*"; }
fail() { FAIL=$((FAIL+1)); echo "$P FAIL: $*" >&2; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RFI="$ROOT/32-command-center-setup/scripts/run-full-install.sh"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
awk '/^_cc_mtime\(\)/{p=1} p{print} p&&/}$/{exit}' "$RFI" > "$TMP/fn.sh"
[[ -s "$TMP/fn.sh" ]] || { echo "$P FATAL: _cc_mtime not found in $RFI" >&2; exit 1; }
touch "$TMP/BUILD_ID"

# One PATH per stat flavour available here. CI (ubuntu) has GNU natively; a Mac
# has BSD natively and GNU as gstat (coreutils) -- shim it in as `stat`.
declare -a FLAVOURS=("native:$PATH")
if command -v gstat >/dev/null 2>&1; then
  mkdir -p "$TMP/gnu"; ln -s "$(command -v gstat)" "$TMP/gnu/stat"
  FLAVOURS+=("gnu-shim:$TMP/gnu:$PATH")
fi
stat --version >/dev/null 2>&1 && echo "$P native stat is GNU" || echo "$P native stat is BSD"

for f in "${FLAVOURS[@]}"; do
  name="${f%%:*}"; path="${f#*:}"
  out="$(PATH="$path" bash -c 'set -u; source "$1"; v="$(_cc_mtime "$2")"; pull_ts=5
    if [[ "$v" -gt "$pull_ts" ]]; then echo "ok:$v"; else echo "le:$v"; fi' _ "$TMP/fn.sh" "$TMP/BUILD_ID" 2>&1)"; rc=$?
  if [[ $rc -eq 0 && "$out" =~ ^ok:[0-9]+$ ]]; then
    pass "$name stat: integer mtime, -gt comparison survives set -u ($out)"
  else
    fail "$name stat: rc=$rc output=$(printf '%s' "$out" | head -2 | tr '\n' ' ')"
  fi
  miss="$(PATH="$path" bash -c 'set -u; source "$1"; _cc_mtime "$2"' _ "$TMP/fn.sh" "$TMP/absent" 2>&1)"
  [[ "$miss" == "0" ]] && pass "$name stat: missing file -> 0" || fail "$name stat: missing file -> '$miss'"
done

echo "$P Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
