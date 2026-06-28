#!/usr/bin/env bash
# apply-fleet-standards.sh — Idempotent enforcer for the OpenClaw fleet standard:
#   • Sub-agents fully permitted (spawn + exec + read/write across all agents)
#   • tools.exec: security=full, ask=off (TOP-LEVEL only — valid on 2026.6.1+)
#   • GOAL-4 D4 (4B+4C): FULL fleetwide exec/approval UNGATE + a no-refusal tool
#     baseline at agents.defaults.tools.allow=["*"] so NO department/sub-agent ever
#     refuses a job (exec, file ops, web, MCP, Kie HTTP). The CEO/main per-agent
#     deny is RE-ASSERTED after the baseline (restrict-only precedence keeps the
#     CEO gated while every other agent inherits the wide-open baseline).
#   • Telegram media limit 50 MB (inbound + outbound)
#   • WhatsApp PERMANENTLY DISABLED (fleet-wide, non-negotiable — see FLEET-STANDARDS.md §3)
#
# NOTE (v11.3.1): agents.defaults.tools.exec is INVALID on OpenClaw 2026.6.1+
#   and causes "agents.defaults: Invalid input" / auto-revert by doctor --fix.
#   Only the top-level tools.exec is valid. Generation depts get per-agent
#   tools.allow set by build-workforce.py, not by this canonical block.
#
# GOAL-4 D4 COORDINATION (with Goal-5 CEO tool-gate):
#   The no-refusal baseline is agents.defaults.tools.ALLOW (valid on 2026.6.1+ —
#   unlike agents.defaults.tools.EXEC, which is the poison key). Under OpenClaw's
#   RESTRICT-ONLY tool-policy precedence (docs.openclaw.ai/tools/
#   multi-agent-sandbox-tools: "each level can further restrict tools, but cannot
#   grant back denied tools from earlier levels"), a per-agent deny on `main`
#   STILL restricts even though defaults allow ["*"]. So the wide-open baseline
#   frees departments + sub-agents WITHOUT re-opening the CEO. The CEO deny
#   re-assert below runs AFTER the baseline merge to make the order explicit and
#   self-documenting.
#
# Why a script and not `openclaw config set`:
#   Per-agent overrides in agents.list[] override global defaults. The schema
#   validator (2026.5.20+) rejects deep nested keys via CLI. The supported
#   pattern is direct JSON merge against openclaw.json, then validate. This
#   script ships the canonical block verified on a Mac mini client box (2026.6.1).
#
# Idempotent: re-running is a no-op if config already matches canonical block.
#
# Path detection:
#   - If /data/.openclaw/openclaw.json exists  → VPS container layout.
#   - Else                                     → $HOME/.openclaw/openclaw.json
#                                                (Mac mini layout).
#
# Verification (success criteria):
#   openclaw config validate must exit clean.
#
# Logs before/after state and reports idempotent status.

set -euo pipefail

# ─── Temp-file cleanup on EXIT ───────────────────────────────────────────────
_APPLY_TMPFILES=()
_cleanup_tmpfiles() {
  for _f in "${_APPLY_TMPFILES[@]+"${_APPLY_TMPFILES[@]}"}"; do
    [ -f "$_f" ] && rm -f "$_f"
  done
}
trap _cleanup_tmpfiles EXIT

# ─── Path detection ──────────────────────────────────────────────────────────
if [ -f /data/.openclaw/openclaw.json ]; then
  OC_ROOT="/data/.openclaw"
  OC_USER="node"
elif [ -f "$HOME/.openclaw/openclaw.json" ]; then
  OC_ROOT="$HOME/.openclaw"
  OC_USER="$(whoami)"
else
  echo "ERROR: cannot find openclaw.json in /data/.openclaw or $HOME/.openclaw" >&2
  exit 1
fi

OC_CONFIG="$OC_ROOT/openclaw.json"
TIMESTAMP=$(date +%Y%m%d%H%M%S)
OC_BACKUP="$OC_CONFIG.bak-fleet-$TIMESTAMP"

echo "[apply-fleet-standards] config: $OC_CONFIG"

# ─── 1. Backup the current config ────────────────────────────────────────────
cp "$OC_CONFIG" "$OC_BACKUP"
echo "[apply-fleet-standards] backed up to: $OC_BACKUP"

# ─── 1b. Detect the running gateway binary version (D1 — schema-aware baseline) ──
# DEFECT 1 (v13.1.3): OpenClaw 2026.6.8 REJECTS any agents.defaults.tools.* key at
# config-validate ("agents.defaults: Invalid input"). Writing the GOAL-4 no-refusal
# baseline as agents.defaults.tools.allow=["*"] therefore self-rolls-back (the
# validate-fail rollback at the tail of this script restores the backup), leaving
# the box UN-ungated; verify-routing.sh G7b then FATALs.
#
# Fix: on schemas that REJECT agents.defaults.tools.* (>= 2026.6.8), express the
# no-refusal baseline ONLY with keys proven to validate clean:
#   • root tools.exec.security=full + tools.exec.ask=off  (fleet-wide exec ungate)
#   • agents.defaults.subagents.allowAgents=["*"] + requireAgentId=false (spawn ungate)
# That functional ungate is the satisfied Goal-4 baseline on 2026.6.8. On schemas
# that ACCEPT agents.defaults.tools.* (< 2026.6.8, or unknown) we ALSO write the
# wildcard allow as before (legacy-permissive default keeps older boxes unchanged).
#
# OC_VERSION = parsed YYYY.M.P from `openclaw --version`, or "" when unknown.
# FLEET_OC_VERSION_OVERRIDE pins the version for deterministic tests (bypasses the
# live binary). Mirrors smoke-test-provider-capabilities.sh's detector.
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

# WRITE_DEFAULTS_TOOLS=1 → this schema ACCEPTS agents.defaults.tools.* (write the
# wildcard allow). =0 → this schema REJECTS it (>= 2026.6.8); rely on the
# functional ungate instead. Unknown version → default to 1 (legacy-permissive):
# older boxes keep their existing baseline, and the validate gate is the backstop.
WRITE_DEFAULTS_TOOLS=1
if [ -n "$OC_VERSION" ] && _ver_ge "$OC_VERSION" "$TOOLS_DEFAULTS_REJECTED_VERSION"; then
  WRITE_DEFAULTS_TOOLS=0
  echo "[apply-fleet-standards] gateway $OC_VERSION >= $TOOLS_DEFAULTS_REJECTED_VERSION — agents.defaults.tools.* is REJECTED; using functional-ungate baseline (root tools.exec full+off + subagents ungate), NOT agents.defaults.tools.allow"
elif [ -n "$OC_VERSION" ]; then
  echo "[apply-fleet-standards] gateway $OC_VERSION < $TOOLS_DEFAULTS_REJECTED_VERSION — writing agents.defaults.tools.allow=['*'] no-refusal baseline"
else
  echo "[apply-fleet-standards] gateway version unknown — defaulting to writing agents.defaults.tools.allow=['*'] (validate gate is the backstop if a newer schema rejects it)"
fi
export FLEET_WRITE_DEFAULTS_TOOLS="$WRITE_DEFAULTS_TOOLS"

# ─── 2. Deep-merge the canonical fleet block into openclaw.json ──────────────
python3 - "$OC_CONFIG" <<'PYEOF'
import json
import os
import sys
from pathlib import Path

cfg_path = Path(sys.argv[1])
cfg = json.loads(cfg_path.read_text())
before_json = json.dumps(cfg, sort_keys=True, indent=2)

