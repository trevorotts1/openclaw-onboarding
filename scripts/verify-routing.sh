#!/usr/bin/env bash
# verify-routing.sh — FAIL-LOUD gate: verifies all 4 routing-fix layers on this box.
#
# Checks:
#   G1  ROLE_DISCIPLINE_V1 marker present in the resolved AGENTS.md (exactly once)
#   G2  CEO_ROUTING_NO_LOOPHOLES_V4_3 marker present in the resolved AGENTS.md
#   G3  PRIME DIRECTIVE (CEO_ORCHESTRATOR_RULE_V4_3) present in the resolved SOUL.md
#   G3b (V4.3) heading present in the installed ceo-routing-doctrine plugin dist
#   G4  default agent has skills:[] in openclaw.json (pptx skill physically blocked)
#       "default agent" = agents.defaults.systemAgent.agentId -> default:true ->
#       `agents list --json` isDefault -> id="main" -> router id ->
#       the id the CLI prints as "(default)" -> a single-entry agents.entries
#       (2026.10.x removed the per-entry default marker, so the config/JSON
#       sources are the live path now; they work with openclaw off PATH and
#       resolve agents that live as files under <oc-root>/agents/ instead of in
#       agents.list)
#   G5  workspace real-path is in skills.load.allowSymlinkTargets
#   G6  at least one department workspace row exists in mission-control.db
#   G7  CEO/main agent tools policy. The production-tool deny (write/edit/
#       apply_patch/browser/canvas/image/process) was RETIRED 2026-08-05 per
#       Trevor and is no longer asserted. Still enforced: per-agent tools schema
#       validity (no sessions/agentToAgent keys) + GHL MCP deny-by-provider.
#   G8  CEO PreToolUse intent-gate hook is INTENTIONALLY UNWIRED (2026-08-05 per
#       Trevor) — permanent INFO/PASS; the unwired state is the correct state.
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
#   bash verify-routing.sh --strict-exec   # RETIRED 2026-08-05: accepted but now a
#                                          # no-op (its only consumer, the G7
#                                          # INTERIM_EXEC arm, was removed with the
#                                          # production-tool deny gate)
#   bash verify-routing.sh --probe         # also run runtime probes G9/G10/G11
#                                          # (PROBE_BASE_URL overrides CC base URL)
#
# Designed to be wired as a hard precondition gate in run-closeout.sh (Skill 37).
# Also callable standalone for fleet sweeps or CI.

set -euo pipefail

QUIET=0
# STRICT_EXEC is RETIRED (2026-08-05). Still parsed so existing invocations and
# runbooks that pass --strict-exec do not look broken, but nothing reads it now:
# its only consumer was the G7 INTERIM_EXEC arm, removed with the production-tool
# deny gate. Kept assigned so `set -u` is safe if a future arm wants it back.
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

# ─── Decision-engine kill switch mode (KIL-001) ─────────────────────────────
# Same two sources, same order, as scripts/decision-engine-mode.py: env
# OPENCLAW_DECISION_ENGINE_MODE, then the first line of
# $OC_ROOT/decision-engine-mode.conf. Absent: release default 'auto'
# (RELEASE_DEFAULT writes nothing — preserve-by-construction). off/legacy
# share the same improved no-JEV engine; both emit zero JEV traffic.
# G2/G3 honour the switch: auto/shadow REQUIRE V4.3 present; off/legacy
# REQUIRE it ABSENT (a SUPPORTED kill — presence NOT required off-path).
# A corrupt/unknown value is FATAL here (fail loud, never silently re-enable).
KILL_MODE="$(printf '%s' "${OPENCLAW_DECISION_ENGINE_MODE:-}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
KILL_SOURCE="env"
if [ -z "$KILL_MODE" ]; then
  KILL_SOURCE="default"
  KILL_MODE="auto"
  if [ -f "$OC_ROOT/decision-engine-mode.conf" ]; then
    KILL_MODE="$(head -n1 "$OC_ROOT/decision-engine-mode.conf" 2>/dev/null | tr -d '\r' | xargs || true)"
    KILL_SOURCE="file"
  fi
fi
case "$KILL_MODE" in
  auto|shadow|legacy|off|model)
    _info "decision-engine mode: $KILL_MODE (source=$KILL_SOURCE)"
    ;;
  *)
    _fail "decision-engine mode store is CORRUPT: '$KILL_MODE' (source=$KILL_SOURCE, expected one of auto|shadow|legacy|off|model). Nothing was written; write one word to $OC_ROOT/decision-engine-mode.conf or unset \$OPENCLAW_DECISION_ENGINE_MODE."
    FAILURES=$((FAILURES + 1))
    ;;
esac
KILL_ACTIVE=0
if [ "$KILL_MODE" = "off" ] || [ "$KILL_MODE" = "legacy" ]; then
  KILL_ACTIVE=1
fi

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

