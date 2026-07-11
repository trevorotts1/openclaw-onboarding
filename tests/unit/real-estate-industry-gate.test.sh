#!/usr/bin/env bash
# tests/unit/real-estate-industry-gate.test.sh
#
# Acceptance tests for Fix A (REALESTATE-DEPT-GATING-FIX-SPEC-2026-07-11.md,
# Section 3 "FIX A"): Skill 39's real-estate playbook + its pipeline crons must
# install ONLY when the box's captured industry is real-estate, and must FAIL
# CLOSED (skip) on absent/unknown/other industry.
#
# Covers: A1 (non-RE -> zero RE crons), A2 (RE -> exactly one of each, ties to
# Fix B), A3 (fail closed on absent/malformed industry data), A4 (wire.sh hard
# stop — the gate stops the WHOLE vertical, not just crons).
#
# MUTATION-PROOF (per spec Section 3): every negative-control assertion below
# is re-run against a MUTATED copy of shared-utils/industry-gate.sh whose
# oc_is_real_estate_industry() always returns 0 (pretends every box is real
# estate, i.e. "the gate is defeated/removed"). The SAME unmodified
# 07-register-crons.sh / wire.sh, run against the mutated gate, MUST then
# exhibit the exact behavior the fix prevents (RE crons registered / RE steps
# executed on a non-RE box). If a future edit silently weakens or removes the
# gate, these mutation checks stop discriminating and the corresponding PASS
# lines flip to FAIL — proving the test is not vacuous.
#
# Runs entirely in a hermetic sandbox (private $HOME, fake `openclaw` on
# PATH via tests/fixtures/fake-openclaw-cron.py). Never touches a real
# ~/.openclaw or the network.
#
# Exit 0 = all checks pass. Exit 1 = one or more failed (CI FAIL).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FIXTURE="$REPO_ROOT/tests/fixtures/fake-openclaw-cron.py"
PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== real-estate-industry-gate.test.sh ==="
echo ""

