#!/usr/bin/env bash
# Skill 42 — Personal Assistant Library — Install QC
#
# Modes:
#   (default)  structure + doc-truth checks on the shipped library (repo or installed)
#   --live     additionally run live-box assertions on a materialized PA department
#              (CC converge reachability + zero unfilled owner-data placeholders).
#              Enable with `--live` or PA_LIVE=1.
set -u
PASS=0; FAIL=0; WARN=0; SKIP=0
# Absolute dir of this script (sibling-43 pattern — works from any CWD).
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
LIB="$SKILL_DIR/../lib-shared.sh"; [ -f "$LIB" ] && source "$LIB"
if ! command -v resolve_platform_paths >/dev/null 2>&1; then
  # Fallback only when lib-shared.sh is absent. WORKSPACE must be the real OpenClaw
  # workspace root (the old `$HOME/clawd` literal was bogus and never a real path).
  resolve_platform_paths() { export WORKSPACE="$HOME/.openclaw/workspace" SKILLS_DIR_DEFAULT="$HOME/.openclaw/skills"; }
fi
resolve_platform_paths

# ── Mode detection ────────────────────────────────────────────────────────────
LIVE_MODE=0
for arg in "$@"; do [ "$arg" = "--live" ] && LIVE_MODE=1; done
[ "${PA_LIVE:-0}" = "1" ] && LIVE_MODE=1

red(){ printf "\033[31m%s\033[0m\n" "$1"; }; green(){ printf "\033[32m%s\033[0m\n" "$1"; }; yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }; cyan(){ printf "\033[36m%s\033[0m\n" "$1"; }
assert(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else red "  ✗ FAIL — $1"; FAIL=$((FAIL+1)); fi; }
warn_only(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else yellow "  ⚠ WARN — $1"; WARN=$((WARN+1)); fi; }
live_assert(){ if [ "$LIVE_MODE" -eq 0 ]; then cyan "  ⏭ SKIP — $1 (live-box only; re-run with --live on a materialized box)"; SKIP=$((SKIP+1)); return; fi; if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else red "  ✗ FAIL — $1"; FAIL=$((FAIL+1)); fi; }

PA_DIR="$SKILLS_DIR_DEFAULT/42-personal-assistant-library"
# When run from inside the repo/worktree (pre-deploy QC), the installed copy may not
# exist yet — fall back to the skill's own dir so QC tests THESE files (sibling-43).
[ -d "$PA_DIR" ] || PA_DIR="$SKILL_DIR"
SPEC_DIR="$PA_DIR/specialists"

# Owner-data placeholders substituted at MATERIALIZATION (the fill pass is responsible
# for these). Runtime output-template slots ({{PERCENT}}, {{WIN_1}}, {{TREND_ARROW}},
# {{COUNT}}, {{ACTION}} …) are intentionally NOT listed — the specialist fills those
# every run, so they legitimately remain in a materialized copy and must not fail QC.
INSTALL_PLACEHOLDERS='OWNER_NAME|OWNER|NAME|TOKEN|OWNER_EMAIL|OWNER_RECOVERY_EMAIL|OWNER_TIMEZONE|ROLE_TITLE|COMMUNICATION_STYLE|COMPANY_NAME|CLIENT_NAME|CLIENT_NAME_2|COMPANY_INDUSTRY|INDUSTRY_VERTICAL|DEPARTMENT_SLUG|WORKSPACE_PATH|COMPANY_LIBRARY_PATH|GENERATION_DATE|INBOX_TOOL|EMAIL_TOOL|CALENDAR_TOOL|TASK_TOOL|DOCS_TOOL|DOCUMENT_TOOL|MESSAGING_TOOL|COMMUNICATION_TOOL|CRM_TOOL|JOURNAL_TOOL|SEARCH_TOOL|DEEP_SEARCH_TOOL|NOTES_TOOL|RECORDING_TOOL|ZOOM_TOOL|VIDEO_TOOL|FINANCIAL_TOOL|METRICS_DASHBOARD|BOOK_PERSONA_MATRIX|ASSIGNED_PERSONA|ASSIGNED_PERSONA_VERSION|COACH_NAME|THERAPIST_NAME|CRISIS_LINE'

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
# Specialist 19 (Study Partner) is a sub-specialist ROSTER: it ships the standard 6
# role files PLUS 6 sub-role files, for 12 role files total. QC asserts ALL 12 (the
# old branch only checked 2 of them — a hole vs the 12 SKILL.md claims).
ROLE_FILES=("00-START-HERE.md" "IDENTITY.md" "SOUL.md" "governing-personas.md" "how-to.md" "ROSTER.md")
STUDY_PARTNER_SUBROLES=("01-snippet-curator.md" "02-reflection-guide.md" "03-book-curator.md" "04-knowledge-briefer.md" "05-accountability-coach.md" "06-study-partner-director.md")

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
    # Sub-specialist roster: assert ALL 12 role files — the standard 6 AND the 6 sub-roles.
    for rf in "${ROLE_FILES[@]}"; do
      assert "$slug has $rf" "[ -f \"$SPEC_DIR/$slug/$rf\" ]"
    done
    for sub in "${STUDY_PARTNER_SUBROLES[@]}"; do
      assert "$slug has sub-role $sub" "[ -f \"$SPEC_DIR/$slug/$sub\" ]"
    done
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
echo "── Materialization contract (CC converge + placeholder fill) ──"
# The mandatory closing step: materialization must run the Command Center converge
# (was never wired — a PA specialist could land in the workspace un-converged).
assert "INSTALL.md documents the closing 'sync-extensions.sh --converge'" \
  "grep -q 'sync-extensions.sh --converge' \"$PA_DIR/INSTALL.md\""
assert "INSTRUCTIONS.md documents the closing 'sync-extensions.sh --converge'" \
  "grep -q 'sync-extensions.sh --converge' \"$PA_DIR/INSTRUCTIONS.md\""
# The materialization workflow must include a post-fill residual placeholder scan.
assert "INSTALL.md documents a post-materialization residual placeholder scan" \
  "grep -q 'RESIDUAL' \"$PA_DIR/INSTALL.md\""

# ── Live-box assertions (materialized PA department only) ─────────────────────
PA_WS="$WORKSPACE/departments/personal-assistant"
CC_SYNC="$SKILLS_DIR_DEFAULT/32-command-center-setup/scripts/sync-extensions.sh"
# When a PA dept is materialized AND Command Center (Skill 32) is installed, the
# converge tool must be reachable so the mandatory closing step can run. Fail-soft:
# if either the PA dept or Skill 32 is absent, this is a no-op pass.
live_assert "CC converge tool reachable for materialized PA dept (fail-soft if Skill 32 absent)" \
  "[ ! -d \"$PA_WS\" ] || [ ! -d \"$SKILLS_DIR_DEFAULT/32-command-center-setup\" ] || [ -x \"$CC_SYNC\" ]"
# Zero unfilled owner-data placeholders may survive in the materialized copy (runtime
# output slots are exempt by construction — they are not in INSTALL_PLACEHOLDERS).
live_assert "no unfilled owner-data placeholder survives in materialized PA dept" \
  "[ ! -d \"$PA_WS\" ] || ! grep -rqE '\\{\\{('\"$INSTALL_PLACEHOLDERS\"')\\}\\}' \"$PA_WS\""

echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings | $SKIP skipped ═══"
[ $FAIL -gt 0 ] && { red "Skill 42 QC FAILED"; exit 1; } || { green "Skill 42 QC PASS"; exit 0; }
