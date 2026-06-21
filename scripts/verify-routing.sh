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
#   G7  CEO/main agent tool-gate: production tools (write/edit/apply_patch/
#       browser/canvas/image/process) denied + GHL MCP denied by provider.
#       FAIL-WARN (not clean) while 'exec' is still allowed as the interim
#       ingest-routing path; --strict-exec hard-fails that interim state. When an
#       owner-consent sidecar is present the gate is intentionally lifted (INFO).
#   G8  CEO PreToolUse intent-gate hook is wired (Claude-Code boxes) AND the
#       owner-consent sidecar path is NOT inside any agent-writable workspace.
#       (block-and-redirect enforcement — goal doc Option 1). On pure OpenClaw
#       boxes with no Claude Code settings.json this gate is INFO/skip, since the
#       OpenClaw runtime brake is the Layer-1 hard tool-deny, not a hook.
#
# Runtime obedience probes (only with --probe; need a live Command Center):
#   G9   in-house master self-execution (no consent) → task failed + deliverable
#        discarded + work re-emitted to a specialist (QC state-gate).
#   G10  competence-excuse handback → 422 reject, task stays with the specialist
#        and is re-dispatched (no-bounce-back rule).
#   G11  CEO requested_model survives ingest onto tasks.model_id (model choice
#        preserved through the gate).
#
# Exit codes:
#   0  — all checks pass (routing is clean)
#   1  — one or more checks failed (FATAL — do not proceed)
#
# Usage:
#   bash verify-routing.sh                 # static gates G1–G8
#   bash verify-routing.sh --quiet         # exit code only (no printed output)
#   bash verify-routing.sh --strict-exec   # hard-fail G7 while exec is still allowed
#   bash verify-routing.sh --probe         # also run runtime probes G9/G10/G11
#                                          # (PROBE_BASE_URL overrides CC base URL)
#
# Designed to be wired as a hard precondition gate in run-closeout.sh (Skill 37).
# Also callable standalone for fleet sweeps or CI.

set -euo pipefail

QUIET=0
STRICT_EXEC=0
PROBE=0
for _arg in "$@"; do
  [[ "$_arg" == "--quiet" ]] && QUIET=1
  [[ "$_arg" == "--strict-exec" ]] && STRICT_EXEC=1
  [[ "$_arg" == "--probe" ]] && PROBE=1
done
# Base URL for the runtime probes (G9/G10/G11). Override with PROBE_BASE_URL.
PROBE_BASE_URL="${PROBE_BASE_URL:-http://localhost:4000}"

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

# ─── Gateway version detection (D1 — schema-aware G7b) ───────────────────────
# OpenClaw 2026.6.8 REJECTS agents.defaults.tools.* so apply-fleet-standards.sh
# expresses the GOAL-4 no-refusal baseline via the functional ungate instead
# (root tools.exec full+off + agents.defaults.subagents ungate). G7b must accept
# that functional ungate as the satisfied baseline on 2026.6.8 rather than demand
# the rejected agents.defaults.tools.allow. FLEET_OC_VERSION_OVERRIDE pins the
# version for deterministic tests.
TOOLS_DEFAULTS_REJECTED_VERSION="2026.6.8"
OC_VERSION=""
if command -v openclaw >/dev/null 2>&1; then
  _oc_raw="$(openclaw --version 2>&1 | tr -d '\r' | head -n1 || true)"
  OC_VERSION="$(printf '%s' "$_oc_raw" | grep -oE '20[0-9]{2}\.[0-9]+\.[0-9]+' | head -n1 || true)"
fi
OC_VERSION="${FLEET_OC_VERSION_OVERRIDE:-$OC_VERSION}"

# _ver_ge A B → 0 if version A >= version B (numeric YYYY.M.P compare).
_ver_ge() {
  printf '%s\n%s\n' "$2" "$1" | sort -t. -k1,1n -k2,2n -k3,3n -C
}

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

