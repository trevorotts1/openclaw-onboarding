#!/usr/bin/env bash
# test-closeout-ghost-and-rating.sh — regression tests for the two closeout
# robustness bugs the 14-client normalization exposed.
#
# BUG A (GHOST FALSE-DONE): resume-closeout-cron.sh must NEVER self-stamp
#   closeoutStatus=done when a critical leg failed. On a simulated critical
#   failure the status must become "partial" (or stay "failed") with named
#   pending slots — and a re-run must NOT overwrite it to "done".
#
# BUG B (8.5 SELF-RATING GATE HOLDS ARTIFACTS): a generated artifact must get
#   a REAL rating (released on pass, or failed loud with a reason) — never left
#   silently held with qualityRatings=null.
#
# No live box, no network. Builds fake OpenClaw roots in temp dirs and runs the
# real scripts against fixtures with `openclaw` stubbed.
#
# EXIT: 0 all pass, 1 any fail.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CRON="$SCRIPT_DIR/resume-closeout-cron.sh"
RATER="$SCRIPT_DIR/qc-rate-artifacts.sh"
VERIFY_TG_SRC="$SCRIPT_DIR/verify-telegram-delivery.sh"

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); printf '\033[32mPASS\033[0m %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf '\033[31mFAIL\033[0m %s\n' "$1"; }
info() { printf '     %s\n' "$1"; }

# Build a fake OpenClaw root that the cron's platform detection will pick up via
# HOME. Returns the root path on stdout. Installs an `openclaw` stub on PATH and
# a copy of verify-telegram-delivery.sh under skills/.
make_fake_box() {
  local root="$1"
  mkdir -p "$root/workspace" "$root/skills/37-zhc-closeout/scripts" "$root/bin"
  cp "$VERIFY_TG_SRC" "$root/skills/37-zhc-closeout/scripts/verify-telegram-delivery.sh"
  cp "$SCRIPT_DIR/run-closeout.sh" "$root/skills/37-zhc-closeout/scripts/run-closeout.sh" 2>/dev/null || true
  # openclaw stub: cron list/rm/message all succeed quietly so the cron's
  # self_remove / escalation paths are no-ops in the test.
  cat > "$root/bin/openclaw" <<'STUB'
#!/usr/bin/env bash
# no-op openclaw stub for tests
case "$1" in
  cron)    exit 0 ;;
  message) exit 0 ;;
  config)  echo "" ; exit 0 ;;
  *)       exit 0 ;;
esac
STUB
  chmod +x "$root/bin/openclaw"
  printf '%s' "$root"
}

# Run the cron against a fake box. We override HOME so platform detection finds
# $root/.openclaw — so root MUST be "$tmp/.openclaw".
run_cron() {
  local home_dir="$1"
  ( PATH="$home_dir/.openclaw/bin:$PATH" HOME="$home_dir" \
    ZHC_CLOSEOUT_MAX_CRON_RUNS=999 \
    bash "$CRON" >/dev/null 2>&1 ) || true
}

# =====================================================================
# BUG A — Ghost false-done
# =====================================================================
printf '\n=== BUG A: ghost false-done (resume cron must not stamp done over critical failure) ===\n'

# ---------------------------------------------------------------------
# A1: run-closeout finalize recorded closeoutStatus=failed (critical-failed:
#     infographic-1,telegram). All 7 URL/flag fields happen to be present.
#     The OLD cron would stamp done (total_done==7). The FIXED cron must REFUSE.
# ---------------------------------------------------------------------
tmpA=$(mktemp -d)
boxA="$tmpA/.openclaw"
make_fake_box "$boxA" >/dev/null
stateA="$boxA/workspace/.workforce-build-state.json"
# All 7 leg FIELDS present, but closeoutStatus=failed with recorded critical legs,
# AND messagesDelivered has NO real messageId (telegram critically failed).
cat > "$stateA" <<'JSON'
{
  "buildCompletedAt": "2026-06-01T00:00:00Z",
  "closeoutStatus": "failed",
  "closeoutFailureReason": "critical-failed: infographic-1,telegram",
  "closeoutCriticalFailed": ["infographic-1","telegram"],
  "closeoutPendingSlots": ["infographic-1","telegram"],
  "ownerChat": "9999999999",
  "infographic1Url": "file:///tmp/inf1.png",
  "infographic2Url": "https://kie.ai/inf2.png",
  "celebrationVideoUrl": "https://kie.ai/v.mp4",
  "notionRootPageUrl": "https://www.notion.so/x",
  "messagesDelivered": [
    {"n": 1, "messageId": "", "status": "send-failed", "chatId": "9999999999", "ts": "2026-06-01T00:01:00Z"}
  ],
  "closeoutDeliverables": {
    "telegramSequenceSent": true,
    "ccUrlDelivered": true,
    "n8nWired": "skipped"
  }
}
JSON
run_cron "$tmpA"
gotA=$(jq -r '.closeoutStatus' "$stateA")
info "A1 closeoutStatus after cron = $gotA"
if [[ "$gotA" != "done" ]]; then
  pass "A1: cron did NOT stamp done over a recorded critical failure (status=$gotA)"
