#!/usr/bin/env bash
# ============================================================
#  test-p207-general-task-catchall-probe.sh — P2-07 (c) steps 1+3 regression lock
#
#  Proves scripts/probe/p207-general-task-catchall-probe.py's two INDEPENDENT
#  checks (general-task workspace-row+runtime parity / routing-doctrine text
#  in the RESOLVED AGENTS.md) each correctly flip the overall verdict.
#
#  Every scenario stubs a throwaway sqlite DB, a throwaway openclaw.json, and
#  a throwaway AGENTS.md so this test NEVER touches the real
#  mission-control.db, the real openclaw.json, or the real workspace.
#
#  FAIL-FIRST PROOF (reproducible): before
#  scripts/probe/p207-general-task-catchall-probe.py existed, scenario 0 below
#  fails (script not found) and every dependent scenario fails with it --
#  0/N pass. With the script shipped, N/N pass.
#
#  EXIT CODES: 0 all passed, 1 one or more failed.
# ============================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROBE="$REPO_ROOT/scripts/probe/p207-general-task-catchall-probe.py"
FAIL_COUNT=0
PASS_COUNT=0

_pass() { echo "  PASS: $1"; PASS_COUNT=$((PASS_COUNT + 1)); }
_fail() { echo "  FAIL: $1" >&2; FAIL_COUNT=$((FAIL_COUNT + 1)); }
_section() { echo ""; echo "=== $1 ==="; }

_section "Scenario 0 — the probe script must exist and be syntactically valid python3"
if [ -f "$PROBE" ]; then
  _pass "p207-general-task-catchall-probe.py shipped at $PROBE"
else
  _fail "p207-general-task-catchall-probe.py NOT FOUND at $PROBE -- pre-fix tree"
fi
if [ -f "$PROBE" ] && python3 -m py_compile "$PROBE" 2>/dev/null; then
  _pass "python3 -m py_compile OK"
else
  [ -f "$PROBE" ] && _fail "python3 -m py_compile FAILED"
fi
if [ ! -f "$PROBE" ]; then
  _section "SUMMARY"; echo "  Passed: $PASS_COUNT   Failed: $FAIL_COUNT"; exit 1
fi

TESTHOME="$(mktemp -d)"
trap 'rm -rf "$TESTHOME"' EXIT

_mk_db() {
  # $1=db path  $2=general_task_present(0/1)  $3=has_matching_agent_row(0/1)
  local db="$1" present="$2" matched="$3"
  python3 - "$db" "$present" "$matched" <<'PYEOF'
import sqlite3, sys
db, present, matched = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
conn = sqlite3.connect(db)
conn.execute("CREATE TABLE workspaces (id TEXT, name TEXT, slug TEXT, type TEXT)")
conn.execute("CREATE TABLE agents (workspace_id TEXT, name TEXT, role TEXT)")
if present:
    conn.execute("INSERT INTO workspaces (id, name, slug, type) VALUES ('ws-gt', 'General Task', 'general-task', 'dept')")
    if matched:
        conn.execute("INSERT INTO agents (workspace_id, name, role) VALUES ('ws-gt', 'General Task Lead', 'general-task')")
# Always seed one unrelated department so the table is non-empty either way.
conn.execute("INSERT INTO workspaces (id, name, slug, type) VALUES ('ws-x', 'Marketing', 'marketing', 'dept')")
conn.execute("INSERT INTO agents (workspace_id, name, role) VALUES ('ws-x', 'Marketing Lead', 'marketing')")
conn.commit()
conn.close()
PYEOF
}

_mk_config() {
  # $1=config path  $2=include_general_task_agent(0/1)
  local cfg="$1" include="$2"
  if [ "$include" = "1" ]; then
    cat > "$cfg" <<'EOF'
{"agents": {"list": [
  {"id": "dept-general-task", "workspace": "/tmp/does-not-matter"},
  {"id": "dept-marketing", "workspace": "/tmp/does-not-matter"}
]}}
EOF
  else
    cat > "$cfg" <<'EOF'
{"agents": {"list": [
  {"id": "dept-marketing", "workspace": "/tmp/does-not-matter"}
]}}
EOF
  fi
}