# ─── openclaw CLI probe (B3 — PATH alone is not enough) ──────────────────────
# A PATH-only lookup means that on a box whose openclaw lives outside PATH BOTH
# CLI sources — `agents list --json` isDefault and the "(default)" text line —
# silently never run, leaving only systemAgent.agentId. That is exactly the
# off-PATH condition the order names.
# Candidate list follows the existing precedent in scripts/_rr_registry_lib.py
# PROBE_SH ($HOME/.openclaw/bin, /usr/local/bin, /data/.openclaw/bin) plus the
# Homebrew and /usr/bin locations. PATH wins when it resolves; otherwise the
# first executable absolute candidate. One binary is resolved ONCE here and
# exported, so G4 and G7 run the same CLI, and the full tried-list is exported
# so a failure message can name every source probed (B4).
_OC_CLI_CANDIDATES=("$HOME/.openclaw/bin/openclaw" "/usr/local/bin/openclaw" "/data/.openclaw/bin/openclaw" "/opt/homebrew/bin/openclaw" "/usr/bin/openclaw")
OC_CLI_BIN="$(command -v openclaw 2>/dev/null || true)"
if [ -z "$OC_CLI_BIN" ]; then
  for _oc_cand in "${_OC_CLI_CANDIDATES[@]}"; do
    if [ -x "$_oc_cand" ]; then OC_CLI_BIN="$_oc_cand"; break; fi
  done
fi
OC_CLI_TRIED="PATH"
for _oc_cand in "${_OC_CLI_CANDIDATES[@]}"; do OC_CLI_TRIED="$OC_CLI_TRIED, $_oc_cand"; done
export VERIFY_ROUTING_OC_CLI="$OC_CLI_BIN"
export VERIFY_ROUTING_OC_CLI_TRIED="$OC_CLI_TRIED"
if [ -n "$OC_CLI_BIN" ]; then
  _info "openclaw CLI probe: using $OC_CLI_BIN"
else
  _info "openclaw CLI probe: CLI probes skipped (openclaw not found at any probed path: $OC_CLI_TRIED)"
fi

# _ver_ge A B → 0 if version A >= version B (numeric YYYY.M.P compare).
_ver_ge() {
  printf '%s\n%s\n' "$2" "$1" | sort -t. -k1,1n -k2,2n -k3,3n -C
}

# ─── Resolve main agent workspace ────────────────────────────────────────────

WORKSPACE_DIR=""

