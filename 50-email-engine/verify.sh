#!/usr/bin/env bash
# ==============================================================================
# 50-email-engine/verify.sh — Email Engine self-verification gate.
# ------------------------------------------------------------------------------
# READ-ONLY and IDEMPOTENT (writes nothing outside a temp built-index it removes).
# Runs the skill's fail-closed checks and exits NONZERO on ANY failure, so it can
# gate a merge / CI / a post-install check. Mirrors 51-signature-presentation/verify.sh.
#
#   1. prove-email.py --self-test          (built-in VALID + VIOLATION fixtures)
#   1b. test_department_routing.py         (AST static: board card routes to the REAL
#                                           primary department "marketing", never "email")
#   2. email_matcher_cli.py --selftest     (route corpus examples to their entry)
#   3. emit_build_plan.py --selftest       (DRAFT-ONLY build-plan emitter)
#   4. email-library/register.py --check   (paired files + built index + coverage)
#   5. golden reproduce                    (prove-email PASS on the golden brief + emails)
#   5b. golden certificate authenticates   (T0-64: the SHIPPED reference artifact is put
#                                           through the deploy-time contract — all phases
#                                           pass + certificate_sha recomputes + HMAC
#                                           signature verifies. It previously carried no
#                                           signature at all, would have been rejected by
#                                           the skill's own verifier, and nothing checked)
#   5c. brief usage failures               (T0-63: a supplied-but-unreadable --brief is a
#                                           USAGE failure, never a silent PASS)
#   6. broken-variants reject              (each trips its distinct AF, exit 2)
#
# Usage:  bash 50-email-engine/verify.sh
# Exit:   0 = all checks passed;  nonzero = at least one check failed.
# ==============================================================================
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
TOOLS="$SKILL_DIR/tools"
LIB="$SKILL_DIR/email-library"
GOLDEN="$SKILL_DIR/examples/golden-landing-10"
PY="${PYTHON:-python3}"

fails=0
run() {
    local label="$1"; shift
    local log rc
    log="$("$@" 2>&1)"; rc=$?
    if [ "$rc" -eq 0 ]; then
        printf '  [PASS] %s\n' "$label"
    else
        printf '  [FAIL] %s (rc=%s)\n' "$label" "$rc"
        printf '%s\n' "$log" | sed 's/^/         /'
        fails=$((fails + 1))
    fi
}

# expect_reject "<label>" <file> <kind> <AF-CODE> — passes iff the prover REJECTS
# (exit 2) AND the expected AF code is present.
expect_reject() {
    local label="$1" file="$2" kind="$3" code="$4"
    local out rc
    out="$("$PY" "$TOOLS/prove-email.py" "$file" --kind "$kind" --json 2>&1)"; rc=$?
    if [ "$rc" -eq 2 ] && printf '%s' "$out" | grep -q "$code"; then
        printf '  [PASS] reject %-20s -> %s\n' "$label" "$code"
    else
        printf '  [FAIL] reject %-20s (rc=%s, expected exit 2 + %s)\n' "$label" "$rc" "$code"
        fails=$((fails + 1))
    fi
}

echo "== Skill 50 (Email Engine) :: verify.sh =="

run "prove-email.py --self-test"        "$PY" "$TOOLS/prove-email.py" --self-test
run "run_email_engine.py --self-test"   "$PY" "$SKILL_DIR/run_email_engine.py" --self-test
run "test_department_routing.py"        "$PY" "$SKILL_DIR/test_department_routing.py"
run "test_intake_contract_authority.py" "$PY" "$SKILL_DIR/test_intake_contract_authority.py"
run "email_matcher_cli.py --selftest"   "$PY" "$TOOLS/email_matcher_cli.py" --selftest
run "emit_build_plan.py --selftest"     "$PY" "$TOOLS/emit_build_plan.py" --selftest
run "email-library/register.py --check" "$PY" "$LIB/register.py" --check

# 5) golden reproduce — the brief + the 10-email ledger both PASS.
run "golden brief PASS"  "$PY" "$TOOLS/prove-email.py" "$GOLDEN/brief.json" --kind intake
run "golden emails PASS" "$PY" "$TOOLS/prove-email.py" "$GOLDEN/emails.json" --kind sequence

# 5b) T0-64 — the SHIPPED reference certificate must satisfy the same contract the
# deploy gate applies. This is the check whose absence let an unsigned artifact ship.
run "golden certificate authenticates" \
    "$PY" "$SKILL_DIR/run_email_engine.py" --verify-certificate "$GOLDEN"

# expect_usage "<label>" <args...> — passes iff the prover returns the USAGE exit
# code (3) AND says USAGE. A silent PASS here is the T0-63 defect.
expect_usage() {
    local label="$1"; shift
    local out rc
    out="$("$PY" "$TOOLS/prove-email.py" "$@" 2>&1)"; rc=$?
    if [ "$rc" -eq 3 ] && printf '%s' "$out" | grep -q 'USAGE'; then
        printf '  [PASS] usage  %s\n' "$label"
    else
        printf '  [FAIL] usage  %s (rc=%s, expected exit 3 + a USAGE failure)\n' "$label" "$rc"
        printf '%s\n' "$out" | sed 's/^/         /'
        fails=$((fails + 1))
    fi
}

# 5c) T0-63 — a SUPPLIED brief that cannot be read or parsed is a usage failure,
# not the same silent `None` as "no brief was supplied".
BRIEF_TMP="$(mktemp "${TMPDIR:-/tmp}/email-verify-brief.XXXXXX")"
printf '{ this is not json' > "$BRIEF_TMP"
expect_usage "missing --brief path"    "$GOLDEN/emails.json" --kind sequence --brief "$GOLDEN/no-such-brief.json"
expect_usage "unparseable --brief"     "$GOLDEN/emails.json" --kind sequence --brief "$BRIEF_TMP"
rm -f "$BRIEF_TMP"
# ANTI-FALSE-FAIL CONTROL: a readable brief is unaffected.
run "readable --brief still PASSES" \
    "$PY" "$TOOLS/prove-email.py" "$GOLDEN/emails.json" --kind sequence --brief "$GOLDEN/brief.json"

# 6) broken-variants reject — each trips its distinct AF (fail-closed proof).
BV="$GOLDEN/broken-variants"
expect_reject "wrong-length"         "$BV/wrong_length/emails.json"          sequence "AF-EMAIL-SEQUENCE-LENGTH"
expect_reject "framework-incomplete" "$BV/framework_incomplete/email.json"   email    "AF-EMAIL-FRAMEWORK-INCOMPLETE"
expect_reject "persona-named"        "$BV/persona_named/email.json"          email    "AF-EMAIL-PERSONA-NAMED"
expect_reject "missing-subject"      "$BV/missing_subject/email.json"        email    "AF-EMAIL-SUBJECT-COUNT"
expect_reject "unapproved-deploy"    "$BV/unapproved_deploy/emails.json"     sequence "AF-PROCESS-INTEGRITY"

echo "=================================================="
if [ "$fails" -eq 0 ]; then
    echo "RESULT: PASS — all Skill 50 self-verification checks green."
    exit 0
fi
echo "RESULT: FAIL — $fails check(s) failed."
exit 1
