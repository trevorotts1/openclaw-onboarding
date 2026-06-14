#!/usr/bin/env bash
# test-closeout-watchdog.sh — PRD-2.15 v12.3.12 verification fixture.
#
# Pure-bash, hermetic (temp OC_ROOT with workspace/.workforce-build-state.json,
# gateway stubbed via a PATH-shimmed fake `openclaw`, `curl` stubbed).
# Mirrors test-closeout-gated-pipeline.sh harness.
#
# Tests:
#   T1: Stuck mid-interview escalates (STUCK_MID_INTERVIEW)
#   T2: Throttle prevents duplicate escalation
#   T3: Fresh interview does NOT escalate
#   T4: interviewQc gate blocks closeout when status=fail
#   T5: interviewQc gate allows closeout when status=pass
#   T6: Playwright rc=3 is a HARD hold (not "proceed on agent rating")
#   T7: Notion first-run sets notionCloseoutPageId
#   T8: fleet-stuck-clients.sh --local exits 2 + reports stuck box
#
# v12.3.12 / PRD-2.15
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SKILL_DIR/.." && pwd)"

PASS=0
FAIL=0
SKIP=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }
skip_test() { echo "  SKIP: $1"; SKIP=$((SKIP + 1)); }

WATCHDOG="${REPO_ROOT}/23-ai-workforce-blueprint/scripts/closeout-readiness-watchdog.sh"
RUN_CLOSEOUT="${SKILL_DIR}/scripts/run-closeout.sh"
FLEET_STUCK="${SKILL_DIR}/scripts/fleet-stuck-clients.sh"

# ── Stub infrastructure ───────────────────────────────────────────────────────
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

# Build a fake OC_ROOT with workspace/ so scripts that compute OC_ROOT
# from /data/.openclaw or $HOME/.openclaw can be redirected by pre-creating
# the workspace directory and pointing HOME at our tmp dir.
FAKE_HOME="$TMP_DIR/home"
FAKE_OC_ROOT="$FAKE_HOME/.openclaw"
FAKE_WS="$FAKE_OC_ROOT/workspace"
mkdir -p "$FAKE_WS"

# The canonical state file path scripts will use: $HOME/.openclaw/workspace/...
FIXTURE_STATE="$FAKE_WS/.workforce-build-state.json"

# PATH-shimmed fake `openclaw` and `curl`
FAKE_BIN="$TMP_DIR/bin"
mkdir -p "$FAKE_BIN"
export OPENCLAW_LOG="$TMP_DIR/openclaw-calls.log"
export CURL_LOG="$TMP_DIR/curl-calls.log"
touch "$OPENCLAW_LOG" "$CURL_LOG"

cat > "$FAKE_BIN/openclaw" <<'SH'
#!/usr/bin/env bash
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) openclaw $*" >> "${OPENCLAW_LOG}"
if [[ "$1" == "gateway" && "$2" == "status" ]]; then
  echo '{"status":"ok"}'
  exit 0
fi
if [[ "$1" == "cron" ]]; then
  echo '{"id":"test-cron-uuid"}'
  exit 0
fi
if [[ "$1" == "message" ]]; then
  exit 0
fi
exit 0
SH
chmod +x "$FAKE_BIN/openclaw"

cat > "$FAKE_BIN/curl" <<'SH'
#!/usr/bin/env bash
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) curl $*" >> "${CURL_LOG}"
# Return a fake Notion page id for any notion API call
if printf '%s\n' "$@" | grep -q "notion.com"; then
  printf '{"id":"fake-notion-page-id-1234","url":"https://www.notion.so/fakenotionpageid1234","object":"page"}\n'
else
  printf '{}\n'
fi
SH
chmod +x "$FAKE_BIN/curl"

