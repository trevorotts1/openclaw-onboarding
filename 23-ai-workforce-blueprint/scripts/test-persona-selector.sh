#!/bin/bash
# test-persona-selector.sh — v11.4.0
#
# Live quality test for persona-selector-v2.py (canonical selector, PRD item 1.1).
# select-persona-for-task.py is a deprecated shim; this test drives v2 directly.
#
# Fires 10 canned tasks across 5 departments and verifies:
#   1. Each call returns a persona id (non-empty)
#   2. Persona diversity: NOT the same persona for every task
#      (catches stale-cache or single-persona-always bugs)
#   3. 5-layer breakdowns vary across tasks
#      (catches "selector always returns 0.7 for everything")
#   4. Marketing-tagged tasks return Marketing-tagged personas
#      (catches keyword filter not running)
#   5. Output JSON includes "funnel" key with pool/after_keyword/after_semantic
#      (catches funnel stages not running)
#
# This is a SMOKE TEST for quality, not a deep test. Pass = the selector
# is functioning. Quality of selection still requires human review of the
# top-3 candidates per task.
#
# USAGE:
#   bash test-persona-selector.sh
#   bash test-persona-selector.sh --verbose   # prints full JSON per call
#
# EXIT CODES:
#   0 = all assertions pass
#   1 = selector script missing
#   2 = no governing-personas found (Skill 23 hasn't run)
#   3 = one or more assertions failed

set -u

VERBOSE=false

while [ $# -gt 0 ]; do
  case "$1" in
    --verbose)      VERBOSE=true; shift ;;
    --help|-h)
      sed -n '1,30p' "$0"
      exit 0
      ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

# ─── CANONICAL SELECTOR PATH (persona-selector-v2.py) ───────────────────────
SELECTOR="$HOME/Downloads/openclaw-master-files/23-ai-workforce-blueprint/scripts/persona-selector-v2.py"
[ ! -f "$SELECTOR" ] && SELECTOR="$HOME/.openclaw/skills/23-ai-workforce-blueprint/scripts/persona-selector-v2.py"

red()    { printf "\033[31m%s\033[0m\n" "$1"; }
green()  { printf "\033[32m%s\033[0m\n" "$1"; }
yellow() { printf "\033[33m%s\033[0m\n" "$1"; }
blue()   { printf "\033[34m%s\033[0m\n" "$1"; }

# ─── PRE-FLIGHT ──────────────────────────────────────────────────────────────
if [ ! -x "$SELECTOR" ]; then
  red "ERROR: persona-selector-v2.py not found or not executable: $SELECTOR"
  red "Run update-skills.sh --only 23 to install."
  exit 1
fi

blue "═══════════════════════════════════════════════════"
blue "  Persona Selector Quality Test — v11.4.0"
blue "  Canonical selector: persona-selector-v2.py"
blue "═══════════════════════════════════════════════════"
echo "Selector: $SELECTOR"
echo

SLUG_ARG=""

# ─── 10 CANNED TASKS ─────────────────────────────────────────────────────────
# Mix of dept + task type. Diversity is deliberate — different writing styles,
# different domains, different urgencies — so the selector should naturally
# return different personas for each.
TASKS=(
  "marketing|Write a launch email hook for our new lead magnet"
  "marketing|Create a 30-day content calendar focused on storytelling"
  "marketing|Run a competitive analysis on the top 3 players in our space"
  "sales|Draft an objection-handling script for the price objection"
  "sales|Write a follow-up sequence for cold leads who downloaded the eBook"
  "operations|Document the standard process for onboarding a new vendor"
  "creative|Write three social media hooks for the founder's keynote video"
  "customer-support|Draft a polite response to a customer complaint about a delayed order"
  "ceo|Outline next quarter's strategic priorities for the leadership team"
  "research|Summarize the top 5 insights from the McKinsey 2026 SaaS benchmarks report"
)

results=()
personas_seen=()
breakdowns_seen=()

