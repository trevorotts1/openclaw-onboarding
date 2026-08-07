#!/usr/bin/env bash
# ghl-mcp-env-credential-guard.test.sh
#
# MUTATION PROOF for BLOCKER 1: scripts/ghl-mcp-autostart.sh must never replace a
# WORKING GHL token/location pairing with an unproven one, and must never rewrite
# the server .env without a verified backup.
#
# WHAT THIS IS PROVING, and why it needs a real proof rather than a lint.
# The live incident (operator box, 2026-08-03) was: same token, .env location
# -> HTTP 200; the value the installer wrote over it -> HTTP 403 "The token does
# not have access to this location." main.js testConnection()s at boot and
# exit(1)s, so the server went down and STAYED down, and nothing had kept a copy
# of the working file. A check that merely greps for the word "backup" would go
# green on a fix that still clobbers. So this test drives the REAL function with
# a stub `curl` on PATH and asserts the BYTES that end up in .env.
#
# NO NETWORK. The stub curl is a plain script earlier on PATH; the production
# code is untouched (no test-only seam, no injected command variable).
#
# Extraction, not re-implementation: the block between the
# GHL-MCP-ENV-CREDENTIAL-GUARD markers in the real script is sourced verbatim,
# the same pattern scripts/test-updater-traps-1-and-3.sh uses. A copy of the
# logic here could pass while the shipped file regressed.
#
# Exit 0 = every case behaved. Exit 1 = a case regressed (details on stderr).

set -uo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SELF_DIR/../.." && pwd)"
SRC="$REPO_ROOT/scripts/ghl-mcp-autostart.sh"

FAILURES=0
pass() { printf '  PASS  %s\n' "$*"; }
fail() { printf '  FAIL  %s\n' "$*" >&2; FAILURES=$((FAILURES+1)); }

[ -f "$SRC" ] || { printf 'FATAL: %s not found\n' "$SRC" >&2; exit 1; }

# ── Extract the guarded block verbatim ───────────────────────────────────────
BLOCK="$(mktemp "${TMPDIR:-/tmp}/ghl-env-guard-block.XXXXXX")"
awk '/^# >>> GHL-MCP-ENV-CREDENTIAL-GUARD-BEGIN/{f=1;next} /^# <<< GHL-MCP-ENV-CREDENTIAL-GUARD-END/{f=0} f' \
  "$SRC" > "$BLOCK"
if [ ! -s "$BLOCK" ]; then
  printf 'FATAL: the GHL-MCP-ENV-CREDENTIAL-GUARD markers are missing from %s.\n' "$SRC" >&2
  printf '       The credential guard cannot be proven, so this test fails closed.\n' >&2
  rm -f "$BLOCK"; exit 1
fi

# The block must still contain the load-bearing pieces. A refactor that deletes
# the validation or the backup would otherwise make every case below vacuous.
for _needle in 'resolve_location_id' '_backup_server_env' '_ghl_location_verdict' 'cmp -s'; do
  grep -qF "$_needle" "$BLOCK" \
    || { printf 'FATAL: extracted block no longer contains %s\n' "$_needle" >&2; rm -f "$BLOCK"; exit 1; }
done

