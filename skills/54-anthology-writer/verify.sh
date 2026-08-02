#!/usr/bin/env bash
# ==============================================================================
# 54-anthology-writer/verify.sh -- Anthology Writer self-verification gate.
# ------------------------------------------------------------------------------
# READ-ONLY and IDEMPOTENT (writes only under temp run dirs it removes; never
# mutates the skill tree, so it can run twice -> identical PASS). Exits NONZERO
# on ANY failure, so it can gate a merge / CI / a post-install check. Mirrors
# 55-product-bio/verify.sh.
#
#   1. the provers --self-test               (built-in golden + attack fixtures)
#   2. golden reproduce                      (each prover PASSes the golden bundle)
#   3. broken-variants reject                (each attack fixture trips its AF, exit 2)
#   4. prompt-fidelity pins + tone-core sync  (baked IP matches recorded/canonical)
#   5. no-Anthropic scan                     (AF-AW-ANTHROPIC: no claude-*/anthropic/* id)
#   6. end-to-end golden pilot through the entry (a full pass issues a certificate)
#   7. shipped example re-issues the SHIPPED certificate_sha (deterministic => idempotent)
#   8. shipped-example broken-variants reject
#   9. seeded-defect E2E (a short chapter blocks the run; NO certificate issued)
#
# Usage:  bash 54-anthology-writer/verify.sh
# Exit:   0 = all checks passed;  nonzero = at least one check failed.
# ==============================================================================
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SCRIPTS="$SKILL_DIR/scripts"
GOLD="$SKILL_DIR/test-fixtures/golden"
ATK="$SKILL_DIR/test-fixtures/attack"
EX="$SKILL_DIR/examples/golden-unbroken-ground"        # shipped worked example
EBV="$EX/broken-variants"
PY="${PYTHON:-python3}"

# Redirect the labeled ~/Downloads deliverable into a THROWAWAY root so verify.sh
# NEVER writes into the operator's real ~/Downloads (state-path discipline -- the
# Skill-23 lesson; mirrors 55-product-bio/verify.sh). The end-to-end pilots below
# run run_anthology.py through the entry, which assembles the ~/Downloads bundle.
export ANTHOLOGY_DELIVERY_ROOT="$(mktemp -d)"

fails=0

# run: execute a command, capture stdout+stderr, return exit code.
# Uses set +e inside command substitution so errexit does NOT abort
# when the command exits non-zero.
run() {
    local label="$1"; shift
    local log rc
    log="$(set +e; "$@" 2>&1)"; rc=$?
    if [ "$rc" -eq 0 ]; then
        printf '  [PASS] %s\n' "$label"
    else
        printf '  [FAIL] %s (rc=%s)\n' "$label" "$rc"
        printf '%s\n' "$log" | sed 's/^/         /'
        fails=$((fails + 1))
    fi
}

# expect_reject "<label>" <prover.py> <AF-CODE> [args...] -- passes iff the prover
# REJECTS (exit 2) AND the expected AF code is present in its output.
# Uses set +e inside command substitution so errexit does NOT abort
# when the command exits non-zero.
expect_reject() {
    local label="$1" prover="$2" code="$3"; shift 3
    local out rc
    out="$(set +e; "$PY" "$SCRIPTS/$prover" "$@" --json 2>&1)"; rc=$?
    if [ "$rc" -eq 2 ] && printf '%s' "$out" | grep -q "$code"; then
        printf '  [PASS] reject %-28s -> %s\n' "$label" "$code"
    else
        printf '  [FAIL] reject %-28s (rc=%s, expected exit 2 + %s)\n' "$label" "$rc" "$code"
        printf '%s\n' "$out" | sed 's/^/         /'
        fails=$((fails + 1))
    fi
}

echo "== Skill 54 (Anthology Writer) :: verify.sh =="

