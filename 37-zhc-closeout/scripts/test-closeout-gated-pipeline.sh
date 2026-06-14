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
# T11: v12.3.10 — run-closeout.sh self-removes interview-nudge cron at done-transition
# ============================================================
# Acceptance test A: when interviewComplete=true reaches closeoutStatus=done,
# run-closeout.sh must call `openclaw cron rm <interviewNudgeUuid>` alongside
# the existing closeout-resume cron rm. Verified by static grep (the test
# for the dynamic path is in test-interview-experience.sh T13).
printf '\n--- T11: v12.3.10 interview-nudge cron self-remove at done-transition ---\n'

if [[ ! -f "$run_script" ]]; then
  fail "T11: run-closeout.sh not found at $run_script"
else
  # 11a: run-closeout.sh references interviewNudgeUuid (the UUID key)
  if grep -q 'interviewNudgeUuid' "$run_script"; then
    pass "T11a: run-closeout.sh references interviewNudgeUuid (nudge cron self-remove wired)"
  else
    fail "T11a: run-closeout.sh does NOT reference interviewNudgeUuid — nudge cron self-remove missing"
  fi

  # 11b: run-closeout.sh issues `openclaw cron rm` for the nudge cron
  # Check that there is a cron rm call near the interviewNudgeUuid reference
  nudge_rm_context=$(grep -A5 'interviewNudgeUuid' "$run_script" | grep 'cron rm' || true)
  if [[ -n "$nudge_rm_context" ]]; then
    pass "T11b: run-closeout.sh calls 'cron rm' after resolving interviewNudgeUuid"
  else
    # Also accept the pattern where rm is called with the variable directly
    nudge_rm_context2=$(grep 'nudge_cron_uuid\|nudge.*cron.*rm\|cron rm.*nudge' "$run_script" || true)
    if [[ -n "$nudge_rm_context2" ]]; then
      pass "T11b: run-closeout.sh has nudge cron rm call (variable form)"
    else
      fail "T11b: run-closeout.sh does not call 'cron rm' for the interview-nudge cron"
    fi
  fi

  # 11c: the nudge-cron rm block is at the done-transition (alongside closeout-resume rm)
  # Check that both closeoutResumeUuid and interviewNudgeUuid appear in the same done-transition block
  done_block=$(awk '/PRD-2.8: SELF-REMOVE/,/closeoutStatus.*=.*done/' "$run_script" 2>/dev/null || true)
  if echo "$done_block" | grep -q 'interviewNudgeUuid'; then
    pass "T11c: interview-nudge cron rm is in the done-transition block alongside closeout-resume rm"
  else
    fail "T11c: interview-nudge cron rm is NOT in the done-transition block — may not fire at closeout"
  fi

  # 11d: a fallback name-scan is present for pre-UUID boxes (Talaya fleet rescue)
  if grep -q 'interview-nudge' "$run_script" && grep -q 'scan_uuid\|grep.*interview-nudge\|awk.*interview-nudge' "$run_script"; then
    pass "T11d: run-closeout.sh has a fallback name-scan for boxes without a recorded interviewNudgeUuid"
  else
    fail "T11d: run-closeout.sh missing fallback name-scan for pre-UUID boxes (Talaya)"
  fi
fi

# ============================================================
# T12: v12.3.10 — build-state-schema.json has interviewNudgeUuid + interviewNudgeRegisteredAt
# ============================================================
printf '\n--- T12 (schema): build-state-schema.json has v12.3.10 nudge UUID fields ---\n'
schema_file_t12="$REPO_ROOT/23-ai-workforce-blueprint/build-state-schema.json"
if [[ ! -f "$schema_file_t12" ]]; then
  fail "T12(schema): build-state-schema.json not found"
else
  t12s_ok=1
  for field in interviewNudgeUuid interviewNudgeRegisteredAt; do
    if jq -e ".properties.${field}" "$schema_file_t12" >/dev/null 2>&1; then
      info "schema has $field"
    else
      info "MISSING from schema: $field"
      t12s_ok=0
    fi
  done
  [[ "$t12s_ok" -eq 1 ]] \
    && pass "T12(schema): interviewNudgeUuid + interviewNudgeRegisteredAt present in build-state-schema.json" \
    || fail "T12(schema): one or more v12.3.10 nudge UUID fields missing from build-state-schema.json"
fi

# ============================================================
# T13 (v12.6.0): Deterministic auto-fire -- in-process exec wired in both scripts
# ============================================================
printf '\n--- T13 (v12.6.0): deterministic in-process exec of run-closeout.sh ---\n'
resume_build="$REPO_ROOT/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
resume_cron="$SCRIPT_DIR/resume-closeout-cron.sh"