_mk_agents_md_full() {
  cat > "$1" <<'EOF'
<!-- CEO_ROUTING_NO_LOOPHOLES_V2 -->
## CEO ROUTING — NO LOOPHOLES

| Loophole | Status |
|----------|--------|
| "I don't know which department, so I'll do it myself" | VIOLATION — route to `department_slug: "general-task"` |

<!-- END CEO_ROUTING_NO_LOOPHOLES_V2 -->
---
EOF
}

_mk_agents_md_no_rule() {
  cat > "$1" <<'EOF'
<!-- CEO_ROUTING_NO_LOOPHOLES_V2 -->
## CEO ROUTING — NO LOOPHOLES

Some unrelated doctrine text with no general-task mention at all.

<!-- END CEO_ROUTING_NO_LOOPHOLES_V2 -->
---
EOF
}

_mk_agents_md_no_marker() {
  cat > "$1" <<'EOF'
# Just a plain AGENTS.md with no routing doctrine stamped at all.
Some other content.
EOF
}

_run_probe() { python3 "$PROBE" "$@"; }

# ─── Scenario 1: everything healthy — ARMED, exit 0 ─────────────────────────
_section "Scenario 1 — general-task row+runtime present AND doctrine text present -> ARMED, exit 0"
DB1="$TESTHOME/mc1.db"; _mk_db "$DB1" 1 1
CFG1="$TESTHOME/oc1.json"; _mk_config "$CFG1" 1
AMD1="$TESTHOME/AGENTS1.md"; _mk_agents_md_full "$AMD1"
OUT1="$(_run_probe --json --db "$DB1" --config "$CFG1" --agents-md "$AMD1" 2>&1)"; RC1=$?
if [ "$RC1" -eq 0 ] && echo "$OUT1" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['overall_armed'] is True
assert d['general_task_runtime']['runtime_matched'] is True
assert d['routing_doctrine']['marker_present'] is True
assert d['routing_doctrine']['rule_text_present'] is True
" 2>/dev/null; then
  _pass "healthy inputs -> ARMED, exit 0, all sub-fields correct"
else
  _fail "healthy inputs did not report ARMED (rc=$RC1): $OUT1"
fi

# ─── Scenario 2: general-task workspace row MISSING -> DEGRADED ────────────
_section "Scenario 2 — general-task workspace row missing (P2-06 wipe class) -> DEGRADED, exit 1"
DB2="$TESTHOME/mc2.db"; _mk_db "$DB2" 0 0
OUT2="$(_run_probe --json --db "$DB2" --config "$CFG1" --agents-md "$AMD1" 2>&1)"; RC2=$?
if [ "$RC2" -eq 1 ] && echo "$OUT2" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['overall_armed'] is False
assert d['general_task_runtime']['workspace_row_present'] is False
assert 'P2-06' in d['general_task_runtime']['note']
" 2>/dev/null; then
  _pass "missing workspace row correctly reported DEGRADED, points at P2-06 remediation"
else
  _fail "missing workspace row did not report DEGRADED correctly (rc=$RC2): $OUT2"
fi

# ─── Scenario 3: row present but NO matching runtime entry -> DEGRADED ─────
_section "Scenario 3 — general-task workspace row present but NO agents.list[] runtime match -> DEGRADED"
DB3="$TESTHOME/mc3.db"; _mk_db "$DB3" 1 0
CFG3="$TESTHOME/oc3.json"; _mk_config "$CFG3" 0
OUT3="$(_run_probe --json --db "$DB3" --config "$CFG3" --agents-md "$AMD1" 2>&1)"; RC3=$?
if [ "$RC3" -eq 1 ] && echo "$OUT3" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['overall_armed'] is False
assert d['general_task_runtime']['workspace_row_present'] is True
assert d['general_task_runtime']['runtime_matched'] is False
assert 'no_specialist_runtime' in d['general_task_runtime']['note']
" 2>/dev/null; then
  _pass "workspace row present + no runtime match correctly reported DEGRADED (no_specialist_runtime class)"
