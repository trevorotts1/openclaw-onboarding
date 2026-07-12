#!/usr/bin/env bash
# qc-runtime-tool-gating.sh - machine-enforce the RUNTIME U-1 tool-gating PROVER.
#
# THE RULE this gate protects: the U-1 guarantee ("at runtime, before any tool
# call, the brain resolves the active phase's enabled tools and REFUSES any tool
# the phase does not grant") must have a machine-enforced RUNTIME proof, not just
# a build-time static parse. scripts/33-runtime-tool-gating-prover.sh is that
# proof - the tool-gating analog of scripts/24-self-test-hook.sh. "Prose in a
# protocol" is not enforcement; a missing/unwired runtime prover must FAIL the
# build.
#
# WHAT THIS GATE ASSERTS:
#   1. scripts/33-runtime-tool-gating-prover.sh EXISTS and is bash -n clean.
#   2. The fixture playbook + log exist AND express a REAL gating boundary -
#      proven by RUNNING the canonical engine (tools/playbook_engine.py resolve),
#      not by grep: the active phase must grant tool A (check_availability) and
#      must NOT grant tool B (book_appointment).
#   3. The prover's --dry-run (Layer A) actually PASSES against the shipped
#      fixture (exit 0) - the static ground-truth boundary holds today.
#   4. The prover wires the LIVE layer: POSTs a synthetic inbound to its OWN hook
#      URL with the REAL Bearer, reads the session transcript, asserts the agent
#      did NOT invoke tool B (the refusal), and requires a granted-alternative
#      action (no silent no-op).
#   5. It writes the runtimeToolGatingPassed state field and fails on violation.
#   6. It is WIRED into scripts/11-run-qc-checklist.sh (the pre-handoff gate set)
#      and into scripts/04-register-crons.sh (the box-level self-test schedule).
#
# Exit codes: 0 = all assertions pass; 1 = one or more fail; 2 = engine/python3
#             unavailable (cannot judge the fixture boundary).
# BASH only (grep core) - respects qc-static's .py claude-/anthropic ban.
#
# Usage: bash scripts/qc-runtime-tool-gating.sh [--skill-dir DIR]

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    -h|--help) sed -n '1,40p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

PROVER="$SKILL_DIR/scripts/33-runtime-tool-gating-prover.sh"
ENGINE="$SKILL_DIR/tools/playbook_engine.py"
FIXTURE_PLAYBOOK="$SKILL_DIR/tools/tests/fixtures/runtime-gating-playbook.md"
FIXTURE_LOG="$SKILL_DIR/tools/tests/fixtures/runtime-gating-log.md"
QCC="$SKILL_DIR/scripts/11-run-qc-checklist.sh"
CRONS="$SKILL_DIR/scripts/04-register-crons.sh"

TOOL_A="check_availability"
TOOL_B="book_appointment"

MISSING=()

# --- 1. prover exists + parses -------------------------------------------
if [ ! -f "$PROVER" ]; then
  MISSING+=('scripts/33-runtime-tool-gating-prover.sh does not exist (the runtime tool-gating prover)')
else
  bash -n "$PROVER" 2>/dev/null || MISSING+=('scripts/33-runtime-tool-gating-prover.sh has a bash syntax error (bash -n failed)')
  # --- 4. live-layer wiring present in the prover ---
  grep -qE 'curl .* -X POST "?\$ENDPOINT|-X POST "\$\{?ENDPOINT' "$PROVER" || \
    MISSING+=('prover must POST a synthetic inbound (curl -X POST to the hook)')
  grep -qE '/hooks/\$\{?HOOK_NAME|hooks/\$\{?HOOK_NAME' "$PROVER" || \
    MISSING+=('prover must POST to its OWN public hook URL (/hooks/<HOOK_NAME>)')
  grep -qiE 'Authorization: Bearer \$\{?HOOKS_TOKEN' "$PROVER" || \
    MISSING+=('prover must send the REAL Bearer token (Authorization: Bearer $HOOKS_TOKEN)')
  grep -q '"channel":"sms"' "$PROVER" || MISSING+=('prover synthetic body must be channel=sms')
  grep -qE '==23|23-key|len\(d\)==23' "$PROVER" || MISSING+=('prover must build/verify a 23-key body')
  grep -q "$TOOL_B" "$PROVER" || MISSING+=("prover must reference the ungranted tool $TOOL_B (the temptation)")
  grep -qiE 'did NOT invoke|INVOKED the ungranted|REFUSED' "$PROVER" || \
    MISSING+=('prover must assert the agent did NOT invoke the ungranted tool (the refusal check)')
  grep -q 'sessions/\*.jsonl' "$PROVER" || grep -qi 'transcript' "$PROVER" || \
    MISSING+=('prover must read the session transcript for a ground-truth verdict')
  grep -q 'runtimeToolGatingPassed' "$PROVER" || \
    MISSING+=('prover must write the runtimeToolGatingPassed state field')
  grep -qE 'runtimeToolGatingPassed" "false|mark_fail' "$PROVER" || \
    MISSING+=('prover must set runtimeToolGatingPassed=false on failure')
  grep -qE 'playbook_engine.py resolve|"\$ENGINE" resolve' "$PROVER" || \
    MISSING+=('prover must resolve the active phase via the canonical engine (Layer A ground truth)')
