#!/usr/bin/env bash
# tests/unit/move-task-persona-lifecycle.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# Hermetic tests for F4.4 — the Kanban Persona-Gate in
# 32-command-center-setup/scripts/move-task.py.
#
# Contract under test:
#   * INTO in_progress  -> warn-and-heal, NEVER blocks (availability > purity).
#   * INTO review       -> HARD gate: persona_id present OR no_persona_required
#                          recorded, else BLOCK (exit 2) unless --allow-no-persona.
#   * The heal invokes the canonical selector (bounded, --no-llm --no-record) and
#     applies its result to the task row.
#   * A board WITHOUT the persona_id column (Skill 23 not installed) is unaffected
#     — the gate is a silent no-op.
#
# The selector is stubbed via MOVE_TASK_SELECTOR + $STUB_MODE so every branch is
# deterministic. No network, no Gemini key, sqlite via python3 stdlib.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MOVE="$REPO_ROOT/32-command-center-setup/scripts/move-task.py"

PASS=0; FAIL=0
pass() { echo "  PASS: $*"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

[ -f "$MOVE" ] || { echo "FATAL: missing $MOVE"; exit 2; }

SB="$(mktemp -d -t mtpl-test.XXXXXX)"
trap 'rm -rf "$SB"' EXIT

# ── Stub selector: emits controllable JSON from $STUB_MODE, ignores its args ──
STUB="$SB/persona-selector-stub.py"
cat > "$STUB" <<'PY'
import json, os, sys
mode = os.environ.get("STUB_MODE", "persona")
if mode == "persona":
    print(json.dumps({"persona_id": "stub-persona", "persona_name": "Stub Persona",
                      "interaction_mode": "leadership", "score": 0.91}))
elif mode == "mechanical":
    print(json.dumps({"persona_id": None, "no_persona_required": True,
                      "message": "mechanical"}))
else:  # "null" — selector produced nothing usable (unresolved)
    print(json.dumps({"persona_id": None}))
sys.exit(0)
PY
export MOVE_TASK_SELECTOR="$STUB"

# ── DB builders ──────────────────────────────────────────────────────────────
# mk_db <path> <persona_aware:0|1>  → tasks table (+ one task 't1' naked, backlog)
mk_db() {
    local db="$1" aware="$2"
    DB="$db" AWARE="$aware" python3 - <<'PY'
import os, sqlite3
db=os.environ["DB"]; aware=os.environ["AWARE"]=="1"
c=sqlite3.connect(db)
cols = ["id TEXT PRIMARY KEY", "title TEXT", "description TEXT",
        "status TEXT", "department TEXT", "updated_at TEXT"]
if aware:
    cols += ["persona_id TEXT", "persona_name TEXT", "persona_mode TEXT",
             "persona_score REAL", "persona_selected_at TEXT"]
c.execute("CREATE TABLE tasks (%s)" % ", ".join(cols))
c.execute("INSERT INTO tasks (id,title,description,status,department) VALUES "
          "('t1','Write launch email','draft a promo email','backlog','marketing')")
c.commit(); c.close()
PY
}

# field <db> <col> → prints value of tasks.t1.<col> ('' if col absent/null)
field() {
    DB="$1" COL="$2" python3 - <<'PY'
import os, sqlite3
c=sqlite3.connect(os.environ["DB"])
try:
    r=c.execute("SELECT %s FROM tasks WHERE id='t1'" % os.environ["COL"]).fetchone()
    print("" if (not r or r[0] is None) else r[0])
except Exception:
    print("__NOCOL__")
PY
}
set_status() { DB="$1" ST="$2" python3 - <<'PY'
import os, sqlite3
c=sqlite3.connect(os.environ["DB"]); c.execute("UPDATE tasks SET status=? WHERE id='t1'",(os.environ["ST"],)); c.commit()
PY
}
audit_gate_present() { DB="$1" G="$2" python3 - <<'PY'
import os, sqlite3
c=sqlite3.connect(os.environ["DB"])
try:
    r=c.execute("SELECT 1 FROM task_status_audit WHERE task_id='t1' AND gate=? LIMIT 1",(os.environ["G"],)).fetchone()
    print("1" if r else "0")
except Exception:
    print("0")
PY
}
mv_move() { python3 "$MOVE" --db "$1" move --task t1 --to "$2" "${@:3}"; }

echo "== F4.4 Persona-Gate lifecycle =="

# ── T1: naked -> in_progress, stub returns persona -> proceeds + healed ──
DB="$SB/t1.db"; mk_db "$DB" 1
STUB_MODE=persona mv_move "$DB" in_progress >/dev/null 2>&1
rc=$?
[ "$rc" = "0" ] && pass "T1 in_progress never blocks (rc=0)" || fail "T1 rc=$rc (want 0)"
[ "$(field "$DB" status)" = "in_progress" ] && pass "T1 status advanced" || fail "T1 status=$(field "$DB" status)"
[ "$(field "$DB" persona_id)" = "stub-persona" ] && pass "T1 healed persona applied" || fail "T1 persona_id=$(field "$DB" persona_id)"

# ── T2: naked -> review, stub returns persona -> proceeds + healed ──
DB="$SB/t2.db"; mk_db "$DB" 1
STUB_MODE=persona mv_move "$DB" review >/dev/null 2>&1
rc=$?
[ "$rc" = "0" ] && pass "T2 review proceeds when heal assigns persona (rc=0)" || fail "T2 rc=$rc (want 0)"
[ "$(field "$DB" persona_id)" = "stub-persona" ] && pass "T2 persona_id set" || fail "T2 persona_id=$(field "$DB" persona_id)"

# ── T3: naked -> review, stub mechanical -> proceeds + no_persona_required ──
DB="$SB/t3.db"; mk_db "$DB" 1
STUB_MODE=mechanical mv_move "$DB" review >/dev/null 2>&1
rc=$?
[ "$rc" = "0" ] && pass "T3 review proceeds on no_persona_required (rc=0)" || fail "T3 rc=$rc (want 0)"
[ "$(field "$DB" persona_mode)" = "none" ] && pass "T3 no_persona_required recorded (mode=none)" || fail "T3 persona_mode=$(field "$DB" persona_mode)"
[ "$(audit_gate_present "$DB" healed-no-persona-required)" = "1" ] && pass "T3 audit marker written" || fail "T3 no audit marker"

# ── T4: naked -> review, stub null (unresolved) -> BLOCKED (exit 2) ──
DB="$SB/t4.db"; mk_db "$DB" 1
STUB_MODE=null mv_move "$DB" review >/dev/null 2>&1
rc=$?
[ "$rc" = "2" ] && pass "T4 naked review HARD-BLOCKED (rc=2)" || fail "T4 rc=$rc (want 2)"
[ "$(field "$DB" status)" = "backlog" ] && pass "T4 status unchanged (blocked)" || fail "T4 status=$(field "$DB" status)"
[ "$(audit_gate_present "$DB" blocked-naked-review)" = "1" ] && pass "T4 block audited" || fail "T4 no block audit"

# ── T5: naked -> review, stub null + --allow-no-persona -> proceeds ──
DB="$SB/t5.db"; mk_db "$DB" 1
STUB_MODE=null mv_move "$DB" review --allow-no-persona >/dev/null 2>&1
rc=$?
[ "$rc" = "0" ] && pass "T5 --allow-no-persona overrides (rc=0)" || fail "T5 rc=$rc (want 0)"
[ "$(field "$DB" persona_mode)" = "none" ] && pass "T5 override recorded no_persona_required" || fail "T5 persona_mode=$(field "$DB" persona_mode)"

# ── T6: task already has persona, stub null -> proceeds (heal not needed) ──
DB="$SB/t6.db"; mk_db "$DB" 1
DB="$DB" python3 - <<'PY'
import os, sqlite3
c=sqlite3.connect(os.environ["DB"]); c.execute("UPDATE tasks SET persona_id='already-set' WHERE id='t1'"); c.commit()
PY
STUB_MODE=null mv_move "$DB" review >/dev/null 2>&1
rc=$?
[ "$rc" = "0" ] && pass "T6 existing persona passes review (rc=0)" || fail "T6 rc=$rc (want 0)"

# ── T7: NON-persona-aware board -> gate is a silent no-op ──
DB="$SB/t7.db"; mk_db "$DB" 0
STUB_MODE=null mv_move "$DB" review >/dev/null 2>&1
rc=$?
[ "$rc" = "0" ] && pass "T7 non-persona board: gate no-op (rc=0)" || fail "T7 rc=$rc (want 0)"
[ "$(field "$DB" status)" = "review" ] && pass "T7 status advanced on non-persona board" || fail "T7 status=$(field "$DB" status)"

# ── T8: In Progress with unresolved selector still proceeds (never park) ──
DB="$SB/t8.db"; mk_db "$DB" 1
STUB_MODE=null mv_move "$DB" in_progress >/dev/null 2>&1
rc=$?
[ "$rc" = "0" ] && pass "T8 in_progress never parks even when naked (rc=0)" || fail "T8 rc=$rc (want 0)"
[ "$(audit_gate_present "$DB" warn-naked-in-progress)" = "1" ] && pass "T8 naked-in-progress warned+audited" || fail "T8 no warn audit"

echo ""
echo "── move-task-persona-lifecycle: PASS=$PASS FAIL=$FAIL ──"
[ "$FAIL" -eq 0 ] || exit 1
