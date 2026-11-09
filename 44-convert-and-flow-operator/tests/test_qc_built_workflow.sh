#!/usr/bin/env bash
# test_qc_built_workflow.sh — S44-24 / S44-11 exit-gate proof for qc-built-workflow.sh.
#
#   bash 44-convert-and-flow-operator/tests/test_qc_built_workflow.sh
#
# Offline: a stub `caf` supplies the export and a stub verifier stands in for the approval
# flow's verifier (shared-utils/signature_launch_contract/approval_record.py). The script under
# test is COPIED into a scratch tree so its SCRIPT_DIR-relative verifier lookup resolves to the
# stub; nothing real is contacted. Exits 0 only when every case holds.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL="$(cd "$HERE/.." && pwd)"
T="$(mktemp -d "${TMPDIR:-/tmp}/qc-gate-test-XXXXXX")"
trap 'rm -rf "$T"' EXIT

mkdir -p "$T/44-convert-and-flow-operator" "$T/shared-utils/signature_launch_contract" "$T/bin" "$T/home"
cp "$SKILL/qc-built-workflow.sh" "$T/44-convert-and-flow-operator/"
ln -s "$SKILL/tools" "$T/44-convert-and-flow-operator/tools"
QC="$T/44-convert-and-flow-operator/qc-built-workflow.sh"

# Stub verifier: same call shape and failure type as the real one; accepts exactly one approval.
cat > "$T/shared-utils/signature_launch_contract/approval_record.py" <<'PY'
class ApprovalRefused(Exception):
    def __init__(self, code, message=""):
        super().__init__(code + ": " + message)
        self.code = code

def verify(approval_id, kind, plan_hash, scope, **kw):
    if approval_id != "appr-good-0001" or kind != "launch_plan_build" or plan_hash != "abcd1234":
        raise ApprovalRefused("APPROVAL-NOT-FROM-AUTHORITY", "unknown approval")
    if not set(scope) <= {"publish:DRAFT", "reentry:ONCE"}:
        raise ApprovalRefused("APPROVAL-SCOPE", "scope not covered")
    return {"ok": True}
PY

# Stub caf: copies $QC_TEST_EXPORT to --out.
cat > "$T/bin/caf" <<'SH'
#!/usr/bin/env bash
while [ $# -gt 0 ]; do [ "$1" = "--out" ] && { cp "$QC_TEST_EXPORT" "$2"; exit 0; }; shift; done
exit 1
SH
chmod +x "$T/bin/caf"

cat > "$T/export-plain.json" <<'JSON'
{"id":"WFTEST001","name":"ZHC-test","status":"draft","allowMultiple":false,"active":false,
 "workflowData":{"templates":[
  {"id":"n1","type":"sms","name":"Send","parentKey":null,"next":"n2","attributes":{"body":"hi","fromNumber":"+15555550100"}},
  {"id":"n2","type":"end","name":"Finish","parentKey":"n1"}]},
 "triggers":[{"id":"T1","type":"form_submitted","targetActionId":"n1"}]}
JSON
cat > "$T/export-waits.json" <<'JSON'
{"id":"WFTEST001","name":"ZHC-test","status":"draft","allowMultiple":false,"active":false,
 "workflowData":{"templates":[
  {"id":"n1","type":"sms","name":"Send","parentKey":null,"next":"n2","attributes":{"body":"hi","fromNumber":"+15555550100"}},
  {"id":"n2","type":"wait","name":"Wait 2 Days","parentKey":"n1","next":"n3","attributes":{"type":"time","startAfter":{"type":"days","value":2,"when":"after"}}},
  {"id":"n3","type":"wait","name":"Wait until date","parentKey":"n2","next":"n4","attributes":{"type":"date","endDate":"2026-11-26T09:00:00-05:00"}},
  {"id":"n4","type":"end","name":"Finish","parentKey":"n3"}]},
 "triggers":[{"id":"T1","type":"form_submitted","targetActionId":"n1"}]}
JSON
echo '{}' > "$T/deps.json"

# Signed PLAN MODE run files (what the approval flow records) and grade files.
plan() { printf '{"approval_id":"%s","plan_hash":"abcd1234","publish_intent":"%s","re_entry":"ONCE","build_model":"%s"}' "$1" "$2" "$3" > "$T/$4"; }
plan appr-good-0001 DRAFT build-model-a plan-good.json
plan appr-good-0001 LIVE  build-model-a plan-live.json
plan appr-forged-99 DRAFT build-model-a plan-forged.json
plan appr-good-0001 DRAFT qc-model-b    plan-samemodel.json
HUMAN="WF-1 WF-2 WF-8 WF-9 WF-10 WF-11 WF-13 WF-14 WF-16 WF-17 WF-19 WF-20"
grades() { # grades <file> [item-to-omit] [item-to-fail]
  python3 -I - "$T/$1" "${2:-}" "${3:-}" $HUMAN <<'PY'
import json, sys
out, omit, fail, items = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
g = {i: {"grade": "FAIL" if i == fail else "PASS", "observed": "read from export"} for i in items if i != omit}
json.dump({"workflow_id": "WFTEST001", "grades": g}, open(out, "w"))
PY
}
grades grades-all.json
grades grades-missing1.json WF-20
grades grades-fail1.json "" WF-8

run() { # run <export> <args...>; sets RC, OUT
  local exp="$1"; shift
  OUT="$(env PATH="$T/bin:$PATH" HOME="$T/home" OPENCLAW_PLATFORM=mac QC_TEST_EXPORT="$T/$exp" \
        bash "$QC" WFTEST001 --deps "$T/deps.json" "$@" 2>&1)"; RC=$?
}
json_field() { # json_field key [key...] : walk the --json output by keys
  printf '%s' "$OUT" | python3 -I -c '
import json, sys
t = sys.stdin.read(); d = json.loads(t[t.index("{"):t.rindex("}") + 1])
for k in sys.argv[1:]:
    d = d[k]
print(d)' "$@"
}

FAILS=0
ok()  { echo "ok   - $1"; }
bad() { echo "FAIL - $1"; echo "       rc=$RC out=$(printf '%s' "$OUT" | tr '\n' ' ' | cut -c1-400)"; FAILS=$((FAILS + 1)); }
expect_nonzero() { if [ "$RC" -ne 0 ]; then ok "$1 (rc=$RC)"; else bad "$1 exited 0"; fi; }
expect_has() { case "$OUT" in *"$2"*) ok "$1 names '$2'" ;; *) bad "$1 does not name '$2'" ;; esac; }

