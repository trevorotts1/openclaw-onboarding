#!/usr/bin/env bash
# tests/rescue/RR-004/test_receiver_additive_fields.sh — ONB-side RR-004 gate.
#
# Pins the ADDITIVE receiver pairing (SPEC RR-004 shared rollout contract):
#   1. RECEIVER_VERSION advanced to the additive version (1.4.0),
#   2. _parse_claim extracts attempt_id / attempt_generation /
#      lease_expires_at when the server sends them, and leaves them EMPTY when
#      it does not (pre-RR-004 server fixture),
#   3. the ack body echoes the attempt identity VERBATIM (and omits the fields
#      when empty — old servers see no change),
#   4. a pre-RR-004 claim (no attempt fields) still parses and acks cleanly —
#      the receiver must not gate on the new fields yet (strict mode comes
#      only after the additive server contract is confirmed).
#
# Sanitized fixtures only (synthetic box slug, synthetic token file). The
# script's network surface is exercised through the same _post override path
# the fixture uses — no real webhook is contacted.
#
# Run: bash tests/rescue/RR-004/test_receiver_additive_fields.sh

set -u
PASS=0
FAIL=0
say_ok() { PASS=$((PASS+1)); echo "  ok $1"; }
say_fail() { FAIL=$((FAIL+1)); echo "  FAIL $1 ${2:-}"; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
POLL="$REPO/65-rescue-receiver/rescue-poll.sh"

echo "== RR-004 ONB: receiver additive claim/ack fields =="

[ -f "$POLL" ] && say_ok "rescue-poll.sh exists" || say_fail "rescue-poll.sh missing" "$POLL"

# 1. version advanced
# RR-027 note: this assertion pins the ADDITIVE FLOOR (>= 1.4.0), not the
# exact string — the RR-027 credential-hygiene slice legitimately advanced
# RECEIVER_VERSION again (1.5.0) and pinning an exact value would make every
# later additive bump break this gate.
ver="$(grep -E '^RECEIVER_VERSION=' "$POLL" | head -1 | cut -d'"' -f2)"
case "$ver" in
  1.4.*|1.[5-9].*|[2-9].*) say_ok "RECEIVER_VERSION carries the additive floor (>=1.4.0): $ver" ;;
  *) say_fail "RECEIVER_VERSION" "got $ver" ;;
esac
pkg="$(cat "$REPO/65-rescue-receiver/skill-version.txt" | tr -d '[:space:]')"
case "$pkg" in
  v23.[1-9]*|v2[4-9]*) say_ok "skill package bumped past v23.1.0: $pkg" ;;
  *) say_fail "skill-version.txt" "got $pkg" ;;
esac

# 2. additive parse fields present
for f in attempt_id attempt_generation lease_expires_at; do
  grep -q "_json_field \"\$_pc_resp\" \"$f\"" "$POLL" && say_ok "_parse_claim extracts $f" || say_fail "_parse_claim missing $f"
done

# 3. ack body echoes attempt identity; omitted when empty
grep -q 'attempt_id' "$POLL" && grep -q '_attempt_json' "$POLL" && say_ok "ack body carries the attempt-echo block" || say_fail "ack attempt-echo block"

# 4. functional fixture: source the poll script's functions in a sandbox and
#    drive _parse_claim/_ack against synthetic claim responses.
FIX="$(mktemp -d)"
trap 'rm -rf "$FIX"' EXIT
cat > "$FIX/rrbox.env" <<'ENVEOF'
RR_BOX_SLUG=box-synthetic
RR_URL=http://127.0.0.1:1/never-contacted
RR_BOX_TOKEN=synthetic-token-value
ENVEOF
# A stub _json_field good enough for flat string/number fields.
stub_json_field() {
  python3 - "$1" "$2" <<'PYEOF'
import json,sys
try:
    doc=json.loads(sys.argv[2])
except Exception:
    print(""); raise SystemExit
v=doc.get(sys.argv[1],"")
print("" if v is None else str(v))
PYEOF
}
export -f stub_json_field
JSON_FIELD_STUB=1

# extract the exact functions we need. NAME-anchored, not line-anchored
# (a hardcoded line number broke the moment any edit above shifted the
# file — the extraction silently sliced into the middle of _parse_claim
# and produced a stray ';;'). Each function is cut from its own
# definition line to its first column-0 closing brace.
extract_fn() {  # extract_fn <file> <fn-name>
  local f="$1" fn="$2" s e
  s="$(grep -n "^${fn}()" "$f" | head -1 | cut -d: -f1)"
  [ -n "$s" ] || { echo "EXTRACT-MISSING ${fn}" >&2; return 1; }
  e="$(awk -v s="$s" 'NR>=s && /^}/ {print NR; exit}' "$f")"
  [ -n "$e" ] || { echo "EXTRACT-UNTERMINATED ${fn}" >&2; return 1; }
  sed -n "${s},${e}p" "$f"
}
{
  extract_fn "$POLL" _json_field
  extract_fn "$POLL" _json_str
  extract_fn "$POLL" _parse_claim
  extract_fn "$POLL" _ack
  echo '_log() { :; }'
  echo "_ack_capture=\"$FIX/captured-body.txt\""
  echo '_post() { printf '"'"'%s'"'"' "$_ack_body" >> "$_ack_capture"; return 0; }'
} > "$FIX/funcs.sh"

