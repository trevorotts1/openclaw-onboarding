#!/usr/bin/env bash
# tests/unit/cron-tombstone-durability.test.sh
#
# Acceptance tests for the DURABLE TOMBSTONE fix (fix/industry-gate-and-idempotent-crons,
# added 2026-07-11 in response to a live-VPS finding relayed mid-branch):
# `openclaw cron list --json` was observed on a live box returning ONLY
# ENABLED jobs (16 of 31 rows actually present — the 15 missing rows were
# disabled duplicates). Every presence check in this fix (_cron_present /
# oc_cron_present) reads exactly that view, so a DISABLED-and-invisible cron
# is silently RESURRECTED by the next install.sh/update-skills.sh run. A fleet
# cleanup that disables duplicate crons is therefore undone by the very next
# version update — unless a disable/removal is made DURABLE independent of
# `cron list --json` visibility. That is what oc_cron_tombstone /
# oc_cron_tombstoned (shared-utils/cron-lib.sh) + scripts/tombstone-cron.sh do.
#
# T1  Best-effort flag-detection layer: WHEN the fake CLI's `cron list --help`
#     DOES advertise a full-visibility flag, oc_cron_present correctly uses it
#     to see an otherwise-hidden job (the CLI-support-permitting case).
# T2  THE DECISIVE CASE — the fake CLI advertises NO such flag at all
#     (matching docs.openclaw.ai/cli/cron, which documents none, and the
#     live-observed box): a job is registered, then marked "hidden" (simulates
#     an operator disabling it — genuinely invisible to `cron list --json`,
#     the worst case actually observed). WITHOUT a tombstone, re-running the
#     SAME registrar RESURRECTS it — reproducing the live defect exactly.
# T3  The exact sequence requested: register -> disable (hidden) ->
#     tombstone -> run the updater again -> assert NOT resurrected. This is
#     the end-to-end proof the fleet cleanup's kills can survive an update.
# MUTATION PROOF: remove the tombstone check from a copy of the registrar
#     (revert to the historical add-or-skip-on-presence-only shape) and prove
#     the SAME T3 sequence now DOES resurrect the job — T3's assertion is a
#     real, non-vacuous check of the tombstone wiring, not an incidental pass.
#
# Runs hermetically; never touches a real ~/.openclaw or network.
# Exit 0 = all checks pass. Exit 1 = one or more failed (CI FAIL).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FIXTURE="$REPO_ROOT/tests/fixtures/fake-openclaw-cron.py"
PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== cron-tombstone-durability.test.sh ==="
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
mkdir -p "$SKILL_COPY/shared-utils" "$SKILL_COPY/scripts"
cp "$REPO_ROOT/shared-utils/industry-gate.sh" "$SKILL_COPY/shared-utils/industry-gate.sh"
cp "$REPO_ROOT/shared-utils/cron-lib.sh" "$SKILL_COPY/shared-utils/cron-lib.sh"
# Placed at $SKILL_COPY/scripts/ (sibling of $SKILL_COPY/shared-utils/), same
# relative layout as the real repo, so tombstone-cron.sh's own
# "$(dirname script)/../shared-utils/cron-lib.sh" resolution finds the
# sandboxed cron-lib.sh with NO path-patching needed.
cp "$REPO_ROOT/scripts/tombstone-cron.sh" "$SKILL_COPY/scripts/tombstone-cron.sh"
TOMBSTONE_SCRIPT="$SKILL_COPY/scripts/tombstone-cron.sh"

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

_count_visible() { # <jobs_file> <name>  (jobs NOT marked hidden)
  python3 -c "
import json,sys
try:
    jobs = json.load(open(sys.argv[1]))
except Exception:
    print(0); sys.exit(0)
print(sum(1 for j in jobs if j.get('name') == sys.argv[2] and not j.get('hidden')))
" "$1" "$2"
}

_mark_hidden() { # <jobs_file> <name>  — simulate "operator disabled it"
  python3 -c "
import json,sys
jobs = json.load(open(sys.argv[1]))
for j in jobs:
    if j.get('name') == sys.argv[2]:
        j['hidden'] = True
json.dump(jobs, open(sys.argv[1], 'w'))
" "$1" "$2"
}

TARGET="re-open-house-followup-scan"   # 27 chars, the real Skill-39 cron name

# ---------------------------------------------------------------------------
# T1 — best-effort flag layer works WHEN the CLI advertises one
# ---------------------------------------------------------------------------
echo "--- T1: best-effort flag detection sees a hidden job WHEN the CLI advertises a status flag ---"
H1="$SANDBOX/home-t1"; bin1="$SANDBOX/bin-t1"; J1="$SANDBOX/jobs-t1.json"; C1="$SANDBOX/calls-t1.log"
mkdir -p "$H1/.openclaw"; _mkbin "$bin1"
python3 -c "
import json
print(json.dumps([{'name':'$TARGET','id':'fake-001','kind':'command','cron':'0 18 * * *','hidden':True}]))
" > "$J1"
: > "$C1"
t1_rc=$(HOME="$H1" PATH="$bin1:$PATH" FAKE_OC_JOBS_FILE="$J1" FAKE_OC_CALLS_FILE="$C1" \
  FAKE_OC_ADVERTISE_STATUS_FLAG=1 \
  bash -c 'source "'"$SKILL_COPY"'/shared-utils/cron-lib.sh"; oc_cron_present "'"$TARGET"'"; echo $?')
