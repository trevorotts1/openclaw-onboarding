#!/usr/bin/env bash
# test_qc_gate.sh — S44-46: the QC model is a signed fact, not a typed string.
#
#   bash 44-convert-and-flow-operator/tests/test_qc_gate.sh
#
# Fail-before / pass-after: qc-built-workflow.sh used to accept `--qc-model <any string>`, so the
# builder could QC itself under a made-up model name and still exit 0. It now takes `--qc-session`, a
# record the approval flow signed (kind qc_session, scope qc_model:<model> + qc_session:<id>, bound to
# the PLAN MODE plan_hash). Offline: a stub `caf` supplies the export; a stub verifier stands in for the
# approval authority and mints exactly one QC session record. SKILL44_DIR points the test at another
# copy of the skill (used once to show the failing run against the pre-fix script).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL="${SKILL44_DIR:-$(cd "$HERE/.." && pwd)}"
T="$(mktemp -d "${TMPDIR:-/tmp}/qc-session-test-XXXXXX")"
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
    # the authority signs these unsafe values: only the script's own safe-character check can refuse them
    "appr-qc-u1-0001": ("qc_session", {"qc_model:qc model;x", "qc_session:sess-b-0001"}),
    "appr-qc-u2-0001": ("qc_session", {"qc_model:qc-model-b", "qc_session:sess/b-0001"}),
    "appr-qc-u3-0001": ("qc_session", {"qc_model:" + "m" * 81, "qc_session:sess-b-0001"}),
    "appr-qc-u4-0001": ("qc_session", {"qc_model:qc-model-b", "qc_session:" + "s" * 81}),
    "appr-qc-ok-0001": ("qc_session", {"qc_model:Qc/Model_B.1:x@1+y-Z9", "qc_session:sess-b-0001"}),
    "appr-qc-ok2-0001": ("qc_session", {"qc_model:qc-model-b", "qc_session:Sess.A_9:b@c+d-E"}),
    "appr-qc-ok3-0001": ("qc_session", {"qc_model:" + "m" * 80, "qc_session:" + "s" * 80}),
}

def verify(approval_id, kind, plan_hash, scope, **kw):
    if kw.get("test_only", False) is not False:  # the real verifier accepts a local test record under test_only=True
        raise ApprovalRefused("APPROVAL-NOT-FROM-AUTHORITY", "test_only must be exactly False")
    if approval_id == "appr-qc-long-0001":
        raise ApprovalRefused("APPROVAL-LONG", "x" * 200)
    entry = GOOD.get(approval_id)
    h = str(plan_hash).strip().lower()
    h = h[7:] if h.startswith("sha256:") else h
    if entry is None or kind != entry[0] or h != "abcd1234":
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

# An email-only workflow keeps this file about the gate: no SMS rules to satisfy.
cat > "$T/export.json" <<JSON
{"id":"WFTEST001","name":"ZHC-test","status":"draft","allowMultiple":false,"active":false,
 "workflowData":{"templates":[
  {"id":"n1","type":"email","name":"Mail","parentKey":null,"next":"n2","attributes":{"subject":"s","body":"<p>$(printf 'word %.0s' $(seq 1 60))</p>"}},
  {"id":"n2","type":"end","name":"Finish","parentKey":"n1"}]},
 "triggers":[{"id":"T1","type":"form_submitted","targetActionId":"n1"}]}
JSON
echo '{}' > "$T/deps.json"

