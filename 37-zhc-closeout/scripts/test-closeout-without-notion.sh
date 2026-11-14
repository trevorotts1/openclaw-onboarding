#!/usr/bin/env bash
# test-closeout-without-notion.sh -- BU-60 acceptance fixture (WF-090 / decision D-8).
#
# A closeout is done when the owner has what was delivered. When no client-owned
# Notion parent page is shared with the integration, create-notion-closeout.sh
# exits 2 (the ownership hold). That leg must be WAIVED and REPORTED, not block
# the closeout forever: final closeoutStatus=done, closeoutWaivedLegs=["notion"],
# and the operator summary fires exactly once -- AFTER the state says done.
#
# Strategy: a fake OpenClaw box in a temp dir holds copies of the real scripts
# under skills/. Every generator and the Telegram/verify/operator scripts are
# replaced with stubs, so nothing leaves this machine and no paid backend runs.
#
# EXIT: 0 all PASS, 1 any FAIL.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SKILL_DIR/.." && pwd)"
SRC37="$SCRIPT_DIR"
SRC23="$REPO_ROOT/23-ai-workforce-blueprint/scripts"
SRCSU="$REPO_ROOT/shared-utils"

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); printf '\033[32m✔\033[0m %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf '\033[31m✘\033[0m %s\n' "$1"; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/bu60-closeout.XXXXXX")"
trap 'if [[ -z "${KEEP_WORK:-}" ]]; then rm -rf "$WORK"; fi' EXIT
echo "    fixture work dir: $WORK"

BOX="$WORK/box"
OC="$BOX/.openclaw"
SK="$OC/skills"
mkdir -p "$SK/37-zhc-closeout/scripts" "$SK/23-ai-workforce-blueprint/scripts" \
         "$SK/shared-utils" "$OC/workspace" "$BOX/bin"

cp "$SRC37/run-closeout.sh" "$SRC37/lib-closeout-state.sh" "$SRC37/cleanup-closeout.py" \
   "$SK/37-zhc-closeout/scripts/" || { echo "fixture: copy 37 failed" >&2; exit 1; }
cp "$SRC23/lib-workforce-state.sh" "$SRC23/workforce_state.py" "$SRC23/workforce_completion.py" \
   "$SRC23/interview_eligibility.py" "$SK/23-ai-workforce-blueprint/scripts/" \
   || { echo "fixture: copy 23 failed" >&2; exit 1; }
cp "$SRCSU/owner_sends_hold.py" "$SRCSU/resolve-oc-root.sh" "$SRCSU/operator-chat-id.sh" \
   "$SK/shared-utils/" || { echo "fixture: copy shared-utils failed" >&2; exit 1; }

STATE="$OC/workspace/.workforce-build-state.json"
OPLOG="$WORK/operator-summary.log"
BUILD_ID="11111111-1111-1111-1111-111111111111"

# ---- stubs ---------------------------------------------------------------
printf '#!/usr/bin/env bash\nexit 0\n' > "$SK/23-ai-workforce-blueprint/scripts/verify-zhc-standard.sh"
printf '#!/usr/bin/env bash\nexit 0\n' > "$SK/23-ai-workforce-blueprint/scripts/verify-wiring.sh"
# no Notion parent is shared with the integration -> create-notion-closeout.sh exit 2
printf '#!/usr/bin/env bash\nexit 2\n' > "$SK/37-zhc-closeout/scripts/create-notion-closeout.sh"
printf '#!/usr/bin/env bash\nexit 0\n' > "$WORK/orgchart-qc-stub.sh"
chmod +x "$SK/23-ai-workforce-blueprint/scripts/verify-zhc-standard.sh" \
         "$SK/23-ai-workforce-blueprint/scripts/verify-wiring.sh" \
         "$SK/37-zhc-closeout/scripts/create-notion-closeout.sh" "$WORK/orgchart-qc-stub.sh"

# Telegram delivery stub: every other leg succeeds; record ids for the guard.
cat > "$SK/37-zhc-closeout/scripts/send-telegram-celebration.sh" <<'STUB'
#!/usr/bin/env bash
set -u
STATE_FILE="${ZHC_STATE_FILE:-$HOME/.openclaw/workspace/.workforce-build-state.json}"
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib-closeout-state.sh"
state_set '.messagesDelivered = [
  {"n": 1, "messageId": "fixture-1", "chatId": "9999999999", "ts": "2026-06-01T00:01:00Z"},
  {"n": 6, "messageId": "fixture-6", "chatId": "9999999999", "ts": "2026-06-01T00:02:00Z"},
  {"n": 7, "messageId": "fixture-7", "chatId": "9999999999", "ts": "2026-06-01T00:03:00Z"}
] | .closeoutStatus = "sent"'
exit 0
STUB

# Verify-delivery stub: a real receipt shape whose artifactDigest is exact.
cat > "$SK/37-zhc-closeout/scripts/verify-telegram-delivery.sh" <<'STUB'
#!/usr/bin/env bash
set -u
_h="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_oc="${HOME}/.openclaw"
STATE="${ZHC_STATE_FILE:-$_oc/workspace/.workforce-build-state.json}"
_verify="$(python3 - "$STATE" "$_h/../../23-ai-workforce-blueprint/scripts" <<'PY'
import json, sys
sys.path.insert(0, sys.argv[2])
import workforce_completion as wc
state = json.load(open(sys.argv[1]))
print(json.dumps({
    "status": "pass",
    "authority": "gateway-json-registry",
    "buildId": state.get("buildId"),
    "artifactDigest": wc.closeout_artifact_digest(state),
    "results": [
        {"n": 1, "required": True, "verdict": "pass-present", "messageId": "fixture-1"},
        {"n": 6, "required": True, "verdict": "pass-present", "messageId": "fixture-6"},
        {"n": 7, "required": True, "verdict": "pass-present", "messageId": "fixture-7"},
    ],
}))
PY
)"
python3 "$_h/../../23-ai-workforce-blueprint/scripts/workforce_state.py" jq "$STATE" \
  ".telegramDeliveryVerification = $_verify" || exit 1
