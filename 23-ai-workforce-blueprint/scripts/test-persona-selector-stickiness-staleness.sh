#!/usr/bin/env bash
# test-persona-selector-stickiness-staleness.sh
#
# Regression guard for the STICKY-CACHE STALENESS + CRAFT/VARIETY defect (v14.23.3).
#
# The live failure this locks down: the persona_assignment "stickiness" cache for
# (operations, design) had locked onto sinek-start-with-why (0.5915) even though the
# v14.15 craft-domain bonus already made rohde-the-sketchnote-workbook (0.6896) the
# correct fresh-score winner. Two compounding bugs caused it:
#   1. check_sticky_assignment() never read the needs_review flag, so a row the
#      selector itself flagged as stale (>= ANTI_STALENESS_THRESHOLD identical picks
#      in a row) was served FOREVER — detection without enforcement.
#   2. Even after a fresh re-score, anti-repetition variety could penalise / sample
#      AWAY the genuine craft specialist below a generalist, which stickiness would
#      then re-lock — defeating the entire purpose of craft routing.
#
# The fix: (a) a needs_review=1 row busts the cache -> forces a re-score; (b) on a
# genuine craft/specialty task the specialist (the top PRE-variety candidate carrying
# a craft_domain_bonus / specialty_tag_bonus) is exempt from the variety penalty and
# picked deterministically; (c) needs_review can clear once the streak resets.
#
# Hermetic + deterministic: HEURISTIC path (no gemini index / no API key in CI),
# canonical 54-persona persona-categories.json, temp HOME, temp sqlite DB. No client
# data — all personas are public authors.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPTS="$REPO_ROOT/23-ai-workforce-blueprint/scripts"
CANON_CATS="$REPO_ROOT/22-book-to-persona-coaching-leadership-system/persona-categories.json"

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

TMP_HOME="$(mktemp -d)"
DB="$TMP_HOME/mission-control.db"
trap 'rm -rf "$TMP_HOME"' EXIT

seed_db() {
  python3 - "$DB" <<'PY'
import sqlite3, sys
db = sys.argv[1]
c = sqlite3.connect(db)
c.executescript("""
DROP TABLE IF EXISTS persona_assignment;
DROP TABLE IF EXISTS persona_selection_log;
CREATE TABLE persona_assignment (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  department_id TEXT NOT NULL, task_category TEXT NOT NULL,
  persona_id TEXT NOT NULL, persona_name TEXT, persona_mode TEXT,
  persona_version INTEGER DEFAULT 1, last_score REAL,
  last_assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  switch_count INTEGER DEFAULT 0, consecutive_count INTEGER DEFAULT 0,
  needs_review INTEGER DEFAULT 0,
  UNIQUE (department_id, task_category));
CREATE TABLE persona_selection_log (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  task_id TEXT NOT NULL, persona_id TEXT NOT NULL, persona_name TEXT,
  mode TEXT, score REAL, layer_scores TEXT, department_id TEXT,
  selected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
""")
c.commit(); c.close()
PY
}

set_assignment() { # dept cat persona score consecutive needs_review
  sqlite3 "$DB" "INSERT INTO persona_assignment
    (department_id,task_category,persona_id,persona_name,persona_mode,last_score,consecutive_count,needs_review)
    VALUES ('$1','$2','$3','$3','leadership',$4,$5,$6)
    ON CONFLICT(department_id,task_category) DO UPDATE SET
      persona_id=excluded.persona_id, last_score=excluded.last_score,
      consecutive_count=excluded.consecutive_count, needs_review=excluded.needs_review;"
}

log_recent_use() { # dept cat persona n
  for _ in $(seq 1 "$4"); do
    sqlite3 "$DB" "INSERT INTO persona_selection_log (task_id,persona_id,department_id,layer_scores,selected_at)
      VALUES ('t-'||hex(randomblob(4)),'$3','$1','{\"task_category\":\"$2\"}', datetime('now','-1 hours'));"
  done
}