plan() { printf '{"approval_id":"%s","plan_hash":"abcd1234","publish_intent":"DRAFT","re_entry":"ONCE","build_model":"%s"}' "$1" "$2" > "$T/$3"; }
qcs()  { printf '{"approval_id":"%s","plan_hash":"%s","qc_model":"%s","session_id":"%s"}' "$1" "$2" "$3" "$4" > "$T/$5"; }
plan appr-good-0001 build-model-a plan.json
plan appr-good-0001 qc-model-b plan-built-on-qc-model.json
qcs appr-qc-b-0001   abcd1234 qc-model-b sess-b-0001 qcs-minted.json           # what the authority minted
qcs appr-selfwritten abcd1234 qc-model-b sess-self-01 qcs-selfwritten.json     # the builder wrote this itself
qcs appr-qc-b-0001   abcd1234 qc-model-z sess-b-0001 qcs-model-edited.json     # model swapped after signing
qcs appr-qc-b-0001   abcd1234 qc-model-b sess-other-9 qcs-session-edited.json  # session id swapped after signing
qcs appr-qc-u1-0001  abcd1234 "qc model;x" sess-b-0001 qcs-unsafe-model.json    # signed, but unsafe characters
qcs appr-qc-u2-0001  abcd1234 qc-model-b "sess/b-0001" qcs-unsafe-session.json  # signed, but "/" is not allowed in a session id
qcs appr-qc-u3-0001  abcd1234 "$(printf 'm%.0s' $(seq 1 81))" sess-b-0001 qcs-long-model.json
qcs appr-qc-u4-0001  abcd1234 qc-model-b "$(printf 's%.0s' $(seq 1 81))" qcs-long-session.json
qcs appr-qc-ok-0001  abcd1234 "Qc/Model_B.1:x@1+y-Z9" sess-b-0001 qcs-safe-model-slash.json  # every allowed character class in a model name
qcs appr-qc-ok2-0001 abcd1234 qc-model-b "Sess.A_9:b@c+d-E" qcs-safe-session-chars.json       # every allowed character class in a session id
qcs appr-qc-ok3-0001 abcd1234 "$(printf 'm%.0s' $(seq 1 80))" "$(printf 's%.0s' $(seq 1 80))" qcs-exactly-80.json  # 80 is the longest allowed
HUMAN="WF-1 WF-2 WF-8 WF-9 WF-10 WF-11 WF-13 WF-14 WF-16 WF-17 WF-19 WF-20"
/opt/homebrew/bin/python3 -I - "$T/grades.json" $HUMAN <<'PY'
import json, sys
json.dump({"workflow_id": "WFTEST001", "grades": {i: {"grade": "PASS", "observed": "read from export"} for i in sys.argv[2:]}}, open(sys.argv[1], "w"))
PY

run() { # run <plan> <args...>
  local plan="$1"; shift
  OUT="$(env PATH="${EXTRA_PATH:+$EXTRA_PATH:}$T/bin:$PATH" HOME="$T/home" OPENCLAW_PLATFORM=mac QC_TEST_EXPORT="${EXPORT_FILE:-$T/export.json}" \
        bash "$QC" WFTEST001 --deps "$T/deps.json" --publish-intent DRAFT --re-entry ONCE \
        --plan-mode-file "$T/$plan" --grades "$T/grades.json" "$@" 2>&1)"; RC=$?
}
FAILS=0
ok()  { echo "ok   - $1"; }
bad() { echo "FAIL - $1"; echo "       rc=$RC out=$(printf '%s' "$OUT" | tr '\n' ' ' | cut -c1-400)"; FAILS=$((FAILS + 1)); }
refused() { # refused <label> <needle>
  if [ "$RC" -ne 0 ]; then ok "$1 (rc=$RC)"; else bad "$1 exited 0"; fi
  case "$OUT" in *"$2"*) ok "$1 names '$2'" ;; *) bad "$1 does not name '$2'" ;; esac
}

# 1. The record the authority minted: exit 0, and the ledger names the signed model and session.
run plan.json --qc-session "$T/qcs-minted.json"
[ "$RC" -eq 0 ] && ok "minted QC session record exits 0" || bad "minted QC session record did not exit 0"
LEDGER="$T/home/.openclaw/tools/convert-and-flow-cli/data/build-events.jsonl"
case "$(tail -n 1 "$LEDGER" 2>/dev/null)" in
  *'"qc_model":"qc-model-b"'*'"qc_session_id":"sess-b-0001"'*) ok "build-events records the signed model and session id" ;;
  *) bad "build-events lacks qc_model/qc_session_id" ;;
esac

# 2. The typed string is gone.
run plan.json --qc-model qc-model-b
refused "--qc-model <string>" "no longer accepted"
[ "$RC" -eq 2 ] && ok "--qc-model refusal exit is 2" || bad "--qc-model refusal exit is not 2"
run plan.json --qc-model qc-model-b --qc-session "$T/qcs-minted.json"
refused "--qc-model next to a good --qc-session" "no longer accepted"