# DEFECT 1 (v13.1.3): schema-version-aware no-refusal baseline.
# FLEET_WRITE_DEFAULTS_TOOLS=1 → this schema accepts agents.defaults.tools.* so we
#   write the wildcard allow (legacy / < 2026.6.8 / unknown-version default).
# FLEET_WRITE_DEFAULTS_TOOLS=0 → schema REJECTS agents.defaults.tools.* (>= 2026.6.8)
#   so we DO NOT write it; the functional ungate (root tools.exec full+off +
#   agents.defaults.subagents ungate) IS the satisfied Goal-4 no-refusal baseline.
WRITE_DEFAULTS_TOOLS = os.environ.get("FLEET_WRITE_DEFAULTS_TOOLS", "1") == "1"

# CANONICAL FLEET STANDARD BLOCK
# Verified against:
#   - docs.openclaw.ai/tools/subagents (allowAgents wildcard, per-agent override)
#   - docs.openclaw.ai/gateway/security (exec.security, exec.ask, sandbox)
#   - docs.openclaw.ai/tools/multi-agent-sandbox-tools (agent-specific policy)
#   - Live test on OpenClaw 2026.6.1 (Mac mini client box, v11.3.1 fix)
#
# v11.3.1 FIX: agents.defaults.tools.exec is REMOVED from this block.
#   On OpenClaw 2026.6.1 the schema validator rejects it with
#   "agents.defaults: Invalid input" and openclaw doctor --fix auto-reverts it.
#   The exec policy lives at TOP-LEVEL tools.exec only.
#   Generation departments get per-agent tools.allow via build-workforce.py.
#
# Key insight: per-agent settings override global defaults. So we must:
#   1. Set top-level tools.exec for the gateway-wide exec policy.
#   2. Set agents.defaults.subagents.allowAgents to ["*"] for full spawn perm.
#   3. Iterate all agents and set their explicit allowAgents to ["*"] OR
#      delete their per-agent allowAgents so they inherit the global default.

CANONICAL = {
    "tools": {
        "exec": {
            "security": "full",
            "ask": "off"
        }
    },
    "agents": {
        "defaults": {
            "subagents": {
                "allowAgents": ["*"],
                "requireAgentId": False
            }
            # GOAL-4 D4 (4B+4C) — NO-REFUSAL TOOL BASELINE.
            # agents.defaults.tools.allow=["*"] is the positive baseline that, on
            # schemas that ACCEPT it, guarantees EVERY agent — departments + their
            # sub-agents — can run exec / file ops / web / MCP / Kie HTTP without
            # ever refusing a job. It is APPENDED below (not inlined here) ONLY when
            # WRITE_DEFAULTS_TOOLS is True, because OpenClaw 2026.6.8 REJECTS any
            # agents.defaults.tools.* key with "agents.defaults: Invalid input"
            # (DEFECT 1). On 2026.6.8 the functional ungate — root tools.exec
            # full+off (above) + agents.defaults.subagents ungate (here) — IS the
            # satisfied Goal-4 no-refusal baseline.
            #   • When written, this is the VALID defaults-level key (allow), NOT the
            #     poison key (exec). agents.defaults.tools.EXEC never validates.
            #   • Under RESTRICT-ONLY precedence the per-agent CEO deny (main)
            #     re-asserted below STILL wins, so this wildcard does NOT re-open
            #     the CEO's denied production tools.
        }
    },
    "channels": {
        "telegram": {
            "mediaMaxMb": 50
        }
    },
    # WHATSAPP BAN (fleet-wide, permanent — see FLEET-STANDARDS.md §3).
    # The Hostinger wrapper auto-installs WhatsApp on every boot when
    # WHATSAPP_NUMBER is set in the Docker env, causing a QR-scan crash-loop.
    # Locking enabled=false here prevents the gateway from ever activating it
    # even if the env var slips back in.
    "plugins": {
        "entries": {
            "whatsapp": {
                "enabled": False
            }
        }
    }
}

def deep_merge(dst, src):
    """Recursively merge src into dst, returning dst."""
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst

# Apply the canonical block.
deep_merge(cfg, CANONICAL)

# DEFECT 1 (v13.1.3) — schema-version-aware no-refusal baseline.
_agents_defaults = cfg.setdefault("agents", {}).setdefault("defaults", {})
if WRITE_DEFAULTS_TOOLS:
    # Schema accepts agents.defaults.tools.* — write/refresh the wildcard allow.
    _adt = _agents_defaults.setdefault("tools", {})
    if not isinstance(_adt, dict):
        _adt = {}
        _agents_defaults["tools"] = _adt
    _adt["allow"] = ["*"]
    print("[apply-fleet-standards] GOAL-4 baseline: agents.defaults.tools.allow=['*'] written")
else:
    # Schema (>= 2026.6.8) REJECTS agents.defaults.tools.* — never write it, AND
    # strip any pre-existing agents.defaults.tools so a box previously rolled with
    # the poison key validates clean again (idempotent self-heal). The functional
    # ungate (root tools.exec full+off + agents.defaults.subagents ungate) is the
    # satisfied Goal-4 no-refusal baseline on this schema.
    if "tools" in _agents_defaults:
        del _agents_defaults["tools"]
        print("[apply-fleet-standards] GOAL-4 baseline: stripped rejected agents.defaults.tools (2026.6.8 schema) — functional ungate is the baseline")
    else:
        print("[apply-fleet-standards] GOAL-4 baseline: agents.defaults.tools NOT written (2026.6.8 schema) — functional ungate is the baseline")

# Fix per-agent subagents overrides: any agent with an explicit allowAgents
# that is NOT ["*"] should be set to ["*"]. This is the critical piece that
# was missing in earlier partial fixes.
if "agents" in cfg and "list" in cfg["agents"]:
    for agent in cfg["agents"]["list"]:
        if "subagents" in agent and "allowAgents" in agent["subagents"]:
            if agent["subagents"]["allowAgents"] != ["*"]:
                agent_name = agent.get("name", "unknown")
                print(f"[apply-fleet-standards] fixing agent '{agent_name}' allowAgents → ['*']")
                agent["subagents"]["allowAgents"] = ["*"]

# GOAL-5 Item 1 + GOAL-4 D4 COORDINATION GUARD — RE-ASSERT CEO tool-gate.
# Two fleet-wide opens precede this re-assert and BOTH must be prevented from
# re-opening the CEO's denied production tools:
#   (1) agents.defaults.subagents.allowAgents=["*"] — re-opens sub-agent spawning.
#   (2) agents.defaults.tools.allow=["*"]          — the GOAL-4 no-refusal baseline.
# Neither re-opens the CEO because OpenClaw tool policy is RESTRICT-ONLY: a
# per-agent deny on `main` (and the deny a spawned sub-agent inherits from its
# parent) cannot be granted back by a broader defaults allow. We re-assert the
# per-agent CEO deny HERE, AFTER the canonical/defaults merge above, so the
# ungate and the CEO gate never fight and the order is explicit. This is the
# SAME deny set applied by apply-routing-fix.sh Layer 5 and build-workforce.py.
# Idempotent: only adds missing entries.
# KEEP IN SYNC with build-workforce.py (CEO_TOOL_*) and apply-routing-fix.sh L5
# and hooks/lib-ceo-tool-gate.sh. test-ceo-tool-gate.sh asserts they match.
_CEO_TOOL_DENY = [
    "write", "edit", "apply_patch", "browser", "canvas", "image", "process",
    "ghl-community-mcp__*", "ghl-mcp__*",
]
_CEO_TOOL_ALLOW = [
    "read", "web_fetch", "web_search",
    "message", "telegram", "slack", "discord",
    "sessions_send", "sessions_list", "sessions_history",
    "exec",  # INTERIM — replace with mc-route__route_task once that MCP tool ships
]
_CEO_MCP_DENY = {
    "ghl-community-mcp": {"deny": ["*"]},
    "ghl-mcp": {"deny": ["*"]},
}

