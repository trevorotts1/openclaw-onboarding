#!/usr/bin/env bash
# tests/unit/system-integrity-warning-promotion.test.sh
#
# U076 — the repository-scale integrity gate (scripts/qc-system-integrity.sh)
# reported PASS whenever $FAIL -eq 0 regardless of its warn-only call sites, so
# genuine breakage (symlink drift, a stranded legacy tree, a missing Mission
# Control DB) printed remediation text but could never affect the exit code. A
# box with a missing DB still reported "ALL CHECKS PASSED".
#
# THE FIX: promote the warnings that represent genuine breakage into the failure
# path (they now increment FAIL), and convert the warnings that mean
# "not-applicable" (workforce not built yet, cosmetic brand colors) into explicit
# not-applicable results via a new na() helper that increments NA, NOT WARN.
#
# Tests:
#   PART 1 (BEHAVIORAL) — extract the real counter/helper block from the script
#     and prove: na() increments NA and NOT WARN; a FAIL>0 makes the verdict fail
#     while WARN/NA alone do not.
#   PART 2 (SOURCE GUARD) — the genuine-breakage sites (2.3 drift, 2.14 legacy
#     tree, 7.0 missing DB) now use FAIL, and their old warn-only shapes are gone;
#     the not-applicable sites (2.6 stubs, 2.7 no-SOPs, 7.2 brand colors) now use
#     na(), and their old warn-only shapes are gone.
#   PART 3 (MUTATION PROOF) — revert the 7.0 missing-DB site to its old warn-only
#     shape -> the source guard turns RED; restore -> GREEN.
#
# Exit 0 = all checks pass. Exit 1 = one or more failed (CI FAIL).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/qc-system-integrity.sh"
PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== system-integrity-warning-promotion.test.sh ==="
[ -f "$SCRIPT" ] || { echo "FAIL: script not found at $SCRIPT"; exit 1; }

SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/u076-XXXXXX")"
trap 'rm -rf "$SANDBOX" 2>/dev/null || true' EXIT

# ─── PART 1: BEHAVIORAL — the real counter/helper block ──────────────────────
echo ""
echo "--- PART 1: na() increments NA (not WARN); FAIL alone fails the verdict ---"

# Extract the real helper block from the script: from the `PASS=0` counter line
# through the na() definition (the line carrying NA=$((NA+1))). This tests the
# ACTUAL shipped helpers, not a copy.
HELPERS="$SANDBOX/helpers.sh"
awk '
  /^PASS=0/            { grab=1 }
  grab                 { print }
  grab && /NA=\$\(\(NA\+1\)\)/ { exit }
' "$SCRIPT" > "$HELPERS"

if [ -s "$HELPERS" ] && grep -q 'NA=$((NA+1))' "$HELPERS"; then
  pass "PART 1: extracted the real counter/helper block (incl. na()) from the script"
else
  fail "PART 1: could not extract the helper block from the script"
fi

# Source the extracted helpers in a subshell and exercise the counters.
# qc_verdict lives in lib-qc-shared.sh (sourced by the real script at line 19),
# so source it here too to test the real verdict contract.
LIB_SHARED="$REPO_ROOT/lib-qc-shared.sh"
BEHAV="$(bash -c '
  set -u
  source "'"$HELPERS"'"
  source "'"$LIB_SHARED"'"
  # na() must bump NA and leave WARN untouched
  before_warn=$WARN
  na "synthetic not-applicable" >/dev/null
  if [ "$NA" = "1" ] && [ "$WARN" = "$before_warn" ]; then
    echo "NA_OK"
  else
    echo "NA_BAD NA=$NA WARN=$WARN"
  fi
  # the verdict contract: FAIL>0 fails; WARN/NA alone pass (QC_FAIL_ON_WARN unset)
  PASS=5; FAIL=0; WARN=3; NA=2
  QC_PASS=$PASS QC_FAIL=$FAIL QC_WARN=$WARN
  if qc_verdict "t" >/dev/null 2>&1; then echo "VERDICT_WARN_ONLY_PASS"; else echo "VERDICT_WARN_ONLY_FAIL"; fi
  FAIL=1
  QC_PASS=$PASS QC_FAIL=$FAIL QC_WARN=$WARN
  if qc_verdict "t" >/dev/null 2>&1; then echo "VERDICT_FAIL_PASS"; else echo "VERDICT_FAIL_FAIL"; fi
' 2>/dev/null)"

case "$BEHAV" in *NA_OK*) pass "PART 1: na() increments NA and does NOT increment WARN" ;;
                 *) fail "PART 1: na() counter behaviour wrong: $BEHAV" ;; esac
case "$BEHAV" in *VERDICT_WARN_ONLY_PASS*) pass "PART 1: warnings/NA alone do NOT fail the verdict (exit 0)" ;;
                 *) fail "PART 1: warn/NA-only run should pass: $BEHAV" ;; esac
case "$BEHAV" in *VERDICT_FAIL_FAIL*) pass "PART 1: a FAIL>0 fails the verdict (exit non-zero)" ;;
                 *) fail "PART 1: a FAIL>0 must fail the verdict: $BEHAV" ;; esac

# ─── PART 2: SOURCE GUARD — breakage promoted, N/A converted ─────────────────
echo ""
echo "--- PART 2: genuine-breakage sites use FAIL; not-applicable sites use na() ---"

