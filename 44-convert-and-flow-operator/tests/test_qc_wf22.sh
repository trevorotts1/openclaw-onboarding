#!/usr/bin/env bash
# test_qc_wf22.sh — S44-32: SMS compliance must be SAVED NATIVE conditions, proven by the per-build QC.
#
#   bash 44-convert-and-flow-operator/tests/test_qc_wf22.sh
#
# The fix spec calls this item "WF-22"; WF-22 already is the email-body check, so the SMS item is
# WF-25 (appended, no renumbering). This file proves WF-25 and the mechanical WF-16 it feeds.
#
# Fail-before / pass-after: on a script that never runs sms_eligibility.py verify-saved, an export with
# SMS steps and NO native STOP condition still reached exit 0. Here that export must exit non-zero with
# WF-25 FAIL. Offline: a stub `caf` supplies the export and a stub verifier stands in for the approval
# flow (same pattern as test_qc_built_workflow.sh). SKILL44_DIR points the test at another copy of the
# skill (used once to show the failing run against the pre-fix script).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL="${SKILL44_DIR:-$(cd "$HERE/.." && pwd)}"
T="$(mktemp -d "${TMPDIR:-/tmp}/qc-wf25-test-XXXXXX")"
trap 'rm -rf "$T"' EXIT

mkdir -p "$T/44-convert-and-flow-operator" "$T/shared-utils/signature_launch_contract" "$T/bin" "$T/home"
cp "$SKILL/qc-built-workflow.sh" "$T/44-convert-and-flow-operator/"
ln -s "$SKILL/tools" "$T/44-convert-and-flow-operator/tools"
ln -s "$SKILL/automation-templates" "$T/44-convert-and-flow-operator/automation-templates"
QC="$T/44-convert-and-flow-operator/qc-built-workflow.sh"

cat > "$T/shared-utils/signature_launch_contract/approval_record.py" <<'PY'
class ApprovalRefused(Exception):
    def __init__(self, code, message=""):
        super().__init__(code + ": " + message)
        self.code = code

GOOD = {
    "appr-good-0001": ("launch_plan_build", {"publish:DRAFT", "reentry:ONCE"}),
    "appr-qc-b-0001": ("qc_session", {"qc_model:qc-model-b", "qc_session:sess-b-0001"}),
}

def verify(approval_id, kind, plan_hash, scope, **kw):
    if kw.get("test_only", False) is not False:  # the real verifier accepts a local test record under test_only=True
        raise ApprovalRefused("APPROVAL-NOT-FROM-AUTHORITY", "test_only must be exactly False")
    entry = GOOD.get(approval_id)
    if entry is None or kind != entry[0] or plan_hash != "abcd1234":
        raise ApprovalRefused("APPROVAL-NOT-FROM-AUTHORITY", "unknown approval")
    if not set(scope) <= entry[1]:
        raise ApprovalRefused("APPROVAL-SCOPE", "scope not covered")
    return {"ok": True}
PY

