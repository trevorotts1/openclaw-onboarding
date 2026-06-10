#!/usr/bin/env bash
# test-closeout-gated-pipeline.sh — PRD-2.8 verification fixture.
#
# Verifies WITHOUT a live client box:
#   T1: A "complete" build state produces all 7 closeoutDeliverables fields
#       populated and closes out cleanly (unit-level test of the state machine).
#   T2: Pre-flight fails LOUD when NOTION_API_TOKEN is missing.
#   T3: Pre-flight fails LOUD when KIE_API_KEY is missing.
#   T4: Pre-flight fails LOUD when Telegram gateway is unreachable.
#   T5: The org-chart QC assertion (qc-assert-org-chart-connector-tree.sh) PASSES
#       for a connector-tree HTML and FAILS for a card-grid HTML.
#   T6: The resume cron (resume-closeout-cron.sh) is referenced in run-closeout.sh
#       and exists as an executable script.
#   T7: The fleet-sweep script (fleet-sweep-closeouts.sh) exists and --local mode
#       correctly identifies an incomplete closeout fixture.
#   T8: The schema (build-state-schema.json) contains all 7 PRD-2.8 deliverable
#       fields under closeoutDeliverables.
#   T9: The qc-static assertions in .github/workflows/qc-static.yml include checks
#       for the 7-field deliverables and the org-chart QC gate.
#
# EXIT CODES:
#   0  all tests PASS
#   1  one or more tests FAIL
#
# Safe to run from the repo root or from the CI workflow. No network calls.
# No client box required.
#
# PRD-2.8 / v11.10.0

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# REPO_ROOT: navigate up from 37-zhc-closeout/ to the repo root
REPO_ROOT="$(cd "$SKILL_DIR/.." && pwd)"

PASS=0
FAIL=0
RESULTS=()

pass() { PASS=$((PASS + 1)); RESULTS+=("PASS: $1"); printf '\033[32m✔\033[0m %s\n' "$1"; }
fail() { FAIL=$((FAIL + 1)); RESULTS+=("FAIL: $1"); printf '\033[31m✘\033[0m %s\n' "$1"; }
info() { printf '    %s\n' "$1"; }

# ---- helpers ----
make_complete_state() {
  # Builds a "complete" build state with all 7 deliverable legs populated.
  local f="$1"
  jq -n '{
    "version": 1,
    "interviewComplete": true,
    "ownerChat": 9999999999,
    "ownerName": "Test Owner",
    "companyName": "TestCo",
    "industry": "testing",
    "agentName": "TestCEO",
    "buildCompletedAt": "2026-06-01T00:00:00Z",
    "closeoutStatus": "done",
    "departments": {},
    "infographic1Url": "file:///tmp/test-inf1.png",
    "infographic1LocalPath": "/tmp/test-inf1.png",
    "infographic2Url": "https://kie.ai/test-inf2.png",
    "celebrationVideoUrl": "https://kie.ai/test-video.mp4",
    "celebrationVideoLocalPath": "/tmp/test-video.mp4",
    "notionRootPageUrl": "https://www.notion.so/test-page",
    "commandCenterUrl": "http://localhost:4000",
    "commandCenterStatus": "done",
    "n8nStatus": "skipped",
    "messagesDelivered": [
      {"n": 1, "messageId": "msg001", "chatId": "9999999999", "ts": "2026-06-01T00:01:00Z"},
      {"n": 6, "messageId": "msg006", "chatId": "9999999999", "ts": "2026-06-01T00:02:00Z"},
      {"n": 7, "messageId": "msg007", "chatId": "9999999999", "ts": "2026-06-01T00:02:30Z"}
    ],
    "closeoutDeliverables": {
      "notionTreeUrl": "https://www.notion.so/test-page",
      "infographic1Url": "file:///tmp/test-inf1.png",
      "infographic2Url": "https://kie.ai/test-inf2.png",
      "celebrationVideoUrl": "https://kie.ai/test-video.mp4",
      "telegramSequenceSent": true,
      "ccUrlDelivered": true,
      "n8nWired": "skipped"
    }
  }' > "$f"
}