else
  _fail "no-runtime-match case did not report DEGRADED correctly (rc=$RC3): $OUT3"
fi

# ─── Scenario 4: doctrine rule text missing -> DEGRADED ─────────────────────
_section "Scenario 4 — CEO_ROUTING_NO_LOOPHOLES marker present but general-task rule text missing -> DEGRADED"
AMD4="$TESTHOME/AGENTS4.md"; _mk_agents_md_no_rule "$AMD4"
OUT4="$(_run_probe --json --db "$DB1" --config "$CFG1" --agents-md "$AMD4" 2>&1)"; RC4=$?
if [ "$RC4" -eq 1 ] && echo "$OUT4" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['overall_armed'] is False
assert d['routing_doctrine']['marker_present'] is True
assert d['routing_doctrine']['rule_text_present'] is False
" 2>/dev/null; then
  _pass "marker present but rule text missing correctly reported DEGRADED"
else
  _fail "missing-rule-text case did not report DEGRADED correctly (rc=$RC4): $OUT4"
fi

# ─── Scenario 5: doctrine marker entirely absent -> DEGRADED ───────────────
_section "Scenario 5 — no CEO_ROUTING_NO_LOOPHOLES marker at all (stamper never ran) -> DEGRADED"
AMD5="$TESTHOME/AGENTS5.md"; _mk_agents_md_no_marker "$AMD5"
OUT5="$(_run_probe --json --db "$DB1" --config "$CFG1" --agents-md "$AMD5" 2>&1)"; RC5=$?
if [ "$RC5" -eq 1 ] && echo "$OUT5" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['overall_armed'] is False
assert d['routing_doctrine']['marker_present'] is False
assert d['routing_doctrine']['rule_text_present'] is False
" 2>/dev/null; then
  _pass "no marker at all correctly reported DEGRADED"
else
  _fail "no-marker case did not report DEGRADED correctly (rc=$RC5): $OUT5"
fi

# ─── Scenario 6: RESOLVED AGENTS.md file does not exist at all -> DEGRADED ─
_section "Scenario 6 — RESOLVED AGENTS.md missing entirely (stamper never ran on this box) -> DEGRADED"
OUT6="$(_run_probe --json --db "$DB1" --config "$CFG1" --agents-md "$TESTHOME/does-not-exist.md" 2>&1)"; RC6=$?
if [ "$RC6" -eq 1 ] && echo "$OUT6" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['overall_armed'] is False
assert 'not found' in d['routing_doctrine']['note']
" 2>/dev/null; then
  _pass "missing AGENTS.md file correctly reported DEGRADED"
else
  _fail "missing-AGENTS.md case did not report DEGRADED correctly (rc=$RC6): $OUT6"
fi

# ─── Scenario 7: text (non-JSON) output includes the excerpt for LLM review ─
_section "Scenario 7 — human-readable output quotes the matched excerpt (for the Haiku LLM read)"
OUT7="$(_run_probe --db "$DB1" --config "$CFG1" --agents-md "$AMD1" 2>&1)"
if echo "$OUT7" | grep -q "excerpt:" && echo "$OUT7" | grep -q "VERDICT: ARMED"; then
  _pass "human-readable output includes a quoted excerpt + VERDICT line"
else
  _fail "human-readable output missing excerpt or verdict: $OUT7"
fi

_section "SUMMARY"
echo "  Passed: $PASS_COUNT   Failed: $FAIL_COUNT"
if [ "$FAIL_COUNT" -gt 0 ]; then
  exit 1
fi
exit 0