cat > "$T/bin/caf" <<'SH'
#!/usr/bin/env bash
while [ $# -gt 0 ]; do [ "$1" = "--out" ] && { cp "$QC_TEST_EXPORT" "$2"; exit 0; }; shift; done
exit 1
SH
chmod +x "$T/bin/caf"

# mkexport <file> <sms|email> <conditions-json|none> [sms-attributes-json]
#   a leading guard step carries the saved conditions; "none" leaves the SMS step with no guard at all.
mkexport() {
  local extra="${4:-}"; [ -n "$extra" ] || extra='{}'
  /opt/homebrew/bin/python3 -I - "$T/$1" "$2" "$3" "$extra" <<'PY'
import json, sys
out, channel, conds, extra = sys.argv[1], sys.argv[2], sys.argv[3], json.loads(sys.argv[4])
if channel == "sms":
    send = {"id": "n1", "type": "sms", "name": "Send", "next": "n2",
            "attributes": dict({"body": "Reply STOP to opt out.",
                                "purpose": "Respect sms-opted-out and STOP; send only inside 08:00-21:00 quiet hours.",
                                "fromNumber": "+15555550100"}, **extra)}
else:
    send = {"id": "n1", "type": "email", "name": "Mail", "next": "n2",
            "attributes": {"subject": "s", "body": "<p>" + ("word " * 60) + "</p>"}}
steps = []
if conds != "none":
    steps.append({"id": "g1", "type": "filter", "name": "Compliance guard", "parentKey": None, "next": "n1",
                  "attributes": {"conditions": json.loads(conds)}})
    send["parentKey"] = "g1"
else:
    send["parentKey"] = None
steps += [send, {"id": "n2", "type": "end", "name": "Finish", "parentKey": "n1"}]
root = steps[0]["id"]
json.dump({"id": "WFTEST001", "name": "ZHC-test", "status": "draft", "allowMultiple": False, "active": False,
           "workflowData": {"templates": steps},
           "triggers": [{"id": "T1", "type": "form_submitted", "targetActionId": root}]}, open(out, "w"))
PY
}

CONSENT='{"type":"tag_present","value":"sms-subscribed"}'
SUPPRESS='{"type":"tag_absent","value":"sms-opted-out"}'
CAP='{"type":"field_lt","field":"contact_marketing_sends","value":5}'
WINDOW='{"type":"time_window","start":"08:00","end":"21:00","timezone":"recipient_local"}'
DEADLINE='{"type":"deadline","anchor":"doors_close_at"}'
ALL="[$CONSENT,$SUPPRESS,$CAP,$WINDOW,$DEADLINE]"

mkexport sms-none.json   sms   none
mkexport sms-full.json   sms   "$ALL"
mkexport sms-nostop.json sms   "[$CONSENT,$CAP,$WINDOW,$DEADLINE]"
mkexport sms-nowin.json  sms   "[$CONSENT,$SUPPRESS,$CAP,$DEADLINE]"
mkexport sms-oper.json   sms   "[$SUPPRESS,$WINDOW]" '{"category":"operational"}'
mkexport sms-oper-nostop.json sms "[$WINDOW]" '{"category":"operational"}'
mkexport email-only.json email none
/opt/homebrew/bin/python3 -I - "$T/sms-disabled.json" "$ALL" <<'PY'
import json, sys
d = {"id": "WFTEST001", "name": "ZHC-test", "status": "draft", "allowMultiple": False, "active": False,
     "workflowData": {"templates": [
         {"id": "g1", "type": "filter", "name": "Compliance guard", "parentKey": None, "next": "n1", "disabled": True,
          "attributes": {"conditions": json.loads(sys.argv[2])}},
         {"id": "n1", "type": "sms", "name": "Send", "parentKey": "g1", "next": "n2",
          "attributes": {"body": "x", "fromNumber": "+15555550100"}},
         {"id": "n2", "type": "end", "name": "Finish", "parentKey": "n1"}]},
     "triggers": [{"id": "T1", "type": "form_submitted", "targetActionId": "g1"}]}
json.dump(d, open(sys.argv[1], "w"))
PY
# one-defect variants for the rubric D6 (Deliverability) floor: no From-number key on the SMS node (WF-12),
# an empty email body (WF-22)
/opt/homebrew/bin/python3 -I - "$T" <<'PY'
import json, sys
t = sys.argv[1]
d = json.load(open(t + "/sms-full.json"))
for step in d["workflowData"]["templates"]:
    step.get("attributes", {}).pop("fromNumber", None)
json.dump(d, open(t + "/sms-nofrom.json", "w"))
d = json.load(open(t + "/email-only.json"))
for step in d["workflowData"]["templates"]:
    if step["type"] == "email":
        step["attributes"]["body"] = ""
json.dump(d, open(t + "/email-emptybody.json", "w"))
PY
echo '{}' > "$T/deps.json"

printf '{"approval_id":"appr-good-0001","plan_hash":"abcd1234","publish_intent":"DRAFT","re_entry":"ONCE","build_model":"build-model-a"}' > "$T/plan.json"
printf '{"approval_id":"appr-qc-b-0001","plan_hash":"abcd1234","qc_model":"qc-model-b","session_id":"sess-b-0001"}' > "$T/qcs.json"
HUMAN="WF-1 WF-2 WF-8 WF-9 WF-10 WF-11 WF-13 WF-14 WF-16 WF-17 WF-19 WF-20"
/opt/homebrew/bin/python3 -I - "$T" $HUMAN <<'PY'
import json, sys
t, items = sys.argv[1], sys.argv[2:]
for name, drop in (("grades-all.json", ()), ("grades-no16.json", ("WF-16",))):
    g = {i: {"grade": "PASS", "observed": "read from export"} for i in items if i not in drop}
    json.dump({"workflow_id": "WFTEST001", "grades": g}, open(t + "/" + name, "w"))
PY

run() { # run <export> <grades> [extra args]
  local exp="$1" grades="$2"; shift 2
  OUT="$(env PATH="$T/bin:$PATH" HOME="$T/home" OPENCLAW_PLATFORM=mac QC_TEST_EXPORT="$T/$exp" \
        bash "$QC" WFTEST001 --deps "$T/deps.json" --publish-intent DRAFT --re-entry ONCE \
        --plan-mode-file "$T/plan.json" --qc-session "$T/qcs.json" --grades "$T/$grades" --json "$@" 2>&1)"; RC=$?
}
run_text() { # same as run, in the text report (no --json): which list each item is shown in
  local exp="$1" grades="$2"; shift 2
  OUT="$(env PATH="$T/bin:$PATH" HOME="$T/home" OPENCLAW_PLATFORM=mac QC_TEST_EXPORT="$T/$exp" \
        bash "$QC" WFTEST001 --deps "$T/deps.json" --publish-intent DRAFT --re-entry ONCE \
        --plan-mode-file "$T/plan.json" --qc-session "$T/qcs.json" --grades "$T/$grades" "$@" 2>&1)"; RC=$?
}
item() { # item <WF-id> <field>
  printf '%s' "$OUT" | /opt/homebrew/bin/python3 -I -c '
import json, sys
t = sys.stdin.read()
try:
    d = json.loads(t[t.index("{"):t.rindex("}") + 1])
    print(d["items"][sys.argv[1]][sys.argv[2]])
except Exception:
    print("UNPARSEABLE")' "$1" "$2"
}

item_text() { # item_text <WF-id>: the status column of that item in the last text report
  printf '%s\n' "$OUT" | awk -v w="$1" '$1 == w { print $2; exit }'
}
floor() { # the weighted rubric floor of the last text report, times 100
  printf '%s\n' "$OUT" | awk '/WEIGHTED FLOOR SCORE:/ { gsub(/\./, "", $4); print $4; exit }'
}
section() { # section <WF-id>: which list the text report puts the item in (before or after the human-review heading)
  printf '%s\n' "$OUT" | awk -v w="$1" '/Items requiring QC agent review/ { human = 1 } $1 == w { print (human ? "human" : "mechanical"); exit }'
}

FAILS=0
ok()  { echo "ok   - $1"; }
bad() { echo "FAIL - $1"; echo "       rc=$RC out=$(printf '%s' "$OUT" | tr '\n' ' ' | cut -c1-500)"; FAILS=$((FAILS + 1)); }
expect() { if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (got '$2', wanted '$3')"; fi; }

# 1. SMS steps and NO native STOP/suppression/quiet-hours condition: WF-25 FAIL and a non-zero exit.
#    (Pre-fix this exact export exited 0.)
run sms-none.json grades-all.json
expect "no conditions: WF-25 FAIL" "$(item WF-25 status)" FAIL
[ "$RC" -eq 1 ] && ok "no conditions: exit 1" || bad "no conditions: exit is $RC, not 1"
case "$(item WF-25 observed)" in *"suppression"*"quiet_hours"*) ok "no conditions: names the missing rules" ;; *) bad "no conditions: missing rules not named" ;; esac

