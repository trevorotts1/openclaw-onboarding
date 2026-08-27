#!/usr/bin/env bash
# tests/unit/pres-reflex-v2-content-restamp.test.sh
# ---------------------------------------------------------------------------
# Regression lock for the PRESENTATION_ROUTING_REFLEX_V2 idempotency fix in
# scripts/apply-routing-fix.sh and scripts/apply-fleet-standards.sh (KEEP-IN-
# SYNC twins).
#
# ROOT CAUSE THIS COVERS: both scripts used to guard the V2 stamp with marker
# PRESENCE only (`if grep -qF "$V2_MARKER" file; then no-op; else restamp;
# fi`). Once a box was stamped, a later CONTENT revision to the template
# under the SAME V2 marker (e.g. the chat-id MANDATORY addition) never
# propagated to already-stamped boxes -- they stayed frozen at the
# first-stamped body forever. The fix replaces the presence-only guard with
# the same "render the template, compare it to what is currently stamped,
# write only on a real diff" convention already used by
# RESCUE_ESCALATION_BOXNAME_V2 in apply-fleet-standards.sh.
#
# METHOD: extract the PRESCMP_PY heredoc body VERBATIM from both scripts (by
# locating the exact markers), assert the two extractions are byte-identical
# (the twins must stay in sync), then drive the extracted comparator through
# fixtures. Fails loud (exit 2) if the markers drift out of either script.
# ---------------------------------------------------------------------------
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ARF="$REPO_ROOT/scripts/apply-routing-fix.sh"
AFS="$REPO_ROOT/scripts/apply-fleet-standards.sh"

[ -f "$ARF" ] || { echo "FATAL: $ARF not found"; exit 2; }
[ -f "$AFS" ] || { echo "FATAL: $AFS not found"; exit 2; }
if [ -z "${BASH_VERSION:-}" ]; then echo "FATAL: not running under bash"; exit 2; fi
echo "Running under BASH_VERSION=$BASH_VERSION (asserted, not assumed)"

PASS=0
FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ✓ $1"; }
bad() { FAIL=$((FAIL+1)); echo "  ✗ $1"; }

WORK="$(mktemp -d -t pres-reflex-restamp-test-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

extract() {
  # extract <script> <outfile> -- pulls the PRESCMP_PY heredoc body between
  # the exact opening line and the bare "PRESCMP_PY" terminator.
  awk '
    /^  PRES_REFLEX_VERDICT="\$\(python3 - "\$AGENTS_FILE[A-Z_]*" "\$PRES_REFLEX_RENDERED" <<.PRESCMP_PY./ { p=1; next }
    p && $0 == "PRESCMP_PY" { exit }
    p { print }
  ' "$1" > "$2"
}

extract "$ARF" "$WORK/prescmp-arf.py"
extract "$AFS" "$WORK/prescmp-afs.py"

if [ ! -s "$WORK/prescmp-arf.py" ]; then
  echo "FATAL: could not extract PRESCMP_PY from $ARF (marker drift?)"; exit 2
fi
if [ ! -s "$WORK/prescmp-afs.py" ]; then
  echo "FATAL: could not extract PRESCMP_PY from $AFS (marker drift?)"; exit 2
fi
python3 -c "compile(open('$WORK/prescmp-arf.py').read(), 'arf', 'exec')" || { echo "FATAL: apply-routing-fix.sh PRESCMP_PY is not valid python"; exit 2; }
python3 -c "compile(open('$WORK/prescmp-afs.py').read(), 'afs', 'exec')" || { echo "FATAL: apply-fleet-standards.sh PRESCMP_PY is not valid python"; exit 2; }

echo ""
echo "=== TWIN-SYNC CHECK: both scripts carry the byte-identical comparator (CONTROL) ==="
if diff -q "$WORK/prescmp-arf.py" "$WORK/prescmp-afs.py" >/dev/null 2>&1; then
  ok "apply-routing-fix.sh and apply-fleet-standards.sh comparators are byte-identical"
else
  bad "comparators have drifted apart between the two KEEP-IN-SYNC scripts"
  diff "$WORK/prescmp-arf.py" "$WORK/prescmp-afs.py" | sed 's/^/    /'
fi

CMP="$WORK/prescmp-arf.py"  # identical to afs; use either from here on

# Old vs new "rendered template" fixtures -- stand in for a template body
# revision under the SAME V2 marker (e.g. the chat-id MANDATORY addition).
cat > "$WORK/rendered-old.txt" <<'EOF'
<!-- PRESENTATION_ROUTING_REFLEX_V2 -->
# REFLEX 0 (old body, no chat-id text)

Route the task now via the helper.
<!-- END PRESENTATION_ROUTING_REFLEX_V2 -->
EOF

cat > "$WORK/rendered-new.txt" <<'EOF'
<!-- PRESENTATION_ROUTING_REFLEX_V2 -->
# REFLEX 0 (new body, WITH chat-id text)

Route the task now via the helper.
The chat id is MANDATORY when you have it.
<!-- END PRESENTATION_ROUTING_REFLEX_V2 -->
EOF

# ---------------------------------------------------------------------------
# SCENARIO 1: fresh AGENTS.md, no marker at all -> first stamp.
# ---------------------------------------------------------------------------
echo ""
echo "=== SCENARIO 1: unmarked box gets stamped fresh (ASSERTION) ==="
a1="$WORK/AGENTS-1.md"
cat > "$a1" <<'EOF'
# Agent Instructions