[ "$t1_rc" -eq 0 ] && pass "T1: oc_cron_present sees a HIDDEN job (rc=0) once the CLI advertises --status (best-effort layer works when available)" \
                   || fail "T1: oc_cron_present did not see the hidden job even with the flag advertised (rc=$t1_rc, expected 0)"

# ---------------------------------------------------------------------------
# T2 — THE DECISIVE CASE: no flag advertised at all (matches the live box) —
# a hidden job is genuinely invisible, and WITHOUT a tombstone gets resurrected.
# ---------------------------------------------------------------------------
echo ""
echo "--- T2: no full-visibility flag advertised (matches docs.openclaw.ai/cli/cron + the live box) ---"
H2="$SANDBOX/home-t2"; bin2="$SANDBOX/bin-t2"; J2="$SANDBOX/jobs-t2.json"; C2="$SANDBOX/calls-t2.log"
_seed_re_state "$H2"; _mkbin "$bin2"
# Run 1: register normally (both RE crons land).
: > "$C2"; printf '[]' > "$J2"
HOME="$H2" PATH="$bin2:$PATH" FAKE_OC_JOBS_FILE="$J2" FAKE_OC_CALLS_FILE="$C2" \
  bash "$SKILL_COPY/39-real-estate-playbook/scripts/07-register-crons.sh" > "$SANDBOX/t2-run1.log" 2>&1
before=$(_count_visible "$J2" "$TARGET")
[ "$before" -eq 1 ] && pass "T2a: initial registration landed exactly 1 copy of $TARGET" || fail "T2a: initial registration landed $before copies (expected 1)"

# Simulate: operator disables it (hidden=true; invisible to --json with NO
# flag advertised, since FAKE_OC_ADVERTISE_STATUS_FLAG is unset here).
_mark_hidden "$J2" "$TARGET"

# Run 2 (the "next update"): WITHOUT any tombstone, run the SAME registrar again.
HOME="$H2" PATH="$bin2:$PATH" FAKE_OC_JOBS_FILE="$J2" FAKE_OC_CALLS_FILE="$C2" \
  bash "$SKILL_COPY/39-real-estate-playbook/scripts/07-register-crons.sh" > "$SANDBOX/t2-run2.log" 2>&1
