#!/usr/bin/env bash
# ============================================================================
# installer-completeness-verification.test.sh
#
# Regression guard for INSTALLER-COMPLETENESS-V1. The ONE property this whole
# test exists for:
#
#     the installer may never emit a receipt (.onboarding-content-manifest.json)
#     asserting a digest for a skill it did not actually compare against the box,
#     and may never install from a source tree it has not proven complete.
#
# Every test is that property asked a different way.
#
#   T1  scope-honesty block PRESENT   — update-skills.sh carries the
#                                       MANIFEST-SCOPE-HONESTY block. Without it
#                                       a `--only` run silently reverts to
#                                       recording every skill in the release.
#   T2  skills{} is ONLY-filtered     — the manifest build loop applies the same
#                                       $ONLY_SKILLS prefix filter the copy loop
#                                       and the A3 gate apply. Asserted
#                                       BEHAVIOURALLY by executing the extracted
#                                       loop, not by grepping for a variable.
#   T3  full run keeps every skill    — with ONLY_SKILLS empty the same loop
#                                       records all non-archived skills, so the
#                                       fix cannot have narrowed normal runs.
#   T4  content_verified never lies   — a selective run sets content_verified to
#                                       "partial" and tree_sha to "partial";
#                                       a full run sets "true" and a real rollup.
#   T5  carry-forward, never invent   — the receipt writer merges the box's PRIOR
#                                       skills map under this run's entries, so
#                                       an out-of-scope skill keeps its last
#                                       genuinely-verified digest and is never
#                                       assigned a source digest it was not
#                                       checked against.
#   T6  A2 source-coverage block PRESENT — update-skills.sh carries the
#                                       A2-SOURCE-COVERAGE-ASSERTION block and no
#                                       longer swallows skill-content-hash.sh's
#                                       exit code with `|| true`.
#   T7  A2 catches a truncated manifest — a source dir present on disk but absent
#                                       from the computed manifest is detected.
#   T8  A2 passes a complete source   — the same check is silent when every
#                                       non-archived numbered dir is covered.
#   T9  A4 uses the canonical hasher  — check-updates.sh prefers
#                                       skill-content-hash.sh so both sides of
#                                       the drift comparison share one exclusion
#                                       list, and treats content_verified!=true
#                                       as drift.
#
# Self-contained: bash + coreutils + python3. Temp dirs only. No box, no
# network, no installer is ever executed.
#
# Run:  bash tests/unit/installer-completeness-verification.test.sh
# ============================================================================
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
UPDATE_SKILLS="$REPO_ROOT/update-skills.sh"
CHECK_UPDATES="$REPO_ROOT/check-updates.sh"

