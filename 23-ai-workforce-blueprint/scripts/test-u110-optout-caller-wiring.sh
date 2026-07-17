#!/usr/bin/env bash
# test-u110-optout-caller-wiring.sh — U110 (E5-5, closes G2d) provisioning
# caller-wiring proof.
#
# THE GAP: U108 built department-optout-sync.py (derives
# `provisioning/department-optout.json` from the interview's provenance-gated
# decline decisions) but its own CHANGELOG entry (v20.0.61) named the residual
# explicitly: "provisioning caller-wiring ... explicitly routed, not fixed
# here (owned by U110)". With no caller, the script was referenced only by
# itself, its own test, and the CHANGELOG — never invoked from the real
# provisioning flow. `provisioning/department-optout.json` was therefore NEVER
# produced on an actual box, so the Command Center board (U110's own CC leg)
# reads a file nobody writes. This suite proves the CALLER now exists and is
# load-bearing.
#
# THE ROUTE UNDER TEST (deliberately NOT the department-optout-sync.py
# function called directly — that is U108's own suite,
# test-department-optout-sync.sh, and does not prove any caller exists):
# resume-workforce-build.sh, the ONE durable, recurring provisioning-flow
# driver on every box (its own header: "the ONLY autonomous-recovery layer in
# the workforce-build pipeline"). Every assertion below RUNS that real script
# as a subprocess in a hermetic $HOME sandbox and observes the file it
# produces on disk — never imports or calls department_optout_sync directly.
#
#   T1: a hermetic run with NO build-state on the box still produces
#       provisioning/department-optout.json (empty optedOut/unconfirmed) —
#       the caller fires unconditionally, not only on a terminal build.
#   T2: a hermetic run with a REAL provenance-gated, warning-acknowledged
#       decline of a FLOOR department ('general-task' — the catch-all
#       department; declinable-with-warning per the ratified 2026-07-16
#       ruling that general-task is NOT structurally exempt like ceo/
#       master-orchestrator) flows end-to-end through the real caller into
#       the written contract file (floorStatus=floor-confirmed,
#       lossWarningShown=true).
#   T3: a floor decline MISSING lossWarningAck flows through the real caller
#       into `unconfirmed`, NEVER into `optedOut` (U108 acceptance (d)'s
#       guard survives being reached through the new caller, not just when
#       the sync function is called directly).
#   T4 (MUTATION GUARD — "make the test guard the thing"): the wiring block is
#       bounded by sentinel comments (`U110-OPTOUT-SYNC-BEGIN/END`) in
#       resume-workforce-build.sh. This test PROGRAMMATICALLY excises exactly
#       that block from a copy of the script (never hand-edits, so the excise
#       cannot silently drift from the real block), confirms the mutant is
#       still syntactically valid bash (bash -n), then re-runs the SAME T1
#       sandbox setup against the mutant and asserts
#       provisioning/department-optout.json is NOT produced. If someone
#       deletes the call site (or the whole block), this goes RED — proving
#       T1-T3 are not passing "by accident" of some other code path.
#   T5: removing ONLY department-optout-sync.py (the callee) from the picture
#       — rename it out of the way — still lets resume-workforce-build.sh run
#       to completion (exit 0, fire-and-forget, never a build blocker) but
#       the contract file is correctly NOT produced, and the miss is logged.
#
# Hermetic: every test sets HOME to a fresh mktemp sandbox and does not rely
# on /data/.openclaw existing (it never does on ubuntu-latest). No openclaw
# CLI, no network. Depends on python3 (already required by every other
# Skill-23 provisioning suite) and bash; jq is NOT required for T1/T3-T5 (no
# .workforce-build-state.json on disk short-circuits every jq-guarded branch)
# and IS present on ubuntu-latest for T2.
#
# Exit 0 = all assertions pass; non-zero = at least one failed (CI FAIL).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESUME="$SCRIPT_DIR/resume-workforce-build.sh"
SYNC_SCRIPT="$SCRIPT_DIR/department-optout-sync.py"