# ─── G7: CEO tool-gate present (GOAL-5 Item 1 — Layer-1 structural brake) ─────
# The hard structural brake: the CEO/orchestrator agent must DENY every
# production tool so skills:[] (G4) is not the only thing stopping in-house work.
# Asserts, on the resolved CEO agent in openclaw.json:
#   - tools.deny ⊇ {write, edit, apply_patch, browser, canvas, image, process}
#   - tools.byProvider["ghl-community-mcp"].deny == ["*"]  (GHL MCP denied)
#   - exec is NOT in tools.allow  → clean PASS
#     exec IS in tools.allow      → FAIL-WARN (interim routing hole; not clean)
#                                   unless a route-task MCP tool is allowed.
# The CEO agent is resolved as id==main → default:true → known CEO ids.
#
# NOTE: this gate intentionally PASSES on a CONSENTED box (owner carve-out
# active: ceo-consent.json present AND the gate lifted) — re-gating that box
# would fight the owner. If the consent sidecar is present, G7 reports INFO and
# does not fail (the QC state-gate covers a consented box at completion time).
_info "G7: checking CEO tool-gate (production tools denied on the orchestrator)"

# Honor an active owner-consent carve-out: if consent is granted, the lifted
# gate is EXPECTED, not a failure.
_CEO_CONSENT_FILE=""
if [ -n "${CEO_CONSENT_FILE:-}" ]; then
  _CEO_CONSENT_FILE="$CEO_CONSENT_FILE"
elif [ -f /data/.openclaw/state/ceo-consent.json ]; then
  _CEO_CONSENT_FILE="/data/.openclaw/state/ceo-consent.json"
elif [ -f "$HOME/.openclaw/state/ceo-consent.json" ]; then
  _CEO_CONSENT_FILE="$HOME/.openclaw/state/ceo-consent.json"
fi

G7_RESULT=$(python3 - "$OC_CONFIG" <<'PYEOF'
import json, sys
from pathlib import Path

REQUIRED_DENY = {"write", "edit", "apply_patch", "browser", "canvas", "image", "process"}
CEO_IDS = ("main", "dept-ceo", "ceo", "master-orchestrator", "dept-master-orchestrator")

try:
    cfg = json.loads(Path(sys.argv[1]).read_text())
    agents = cfg.get("agents", {}).get("list", []) or []

    # DEFECT 2 (v13.1.3): resolve the box's ACTUAL default agent (default:true)
    # FIRST, then fall back to id=="main", then known CEO ids. Boxes whose default
    # agent is "dept-executive-office" (default:true) were previously checked on a
    # different "main" agent — masking an ungated default agent.
    ceo = None
    for ag in agents:
        if isinstance(ag, dict) and ag.get("default") is True:
            ceo = ag; break
    if ceo is None:
        for ag in agents:
            if isinstance(ag, dict) and ag.get("id") == "main":
                ceo = ag; break
    if ceo is None:
        for ag in agents:
            if isinstance(ag, dict) and ag.get("id") in CEO_IDS:
                ceo = ag; break
    if ceo is None:
        print("NO_CEO_AGENT"); sys.exit(0)

    cid = ceo.get("id", "<unknown>")
    tools = ceo.get("tools")
    if not isinstance(tools, dict):
        print(f"NO_TOOLS:{cid}"); sys.exit(0)

    deny = set(tools.get("deny") or [])
    missing = REQUIRED_DENY - deny
    if missing:
        print(f"DENY_INCOMPLETE:{cid}:{','.join(sorted(missing))}"); sys.exit(0)

    # GHL MCP denied? accept byProvider form OR the name-glob fallback.
    bp = tools.get("byProvider") or {}
    ghl_bp = isinstance(bp, dict) and (
        bp.get("ghl-community-mcp", {}).get("deny") == ["*"]
        or bp.get("ghl-mcp", {}).get("deny") == ["*"]
    )
    ghl_glob = any(t in deny for t in ("ghl-community-mcp__*", "ghl-mcp__*"))
    if not (ghl_bp or ghl_glob):
        print(f"GHL_NOT_DENIED:{cid}"); sys.exit(0)

    allow = set(tools.get("allow") or [])
    has_route_tool = any(t.endswith("__route_task") or t == "route_task" for t in allow)
    if "exec" in allow and not has_route_tool:
        # Interim posture: exec is the routing path but also a production hole.
        print(f"INTERIM_EXEC:{cid}"); sys.exit(0)

    print(f"PASS:{cid}")
except Exception as e:
    print(f"ERROR:{e}")
PYEOF
) || G7_RESULT="ERROR:python3_failed"