COMMON=(--publish-intent DRAFT --re-entry ONCE --qc-model qc-model-b --grades "$T/grades-all.json")

# 1. PLAN MODE run file absent -> never exit 0 (exit 0 today).
run export-plain.json "${COMMON[@]}"
expect_nonzero "plan-mode file absent"; expect_has "plan-mode file absent" plan_mode_file_absent

# 2. file path given but missing on disk
run export-plain.json "${COMMON[@]}" --plan-mode-file "$T/does-not-exist.json"
expect_nonzero "plan-mode file path missing on disk"

# 3. publish intent differs from the signed file
run export-plain.json --publish-intent LIVE --re-entry ONCE --qc-model qc-model-b --grades "$T/grades-all.json" --plan-mode-file "$T/plan-good.json"
expect_nonzero "CLI LIVE vs signed DRAFT"; expect_has "CLI LIVE vs signed DRAFT" publish_intent_differs
run export-plain.json "${COMMON[@]}" --plan-mode-file "$T/plan-live.json"
expect_nonzero "signed LIVE vs CLI DRAFT"; expect_has "signed LIVE vs CLI DRAFT" publish_intent_differs

# 4. a file the approval flow did not sign (verifier refuses)
run export-plain.json "${COMMON[@]}" --plan-mode-file "$T/plan-forged.json"
expect_nonzero "unsigned/forged approval"; expect_has "unsigned/forged approval" APPROVAL-NOT-FROM-AUTHORITY

# 5. verifier absent -> an unverifiable file is not a signature
mv "$T/shared-utils/signature_launch_contract/approval_record.py" "$T/verifier.off"
run export-plain.json "${COMMON[@]}" --plan-mode-file "$T/plan-good.json"
expect_nonzero "verifier absent"; expect_has "verifier absent" approval_verifier_missing
mv "$T/verifier.off" "$T/shared-utils/signature_launch_contract/approval_record.py"

# 6. QC model missing, and QC on the build model
run export-plain.json --publish-intent DRAFT --re-entry ONCE --grades "$T/grades-all.json" --plan-mode-file "$T/plan-good.json"
expect_nonzero "QC model not recorded"; expect_has "QC model not recorded" qc_model_missing_or_invalid
run export-plain.json "${COMMON[@]}" --plan-mode-file "$T/plan-samemodel.json"
expect_nonzero "QC model == build model"; expect_has "QC model == build model" qc_not_independent