WORKSPACE_DIR=$(OC_JSON="$OC_CONFIG" python3 - <<'PYEOF'
import json, os, sys

def _oc_agents(cfg):
    """Live agent dicts + an identity->id map, from agents.entries (canonical,
    keyed by agent id) with a fallback to legacy agents.list.

    Returns LIVE references into cfg so a caller may mutate an entry and write
    cfg back — building copies here would make the L2/L5 appliers mutate a
    throwaway, write the file back unchanged and still report success.

    The id is carried in a side map, NEVER written into the entry:
    agents.entries.<id> rejects an "id" key ("Unrecognized key: id") and the
    config would fail validation.
    """
    _ag = cfg.get("agents", {}) or {}
    _en = _ag.get("entries", {}) or {}
    if isinstance(_en, dict) and _en:
        lst = [v for v in _en.values() if isinstance(v, dict)]
        ids = {id(v): k for k, v in _en.items() if isinstance(v, dict)}
    else:
        lst = [a for a in (_ag.get("list", []) or []) if isinstance(a, dict)]
        ids = {id(a): a.get("id") for a in lst}
    return lst, ids


def _oc_id(ag, default="<unknown>"):
    """Agent id for a dict returned by _oc_agents()."""
    if not isinstance(ag, dict):
        return default
    return _OC_IDS.get(id(ag)) or ag.get("id") or default

try:
    cfg = json.load(open(os.environ['OC_JSON']))
    _agents, _OC_IDS = _oc_agents(cfg)
    for ag in _agents:
        if (_OC_IDS.get(id(ag)) or ag.get('id')) == 'main':
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
  # Count the block MARKER, not every mention: a Lean Core pointer line
  # ("**Full text:** ... §ROLE_DISCIPLINE_V1") names it too and read as a
  # duplicate. (grep -c prints 0 AND exits 1 on no match: `|| true`, never
  # `|| echo 0`, which made the count "0<newline>0".)
  RD_COUNT=$(grep -cF "<!-- ROLE_DISCIPLINE_V1 -->" "$AGENTS_FILE" 2>/dev/null || true)
  RD_COUNT=${RD_COUNT:-0}
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

# ─── G2: CEO_ROUTING_NO_LOOPHOLES_V4_3 in AGENTS.md ──────────────────────────
# Exact marker (v25.2.22 fix 3): the version-agnostic V[0-9]+ pattern accepted a
# box left on V1/V2/V4. Only the current V4_3 marker passes; a bare _V4 or older
# marker means the box missed the roll — run the stamper.
# KIL-001: G2 honours the kill switch (SUPPORTED, never REQUIRED). Kill off
# (mode off/legacy): operative V4.3 instructions must be ABSENT — presence NOT
# required, ABSENCE required. Kill on (auto/shadow): presence required.
if [ "$KILL_ACTIVE" = "1" ]; then
  _info "G2: kill switch on (mode=$KILL_MODE) — CEO_ROUTING_NO_LOOPHOLES_V4_3 must be ABSENT from $AGENTS_FILE"
  if [ -f "$AGENTS_FILE" ] && grep -qF "CEO_ROUTING_NO_LOOPHOLES_V4_3" "$AGENTS_FILE" 2>/dev/null; then
    _fail "G2: kill switch on (mode=$KILL_MODE) but CEO_ROUTING_NO_LOOPHOLES_V4_3 still PRESENT in $AGENTS_FILE — re-run apply-routing-fix.sh to strip operative instructions"
    FAILURES=$((FAILURES + 1))
  else
    _pass "G2: kill switch on (mode=$KILL_MODE) — no operative V4.3 routing block in $AGENTS_FILE"
  fi
else
  _info "G2: checking CEO_ROUTING_NO_LOOPHOLES_V4_3 in $AGENTS_FILE"
  if [ -f "$AGENTS_FILE" ] && grep -qF "CEO_ROUTING_NO_LOOPHOLES_V4_3" "$AGENTS_FILE" 2>/dev/null; then
    _pass "G2: CEO_ROUTING_NO_LOOPHOLES_V4_3 present in $AGENTS_FILE"
  else
    _fail "G2: CEO_ROUTING_NO_LOOPHOLES_V4_3 MISSING from $AGENTS_FILE (a bare V4/V3 marker is not accepted) — run apply-routing-fix.sh"
    FAILURES=$((FAILURES + 1))
  fi
fi

# ─── G3: PRIME DIRECTIVE in SOUL.md ──────────────────────────────────────────
# Exact marker (v25.2.22 fix 3): a box left on V4 or V3 must fail.
if [ "$KILL_ACTIVE" = "1" ]; then
  _info "G3: kill switch on (mode=$KILL_MODE) — CEO_ORCHESTRATOR_RULE_V4_3 must be ABSENT from $SOUL_FILE"
  if [ -f "$SOUL_FILE" ] && grep -qF "CEO_ORCHESTRATOR_RULE_V4_3" "$SOUL_FILE" 2>/dev/null; then
    _fail "G3: kill switch on (mode=$KILL_MODE) but CEO_ORCHESTRATOR_RULE_V4_3 still PRESENT in $SOUL_FILE — re-run apply-routing-fix.sh to strip operative instructions"
    FAILURES=$((FAILURES + 1))
  else
    _pass "G3: kill switch on (mode=$KILL_MODE) — no operative V4.3 directive in $SOUL_FILE"
  fi
else
  _info "G3: checking CEO_ORCHESTRATOR_RULE_V4_3 in $SOUL_FILE"
  if [ -f "$SOUL_FILE" ] && grep -qF "CEO_ORCHESTRATOR_RULE_V4_3" "$SOUL_FILE" 2>/dev/null; then
    _pass "G3: CEO_ORCHESTRATOR_RULE (PRIME DIRECTIVE) present in $SOUL_FILE"
  else
    _fail "G3: CEO_ORCHESTRATOR_RULE_V4_3 MISSING from $SOUL_FILE (a bare V4/V3 marker is not accepted) — run apply-routing-fix.sh"
    FAILURES=$((FAILURES + 1))
  fi
fi

# ─── G3b: plugin routing doctrine heading ───────────────────────────────────
# v25.2.22 fix 3: the installed plugin dist must be on the (V4.3) heading too,
# else it keeps prepending an old preamble even when SOUL.md/AGENTS.md are current.
PLUGIN_DIST="$OC_ROOT/extensions/ceo-routing-doctrine/dist/index.js"
_info "G3b: checking (V4.3) heading in $PLUGIN_DIST"
if [ -f "$PLUGIN_DIST" ] && grep -qF "(V4.3)" "$PLUGIN_DIST" 2>/dev/null; then
  _pass "G3b: (V4.3) heading present in $PLUGIN_DIST"
else
  _fail "G3b: (V4.3) heading MISSING from $PLUGIN_DIST — reinstall the plugin (install.sh / update-skills.sh)"
  FAILURES=$((FAILURES + 1))
fi

# ─── shared default-agent resolution — ONE chain for BOTH G4 and G7 ─────────
# B1: on the exact box class this order is about (agents.list EMPTY, the default
# agent living only as a file under <oc-root>/agents/, no default:true, no
# id=main) G4 resolved the default (PA_DEFAULT_OK) while G7, matching CONFIG
# ENTRIES only, returned NO_CEO_AGENT and FATAL'd. Both gates now exec this ONE
# body, so the chain cannot drift between them again.
#
# Resolution order — unchanged from baseline, identical in G4 and G7:
#   1 agents.defaults.systemAgent.agentId    (config entry OR on-disk agent dir)
#   2 default:true                           (legacy per-entry marker)
#   3 `openclaw agents list --json` isDefault (config entry OR on-disk agent dir)
#   4 id == "main"
#   5 router-id heuristic
#   6 the id `openclaw agents list` prints as "(default)"
#   7 a single-entry roster
#
# Every CLI call goes through the probed binary exported above (B3) and swallows
# binary absent / non-zero exit / malformed JSON / timeout, falling through to
# the next source instead of aborting the script. Exported to both gate bodies
# as VERIFY_ROUTING_RESOLVE_FILE; each body fails loud if it is missing.
# argv: [1] openclaw.json, [2] the OpenClaw root.
# A heredoc wrapped in $(cat ...) inside an assignment makes bash's
# INCREMENTAL reader desync: `bash -n` (whole-file parse) accepts it, but a
# real run misparses everything after it. Write the body to a temp file with
# a plain redirect instead; both gate bodies exec(compile(open(path)...)).
VERIFY_ROUTING_RESOLVE_FILE="$(mktemp "${TMPDIR:-/tmp}/onb-w1-PRF-002-resolver.XXXXXX.py")"
trap 'rm -f "$VERIFY_ROUTING_RESOLVE_FILE"' EXIT
cat > "$VERIFY_ROUTING_RESOLVE_FILE" <<'PYEOF'
import json, os, re, subprocess, sys
from pathlib import Path

def _oc_agents(cfg):
    """Live agent dicts + an identity->id map, from agents.entries (canonical,
    keyed by agent id) with a fallback to legacy agents.list.

    Returns LIVE references into cfg so a caller may mutate an entry and write
    cfg back — building copies here would make the L2/L5 appliers mutate a
    throwaway, write the file back unchanged and still report success.

    The id is carried in a side map, NEVER written into the entry:
    agents.entries.<id> rejects an "id" key ("Unrecognized key: id") and the
    config would fail validation.
    """
    _ag = cfg.get("agents", {}) or {}
    _en = _ag.get("entries", {}) or {}
    if isinstance(_en, dict) and _en:
        lst = [v for v in _en.values() if isinstance(v, dict)]
        ids = {id(v): k for k, v in _en.items() if isinstance(v, dict)}
    else:
        lst = [a for a in (_ag.get("list", []) or []) if isinstance(a, dict)]
        ids = {id(a): a.get("id") for a in lst}
    return lst, ids

_OC_IDS = {}

def _oc_id(ag, default="<unknown>"):
    """Agent id for a dict returned by _oc_agents()."""
    if not isinstance(ag, dict):
        return default
    return _OC_IDS.get(id(ag)) or ag.get("id") or default

def _oc_agent_dir(cid):
    """<oc-root>/agents/<cid>/ when it is a safe, existing directory, else None.
    OpenClaw 2026.10.x keeps agents as files there and openclaw.json may carry
    NO list/entries row for them, so an id from systemAgent.agentId or
    `agents list --json` is a real resolution even when it matches no config
    entry."""
    if not isinstance(cid, str) or not cid or "/" in cid or cid in (".", ".."):
        return None
    try:
        p = Path(sys.argv[2]) / "agents" / cid
        return p if p.is_dir() else None
    except Exception:
        return None

def _oc_agent_on_disk(cid):
    return _oc_agent_dir(cid) is not None

_AGENTS = []

def _source_file_backed(ag):
    """True when `ag` is a SYNTHESIZED {"id": ...} stub (the agent exists only
    as a file under <oc-root>/agents/ and has NO openclaw.json entry), false
    for a live config entry. Identity-based: config entries are the SAME
    objects _oc_agents() returns."""
    if not isinstance(ag, dict):
        return False
    return all(a is not ag for a in _AGENTS)

def _agent_manifests(cid):
    """[(file, dict)] for every flat *.json manifest directly under the agent's
    own directory — real, readable evidence for an agent that has NO
    openclaw.json entry. Unreadable/non-JSON files are skipped, never guessed."""
    d = _oc_agent_dir(cid)
    if d is None:
        return []
    out = []
    try:
        for f in sorted(d.glob("*.json")):
            try:
                data = json.loads(f.read_text())
            except Exception:
                continue
            if isinstance(data, dict):
                out.append((f.name, data))
    except Exception:
        pass
    return out

def _disk_field(cid, key, kind):
    """(value, "agents/<cid>/<file>") for the first `key` of type `kind` in the
    agent's own directory manifests, else (None, None). Callers must report the
    None/None case as INSUFFICIENT EVIDENCE — never as a pass."""
    for name, data in _agent_manifests(cid):
        v = data.get(key)
        if isinstance(v, kind):
            return v, "agents/%s/%s" % (cid, name)
    return None, None

# Router identity — keep IN SYNC with hooks/lib-ceo-tool-gate.sh CEO_ROUTER_IDS.
ROUTER_IDS = {
    "main", "ceo", "dept-ceo",
    "master-orchestrator", "dept-master-orchestrator",
    "dept-executive-office",
}
def _is_router(ag):
    if not isinstance(ag, dict):
        return False
    if ag.get("is_master") is True:
        return True
    if isinstance(ag.get("role"), str) and ag.get("role").strip().lower() == "router":
        return True
    return _oc_id(ag, "") in ROUTER_IDS

# Probed CLI (exported by the shell once for both gates) + the tried list, so a
# failure message can name every source probed (B4).
OC_CLI_BIN = os.environ.get("VERIFY_ROUTING_OC_CLI", "")
OC_CLI_TRIED = os.environ.get("VERIFY_ROUTING_OC_CLI_TRIED", "PATH")

SOURCES_TRIED = (
    "agents.defaults.systemAgent.agentId",
    "default:true",
    "openclaw agents list --json isDefault",
    "id=main",
    "router-id heuristic",
    "openclaw agents list '(default)' text",
    "single-entry roster",
)

def _cli(args, timeout=30):
    """Run the probed openclaw binary. NEVER raises and never aborts the
    script: binary absent, non-zero exit, malformed output and timeout all
    return None so the caller falls through to the next source (B3)."""
    if not OC_CLI_BIN:
        return None
    try:
        p = subprocess.run([OC_CLI_BIN] + list(args),
                           capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None
    if p.returncode != 0:
        return None
    return p.stdout or ""

def cli_probe_note():
    """B4: distinguish 'probes were skipped' from 'probed and found nothing'."""
    if OC_CLI_BIN:
        return "CLI probed and found no default (openclaw at %s)" % OC_CLI_BIN
    return "CLI probes skipped (openclaw not found at any probed path: %s)" % OC_CLI_TRIED

def no_resolution_note():
    return ("sources tried, in order: " + ", ".join(SOURCES_TRIED)
            + "; " + cli_probe_note())

def resolve_default_agent(cfg):
    """THE default-agent chain, shared by G4 and G7 (B1).

    Returns (agent_or_None, source_or_None, agents). The agent is a LIVE
    config entry when one matches, else {"id": ...} for an agent that exists
    only as a file under <oc-root>/agents/ (2026.10.x file-backed agent)."""
    global _OC_IDS, _AGENTS
    agents, _OC_IDS = _oc_agents(cfg)
    _AGENTS = agents

    def match(sid, allow_disk=True):
        """Config entry first; for the sources that accepted a file-backed agent
        on baseline (systemAgent, --json isDefault, "(default)" text) an id that
        exists only under <oc-root>/agents/ counts too. allow_disk=False keeps
        the id=main / router-id steps config-entry-only, exactly as before."""
        if not isinstance(sid, str) or not sid:
            return None
        ag = next((a for a in agents if _oc_id(a) == sid), None)
        if ag is None and allow_disk and _oc_agent_on_disk(sid):
            ag = {"id": sid}
        return ag

    # 1 (config-only, works with openclaw OFF PATH): agents.defaults.systemAgent
    # .agentId — the runtime's own choice, the same order
    # scripts/onboarding-state.sh obs_default_agent() uses. Accepted when it
    # names a config entry OR an on-disk agent dir, so a file-backed default
    # resolves instead of reading "no default agent".
    _sa = ((cfg.get("agents", {}) or {}).get("defaults", {}) or {}).get("systemAgent", {}) or {}
    _sa_id = _sa.get("agentId") if isinstance(_sa, dict) else None
    if isinstance(_sa_id, str) and _sa_id:
        ag = match(_sa_id)
        if ag is not None:
            return ag, "agents.defaults.systemAgent.agentId", agents

    # 2 default:true (legacy marker; 2026.10.x strips it)
    for ag in agents:
        if isinstance(ag, dict) and ag.get("default") is True:
            return ag, "default:true", agents

    # 3 (OpenClaw 2026.10.x): the per-entry `default` marker no longer exists —
    # the config schema rejects it and `openclaw doctor --fix` strips it. The
    # CLI still resolves and PRINTS the default, so ask the runtime. `--json` +
    # isDefault is the structured answer (survives CLI text reformatting and
    # sees file-backed agents) and outranks the id-guessing fallbacks below.
    out = _cli(["agents", "list", "--json"])
    if out:
        try:
            rows = json.loads(out)
            if isinstance(rows, dict):
                rows = rows.get("agents") or rows.get("list") or []
            for r in (rows if isinstance(rows, list) else []):
                if isinstance(r, dict) and r.get("isDefault") is True:
                    rid = r.get("id") or r.get("agentId") or r.get("name")
                    ag = match(rid)
                    if ag is not None:
                        return ag, "openclaw agents list --json isDefault", agents
        except Exception:
            pass

    # 4 fall back to id=="main" (legacy convention, config entries only)
    ag = match("main", allow_disk=False)
    if ag is not None:
        return ag, "id=main", agents

    # 5 a known router/CEO id. A box whose router is not literally named "main"
    # must not read as "no default agent".
    for ag in agents:
        if _oc_id(ag) in ROUTER_IDS:
            return ag, "router-id heuristic", agents

    # 6 the id `openclaw agents list` prints as "(default)" (text form, the
    # pre-`--json` path — kept for CLIs that only emit the table).
    out = _cli(["agents", "list"])
    if out:
        try:
            out = re.sub(r"\x1b\[[0-9;]*m", "", out)
            m = re.search(r"^\s*-\s*(\S+)\s*\(default\)", out, re.M)
            if m:
                ag = match(m.group(1))
                if ag is not None:
                    return ag, "openclaw agents list '(default)' text", agents
        except Exception:
            pass

    # 7 the only agent on the box
    if len(agents) == 1:
        return agents[0], "single-entry roster", agents
    return None, None, agents
PYEOF
export VERIFY_ROUTING_RESOLVE_FILE

# ─── G4: default agent has skills:[] ─────────────────────────────────────────
# The "default agent" is resolved by the shared chain above (ONE body, used by
# G4 AND G7 — see "shared default-agent resolution"): agents.defaults.
# systemAgent.agentId (config entry OR on-disk agent dir; config-only, works
# with openclaw off PATH), then the first entry in agents.list with
# default:true, then the isDefault flag from `agents list --json` (structured:
# survives CLI text reformatting and resolves file-backed agents), then
# id=="main" (pre-v10 convention), then a router id, then the id
# `openclaw agents list` prints as "(default)", then a single-entry
# agents.entries (2026.10.x has no default marker at all).
# Boxes whose primary agent is named "ceo", "dept-master-orchestrator", or any
# other router id are gated; a PERSONAL-ASSISTANT-default box (default agent is
# NOT a router) is a VALID topology — skills:[] is NOT required there and its
# absence must NOT FATAL (v13.2.2 PA-freeze guard).
# Skills are asserted only from evidence that exists: a live config entry (as
# always), or the FILE-BACKED agent's own <oc-root>/agents/<id>/*.json
# manifests. No skills evidence at all → UNKNOWN_SKILLS / INSUFFICIENT EVIDENCE
# (B2), never an unbacked "inherits installed skills".
_info "G4: detecting default agent and checking skills:[] in $OC_CONFIG"
G4_RESULT=$(python3 - "$OC_CONFIG" "$OC_ROOT" <<'PYEOF'

import json, os, sys

_SRC = os.environ.get("VERIFY_ROUTING_RESOLVE_FILE")
if not _SRC or not os.path.isfile(_SRC):
    print("ERROR:VERIFY_ROUTING_RESOLVE_FILE not exported (shared resolver missing)")
    sys.exit(0)
exec(compile(open(_SRC).read(), "<verify-routing shared default-agent resolver>", "exec"))

try:
    cfg = json.loads(Path(sys.argv[1]).read_text())
    default_agent, _source, agents_list = resolve_default_agent(cfg)

    if default_agent is None:
        print("NO_DEFAULT_AGENT:" + no_resolution_note())
        sys.exit(0)

    agent_id = _oc_id(default_agent)

    # PA-DEFAULT topology: the default agent is a hands-on personal assistant /
    # owner agent, NOT a router. skills:[] (the pptx router-deny) is intentionally
    # NOT applied there — a PA needs its skills. This is a PASSING configuration.
    if not _is_router(default_agent):
        print(f"PA_DEFAULT_OK:{agent_id}")
        sys.exit(0)

    # B2 (fail-closed skills evidence). A FILE-BACKED agent resolves to a bare
    # {"id": ...} because it exists only under <oc-root>/agents/ and has NO
    # openclaw.json entry — the old code then reported "inherits installed
    # skills" with ZERO evidence. Now the skills policy is read from real
    # evidence only:
    #   * config entry carries a list  -> EMPTY_SKILLS / HAS_SKILLS, unchanged
    #   * config entry has no skills   -> PASS, named as "no skills override"
    #   * file-backed, own-dir manifests carry a list -> EMPTY_SKILLS / HAS_SKILLS
    #   * file-backed, no skills evidence anywhere   -> UNKNOWN (INSUFFICIENT
    #     EVIDENCE): explicit, never an unbacked "inherits installed skills".
    if not _source_file_backed(default_agent):
        skills = default_agent.get("skills")
        if isinstance(skills, list) and len(skills) == 0:
            print(f"EMPTY_SKILLS:{agent_id}")
        elif skills is None:
            print(f"PASS:{agent_id}")
        else:
            print(f"HAS_SKILLS:{agent_id}:{json.dumps(skills)}")
    else:
        skills, _where = _disk_field(agent_id, "skills", list)
        if skills is not None:
            if len(skills) == 0:
                print(f"EMPTY_SKILLS:{agent_id}")
            else:
                print(f"HAS_SKILLS:{agent_id}:{json.dumps(skills)}@{_where}")
        else:
            print(f"UNKNOWN_SKILLS:{agent_id}")
except Exception as e:
    print(f"ERROR:{e}")

PYEOF
) || G4_RESULT="ERROR:python3_failed"

case "$G4_RESULT" in
  PASS:*)
    _G4_ID="${G4_RESULT#PASS:}"
    _pass "G4: default agent (id=${_G4_ID}) inherits installed skills for assigned fallback execution"
    ;;
  PA_DEFAULT_OK:*)
    _G4_ID="${G4_RESULT#PA_DEFAULT_OK:}"
    _pass "G4: default agent (id=${_G4_ID}) is a PERSONAL-ASSISTANT/non-router — pptx router-deny N/A; PA-default topology is valid (v13.2.2)"
    ;;
  EMPTY_SKILLS:*)
    _G4_ID="${G4_RESULT#EMPTY_SKILLS:}"
    _fail "G4: default agent (id=${_G4_ID}) still has legacy empty skills; run apply-routing-fix.sh"
    FAILURES=$((FAILURES + 1))
    ;;
  HAS_SKILLS:*)
    # strip leading "HAS_SKILLS:" then extract id (up to first :) and remainder
    _G4_REST="${G4_RESULT#HAS_SKILLS:}"
    _G4_ID="${_G4_REST%%:*}"
    _G4_SKILLS="${_G4_REST#*:}"
    _pass "G4: default agent (id=${_G4_ID}) retains owner-configured skills: ${_G4_SKILLS}"
    ;;
  UNKNOWN_SKILLS:*)
    # B2 fail-closed: a FILE-BACKED router default has no skills evidence
    # anywhere, so the gate reports INSUFFICIENT EVIDENCE and names the fields
    # it could not read. It must never claim "inherits installed skills".
    _G4_ID="${G4_RESULT#UNKNOWN_SKILLS:}"
    _fail "G4: default agent (id=${_G4_ID}) is FILE-BACKED (no openclaw.json agents entry) and carries NO skills evidence — INSUFFICIENT EVIDENCE, not 'inherits installed skills'. Checked: agents.entries.${_G4_ID}, agents.list[], ${OC_ROOT}/agents/${_G4_ID}/*.json. Run apply-routing-fix.sh"
    FAILURES=$((FAILURES + 1))
    ;;
  NO_DEFAULT_AGENT:*)
    # B4: name EVERY source tried and distinguish "probes skipped" from
    # "probed and found no default".
    _fail "G4: no default agent resolved — ${G4_RESULT#NO_DEFAULT_AGENT:}"
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

