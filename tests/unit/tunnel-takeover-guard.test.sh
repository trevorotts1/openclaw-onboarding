#!/usr/bin/env bash
# tests/unit/tunnel-takeover-guard.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# Regression lock for the "second connector silently takes the live tunnel"
# outage (2026-11-06: two client boxes, both dead links).
#
# ROOT CAUSE guarded here: a Mac can serve one useful connector per installed
# cloudflared service, and more than one installer writes a connector token for
# that box (Skill-38's `cloudflared service install`, Skill-32's CC daemon).
# Whichever runs last wins the live connector; the other tunnel drops to 0
# connections while DNS still points at it, so the link answers Cloudflare
# Access and then dies with CF 1033 / 502 after login.
#
# Asserts:
#   1. no installed service            -> allowed
#   2. same tunnel already installed   -> allowed (idempotent re-run)
#   3. a DIFFERENT tunnel installed    -> REFUSED, exit 11, names the other tunnel
#   4. FORCE_TUNNEL_TAKEOVER=1         -> allowed (deliberate displacement)
#   5. tunnel id is read from a token  -> correct id, token never printed
#   6. both installers call the guard  -> wiring lock
#
# Hermetic: fake HOME + fake launchd dirs, no network, no sudo, no real token.
# bash 3.2-safe. Exit 0 = pass, 1 = fail.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GUARD="$REPO_ROOT/shared-utils/tunnel-takeover-guard.sh"
S38="$REPO_ROOT/38-conversational-ai-system/scripts/13-create-cloudflare-tunnel.sh"
CCD="$REPO_ROOT/32-command-center-setup/scripts/setup-tunnel-daemon.sh"

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
eq()   { if [ "$1" = "$2" ]; then pass "$3"; else fail "$3 (got '$1' want '$2')"; fi; }

echo "=== tunnel-takeover-guard.test.sh ==="
for f in "$GUARD" "$S38" "$CCD"; do
  [ -f "$f" ] || { echo "  FAIL: required file not found: $f"; exit 1; }
done

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
export HOME="$WORK/home"; mkdir -p "$HOME"
export TTG_LAUNCHD_DIR="$WORK/daemons"; mkdir -p "$TTG_LAUNCHD_DIR"
export TTG_AGENT_DIR="$WORK/agents"; mkdir -p "$TTG_AGENT_DIR"
TOK_A="11111111-1111-1111-1111-111111111111"
TOK_B="22222222-2222-2222-2222-222222222222"

mk_token_file() {  # <path> <tunnel-id>
  python3 - "$1" "$2" <<'PY'
import base64, json, sys
blob = json.dumps({"a": "acct", "t": sys.argv[2], "s": "SECRET-MUST-NOT-PRINT"}).encode()
open(sys.argv[1], "wb").write(base64.b64encode(blob))
PY
}
mk_plist() {  # <dir> <label> <token-file>
  printf '<?xml version="1.0"?><plist version="1.0"><dict><key>Label</key><string>%s</string><key>ProgramArguments</key><array><string>cloudflared</string><string>--token-file</string><string>%s</string></array></dict></plist>\n' \
    "$2" "$3" > "$1/$2.plist"
}

# shellcheck source=/dev/null
. "$GUARD"

echo "-- 1. no installed service"
rm -f "$TTG_LAUNCHD_DIR"/*.plist "$TTG_AGENT_DIR"/*.plist 2>/dev/null
guard_tunnel_takeover "$TOK_A" "" 2>/dev/null; eq "$?" "0" "clean box is allowed"

echo "-- 2. same tunnel already installed"
mk_token_file "$WORK/tokA" "$TOK_A"
mk_plist "$TTG_AGENT_DIR" "com.cloudflare.cloudflared" "$WORK/tokA"
guard_tunnel_takeover "$TOK_A" "" 2>/dev/null; eq "$?" "0" "re-installing the same tunnel is allowed"

echo "-- 3. a DIFFERENT tunnel is installed"
mk_token_file "$WORK/tokB" "$TOK_B"
mk_plist "$TTG_AGENT_DIR" "com.cloudflare.rescue" "$WORK/tokB"
OUT="$(guard_tunnel_takeover "$TOK_A" "" 2>&1)"; RC=$?
eq "$RC" "11" "different tunnel is refused"
case "$OUT" in *"$TOK_B"*) pass "refusal names the tunnel that would go dark";; *) fail "refusal does not name the conflicting tunnel";; esac
case "$OUT" in *SECRET-MUST-NOT-PRINT*) fail "refusal leaked the connector secret";; *) pass "connector secret never printed";; esac

echo "-- 4. FORCE_TUNNEL_TAKEOVER=1"
FORCE_TUNNEL_TAKEOVER=1 guard_tunnel_takeover "$TOK_A" "" 2>/dev/null
eq "$?" "0" "explicit override allows deliberate displacement"

echo "-- 5. tunnel id from a token on stdin"
mk_token_file "$WORK/tokC" "$TOK_B"
eq "$(cat "$WORK/tokC" | ttg_token_tunnel_id_stdin)" "$TOK_B" "stdin token decodes to the right tunnel id"
eq "$(ttg_token_tunnel_id "$WORK/tokC")" "$TOK_B" "file token decodes to the right tunnel id"
printf 'not-a-token' | ttg_token_tunnel_id_stdin >/dev/null 2>&1
eq "$?" "0" "garbage token is ignored, not fatal"

echo "-- 6. both installers call the guard"
grep -q 'guard_tunnel_takeover' "$S38" \
  && pass "Skill-38 tunnel script calls the guard" \
  || fail "Skill-38 tunnel script does not call the guard"
grep -q 'guard_tunnel_takeover' "$CCD" \
  && pass "CC daemon installer calls the guard" \
  || fail "CC daemon installer does not call the guard"

echo
echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