# ── Harness ──────────────────────────────────────────────────────────────────
# Builds a throwaway "box": an MCP dir, a stub curl whose verdict per location
# id is scripted by the caller, and the extracted functions.
#
#   run_case <name> <existing .env location or ""> <candidate GHL_LOC> \
#            <OK location ids, space separated> <403 location ids, space separated>
# Leaves the resulting .env at $CASE_DIR/.env and the log at $CASE_DIR/run.log.
run_case() {
  CASE_NAME="$1"; _existing="$2"; _candidate="$3"; _ok_ids="$4"; _403_ids="$5"
  CASE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/ghl-env-case.XXXXXX")"
  mkdir -p "$CASE_DIR/mcp" "$CASE_DIR/bin"

  cat > "$CASE_DIR/bin/curl" <<STUBEOF
#!/usr/bin/env bash
# Stub curl. Prints only an HTTP status code, exactly like
# 'curl -s -o /dev/null -w %{http_code}'. Never touches the network.
_url=""
for _a in "\$@"; do
  case "\$_a" in https://*) _url="\$_a" ;; esac
done
_loc="\${_url##*/}"
for _o in ${_ok_ids}; do [ "\$_loc" = "\$_o" ] && { printf '200'; exit 0; }; done
for _b in ${_403_ids}; do [ "\$_loc" = "\$_b" ] && { printf '403'; exit 0; }; done
printf '000'
exit 0
STUBEOF
  chmod +x "$CASE_DIR/bin/curl"

  if [ -n "$_existing" ]; then
    cat > "$CASE_DIR/mcp/.env" <<EOF
GHL_API_KEY=tok-EXISTING
GHL_BASE_URL=https://services.leadconnectorhq.com
GHL_LOCATION_ID=${_existing}
PORT=8765
MCP_SERVER_PORT=8765
GHL_TOOL_PROFILE=curated
GHL_MCP_BIND_HOST=127.0.0.1
NODE_ENV=production
EOF
    chmod 600 "$CASE_DIR/mcp/.env"
  fi

  (
    set -u
    PATH="$CASE_DIR/bin:$PATH"; export PATH
    log() { printf '  [ghl-mcp-autostart] %s\n' "$*"; }
    MCP_DIR="$CASE_DIR/mcp"
    GHL_TOKEN="tok-TEST"
    GHL_LOC="$_candidate"
    GHL_MCP_PORT=8765
    GHL_MCP_TOOL_PROFILE="curated"
    GHL_MCP_BIND_HOST="127.0.0.1"
    # shellcheck disable=SC1090
    . "$BLOCK"
    write_server_env
  ) > "$CASE_DIR/run.log" 2>&1
  CASE_RC=$?
  CASE_ENV="$CASE_DIR/mcp/.env"
  CASE_LOC="$(sed -n 's/^GHL_LOCATION_ID=//p' "$CASE_ENV" 2>/dev/null | tail -1)"
  CASE_BAKS="$(ls -1 "$CASE_DIR/mcp/".env.bak-* 2>/dev/null | wc -l | tr -d ' ')"
}

printf 'ghl-mcp-env-credential-guard: BLOCKER 1 — never clobber a working credential pairing\n\n'

# ── CASE 1 (THE LIVE INCIDENT). Working value on disk, configured value is 403.
#    MUST keep the working one. This is the case that took the box down.
run_case "live incident" "WORKINGLOC" "BROKENLOC" "WORKINGLOC" "BROKENLOC"
if [ "$CASE_LOC" = "WORKINGLOC" ]; then
  pass "403 candidate REJECTED — the working on-disk location was kept (server stays up)"
else
  fail "403 candidate was written anyway (GHL_LOCATION_ID=$CASE_LOC) — this is the outage, unfixed"
fi
grep -q 'NOT OVERWRITTEN' "$CASE_DIR/run.log" \
  && pass "the refusal is LOUD (operator sees why, and what to fix)" \
  || fail "the refusal was silent — an operator would never learn the configured value is wrong"

# ── CASE 2 (the fix must not be a blanket refusal). Configured value validates,
#    on-disk one does not: the new value MUST be adopted, or a legitimate
#    location change could never be rolled out.
run_case "legitimate change" "STALELOC" "GOODLOC" "GOODLOC" "STALELOC"
if [ "$CASE_LOC" = "GOODLOC" ]; then
  pass "validated candidate ADOPTED — a real location change still rolls out"
else
  fail "validated candidate was NOT adopted (GHL_LOCATION_ID=$CASE_LOC) — the guard is over-broad"
fi

# ── CASE 3 (cannot tell != permission to clobber). Both probes return 000
#    (offline / curl blocked). The existing value must survive.
run_case "undeterminable" "WORKINGLOC" "OTHERLOC" "" ""
if [ "$CASE_LOC" = "WORKINGLOC" ]; then
  pass "undeterminable pairing KEPT the on-disk value (an unproven candidate never wins)"
else
  fail "an UNPROVEN candidate overwrote the on-disk value (GHL_LOCATION_ID=$CASE_LOC)"
fi