# ─── G7: CEO agent tools policy (production-tool deny RETIRED 2026-08-05) ─────
# RETIRED 2026-08-05 per Trevor: the CEO gate (production-tool deny on the
# orchestrator) was removed from box + repo because it denied `write` while
# memoryFlush demanded a memory write — creating loops and eating Telegram
# messages. The production-tool deny assertion is GONE from this gate; it is
# never a failure path again. Mirrors how G8 was retired below.
#
# TWO checks in G7 SURVIVE the retirement and are still enforced here, because
# neither has anything to do with the write-deny loop:
#   1. PER-AGENT SCHEMA CORRUPTION — sessions/agentToAgent on a per-agent tools
#      block are schema-invalid (AgentEntry.tools is additionalProperties:false)
#      and make `openclaw config validate` FAIL → reload skipped → cron engine
#      down. Hard-fail, and hard-fail even under an owner-consent carve-out.
#   2. GHL MCP DENY-BY-PROVIDER — a separate brake from the production deny;
#      byProvider["ghl-community-mcp"].deny==["*"] or the name-glob fallback.
#
# Deliberately NO LONGER checked: tools.deny ⊇ {write, edit, apply_patch,
# browser, canvas, image, process} (the retired gate), and `exec` in tools.allow
# (exec is now a normal member of CEO_TOOL_ALLOW — the routing path — so the old
# INTERIM_EXEC fail-warn would fire on every correctly-configured box).
#
# The CEO agent is resolved by the SAME shared chain as G4 (see "shared
# default-agent resolution" above): agents.defaults.systemAgent.agentId →
# default:true → the isDefault flag from `agents list --json` → id=="main" →
# known CEO ids → the id `openclaw agents list` prints as "(default)" → a
# single-agent box. A FILE-BACKED default (an id with no openclaw.json entry)
# now resolves here exactly as it does in G4 (B1), so G7 no longer answers
# NO_CEO_AGENT on a box G4 passes. The tools/GHL checks are never loosened: the
# file-backed agent's policy is read from its own agents/<id>/*.json manifests,
# and with no such evidence G7 reports INSUFFICIENT EVIDENCE and FAILS.
_info "G7: CEO production-tool deny RETIRED (Trevor 2026-08-05) — not enforced; still checking per-agent tools schema validity + GHL MCP deny-by-provider."
_pass "G7: CEO production-tool deny intentionally absent (retired fleet-wide per Trevor 2026-08-05) — no longer a requirement"

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

