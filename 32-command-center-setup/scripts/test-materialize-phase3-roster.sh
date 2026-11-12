#!/usr/bin/env bash
# test-materialize-phase3-roster.sh — U-24 (CC-046).
#
# Phase 3 of materialize-dept-agents.sh must run from the roster file it was
# given, and must fail (not succeed silently) when that roster cannot be read.
#
# Three cases, each in its own temporary HOME, OpenClaw root and SQLite DB:
#   1. roster present (two departments)      -> exit 0, per-department rows written
#   2. roster absent, workspaces table there -> exit 0, rows written from the table
#   3. roster absent, workspaces table gone  -> non-zero exit, warning printed
#
# Nothing is written inside the repository: the script under test, its trio/quad
# library and a recording stub scaffolder are copied into the case folder.
# Asserts on exit codes and values read back from the database, never on a
# "search printed nothing".

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_SCRIPT="$SCRIPT_DIR/materialize-dept-agents.sh"
SOURCE_LIB="$SCRIPT_DIR/lib-trio-quad-rows.py"

if ! command -v python3 >/dev/null 2>&1; then
  echo "FATAL: python3 not on PATH — this test needs it (the script under test does too)"
  exit 1
fi
for _f in "$SOURCE_SCRIPT" "$SOURCE_LIB"; do
  if [[ ! -f "$_f" ]]; then
    echo "FATAL: missing $_f"
    exit 1
  fi
done

TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/u24-phase3.XXXXXX")" || {
  echo "FATAL: cannot create a temporary directory"
  exit 1
}
cleanup() { rm -rf "$TEST_ROOT"; }
trap cleanup EXIT

PASS=0
FAIL=0
ok()  { echo "ok   - $1"; PASS=$((PASS + 1)); }
bad() { echo "FAIL - $1"; FAIL=$((FAIL + 1)); }

# new_case <name>: sets up CASE_DIR / HOME / ROOT / DB / SCRIPTS for one case.
new_case() {
  CASE_DIR="$TEST_ROOT/$1"
  HOME="$CASE_DIR/home"
  ROOT="$HOME/.openclaw"
  SCRIPTS="$CASE_DIR/scripts"
  DB="$HOME/projects/command-center/mission-control.db"
  mkdir -p "$ROOT/workspace" "$SCRIPTS" "$(dirname "$DB")" "$CASE_DIR/tmp"

  cp "$SOURCE_SCRIPT" "$SCRIPTS/materialize-dept-agents.sh"
  cp "$SOURCE_LIB" "$SCRIPTS/lib-trio-quad-rows.py"
  # U-24 repair: the shared DB resolver lives two dirs above the scripts dir;
  # the copied script derives its path from its own location, so mirror the
  # same layout inside the case or Phase 3's resolver import always fails.
  if [[ -f "$SCRIPT_DIR/../../shared-utils/resolve_db.py" ]]; then
    mkdir -p "$CASE_DIR/shared-utils"
    cp "$SCRIPT_DIR/../../shared-utils/resolve_db.py" "$CASE_DIR/shared-utils/"
  fi

  # Recording stub for scaffold-agent-files.sh: one line of arguments per call.
  cat > "$SCRIPTS/scaffold-agent-files.sh" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "${SCAFFOLD_CALLS:?}"
exit 0
STUB
  chmod +x "$SCRIPTS/scaffold-agent-files.sh"
  export SCAFFOLD_CALLS="$CASE_DIR/scaffold-calls.txt"

  printf '{"agents": {}}\n' > "$ROOT/openclaw.json"
  cat > "$ROOT/workspace/.workforce-build-state.json" <<'JSON'
{"interviewComplete": true, "companySlug": "testco"}
JSON
  mkdir -p "$ROOT/workspace/departments"
}

# make_db full|bare — full has the workspaces + agents tables and two
# departments; bare has one unrelated table (so the file is not a 0-byte decoy)
# and NO workspaces table.
make_db() {
  python3 - "$DB" "$1" <<'PY'
import sqlite3
import sys

path, mode = sys.argv[1], sys.argv[2]
con = sqlite3.connect(path)
if mode == "full":
    con.execute(
        "CREATE TABLE workspaces (id TEXT PRIMARY KEY, name TEXT, slug TEXT)"
    )
    con.execute(
        "CREATE TABLE agents ("
        "id TEXT PRIMARY KEY, workspace_id TEXT, name TEXT, role TEXT, "
        "role_type TEXT, persona TEXT, description TEXT, specialist_type TEXT, "
        "status TEXT, avatar_emoji TEXT, is_master INTEGER, created_at TEXT, "
        "updated_at TEXT)"
    )
    con.executemany(
        "INSERT INTO workspaces (id, name, slug) VALUES (?, ?, ?)",
        [("ws-marketing", "Marketing", "marketing"),
         ("ws-sales", "Sales", "sales"),
         # Non-department rows the Command Center seeds under fixed identities
         # (structural default, setup General lane, engine lane, no-fit
         # catch-all). Phase 3's fallback must not write sub-agents into these.
         ("default", "General", "default"),
         ("testco-general", "General", "testco-general"),
         ("podcast", "Podcast", "podcast"),
         ("general-task", "General Task", "general-task")],
    )
elif mode == "bare":
    con.execute("CREATE TABLE unrelated (id INTEGER)")
else:
    raise SystemExit(f"unknown db mode: {mode}")
con.commit()
con.close()
PY
}

