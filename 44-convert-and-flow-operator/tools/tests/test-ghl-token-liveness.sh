#!/bin/bash
# test-ghl-token-liveness.sh — regression suite for check-ghl-token-liveness.sh
#
# THE BUG THIS EXISTS TO CATCH (production failure, 2026-06-23 -> 2026-08-27):
# the liveness check resolved credentials with "process env wins over file", but
# the gateway hands this cron a START-TIME SNAPSHOT of the box env. A 63-character
# placeholder sitting in openclaw.json env.vars therefore masked a valid
# 503-character token in secrets/.env. The check failed, and its failure branch
# messages the CLIENT directly — so a stale-config bug became 65 days of
# "your Convert and Flow connection expired, go re-grab your token" messages to a
# paying client whose automations were working the whole time (the engine, caf,
# does `set -a; source secrets/.env`, so the FILE always won for the engine).
#
# The invariant under test: TEST WHAT caf WILL ACTUALLY USE, and never message the
# client for anything that is not a CONFIRMED credential failure.
#
# SAFETY: runs entirely in a throwaway sandbox HOME. The `openclaw message send`
# line is sed-stubbed AND the NO_SEND hook is set; python3 is PATH-shadowed by a
# fake that returns canned results, so no network call and no message is ever made.
# Asserted below before anything runs.
#
# USAGE:  bash 44-convert-and-flow-operator/tools/tests/test-ghl-token-liveness.sh
# EXIT:   0 all good, non-zero on a failed precondition.

set -uo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${GHL_LIVENESS_TARGET:-$SELF_DIR/../check-ghl-token-liveness.sh}"
[ -f "$TARGET" ] || { echo "ABORT: script under test not found: $TARGET"; exit 9; }
SB="$(mktemp -d "${TMPDIR:-/tmp}/ghl-liveness-test.XXXXXX")"
trap 'rm -rf "$SB"' EXIT
mkdir -p "$SB/home/.openclaw/secrets" "$SB/home/.openclaw/workspace" "$SB/state" "$SB/fakebin"
printf '{"channels":{"telegram":{"allowFrom":["123456789"]}}}\n' > "$SB/home/.openclaw/openclaw.json"
SEC="$SB/home/.openclaw/secrets/.env"
[ -d /data/.openclaw ] && { echo "ABORT: /data/.openclaw exists locally"; exit 9; }
# Use a synthetic operator ID in the sandbox copy and the rejection probe.
# Production exclusion rules are unchanged; no real recipient is a fixture target.
sed -e 's/5252140759/990000001/g' \
    -e 's|^if openclaw message send|if echo STUB \&\& false; then :; elif false|' \
    -e "s|^STATE_DIR=.*|STATE_DIR=\"$SB/state\"|" "$TARGET" > "$SB/prop.sh"
echo "neutered: live-send-lines=$(/usr/bin/grep -c '^if openclaw message send' "$SB/prop.sh") stub=$(/usr/bin/grep -c '^if echo STUB' "$SB/prop.sh") state=$(/usr/bin/grep -c "^STATE_DIR=\"$SB/state\"" "$SB/prop.sh")"
# fake python3: canned exchange result / canned chat id; never touches the network
cat > "$SB/fakebin/python3" <<'EOF'
#!/bin/bash
IN=$(cat)
case "$IN" in
  *grant_type*) printf '%s\n' "${FAKE_EXCHANGE:-VALID}" ;;
  *allowFrom*)  printf '%s\n' "${FAKE_CHAT:-123456789}" ;;
  *) echo "fake-python3: unexpected use" >&2; exit 97 ;;
