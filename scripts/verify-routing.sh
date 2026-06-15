#!/usr/bin/env bash
# verify-routing.sh — FAIL-LOUD gate: verifies all 4 routing-fix layers on this box.
#
# Checks:
#   G1  ROLE_DISCIPLINE_V1 marker present in the resolved AGENTS.md (exactly once)
#   G2  CEO_ROUTING_NO_LOOPHOLES_V1 marker present in the resolved AGENTS.md
#   G3  PRIME DIRECTIVE (CEO_ORCHESTRATOR_RULE_V2) present in the resolved SOUL.md
#   G4  default agent has skills:[] in openclaw.json (pptx skill physically blocked)
#       "default agent" = first agent with default:true; falls back to id="main"
#   G5  workspace real-path is in skills.load.allowSymlinkTargets
#   G6  at least one department workspace row exists in mission-control.db
#
# Exit codes:
#   0  — all checks pass (routing is clean)
#   1  — one or more checks failed (FATAL — do not proceed)
#
# Usage:
#   bash verify-routing.sh             # check + report + exit
#   bash verify-routing.sh --quiet     # exit code only (no printed output)
#
# Designed to be wired as a hard precondition gate in run-closeout.sh (Skill 37).
# Also callable standalone for fleet sweeps or CI.

set -euo pipefail

QUIET=0
for _arg in "$@"; do
  [[ "$_arg" == "--quiet" ]] && QUIET=1
done

_pass() { [ "$QUIET" = "0" ] && printf '[verify-routing] PASS  %s\n' "$*"; }
_fail() { printf '[verify-routing] FATAL %s\n' "$*" >&2; }
_info() { [ "$QUIET" = "0" ] && printf '[verify-routing] INFO  %s\n' "$*"; }

FAILURES=0

# ─── Platform detection ───────────────────────────────────────────────────────

if [ -f /data/.openclaw/openclaw.json ]; then
  OC_ROOT="/data/.openclaw"
elif [ -f "$HOME/.openclaw/openclaw.json" ]; then
  OC_ROOT="$HOME/.openclaw"
else
  _fail "cannot find openclaw.json in /data/.openclaw or $HOME/.openclaw"
  exit 1
fi

OC_CONFIG="$OC_ROOT/openclaw.json"

# ─── Resolve main agent workspace ────────────────────────────────────────────

WORKSPACE_DIR=""

WORKSPACE_DIR=$(OC_JSON="$OC_CONFIG" python3 - <<'PYEOF'
import json, os, sys
try:
    cfg = json.load(open(os.environ['OC_JSON']))
    for ag in cfg.get('agents', {}).get('list', []) or []:
        if isinstance(ag, dict) and ag.get('id') == 'main':
            ws = ag.get('workspace')
            if ws:
                print(os.path.expanduser(ws))
                sys.exit(0)
except Exception:
    pass
sys.exit(0)
PYEOF
) || WORKSPACE_DIR=""