else
  fail "A1: GHOST -- cron stamped done over critical-failed (status=$gotA)"
fi

# ---------------------------------------------------------------------
# A2: closeoutStatus=generating (no sticky failed marker), 7 fields present,
#     but Telegram NOT verifiable (no real messageId). Cron must stamp PARTIAL
#     with named pending slots, NOT done.
# ---------------------------------------------------------------------
tmpB=$(mktemp -d)
boxB="$tmpB/.openclaw"
make_fake_box "$boxB" >/dev/null
stateB="$boxB/workspace/.workforce-build-state.json"
cat > "$stateB" <<'JSON'
{
  "buildCompletedAt": "2026-06-01T00:00:00Z",
  "closeoutStatus": "generating",
  "ownerChat": "9999999999",
  "infographic1Url": "file:///tmp/inf1.png",
  "infographic2Url": "https://kie.ai/inf2.png",
  "celebrationVideoUrl": "https://kie.ai/v.mp4",
  "notionRootPageUrl": "https://www.notion.so/x",
  "messagesDelivered": [
    {"n": 1, "messageId": "", "status": "send-failed", "chatId": "9999999999", "ts": "2026-06-01T00:01:00Z"}
  ],
  "closeoutDeliverables": {
    "telegramSequenceSent": true,
    "ccUrlDelivered": true,
    "n8nWired": "skipped"
  }
}
JSON
run_cron "$tmpB"
gotB=$(jq -r '.closeoutStatus' "$stateB")
slotsB=$(jq -rc '.closeoutPendingSlots // []' "$stateB")
info "A2 closeoutStatus=$gotB pendingSlots=$slotsB"
if [[ "$gotB" == "partial" ]] && echo "$slotsB" | grep -q 'telegram'; then
  pass "A2: unverified telegram -> partial with named pending slots (slots=$slotsB)"
elif [[ "$gotB" != "done" ]]; then
  pass "A2: did not stamp done on unverified telegram (status=$gotB)"
else
  fail "A2: GHOST -- stamped done with unverified telegram (status=$gotB)"
fi

# ---------------------------------------------------------------------
# A3: RE-RUN guard. Take A1's failed state (now partial-or-failed) and fire the
#     cron AGAIN. It must still NOT become done.
# ---------------------------------------------------------------------
run_cron "$tmpA"
gotA2=$(jq -r '.closeoutStatus' "$stateA")
info "A3 closeoutStatus after 2nd cron fire = $gotA2"
if [[ "$gotA2" != "done" ]]; then
  pass "A3: re-run could NOT overwrite to done (status=$gotA2)"
else
  fail "A3: GHOST -- second cron fire flipped to done (status=$gotA2)"
fi