fi

# --- 2. fixtures express a REAL gating boundary (proven by the engine) ----
if [ ! -f "$ENGINE" ] || ! command -v python3 >/dev/null 2>&1; then
  echo "qc-runtime-tool-gating: engine tools/playbook_engine.py or python3 unavailable - cannot judge the fixture boundary."
  exit 2
fi
if [ ! -f "$FIXTURE_PLAYBOOK" ]; then
  MISSING+=('tools/tests/fixtures/runtime-gating-playbook.md is missing (the gating fixture)')
elif [ ! -f "$FIXTURE_LOG" ]; then
  MISSING+=('tools/tests/fixtures/runtime-gating-log.md is missing (the gating fixture log)')
else
  ENABLED="$(python3 "$ENGINE" resolve --log "$FIXTURE_LOG" --playbook "$FIXTURE_PLAYBOOK" --json 2>/dev/null \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(",".join(d.get("enabled_tools") or []))' 2>/dev/null || true)"
  case ",$ENABLED," in
    *",$TOOL_A,"*) : ;;
    *) MISSING+=("fixture active phase does NOT grant tool A ($TOOL_A); resolved=[$ENABLED]") ;;
  esac
  case ",$ENABLED," in
    *",$TOOL_B,"*) MISSING+=("fixture active phase GRANTS tool B ($TOOL_B) - no gating boundary; resolved=[$ENABLED]") ;;
    *) : ;;
  esac
fi

# --- 3. the prover's --dry-run (Layer A) passes against the shipped fixture
if [ -f "$PROVER" ]; then
  _tmp_state="$(mktemp 2>/dev/null || echo "${TMPDIR:-/tmp}/.qc-runtime-gating-state.$$")"
  if RUN_STATE_FILE="$_tmp_state" bash "$PROVER" --dry-run >/dev/null 2>&1; then
    : # Layer A green
  else
    MISSING+=('prover --dry-run (Layer A static ground truth) does NOT pass against the shipped fixture')
  fi
  rm -f "$_tmp_state" 2>/dev/null || true
fi

# --- 6. wired into the pre-handoff gate set + the box-level self-test cron -
[ -f "$QCC" ] && grep -q 'qc-runtime-tool-gating' "$QCC" || \
  MISSING+=('scripts/11-run-qc-checklist.sh must invoke qc-runtime-tool-gating.sh (the gate set)')
[ -f "$CRONS" ] && grep -q '33-runtime-tool-gating-prover' "$CRONS" || \
  MISSING+=('scripts/04-register-crons.sh must register the runtime tool-gating prover on the box-level self-test schedule')

echo "=== qc-runtime-tool-gating: runtime U-1 tool-gating prover ==="
echo "skill dir : $SKILL_DIR"
echo "fixture enabled tools: ${ENABLED:-<unresolved>}"
echo ""
if [ "${#MISSING[@]}" -eq 0 ]; then
  echo "  [PASS] 33-runtime-tool-gating-prover.sh exists, parses, and its Layer-A ground truth holds (grants $TOOL_A, refuses $TOOL_B)"
  echo "  [PASS] the prover POSTs a synthetic inbound to its own hook, reads the transcript, asserts the agent refused $TOOL_B, and writes runtimeToolGatingPassed"
  echo "  [PASS] wired into the pre-handoff gate set (11-run-qc-checklist.sh) and the box-level self-test cron (04-register-crons.sh)"
  echo ""
  echo "RESULT: PASS - tool gating has a machine-enforced RUNTIME proof, not just a build-time static parse."
  exit 0
else
  echo "RESULT: FAIL - the runtime tool-gating prover is missing/unwired:"
  for m in "${MISSING[@]}"; do echo "          - $m"; done
  exit 1
fi