# 2. The words are in the copy, the conditions are not saved: prose never satisfies a rule.
case "$(item WF-25 observed)" in *"prose_only=suppression"*) ok "prose-only rules are reported" ;; *) bad "prose-only rules not reported" ;; esac

# 3. Every marketing rule saved natively: WF-25 PASS, WF-16 mechanical PASS, exit 0 (all else graded).
run sms-full.json grades-no16.json
expect "full conditions: WF-25 PASS" "$(item WF-25 status)" PASS
expect "full conditions: WF-16 PASS (mechanical)" "$(item WF-16 status)" PASS
case "$(item WF-25 observed)" in *"category=marketing"*) ok "full conditions: WF-25 names the marketing category" ;; *) bad "full conditions: WF-25 does not name category=marketing" ;; esac
run_text sms-full.json grades-no16.json
expect "full conditions: WF-16 is listed with the mechanical items" "$(section WF-16)" mechanical
expect "full conditions: the other human-review items stay in the human list" "$(section WF-1)" human
expect "full conditions: WF-20 stays in the human list" "$(section WF-20)" human
[ "$RC" -eq 0 ] && ok "full conditions: exit 0 without a WF-16 human grade" || bad "full conditions: exit is $RC"

# 4. One rule missing is enough: no STOP condition; no time window.
run sms-nostop.json grades-no16.json
expect "no suppression condition: WF-25 FAIL" "$(item WF-25 status)" FAIL
case "$(item WF-16 observed)" in "stop_condition=MISSING time_window=saved") ok "no suppression condition: WF-16 names the missing stop condition" ;; *) bad "no suppression condition: WF-16 observed text is '$(item WF-16 observed)'" ;; esac
case "$(item WF-25 observed)" in *"category=marketing"*) ok "no suppression condition: WF-25 names the marketing category" ;; *) bad "no suppression condition: WF-25 does not name category=marketing" ;; esac
expect "no suppression condition: WF-16 FAIL" "$(item WF-16 status)" FAIL
[ "$RC" -eq 1 ] && ok "no suppression condition: exit 1" || bad "no suppression condition: exit is $RC"
run_text sms-nostop.json grades-no16.json
expect "no suppression condition: WF-16 is listed with the mechanical items" "$(section WF-16)" mechanical
run sms-nowin.json grades-no16.json
expect "no time window: WF-25 FAIL" "$(item WF-25 status)" FAIL
case "$(item WF-16 observed)" in "stop_condition=saved time_window=MISSING") ok "no time window: WF-16 names the missing window" ;; *) bad "no time window: WF-16 observed text is '$(item WF-16 observed)'" ;; esac
expect "no time window: WF-16 FAIL" "$(item WF-16 status)" FAIL

