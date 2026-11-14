#!/usr/bin/env bash
# tests/rescue/RRX-ESC/test_escalation_tpl_stamp_idempotent.sh   (RRX-020)
# Proves the NEW escalation section survives BOTH writers unchanged.
#   1. The standalone stamper appends the rendered template to an AGENTS.md,
#      then a second run is a no-op (no duplicated section).
#   2. The section 5j Python block of scripts/apply-fleet-standards.sh is run
#      against that result twice: the file is byte-identical after the second
#      run and still carries the box's client label and agent name.
# The Python block is EXTRACTED from apply-fleet-standards.sh with the same
# awk the sibling rescue-escalation-v2-marker-bump.test.sh uses -- never a
# pasted copy, which would drift. The script itself is only read.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
AFS="$REPO_ROOT/scripts/apply-fleet-standards.sh"
TPL="$REPO_ROOT/scripts/rescue-escalation-section.md.tpl"
STAMPER="$REPO_ROOT/23-ai-workforce-blueprint/templates/role-library/rescue-rangers/scripts/stamp-rescue-escalation-section.sh"
[ -f "$AFS" ] || { echo "FATAL: $AFS not found"; exit 2; }
[ -f "$TPL" ] || { echo "FATAL: $TPL not found"; exit 2; }
[ -f "$STAMPER" ] || { echo "FATAL: $STAMPER not found"; exit 2; }

PASS=0
FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ok   $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $1"; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/rrx-esc-stamp-XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

# --- extract the section 5j Python block (same awk as the marker-bump test) --
ESCPY="$WORK/escpy.py"
awk '
  /python3 - "\$AGENTS_FILE" 2>\/dev\/null <</ { p=1; next }
  p && $0 == "ESCPY" { exit }
  p { print }
' "$AFS" > "$ESCPY"
[ -s "$ESCPY" ] || { echo "FATAL: could not extract the ESCPY body from $AFS (marker drift?)"; exit 2; }
python3 -c "compile(open('$ESCPY').read(), '$ESCPY', 'exec')" || { echo "FATAL: extracted ESCPY body is not valid python"; exit 2; }
echo "Extracted ESCPY body: $(wc -l < "$ESCPY" | tr -d ' ') lines"

# --- 1. render twice through the stamper ------------------------------------
AGENTS="$WORK/AGENTS.md"
printf '# Agent Instructions\n\nExisting content.\n' > "$AGENTS"
STAMP_ARGS=(--agents "$AGENTS" --tpl "$TPL"
  --person "Example Person" --client "Example Client Co" --agent "example-agent"
  --box-name "example-box" --box-type "Mac Mini"
  --oc-version "2026.5.22" --return-to "123456")
bash "$STAMPER" "${STAMP_ARGS[@]}" > "$WORK/stamp1.out" 2>&1
RC1=$?
bash "$STAMPER" "${STAMP_ARGS[@]}" > "$WORK/stamp2.out" 2>&1
RC2=$?
[ "$RC1" -eq 0 ] && ok "stamper first run exits 0" || bad "stamper first run exits $RC1: $(tail -1 "$WORK/stamp1.out")"
[ "$RC2" -eq 0 ] && ok "stamper second run exits 0" || bad "stamper second run exits $RC2: $(tail -1 "$WORK/stamp2.out")"
N_START="$(grep -cF '<!-- RESCUE_ESCALATION_BOXNAME_V3 -->' "$AGENTS" 2>/dev/null || true)"
[ "${N_START:-0}" = "1" ] && ok "stamper rendered exactly one marked section" || bad "stamper produced ${N_START:-0} marked sections, expected 1"
grep -qF 'Example Client Co' "$AGENTS" && ok "stamper rendered the client label" || bad "client label missing after the stamper"
grep -qF 'example-agent' "$AGENTS" && ok "stamper rendered the agent name" || bad "agent name missing after the stamper"

# --- 2. run the fleet-roll Python block twice --------------------------------
run_escpy() {
  RESCUE_BOX_SLUG="example-box" RESCUE_TPL="$TPL" _RESCUE_IS_VPS="0" \
    python3 "$ESCPY" "$AGENTS"
}
VERDICT1="$(run_escpy)"
echo "  fleet-roll verdict 1: $VERDICT1"
SHA1="$(shasum -a 256 "$AGENTS" | awk '{print $1}')"
VERDICT2="$(run_escpy)"
echo "  fleet-roll verdict 2: $VERDICT2"
SHA2="$(shasum -a 256 "$AGENTS" | awk '{print $1}')"

[ "$SHA1" = "$SHA2" ] && ok "second fleet-roll run leaves the file byte-identical" \
  || bad "second fleet-roll run changed the file (before=$SHA1 after=$SHA2)"
[ "$VERDICT2" = "noop" ] && ok "second fleet-roll run reports noop" \
  || bad "second fleet-roll run reported '$VERDICT2', expected noop"
N_START2="$(grep -cF '<!-- RESCUE_ESCALATION_BOXNAME_V3 -->' "$AGENTS" 2>/dev/null || true)"
[ "${N_START2:-0}" = "1" ] && ok "still exactly one marked section after both writers" || bad "${N_START2:-0} marked sections after both writers, expected 1"
grep -qF 'Example Client Co' "$AGENTS" && ok "client label still present after both writers" || bad "client label lost by the fleet-roll block"
grep -qF 'example-agent' "$AGENTS" && ok "agent name still present after both writers" || bad "agent name lost by the fleet-roll block"

echo ""
echo "============================================================"
echo "RESULT: $PASS passed, $FAIL failed"
echo "============================================================"
[ "$FAIL" -eq 0 ]