exit 0
STUB

# Operator summary stub: one line = the state's closeoutStatus at send time.
cat > "$SK/37-zhc-closeout/scripts/send-operator-summary.sh" <<STUB
#!/usr/bin/env bash
set -u
jq -r '.closeoutStatus // "null"' "$STATE" >> "$OPLOG"
exit 0
STUB

cat > "$BOX/bin/openclaw" <<'STUB'
#!/usr/bin/env bash
case "${1:-}" in
  cron)    printf '{"uuid":"fixture-closeout-resume"}\n'; exit 0 ;;
  gateway) printf '{"status":"ok"}\n'; exit 0 ;;
  message) exit 0 ;;
  *)       exit 0 ;;
esac
STUB
chmod +x "$SK/37-zhc-closeout/scripts/send-telegram-celebration.sh" \
         "$SK/37-zhc-closeout/scripts/verify-telegram-delivery.sh" \
         "$SK/37-zhc-closeout/scripts/send-operator-summary.sh" "$BOX/bin/openclaw"

# ---- fixture state: a finished build, all legs real except Notion --------
jq -n --arg bid "$BUILD_ID" '{
  "version": 1,
  "companySlug": "fixture-co",
  "companyName": "Fixture Co",
  "ownerChat": 9999999999,
  "ownerName": "Test Owner",
  "agentName": "TestCEO",
  "interviewComplete": true,
  "interviewCompletedAt": "2026-06-01T00:00:00Z",
  "interviewQc": {"status": "pass", "reasons": []},
  "buildId": $bid,
  "buildCompletedAt": "2026-06-01T00:00:00Z",
  "completionVerification": {"version": 1, "buildId": $bid, "companyId": "fixture-co",
                             "status": "verified", "checkedAt": "2026-06-01T00:00:00Z",
                             "unmetRequirements": [], "inputDigest": "fixture", "artifactDigest": "fixture"},
  "commandCenterStatus": "done",
  "commandCenterBuildFresh": true,
  "commandCenterWorkspacesSeeded": true,
  "commandCenterDepartmentsSynced": true,
  "commandCenterMdContentSynced": true,
  "commandCenterDashboardContentSeeded": true,
  "commandCenterDeptRuntimeParity": true,
  "commandCenterTenantReady": true,
  "commandCenterUrl": "https://cc.example.test/",
  "closeoutStatus": "pending",
  "departments": [],
  "infographic1Url": "https://media.example.test/inf1.png",
  "infographic2Url": "https://media.example.test/inf2.png",
  "celebrationVideoUrl": "https://media.example.test/video.mp4",
  "qualityHeld": [],
  "qualityRatings": {
    "org_chart": {"score": 9, "qc": "pass"},
    "flow_diagram": {"score": 9, "qc": "pass"},
    "celebration_video": {"score": 9, "qc": "pass"}
  }
}' > "$STATE" || { echo "fixture: state write failed" >&2; exit 1; }
: > "$OPLOG"