# 7. all 12 human-review items ungraded (exit 0 today): no grades file, then one item missing
run export-plain.json --publish-intent DRAFT --re-entry ONCE --qc-model qc-model-b --plan-mode-file "$T/plan-good.json"
expect_nonzero "all human items ungraded"; expect_has "all human items ungraded" UNGRADED
[ "$RC" -eq 2 ] && ok "ungraded exit is 2" || bad "ungraded exit is not 2"
run export-plain.json --publish-intent DRAFT --re-entry ONCE --qc-model qc-model-b --grades "$T/grades-missing1.json" --plan-mode-file "$T/plan-good.json"
expect_nonzero "one human item ungraded"; expect_has "one human item ungraded" WF-20

# 8. a human grade of FAIL blocks exit 0
run export-plain.json --publish-intent DRAFT --re-entry ONCE --qc-model qc-model-b --grades "$T/grades-fail1.json" --plan-mode-file "$T/plan-good.json"
expect_nonzero "human grade FAIL"

# 9. everything signed and graded -> exit 0, and the QC runner model is in build-events
run export-plain.json "${COMMON[@]}" --plan-mode-file "$T/plan-good.json"
if [ "$RC" -eq 0 ]; then ok "signed + graded + independent model exits 0"; else bad "happy path did not exit 0"; fi
LEDGER="$T/home/.openclaw/tools/convert-and-flow-cli/data/build-events.jsonl"
LAST="$(tail -n 1 "$LEDGER" 2>/dev/null || true)"
case "$LAST" in *'"qc_model":"qc-model-b"'*'"plan_mode_gate":"PASS"'*'"verdict":"PASS"'*|*'"verdict":"PASS"'*'"qc_model":"qc-model-b"'*) ok "build-events records qc_model and gate" ;; *) bad "build-events lacks qc_model/gate: $LAST" ;; esac
run export-plain.json "${COMMON[@]}" --plan-mode-file "$T/plan-good.json" --json
[ "$(json_field qc_model)" = "qc-model-b" ] && ok "--json reports qc_model" || bad "--json lacks qc_model"

# 10. WF-9 (S44-11): launch build compares export wait nodes with the compiled schedule
cat > "$T/sched-ok.json" <<'JSON'
{"waits":[{"kind":"delay","value":2,"unit":"days"},{"kind":"until_date","until":"2026-11-26T14:00:00Z"}]}
JSON
cat > "$T/sched-bad.json" <<'JSON'
{"waits":[{"kind":"delay","value":2,"unit":"days"},{"kind":"delay","value":3,"unit":"days"}]}
JSON
LCOMMON=(--publish-intent DRAFT --re-entry ONCE --qc-model qc-model-b --plan-mode-file "$T/plan-good.json" --json)
run export-waits.json "${LCOMMON[@]}" --launch-schedule "$T/sched-ok.json"
[ "$(json_field items WF-9 status)" = "PASS" ] && ok "WF-9 PASS when waits match the compiled schedule (UTC-equal dates)" || bad "WF-9 not PASS on matching schedule"
run export-waits.json "${LCOMMON[@]}" --launch-schedule "$T/sched-bad.json"
[ "$(json_field items WF-9 status)" = "FAIL" ] && ok "WF-9 FAIL when a date wait was built as a duration wait" || bad "WF-9 not FAIL on mismatched schedule"
[ "$RC" -ne 0 ] && ok "mismatched launch schedule exits non-zero" || bad "mismatched launch schedule exited 0"
run export-waits.json "${LCOMMON[@]}" --launch
[ "$(json_field items WF-9 status)" = "FAIL" ] && ok "WF-9 FAIL on a launch build with no compiled schedule" || bad "WF-9 not FAIL without a schedule"
run export-waits.json "${LCOMMON[@]}"
[ "$(json_field items WF-9 status)" = "REQUIRES_HUMAN_REVIEW" ] && ok "WF-9 stays human review on a non-launch build" || bad "WF-9 changed on non-launch build"

echo
if [ "$FAILS" -eq 0 ]; then echo "ALL PASS"; exit 0; fi
echo "$FAILS FAILED"; exit 1