# 3. No record, a record nobody minted, or a minted record edited afterwards: never exit 0.
run plan.json
refused "no QC session record" qc_session_absent
case "$OUT" in *"no --qc-session"*) ok "absent record says no --qc-session was passed" ;; *) bad "absent record does not say no --qc-session was passed" ;; esac
run plan.json --qc-session "$T/not-there.json"
refused "QC session path that does not exist" qc_session_absent
case "$OUT" in *"($T/not-there.json)"*) ok "absent record names the path it was given" ;; *) bad "absent record does not name the path it was given" ;; esac
run not-there-plan.json --qc-session "$T/qcs-minted.json"
refused "PLAN MODE path that does not exist" plan_mode_file_absent
case "$OUT" in *"($T/not-there-plan.json)"*) ok "absent plan file names the path it was given" ;; *) bad "absent plan file does not name the path it was given" ;; esac
OUT="$(env PATH="$T/bin:$PATH" HOME="$T/home" OPENCLAW_PLATFORM=mac QC_TEST_EXPORT="$T/export.json" \
      bash "$QC" WFTEST001 --deps "$T/deps.json" --publish-intent DRAFT --re-entry ONCE \
      --grades "$T/grades.json" --qc-session "$T/qcs-minted.json" 2>&1)"; RC=$?
refused "no --plan-mode-file at all" plan_mode_file_absent
case "$OUT" in *"no --plan-mode-file"*) ok "missing flag says no --plan-mode-file was passed" ;; *) bad "missing flag does not say no --plan-mode-file was passed" ;; esac
run plan.json --qc-session "$T/qcs-selfwritten.json"
refused "self-written QC session record" qc_session_not_verified
run plan.json --qc-session "$T/qcs-model-edited.json"
refused "QC model swapped after signing" qc_session_not_verified
run plan.json --qc-session "$T/qcs-session-edited.json"
refused "session id swapped after signing" qc_session_not_verified

# 3b. A QC session record that is not a complete object of four non-blank strings is malformed, whichever
#     key is missing, blank or not a string; so is JSON that is not an object or not JSON at all.
/opt/homebrew/bin/python3 -I - "$T" <<'PY'
import json, sys
t = sys.argv[1]
good = {"approval_id": "appr-qc-b-0001", "plan_hash": "abcd1234", "qc_model": "qc-model-b", "session_id": "sess-b-0001"}
for key in good:
    for label, value in (("missing", None), ("blank", "   "), ("int", 7), ("null", "NULL")):
        rec = dict(good)
        if label == "missing":
            del rec[key]
        else:
            rec[key] = None if value == "NULL" else value
        json.dump(rec, open("%s/qcs-bad-%s-%s.json" % (t, key, label), "w"))
open(t + "/qcs-bad-list.json", "w").write("[1, 2]")
open(t + "/qcs-bad-text.json", "w").write("{not json")
PY
for _f in "$T"/qcs-bad-*.json; do
  run plan.json --qc-session "$_f"
  refused "malformed QC session record $(basename "$_f" .json)" qc_session_malformed
done

# 3c. The reason the gate prints is cut at 300 characters (a long path must not flood the report).
LONGNAME="$(printf 'p%.0s' $(seq 1 200))/$(printf 'q%.0s' $(seq 1 200))"
run "$LONGNAME" --qc-session "$T/qcs-minted.json"
refused "PLAN MODE path of 400 characters" plan_mode_file_absent
REASON="${OUT#*PLAN MODE gate: }"; REASON="${REASON%%. Exit 0 needs*}"
[ "${#REASON}" -eq 300 ] && ok "gate reason is cut at exactly 300 characters" || bad "gate reason is ${#REASON} characters, not 300"