# run_script: runs the copied script with the case's HOME/root/DB.
# Sets OUT (combined output) and RC.
run_script() {
  OUT="$CASE_DIR/out.txt"
  HOME="$HOME" \
  DASHBOARD_DB_PATH="$DB" \
  TMPDIR="$CASE_DIR/tmp" \
    bash "$SCRIPTS/materialize-dept-agents.sh" > "$OUT" 2>&1
  RC=$?
}

agent_row_count() {
  python3 - "$DB" <<'PY'
import sqlite3
import sys

con = sqlite3.connect(sys.argv[1])
try:
    print(con.execute("SELECT COUNT(*) FROM agents").fetchone()[0])
except sqlite3.Error:
    print(-1)
finally:
    con.close()
PY
}

agent_workspace_count() {
  python3 - "$DB" <<'PY'
import sqlite3
import sys

con = sqlite3.connect(sys.argv[1])
try:
    print(con.execute("SELECT COUNT(DISTINCT workspace_id) FROM agents").fetchone()[0])
except sqlite3.Error:
    print(-1)
finally:
    con.close()
PY
}

# non_department_row_count: sub-agent rows Phase 3 wrote into the fixed-identity
# non-department rows make_db full seeds (structural default, setup General lane,
# engine lane, no-fit catch-all). Must be 0 — the fallback returns departments only.
non_department_row_count() {
  python3 - "$DB" <<'PY'
import sqlite3
import sys

con = sqlite3.connect(sys.argv[1])
try:
    print(con.execute(
        "SELECT COUNT(*) FROM agents WHERE workspace_id IN "
        "('default', 'testco-general', 'podcast', 'general-task')"
    ).fetchone()[0])
except sqlite3.Error:
    print(-1)
finally:
    con.close()
PY
}

output_has() {
  case "$(cat "$OUT" 2>/dev/null)" in
    *"$1"*) return 0 ;;
    *) return 1 ;;
  esac
}

scaffold_call_count() {
  if [[ -f "$SCAFFOLD_CALLS" ]]; then
    wc -l < "$SCAFFOLD_CALLS" | tr -d ' '
  else
    echo 0
  fi
}

show_output() { echo "      --- output ---"; sed 's/^/      /' "$OUT" 2>/dev/null; }

# ── Case 1: roster present, two departments ─────────────────────────────────
new_case case1
make_db full
mkdir -p "$ROOT/workspace/departments/marketing" "$ROOT/workspace/departments/sales"
run_script

if [[ "$RC" -eq 0 ]]; then
  ok "case 1: exit 0"
else
  bad "case 1: expected exit 0, got $RC"; show_output
fi
if output_has "could not read workspaces table"; then
  bad "case 1: output contains the unreadable-roster warning"; show_output
else
  ok "case 1: no unreadable-roster warning"
fi
_rows="$(agent_row_count)"
if [[ "$_rows" -eq 8 ]]; then
  ok "case 1: Phase 3 wrote 8 sub-agent rows (4 per department)"
else
  bad "case 1: expected 8 sub-agent rows, found $_rows"; show_output
fi
_ws="$(agent_workspace_count)"
if [[ "$_ws" -eq 2 ]]; then
  ok "case 1: rows landed on 2 departments"
else
  bad "case 1: expected rows on 2 departments, found $_ws"
fi
_calls="$(scaffold_call_count)"
if [[ "$_calls" -eq 2 ]]; then
  ok "case 1: scaffolder ran for both departments"
else
  bad "case 1: expected 2 scaffolder calls, found $_calls"
fi
if [[ -f "$ROOT/.materialize-dept-agents.manifest" ]]; then
  bad "case 1: roster file still present after the run"
else
  ok "case 1: roster file removed once Phase 3 used it"
fi

# ── Case 2: roster absent, workspaces table readable ────────────────────────
new_case case2
make_db full
run_script

if [[ "$RC" -eq 0 ]]; then
  ok "case 2: exit 0"
else
  bad "case 2: expected exit 0, got $RC"; show_output
fi
if output_has "could not read workspaces table"; then
  bad "case 2: output contains the unreadable-roster warning"; show_output
else
  ok "case 2: no unreadable-roster warning"
fi
_rows="$(agent_row_count)"
if [[ "$_rows" -eq 8 ]]; then
  ok "case 2: Phase 3 wrote 8 sub-agent rows from the workspaces table"
else
  bad "case 2: expected 8 sub-agent rows, found $_rows"; show_output
fi
_ws="$(agent_workspace_count)"
if [[ "$_ws" -eq 2 ]]; then
  ok "case 2: rows landed on the 2 departments in the table"
else
  bad "case 2: expected rows on 2 departments, found $_ws"
fi
_nd="$(non_department_row_count)"
if [[ "$_nd" -eq 0 ]]; then
  ok "case 2: no rows on non-department workspaces (default/testco-general/podcast/general-task)"
else
  bad "case 2: expected 0 rows on non-department workspaces, found $_nd"; show_output
fi

# ── Case 3: roster absent, workspaces table missing ─────────────────────────
new_case case3
make_db bare
run_script

if [[ "$RC" -ne 0 ]]; then
  ok "case 3: non-zero exit ($RC) when the roster cannot be read"
else
  bad "case 3: expected a non-zero exit, got 0"; show_output
fi
if output_has "could not read workspaces table"; then
  ok "case 3: warning names the unreadable roster"
else
  bad "case 3: expected the unreadable-roster warning"; show_output
fi

echo
echo "passed: $PASS  failed: $FAIL"
[[ "$FAIL" -eq 0 ]]