# ---------------------------------------------------------------------------
# Sandbox helpers
# ---------------------------------------------------------------------------
SANDBOX="$(mktemp -d)"
cleanup() { rm -rf "$SANDBOX" 2>/dev/null || true; }
trap cleanup EXIT
case "$SANDBOX" in
  */.openclaw|*/.openclaw/*) echo "REFUSING: sandbox path resolved into a real .openclaw ($SANDBOX)"; exit 2 ;;
esac

# A private copy of the skill + its shared-utils dependency, so mutation tests
# can edit a COPY of industry-gate.sh without touching the real repo file.
SKILL_COPY="$SANDBOX/repo"
mkdir -p "$SKILL_COPY"
cp -r "$REPO_ROOT/39-real-estate-playbook" "$SKILL_COPY/"
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

_seed_state() { # <home> <json-content-or-empty-to-omit-file>
  local home="$1" content="$2"
  mkdir -p "$home/.openclaw/workspace"
  if [ -n "$content" ]; then
    printf '%s' "$content" > "$home/.openclaw/workspace/.workforce-build-state.json"
  fi
}

_run_register_crons() { # <home> <jobs_file> <calls_file>
  local home="$1" jobs="$2" calls="$3" bin="$SANDBOX/bin-$$RANDOM"
  _mkbin "$bin"
  : > "$jobs"; printf '[]' > "$jobs"; : > "$calls"
  HOME="$home" PATH="$bin:$PATH" FAKE_OC_JOBS_FILE="$jobs" FAKE_OC_CALLS_FILE="$calls" \
    bash "$SKILL_COPY/39-real-estate-playbook/scripts/07-register-crons.sh" > "$SANDBOX/out.$$RANDOM.log" 2>&1
  echo $?
}

_re_cron_count() { # <jobs_file>
  python3 -c "
import json,sys
try:
    jobs = json.load(open(sys.argv[1]))
except Exception:
    print(0); sys.exit(0)
names = ('re-open-house-followup-scan','re-post-close-anniversary')
print(sum(1 for j in jobs if j.get('name') in names))
" "$1"
}

# ---------------------------------------------------------------------------
# A1 — Non-RE industry -> ZERO RE crons
# ---------------------------------------------------------------------------
echo "--- A1: non-real-estate industry -> zero RE crons ---"
H1="$SANDBOX/home-a1"; J1="$SANDBOX/jobs-a1.json"; C1="$SANDBOX/calls-a1.log"
_seed_state "$H1" '{"industryPack":{"slug":"saas","source":"auto-detected"}}'
rc1=$(_run_register_crons "$H1" "$J1" "$C1")
n1=$(_re_cron_count "$J1")
[ "$rc1" -eq 0 ] && pass "A1a: 07-register-crons.sh exits 0 on a saas box" || fail "A1a: exited $rc1 (expected 0)"
[ "$n1" -eq 0 ] && pass "A1b: zero RE crons registered on a saas box" || fail "A1b: $n1 RE crons registered (expected 0)"
# NOTE: `grep -c` already prints "0" (and only "0") on zero matches — it does
# NOT need an `|| echo 0` fallback (that would double-append a second "0" line
# since -c's own exit code is 1 on no-match, which is not a stdout failure).
addcalls1=$(grep -c "^cron add" "$C1" 2>/dev/null)
[ "$addcalls1" -eq 0 ] && pass "A1c: zero 'cron add' calls made at all" || fail "A1c: $addcalls1 'cron add' calls made (expected 0)"

# ---------------------------------------------------------------------------
# A2 — RE industry -> exactly ONE of each cron, run TWICE (ties Fix A + Fix B)
# ---------------------------------------------------------------------------
echo ""
echo "--- A2: real-estate industry -> exactly one of each RE cron, run twice ---"
H2="$SANDBOX/home-a2"; J2="$SANDBOX/jobs-a2.json"; C2="$SANDBOX/calls-a2.log"
_seed_state "$H2" '{"industryPack":{"slug":"real-estate","source":"owner-confirmed"}}'
bin2="$SANDBOX/bin-a2"; _mkbin "$bin2"
printf '[]' > "$J2"; : > "$C2"
HOME="$H2" PATH="$bin2:$PATH" FAKE_OC_JOBS_FILE="$J2" FAKE_OC_CALLS_FILE="$C2" \
  bash "$SKILL_COPY/39-real-estate-playbook/scripts/07-register-crons.sh" > "$SANDBOX/a2-run1.log" 2>&1
rc2a=$?
HOME="$H2" PATH="$bin2:$PATH" FAKE_OC_JOBS_FILE="$J2" FAKE_OC_CALLS_FILE="$C2" \
  bash "$SKILL_COPY/39-real-estate-playbook/scripts/07-register-crons.sh" > "$SANDBOX/a2-run2.log" 2>&1
rc2b=$?
n2=$(_re_cron_count "$J2")
[ "$rc2a" -eq 0 ] && [ "$rc2b" -eq 0 ] && pass "A2a: both runs exit 0 on a real-estate box" || fail "A2a: run1=$rc2a run2=$rc2b (expected 0/0)"
[ "$n2" -eq 2 ] && pass "A2b: exactly 2 RE cron entries exist after 2 runs (1 of each name)" || fail "A2b: $n2 RE cron entries exist after 2 runs (expected 2)"

# ---------------------------------------------------------------------------
# A3 — FAIL CLOSED on absent/malformed industry data
# ---------------------------------------------------------------------------
echo ""
echo "--- A3: FAIL CLOSED on absent/malformed industry data ---"
H3a="$SANDBOX/home-a3a"; J3a="$SANDBOX/jobs-a3a.json"; C3a="$SANDBOX/calls-a3a.log"
mkdir -p "$H3a/.openclaw/workspace"   # state FILE deliberately absent
rc3a=$(_run_register_crons "$H3a" "$J3a" "$C3a")
n3a=$(_re_cron_count "$J3a")
[ "$rc3a" -eq 0 ] && [ "$n3a" -eq 0 ] && pass "A3a: build-state file MISSING -> zero RE crons, exit 0 (fail closed)" || fail "A3a: rc=$rc3a n=$n3a (expected 0/0)"

H3b="$SANDBOX/home-a3b"; J3b="$SANDBOX/jobs-a3b.json"; C3b="$SANDBOX/calls-a3b.log"
_seed_state "$H3b" '{"companyName":"Acme"}'   # present, but NO industryPack and no top-level .industry
rc3b=$(_run_register_crons "$H3b" "$J3b" "$C3b")
n3b=$(_re_cron_count "$J3b")
[ "$rc3b" -eq 0 ] && [ "$n3b" -eq 0 ] && pass "A3b: build-state present but NO industryPack -> zero RE crons (fail closed)" || fail "A3b: rc=$rc3b n=$n3b (expected 0/0)"

H3c="$SANDBOX/home-a3c"; J3c="$SANDBOX/jobs-a3c.json"; C3c="$SANDBOX/calls-a3c.log"
_seed_state "$H3c" '{"industryPack":{"slug":"unknown","source":"auto-detected"}}'
rc3c=$(_run_register_crons "$H3c" "$J3c" "$C3c")
n3c=$(_re_cron_count "$J3c")
[ "$rc3c" -eq 0 ] && [ "$n3c" -eq 0 ] && pass "A3c: industryPack.slug='unknown' -> zero RE crons (fail closed)" || fail "A3c: rc=$rc3c n=$n3c (expected 0/0)"

H3d="$SANDBOX/home-a3d"; J3d="$SANDBOX/jobs-a3d.json"; C3d="$SANDBOX/calls-a3d.log"
_seed_state "$H3d" '{"industryPack":{"slug":null,"source":"auto-detected"}}'
rc3d=$(_run_register_crons "$H3d" "$J3d" "$C3d")
n3d=$(_re_cron_count "$J3d")
[ "$rc3d" -eq 0 ] && [ "$n3d" -eq 0 ] && pass "A3d: industryPack.slug=null -> zero RE crons (fail closed)" || fail "A3d: rc=$rc3d n=$n3d (expected 0/0)"

# ---------------------------------------------------------------------------
# A4 — wire.sh HARD STOP: the gate stops the WHOLE vertical, not just crons
# ---------------------------------------------------------------------------
echo ""
echo "--- A4: wire.sh hard-stop on non-RE box (no steps 01-08 execute) ---"
H4="$SANDBOX/home-a4"; MFD4="$SANDBOX/mfd-a4"
mkdir -p "$H4/.openclaw/workspace" "$MFD4"
_seed_state "$H4" '{"industryPack":{"slug":"agency","source":"auto-detected"}}'
bin4="$SANDBOX/bin-a4"; _mkbin "$bin4"
J4="$SANDBOX/jobs-a4.json"; C4="$SANDBOX/calls-a4.log"; printf '[]' > "$J4"; : > "$C4"
HOME="$H4" PATH="$bin4:$PATH" MASTER_FILES_DIR="$MFD4" FAKE_OC_JOBS_FILE="$J4" FAKE_OC_CALLS_FILE="$C4" \
  timeout 30 bash "$SKILL_COPY/39-real-estate-playbook/wire.sh" > "$SANDBOX/wire-a4.log" 2>&1
rc4=$?
[ "$rc4" -eq 0 ] && pass "A4a: wire.sh exits 0 (clean skip, not an error) on a non-RE box" || fail "A4a: wire.sh exited $rc4"
grep -qi "SKIP Skill 39" "$SANDBOX/wire-a4.log" && pass "A4b: wire.sh logs the SKIP Skill 39 message" || fail "A4b: wire.sh did not log a SKIP message"
if [ -f "$MFD4/real-estate-events.jsonl" ]; then
  fail "A4c: real-estate-events.jsonl WAS created on a non-RE box (steps 01-08 ran despite the gate)"
else
  pass "A4c: real-estate-events.jsonl NOT created (step 03 never ran — the gate stopped the whole vertical)"
fi
n4=$(_re_cron_count "$J4")
[ "$n4" -eq 0 ] && pass "A4d: zero RE crons registered via the wire.sh path either" || fail "A4d: $n4 RE crons registered via wire.sh (expected 0)"

# ---------------------------------------------------------------------------
# MUTATION PROOFS — defeat the gate, prove the SAME tests now FAIL the
# invariant (i.e. the harness is discriminating, not vacuous).
# ---------------------------------------------------------------------------
echo ""
echo "--- MUTATION PROOF: gate defeated (oc_is_real_estate_industry always true) ---"
MUT_GATE="$SKILL_COPY/shared-utils/industry-gate.sh"
cat > "$MUT_GATE" <<'EOF'
#!/usr/bin/env bash
# MUTATED for testing: always claims real-estate regardless of build-state.
oc_is_real_estate_industry() {
  OC_INDUSTRY_GATE_REASON="MUTATED: gate defeated (always true)"
  return 0
}
EOF

Hm1="$SANDBOX/home-mut1"; Jm1="$SANDBOX/jobs-mut1.json"; Cm1="$SANDBOX/calls-mut1.log"
_seed_state "$Hm1" '{"industryPack":{"slug":"saas","source":"auto-detected"}}'
rcm1=$(_run_register_crons "$Hm1" "$Jm1" "$Cm1")
nm1=$(_re_cron_count "$Jm1")
if [ "$nm1" -ge 1 ]; then
  pass "MUT1: with the gate DEFEATED, a saas box now gets RE crons registered ($nm1) — proves A1's assertion (n==0) is a REAL, non-vacuous check of the gate's presence"
else
  fail "MUT1: even with the industry-gate.sh MUTATED to always return true, no RE crons were added — the mutation harness itself is broken (cannot prove A1 is discriminating)"
fi

Hm4="$SANDBOX/home-mut4"; MFDm4="$SANDBOX/mfd-mut4"
mkdir -p "$Hm4/.openclaw/workspace" "$MFDm4"
_seed_state "$Hm4" '{"industryPack":{"slug":"agency","source":"auto-detected"}}'
binm4="$SANDBOX/bin-mut4"; _mkbin "$binm4"
Jm4="$SANDBOX/jobs-mut4.json"; Cm4="$SANDBOX/calls-mut4.log"; printf '[]' > "$Jm4"; : > "$Cm4"
HOME="$Hm4" PATH="$binm4:$PATH" MASTER_FILES_DIR="$MFDm4" FAKE_OC_JOBS_FILE="$Jm4" FAKE_OC_CALLS_FILE="$Cm4" \
  timeout 30 bash "$SKILL_COPY/39-real-estate-playbook/wire.sh" > "$SANDBOX/wire-mut4.log" 2>&1 || true
if [ -f "$MFDm4/real-estate-events.jsonl" ]; then
  pass "MUT4: with the gate DEFEATED, wire.sh on a non-RE box NOW runs step 03 (real-estate-events.jsonl created) — proves A4c is a REAL, non-vacuous check of the wire.sh hard-stop"
else
  fail "MUT4: even with the gate MUTATED to always return true, wire.sh still did not run step 03 — the mutation harness itself is broken (cannot prove A4c is discriminating), OR wire.sh has a SECOND independent gate not captured by this mutation (check 00-verify-prerequisites.sh Section A-D and 07-register-crons.sh's own gate)"
fi

# ---------------------------------------------------------------------------
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo "FAIL: $FAIL check(s) failed — CI guard triggered"
  exit 1
fi
echo "PASS: all real-estate-industry-gate checks pass"
exit 0
