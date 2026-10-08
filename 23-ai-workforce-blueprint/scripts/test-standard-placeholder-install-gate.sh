#!/usr/bin/env bash
# test-standard-placeholder-install-gate.sh - STD001: run-full-install.sh must let an ACTIVE standard
# placeholder skip the interview gate and treat BLOCK B as a full install until ccProvisionedAt is set.
# Source-and-stub: the real gate lines are extracted from the installer and evaluated against a fake
# build-state, so a drift in the installer fails this test. Nothing real is touched.
set -uo pipefail
RFI="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../32-command-center-setup/scripts" && pwd)/run-full-install.sh"
PASS=0; FAIL=0
good() { PASS=$((PASS+1)); echo "PASS: $1"; }
bad()  { FAIL=$((FAIL+1)); echo "FAIL: $1" >&2; }
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
STATE_FILE="$TMP/s.json"
state_get() { jq -r "$1 // empty" "$STATE_FILE" 2>/dev/null; }

FN="$(grep -m1 '^standard_placeholder_active()' "$RFI")"
SP_LINE="$(grep -m1 '^SP_ACTIVE=false; standard_placeholder_active' "$RFI")"
BB_LINES="$(grep -A1 -m1 '^BLOCK_B_UPDATE_ONLY="\$UPDATE_ONLY"' "$RFI")"
GATE="$(grep -m1 '^if \[\[ "\$SP_ACTIVE" != "true" &&' "$RFI")"
[ -n "$FN" ] && [ -n "$SP_LINE" ] && [ -n "$BB_LINES" ] && [ -n "$GATE" ] && good "installer carries the placeholder gate lines" || bad "gate lines missing from run-full-install.sh"
eval "$FN"

evalstate() { # <state json> <UPDATE_ONLY> -> prints "SP_ACTIVE BLOCK_B_UPDATE_ONLY"
  printf '%s' "$1" > "$STATE_FILE"; UPDATE_ONLY="$2"
  eval "$SP_LINE"; eval "$BB_LINES"
  echo "$SP_ACTIVE $BLOCK_B_UPDATE_ONLY"
}
ACT='"companyMode":"standard-placeholder","interviewComplete":false'
[ "$(evalstate "{$ACT,\"standardPlaceholder\":{\"status\":\"active\"}}" true)" = "true false" ] \
  && good "active placeholder, not yet provisioned: --update-only runs BLOCK B as a full install" || bad "active/unprovisioned"
[ "$(evalstate "{$ACT,\"standardPlaceholder\":{\"status\":\"active\",\"ccProvisionedAt\":\"2026-10-08T00:00:00Z\"}}" true)" = "true true" ] \
  && good "after ccProvisionedAt: --update-only is a normal refresh again" || bad "provisioned"
[ "$(evalstate "{$ACT,\"standardPlaceholder\":{\"status\":\"superseded\"}}" true)" = "false true" ] \
  && good "superseded placeholder: gating is back to normal" || bad "superseded"
[ "$(evalstate '{"interviewComplete":false,"standardPrebuild":{"status":"done"}}' true)" = "false true" ] \
  && good "bare standardPrebuild (no placeholder) changes nothing" || bad "bare prebuild"

# The interview gate condition must be skipped by an active placeholder.
printf '%s' "{$ACT,\"launchBootstrap\":{},\"standardPlaceholder\":{\"status\":\"active\"}}" > "$STATE_FILE"; UPDATE_ONLY=false
eval "$SP_LINE"; COND="${GATE#if }"; COND="${COND%; then}"
if eval "$COND"; then bad "gate still entered with an active placeholder"; else good "interview gate skipped when the placeholder is active"; fi
printf '%s' '{"interviewComplete":false,"launchBootstrap":{}}' > "$STATE_FILE"; UPDATE_ONLY=true; eval "$SP_LINE"
if eval "$COND"; then good "interview gate still entered without a placeholder (real-interview gating unchanged)"; else bad "gate no longer guards the normal case"; fi

# BLOCK B must never read the raw UPDATE_ONLY.
LEFT="$(awk '/^# BLOCK B - REAL ZERO-HUMAN WORKFORCE/{f=1} /^# PHASE 7 /{f=0} f && /UPDATE_ONLY/ && !/BLOCK_B_UPDATE_ONLY/ && !/^[[:space:]]*#/' "$RFI")"
[ -z "$LEFT" ] && good "no raw UPDATE_ONLY reads left inside BLOCK B" || bad "raw UPDATE_ONLY in BLOCK B: $LEFT"
grep -q 'standardPlaceholder.ccProvisionedAt = ' "$RFI" && good "FINAL done branch stamps ccProvisionedAt" || bad "ccProvisionedAt stamp missing"

echo "test-standard-placeholder-install-gate.sh: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