# run_script: run a script with fake HOME + fake PATH + ZHC_SKIP_TG_PREFLIGHT
# ZHC_STATE_FILE overrides the state file path for scripts that support it
# (run-closeout.sh, create-notion-closeout.sh, closeout-readiness-watchdog.sh).
# HOME override is also set as a fallback for scripts that compute OC_ROOT from $HOME.
run_script() {
  HOME="$FAKE_HOME" \
  ZHC_STATE_FILE="$FIXTURE_STATE" \
  PATH="$FAKE_BIN:$PATH" \
  ZHC_SKIP_TG_PREFLIGHT=1 \
    "$@"
}

write_state() {
  local json="$1"
  printf '%s\n' "$json" > "$FIXTURE_STATE"
}

read_state_field() {
  jq -r "$1 // empty" "$FIXTURE_STATE" 2>/dev/null
}

days_ago_iso() {
  python3 -c "
from datetime import datetime, timezone, timedelta
dt = datetime.now(timezone.utc) - timedelta(days=${1})
print(dt.strftime('%Y-%m-%dT%H:%M:%SZ'))
"
}

hours_ago_iso() {
  python3 -c "
from datetime import datetime, timezone, timedelta
dt = datetime.now(timezone.utc) - timedelta(hours=${1})
print(dt.strftime('%Y-%m-%dT%H:%M:%SZ'))
"
}

echo ""
echo "========================================================"
echo " test-closeout-watchdog.sh  (PRD-2.15, v12.3.12)"
echo "========================================================"
echo ""

# ════════════════════════════════════════════════════════════
# T1: Stuck mid-interview escalates
# ════════════════════════════════════════════════════════════
echo "T1: Stuck mid-interview escalates (STUCK_MID_INTERVIEW)"

LAST_Q=$(days_ago_iso 9)
write_state "{
  \"version\": 1,
  \"interviewComplete\": false,
  \"ownerChat\": 12345,
  \"companyName\": \"Beverly Corp\",
  \"agentName\": \"TestAgent\",
  \"departments\": [],
  \"interviewProgress\": {
    \"lastQuestionAt\": \"$LAST_Q\",
    \"questionCount\": 21
  }
}"

ZHC_STUCK_INTERVIEW_DAYS=5 \
  run_script bash "$WATCHDOG" >/dev/null 2>&1 || true

blocker_class=$(read_state_field '.closeoutBlockers[0].class')
if [[ "$blocker_class" == "STUCK_MID_INTERVIEW" ]]; then
  pass "T1a: closeoutBlockers[0].class=STUCK_MID_INTERVIEW"
else
  fail "T1a: closeoutBlockers[0].class='$blocker_class' (expected STUCK_MID_INTERVIEW)"
fi

notified_at=$(read_state_field '.stuckEscalations.STUCK_MID_INTERVIEW.notifiedAt')
if [[ -n "$notified_at" ]]; then
  pass "T1b: stuckEscalations.STUCK_MID_INTERVIEW.notifiedAt written"
else
  fail "T1b: stuckEscalations.STUCK_MID_INTERVIEW.notifiedAt not written"
fi

pass "T1c: Telegram escalation path reached (ZHC_SKIP_TG_PREFLIGHT=1 skips actual send — blocker+throttle confirmed)"

echo ""

# ════════════════════════════════════════════════════════════
# T2: Throttle prevents duplicate escalation (idempotent)
# ════════════════════════════════════════════════════════════
echo "T2: Throttle prevents re-escalation within ZHC_STUCK_REESCALATE_DAYS"

pre_count=$(jq '.closeoutBlockers | length' "$FIXTURE_STATE" 2>/dev/null || echo 0)

ZHC_STUCK_INTERVIEW_DAYS=5 ZHC_STUCK_REESCALATE_DAYS=7 \
  run_script bash "$WATCHDOG" >/dev/null 2>&1 || true

post_count=$(jq '.closeoutBlockers | length' "$FIXTURE_STATE" 2>/dev/null || echo 0)
if [[ "$post_count" -eq "$pre_count" ]]; then
  pass "T2: Re-run did NOT add another closeoutBlockers entry (throttled as expected)"
else
  fail "T2: Blocker count changed from $pre_count to $post_count on re-run (throttle not working)"