# 3d. The plan hash may carry a "sha256:" prefix and any case on either side; a different hash is a mismatch.
qcs appr-qc-b-0001 "sha256:ABCD1234" qc-model-b sess-b-0001 qcs-hash-prefixed.json
qcs appr-qc-b-0001 "sha256:ffff0000" qc-model-b sess-b-0001 qcs-hash-other.json
qcs appr-qc-b-0001 "bcd1234" qc-model-b sess-b-0001 qcs-hash-short.json
run plan.json --qc-session "$T/qcs-hash-prefixed.json"
[ "$RC" -eq 0 ] && ok "plan hash with sha256: prefix and upper case matches" || bad "plan hash with sha256: prefix and upper case was refused"
run plan.json --qc-session "$T/qcs-hash-other.json"
refused "QC session bound to a different plan hash" qc_session_plan_mismatch
run plan.json --qc-session "$T/qcs-hash-short.json"
refused "QC session hash that is only the tail of the plan hash" qc_session_plan_mismatch

# 3e. The authority's refusal text is shown cut at 120 characters ("APPROVAL-LONG: " is 15 of them).
qcs appr-qc-long-0001 abcd1234 qc-model-b sess-b-0001 qcs-long-refusal.json
run plan.json --qc-session "$T/qcs-long-refusal.json"
refused "authority refusal with a 200-character message" qc_session_not_verified
case "$OUT" in *"$(printf 'x%.0s' $(seq 1 105))"*) ok "refusal text keeps 120 characters" ;; *) bad "refusal text shorter than 120 characters" ;; esac
case "$OUT" in *"$(printf 'x%.0s' $(seq 1 106))"*) bad "refusal text longer than 120 characters" ;; *) ok "refusal text is cut at 120 characters" ;; esac

# 3f. The refusal is printed on stderr, and a call with no workflow id prints its usage on stderr, exit 2.
ERR="$(env PATH="$T/bin:$PATH" HOME="$T/home" OPENCLAW_PLATFORM=mac QC_TEST_EXPORT="$T/export.json" \
      bash "$QC" WFTEST001 --deps "$T/deps.json" --publish-intent DRAFT --re-entry ONCE \
      --plan-mode-file "$T/plan.json" --grades "$T/grades.json" 2>&1 >/dev/null)"
case "$ERR" in *"PLAN MODE gate: qc_session_absent"*) ok "the gate refusal is on stderr" ;; *) bad "the gate refusal is not on stderr" ;; esac
OUT="$(env PATH="$T/bin:$PATH" HOME="$T/home" bash "$QC" 2>/dev/null)"; RC=$?
[ "$RC" -eq 2 ] && [ -z "$OUT" ] && ok "no workflow id: exit 2, nothing on stdout" || bad "no workflow id: exit $RC with stdout '$OUT'"
ERR="$(env PATH="$T/bin:$PATH" HOME="$T/home" bash "$QC" 2>&1 >/dev/null)"
case "$ERR" in *"workflow-id required"*"--qc-session"*) ok "usage on stderr names --qc-session" ;; *) bad "usage on stderr does not name --qc-session" ;; esac

# 4. Independence: the signed model must differ from the build model the PLAN MODE file names.
run plan-built-on-qc-model.json --qc-session "$T/qcs-minted.json"
refused "signed QC model == build model" qc_not_independent

# 5. The safe-character check: a signed record whose model or session id has characters outside the
#    safe set (or is over 80 characters) is refused by the script itself, while a safe model with / @ + passes.
run plan.json --qc-session "$T/qcs-unsafe-model.json"
refused "signed QC model with a space and ;" "safe set"
run plan.json --qc-session "$T/qcs-unsafe-session.json"
refused "signed session id with /" "safe set"
run plan.json --qc-session "$T/qcs-long-model.json"
refused "signed QC model over 80 characters" "safe set"
run plan.json --qc-session "$T/qcs-long-session.json"
refused "signed session id over 80 characters" "safe set"
run plan.json --qc-session "$T/qcs-safe-model-slash.json"
[ "$RC" -eq 0 ] && ok "safe model name with / @ + is accepted" || bad "safe model name with / @ + was refused"
run plan.json --qc-session "$T/qcs-safe-session-chars.json"
[ "$RC" -eq 0 ] && ok "session id with every allowed character is accepted" || bad "session id with every allowed character was refused"
run plan.json --qc-session "$T/qcs-exactly-80.json"
[ "$RC" -eq 0 ] && ok "model and session id of exactly 80 characters are accepted" || bad "80-character model/session id was refused"