G7_RESULT=$(python3 - "$OC_CONFIG" "$OC_ROOT" <<'PYEOF'

import json, os, sys

_SRC = os.environ.get("VERIFY_ROUTING_RESOLVE_FILE")
if not _SRC or not os.path.isfile(_SRC):
    print("ERROR:VERIFY_ROUTING_RESOLVE_FILE not exported (shared resolver missing)")
    sys.exit(0)
exec(compile(open(_SRC).read(), "<verify-routing shared default-agent resolver>", "exec"))

try:
    cfg = json.loads(Path(sys.argv[1]).read_text())
    ceo, _source, agents = resolve_default_agent(cfg)

    if ceo is None:
        print("NO_CEO_AGENT:" + no_resolution_note())
        sys.exit(0)

    cid = _oc_id(ceo)

    # PA-DEFAULT topology -> no CEO gate expected on the default agent. But if a
    # SEPARATE router agent ALSO exists on the box (e.g. a dept-ceo alongside a PA
    # default), gate-check THAT router instead so a real router is never missed.
    if not _is_router(ceo):
        router = next((a for a in agents if _is_router(a)), None)
        if router is None:
            print(f"PA_DEFAULT_OK:{cid}"); sys.exit(0)
        ceo = router
        cid = _oc_id(ceo)

    # B1: a FILE-BACKED agent (id resolved only from <oc-root>/agents/<id>/, no
    # openclaw.json entry) has no config tools block. Read its OWN directory
    # manifests for a real tools policy; assert on that exactly as strictly.
    # With no tools evidence at all, say INSUFFICIENT EVIDENCE instead of
    # fabricating a NO_TOOLS defect — and never a silent pass.
    _from_disk = _source_file_backed(ceo)
    _tools_src = f"openclaw.json agent entry {cid}"
    if _from_disk:
        tools, _tools_src = _disk_field(cid, "tools", dict)
        if tools is None:
            print(f"NO_ENTRY_INSUFFICIENT_EVIDENCE:{cid}"); sys.exit(0)
    else:
        tools = ceo.get("tools")

    if not isinstance(tools, dict):
        print(f"NO_TOOLS:{cid}"); sys.exit(0)

    # v16.1.3: sessions/agentToAgent are ROOT `tools` keys; on a PER-AGENT tools
    # block they are schema-invalid (AgentEntry.tools is additionalProperties:
    # false) and fail `openclaw config validate` -> reload skipped -> cron engine
    # down on a router-default box. Flag a box still carrying them so the roll's
    # self-heal (apply-routing-fix.sh / apply-fleet-standards.sh) is known to be
    # required. Hard-fail even under an owner-consent carve-out (the corruption
    # is independent of the deny gate).
    _bad_peragent = [k for k in ("sessions", "agentToAgent") if k in tools]
    if _bad_peragent:
        print(f"PERAGENT_INVALID_KEYS:{cid}:{','.join(_bad_peragent)}"); sys.exit(0)

    # `deny` is still read, but ONLY to support the GHL MCP name-glob fallback
    # below. The production-tool deny assertion is retired (see header).
    deny = set(tools.get("deny") or [])

    # GHL MCP denied? accept byProvider form OR the name-glob fallback.
    bp = tools.get("byProvider") or {}
    ghl_bp = isinstance(bp, dict) and (
        bp.get("ghl-community-mcp", {}).get("deny") == ["*"]
        or bp.get("ghl-mcp", {}).get("deny") == ["*"]
    )
    ghl_glob = any(t in deny for t in ("ghl-community-mcp__*", "ghl-mcp__*"))
    if not (ghl_bp or ghl_glob):
        print(f"GHL_NOT_DENIED:{cid}"); sys.exit(0)

    # Evidence source is named only for a file-backed agent; a config-backed box
    # keeps the exact baseline PASS: token.
    print(f"PASS:{cid}@{_tools_src}" if _from_disk else f"PASS:{cid}")
except Exception as e:
    print(f"ERROR:{e}")

PYEOF
) || G7_RESULT="ERROR:python3_failed"