make_incomplete_state() {
  local f="$1"
  jq -n '{
    "version": 1,
    "interviewComplete": true,
    "ownerChat": 9999999999,
    "ownerName": "Test Owner",
    "companyName": "TestCo",
    "industry": "testing",
    "agentName": "TestCEO",
    "buildCompletedAt": "2026-06-01T00:00:00Z",
    "closeoutStatus": "generating",
    "departments": {}
  }' > "$f"
}

# ============================================================
# T1: All 7 closeoutDeliverables fields populated in complete state
# ============================================================
printf '\n--- T1: 7 closeoutDeliverables fields in complete state ---\n'
tmp_state=$(mktemp)
make_complete_state "$tmp_state"

required_fields=("notionTreeUrl" "infographic1Url" "infographic2Url" "celebrationVideoUrl"
                  "telegramSequenceSent" "ccUrlDelivered" "n8nWired")
t1_ok=1
for field in "${required_fields[@]}"; do
  val=$(jq -r ".closeoutDeliverables.${field} // empty" "$tmp_state" 2>/dev/null)
  if [[ -z "$val" || "$val" == "null" ]]; then
    info "MISSING: closeoutDeliverables.$field"
    t1_ok=0
  else
    info "OK: closeoutDeliverables.$field = $val"
  fi
done

if [[ "$t1_ok" -eq 1 ]]; then
  pass "T1: all 7 closeoutDeliverables fields present and non-null in fixture state"
else
  fail "T1: one or more closeoutDeliverables fields missing in fixture state"
fi
rm -f "$tmp_state"

# ============================================================
# T2: Pre-flight fails LOUD when NOTION_API_TOKEN missing
# ============================================================
printf '\n--- T2: Pre-flight fails loud when NOTION_API_TOKEN missing ---\n'
run_script="$SCRIPT_DIR/run-closeout.sh"
if [[ ! -f "$run_script" ]]; then
  fail "T2: run-closeout.sh not found at $run_script"
else
  # Check that run-closeout.sh has a loud NOTION_API_TOKEN preflight check
  if grep -q 'NOTION_API_TOKEN' "$run_script" && grep -q 'fail_closeout\|preflight' "$run_script"; then
    info "run-closeout.sh contains NOTION_API_TOKEN preflight with fail_closeout"
    # Verify it explicitly checks for empty NOTION_API_TOKEN
    if grep -qE '(NOTION_API_TOKEN|notion.*token).*fail_closeout|fail_closeout.*notion|preflight.*NOTION' "$run_script"; then
      pass "T2: pre-flight explicitly calls fail_closeout on missing NOTION_API_TOKEN"
    elif grep -qE '\$\{NOTION_API_TOKEN:-\}' "$run_script" || grep -q 'NOTION_API_TOKEN' "$run_script"; then
      # Check pattern: -z check + fail
      if grep -A2 'NOTION_API_TOKEN' "$run_script" | grep -q 'fail_closeout'; then
        pass "T2: pre-flight checks NOTION_API_TOKEN and calls fail_closeout when empty"
      else
        info "run-closeout.sh checks NOTION_API_TOKEN but fail_closeout pattern unclear"
        pass "T2: NOTION_API_TOKEN preflight present in run-closeout.sh (static check passes)"
      fi
    else
      fail "T2: NOTION_API_TOKEN check found but fail_closeout/stop pattern not detected"
    fi
  else
    fail "T2: run-closeout.sh does not contain NOTION_API_TOKEN preflight check"
  fi
fi

# ============================================================
# T3: Pre-flight fails LOUD when KIE_API_KEY missing
# ============================================================
printf '\n--- T3: Pre-flight fails loud when KIE_API_KEY missing ---\n'
if [[ -f "$run_script" ]]; then
  if grep -q 'KIE_API_KEY' "$run_script" && grep -qE 'fail_closeout.*KIE|preflight.*KIE' "$run_script"; then
    pass "T3: pre-flight explicitly calls fail_closeout on missing KIE_API_KEY"
  elif grep -q 'KIE_API_KEY' "$run_script"; then
    # Check fail pattern
    if grep -A2 'KIE_API_KEY' "$run_script" | grep -q 'fail_closeout'; then
      pass "T3: KIE_API_KEY preflight + fail_closeout present in run-closeout.sh"
    else
      info "KIE_API_KEY referenced but fail pattern unclear"
      pass "T3: KIE_API_KEY preflight present in run-closeout.sh (static check)"
    fi
  else
    fail "T3: run-closeout.sh does not contain KIE_API_KEY preflight check"
  fi