# 5. A disabled guard step proves nothing.
run sms-disabled.json grades-all.json
expect "disabled guard: WF-25 FAIL" "$(item WF-25 status)" FAIL

# 6. Operational sets are held to suppression + quiet hours only.
run sms-oper.json grades-no16.json
expect "operational set with its two rules: WF-25 PASS" "$(item WF-25 status)" PASS
case "$(item WF-25 observed)" in *"category=operational"*) ok "operational set: WF-25 names the operational category" ;; *) bad "operational set: WF-25 does not name category=operational" ;; esac
run sms-oper-nostop.json grades-no16.json
expect "operational set without suppression: WF-25 FAIL" "$(item WF-25 status)" FAIL

# 7. No SMS node: nothing to prove, WF-16 stays human review, the verifier is not needed.
rm "$T/44-convert-and-flow-operator/automation-templates"
run email-only.json grades-all.json
expect "email only: WF-25 PASS (n/a)" "$(item WF-25 status)" PASS
expect "email only: WF-16 stays human review" "$(item WF-16 status)" "HUMAN_PASS"
run_text email-only.json grades-all.json
expect "email only: WF-16 is listed with the human-review items" "$(section WF-16)" human

# 8. SMS node and the verifier is absent: fail closed, never a pass.
run sms-full.json grades-no16.json
expect "verifier absent with an SMS node: WF-25 FAIL" "$(item WF-25 status)" FAIL
case "$(item WF-25 observed)" in *sms_verifier_missing*) ok "verifier absent is named" ;; *) bad "verifier absent not named" ;; esac
[ "$RC" -eq 1 ] && ok "verifier absent: exit 1" || bad "verifier absent: exit is $RC"
ln -s "$SKILL/automation-templates" "$T/44-convert-and-flow-operator/automation-templates"

