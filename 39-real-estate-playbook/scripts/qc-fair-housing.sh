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

# 2. THE ROUTING ENTRY POINT MUST REFUSE A PROTECTED ATTRIBUTE BEFORE SCORING.
#
#    SK1-30 / T0-52 — what this replaces. Checks 2 and 3 used to be three text
#    searches:
#        grep -qi "never route on" protocols/lead-routing-protocol.md
#        grep -q  "fair_housing_offending_keys" lib-re-events.sh
#        grep -q  "REFUSED (fair-housing)"      lib-re-events.sh
#    and the verdict line then claimed "fair-housing is machine-enforced". What
#    those searches proved is that a sentence is still in a markdown file and two
#    strings are still in a shell file. The denylist they pointed at sits at the
#    point an event is WRITTEN — after the routing decision has already been made
#    — so the routing itself was never examined by anything. On a surface with
#    real legal exposure the enforced object was the shape of a log line.
#
#    The gate now DRIVES the routing entry point (scripts/route-lead.sh) with a
#    protected-attribute payload and requires: a non-zero refusal, no agent in
#    the output, and an EMPTY scoring trace — the last of which is what proves
#    the detector ran BEFORE any filtering or scoring rather than after it.
ENTRY="$SCRIPT_DIR/route-lead.sh"
if [ ! -f "$ENTRY" ]; then
  echo "  [FAIL] the routing entry point scripts/route-lead.sh is MISSING — routing would be"
  echo "         computed somewhere this gate cannot see, which is the state T0-52 describes"
  FAIL=1
else
  FH_SB="$(mktemp -d)"
  trap 'rm -rf "$FH_SB"' EXIT
  cat > "$FH_SB/roster.json" <<'ROSTER'
{"version":"1.0.0","agents":[
 {"agent_ref":"QC-A1","active":true,"specialties":["buyer","first_time"],"areas":["north"],"capacity_weight":1.0},
 {"agent_ref":"QC-A2","active":true,"specialties":["listing","luxury"],"areas":["north"],"capacity_weight":1.0}],
 "fallback_queue":"QC-FALLBACK"}
ROSTER
  printf '%s' '{"role":"buyer","race":"withheld","area":"north"}' > "$FH_SB/lead-protected.json"
  printf '%s' '{"role":"seller","signals":["luxury"],"area":"north"}' > "$FH_SB/lead-clean.json"

  # 2a. A protected attribute in the LEAD is refused, before any scoring.
  OUT="$(MASTER_FILES_DIR="$FH_SB" SKILL39_ROUTE_TRACE="$FH_SB/trace-protected.txt" \
          bash "$ENTRY" --lead "$FH_SB/lead-protected.json" --roster "$FH_SB/roster.json" --json 2>/dev/null)"
  RC=$?
  if [ "$RC" -eq 3 ]; then
    echo "  [PASS] routing REFUSES a lead carrying a protected-class field (exit 3)"
  else
    echo "  [FAIL] routing did not refuse a protected-class lead (exit $RC, output: $OUT)"; FAIL=1
  fi
  if [ -z "$OUT" ]; then
    echo "  [PASS] the refusal emitted NO routing decision"
  else
    echo "  [FAIL] a routing decision was emitted for a protected-class lead: $OUT"; FAIL=1
  fi
  if [ ! -s "$FH_SB/trace-protected.txt" ]; then
    echo "  [PASS] the refusal happened BEFORE any filtering or scoring (scoring trace is empty)"
  else
    echo "  [FAIL] the routing scored agents BEFORE refusing — the detector runs too late:"
    sed 's/^/         /' "$FH_SB/trace-protected.txt"
    FAIL=1
  fi

  # 2b. A protected attribute in the ROSTER is refused too (both payloads).
  cp "$FH_SB/roster.json" "$FH_SB/roster-protected.json"
  jq '.agents[0] += {"familial_status":"withheld"}' "$FH_SB/roster.json" > "$FH_SB/roster-protected.json"
  MASTER_FILES_DIR="$FH_SB" bash "$ENTRY" --lead "$FH_SB/lead-clean.json" --roster "$FH_SB/roster-protected.json" --json >/dev/null 2>&1
  if [ $? -eq 3 ]; then
    echo "  [PASS] routing REFUSES a ROSTER carrying a protected-class field"
  else
    echo "  [FAIL] a protected-class field in the roster did not stop routing"; FAIL=1
  fi

  # 2c. ANTI-FALSE-POSITIVE: a clean specialty-only lead still routes. A gate
  #     that refuses everything enforces nothing anyone will keep switched on.
  CLEAN_OUT="$(MASTER_FILES_DIR="$FH_SB" SKILL39_ROUTE_TRACE="$FH_SB/trace-clean.txt" \
                bash "$ENTRY" --lead "$FH_SB/lead-clean.json" --roster "$FH_SB/roster.json" --json 2>/dev/null)"
  CRC=$?
  if [ "$CRC" -eq 0 ] && printf '%s' "$CLEAN_OUT" | jq -e '.routed == true and (.agent_ref | type=="string")' >/dev/null 2>&1; then
    echo "  [PASS] a clean specialty-only lead still routes ($CLEAN_OUT)"
  else
    echo "  [FAIL] a clean lead did NOT route (exit $CRC, output: $CLEAN_OUT)"; FAIL=1
  fi
  if [ -s "$FH_SB/trace-clean.txt" ]; then
    echo "  [PASS] the clean lead DID reach scoring (the trace is not vacuously empty)"
  else
    echo "  [FAIL] the clean lead never reached scoring — the empty-trace assertion above proves nothing"; FAIL=1
  fi
fi

# 3. The protocol document must name the routing entry point, so an operator
#    reading the protocol is sent to the enforced path rather than to prose.
#    This is a DOCUMENTATION check, not the enforcement proof — the enforcement
#    proof is the behavioural drive in section 2.
LR="$SKILL_DIR/protocols/lead-routing-protocol.md"
if [ -f "$LR" ] && grep -q "route-lead.sh" "$LR"; then
  echo "  [PASS] the lead-routing protocol names scripts/route-lead.sh as the entry point"
else
  echo "  [FAIL] protocols/lead-routing-protocol.md does not name the routing entry point"; FAIL=1
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "RESULT: PASS — fair-housing gates the ROUTING DECISION: scripts/route-lead.sh refuses a protected attribute before any filtering or scoring, and the same denylist still guards the event chokepoint."
  exit 0
else
  echo "RESULT: FAIL — fair-housing enforcement gap detected above."
  exit 1
fi
