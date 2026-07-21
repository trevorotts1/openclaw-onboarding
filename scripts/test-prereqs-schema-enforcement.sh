#!/usr/bin/env bash
# test-prereqs-schema-enforcement.sh -- prove a declared skill dependency is
# ACTUALLY enforced, in both directions, by driving the REAL checker.
#
# Every assertion here was verified to FAIL against the pre-v12.11.0 checker and
# the pre-v12.11.0 lint. A test that passes against both the broken and the
# fixed code proves nothing, so each case below is paired: dependency PRESENT
# must report satisfied (rc 0) AND dependency ABSENT must name it unmet (rc 2).
# A checker that hard-codes False passes the ABSENT half and fails the PRESENT
# half -- which is exactly how {"skillId": N} used to behave.
#
# Usage: bash scripts/test-prereqs-schema-enforcement.sh
# Exit 0 = all assertions pass, 1 = at least one failed.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECKER="$REPO_ROOT/shared-utils/check-skill-prereqs.sh"
LINT="$REPO_ROOT/scripts/qc-prereqs-json.sh"

PASS=0
FAIL=0

SANDBOX="$(mktemp -d)"
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT

# Isolate HOME so the checker's state-file writer can never touch a real
# ~/.openclaw/.onboarding-state.json on an operator or fleet box.
export HOME="$SANDBOX/home"
mkdir -p "$HOME"

