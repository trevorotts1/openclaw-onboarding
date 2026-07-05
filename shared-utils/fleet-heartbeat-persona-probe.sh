#!/usr/bin/env bash
# ============================================================================
#  fleet-heartbeat-persona-probe.sh  —  persona-system observability probe
#  Version: v1.0.0  |  Added: 2026-07-05  (F4.4 lifecycle + F4.7 fleet skew)
#
#  PURPOSE
#  -------
#  Two cheap, read-mostly health signals for the persona matching subsystem,
#  meant to be called from the fleet heartbeat / an operator living-status doc:
#
#    (1) NAKED IN-FLIGHT COUNT (F4.4) — how many in-flight tasks (status
#        in_progress / review) are persona-"naked": no assigned persona AND no
#        recorded no_persona_required decision. On a healthy box (FDN-2 fallback
#        + the move-task Persona-Gate live) this is ZERO. A non-zero count is a
#        bug signal — surfaced, not silently tolerated.
#
#    (2) SYNTHETIC SELECTOR SELF-TEST (F4.7) — a `--no-record` dry-run of the
#        canonical selector, asserting selection ACTUALLY RUNS on THIS box (fleet
#        CC builds roll out unevenly; a loose cc-compat gate can pass while the
#        selector is absent/broken). Degrades LOUDLY — never silently — when
#        Skill 23 is missing.
#
#  ⚠️  OPERATOR-SIDE ONLY.  Per the operator-box-separate + silent-updates
#      doctrine this probe performs NO messaging of any kind. It writes an
#      operator report to stdout and sets an exit code. It MUST NEVER be wired to
#      a client-visible channel (Telegram/GHL). The heartbeat caller decides
#      where the operator sees it.  --no-record means it also never mutates the
#      selector's stickiness/variety/selection-log tables.
#
#  USAGE
#  -----
#    fleet-heartbeat-persona-probe.sh                 # human report, exit code
#    fleet-heartbeat-persona-probe.sh --json          # machine JSON
#    fleet-heartbeat-persona-probe.sh --box <label>   # tag the report with a box id
#    fleet-heartbeat-persona-probe.sh --db <path>     # override DB autodiscovery
#    fleet-heartbeat-persona-probe.sh --selector <p>  # override selector path
#
#  EXIT CODES
#    0  healthy      (selector runs AND naked==0)
#    1  degraded     (selector self-test failed OR naked>0)  ← operator attention
#    2  n/a          (no persona-aware DB / persona system not provisioned here)
# ============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

JSON=0
BOX="${OPENCLAW_BOX_LABEL:-$(hostname -s 2>/dev/null || echo unknown)}"
DB_OVERRIDE=""
SELECTOR_OVERRIDE="${MOVE_TASK_SELECTOR:-}"

while [ $# -gt 0 ]; do
    case "$1" in
        --json) JSON=1 ;;
        --box) shift; BOX="${1:-$BOX}" ;;
        --db) shift; DB_OVERRIDE="${1:-}" ;;
        --selector) shift; SELECTOR_OVERRIDE="${1:-}" ;;
        -h|--help) sed -n '2,45p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
    shift
done

# ── Resolve the selector (override → installed skills tree → repo-relative) ──
resolve_selector() {
    if [ -n "$SELECTOR_OVERRIDE" ] && [ -f "$SELECTOR_OVERRIDE" ]; then
        echo "$SELECTOR_OVERRIDE"; return 0
    fi
    local installed="$HOME/.openclaw/skills/23-ai-workforce-blueprint/scripts/persona-selector-v2.py"
    local repo="$REPO_ROOT/23-ai-workforce-blueprint/scripts/persona-selector-v2.py"
    if [ -f "$installed" ]; then echo "$installed"; return 0; fi
    if [ -f "$repo" ]; then echo "$repo"; return 0; fi
    echo ""; return 1
}
SELECTOR="$(resolve_selector)"

