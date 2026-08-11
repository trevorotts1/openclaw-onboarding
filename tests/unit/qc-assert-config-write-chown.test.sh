#!/usr/bin/env bash
# tests/unit/qc-assert-config-write-chown.test.sh
#
# CI guard: verifies scripts/qc-assert-config-write-chown.sh's BASELINE MODE
# (--write-baseline / default / --strict), added to make an already-correct
# gate adoptable against pre-existing debt instead of landing RED on day one.
# A gate that is RED when it lands either blocks all unrelated work or gets
# bypassed with --no-verify, and within a week everyone ignores it -- the
# same failure mode as a test that fails for a property of its host, not a
# real defect. The baseline exists so pre-existing findings are known debt
# (INFO, non-blocking) while a genuinely NEW unguarded write still fails the
# build immediately.
#
# Assertion groups -- each against a THROWAWAY fixture repo under a temp dir
# (never the real repo, never a live gateway):
#   (1) BASELINED_ONLY -- a repo whose only finding is in the baseline -> 0
#   (2) NEW_VIOLATION  -- that repo plus ONE NEW unguarded write -> 1, and
#                          the output names the new finding by file:line and
#                          tags it NEW VIOLATION, while the pre-existing
#                          finding is still tagged KNOWN DEBT alongside it.
#                          THIS IS THE ASSERTION THAT MATTERS MOST: it proves
#                          the baseline suppresses old debt WITHOUT blinding
#                          the gate to a genuinely new fault of the exact
#                          class this gate exists to catch.
#   (3) MISSING_BASELINE -- no baseline.txt at all -> 3 (UNDETERMINED),
#                          never 0 -- an absent instrument must never read
#                          as a clean sweep.
#   (4) STRICT_IGNORES_BASELINE -- --strict fails even on a fully-baselined
#                          repo (baseline written, then ignored on purpose).
#   (5) FIXED_NOT_BROKEN -- a baselined finding that has since been fixed
#                          (a chown restore added, in the SAME file, same
#                          write line) -> still exit 0, and the resolved
#                          baseline entry is reported as INFO. Fixing
#                          something must never break the build.
#   (6) COUNT_AWARE_BYPASS_REGRESSION -- THE ASSERTION THAT MATTERS MOST.
#                          A confirmed bypass: the baseline key alone (no
#                          count) collapsed every IDENTICAL literal line in
#                          one file onto ONE entry, so a file with N
#                          identical unguarded writes recorded N as "1
#                          known debt", and a genuinely NEW (N+1)th
#                          identical write was silently accepted as already
#                          covered. This baselines N=2 identical writes,
#                          confirms exit 0, then adds a 3rd identical line
#                          and requires exit 1, with the message naming the
#                          file and both counts. If this ever regresses back
#                          to exit 0, the bypass is open again.
#   (7) COUNT_DECREASE -- removing one of N baselined identical lines (count
#                          drops but stays > 0) -> exit 0, reported as
#                          "partially resolved". Fixing something must never
#                          break the build, even partially.
#   (8) LEGACY_BASELINE_NO_COUNT -- a baseline line written before the
#                          count-aware format existed (no <TAB><count>
#                          field) is read as count=1, not unbounded and not
#                          a crash, with an INFO advisory to upgrade the
#                          file. A second identical occurrence appearing
#                          against that implied count of 1 -> exit 1.
#
# Every case runs the REAL gate script (scripts/qc-assert-config-write-chown.sh)
# against a fixture via --repo-root -- never a re-implementation of its
# detection logic.
#
# Run: bash tests/unit/qc-assert-config-write-chown.test.sh
# Exit 0 = all checks pass. Exit 1 = one or more checks failed.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATE="$REPO_ROOT/scripts/qc-assert-config-write-chown.sh"

PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== qc-assert-config-write-chown.test.sh ==="
echo ""

if [[ ! -f "$GATE" ]]; then
  echo "FATAL: scripts/qc-assert-config-write-chown.sh not found at $GATE" >&2
  exit 1
fi

SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/qc-config-write-chown-test.XXXXXX")"
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT

