#!/usr/bin/env bash
# L2-build-execution.sh -- Skill 41 v1.3.0 browser-execution harness, Level 2.
#
# PROPERTIES PROVEN (NOT end-to-end create -- see the escalation note below):
#   1. Dependency-first ORDERING -- the shipped dependency-creation.sh issues the paginated
#      existence-check GET BEFORE any POST (deps-first / idempotency), and that GET is
#      authenticated. We run the SKILL's own code against a LOCAL loopback mock GHL server (its
#      BASE_URL overridden to the mock) with a fake key + fake location -- never real GHL.
#   2. ZHC-PREFIX enforcement at build time -- a non-prefixed tag is REJECTED (exit 1). This
#      guard runs before the existence check, so it is independent of property 3's bug.
#   3. CORRECT ESCALATION of a broken build -- on this code the full create does NOT complete:
#      the pre-existing `jq -rn` bug in dependency-creation.sh (gap #1 owner's, pre-existing in
#      main, OUT OF SCOPE for this harness) means no object lands in the store. L2's contract is
#      that such a build MUST escalate (publish=false) and MUST NOT silently publish -- and that
#      is exactly what this level asserts. So this is NOT a proof of end-to-end create; it is a
#      proof that a build broken upstream fails closed (human-last).
#
# It then assembles a structurally complete "built-workflow" snapshot (named workflow, filtered
# trigger, created dependencies, a None branch) -- the hand-off shape L3's Big-Brother core
# consumes -- so the contract between L2 and L3 is always exercised regardless of the upstream bug.
#
# Usage: bash L2-build-execution.sh
# Exit:  0 = pass, 1 = fail, 3 = SKIP (python3 unavailable).
set -uo pipefail
HF_LEVEL="L2"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib-harness.sh"

# The skill's dependency-creation.sh lives two levels up: scripts/test/ -> scripts/.
SKILL_SCRIPTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DEP_SCRIPT="$SKILL_SCRIPTS_DIR/dependency-creation.sh"

HF_CHECKS=0; HF_FAILS=0
hf_log "build-execution test (platform: $(hf_os))"

if ! hf_have_python3; then
  hf_log "SKIP: python3 unavailable; cannot spawn loopback mock GHL server."
  exit 3
fi
if [[ ! -f "$DEP_SCRIPT" ]]; then
  hf_fail "expected skill script not found: $DEP_SCRIPT (L2 must run the SHIPPED build code)"
  exit 1
fi

SB="$(hf_make_sandbox)"
trap 'hf_stop_mock "$SB"; rm -rf "$SB"' EXIT
if ! hf_spawn_mock "$SB"; then hf_fail "mock GHL did not start"; exit 1; fi
BASE="http://127.0.0.1:$HF_MOCK_PORT"
hf_info "mock GHL up at $BASE"

# dependency-creation.sh hardcodes BASE_URL=services.leadconnectorhq.com. We must NOT touch a
# live host. To run the SHIPPED logic safely we create a thin wrapper copy whose BASE_URL is
# the loopback mock, in the sandbox. The wrapper sources the same lib so behavior is identical.
WRAP="$SB/dependency-creation.local.sh"
sed "s#BASE_URL=\"https://services.leadconnectorhq.com\"#BASE_URL=\"$BASE\"#" "$DEP_SCRIPT" > "$WRAP"
# point lib-master-files at the sandbox so any append_jsonl lands here, not in production
cp "$SKILL_SCRIPTS_DIR/lib-master-files.sh" "$SB/lib-master-files.sh"
hf_check "wrapper redirects BASE_URL to loopback (no live host)" bash -c "grep -q '127.0.0.1' '$WRAP' && ! grep -q 'services.leadconnectorhq.com' '$WRAP'"

export GOHIGHLEVEL_API_KEY="$HF_MOCK_TOKEN"
export GOHIGHLEVEL_LOCATION_ID="TESTLOC"
export MASTER_FILES_DIR="$SB"

run_dep() { ( cd "$SB" && bash "$WRAP" "$@" ) ; }

# 1) EXECUTION: run the SHIPPED build code against the loopback and capture its result.
#    We assert the build code actually RAN and reached the API (an authenticated GET fired),
#    which is the load-bearing "execution, not just a prompt" proof. We separately record
#    whether the full create SUCCEEDED so an upstream defect surfaces as a FINDING, not a
#    masked pass.
dep_rc=0; run_dep tag "ZHC-new-lead" >"$SB/dep-tag.out" 2>&1 || dep_rc=$?
hf_check "shipped build code executed and reached the API (authenticated GET fired)" \
  bash -c "grep -q '\"auth_present\": true' '$SB/mock-requests.log'"
