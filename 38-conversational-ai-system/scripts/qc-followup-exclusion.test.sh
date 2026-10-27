#!/usr/bin/env bash
# qc-followup-exclusion.test.sh — negative test for qc-followup-exclusion.sh (review C4).
#
# A QC gate that can never fail is worthless. This proves qc-followup-exclusion.sh:
#   (A) PASSES on the real, intact skill tree, and
#   (B) FAILS (exit non-zero) when a C4 invariant is broken — one throwaway copy per
#       mutation:
#         1. the Purple-sequence exclusion section is removed from the protocol,
#         2. `collection_sequence_id` is neutered in the AGENTS.md stanza writer,
#         3. the SHARED REMINDER MACHINE owner is neutered in the canonical rules reference,
#         4. the stale "Pre-Feature-15" note is reintroduced,
#         5. the stale "Until v5.7" note is reintroduced,
#         6. the gate is unwired from 11-run-qc-checklist.sh,
#         7. CONTROL PROOF: the positive control text is removed (the cadence heading), so
#            the gate must report a broken scan and FAIL — a green result can never come
#            from a scan that reads nothing.
#
# BASH only (no .py) so it respects qc-static's claude-/anthropic ban. Self-contained:
# copies the skill to a temp dir, mutates the copy, runs the gate against --skill-dir
# (with the REAL --repo-root, so the CI-wiring checks stay honest).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SKILL_DIR/.." && pwd)"
GATE="$SCRIPT_DIR/qc-followup-exclusion.sh"

[ -f "$GATE" ] || { echo "FAIL: qc-followup-exclusion.sh not found at $GATE"; exit 1; }

RC=0
ok() { echo "  [TEST PASS] $1"; }
ng() { echo "  [TEST FAIL] $1"; RC=1; }

echo "=== qc-followup-exclusion.test: negative test for the C4 gate ==="

# (A) The intact skill must PASS.
if bash "$GATE" >/dev/null 2>&1; then
  ok "intact skill passes qc-followup-exclusion.sh"
else
  ng "intact skill should PASS qc-followup-exclusion.sh but it failed — run: bash $GATE"
fi

make_copy() {
  local dst; dst="$(mktemp -d)"
  cp -a "$SKILL_DIR/." "$dst/"
  printf '%s' "$dst"
}

run_should_fail() {
  local dir="$1" desc="$2"
  if bash "$GATE" --skill-dir "$dir" --repo-root "$REPO_ROOT" >/dev/null 2>&1; then
    ng "gate should FAIL when $desc — but it PASSED"
  else
    ok "gate correctly FAILS when $desc"
  fi
  rm -rf "$dir"
}

# (B1) Remove the whole exclusion section from the protocol.
D1="$(make_copy)"
TMP="$(mktemp)"
awk '
  /^## Purple collection sequence exclusion/ { skip=1; next }
  /^## Tags this protocol creates/          { skip=0 }
  skip==0
' "$D1/protocols/intelligent-followup-protocol.md" > "$TMP"
mv "$TMP" "$D1/protocols/intelligent-followup-protocol.md"
run_should_fail "$D1" "the Purple collection sequence exclusion section is removed from the protocol"

# (B2) Neuter the exclusion key in the AGENTS.md stanza writer.
D2="$(make_copy)"
TMP="$(mktemp)"
sed 's/collection_sequence_id/SEQUENCE_FIELD_REMOVED/g' "$D2/scripts/05-update-agents-md.sh" > "$TMP"
mv "$TMP" "$D2/scripts/05-update-agents-md.sh"
run_should_fail "$D2" "collection_sequence_id is neutered in 05-update-agents-md.sh"

# (B3) Neuter the owner in the canonical rules reference.
D3="$(make_copy)"
TMP="$(mktemp)"
sed 's/SHARED REMINDER MACHINE/UNOWNED_SEQUENCE/g' "$D3/references/agents-runtime-rules.md" > "$TMP"
mv "$TMP" "$D3/references/agents-runtime-rules.md"
run_should_fail "$D3" "the SHARED REMINDER MACHINE owner is neutered in agents-runtime-rules.md"

# (B4) Reintroduce the stale "Pre-Feature-15" note.
D4="$(make_copy)"
printf '\n## Pre-Feature-15 implementation\n\nThis protocol uses direct OpenClaw cron scheduling.\n' \
  >> "$D4/protocols/intelligent-followup-protocol.md"
run_should_fail "$D4" "the stale 'Pre-Feature-15' note is reintroduced into the protocol"

# (B5) Reintroduce the stale "Until v5.7" note.
D5="$(make_copy)"
printf '\nUntil v5.7 ships F29 hand-off, agent tags contact ZHC-stalled-sales.\n' \
  >> "$D5/protocols/intelligent-followup-protocol.md"
run_should_fail "$D5" "the stale 'Until v5.7' note is reintroduced into the protocol"

# (B6) Unwire the gate from the QC checklist.
D6="$(make_copy)"
TMP="$(mktemp)"
sed '/qc-followup-exclusion\.sh/d' "$D6/scripts/11-run-qc-checklist.sh" > "$TMP"
mv "$TMP" "$D6/scripts/11-run-qc-checklist.sh"
run_should_fail "$D6" "the gate is unwired from 11-run-qc-checklist.sh"

# (B7) Control proof: remove the positive control text. The gate must refuse to certify
#      absences when its own scan no longer sees known-present text.
D7="$(make_copy)"
TMP="$(mktemp)"
sed '/^## 10-touchpoint cadence/d' "$D7/protocols/intelligent-followup-protocol.md" > "$TMP"
mv "$TMP" "$D7/protocols/intelligent-followup-protocol.md"
run_should_fail "$D7" "the positive control text is removed (a blind scan must not certify success)"

echo ""
if [ "$RC" -eq 0 ]; then
  echo "RESULT: PASS — qc-followup-exclusion.sh passes intact and fails on each broken C4 invariant, including a blinded scan."
  exit 0
else
  echo "RESULT: FAIL — the negative test did not behave as expected (see above)."
  exit 1
fi
