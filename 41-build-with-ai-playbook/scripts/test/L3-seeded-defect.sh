#!/usr/bin/env bash
# L3-seeded-defect.sh -- Skill 41 v1.3.0 browser-execution harness, Level 3.
#
# PROPERTY PROVEN: the Big-Brother QC core (the autonomous human-last reviewer) actually
# CATCHES the seeded defects -- it neither under-flags (misses a real defect, which would let
# a broken workflow publish) nor over-flags (trips on a clean workflow, which would block good
# work and erode trust). This is the heart of the closed loop.
#
# How it proves it (executable, not prose):
#   * The CLEAN fixture must scan to ZERO defects   -> positive control against over-flagging.
#   * Each DEFECT fixture must scan to EXACTLY its declared `expect_defects` set
#                                                    -> the core under-flag / mis-classify guard.
#   * A LAST-LINE meta-check mutates the clean fixture in-memory to inject a defect and asserts
#     the scanner now flags it -> proves the scanner is genuinely reading the input, not
#     returning a canned answer.
#
# All fixtures are static JSON with NO creds / NO live URLs / NO real PII (see fixtures/INDEX.md).
#
# Usage: bash L3-seeded-defect.sh
# Exit:  0 = pass, 1 = fail.
set -uo pipefail
HF_LEVEL="L3"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib-harness.sh"
FX="$SCRIPT_DIR/fixtures"

HF_CHECKS=0; HF_FAILS=0
hf_log "seeded-defect Big-Brother core test"

if [[ ! -d "$FX" ]]; then hf_fail "fixtures dir missing: $FX"; exit 1; fi

# normalize a multiline defect list to a sorted compact JSON array for comparison
norm() { sort | grep -v '^$' | jq -R . | jq -sc 'sort'; }

# 1) CLEAN fixture must be clean.
clean_got="$(hf_bigbrother_scan "$FX/clean-workflow.json" | norm)"
hf_check "clean-workflow scans to ZERO defects (got $clean_got)" test "$clean_got" = "[]"

# 2) Each defect fixture must produce exactly its expected set.
for f in "$FX"/defect-D*.json; do
  [[ -f "$f" ]] || continue
  base="$(basename "$f")"
  exp="$(jq -c '.expect_defects | sort' "$f")"
  got="$(hf_bigbrother_scan "$f" | norm)"
  hf_check "$base caught exactly $exp (got $got)" test "$got" = "$exp"
done

# 3) Coverage: assert all 7 defect classes have a fixture (no silent gap in the core).
declare -a CLASSES=(D1_MISSING_DEPENDENCY D2_UNFILTERED_TRIGGER D3_NO_NONE_BRANCH \
                    D4_MISSING_ZHC_PREFIX D5_REFIRE_UNGUARDED D6_WEBHOOK_FULL_URL D7_PII_IN_LOG)
for cls in "${CLASSES[@]}"; do
  hit=0
  for f in "$FX"/defect-D*.json; do
    jq -e --arg c "$cls" '.expect_defects | index($c)' "$f" >/dev/null 2>&1 && { hit=1; break; }
  done
  hf_check "defect class $cls has a covering fixture" test "$hit" = "1"
done

# 4) META: mutate the clean fixture to inject an unfiltered trigger and confirm the scanner
#    now flags D2 -- proves it actually reads the input rather than returning a canned result.
SB="$(hf_make_sandbox)"; trap 'rm -rf "$SB"' EXIT
jq '.triggers[0].filters=[] | .triggers[0].allow_everyone=false' "$FX/clean-workflow.json" > "$SB/mutated.json"
mut_got="$(hf_bigbrother_scan "$SB/mutated.json" | norm)"
hf_check "mutating clean->unfiltered makes the core flag D2 (got $mut_got)" bash -c "echo '$mut_got' | jq -e 'index(\"D2_UNFILTERED_TRIGGER\")' >/dev/null"

hf_log "checks=$HF_CHECKS fails=$HF_FAILS"
if [[ $HF_FAILS -eq 0 ]]; then hf_pass "Big-Brother core catches every seeded defect and passes the clean control (and reads live input)"; exit 0; fi
hf_fail "$HF_FAILS seeded-defect check(s) failed -- the human-last reviewer is NOT trustworthy; do not ship"; exit 1
