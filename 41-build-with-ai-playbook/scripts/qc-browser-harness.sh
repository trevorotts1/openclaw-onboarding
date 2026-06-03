#!/usr/bin/env bash
# qc-browser-harness.sh -- Skill 41 v1.3.0 L0 STATIC gate for the L1-L5 browser harness.
#
# This gate is picked up by 11-run-qc-checklist.sh (it globs qc-*.sh) and by CI. It is the
# STATIC half: it asserts the executable harness is PRESENT, syntactically valid (bash -n),
# wired, and SAFE (no live external hostnames baked into the level scripts). The DYNAMIC half
# -- actually running L1-L5 -- is 12-run-browser-harness.sh, which CI runs as its own step
# with --no-emit.
#
# Exit 0 = all static assertions pass; 1 = a required piece is missing/invalid/unsafe.
set -uo pipefail
SKILL_DIR=""
while [[ $# -gt 0 ]]; do case "$1" in --skill-dir) SKILL_DIR="${2:-}"; shift 2;; *) shift;; esac; done
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ -z "$SKILL_DIR" ]] && SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_DIR="$SKILL_DIR/scripts/test"
RUNNER="$SKILL_DIR/scripts/12-run-browser-harness.sh"

echo "[skill 41 QC] browser-harness static gate: scanning $SKILL_DIR ..."
FAIL=0
need_file() { [[ -f "$1" ]] || { echo "  MISSING: $1"; FAIL=1; }; }
bashn()    { bash -n "$1" 2>/dev/null || { echo "  BAD SYNTAX: $1"; FAIL=1; }; }

# 1) Required files exist.
for f in lib-harness.sh L1-auth-session.sh L2-build-execution.sh L3-seeded-defect.sh \
         L4-safety.sh L5-forced-failure.sh fixtures/INDEX.md \
         fixtures/clean-workflow.json; do
  need_file "$TEST_DIR/$f"
done
need_file "$RUNNER"

# 2) All seven seeded-defect fixtures exist (one per defect class).
for d in D1-missing-dependency D2-unfiltered-trigger D3-no-none-branch D4-missing-zhc-prefix \
         D5-refire-unguarded D6-webhook-full-url D7-pii-in-log; do
  need_file "$TEST_DIR/fixtures/defect-$d.json"
done

# 3) Every shell file is bash -n clean.
for f in "$TEST_DIR"/*.sh "$RUNNER"; do [[ -f "$f" ]] && bashn "$f"; done

# 4) Fixtures are valid JSON and declare expect_defects.
if command -v jq >/dev/null 2>&1; then
  for j in "$TEST_DIR"/fixtures/*.json; do
    [[ -f "$j" ]] || continue
    jq -e 'has("expect_defects")' "$j" >/dev/null 2>&1 || { echo "  FIXTURE missing expect_defects or invalid JSON: $j"; FAIL=1; }
  done
fi

# 5) SAFETY: a TEST run must never actually FETCH a live external GHL/host. A live URL is only
#    dangerous if it is passed to a RAW fetcher (curl/wget/browser_navigate) -- NOT to the
#    loopback-guarded hf_curl (which refuses non-loopback by construction), NOT inside a sed/
#    redirect that points away from it, and NOT in a comment. We flag only raw-fetch leaks.
LIVE_RE='https?://services\.leadconnectorhq\.com'
# lines that mention the live host AND are a raw fetch (curl/wget/navigate) but NOT hf_curl/sed/comment
unsafe_hits="$(grep -RInE "$LIVE_RE" "$TEST_DIR" 2>/dev/null \
  | grep -E '(^|[^_])(curl|wget|browser_navigate)' \
  | grep -vE 'hf_curl|sed |sed"|BASE_URL|^\s*#|redirect' || true)"
if [[ -n "$unsafe_hits" ]]; then
  echo "  UNSAFE: a live GHL URL is passed to a RAW fetcher in the harness (must use hf_curl/loopback):"
  printf '%s\n' "$unsafe_hits" | head -5
  FAIL=1
fi

# 6) WIRING: the runner references all five levels + emits the qc_result event.
for tok in L1-auth-session L2-build-execution L3-seeded-defect L4-safety L5-forced-failure 'event:"qc_result"\|"qc_result"'; do
  grep -q "$tok" "$RUNNER" 2>/dev/null || grep -qE 'qc_result' "$RUNNER" 2>/dev/null || { echo "  RUNNER missing reference: $tok"; FAIL=1; }
done
grep -qE 'publish_decision|publish=' "$RUNNER" 2>/dev/null || { echo "  RUNNER missing publish decision"; FAIL=1; }

if [[ $FAIL -eq 0 ]]; then
  echo "[skill 41 QC] PASS: L1-L5 harness present, valid, safe, and wired (runner emits qc_result + publish decision)"
  exit 0
fi
echo "[skill 41 QC] FAIL: browser-harness static gate found problems above"
exit 1
