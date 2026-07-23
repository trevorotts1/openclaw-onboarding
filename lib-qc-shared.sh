#!/bin/bash
# lib-qc-shared.sh — shared QC assert/warn/verdict helpers (U073, STAGE 1).
#
# THE PROBLEM (MASTER-SPEC #73/#97/#122): of the 49 per-skill install QC gates
# (NN-slug/qc-*.sh), 37 contain at least one warn-only check, and NOT ONE of
# the 37 can exit non-zero because of a warning. Every verdict line reads only
# the $FAIL counter; the $WARN counter is printed but never consulted. This
# library and the two repo-level gates (scripts/qc-system-integrity.sh,
# scripts/qc-agent.sh) now share ONE verdict implementation that consults
# BOTH counters — behind an opt-in flag so STAGE 1 changes no behavior.
#
# ── TWO-STAGE PLAN ────────────────────────────────────────────────────────────
#   STAGE 1 (this unit, U073): extract these helpers; route the repo-level
#     gates' verdicts through qc_verdict WITHOUT setting QC_FAIL_ON_WARN=1.
#     Every gate's pass/fail behavior is byte-for-byte unchanged.
#   STAGE 2 (later units, one at a time): promote individual warn-only checks
#     to required, PER-CHECK, PER-SKILL, with fleet-wide report-only
#     measurement (QC_FAIL_ON_WARN=1 in a measurement pass first) between
#     each promotion, so a check is only made fatal once the fleet proves it
#     fires on genuinely broken installs and not on healthy boxes.
#
# ── USAGE ─────────────────────────────────────────────────────────────────────
#   source lib-qc-shared.sh          # from a gate script (repo root)
#   qc_assert "1.1 thing works" test -f /path/to/thing
#   qc_warn   "1.2 nice-to-have" command --check
#   qc_verdict "skill-label"; exit $?
#
#   Counters live in the QC_* namespace (QC_PASS / QC_FAIL / QC_WARN) so a
#   caller's own local PASS/FAIL/WARN variables never collide. A gate that
#   keeps its own counters maps them at verdict time:
#     QC_PASS=$PASS QC_FAIL=$FAIL QC_WARN=$WARN; qc_verdict "label"
#
# ── BEHAVIOR CONTRACT ─────────────────────────────────────────────────────────
#   qc_verdict exits non-zero when QC_FAIL > 0, OR when QC_WARN > 0 AND
#   QC_FAIL_ON_WARN=1 (the STAGE-2 per-gate opt-in). With the flag unset —
#   the STAGE-1 default everywhere — warnings are reported but never fatal.

# qc_assert <label> <command...> — a REQUIRED check. PASS/FAIL; increments
# QC_FAIL when the command exits non-zero.
qc_assert() {
  local label="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "  ✓ $label"
    QC_PASS=$(( ${QC_PASS:-0} + 1 ))
  else
    echo "  ✗ $label"
    QC_FAIL=$(( ${QC_FAIL:-0} + 1 ))
  fi
}

# qc_warn <label> <command...> — a WARN-ONLY check. PASS/WARN; increments
# QC_WARN when the command exits non-zero. Never increments QC_FAIL, so a
# warn-only check can only fail the gate once STAGE 2 opts the gate into
# QC_FAIL_ON_WARN=1.
qc_warn() {
  local label="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "  ✓ $label"
    QC_PASS=$(( ${QC_PASS:-0} + 1 ))
  else
    echo "  ⚠ $label (warn-only)"
    QC_WARN=$(( ${QC_WARN:-0} + 1 ))
  fi
}

# qc_verdict <skill_label> — print the result line and decide the exit code.
# Consults BOTH counters; the warning arm is gated on QC_FAIL_ON_WARN so
# STAGE 1 is behavior-preserving. Returns 0 (PASS) or 1 (FAIL).
qc_verdict() {
  local label="$1"
  echo "═══ Result: ${QC_PASS:-0} passed | ${QC_FAIL:-0} failed | ${QC_WARN:-0} warnings ═══"
  if [ "${QC_FAIL:-0}" -gt 0 ]; then echo "QC FAIL: $label"; return 1; fi
  # STAGE-2 OPT-IN: only fail on warnings when explicitly enabled per-gate.
  if [ "${QC_FAIL_ON_WARN:-0}" = "1" ] && [ "${QC_WARN:-0}" -gt 0 ]; then
    echo "QC FAIL (warnings promoted): $label"; return 1
  fi
  echo "QC PASS: $label"; return 0
}