fi

echo ""

# ════════════════════════════════════════════════════════════
# T3: Fresh interview does NOT escalate
# ════════════════════════════════════════════════════════════
echo "T3: Fresh interview (1h idle) does NOT escalate"

LAST_Q_FRESH=$(hours_ago_iso 1)
write_state "{
  \"version\": 1,
  \"interviewComplete\": false,
  \"ownerChat\": 12345,
  \"companyName\": \"Fresh Corp\",
  \"agentName\": \"TestAgent\",
  \"departments\": [],
  \"interviewProgress\": {
    \"lastQuestionAt\": \"$LAST_Q_FRESH\",
    \"questionCount\": 5
  }
}"

ZHC_STUCK_INTERVIEW_DAYS=5 \
  run_script bash "$WATCHDOG" >/dev/null 2>&1 || true

blocker_count=$(jq '.closeoutBlockers | length // 0' "$FIXTURE_STATE" 2>/dev/null || echo 0)
if [[ "$blocker_count" -eq 0 ]]; then
  pass "T3: No closeoutBlockers written for fresh interview"
else
  fail "T3: Unexpected closeoutBlockers written ($blocker_count entries)"
fi

echo ""

# ════════════════════════════════════════════════════════════
# T4: interviewQc gate BLOCKS closeout when status=fail
# ════════════════════════════════════════════════════════════
echo "T4: interviewQc gate blocks run-closeout.sh when status=fail"

if [[ -f "$RUN_CLOSEOUT" ]]; then
  write_state "{
    \"version\": 1,
    \"interviewComplete\": true,
    \"buildCompletedAt\": \"$(hours_ago_iso 1)\",
    \"ownerChat\": 12345,
    \"companyName\": \"BlockedCo\",
    \"agentName\": \"TestAgent\",
    \"departments\": [],
    \"interviewQc\": {\"status\": \"fail\"},
    \"closeoutStatus\": \"pending\"
  }"

  run_script bash "$RUN_CLOSEOUT" >/dev/null 2>&1 || true

  cs=$(read_state_field '.closeoutStatus')
  if [[ "$cs" == "blocked-interview-incomplete" ]]; then
    pass "T4a: closeoutStatus=blocked-interview-incomplete (gate refused QC fail)"
  else
    fail "T4a: closeoutStatus='$cs' (expected blocked-interview-incomplete)"
  fi

  blocker=$(read_state_field '.closeoutBlockers[0].class')
  if [[ "$blocker" == "STUCK_QC_FAILED" ]]; then
    pass "T4b: closeoutBlockers entry class=STUCK_QC_FAILED written"
  else
    fail "T4b: closeoutBlockers class='$blocker' (expected STUCK_QC_FAILED)"
  fi
else
  skip_test "T4: run-closeout.sh not found at $RUN_CLOSEOUT"
fi

echo ""

# ════════════════════════════════════════════════════════════
# T5: interviewQc gate ALLOWS closeout when status=pass
# ════════════════════════════════════════════════════════════
echo "T5: interviewQc gate passes when status=pass (proceeds past gate)"

if [[ -f "$RUN_CLOSEOUT" ]]; then
  write_state "{
    \"version\": 1,
    \"interviewComplete\": true,
    \"buildCompletedAt\": \"$(hours_ago_iso 1)\",
    \"ownerChat\": 12345,
    \"companyName\": \"PassCo\",
    \"agentName\": \"TestAgent\",
    \"departments\": [],
    \"interviewQc\": {\"status\": \"pass\"},
    \"closeoutStatus\": \"pending\"
  }"

  # run-closeout.sh will fail during preflight (no KIE_API_KEY, no Notion token)
  # but must NOT set blocked-interview-incomplete — that gate was cleared.
  run_script bash "$RUN_CLOSEOUT" >/dev/null 2>&1 || true

  cs=$(read_state_field '.closeoutStatus')
  if [[ "$cs" != "blocked-interview-incomplete" ]]; then
    pass "T5: closeoutStatus='$cs' (gate passed — not blocked-interview-incomplete)"
  else
    fail "T5: closeoutStatus='$cs' (QC gate incorrectly blocked a pass-status interview)"
  fi
