#!/usr/bin/env bash
# tests/unit/skill38-qc-gates-live-agentsmd-awareness.test.sh
# ============================================================================
# DEFECT: 9 of skill 38's qc-*.sh gates (F17 segmentation, F21 multi-tenant,
# U-1 tool-gating, U-2 workflow-exits, U-6 client-test-mode, ZHC tag-prefix,
# F16 A/B testing, F49 ZHC pixel, F18 webhook-chaining) asserted their AGENTS
# marker was present by grepping the SHIPPED SOURCE script
# (scripts/05-update-agents-md.sh) for its own marker text. That proves the
# writer CAN produce the marker; it proves NOTHING about whether the writer
# EVER RAN on this box. A box whose AGENTS.md was never rewritten (the exact
# scenario in the companion wiring defect) still reported qc-passed forever.
#
# THIS SUITE MUTATION-PROVES the fix in BOTH directions, per gate, per marker:
#   (1) a LIVE AGENTS.md that does NOT carry the marker -> gate FAILS, citing
#       the LIVE file by name (not just the source script).
#   (2) a LIVE AGENTS.md that DOES carry the marker (produced by actually
#       running 05-update-agents-md.sh — the real writer, not a hand-typed
#       fixture) -> gate PASSES.
#
# The skill tree itself (protocols, installers, memory rules) is untouched in
# both cases — only the LIVE AGENTS.md differs — so any residual failure can
# only be attributed to the live-file check this suite targets.
#
# Exit 0 = every gate/marker pair proven in both directions. Exit 1 = a
# regression was found.
# ============================================================================
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SKILL_DIR="$REPO_ROOT/38-conversational-ai-system"
AG_SCRIPT="$SKILL_DIR/scripts/05-update-agents-md.sh"

PASS=0; FAIL=0
ok()  { printf '  \033[32m✓ PASS\033[0m — %s\n' "$1"; PASS=$((PASS+1)); }
bad() { printf '  \033[31m✗ FAIL\033[0m — %s\n' "$1"; FAIL=$((FAIL+1)); }
hdr() { printf '\n\033[1m%s\033[0m\n' "$1"; }