# If an owner-consent carve-out is active, a lifted gate is expected → INFO only.
if [ -n "$_CEO_CONSENT_FILE" ] && [ -f "$_CEO_CONSENT_FILE" ]; then
  case "$G7_RESULT" in
    PASS:*) _pass "G7: CEO tool-gate present (id=${G7_RESULT#PASS:}) [consent sidecar also present]" ;;
    *)      _info "G7: owner-consent carve-out ACTIVE ($_CEO_CONSENT_FILE) — CEO tool-gate is intentionally lifted; QC state-gate covers this box. Not failing." ;;
  esac
else
  case "$G7_RESULT" in
    PASS:*)
      _pass "G7: CEO tool-gate present (id=${G7_RESULT#PASS:}) — production tools + GHL MCP denied, exec not exposed"
      ;;
    INTERIM_EXEC:*)
      # FAIL-WARN (visible, NOT a silent pass): the production denies ARE in
      # place (the main brake holds), but exec is still allowed as the routing
      # path — a residual hole until the route-task MCP tool ships. We do NOT
      # mark the box "clean" (no PASS line) yet we do NOT block closeout fleet-
      # wide on a state that is currently universal. Pass --strict-exec to make
      # this a hard FAILURE once route-task is expected on the box.
      if [ "${STRICT_EXEC:-0}" = "1" ]; then
        _fail "G7: CEO tool-gate INTERIM (id=${G7_RESULT#INTERIM_EXEC:}) — production tools denied BUT 'exec' still in allow (routing hole). --strict-exec set: ship the route-task MCP tool + remove exec from CEO_TOOL_ALLOW."
        FAILURES=$((FAILURES + 1))
      else
        printf '[verify-routing] WARN  G7: CEO tool-gate INTERIM (id=%s) — production tools + GHL MCP denied (brake holds), but '\''exec'\'' is still allowed as the ingest-routing path. NOT marked clean. Replace exec with the route-task MCP tool to clear; run with --strict-exec to hard-fail.\n' "${G7_RESULT#INTERIM_EXEC:}" >&2
      fi
      ;;
    DENY_INCOMPLETE:*)
      _G7_REST="${G7_RESULT#DENY_INCOMPLETE:}"
      _fail "G7: CEO tool-gate INCOMPLETE (id=${_G7_REST%%:*}) — missing denies: ${_G7_REST#*:}; run apply-routing-fix.sh (Layer 5)"
      FAILURES=$((FAILURES + 1))
      ;;
    GHL_NOT_DENIED:*)
      _fail "G7: CEO tool-gate (id=${G7_RESULT#GHL_NOT_DENIED:}) does NOT deny GHL MCP — add byProvider['ghl-community-mcp'].deny=['*']; run apply-routing-fix.sh (Layer 5)"
      FAILURES=$((FAILURES + 1))
      ;;
    NO_TOOLS:*)
      _fail "G7: CEO agent (id=${G7_RESULT#NO_TOOLS:}) has NO tools policy — production tools wide open; run apply-routing-fix.sh (Layer 5)"
      FAILURES=$((FAILURES + 1))
      ;;
    NO_CEO_AGENT)
      _fail "G7: no CEO/main agent found in openclaw.json agents.list"
      FAILURES=$((FAILURES + 1))
      ;;
    ERROR:*)
      _fail "G7: could not read openclaw.json: ${G7_RESULT#ERROR:}"
      FAILURES=$((FAILURES + 1))
      ;;
  esac
fi