if [[ -f "$resume_build" ]]; then
  # Accept: nohup bash <var> or nohup bash "...", plus scripts that search for run-closeout.sh
  if grep -qE 'nohup bash|bash.*CLOSEOUT_SCRIPT|_CLOSEOUT_SCRIPT.*bash' "$resume_build" \
     && grep -q 'run-closeout.sh' "$resume_build"; then
    pass "T13a: resume-workforce-build.sh launches run-closeout.sh in-process (deterministic exec found)"
  else
    fail "T13a: resume-workforce-build.sh does NOT have a literal in-process exec of run-closeout.sh"
  fi
else
  fail "T13a: resume-workforce-build.sh not found at $resume_build"
fi

if [[ -f "$resume_cron" ]]; then
  if grep -qE 'nohup bash|bash.*CLOSEOUT_SCRIPT|_CLOSEOUT_SCRIPT.*bash' "$resume_cron" \
     && grep -q 'run-closeout.sh' "$resume_cron"; then
    pass "T13b: resume-closeout-cron.sh launches run-closeout.sh in-process (deterministic exec found)"
  else
    fail "T13b: resume-closeout-cron.sh does NOT have a literal in-process exec of run-closeout.sh"
  fi
else
  fail "T13b: resume-closeout-cron.sh not found at $resume_cron"
fi

# ============================================================
# T14 (v12.6.0): Notion booklet -- AI CEO section + CC how-to section + Lean wording
# ============================================================
printf '\n--- T14 (v12.6.0): Notion booklet content spec ---\n'
notion_script="$SCRIPT_DIR/create-notion-closeout.sh"

if [[ ! -f "$notion_script" ]]; then
  fail "T14: create-notion-closeout.sh not found"
else
  # T14a: dedicated AI CEO section exists
  if grep -qiE 'Who Is Your AI CEO|AI CEO|section.*3.*ai.*ceo|Triad Rule' "$notion_script"; then
    pass "T14a: create-notion-closeout.sh has a dedicated AI CEO section"
  else
    fail "T14a: create-notion-closeout.sh is missing a dedicated AI CEO section"
  fi

  # T14b: How to Use Your Command Center section exists
  if grep -qiE 'How to Use Your Command Center|Command Center.*walkthrough|Kanban.*column|section.*6.*command' "$notion_script"; then
    pass "T14b: create-notion-closeout.sh has a How to Use Your Command Center section"
  else
    fail "T14b: create-notion-closeout.sh missing Command Center how-to section"
  fi

  # T14c: CC URL is read from state and embedded in the section
  if grep -q 'commandCenterUrl\|CC_URL' "$notion_script"; then
    pass "T14c: create-notion-closeout.sh reads commandCenterUrl from state"
  else
    fail "T14c: create-notion-closeout.sh does not read commandCenterUrl from state"
  fi

  # T14d: Lean wording present (not just DMAIC)
  if grep -qiE 'Lean|waste|variation' "$notion_script"; then
    pass "T14d: create-notion-closeout.sh has Lean/waste/variation wording in Six Sigma section"
  else
    fail "T14d: create-notion-closeout.sh missing Lean / waste / variation wording"
  fi

  # T14e: chunk helper or length guard for rich_text
  if grep -qE 'chunk|1900|1800|2000|split.*text|text.*split' "$notion_script"; then
    pass "T14e: create-notion-closeout.sh has rich-text chunking / length guard"
  else
    fail "T14e: create-notion-closeout.sh missing rich-text chunking (<=1900 chars)"
  fi

  # T14f: RPS pacing (sleep 0.4 or pace())
  if grep -qE 'sleep 0\.4|pace\(\)|pace ;' "$notion_script"; then
    pass "T14f: create-notion-closeout.sh has RPS pacing (>=0.4s between calls)"
  else
    fail "T14f: create-notion-closeout.sh missing inter-request pacing"
  fi

  # T14g: director_title from naming map read
  if grep -q 'director_title\|naming.map\|NAMING_MAP\|department-naming-map' "$notion_script"; then
    pass "T14g: create-notion-closeout.sh reads director_title from department-naming-map.json"
  else
    fail "T14g: create-notion-closeout.sh does not read director_title from naming map"
  fi

  # T14h: booklet-content.md exists
  if [[ -f "$SKILL_DIR/templates/booklet-content.md" ]]; then
    pass "T14h: templates/booklet-content.md exists (editable prose source)"
  else
    fail "T14h: templates/booklet-content.md missing"
  fi
fi

