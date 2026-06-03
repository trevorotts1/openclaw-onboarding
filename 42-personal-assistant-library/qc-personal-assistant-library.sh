#!/usr/bin/env bash
# Skill 42 — Personal Assistant Library — Install QC
set -u
PASS=0; FAIL=0; WARN=0
SKILL_DIR="$(dirname "$0")"
LIB="$SKILL_DIR/../lib-shared.sh"; [ -f "$LIB" ] && source "$LIB"
if ! command -v resolve_platform_paths >/dev/null 2>&1; then
  resolve_platform_paths() { export WORKSPACE="$HOME/clawd" SKILLS_DIR_DEFAULT="$HOME/.openclaw/skills"; }
fi
resolve_platform_paths
red(){ printf "\033[31m%s\033[0m\n" "$1"; }; green(){ printf "\033[32m%s\033[0m\n" "$1"; }; yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }
assert(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else red "  ✗ FAIL — $1"; FAIL=$((FAIL+1)); fi; }
warn_only(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else yellow "  ⚠ WARN — $1"; WARN=$((WARN+1)); fi; }

PA_DIR="$SKILLS_DIR_DEFAULT/42-personal-assistant-library"
SPEC_DIR="$PA_DIR/specialists"

# The 29 specialist slugs (in order)
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
# Specialist 19 (Study Partner) ships a sub-specialist roster instead of a single
# flat IDENTITY/SOUL pair — its role files are exempted from the per-file role check.
ROLE_FILES=("00-START-HERE.md" "IDENTITY.md" "SOUL.md" "governing-personas.md" "how-to.md" "ROSTER.md")

echo ""
echo "═══ Skill 42 — Personal Assistant Library — Install QC ═══"
echo ""

assert "Skill 42 folder present" "[ -d \"$PA_DIR\" ]"
assert "specialists/ folder present" "[ -d \"$SPEC_DIR\" ]"
assert "specialists/_index.md present" "[ -f \"$SPEC_DIR/_index.md\" ]"
assert "all 29 specialist folders present" "[ \$(find \"$SPEC_DIR\" -maxdepth 1 -type d -name '[0-9][0-9]-*' 2>/dev/null | wc -l | tr -d ' ') -eq 29 ]"

for slug in "${SPECIALISTS[@]}"; do
  assert "specialist $slug present" "[ -d \"$SPEC_DIR/$slug\" ]"
  if [ "$slug" = "19-study-partner" ]; then
    # Sub-specialist roster: require the orientation + roster + SOP, not the flat role set.
    assert "$slug has 00-START-HERE.md + ROSTER.md" "[ -f \"$SPEC_DIR/$slug/00-START-HERE.md\" ] && [ -f \"$SPEC_DIR/$slug/ROSTER.md\" ]"
  else
    for rf in "${ROLE_FILES[@]}"; do
      assert "$slug has $rf" "[ -f \"$SPEC_DIR/$slug/$rf\" ]"
    done
  fi
  assert "$slug has SOP/00-INDEX.md" "[ -f \"$SPEC_DIR/$slug/SOP/00-INDEX.md\" ]"
  assert "$slug has >=1 SOP PA-NN-NN.md" "[ \$(find \"$SPEC_DIR/$slug/SOP\" -name 'PA-*.md' 2>/dev/null | wc -l | tr -d ' ') -ge 1 ]"
done

assert "162 SOP PA-NN-NN.md files total" "[ \$(find \"$SPEC_DIR\" -path '*/SOP/PA-*.md' 2>/dev/null | wc -l | tr -d ' ') -eq 162 ]"
assert "29 SOP/00-INDEX.md files total" "[ \$(find \"$SPEC_DIR\" -path '*/SOP/00-INDEX.md' 2>/dev/null | wc -l | tr -d ' ') -eq 29 ]"
assert "no working artifacts shipped (.bak/.tmp/QC-READY.txt)" "[ \$(find \"$PA_DIR\" \\( -name '*.bak' -o -name '*.tmp' -o -name 'QC-READY.txt' \\) 2>/dev/null | wc -l | tr -d ' ') -eq 0 ]"
assert "verify-pa-install.sh present" "[ -f \"$PA_DIR/scripts/verify-pa-install.sh\" ]"

warn_only "Skill 23 (AI Workforce) installed (required for workspace materialization)" "[ -d \"$SKILLS_DIR_DEFAULT/23-ai-workforce-blueprint\" ]"
warn_only "Skill 22 (Persona) installed (recommended; graceful degradation supported)" "[ -d \"$SKILLS_DIR_DEFAULT/22-book-to-persona-coaching-leadership-system\" ]"

echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 42 QC FAILED"; exit 1; } || { green "Skill 42 QC PASS"; exit 0; }
