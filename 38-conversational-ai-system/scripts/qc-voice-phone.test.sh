#!/usr/bin/env bash
# qc-voice-phone.test.sh — negative test for qc-voice-phone.sh (F14).
#
# A QC gate that can never fail is worthless. This proves qc-voice-phone.sh:
#   (A) PASSES on the real, intact skill tree, and
#   (B) FAILS (exit non-zero) when an F14 invariant is broken — here we break THREE
#       different invariants in three throwaway copies:
#         1. neuter the operator-only / never-customer-invoked OUTBOUND-dial guard,
#         2. neuter the HONEST live-telephony gap (the "not faked / provisioned at
#            setup" disclaimer),
#         3. drop the voice-call-events.jsonl seeding from the installer.
#
# BASH only (no .py) so it respects qc-static's claude-/anthropic ban. Self-contained:
# copies the skill to a temp dir, mutates the copy, runs the gate against --skill-dir.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
GATE="$SCRIPT_DIR/qc-voice-phone.sh"

[ -f "$GATE" ] || { echo "FAIL: qc-voice-phone.sh not found at $GATE"; exit 1; }

RC=0
ok()   { echo "  [TEST PASS] $1"; }
ng()   { echo "  [TEST FAIL] $1"; RC=1; }

echo "=== qc-voice-phone.test: negative test for the F14 gate ==="

# (A) The intact skill must PASS.
if bash "$GATE" --skill-dir "$SKILL_DIR" >/dev/null 2>&1; then
  ok "intact skill passes qc-voice-phone.sh"
else
  ng "intact skill should PASS qc-voice-phone.sh but it failed — run: bash $GATE"
fi

make_copy() {
  local dst; dst="$(mktemp -d)"
  cp -a "$SKILL_DIR/." "$dst/"
  printf '%s' "$dst"
}

run_should_fail() {
  local dir="$1" desc="$2"
  if bash "$GATE" --skill-dir "$dir" >/dev/null 2>&1; then
    ng "gate should FAIL when $desc — but it PASSED"
  else
    ok "gate correctly FAILS when $desc"
  fi
  rm -rf "$dir"
}

# (B1) Neuter the operator-only / never-customer-invoked OUTBOUND-dial guard. The
#      gate keys on (operator-only/operator-gated) AND (the outbound-dial-injection /
#      call-placement-instruction / can-never-cause-an-outbound-call phrasing); strip
#      BOTH halves so the guard can no longer be proven (case-insensitive).
D1="$(make_copy)"
TMP="$(mktemp)"
sed -E -e 's/operator-only/VOICE_GUARD_REMOVED/Ig' \
       -e 's/operator only/VOICE_GUARD_REMOVED/Ig' \
       -e 's/operator-gated/VOICE_GUARD_REMOVED/Ig' \
       -e 's/outbound.?dial injection/VOICE_GUARD_REMOVED/Ig' \
       -e 's/call-placement instruction/VOICE_GUARD_REMOVED/Ig' \
       -e 's/can never cause the agent to place an outbound call/can place outbound calls/Ig' \
       -e 's/never cause an outbound dial/now causes outbound dials/Ig' \
    "$D1/protocols/voice-phone-protocol.md" > "$TMP"; mv "$TMP" "$D1/protocols/voice-phone-protocol.md"
run_should_fail "$D1" "the operator-only / never-customer-invoked OUTBOUND-dial guard is neutered"

# (B2) Neuter the HONEST live-telephony gap. The gate keys on (NOT faked / provisioned
#      at setup / honest gap / scaffold + wizard) AND (requires operator-provisioned
#      credentials / media-stream bridge provisioned). Strip BOTH halves.
D2="$(make_copy)"
TMP="$(mktemp)"
sed -E -e 's/NOT faked/now fully live/Ig' \
       -e 's/not faked/now fully live/Ig' \
       -e 's/do not fake/we fake/Ig' \
       -e 's/provisioned at setup/already live in the repo/Ig' \
       -e 's/honest gap/HONESTY_REMOVED/Ig' \
       -e 's/scaffold \+ wizard/HONESTY_REMOVED/Ig' \
       -e 's/requires operator-provisioned/needs nothing from the operator —/Ig' \
       -e 's/operator-provisioned credentials/HONESTY_REMOVED/Ig' \
       -e 's/media-stream bridge.*provisioned/media-stream bridge is built-in/Ig' \
    "$D2/protocols/voice-phone-protocol.md" > "$TMP"; mv "$TMP" "$D2/protocols/voice-phone-protocol.md"
run_should_fail "$D2" "the HONEST live-telephony gap (not-faked / provisioned-at-setup) is neutered"

# (B3) Drop the voice-call-events.jsonl seeding from the installer.
D3="$(make_copy)"
TMP="$(mktemp)"; grep -v 'voice-call-events.jsonl' "$D3/scripts/25-seed-round3-feature-files.sh" > "$TMP"; mv "$TMP" "$D3/scripts/25-seed-round3-feature-files.sh"
run_should_fail "$D3" "the voice-call-events.jsonl sink is no longer seeded by the installer"

echo ""
if [ "$RC" -eq 0 ]; then
  echo "RESULT: PASS — qc-voice-phone.sh passes intact and fails on each broken invariant."
  exit 0
else
  echo "RESULT: FAIL — the negative test did not behave as expected (see above)."
  exit 1
fi