# Owner-consent carve-out guard: if an owner-consent grant is ACTIVE, the gate
# is intentionally lifted — re-asserting it here would silently revoke the
# owner's grant. Skip the re-gate while consent is present (the same single
# shared sidecar read by src/lib/consent.ts and hooks/lib-ceo-consent.sh).
import os as _os
def _ceo_consent_active():
    cands = []
    if _os.environ.get("CEO_CONSENT_FILE"):
        cands.append(_os.environ["CEO_CONSENT_FILE"])
    cands.append("/data/.openclaw/state/ceo-consent.json")
    cands.append(_os.path.join(_os.path.expanduser("~"), ".openclaw", "state", "ceo-consent.json"))
    for c in cands:
        try:
            with open(c) as fh:
                rec = json.load(fh)
            if isinstance(rec, dict) and rec.get("granted") is True:
                return True
        except Exception:
            continue
    return False

if _ceo_consent_active():
    print("[apply-fleet-standards] owner-consent carve-out ACTIVE — skipping CEO tool-gate re-assert (would revoke the owner's grant)")
elif "agents" in cfg and "list" in cfg["agents"]:
    # DEFECT 2 (v13.1.3) + v13.2.2 PA-FREEZE FIX: re-assert the gate on the box's
    # default agent (default:true, else id=="main") ONLY IF it is a ROUTER —
    # matching apply-routing-fix.sh L5 and verify-routing.sh G7 so the gate target
    # never drifts across the roll. v13.1.3 re-asserted on ANY default:true agent,
    # which froze a personal-assistant-default box. Router iff is_master /
    # role=="router" / id in ROUTER_IDS; a non-router default agent is left alone.
    ROUTER_IDS = {  # keep IN SYNC with hooks/lib-ceo-tool-gate.sh CEO_ROUTER_IDS
        "main", "ceo", "dept-ceo",
        "master-orchestrator", "dept-master-orchestrator",
        "dept-executive-office",
    }
    def _is_router(a):
        if not isinstance(a, dict):
            return False
        if a.get("is_master") is True:
            return True
        if isinstance(a.get("role"), str) and a.get("role").strip().lower() == "router":
            return True
        return a.get("id") in ROUTER_IDS

    _agents = cfg["agents"]["list"]
    _ceo_agent = next((a for a in _agents if isinstance(a, dict) and a.get("default") is True), None)
    if _ceo_agent is None:
        _ceo_agent = next((a for a in _agents if isinstance(a, dict) and a.get("id") == "main"), None)
    if _ceo_agent is not None and not _is_router(_ceo_agent):
        # PA-FREEZE GUARD: default agent is a personal assistant / owner agent —
        # the CEO production lock would freeze it. Do NOT re-assert here.
        print(f"[apply-fleet-standards] default agent (id={_ceo_agent.get('id','<unknown>')}) is a PERSONAL-ASSISTANT/non-router — SKIPPING CEO tool-gate re-assert (v13.2.2 PA-freeze guard)")
        _ceo_agent = None
    if _ceo_agent is not None:
        agent = _ceo_agent
        tools = agent.setdefault("tools", {})
        deny = tools.setdefault("deny", [])
        if not isinstance(deny, list):
            deny = []; tools["deny"] = deny
        for t in _CEO_TOOL_DENY:
            if t not in deny:
                deny.append(t)
        allow = tools.setdefault("allow", [])
        if not isinstance(allow, list):
            allow = []; tools["allow"] = allow
        for t in _CEO_TOOL_ALLOW:
            if t not in allow:
                allow.append(t)
        tools["allow"] = [t for t in allow if t not in deny]  # deny wins
        by_provider = tools.setdefault("byProvider", {})
        if not isinstance(by_provider, dict):
            by_provider = {}; tools["byProvider"] = by_provider
        for prov, rule in _CEO_MCP_DENY.items():
            by_provider[prov] = rule
        # Cross-agent routing: routing agent MUST see all sessions so it can
        # locate and hand off to any department agent. Default gateway
        # behaviour is "tree" (spawned-children only), which silently blocks
        # department handoffs.
        _sessions = tools.setdefault("sessions", {})
        if not isinstance(_sessions, dict):
            _sessions = {}
            tools["sessions"] = _sessions
        if _sessions.get("visibility") != "all":
            _sessions["visibility"] = "all"
        # agentToAgent: routing agent must be able to message peer agents
        # directly. Idempotent — preserves any existing allow list if already
        # customized (setdefault only seeds missing keys).
        _a2a = tools.setdefault("agentToAgent", {})
        if not isinstance(_a2a, dict):
            _a2a = {}
            tools["agentToAgent"] = _a2a
        _a2a.setdefault("enabled", True)
        _a2a.setdefault("allow", ["*"])
        print(f"[apply-fleet-standards] re-asserted CEO tool-gate on default agent (id={agent.get('id','<unknown>')}; production tools denied)")

after_json = json.dumps(cfg, sort_keys=True, indent=2)

if before_json == after_json:
    print("[apply-fleet-standards] config already canonical — no-op")
else:
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")
    print("[apply-fleet-standards] config merged → " + str(cfg_path))

# Print before/after for audit.
print("\n[apply-fleet-standards] BEFORE (canonical block only):")
canonical_before = {k: v for k, v in json.loads(before_json).items()
                    if k in CANONICAL}
print(json.dumps(canonical_before, indent=2))

print("\n[apply-fleet-standards] AFTER (canonical block only):")
canonical_after = {k: v for k, v in json.loads(after_json).items()
                   if k in CANONICAL}
print(json.dumps(canonical_after, indent=2))

PYEOF

# ─── 3. Chown back to the OpenClaw runtime user (VPS container only) ─────────
if [ "$OC_ROOT" = "/data/.openclaw" ]; then
  chown "$OC_USER:$OC_USER" "$OC_CONFIG" 2>/dev/null || true
fi

# ─── 3b. WhatsApp env-file ban (VPS Hostinger Docker only) ──────────────────
# The Hostinger wrapper auto-installs and enables WhatsApp on every boot when
# WHATSAPP_NUMBER is present in /docker/<project>/.env, regardless of openclaw.json.
# This step comments out the line so it can never trigger the auto-install path.
# Idempotent: a line already commented-out is a no-op.
# Non-blocking: if the .env file is not reachable from this context we warn only.
if [ "$OC_ROOT" = "/data/.openclaw" ]; then
  _DOCKER_ENV_CANDIDATES=()
  # Try to locate the Hostinger compose project env file from inside the container.
  # Common patterns: /docker/<project>/.env or /data/docker/<project>/.env
  for _candidate in /docker/*/.env /data/docker/*/.env; do
    [ -f "$_candidate" ] && _DOCKER_ENV_CANDIDATES+=("$_candidate")
  done

  if [ "${#_DOCKER_ENV_CANDIDATES[@]}" -eq 0 ]; then
    echo "[apply-fleet-standards] WhatsApp env-ban: no /docker/*/.env found from this context — skipping (safe; plugin already disabled in openclaw.json)"
  else
    for _envf in "${_DOCKER_ENV_CANDIDATES[@]}"; do
      if grep -qE '^[[:space:]]*WHATSAPP_NUMBER[[:space:]]*=' "$_envf" 2>/dev/null; then
        # Uncommented WHATSAPP_NUMBER line found — comment it out permanently.
        _envf_bak="${_envf}.bak-whatsapp-ban-$(date +%Y%m%d%H%M%S)"
        cp "$_envf" "$_envf_bak"
        # Use perl for in-place sed that works on both GNU and BSD
        perl -i -pe 's/^([[:space:]]*)(WHATSAPP_NUMBER[[:space:]]*=.*)$/$1# WHATSAPP_NUMBER PERMANENTLY DISABLED (fleet ban — openclaw-onboarding FLEET-STANDARDS.md §3)\n# $2/' "$_envf"
        echo "[apply-fleet-standards] WhatsApp env-ban: commented out WHATSAPP_NUMBER in $_envf (backup: $_envf_bak)"
      else
        echo "[apply-fleet-standards] WhatsApp env-ban: WHATSAPP_NUMBER already absent/commented in $_envf — no-op"
      fi
    done
  fi
