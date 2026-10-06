#!/usr/bin/env bash
# bootstrap-pointerize.test.sh — the properties the lean-bootstrap fix must hold.
#
# Each test states the DEFECT it exists to catch, because every one of these was
# a real bug in the first cut of this feature, not a hypothetical.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENGINE="$REPO/scripts/bootstrap-pointerize.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "  ✓ PASS — $1"; }
fail() { FAIL=$((FAIL+1)); echo "  ✗ FAIL — $1"; }

echo "═══ bootstrap-pointerize — lean bootstrap stamping ═══"

command -v python3 >/dev/null 2>&1 || { echo "FATAL: python3 required"; exit 2; }
[ -f "$ENGINE" ] || { echo "FATAL: engine missing at $ENGINE"; exit 2; }

REF="$TMP/master-files/bootstrap-references/AGENTS.md"

_fixture() {
  cat > "$TMP/AGENTS.md" <<'EOF'
# Bootstrap

<!-- BEGIN skill:99-demo:agents -->
## Demo skill
This is the demo skill summary line that explains what the surface does.
NEVER send without reading the playbook first.
Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor.
Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut.
Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore.
Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia.
Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium.
Nemo enim ipsam voluptatem quia voluptas sit aspernatur aut odit aut fugit.
Neque porro quisquam est, qui dolorem ipsum quia dolor sit amet consectetur.
At vero eos et accusamus et iusto odio dignissimos ducimus qui blanditiis.
Temporibus autem quibusdam et aut officiis debitis aut rerum necessitatibus.
Nam libero tempore, cum soluta nobis est eligendi optio cumque nihil impedit.
<!-- END skill:99-demo:agents -->

<!-- SHARED_STANDARD_V1 -->
## Shared standard
The shared standard summary line describing the rule that every agent follows.
Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor.
Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut.
Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore.
Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia.
Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium.
Nemo enim ipsam voluptatem quia voluptas sit aspernatur aut odit aut fugit.
Neque porro quisquam est, qui dolorem ipsum quia dolor sit amet consectetur.
At vero eos et accusamus et iusto odio dignissimos ducimus qui blanditiis.
Temporibus autem quibusdam et aut officiis debitis aut rerum necessitatibus.

<!-- PAIRED_REFLEX_V2 -->
## Paired reflex
This block is owned by a writer that rewrites it wholesale on every roll.
Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor.
Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut.
Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore.
Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia.
Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium.
Nemo enim ipsam voluptatem quia voluptas sit aspernatur aut odit aut fugit.
Neque porro quisquam est, qui dolorem ipsum quia dolor sit amet consectetur.
At vero eos et accusamus et iusto odio dignissimos ducimus qui blanditiis.
<!-- END PAIRED_REFLEX_V2 -->

<!-- SMALL_ONE_V1 -->
## Small block
Short enough that pointerizing it would save nothing.
EOF
  rm -rf "$TMP/master-files"
}

# ── T1: a fat marker PAIR becomes a pointer, and the file shrinks ────────────
_fixture
BEFORE=$(wc -c < "$TMP/AGENTS.md")
python3 "$ENGINE" sweep --bootstrap "$TMP/AGENTS.md" --ref-file "$REF" >"$TMP/r1.json" 2>&1
AFTER=$(wc -c < "$TMP/AGENTS.md")
if [ "$AFTER" -lt "$BEFORE" ] && grep -q '\*\*Full text:\*\*' "$TMP/AGENTS.md"; then
  pass "a fat block is replaced by a pointer and the file shrinks ($BEFORE -> $AFTER bytes)"
else
  fail "no pointer written or file did not shrink ($BEFORE -> $AFTER bytes)"
fi

# ── T2: markers survive — every idempotency guard in the repo keys on them ───
if grep -q '<!-- BEGIN skill:99-demo:agents -->' "$TMP/AGENTS.md" &&
   grep -q '<!-- END skill:99-demo:agents -->' "$TMP/AGENTS.md" &&
   grep -q '<!-- SHARED_STANDARD_V1 -->' "$TMP/AGENTS.md"; then
  pass "BEGIN/END pair and bare sentinel are preserved"
else
  fail "a marker was destroyed — every idempotency guard keyed on it now breaks"
fi

# ── T3: DEFECT — the first cut swallowed an END marker on a paired sentinel ──
S=$(grep -c '<!-- PAIRED_REFLEX_V2 -->' "$TMP/AGENTS.md")
E=$(grep -c '<!-- END PAIRED_REFLEX_V2 -->' "$TMP/AGENTS.md")
if [ "$S" -eq 1 ] && [ "$E" -eq 1 ]; then
  pass "a sentinel that owns an END is left alone, pair intact (start=$S end=$E)"