# ---- run the real pipeline ----------------------------------------------
echo "--- running run-closeout.sh with no Notion parent configured ---"
rc=0
env -i \
  PATH="$BOX/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin" \
  HOME="$BOX" \
  TMPDIR="${TMPDIR:-/tmp}" \
  KIE_API_KEY=fixture-not-a-real-key \
  NOTION_API_TOKEN=fixture-not-a-real-token \
  ZHC_SKIP_TG_PREFLIGHT=1 \
  ZHC_SKIP_ROUTING_PREFLIGHT=1 \
  ZHC_SKIP_PROVIDER_SMOKE=1 \
  ZHC_OPERATOR_CHAT_ID=9999999999 \
  ZHC_ORGCHART_QC_SCRIPT="$WORK/orgchart-qc-stub.sh" \
  bash "$SK/37-zhc-closeout/scripts/run-closeout.sh" > "$WORK/run.out" 2>&1 || rc=$?
echo "    run-closeout rc=$rc (log: $WORK/run.out)"

if [[ "$rc" -eq 0 ]]; then
  pass "run-closeout.sh exited 0"
else
  fail "run-closeout.sh exited $rc (expected 0)"
  tail -15 "$WORK/run.out" | sed 's/^/    /'
fi

got_status="$(jq -r '.closeoutStatus // "absent"' "$STATE" 2>/dev/null)"
if [[ "$got_status" == "done" ]]; then
  pass "closeoutStatus=done with the Notion leg missing"
else
  fail "closeoutStatus=$got_status (expected done)"
fi

got_waived="$(jq -c '.closeoutWaivedLegs // null' "$STATE" 2>/dev/null)"
if [[ "$got_waived" == '["notion"]' ]]; then
  pass "closeoutWaivedLegs == [\"notion\"]"
else
  fail "closeoutWaivedLegs=$got_waived (expected [\"notion\"])"
fi

op_calls="$(wc -l < "$OPLOG" | tr -d ' ')"
if [[ "$op_calls" == "1" ]]; then
  pass "operator summary received exactly one message"
else
  fail "operator summary received $op_calls messages (expected 1)"
fi

op_status="$(head -1 "$OPLOG" 2>/dev/null)"
if [[ "$op_status" == "done" ]]; then
  pass "operator summary fired AFTER the state showed done"
else
  fail "operator summary saw closeoutStatus='$op_status' (expected done)"
fi

printf '\nTotal: %d passed, %d failed\n' "$PASS" "$FAIL"
if [[ "$FAIL" -eq 0 ]]; then exit 0; else exit 1; fi