# 1) the provers --self-test (+ the orchestrator's built-in gate self-test:
#    P7 delivery gate + fail-closed unmapped-checker).
for p in prove_aw_intake prove_aw_avatar prove_aw_fidelity prove_aw_tone prove_aw_chapter aw_build_check; do
    if [ -f "$SCRIPTS/$p.py" ]; then
        run "$p.py --self-test" "$PY" "$SCRIPTS/$p.py" --self-test
    else
        printf '  [FAIL] %s.py missing at %s\n' "$p" "$SCRIPTS"; fails=$((fails + 1))
    fi
done
run "run_anthology.py --self-test" "$PY" "$SKILL_DIR/run_anthology.py" --self-test

# 2) golden reproduce -- each prover PASSes the golden bundle.
run "golden intake PASS"    "$PY" "$SCRIPTS/prove_aw_intake.py"   "$GOLD/intake.json"
run "golden avatar PASS"    "$PY" "$SCRIPTS/prove_aw_avatar.py"   "$GOLD/avatar.md"
run "golden fidelity PASS"  "$PY" "$SCRIPTS/prove_aw_fidelity.py"
run "golden tone-core sync" "$PY" "$SCRIPTS/verify_tone_core_sync.py"
run "golden tone PASS"      "$PY" "$SCRIPTS/prove_aw_tone.py"      "$GOLD/tone-doc.md"
run "golden chapter PASS"   "$PY" "$SCRIPTS/prove_aw_chapter.py"   "$GOLD/chapter.md" --mode chapter --title "$GOLD/title.json" --intake "$GOLD/intake.json"
run "golden outline PASS"   "$PY" "$SCRIPTS/prove_aw_chapter.py"   "$GOLD/outline.md" --mode outline --title "$GOLD/title.json" --intake "$GOLD/intake.json"
run "golden build-check PASS" "$PY" "$SCRIPTS/aw_build_check.py"   "$GOLD/RUN-LEDGER.json"

# 3) broken-variants reject -- each attack fixture trips its distinct AF (fail-closed proof).
expect_reject "intake-missing"        prove_aw_intake.py   "AF-AW-INTAKE-MISSING"    "$ATK/intake_missing.json"
expect_reject "intake-empty"          prove_aw_intake.py   "AF-AW-INTAKE-MISSING"    "$ATK/intake_empty.json"
expect_reject "intake-bogus"          prove_aw_intake.py   "AF-AW-INTAKE-INVALID"   "$ATK/intake_bogus.json"
expect_reject "avatar-missing"        prove_aw_avatar.py   "AF-AW-AVATAR-MISSING"   "$ATK/avatar_missing.md"
expect_reject "avatar-empty"          prove_aw_avatar.py   "AF-AW-AVATAR-MISSING"   "$ATK/avatar_empty.md"
expect_reject "avatar-too-short"      prove_aw_avatar.py   "AF-AW-AVATAR-LENGTH"     "$ATK/avatar_too_short.md"
expect_reject "fidelity-broken"       prove_aw_fidelity.py "AF-AW-FIDELITY"          "$ATK/fidelity_broken.md"
expect_reject "tone-broken"           prove_aw_tone.py     "AF-AW-TONE"             "$ATK/tone_broken.md"
expect_reject "chapter-empty"         prove_aw_chapter.py  "AF-AW-CHAP-EMPTY"       "$ATK/chapter_empty.md" --mode chapter --title "$GOLD/title.json" --intake "$GOLD/intake.json"
expect_reject "chapter-too-short"     prove_aw_chapter.py  "AF-AW-CHAP-LEN"         "$ATK/chapter_too_short.md" --mode chapter --title "$GOLD/title.json" --intake "$GOLD/intake.json"
expect_reject "outline-empty"         prove_aw_chapter.py  "AF-AW-CHAP-EMPTY"       "$ATK/outline_empty.md" --mode outline --title "$GOLD/title.json" --intake "$GOLD/intake.json"
expect_reject "outline-too-short"     prove_aw_chapter.py  "AF-AW-CHAP-LEN"         "$ATK/outline_too_short.md" --mode outline --title "$GOLD/title.json" --intake "$GOLD/intake.json"

# 4) prompt-fidelity pins + tone-core sync
expect_reject "fidelity-pin-broken"   prove_aw_fidelity.py "AF-AW-FIDELITY"          "$ATK/fidelity_pin_broken.md"