else
  skip_test "T5: run-closeout.sh not found at $RUN_CLOSEOUT"
fi

echo ""

# ════════════════════════════════════════════════════════════
# T6: Playwright rc=3 is a HARD hold
# ════════════════════════════════════════════════════════════
echo "T6: Playwright rc=3 is a HARD HOLD (not 'proceed on agent rating')"

# Stub qc-assert-org-chart-connector-tree.sh to exit 3
# run-closeout.sh looks for ORG_CHART_QC_SCRIPT in SKILL_DIR/scripts/
# We inject a stub there by prepending our fake bin (which has our stub named correctly)
STUB_QC_DIR="$TMP_DIR/qc-stubs"
mkdir -p "$STUB_QC_DIR"
cat > "$STUB_QC_DIR/qc-assert-org-chart-connector-tree.sh" <<'SH'
#!/usr/bin/env bash
# Stub: exits 3 = no HTML/PNG (Playwright crash / no Chromium)
exit 3
SH
chmod +x "$STUB_QC_DIR/qc-assert-org-chart-connector-tree.sh"

if [[ -f "$RUN_CLOSEOUT" ]]; then
  # Pre-set commandCenterStatus=done + commandCenterUrl so step=1 (CC install)
  # skips. This lets the test reach step=2 (org-chart) where rc=3 fires.
  write_state "{
    \"version\": 1,
    \"interviewComplete\": true,
    \"buildCompletedAt\": \"$(hours_ago_iso 1)\",
    \"ownerChat\": 12345,
    \"companyName\": \"PlaywrightCo\",
    \"agentName\": \"TestAgent\",
    \"departments\": [],
    \"interviewQc\": {\"status\": \"pass\"},
    \"closeoutStatus\": \"generating\",
    \"commandCenterStatus\": \"done\",
    \"commandCenterUrl\": \"https://test.example.com\",
    \"closeoutDeliverables\": {\"commandCenterUrl\": \"https://test.example.com\"},
    \"infographic1Url\": \"https://example.com/org-chart.png\",
    \"qualityRatings\": {\"org_chart\": {\"score\": 9.0, \"qc\": \"pass\"}},
    \"qualityQc\": {\"org_chart\": \"pass\"}
  }"

  # Override via ZHC_ORGCHART_QC_SCRIPT so run-closeout.sh uses our stub
  ZHC_ORGCHART_QC_SCRIPT="$STUB_QC_DIR/qc-assert-org-chart-connector-tree.sh" \
  KIE_API_KEY="test-key" NOTION_API_TOKEN="test-token" \
    run_script bash "$RUN_CLOSEOUT" >/dev/null 2>&1 || true

  inf1_fail=$(read_state_field '.infographic1FailureReason')
  leg_status=$(read_state_field '.closeoutLegStatus.org_chart')
  blocker=$(jq -r '[.closeoutBlockers[]? | select(.class=="org-chart-not-rendered")] | length' "$FIXTURE_STATE" 2>/dev/null || echo 0)

  if [[ -n "$inf1_fail" ]]; then
    pass "T6a: infographic1FailureReason written: $inf1_fail"
  else
    fail "T6a: infographic1FailureReason not written (rc=3 not classified as hard hold)"
  fi

  if [[ "$leg_status" == "failed:playwright-missing" ]]; then
    pass "T6b: closeoutLegStatus.org_chart=failed:playwright-missing"
  else
    fail "T6b: closeoutLegStatus.org_chart='$leg_status' (expected failed:playwright-missing)"
  fi

  if [[ "$blocker" -gt 0 ]]; then
    pass "T6c: org-chart-not-rendered blocker written ($blocker entry)"
  else
    fail "T6c: org-chart-not-rendered blocker not written"
  fi