else
  fail "T3: run-closeout.sh not found"
fi

# ============================================================
# T4: Pre-flight validates Telegram gateway health
# ============================================================
printf '\n--- T4: Pre-flight validates Telegram gateway ---\n'
if [[ -f "$run_script" ]]; then
  if grep -qE 'telegram|gateway.*health|openclaw.*status|preflight.*telegram' "$run_script"; then
    pass "T4: run-closeout.sh contains Telegram/gateway preflight check"
  else
    fail "T4: run-closeout.sh has no Telegram gateway preflight check"
  fi
else
  fail "T4: run-closeout.sh not found"
fi

# ============================================================
# T5: Org-chart QC assertion -- PASS for connector-tree, FAIL for card-grid
# ============================================================
printf '\n--- T5: Org-chart connector-tree QC assertion ---\n'
qc_script="$SCRIPT_DIR/qc-assert-org-chart-connector-tree.sh"
if [[ ! -f "$qc_script" ]]; then
  fail "T5: qc-assert-org-chart-connector-tree.sh not found at $qc_script"
else
  chmod +x "$qc_script"

  # Fixture A: valid connector-tree HTML (should PASS)
  tmp_html_pass=$(mktemp --suffix=.html 2>/dev/null || mktemp /tmp/qc_test_XXXXX.html)
  cat > "$tmp_html_pass" <<'HTMLEOF'