# make_fixture DIR -- a throwaway repo with exactly ONE unguarded config
# write (no chown, no trap, no opt-out marker) in scripts/demo-writer.sh.
make_fixture() {
  local dir="$1"
  mkdir -p "$dir/scripts"
  cat > "$dir/scripts/demo-writer.sh" <<'EOF'
#!/usr/bin/env bash
# throwaway fixture -- not wired into anything real
openclaw config set agents.defaults.demo.setting true
EOF
}

baseline_path() { printf '%s/tests/fixtures/qc-assert-config-write-chown/baseline.txt' "$1"; }

# make_fixture_n_identical DIR N -- a throwaway repo whose only findings are
# N verbatim-identical unguarded config writes (no chown, no trap, no
# opt-out marker) in scripts/demo-writer.sh -- the exact shape of the
# confirmed bypass (identical lines collapsing onto one baseline key).
make_fixture_n_identical() {
  local dir="$1" n="$2" i
  mkdir -p "$dir/scripts"
  {
    echo '#!/usr/bin/env bash'
    echo '# throwaway fixture -- N identical unguarded writes, no chown, no trap'
    for ((i = 0; i < n; i++)); do
      echo 'openclaw config set agents.defaults.demo.repeated true'
    done
  } > "$dir/scripts/demo-writer.sh"
}

# ---------------------------------------------------------------------------
# (1) BASELINED_ONLY: a repo whose only finding is captured in the baseline
# ---------------------------------------------------------------------------
echo "--- (1) BASELINED_ONLY: fixture's only finding is baselined -> exit 0 ---"

FIX1="$SANDBOX/case1"
make_fixture "$FIX1"

bash "$GATE" --repo-root "$FIX1" --write-baseline --quiet >/dev/null 2>&1
wb_rc=$?
if [[ "$wb_rc" -eq 0 ]]; then
  pass "1a: --write-baseline exits 0"
else
  fail "1a: --write-baseline exited $wb_rc, expected 0"
fi

BASE1="$(baseline_path "$FIX1")"
if [[ ! -f "$BASE1" ]]; then
  fail "1b: --write-baseline did not create baseline.txt at $BASE1"
else
  entries1="$(grep -v '^[[:space:]]*#' "$BASE1" | grep -cv '^[[:space:]]*$')"
  if [[ "$entries1" -eq 1 ]]; then
    pass "1b: baseline.txt has exactly 1 entry (the one seeded finding)"
  else
    fail "1b: baseline.txt has $entries1 entries, expected 1"
  fi
fi

out1="$(bash "$GATE" --repo-root "$FIX1" 2>&1)"
rc1=$?
if [[ "$rc1" -eq 0 ]]; then
  pass "1c: default mode on a fully-baselined fixture exits 0"
else
  fail "1c: default mode exited $rc1 (expected 0). Output: $out1"
fi
if printf '%s\n' "$out1" | grep -q 'KNOWN DEBT'; then
  pass "1d: the baselined finding is reported as KNOWN DEBT"
else
  fail "1d: expected a KNOWN DEBT line in output, not found. Output: $out1"
fi

# ---------------------------------------------------------------------------
# (2) NEW_VIOLATION -- most important assertion: baseline + one genuinely
#     new unguarded write -> exit 1, and the output names the new finding
# ---------------------------------------------------------------------------
echo ""
echo "--- (2) NEW_VIOLATION: same repo + ONE new unguarded write -> exit 1, names it ---"

FIX2="$SANDBOX/case2"
make_fixture "$FIX2"
bash "$GATE" --repo-root "$FIX2" --write-baseline --quiet >/dev/null 2>&1

cat >> "$FIX2/scripts/demo-writer.sh" <<'EOF'
openclaw config set agents.defaults.demo.brandNewSetting enabled
EOF

# Determine the actual line numbers dynamically -- never hardcode them, so
# this test does not silently stop testing anything if the fixture content
# above ever shifts.
orig_lineno="$(grep -n 'demo\.setting true' "$FIX2/scripts/demo-writer.sh" | head -1 | cut -d: -f1)"
new_lineno="$(grep -n 'brandNewSetting' "$FIX2/scripts/demo-writer.sh" | head -1 | cut -d: -f1)"

out2="$(bash "$GATE" --repo-root "$FIX2" 2>&1)"
rc2=$?
if [[ "$rc2" -eq 1 ]]; then
  pass "2a: default mode exits 1 with a new unguarded write present"