if [ -z "$WORKSPACE_DIR" ] && command -v openclaw >/dev/null 2>&1; then
  WORKSPACE_DIR=$(openclaw config get agents.defaults.workspace 2>/dev/null \
    | head -1 | python3 -c "
import sys, json, os
try:
    raw = sys.stdin.read().strip()
    print(os.path.expanduser(json.loads(raw) if raw.startswith('\"') else raw))
except Exception:
    pass
" 2>/dev/null) || WORKSPACE_DIR=""
fi

WORKSPACE_DIR="${WORKSPACE_DIR:-$OC_ROOT/workspace}"

_info "config: $OC_CONFIG"
_info "workspace: $WORKSPACE_DIR"

AGENTS_FILE="$WORKSPACE_DIR/AGENTS.md"
SOUL_FILE="$WORKSPACE_DIR/SOUL.md"

# ─── G1: ROLE_DISCIPLINE_V1 in AGENTS.md ─────────────────────────────────────
_info "G1: checking ROLE_DISCIPLINE_V1 in $AGENTS_FILE"
if [ ! -f "$AGENTS_FILE" ]; then
  _fail "G1: AGENTS.md not found at $AGENTS_FILE"
  FAILURES=$((FAILURES + 1))
else
  RD_COUNT=$(grep -c "ROLE_DISCIPLINE_V1" "$AGENTS_FILE" 2>/dev/null || echo "0")
  if [ "$RD_COUNT" -eq 1 ]; then
    _pass "G1: ROLE_DISCIPLINE_V1 present in $AGENTS_FILE (count=$RD_COUNT)"
  elif [ "$RD_COUNT" -eq 0 ]; then
    _fail "G1: ROLE_DISCIPLINE_V1 MISSING from $AGENTS_FILE — run apply-routing-fix.sh"
    FAILURES=$((FAILURES + 1))
  else
    _fail "G1: ROLE_DISCIPLINE_V1 appears $RD_COUNT times in $AGENTS_FILE (expected 1) — de-dup needed"
    FAILURES=$((FAILURES + 1))
  fi
fi

# ─── G2: CEO_ROUTING_NO_LOOPHOLES_V1 in AGENTS.md ────────────────────────────
_info "G2: checking CEO_ROUTING_NO_LOOPHOLES_V1 in $AGENTS_FILE"
if [ -f "$AGENTS_FILE" ] && grep -qF "CEO_ROUTING_NO_LOOPHOLES_V1" "$AGENTS_FILE" 2>/dev/null; then
  _pass "G2: CEO_ROUTING_NO_LOOPHOLES_V1 present in $AGENTS_FILE"
else
  _fail "G2: CEO_ROUTING_NO_LOOPHOLES_V1 MISSING from $AGENTS_FILE — run apply-routing-fix.sh"
  FAILURES=$((FAILURES + 1))
fi

# ─── G3: PRIME DIRECTIVE in SOUL.md ──────────────────────────────────────────
_info "G3: checking CEO_ORCHESTRATOR_RULE_V2 (PRIME DIRECTIVE) in $SOUL_FILE"
if [ -f "$SOUL_FILE" ] && grep -qF "CEO_ORCHESTRATOR_RULE_V2" "$SOUL_FILE" 2>/dev/null; then
  _pass "G3: CEO_ORCHESTRATOR_RULE_V2 (PRIME DIRECTIVE) present in $SOUL_FILE"
else
  _fail "G3: CEO_ORCHESTRATOR_RULE_V2 MISSING from $SOUL_FILE — run apply-routing-fix.sh"
  FAILURES=$((FAILURES + 1))
fi

# ─── G4: default agent has skills:[] ─────────────────────────────────────────
# The "default agent" is the first entry in agents.list with default:true;
# if none carries that flag, fall back to id=="main" (pre-v10 convention).
# Boxes whose primary agent is named "ceo", "dept-master-orchestrator", or any
# other id would previously trigger a false-FATAL here.
_info "G4: detecting default agent and checking skills:[] in $OC_CONFIG"
G4_RESULT=$(python3 - "$OC_CONFIG" <<'PYEOF'
import json, sys
from pathlib import Path

try:
    cfg = json.loads(Path(sys.argv[1]).read_text())
    agents_list = cfg.get("agents", {}).get("list", []) or []

    # Priority 1: agent with default:true
    default_agent = None
    for ag in agents_list:
        if isinstance(ag, dict) and ag.get("default") is True:
            default_agent = ag
            break

    # Priority 2: fall back to id=="main" (legacy convention)
    if default_agent is None:
        for ag in agents_list:
            if isinstance(ag, dict) and ag.get("id") == "main":
                default_agent = ag
                break

    if default_agent is None:
        print("NO_DEFAULT_AGENT")
        sys.exit(0)

    agent_id = default_agent.get("id", "<unknown>")
    skills = default_agent.get("skills")
    if isinstance(skills, list) and len(skills) == 0:
        print(f"PASS:{agent_id}")
    elif skills is None:
        print(f"MISSING_KEY:{agent_id}")
    else:
        print(f"HAS_SKILLS:{agent_id}:{json.dumps(skills)}")
except Exception as e:
    print(f"ERROR:{e}")
PYEOF
) || G4_RESULT="ERROR:python3_failed"

case "$G4_RESULT" in
  PASS:*)
    _G4_ID="${G4_RESULT#PASS:}"
    _pass "G4: default agent (id=${_G4_ID}) skills:[] is set (pptx skill blocked)"
    ;;
  MISSING_KEY:*)
    _G4_ID="${G4_RESULT#MISSING_KEY:}"
    _fail "G4: default agent (id=${_G4_ID}) has no 'skills' key in openclaw.json — pptx deny NOT applied; run apply-routing-fix.sh"
    FAILURES=$((FAILURES + 1))
    ;;
  HAS_SKILLS:*)
    # strip leading "HAS_SKILLS:" then extract id (up to first :) and remainder
    _G4_REST="${G4_RESULT#HAS_SKILLS:}"
    _G4_ID="${_G4_REST%%:*}"
    _G4_SKILLS="${_G4_REST#*:}"
    _fail "G4: default agent (id=${_G4_ID}) skills is not empty: ${_G4_SKILLS} — run apply-routing-fix.sh"
    FAILURES=$((FAILURES + 1))
    ;;
  NO_DEFAULT_AGENT)
    _fail "G4: no default agent found in openclaw.json agents.list (no default:true entry and no id=main fallback)"
    FAILURES=$((FAILURES + 1))
    ;;
  ERROR:*)
    _fail "G4: could not read openclaw.json: ${G4_RESULT#ERROR:}"
    FAILURES=$((FAILURES + 1))
    ;;
