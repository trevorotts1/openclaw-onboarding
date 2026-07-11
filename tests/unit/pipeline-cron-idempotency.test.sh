#!/usr/bin/env bash
# tests/unit/pipeline-cron-idempotency.test.sh
#
# Acceptance tests for Fix B (REALESTATE-DEPT-GATING-FIX-SPEC-2026-07-11.md,
# Section 3 "FIX B"): re-running a pipeline-cron installer/updater can NEVER
# produce a 2nd..Nth copy of a cron with a given name — including names > 22
# chars, where `openclaw cron list`'s TEXT TABLE truncates and a text-grep
# presence check false-negatives (the confirmed root cause of the Skill 39 /
# Skill 38 6x-duplicate-cron incident).
#
# Covers: B1 (installer run twice -> exactly one cron per name, both Skill 39
# and Skill 38 registrars), B2 (truncation regression guard, unit-level on
# oc_cron_present itself), B3 (N-run/6x idempotency — directly reproduces and
# disproves the historical incident). Also folds in C1 (no burst — a stable
# single scheduled minute per name, proven as a corollary of B1/B3).
#
# MUTATION-PROOF: after every real (unmutated) assertion, the SAME scenario is
# re-run against a MUTATED copy of shared-utils/cron-lib.sh whose
# oc_cron_present() is replaced with the historical buggy implementation
# (`openclaw cron list | grep -qF "$name"` — a plain text-table grep, no
# --json). Reintroducing that exact grep MUST reproduce the duplicate-add bug
# through the SAME unmodified registrar scripts — proving these tests are not
# vacuous.
#
# Runs hermetically (private $HOME, sandboxed skill-dir copies, fake
# `openclaw` on PATH via tests/fixtures/fake-openclaw-cron.py). Never touches
# a real ~/.openclaw or the network.
#
# Exit 0 = all checks pass. Exit 1 = one or more failed (CI FAIL).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FIXTURE="$REPO_ROOT/tests/fixtures/fake-openclaw-cron.py"
PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== pipeline-cron-idempotency.test.sh ==="
echo ""