PASS=0
FAIL=0
ok()   { PASS=$((PASS+1)); echo "  ok   — $1"; }
bad()  { FAIL=$((FAIL+1)); echo "  FAIL — $1"; }
check(){ if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (want '$3', got '$2')"; fi; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "== INSTALLER-COMPLETENESS-V1 =="

# ---------------------------------------------------------------- T1
if grep -q 'MANIFEST-SCOPE-HONESTY-BEGIN' "$UPDATE_SKILLS" \
   && grep -q 'MANIFEST-SCOPE-HONESTY-END' "$UPDATE_SKILLS"; then
  ok "T1 scope-honesty block present in update-skills.sh"
else
  bad "T1 scope-honesty block MISSING from update-skills.sh"
fi

# ---------------------------------------------------------------- T2/T3
# Extract the real manifest-build loop and run it against a synthetic manifest.
# Extracting (rather than reimplementing) is what makes this a guard: if the
# loop in update-skills.sh loses its filter, this test fails.
sed -n '/MANIFEST-SCOPE-HONESTY-BEGIN/,/MANIFEST-SCOPE-HONESTY-END/p' \
    "$UPDATE_SKILLS" > "$TMP/scope-block.sh"
if [ ! -s "$TMP/scope-block.sh" ]; then
  bad "T2/T3/T4 could not extract the scope-honesty block — skipping behavioural tests"
else
  run_block() {
    # $1 = ONLY_SKILLS value
    ONLY_SKILLS="$1" SRC_MANIFEST="$SRC_MANIFEST_FIXTURE" bash -c '
      set -uo pipefail
      _SKILLS_JSON=""
      _TREE_SHA="unknown"
      _CONTENT_VERIFIED="true"
      _VERIFIED_SCOPE="full"
      source "'"$TMP"'/scope-block.sh" >/dev/null 2>&1
      printf "%s\n%s\n%s\n%s\n" "$_SKILLS_JSON" "$_CONTENT_VERIFIED" "$_TREE_SHA" "$_VERIFIED_SCOPE"
    '
  }
  SRC_MANIFEST_FIXTURE="$(printf '%s\n' \
    '01-teach-yourself-protocol|aaa' \
    '23-ai-workforce-blueprint|bbb' \
    '32-command-center-setup|ccc' \
    '33-department-heads-ARCHIVED|ddd' \
    '47-movie-producer|eee' \
    '__TREE_SHA__|rollup123')"
  export SRC_MANIFEST_FIXTURE

  OUT_ONLY="$(run_block '23,32')"
  JSON_ONLY="$(printf '%s\n' "$OUT_ONLY" | sed -n '1p')"
  CV_ONLY="$(printf '%s\n' "$OUT_ONLY" | sed -n '2p')"
  TS_ONLY="$(printf '%s\n' "$OUT_ONLY" | sed -n '3p')"

  case "$JSON_ONLY" in
    *'"23-ai-workforce-blueprint"'*) _t2a=yes ;; *) _t2a=no ;;
  esac
  case "$JSON_ONLY" in
    *'"32-command-center-setup"'*) _t2b=yes ;; *) _t2b=no ;;
  esac
  case "$JSON_ONLY" in
    *'47-movie-producer'*) _t2c=leaked ;; *) _t2c=clean ;;
  esac
  case "$JSON_ONLY" in
    *'01-teach-yourself-protocol'*) _t2d=leaked ;; *) _t2d=clean ;;
  esac
  check "T2 --only 23,32 records skill 23"            "$_t2a" "yes"
  check "T2 --only 23,32 records skill 32"            "$_t2b" "yes"
  check "T2 --only 23,32 does NOT record skill 47"    "$_t2c" "clean"
  check "T2 --only 23,32 does NOT record skill 01"    "$_t2d" "clean"
  check "T4 --only sets content_verified=partial"     "$CV_ONLY" "partial"
  check "T4 --only sets tree_sha=partial"             "$TS_ONLY" "partial"

  OUT_FULL="$(run_block '')"
  JSON_FULL="$(printf '%s\n' "$OUT_FULL" | sed -n '1p')"
  CV_FULL="$(printf '%s\n' "$OUT_FULL" | sed -n '2p')"
  TS_FULL="$(printf '%s\n' "$OUT_FULL" | sed -n '3p')"
  _t3=ok
  for want in 01-teach-yourself-protocol 23-ai-workforce-blueprint \
              32-command-center-setup 47-movie-producer; do
    case "$JSON_FULL" in *"\"$want\""*) : ;; *) _t3="missing:$want" ;; esac
  done
  check "T3 full run records every non-archived skill" "$_t3" "ok"
  case "$JSON_FULL" in
    *ARCHIVED*) _t3b=leaked ;; *) _t3b=clean ;;
  esac
  check "T3 full run still excludes ARCHIVED"          "$_t3b" "clean"
  check "T4 full run sets content_verified=true"       "$CV_FULL" "true"
  check "T4 full run sets a real tree_sha"             "$TS_FULL" "rollup123"
fi

# ---------------------------------------------------------------- T5
# The receipt writer must merge the PRIOR skills map under this run's entries.
if grep -q "CARRY-FORWARD (INSTALLER-COMPLETENESS-V1)" "$UPDATE_SKILLS" \
   && grep -q "skills.update(verified_this_run)" "$UPDATE_SKILLS" \
   && grep -q "skills.update(_prev_skills)" "$UPDATE_SKILLS"; then
  ok "T5 receipt writer merges prior receipt under this run's entries"
