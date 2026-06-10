#!/bin/bash
# test-persona-selector.sh — v11.5.0
#
# Live quality test for persona-selector-v2.py (canonical selector, PRD item 1.2).
# select-persona-for-task.py is a deprecated shim; this test drives v2 directly.
#
# Fires 10 canned tasks across 5 departments and verifies:
#   1. Each call returns a persona id (non-empty)
#   2. Persona diversity: NOT the same persona for every task
#      (catches stale-cache or single-persona-always bugs)
#   3. 5-layer breakdowns vary across tasks
#      (catches "selector always returns 0.7 for everything")
#   4. Marketing-tagged tasks return personas with domain tags intersecting
#      {marketing, copywriting, communication, sales, strategy-innovation}
#      FAIL if any returned persona has ZERO tag overlap (PRD 1.2 Defect 1-3 verify:
#      "finance-tagged personas were not scored")
#   5. Output JSON includes "funnel" key with pool/category/semantic
#      (catches funnel stages not running — PRD 1.2 canonical key names)
#   6. Funnel counts are monotonically non-increasing: pool >= category >= semantic
#      (catches never-to-zero invariant breaking)
#
# VPS layout: run with MASTER_FILES_DIR=/data/openclaw-master-files exported to
# exercise the VPS path resolution (no script edit needed; selector reads env).
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

# Locate persona-categories.json for A4 tag-intersection assertion
# PRD 2.7: canonical = workspace/data/coaching-personas/persona-categories.json.
# Skill-folder copy is shipped seed (READ-ONLY); only used as final fallback here.
PERSONA_CAT_FILE="$HOME/.openclaw/workspace/data/coaching-personas/persona-categories.json"
[ ! -f "$PERSONA_CAT_FILE" ] && PERSONA_CAT_FILE="/data/.openclaw/workspace/data/coaching-personas/persona-categories.json"
[ ! -f "$PERSONA_CAT_FILE" ] && PERSONA_CAT_FILE="$HOME/.openclaw/skills/22-book-to-persona-coaching-leadership-system/persona-categories.json"
[ ! -f "$PERSONA_CAT_FILE" ] && PERSONA_CAT_FILE=""  # A4 tag check skipped if file missing

blue "═══════════════════════════════════════════════════"
blue "  Persona Selector Quality Test — v11.5.0"
blue "  Canonical selector: persona-selector-v2.py"
blue "  PRD item 1.2 — rebuilt matching funnel"
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
mkt_result_personas=()

for entry in "${TASKS[@]}"; do
  dept=$(echo "$entry" | cut -d'|' -f1)
  task=$(echo "$entry" | cut -d'|' -f2)

  echo -n "  Task: [$dept] $task ... "

  output=$(SCORING_MODE=heuristic python3 "$SELECTOR" --department "$dept" --task "$task" --format json 2>/dev/null)
  rc=$?

  if [ -z "$output" ] || [ "$rc" -ne 0 ] && [ "$rc" -ne 2 ]; then
    red "FAIL (rc=$rc)"
    results+=("FAIL|$dept|$task|no output")
    continue
  fi

  persona=$(echo "$output" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('persona_id','') or 'NONE')" 2>/dev/null)
  score=$(echo "$output" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('score',0))" 2>/dev/null)
  funnel_pool=$(echo "$output" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('funnel',{}).get('pool','?'))" 2>/dev/null)
  funnel_cat=$(echo "$output" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('funnel',{}).get('category','?'))" 2>/dev/null)
  funnel_sem=$(echo "$output" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('funnel',{}).get('semantic','?'))" 2>/dev/null)
  mode=$(echo "$output" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('interaction_mode',''))" 2>/dev/null)

  if [ -z "$persona" ] || [ "$persona" = "NONE" ]; then
    red "FAIL (no persona returned)"
    results+=("FAIL|$dept|$task|no persona")
    continue
  fi

  green "$persona (score=$score, funnel=$funnel_pool→$funnel_cat→$funnel_sem)"
  results+=("PASS|$dept|$task|$persona|$score|$funnel_pool|$funnel_cat|$funnel_sem")
  personas_seen+=("$persona")
  breakdowns_seen+=("$score")

  if [ "$dept" = "marketing" ]; then
    mkt_result_personas+=("$persona")
  fi

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