fi

# ─── 3c. WhatsApp env-ban QC guard (hard-fail if still active) ───────────────
# After the above neutralization, assert that the plugin is truly disabled.
python3 - "$OC_CONFIG" <<'WAQCEOF'
import json, sys
cfg = json.loads(open(sys.argv[1]).read())
enabled = (cfg.get("plugins", {})
              .get("entries", {})
              .get("whatsapp", {})
              .get("enabled", False))
if enabled:
    print("ERROR: plugins.entries.whatsapp.enabled is still True after fleet-standards apply — this is a hard-fail.", file=sys.stderr)
    sys.exit(1)
else:
    print("[apply-fleet-standards] WhatsApp ban QC: plugins.entries.whatsapp.enabled = false — PASS")
WAQCEOF

# ─── 4. Validate + report ────────────────────────────────────────────────────
echo ""
echo "[apply-fleet-standards] running: openclaw config validate"
if ! openclaw config validate; then
  echo "ERROR: openclaw config validate failed — see output above" >&2
  echo "[apply-fleet-standards] rolling back to: $OC_BACKUP"
  cp "$OC_BACKUP" "$OC_CONFIG"
  exit 1
fi

echo ""
echo "[apply-fleet-standards] config standards applied"

# ─── 5a. Inject ROLE DISCIPLINE into the agent's active AGENTS.md (PR2) ────────
# This is the role-scoped governance block from CANONICAL-ORCHESTRATOR-RULE.md.
# It is injected at the TOP of AGENTS.md (before existing content) so every
# agent — CEO and specialists alike — sees the role mandate on first read.
# Idempotent: guarded by <!-- ROLE_DISCIPLINE_V1 --> marker.
#
# PRD 1.11: Workspace resolution delegates to resolve_injected_core_files()
# (shared-utils/) when available — that is the SINGLE canonical implementation.
# The inline 3-step fallback is kept for early-boot/install-time compatibility.

_resolve_workspace_via_shared_helper() {
  # Try the shared Python helper first (PRD 1.11 single-source-of-truth).
  local SCRIPT_DIR
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local SHARED_UTILS="$SCRIPT_DIR/../shared-utils"
  local HELPER="$SHARED_UTILS/resolve_injected_core_files.py"
  if [ -f "$HELPER" ]; then
    OC_JSON="${OC_CONFIG:-}" python3 -c "
import sys, os
sys.path.insert(0, '$SHARED_UTILS')
from resolve_injected_core_files import resolve_injected_core_files
r = resolve_injected_core_files('main')
print(r['workspace'])
" 2>/dev/null && return 0
  fi
  return 1
}

WORKSPACE_DIR=""
WORKSPACE_DIR=$(_resolve_workspace_via_shared_helper 2>/dev/null) || WORKSPACE_DIR=""

if [ -z "$WORKSPACE_DIR" ] && [ -f "$OC_CONFIG" ]; then
  WORKSPACE_DIR=$(OC_JSON="$OC_CONFIG" python3 -c "
import json, os
try:
    cfg = json.load(open(os.environ['OC_JSON']))
    for ag in cfg.get('agents', {}).get('list', []) or []:
        if isinstance(ag, dict) and ag.get('id') == 'main':
            ws = ag.get('workspace')
            if ws:
                print(os.path.expanduser(ws)); break
except Exception:
    pass
" 2>/dev/null) || WORKSPACE_DIR=""
fi
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
if [ ! -d "$WORKSPACE_DIR" ]; then
  WORKSPACE_DIR="$OC_ROOT/workspace"
fi
mkdir -p "$WORKSPACE_DIR"
AGENTS_FILE_EARLY="$WORKSPACE_DIR/AGENTS.md"
touch "$AGENTS_FILE_EARLY"

ROLE_DISC_MARKER="<!-- ROLE_DISCIPLINE_V1 -->"
if grep -qF "$ROLE_DISC_MARKER" "$AGENTS_FILE_EARLY"; then
  echo "[apply-fleet-standards] ROLE DISCIPLINE already present in $AGENTS_FILE_EARLY — no-op"
else
  echo "[apply-fleet-standards] injecting ROLE DISCIPLINE at top of $AGENTS_FILE_EARLY"
  ORIGINAL_CONTENT=$(cat "$AGENTS_FILE_EARLY")
  cat > "$AGENTS_FILE_EARLY" <<'RDEOF'
<!-- ROLE_DISCIPLINE_V1 -->
## ROLE DISCIPLINE (non-negotiable — every agent, every level)

No agent decides what it will or will not do.

- The **CEO / master-orchestrator** is a ROUTER: it routes every task to a department by posting
  to `/api/tasks/ingest` with `department_slug`; it does not execute work, pick specialists,
  or commandeer sub-agents to keep control. Before doing any task itself it must seek and
  receive explicit owner permission — routing is always allowed without permission.
- A **department specialist** EXECUTES the task assigned to it against its SOP — including
  generating graphics/video via KIE.ai / Fal.ai — and does not refuse, redefine, or bounce
  its assigned role.
- An agent that overrides its defined role gets flagged. Persistent non-compliance (>20 flags)
  = the agent is reset (identity + soul deleted and rebuilt fresh).

This rule is role-scoped so it reinforces the CEO routing mandate WITHOUT gagging executing
specialists. Both behaviors — the CEO routing and specialists executing — are equally required.

### POLICY-DENY MEANS ROUTE (block-and-redirect self-correction)

The CEO's production tools (write, edit, exec, browser, image generation, and every
`ghl-community-mcp__*` / MCP production tool) are GATED behind owner consent. If any tool
returns a **policy / permission deny** error, that is NOT a bug and NOT something to retry —
it is the system telling you to **ROUTE**: immediately POST `/api/tasks/ingest` with a
`department_slug`. Do NOT retry the denied tool, do NOT spawn a sub-agent to do the denied
work, and do NOT seek an un-gated alternate tool. The gate opens ONLY via an explicit
owner-consent grant. Until then: a deny = route.

### NO BOUNCE-BACK (department specialists)

A department specialist MAY NOT return a properly-routed task to the CEO citing CEO competence,
triviality, or "the CEO should do this." A handback is ONLY valid when it names a CONCRETE
MISSING INPUT — a specific data field, credential, asset, decision, or access that was required
and not provided (`missing_input: { kind, name, why_blocking }`). A handback without a named
missing input is auto-rejected (HTTP 422): the task stays with the SAME specialist and is
re-dispatched. The CEO never inherits work via a bounce.

---

RDEOF
  printf '%s' "$ORIGINAL_CONTENT" >> "$AGENTS_FILE_EARLY"
  echo "[apply-fleet-standards] ROLE DISCIPLINE injected at top of $AGENTS_FILE_EARLY"
fi

# ─── 4b. Inject CEO ROUTING — NO LOOPHOLES block into AGENTS.md ──────────────
# v11.3.2: closes the "trivial task / quick API call / spawn-a-sub-agent" loopholes
# that let the CEO self-execute even when the PRIME DIRECTIVE partially loaded.
# Injected after ROLE_DISCIPLINE (or at top when ROLE_DISCIPLINE already present).
# Idempotent: guarded by <!-- CEO_ROUTING_NO_LOOPHOLES_V1 --> marker.
CEO_ROUTING_MARKER="<!-- CEO_ROUTING_NO_LOOPHOLES_V1 -->"
if grep -qF "$CEO_ROUTING_MARKER" "$AGENTS_FILE_EARLY"; then
  echo "[apply-fleet-standards] CEO ROUTING NO LOOPHOLES already present in $AGENTS_FILE_EARLY — no-op"
