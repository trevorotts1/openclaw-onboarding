#!/usr/bin/env bash
# onbox-drift-gate.test.sh — GK-28/U90 step (a) regression test.
#
# Proves lib-onbox-drift.sh's agent_browser_onbox_drift + the wired
# qc-agent-browser.sh gate:
#   1. No on-box source-of-truth file present -> "" (skip, PASS). SKILL.md
#      documents that path as OPTIONAL — nothing to check when absent.
#   2. On-box file present, no baseline ever pinned -> NO-BASELINE-PINNED,
#      and qc-agent-browser.sh FAILS (fail-closed: unknown state is a gap,
#      never a silent pass).
#   3. On-box file present, baseline pinned, file UNCHANGED since -> MATCH,
#      qc-agent-browser.sh PASSES.
#   4. On-box file present, baseline pinned, file DELIBERATELY DRIFTED after
#      pinning -> DRIFT, qc-agent-browser.sh FAILS naming it (the unit's own
#      binary acceptance: "QC fails when the on-box ~/clawd copy is
#      deliberately drifted (fixture)").
#   5. pin-onbox-source-of-truth.sh itself: captures a baseline, --check
#      passes right after capture, and --check fails after a subsequent edit.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && cd .. && pwd)"

# shellcheck source=../lib-onbox-drift.sh
source "$SCRIPT_DIR/../lib-onbox-drift.sh"

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== onbox-drift-gate.test.sh (GK-28/U90) ==="

WORK="$(mktemp -d)"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

stage_install() {
  # $1 = HOME dir to create -- stages a full skill copy under it.
  local home="$1" staged="$1/.openclaw/skills/03-agent-browser"
  mkdir -p "$1/.openclaw/skills"
  cp -R "$SKILL_DIR" "$staged"
  echo "$staged"
}

# ── (1) lib function directly: on-box path absent -> "" ─────────────────────
NOPE="$WORK/does-not-exist/SKILL.md"
PINFILE_UNUSED="$WORK/unused.pin"
OUT1="$(agent_browser_onbox_drift "$NOPE" "$PINFILE_UNUSED")"
if [ "$OUT1" = "" ]; then
  pass "lib: absent on-box file -> empty (nothing to check)"
else
  fail "lib: expected empty output for an absent on-box file, got: '$OUT1'"
fi

# ── (2) lib function directly: present + no pin -> NO-BASELINE-PINNED ───────
ONBOX2="$WORK/onbox2/SKILL.md"
mkdir -p "$(dirname "$ONBOX2")"
printf '# real on-box source-of-truth doc\nsome content\n' > "$ONBOX2"
PIN2="$WORK/pin2.pin"   # never created
OUT2="$(agent_browser_onbox_drift "$ONBOX2" "$PIN2")"
if [ "$OUT2" = "NO-BASELINE-PINNED" ]; then
  pass "lib: on-box file present, no pin file -> NO-BASELINE-PINNED"
else
  fail "lib: expected NO-BASELINE-PINNED, got: '$OUT2'"
fi

# ── (3) lib function directly: present + UNCAPTURED placeholder pin -> NO-BASELINE-PINNED
PIN3="$WORK/pin3.pin"
printf '# comment\nUNCAPTURED\n' > "$PIN3"
OUT3="$(agent_browser_onbox_drift "$ONBOX2" "$PIN3")"
if [ "$OUT3" = "NO-BASELINE-PINNED" ]; then
  pass "lib: UNCAPTURED placeholder pin -> NO-BASELINE-PINNED (fail-closed, not a silent skip)"
else
  fail "lib: expected NO-BASELINE-PINNED for an UNCAPTURED pin, got: '$OUT3'"
fi

# ── (4) full pin/verify cycle via pin-onbox-source-of-truth.sh ──────────────
HOME4="$WORK/home-cycle"
STAGED4="$(stage_install "$HOME4")"
ONBOX4="$HOME4/clawd/skills/agent-browser/SKILL.md"
mkdir -p "$(dirname "$ONBOX4")"
printf '# real on-box doc v1\ncontent here\n' > "$ONBOX4"

# --check BEFORE any pin exists -> FAIL
RC4A=0
AGENT_BROWSER_ONBOX_SKILLMD="$ONBOX4" bash "$STAGED4/scripts/pin-onbox-source-of-truth.sh" --check >/tmp/onbox4a.$$ 2>&1 || RC4A=$?
if [ "$RC4A" -ne 0 ] && grep -q "no baseline pinned yet" /tmp/onbox4a.$$; then
  pass "pin script --check FAILS before any baseline is captured"
else
  fail "expected --check to FAIL before capture; rc=$RC4A, output: $(cat /tmp/onbox4a.$$)"
fi
rm -f /tmp/onbox4a.$$

# capture (no args) -> writes the pin
RC4B=0
AGENT_BROWSER_ONBOX_SKILLMD="$ONBOX4" bash "$STAGED4/scripts/pin-onbox-source-of-truth.sh" >/tmp/onbox4b.$$ 2>&1 || RC4B=$?
if [ "$RC4B" -eq 0 ] && grep -q "^OK — pinned" /tmp/onbox4b.$$; then
  pass "pin script captures a baseline (exit 0, 'OK — pinned' line)"
else
  fail "expected the capture run to succeed; rc=$RC4B, output: $(cat /tmp/onbox4b.$$)"
fi
rm -f /tmp/onbox4b.$$

# --check right after capture, unchanged file -> PASS
RC4C=0
AGENT_BROWSER_ONBOX_SKILLMD="$ONBOX4" bash "$STAGED4/scripts/pin-onbox-source-of-truth.sh" --check >/tmp/onbox4c.$$ 2>&1 || RC4C=$?
if [ "$RC4C" -eq 0 ] && grep -q "^PASS" /tmp/onbox4c.$$; then
  pass "pin script --check PASSES immediately after capture (unchanged file)"
