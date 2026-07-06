#!/usr/bin/env bash
# test-persona-selector-sop-aware.sh
#
# Regression guard for SOP-AWARE MATCHING (F3.4 / F4.2, DEP-1).
# Proves the selector now CONSUMES the governing SOP:
#   • --sop-hints (sops.persona_hints) UNIONs the hinted persona into the scoring
#     pool DEPARTMENT-AGNOSTICALLY and never-to-zero (F4.2: was written-never-read),
#     with a BOUNDED, task_fit-coupled additive bonus that
#       - lets a hinted persona win among otherwise-equal candidates, but
#       - CANNOT overturn a strongly-named specialty specialist (bound proof); and
#   • --sop-name / --sop-steps / --sop-slug are FOLDED into the match query, so a
#     specialty named only in the SOP (not the task text) still drives recall; and
#   • with NO --sop-* flags the selection is byte-identical to the pre-SOP behavior
#     (inertness) and a non-installed hint id is ignored (funnel.hinted == 0).
#
# Runs in the HEURISTIC path (no gemini index / no API key in CI) against the
# canonical persona-categories.json seeded into a temp HOME — hermetic and
# deterministic. No client data: all personas are public authors.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPTS="$REPO_ROOT/23-ai-workforce-blueprint/scripts"
CANON_CATS="$REPO_ROOT/22-book-to-persona-coaching-leadership-system/persona-categories.json"

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

TMP_HOME="$(mktemp -d)"
trap 'rm -rf "$TMP_HOME"' EXIT
mkdir -p "$TMP_HOME/.openclaw/workspace/data/coaching-personas"
SEEDED_CATS="$TMP_HOME/.openclaw/workspace/data/coaching-personas/persona-categories.json"
cp "$CANON_CATS" "$SEEDED_CATS"

# Emit the FULL selection JSON. Empty temp HOME => no gemini index => heuristic
# path (in-process embedder and gemini-search subprocess both yield no semantic
# signal). PERSONA_CATEGORIES_PATH pins OUR seeded canonical file so an inherited
# override from a previous CI step cannot leak in.
run_json() {
  local task="$1" dept="$2"; shift 2
  HOME="$TMP_HOME" OPENCLAW_PLATFORM=mac SCORING_MODE=heuristic \
  PERSONA_CATEGORIES_PATH="$SEEDED_CATS" \
    python3 "$SCRIPTS/persona-selector-v2.py" \
      --task "$task" --department "$dept" \
      --no-variety --skip-stickiness --format json "$@" 2>/dev/null
}

# Extract a scalar via a python expression over the parsed JSON (var `d`).
jget() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }

echo "=== test-persona-selector-sop-aware.sh (heuristic, canonical pool) ==="
echo ""

NM_TASK="network marketing recruiting downline duplication"

# ── T1 — INERTNESS: no --sop-* flag reproduces the baseline winner ────────────
echo "--- T1 inertness: no SOP flags -> baseline specialist unchanged ---"
got="$(run_json "$NM_TASK" marketing | jget "d.get('persona_id')")"
[ "$got" = "brunson-network-marketing-secrets" ] \
  && pass "no-SOP baseline -> $got" \
  || fail "no-SOP baseline -> $got (expected brunson-network-marketing-secrets)"

# A no-SOP run must NOT carry a 'sop' block and (non-sticky) reports hinted==0.
sop_present="$(run_json "$NM_TASK" marketing | jget "'sop' in d")"
hinted0="$(run_json "$NM_TASK" marketing | jget "d.get('funnel',{}).get('hinted')")"
{ [ "$sop_present" = "False" ] && [ "$hinted0" = "0" ]; } \
  && pass "no-SOP run: no sop block, funnel.hinted=0" \
  || fail "no-SOP run leaked SOP state (sop_present=$sop_present hinted=$hinted0)"
echo ""

# ── T2 — BOUND PROOF: a poisoned hint cannot beat a strong specialty specialist ─
echo "--- T2 bound: poison hint (covey) does NOT overturn brunson on an NM task ---"
got="$(run_json "$NM_TASK" marketing --sop-hints covey-7-habits | jget "d.get('persona_id')")"
[ "$got" = "brunson-network-marketing-secrets" ] \
  && pass "NM task + poison hint -> $got (specialty > bounded hint)" \
  || fail "NM task + poison hint -> $got (bounded hint wrongly overturned specialist)"
echo ""