else
  fail "2a: default mode exited $rc2, expected 1. Output: $out2"
fi

new_line_out="$(printf '%s\n' "$out2" | grep "scripts/demo-writer.sh:${new_lineno} ")"
if [[ -n "$new_line_out" ]] && printf '%s' "$new_line_out" | grep -q 'NEW VIOLATION'; then
  pass "2b: output names scripts/demo-writer.sh:${new_lineno} and tags it NEW VIOLATION"
else
  fail "2b: expected a NEW VIOLATION line for scripts/demo-writer.sh:${new_lineno}. Output: $out2"
fi

orig_line_out="$(printf '%s\n' "$out2" | grep "scripts/demo-writer.sh:${orig_lineno} ")"
if [[ -n "$orig_line_out" ]] && printf '%s' "$orig_line_out" | grep -q 'KNOWN DEBT'; then
  pass "2c: the ORIGINAL baselined finding (line ${orig_lineno}) is still KNOWN DEBT, not swept up as new"
else
  fail "2c: the original baselined finding was not reported as KNOWN DEBT alongside the new one. Output: $out2"
fi

if printf '%s\n' "$out2" | grep -q '^\[qc-config-write-chown\] FAIL  1 NEW config write'; then
  pass "2d: summary reports exactly 1 new violation"
else
  fail "2d: summary did not report exactly 1 new violation. Output: $out2"
fi

# ---------------------------------------------------------------------------
# (3) MISSING_BASELINE -- no baseline.txt at all -> exit 3, never 0
# ---------------------------------------------------------------------------
echo ""
echo "--- (3) MISSING_BASELINE: no baseline file -> exit 3 (UNDETERMINED) ---"

FIX3="$SANDBOX/case3"
make_fixture "$FIX3"
# Deliberately do NOT run --write-baseline for this fixture.

out3="$(bash "$GATE" --repo-root "$FIX3" 2>&1)"
rc3=$?
if [[ "$rc3" -eq 3 ]]; then
  pass "3a: default mode with no baseline file exits 3"
else
  fail "3a: default mode with no baseline file exited $rc3, expected 3. Output: $out3"
fi
if [[ "$rc3" -eq 0 ]]; then
  fail "3b: CRITICAL -- missing baseline must never exit 0 (silent pass)"
else
  pass "3b: missing baseline did not silently pass (exit != 0)"
fi
if printf '%s\n' "$out3" | grep -q 'UNDETERMINED'; then
  pass "3c: output is tagged UNDETERMINED"
else
  fail "3c: output did not contain an UNDETERMINED tag. Output: $out3"
fi

# ---------------------------------------------------------------------------
# (4) STRICT_IGNORES_BASELINE -- --strict fails even on baselined findings
# ---------------------------------------------------------------------------
echo ""
echo "--- (4) STRICT_IGNORES_BASELINE: --strict fails on a fully-baselined repo ---"

FIX4="$SANDBOX/case4"
make_fixture "$FIX4"
bash "$GATE" --repo-root "$FIX4" --write-baseline --quiet >/dev/null 2>&1

out4="$(bash "$GATE" --repo-root "$FIX4" --strict 2>&1)"
rc4=$?
if [[ "$rc4" -eq 1 ]]; then
  pass "4a: --strict exits 1 on a repo whose only finding is baselined"
else
  fail "4a: --strict exited $rc4, expected 1. Output: $out4"
fi
if printf '%s\n' "$out4" | grep -q 'FAIL.*scripts/demo-writer.sh'; then
  pass "4b: --strict output names the baselined-but-still-failing finding as FAIL"
else
  fail "4b: --strict output did not FAIL demo-writer.sh. Output: $out4"
fi
if printf '%s\n' "$out4" | grep -q 'KNOWN DEBT'; then
  fail "4c: --strict output must not classify anything as KNOWN DEBT (baseline must be ignored)"
else
  pass "4c: --strict output contains no KNOWN DEBT classification (baseline genuinely ignored)"
fi

# ---------------------------------------------------------------------------
# (5) FIXED_NOT_BROKEN -- a baselined finding that has since been fixed
#     (a chown restore added) must NOT break the build
# ---------------------------------------------------------------------------
echo ""
echo "--- (5) FIXED_NOT_BROKEN: baselined finding fixed -> still exit 0 ---"