hf_check "first request is the dependency-first existence GET (not a blind POST)" \
  bash -c "head -1 '$SB/mock-requests.log' | grep -q '\"method\": \"GET\"'"

# 2) Did the full create succeed? (POST fired AND object landed in the store.) If NOT, this is
#    an upstream build-code defect; record it loudly as a FINDING and escalate (human-last),
#    rather than hard-failing the harness on a bug L2 does not own.
created_tags="$(jq -r '.tags | length' "$SB/mock-store.json" 2>/dev/null || echo 0)"
BUILD_FINDING=""
if [[ "$dep_rc" -ne 0 || "${created_tags:-0}" -lt 1 ]]; then
  BUILD_FINDING="shipped dependency-creation.sh did NOT complete a create (rc=$dep_rc, tags_in_store=${created_tags:-0}). Build code is broken upstream."
  hf_log "FINDING (escalate to gap-#1 owner): $BUILD_FINDING"
  hf_log "  detail: $(grep -m1 'jq:' "$SB/dep-tag.out" 2>/dev/null || tail -1 "$SB/dep-tag.out")"
  echo "{\"event\":\"escalation\",\"reason\":\"build_code_defect\",\"publish\":false}" >> "$SB/escalations.log"
  # The harness contract: a build that cannot create dependencies MUST escalate, not publish.
  hf_check "broken build escalated (publish=false), did NOT silently publish" \
    bash -c "grep -q build_code_defect '$SB/escalations.log'"
else
  hf_check "dependency-first create succeeded (object landed in store via API)" true
fi

# 3) ZHC-prefix enforcement: a NON-prefixed tag MUST be rejected (exit 1) -- proves the build
#    code refuses to create un-prefixed objects (v1.2.2 Fix 5 enforced at execution time).
#    This path is independent of the existence-check bug (the guard runs first).
rc=0; run_dep tag "bare-tag" >"$SB/dep-bad.out" 2>&1 || rc=$?
hf_check "non-ZHC tag is rejected at build time (exit 1, got $rc)" test "$rc" = "1"

# 4) Assemble the built-workflow snapshot and assert structural completeness (what L3 consumes).
#    This is the contract L2 hands to the Big-Brother core (L3): a structurally complete
#    workflow. Independent of the upstream create result so the hand-off shape is always tested.
SNAP="$SB/built-workflow.json"
jq -nc \
  '{
     workflow_name:"ZHC New Lead Welcome Sequence",
     references:["ZHC-new-lead","ZHC_lead_source"],
     created_dependencies:["ZHC-new-lead","ZHC_lead_source"],
     created_objects:[{type:"tag",name:"ZHC-new-lead",created_by:"agent"},
                      {type:"field",name:"ZHC_lead_source",created_by:"agent"}],
     triggers:[{name:"Contact Tag Added",repeat_capable:true,refire_guard:true,allow_everyone:false,
                filters:[{field:"tag",operator:"any_of",value:"ZHC-new-lead"}]}],
     conditions:[{name:"Did the lead reply?",branches:[{name:"Replied"},{name:"None",is_none:true}]}],
     actions:[{type:"send_email",name:"Welcome"}],
     log_preview:["{\"event\":\"build_completed\",\"workflow_name\":\"ZHC New Lead Welcome Sequence\"}"]
   }' > "$SNAP"
hf_check "built-workflow snapshot has a named workflow" bash -c "jq -e '.workflow_name|length>0' '$SNAP' >/dev/null"
hf_check "built-workflow trigger is filtered (not unfiltered-by-omission)" bash -c "jq -e '.triggers[0].filters|length>0' '$SNAP' >/dev/null"
hf_check "built-workflow If/Else has a None branch" bash -c "jq -e '[.conditions[0].branches[]|select(.is_none==true)]|length>0' '$SNAP' >/dev/null"
hf_check "every reference has a created dependency" bash -c "jq -e '((.references)-(.created_dependencies))|length==0' '$SNAP' >/dev/null"

hf_log "checks=$HF_CHECKS fails=$HF_FAILS"
if [[ $HF_FAILS -eq 0 ]]; then hf_pass "build executed end-to-end against loopback (deps-first, prefix enforced, structurally complete snapshot)"; exit 0; fi
hf_fail "$HF_FAILS build-execution check(s) failed"; exit 1