# ── T3 — POOL UNION / never-to-zero: a hint pulls a category-filtered persona in ─
echo "--- T3 union: finance task + hint rohde -> hinted==1 and rohde carries bonus ---"
FIN_TASK="quarterly budget forecast and pricing model"
J="$(run_json "$FIN_TASK" finance --sop-hints rohde-the-sketchnote-workbook)"
hinted="$(printf '%s' "$J" | jget "d.get('funnel',{}).get('hinted')")"
has_bonus="$(printf '%s' "$J" | jget "any(t.get('persona_id')=='rohde-the-sketchnote-workbook' and t.get('sop_hint_bonus',0)>0 for t in d.get('breakdown',{}).get('top_3',[]))")"
{ [ "$hinted" = "1" ] && [ "$has_bonus" = "True" ]; } \
  && pass "rohde UNIONed into finance pool (hinted=$hinted) with sop_hint_bonus" \
  || fail "rohde not properly unioned/bonused (hinted=$hinted has_bonus=$has_bonus)"

# The bounded bonus is capped: sop_hint_bonus must be <= 0.30 (the SOP_HINT cap).
bonus_val="$(printf '%s' "$J" | jget "max([t.get('sop_hint_bonus',0) for t in d.get('breakdown',{}).get('top_3',[])]+[0])")"
python3 -c "import sys; sys.exit(0 if 0 < $bonus_val <= 0.30 else 1)" \
  && pass "sop_hint_bonus=$bonus_val within (0, 0.30] cap" \
  || fail "sop_hint_bonus=$bonus_val outside the (0, 0.30] cap"
echo ""

# ── T4 — TIEBREAK WIN: among otherwise-neutral candidates the hint decides ─────
echo "--- T4 tiebreak: neutral task + hint voss -> voss wins (relevant hint wins) ---"
NEU_TASK="prepare the standard weekly status update for the team"
J="$(run_json "$NEU_TASK" general-task --sop-hints voss-never-split-difference)"
got="$(printf '%s' "$J" | jget "d.get('persona_id')")"
won_bonus="$(printf '%s' "$J" | jget "next((t.get('sop_hint_bonus',0) for t in d.get('breakdown',{}).get('top_3',[]) if t.get('persona_id')=='voss-never-split-difference'),0)")"
{ [ "$got" = "voss-never-split-difference" ] && python3 -c "import sys;sys.exit(0 if $won_bonus>0 else 1)"; } \
  && pass "neutral task + hint voss -> $got (bonus=$won_bonus)" \
  || fail "neutral task + hint voss -> $got (bonus=$won_bonus, expected voss to win)"
echo ""

# ── T5 — COMPOSITE FOLD: a specialty named only in the SOP drives recall ───────
echo "--- T5 fold: --sop-name 'sketchnote...' pulls rohde though task text omits it ---"
VIS_TASK="please handle the visual summary for the team"
# Control: task alone must NOT select rohde (no rohde specialty tag in the task).
ctrl="$(run_json "$VIS_TASK" general-task | jget "d.get('persona_id')")"
# With the SOP name folded in, 'sketchnote'/'visual thinking' now match rohde.
withsop="$(run_json "$VIS_TASK" general-task --sop-name "create a sketchnote visual thinking map" | jget "d.get('persona_id')")"
{ [ "$ctrl" != "rohde-the-sketchnote-workbook" ] && [ "$withsop" = "rohde-the-sketchnote-workbook" ]; } \
  && pass "SOP-name fold flipped selection: control=$ctrl withsop=$withsop" \
  || fail "SOP-name fold ineffective: control=$ctrl withsop=$withsop (expected control!=rohde, withsop=rohde)"
echo ""

# ── T6 — NON-INSTALLED hint is ignored (never reference an absent persona) ─────
echo "--- T6 safety: a bogus hint id is ignored (hinted==0, winner unchanged) ---"
J="$(run_json "$NM_TASK" marketing --sop-hints no-such-persona-xyz)"
hinted="$(printf '%s' "$J" | jget "d.get('funnel',{}).get('hinted')")"
got="$(printf '%s' "$J" | jget "d.get('persona_id')")"
{ [ "$hinted" = "0" ] && [ "$got" = "brunson-network-marketing-secrets" ]; } \
  && pass "bogus hint ignored (hinted=$hinted, winner=$got)" \
  || fail "bogus hint mishandled (hinted=$hinted, winner=$got)"
echo ""

echo "========================================"
echo "RESULTS: $PASS passed, $FAIL failed"
echo "========================================"
[ "$FAIL" -eq 0 ]
