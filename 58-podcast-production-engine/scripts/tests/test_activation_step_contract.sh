#!/usr/bin/env bash
# =============================================================================
# PODCAST PRODUCTION ENGINE :: activation_step contract test
# -----------------------------------------------------------------------------
# The defect this locks down: provision-podcast-client.sh used to verify each
# activation helper by re-running it as "$helper --check <same install args>".
# Neither shipped helper has ever accepted --check; both reject an unknown flag
# with exit 2. Every provision therefore died at activation:department with exit
# 22 AFTER the install had already succeeded, and no box ever reached the fleet
# guarantee (provision => processor active).
#
# The test drives the REAL activation_step function, lifted out of the shipped
# provisioner, against fake helpers:
#
#   T1  a helper that REJECTS --check (like both real ones) but accepts --verify
#       PASSES the step. Under the old contract this case FAILED.
#   T2  a helper whose install succeeds but whose --verify read-back fails must
#       FAIL the step (no silent partial activation).
#   T3  a helper that is absent fails the step.
#   T4  a call with no -- separator is a mis-declaration and fails closed
#       (a step with no verify surface may never report a piece active).
#   T5  install args and verify args are delivered separately and verbatim.
#   T6  the shipped call sites pass a -- separator and a --verify read-back, and
#       the shipped provisioner no longer re-runs a helper with --check.
#   T7  the two REAL helpers reject --check and accept --verify, so the contract
#       the provisioner now relies on is the contract they actually implement.
#
# Hermetic: temp dir, fake helpers, no network, no box config, no secrets.
# =============================================================================
set -uo pipefail

SCRIPT_DIR_SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE_SCRIPTS="$(cd "$SCRIPT_DIR_SELF/.." && pwd)"
PROVISION="$ENGINE_SCRIPTS/provision-podcast-client.sh"

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); printf '  PASS  %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }

[ -f "$PROVISION" ] || { echo "FATAL: $PROVISION not found"; exit 2; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/activation-step-test.XXXXXX")" || exit 1
trap 'rm -rf "$WORK"' EXIT

# ---------------------------------------------------------------------------
# Lift the REAL activation_step out of the shipped provisioner. Testing a copy
# would prove nothing about what ships.
# ---------------------------------------------------------------------------
awk '/^activation_step\(\) \{/,/^\}$/' "$PROVISION" > "$WORK/activation_step.sh"
if [ ! -s "$WORK/activation_step.sh" ] || ! grep -q '^activation_step() {' "$WORK/activation_step.sh"; then
  echo "FATAL: could not lift activation_step() out of $PROVISION"
  exit 2
fi

# ---------------------------------------------------------------------------
# Harness: the stubs activation_step needs, plus a recorder so the test can see
# exactly which argv each helper invocation received.
# ---------------------------------------------------------------------------
cat > "$WORK/harness.sh" <<'HARNESS'
set -uo pipefail
LEDGER="$WORK/ledger.log"
log() { printf '%s\n' "$*" >&2; }
ledger_step() { printf 'STEP\t%s\t%s\t%s\n' "$1" "$2" "$3" >> "$LEDGER"; }
ledger_fact() { printf 'FACT\t%s\t%s\n' "$1" "$2" >> "$LEDGER"; }
ledger_finish() { :; }
die() { local code="$1"; shift; printf 'DIE\t%s\t%s\n' "$code" "$*" >> "$LEDGER"; exit "$code"; }
runas() { "$@"; }
HARNESS

# A fake helper that behaves exactly like the two real ones: it accepts
# --client-slug and --verify, and rejects any unknown flag (--check included)
# with exit 2. VERIFY_RESULT controls what its read-back reports.
make_helper() {
  local path="$1" verify_result="${2:-0}"
  cat > "$path" <<HELPER
#!/usr/bin/env bash
set -uo pipefail
printf 'ARGV\t%s\n' "\$*" >> "\$HELPER_LOG"
MODE=install
while [ \$# -gt 0 ]; do
  case "\$1" in
    --client-slug)   shift 2 ;;
    --prime-session) shift ;;
    --verify)        MODE=verify; shift ;;
    *) printf 'UNKNOWN_FLAG\t%s\n' "\$1" >> "\$HELPER_LOG"; exit 2 ;;
  esac
done
if [ "\$MODE" = "verify" ]; then exit $verify_result; fi
exit 0
HELPER
  chmod +x "$path"
}

run_step() { # run_step <helper-dir> <args...> ; prints rc
  local dir="$1"; shift
  ( export WORK
    SCRIPT_DIR="$dir"
    DRY_RUN="0"
    SLUG="acme-media"
    . "$WORK/harness.sh"
    . "$WORK/activation_step.sh"
    activation_step "activation:test" 22 "the fake piece" "helper.sh" "$@"
  ) >/dev/null 2>&1
  printf '%s' "$?"
}

# --- T1: a helper that rejects --check but accepts --verify PASSES ----------
echo "== T1 --verify read-back is the contract (the old --check was fiction) =="
D1="$WORK/t1"; mkdir -p "$D1"; make_helper "$D1/helper.sh" 0
: > "$WORK/ledger.log"; export HELPER_LOG="$WORK/t1.helper.log"; : > "$HELPER_LOG"
RC="$(run_step "$D1" --client-slug acme-media --prime-session -- --verify --client-slug acme-media)"
if [ "$RC" = "0" ]; then pass "T1: activation_step succeeds against a --verify helper"; else fail "T1: rc=$RC"; fi
if grep -q "UNKNOWN_FLAG" "$HELPER_LOG"; then
  fail "T1: activation_step still sends the helper a flag it rejects: $(grep UNKNOWN_FLAG "$HELPER_LOG" | head -1)"