# If an owner-consent carve-out is active, a lifted gate is expected → INFO only.
if [ -n "$_CEO_CONSENT_FILE" ] && [ -f "$_CEO_CONSENT_FILE" ]; then
  case "$G7_RESULT" in
    PASS:*)          _pass "G7: CEO agent tools policy OK (id=${G7_RESULT#PASS:}) — per-agent schema clean, GHL MCP denied [consent sidecar also present]" ;;
    PA_DEFAULT_OK:*) _pass "G7: default agent (id=${G7_RESULT#PA_DEFAULT_OK:}) is a PERSONAL-ASSISTANT/non-router — CEO tool-gate N/A; PA-default topology is valid (v13.2.2)" ;;
    PERAGENT_INVALID_KEYS:*)
      _G7_PK="${G7_RESULT#PERAGENT_INVALID_KEYS:}"
      _fail "G7: CEO agent (id=${_G7_PK%%:*}) carries SCHEMA-INVALID per-agent tools keys [${_G7_PK#*:}] — these belong on ROOT tools (config.tools), not agents.list[].tools; config validate FAILS → reload skipped → cron engine down. Run apply-routing-fix.sh / apply-fleet-standards.sh (v16.1.3 self-heal repairs it). Fails even under consent (corruption is independent of the deny gate)."
      FAILURES=$((FAILURES + 1))
      ;;
    *)               _info "G7: owner-consent carve-out ACTIVE ($_CEO_CONSENT_FILE) — CEO tool-gate is intentionally lifted; QC state-gate covers this box. Not failing." ;;
  esac