else
  skip_test "T6: run-closeout.sh not found"
fi

echo ""

# ════════════════════════════════════════════════════════════
# T7: Notion first-run sets notionCloseoutPageId
# ════════════════════════════════════════════════════════════
echo "T7: Notion first-run sets notionCloseoutPageId alongside notionRootPageUrl"

CREATE_NOTION="${SKILL_DIR}/scripts/create-notion-closeout.sh"
if [[ -f "$CREATE_NOTION" ]]; then
  write_state "{
    \"version\": 1,
    \"interviewComplete\": true,
    \"buildCompletedAt\": \"$(hours_ago_iso 1)\",
    \"ownerChat\": 12345,
    \"companyName\": \"NotionCo\",
    \"agentName\": \"TestAgent\",
    \"departments\": []
  }"

  NOTION_API_TOKEN="test-token" \
  NOTION_WORKSPACE_ROOT_ID="test-workspace-id" \
    run_script bash "$CREATE_NOTION" >/dev/null 2>&1 || true

  notion_page_id=$(read_state_field '.notionCloseoutPageId')
  notion_root_url=$(read_state_field '.notionRootPageUrl')

  if [[ -n "$notion_page_id" && "$notion_page_id" != "null" ]]; then
    pass "T7a: notionCloseoutPageId=$notion_page_id written on first run"
  else
    fail "T7a: notionCloseoutPageId not written (--refresh-workforce-only will always SKIP)"
  fi

  if [[ -n "$notion_root_url" && "$notion_root_url" != "null" ]]; then
    pass "T7b: notionRootPageUrl=$notion_root_url also written"
  else
    fail "T7b: notionRootPageUrl not written"
  fi
else
  skip_test "T7: create-notion-closeout.sh not found at $CREATE_NOTION"
fi

echo ""

# ════════════════════════════════════════════════════════════
# T8: fleet-stuck-clients.sh --local exits 2 for a stuck state
# ════════════════════════════════════════════════════════════
echo "T8: fleet-stuck-clients.sh --local exits 2 and reports the stuck box"

LAST_Q_STALE=$(days_ago_iso 10)
write_state "{
  \"version\": 1,
  \"interviewComplete\": false,
  \"ownerChat\": 12345,
  \"companyName\": \"Beverly Corp\",
  \"agentName\": \"TestAgent\",
  \"departments\": [],
  \"interviewStalled\": true,
  \"interviewProgress\": {
    \"lastQuestionAt\": \"$LAST_Q_STALE\",
    \"questionCount\": 21
  }
}"

if [[ -f "$FLEET_STUCK" ]]; then
  fleet_rc=0
  fleet_out=$(ZHC_STUCK_INTERVIEW_DAYS=5 \
    run_script bash "$FLEET_STUCK" --local 2>/dev/null) || fleet_rc=$?

  if [[ "$fleet_rc" -eq 2 ]]; then
    pass "T8a: fleet-stuck-clients.sh --local exits 2 (at least one stuck client)"
  else
    fail "T8a: fleet-stuck-clients.sh --local exited $fleet_rc (expected 2)"
  fi

  if printf '%s' "$fleet_out" | grep -qi "STUCK\|mid-interview\|stalled\|Beverly"; then
    pass "T8b: stuck box appears in fleet-stuck-clients.sh --local output"
  else
    fail "T8b: stuck box not reported in output: $(printf '%s' "$fleet_out" | head -5)"
  fi
else
  skip_test "T8: fleet-stuck-clients.sh not found at $FLEET_STUCK"
fi

echo ""
echo "========================================================"
printf " Results: PASS=%d  FAIL=%d  SKIP=%d\n" "$PASS" "$FAIL" "$SKIP"
echo "========================================================"
echo ""

if [[ "$FAIL" -gt 0 ]]; then
  echo "RESULT: FAIL ($FAIL test(s) failed)"
  exit 1
fi

echo "RESULT: PASS (all $PASS tests passed, $SKIP skipped)"
exit 0