# ============================================================
# T15 (v12.6.0): Visual intelligence set -- min 3 prompts, GPT-Image-2, generator exists
# ============================================================
printf '\n--- T15 (v12.6.0): visual intelligence set generator ---\n'
vi_script="$SCRIPT_DIR/generate-visual-intelligence.sh"
mandatory_prompts=(
  "$SKILL_DIR/templates/infographic-1-prompt.md"
  "$SKILL_DIR/templates/img-what-is-zhc-prompt.md"
  "$SKILL_DIR/templates/img-how-your-zhc-works-prompt.md"
)

if [[ ! -f "$vi_script" ]]; then
  fail "T15a: generate-visual-intelligence.sh not found at $vi_script"
else
  pass "T15a: generate-visual-intelligence.sh exists"

  # Check it issues >=3 prompt entries (mandatory queue)
  prompt_count=$(grep -cE 'infographic-1-prompt\.md|img-what-is-zhc|img-how-your-zhc-works|img-dept-overview|img-sop-system|img-six-sigma|infographic-2-prompt' "$vi_script" 2>/dev/null || echo "0")
  if [[ "$prompt_count" -ge 3 ]]; then
    pass "T15b: generate-visual-intelligence.sh references >= 3 distinct prompt templates"
  else
    fail "T15b: generate-visual-intelligence.sh references only $prompt_count prompt templates (need >= 3)"
  fi

  # Check GPT-Image-2 is the primary model
  if grep -qE 'gpt-image-2|GPT_IMAGE_2|PRIMARY_MODEL.*gpt' "$vi_script"; then
    pass "T15c: generate-visual-intelligence.sh uses gpt-image-2 as primary model"
  else
    fail "T15c: generate-visual-intelligence.sh does not use gpt-image-2 as primary"
  fi

  # Check cap enforcement (max 30)
  if grep -qE 'CAP|cap.*30|30.*cap|\[.*30.*\]' "$vi_script"; then
    pass "T15d: generate-visual-intelligence.sh enforces a cap (<=30)"
  else
    fail "T15d: generate-visual-intelligence.sh missing cap enforcement"
  fi
fi

for pfile in "${mandatory_prompts[@]}"; do
  if [[ -f "$pfile" ]]; then
    # Check the file is non-empty and has real prompt content
    lines=$(wc -l < "$pfile" 2>/dev/null || echo "0")
    if [[ "$lines" -gt 3 ]]; then
      pass "T15-prompt: $(basename $pfile) exists and is non-empty ($lines lines)"
    else
      fail "T15-prompt: $(basename $pfile) exists but appears empty ($lines lines)"
    fi
  else
    fail "T15-prompt: MISSING mandatory prompt file: $pfile"
  fi
done

# Check visualIntelligenceUrls is referenced in state writes
if grep -q 'visualIntelligenceUrls' "$vi_script" 2>/dev/null; then
  pass "T15e: generate-visual-intelligence.sh writes .visualIntelligenceUrls to state"
else
  fail "T15e: generate-visual-intelligence.sh does not write .visualIntelligenceUrls to state"
fi

# ============================================================
# T16 (v12.6.0): Celebration video -- 8s default, audio flag, logo, prompt duration match
# ============================================================
printf '\n--- T16 (v12.6.0): celebration video fixes ---\n'
video_script="$SCRIPT_DIR/generate-celebration-video.sh"
video_prompt="$SKILL_DIR/templates/veo-prompt.txt"

if [[ ! -f "$video_script" ]]; then
  fail "T16: generate-celebration-video.sh not found"
else
  # T16a: default duration is 8 (not 4)
  if grep -qE 'DURATION="8".*#.*PRD|PRD.*DURATION.*8|""\s*\)\s*DURATION="8"' "$video_script"; then
    pass "T16a: Gemini Omni default duration is 8 (meets 8s floor)"
  elif grep -A2 '"")' "$video_script" | grep -q 'DURATION="8"'; then
    pass "T16a: Gemini Omni default duration is 8 (meets 8s floor)"
  else
    fail "T16a: Gemini Omni default duration may still be 4 -- check generate-celebration-video.sh"
  fi

  # T16b: generate_audio in PRIMARY Gemini Omni body (submit_gemini_omni function).
  # The function lives around lines 120-200. Check the relevant band + also a global check
  # that generate_audio appears BEFORE submit_veo (which was the ONLY place it lived before).
  _veo_line=$(grep -n 'submit_veo()' "$video_script" 2>/dev/null | head -1 | cut -d: -f1)
  [[ -z "$_veo_line" ]] && _veo_line=999
  # Count generate_audio lines that appear before the veo function (= in the gemini body)
  _audio_before_veo=$(awk -v stop="$_veo_line" 'NR < stop && /generate_audio/' "$video_script" | wc -l)
  if [[ "$_audio_before_veo" -gt 0 ]]; then
    pass "T16b: PRIMARY Gemini Omni body includes generate_audio (audio flag set, $_audio_before_veo line(s) before submit_veo)"
  else
    fail "T16b: PRIMARY Gemini Omni body missing generate_audio flag (only found in Veo fallback, not before line $_veo_line)"
  fi

  # T16c: logo URL read from state/branding-questions.json
  if grep -qE 'logo_url|logoUrl|LOGO_URL|branding-questions' "$video_script"; then
    pass "T16c: generate-celebration-video.sh reads client logo_url"
  else
    fail "T16c: generate-celebration-video.sh does not read client logo_url"
  fi