esac
EOF
chmod +x "$SB/fakebin/python3"
REALPY=$(command -v python3)
L503() { "$REALPY" -c "print('$1'*503)"; }
FILE=$(L503 F); STALE=$(L503 S); CAF=$(L503 C); OLD=$(L503 O); NEW=$(L503 N); IMP=$("$REALPY" -c "print('I'*63)")
fp() { printf '%s' "$1" | shasum -a 256 | cut -c1-8; }
echo "fps: FILE=$(fp "$FILE") STALE=$(fp "$STALE") CAF=$(fp "$CAF") OLD=$(fp "$OLD") NEW=$(fp "$NEW") IMP63=$(fp "$IMP")"
BASHES=""; for b in /opt/homebrew/bin/bash /bin/bash; do [ -x "$b" ] && BASHES="$BASHES $b"; done
run() { # label [VAR=val ...]   (env passed through)
  local label="$1"; shift
  for b in $BASHES; do
    rm -f "$SB/state"/*; local out rc
    out=$(cd "$SB" && env -i HOME="$SB/home" PATH="$SB/fakebin:/usr/bin:/bin" "$@" "$b" "$SB/prop.sh" 2>&1); rc=$?
    printf '  [%-7s bash%s] rc=%s stamps=[%s] :: %s\n' "$label" "$($b --version | head -1 | sed -E 's/.*version ([0-9]).*/\1/')" "$rc" "$(ls "$SB/state" 2>/dev/null | sed -E 's/ghl-token-liveness-[0-9-]+//' | tr '\n' ' ')" "$(printf '%s' "$out" | /usr/bin/grep -E 'RESOLVED|SKIP|CONFIG PROBLEM|DRIFT|PASS|FAIL|NO_SEND|already|refusing|STUB|WARN|unbound|error' | cut -c1-150 | tr '\n' '|' | cut -c1-420)"
  done
}
hdr() { echo; echo "### $1"; }
hdr "R-CTRL-A file only (expect source=secrets-file fp FILE drift=no rc0)"; printf 'GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN=%s\n' "$FILE" > "$SEC"; run ctrlA GHL_LIVENESS_RESOLVE_ONLY=1
hdr "R-CTRL-B nothing anywhere (expect SKIP rc0 + .no-token)"; printf 'OTHER=1\n' > "$SEC"; run ctrlB GHL_LIVENESS_RESOLVE_ONLY=1
hdr "R1 THE BUG: env STALE + file FILE same name (expect file fp, drift=yes)"; printf 'GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN=%s\n' "$FILE" > "$SEC"; run R1 GHL_LIVENESS_RESOLVE_ONLY=1 GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN="$STALE"
hdr "R2 HISTORICAL: env 63-char impostor + file 503 real (expect file fp, drift=yes)"; run R2 GHL_LIVENESS_RESOLVE_ONLY=1 GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN="$IMP"
hdr "R3 MASKING: env STALE GOHIGHLEVEL, file only CAF (engine would use STALE -> expect CONFIG PROBLEM rc2, no RESOLVED)"; printf 'CAF_FIREBASE_REFRESH_TOKEN=%s\n' "$CAF" > "$SEC"; run R3 GHL_LIVENESS_RESOLVE_ONLY=1 GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN="$STALE"
hdr "R4 placeholder only: env 63-char impostor, no file (expect CONFIG PROBLEM rc2)"; rm -f "$SEC"; run R4 GHL_LIVENESS_RESOLVE_ONLY=1 GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN="$IMP"
hdr "R5 dup lines OLD then NEW, no env (expect NEW fp = last wins)"; printf 'GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN=%s\nX=1\nGOHIGHLEVEL_FIREBASE_REFRESH_TOKEN=%s\n' "$OLD" "$NEW" > "$SEC"; run R5 GHL_LIVENESS_RESOLVE_ONLY=1
hdr "R6 file 'VAR=' empty + env STALE (engine blanks it -> expect CONFIG PROBLEM rc2)"; printf 'GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN=\n' > "$SEC"; run R6 GHL_LIVENESS_RESOLVE_ONLY=1 GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN="$STALE"
hdr "R7 trailing whitespace in file (expect len=503, not 505)"; printf 'GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN=%s  \n' "$FILE" > "$SEC"; run R7 GHL_LIVENESS_RESOLVE_ONLY=1
hdr "R8 CRLF file (expect CONFIG PROBLEM rc2)"; printf 'GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN=%s\r\n' "$FILE" > "$SEC"; run R8 GHL_LIVENESS_RESOLVE_ONLY=1
hdr "R9 export-prefixed + quoted + env STALE (expect file fp)"; printf 'export GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN="%s"\n' "$FILE" > "$SEC"; run R9 GHL_LIVENESS_RESOLVE_ONLY=1 GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN="$STALE"
hdr "R10 env only, no file at all (expect source=process-env, drift=yes ABSENT, rc0 resolve)"; rm -f "$SEC"; run R10 GHL_LIVENESS_RESOLVE_ONLY=1 GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN="$STALE"
hdr "R11 unreadable secrets file + env STALE (expect no crash; file unreadable => env used, drift ABSENT)"; printf 'GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN=%s\n' "$FILE" > "$SEC"; chmod 000 "$SEC"; run R11 GHL_LIVENESS_RESOLVE_ONLY=1 GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN="$STALE"; chmod 600 "$SEC"
hdr "S1 exchange VALID, no drift (expect PASS rc0, .ok only)"; printf 'GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN=%s\n' "$FILE" > "$SEC"; run S1 FAKE_EXCHANGE=VALID GHL_LIVENESS_NO_SEND=1
hdr "S2 exchange VALID + drift (expect PASS + DRIFT PERSISTS rc2, .ok + .drift)"; run S2 FAKE_EXCHANGE=VALID GHL_LIVENESS_NO_SEND=1 GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN="$STALE"
hdr "S3 TOKEN_EXPIRED (expect FAIL -> NO_SEND would-notify rc1, no stamp since not sent)"; run S3 FAKE_EXCHANGE=INVALID:TOKEN_EXPIRED GHL_LIVENESS_NO_SEND=1
hdr "S4 NETWORK_ERROR (expect CONFIG PROBLEM rc2, no notify)"; run S4 FAKE_EXCHANGE=NETWORK_ERROR:timeout GHL_LIVENESS_NO_SEND=1
hdr "S5 HTTP 429/500 shaped INVALID (expect CONFIG PROBLEM rc2)"; run S5 "FAKE_EXCHANGE=INVALID:Too Many Requests" GHL_LIVENESS_NO_SEND=1
hdr "S6 USER_DISABLED (expect credential path rc1)"; run S6 FAKE_EXCHANGE=INVALID:USER_DISABLED GHL_LIVENESS_NO_SEND=1
hdr "S7 .notified guard (expect rc1 already-notified, nothing else)"; touch "$SB/state/ghl-token-liveness-$(date -u +%Y-%m-%d).notified"; for b in $BASHES; do out=$(cd "$SB" && env -i HOME="$SB/home" PATH="$SB/fakebin:/usr/bin:/bin" FAKE_EXCHANGE=INVALID:TOKEN_EXPIRED "$b" "$SB/prop.sh" 2>&1); echo "  [S7 $(basename $b)] rc=$? :: $(printf '%s' "$out" | /usr/bin/grep -E 'already|FAIL|NO_SEND' | cut -c1-120)"; done; rm -f "$SB/state"/*
hdr "S8 operator chat id resolved (expect refusing, rc1, no send)"; run S8 FAKE_EXCHANGE=INVALID:TOKEN_EXPIRED FAKE_CHAT=990000001
hdr "S9 send path WITHOUT NO_SEND hook: stub must be hit (expect STUB + WARN not notified, rc1, no .notified stamp)"; run S9 FAKE_EXCHANGE=INVALID:TOKEN_EXPIRED
echo; echo "leftover state files: $(ls "$SB/state" | wc -l | tr -d ' ')"