# ---------------------------------------------------------------------
# A4: POSITIVE control. All 7 legs present AND telegram genuinely confirmed
#     (real messageIds for required slots 1,6,7; registry absent -> derived mode
#     confirms from captured ids). Cron SHOULD stamp done.
# ---------------------------------------------------------------------
tmpC=$(mktemp -d)
boxC="$tmpC/.openclaw"
make_fake_box "$boxC" >/dev/null
stateC="$boxC/workspace/.workforce-build-state.json"
NOWISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)
cat > "$stateC" <<JSON
{
  "buildCompletedAt": "2026-06-01T00:00:00Z",
  "closeoutStatus": "generating",
  "ownerChat": "9999999999",
  "infographic1Url": "file:///tmp/inf1.png",
  "infographic2Url": "https://kie.ai/inf2.png",
  "celebrationVideoUrl": "https://kie.ai/v.mp4",
  "notionRootPageUrl": "https://www.notion.so/x",
  "messagesDelivered": [
    {"n": 1, "messageId": "msg001", "chatId": "9999999999", "ts": "$NOWISO"},
    {"n": 6, "messageId": "msg006", "chatId": "9999999999", "ts": "$NOWISO"},
    {"n": 7, "messageId": "msg007", "chatId": "9999999999", "ts": "$NOWISO"}
  ],
  "closeoutDeliverables": {
    "telegramSequenceSent": true,
    "ccUrlDelivered": true,
    "n8nWired": "skipped"
  }
}
JSON
run_cron "$tmpC"
gotC=$(jq -r '.closeoutStatus' "$stateC")
info "A4 closeoutStatus after cron = $gotC"
if [[ "$gotC" == "done" ]]; then
  pass "A4: positive control -- verified-complete closeout DOES reach done"
else
  fail "A4: regression -- a genuinely-complete+verified closeout failed to reach done (status=$gotC)"
fi

# =====================================================================
# BUG B — 8.5 self-rating gate holds artifacts
# =====================================================================
printf '\n=== BUG B: deterministic rate+release (never silent null) ===\n'

# ---------------------------------------------------------------------
# B1: flow_diagram artifact present (remote https URL). Rater must RELEASE it:
#     write a real rating with qc=pass and score >= 8.5 — not leave it null.
# ---------------------------------------------------------------------
tmpD=$(mktemp -d)
stateD="$tmpD/state.json"
cat > "$stateD" <<'JSON'
{ "infographic2Url": "https://kie.ai/flow-diagram.png" }
JSON
ZHC_STATE_FILE="$stateD" ZHC_LOG_FILE="/dev/null" bash "$RATER" --key flow_diagram --state "$stateD" >/dev/null 2>&1 || true
scoreD=$(jq -r '.qualityRatings.flow_diagram.score // "null"' "$stateD")
qcD=$(jq -r '.qualityRatings.flow_diagram.qc // "null"' "$stateD")
info "B1 flow_diagram score=$scoreD qc=$qcD"
if [[ "$scoreD" != "null" ]] && awk -v s="$scoreD" 'BEGIN{exit !(s+0>=8.5)}' && [[ "$qcD" == "pass" ]]; then
  pass "B1: present artifact RATED + RELEASED (score=$scoreD>=8.5, qc=pass) -- not silent null"
else
  fail "B1: artifact NOT released (score=$scoreD qc=$qcD)"
fi

# ---------------------------------------------------------------------
# B2: FAIL LOUD. flow_diagram URL points at a tiny local file (< 1KB = empty/
#     error placeholder). Rater must write a NON-null rating with qc=fail and a
#     reason — never null, never an undeserved pass.
# ---------------------------------------------------------------------
tmpE=$(mktemp -d)
stateE="$tmpE/state.json"
tinyfile="$tmpE/empty.png"
printf 'x' > "$tinyfile"   # 1 byte
jq -n --arg p "file://$tinyfile" --arg lp "$tinyfile" \
  '{infographic2Url:$p, infographic2LocalPath:$lp}' > "$stateE"
ZHC_STATE_FILE="$stateE" ZHC_LOG_FILE="/dev/null" bash "$RATER" --key flow_diagram --state "$stateE" >/dev/null 2>&1 || true
scoreE=$(jq -r '.qualityRatings.flow_diagram.score // "null"' "$stateE")
qcE=$(jq -r '.qualityRatings.flow_diagram.qc // "null"' "$stateE")
noteE=$(jq -r '.qualityRatings.flow_diagram.note // ""' "$stateE")
info "B2 flow_diagram score=$scoreE qc=$qcE note=$noteE"
if [[ "$scoreE" != "null" && "$qcE" == "fail" && -n "$noteE" ]]; then
  pass "B2: empty artifact FAILED LOUD (score=$scoreE qc=fail, reason recorded) -- not silent null, not undeserved pass"