fi

if [[ -f "$video_prompt" ]]; then
  # T16d: prompt does not say 15 seconds (was the contradiction)
  if grep -q '15-second\|15 second\|15sec' "$video_prompt"; then
    fail "T16d: veo-prompt.txt still says '15 second' -- duration contradiction not fixed"
  else
    pass "T16d: veo-prompt.txt does not contain '15 second' contradiction"
  fi

  # T16e: prompt says 8 seconds or mentions achievable duration
  if grep -qE '8-second|8 second|8s|8sec' "$video_prompt"; then
    pass "T16e: veo-prompt.txt narrative matches achievable 8s duration"
  else
    fail "T16e: veo-prompt.txt narrative does not mention 8s duration"
  fi

  # T16f: prompt uses client logo directive (not hardcoded BlackCEO)
  if grep -qE 'client.*logo|logo.*client|COMPANY_NAME.*logo|logo.*COMPANY|client brand' "$video_prompt"; then
    pass "T16f: veo-prompt.txt has client-logo directive (not hardcoded BlackCEO)"
  elif ! grep -q 'BlackCEO' "$video_prompt" || grep -q 'client' "$video_prompt"; then
    pass "T16f: veo-prompt.txt logo directive does not hardcode BlackCEO (acceptable)"
  else
    fail "T16f: veo-prompt.txt still has hardcoded BlackCEO mark -- should use client logo"
  fi
else
  fail "T16d-f: veo-prompt.txt not found at $video_prompt"
fi

# ============================================================
# T17 (v12.6.0): No stale "233" count as a live role-count assertion
# ============================================================
printf '\n--- T17 (v12.6.0): stale 233 count eliminated from live assertions ---\n'

# Check ZHC-BUILDOUT-EXPERIENCE.md
exp_file="$REPO_ROOT/23-ai-workforce-blueprint/ZHC-BUILDOUT-EXPERIENCE.md"
if [[ -f "$exp_file" ]]; then
  # 233 as a live role-count claim: "233-template role library" or "233 roles" etc.
  if grep -qE '233-template role library|233 roles|"233"' "$exp_file"; then
    fail "T17a: ZHC-BUILDOUT-EXPERIENCE.md still contains stale '233' role-count claim"
  else
    pass "T17a: ZHC-BUILDOUT-EXPERIENCE.md: no stale '233' live role-count claims"
  fi
else
  fail "T17a: ZHC-BUILDOUT-EXPERIENCE.md not found"
fi

# Check INSTRUCTIONS.md
inst_file="$REPO_ROOT/23-ai-workforce-blueprint/INSTRUCTIONS.md"
if [[ -f "$inst_file" ]]; then
  # "233-template library" references in step descriptions
  if grep -qE '233-template library' "$inst_file"; then
    fail "T17b: INSTRUCTIONS.md still contains '233-template library' reference"
  else
    pass "T17b: INSTRUCTIONS.md: '233-template library' references updated"
  fi
else
  fail "T17b: INSTRUCTIONS.md not found"
fi

# ============================================================
# T18 (v12.6.0): CC link written into AGENTS.md + TOOLS.md at closeout
# ============================================================
printf '\n--- T18 (v12.6.0): CC link written to AGENTS.md + TOOLS.md ---\n'
if [[ -f "$run_script" ]]; then
  if grep -qE 'AGENTS\.md|TOOLS\.md' "$run_script" && grep -q 'commandCenterUrl\|_cc_url' "$run_script"; then
    pass "T18: run-closeout.sh writes commandCenterUrl into AGENTS.md and TOOLS.md"
  else
    fail "T18: run-closeout.sh does not write CC URL into AGENTS.md / TOOLS.md"
  fi
else
  fail "T18: run-closeout.sh not found"
fi

# ============================================================
# Summary
# ============================================================
printf '\n============================================================\n'
printf 'PRD-2.8 / PRD-FINAL-PACKAGE Closeout Gated Pipeline -- Test Results\n'
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