FIX5="$SANDBOX/case5"
make_fixture "$FIX5"
bash "$GATE" --repo-root "$FIX5" --write-baseline --quiet >/dev/null 2>&1

# Same write line as the baselined one, now with a recognized ownership
# restore added elsewhere in the file -- this is what "fixed" looks like.
cat > "$FIX5/scripts/demo-writer.sh" <<'EOF'
#!/usr/bin/env bash
# throwaway fixture -- now carries an ownership restore for the same write
openclaw config set agents.defaults.demo.setting true
chown 1000:1000 "$OC_CONFIG" 2>/dev/null || true
EOF

out5="$(bash "$GATE" --repo-root "$FIX5" 2>&1)"
rc5=$?
if [[ "$rc5" -eq 0 ]]; then
  pass "5a: fixing the baselined finding still exits 0"
else
  fail "5a: exited $rc5 after fixing the baselined finding (expected 0 -- fixing must never break the build). Output: $out5"
fi
if printf '%s\n' "$out5" | grep -q 'baseline entry resolved'; then
  pass "5b: output reports the baseline entry as resolved"
else
  fail "5b: output did not report a resolved baseline entry. Output: $out5"
fi

# ---------------------------------------------------------------------------
# (6) COUNT_AWARE_BYPASS_REGRESSION -- THE ASSERTION THAT MATTERS MOST: a
#     file with N identical unguarded writes, baselined; add ONE more
#     identical line -> gate exits 1, message names the file and both
#     counts. This is the exact reproduction of the confirmed bypass; if
#     count-awareness is ever reverted, this is the check that must fail.
# ---------------------------------------------------------------------------
echo ""
echo "--- (6) COUNT_AWARE_BYPASS_REGRESSION: N=2 identical writes baselined, add ONE more -> exit 1 ---"

FIX6="$SANDBOX/case6"
make_fixture_n_identical "$FIX6" 2
bash "$GATE" --repo-root "$FIX6" --write-baseline --quiet >/dev/null 2>&1

BASE6="$(baseline_path "$FIX6")"
baselined_count6="$(grep -F 'demo-writer.sh::openclaw config set agents.defaults.demo.repeated true' "$BASE6" | cut -f2)"
if [[ "$baselined_count6" == "2" ]]; then
  pass "6a: baseline records count=2 for the 2 identical occurrences (not 1 -- the bug this closes)"
else
  fail "6a: expected baselined count 2, got '$baselined_count6'. baseline file:
$(cat "$BASE6")"
fi

out6_before="$(bash "$GATE" --repo-root "$FIX6" 2>&1)"
rc6_before=$?
if [[ "$rc6_before" -eq 0 ]]; then
  pass "6b: default mode on the freshly-baselined N=2 fixture exits 0"
else
  fail "6b: default mode exited $rc6_before before adding a 3rd line (expected 0). Output: $out6_before"
fi

# The exact reproduction: add a THIRD verbatim-identical line.
cat >> "$FIX6/scripts/demo-writer.sh" <<'EOF'
openclaw config set agents.defaults.demo.repeated true
EOF

out6="$(bash "$GATE" --repo-root "$FIX6" 2>&1)"
rc6=$?
if [[ "$rc6" -eq 1 ]]; then
  pass "6c: THE BYPASS REGRESSION CHECK -- a 3rd identical occurrence beyond the baselined count of 2 exits 1"
else
  fail "6c: CRITICAL REGRESSION -- a 3rd identical occurrence exited $rc6, expected 1. If this is 0, count-awareness has regressed and the bypass this unit closed is open again. Output: $out6"
fi

if printf '%s\n' "$out6" | grep -q 'demo-writer.sh' && printf '%s\n' "$out6" | grep -q '3 occurrence(s), baseline allows 2'; then
  pass "6d: message names the file and both counts (3 occurrence(s), baseline allows 2)"
else
  fail "6d: expected a message naming the file and both counts ('3 occurrence(s), baseline allows 2'). Output: $out6"
fi