Some preceding content.
EOF
v1="$(python3 "$CMP" "$a1" "$WORK/rendered-new.txt")"
if [ "$v1" = "stamped" ] && grep -q "MANDATORY" "$a1" && grep -q "Some preceding content" "$a1"; then
  ok "unmarked box: stamped (verdict=$v1), new body present, trailing content preserved"
else
  bad "unmarked box: expected verdict=stamped with new body (verdict=$v1)"
fi

# ---------------------------------------------------------------------------
# SCENARIO 2 (THE BUG, PROVEN FIXED): box already V2-stamped with the OLD
# body must re-stamp when compared against a template whose body changed.
# ---------------------------------------------------------------------------
echo ""
echo "=== SCENARIO 2: V2-stamped-with-OLD-body box re-stamps on content diff (ASSERTION) ==="
a2="$WORK/AGENTS-2.md"
cat "$WORK/rendered-old.txt" > "$a2"
printf '\n# Agent Instructions\n\nSome preceding content.\n' >> "$a2"
before_sha2="$(shasum -a 256 "$a2" | awk '{print $1}')"
v2="$(python3 "$CMP" "$a2" "$WORK/rendered-new.txt")"
if [ "$v2" = "restamped" ] && grep -q "MANDATORY" "$a2" && ! grep -q "old body" "$a2"; then
  ok "old-body box: re-stamped (verdict=$v2), new (chat-id) content now present, old body gone"
else
  bad "old-body box: expected verdict=restamped with new content landed (verdict=$v2)"
  echo "  --- resulting file ---"; sed 's/^/    /' "$a2"
fi

# ---------------------------------------------------------------------------
# SCENARIO 3 (CONTROL): second run on the now-current box is a byte-
# identical no-op.
# ---------------------------------------------------------------------------
echo ""
echo "=== SCENARIO 3: already-current box is a byte-identical no-op (CONTROL) ==="
before_sha3="$(shasum -a 256 "$a2" | awk '{print $1}')"
v3="$(python3 "$CMP" "$a2" "$WORK/rendered-new.txt")"
after_sha3="$(shasum -a 256 "$a2" | awk '{print $1}')"
if [ "$v3" = "noop" ] && [ "$before_sha3" = "$after_sha3" ]; then
  ok "already-current box: second run is a byte-identical no-op (verdict=noop)"
else
  bad "already-current box: expected verdict=noop and unchanged bytes (verdict=$v3, sha before=$before_sha3 after=$after_sha3)"
fi

# ---------------------------------------------------------------------------
# SCENARIO 4: a stray V1 marker co-existing with a byte-identical V2 body
# must still force a re-stamp (cleanup), never a no-op.
# ---------------------------------------------------------------------------
echo ""
echo "=== SCENARIO 4: stray V1 co-existing with current V2 forces cleanup (ASSERTION) ==="
a4="$WORK/AGENTS-4.md"
cat > "$a4" <<'EOF'
<!-- PRESENTATION_ROUTING_REFLEX_V1 -->
# Old V1 body
<!-- END PRESENTATION_ROUTING_REFLEX_V1 -->

<!-- PRESENTATION_ROUTING_REFLEX_V2 -->
# REFLEX 0 (new body, WITH chat-id text)

Route the task now via the helper.
The chat id is MANDATORY when you have it.
<!-- END PRESENTATION_ROUTING_REFLEX_V2 -->

# Agent Instructions
EOF
v4="$(python3 "$CMP" "$a4" "$WORK/rendered-new.txt")"
if [ "$v4" = "restamped" ] && ! grep -q "PRESENTATION_ROUTING_REFLEX_V1" "$a4" && grep -c "PRESENTATION_ROUTING_REFLEX_V2" "$a4" | grep -qx 2; then
  ok "stray V1 + current V2: forced re-stamp (verdict=$v4), V1 fully removed, exactly one V2 pair remains"
else
  bad "stray V1 + current V2: expected verdict=restamped with V1 removed (verdict=$v4)"
  echo "  --- resulting file ---"; sed 's/^/    /' "$a4"
fi

# ---------------------------------------------------------------------------
# SCENARIO 5 (CONTROL): a box carrying ONLY a stray V1 (no V2 at all) must
# migrate to V2, not error.
# ---------------------------------------------------------------------------
echo ""
echo "=== SCENARIO 5: V1-only box migrates to V2 (CONTROL) ==="
a5="$WORK/AGENTS-5.md"
cat > "$a5" <<'EOF'
<!-- PRESENTATION_ROUTING_REFLEX_V1 -->
# Old V1 body
<!-- END PRESENTATION_ROUTING_REFLEX_V1 -->

# Agent Instructions
EOF
v5="$(python3 "$CMP" "$a5" "$WORK/rendered-new.txt")"
if [ "$v5" = "migrated" ] && grep -q "MANDATORY" "$a5" && ! grep -q "PRESENTATION_ROUTING_REFLEX_V1" "$a5"; then
  ok "V1-only box: migrated to V2 (verdict=$v5), new content present, V1 gone"
else
  bad "V1-only box: expected verdict=migrated (verdict=$v5)"
fi

echo ""
echo "============================================================"
echo "RESULT: $PASS passed, $FAIL failed"
echo "============================================================"
[ "$FAIL" -eq 0 ]