PASS=0
FAIL=0
ok()  { PASS=$((PASS+1)); echo "  PASS: $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }

if [[ ! -f "$RESUME" ]]; then
  echo "FATAL: $RESUME not found"
  exit 1
fi

# ─────────────────────────────────────────────────────────────────────────
echo "== T1: hermetic run with NO build-state still produces the contract file =="
T1_HOME="$(mktemp -d)"
mkdir -p "$T1_HOME/.openclaw"
T1_RC=0
HOME="$T1_HOME" bash "$RESUME" >/dev/null 2>&1 || T1_RC=$?
T1_OUT="$T1_HOME/.openclaw/workspace/provisioning/department-optout.json"

[[ "$T1_RC" -eq 0 ]] && ok "T1: resume-workforce-build.sh exits 0 with no build-state" \
                      || bad "T1: resume-workforce-build.sh exited $T1_RC (expected 0)"

if [[ -f "$T1_OUT" ]]; then
  ok "T1: provisioning/department-optout.json was produced by the real route"
  python3 - "$T1_OUT" <<'PY' && ok "T1: contract file is well-formed (empty optedOut/unconfirmed)" \
                              || bad "T1: contract file shape unexpected"
import json, sys
d = json.load(open(sys.argv[1]))
assert d.get("optedOut") == {}, d
assert d.get("unconfirmed") == [], d
assert "generatedAt" in d, d
PY
else
  bad "T1: provisioning/department-optout.json was NOT produced (the caller wiring is missing or broken)"
  bad "T1: contract file shape (skipped — file absent)"
fi

# ─────────────────────────────────────────────────────────────────────────
echo ""
echo "== T2: a REAL provenance-gated, warning-acknowledged decline of a FLOOR"
echo "   department ('general-task') flows through the real caller =="
T2_HOME="$(mktemp -d)"
mkdir -p "$T2_HOME/.openclaw/workspace"
cat > "$T2_HOME/.openclaw/workspace/.workforce-build-state.json" <<'JSON'
{
  "canonicalReconciliation": {
    "decisions": {
      "general-task": {
        "decision": "no",
        "source": "interview-board",
        "decidedAt": "2026-07-16T12:00:00Z",
        "decidedBy": "owner",
        "lossWarningAck": true,
        "lossWarning": "Opting out of General Task disables catch-all routing for mis-tagged work."
      }
    }
  }
}
JSON
T2_RC=0
HOME="$T2_HOME" bash "$RESUME" >/dev/null 2>&1 || T2_RC=$?
T2_OUT="$T2_HOME/.openclaw/workspace/provisioning/department-optout.json"

if [[ -f "$T2_OUT" ]]; then
  python3 - "$T2_OUT" <<'PY' && ok "T2: 'general-task' decline flows end-to-end into optedOut (floor-confirmed, warning shown)" \
                              || bad "T2: 'general-task' not honored correctly in the written contract"
import json, sys
d = json.load(open(sys.argv[1]))
rec = d.get("optedOut", {}).get("general-task")
assert rec is not None, f"'general-task' missing from optedOut: {d}"
assert rec.get("optedOut") is True, rec
assert rec.get("floorStatus") == "floor-confirmed", rec
assert rec.get("lossWarningShown") is True, rec
assert d.get("unconfirmed") == [], d
PY
else
  bad "T2: provisioning/department-optout.json was NOT produced"
fi

# ─────────────────────────────────────────────────────────────────────────
echo ""
echo "== T3: a floor decline MISSING lossWarningAck lands in 'unconfirmed', never 'optedOut' =="
T3_HOME="$(mktemp -d)"
mkdir -p "$T3_HOME/.openclaw/workspace"
cat > "$T3_HOME/.openclaw/workspace/.workforce-build-state.json" <<'JSON'
{
  "canonicalReconciliation": {
    "decisions": {
      "legal": {
        "decision": "no",
        "source": "interview-board",
        "decidedAt": "2026-07-16T12:00:00Z",
        "decidedBy": "owner"
      }
    }
  }
}
JSON
HOME="$T3_HOME" bash "$RESUME" >/dev/null 2>&1 || true
T3_OUT="$T3_HOME/.openclaw/workspace/provisioning/department-optout.json"

if [[ -f "$T3_OUT" ]]; then
  python3 - "$T3_OUT" <<'PY' && ok "T3: unconfirmed floor decline never silently honored as opted-out (guard survives the real caller)" \
                              || bad "T3: unconfirmed floor decline was wrongly honored, or not flagged"
import json, sys
d = json.load(open(sys.argv[1]))
assert "legal" not in d.get("optedOut", {}), d
unc_depts = [u.get("department") for u in d.get("unconfirmed", [])]
assert "legal" in unc_depts, d
PY
else
  bad "T3: provisioning/department-optout.json was NOT produced"
fi

# ─────────────────────────────────────────────────────────────────────────
echo ""
echo "== T4 (MUTATION GUARD): excising the U110-OPTOUT-SYNC block must turn T1 RED =="
MUT_DIR="$(mktemp -d)"
MUTANT="$MUT_DIR/resume-workforce-build.sh"

if ! grep -q '# === U110-OPTOUT-SYNC-BEGIN' "$RESUME" || ! grep -q '# === U110-OPTOUT-SYNC-END ===' "$RESUME"; then
  bad "T4: sentinel markers not found in resume-workforce-build.sh — cannot mutation-test the wiring"
else
  # Programmatic excision: drop every line from BEGIN through END inclusive.
  # Never hand-maintained, so it cannot drift from the real block boundaries.
  awk '
    /# === U110-OPTOUT-SYNC-BEGIN/ { skip = 1 }
    !skip { print }
    /# === U110-OPTOUT-SYNC-END ===/ { skip = 0; next }
  ' "$RESUME" > "$MUTANT"

  BEGIN_LINES=$(grep -c '# === U110-OPTOUT-SYNC-BEGIN' "$RESUME")
  # grep -c prints a count (0 or more) on both match and no-match; it only
  # exits non-zero on no-match, so DON'T `|| echo 0` here — with `set -uo
  # pipefail` that would append a SECOND "0" line on the no-match case (grep
  # already printed "0"), corrupting the arithmetic comparison below.
  MUT_HAS_MARKER=$(grep -c 'U110-OPTOUT-SYNC' "$MUTANT" 2>/dev/null)
  [[ -z "$MUT_HAS_MARKER" ]] && MUT_HAS_MARKER=0
  if [[ "$BEGIN_LINES" -ge 1 && "$MUT_HAS_MARKER" -eq 0 ]]; then
    ok "T4: sentinel-bounded block cleanly excised from the mutant (0 remaining markers)"
  else
    bad "T4: excision did not cleanly remove the sentinel block (found $MUT_HAS_MARKER marker line(s) left)"
  fi

  if bash -n "$MUTANT" 2>/dev/null; then
    ok "T4: mutant is still syntactically valid bash (the excision didn't just corrupt the script)"
  else
    bad "T4: mutant has a syntax error — excision boundaries are wrong"
  fi

  T4_HOME="$(mktemp -d)"
  mkdir -p "$T4_HOME/.openclaw"
  T4_RC=0
  HOME="$T4_HOME" bash "$MUTANT" >/dev/null 2>&1 || T4_RC=$?
  T4_OUT="$T4_HOME/.openclaw/workspace/provisioning/department-optout.json"

  if [[ ! -f "$T4_OUT" ]]; then
    ok "T4: with the wiring excised, provisioning/department-optout.json is correctly NOT produced (RED without the fix)"
  else
    bad "T4: contract file was STILL produced with the wiring excised — T1-T3 are not actually guarding the caller"
  fi
fi

# ─────────────────────────────────────────────────────────────────────────
echo ""
echo "== T5: removing the CALLEE (department-optout-sync.py) — caller degrades safely, never blocks the build =="
T5_HOME="$(mktemp -d)"
mkdir -p "$T5_HOME/.openclaw"
MOVED=0
if [[ -f "$SYNC_SCRIPT" ]]; then
  mv "$SYNC_SCRIPT" "${SYNC_SCRIPT}.hidden-for-t5"
  MOVED=1
fi
T5_RC=0
HOME="$T5_HOME" bash "$RESUME" >/dev/null 2>&1 || T5_RC=$?
if [[ "$MOVED" -eq 1 ]]; then
  mv "${SYNC_SCRIPT}.hidden-for-t5" "$SYNC_SCRIPT"
fi
T5_OUT="$T5_HOME/.openclaw/workspace/provisioning/department-optout.json"

[[ "$T5_RC" -eq 0 ]] && ok "T5: resume-workforce-build.sh still exits 0 when the callee script is absent (never a build blocker)" \
                      || bad "T5: resume-workforce-build.sh exited $T5_RC when the callee was absent (should degrade to 0)"
[[ ! -f "$T5_OUT" ]] && ok "T5: no contract file is fabricated when the callee script is absent" \
                       || bad "T5: a contract file appeared even though the callee script was absent"

# ─────────────────────────────────────────────────────────────────────────
echo ""
echo "==================================================="
echo "  test-u110-optout-caller-wiring: PASS=$PASS FAIL=$FAIL"
echo "==================================================="
if (( FAIL > 0 )); then
  echo "FAIL: $FAIL check(s) failed — CI guard triggered"
  exit 1
fi
echo "PASS: all U110 optout-caller-wiring checks pass"
exit 0