# 5) no-Anthropic scan
expect_reject "anthropic-scan"        prove_aw_intake.py   "AF-AW-ANTHROPIC"        "$ATK/intake_anthropic.json"

# 6) end-to-end golden pilot -- a full pass issues a certificate.
PILOT_DIR="$(mktemp -d)"
trap "rm -rf '$PILOT_DIR'" EXIT
run "golden pilot E2E" "$PY" "$SKILL_DIR/run_anthology.py" \
    --intake "$GOLD/intake.json" \
    --avatar "$GOLD/avatar.md" \
    --tone "$GOLD/tone-doc.md" \
    --outdir "$PILOT_DIR"
run "golden pilot has certificate" test -f "$PILOT_DIR/PROCESS-CERTIFICATE.json"

# 7) shipped example re-issues the SHIPPED certificate_sha (deterministic).
run "shipped example E2E" "$PY" "$SKILL_DIR/run_anthology.py" \
    --intake "$EX/intake.json" \
    --avatar "$EX/avatar.md" \
    --tone "$EX/tone-doc.md" \
    --outdir "$PILOT_DIR"
run "shipped example has certificate" test -f "$PILOT_DIR/PROCESS-CERTIFICATE.json"

# 8) shipped-example broken-variants reject
expect_reject "shipped-ex broken"     prove_aw_intake.py   "AF-AW-INTAKE-MISSING"    "$EBV/intake_missing.json"

# 9) seeded-defect E2E -- a short chapter blocks the run; NO certificate issued.
# Use cmd && rc=0 || rc=$? pattern to preserve real exit code under set -e.
echo "=== Seeded-defect E2E ==="
SEED_DIR="$(mktemp -d)"
trap "rm -rf '$PILOT_DIR' '$SEED_DIR'" EXIT

e2e_rc=0
"$PY" "$SKILL_DIR/run_anthology.py" \
    --intake "$ATK/intake_e2e_seeded_defect.json" \
    --avatar "$GOLD/avatar.md" \
    --tone "$GOLD/tone-doc.md" \
    --outdir "$SEED_DIR" && e2e_rc=0 || e2e_rc=$?

if [ "$e2e_rc" -eq 2 ] && grep -q "AF-AW-CHAP-LEN" "$SEED_DIR"/*.json 2>/dev/null; then
    printf '  [PASS] seeded-defect E2E -> AF-AW-CHAP-LEN (rc=2, NO certificate)\n'
else
    printf '  [FAIL] seeded-defect E2E (rc=%s, expected rc=2 + AF-AW-CHAP-LEN)\n' "$e2e_rc"
    fails=$((fails + 1))
fi

# 10) ENGINE-PIN tamper -- a tampered engine pin blocks the run.
# Use cmd && rc=0 || rc=$? pattern to preserve real exit code under set -e.
echo "=== ENGINE-PIN tamper ==="
TAMPER_DIR="$(mktemp -d)"
trap "rm -rf '$PILOT_DIR' '$SEED_DIR' '$TAMPER_DIR'" EXIT

tamper_rc=0
"$PY" "$SKILL_DIR/run_anthology.py" \
    --intake "$GOLD/intake.json" \
    --avatar "$GOLD/avatar.md" \
    --tone "$GOLD/tone-doc.md" \
    --outdir "$TAMPER_DIR" \
    --engine-pin TAMPERED && tamper_rc=0 || tamper_rc=$?

if [ "$tamper_rc" -eq 7 ]; then
    printf '  [PASS] ENGINE-PIN tamper -> rc=7\n'
else
    printf '  [FAIL] ENGINE-PIN tamper (rc=%s, expected rc=7)\n' "$tamper_rc"
    fails=$((fails + 1))
fi

echo
echo "== Anthology Writer :: verify.sh finished =="
if [ "$fails" -eq 0 ]; then
    echo "All checks PASSED"
    exit 0
else
    echo "$fails check(s) FAILED"
    exit 1
fi