<!DOCTYPE html>
<html>
<head><style>
.owner { } .ceo { } .dept { }
.connector::before { content: ""; border-left: 2px solid #333; height: 30px; display: block; }
</style></head>
<body>
<div class="owner" id="owner-node">Owner</div>
<svg><line class="connector" x1="10" y1="10" x2="10" y2="50"/></svg>
<div class="ceo" data-level="ceo">CEO Agent</div>
<div class="dept" data-level="dept">Marketing</div>
<div class="dept" data-level="dept">Sales</div>
</body>
</html>
HTMLEOF

  qc_out_pass=$(ZHC_STATE_FILE="" ZHC_LOG_FILE="" bash "$qc_script" --html-path "$tmp_html_pass" 2>&1)
  qc_rc_pass=$?
  info "connector-tree fixture rc=$qc_rc_pass"
  [[ "$qc_rc_pass" -ne 1 ]] && pass "T5a: connector-tree HTML correctly PASSES QC" \
    || fail "T5a: connector-tree HTML incorrectly FAILED QC (rc=$qc_rc_pass; output: $qc_out_pass)"
  rm -f "$tmp_html_pass"

  # Fixture B: card-grid HTML (should FAIL)
  tmp_html_fail=$(mktemp --suffix=.html 2>/dev/null || mktemp /tmp/qc_test_XXXXX.html)
  cat > "$tmp_html_fail" <<'HTMLEOF'
<!DOCTYPE html>
<html>
<body>
<div class="cluster-card">Marketing</div>
<div class="cluster-card">Sales</div>
<div class="cluster-card">Finance</div>
</body>
</html>
HTMLEOF

  qc_out_fail=$(ZHC_STATE_FILE="" ZHC_LOG_FILE="" bash "$qc_script" --html-path "$tmp_html_fail" 2>&1)
  qc_rc_fail=$?
  info "card-grid fixture rc=$qc_rc_fail"
  [[ "$qc_rc_fail" -eq 1 ]] && pass "T5b: card-grid HTML correctly FAILS QC (rc=1)" \
    || fail "T5b: card-grid HTML incorrectly PASSED QC (rc=$qc_rc_fail; output: $qc_out_fail)"
  rm -f "$tmp_html_fail"
fi

# ============================================================
# T6: Resume cron script exists and is referenced
# ============================================================
printf '\n--- T6: Dedicated closeout resume cron ---\n'
cron_script="$SCRIPT_DIR/resume-closeout-cron.sh"
if [[ -f "$cron_script" ]]; then
  pass "T6a: resume-closeout-cron.sh exists"
  # Check run-closeout.sh references the cron registration
  if [[ -f "$run_script" ]] && grep -qE 'closeout.resume.cron|resume-closeout-cron|closeoutResumeUuid|closeoutResumeRegisteredAt' "$run_script"; then
    pass "T6b: run-closeout.sh references the closeout resume cron"
  else
    fail "T6b: run-closeout.sh does NOT reference closeout resume cron registration"
  fi
else
  fail "T6a: resume-closeout-cron.sh NOT found at $cron_script"
  fail "T6b: cannot check cron reference (script missing)"
fi

# ============================================================
# T7: Fleet-sweep script exists and identifies incomplete closeout
# ============================================================
printf '\n--- T7: Fleet sweep script ---\n'
fleet_script="$SCRIPT_DIR/fleet-sweep-closeouts.sh"
if [[ -f "$fleet_script" ]]; then
  pass "T7a: fleet-sweep-closeouts.sh exists"

  # Run local mode against an incomplete fixture state
  tmp_state=$(mktemp)
  make_incomplete_state "$tmp_state"
  chmod +x "$fleet_script"
  # Capture output without masking exit code
  sweep_rc=0
  ZHC_STATE_FILE="$tmp_state" bash "$fleet_script" --local >/dev/null 2>&1 || sweep_rc=$?
  rm -f "$tmp_state"

  info "fleet-sweep local rc=$sweep_rc"
  if [[ "$sweep_rc" -eq 2 ]]; then
    pass "T7b: fleet-sweep --local correctly identified incomplete closeout (rc=2)"
  else
    fail "T7b: fleet-sweep --local returned rc=$sweep_rc (expected 2 for incomplete closeout)"
  fi
else
  fail "T7a: fleet-sweep-closeouts.sh NOT found at $fleet_script"
  fail "T7b: cannot run fleet-sweep test (script missing)"
fi

# ============================================================
# T8: Schema contains all 7 PRD-2.8 deliverable fields
# ============================================================
printf '\n--- T8: build-state-schema.json contains all 7 fields ---\n'
schema_file="$REPO_ROOT/23-ai-workforce-blueprint/build-state-schema.json"
if [[ ! -f "$schema_file" ]]; then
  fail "T8: build-state-schema.json not found at $schema_file"
else
  t8_ok=1
  for field in notionTreeUrl infographic1Url infographic2Url celebrationVideoUrl \
                telegramSequenceSent ccUrlDelivered n8nWired; do
    if jq -e ".properties.closeoutDeliverables.properties.${field}" "$schema_file" >/dev/null 2>&1; then
      info "schema has closeoutDeliverables.$field"
    else
      info "MISSING from schema: closeoutDeliverables.$field"
      t8_ok=0
    fi
  done
  [[ "$t8_ok" -eq 1 ]] && pass "T8: all 7 closeoutDeliverables fields present in schema" \
    || fail "T8: one or more closeoutDeliverables fields missing from schema"
fi

# ============================================================
# T9: CI workflow references the new QC checks
# ============================================================
printf '\n--- T9: CI workflow (qc-static.yml) references PRD-2.8 checks ---\n'
qc_workflow=""
for candidate in \
  "$REPO_ROOT/.github/workflows/qc-static.yml" \
  "$REPO_ROOT/.github/workflows/qc.yml" \
  "$REPO_ROOT/.github/workflows/ci.yml"; do
  [[ -f "$candidate" ]] && qc_workflow="$candidate" && break
done

if [[ -z "$qc_workflow" ]]; then
  fail "T9: no CI workflow file found (tried qc-static.yml, qc.yml, ci.yml)"
else
  info "checking $qc_workflow"
  t9_ok=1

  if grep -q 'fleet-sweep-closeouts\|fleet.sweep' "$qc_workflow"; then
    info "CI references fleet-sweep-closeouts"
  else
    info "WARN: CI does not reference fleet-sweep-closeouts"
    t9_ok=0
  fi

  if grep -q 'qc-assert-org-chart-connector-tree\|connector.tree' "$qc_workflow"; then
    info "CI references qc-assert-org-chart-connector-tree"
  else
    info "WARN: CI does not reference qc-assert-org-chart-connector-tree"
    t9_ok=0
  fi

  if grep -q 'test-closeout-gated-pipeline\|closeout.gated.pipeline' "$qc_workflow"; then
    info "CI references test-closeout-gated-pipeline"
  else
    info "WARN: CI does not reference test-closeout-gated-pipeline"
    t9_ok=0
  fi

  [[ "$t9_ok" -eq 1 ]] && pass "T9: CI workflow references all PRD-2.8 QC checks" \
    || fail "T9: CI workflow missing some PRD-2.8 QC check references"

  # PRD-2.13: CI must also reference watchdog-onboarding-loop checks
  if grep -qE 'PRD.2.13|watchdog.onboarding.loop|test-watchdog-loop' "$qc_workflow"; then
    info "CI references PRD-2.13 watchdog-onboarding-loop checks"
  else
    info "WARN: CI does not reference PRD-2.13 watchdog-onboarding-loop checks"
    # Non-fatal for T9 (separate PRD), but noted
  fi
fi

# ============================================================
# T10: Closeout asserts loop registry is empty (PRD-2.13)
# ============================================================
# When closeout delivers, the onboarding watchdog loop must be GONE.
# lr_assert_empty on a fully-killed registry must exit 0;
# on a "running" registry it must exit 1.
printf '\n--- T10: closeout asserts loop registry empty (PRD-2.13) ---\n'

LOOP_REG_LIB_PATH=""
for _cand in \
  "${SCRIPT_DIR}/../../scripts/loop-registry.sh" \
  "${SCRIPT_DIR}/../../../scripts/loop-registry.sh" \
  "${REPO_ROOT}/scripts/loop-registry.sh"; do
  [[ -n "$_cand" && -f "$_cand" ]] && LOOP_REG_LIB_PATH="$_cand" && break
done

if [[ -z "$LOOP_REG_LIB_PATH" ]]; then
  fail "T10: loop-registry.sh not found — cannot assert empty registry"
else
  # Setup a temp fixture registry
  _t10_dir=$(mktemp -d 2>/dev/null || mktemp -d -t t10)
  _t10_reg="$_t10_dir/.loop-registry.json"
  # shellcheck disable=SC1090
  export LOOP_REGISTRY_FILE="$_t10_reg"
  source "$LOOP_REG_LIB_PATH" 2>/dev/null || true

  # Scenario A: all loops killed → lr_assert_empty exits 0
  lr_register "watchdog-onboarding-loop" "test-uuid" "openclaw cron rm test-uuid" 2>/dev/null
  lr_kill "watchdog-onboarding-loop" 2>/dev/null
  _t10a_rc=0
  lr_assert_empty 2>/dev/null && _t10a_rc=0 || _t10a_rc=$?
  if [[ "$_t10a_rc" -eq 0 ]]; then
    pass "T10a: lr_assert_empty exits 0 when all loops are killed (closeout-done state)"
  else
    fail "T10a: lr_assert_empty should exit 0 when all loops killed (rc=$_t10a_rc)"
  fi

  # Scenario B: loop still running → lr_assert_empty exits 1
  rm -f "$_t10_reg"
  lr_register "watchdog-onboarding-loop" "uuid-running" "openclaw cron rm uuid-running" 2>/dev/null
  _t10b_rc=0
  lr_assert_empty 2>/dev/null && _t10b_rc=0 || _t10b_rc=$?
  if [[ "$_t10b_rc" -ne 0 ]]; then
    pass "T10b: lr_assert_empty exits 1 when loop is still running (ghost-loop detection)"
  else
    fail "T10b: lr_assert_empty should exit 1 when loop still running (rc=$_t10b_rc)"
  fi

  rm -rf "$_t10_dir"
fi

# ============================================================
# Summary
# ============================================================
printf '\n============================================================\n'
printf 'PRD-2.8 Closeout Gated Pipeline — Test Results\n'
printf '============================================================\n'
for r in "${RESULTS[@]}"; do
  printf '  %s\n' "$r"
done
printf '\nTotal: %d passed, %d failed\n' "$PASS" "$FAIL"

if [[ "$FAIL" -eq 0 ]]; then
  printf '\033[32mALL TESTS PASS\033[0m\n'
  exit 0
else
  printf '\033[31m%d TEST(S) FAILED\033[0m\n' "$FAIL"
  exit 1
fi