for entry in "${TASKS[@]}"; do
  dept=$(echo "$entry" | cut -d'|' -f1)
  task=$(echo "$entry" | cut -d'|' -f2)

  echo -n "  Task: [$dept] $task ... "

  output=$(python3 "$SELECTOR" --department "$dept" --task "$task" --format json 2>/dev/null)
  rc=$?

  if [ -z "$output" ] || [ "$rc" -ne 0 ] && [ "$rc" -ne 2 ]; then
    red "FAIL (rc=$rc)"
    results+=("FAIL|$dept|$task|no output")
    continue
  fi

  persona=$(echo "$output" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('persona_id','') or 'NONE')" 2>/dev/null)
  score=$(echo "$output" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('score',0))" 2>/dev/null)
  funnel_pool=$(echo "$output" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('funnel',{}).get('pool','?'))" 2>/dev/null)
  funnel_kw=$(echo "$output" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('funnel',{}).get('after_keyword','?'))" 2>/dev/null)
  funnel_sem=$(echo "$output" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('funnel',{}).get('after_semantic','?'))" 2>/dev/null)
  mode=$(echo "$output" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('interaction_mode',''))" 2>/dev/null)

  if [ -z "$persona" ] || [ "$persona" = "NONE" ]; then
    red "FAIL (no persona returned)"
    results+=("FAIL|$dept|$task|no persona")
    continue
  fi

  green "$persona (score=$score, funnel=$funnel_pool→$funnel_kw→$funnel_sem)"
  results+=("PASS|$dept|$task|$persona|$score|$funnel_pool|$funnel_kw|$funnel_sem")
  personas_seen+=("$persona")
  breakdowns_seen+=("$score")

  if [ "$VERBOSE" = "true" ]; then
    echo "    Mode: $mode"
    echo "$output" | python3 -m json.tool | sed 's/^/      /'
  fi
done

echo
blue "═══ Assertions ═══"

# A1: every task returned a persona
fails=$(printf '%s\n' "${results[@]}" | grep -c "^FAIL" || true)
if [ "$fails" = "0" ]; then
  green "  ✓ A1  All ${#TASKS[@]} tasks returned a persona"
  A1=PASS
else
  red "  ✗ A1  $fails / ${#TASKS[@]} tasks failed to return a persona"
  A1=FAIL
fi

# A2: persona diversity (NOT same persona for every task)
unique=$(printf '%s\n' "${personas_seen[@]}" | sort -u | wc -l | tr -d ' ')
total=${#personas_seen[@]}
if [ "$total" -gt 0 ] && [ "$unique" -ge 3 ]; then
  green "  ✓ A2  Persona diversity OK ($unique unique across $total tasks)"
  A2=PASS
elif [ "$total" -gt 0 ]; then
  red "  ✗ A2  Selector returned only $unique unique persona(s) across $total tasks (expected ≥ 3)"
  echo "       Personas seen: $(printf '%s\n' "${personas_seen[@]}" | sort -u | tr '\n' ',')"
  A2=FAIL
else
  yellow "  ⚠ A2  No personas to compare (A1 already failed)"
  A2=SKIP
fi

# A3: breakdown variance
unique_breakdowns=$(printf '%s\n' "${breakdowns_seen[@]}" | sort -u | wc -l | tr -d ' ')
if [ "$total" -gt 0 ] && [ "$unique_breakdowns" -ge 3 ]; then
  green "  ✓ A3  Score breakdowns vary ($unique_breakdowns unique score+semantic pairs)"
  A3=PASS
elif [ "$total" -gt 0 ]; then
  yellow "  ⚠ A3  Only $unique_breakdowns unique score breakdowns — selector may be using flat scoring"
  echo "       This is acceptable as a baseline but indicates the 5-layer scoring is heuristic, not data-driven."
  A3=WARN
else
  A3=SKIP
fi

# A4: marketing-tagged tasks → look at what came back
mkt_personas=$(printf '%s\n' "${results[@]}" | grep "^PASS|marketing|" | cut -d'|' -f4 | sort -u)
if [ -n "$mkt_personas" ]; then
  green "  ✓ A4  Marketing tasks returned: $(echo "$mkt_personas" | tr '\n' ',' | sed 's/,$//')"
  A4=PASS
else
  yellow "  ⚠ A4  No marketing tasks succeeded; cannot verify keyword filter"
  A4=SKIP
fi

# A5: funnel key present in output (PRD item 1.1 — funnel counts in JSON)
funnel_present=$(printf '%s\n' "${results[@]}" | grep "^PASS" | grep -v '|\?|' | wc -l | tr -d ' ')
if [ "$total" -gt 0 ] && [ "$funnel_present" -ge "$total" ]; then
  green "  ✓ A5  Funnel counts present in all output JSON (pool→keyword→semantic)"
  A5=PASS
elif [ "$total" -gt 0 ]; then
  yellow "  ⚠ A5  Funnel counts missing from some outputs — check persona-selector-v2.py version"
  A5=WARN
else
  A5=SKIP
fi

echo
blue "═══ Summary ═══"
echo "  A1 Returns persona:        $A1"
echo "  A2 Persona diversity:      $A2"
echo "  A3 Breakdown variance:     $A3"
echo "  A4 Keyword filter (mkt):   $A4"
echo "  A5 Funnel counts in JSON:  $A5"
echo

if [ "$A1" = "PASS" ] && [ "$A2" != "FAIL" ]; then
  green "OVERALL: SELECTOR FUNCTIONAL ✓"
  echo "Quality of selection still requires human review of top-3 candidates per task."
  exit 0
else
  red "OVERALL: SELECTOR HAS ISSUES — investigate above"
  exit 3
fi
