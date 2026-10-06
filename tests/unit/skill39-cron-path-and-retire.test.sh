#!/usr/bin/env bash
# tests/unit/skill39-cron-path-and-retire.test.sh
# Skill 39 RE crons:
#   T1 non-RE box: an enabled pre-gate RE cron is DISABLED (kept, not deleted), nothing added.
#   T2 the same retirement runs through wire.sh (the per-roll path), not only a direct call.
#   T3 RE box: a fresh registration carries the REAL master-files path, no placeholder.
#   T4 RE box: an existing placeholder cron is repaired in place (same id, no duplicate).
#   T5 RE box with MASTER_FILES_DIR unresolved: nothing registered.
#   T6 anti-vacuity: origin's pre-fix 07 (from git, when available) leaves T1's cron enabled.
# Hermetic: private HOME, fake `openclaw` (tests/fixtures/fake-openclaw-cron.py).
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FIXTURE="$REPO_ROOT/tests/fixtures/fake-openclaw-cron.py"
SB="$(mktemp -d)"; trap 'rm -rf "$SB"' EXIT
PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

mkdir -p "$SB/repo/shared-utils" "$SB/bin"
cp -r "$REPO_ROOT/39-real-estate-playbook" "$SB/repo/"
cp "$REPO_ROOT/shared-utils/industry-gate.sh" "$REPO_ROOT/shared-utils/cron-lib.sh" "$SB/repo/shared-utils/"
printf '#!/usr/bin/env bash\nexec python3 "%s" "$@"\n' "$FIXTURE" > "$SB/bin/openclaw"; chmod +x "$SB/bin/openclaw"
REG="$SB/repo/39-real-estate-playbook/scripts/07-register-crons.sh"
PLACEHOLDER_MSG='Skill 39 daily post-close anniversary + sphere-reactivation scan ... append the corresponding events to <MASTER_FILES_DIR>/real-estate-events.jsonl.'

setup() { # <case> <industry-slug-or-empty> -> prints HOME; seeds one enabled pre-gate anniversary cron
  local h="$SB/$1"; mkdir -p "$h/.openclaw/workspace" "$h/mfd"
  [ -n "$2" ] && printf '{"industryPack":{"slug":"%s","source":"interview"}}' "$2" > "$h/.openclaw/workspace/.workforce-build-state.json"
  python3 -c "import json,sys; json.dump([{'id':'old-1','name':'re-post-close-anniversary','kind':'agentTurn','enabled':True,'message':sys.argv[1]}], open(sys.argv[2],'w'))" "$PLACEHOLDER_MSG" "$h/jobs.json"
  : > "$h/calls"; echo "$h"
}
run() { # <home> <script> [MASTER_FILES_DIR]
  HOME="$1" PATH="$SB/bin:$PATH" FAKE_OC_JOBS_FILE="$1/jobs.json" FAKE_OC_CALLS_FILE="$1/calls" MASTER_FILES_DIR="${3-}" \
    OPENCLAW_SKILLS_DIR="$SB/repo" timeout 60 bash "$2" > "$1/out.log" 2>&1
}
# q: evaluate a test-authored literal expression over the fixture jobs (J). Test-only.
q() { python3 -c "import json,sys; J=json.load(open(sys.argv[1])); print(eval(sys.argv[2]))" "$1/jobs.json" "$2"; }

echo "=== skill39-cron-path-and-retire ==="
H=$(setup t1 saas); run "$H" "$REG"
[ "$(q "$H" "[j.get('enabled',True) for j in J if j['id']=='old-1']")" = "[False]" ] && pass "T1a non-RE: pre-gate cron disabled" || fail "T1a cron not disabled: $(q "$H" J)"
[ "$(q "$H" "len(J)")" = "1" ] && pass "T1b cron kept, nothing added" || fail "T1b job count $(q "$H" "len(J)")"
grep -q "cron add" "$H/calls" && fail "T1c cron add called on non-RE box" || pass "T1c no cron add on non-RE box"

H=$(setup t2 ""); run "$H" "$SB/repo/39-real-estate-playbook/wire.sh"
[ "$(q "$H" "[j.get('enabled',True) for j in J]")" = "[False]" ] && pass "T2 wire.sh (no industryPack) retires the cron" || fail "T2 wire.sh did not retire: $(q "$H" J)"

H=$(setup t3 real-estate); echo '[]' > "$H/jobs.json"; run "$H" "$REG" "$H/mfd"
python3 -c "
import json,sys; J=[j for j in json.load(open('$H/jobs.json')) if j['name']=='re-post-close-anniversary']
sys.exit(0 if len(J)==1 and '<MASTER_FILES_DIR>' not in J[0]['message'] and '$H/mfd/real-estate-events.jsonl' in J[0]['message'] else 1)" \
  && pass "T3 fresh registration carries the real path" || fail "T3 message not substituted: $(q "$H" "[j['message'][-90:] for j in J]")"

H=$(setup t4 real-estate); run "$H" "$REG" "$H/mfd"
python3 -c "
import json,sys; J=[j for j in json.load(open('$H/jobs.json')) if j['name']=='re-post-close-anniversary']
sys.exit(0 if len(J)==1 and J[0]['id']=='old-1' and '<MASTER_FILES_DIR>' not in J[0]['message'] and '$H/mfd/' in J[0]['message'] else 1)" \
  && pass "T4 placeholder cron repaired in place (same id, no duplicate)" || fail "T4 repair failed: $(q "$H" J)"

H=$(setup t5 real-estate); echo '[]' > "$H/jobs.json"; run "$H" "$REG" ""
[ "$(q "$H" "len(J)")" = "0" ] && grep -q "MASTER_FILES_DIR unresolved" "$H/out.log" && pass "T5 unresolved path -> nothing registered" || fail "T5 registered without a path: $(q "$H" "len(J)")"

if OLD="$(git -C "$REPO_ROOT" show origin/main:39-real-estate-playbook/scripts/07-register-crons.sh 2>/dev/null)" && ! grep -q "_re_cron_rows" <<<"$OLD"; then
  printf '%s\n' "$OLD" > "$SB/repo/39-real-estate-playbook/scripts/07-old.sh"
  H=$(setup t6 saas); run "$H" "$SB/repo/39-real-estate-playbook/scripts/07-old.sh"
  [ "$(q "$H" "[j.get('enabled',True) for j in J]")" = "[True]" ] && pass "T6 anti-vacuity: pre-fix registrar leaves the cron enabled" || fail "T6 pre-fix registrar also disabled it (T1 is vacuous)"
else
  echo "  SKIP: T6 (origin/main copy unavailable or already fixed)"
fi
echo "=== $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