# ── (1) Naked in-flight count — delegated to python for schema tolerance ──
# Emits: "<state>|<naked>|<in_flight>|<db_path>"
#   state: ok | not_provisioned | no_db
NAKED_LINE="$(REPO_ROOT="$REPO_ROOT" DB_OVERRIDE="$DB_OVERRIDE" python3 - <<'PY'
import os, sqlite3, sys
sys.path.insert(0, os.path.join(os.environ["REPO_ROOT"], "shared-utils"))
db = os.environ.get("DB_OVERRIDE") or ""
if not db:
    try:
        from resolve_db import find_dashboard_db, is_db_found
        p = find_dashboard_db()
        if is_db_found(p):
            db = str(p)
    except Exception:
        db = ""
    if not db:
        from pathlib import Path
        for c in (Path.home()/"projects/command-center/mission-control.db",
                  Path("/data/projects/command-center/mission-control.db"),
                  Path("/app/mission-control.db")):
            if c.is_file():
                db = str(c); break
if not db or not os.path.isfile(db):
    print("no_db|0|0|"); raise SystemExit(0)
try:
    c = sqlite3.connect(db)
    cols = [r[1] for r in c.execute("PRAGMA table_info(tasks)")]
except Exception:
    print("no_db|0|0|%s" % db); raise SystemExit(0)
if "persona_id" not in cols:
    print("not_provisioned|0|0|%s" % db); raise SystemExit(0)

INFLIGHT = ("in_progress", "review")
qmarks = ",".join("?" * len(INFLIGHT))
in_flight = c.execute(
    "SELECT COUNT(*) FROM tasks WHERE status IN (%s)" % qmarks, INFLIGHT).fetchone()[0]

# naked = in-flight, no persona_id, no recorded no_persona_required decision.
conds = ["status IN (%s)" % qmarks,
         "(persona_id IS NULL OR TRIM(persona_id) = '')"]
if "no_persona_required" in cols:
    conds.append("COALESCE(no_persona_required,0) NOT IN (1,'1','true','True')")
if "persona_mode" in cols:
    conds.append("LOWER(COALESCE(persona_mode,'')) NOT IN "
                 "('none','not_required','not-required','mechanical')")
naked_q = ("SELECT COUNT(*) FROM tasks t WHERE " + " AND ".join(conds) +
           " AND NOT EXISTS (SELECT 1 FROM task_status_audit a "
           "  WHERE a.task_id = t.id AND a.gate IN "
           "  ('no-persona-required','healed-no-persona-required'))")
try:
    naked = c.execute(naked_q, INFLIGHT + INFLIGHT).fetchone()[0]
except sqlite3.OperationalError:
    # task_status_audit absent (fresh box) — drop the NOT EXISTS leg.
    naked_q2 = "SELECT COUNT(*) FROM tasks t WHERE " + " AND ".join(conds)
    naked = c.execute(naked_q2, INFLIGHT).fetchone()[0]
print("ok|%d|%d|%s" % (naked, in_flight, db))
PY
)"

DB_STATE="${NAKED_LINE%%|*}"
_rest="${NAKED_LINE#*|}"
NAKED="${_rest%%|*}"; _rest="${_rest#*|}"
IN_FLIGHT="${_rest%%|*}"
DB_PATH="${_rest#*|}"

# ── (2) Synthetic selector self-test (--no-record dry run) ──
SELFTEST="fail"; SELFTEST_DETAIL=""
if [ -z "$SELECTOR" ]; then
    SELFTEST="unavailable"
    SELFTEST_DETAIL="persona-selector-v2.py not found (Skill 23 not installed on this box)"
else
    OUT="$("${PYTHON:-python3}" "$SELECTOR" \
             --task "probe: write a short welcome email to a new subscriber" \
             --department general --no-llm --no-record --format json 2>/dev/null)"
    RC=$?
    if [ $RC -ne 0 ] || [ -z "$OUT" ]; then
        SELFTEST="fail"
        SELFTEST_DETAIL="selector exited $RC / empty output"
    else
        VERDICT="$(OUT="$OUT" python3 - <<'PY'