# 2a. The genuine-breakage sites must increment FAIL (not WARN).
# 2.14 legacy tree: the FAIL arm must exist and the old warn-only shape must be gone.
if grep -q '2.14 Legacy tree(s) present' "$SCRIPT" && \
   grep -A1 '2.14 Legacy tree(s) present' "$SCRIPT" | grep -q 'FAIL=$((FAIL+1))'; then
  pass "PART 2: check 2.14 (stranded legacy tree) increments FAIL"
else
  fail "PART 2: check 2.14 (stranded legacy tree) does not increment FAIL"
fi
if grep -q 'yellow "  ⚠ 2.14 Legacy tree' "$SCRIPT"; then
  fail "PART 2: check 2.14 still has its old warn-only (yellow) shape"
else
  pass "PART 2: check 2.14 old warn-only shape removed"
fi

# 7.0 missing Mission Control DB: FAIL arm present, old warn-only shape gone.
if grep -A1 '7.0  Mission Control DB not found' "$SCRIPT" | grep -q 'FAIL=$((FAIL+1))'; then
  pass "PART 2: check 7.0 (missing Mission Control DB) increments FAIL"
else
  fail "PART 2: check 7.0 (missing Mission Control DB) does not increment FAIL"
fi
if grep -q 'yellow "  ⚠ 7.0  Mission Control DB not found' "$SCRIPT"; then
  fail "PART 2: check 7.0 still has its old warn-only (yellow) shape"
else
  pass "PART 2: check 7.0 old warn-only shape removed"
fi

# 2.3 mixed symlink drift: the drift arm must increment FAIL.
if grep -A1 'symlink drift detected' "$SCRIPT" | grep -q 'FAIL=$((FAIL+1))'; then
  pass "PART 2: check 2.3 (mixed symlink drift) increments FAIL"
else
  fail "PART 2: check 2.3 (mixed symlink drift) does not increment FAIL"
fi

# 2b. The not-applicable sites must use na() (not yellow/WARN).
for id_desc in \
  "2.6  \$STUBS SOP file(s) still contain stub placeholders" \
  "2.7  No SOPs found to check" \
  "7.2  No brand colors in DB"; do
  # na() prints "  ⊘ <desc>  (not applicable)" — match the description prefix on an na line.
  desc_core="$(printf '%s' "$id_desc" | sed 's/\\\$STUBS/$STUBS/')"
  if grep -F "na \"$desc_core" "$SCRIPT" >/dev/null 2>&1 || \
     grep -F "na \"${id_desc}" "$SCRIPT" >/dev/null 2>&1; then
    pass "PART 2: check ${id_desc%% *} uses na() (not-applicable)"
  else
    fail "PART 2: check ${id_desc%% *} does not use na()"
  fi
done

# The old warn-only shapes for the N/A sites must be gone.
if grep -q 'yellow "  ⚠ 2.6  \$STUBS SOP file' "$SCRIPT"; then
  fail "PART 2: check 2.6 still has its old warn-only (yellow) shape"
else
  pass "PART 2: check 2.6 old warn-only shape removed"
fi
if grep -q 'yellow "  ⚠ 7.2  No brand colors' "$SCRIPT"; then
  fail "PART 2: check 7.2 still has its old warn-only (yellow) shape"
else
  pass "PART 2: check 7.2 old warn-only shape removed"
fi

# ─── PART 3: MUTATION PROOF ──────────────────────────────────────────────────
echo ""
echo "--- PART 3: MUTATION PROOF — revert 7.0 to warn-only -> guard RED; restore -> GREEN ---"
MUT="$SANDBOX/qc-system-integrity.MUTATED.sh"
python3 - "$SCRIPT" "$MUT" <<'PY'
import sys
src, dst = sys.argv[1], sys.argv[2]
s = open(src).read()
# Revert the 7.0 missing-DB site to its PRE-FIX warn-only shape.
needle = '''  red "  ✗ 7.0  Mission Control DB not found — Skill 32 may not be installed"; FAIL=$((FAIL+1))
  FAILURES+=("7.0|Mission Control DB not found|Install Skill 32 or verify the mission-control.db path (~/projects/command-center or /opt/mission-control)")'''
repl = '''  yellow "  ⚠ 7.0  Mission Control DB not found — Skill 32 may not be installed"; WARN=$((WARN+1))'''
assert needle in s, "mutation target (7.0 FAIL arm) not found"
open(dst, "w").write(s.replace(needle, repl))
PY

# The PART-2 7.0 guard logic, run against an arbitrary script path.
guard_7_0() {
  local f="$1"
  grep -A1 '7.0  Mission Control DB not found' "$f" | grep -q 'FAIL=$((FAIL+1))'
}

if guard_7_0 "$MUT"; then
  fail "PART 3 RED: mutated (warn-only) script still passes the 7.0 FAIL guard — guard is not discriminating"
else
  pass "PART 3 RED: with 7.0 reverted to warn-only, the FAIL guard turns RED (mutation detected)"
fi
if guard_7_0 "$SCRIPT"; then
  pass "PART 3 GREEN: the real script passes the 7.0 FAIL guard (fix restored)"
else
  fail "PART 3 GREEN: the real script does not pass the 7.0 FAIL guard"
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -gt 0 ] && { echo "FAIL: $FAIL check(s) failed — CI guard triggered"; exit 1; }
echo "PASS: genuine-breakage warnings are promoted to FAIL; not-applicable warnings are na()"
exit 0
