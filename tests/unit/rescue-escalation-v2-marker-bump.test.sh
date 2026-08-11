#!/usr/bin/env bash
# tests/unit/rescue-escalation-v2-marker-bump.test.sh
# ---------------------------------------------------------------------------
# R7 -- proves the RESCUE_ESCALATION_BOXNAME V1->V2 marker bump in
# apply-fleet-standards.sh (§5j) actually re-stamps correctly on all three
# real box populations: a box already carrying a V1-stamped section, a box
# with no marker at all (bare heading), and a box already on V2 (idempotent
# no-op). Also proves the LOOP: routing line actually lands in the rendered
# output, and that a V1->V2 transition does not leave the old V1 opening
# marker orphaned above the new section.
#
# METHOD: extract the ESCPY heredoc body VERBATIM from apply-fleet-
# standards.sh (between the python3 invocation line and the bare "ESCPY"
# terminator), by locating those exact markers -- never a reimplementation.
# Fails loud (exit 2) if the markers drift.
# ---------------------------------------------------------------------------
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AFS="$REPO_ROOT/scripts/apply-fleet-standards.sh"
TPL="$REPO_ROOT/scripts/rescue-escalation-section.md.tpl"

[ -f "$AFS" ] || { echo "FATAL: $AFS not found"; exit 2; }
[ -f "$TPL" ] || { echo "FATAL: $TPL not found"; exit 2; }
if [ -z "${BASH_VERSION:-}" ]; then echo "FATAL: not running under bash"; exit 2; fi
echo "Running under BASH_VERSION=$BASH_VERSION (asserted, not assumed)"

PASS=0
FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ✓ $1"; }
bad() { FAIL=$((FAIL+1)); echo "  ✗ $1"; }

WORK="$(mktemp -d -t rescue-esc-v2-test-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

ESCPY="$WORK/escpy.py"
awk '
  /python3 - "\$AGENTS_FILE" 2>\/dev\/null <</ { p=1; next }
  p && $0 == "ESCPY" { exit }
  p { print }
' "$AFS" > "$ESCPY"
if [ ! -s "$ESCPY" ]; then
  echo "FATAL: could not extract the ESCPY heredoc body from $AFS (marker drift?)"
  exit 2
fi
echo "Extracted ESCPY body: $(wc -l < "$ESCPY" | tr -d ' ') lines"
python3 -c "compile(open('$ESCPY').read(), '$ESCPY', 'exec')" || { echo "FATAL: extracted ESCPY body is not valid python"; exit 2; }

# Template must carry the V2 marker pair and the LOOP: line before any
# fixture is meaningful.
if ! grep -q "RESCUE_ESCALATION_BOXNAME_V2" "$TPL"; then
  echo "FATAL: $TPL does not carry the V2 marker -- nothing below is testing what it claims to"
  exit 2
fi
if ! grep -q "LOOP:" "$TPL"; then
  echo "FATAL: $TPL does not carry the LOOP: routing line"
  exit 2
fi

run_escpy() {
  # run_escpy <agents-file> -- runs the extracted ESCPY against it with a
  # fixed slug, prints ESCPY's own stdout verdict token.
  local agents="$1"
  RESCUE_BOX_SLUG="test-box-slug" RESCUE_TPL="$TPL" _RESCUE_IS_VPS="0" \
    python3 "$ESCPY" "$agents"
}

# ---------------------------------------------------------------------------
# SCENARIO 1: box already carrying a V1-stamped section (marker pair only,
# no LOOP: line, boxName pre-filled from the old render) -- must be found via
# the "replace" branch is WRONG for this box (V1 marker != V2 START), so it
# must go through "upgrade" and land on V2 content with NO orphaned V1 tag.
# ---------------------------------------------------------------------------
echo ""
echo "=== SCENARIO 1: V1-stamped box upgrades to V2, no orphaned V1 tag (ASSERTION) ==="
a1="$WORK/AGENTS-v1.md"
cat > "$a1" <<'EOF'
# Agent Instructions

Some preceding content.

<!-- RESCUE_ESCALATION_BOXNAME_V1 -->
## Escalate to Rescue Rangers (when you are stuck)

Old V1 body text, no LOOP: routing line here.