import json, os
try:
    d = json.loads(os.environ["OUT"])
except Exception:
    print("fail|unparseable JSON"); raise SystemExit(0)
pid = d.get("persona_id")
if d.get("no_persona_required"):
    print("ok|no_persona_required (mechanical synthetic — acceptable)"); raise SystemExit(0)
if pid and str(pid).strip():
    print("ok|selected %s" % pid); raise SystemExit(0)
print("fail|selector returned no persona_id and no no_persona_required")
PY
)"
        SELFTEST="${VERDICT%%|*}"
        SELFTEST_DETAIL="${VERDICT#*|}"
    fi
fi

# ── Verdict ──────────────────────────────────────────────────────────────────
EXIT=0
if [ "$DB_STATE" = "no_db" ] || [ "$DB_STATE" = "not_provisioned" ]; then
    # If the box has no persona-aware CC, the only meaningful signal is the
    # selector self-test. A working selector on a not-yet-provisioned box is fine.
    if [ "$SELFTEST" = "ok" ]; then EXIT=2; else EXIT=1; fi
else
    if [ "$SELFTEST" != "ok" ]; then EXIT=1; fi
    if [ "${NAKED:-0}" -gt 0 ] 2>/dev/null; then EXIT=1; fi
fi

if [ "$JSON" -eq 1 ]; then
    BOX="$BOX" DB_STATE="$DB_STATE" DB_PATH="$DB_PATH" NAKED="${NAKED:-0}" \
    IN_FLIGHT="${IN_FLIGHT:-0}" SELFTEST="$SELFTEST" DETAIL="$SELFTEST_DETAIL" \
    SELECTOR="$SELECTOR" EXIT="$EXIT" python3 - <<'PY'
import json, os
print(json.dumps({
    "probe": "persona-system",
    "box": os.environ["BOX"],
    "db_state": os.environ["DB_STATE"],
    "db_path": os.environ["DB_PATH"] or None,
    "naked_in_flight": int(os.environ["NAKED"]),
    "in_flight_total": int(os.environ["IN_FLIGHT"]),
    "selector_selftest": os.environ["SELFTEST"],
    "selector_selftest_detail": os.environ["DETAIL"],
    "selector_path": os.environ["SELECTOR"] or None,
    "verdict": {"0": "healthy", "1": "degraded", "2": "n/a"}[os.environ["EXIT"]],
    "operator_side_only": True,
}, indent=2))
PY
else
    echo "── persona-system probe [box: $BOX] ──"
    case "$DB_STATE" in
        no_db)          echo "  DB:            not found (Command Center not installed here)";;
        not_provisioned)echo "  DB:            $DB_PATH (no persona columns — persona system not provisioned)";;
        *)              echo "  DB:            $DB_PATH";
                        echo "  in-flight:     $IN_FLIGHT (in_progress + review)";
                        if [ "${NAKED:-0}" -gt 0 ] 2>/dev/null; then
                            echo "  naked:         $NAKED  ⚠️  DEGRADED — in-flight tasks with no persona / no no_persona_required";
                        else
                            echo "  naked:         0  ✔";
                        fi;;
    esac
    case "$SELFTEST" in
        ok)          echo "  selftest:      ✔  $SELFTEST_DETAIL";;
        unavailable) echo "  selftest:      ⚠️  UNAVAILABLE — $SELFTEST_DETAIL";;
        *)           echo "  selftest:      ✗  FAIL — $SELFTEST_DETAIL";;
    esac
    echo "  verdict:       $([ $EXIT -eq 0 ] && echo healthy || { [ $EXIT -eq 2 ] && echo 'n/a (not provisioned)' || echo 'DEGRADED — operator attention'; })"
    echo "  (operator-side only — this probe sends no messages)"
fi

exit "$EXIT"