bash -n "$FIX/funcs.sh" && say_ok "extracted functions parse" || say_fail "extracted functions syntax"

# fixture A: MODERN claim (with attempt fields)
MODERN='{"status":"instruction","instruction_id":"ins-syn-1","idempotency_key":"idem-syn-1","ticket_id":"RRT-syn","agent_id":"main","session_key":"sess-syn","payload_b64":"aGVsbG8=","mode":"live","attempt_id":"tok-syn-123","attempt_generation":2,"lease_expires_at":"2026-09-09T12:00:00.000Z"}'
# fixture B: LEGACY claim (pre-RR-004, no attempt fields)
LEGACY='{"status":"instruction","instruction_id":"ins-syn-2","idempotency_key":"idem-syn-2","ticket_id":"RRT-syn2","agent_id":"main","session_key":"sess-syn2","payload_b64":"aGVsbG8=","mode":"live"}'

FIX_SCRIPT="$FIX/run.sh"
cat > "$FIX_SCRIPT" <<OUTER
source "$FIX/funcs.sh"

_parse_claim '$MODERN'
echo "MODERN attempt_id=[\$ATTEMPT_ID] gen=[\$ATTEMPT_GENERATION] lease=[\$LEASE_EXPIRES_AT] rc_ok"
_parse_claim '$LEGACY'
echo "LEGACY attempt_id=[\$ATTEMPT_ID] gen=[\$ATTEMPT_GENERATION] lease=[\$LEASE_EXPIRES_AT] rc_ok"
OUTER
OUT="$(bash "$FIX_SCRIPT" 2>&1)"
echo "$OUT" | grep -q 'MODERN attempt_id=\[tok-syn-123\] gen=\[2\] lease=\[2026-09-09T12:00:00.000Z\] rc_ok' \
  && say_ok "modern claim parses attempt fields" || say_fail "modern claim parse" "$OUT"
echo "$OUT" | grep -q 'LEGACY attempt_id=\[\] gen=\[\] lease=\[\] rc_ok' \
  && say_ok "legacy claim parses with EMPTY attempt fields (no gating)" || say_fail "legacy claim parse" "$OUT"

# ack-echo fixture: with attempt fields set, the body carries them verbatim
ACK_SCRIPT="$FIX/ack.sh"
cat > "$ACK_SCRIPT" <<OUTER3
source "$FIX/funcs.sh"
INSTRUCTION_ID="ins-syn-1"
IDEMPOTENCY_KEY="idem-syn-1"
ATTEMPT_ID="tok-syn-123"
ATTEMPT_GENERATION="2"
LEASE_EXPIRES_AT="2026-09-09T12:00:00.000Z"
_ack "delivered" 0 35 "" 12 "synthetic excerpt"
echo "----"
# legacy: attempt fields empty -> fields OMITTED from the body
INSTRUCTION_ID="ins-syn-2"
IDEMPOTENCY_KEY="idem-syn-2"
ATTEMPT_ID=""
ATTEMPT_GENERATION=""
LEASE_EXPIRES_AT=""
_ack "delivered" 0 35 "" 12 ""
OUTER3
ACK_OUT="$(bash "$ACK_SCRIPT" 2>&1 || echo ACKRUN-FAILED)"
# Both acks ran INSIDE one script; _post appended BOTH bodies to one file.
# Split on the boundary between the two JSON docs ('}{' junction).
RAW="$(cat "$FIX/captured-body.txt" 2>/dev/null || echo MISSING)"
cat > "$FIX/split.py" <<'SPLITEOF'
import sys
raw = open(sys.argv[1]).read()
docs = []
depth = 0
start = None
for i, ch in enumerate(raw):
    if ch == '{':
        if depth == 0:
            start = i
        depth += 1
    elif ch == '}':
        depth -= 1
        if depth == 0 and start is not None:
            docs.append(raw[start:i + 1])
            start = None
docs.append("")  # ensure DOC2 slot exists even with a single doc
sys.stdout.write("~~~".join(docs))
SPLITEOF
SPLIT="$(python3 "$FIX/split.py" "$FIX/captured-body.txt" 2>/dev/null || echo "MISSING~~~")"
DOC1="$(printf '%s' "$SPLIT" | awk -F'~~~' '{print $1}')"
DOC2="$(printf '%s' "$SPLIT" | awk -F'~~~' '{print $2}')"
[ -z "$DOC2" ] && DOC2="(empty)"
echo "$DOC1" | grep -q '"attempt_id":"tok-syn-123"' && echo "$DOC1" | grep -q '"attempt_generation":2' && echo "$DOC1" | grep -q '"lease_expires_at":"2026-09-09T12:00:00.000Z"' \
  && say_ok "ack echoes attempt identity verbatim when present" || say_fail "ack echo" "$DOC1"
case "$DOC2" in
  *attempt_id*|*attempt_generation*|*lease_expires_at*) say_fail "legacy ack omits attempt fields" "$DOC2" ;;
  *"action"*"ack"*) say_ok "legacy ack omits attempt fields entirely (old-server compatible)" ;;
  *) say_fail "legacy ack body missing" "$DOC2" ;;
esac

echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