# ─── G7b: GOAL-4 D4 no-refusal baseline (departments/sub-agents never refuse) ─
# The fleetwide ungate (4B+4C) must leave a positive no-refusal baseline so NO
# department or sub-agent ever refuses a job. There are TWO valid forms:
#
#   FORM A (legacy, < 2026.6.8): agents.defaults.tools.allow == ["*"]  (wide-open),
#     OR the explicit group set ["group:runtime","group:fs","group:web","group:plugins"].
#
#   FORM B (FUNCTIONAL UNGATE, required on 2026.6.8+): OpenClaw 2026.6.8 REJECTS any
#     agents.defaults.tools.* key ("agents.defaults: Invalid input"), so the
#     baseline is expressed with the VALID levers instead —
#         root tools.exec.security == "full" AND tools.exec.ask == "off"
#         AND agents.defaults.subagents.allowAgents contains "*".
#     That functional ungate IS the satisfied Goal-4 baseline on 2026.6.8.
#
# G7b PASSES when EITHER form is present. On 2026.6.8 the absence of
# agents.defaults.tools.allow is EXPECTED (not a failure); the functional ungate
# is what is checked. PAIRED with G7: this gate confirms "no refusals" while G7
# confirms the CEO is STILL gated — the per-box proof both coexist.
if [ -n "$OC_VERSION" ] && _ver_ge "$OC_VERSION" "$TOOLS_DEFAULTS_REJECTED_VERSION"; then
  G7B_SCHEMA_REJECTS_TOOLS=1
else
  G7B_SCHEMA_REJECTS_TOOLS=0
fi
_info "G7b: checking GOAL-4 no-refusal baseline (schema_rejects_defaults_tools=$G7B_SCHEMA_REJECTS_TOOLS, version=${OC_VERSION:-unknown})"
G7B_RESULT=$(G7B_SCHEMA_REJECTS_TOOLS="$G7B_SCHEMA_REJECTS_TOOLS" python3 - "$OC_CONFIG" <<'PYEOF'
import json, os, sys
from pathlib import Path
try:
    cfg = json.loads(Path(sys.argv[1]).read_text())
    schema_rejects = os.environ.get("G7B_SCHEMA_REJECTS_TOOLS", "0") == "1"

    agents_defaults = (cfg.get("agents", {}) or {}).get("defaults", {}) or {}
    allow = (agents_defaults.get("tools") or {}).get("allow")

    # FORM A — agents.defaults.tools.allow (valid only on schemas that accept it).
    form_a_wildcard = allow == ["*"]
    form_a_groups = isinstance(allow, list) and set(allow) >= {
        "group:runtime", "group:fs", "group:web", "group:plugins"
    }

    # FORM B — functional ungate (the satisfied baseline on 2026.6.8).
    exec_cfg = (cfg.get("tools") or {}).get("exec") or {}
    exec_full = exec_cfg.get("security") == "full" and exec_cfg.get("ask") == "off"
    sub_allow = (agents_defaults.get("subagents") or {}).get("allowAgents") or []
    sub_ungated = isinstance(sub_allow, list) and "*" in sub_allow
    form_b = exec_full and sub_ungated

    if form_a_wildcard:
        print("PASS:wildcard")
    elif form_a_groups:
        print("PASS:groups")
    elif form_b:
        print("PASS:functional")
    elif schema_rejects:
        # 2026.6.8: agents.defaults.tools.* is rejected, so its absence is expected;
        # the failure here is a MISSING functional ungate.
        print("MISSING_FUNCTIONAL:exec_full=%s sub_ungated=%s" % (exec_full, sub_ungated))
    elif allow is None:
        print("MISSING")
    else:
        print("WEAK:" + (",".join(map(str, allow)) if isinstance(allow, list) else str(allow)))
except Exception as e:
    print(f"ERROR:{e}")
PYEOF
) || G7B_RESULT="ERROR:python3_failed"
case "$G7B_RESULT" in
  PASS:wildcard)   _pass "G7b: no-refusal baseline present (agents.defaults.tools.allow=['*']) — departments + sub-agents never refuse" ;;
  PASS:groups)     _pass "G7b: no-refusal baseline present (explicit group grant) — departments + sub-agents have runtime/fs/web/plugins" ;;
  PASS:functional) _pass "G7b: no-refusal baseline present via FUNCTIONAL UNGATE (root tools.exec full+off + agents.defaults.subagents ungate) — 2026.6.8-valid Goal-4 baseline; departments + sub-agents never refuse" ;;
  MISSING_FUNCTIONAL:*)
    _fail "G7b: functional-ungate baseline MISSING on a 2026.6.8 schema (${G7B_RESULT#MISSING_FUNCTIONAL:}) — run apply-fleet-standards.sh (sets root tools.exec full+off + agents.defaults.subagents ungate)"
    FAILURES=$((FAILURES + 1)) ;;
  MISSING)
    _fail "G7b: no-refusal baseline MISSING (agents.defaults.tools.allow unset and no functional ungate) — run apply-fleet-standards.sh to set the GOAL-4 D4 baseline"
    FAILURES=$((FAILURES + 1)) ;;
  WEAK:*)
    _fail "G7b: no-refusal baseline WEAK (agents.defaults.tools.allow=${G7B_RESULT#WEAK:}) — not ['*'] nor the runtime/fs/web/plugins group set, and no functional ungate; departments may refuse jobs"
    FAILURES=$((FAILURES + 1)) ;;
  ERROR:*)
    _fail "G7b: could not read openclaw.json: ${G7B_RESULT#ERROR:}"
    FAILURES=$((FAILURES + 1)) ;;