# 9. A verifier whose report and exit status disagree, or whose report is garbage, never passes.
#    Stubs stand in for sms_eligibility.py (the real one is never lying), swapped in for the symlink.
stub() { # stub <label> <exit code> <stdout>
  rm -rf "$T/44-convert-and-flow-operator/automation-templates"
  mkdir -p "$T/44-convert-and-flow-operator/automation-templates/launch-text"
  printf '#!/usr/bin/env python3\nimport sys\nprint(%s)\nsys.exit(%s)\n' "$3" "$2" \
    > "$T/44-convert-and-flow-operator/automation-templates/launch-text/sms_eligibility.py"
  run sms-full.json grades-no16.json
  expect "$1: WF-25 FAIL" "$(item WF-25 status)" FAIL
  case "$(item WF-25 observed)" in *sms_verifier_report_malformed*) ok "$1: named malformed" ;; *) bad "$1: not named malformed" ;; esac
  [ "$RC" -eq 1 ] && ok "$1: exit 1" || bad "$1: exit is $RC"
}
stub "garbage report, exit 0" 0 "'this is not json'"
stub "garbage report, exit 1" 1 "'this is not json'"
stub "ok=true report, exit 1" 1 "'{\"ok\": true, \"category\": \"marketing\", \"sms_nodes\": 1}'"
stub "ok=false report, exit 0" 0 "'{\"ok\": false, \"category\": \"marketing\", \"sms_nodes\": 1}'"

# 10. A verifier that cannot read the export (any exit other than 0 or 1) never passes a workflow that
#     carries an SMS node: the rule is unproven, so WF-25 fails closed and names the exit status.
stubrc() { # stubrc <label> <exit code> <stdout> <export> <wanted rc>
  rm -rf "$T/44-convert-and-flow-operator/automation-templates"
  mkdir -p "$T/44-convert-and-flow-operator/automation-templates/launch-text"
  printf '#!/usr/bin/env python3\nimport sys\nprint(%s)\nsys.exit(%s)\n' "$3" "$2" \
    > "$T/44-convert-and-flow-operator/automation-templates/launch-text/sms_eligibility.py"
  run "$4" grades-no16.json
  expect "$1: WF-25 FAIL" "$(item WF-25 status)" FAIL
  case "$(item WF-25 observed)" in *"sms_verifier_could_not_read_export rc=$2"*) ok "$1: names could_not_read_export rc=$2" ;; *) bad "$1: not named could_not_read_export rc=$2" ;; esac
  [ "$RC" -eq "$5" ] && ok "$1: exit $5" || bad "$1: exit is $RC, not $5"
}
stubrc "verifier exit 2 with SMS nodes" 2 "'cannot read'" sms-full.json 1
stubrc "verifier exit 2, ok=true report, SMS nodes" 2 "'{\"ok\": true, \"category\": \"marketing\", \"sms_nodes\": 1}'" sms-full.json 1
stubrc "verifier exit 3 with SMS nodes" 3 "'cannot read'" sms-full.json 1
stubrc "verifier exit 126 with SMS nodes" 126 "'cannot read'" sms-full.json 1
stubrc "verifier exit 3, export without SMS nodes" 3 "'cannot read'" email-only.json 1
# A report that leaves out sms_nodes says there are none: on an export without SMS steps that is a PASS (n/a).
rm -rf "$T/44-convert-and-flow-operator/automation-templates"
mkdir -p "$T/44-convert-and-flow-operator/automation-templates/launch-text"
printf '#!/usr/bin/env python3\nimport sys\nprint("{\\"ok\\": true, \\"category\\": \\"marketing\\"}")\nsys.exit(0)\n' \
  > "$T/44-convert-and-flow-operator/automation-templates/launch-text/sms_eligibility.py"
