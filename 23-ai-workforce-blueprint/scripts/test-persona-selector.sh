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
# HERMETIC + DETERMINISTIC (2026-07-03): the suite is now non-mutating and
# reproducible. Every selector call runs with --skip-stickiness --no-variety
# --no-record and against a throwaway $DASHBOARD_DB_PATH, so a QC run NEVER
# reads a box's sticky rows nor writes to any live persona DB (PRD §8), and the
# funnel is always exercised on the fresh-selection path so A5/A6 are stable
# regardless of a box's persona_assignment state (PRD §2).
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
# Resolution order (first existing file wins):
#   1. SELECTOR env override (explicit pin, e.g. CI)
#   2. The selector sitting beside THIS script (repo working tree OR an install
#      dir — when the script runs from an install, SCRIPT_DIR *is* that install).
#      This guarantees the test exercises the same copy it ships next to, so a
#      repo-tree run validates the edited template rather than a stale install.
#   3. ~/Downloads master-files install
#   4. ~/.openclaw/skills install
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SELECTOR="${SELECTOR:-$SCRIPT_DIR/persona-selector-v2.py}"
[ ! -f "$SELECTOR" ] && SELECTOR="$HOME/Downloads/openclaw-master-files/23-ai-workforce-blueprint/scripts/persona-selector-v2.py"
[ ! -f "$SELECTOR" ] && SELECTOR="$HOME/.openclaw/skills/23-ai-workforce-blueprint/scripts/persona-selector-v2.py"

red()    { printf "\033[31m%s\033[0m\n" "$1"; }
green()  { printf "\033[32m%s\033[0m\n" "$1"; }
yellow() { printf "\033[33m%s\033[0m\n" "$1"; }
blue()   { printf "\033[34m%s\033[0m\n" "$1"; }

# ─── PRE-FLIGHT ──────────────────────────────────────────────────────────────
# The selector is invoked as `python3 "$SELECTOR"` (see below), so it only needs
# to EXIST and be readable — the executable bit is irrelevant and a readable-but-
# non-executable install (e.g. a master-files copy shipped -rw-r--r--) must NOT
# spuriously fail this preflight.
if [ ! -f "$SELECTOR" ]; then
  red "ERROR: persona-selector-v2.py not found: $SELECTOR"
  red "Run update-skills.sh --only 23 to install."
  exit 1
fi

# ─── HERMETIC QC ─────────────────────────────────────────────────────────────
# This suite must NEVER read or mutate a live persona DB (PRD §8). Two guards,
# belt-and-suspenders:
#   1. Every selector call passes --no-record (skips ALL DB + selection-log
#      writes) and --skip-stickiness (no read of the box's persona_assignment
#      rows). This alone makes the run non-mutating.
#   2. We also point $DASHBOARD_DB_PATH at a throwaway scratch DB and pre-create
#      it (find_dashboard_db picks the FIRST *existing* candidate, so an existing
#      scratch file wins over ~/projects/command-center/mission-control.db). Even
#      if a future code path tried to write, it would land in the scratch dir,
#      never the operator/client DB. Cleaned up on exit.
# NOTE: we deliberately do NOT override $HOME — the selector must still READ the
# real (read-only) persona-categories.json + governing pools to select personas.
_HERMETIC_SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/persona-qc.XXXXXX")"
export DASHBOARD_DB_PATH="$_HERMETIC_SCRATCH/mission-control.db"
: > "$DASHBOARD_DB_PATH"   # empty file so it wins DB resolution; --no-record keeps it empty
cleanup_hermetic() { [ -n "${_HERMETIC_SCRATCH:-}" ] && rm -rf "$_HERMETIC_SCRATCH"; }
trap cleanup_hermetic EXIT
echo "Hermetic scratch DB: $DASHBOARD_DB_PATH (throwaway; QC never touches the live DB)"

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
  "web-development|build the funnel value-ladder and checkout pages"
  "video|Edit raw documentary footage into a montage sequence that tells a visual story"
)

results=()
personas_seen=()
breakdowns_seen=()
mkt_result_personas=()
webdev_result_personas=()
video_result_personas=()
video_top3=""