# 6. Determinism: the header checks (WF-3 trigger, WF-4 active, WF-5 status, WF-6 re-entry) read the export
#    through `grep -q`, which quits at the first match. When the export was piped in with `echo | grep -q`
#    under `set -o pipefail`, the writer died of SIGPIPE whenever grep quit before the writer finished, so
#    the check read as "not found" and the run went red with a small export only now and then under load
#    (the one red seen under 4-way load: WF-6 fell to human review, exit 2). That race is forced here: a
#    `grep` stand-in that, like GNU grep -q, quits after its first 4 KB, and an export of ~300 KB (larger
#    than the pipe buffer, header keys first). Every run must still machine-assert the header and exit 0.
mkdir -p "$T/earlygrep"
REAL_GREP="$(type -P grep)"
cat > "$T/earlygrep/grep" <<SH
#!/usr/bin/env bash
# quits after the first 4 KB when asked for -q, as a real grep -q does on its first match
case "\$1" in -q*) chunk="\$(head -c 4096)"; exec "$REAL_GREP" "\$@" <<< "\$chunk" ;; esac
exec "$REAL_GREP" "\$@"
SH
chmod +x "$T/earlygrep/grep"
/opt/homebrew/bin/python3 -I - "$T/export-large.json" <<'PY'
import json, sys
body = "<p>" + ("word " * 60000) + "</p>"
steps = [{"id": "n1", "type": "email", "name": "Mail", "parentKey": None, "next": "n2", "attributes": {"subject": "s", "body": body}},
         {"id": "n2", "type": "end", "name": "Finish", "parentKey": "n1"}]
d = {"id": "WFTEST001", "name": "ZHC-test", "status": "draft", "allowMultiple": False, "active": False,
     "triggers": [{"id": "T1", "type": "form_submitted", "targetActionId": "n1"}], "workflowData": {"templates": steps}}
json.dump(d, open(sys.argv[1], "w"))
PY
EXPORT_FILE="$T/export-large.json" EXTRA_PATH="$T/earlygrep" run plan.json --qc-session "$T/qcs-minted.json"
EXPORT_FILE=""; EXTRA_PATH=""
[ "$RC" -eq 0 ] && ok "large export with an early-quitting grep exits 0" || bad "large export with an early-quitting grep did not exit 0"
for _w in WF-3 WF-4 WF-5 WF-6; do
  _st="$(printf '%s\n' "$OUT" | awk -v w="$_w" '$1 == w { print $2; exit }')"
  [ "$_st" = PASS ] && ok "large export: $_w machine-asserted PASS" || bad "large export: $_w is '$_st', not PASS"
done

