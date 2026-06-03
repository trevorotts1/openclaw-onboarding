#!/usr/bin/env bash
# Skill 42 — verify-pa-install.sh
# Lightweight structural check: all 29 specialist folders, each specialist's role
# files, and SOP presence. Exits 1 on any missing piece, 0 when complete.
set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PA_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SPEC_DIR="$PA_DIR/specialists"

FAIL=0
note(){ printf "  %s\n" "$1"; }
ok(){ printf "  [OK]   %s\n" "$1"; }
bad(){ printf "  [FAIL] %s\n" "$1"; FAIL=$((FAIL+1)); }

SPECIALISTS=(
  "01-inbox-manager" "02-calendar-scheduling-manager" "03-daily-briefing-debrief"
  "04-task-priority-manager" "05-meeting-assistant" "06-research-answers"
  "07-brainstorming-ideation" "08-my-coach" "09-emotional-support-wellbeing"
  "10-travel-logistics" "11-personal-finance" "12-relationships-dates"
  "13-errands-purchases" "14-life-admin-archivist" "15-christian-spiritual-life"
  "16-motivation-momentum" "17-the-challenger" "18-family-life-stage"
  "19-study-partner" "20-passion-purpose" "21-clarity-specialist"
  "22-youtube-teacher" "23-goal-setter" "24-superwoman-syndrome"
  "25-imposter-syndrome" "26-therapeutic-support" "27-focus-completion"
  "28-celebration-agent" "29-greatness-agent"
)
ROLE_FILES=("00-START-HERE.md" "IDENTITY.md" "SOUL.md" "governing-personas.md" "how-to.md" "ROSTER.md")

echo ""
echo "Personal Assistant Library — install verification"
echo "Skill dir: $PA_DIR"
echo ""

[ -d "$SPEC_DIR" ] && ok "specialists/ present" || bad "specialists/ MISSING"

for slug in "${SPECIALISTS[@]}"; do
  d="$SPEC_DIR/$slug"
  if [ ! -d "$d" ]; then bad "$slug folder MISSING"; continue; fi
  if [ "$slug" = "19-study-partner" ]; then
    { [ -f "$d/00-START-HERE.md" ] && [ -f "$d/ROSTER.md" ]; } && ok "$slug (sub-specialist roster)" || bad "$slug missing orientation/roster"
  else
    miss=""
    for rf in "${ROLE_FILES[@]}"; do [ -f "$d/$rf" ] || miss="$miss $rf"; done
    [ -z "$miss" ] && ok "$slug role files" || bad "$slug missing:$miss"
  fi
  [ -f "$d/SOP/00-INDEX.md" ] || bad "$slug missing SOP/00-INDEX.md"
  cnt=$(find "$d/SOP" -name 'PA-*.md' 2>/dev/null | wc -l | tr -d ' ')
  [ "$cnt" -ge 1 ] || bad "$slug has 0 SOPs"
done

TOTAL_SOP=$(find "$SPEC_DIR" -path '*/SOP/PA-*.md' 2>/dev/null | wc -l | tr -d ' ')
TOTAL_IDX=$(find "$SPEC_DIR" -path '*/SOP/00-INDEX.md' 2>/dev/null | wc -l | tr -d ' ')
[ "$TOTAL_SOP" -eq 162 ] && ok "162 SOPs present" || bad "expected 162 SOPs, found $TOTAL_SOP"
[ "$TOTAL_IDX" -eq 29 ]  && ok "29 SOP indexes present" || bad "expected 29 SOP indexes, found $TOTAL_IDX"

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "PASS — Personal Assistant Library is complete (29 specialists / 162 SOPs)."
  exit 0
else
  echo "FAIL — $FAIL problem(s) found."
  exit 1
fi