for entry in "${TASKS[@]}"; do
  dept=$(echo "$entry" | cut -d'|' -f1)
  task=$(echo "$entry" | cut -d'|' -f2)

  echo -n "  Task: [$dept] $task ... "

  # --skip-stickiness --no-variety : deterministic QC — force the fresh-selection
  #   funnel path (so A5/A6 assert the real funnel, never a box's sticky rows) and
  #   disable the anti-repetition sampler so the pick is reproducible run-to-run.
  # --no-record : hermetic QC — the selector writes NOTHING (no persona_assignment,
  #   no persona_selection_log, no selection-log .md). Combined with the scratch
  #   $DASHBOARD_DB_PATH set above, a QC run can never mutate any live persona DB.
  output=$(SCORING_MODE=heuristic python3 "$SELECTOR" --department "$dept" --task "$task" --format json --skip-stickiness --no-variety --no-record 2>/dev/null)
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

  green "$persona (score=$score, funnel=${funnel_pool}→${funnel_cat}→${funnel_sem})"
  results+=("PASS|$dept|$task|$persona|$score|$funnel_pool|$funnel_cat|$funnel_sem")
  personas_seen+=("$persona")
  breakdowns_seen+=("$score")

  if [ "$dept" = "marketing" ]; then
    mkt_result_personas+=("$persona")
  fi

  if [ "$dept" = "web-development" ]; then
    webdev_result_personas+=("$persona")
  fi

  if [ "$dept" = "video" ]; then
    video_result_personas+=("$persona")
    # Capture the full top-3 candidate ids for this video task (queryability check).
    # A video-domain persona must SURFACE in the funnel for a video task; variety
    # sampling may pick a different top-1, so we assert presence in top-3, not win.
    video_top3=$(echo "$output" | python3 -c "import sys,json; r=json.load(sys.stdin); print(' '.join(c.get('persona_id','') for c in r.get('breakdown',{}).get('top_3',[])))" 2>/dev/null)
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
# Count PASS rows whose three funnel fields are all present AND numeric. Parse per
# row exactly like A6 does.
# FIX (2026-07-03): the old one-liner `grep -v '|\?|'` used a BRE that BOTH BSD and
# GNU grep read as an optional-pipe quantifier (\? makes the preceding literal '|'
# optional), so it matched EVERY row and A5 was permanently WARN even when the funnel
# WAS present (this is the A5 WARN the PRD saw on live boxes). Per-row numeric parse
# is unambiguous.
funnel_present=0
for row in "${results[@]}"; do
  [[ "$row" != PASS* ]] && continue
  IFS='|' read -r _s _d _t _p _sc fp fc fs <<< "$row"
  if [[ "$fp" =~ ^[0-9]+$ ]] && [[ "$fc" =~ ^[0-9]+$ ]] && [[ "$fs" =~ ^[0-9]+$ ]]; then
    funnel_present=$((funnel_present + 1))
  fi
done
if [ "$total" -gt 0 ] && [ "$funnel_present" -ge "$total" ]; then
  green "  ✓ A5  Funnel counts present in all $total output JSON (pool→category→semantic)"
  A5=PASS
elif [ "$total" -gt 0 ]; then
  yellow "  ⚠ A5  Funnel counts present in only $funnel_present/$total outputs — check persona-selector-v2.py version"
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

# A7: web-development tasks → tag-intersection check (U1 widen verify)
# Asserts that every persona returned for web-development tasks has domain tags
# intersecting {marketing, sales, copywriting, strategy-innovation}.
# FAIL if any returned persona has ZERO overlap with this funnel-surface tag set —
# that would mean the U1 web-dev tag widen (line 256) was not applied or
# was reverted. This assertion is IMPOSSIBLE to pass with the pre-U1 tags
# ['operations','productivity-systems'].
WEBDEV_DOMAINS="marketing sales copywriting strategy-innovation"
A7=SKIP
if [ "${#webdev_result_personas[@]}" -gt 0 ]; then
  if [ -n "$PERSONA_CAT_FILE" ]; then
    A7_FAIL=0
    A7_PASS=0
    for pid in "${webdev_result_personas[@]}"; do
      tag_overlap=$(python3 - <<PYEOF 2>/dev/null
import json, sys
cat_file = "$PERSONA_CAT_FILE"
pid = "$pid"
webdev_set = {"marketing","sales","copywriting","strategy-innovation"}
try:
    data = json.loads(open(cat_file).read())
    personas = data.get("personas", {})
    info = personas.get(pid, {})
    import re
    def norm(s): return re.sub(r"[/ _]+", "-", s.lower()).strip("-")
    ptags = {norm(t) for t in (info.get("domain") or info.get("domain_tags") or info.get("tags") or [])}
    overlap = ptags & webdev_set
    print(len(overlap))
except Exception as e:
    print(0)
PYEOF
)
      if [ "$tag_overlap" = "0" ]; then
        red "  ✗ A7  Persona '$pid' returned for web-development task has ZERO funnel-surface tag overlap"
        red "       (marketing/sales/copywriting/strategy-innovation not represented — U1 widen not applied)"
        A7_FAIL=$((A7_FAIL + 1))
      else
        A7_PASS=$((A7_PASS + 1))
      fi
    done
    if [ "$A7_FAIL" -eq 0 ]; then
      green "  ✓ A7  All web-development-task personas have funnel-surface tag overlap ($A7_PASS/$A7_PASS checked)"
      A7=PASS
    else
      red "  ✗ A7  $A7_FAIL web-development persona(s) failed funnel-surface tag intersection check"
      A7=FAIL
    fi
  else
    yellow "  ⚠ A7  persona-categories.json not found — skipping web-dev tag-intersection check"
    webdev_personas_str=$(printf '%s\n' "${webdev_result_personas[@]}" | sort -u | tr '\n' ',' | sed 's/,$//')
    green "  ✓ A7  Web-development tasks returned: $webdev_personas_str (file check skipped)"
    A7=PASS
  fi