else
  case "$G7_RESULT" in
    PASS:*)
      _pass "G7: CEO agent tools policy OK (id=${G7_RESULT#PASS:}) — per-agent tools schema clean, GHL MCP denied (production-tool deny retired 2026-08-05)"
      ;;
    PA_DEFAULT_OK:*)
      _pass "G7: default agent (id=${G7_RESULT#PA_DEFAULT_OK:}) is a PERSONAL-ASSISTANT/non-router — CEO tool-gate N/A; PA-default topology is valid (v13.2.2 PA-freeze guard)"
      ;;
    GHL_NOT_DENIED:*)
      _fail "G7: CEO tool-gate (id=${G7_RESULT#GHL_NOT_DENIED:}) does NOT deny GHL MCP — add byProvider['ghl-community-mcp'].deny=['*']; run apply-routing-fix.sh (Layer 5)"
      FAILURES=$((FAILURES + 1))
      ;;
    NO_TOOLS:*)
      _fail "G7: CEO agent (id=${G7_RESULT#NO_TOOLS:}) has NO tools policy at all — so GHL MCP is NOT denied either; run apply-routing-fix.sh (Layer 5)"
      FAILURES=$((FAILURES + 1))
      ;;
    PERAGENT_INVALID_KEYS:*)
      _G7_PK="${G7_RESULT#PERAGENT_INVALID_KEYS:}"
      _fail "G7: CEO agent (id=${_G7_PK%%:*}) carries SCHEMA-INVALID per-agent tools keys [${_G7_PK#*:}] — these belong on ROOT tools (config.tools), not agents.list[].tools; config validate FAILS → reload skipped → cron engine down. Run apply-routing-fix.sh / apply-fleet-standards.sh (v16.1.3 self-heal repairs it)."
      FAILURES=$((FAILURES + 1))
      ;;
    NO_ENTRY_INSUFFICIENT_EVIDENCE:*)
      # B1/B4: a file-backed default resolved (same chain as G4) but there is no
      # tools policy to assert on — INSUFFICIENT EVIDENCE, named sources, and
      # still FAILURES+=1 (a gate that cannot verify is not a gate that passed).
      _fail "G7: default agent (id=${G7_RESULT#NO_ENTRY_INSUFFICIENT_EVIDENCE:}) is FILE-BACKED — no openclaw.json agent entry and no tools policy under its own agents/<id>/*.json, so per-agent tools schema validity and the GHL MCP deny cannot be verified (INSUFFICIENT EVIDENCE). Run apply-routing-fix.sh"
      FAILURES=$((FAILURES + 1))
      ;;
    NO_CEO_AGENT:*)
      # B4: name EVERY source tried and distinguish "probes skipped" from
      # "probed and found no default".
      _fail "G7: no CEO/main agent found — no default agent resolved from any source. ${G7_RESULT#NO_CEO_AGENT:}"
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
    # tools.exec.mode is the NORMALIZED policy surface; each mode resolves to an
    # underlying (security, ask) pair — docs/tools/permission-modes.md:
    #   full -> security "full" / ask "off"   (run host exec without prompts)
    # A config carrying only mode="full" is therefore already ungated, but this
    # gate used to read the raw pair alone and FATAL'd on it. Accept either form.
    exec_full = exec_cfg.get("mode") == "full" or (
        exec_cfg.get("security") == "full" and exec_cfg.get("ask") == "off"
    )
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

# ─── G8: CEO PreToolUse intent-gate — INTENTIONALLY UNWIRED (2026-08-05) ──────
# Per Trevor's directive, the ceo-intent-gate PreToolUse hook has been removed
# from all boxes and the repo. It was creating loops (memoryFlush recursion via
# the hook's own Bash execution). This gate is now a permanent INFO/PASS — the
# unwired state is the CORRECT and INTENTIONAL state.
_info "G8: CEO PreToolUse intent-gate INTENTIONALLY UNWIRED (Trevor 2026-08-05) — this is the correct state."
_pass "G8: ceo-intent-gate hook NOT wired (intentionally unwired fleet-wide per Trevor 2026-08-05) — no longer a requirement"

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