# ── CASE 4. An EMPTY candidate must never blank a populated location.
run_case "empty candidate" "WORKINGLOC" "" "WORKINGLOC" ""
if [ "$CASE_LOC" = "WORKINGLOC" ]; then
  pass "empty candidate did NOT blank the existing location"
else
  fail "empty candidate blanked/changed the location (GHL_LOCATION_ID=$CASE_LOC)"
fi

# ── CASE 5. A backup must exist whenever the file actually changed.
run_case "backup on change" "STALELOC" "GOODLOC" "GOODLOC" "STALELOC"
if [ "${CASE_BAKS:-0}" -ge 1 ]; then
  pass "a timestamped backup was taken before the rewrite ($CASE_BAKS present)"
else
  fail "the .env was rewritten with NO backup — the exact condition that forced a Time Machine restore"
fi

# ── CASE 6. Idempotence: a run that changes nothing must not write, and must
#    not litter a backup on every roll.
run_case "idempotent no-op" "SAMELOC" "SAMELOC" "SAMELOC" ""
_before="$(cat "$CASE_ENV")"
(
  set -u
  PATH="$CASE_DIR/bin:$PATH"; export PATH
  log() { :; }
  MCP_DIR="$CASE_DIR/mcp"; GHL_TOKEN="tok-TEST"; GHL_LOC="SAMELOC"
  GHL_MCP_PORT=8765; GHL_MCP_TOOL_PROFILE="curated"; GHL_MCP_BIND_HOST="127.0.0.1"
  # shellcheck disable=SC1090
  . "$BLOCK"; write_server_env
) >/dev/null 2>&1
_after="$(cat "$CASE_ENV")"
_baks2="$(ls -1 "$CASE_DIR/mcp/".env.bak-* 2>/dev/null | wc -l | tr -d ' ')"
if [ "$_before" = "$_after" ]; then
  pass "re-running left the .env byte-identical"
else
  fail "re-running rewrote the .env — not idempotent"
fi
if [ "${_baks2:-0}" -le 1 ]; then
  pass "a no-op re-run did not leave another backup behind"
else
  fail "a no-op re-run wrote another backup ($_baks2) — every roll would litter the box"
fi

# ── CASE 7. Backup impossible => rewrite REFUSED, file untouched. Proven by
#    making the directory read-only so cp cannot create the sibling backup.
CASE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/ghl-env-case.XXXXXX")"
mkdir -p "$CASE_DIR/mcp" "$CASE_DIR/bin"
printf 'GHL_LOCATION_ID=WORKINGLOC\n' > "$CASE_DIR/mcp/.env"
_orig="$(cat "$CASE_DIR/mcp/.env")"
chmod 500 "$CASE_DIR/mcp"
(
  set -u
  log() { :; }
  MCP_DIR="$CASE_DIR/mcp"; GHL_TOKEN="tok-TEST"; GHL_LOC="WORKINGLOC"
  GHL_MCP_PORT=8765; GHL_MCP_TOOL_PROFILE="curated"; GHL_MCP_BIND_HOST="127.0.0.1"
  # shellcheck disable=SC1090
  . "$BLOCK"; write_server_env
) >/dev/null 2>&1
_rc7=$?
chmod 700 "$CASE_DIR/mcp"
if [ "$(cat "$CASE_DIR/mcp/.env")" = "$_orig" ]; then
  pass "no-backup-possible REFUSED the rewrite and left the file untouched (rc=$_rc7)"
else
  fail "the .env was rewritten even though no backup could be taken"
fi

# ── CASE 8. Root privilege makes CASE 7 unenforceable (root ignores mode bits),
#    so state that plainly rather than reporting a pass that was never tested.
if [ "$(id -u 2>/dev/null || echo 1)" = "0" ]; then
  printf '  NOTE  running as root: CASE 7 cannot be enforced by mode bits and is informational here.\n'
fi

rm -f "$BLOCK"
printf '\n'
if [ "$FAILURES" -gt 0 ]; then
  printf 'ghl-mcp-env-credential-guard: %s FAILURE(S) — the installer can still destroy a working credential pairing.\n' "$FAILURES" >&2
  exit 1
fi
printf 'ghl-mcp-env-credential-guard: all cases passed.\n'
exit 0