run email-only.json grades-all.json
expect "report without sms_nodes on an email-only export: WF-25 PASS" "$(item WF-25 status)" PASS
case "$(item WF-25 observed)" in *no_sms_nodes*) ok "report without sms_nodes: named no_sms_nodes" ;; *) bad "report without sms_nodes: not named no_sms_nodes" ;; esac
# Exit 2 with no SMS node at all is the verifier saying "no step list": nothing to prove, WF-25 n/a.
stubrc_na() { # same stub, email-only export: not a failure
  rm -rf "$T/44-convert-and-flow-operator/automation-templates"
  mkdir -p "$T/44-convert-and-flow-operator/automation-templates/launch-text"
  printf '#!/usr/bin/env python3\nimport sys\nprint("no step list")\nsys.exit(2)\n' \
    > "$T/44-convert-and-flow-operator/automation-templates/launch-text/sms_eligibility.py"
  run email-only.json grades-all.json
  expect "verifier exit 2, no SMS node: WF-25 PASS (n/a)" "$(item WF-25 status)" PASS
  case "$(item WF-25 observed)" in *no_sms_nodes*) ok "verifier exit 2, no SMS node: named no_sms_nodes" ;; *) bad "verifier exit 2, no SMS node: not named no_sms_nodes" ;; esac
}
stubrc_na
# A verifier that reports zero SMS nodes (rc 0) on an email-only export: nothing to prove, named no_sms_nodes.
rm -rf "$T/44-convert-and-flow-operator/automation-templates"
mkdir -p "$T/44-convert-and-flow-operator/automation-templates/launch-text"
printf '#!/usr/bin/env python3\nimport sys\nprint("{\\"ok\\": true, \\"category\\": \\"marketing\\", \\"sms_nodes\\": 0}")\nsys.exit(0)\n' \
  > "$T/44-convert-and-flow-operator/automation-templates/launch-text/sms_eligibility.py"
run email-only.json grades-all.json
expect "verifier reports 0 SMS nodes: WF-25 PASS" "$(item WF-25 status)" PASS
case "$(item WF-25 observed)" in *no_sms_nodes*) ok "verifier reports 0 SMS nodes: named no_sms_nodes" ;; *) bad "verifier reports 0 SMS nodes: not named no_sms_nodes" ;; esac
rm -rf "$T/44-convert-and-flow-operator/automation-templates"
ln -s "$SKILL/automation-templates" "$T/44-convert-and-flow-operator/automation-templates"

# 11. Rubric D6 (Deliverability) drops from 5 to 1 when ANY of WF-12, WF-22 or WF-25 fails: the weighted
#     floor is 0.40 lower than the same run with all three passing, whichever one fails alone.
run_text sms-full.json grades-no16.json;    BASE_SMS="$(floor)"
run_text sms-nostop.json grades-no16.json;  expect "WF-25 FAIL alone lowers the D6 floor by 0.40" "$((BASE_SMS - $(floor)))" 40
run_text sms-nofrom.json grades-no16.json;  expect "WF-12 FAIL alone lowers the D6 floor by 0.40" "$((BASE_SMS - $(floor)))" 40
expect "WF-12 FAIL alone: WF-25 still PASS" "$(item_text WF-25)" PASS
rm -rf "$T/44-convert-and-flow-operator/automation-templates"
run_text email-only.json grades-all.json;       BASE_MAIL="$(floor)"
run_text email-emptybody.json grades-all.json;  expect "WF-22 FAIL alone lowers the D6 floor by 0.40" "$((BASE_MAIL - $(floor)))" 40
ln -s "$SKILL/automation-templates" "$T/44-convert-and-flow-operator/automation-templates"

echo
if [ "$FAILS" -eq 0 ]; then echo "ALL PASS"; exit 0; fi
echo "$FAILS FAILED"; exit 1