boxName should be "old-slug-value" in this fixture: "old-slug-value"
<!-- END RESCUE_ESCALATION_BOXNAME_V1 -->

## Some Other Section
Untouched.
EOF
result="$(run_escpy "$a1")"
echo "  ESCPY verdict: $result"
if [[ "$result" == upgrade:* ]] \
   && grep -q "RESCUE_ESCALATION_BOXNAME_V2" "$a1" \
   && grep -q "LOOP:" "$a1" \
   && ! grep -q "RESCUE_ESCALATION_BOXNAME_V1" "$a1" \
   && grep -q "test-box-slug" "$a1" \
   && grep -q "## Some Other Section" "$a1"; then
  ok "V1-stamped box: upgraded to V2 (verdict=$result), LOOP: line present, V1 tag NOT orphaned, following section untouched"
else
  bad "V1-stamped box: expected clean V1->V2 upgrade with no orphaned V1 marker (verdict=$result)"
  echo "  --- resulting file ---"; sed 's/^/    /' "$a1"
fi

# ---------------------------------------------------------------------------
# SCENARIO 2: box with no marker at all (bare heading, legacy pre-V1 state)
# -- must upgrade cleanly via the same "upgrade" branch.
# ---------------------------------------------------------------------------
echo ""
echo "=== SCENARIO 2: unmarked (bare heading) box upgrades to V2 (ASSERTION) ==="
a2="$WORK/AGENTS-unmarked.md"
cat > "$a2" <<'EOF'
# Agent Instructions

## Escalate to Rescue Rangers (when you are stuck)

Ancient unmarked body text.

## Some Other Section
Untouched.
EOF
result="$(run_escpy "$a2")"
echo "  ESCPY verdict: $result"
if [[ "$result" == upgrade:* ]] && grep -q "RESCUE_ESCALATION_BOXNAME_V2" "$a2" && grep -q "LOOP:" "$a2"; then
  ok "unmarked box: upgraded to V2 (verdict=$result), LOOP: line present"
else
  bad "unmarked box: expected clean upgrade to V2 (verdict=$result)"
fi

# ---------------------------------------------------------------------------
# SCENARIO 3: box already on V2 -- second run must be a byte-identical no-op.
# ---------------------------------------------------------------------------
echo ""
echo "=== SCENARIO 3: already-V2 box is idempotent (CONTROL) ==="
a3="$WORK/AGENTS-v2.md"
cp "$a1" "$a3" 2>/dev/null || true
# a1 is now V2-stamped from Scenario 1 -- reuse it as the "already V2" fixture
cp "$a1" "$a3"
before_sha="$(shasum -a 256 "$a3" | awk '{print $1}')"
result2="$(run_escpy "$a3")"
after_sha="$(shasum -a 256 "$a3" | awk '{print $1}')"
echo "  ESCPY verdict: $result2"
if [ "$result2" = "noop" ] && [ "$before_sha" = "$after_sha" ]; then
  ok "already-V2 box: second run is a byte-identical no-op (verdict=noop)"
else
  bad "already-V2 box: expected verdict=noop and unchanged bytes (verdict=$result2, sha before=$before_sha after=$after_sha)"
fi

# ---------------------------------------------------------------------------
# SCENARIO 4 (CONTROL): a box with no '## Escalate to Rescue Rangers' section
# at all must be left alone -- verdict=absent, file untouched.
# ---------------------------------------------------------------------------
echo ""
echo "=== SCENARIO 4: box with no escalation section at all is left alone (CONTROL) ==="
a4="$WORK/AGENTS-none.md"
cat > "$a4" <<'EOF'
# Agent Instructions

Nothing about Rescue Rangers here.
EOF
before_sha4="$(shasum -a 256 "$a4" | awk '{print $1}')"
result4="$(run_escpy "$a4")"
after_sha4="$(shasum -a 256 "$a4" | awk '{print $1}')"
if [ "$result4" = "absent" ] && [ "$before_sha4" = "$after_sha4" ]; then
  ok "no-section box: verdict=absent, file untouched (no section created)"
else
  bad "no-section box: expected verdict=absent and untouched (verdict=$result4)"
fi

echo ""
echo "============================================================"
echo "RESULT: $PASS passed, $FAIL failed"
echo "============================================================"
[ "$FAIL" -eq 0 ]