# 6b. The WF-21 snapshot checks (script lines "find | grep -q" and "find | head -1 | grep -q .") had the same
#    race: under `set -o pipefail` a finder killed by SIGPIPE made the pipeline read as "no snapshot", so a real
#    snapshot recorded N/A. Forced here: ~1500 snapshot paths (all under the workflow id, >64 KB of find output,
#    larger than the pipe buffer) and a grep stand-in that quits after its first 4 KB for `-q`. For the second
#    check the stand-in reports "no match" for the first check's id pattern, and for the first check it reports "no match" for the second, so each check must find the snapshot on its own.
SNAPDIR="$T/home/.openclaw/tools/convert-and-flow-cli/data/snapshots/WFTEST001"
mkdir -p "$SNAPDIR"
for _i in $(seq 1 1500); do echo '{"snap":1}' > "$SNAPDIR/snapshot-$(printf 'x%.0s' $(seq 1 40))-$_i.json"; done
wf21() { printf '%s\n' "$OUT" | awk '$1 == "WF-21" { print $2; exit }'; }
run plan.json --qc-session "$T/qcs-minted.json"
[ "$(wf21)" = PASS ] && ok "large snapshot dir, real grep: WF-21 PASS" || bad "large snapshot dir, real grep: WF-21 is '$(wf21)', not PASS"
mkdir -p "$T/earlygrep1"
cat > "$T/earlygrep1/grep" <<SH
#!/usr/bin/env bash
# the fallback check (-q .) finds nothing, so only the id-pattern check can find the snapshot; every other -q quits after the first 4 KB
case "\$1 \$2" in "-q .") cat > /dev/null; exit 1 ;; esac
case "\$1" in -q*) chunk="\$(head -c 4096)"; exec "$REAL_GREP" "\$@" <<< "\$chunk" ;; esac
exec "$REAL_GREP" "\$@"
SH
chmod +x "$T/earlygrep1/grep"
EXTRA_PATH="$T/earlygrep1" run plan.json --qc-session "$T/qcs-minted.json"
EXTRA_PATH=""
[ "$(wf21)" = PASS ] && ok "large snapshot dir with an early-quitting grep: WF-21 PASS (first check)" || bad "large snapshot dir with an early-quitting grep: WF-21 is '$(wf21)', not PASS (first check)"
mkdir -p "$T/earlygrep2"
cat > "$T/earlygrep2/grep" <<SH
#!/usr/bin/env bash
# the id-pattern -q check finds nothing; every other -q quits after the first 4 KB like a real grep -q
case "\$1 \$2" in "-q WFTEST001") cat > /dev/null; exit 1 ;; esac
case "\$1" in -q*) chunk="\$(head -c 4096)"; exec "$REAL_GREP" "\$@" <<< "\$chunk" ;; esac
exec "$REAL_GREP" "\$@"
SH
chmod +x "$T/earlygrep2/grep"
EXTRA_PATH="$T/earlygrep2" run plan.json --qc-session "$T/qcs-minted.json"
EXTRA_PATH=""
[ "$(wf21)" = PASS ] && ok "large snapshot dir with an early-quitting grep: WF-21 PASS (second check)" || bad "large snapshot dir with an early-quitting grep: WF-21 is '$(wf21)', not PASS (second check)"
rm -rf "$T/home/.openclaw/tools/convert-and-flow-cli/data/snapshots"

# 6c. The script's own stderr must carry no shell noise. A backtick pair inside the double-quoted WF-18 python
#    block ran as command substitution and printed "referenced: command not found" on every run.
env PATH="$T/bin:$PATH" HOME="$T/home" OPENCLAW_PLATFORM=mac QC_TEST_EXPORT="$T/export.json" \
  bash "$QC" WFTEST001 --deps "$T/deps.json" --publish-intent DRAFT --re-entry ONCE \
  --plan-mode-file "$T/plan.json" --grades "$T/grades.json" --qc-session "$T/qcs-minted.json" >/dev/null 2>"$T/stderr.txt"
case "$(cat "$T/stderr.txt")" in *"command not found"*) bad "script stderr carries 'command not found': $(head -c 200 "$T/stderr.txt")" ;; *) ok "script stderr carries no 'command not found'" ;; esac

# 7. Fail closed when the gate itself cannot run: a python3 that dies on the PLAN MODE / QC session check
#    (and runs everything else normally) must end in exit 1 naming plan_gate_error, never exit 0.
mkdir -p "$T/crashpy"
REAL_PY="$(type -P python3)"
cat > "$T/crashpy/python3" <<SH
#!/usr/bin/env bash
if [ "\${@: -1}" = "-" ] || printf '%s\n' "\$@" | grep -qx -- '-'; then
  script="\$(cat)"
  case "\$script" in *SESSION_RE*) echo "simulated crash" >&2; exit 3 ;; esac
  exec "$REAL_PY" "\$@" <<< "\$script"
fi
exec "$REAL_PY" "\$@"
SH
chmod +x "$T/crashpy/python3"
EXTRA_PATH="$T/crashpy" run plan.json --qc-session "$T/qcs-minted.json"
EXTRA_PATH=""
refused "PLAN MODE gate that cannot run" plan_gate_error
[ "$RC" -eq 1 ] && ok "crashed gate exit is 1" || bad "crashed gate exit is $RC, not 1"

echo
if [ "$FAILS" -eq 0 ]; then echo "ALL PASS"; exit 0; fi
echo "$FAILS FAILED"; exit 1