esac

# ─── G5: workspace real-path in allowSymlinkTargets ──────────────────────────
_info "G5: checking allowSymlinkTargets contains workspace real-path"

WS_REALPATH=""
if command -v realpath >/dev/null 2>&1; then
  WS_REALPATH=$(realpath -m "$WORKSPACE_DIR" 2>/dev/null) || WS_REALPATH="$WORKSPACE_DIR"
else
  WS_REALPATH=$(python3 -c "import pathlib; print(str(pathlib.Path('$WORKSPACE_DIR').resolve()))" 2>/dev/null) || WS_REALPATH="$WORKSPACE_DIR"
fi

G5_RESULT=$(python3 - "$OC_CONFIG" "$WS_REALPATH" <<'PYEOF'
import json, sys
from pathlib import Path

try:
    cfg = json.loads(Path(sys.argv[1]).read_text())
    ws_real = sys.argv[2]
    targets = cfg.get("skills", {}).get("load", {}).get("allowSymlinkTargets", []) or []
    if ws_real in targets:
        print("PASS")
    else:
        print(f"MISSING:{ws_real} not in {json.dumps(targets)}")
except Exception as e:
    print(f"ERROR:{e}")
PYEOF
) || G5_RESULT="ERROR:python3_failed"

case "$G5_RESULT" in
  PASS)
    _pass "G5: $WS_REALPATH is in skills.load.allowSymlinkTargets"
    ;;
  MISSING:*)
    _fail "G5: allowSymlinkTargets MISSING workspace path — tasks skill will be blocked: ${G5_RESULT#MISSING:}; run apply-routing-fix.sh"
    FAILURES=$((FAILURES + 1))
    ;;
  ERROR:*)
    _fail "G5: could not read openclaw.json: ${G5_RESULT#ERROR:}"
    FAILURES=$((FAILURES + 1))
    ;;
esac

# ─── G6: department workspace rows exist in mission-control.db ────────────────
_info "G6: checking department workspace rows in mission-control.db"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ONBOARDING_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

DB_PATH=$(python3 - <<PYEOF
import sys
from pathlib import Path
import os
HOME = Path.home()

try:
    _SHARED_UTILS = Path("$ONBOARDING_DIR/shared-utils")
    sys.path.insert(0, str(_SHARED_UTILS))
    from resolve_db import find_dashboard_db
    p = find_dashboard_db()
    if p.exists():
        print(str(p))
        sys.exit(0)
except Exception:
    pass

candidates = [
    HOME / "projects/command-center/mission-control.db",
    HOME / "projects/mission-control/mission-control.db",
    Path("/data/projects/command-center/mission-control.db"),
    Path("/opt/mission-control/mission-control.db"),
    Path("/app/mission-control.db"),
]
for c in candidates:
    if c.exists():
        print(str(c))
        sys.exit(0)
sys.exit(1)
PYEOF
) || DB_PATH=""

if [ -z "$DB_PATH" ]; then
  _fail "G6: mission-control.db not found — Command Center (Skill 32) not installed; run apply-routing-fix.sh after CC install"
  FAILURES=$((FAILURES + 1))
else
  DEPT_COUNT=$(python3 - "$DB_PATH" <<'PYEOF'
import sqlite3, sys
try:
    conn = sqlite3.connect(sys.argv[1])
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM workspaces WHERE id != 'default' AND id != 'ceo'")
    count = cur.fetchone()[0]
    conn.close()
    print(str(count))
except Exception as e:
    print(f"ERROR:{e}")
PYEOF
) || DEPT_COUNT="ERROR:python3_failed"

  case "$DEPT_COUNT" in
    ERROR:*)
      _fail "G6: could not query mission-control.db: ${DEPT_COUNT#ERROR:}"
      FAILURES=$((FAILURES + 1))
      ;;
    0)
      _fail "G6: zero department workspace rows in $DB_PATH — run apply-routing-fix.sh (Layer 4)"
      FAILURES=$((FAILURES + 1))
      ;;
    *)
      _pass "G6: $DEPT_COUNT department workspace rows found in $DB_PATH"
      ;;
  esac
fi

# ─── Summary ─────────────────────────────────────────────────────────────────
echo ""
if [ "$FAILURES" -eq 0 ]; then
  _info "ALL CHECKS PASSED — routing is clean on this box"
  exit 0
else
  _fail "$FAILURES check(s) FAILED — routing defect is present on this box"
  _fail "Fix: bash ${SCRIPT_DIR}/apply-routing-fix.sh"
  exit 1
fi