else
  fail "paired sentinel corrupted (start=$S end=$E) — the END was swallowed"
fi

# ── T4: zero content loss — the full text is verbatim in the reference ───────
if [ -f "$REF" ] && grep -q 'Temporibus autem quibusdam' "$REF" &&
   grep -q 'Nam libero tempore' "$REF"; then
  pass "moved text is verbatim in the reference file"
else
  fail "moved text is NOT in the reference file — content was lost"
fi

# ── T5: the pointer names an ABSOLUTE path that EXISTS ──────────────────────
PTR_PATH="$(grep -m1 -o '\*\*Full text:\*\* [^ ]*' "$TMP/AGENTS.md" | awk '{print $3}')"
if [ -n "$PTR_PATH" ] && [ "${PTR_PATH#/}" != "$PTR_PATH" ] && [ -f "$PTR_PATH" ]; then
  pass "pointer names an absolute path that exists"
else
  fail "pointer target is relative or missing: ${PTR_PATH:-<none>}"
fi

# ── T6: idempotency — a second run must be a byte-for-byte no-op ────────────
cp "$TMP/AGENTS.md" "$TMP/after1.md"
python3 "$ENGINE" sweep --bootstrap "$TMP/AGENTS.md" --ref-file "$REF" >/dev/null 2>&1
RC=$?
if cmp -s "$TMP/after1.md" "$TMP/AGENTS.md" && [ "$RC" -eq 10 ]; then
  pass "second run is a byte-identical no-op (rc=10 unchanged)"
else
  fail "second run changed the file or reported written (rc=$RC)"
fi

# ── T7: a small block is left inline — a pointer would cost more than it saves ─
if grep -q '## Small block' "$TMP/AGENTS.md" &&
   grep -q 'Short enough that pointerizing it' "$TMP/AGENTS.md"; then
  pass "a block under the size floor stays inline verbatim"
else
  fail "a small block was pointerized — that makes the file bigger, not smaller"
fi

# ── T8: DEFECT — trigger extraction harvested mid-sentence prose fragments ───
# A line is kept inline only when it DECLARES a gate at its START. "Lorem ipsum"
# prose must never appear on the Triggers line.
if grep -q '\*\*Triggers:\*\*' "$TMP/AGENTS.md"; then
  if grep '\*\*Triggers:\*\*' "$TMP/AGENTS.md" | grep -qi 'lorem ipsum\|consectetur'; then
    fail "Triggers line harvested mid-sentence prose fragments"
  else
    pass "Triggers line carries only anchored gate declarations, no prose fragments"
  fi
else
  pass "no Triggers line emitted where no gate was declared"
fi

# ── T9: mode=full leaves everything verbatim ─────────────────────────────────
_fixture
BEFORE=$(wc -c < "$TMP/AGENTS.md")
OPENCLAW_BOOTSTRAP_POINTER_MODE=full python3 "$ENGINE" sweep \
  --bootstrap "$TMP/AGENTS.md" --ref-file "$REF" >/dev/null 2>&1
AFTER=$(wc -c < "$TMP/AGENTS.md")
if [ "$BEFORE" -eq "$AFTER" ]; then
  pass "mode=full is a no-op — the box-level override is honoured"
else
  fail "mode=full still modified the file ($BEFORE -> $AFTER)"
fi

# ── T10: FAIL-CLOSED — an unwritable reference must NOT leave a dangling pointer ─
_fixture
BLOCKED="$TMP/blocked"
mkdir -p "$BLOCKED"; chmod 500 "$BLOCKED"
BEFORE=$(wc -c < "$TMP/AGENTS.md")
python3 "$ENGINE" sweep --bootstrap "$TMP/AGENTS.md" \
  --ref-file "$BLOCKED/nested/AGENTS.md" >/dev/null 2>&1
AFTER=$(wc -c < "$TMP/AGENTS.md")
chmod 700 "$BLOCKED"
if [ "$BEFORE" -eq "$AFTER" ]; then
  pass "an unwritable reference refuses the stamp and leaves the file unchanged"
else
  fail "stamped a pointer to a reference it could not write ($BEFORE -> $AFTER)"
fi

echo ""
echo "═══ Result: $PASS passed | $FAIL failed ═══"
[ "$FAIL" -eq 0 ] || exit 1
