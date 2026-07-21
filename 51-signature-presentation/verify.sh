#!/usr/bin/env bash
# ==============================================================================
# verify.sh — Skill 51 (Signature Presentation) self-verification gate.
# ------------------------------------------------------------------------------
# READ-ONLY and IDEMPOTENT. Runs the skill's three fail-closed provers in
# --self-test mode (built-in VALID + VIOLATION fixtures) AND the library-register
# --check sanity (both SP roles registered in role-library/_index.json). Exits
# NONZERO on ANY failure so it can gate a merge / CI / a post-install check.
#
#   VERIFY (this file) is the third leg of install / wire / verify:
#     - INSTALL: the main installer's install_skill_51_signature_presentation()
#       copies this skill into the box (skill 23 is the prerequisite engine).
#     - WIRE:    the SOP-SLIDE-06 lockstep already installed the three SP phases
#       (P-SP-INTAKE / P-SP-STRUCTURE / P-SP-P3-HYGIENE) + _chk_sp_* wrappers into
#       the department engine — there is NO separate wire.sh for this skill.
#     - VERIFY:  this script + the three provers.
#
# Usage:  bash 51-signature-presentation/verify.sh
# Exit:   0 = all checks passed;  nonzero = at least one check failed.
# ==============================================================================
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SP_SCRIPTS="$SKILL_DIR/scripts"
# The AI Workforce Blueprint (skill 23) engine is a sibling of this skill both in
# the repo and on an installed box; resolve the register script relative to here.
REGISTER="$SKILL_DIR/../23-ai-workforce-blueprint/scripts/register-library-additions.py"
PY="${PYTHON:-python3}"
# Fleet boxes are Macs; default the platform hint if the caller did not set one.
export OPENCLAW_PLATFORM="${OPENCLAW_PLATFORM:-mac}"

fails=0
run() {
    # run "<label>" <cmd...> — prints PASS/FAIL, increments $fails on nonzero.
    local label="$1"; shift
    local log
    log="$("$@" 2>&1)"; local rc=$?
    if [ "$rc" -eq 0 ]; then
        printf '  [PASS] %s\n' "$label"
    else
        printf '  [FAIL] %s (rc=%s)\n' "$label" "$rc"
        printf '%s\n' "$log" | sed 's/^/         /'
        fails=$((fails + 1))
    fi
}

echo "== Skill 51 (Signature Presentation) :: verify.sh =="

# 1) The five fail-closed SP provers — built-in self-test fixtures.
#    prove_sp_routing is the claim/routing gate (AF-SP-TYPE-UNDECLARED) that closes
#    the "omit deck_type to skip every SP gate" bypass.
#    A10 / T0-12: intake_trace_check is the intake-CONVERSATION gate (AF-INTAKE-BATCH).
#    It was self-tested only in a separate CI job while this script — the skill's own
#    verification leg — never exercised it, and it was wired as advisory. It is now a
#    required preflight in the engine (_chk_sp_intake_trace), so verify.sh must fail
#    when its fixtures do not hold.
for p in prove_sp_routing prove_sp_intake prove_sp_structure prove_sp_no_pitch intake_trace_check; do
    if [ -f "$SP_SCRIPTS/$p.py" ]; then
        run "$p.py --self-test" "$PY" "$SP_SCRIPTS/$p.py" --self-test
    else
        printf '  [FAIL] %s.py missing at %s\n' "$p" "$SP_SCRIPTS"
        fails=$((fails + 1))
    fi
done

# 1b) ENGINE WIRE-PRESENCE — Skill 51 has NO build path of its own; its gates only
#     bite when the Skill-23 presentations engine (build_deck.py) DEFINES + REGISTERS
#     the four _chk_sp_* wrappers (the claim gate + the three sacred gates). When the
#     engine is co-located, assert the wiring landed — FAIL (not warn) if it did not
#     (a stale skill-23 copy / a box where the SOP-SLIDE-06 lockstep never ran would
#     otherwise pass verify.sh while ZERO SP enforcement exists at runtime).
ENGINE="$SKILL_DIR/../23-ai-workforce-blueprint/templates/role-library/presentations/scripts/build_deck.py"
if [ -f "$ENGINE" ]; then
    run "engine wire-presence (P-SP gates wired into build_deck.py)" \
        "$PY" "$SP_SCRIPTS/prove_sp_routing.py" --check-wiring "$ENGINE"
else
    # SK2-08: FAIL (not WARN). Skill 51 has NO build path of its own — its gates
    # bite ONLY when the Skill-23 presentations engine (build_deck.py) is present
    # AND has the four _chk_sp_* wrappers wired. A missing engine means ZERO SP
    # enforcement at runtime, so a WARN-and-pass here would certify a box on which
    # the skill is completely unwired. skill 23 is the declared prerequisite engine.
    printf '  [FAIL] engine build_deck.py NOT co-located at %s — ' "$ENGINE"
    printf 'skill 23 (prerequisite presentations engine) is absent; SP enforcement is unwired.\n'
    fails=$((fails + 1))
fi

# 2) library-register --check sanity: both SP roles are registered in _index.json.
if [ -f "$REGISTER" ]; then
    run "register-library-additions.py --check" "$PY" "$REGISTER" --check
else
    # SK2-08: FAIL (not WARN) — same rationale. The register script is part of the
    # Skill-23 engine; its absence means the SP roles were never registered, so the
    # skill cannot enforce anything.
    printf '  [FAIL] register-library-additions.py NOT found at %s — ' "$REGISTER"
    printf 'skill 23 engine is not co-located; SP roles are unregistered.\n'
    fails=$((fails + 1))
fi

echo "=================================================="
if [ "$fails" -eq 0 ]; then
    echo "RESULT: PASS — all Skill 51 self-verification checks green."
    exit 0
fi
echo "RESULT: FAIL — $fails check(s) failed."
exit 1