ok()   { PASS=$((PASS+1)); printf '  PASS  %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }

# run_checker <case-dir> <dep-present:0|1> -> sets RC and OUT
run_checker() {
  local case_dir="$1" present="$2"
  rm -rf "$case_dir/skills/07-kie-setup"
  [[ "$present" == "1" ]] && mkdir -p "$case_dir/skills/07-kie-setup"
  OUT="$(bash "$CHECKER" "$case_dir/skills/99-under-test" 2>&1)"
  RC=$?
}

# make_case <name> <prereqs-json>
make_case() {
  local name="$1" body="$2"
  local dir="$SANDBOX/$name"
  rm -rf "$dir"
  mkdir -p "$dir/skills/99-under-test"
  printf '%s' "$body" > "$dir/skills/99-under-test/PREREQS.json"
  printf '%s' "$dir"
}

echo "== A. type=skill declared as {\"skillId\": N} =="
DIR="$(make_case a '{"skill":"99-under-test","prerequisites":[{"id":"skill-07","type":"skill","label":"Skill 07 - Kie Setup","check":{"skillId":7},"severity":"required","satisfy":"Install Skill 07."}]}')"
run_checker "$DIR" 1
[[ $RC -eq 0 ]] && ok "skillId + dependency PRESENT -> satisfied (rc 0)" \
                || bad "skillId + dependency PRESENT -> expected rc 0, got $RC :: $OUT"
run_checker "$DIR" 0
if [[ $RC -eq 2 && "$OUT" == *"skill-07"* ]]; then
  ok "skillId + dependency ABSENT -> named unmet (rc 2)"
else
  bad "skillId + dependency ABSENT -> expected rc 2 naming skill-07, got $RC :: $OUT"
fi

echo "== B. type=skill declared as {\"skill\": \"<folder>\"} =="
DIR="$(make_case b '{"skill":"99-under-test","prerequisites":[{"id":"skill-07","type":"skill","label":"Skill 07 - Kie Setup","check":{"skill":"07-kie-setup"},"severity":"required","satisfy":"Install Skill 07."}]}')"
run_checker "$DIR" 1
[[ $RC -eq 0 ]] && ok "folder form + dependency PRESENT -> satisfied (rc 0)" \
                || bad "folder form + dependency PRESENT -> expected rc 0, got $RC :: $OUT"
run_checker "$DIR" 0
if [[ $RC -eq 2 && "$OUT" == *"skill-07"* ]]; then
  ok "folder form + dependency ABSENT -> named unmet (rc 2)"
else
  bad "folder form + dependency ABSENT -> expected rc 2 naming skill-07, got $RC :: $OUT"
fi

echo "== C. unknown / missing type must FAIL CLOSED, never silently pass =="
DIR="$(make_case c '{"prerequisites":[{"skillId":7,"skillName":"kie-setup","required":true,"envVar":"KIE_API_KEY","description":"needs skill 07","satisfy":"Run the Skill 07 installer"}]}')"
run_checker "$DIR" 0
if [[ $RC -eq 2 ]]; then
  ok "legacy shape with no 'type' -> unmet (rc 2), not a silent pass"
else
  bad "legacy shape with no 'type' -> expected rc 2, got $RC :: $OUT"
fi
DIR="$(make_case c2 '{"skill":"99-under-test","prerequisites":[{"id":"bogus","type":"service-balance","label":"invented type","check":{"note":"x"},"severity":"required","satisfy":"do the thing"}]}')"
run_checker "$DIR" 0
if [[ $RC -eq 2 && "$OUT" == *"bogus"* ]]; then
  ok "invented type -> named unmet (rc 2), not a silent pass"
else
  bad "invented type -> expected rc 2 naming bogus, got $RC :: $OUT"
fi

echo "== D. type=state is executed in both directions =="
DIR="$(make_case d "{\"skill\":\"99-under-test\",\"prerequisites\":[{\"id\":\"interview-complete\",\"type\":\"state\",\"label\":\"interview complete\",\"check\":{\"stateFile\":\"$SANDBOX/state.json\",\"field\":\"interviewComplete\",\"equals\":true},\"severity\":\"required\",\"satisfy\":\"Complete the interview.\"}]}")"
rm -f "$SANDBOX/state.json"
run_checker "$DIR" 0
if [[ $RC -eq 2 && "$OUT" == *"interview-complete"* ]]; then
  ok "state file MISSING -> named unmet (rc 2)"
else
  bad "state file MISSING -> expected rc 2, got $RC :: $OUT"
fi
printf '{"interviewComplete": false}' > "$SANDBOX/state.json"
run_checker "$DIR" 0
[[ $RC -eq 2 ]] && ok "state field FALSE -> unmet (rc 2)" \
                || bad "state field FALSE -> expected rc 2, got $RC :: $OUT"
printf '{"interviewComplete": true}' > "$SANDBOX/state.json"
run_checker "$DIR" 0
[[ $RC -eq 0 ]] && ok "state field TRUE -> satisfied (rc 0)" \
                || bad "state field TRUE -> expected rc 0, got $RC :: $OUT"

echo "== E. lint rejects declarations the runtime cannot enforce =="
lint_fixture() { # lint_fixture <name> <json> ; sets LRC and LOUT
  local name="$1" body="$2"
  local root="$SANDBOX/lint-$name"
  rm -rf "$root"; mkdir -p "$root/scripts" "$root/99-fixture"
  cp "$LINT" "$root/scripts/qc-prereqs-json.sh"
  printf '%s' "$body" > "$root/99-fixture/PREREQS.json"
  LOUT="$(bash "$root/scripts/qc-prereqs-json.sh" 2>&1)"
  LRC=$?
}

lint_fixture skillkey '{"skill":"99-fixture","prerequisites":[{"id":"dep","type":"skill","label":"dep","check":{"skillName":"kie-setup"},"severity":"required","satisfy":"install it"}]}'
if [[ $LRC -eq 1 && "$LOUT" == *"enforce nothing"* ]]; then
  ok "lint rejects type=skill whose check has neither 'skill' nor 'skillId'"
else
  bad "lint should reject unenforceable skill check, got rc $LRC :: $LOUT"
fi

lint_fixture dangling '{"skill":"99-fixture","prerequisites":[{"id":"dep","type":"skill","label":"dep","check":{"skill":"19-cloudflare-setup"},"severity":"required","satisfy":"install it"}]}'
if [[ $LRC -eq 1 && "$LOUT" == *"does not exist"* ]]; then
  ok "lint rejects a skill dependency naming a folder that does not exist"
else
  bad "lint should reject dangling skill dependency, got rc $LRC :: $LOUT"
fi

lint_fixture manualreq '{"skill":"99-fixture","prerequisites":[{"id":"dep","type":"manual","label":"dep","check":{"note":"x"},"severity":"required","satisfy":"do it"}]}'
if [[ $LRC -eq 1 && "$LOUT" == *"cannot be required"* ]]; then
  ok "lint rejects type=manual carrying severity=required"
else
  bad "lint should reject manual+required, got rc $LRC :: $LOUT"
fi

lint_fixture badsev '{"skill":"99-fixture","prerequisites":[{"id":"dep","type":"credential","label":"dep","check":{"envVar":"X"},"severity":"warning","satisfy":"set it"}]}'
if [[ $LRC -eq 1 && "$LOUT" == *"unknown severity"* ]]; then
  ok "lint rejects severity 'warning'"
else
  bad "lint should reject severity 'warning', got rc $LRC :: $LOUT"
fi

echo "== F. every PREREQS.json in this repo passes the lint =="
if bash "$LINT" >/dev/null 2>&1; then
  ok "repo-wide qc-prereqs-json.sh passes"
else
  bad "repo-wide qc-prereqs-json.sh FAILED: $(bash "$LINT" 2>&1 | tail -20)"
fi

echo
echo "prereqs schema enforcement: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]] || exit 1
exit 0