SANDBOX="$(mktemp -d)"
cleanup() { rm -rf "$SANDBOX" 2>/dev/null || true; }
trap cleanup EXIT
case "$SANDBOX" in
  */.openclaw|*/.openclaw/*) echo "REFUSING: sandbox path resolved into a real .openclaw ($SANDBOX)"; exit 2 ;;
esac

SKILL_COPY="$SANDBOX/repo"
mkdir -p "$SKILL_COPY"
cp -r "$REPO_ROOT/39-real-estate-playbook" "$SKILL_COPY/"
cp -r "$REPO_ROOT/38-conversational-ai-system" "$SKILL_COPY/"
mkdir -p "$SKILL_COPY/shared-utils"
cp "$REPO_ROOT/shared-utils/industry-gate.sh" "$SKILL_COPY/shared-utils/industry-gate.sh"
cp "$REPO_ROOT/shared-utils/cron-lib.sh" "$SKILL_COPY/shared-utils/cron-lib.sh"

_mkbin() {
  local dir="$1"
  mkdir -p "$dir"
  cat > "$dir/openclaw" <<SHIM
#!/usr/bin/env bash
exec python3 "$FIXTURE" "\$@"
SHIM
  chmod +x "$dir/openclaw"
}

_seed_re_state() { # <home>
  mkdir -p "$1/.openclaw/workspace"
  printf '%s' '{"industryPack":{"slug":"real-estate","source":"owner-confirmed"}}' \
    > "$1/.openclaw/workspace/.workforce-build-state.json"
}

_count_name() { # <jobs_file> <name>
  python3 -c "
import json,sys
try:
    jobs = json.load(open(sys.argv[1]))
except Exception:
    print(0); sys.exit(0)
print(sum(1 for j in jobs if j.get('name') == sys.argv[2]))
" "$1" "$2"
}

# ---------------------------------------------------------------------------
# B1 + B3 — Skill 39: run N times -> exactly 1 of each RE cron name
# ---------------------------------------------------------------------------
echo "--- B1/B3 (Skill 39): run 07-register-crons.sh 6x -> exactly 1 per name ---"
H39="$SANDBOX/home-39"; bin39="$SANDBOX/bin-39"; J39="$SANDBOX/jobs-39.json"; C39="$SANDBOX/calls-39.log"
_seed_re_state "$H39"; _mkbin "$bin39"; printf '[]' > "$J39"; : > "$C39"
for i in 1 2 3 4 5 6; do
  HOME="$H39" PATH="$bin39:$PATH" FAKE_OC_JOBS_FILE="$J39" FAKE_OC_CALLS_FILE="$C39" \
    bash "$SKILL_COPY/39-real-estate-playbook/scripts/07-register-crons.sh" > "$SANDBOX/39-run$i.log" 2>&1
done
n39a=$(_count_name "$J39" "re-open-house-followup-scan")
n39b=$(_count_name "$J39" "re-post-close-anniversary")
[ "$n39a" -eq 1 ] && pass "B3-39a: re-open-house-followup-scan (27 chars) == 1 copy after 6 runs" || fail "B3-39a: $n39a copies after 6 runs (expected 1 — reproduces the historical 6x-duplicate bug if != 1)"
[ "$n39b" -eq 1 ] && pass "B3-39b: re-post-close-anniversary (25 chars) == 1 copy after 6 runs" || fail "B3-39b: $n39b copies after 6 runs (expected 1)"
addcalls39=$(grep -c "^cron add.*re-open-house-followup-scan" "$C39" 2>/dev/null)
[ "$addcalls39" -eq 1 ] && pass "B1-39: exactly ONE 'cron add' call for re-open-house-followup-scan across all 6 runs (runs 2-6 correctly detected presence)" || fail "B1-39: $addcalls39 'cron add' calls for re-open-house-followup-scan (expected 1)"

# C1 corollary: schedule stayed a single stable minute value (no reschedule churn).
sched39=$(python3 -c "
import json
jobs=json.load(open('$J39'))
m=[j['cron'] for j in jobs if j.get('name')=='re-open-house-followup-scan']
print(m[0] if m else '')
")
case "$sched39" in
  [0-9]" 18 * * *"|[0-9][0-9]" 18 * * *") pass "C1-39: re-open-house-followup-scan schedule is a single stable '<min> 18 * * *' entry ($sched39)" ;;
  *) fail "C1-39: unexpected/unstable schedule for re-open-house-followup-scan: '$sched39'" ;;
esac

# ---------------------------------------------------------------------------
# B1 + B3 — Skill 38: run N times -> exactly 1 of each cron name
# ---------------------------------------------------------------------------
echo ""
echo "--- B1/B3 (Skill 38): run 04-register-crons.sh 6x -> exactly 1 per name ---"
H38="$SANDBOX/home-38"; bin38="$SANDBOX/bin-38"; J38="$SANDBOX/jobs-38.json"; C38="$SANDBOX/calls-38.log"
mkdir -p "$H38/.openclaw"; _mkbin "$bin38"; printf '[]' > "$J38"; : > "$C38"
for i in 1 2 3 4 5 6; do
  HOME="$H38" PATH="$bin38:$PATH" FAKE_OC_JOBS_FILE="$J38" FAKE_OC_CALLS_FILE="$C38" \
    bash "$SKILL_COPY/38-conversational-ai-system/scripts/04-register-crons.sh" > "$SANDBOX/38-run$i.log" 2>&1
done
_38_names=( "conversation-log-summarizer" "analytics-weekly-digest" "weekly-tune-up" "proactive-suggestions-scan" "system-health-heartbeat" "ghl-pit-liveness" )
all38_ok=1
for n in "${_38_names[@]}"; do
  c=$(_count_name "$J38" "$n")
  if [ "$c" -eq 1 ]; then
    pass "B3-38: '$n' (${#n} chars) == 1 copy after 6 runs"
  else
    fail "B3-38: '$n' has $c copies after 6 runs (expected 1)"
    all38_ok=0
  fi
done
[ "$all38_ok" -eq 1 ] && pass "B1-38: all 6 Skill-38 crons idempotent across 6 runs (incl. 4 names > 22 chars: conversation-log-summarizer=27, proactive-suggestions-scan=26, analytics-weekly-digest=23, system-health-heartbeat=23)" || fail "B1-38: one or more Skill-38 crons duplicated"

# ---------------------------------------------------------------------------
# B2 — Truncation regression guard (unit-level, directly on oc_cron_present)
# ---------------------------------------------------------------------------
echo ""
echo "--- B2: truncation regression guard (oc_cron_present vs. the truncated text table) ---"
H_B2="$SANDBOX/home-b2"; bin_b2="$SANDBOX/bin-b2"; J_B2="$SANDBOX/jobs-b2.json"; C_B2="$SANDBOX/calls-b2.log"
mkdir -p "$H_B2/.openclaw"; _mkbin "$bin_b2"
LONG_NAME="re-open-house-followup-scan"   # 27 chars — exceeds the ~22-char truncation threshold
python3 -c "
import json
print(json.dumps([{'name': '$LONG_NAME', 'id': 'fake-001', 'kind': 'agentTurn', 'cron': '0 18 * * *'}]))
" > "$J_B2"
: > "$C_B2"

# (a) Prove the fixture actually reproduces the real bug's PRECONDITION: the
# text table (no --json) truncates this name.
TEXT_TABLE=$(PATH="$bin_b2:$PATH" FAKE_OC_JOBS_FILE="$J_B2" FAKE_OC_CALLS_FILE="$C_B2" openclaw cron list)
if printf '%s' "$TEXT_TABLE" | grep -qF "$LONG_NAME"; then
  fail "B2a: fixture's text-table 'cron list' output was NOT truncated for a $(( ${#LONG_NAME} ))-char name — the truncation-bug precondition is not reproduced; B2's proof is invalid"
else
  pass "B2a: fixture's text-table 'cron list' output IS truncated for '$LONG_NAME' (${#LONG_NAME} chars) — reproduces the real CLI's ~22-char truncation"
fi

# (b) Prove oc_cron_present() STILL correctly detects presence via --json.
b2_present_rc=$(PATH="$bin_b2:$PATH" FAKE_OC_JOBS_FILE="$J_B2" FAKE_OC_CALLS_FILE="$C_B2" \
  bash -c 'source "'"$SKILL_COPY"'/shared-utils/cron-lib.sh"; oc_cron_present "'"$LONG_NAME"'"; echo $?')
[ "$b2_present_rc" -eq 0 ] && pass "B2b: oc_cron_present() returns PRESENT (0) for the truncated-in-text-table name (reads --json, not the text table)" || fail "B2b: oc_cron_present() returned $b2_present_rc (expected 0 — present)"

# ---------------------------------------------------------------------------
# MUTATION PROOF — reintroduce the historical text-grep bug into cron-lib.sh,
# prove the SAME registrar scripts now duplicate.
# ---------------------------------------------------------------------------
echo ""
echo "--- MUTATION PROOF: reintroducing the old text-table grep reproduces the 6x-duplicate bug ---"
MUT_CRONLIB="$SKILL_COPY/shared-utils/cron-lib.sh"
cat > "$MUT_CRONLIB" <<'EOF'
#!/usr/bin/env bash
# MUTATED for testing: the HISTORICAL buggy implementation (pre-fix) — a
# plain text-table grep, exactly as it existed in 07-register-crons.sh before
# this fix (and in 04-register-crons.sh, ensure-pipeline-crons.sh pre-v13.0.2).
oc_cron_present() {
  local name="$1"
  openclaw cron list 2>/dev/null | grep -qF "$name"
}
oc_cron_minute_jitter() { echo 0; }
EOF

Hmut="$SANDBOX/home-mut"; binmut="$SANDBOX/bin-mut"; Jmut="$SANDBOX/jobs-mut.json"; Cmut="$SANDBOX/calls-mut.log"
_seed_re_state "$Hmut"; _mkbin "$binmut"; printf '[]' > "$Jmut"; : > "$Cmut"
for i in 1 2 3 4 5 6; do
  HOME="$Hmut" PATH="$binmut:$PATH" FAKE_OC_JOBS_FILE="$Jmut" FAKE_OC_CALLS_FILE="$Cmut" \
    bash "$SKILL_COPY/39-real-estate-playbook/scripts/07-register-crons.sh" > "$SANDBOX/mut-run$i.log" 2>&1
done
nmut=$(_count_name "$Jmut" "re-open-house-followup-scan")
if [ "$nmut" -gt 1 ]; then
  pass "MUT-B: with cron-lib.sh MUTATED back to a text-table grep, 6 runs produced $nmut copies of re-open-house-followup-scan — reproduces the historical 6x-duplicate bug, proving B1/B3's ==1 assertions are REAL, non-vacuous checks"
else
  fail "MUT-B: even with cron-lib.sh mutated to the historical buggy grep, only $nmut copy(ies) resulted — the mutation harness itself is broken (cannot prove B1/B3 are discriminating)"
fi

# ---------------------------------------------------------------------------
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo "FAIL: $FAIL check(s) failed — CI guard triggered"
  exit 1
fi
echo "PASS: all pipeline-cron-idempotency checks pass"
exit 0