after_visible=$(_count_visible "$J2" "$TARGET")
after_total=$(python3 -c "
import json
jobs=json.load(open('$J2'))
print(sum(1 for j in jobs if j.get('name')=='$TARGET'))
")
if [ "$after_total" -ge 2 ]; then
  pass "T2b: WITHOUT a tombstone, disabling+re-updating RESURRECTED $TARGET ($after_total total copies now) — reproduces the live-VPS defect exactly, proving the harness models it correctly"
else
  fail "T2b: expected the un-tombstoned disable to be resurrected ($after_total copies; expected >=2) — the reproduction harness itself may be broken"
fi

# ---------------------------------------------------------------------------
# T3 — THE FIX: register -> disable -> TOMBSTONE -> update again -> NOT resurrected
# ---------------------------------------------------------------------------
echo ""
echo "--- T3: register -> disable -> tombstone -> update again -> NOT resurrected ---"
H3="$SANDBOX/home-t3"; bin3="$SANDBOX/bin-t3"; J3="$SANDBOX/jobs-t3.json"; C3="$SANDBOX/calls-t3.log"
_seed_re_state "$H3"; _mkbin "$bin3"
: > "$C3"; printf '[]' > "$J3"
HOME="$H3" PATH="$bin3:$PATH" FAKE_OC_JOBS_FILE="$J3" FAKE_OC_CALLS_FILE="$C3" \
  bash "$SKILL_COPY/39-real-estate-playbook/scripts/07-register-crons.sh" > "$SANDBOX/t3-run1.log" 2>&1
_mark_hidden "$J3" "$TARGET"
# Operator/fleet-cleanup tombstones it (durable, independent of --json visibility).
HOME="$H3" bash "$TOMBSTONE_SCRIPT" "$TARGET" "T3 test — simulated fleet-cleanup disable" > "$SANDBOX/t3-tombstone.log" 2>&1
tomb_rc=$?
[ "$tomb_rc" -eq 0 ] && pass "T3a: tombstone-cron.sh wrote the tombstone successfully" || fail "T3a: tombstone-cron.sh exited $tomb_rc"

# Run the updater AGAIN (simulates the next install.sh/update-skills.sh pass).
HOME="$H3" PATH="$bin3:$PATH" FAKE_OC_JOBS_FILE="$J3" FAKE_OC_CALLS_FILE="$C3" \
  bash "$SKILL_COPY/39-real-estate-playbook/scripts/07-register-crons.sh" > "$SANDBOX/t3-run2.log" 2>&1
# ...and once more for good measure (the fix must hold across N updates, not just one).
HOME="$H3" PATH="$bin3:$PATH" FAKE_OC_JOBS_FILE="$J3" FAKE_OC_CALLS_FILE="$C3" \
  bash "$SKILL_COPY/39-real-estate-playbook/scripts/07-register-crons.sh" > "$SANDBOX/t3-run3.log" 2>&1

total3=$(python3 -c "
import json
jobs=json.load(open('$J3'))
print(sum(1 for j in jobs if j.get('name')=='$TARGET'))
")
[ "$total3" -eq 1 ] && pass "T3b: with a tombstone in place, TWO further updater runs left exactly 1 copy of $TARGET (NOT resurrected)" \
                     || fail "T3b: $total3 copies of $TARGET exist after tombstoning + 2 more updater runs (expected 1 — the kill was undone)"
grep -qi "TOMBSTONED" "$SANDBOX/t3-run2.log" && pass "T3c: the registrar logged the TOMBSTONED skip explicitly" || fail "T3c: registrar did not log a TOMBSTONED skip message"

# ---------------------------------------------------------------------------
# MUTATION PROOF — strip the tombstone check from a copy of the registrar,
# prove the SAME T3 sequence now resurrects the job.
# ---------------------------------------------------------------------------
echo ""
echo "--- MUTATION PROOF: registrar without the tombstone check resurrects a disabled cron ---"
MUT_SCRIPT="$SKILL_COPY/39-real-estate-playbook/scripts/07-register-crons.sh"
# Remove ONLY the tombstone gate (3-line if-block); everything else (industry
# gate, oc_cron_present idempotency) is untouched, isolating this mutation to
# the exact mechanism under test.
python3 - "$MUT_SCRIPT" <<'PYEOF'
import re, sys
path = sys.argv[1]
src = open(path).read()
pattern = re.compile(
    r'  if oc_cron_tombstoned "\$name"; then\n'
    r'.*?\n'
    r'    continue\n'
    r'  fi\n',
    re.S,
)
new_src, n = pattern.subn('', src, count=1)
if n != 1:
    print("MUTATION_FAILED: tombstone-gate pattern not found (0 or >1 matches)", file=sys.stderr)
    sys.exit(1)
open(path, "w").write(new_src)
PYEOF
mut_ok=$?

if [ "$mut_ok" -ne 0 ]; then
  fail "MUT-T: could not apply the tombstone-removal mutation to the sandbox copy — cannot prove T3 is discriminating"
else
  Hm="$SANDBOX/home-mut"; binm="$SANDBOX/bin-mut"; Jm="$SANDBOX/jobs-mut.json"; Cm="$SANDBOX/calls-mut.log"
  _seed_re_state "$Hm"; _mkbin "$binm"
  : > "$Cm"; printf '[]' > "$Jm"
  HOME="$Hm" PATH="$binm:$PATH" FAKE_OC_JOBS_FILE="$Jm" FAKE_OC_CALLS_FILE="$Cm" \
    bash "$MUT_SCRIPT" > "$SANDBOX/mut-run1.log" 2>&1
  _mark_hidden "$Jm" "$TARGET"
  HOME="$Hm" bash "$TOMBSTONE_SCRIPT" "$TARGET" "mutation test" > "$SANDBOX/mut-tombstone.log" 2>&1
  HOME="$Hm" PATH="$binm:$PATH" FAKE_OC_JOBS_FILE="$Jm" FAKE_OC_CALLS_FILE="$Cm" \
    bash "$MUT_SCRIPT" > "$SANDBOX/mut-run2.log" 2>&1
  totalm=$(python3 -c "
import json
jobs=json.load(open('$Jm'))
print(sum(1 for j in jobs if j.get('name')=='$TARGET'))
")
  if [ "$totalm" -ge 2 ]; then
    pass "MUT-T: WITHOUT the tombstone check (mutated registrar), the SAME tombstone-then-update sequence resurrected $TARGET ($totalm copies) — proves T3b's ==1 assertion is a REAL, non-vacuous check of the tombstone wiring, not an incidental pass"
  else
    fail "MUT-T: even with the tombstone check removed, only $totalm copy(ies) resulted — the mutation harness itself is broken (cannot prove T3 is discriminating)"
  fi
fi

# ---------------------------------------------------------------------------
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo "FAIL: $FAIL check(s) failed — CI guard triggered"
  exit 1
fi
echo "PASS: all cron-tombstone-durability checks pass"
exit 0