else
  bad "T5 receipt writer does NOT carry the prior skills map forward"
fi
# and it must never take an out-of-scope digest from SRC_MANIFEST instead
if grep -q "'verified_this_run': sorted(verified_this_run.keys())" "$UPDATE_SKILLS"; then
  ok "T5 receipt records which skills were verified THIS run"
else
  bad "T5 receipt does not record verified_this_run"
fi
# A FULL run must NOT merge: it verified everything the release ships, so the
# prior map contributes only retired skills, which would inflate the receipt and
# the A2 shrink-guard baseline forever.
if grep -q "if '\${_VERIFIED_SCOPE:-full}' != 'full':" "$UPDATE_SKILLS"; then
  ok "T5 carry-forward is gated to SELECTIVE runs only"
else
  bad "T5 carry-forward is not gated — a full run would accumulate retired skills forever"
fi

# ---------------------------------------------------------------- T6
if grep -q 'A2-SOURCE-COVERAGE-ASSERTION-BEGIN' "$UPDATE_SKILLS" \
   && grep -q 'A2-SOURCE-COVERAGE-ASSERTION-END' "$UPDATE_SKILLS"; then
  ok "T6 A2 source-coverage block present"
else
  bad "T6 A2 source-coverage block MISSING"
fi
if grep -q 'SRC_MANIFEST=\$(bash "\$_CONTENT_HASH_SCRIPT" "\$EXTRACTED_DIR" 2>/dev/null || true)' "$UPDATE_SKILLS"; then
  bad "T6 SRC_MANIFEST still swallows skill-content-hash.sh's exit code with '|| true'"
else
  ok "T6 SRC_MANIFEST no longer swallows the hasher's exit code"
fi

# ---------------------------------------------------------------- T7/T8
# Behavioural check of the coverage comparison itself (same shape as the
# installer's loop): a source dir absent from the manifest must be detected.
coverage_probe() {
  # $1 = extracted dir, $2 = manifest text -> prints missing names
  local _ex="$1" _man="$2" _out=""
  for _d in "$_ex"/[0-9]*/; do
    [ -d "$_d" ] || continue
    local _n; _n="$(basename "$_d")"
    case "$_n" in *ARCHIVED*) continue ;; esac
    if ! printf '%s\n' "$_man" | grep -q "^${_n}|"; then
      _out="${_out} ${_n}"
    fi
  done
  printf '%s' "$_out"
}
mkdir -p "$TMP/src/01-alpha" "$TMP/src/23-bravo" "$TMP/src/47-charlie" \
         "$TMP/src/33-delta-ARCHIVED"
TRUNC_MAN="$(printf '%s\n' '01-alpha|a' '23-bravo|b' '__TREE_SHA__|r')"
FULL_MAN="$(printf '%s\n' '01-alpha|a' '23-bravo|b' '47-charlie|c' '__TREE_SHA__|r')"
check "T7 truncated manifest detected" "$(coverage_probe "$TMP/src" "$TRUNC_MAN")" " 47-charlie"
check "T8 complete manifest is silent" "$(coverage_probe "$TMP/src" "$FULL_MAN")" ""

# ---------------------------------------------------------------- T9
if grep -q 'A4-HASHER-PARITY-BEGIN' "$CHECK_UPDATES" \
   && grep -q 'canonical_digests' "$CHECK_UPDATES"; then
  ok "T9 check-updates.sh prefers the canonical hasher"
else
  bad "T9 check-updates.sh still re-implements the digest with a divergent exclusion list"
fi
if grep -q '__scope__' "$CHECK_UPDATES"; then
  ok "T9 check-updates.sh treats content_verified!=true as drift"
else
  bad "T9 check-updates.sh ignores a partial receipt"
fi

echo ""
echo "  passed=$PASS failed=$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