# ---------------------------------------------------------------------------
# (7) COUNT_DECREASE -- removing one of N identical baselined lines (count
#     drops but stays > 0) must NOT break the build.
# ---------------------------------------------------------------------------
echo ""
echo "--- (7) COUNT_DECREASE: removing one of N identical lines (count decreases) -> exit 0 ---"

FIX7="$SANDBOX/case7"
make_fixture_n_identical "$FIX7" 3
bash "$GATE" --repo-root "$FIX7" --write-baseline --quiet >/dev/null 2>&1

# Remove ONE of the 3 identical lines -- 2 remain (still > 0).
{
  echo '#!/usr/bin/env bash'
  echo '# throwaway fixture -- one of 3 identical writes has been removed'
  echo 'openclaw config set agents.defaults.demo.repeated true'
  echo 'openclaw config set agents.defaults.demo.repeated true'
} > "$FIX7/scripts/demo-writer.sh"

out7="$(bash "$GATE" --repo-root "$FIX7" 2>&1)"
rc7=$?
if [[ "$rc7" -eq 0 ]]; then
  pass "7a: removing one of N identical baselined lines (count decreases, still > 0) exits 0"
else
  fail "7a: exited $rc7 after removing one occurrence (expected 0 -- fixing must never break the build, even partially). Output: $out7"
fi
if printf '%s\n' "$out7" | grep -qi 'partially resolved'; then
  pass "7b: output reports the reduced count as partially resolved"
else
  fail "7b: expected a 'partially resolved' INFO line. Output: $out7"
fi

# ---------------------------------------------------------------------------
# (8) LEGACY_BASELINE_NO_COUNT -- a baseline line written before the
#     count-aware format existed (no <TAB><count> field) is read as
#     count=1 -- not unbounded, not skipped, not a crash -- and a second
#     identical occurrence against that implied count of 1 still fails.
# ---------------------------------------------------------------------------
echo ""
echo "--- (8) LEGACY_BASELINE_NO_COUNT: no-count baseline line treated as 1; 2nd occurrence -> exit 1 ---"

FIX8="$SANDBOX/case8"
make_fixture "$FIX8"
bash "$GATE" --repo-root "$FIX8" --write-baseline --quiet >/dev/null 2>&1
BASE8="$(baseline_path "$FIX8")"

# Downgrade the one real finding to the LEGACY format (strip the
# <TAB><count> field) to simulate a baseline written before count-awareness.
legacy_key="$(grep -v '^[[:space:]]*#' "$BASE8" | grep -v '^[[:space:]]*$' | head -1 | cut -f1)"
{
  grep '^#' "$BASE8"
  printf '%s\n' "$legacy_key"
} > "$BASE8.tmp"
mv "$BASE8.tmp" "$BASE8"

out8_legacy_only="$(bash "$GATE" --repo-root "$FIX8" 2>&1)"
rc8_legacy_only=$?
if [[ "$rc8_legacy_only" -eq 0 ]]; then
  pass "8a: a legacy (no-count) baseline entry matching the single observed occurrence still exits 0"
else
  fail "8a: exited $rc8_legacy_only against a legacy baseline with one matching occurrence (expected 0). Output: $out8_legacy_only"
fi
if printf '%s\n' "$out8_legacy_only" | grep -qi 'legacy'; then
  pass "8b: output advises upgrading the legacy baseline format (via --write-baseline)"
else
  fail "8b: expected an INFO advisory about the legacy baseline format. Output: $out8_legacy_only"
fi

# Add a SECOND identical occurrence -- the legacy entry's implied count=1
# is now exceeded.
cat >> "$FIX8/scripts/demo-writer.sh" <<'EOF'
openclaw config set agents.defaults.demo.setting true
EOF

out8="$(bash "$GATE" --repo-root "$FIX8" 2>&1)"
rc8=$?
if [[ "$rc8" -eq 1 ]]; then
  pass "8c: a legacy baseline entry (count=1 implied) is exceeded by a 2nd occurrence -> exit 1"
else
  fail "8c: exited $rc8 with a legacy baseline entry and 2 observed occurrences (expected 1). Output: $out8"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="

if [[ "$FAIL" -gt 0 ]]; then
  echo "FAIL: $FAIL check(s) failed -- CI guard triggered"
  exit 1
fi

echo "PASS: all qc-assert-config-write-chown baseline-mode checks pass"
exit 0