esac

# ─── G8: CEO PreToolUse intent-gate wired + consent sidecar path safe ────────
# Block-and-redirect enforcement (goal doc Option 1). Two parts:
#   8a. Claude-Code box: settings.json hooks.PreToolUse contains an entry whose
#       command is .../ceo-intent-gate.sh. (On a pure OpenClaw box with no
#       settings.json, 8a is INFO/skip — the OpenClaw runtime brake is the
#       Layer-1 hard tool-deny, not a hook.)
#   8b. Consent-path safety: the resolved owner-consent sidecar must live OUTSIDE
#       the agent workspace (so the CEO agent cannot author its own consent).
_info "G8: checking CEO intent-gate hook + consent-path safety"

# 8a — locate a Claude Code settings.json (project then user level).
CC_SETTINGS=""
for _cand in \
  "${CLAUDE_SETTINGS_FILE:-}" \
  "$HOME/.claude/settings.json" \
  "/data/.claude/settings.json"; do
  [ -n "$_cand" ] || continue
  if [ -f "$_cand" ]; then CC_SETTINGS="$_cand"; break; fi
done

if [ -z "$CC_SETTINGS" ]; then
  _info "G8a: no Claude Code settings.json found — OpenClaw box; PreToolUse hook N/A (Layer-1 tool-deny is the brake here). Skipping 8a."
else
  G8A=$(SETTINGS_PATH="$CC_SETTINGS" python3 - <<'PYEOF'
import json, os, sys
try:
    cfg = json.load(open(os.environ["SETTINGS_PATH"]))
    pre = (cfg.get("hooks", {}) or {}).get("PreToolUse", []) or []
    found = False
    for entry in pre:
        if not isinstance(entry, dict):
            continue
        for h in entry.get("hooks", []) or []:
            cmd = h.get("command", "") if isinstance(h, dict) else ""
            if "ceo-intent-gate.sh" in cmd:
                found = True
    print("PASS" if found else "MISSING")
except Exception as e:
    print(f"ERROR:{e}")
PYEOF
) || G8A="ERROR:python3_failed"
  case "$G8A" in
    PASS) _pass "G8a: ceo-intent-gate.sh wired in $CC_SETTINGS hooks.PreToolUse" ;;
    MISSING)
      _fail "G8a: PreToolUse intent-gate NOT wired in $CC_SETTINGS — run install-ceo-intent-gate.sh"
      FAILURES=$((FAILURES + 1)) ;;
    ERROR:*)
      _fail "G8a: could not read $CC_SETTINGS: ${G8A#ERROR:}"
      FAILURES=$((FAILURES + 1)) ;;
  esac