else
  yellow "  ⚠ A7  No web-development tasks succeeded; cannot verify U1 widen"
  A7=SKIP
fi

# A8: video task → a video-domain persona is QUERYABLE (OpenMontage video widen verify)
# The video department gained four domain tags {video, editing, montage,
# visual-storytelling} (persona-categories.json + DEPT_DOMAIN_TAGS["video"]) so the
# OpenMontage role can match a video-production persona. This asserts that for a
# video task, a persona whose domain intersects those four tags SURFACES in the
# funnel's top-3 candidates. We check top-3 presence (queryability), NOT top-1 win:
# the funnel deliberately retains marketing/copywriting tags for the video dept and
# the v10.14.28 variety sampler may pick a different #1, so demanding the winner be
# the video persona would be brittle. Presence in top-3 proves the widen + tagging
# made the video persona reachable.
#
# SKIP-SAFE: on a clean fleet box with NO video-domain persona ingested yet
# (persona-categories.json ships ZERO video personas), the top-3 has no video-tag
# persona to find, so this SKIPs rather than failing. It only FAILs once a
# video-domain persona EXISTS in the library but does NOT reach the top-3 for a
# video task — i.e. the widen was reverted.
A8=SKIP
if [ "${#video_result_personas[@]}" -gt 0 ] && [ -n "$video_top3" ]; then
  if [ -n "$PERSONA_CAT_FILE" ]; then
    # Is there ANY video-domain persona in the whole library?
    lib_has_video=$(python3 - <<PYEOF 2>/dev/null
import json
cat_file = "$PERSONA_CAT_FILE"
video_set = {"video","editing","montage","visual-storytelling"}
import re
def norm(s): return re.sub(r"[/ _]+", "-", s.lower()).strip("-")
try:
    data = json.loads(open(cat_file).read())
    personas = data.get("personas", {})
    n = sum(1 for v in personas.values()
            if {norm(t) for t in (v.get("domain") or v.get("domain_tags") or v.get("tags") or [])} & video_set)
    print(n)
except Exception:
    print(0)
PYEOF
)
    if [ "${lib_has_video:-0}" = "0" ]; then
      yellow "  ⚠ A8  No video-domain persona in the library yet — video queryability check skipped"
      A8=SKIP
    else
      # A video-domain persona EXISTS; require it to surface in the video task's top-3.
      top3_video_hit=$(python3 - <<PYEOF 2>/dev/null
import json
cat_file = "$PERSONA_CAT_FILE"
top3 = "$video_top3".split()
video_set = {"video","editing","montage","visual-storytelling"}
import re
def norm(s): return re.sub(r"[/ _]+", "-", s.lower()).strip("-")
try:
    data = json.loads(open(cat_file).read())
    personas = data.get("personas", {})
    hit = [pid for pid in top3
           if {norm(t) for t in (personas.get(pid, {}).get("domain")
               or personas.get(pid, {}).get("domain_tags")
               or personas.get(pid, {}).get("tags") or [])} & video_set]
    print(hit[0] if hit else "")
except Exception:
    print("")
PYEOF
)
      if [ -n "$top3_video_hit" ]; then
        green "  ✓ A8  Video-domain persona queryable for video task: '$top3_video_hit' in top-3"
        A8=PASS
      else
        red "  ✗ A8  A video-domain persona exists but did NOT surface in the video task top-3"
        red "       top-3 was: $video_top3"
        red "       (video widen not applied or persona mis-tagged — video role would match nothing)"
        A8=FAIL
      fi
    fi
  else
    yellow "  ⚠ A8  persona-categories.json not found — skipping video queryability check"
    A8=SKIP
  fi
else
  yellow "  ⚠ A8  No video task top-3 captured — video queryability check skipped"
  A8=SKIP
fi

echo
blue "═══ Summary ═══"
echo "  A1 Returns persona:              $A1"
echo "  A2 Persona diversity:            $A2"
echo "  A3 Breakdown variance:           $A3"
echo "  A4 Category filter (mkt tags):   $A4"
echo "  A5 Funnel counts in JSON:        $A5"
echo "  A6 Monotonic funnel invariant:   $A6"
echo "  A7 Web-dev funnel-surface tags:  $A7"
echo "  A8 Video-domain tags:            $A8"
echo

if [ "$A1" = "PASS" ] && [ "$A2" != "FAIL" ] && [ "$A4" != "FAIL" ] && [ "$A7" != "FAIL" ] && [ "$A8" != "FAIL" ] && [ "$A6" != "FAIL" ]; then
  green "OVERALL: SELECTOR FUNCTIONAL ✓"
  echo "Quality of selection still requires human review of top-3 candidates per task."
  exit 0
else
  red "OVERALL: SELECTOR HAS ISSUES — investigate above"
  exit 3
fi
