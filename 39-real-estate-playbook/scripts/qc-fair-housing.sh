#!/usr/bin/env bash
# qc-fair-housing.sh — CODED, fail-closed fair-housing / lead-routing gate.
#
# WHY (SK1-21): fair housing was previously enforced ONLY by LLM prose
# (references/fair-housing-guardrails.md, protocols/lead-routing-protocol.md).
# Prose is not enforcement. This gate is the machine-checkable floor: routing and
# qualification must NEVER record or route on a protected characteristic, so a
# structured payload carrying a protected-class field is REFUSED. The same
# denylist runs at the runtime event chokepoint (lib-re-events.sh :: re_event),
# so every event write is guarded, not just this gate.
#
# Modes:
#   check-payload '<json>'   runtime guard — exit 3 if the payload carries a
#                            protected-class field (fail-closed), 0 if clean.
#   (default) [--skill-dir D]  build QC — assert the guardrails doc, the
#                            lead-routing protocol, and the re_event chokepoint
#                            enforcement all exist, and self-test the denylist
#                            against a known-bad and a known-good payload.
#
# Exit: 0 = pass/clean; 1 = build QC failed; 3 = payload violated (fail-closed).

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Reuse the single source of truth for the denylist (sourcing is safe: the
# lib's direct-invocation dispatch is guarded by BASH_SOURCE==$0).
# shellcheck source=/dev/null
. "$SCRIPT_DIR/lib-re-events.sh"

command -v jq >/dev/null 2>&1 || { echo "qc-fair-housing: jq required" >&2; exit 1; }

# ---- runtime guard mode ----
if [ "${1:-}" = "check-payload" ]; then
  payload="${2:-}"
  [ -n "$payload" ] || { echo "check-payload: missing JSON payload" >&2; exit 2; }
  hits="$(fair_housing_offending_keys "$payload")"
  if [ -n "$hits" ]; then
    echo "BLOCKED (fair-housing): protected-class field(s): $(printf '%s' "$hits" | paste -sd, - | sed 's/,$//')" >&2
    exit 3
  fi
  echo "OK: payload carries no protected-class field."
  exit 0
fi

# ---- build QC mode ----
while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    -h|--help) sed -n '1,25p' "$0"; exit 0 ;;
    *) shift ;;
  esac
done

FAIL=0
echo "=== qc-fair-housing (Skill 39): coded fair-housing gate ==="

# 1. The guardrails reference must exist and enumerate the protected classes.
GR="$SKILL_DIR/references/fair-housing-guardrails.md"
if [ -f "$GR" ] && grep -qi "protected class" "$GR" && grep -qi "familial status" "$GR"; then
  echo "  [PASS] guardrails reference present and enumerates protected classes"
else
  echo "  [FAIL] references/fair-housing-guardrails.md missing or does not enumerate protected classes"; FAIL=1
fi

# 2. The lead-routing protocol must commit to specialty/availability-only routing.
LR="$SKILL_DIR/protocols/lead-routing-protocol.md"
if [ -f "$LR" ] && grep -qi "never route on" "$LR"; then
  echo "  [PASS] lead-routing protocol commits to non-protected-class routing"
else
  echo "  [FAIL] protocols/lead-routing-protocol.md missing the 'never route on a protected class' rule"; FAIL=1
fi

# 3. The runtime chokepoint (re_event) must ENFORCE the denylist — prose alone is
#    not enough. Assert the code path exists so it can't be silently removed.
RE="$SCRIPT_DIR/lib-re-events.sh"
if grep -q "fair_housing_offending_keys" "$RE" && grep -q "REFUSED (fair-housing)" "$RE"; then
  echo "  [PASS] re_event enforces the fair-housing denylist at the write chokepoint"
else
  echo "  [FAIL] lib-re-events.sh does not fail-closed on a protected-class payload"; FAIL=1
fi

# 4. Self-test the denylist: a known-bad payload must be flagged, a clean one not.
BAD='{"role":"buyer","race":"redacted","area":"north"}'
GOOD='{"role":"buyer","specialties":["first_time"],"area":"north","price_band":"mid"}'
if [ -n "$(fair_housing_offending_keys "$BAD")" ]; then
  echo "  [PASS] denylist flags a protected-class field (race)"
else
  echo "  [FAIL] denylist did NOT flag a protected-class field"; FAIL=1
fi
if [ -z "$(fair_housing_offending_keys "$GOOD")" ]; then
  echo "  [PASS] denylist passes a clean specialty-only payload"
else
  echo "  [FAIL] denylist false-positived on a clean payload: $(fair_housing_offending_keys "$GOOD")"; FAIL=1
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "RESULT: PASS — fair-housing is machine-enforced (coded denylist at the event chokepoint)."
  exit 0
else
  echo "RESULT: FAIL — fair-housing enforcement gap detected above."
  exit 1
fi