[ -f "$AG_SCRIPT" ] || { echo "FATAL: $AG_SCRIPT not found"; exit 2; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# A single "rewritten" AGENTS.md, produced ONCE by the real writer, reused as
# the (2) fixture for every gate below (it carries every current marker, not
# just one skill-feature's).
REWRITTEN_AGENTS="$WORK/rewritten/AGENTS.md"
mkdir -p "$WORK/rewritten"
printf '# AGENTS.md\n\nPre-existing operator content.\n' > "$REWRITTEN_AGENTS"
if ! AGENTS_MD="$REWRITTEN_AGENTS" SKILL38_MASTER_FILES_DIR="$WORK/master-files" \
       bash "$AG_SCRIPT" >"$WORK/writer.log" 2>&1; then
  echo "FATAL: could not produce a rewritten AGENTS.md fixture (05-update-agents-md.sh failed) — see $WORK/writer.log"
  cat "$WORK/writer.log"
  exit 2
fi

# A "never rewritten" AGENTS.md: plausible pre-existing content, NO SKILL38
# stanzas at all — exactly the reported defect scenario.
STALE_AGENTS="$WORK/stale/AGENTS.md"
mkdir -p "$WORK/stale"
printf '# AGENTS.md\n\nPre-existing operator content. No skill-38 stanzas here.\n' > "$STALE_AGENTS"

# gate_marker_case <gate-script> <marker> [extra-args...]
# Runs the gate against the STALE fixture (expect the marker sub-check to
# fail, cited against the LIVE path) and the REWRITTEN fixture (expect it to
# pass), using --skill-dir where the gate supports it (real skill tree
# otherwise, so every OTHER static invariant stays green in both runs).
gate_marker_case() {
  local script="$1" marker="$2"; shift 2
  local name; name="$(basename "$script")"
  local out

  out="$(AGENTS_MD="$STALE_AGENTS" bash "$SKILL_DIR/scripts/$script" "$@" 2>&1)"
  if echo "$out" | grep -qE "LIVE AGENTS\.md .*MISSING the $marker marker"; then
    ok "$name / $marker — STALE live AGENTS.md correctly FAILS, citing the LIVE file (not the source script)"
  else
    bad "$name / $marker — STALE live AGENTS.md did not produce the expected LIVE-file failure"
    echo "$out" | grep -i "$marker" | sed 's/^/      /'
  fi

  out="$(AGENTS_MD="$REWRITTEN_AGENTS" bash "$SKILL_DIR/scripts/$script" "$@" 2>&1)"
  if echo "$out" | grep -qE "LIVE AGENTS\.md .*carries the $marker marker"; then
    ok "$name / $marker — REWRITTEN live AGENTS.md correctly PASSES the live-file check"
  else
    bad "$name / $marker — REWRITTEN live AGENTS.md did not pass the live-file check"
    echo "$out" | grep -i "$marker" | sed 's/^/      /'
  fi
}

hdr "Per-gate live-AGENTS.md mutation proof (stale -> FAIL, rewritten -> PASS)"
gate_marker_case "qc-segmentation.sh"      "STEP_1_85_SEGMENTATION_AWARENESS"
gate_marker_case "qc-multi-tenant.sh"      "STEP_0_8_MULTI_TENANT_ISOLATION"
gate_marker_case "qc-zhc-tag-prefix.sh"    "SKILL38_ZHC_TAG_PREFIX"
gate_marker_case "qc-ab-testing.sh"        "STEP_1_87_AB_TESTING"
gate_marker_case "qc-zhc-pixel.sh"         "STEP_1_45_PIXEL_CONCIERGE"
gate_marker_case "qc-webhook-chaining.sh"  "STEP_2_9_WEBHOOK_CHAINING"
gate_marker_case "qc-client-test-mode.sh"  "CLIENT_TEST_MODE"
gate_marker_case "qc-client-test-mode.sh"  "STEP_0_4_TEST_MODE_REREAD"

hdr "Python-embedded gates (qc-workflow-exits.sh, qc-tool-gating.sh) — same proof via --json (no stdout pollution)"

py_gate_case() {
  local script="$1" marker="$2" needle="$3"
  local name; name="$(basename "$script")"
  local json failures_str

  json="$(AGENTS_MD="$STALE_AGENTS" bash "$SKILL_DIR/scripts/$script" --json 2>/dev/null)"
  failures_str="$(printf '%s' "$json" | python3 -c "import json,sys; print(' | '.join(json.load(sys.stdin).get('failures',[])))" 2>/dev/null)"
  if printf '%s' "$failures_str" | grep -qE "LIVE AGENTS\.md .*MISSING the $marker marker"; then
    ok "$name / $marker — STALE live AGENTS.md correctly FAILS, citing the LIVE file (--json failures[])"
  else
    bad "$name / $marker — STALE live AGENTS.md did not produce the expected LIVE-file failure in --json output"
    echo "$failures_str" | sed 's/^/      /'
  fi
  # JSON must still be valid JSON even with our extra stderr diagnostics (proves
  # the fix did not leak plain-text prints onto stdout and corrupt --json mode).
  if printf '%s' "$json" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
    ok "$name — --json output remains valid JSON (no stdout pollution from the live-file diagnostics)"
  else
    bad "$name — --json output is NOT valid JSON (a live-file diagnostic leaked onto stdout)"
  fi

  json="$(AGENTS_MD="$REWRITTEN_AGENTS" bash "$SKILL_DIR/scripts/$script" --json 2>/dev/null)"
  failures_str="$(printf '%s' "$json" | python3 -c "import json,sys; print(' | '.join(json.load(sys.stdin).get('failures',[])))" 2>/dev/null)"
  if printf '%s' "$failures_str" | grep -q "$marker"; then
    bad "$name / $marker — REWRITTEN live AGENTS.md still reports a $marker failure"
  else
    ok "$name / $marker — REWRITTEN live AGENTS.md reports no $marker failure"
  fi
}

py_gate_case "qc-workflow-exits.sh" "STEP_1_30_EXIT_RULES" "workflow-exit-rules-protocol"
py_gate_case "qc-tool-gating.sh"    "STEP_1_88_TOOL_GATING"  "tool-gating-protocol"

hdr "No live AGENTS.md at all (bare CI checkout) — SKIP, never a spurious FAIL"
NOWHERE="$WORK/does-not-exist/AGENTS.md"
for script_marker in \
  "qc-segmentation.sh:STEP_1_85_SEGMENTATION_AWARENESS" \
  "qc-multi-tenant.sh:STEP_0_8_MULTI_TENANT_ISOLATION" \
  "qc-zhc-tag-prefix.sh:SKILL38_ZHC_TAG_PREFIX" \
  "qc-ab-testing.sh:STEP_1_87_AB_TESTING" \
  "qc-zhc-pixel.sh:STEP_1_45_PIXEL_CONCIERGE" \
  "qc-webhook-chaining.sh:STEP_2_9_WEBHOOK_CHAINING" \
  "qc-client-test-mode.sh:CLIENT_TEST_MODE"; do
  script="${script_marker%%:*}"; marker="${script_marker##*:}"
  out="$(AGENTS_MD="$NOWHERE" bash "$SKILL_DIR/scripts/$script" 2>&1)"
  if echo "$out" | grep -q "\[SKIP\] no live AGENTS.md found"; then
    ok "$script — no live AGENTS.md anywhere -> SKIP (not a false FAIL)"
  else
    bad "$script — no live AGENTS.md anywhere did not produce the expected SKIP line"
  fi
done
for script in qc-workflow-exits.sh qc-tool-gating.sh; do
  json="$(AGENTS_MD="$NOWHERE" bash "$SKILL_DIR/scripts/$script" --json 2>/dev/null)"
  verdict="$(printf '%s' "$json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('verdict','?'))" 2>/dev/null)"
  # PASS here means: absence of a live file did not itself add a failure (the
  # gate's overall verdict on the real skill tree is otherwise PASS).
  if [ "$verdict" = "PASS" ]; then
    ok "$script — no live AGENTS.md anywhere -> overall verdict still PASS (SKIP, not a false FAIL)"
  else
    bad "$script — no live AGENTS.md anywhere flipped the overall verdict to $verdict (should SKIP, not fail)"
  fi
done

printf '\n=========================================\n'
printf 'SKILL-38 QC-GATES LIVE-AGENTSMD AWARENESS: PASS=%d FAIL=%d\n' "$PASS" "$FAIL"
printf '=========================================\n'
[ "$FAIL" -eq 0 ]
