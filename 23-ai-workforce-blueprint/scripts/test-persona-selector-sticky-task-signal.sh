#!/usr/bin/env bash
# test-persona-selector-sticky-task-signal.sh
#
# Regression guard for F3.5 — CATEGORY-LEVEL STICKINESS TASK-SIGNAL BYPASS.
#
# The defect this locks down: check_sticky_assignment() serves ONE cached persona
# for the whole (department, task_category) key (last_score >= 0.5), short-circuiting
# the funnel + Layer-5 semantic + perspective/specialty recall. With only ~17 coarse
# categories, two very different tasks collapse to the same key — e.g.
#   "write a landing page for Black women founders"   -> (marketing, content-write)
#   "write a blog post about productivity habits"     -> (marketing, content-write)
# so the second task's cached pick would be served for the first, and a lived-
# experience / named specialist never gets a chance while the row is TRUSTED
# (anti-staleness only fires after N identical picks).
#
# The fix (task_signal_bypasses_stickiness): before serving a sticky row, run two
# CHEAP detectors on the task text — infer_task_perspectives() (pure regex) and a
# specialty-hit probe over custom[] tags (NO embedding). If EITHER fires, skip
# stickiness for THIS task (out["sticky_bypassed"] = "task-signal") and fall through
# to a fresh full-funnel selection. Generic tasks fire neither -> the trusted fast
# path (breakdown.stickiness == True) is UNCHANGED.
#
# Hermetic + deterministic: HEURISTIC path (no gemini index / no API key in CI),
# canonical persona-categories.json, temp HOME, temp sqlite DB. No client data —
# all personas are public authors.
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

set_assignment() { # dept cat persona score  (needs_review=0 -> TRUSTED sticky)
  sqlite3 "$DB" "INSERT INTO persona_assignment
    (department_id,task_category,persona_id,persona_name,persona_mode,last_score,consecutive_count,needs_review)
    VALUES ('$1','$2','$3','$3','leadership',$4,1,0)
    ON CONFLICT(department_id,task_category) DO UPDATE SET
      persona_id=excluded.persona_id, last_score=excluded.last_score, needs_review=0;"
}

# Emits "<sticky>|<bypassed>|<persona_id>" for one selection.
run_probe() { # task dept
  HOME="$TMP_HOME" OPENCLAW_PLATFORM=mac SCORING_MODE=heuristic \
  PERSONA_CATEGORIES_PATH="$CANON_CATS" DASHBOARD_DB_PATH="$DB" \
    python3 "$SCRIPTS/persona-selector-v2.py" \
      --task "$1" --department "$2" --format json --no-record 2>/dev/null \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('%s|%s|%s' % ('yes' if d.get('breakdown',{}).get('stickiness') else 'no', d.get('sticky_bypassed') or '-', d.get('persona_id')))"
}

echo "=== test-persona-selector-sticky-task-signal.sh (F3.5, heuristic) ==="
echo ""

# ── 1) GENERIC task in a category with a TRUSTED sticky row -> served sticky (fast path intact) ──
echo "--- 1) generic content-write task keeps the trusted sticky fast path ---"
seed_db
set_assignment marketing content-write sinek-start-with-why 0.62
r="$(run_probe "write a blog post about productivity habits" marketing)"
sticky="${r%%|*}"; rest="${r#*|}"; bypassed="${rest%%|*}"; pid="${rest#*|}"
{ [ "$sticky" = "yes" ] && [ "$bypassed" = "-" ] && [ "$pid" = "sinek-start-with-why" ]; } \
  && pass "generic -> STICKY served, no bypass ($r)" \
  || fail "generic did not keep fast path ($r)"
echo ""

# ── 2) PERSPECTIVE task in the SAME sticky category -> stickiness bypassed (fresh selection) ──
echo "--- 2) perspective task (Black women) bypasses the same sticky row ---"
seed_db
set_assignment marketing content-write sinek-start-with-why 0.62
r="$(run_probe "write a landing page for Black women founders" marketing)"
sticky="${r%%|*}"; rest="${r#*|}"; bypassed="${rest%%|*}"; pid="${rest#*|}"
{ [ "$sticky" = "no" ] && [ "$bypassed" = "task-signal" ]; } \
  && pass "perspective -> sticky BYPASSED via task-signal ($r)" \
  || fail "perspective did NOT bypass stickiness ($r)"
echo ""

# ── 3) GENERIC email task with a TRUSTED sticky row -> served sticky (fast path intact) ──
echo "--- 3) generic email task keeps the trusted sticky fast path ---"
seed_db
set_assignment marketing email-outreach carnegie-how-to-win-friends-digital-age 0.58
r="$(run_probe "send the weekly newsletter" marketing)"
sticky="${r%%|*}"; rest="${r#*|}"; bypassed="${rest%%|*}"; pid="${rest#*|}"
{ [ "$sticky" = "yes" ] && [ "$bypassed" = "-" ] && [ "$pid" = "carnegie-how-to-win-friends-digital-age" ]; } \
  && pass "generic email -> STICKY served, no bypass ($r)" \
  || fail "generic email did not keep fast path ($r)"
echo ""

# ── 4) SPECIALTY-NAMED task in the SAME sticky category -> stickiness bypassed ──
echo "--- 4) named-specialty task (network marketing) bypasses the same sticky row ---"
seed_db
set_assignment marketing email-outreach carnegie-how-to-win-friends-digital-age 0.58
r="$(run_probe "write email copy about network marketing duplication" marketing)"
sticky="${r%%|*}"; rest="${r#*|}"; bypassed="${rest%%|*}"; pid="${rest#*|}"
{ [ "$sticky" = "no" ] && [ "$bypassed" = "task-signal" ]; } \
  && pass "specialty -> sticky BYPASSED via task-signal ($r)" \
  || fail "specialty did NOT bypass stickiness ($r)"
echo ""

echo "========================================"
echo "RESULTS: $PASS passed, $FAIL failed"
echo "========================================"
[ "$FAIL" -eq 0 ]