else
  fail "expected --check to PASS right after capture; rc=$RC4C, output: $(cat /tmp/onbox4c.$$)"
fi
rm -f /tmp/onbox4c.$$

# drift the on-box file -> --check FAILS
printf '# real on-box doc v2 -- DRIFTED\nDIFFERENT content now\n' > "$ONBOX4"
RC4D=0
AGENT_BROWSER_ONBOX_SKILLMD="$ONBOX4" bash "$STAGED4/scripts/pin-onbox-source-of-truth.sh" --check >/tmp/onbox4d.$$ 2>&1 || RC4D=$?
if [ "$RC4D" -ne 0 ] && grep -q "DRIFTED from the pinned baseline" /tmp/onbox4d.$$; then
  pass "pin script --check FAILS after the on-box file is deliberately drifted, naming DRIFT"
else
  fail "expected --check to FAIL after drift; rc=$RC4D, output: $(cat /tmp/onbox4d.$$)"
fi
rm -f /tmp/onbox4d.$$

# ── (5) qc-agent-browser.sh itself: end-to-end wired gate ───────────────────
# 5a: no on-box file at all -> the drift-gate SECTION passes (info line),
#     overall QC unaffected by this gate (other sections may still WARN/FAIL
#     for unrelated reasons in a bare sandbox -- we only assert THIS section).
HOME5A="$WORK/home-qc-absent"
STAGED5A="$(stage_install "$HOME5A")"
OUT5A="$(HOME="$HOME5A" AGENT_BROWSER_ONBOX_SKILLMD="$HOME5A/nope/SKILL.md" bash "$STAGED5A/qc-agent-browser.sh" 2>&1 || true)"
if echo "$OUT5A" | grep -q "no on-box source-of-truth copy present"; then
  pass "qc-agent-browser.sh: absent on-box file -> info/skip line present"
else
  fail "qc-agent-browser.sh: expected the absent-onbox info line; output: $OUT5A"
fi

# 5b: on-box file present, never pinned -> qc-agent-browser.sh FAILS this section
HOME5B="$WORK/home-qc-nopin"
STAGED5B="$(stage_install "$HOME5B")"
ONBOX5B="$HOME5B/clawd/skills/agent-browser/SKILL.md"
mkdir -p "$(dirname "$ONBOX5B")"
printf '# on-box doc, never pinned\n' > "$ONBOX5B"
OUT5B="$(HOME="$HOME5B" AGENT_BROWSER_ONBOX_SKILLMD="$ONBOX5B" bash "$STAGED5B/qc-agent-browser.sh" 2>&1 || true)"
if echo "$OUT5B" | grep -q "FAIL.*no baseline pinned"; then
  pass "qc-agent-browser.sh: on-box file present + no pin -> FAILS (fail-closed)"
else
  fail "qc-agent-browser.sh: expected a FAIL naming the missing baseline; output: $OUT5B"
fi

# 5c: on-box file present, pinned, then DRIFTED -> qc-agent-browser.sh FAILS naming DRIFT
HOME5C="$WORK/home-qc-drift"
STAGED5C="$(stage_install "$HOME5C")"
ONBOX5C="$HOME5C/clawd/skills/agent-browser/SKILL.md"
mkdir -p "$(dirname "$ONBOX5C")"
printf '# on-box doc v1\n' > "$ONBOX5C"
AGENT_BROWSER_ONBOX_SKILLMD="$ONBOX5C" bash "$STAGED5C/scripts/pin-onbox-source-of-truth.sh" >/dev/null 2>&1
printf '# on-box doc v2 -- DRIFTED after pin\n' > "$ONBOX5C"
OUT5C="$(HOME="$HOME5C" AGENT_BROWSER_ONBOX_SKILLMD="$ONBOX5C" bash "$STAGED5C/qc-agent-browser.sh" 2>&1 || true)"
if echo "$OUT5C" | grep -q "FAIL.*DRIFTED from the pinned baseline"; then
  pass "qc-agent-browser.sh: pinned on-box file, deliberately drifted -> FAILS naming DRIFT (unit's binary acceptance)"
else
  fail "qc-agent-browser.sh: expected a FAIL naming the drift; output: $OUT5C"
fi

# 5d: on-box file present, pinned, UNCHANGED -> this section PASSES
HOME5D="$WORK/home-qc-clean"
STAGED5D="$(stage_install "$HOME5D")"
ONBOX5D="$HOME5D/clawd/skills/agent-browser/SKILL.md"
mkdir -p "$(dirname "$ONBOX5D")"
printf '# on-box doc, unchanged\n' > "$ONBOX5D"
AGENT_BROWSER_ONBOX_SKILLMD="$ONBOX5D" bash "$STAGED5D/scripts/pin-onbox-source-of-truth.sh" >/dev/null 2>&1
OUT5D="$(HOME="$HOME5D" AGENT_BROWSER_ONBOX_SKILLMD="$ONBOX5D" bash "$STAGED5D/qc-agent-browser.sh" 2>&1 || true)"
if echo "$OUT5D" | grep -q "matches the pinned baseline"; then
  pass "qc-agent-browser.sh: pinned on-box file, unchanged -> PASSES this section"
else
  fail "qc-agent-browser.sh: expected a PASS line for the unchanged pinned file; output: $OUT5D"
fi

echo ""
echo "================================================="
echo "Results: $PASS passed, $FAIL failed"
echo "================================================="
if [ "$FAIL" -eq 0 ]; then
  echo "ALL TESTS PASSED"
  exit 0
else
  echo "TESTS FAILED"
  exit 1
fi
