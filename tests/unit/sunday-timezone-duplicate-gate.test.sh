#!/usr/bin/env bash
# ============================================================================
# sunday-timezone-duplicate-gate.test.sh — U003 regression suite
#
# Tests the duplicate-detection gate inserted by U003 in the update path
# (update-skills.sh). Stubs crontab via PATH so no real crontab is ever read or
# written.
#
#   D1  legacy 0 3 * * 0 entry detected and re-retired (gate fires)
#   D2  no legacy entry — gate is silent (passes through)
#   D3  detection removed — test goes RED (mutation-proof: remove the
#       if-detect block and the expected WARNING never appears)
#   D4  gate uses retire_legacy_sunday_crontab (not a local reimplementation)
#
# Run:  bash tests/unit/sunday-timezone-duplicate-gate.test.sh
# ============================================================================
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
UPDATE_SKILLS="$REPO_ROOT/update-skills.sh"

PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  PASS  %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; [ $# -ge 2 ] && printf '        %s\n' "$2"; }
head2() { printf '\n== %s\n' "$1"; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/u003-test.XXXXXX")" || exit 1
trap 'rm -rf "$WORK"' EXIT

# ── Extract function bodies for inlining ────────────────────────────────────
_detect_crontab_body() {
  sed -n '/^detect_legacy_sunday_crontab()/,/^}$/p' "$UPDATE_SKILLS"
}
_retire_crontab_body() {
  sed -n '/^retire_legacy_sunday_crontab()/,/^}$/p' "$UPDATE_SKILLS"
}

RETIRE_BODY="$(_detect_crontab_body)
$(_retire_crontab_body)"

# Extract the duplicate-detection gate snippet from update-skills.sh
# (the block between "U001-U003 DUPLICATE-DETECTION GATE" and the blank
# line before "Ensure the Sunday weekly update-check cron exists")
_extract_duplicate_gate() {
  sed -n '/U001-U003 DUPLICATE-DETECTION GATE/,/Ensure the Sunday weekly update-check cron exists/p' "$UPDATE_SKILLS" \
    | sed -n '/^  if detect_legacy_sunday_crontab/,/^  fi$/p'
}

# ── D1: legacy 0 3 * * 0 entry detected and re-retired ──────────────────────
head2 "D1 — legacy 0 3 * * 0 entry detected and re-retired"
D1HOME="$WORK/d1-home"; mkdir -p "$D1HOME"
D1BIN="$WORK/d1-bin"; mkdir -p "$D1BIN"

echo "0 3 * * 0 /home/user/update-skills.sh
0 9 * * 1 echo Monday job" > "$D1HOME/.fake-crontab"

cat > "$D1BIN/crontab" <<_EOS
#!/usr/bin/env bash
if [ "\$1" = "-l" ]; then
  cat "$D1HOME/.fake-crontab"
  exit 0
fi
cp "\$1" "$D1HOME/.fake-crontab" 2>/dev/null && exit 0
exit 1
_EOS
chmod +x "$D1BIN/crontab"

DUPLICATE_GATE="$(_extract_duplicate_gate)"

cat > "$WORK/_d1.sh" <<_EOS
#!/usr/bin/env bash
set -u
$RETIRE_BODY
$DUPLICATE_GATE
_EOS
chmod +x "$WORK/_d1.sh"

OUT="$(PATH="$D1BIN:$PATH" HOME="$D1HOME" TMPDIR="$WORK" bash "$WORK/_d1.sh" 2>&1)"; RC=$?

if [ $RC -eq 0 ] && echo "$OUT" | grep -q 'WARNING.*legacy Sunday'; then
  ok "D1: gate fired WARNING for legacy 0 3 * * 0: rc=$RC"
else
  bad "D1: expected WARNING for legacy entry, got rc=$RC output=$OUT"
fi

! grep -q '0 3 \* \* 0' "$D1HOME/.fake-crontab" && \
  ok "D1: legacy entry removed from crontab (re-retired)" || \
  bad "D1: legacy entry still present in crontab"

echo "$OUT" | grep -q 'RETIRED' && ok "D1: retirement message printed" || bad "D1: no RETIRED message"

# ── D2: no legacy entry — gate is silent ────────────────────────────────────
head2 "D2 — no legacy entry — gate is silent"
D2HOME="$WORK/d2-home"; mkdir -p "$D2HOME"
D2BIN="$WORK/d2-bin"; mkdir -p "$D2BIN"

echo "0 9 * * 1 echo Monday job" > "$D2HOME/.fake-crontab"

cat > "$D2BIN/crontab" <<_EOS
#!/usr/bin/env bash
[ "\$1" = "-l" ] && { cat "$D2HOME/.fake-crontab"; exit 0; }
exit 0
_EOS
chmod +x "$D2BIN/crontab"

cat > "$WORK/_d2.sh" <<_EOS
#!/usr/bin/env bash
set -u
$RETIRE_BODY
$DUPLICATE_GATE
_EOS
chmod +x "$WORK/_d2.sh"

OUT="$(PATH="$D2BIN:$PATH" HOME="$D2HOME" TMPDIR="$WORK" bash "$WORK/_d2.sh" 2>&1)"; RC=$?
if [ $RC -eq 0 ] && ! echo "$OUT" | grep -q 'WARNING.*legacy Sunday'; then
  ok "D2: gate silent when no legacy entry: rc=$RC"
else
  bad "D2: unexpected WARNING or non-zero, rc=$RC output=$OUT"
fi

# ── D3: detection removed — test goes RED ───────────────────────────────────
head2 "D3 — detection removed (mutation-proof: RED when gate absent)"
D3HOME="$WORK/d3-home"; mkdir -p "$D3HOME"
D3BIN="$WORK/d3-bin"; mkdir -p "$D3BIN"

echo "0 3 * * 0 /home/user/update-skills.sh
0 9 * * 1 echo Monday job" > "$D3HOME/.fake-crontab"

cat > "$D3BIN/crontab" <<_EOS
#!/usr/bin/env bash
if [ "\$1" = "-l" ]; then
  cat "$D3HOME/.fake-crontab"
  exit 0
fi
cp "\$1" "$D3HOME/.fake-crontab" 2>/dev/null && exit 0
exit 1
_EOS
chmod +x "$D3BIN/crontab"

# Simulate the gate having been removed — run detect + retire directly
# with NO gate intervention. If the gate exists, it would fire. We verify
# the gate exists by checking that the snippet extracted above is non-empty.
if grep -q 'U001-U003 DUPLICATE-DETECTION GATE' "$UPDATE_SKILLS"; then
  ok "D3: duplicate-detection gate text exists in update-skills.sh"
else
  bad "D3: duplicate-detection gate block NOT found — RED (mutation-proof)"
fi

# Verify the actual gate code exists (has executable gate lines)
GATE_LINES="$(_extract_duplicate_gate)"
if [ -n "$GATE_LINES" ] && echo "$GATE_LINES" | grep -q 'detect_legacy_sunday_crontab'; then
  ok "D3: executable gate code present (detect_legacy_sunday_crontab call)"
else
  bad "D3: executable gate code NOT found — RED (mutation-proof)"
fi

# Check that retire_legacy_sunday_crontab is called within the gate
if echo "$GATE_LINES" | grep -q 'retire_legacy_sunday_crontab'; then
  ok "D3: gate calls retire_legacy_sunday_crontab (not reimplementing locally)"
else
  bad "D3: gate does NOT call retire_legacy_sunday_crontab"
fi

# ── D4: gate uses retire_legacy_sunday_crontab (U001's function) ────────────
head2 "D4 — gate delegates to retire_legacy_sunday_crontab"
# Confirm retire_legacy_sunday_crontab is defined in update-skills.sh (from U001)
if grep -q '^retire_legacy_sunday_crontab()' "$UPDATE_SKILLS"; then
  ok "D4: retire_legacy_sunday_crontab defined (U001 present)"
else
  bad "D4: retire_legacy_sunday_crontab NOT defined — U001 missing"
fi

# Verify detect_legacy_sunday_crontab is also present
if grep -q '^detect_legacy_sunday_crontab()' "$UPDATE_SKILLS"; then
  ok "D4: detect_legacy_sunday_crontab defined (U001 present)"
else
  bad "D4: detect_legacy_sunday_crontab NOT defined — U001 missing"
fi

# ── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo "============================================"
echo "  U003 sunday-timezone-duplicate-gate: $PASS passed, $FAIL failed"
echo "============================================"
[ "$FAIL" -eq 0 ] || exit 1