else
  fail "B2: empty artifact not failed-loud correctly (score=$scoreE qc=$qcE)"
fi

# ---------------------------------------------------------------------
# B3: MISSING artifact. No infographic2Url at all. Rater must still write a
#     real (failing) rating — never leave qualityRatings null.
# ---------------------------------------------------------------------
tmpF=$(mktemp -d)
stateF="$tmpF/state.json"
echo '{}' > "$stateF"
ZHC_STATE_FILE="$stateF" ZHC_LOG_FILE="/dev/null" bash "$RATER" --key flow_diagram --state "$stateF" >/dev/null 2>&1 || true
scoreF=$(jq -r '.qualityRatings.flow_diagram.score // "null"' "$stateF")
qcF=$(jq -r '.qualityRatings.flow_diagram.qc // "null"' "$stateF")
info "B3 missing-artifact score=$scoreF qc=$qcF"
if [[ "$scoreF" != "null" && "$qcF" == "fail" ]]; then
  pass "B3: missing artifact -> real failing rating written (no silent null)"
else
  fail "B3: missing artifact left rating null/unwritten (score=$scoreF qc=$qcF)"
fi

# ---------------------------------------------------------------------
# B4: closeout_docs with 9 sections recorded + notion leg pass -> RELEASE.
# ---------------------------------------------------------------------
tmpG=$(mktemp -d)
stateG="$tmpG/state.json"
cat > "$stateG" <<'JSON'
{ "notionRootPageUrl": "https://www.notion.so/closeout-abc",
  "notionSectionsCreated": 9,
  "closeoutLegStatus": { "notion": "pass" } }
JSON
ZHC_STATE_FILE="$stateG" ZHC_LOG_FILE="/dev/null" bash "$RATER" --key closeout_docs --state "$stateG" >/dev/null 2>&1 || true
scoreG=$(jq -r '.qualityRatings.closeout_docs.score // "null"' "$stateG")
qcG=$(jq -r '.qualityRatings.closeout_docs.qc // "null"' "$stateG")
info "B4 closeout_docs score=$scoreG qc=$qcG"
if [[ "$scoreG" != "null" ]] && awk -v s="$scoreG" 'BEGIN{exit !(s+0>=8.5)}' && [[ "$qcG" == "pass" ]]; then
  pass "B4: complete Notion doc (9/9 sections) RATED + RELEASED"
else
  fail "B4: complete Notion doc not released (score=$scoreG qc=$qcG)"
fi

# ---------------------------------------------------------------------
# B5: closeout_docs with only 4/9 sections -> FAIL LOUD (held, reason recorded).
# ---------------------------------------------------------------------
tmpH=$(mktemp -d)
stateH="$tmpH/state.json"
cat > "$stateH" <<'JSON'
{ "notionRootPageUrl": "https://www.notion.so/closeout-abc",
  "notionSectionsCreated": 4 }
JSON
ZHC_STATE_FILE="$stateH" ZHC_LOG_FILE="/dev/null" bash "$RATER" --key closeout_docs --state "$stateH" >/dev/null 2>&1 || true
scoreH=$(jq -r '.qualityRatings.closeout_docs.score // "null"' "$stateH")
qcH=$(jq -r '.qualityRatings.closeout_docs.qc // "null"' "$stateH")
info "B5 closeout_docs score=$scoreH qc=$qcH"
if [[ "$scoreH" != "null" && "$qcH" == "fail" ]]; then
  pass "B5: incomplete Notion doc (4/9) FAILED LOUD (not released, reason recorded)"
else
  fail "B5: incomplete Notion doc not failed-loud (score=$scoreH qc=$qcH)"
fi

# cleanup
rm -rf "$tmpA" "$tmpB" "$tmpC" "$tmpD" "$tmpE" "$tmpF" "$tmpG" "$tmpH"

printf '\n----------------------------------------\n'
printf 'Total: %d passed, %d failed\n' "$PASS" "$FAIL"
[[ "$FAIL" -eq 0 ]] && { printf '\033[32mALL TESTS PASS\033[0m\n'; exit 0; } || { printf '\033[31m%d FAILED\033[0m\n' "$FAIL"; exit 1; }