else
  echo "[apply-fleet-standards] injecting CEO ROUTING NO LOOPHOLES into $AGENTS_FILE_EARLY"
  # Insert after the ROLE_DISCIPLINE block (after the first --- separator that
  # follows the ROLE_DISCIPLINE marker). Use awk to inject after first --- post-marker.
  TMPF=$(mktemp); _APPLY_TMPFILES+=("$TMPF")
  awk -v marker="$ROLE_DISC_MARKER" '
    BEGIN { injected=0; in_rd=0 }
    {
      print
      if (!injected && index($0, marker)) { in_rd=1 }
      if (in_rd && !injected && /^---[[:space:]]*$/) {
        print ""
        print "<!-- CEO_ROUTING_NO_LOOPHOLES_V1 -->"
        print "## ⛔ CEO ROUTING — NO LOOPHOLES (v11.3.2 — closes all self-execution escape hatches)"
        print ""
        print "The CEO / master-orchestrator'\''s ONLY permitted routing action is:"
        print ""
        print "  **POST \`/api/tasks/ingest\` with \`department_slug: \"<slug>\"\`**"
        print ""
        print "This places the task on the department'\''s Kanban board. The DEPARTMENT assigns the specialist"
        print "and the persona. The doing belongs to the department — never to the CEO."
        print ""
        print "### Closed loopholes (these are ALL violations, no exceptions):"
        print ""
        print "| Loophole | Status |"
        print "|----------|--------|"
        print "| \"This task is trivial / simple / quick — I'\''ll just do it myself\" | ❌ VIOLATION |"
        print "| \"I know how to make this API call, I'\''ll handle it directly\" | ❌ VIOLATION |"
        print "| \"I'\''ll spawn a sub-agent and have it execute the work for me\" | ❌ VIOLATION — spawning a sub-agent to do production work IS the same as self-executing |"
        print "| \"I'\''m telling the sub-agent to call KIE.ai / Fal.ai for me\" | ❌ VIOLATION — same as above |"
        print "| \"I don'\''t know which department, so I'\''ll do it myself\" | ❌ VIOLATION — route to \`department_slug: \"general-task\"\` |"
        print "| \"The owner seemed to want a quick answer\" | ❌ VIOLATION — route and let the department respond |"
        print ""
        print "### What the CEO MAY do (exhaustive list):"
        print "- Have conversations with the owner"
        print "- POST to \`/api/tasks/ingest\` to route tasks"
        print "- Send Telegram messages"
        print "- Read workspace files"
        print "- Restart the gateway (orchestrator-only authority, N7)"
        print "- Manage agent/department config"
        print ""
        print "### Sub-agent bypass clause"
        print "Spawning a sub-agent and instructing it to execute production work IS THE SAME VIOLATION as"
        print "self-executing. If a sub-agent is spawned, it MUST read its own role files and operate via"
        print "the task board — it is NOT a production tool for the orchestrator."
        print ""
        print "### Owner-permission exception"
        print "Before the CEO would EVER do a task itself, it must FIRST seek AND RECEIVE explicit permission"
        print "and consent from the owner. Seeking permission alone is not enough — explicit consent must be"
        print "received. Without that explicit consent, the CEO routes — always."
        print ""
        print "---"
        print ""
        injected=1
      }
    }
  ' "$AGENTS_FILE_EARLY" > "$TMPF"
  # If ROLE_DISCIPLINE marker wasn't found (older box), just prepend at top
  if ! grep -qF "$CEO_ROUTING_MARKER" "$TMPF"; then
    ORIG2=$(cat "$AGENTS_FILE_EARLY")
    {
      printf '<!-- CEO_ROUTING_NO_LOOPHOLES_V1 -->\n'
      printf '## ⛔ CEO ROUTING — NO LOOPHOLES (v11.3.2 — closes all self-execution escape hatches)\n\n'
      printf 'The CEO'\''s ONLY permitted routing action: POST /api/tasks/ingest with department_slug.\n'
      printf 'No trivial-task, quick-API-call, or spawn-sub-agent exceptions. See AGENTS.md for full rule.\n\n'
      printf '---\n\n'
      printf '%s' "$ORIG2"
    } > "$TMPF"
  fi
  mv "$TMPF" "$AGENTS_FILE_EARLY"
  echo "[apply-fleet-standards] CEO ROUTING NO LOOPHOLES injected into $AGENTS_FILE_EARLY"
fi

if [ "$OC_ROOT" = "/data/.openclaw" ]; then
  chown "$OC_USER:$OC_USER" "$AGENTS_FILE_EARLY" 2>/dev/null || true
fi

# ─── 4c. Inject CREDENTIAL_CHECK_V2 (N33 + N34) into AGENTS.md ──────────────
# Idempotent: guarded by <!-- CREDENTIAL_CHECK_V2 --> marker.
# Upgrade path: if a box carries V1, strip it and inject V2 in its place.
# This is idempotent: re-running on a V2 box is a no-op.
CRED_CHECK_V2_MARKER="<!-- CREDENTIAL_CHECK_V2 -->"
CRED_CHECK_V1_MARKER="<!-- CREDENTIAL_CHECK_V1 -->"

if grep -qF "$CRED_CHECK_V2_MARKER" "$AGENTS_FILE_EARLY"; then
  echo "[apply-fleet-standards] CREDENTIAL_CHECK_V2 already present in $AGENTS_FILE_EARLY — no-op"
else
  echo "[apply-fleet-standards] injecting CREDENTIAL_CHECK_V2 (N33+N34) into $AGENTS_FILE_EARLY"
  # Remove any V1 block if present (strip from V1 marker to the next top-level ---\n heading)
  # Note: the python3 script writes directly to sys.argv[1]; no separate temp file needed.
  python3 - "$AGENTS_FILE_EARLY" <<'CCPYEOF'
import sys, re

path = sys.argv[1]
content = open(path).read()

# Strip V1 block if present: from <!-- CREDENTIAL_CHECK_V1 --> to next top-level ---
v1_pattern = re.compile(
    r'<!-- CREDENTIAL_CHECK_V1 -->.*?(?=\n---\n(?:\n|##|\Z))',
    re.DOTALL
)
content = v1_pattern.sub('', content)

open(path, 'w').write(content)
CCPYEOF
  # Append V2 block at end (before any trailing learned-lessons section if present)
  cat >> "$AGENTS_FILE_EARLY" <<'CCEOF'

<!-- CREDENTIAL_CHECK_V2 -->
## 🔴 N33 — Credential Check Protocol (never falsely report a key missing)

> Idempotency marker: `CREDENTIAL_CHECK_V2`. `apply-fleet-standards.sh` injects this on
> existing boxes. Do NOT add it again if the marker is already present.
> Boxes carrying `CREDENTIAL_CHECK_V1` are automatically upgraded to V2 on next run.

A credential that exists in the live process env but is absent from a flat file is **PRESENT**.
An agent that reports "missing" without the evidence triad below has made a false claim.

### The Evidence Triad (required before "missing")

Before reporting any key as absent, you MUST have completed all three steps:

1. **Live process env** — checked via `docker exec <container> printenv` (VPS) or `ps eww <gw-pid>` (Mac).
2. **MCP server headers** — checked `openclaw.json mcp.servers.<svc>.headers` + `.env`.
3. **All .env stores** — checked every store listed in the "checked" output of `check-credential.sh`.

Only after all three return empty may you say a key is **GENUINELY-ABSENT**.

Use the canonical helper:
```
~/.openclaw/skills/shared-utils/check-credential.sh <KEY_NAME>
~/.openclaw/skills/shared-utils/check-credential.sh --provider <PROVIDER_NAME> --json
```

<!-- N34 -->
## 🔴 N34 — Provider Detection Protocol (a missing config block is NEVER proof a provider is absent)

"Does box X have provider Y" = **can the gateway resolve Y's API key at runtime** — NOT "is there a `models.providers.<Y>` block."

Run `check-credential.sh --provider <Y>` (live process env FIRST). Three verdicts:

| Verdict | Exit | Action |
|---|---|---|
| `PRESENT_WITH_BLOCK` | 0 | Key live + block references it — update block |
| `NEEDS_BLOCK` | 3 | Key live, no block — HAS the provider, CREATE the block |
| `GENUINELY-ABSENT` | 1 | Only after live-env tier + all stores empty — then skip |