fi

# 8b — consent sidecar path must be OUTSIDE the agent workspace.
CONSENT_LIB=""
for _cand in \
  "$ONBOARDING_DIR/hooks/lib-ceo-consent.sh" \
  "$OC_ROOT/hooks/lib-ceo-consent.sh"; do
  [ -f "$_cand" ] && CONSENT_LIB="$_cand" && break
done
if [ -z "$CONSENT_LIB" ]; then
  _fail "G8b: lib-ceo-consent.sh not found — consent reader missing; run install-ceo-intent-gate.sh"
  FAILURES=$((FAILURES + 1))
else
  # shellcheck source=/dev/null
  . "$CONSENT_LIB"
  CONSENT_PATH="$(ceo_consent_file)"
  # Resolve both to real-ish absolute paths for the containment test.
  _WS_ABS="$WS_REALPATH"
  case "$CONSENT_PATH" in
    "$_WS_ABS"/*|"$WORKSPACE_DIR"/*)
      _fail "G8b: consent sidecar ($CONSENT_PATH) is INSIDE the agent workspace ($_WS_ABS) — the CEO agent could author its own consent. UNSAFE."
      FAILURES=$((FAILURES + 1)) ;;
    *)
      _pass "G8b: consent sidecar ($CONSENT_PATH) is outside the agent workspace — agent cannot self-consent" ;;
  esac
fi

# ═════════════════════════════════════════════════════════════════════════════
# RUNTIME OBEDIENCE PROBES (G9/G10/G11) — only with --probe (need a live CC)
# ═════════════════════════════════════════════════════════════════════════════
# G1–G8 are static/config checks. The goal's Definition-of-Done demands proof of
# RUNTIME obedience: that a master self-execution is actually discarded+re-routed,
# that a competence-excuse bounce is actually rejected, and that a CEO-chosen
# model actually survives to dispatch. These probes plant fixtures and drive the
# real endpoints on a LIVE Command Center.
if [ "$PROBE" = "0" ]; then
  _info "G9/G10/G11: runtime probes skipped (pass --probe with a live CC to run them)"
else
  _info "G9/G10/G11: running runtime obedience probes against $PROBE_BASE_URL"

  # Resolve the DB (reuse G6's resolver). If absent, the probes cannot plant fixtures.
  PROBE_DB="${DB_PATH:-}"
  if [ -z "$PROBE_DB" ]; then
    _fail "G9/G10/G11: mission-control.db not found — cannot plant probe fixtures"
    FAILURES=$((FAILURES + 1))
  else
    # ── G9: in-house master self-execution → failed + discarded + re-routed ──
    _info "G9: probing in-house-master rejection (no consent) via agent-completion"
    G9_OUT=$(PROBE_DB="$PROBE_DB" PROBE_BASE_URL="$PROBE_BASE_URL" python3 - <<'PYEOF'
import json, os, sqlite3, urllib.request, uuid, sys

db = os.environ["PROBE_DB"]; base = os.environ["PROBE_BASE_URL"].rstrip("/")
conn = sqlite3.connect(db); conn.row_factory = sqlite3.Row; cur = conn.cursor()

# Find (or fail) a master agent + its workspace.
m = cur.execute("SELECT id, workspace_id FROM agents WHERE is_master = 1 LIMIT 1").fetchone()
if not m:
    print("SKIP:no-master-agent"); sys.exit(0)
master_id = m["id"]; ws = m["workspace_id"]

tid = str(uuid.uuid4())
cur.execute(
    "INSERT INTO tasks (id, title, description, status, priority, assigned_agent_id, created_by_agent_id, workspace_id, created_at, updated_at) "
    "VALUES (?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))",
    (tid, "PROBE G9 in-house master deliverable", "probe", "in_progress", "medium", master_id, master_id, ws),
)
did = str(uuid.uuid4())
cur.execute(
    "INSERT INTO task_deliverables (id, task_id, deliverable_type, title, created_at, updated_at) "
    "VALUES (?,?,?,?,datetime('now'),datetime('now'))",
    (did, tid, "file", "probe-artifact.html"),
)
conn.commit()

# Ensure NO consent sidecar covers this task: handled by env (CEO_CONSENT_FILE unset/empty file).
req = urllib.request.Request(
    base + "/api/webhooks/agent-completion",
    data=json.dumps({"task_id": tid, "summary": "did it myself"}).encode(),
    headers={"Content-Type": "application/json"}, method="POST",
)
status = None
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        status = r.status
except urllib.error.HTTPError as e:
    status = e.code  # 409 expected (in_house_master_block)
except Exception as e:
    print("ERROR:request-failed:%s" % e); sys.exit(0)

# Re-read DB state.
row = cur.execute("SELECT status FROM tasks WHERE id = ?", (tid,)).fetchone()
delrow = cur.execute("SELECT discarded FROM task_deliverables WHERE id = ?", (did,)).fetchone()
# A fresh re-emitted task with the same title should exist, NOT assigned to the master.
reemit = cur.execute(
    "SELECT id, assigned_agent_id FROM tasks WHERE title = ? AND id != ? ORDER BY created_at DESC LIMIT 1",
    ("PROBE G9 in-house master deliverable", tid),
).fetchone()
conn.close()

failed_ok = (row and row["status"] == "failed")
discarded_ok = (delrow and delrow["discarded"] == 1)
reemit_ok = (reemit is not None and reemit["assigned_agent_id"] != master_id)
if status == 409 and failed_ok and discarded_ok and reemit_ok:
    print("PASS")
else:
    print("FAIL:status=%s failed=%s discarded=%s reemit=%s" % (status, failed_ok, discarded_ok, reemit_ok))
PYEOF
) || G9_OUT="ERROR:python3_failed"
    case "$G9_OUT" in
      PASS)      _pass "G9: in-house-master deliverable was failed + discarded + re-routed to a specialist" ;;
      SKIP:*)    _info "G9: skipped (${G9_OUT#SKIP:}) — no master agent seeded to probe" ;;
      ERROR:*)   _fail "G9: probe error: ${G9_OUT#ERROR:}"; FAILURES=$((FAILURES + 1)) ;;
      *)         _fail "G9: in-house-master rejection did NOT fire as expected — ${G9_OUT}"; FAILURES=$((FAILURES + 1)) ;;
    esac

    # ── G10: competence-excuse handback → 422 reject, stays with specialist ──
    _info "G10: probing no-bounce-back (competence excuse) via return-to-orchestrator"
    G10_OUT=$(PROBE_DB="$PROBE_DB" PROBE_BASE_URL="$PROBE_BASE_URL" python3 - <<'PYEOF'
import json, os, sqlite3, urllib.request, uuid, sys

db = os.environ["PROBE_DB"]; base = os.environ["PROBE_BASE_URL"].rstrip("/")
conn = sqlite3.connect(db); conn.row_factory = sqlite3.Row; cur = conn.cursor()

# A non-master specialist + workspace.
s = cur.execute("SELECT id, workspace_id FROM agents WHERE COALESCE(is_master,0) = 0 LIMIT 1").fetchone()
if not s:
    print("SKIP:no-specialist-agent"); sys.exit(0)
spec_id = s["id"]; ws = s["workspace_id"]

tid = str(uuid.uuid4())
cur.execute(
    "INSERT INTO tasks (id, title, description, status, priority, assigned_agent_id, workspace_id, created_at, updated_at) "
    "VALUES (?,?,?,?,?,?,?,datetime('now'),datetime('now'))",
    (tid, "PROBE G10 bounce", "probe", "in_progress", "medium", spec_id, ws),
)
conn.commit()

# Competence-excuse handback with NO missing_input.
body = {
    "problem": "This is trivial, the CEO should do this himself.",
    "what_i_tried": "nothing, not my job",
    "what_i_think_it_needs": "the CEO knows how to do this",
}
req = urllib.request.Request(
    base + "/api/tasks/%s/return-to-orchestrator" % tid,
    data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST",
)
status = None; payload = {}
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        status = r.status; payload = json.loads(r.read() or b"{}")
except urllib.error.HTTPError as e:
    status = e.code
    try: payload = json.loads(e.read() or b"{}")
    except Exception: payload = {}
except Exception as e:
    print("ERROR:request-failed:%s" % e); sys.exit(0)

row = cur.execute("SELECT status, assigned_agent_id FROM tasks WHERE id = ?", (tid,)).fetchone()
conn.close()

# Expect: 422, rejected:true, task NOT in backlog (still with specialist), assignee unchanged.
rejected = bool(payload.get("rejected"))
stays = (row and row["assigned_agent_id"] == spec_id and row["status"] != "backlog")
if status == 422 and rejected and stays:
    print("PASS")
else:
    print("FAIL:status=%s rejected=%s stays=%s status_now=%s" % (status, rejected, stays, row["status"] if row else None))
PYEOF
) || G10_OUT="ERROR:python3_failed"
    case "$G10_OUT" in
      PASS)    _pass "G10: competence-excuse bounce rejected (422); task stayed with the specialist" ;;
      SKIP:*)  _info "G10: skipped (${G10_OUT#SKIP:}) — no specialist agent seeded to probe" ;;
      ERROR:*) _fail "G10: probe error: ${G10_OUT#ERROR:}"; FAILURES=$((FAILURES + 1)) ;;
      *)       _fail "G10: no-bounce-back gate did NOT reject as expected — ${G10_OUT}"; FAILURES=$((FAILURES + 1)) ;;
    esac

    # ── G11: CEO requested_model survives ingest → tasks.model_id ──
    _info "G11: probing model-choice survival via ingest requested_model"
    G11_OUT=$(PROBE_DB="$PROBE_DB" PROBE_BASE_URL="$PROBE_BASE_URL" python3 - <<'PYEOF'
import json, os, sqlite3, urllib.request, uuid, sys

db = os.environ["PROBE_DB"]; base = os.environ["PROBE_BASE_URL"].rstrip("/")
want_model = "probe/ceo-chosen-model-%s" % uuid.uuid4().hex[:8]
title = "PROBE G11 model survival %s" % uuid.uuid4().hex[:6]

req = urllib.request.Request(
    base + "/api/tasks/ingest",
    data=json.dumps({"title": title, "description": "probe", "requested_model": want_model}).encode(),
    headers={"Content-Type": "application/json"}, method="POST",
)
payload = {}
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        payload = json.loads(r.read() or b"{}")
except urllib.error.HTTPError as e:
    try: payload = json.loads(e.read() or b"{}")
    except Exception: payload = {}
except Exception as e:
    print("ERROR:request-failed:%s" % e); sys.exit(0)

new_id = payload.get("task_id")
if not new_id:
    print("FAIL:no-task-id payload=%s" % payload); sys.exit(0)

conn = sqlite3.connect(db); conn.row_factory = sqlite3.Row; cur = conn.cursor()
row = cur.execute("SELECT model_id FROM tasks WHERE id = ?", (new_id,)).fetchone()
conn.close()
if row and row["model_id"] == want_model:
    print("PASS")
else:
    print("FAIL:model_id=%s want=%s" % (row["model_id"] if row else None, want_model))
PYEOF
) || G11_OUT="ERROR:python3_failed"
    case "$G11_OUT" in
      PASS)    _pass "G11: CEO requested_model survived ingest onto tasks.model_id (model choice preserved)" ;;
      ERROR:*) _fail "G11: probe error: ${G11_OUT#ERROR:}"; FAILURES=$((FAILURES + 1)) ;;
      *)       _fail "G11: CEO model choice did NOT survive ingest — ${G11_OUT}"; FAILURES=$((FAILURES + 1)) ;;
    esac
  fi
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