else
  pass "T1: no rejected flag was ever sent to the helper"
fi
if grep -q $'ARGV\t--check' "$HELPER_LOG"; then fail "T1: --check was sent"; else pass "T1: --check was never sent"; fi

# --- T2: install OK but verify FAILS must fail the step --------------------
echo "== T2 a failing read-back fails the step (no silent partial activation) =="
D2="$WORK/t2"; mkdir -p "$D2"; make_helper "$D2/helper.sh" 1
: > "$WORK/ledger.log"; export HELPER_LOG="$WORK/t2.helper.log"; : > "$HELPER_LOG"
RC="$(run_step "$D2" --client-slug acme-media -- --verify --client-slug acme-media)"
if [ "$RC" = "22" ]; then pass "T2: a failing --verify aborts with the stage exit code"; else fail "T2: rc=$RC (expected 22)"; fi
if grep -q $'STEP\tactivation:test\tFAIL' "$WORK/ledger.log"; then pass "T2: the ledger records FAIL"; else fail "T2: no FAIL ledger row"; fi

# --- T3: absent helper fails the step --------------------------------------
echo "== T3 a missing helper fails closed =="
D3="$WORK/t3"; mkdir -p "$D3"
: > "$WORK/ledger.log"; export HELPER_LOG="$WORK/t3.helper.log"; : > "$HELPER_LOG"
RC="$(run_step "$D3" --client-slug acme-media -- --verify --client-slug acme-media)"
if [ "$RC" = "22" ]; then pass "T3: a missing helper aborts with the stage exit code"; else fail "T3: rc=$RC (expected 22)"; fi

# --- T4: no separator is a mis-declaration ---------------------------------
echo "== T4 a step declared with no verify surface fails closed =="
D4="$WORK/t4"; mkdir -p "$D4"; make_helper "$D4/helper.sh" 0
: > "$WORK/ledger.log"; export HELPER_LOG="$WORK/t4.helper.log"; : > "$HELPER_LOG"
RC="$(run_step "$D4" --client-slug acme-media)"
if [ "$RC" = "22" ]; then pass "T4: a missing -- separator aborts instead of claiming ACTIVE"; else fail "T4: rc=$RC (expected 22)"; fi

# --- T5: install args and verify args are delivered separately -------------
echo "== T5 install args and verify args are separate and verbatim =="
D5="$WORK/t5"; mkdir -p "$D5"; make_helper "$D5/helper.sh" 0
: > "$WORK/ledger.log"; export HELPER_LOG="$WORK/t5.helper.log"; : > "$HELPER_LOG"
RC="$(run_step "$D5" --client-slug acme-media --prime-session -- --verify --client-slug acme-media)"
FIRST="$(sed -n '1s/^ARGV\t//p' "$HELPER_LOG")"
SECOND="$(sed -n '2s/^ARGV\t//p' "$HELPER_LOG")"
if [ "$FIRST" = "--client-slug acme-media --prime-session" ]; then
  pass "T5: install invocation argv is exactly the install args"
else
  fail "T5: install argv was '$FIRST'"
fi
if [ "$SECOND" = "--verify --client-slug acme-media" ]; then
  pass "T5: verify invocation argv is exactly the verify args"
else
  fail "T5: verify argv was '$SECOND'"
fi

# --- T6: the shipped call sites honour the contract ------------------------
echo "== T6 the shipped provisioner declares a verify surface for every step =="
if grep -qE '\-\-check[[:space:]]+"\$@"' "$PROVISION"; then
  fail "T6: the provisioner still re-runs a helper with --check \"\$@\""
else
  pass "T6: no --check read-back survives in the provisioner"
fi
SITES="$(grep -c 'activation_step "activation:' "$PROVISION" || true)"
VERIFIED="$(grep -A2 'activation_step "activation:' "$PROVISION" | grep -c -- '-- --verify --client-slug' || true)"
if [ "${SITES:-0}" -ge 1 ] && [ "${VERIFIED:-0}" = "${SITES:-0}" ]; then
  pass "T6: all $SITES generic activation call sites pass -- --verify --client-slug"
else
  fail "T6: $SITES call site(s), $VERIFIED with a -- --verify read-back"
fi
# Department install/readiness intentionally straddles hook registration: the
# registrar creates the namespace the department's verify needs. It cannot use
# one generic run-then-verify helper call without verifying too early.
if grep -q 'install-podcast-department.sh" --client-slug "\$SLUG" --prime-session' "$PROVISION" \
  && grep -q 'install-podcast-department.sh" --verify --client-slug "\$SLUG"' "$PROVISION"; then
  pass "T6: the department install and post-hook read-back both carry --client-slug"
else
  fail "T6: the department step lacks its install or post-hook --verify invocation"
fi

# --- T7: the REAL helpers implement the contract ---------------------------
echo "== T7 the real helpers reject --check and accept --verify =="
for h in install-podcast-department.sh register-podcast-hook.sh; do
  HP="$ENGINE_SCRIPTS/$h"
  if [ ! -f "$HP" ]; then fail "T7: $h not present"; continue; fi
  if grep -qE '^\s+--check\)' "$HP"; then
    fail "T7: $h claims to accept --check (the contract said it did; it never has)"
  else
    pass "T7: $h has no --check arm (so the old read-back could only ever exit 2)"
  fi
  if grep -qE '^\s+--verify\)' "$HP"; then
    pass "T7: $h implements --verify"
  else
    fail "T7: $h has no --verify arm; the provisioner's read-back would abort"
  fi
done

echo ""
echo "activation_step contract: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