**Hard violations:** emitting absent/no-provider from a config-block check alone; writing `had_X: false` for a check that never ran (use `NOT_ASSESSED`). Sonnet only — never Haiku for credential checks.

Block-name matching is on the **referenced apiKey**, not the block name (`openrouter-grok` with `apiKey: $OPENROUTER_API_KEY` IS the openrouter provider).

Root cause: 2026-06-13 Kimi-2.7 sweep falsely reported 5/5 boxes as no-OpenRouter from a `models.providers`-only check while `OPENROUTER_API_KEY` was live in the container env.

CCEOF
  echo "[apply-fleet-standards] CREDENTIAL_CHECK_V2 injected into $AGENTS_FILE_EARLY"
fi

if [ "$OC_ROOT" = "/data/.openclaw" ]; then
  chown "$OC_USER:$OC_USER" "$AGENTS_FILE_EARLY" 2>/dev/null || true
fi

# ─── 5. Append BIG PROJECT MODE standard to the agent's active AGENTS.md ──────
# Universal operating standard (see BIG-PROJECT-MODE.md at repo root). This is
# appended to the SAME active-workspace AGENTS.md that install.sh / update-skills
# target — not a per-role copy.
#
# IDEMPOTENCY (v2): the block is versioned via the heading
#   "## BIG PROJECT MODE (v2)"
# If the file contains ONLY the old v1 heading ("## BIG PROJECT MODE" without
# "(v2)"), the v1 block is replaced in-place with the v2 block.
# If v2 is already present, the run is a no-op.
# This ensures existing clients who received the v1 block get the updated
# Rule 0 (ECHO-BACK GATE) on the next apply-fleet-standards run.
#
# PRD 1.11: Workspace resolution delegates to resolve_injected_core_files()
# (shared-utils/) — single source of truth for the gateway-injected paths.
# The inline 3-step fallback is kept for early-boot/install-time compatibility.
# The shared helper already defined _resolve_workspace_via_shared_helper above.
#
# Priority (mirrors install.sh Step 10 exactly):
#   1. agents.list[main].workspace (per-agent override — wins if set)
#   2. agents.defaults.workspace via `openclaw config get`
#   3. $OC_ROOT/workspace (canonical OpenClaw default — Mac or VPS)
# Clawd is dead; ~/clawd is never a fallback.

WORKSPACE_DIR=""
WORKSPACE_DIR=$(_resolve_workspace_via_shared_helper 2>/dev/null) || WORKSPACE_DIR=""