run_select() { # task dept [extra-flags]
  HOME="$TMP_HOME" OPENCLAW_PLATFORM=mac SCORING_MODE=heuristic \
  PERSONA_CATEGORIES_PATH="$CANON_CATS" DASHBOARD_DB_PATH="$DB" \
    python3 "$SCRIPTS/persona-selector-v2.py" \
      --task "$1" --department "$2" --format json ${3:-} 2>/dev/null \
  | python3 -c "import json,sys;print(json.load(sys.stdin).get('persona_id'))"
}

is_sticky() { # task dept  -> prints "yes"/"no"
  HOME="$TMP_HOME" OPENCLAW_PLATFORM=mac SCORING_MODE=heuristic \
  PERSONA_CATEGORIES_PATH="$CANON_CATS" DASHBOARD_DB_PATH="$DB" \
    python3 "$SCRIPTS/persona-selector-v2.py" \
      --task "$1" --department "$2" --format json 2>/dev/null \
  | python3 -c "import json,sys;print('yes' if json.load(sys.stdin).get('breakdown',{}).get('stickiness') else 'no')"
}

SK_TASK="Visually sketchnote and map our customer-onboarding process"

echo "=== test-persona-selector-stickiness-staleness.sh (heuristic, 54-persona pool) ==="
echo ""

# ── Test 1: a FLAGGED-STALE craft row busts the cache, craft routing wins, row heals ──
echo "--- 1) needs_review=1 stale sticky (sinek) is busted -> rohde wins + heals ---"
seed_db
set_assignment operations design sinek-start-with-why 0.5915 6 1   # poisoned + flagged
log_recent_use operations design rohde-the-sketchnote-workbook 3   # variety pressure on rohde
got="$(run_select "$SK_TASK" operations)"
[ "$got" = "rohde-the-sketchnote-workbook" ] \
  && pass "flagged-stale sinek busted -> $got" \
  || fail "flagged-stale row not busted -> $got (expected rohde-the-sketchnote-workbook)"
healed="$(sqlite3 "$DB" "SELECT persona_id||':'||needs_review FROM persona_assignment WHERE department_id='operations' AND task_category='design';")"
[ "$healed" = "rohde-the-sketchnote-workbook:0" ] \
  && pass "row healed -> $healed" \
  || fail "row did not heal -> $healed (expected rohde-the-sketchnote-workbook:0)"
echo ""

# ── Test 2: a TRUSTED sticky row (needs_review=0) is still honored (stickiness intact) ──
echo "--- 2) trusted sticky (needs_review=0) is honored, not re-scored ---"
seed_db
set_assignment operations design rohde-the-sketchnote-workbook 0.6896 2 0
sticky="$(is_sticky "$SK_TASK" operations)"
got="$(run_select "$SK_TASK" operations)"
{ [ "$sticky" = "yes" ] && [ "$got" = "rohde-the-sketchnote-workbook" ]; } \
  && pass "trusted sticky honored -> $got (stickiness=$sticky)" \
  || fail "trusted sticky not honored -> $got (stickiness=$sticky)"
echo ""

# ── Test 3: the bust is GENERAL, not craft-only — a flagged non-craft row re-scores ──
echo "--- 3) needs_review=1 is enforced for non-craft categories too (general re-score) ---"
seed_db
# Park an implausible persona on a sales email row and flag it stale.
set_assignment sales email-outreach goggins-cant-hurt-me 0.55 6 1
got="$(run_select "write a high-converting sales follow-up email to a warm lead" sales)"
[ "$got" != "goggins-cant-hurt-me" ] \
  && pass "flagged non-craft row busted + re-scored -> $got (not the parked goggins)" \
  || fail "flagged non-craft row served stale persona -> $got"
echo ""

echo "========================================"
echo "RESULTS: $PASS passed, $FAIL failed"
echo "========================================"
[ "$FAIL" -eq 0 ]