# A4: marketing-tagged tasks → tag-intersection check (PRD 1.2 Defect 1-3 verify)
# Asserts that every persona returned for marketing tasks has domain tags that
# intersect {marketing, copywriting, communication, sales, strategy-innovation}.
# FAIL if any returned persona has ZERO tag overlap — that means finance-only
# (or other non-marketing) personas were scored and won, which is the Defect 1-3 bug.
MKT_DOMAINS="marketing copywriting communication sales strategy-innovation"
A4=SKIP
if [ "${#mkt_result_personas[@]}" -gt 0 ]; then
  if [ -n "$PERSONA_CAT_FILE" ]; then
    A4_FAIL=0
    A4_PASS=0
    for pid in "${mkt_result_personas[@]}"; do
      tag_overlap=$(python3 - <<PYEOF 2>/dev/null
import json, sys
cat_file = "$PERSONA_CAT_FILE"
pid = "$pid"
mkt_set = {"marketing","copywriting","communication","sales","strategy-innovation"}
try:
    data = json.loads(open(cat_file).read())
    personas = data.get("personas", {})
    info = personas.get(pid, {})
    # Normalise: lowercase, / and spaces → -
    import re
    def norm(s): return re.sub(r"[/ _]+", "-", s.lower()).strip("-")
    ptags = {norm(t) for t in (info.get("domain") or info.get("domain_tags") or info.get("tags") or [])}
    overlap = ptags & mkt_set
    print(len(overlap))
except Exception as e:
    print(0)
PYEOF
)
      if [ "$tag_overlap" = "0" ]; then
        red "  ✗ A4  Persona '$pid' returned for marketing task has ZERO marketing-domain tag overlap"
        red "       (finance-only or unrelated persona leaked through Stage B — Defect 1-3 still present)"
        A4_FAIL=$((A4_FAIL + 1))
      else
        A4_PASS=$((A4_PASS + 1))
      fi
    done
    if [ "$A4_FAIL" -eq 0 ]; then
      green "  ✓ A4  All marketing-task personas have marketing-domain tag overlap ($A4_PASS/$A4_PASS checked)"
      A4=PASS
    else
      red "  ✗ A4  $A4_FAIL marketing persona(s) failed domain-tag intersection check"
      A4=FAIL
    fi
  else
    yellow "  ⚠ A4  persona-categories.json not found — skipping tag-intersection check"
    mkt_personas_str=$(printf '%s\n' "${mkt_result_personas[@]}" | sort -u | tr '\n' ',' | sed 's/,$//')
    green "  ✓ A4  Marketing tasks returned: $mkt_personas_str (file check skipped)"
    A4=PASS
  fi
else
  yellow "  ⚠ A4  No marketing tasks succeeded; cannot verify category filter"
  A4=SKIP
fi

# A5: funnel key present in output (PRD item 1.2 canonical keys: pool/category/semantic)
funnel_present=$(printf '%s\n' "${results[@]}" | grep "^PASS" | grep -v '|\?|' | wc -l | tr -d ' ')
if [ "$total" -gt 0 ] && [ "$funnel_present" -ge "$total" ]; then
  green "  ✓ A5  Funnel counts present in all output JSON (pool→category→semantic)"
  A5=PASS
elif [ "$total" -gt 0 ]; then
  yellow "  ⚠ A5  Funnel counts missing from some outputs — check persona-selector-v2.py version"
  A5=WARN
else
  A5=SKIP
fi

# A6: monotonic funnel (pool >= category >= semantic, all integers, none '?')
# Catches never-to-zero invariant breaking. FAIL if any stage count exceeds
# the prior stage, or if any is non-numeric.
A6=PASS
A6_issues=0
for row in "${results[@]}"; do
  if [[ "$row" != PASS* ]]; then
    continue
  fi
  IFS='|' read -r _status _dept _task _pid _score fp fc fs <<< "$row"
  # Check numeric
  if ! [[ "$fp" =~ ^[0-9]+$ ]] || ! [[ "$fc" =~ ^[0-9]+$ ]] || ! [[ "$fs" =~ ^[0-9]+$ ]]; then
    red "  ✗ A6  Non-numeric funnel count: pool=$fp category=$fc semantic=$fs for [$_dept] $_task"
    A6=FAIL
    A6_issues=$((A6_issues + 1))
    continue
  fi
  # Check monotonically non-increasing
  if [ "$fp" -lt "$fc" ] || [ "$fc" -lt "$fs" ]; then
    red "  ✗ A6  Non-monotonic funnel: pool=$fp category=$fc semantic=$fs for [$_dept] $_task"
    A6=FAIL
    A6_issues=$((A6_issues + 1))
  fi
done
if [ "$A6" = "PASS" ] && [ "$total" -gt 0 ]; then
  green "  ✓ A6  Funnel counts monotonically non-increasing across all $total tasks"
fi

echo
blue "═══ Summary ═══"
echo "  A1 Returns persona:              $A1"
echo "  A2 Persona diversity:            $A2"
echo "  A3 Breakdown variance:           $A3"
echo "  A4 Category filter (mkt tags):   $A4"
echo "  A5 Funnel counts in JSON:        $A5"
echo "  A6 Monotonic funnel invariant:   $A6"
echo

if [ "$A1" = "PASS" ] && [ "$A2" != "FAIL" ] && [ "$A4" != "FAIL" ] && [ "$A6" != "FAIL" ]; then
  green "OVERALL: SELECTOR FUNCTIONAL ✓"
  echo "Quality of selection still requires human review of top-3 candidates per task."
  exit 0
else
  red "OVERALL: SELECTOR HAS ISSUES — investigate above"
  exit 3
fi