if [ -z "$WORKSPACE_DIR" ]; then
  # Inline fallback (step 1)
  WORKSPACE_DIR=$(OC_JSON="$OC_CONFIG" python3 -c "
import json, os
try:
    cfg = json.load(open(os.environ['OC_JSON']))
    for ag in cfg.get('agents', {}).get('list', []) or []:
        if isinstance(ag, dict) and ag.get('id') == 'main':
            ws = ag.get('workspace')
            if ws:
                print(os.path.expanduser(ws)); break
except Exception:
    pass
" 2>/dev/null) || WORKSPACE_DIR=""
fi

# Fallback step 2: agents.defaults.workspace via CLI
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

# Fallback step 3: canonical default
WORKSPACE_DIR="${WORKSPACE_DIR:-$OC_ROOT/workspace}"
if [ ! -d "$WORKSPACE_DIR" ]; then
  WORKSPACE_DIR="$OC_ROOT/workspace"
fi

mkdir -p "$WORKSPACE_DIR"
AGENTS_FILE="$WORKSPACE_DIR/AGENTS.md"
touch "$AGENTS_FILE"

BPM_V2_HEADING="## BIG PROJECT MODE (v2)"
BPM_V1_HEADING="## BIG PROJECT MODE"

if grep -qF "$BPM_V2_HEADING" "$AGENTS_FILE"; then
  echo "[apply-fleet-standards] BIG PROJECT MODE (v2) already present in $AGENTS_FILE — no-op"
elif grep -qF "$BPM_V1_HEADING" "$AGENTS_FILE"; then
  # Upgrade v1 block to v2: strip everything from the v1 heading to end-of-file,
  # then append the v2 block. (v1 heading is always last — appended at end.)
  echo "[apply-fleet-standards] upgrading BIG PROJECT MODE v1 → v2 in $AGENTS_FILE"
  # Find line number of v1 heading and truncate file there (keep content before it).
  V1_LINE=$(grep -n "^## BIG PROJECT MODE$" "$AGENTS_FILE" | tail -1 | cut -d: -f1)
  if [ -n "$V1_LINE" ]; then
    # Keep lines BEFORE the v1 heading (trim the blank line before it too).
    # Guard: head -n 0 or head -n -1 (when V1_LINE <= 2) would wipe the file
    # under set -e. Only run the head/mv when there are lines to keep.
    _KEEP_LINES=$(( V1_LINE - 2 ))
    if [ "$_KEEP_LINES" -gt 0 ]; then
      head -n "$_KEEP_LINES" "$AGENTS_FILE" > "${AGENTS_FILE}.v2tmp"
      mv "${AGENTS_FILE}.v2tmp" "$AGENTS_FILE"
    else
      # v1 heading is at line 1 or 2 — nothing to keep before it; truncate to empty.
      : > "$AGENTS_FILE"
    fi
  fi
  cat >> "$AGENTS_FILE" <<'BPMEOF'

## BIG PROJECT MODE (v2)

**Trigger:** the owner says "big project mode" or hands you a large, multi-part
build/document with many deliverables. On per-token caching models (DeepSeek
direct ~1/120th on cache hits; Anthropic; OpenAI) this cuts input cost 80-95%;
on flat-rate routes (Ollama Cloud) it is still faster with fewer timeouts and
cleaner QC. It is never wrong to use it.

0. **ECHO-BACK GATE (always first).** Before spawning ANYTHING, reply to the
   owner with: every rule restated in your own words (one line each) + the full
   work-slice list + the EXACT model strings you will use for writers and QC.
   Wait for GO. If you think a different model/route/approach would be better —
   you don't decide that. Ask.
1. **Orchestrator pastes; owners send files.** The owner sends the project
   document as a file. Read it ONCE and embed the FULL TEXT, word-for-word, at
   the TOP of every worker's birth instructions. Never tell workers to "read the
   file" (that is one full-price read PER agent instead of per fleet).
2. **Identical bytes first, unique assignment last.** Every spawn = [shared
   document, byte-identical] + [that worker's assignment at the very bottom].
   Never paraphrase the shared block; never put the assignment first. One changed
   character at the front re-prices everything behind it.
3. **Warm-up then fleet.** Spawn ONE worker, let it finish (warms the cache),
   then launch the rest in batches.
4. **Workers live short.** End every assignment with: "everything you need is
   above — do not read other files; write your deliverable, save it, return a
   one-line status." Foraging workers cost 20-50x.
5. **Skinny orchestrator.** Track progress in a LEDGER FILE on disk;
   deliverables go to disk; only one-line statuses flow through the orchestrator
   conversation. Nothing bulky ever lives in the transcript.
6. **Independent QC, real scores.** QC runs on a DIFFERENT model than the
   writers, scores 0-10 against a rubric, gates >= 8.5, defect-loops on fails
   (max 3); numeric scores recorded — never free-text "PASS" stamps.
7. **No worker dies silently.** Ledger + watchdog; restart once -> fresh worker
   -> flag. The completion gate counts delivered files, not hopes.
8. **Tokens only** in any template/master content — never real owner/client data
   the agent happens to know.

**Verify caching worked:** on DeepSeek direct the usage fields
`prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` — after the warm-up
worker, hits should cover the shared document.

Full reference: `BIG-PROJECT-MODE.md` in the onboarding repo.
BPMEOF
  echo "[apply-fleet-standards] BIG PROJECT MODE (v2) written to $AGENTS_FILE"
else
  cat >> "$AGENTS_FILE" <<'BPMEOF'

## BIG PROJECT MODE (v2)

**Trigger:** the owner says "big project mode" or hands you a large, multi-part
build/document with many deliverables. On per-token caching models (DeepSeek
direct ~1/120th on cache hits; Anthropic; OpenAI) this cuts input cost 80-95%;
on flat-rate routes (Ollama Cloud) it is still faster with fewer timeouts and
cleaner QC. It is never wrong to use it.

0. **ECHO-BACK GATE (always first).** Before spawning ANYTHING, reply to the
   owner with: every rule restated in your own words (one line each) + the full
   work-slice list + the EXACT model strings you will use for writers and QC.
   Wait for GO. If you think a different model/route/approach would be better —
   you don't decide that. Ask.
1. **Orchestrator pastes; owners send files.** The owner sends the project
   document as a file. Read it ONCE and embed the FULL TEXT, word-for-word, at
   the TOP of every worker's birth instructions. Never tell workers to "read the
   file" (that is one full-price read PER agent instead of per fleet).
2. **Identical bytes first, unique assignment last.** Every spawn = [shared
   document, byte-identical] + [that worker's assignment at the very bottom].
   Never paraphrase the shared block; never put the assignment first. One changed
   character at the front re-prices everything behind it.
3. **Warm-up then fleet.** Spawn ONE worker, let it finish (warms the cache),
   then launch the rest in batches.
4. **Workers live short.** End every assignment with: "everything you need is
   above — do not read other files; write your deliverable, save it, return a
   one-line status." Foraging workers cost 20-50x.
5. **Skinny orchestrator.** Track progress in a LEDGER FILE on disk;
   deliverables go to disk; only one-line statuses flow through the orchestrator
   conversation. Nothing bulky ever lives in the transcript.
6. **Independent QC, real scores.** QC runs on a DIFFERENT model than the
   writers, scores 0-10 against a rubric, gates >= 8.5, defect-loops on fails
   (max 3); numeric scores recorded — never free-text "PASS" stamps.
7. **No worker dies silently.** Ledger + watchdog; restart once -> fresh worker
   -> flag. The completion gate counts delivered files, not hopes.
8. **Tokens only** in any template/master content — never real owner/client data
   the agent happens to know.

**Verify caching worked:** on DeepSeek direct the usage fields
`prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` — after the warm-up
worker, hits should cover the shared document.

Full reference: `BIG-PROJECT-MODE.md` in the onboarding repo.
BPMEOF
  echo "[apply-fleet-standards] BIG PROJECT MODE (v2) appended to $AGENTS_FILE"
fi

# Chown AGENTS.md back to the runtime user on VPS container layout.
if [ "$OC_ROOT" = "/data/.openclaw" ]; then
  chown "$OC_USER:$OC_USER" "$AGENTS_FILE" 2>/dev/null || true
fi

# ─── 6. Inject PRIME DIRECTIVE into workspace/SOUL.md (v11.3.2 G5-FIX) ───────
# The gateway injects bootstrap files from the main agent's workspace path
# (agents.list[main].workspace → agents.defaults.workspace → ~/.openclaw/workspace).
# build-workforce.py was writing the PRIME DIRECTIVE to DEPARTMENTS_DIR/ceo/SOUL.md
# (the dept-ceo sub-agent workspace) — NOT the file the gateway actually reads for
# the main orchestrator. This step injects the directive into workspace/SOUL.md and
# scrubs the contradictory "personal assistant / handle it yourself" intro.
# Idempotent: guarded by <!-- CEO_ORCHESTRATOR_RULE_V2 --> marker.
CEO_ORCH_V2_MARKER="<!-- CEO_ORCHESTRATOR_RULE_V2 -->"
WS_SOUL_FILE="$WORKSPACE_DIR/SOUL.md"
touch "$WS_SOUL_FILE"

if grep -qF "$CEO_ORCH_V2_MARKER" "$WS_SOUL_FILE" 2>/dev/null; then
  echo "[apply-fleet-standards] PRIME DIRECTIVE already present in $WS_SOUL_FILE — no-op"
else
  echo "[apply-fleet-standards] injecting PRIME DIRECTIVE into $WS_SOUL_FILE"
  # Read existing, strip V1 marker if present, strip personal-assistant intro
  SOUL_EXISTING=$(cat "$WS_SOUL_FILE" 2>/dev/null || true)
  # Strip V1 block if present
  if echo "$SOUL_EXISTING" | grep -qF "<!-- CEO_ORCHESTRATOR_RULE_V1 -->"; then
    SOUL_EXISTING=$(echo "$SOUL_EXISTING" | python3 -c "
import sys, re
content = sys.stdin.read()
content = re.sub(r'<!-- CEO_ORCHESTRATOR_RULE_V1 -->.*?---\s*\n', '', content, count=1, flags=re.DOTALL)
print(content, end='')
")
  fi
  # Strip "personal assistant / handle it yourself" intro (# SOUL.md ... first ---)
  SOUL_EXISTING=$(echo "$SOUL_EXISTING" | python3 -c "
import sys, re
content = sys.stdin.read()
content = re.sub(r'^# SOUL\.md.*?^---\s*\n', '', content, count=1, flags=re.DOTALL | re.MULTILINE)
print(content.lstrip(), end='')
")
  # Write PRIME DIRECTIVE + remaining content
  {
    cat <<'PDEOF'
<!-- CEO_ORCHESTRATOR_RULE_V2 -->
## ⛔ PRIME DIRECTIVE — I AM A TASK ROUTER. I ROUTE. THIS IS NOT OPTIONAL.

1. I am the master orchestrator (CEO). My one job is to ROUTE tasks. When any task or request
   reaches me, I ROUTE it to the correct DEPARTMENT — every time. I have NO permission to decide
   not to route, to refuse a task, or to choose what I will or will not do.
2. I do NOT do the work myself, and I do NOT pick the specialist or spawn/keep control of a
   sub-agent to do it. I route to the DEPARTMENT. The DEPARTMENT decides which specialist
   sub-agent and which persona are needed; the task gets a persona assigned; the task is placed
   on the Kanban board. The doing belongs to the department and its specialist — never to me.
3. Before I would EVER do a task myself, I must FIRST seek and RECEIVE explicit permission and
   consent from the owner (the human in control). Without that explicit consent, I route — always.
   (Routing is my default and is always allowed; I never need permission to route.)
4. If I cannot determine the right department, I route to the General Tasks department. I never
   self-execute because I'm unsure, and I never hold a task to "stay in control" of it.
5. What I MAY do: have conversations, manage agents, manage departments, and route tasks.
   What I may NEVER do: refuse to route, decide who executes, execute the work myself, or
   commandeer a sub-agent to keep control.

### Routing = Creating a DEPARTMENT TASK (not spawning a sub-agent directly)

The correct routing action is POST to `/api/tasks/ingest` with `department_slug: "<slug>"`.
This places the task on the department's Kanban — the DEPARTMENT assigns the specialist.

Spawning a sub-agent and instructing it to execute production work IS THE SAME VIOLATION as
executing the work yourself. If a sub-agent is spawned, it MUST read its own role files and
operate via the task board — it is not a production tool for the orchestrator.

### Binding Rules

- **R1** Never generate images, videos, audio, or written deliverables
- **R2** Never write to files, databases, or external APIs as a production action
- **R3** Never use any skill that produces a deliverable (`skills: []` enforced in config)
- **R4** Every actionable request → `POST /api/tasks/ingest` with `department_slug`
- **R5** If CC unreachable → escalate via Telegram, do NOT execute directly
- **R6** If route is unclear → use `department_slug: "general-task"`, never self-execute
- **R7** Permitted actions only: Telegram messaging, task-ingest POST, read workspace files, gateway restart

---

PDEOF
    printf '%s' "$SOUL_EXISTING"
  } > "$WS_SOUL_FILE"
  echo "[apply-fleet-standards] PRIME DIRECTIVE written to $WS_SOUL_FILE"
fi

if [ "$OC_ROOT" = "/data/.openclaw" ]; then
  chown "$OC_USER:$OC_USER" "$WS_SOUL_FILE" 2>/dev/null || true
fi

# ─── 7. Inject PLATFORM_FACTS_V1 into workspace/AGENTS.md ───────────────────
# W7.2: Per-box AGENTS.md platform stamp.  Records the box's platform,
# config root, env/secrets file paths, and where new keys/tokens go —
# so every agent on this box always knows where things live.
# Idempotent: guarded by <!-- PLATFORM_FACTS_V1 --> marker.
# Paths computed from the existing OC_ROOT detector — never hardcoded.
PLATFORM_FACTS_MARKER="<!-- PLATFORM_FACTS_V1 -->"

if grep -qF "$PLATFORM_FACTS_MARKER" "$AGENTS_FILE"; then
  echo "[apply-fleet-standards] PLATFORM_FACTS_V1 already present in $AGENTS_FILE — no-op"
else
  echo "[apply-fleet-standards] computing platform facts..."

  # ── Detect VPS host variant (Hostinger / Contabo / unknown) ──────────────
  # OPENCLAW_VPS_HOST can be written at install time (W7.1) to pin the value.
  # Fall back to cheap env probing when the var is absent.
  _PF_VPS_HOST="${OPENCLAW_VPS_HOST:-}"
  if [ -z "$_PF_VPS_HOST" ] && [ "$OC_ROOT" = "/data/.openclaw" ]; then
    # Hostinger VPS: Docker Manager sets HPANEL_VPS or container hostname uses
    # "openclaw-<id>" pattern; Contabo uses different host patterns.
    if [ -n "${HPANEL_VPS:-}" ] || hostname 2>/dev/null | grep -qE '^openclaw-[a-z0-9]+$'; then
      _PF_VPS_HOST="hostinger"
    elif [ -f "/etc/contabo-release" ] || [ -n "${CONTABO_INSTANCE_ID:-}" ]; then
      _PF_VPS_HOST="contabo"
    else
      _PF_VPS_HOST="unknown"
    fi
  fi

  # ── Detect compose project name (best-effort; used in Docker env path hint) ─
  _PF_COMPOSE_PROJECT="${COMPOSE_PROJECT_NAME:-}"
  if [ -z "$_PF_COMPOSE_PROJECT" ] && [ "$OC_ROOT" = "/data/.openclaw" ]; then
    # The host /docker/<project>/.env pattern is canonical on Hostinger.
    # Try to read from /docker/ if the mount is visible from inside the container.
    _found_compose=""
    for _dc in /docker/*/.env; do
      if [ -f "$_dc" ]; then
        _found_compose="$(dirname "$_dc")"
        break
      fi
    done
    if [ -n "$_found_compose" ]; then
      _PF_COMPOSE_PROJECT="$(basename "$_found_compose")"
    else
      _PF_COMPOSE_PROJECT="openclaw-<project-id>"
    fi
  fi

  # ── Build platform-specific facts ────────────────────────────────────────
  if [ "$OC_ROOT" = "/data/.openclaw" ]; then
    # VPS Docker (Hostinger or Contabo)
    _PF_PLATFORM="vps-${_PF_VPS_HOST}"
    _PF_CONFIG_ROOT="/data/.openclaw"
    _PF_WORKSPACE="/data/.openclaw/workspace"
    _PF_SKILLS="/data/.openclaw/skills"
    _PF_SECRETS_STORE="/data/.openclaw/secrets/.env"
    _PF_DOCKER_COMPOSE_ENV="/docker/${_PF_COMPOSE_PROJECT}/.env"
    _PF_ENV_SECTION="### Env / secrets stores on this box

**1. Live container env (check THIS first — most current):**
\`\`\`
docker exec <container-name> printenv
\`\`\`
A key set only in the compose env_file is visible here at runtime.

**2. Host compose env file (write target — sets container env on recreate):**
\`${_PF_DOCKER_COMPOSE_ENV}\`
This file is on the HOST, outside the container. To add/change a key:
1. Edit \`${_PF_DOCKER_COMPOSE_ENV}\` on the host.
2. Run \`docker compose up -d --force-recreate\` to apply.
(Never use \`docker compose restart\` — it skips env_file re-read.)

**3. Persistent secrets store inside the container:**
\`${_PF_SECRETS_STORE}\`

### Where new passwords / tokens / keys go

Add the new key to **both**:
- \`${_PF_DOCKER_COMPOSE_ENV}\` (host compose env file — source of truth)
- \`${_PF_SECRETS_STORE}\` (persistent inside container)
Then run \`docker compose up -d --force-recreate\` to apply."
  else
    # Mac (new install: ~/.openclaw; legacy: ~/clawd)
    if [ -d "$HOME/.openclaw" ]; then
      _PF_PLATFORM="mac"
      _PF_CONFIG_ROOT="$HOME/.openclaw"
      _PF_WORKSPACE="$HOME/.openclaw/workspace"
      _PF_SKILLS="$HOME/.openclaw/skills"
      _PF_SECRETS_STORE="$HOME/.openclaw/secrets/.env"
    else
      _PF_PLATFORM="mac-legacy"
      _PF_CONFIG_ROOT="$HOME/clawd"
      _PF_WORKSPACE="$HOME/clawd"
      _PF_SKILLS="$HOME/clawd/skills"
      _PF_SECRETS_STORE="$HOME/clawd/secrets/.env"
    fi
    _PF_ENV_SECTION="### Env / secrets store on this box

**Primary secrets store:**
\`${_PF_SECRETS_STORE}\`

Add new keys here, then restart the gateway:
\`\`\`
launchctl kickstart -k gui/\$(id -u)/ai.openclaw.gateway
# or: openclaw restart
\`\`\`"
  fi

  # ── Write the block ───────────────────────────────────────────────────────
  cat >> "$AGENTS_FILE" <<PFEOF

${PLATFORM_FACTS_MARKER}
## Platform Facts (stamped by apply-fleet-standards.sh — do NOT edit manually)

> This block is written on every install/update and refreshed idempotently.
> Marker: \`PLATFORM_FACTS_V1\`. Manual edits are overwritten on next run.

| Fact | Value |
|------|-------|
| Platform | ${_PF_PLATFORM} |
| Config root | ${_PF_CONFIG_ROOT} |
| Workspace | ${_PF_WORKSPACE} |
| Skills | ${_PF_SKILLS} |
| Secrets store | ${_PF_SECRETS_STORE} |

${_PF_ENV_SECTION}

### Platform-conditional path reference

All scripts in this box must resolve paths from the detector — never hardcode \`/data/.openclaw\` or \`~/.openclaw\`:
- Config root: \`${_PF_CONFIG_ROOT}\`
- Workspace: \`${_PF_WORKSPACE}\`
- Skills: \`${_PF_SKILLS}\`
- Secrets: \`${_PF_SECRETS_STORE}\`

PFEOF
  echo "[apply-fleet-standards] PLATFORM_FACTS_V1 injected into $AGENTS_FILE"
fi

if [ "$OC_ROOT" = "/data/.openclaw" ]; then
  chown "$OC_USER:$OC_USER" "$AGENTS_FILE" 2>/dev/null || true
fi

echo ""
echo "[apply-fleet-standards] DONE"
echo "[apply-fleet-standards] Backup: $OC_BACKUP"
echo "[apply-fleet-standards] Current: $OC_CONFIG"
echo "[apply-fleet-standards] AGENTS.md: $AGENTS_FILE"
echo "[apply-fleet-standards] workspace/SOUL.md: $WS_SOUL_FILE"
