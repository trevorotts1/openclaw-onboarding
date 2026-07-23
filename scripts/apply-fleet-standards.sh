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
#   • tools.toolSearch.mode="directory" — ON-DEMAND MCP tool loading (fleet-wide
#     "schema-every-turn" token-burn fix; compacts GHL's hundreds of tools + all
#     MCP/plugin tools behind a search-on-demand catalog — see FLEET-STANDARDS.md §8)
#   • RESERVED SLOT — prompt caching on the ollama path (the MEASURED dominant
#     per-turn burn: cacheRead=0 fleet-wide). No-op until the verified key returns;
#     DO NOT GUESS the key — see FLEET-STANDARDS.md §9.
#   • Core-bootstrap SIZE GUARD (warn-only, ~150K target) — flags oversized
#     compiled AGENTS/MEMORY/TOOLS/SOUL/IDENTITY re-billed every turn; never edits
#     content — see FLEET-STANDARDS.md §10.
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
        },
        # ON-DEMAND MCP TOOL LOADING — fleet-wide "schema-every-turn" token-burn fix.
        # (FLEET-STANDARDS.md §8.) tools.toolSearch.mode = "directory" compacts EVERY
        # OpenClaw / plugin / MCP tool behind a bounded names+descriptions catalog that
        # the model searches and hydrates ON DEMAND (openclaw.tools search/describe/call),
        # instead of injecting every full tool JSON schema into context on every turn.
        # This is the durable fix for the fleet-wide burn — most acute on the GHL
        # community MCP (`ghl-community-mcp`, ~hundreds of tools) that update-skills.sh
        # `wire_ghl_mcp` re-registers on every pass: directory mode compacts it regardless
        # of how many servers/tools are registered, so re-registration can NEVER
        # reintroduce the full-schema cost. Client-provided run tools stay directly
        # visible; only the standing catalog (OpenClaw/plugin/MCP) is compacted.
        # Verified: docs.openclaw.ai/tools/tool-search — tools.toolSearch.mode accepts
        #   "code" (gateway default) | "tools" | "directory"  (or `false` to disable).
        # Idempotent + override-preserving: deep_merge() recurses into an existing
        # toolSearch block and enforces ONLY `mode`, leaving any per-box tuning
        # (codeTimeoutMs / searchDefaultLimit / maxSearchLimit) untouched. The
        # `openclaw config validate` gate below is the backstop + auto-rollback if a
        # gateway version ever rejects the key.
        "toolSearch": {
            "mode": "directory"
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
    # mc-route__route_task = the SHIPPED signed routing tool (scripts/mc-route.sh);
    # the CEO routes by CALLING it (structured tool call, no shell) — that presence
    # is what clears verify-routing.sh G7. exec is RETAINED (per G1's decision in
    # hooks/lib-ceo-tool-gate.sh), NOT removed: it stays ONLY as the exec channel for
    # the two anchored helpers (route-presentation.sh + mc-route.sh); the intent-gate
    # default-denies every other exec. KEEP IN SYNC with hooks/lib-ceo-tool-gate.sh.
    "mc-route__route_task",
    "exec",
    # FABLE-5 FIX — plugin/operational tools. An explicit per-agent tools.allow is
    # a HARD allowlist: any tool not named here is stripped from the CEO, including
    # the tools its plugins call. active-memory needs memory_search + memory_get;
    # without them the plugin's tool calls resolve to nothing → "No callable tools
    # remain after resolving explicit tool allowlist." Admit the plugin + operational
    # tools; production tools stay DENIED and routing stays behavioral DOCTRINE.
    # Additive — G7 still passes. KEEP IN SYNC with hooks/lib-ceo-tool-gate.sh.
    "memory_search", "memory_get",
    "cron", "gateway", "nodes",
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
        # v16.1.3 FIX — cross-agent routing tools live on ROOT `tools`
        # (config["tools"]), NEVER on a per-agent tools block. The per-agent
        # AgentEntry.tools schema is additionalProperties:false and REJECTS
        # `sessions`/`agentToAgent` (allowed keys: allow/alsoAllow/byProvider/
        # codeMode/deny/elevated/exec/fs/loopDetection/message/profile/sandbox/
        # toolsBySender). Writing them per-agent fails `openclaw config validate`,
        # so the reload is skipped and the cron engine goes down on a
        # router-default box. Root `tools` DOES accept them:
        # tools.sessions.visibility (self|tree|agent|all) and
        # tools.agentToAgent.{enabled,allow[]}. Verified on gateway 2026.5.22,
        # 2026.5.28 and 2026.6.8.
        _root_tools = cfg.setdefault("tools", {})
        if not isinstance(_root_tools, dict):
            _root_tools = {}
            cfg["tools"] = _root_tools
        # sessions.visibility=all: routing agent MUST see all sessions so it can
        # locate and hand off to any department agent (gateway default "tree" —
        # spawned-children only — silently blocks department handoffs).
        _sessions = _root_tools.setdefault("sessions", {})
        if not isinstance(_sessions, dict):
            _sessions = {}
            _root_tools["sessions"] = _sessions
        if _sessions.get("visibility") != "all":
            _sessions["visibility"] = "all"
        # agentToAgent: routing agent must be able to message peer agents
        # directly. Idempotent — preserves any existing allow list if already
        # customized (setdefault only seeds missing keys).
        _a2a = _root_tools.setdefault("agentToAgent", {})
        if not isinstance(_a2a, dict):
            _a2a = {}
            _root_tools["agentToAgent"] = _a2a
        _a2a.setdefault("enabled", True)
        _a2a.setdefault("allow", ["*"])
        print(f"[apply-fleet-standards] re-asserted CEO tool-gate on default agent (id={agent.get('id','<unknown>')}; production tools denied) + routing tools (sessions/agentToAgent) on ROOT tools")

# v16.1.3 SELF-HEAL — sessions/agentToAgent belong on ROOT `tools`, NEVER on a
# per-agent tools block (AgentEntry.tools is additionalProperties:false and
# REJECTS them: a corrupted box fails `openclaw config validate`, the reload is
# skipped, and the cron engine goes down — the original router-default defect).
# REMOVE the schema-invalid keys from EVERY per-agent tools block, MIGRATING the
# configured value up to ROOT `tools` when root does not already carry it, so a
# previously-corrupted box is REPAIRED on the next run (the gateway hot-reloads
# the now-valid config — no restart). Runs UNCONDITIONALLY (independent of the
# consent carve-out / router-gate above) so even a consented or non-router box is
# repaired. Idempotent: no per-agent occurrence → no-op; running twice never
# re-corrupts.
def _heal_peragent_routing_keys(_cfg):
    _rt = _cfg.setdefault("tools", {})
    if not isinstance(_rt, dict):
        _rt = {}
        _cfg["tools"] = _rt
    _healed = []
    for _ag in (_cfg.get("agents", {}) or {}).get("list", []) or []:
        if not isinstance(_ag, dict):
            continue
        _at = _ag.get("tools")
        if not isinstance(_at, dict):
            continue
        for _k in ("sessions", "agentToAgent"):
            if _k in _at:
                if _k not in _rt and isinstance(_at[_k], (dict, list)):
                    _rt[_k] = _at[_k]  # migrate the configured value up to root
                del _at[_k]
                _healed.append(f"{_ag.get('id', '<unknown>')}.{_k}")
    return _healed

_healed_keys = _heal_peragent_routing_keys(cfg)
if _healed_keys:
    print("[apply-fleet-standards] v16.1.3 self-heal: removed schema-invalid per-agent routing keys + ensured on ROOT tools: " + ", ".join(_healed_keys))

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

# ─── 3d. RESERVED SLOT — PROMPT CACHING on the ollama / Ollama-Cloud path ─────
# MEASURED ROOT CAUSE (fleet, 2026-07-09): prompt caching is structurally OFF on
# the ollama path — cacheRead=0 on ~100% of ollama calls across every measured
# box, so the ENTIRE payload is re-billed on every turn. That is the dominant
# per-turn token-burn driver fleet-wide; the tools.toolSearch directory-mode
# standard (§2 above / FLEET-STANDARDS.md §8) is only the tool-SCHEMA lever
# (it helps GHL-heavy boxes, not the caching burn).
#
# The durable fix is enabling prompt caching on the ollama path — BUT the exact
# config key AND whether Ollama-Cloud even supports server-side caching are still
# being verified against the OpenClaw docs. DO NOT GUESS THE KEY: a wrong key
# fails `openclaw config validate` (which rolls this entire apply back) or
# silently no-ops. This is the clearly-marked, idempotent slot. When the VERIFIED
# key/value returns, write it into `cfg` inside the canonical deep-merge block
# above (Section 2) — it is then automatically covered by the
# `openclaw config validate` + rollback gate below. Reference: FLEET-STANDARDS.md §9.
#
# >>> RESERVED-SLOT: PROMPT-CACHING-OLLAMA — fill with the VERIFIED key ONLY <<<
# Placeholder SHAPE (NOT a real key — do NOT write until verified):
#   cfg.setdefault("<verified-subtree>", {})["<verified-key>"] = <verified-value>
#
# This release writes NOTHING here (config stays valid); it only logs the slot.
echo "[apply-fleet-standards] prompt-caching (ollama path): RESERVED slot — awaiting VERIFIED config key (FLEET-STANDARDS.md §9); no-op this release (nothing written)"

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

# ─── 4a-SOVEREIGNTY. Model-sovereignty strip/repair (FAIL-OPEN) ───────────────
# v16.2.17: the onboarding GENERATOR is Anthropic-free/preview-free/Ollama-first,
# but LEGACY boxes remediated earlier can still carry a lingering Anthropic
# provider/plugin block, `-preview`/free slugs in fallback[] chains, or runaway
# cascades. scripts/repair-model-sovereignty.sh is an idempotent, backup-before-
# edit, box-user, no-restart remediation that strips exactly those (keying ONLY
# off FORBIDDEN_PREFIXES + `-preview` + free-sentinels — it never touches a
# client's own OpenAI/OpenRouter/Gemini providers/chains). It was never invoked
# by install/update; wire it here so BOTH install.sh and update-skills.sh run it
# on every pass. FAIL-OPEN: any non-zero (offenders remain / needs owner input /
# missing tool) logs a warning and CONTINUES — it must NEVER abort the run. NO
# gateway reload here (apply-fleet-standards / the caller reloads downstream).
_FS_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPAIR_MS_SCRIPT=""
for _cand in \
  "$_FS_SCRIPT_DIR/repair-model-sovereignty.sh" \
  "$OC_ROOT/scripts/repair-model-sovereignty.sh" \
  "$HOME/.openclaw/scripts/repair-model-sovereignty.sh"; do
  [ -f "$_cand" ] && REPAIR_MS_SCRIPT="$_cand" && break
done
REPAIR_MS_SU=""
for _su in \
  "$OC_ROOT/skills/shared-utils" \
  "$_FS_SCRIPT_DIR/../shared-utils" \
  "$HOME/.openclaw/skills/shared-utils"; do
  if [ -f "$_su/select_model.py" ] && [ -f "$_su/assert_model_sovereignty.py" ]; then
    REPAIR_MS_SU="$_su"; break
  fi
done
if [ -n "$REPAIR_MS_SCRIPT" ]; then
  echo "[apply-fleet-standards] running model-sovereignty strip/repair (fail-open): $REPAIR_MS_SCRIPT"
  _ms_args=(--apply --config "$OC_CONFIG" --box "$(hostname -s 2>/dev/null || echo box)")
  [ -n "$REPAIR_MS_SU" ] && _ms_args+=(--shared-utils "$REPAIR_MS_SU")
  if bash "$REPAIR_MS_SCRIPT" "${_ms_args[@]}"; then
    echo "[apply-fleet-standards] model-sovereignty repair: clean"
  else
    _ms_rc=$?
    echo "[apply-fleet-standards] WARNING: model-sovereignty repair exited $_ms_rc (offenders may remain / needs owner input) — CONTINUING (fail-open)" >&2
  fi
  # VPS: keep the config + any sweep backups owned by the runtime user (mirrors
  # the chown after the canonical merge above). Never freeze the gateway with a
  # root-owned config.
  if [ "$OC_ROOT" = "/data/.openclaw" ]; then
    chown "$OC_USER:$OC_USER" "$OC_CONFIG" 2>/dev/null || true
    for _b in "$OC_CONFIG".bak-model-sweep-*; do
      [ -e "$_b" ] && chown "$OC_USER:$OC_USER" "$_b" 2>/dev/null || true
    done
  fi
else
  echo "[apply-fleet-standards] WARNING: repair-model-sovereignty.sh not found (checked script dir, \$OC_ROOT/scripts, ~/.openclaw/scripts) — SKIPPING model-sovereignty repair (fail-open)" >&2
fi

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

# ─── 5a-SIZEGUARD. Core-bootstrap size guard (WARN-ONLY — never edits content) ─
# MEASURED (fleet, 2026-07-09): several boxes carry a compiled core bootstrap
# (the gateway-injected AGENTS/MEMORY/TOOLS/SOUL/IDENTITY/USER/HEARTBEAT) of
# 190K–330K chars — re-injected on EVERY turn (and, while prompt caching is off
# on the ollama path, re-billed every turn). This guard MEASURES the injected
# core-file set in the resolved workspace (the SAME files the gateway reads — see
# shared-utils/resolve_injected_core_files.py) and WARNS when the total exceeds
# the target. It NEVER edits core-file content — trimming is an operator decision;
# this only makes the bloat visible on every install/update. Idempotent (pure
# measurement) + non-blocking (never aborts the run). Target overridable via
# FLEET_CORE_BOOTSTRAP_TARGET_CHARS. Reference: FLEET-STANDARDS.md §10.
FLEET_CORE_BOOTSTRAP_TARGET_CHARS="${FLEET_CORE_BOOTSTRAP_TARGET_CHARS:-150000}"
WORKSPACE_DIR="$WORKSPACE_DIR" \
FLEET_CORE_BOOTSTRAP_TARGET_CHARS="$FLEET_CORE_BOOTSTRAP_TARGET_CHARS" \
python3 - <<'SIZEEOF' || true
import os
ws = os.environ.get("WORKSPACE_DIR", "")
try:
    target = int(os.environ.get("FLEET_CORE_BOOTSTRAP_TARGET_CHARS", "150000"))
except ValueError:
    target = 150000
# The gateway-injected core-file set (matches resolve_injected_core_files.py).
CORE = ["AGENTS.md", "MEMORY.md", "TOOLS.md", "SOUL.md", "IDENTITY.md", "USER.md", "HEARTBEAT.md"]
total = 0
rows = []
for name in CORE:
    p = os.path.join(ws, name)
    try:
        n = len(open(p, encoding="utf-8", errors="replace").read()) if os.path.isfile(p) else 0
    except Exception:
        n = 0
    if n:
        rows.append((name, n))
        total += n
rows.sort(key=lambda x: -x[1])
if total > target:
    print(f"[apply-fleet-standards] WARN: CORE-BOOTSTRAP {total:,} chars EXCEEDS target {target:,} (workspace {ws})")
    print(f"[apply-fleet-standards]       injected + re-billed every turn — trim to cut per-turn token burn. WARN ONLY (no content edited).")
    for name, n in rows:
        print(f"[apply-fleet-standards]       {name:<13} {n:>8,} chars")
    print(f"[apply-fleet-standards]       TARGET: keep compiled core bootstrap under {target:,} chars/box (FLEET-STANDARDS.md §10)")
else:
    print(f"[apply-fleet-standards] core-bootstrap size guard: {total:,} chars within target {target:,} (workspace {ws}) — OK")
SIZEEOF

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
# Idempotent: guarded by <!-- CEO_ROUTING_NO_LOOPHOLES_V2 --> marker.
# P1-04 (V1→V2): V2 adds the trust-engine rule — when the CEO routes a CLIENT
# message it MUST pass the originating chat id so the report-back loop can keep
# the client informed. Bumping the marker (with the strip-V1 migration below) is
# what makes the new instruction re-inject on the ~30 already-onboarded boxes: a
# stale V1 marker would no-op the block forever and the boxes would never see it.
CEO_ROUTING_MARKER="<!-- CEO_ROUTING_NO_LOOPHOLES_V2 -->"
CEO_ROUTING_MARKER_V1="<!-- CEO_ROUTING_NO_LOOPHOLES_V1 -->"
if grep -qF "$CEO_ROUTING_MARKER_V1" "$AGENTS_FILE_EARLY" 2>/dev/null; then
  # Legacy V1 block present: strip it so V2 re-injects. The V1 block has no END
  # marker — it terminates at the first '---' line after its open marker — so we
  # remove exactly that region (plus the blank lines hugging it).
  python3 - "$AGENTS_FILE_EARLY" <<'CEOSTRIP_PY'
import re, sys
p = sys.argv[1]
c = open(p, encoding="utf-8", errors="replace").read()
c = re.sub(r"\n*<!-- CEO_ROUTING_NO_LOOPHOLES_V1 -->.*?\n---[ \t]*\n", "\n", c, count=1, flags=re.DOTALL)
open(p, "w", encoding="utf-8").write(c)
CEOSTRIP_PY
  echo "[apply-fleet-standards] migrated legacy CEO_ROUTING_NO_LOOPHOLES_V1 → V2 in $AGENTS_FILE_EARLY"
fi
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
        print "<!-- CEO_ROUTING_NO_LOOPHOLES_V2 -->"
        print "## ⛔ CEO ROUTING — NO LOOPHOLES (v11.3.2 — closes all self-execution escape hatches; V2 adds the P1-04 trust-engine chat-id rule)"
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
        print "### Trust engine — pass the client'\''s chat id when you route a CLIENT message (P1-04)"
        print "When the task came from a CLIENT message (e.g. a Telegram request), you MUST pass the ORIGINATING"
        print "chat id so the Command Center'\''s report-back loop keeps the client informed (assigned → in-progress"
        print "+ ETA → done + where-to-find-it). A routed task must NEVER go silent — this is the #1 client"
        print "complaint fix. Set the chat id on the signed router invocation:"
        print ""
        print "    MC_ROUTE_REQUESTER_CHAT_ID=\"<originating client chat id>\" MC_ROUTE_REQUESTER_CHANNEL=\"telegram\" \\"
        print "      bash \"$OC_ROOT/scripts/mc-route.sh\" <department_slug> \"<title>\" \"<owner message, verbatim>\""
        print ""
        print "Leave the chat id UNSET for operator/internal routes (they are never reported on). NEVER invent or"
        print "reuse another client'\''s chat id — pass ONLY the real originating chat id of the message you are routing."
        print ""
        print "<!-- END CEO_ROUTING_NO_LOOPHOLES_V2 -->"
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
      printf '<!-- CEO_ROUTING_NO_LOOPHOLES_V2 -->\n'
      printf '## ⛔ CEO ROUTING — NO LOOPHOLES (v11.3.2 — closes all self-execution escape hatches; V2 adds the P1-04 trust-engine chat-id rule)\n\n'
      printf 'The CEO'\''s ONLY permitted routing action: POST /api/tasks/ingest with department_slug.\n'
      printf 'No trivial-task, quick-API-call, or spawn-sub-agent exceptions. See AGENTS.md for full rule.\n\n'
      printf 'TRUST ENGINE (P1-04): when the task came from a CLIENT message, ALWAYS pass the originating chat id\n'
      printf 'so the report-back loop keeps the client informed — set MC_ROUTE_REQUESTER_CHAT_ID (and\n'
      printf 'MC_ROUTE_REQUESTER_CHANNEL, default telegram) on the signed router: bash "$OC_ROOT/scripts/mc-route.sh".\n'
      printf 'Leave it unset for operator/internal routes; never invent or reuse another client'\''s chat id.\n\n'
      printf '<!-- END CEO_ROUTING_NO_LOOPHOLES_V2 -->\n'
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

# ─── 4b-REFLEX. Stamp the SIGNED route helper + PRESENTATION_ROUTING_REFLEX_V2 ─
# TRIGGER-BEFORE-THINKING reflex: on a presentation / deck / PowerPoint / slide /
# keynote request the CEO's VERY FIRST action must route the task to the
# `presentations` department on the Command Center — no reads, no sessions_list,
# no verifying the department, no intake questions.
#
# P1-4 FIX (V1→V2): the V1 block told the CEO to POST a BARE curl (no auth) to
#   http://127.0.0.1:4000/api/tasks/ingest. The Command Center ships FAIL-CLOSED —
#   middleware 503s external ingest when WEBHOOK_SECRET is unset, 401s when
#   MC_API_TOKEN is set and no Bearer is sent; the ingest route 401s when
#   WEBHOOK_SECRET is set and x-webhook-signature is missing; a loopback curl gets
#   NO same-origin exemption (no Origin header). So V2 has the CEO run a stamped,
#   SIGNED helper ($OC_ROOT/scripts/route-presentation.sh) that resolves
#   MC_API_TOKEN + WEBHOOK_SECRET at RUNTIME (never embedded) and signs BOTH auth
#   layers exactly like 06-ghl-install-pages/tools/cc_board.py. On failure the CEO
#   escalates to the operator — it never falls back to self-intake.
#
# P2-1 FIX (stamp-time guard): if the `presentations` department does NOT exist on
#   this box (owner declined), stamping the reflex would strand every deck card on
#   the CEO board. So we only stamp when presentations is present/unknown, and we
#   REMOVE any previously-stamped block when presentations is affirmatively absent.
#
# PA-BOX GUARD (v16.2.17, PR #459): even before the dept check, a DEFINITIVE
#   personal-assistant-only box — one whose DEFAULT agent is NOT a router (no CEO /
#   master-orchestrator, so no Presentations dept and no Command Center on :4000) —
#   is skipped: the reflex would make the PA POST to a 404 on every deck/slide
#   message. We REUSE the exact router signal the tool-gate layers use (is_master /
#   role=="router" / id in ROUTER_IDS) — NOT dept-dir existence (the presentations
#   dept is seeded in a LATER layer, so a dir check would be stamp-order-dependent).
#   The two guards are UNIFIED below into one path: PA-box → skip/remove reflex;
#   else presentations-dept ABSENT → skip/remove reflex; else (PRESENT/UNKNOWN) →
#   stamp the signed helper + V2.
# The block MUST sit ABOVE ROLE_DISCIPLINE_V1 + CEO_ROUTING_NO_LOOPHOLES_V1 (both
# already stamped at the top by 5a + 4b above): it is stamped LAST as an
# absolute-top prepend and becomes the file's first block. Every later block
# (4c / 5 / 5b / 5c / 5d) appends to the bottom, so this stays topmost.
#
# CC ingest port 4000 is UNIFORM fleet-wide (CC_PORT=4000), so the helper targets
# 127.0.0.1:4000. Idempotent: V2 marker guard; V1 auto-migrated. The route helper
# is (re)written every run so fixes propagate.
# KEEP IN SYNC with the twin stamper in scripts/apply-routing-fix.sh (LAYER 1) —
# the ROUTE_HELPER_SH and PRES_REFLEX_V2 heredocs are BYTE-IDENTICAL twins.
# ─── MC-ROUTE STAMP — general signed task-routing helper (fleet-wide) ─────
# Stamp $OC_ROOT/scripts/mc-route.sh: the SHIPPED implementation behind the CEO's
# `mc-route__route_task` routing tool. It is the GENERAL twin of route-presentation.sh
# (the department is an ARGUMENT, not the hardcoded "presentations"), so the CEO can
# route ANY task to ANY department WITHOUT self-executing. Unlike the presentation
# reflex helper it is NOT gated on the `presentations` department — it is stamped on
# EVERY box, every run. The heredoc body below is BYTE-IDENTICAL to the repo's
# scripts/mc-route.sh (shipped by G1) and BYTE-IDENTICAL between both KEEP-IN-SYNC
# stampers (apply-fleet-standards.sh + apply-routing-fix.sh). Idempotent: the file is
# (re)written verbatim every run (identical bytes) so fixes propagate — the same
# overwrite mechanism the route-presentation.sh helper uses below.
MC_ROUTE_HELPER_DIR="$OC_ROOT/scripts"
MC_ROUTE_HELPER_PATH="$MC_ROUTE_HELPER_DIR/mc-route.sh"
mkdir -p "$MC_ROUTE_HELPER_DIR"
cat > "$MC_ROUTE_HELPER_PATH" <<'MC_ROUTE_SH'
#!/usr/bin/env bash
# mc-route.sh — SIGNED general task-routing helper (fleet-wide).
#
# This is the GENERAL version of route-presentation.sh: the same signed
# Command-Center ingest helper, but the department is an ARGUMENT instead of the
# hardcoded "presentations". It is the shipped implementation behind the
# `mc-route__route_task` routing tool the CEO/orchestrator uses to route ANY
# task to ANY department without self-executing.
#
#   USAGE:  mc-route.sh <department_slug> <title> [description...]
#
#     <department_slug>   target workspace/department (e.g. presentations,
#                         general-task, social-media, video). REQUIRED.
#     <title>             short task title (truncated to 120 chars). REQUIRED.
#     [description...]    the rest of the args are joined with single spaces
#                         into the task description (owner message, verbatim).
#
# WHY (identical to route-presentation.sh): the Command Center ships FAIL-CLOSED.
# Middleware 503s external ingest when WEBHOOK_SECRET is unset, and 401s when
# MC_API_TOKEN is set but no Bearer is sent; the /api/tasks/ingest route 401s when
# WEBHOOK_SECRET is set and x-webhook-signature is missing. A loopback curl gets NO
# same-origin exemption (it sends no Origin). So — exactly like the sanctioned
# producer 06-ghl-install-pages/tools/cc_board.py and route-presentation.sh — this
# helper signs BOTH layers:
#   Authorization: Bearer <MC_API_TOKEN>                          (middleware layer)
#   x-webhook-signature: HMAC-SHA256(WEBHOOK_SECRET, rawBody) hex (route layer)
# Secrets are resolved at RUNTIME from the box's stores; NO secret value is ever
# written into this file.
#
# EXIT 0 on a 2xx ingest; non-zero on failure — on non-zero the CEO must tell the
# owner it is escalating to the operator (never self-intake, never ask intake
# questions, never retry forever).
#
# OPTIONAL ENV OVERRIDES (all have safe defaults; the security-critical secret
# resolution + signing are IDENTICAL to route-presentation.sh):
#   MC_ROUTE_INGEST_URL   ingest endpoint    (default http://127.0.0.1:4000/api/tasks/ingest)
#   MC_ROUTE_SOURCE       payload "source"   (default telegram)
#   MC_ROUTE_PRIORITY     payload "priority" (default medium)
#   MC_ROUTE_MAX_RETRIES  retries after 1st  (default 2)
#   MC_ROUTE_REQUESTER_CHAT_ID   P1-04 trust engine: the ORIGINATING client chat id the
#                                Command Center report-back loop acks/progress/dones back to.
#                                Set by the orchestrator when the task came from a client message.
#   MC_ROUTE_REQUESTER_CHANNEL   the client channel (default telegram); only used when
#                                MC_ROUTE_REQUESTER_CHAT_ID is set.
set -uo pipefail

INGEST_URL="${MC_ROUTE_INGEST_URL:-http://127.0.0.1:4000/api/tasks/ingest}"
MAX_RETRIES="${MC_ROUTE_MAX_RETRIES:-2}"
SOURCE="${MC_ROUTE_SOURCE:-telegram}"
PRIORITY="${MC_ROUTE_PRIORITY:-medium}"
# P1-04 trust engine: the originating client channel + chat id, so the Command
# Center report-back loop can acknowledge/progress/done back to the client. Empty
# (the default) => omitted from the payload (an operator/internal route).
REQUESTER_CHAT_ID="${MC_ROUTE_REQUESTER_CHAT_ID:-}"
REQUESTER_CHANNEL="${MC_ROUTE_REQUESTER_CHANNEL:-telegram}"

DEPARTMENT_SLUG="${1:-}"
TITLE="${2:-}"
# The rest of the args (3..N) form the description, joined with single spaces.
if [ "$#" -gt 2 ]; then
  shift 2
  DESCRIPTION="$*"
else
  DESCRIPTION=""
fi

_escalate() {
  echo "mc-route: FAILED — $1" >&2
  echo "ESCALATE_TO_OPERATOR: task routing failed. The CEO must tell the owner it is escalating this to the operator. Do NOT self-intake, do NOT ask intake questions, do NOT retry." >&2
  exit 1
}

[ -n "$DEPARTMENT_SLUG" ] || _escalate "empty department_slug argument (usage: mc-route.sh <department_slug> <title> [description...])"
[ -n "$TITLE" ]          || _escalate "empty title argument (usage: mc-route.sh <department_slug> <title> [description...])"

# ── Runtime secret resolution (reads only; never hardcoded) ──────────────────
# Store order mirrors the Command Center's own env precedence so the signature
# matches what the CC server validates against; the WEBHOOK_SECRET alias order
# (WEBHOOK_SECRET, then CC_WEBHOOK_SECRET) mirrors cc_board.py. Live process env
# is the last-resort fallback. IDENTICAL to route-presentation.sh.
_ENV_STORES=(
  "$HOME/projects/command-center/.env.local"
  "$HOME/projects/command-center/.env"
  "/data/projects/command-center/.env.local"
  "/data/projects/command-center/.env"
  "$HOME/.openclaw/secrets/.env"
  "/data/.openclaw/secrets/.env"
)

_resolve() {
  # $@ = candidate key names (aliases). First non-empty across the dotenv stores
  # (in order) then the live process env. Prints ONLY the value. Uses python3 for
  # robust dotenv parsing (export / quotes / comments).
  RP_KEYS="$*" python3 - "${_ENV_STORES[@]}" <<'PYRESOLVE'
import os, sys
keys = os.environ.get("RP_KEYS", "").split()
stores = sys.argv[1:]

def parse(path):
    out = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                if s.startswith("export "):
                    s = s[len("export "):]
                if "=" not in s:
                    continue
                k, v = s.split("=", 1)
                k = k.strip(); v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
                    v = v[1:-1]
                out[k] = v
    except Exception:
        return {}
    return out

for path in stores:
    kv = parse(path)
    for k in keys:
        if kv.get(k):
            sys.stdout.write(kv[k]); sys.exit(0)
for k in keys:
    v = os.environ.get(k)
    if v:
        sys.stdout.write(v); sys.exit(0)
PYRESOLVE
}

MC_API_TOKEN="$(_resolve MC_API_TOKEN)"
WEBHOOK_SECRET="$(_resolve WEBHOOK_SECRET CC_WEBHOOK_SECRET)"

# ── Build the EXACT raw body once (compact JSON, like cc_board.py) ───────────
BODY_FILE="$(mktemp "${TMPDIR:-/tmp}/mc-route.XXXXXX")" || _escalate "mktemp failed"
trap 'rm -f "$BODY_FILE"' EXIT
if ! DEPARTMENT_SLUG="$DEPARTMENT_SLUG" TITLE="$TITLE" DESCRIPTION="$DESCRIPTION" \
     SOURCE="$SOURCE" PRIORITY="$PRIORITY" \
     REQUESTER_CHAT_ID="$REQUESTER_CHAT_ID" REQUESTER_CHANNEL="$REQUESTER_CHANNEL" \
     python3 - >"$BODY_FILE" <<'PYBODY'
import json, os, sys
payload = {
    "title": os.environ.get("TITLE", "")[:120],
    "description": os.environ.get("DESCRIPTION", ""),
    "department_slug": os.environ.get("DEPARTMENT_SLUG", ""),
    "source": os.environ.get("SOURCE", "telegram"),
    "priority": os.environ.get("PRIORITY", "medium"),
}
# P1-04 trust engine: pass the originating client chat id through so the Command
# Center captures it and reports acknowledge/progress/done back to the client.
# Only added when present — an operator/internal route omits it entirely.
_rcid = os.environ.get("REQUESTER_CHAT_ID", "").strip()
if _rcid:
    payload["requester_chat_id"] = _rcid
    payload["requester_channel"] = os.environ.get("REQUESTER_CHANNEL", "telegram").strip() or "telegram"
sys.stdout.write(json.dumps(payload, separators=(",", ":")))
PYBODY
then
  _escalate "could not build request body"
fi

# ── Sign the RAW body: HMAC-SHA256(WEBHOOK_SECRET, rawBody) hex (openssl) ─────
# BYTE-FOR-BYTE identical to route-presentation.sh so the signature the CC server
# validates is produced the same way regardless of which helper routed the task.
SIG=""
if [ -n "$WEBHOOK_SECRET" ]; then
  if command -v openssl >/dev/null 2>&1; then
    SIG="$(openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" <"$BODY_FILE" 2>/dev/null | sed -E 's/^.*= *//' | tr -d ' \r\n')"
  fi
  if [ -z "$SIG" ]; then
    # openssl unavailable / parse miss — python3 hmac fallback over the SAME bytes.
    SIG="$(WEBHOOK_SECRET="$WEBHOOK_SECRET" python3 - "$BODY_FILE" <<'PYSIG'
import hashlib, hmac, os, sys
sys.stdout.write(hmac.new(os.environ.get("WEBHOOK_SECRET", "").encode("utf-8"),
                          open(sys.argv[1], "rb").read(), hashlib.sha256).hexdigest())
PYSIG
)"
  fi
fi

# ── Headers: send Bearer / signature ONLY when the respective secret exists ──
_H=(-H 'Content-Type: application/json' -H 'Accept: application/json')
[ -n "$MC_API_TOKEN" ] && _H+=(-H "Authorization: Bearer $MC_API_TOKEN")
[ -n "$SIG" ]          && _H+=(-H "x-webhook-signature: $SIG")

# ── POST with retries (MAX_RETRIES retries after the first attempt) ──────────
attempt=0
http_code=""
resp_body=""
while :; do
  RAW="$(curl -sS -X POST "$INGEST_URL" "${_H[@]}" --data-binary @"$BODY_FILE" -w $'\n%{http_code}' 2>/dev/null || true)"
  http_code="${RAW##*$'\n'}"
  resp_body="${RAW%$'\n'*}"
  case "$http_code" in
    2[0-9][0-9]) break ;;
  esac
  [ "$attempt" -ge "$MAX_RETRIES" ] && break
  attempt=$((attempt + 1))
  sleep 1
done

echo "mc-route: HTTP ${http_code:-<none>} from $INGEST_URL (department=$DEPARTMENT_SLUG)"
[ -n "$resp_body" ] && printf '%s\n' "$resp_body"

case "$http_code" in
  2[0-9][0-9])
    # Workspace-mismatch guard: warn if the card did NOT land on the requested
    # department workspace (mirrors route-presentation.sh's presentations check,
    # generalized to the department_slug argument).
    WS="$(printf '%s' "$resp_body" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    sys.stdout.write(str(d.get("workspace_id", "")) if isinstance(d, dict) else "")
except Exception:
    sys.stdout.write("")' 2>/dev/null || true)"
    if [ -n "$WS" ] && [ "$WS" != "$DEPARTMENT_SLUG" ]; then
      echo "mc-route: WARNING — task landed on workspace '$WS', NOT '$DEPARTMENT_SLUG'." >&2
      echo "ESCALATE_TO_OPERATOR: the '$DEPARTMENT_SLUG' department may be absent on this box. The CEO must tell the owner it is escalating to the operator instead of proceeding or self-intaking." >&2
    fi
    exit 0
    ;;
  *)
    _escalate "ingest POST returned HTTP ${http_code:-<none>} after ${attempt} retr(y|ies)"
    ;;
esac
MC_ROUTE_SH
chmod 755 "$MC_ROUTE_HELPER_PATH"
if [ "$OC_ROOT" = "/data/.openclaw" ]; then
  chown node:node "$MC_ROUTE_HELPER_PATH" 2>/dev/null || true
fi
echo "[mc-route-stamp] stamped signed mc-route helper -> $MC_ROUTE_HELPER_PATH (chmod 755)"

PRES_REFLEX_V2_MARKER="<!-- PRESENTATION_ROUTING_REFLEX_V2 -->"
PRES_REFLEX_V1_MARKER="<!-- PRESENTATION_ROUTING_REFLEX_V1 -->"
PRES_REFLEX_HELPER_DIR="$OC_ROOT/scripts"
PRES_REFLEX_HELPER_PATH="$PRES_REFLEX_HELPER_DIR/route-presentation.sh"

# (a) Does the `presentations` department exist on THIS box? Prints PRESENT |
#     ABSENT | UNKNOWN. Checks the ZHC departments.json canonical roots (Mac:
#     ~/Downloads/openclaw-master-files/...; VPS: /data/openclaw-master-files/...)
#     and the Command Center workspaces (mission-control.db). UNKNOWN = no source
#     was readable (we then stamp anyway; the helper's runtime workspace_id guard
#     backstops a mis-route).
_pres_dept_status() {
  python3 - <<'PRESDETECT_PY'
import glob, json, os, sqlite3, sys
HOME = os.path.expanduser("~")

def slug(s):
    return "".join(c if c.isalnum() else "-" for c in str(s).lower()).strip("-")

read = 0
found = False

dept_globs = [
    os.path.join(HOME, "Downloads/openclaw-master-files/zero-human-company/*/departments.json"),
    "/data/openclaw-master-files/zero-human-company/*/departments.json",
]
for pat in dept_globs:
    for path in glob.glob(pat):
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                data = json.load(fh)
        except Exception:
            continue
        read += 1
        depts = data.get("departments") if isinstance(data, dict) else data
        if isinstance(depts, dict):
            depts = list(depts.values())
        if not isinstance(depts, list):
            continue
        for d in depts:
            if not isinstance(d, dict):
                continue
            for key in ("slug", "department_slug", "name", "id", "title"):
                v = d.get(key)
                if v and "presentation" in slug(v):
                    found = True
                    break
            if found:
                break
        if found:
            break
    if found:
        break

if not found:
    db_cands = [
        os.path.join(HOME, "projects/command-center/mission-control.db"),
        os.path.join(HOME, "projects/mission-control/mission-control.db"),
        "/data/projects/command-center/mission-control.db",
    ]
    for db in db_cands:
        if not os.path.exists(db):
            continue
        try:
            con = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
            cur = con.cursor()
            vals = []
            for tbl, col in (("workspaces", "slug"), ("workspaces", "id"),
                             ("departments", "slug"), ("departments", "name")):
                try:
                    cur.execute("SELECT %s FROM %s" % (col, tbl))
                    vals += [r[0] for r in cur.fetchall() if r and r[0]]
                except Exception:
                    continue
            con.close()
        except Exception:
            continue
        read += 1
        if any("presentation" in slug(v) for v in vals):
            found = True
        if found:
            break

print("PRESENT" if found else ("ABSENT" if read > 0 else "UNKNOWN"))
PRESDETECT_PY
}

# (b) Remove any previously-stamped reflex block (V1 or V2) from an AGENTS.md.
_strip_pres_reflex() {
  python3 - "$1" <<'PRESSTRIP_PY'
import re, sys
p = sys.argv[1]
c = open(p, encoding="utf-8", errors="replace").read()
for ver in ("V1", "V2"):
    c = re.sub(
        r"<!-- PRESENTATION_ROUTING_REFLEX_" + ver + r" -->.*?"
        r"<!-- END PRESENTATION_ROUTING_REFLEX_" + ver + r" -->[ \t]*\r?\n?",
        "", c, flags=re.DOTALL)
c = c.lstrip("\n")
open(p, "w", encoding="utf-8").write(c)
PRESSTRIP_PY
}

# (c) PA-box detection (v16.2.17, PR #459): reuse the tool-gate router signal so a
#     DEFINITIVE personal-assistant-only box never stamps a reflex that would 404.
#     is_master / role=="router" / id in ROUTER_IDS → ROUTER; a non-router default
#     agent → PA (skipped); no-default / unparseable → treated as non-PA (stamps).
_REFLEX_BOXTYPE="$(OC_JSON="$OC_CONFIG" python3 - <<'PYBT'
import json, os
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
try:
    cfg = json.load(open(os.environ["OC_JSON"]))
    agents = cfg.get("agents", {}).get("list", []) or []
    da = next((a for a in agents if isinstance(a, dict) and a.get("default") is True), None)
    if da is None:
        da = next((a for a in agents if isinstance(a, dict) and a.get("id") == "main"), None)
    if da is None:
        print("NO_DEFAULT")
    else:
        print("ROUTER" if _is_router(da) else "PA")
except Exception:
    print("UNKNOWN")
PYBT
)" || _REFLEX_BOXTYPE="UNKNOWN"

PRES_DEPT_STATUS="$(_pres_dept_status 2>/dev/null || echo UNKNOWN)"
echo "[apply-fleet-standards] presentations department check: $PRES_DEPT_STATUS"
echo "[apply-fleet-standards] reflex box-type check: $_REFLEX_BOXTYPE"

if [ "$_REFLEX_BOXTYPE" = "PA" ]; then
  # PA-only box (default agent is a personal-assistant / non-router): no Presentations
  # dept and no Command Center on :4000 — the reflex would POST to a 404. Remove any
  # previously-stamped block and skip.
  if grep -qE 'PRESENTATION_ROUTING_REFLEX_V[12]' "$AGENTS_FILE_EARLY" 2>/dev/null; then
    _strip_pres_reflex "$AGENTS_FILE_EARLY"
    echo "[apply-fleet-standards] PA-only box (non-router default agent) — REMOVED previously-stamped reflex block from $AGENTS_FILE_EARLY (would POST to a 404)"
  else
    echo "[apply-fleet-standards] PA-only box (non-router default agent) — NOT stamping reflex block (would POST to a 404)"
  fi
elif [ "$PRES_DEPT_STATUS" = "ABSENT" ]; then
  # P2-1: owner declined presentations — never stamp (decks would strand on the
  # CEO board). Remove any previously-stamped block and skip.
  if grep -qE 'PRESENTATION_ROUTING_REFLEX_V[12]' "$AGENTS_FILE_EARLY" 2>/dev/null; then
    _strip_pres_reflex "$AGENTS_FILE_EARLY"
    echo "[apply-fleet-standards] presentations dept ABSENT — REMOVED previously-stamped reflex block from $AGENTS_FILE_EARLY (P2-1)"
  else
    echo "[apply-fleet-standards] presentations dept ABSENT — NOT stamping reflex block (P2-1)"
  fi
else
  # PRESENT or UNKNOWN → (re)stamp the signed helper, then stamp V2 at the top.
  mkdir -p "$PRES_REFLEX_HELPER_DIR"
  cat > "$PRES_REFLEX_HELPER_PATH" <<'ROUTE_HELPER_SH'
#!/usr/bin/env bash
# route-presentation.sh — SIGNED presentation-routing helper (fleet-wide).
# Stamped onto this box by BOTH apply-fleet-standards.sh and apply-routing-fix.sh
# (KEEP-IN-SYNC twins) and invoked by the PRESENTATION_ROUTING_REFLEX_V2 block in
# the CEO's AGENTS.md:  bash <this> "<title>" "<verbatim owner message>"
#
# WHY: the Command Center ships FAIL-CLOSED. Middleware 503s external ingest when
# WEBHOOK_SECRET is unset, and 401s when MC_API_TOKEN is set but no Bearer is sent;
# the /api/tasks/ingest route 401s when WEBHOOK_SECRET is set and x-webhook-signature
# is missing. A loopback curl gets NO same-origin exemption (it sends no Origin).
# So — exactly like the sanctioned producer 06-ghl-install-pages/tools/cc_board.py —
# this helper signs BOTH layers:
#   Authorization: Bearer <MC_API_TOKEN>                          (middleware layer)
#   x-webhook-signature: HMAC-SHA256(WEBHOOK_SECRET, rawBody) hex (route layer)
# Secrets are resolved at RUNTIME from the box's stores; NO secret value is ever
# written into this file or into AGENTS.md.
#
# EXIT 0 on a 2xx ingest; non-zero on failure — on non-zero the CEO must tell the
# owner it is escalating to the operator (never self-intake, never ask intake
# questions, never retry forever).
set -uo pipefail

INGEST_URL="http://127.0.0.1:4000/api/tasks/ingest"
MAX_RETRIES=2

TITLE="${1:-}"
DESCRIPTION="${2:-}"

_escalate() {
  echo "route-presentation: FAILED — $1" >&2
  echo "ESCALATE_TO_OPERATOR: presentation routing failed. The CEO must tell the owner it is escalating this to the operator. Do NOT self-intake, do NOT ask intake questions, do NOT retry." >&2
  exit 1
}

[ -n "$TITLE" ] || _escalate "empty title argument"

# ── Runtime secret resolution (reads only; never hardcoded) ──────────────────
# Store order mirrors the Command Center's own env precedence so the signature
# matches what the CC server validates against; the WEBHOOK_SECRET alias order
# (WEBHOOK_SECRET, then CC_WEBHOOK_SECRET) mirrors cc_board.py. Live process env
# is the last-resort fallback.
_ENV_STORES=(
  "$HOME/projects/command-center/.env.local"
  "$HOME/projects/command-center/.env"
  "/data/projects/command-center/.env.local"
  "/data/projects/command-center/.env"
  "$HOME/.openclaw/secrets/.env"
  "/data/.openclaw/secrets/.env"
)

_resolve() {
  # $@ = candidate key names (aliases). First non-empty across the dotenv stores
  # (in order) then the live process env. Prints ONLY the value. Uses python3 for
  # robust dotenv parsing (export / quotes / comments).
  RP_KEYS="$*" python3 - "${_ENV_STORES[@]}" <<'PYRESOLVE'
import os, sys
keys = os.environ.get("RP_KEYS", "").split()
stores = sys.argv[1:]

def parse(path):
    out = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                if s.startswith("export "):
                    s = s[len("export "):]
                if "=" not in s:
                    continue
                k, v = s.split("=", 1)
                k = k.strip(); v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
                    v = v[1:-1]
                out[k] = v
    except Exception:
        return {}
    return out

for path in stores:
    kv = parse(path)
    for k in keys:
        if kv.get(k):
            sys.stdout.write(kv[k]); sys.exit(0)
for k in keys:
    v = os.environ.get(k)
    if v:
        sys.stdout.write(v); sys.exit(0)
PYRESOLVE
}

MC_API_TOKEN="$(_resolve MC_API_TOKEN)"
WEBHOOK_SECRET="$(_resolve WEBHOOK_SECRET CC_WEBHOOK_SECRET)"

# ── Build the EXACT raw body once (compact JSON, like cc_board.py) ───────────
BODY_FILE="$(mktemp "${TMPDIR:-/tmp}/route-pres.XXXXXX")" || _escalate "mktemp failed"
trap 'rm -f "$BODY_FILE"' EXIT
if ! TITLE="$TITLE" DESCRIPTION="$DESCRIPTION" python3 - >"$BODY_FILE" <<'PYBODY'
import json, os, sys
payload = {
    "title": os.environ.get("TITLE", "")[:120],
    "description": os.environ.get("DESCRIPTION", ""),
    "department_slug": "presentations",
    "source": "telegram",
    "priority": "medium",
}
sys.stdout.write(json.dumps(payload, separators=(",", ":")))
PYBODY
then
  _escalate "could not build request body"
fi

# ── Sign the RAW body: HMAC-SHA256(WEBHOOK_SECRET, rawBody) hex (openssl) ─────
SIG=""
if [ -n "$WEBHOOK_SECRET" ]; then
  if command -v openssl >/dev/null 2>&1; then
    SIG="$(openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" <"$BODY_FILE" 2>/dev/null | sed -E 's/^.*= *//' | tr -d ' \r\n')"
  fi
  if [ -z "$SIG" ]; then
    # openssl unavailable / parse miss — python3 hmac fallback over the SAME bytes.
    SIG="$(WEBHOOK_SECRET="$WEBHOOK_SECRET" python3 - "$BODY_FILE" <<'PYSIG'
import hashlib, hmac, os, sys
sys.stdout.write(hmac.new(os.environ.get("WEBHOOK_SECRET", "").encode("utf-8"),
                          open(sys.argv[1], "rb").read(), hashlib.sha256).hexdigest())
PYSIG
)"
  fi
fi

# ── Headers: send Bearer / signature ONLY when the respective secret exists ──
_H=(-H 'Content-Type: application/json' -H 'Accept: application/json')
[ -n "$MC_API_TOKEN" ] && _H+=(-H "Authorization: Bearer $MC_API_TOKEN")
[ -n "$SIG" ]          && _H+=(-H "x-webhook-signature: $SIG")

# ── POST with retries (MAX_RETRIES retries after the first attempt) ──────────
attempt=0
http_code=""
resp_body=""
while :; do
  RAW="$(curl -sS -X POST "$INGEST_URL" "${_H[@]}" --data-binary @"$BODY_FILE" -w $'\n%{http_code}' 2>/dev/null || true)"
  http_code="${RAW##*$'\n'}"
  resp_body="${RAW%$'\n'*}"
  case "$http_code" in
    2[0-9][0-9]) break ;;
  esac
  [ "$attempt" -ge "$MAX_RETRIES" ] && break
  attempt=$((attempt + 1))
  sleep 1
done

echo "route-presentation: HTTP ${http_code:-<none>} from $INGEST_URL"
[ -n "$resp_body" ] && printf '%s\n' "$resp_body"

case "$http_code" in
  2[0-9][0-9])
    # Runtime P2-1 guard: warn if the card did NOT land on the presentations workspace.
    WS="$(printf '%s' "$resp_body" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    sys.stdout.write(str(d.get("workspace_id", "")) if isinstance(d, dict) else "")
except Exception:
    sys.stdout.write("")' 2>/dev/null || true)"
    if [ -n "$WS" ] && [ "$WS" != "presentations" ]; then
      echo "route-presentation: WARNING — task landed on workspace '$WS', NOT 'presentations'." >&2
      echo "ESCALATE_TO_OPERATOR: the presentations department may be absent on this box. The CEO must tell the owner it is escalating to the operator instead of proceeding or self-intaking." >&2
    fi
    exit 0
    ;;
  *)
    _escalate "ingest POST returned HTTP ${http_code:-<none>} after ${attempt} retr(y|ies)"
    ;;
esac
ROUTE_HELPER_SH
  chmod 700 "$PRES_REFLEX_HELPER_PATH"
  echo "[apply-fleet-standards] stamped signed route helper → $PRES_REFLEX_HELPER_PATH (chmod 700)"

  # (d) Idempotent V2 stamp with V1 auto-migration. Re-stamp when V2 is missing OR
  #     a stray V1 co-exists; otherwise no-op (helper was still refreshed above).
  if grep -qF "$PRES_REFLEX_V2_MARKER" "$AGENTS_FILE_EARLY" && ! grep -qF "$PRES_REFLEX_V1_MARKER" "$AGENTS_FILE_EARLY"; then
    echo "[apply-fleet-standards] PRESENTATION_ROUTING_REFLEX_V2 already present in $AGENTS_FILE_EARLY — no-op (helper refreshed)"
  else
    grep -qE 'PRESENTATION_ROUTING_REFLEX_V[12]' "$AGENTS_FILE_EARLY" && _strip_pres_reflex "$AGENTS_FILE_EARLY" || true
    PRES_REFLEX_TMPL="$(mktemp)"; _APPLY_TMPFILES+=("$PRES_REFLEX_TMPL")
    cat > "$PRES_REFLEX_TMPL" <<'PRES_REFLEX_V2'
<!-- PRESENTATION_ROUTING_REFLEX_V2 -->
# ⛔ REFLEX 0 — PRESENTATION REQUESTS: ROUTE BEFORE YOU THINK (this block runs FIRST)

This is a TRIGGER-BEFORE-THINKING rule. It fires BEFORE every other section of this file,
BEFORE you reason, BEFORE you read any SOP, BEFORE you write one word of reply.
It is not a "remember to route" reminder — it is a hard gate on your first action.

TRIGGER (case-insensitive) — the incoming owner message contains ANY of:
  presentation · deck · slide · slides · slide deck · pitch deck · webinar deck ·
  powerpoint · power point · ppt · .pptx · keynote · carousel · one-pager · talk track ·
  "make me a deck/ppt" · "build a deck" · "put together slides" · "some slides" ·
  "a talk/webinar with slides" · "slides for" · presentación · presentation deck

  (Tightened: the bare words "present" and "pitch" no longer trigger — a Marketing ask like
  "pitch our new offer" or "present the Q3 numbers" is NOT a presentation build. Route only on
  presentation/deck/slide-specific forms above, including "pitch deck" and "presentation deck".)

WHEN TRIGGERED your FIRST and ONLY action is EXACTLY these two steps, in order — nothing before them:

  ‼ Your VERY FIRST tool call is the STEP 1 route helper below — literally the first thing you do.
  Do NOT read any file, do NOT run sessions_list, do NOT "check" or "verify the department
  exists", do NOT deliberate, do NOT message another session. Route first. Then ack. Then stop.
  Any tool call before the route helper is a reflex violation.

  STEP 1 — Route the task NOW, before any other output, by running the SIGNED route helper.
  Do NOT hand-craft a bare curl. The Command Center ships FAIL-CLOSED: an unauthenticated curl
  to the ingest endpoint is rejected (503/401). The helper resolves this box's ingest
  credentials at RUNTIME and signs BOTH required auth layers (Bearer + HMAC webhook signature)
  for you. Run it EXACTLY like this, in an exec / bash tool call:

      bash @@ROUTE_HELPER_PATH@@ "<owner request, <=120 chars>" "<owner message, verbatim>"

  ⚠ PORT / ENDPOINT (handled inside the helper): the Command Center on THIS box listens on
  PORT 4000 at IPv4 127.0.0.1 — NOT 3000, NOT 8080, NOT any remembered default. The helper
  already targets http://127.0.0.1:4000/api/tasks/ingest. Do NOT substitute a port and do NOT
  fire your own bare curl.

      SUCCESS = the helper prints an ingest response with {"ok":true,"task_id":"…",
      "workspace_id":"presentations"} and exits 0.

  STEP 2 — Send ONE short acknowledgement to the owner, e.g.:
      "On it — routing this to your Presentations department now. The Brainstorming Buddy will pick it up and start the interview."

  Then STOP. Your turn is over. The Presentations department owns everything after this.

ESCALATION FALLBACK — if the helper FAILS (prints an ESCALATE_TO_OPERATOR line / exits non-zero
after its retries), you do NOT fall back to doing intake yourself, you do NOT retry forever, and
you do NOT ask the owner intake questions. Send ONE message telling the owner you are escalating
to the operator to fix routing, e.g.:
      "I hit a snag routing this to your Presentations department — I'm escalating it to the operator to get it sorted. I won't start the deck myself."
Then STOP.

WORKSPACE-MISMATCH — if the helper succeeds but WARNS that the task landed on a workspace other
than `presentations` (e.g. the CEO board), treat it like the escalation case: tell the owner you
are escalating to the operator (the Presentations department may not be set up on this box). Do
NOT silently proceed and do NOT self-intake.

HARD BANS while this reflex is active — EACH is a routing VIOLATION, no exceptions:
  ✗ Asking the owner ANY intake question (topic, title, audience, goal, existing content, length…)
  ✗ Reading, quoting, or "checking" department SOPs / IDENTITY / SOUL / BUILDER-PROMPT
  ✗ Writing intake.json, slides_copy.md, slides.json, or ANY working file
  ✗ Calling build_deck.py or presentation-canonical-entry.sh
  ✗ Hand-crafting your own unauthenticated curl to the ingest endpoint (it is rejected — use the helper)
  ✗ Spawning a sub-agent to do any of the above (spawning to execute = the same violation)
  ✗ Reading ANY file, running sessions_list, or verifying the department BEFORE the route helper fires
  ✗ Asking the OWNER anything, deliberating, or stalling because you "weren't sure" — you route first

PRE-EMIT SELF-CHECK — before you send text, ask: "Am I about to ask a question or describe the deck?"
  → If YES, you have ALREADY broken the reflex. Discard that draft. Do STEP 1 (the route helper) FIRST.

WHY (do not re-litigate): the Brainstorming Buddy (ROLE-17) — NOT the CEO — runs intake, one
question at a time, and captures the six mandatory fields REPRESENTATION_MIX, AUDIENCE_COMPOSITION,
GROUNDED_CONTENT, VISUAL_MIX, DARK_OK, HOOK_SEED. If the CEO improvises intake, those fields are
lost and the build fails the representation gate. The CEO's entire job for a presentation request
is three words: route, ack, stop.
<!-- END PRESENTATION_ROUTING_REFLEX_V2 -->
PRES_REFLEX_V2
    PRES_REFLEX_RENDERED="$(mktemp)"; _APPLY_TMPFILES+=("$PRES_REFLEX_RENDERED")
    RP_HELPER="$PRES_REFLEX_HELPER_PATH" python3 -c 'import os,sys; sys.stdout.write(open(sys.argv[1]).read().replace("@@ROUTE_HELPER_PATH@@", os.environ["RP_HELPER"]))' "$PRES_REFLEX_TMPL" > "$PRES_REFLEX_RENDERED"
    ORIGINAL_REFLEX_CONTENT="$(cat "$AGENTS_FILE_EARLY")"
    { cat "$PRES_REFLEX_RENDERED"; printf '\n'; printf '%s' "$ORIGINAL_REFLEX_CONTENT"; } > "$AGENTS_FILE_EARLY"
    echo "[apply-fleet-standards] PRESENTATION_ROUTING_REFLEX_V2 stamped at absolute top of $AGENTS_FILE_EARLY"
  fi
fi

# ─── 4b-SKILL-REFLEX. Inject SKILL_INTENT_ROUTING_REFLEX_V1 (Layer C) ──────────
# Departments-That-Use-Skills PRD §4 Layer C / §7.2. A compact, NORMAL-strength
# intent-cluster→department catalog (generated from skill-department-map.json) that
# teaches the CEO: when an owner message matches an intent phrase, the FIRST action
# is to route to the OWNING department via the SIGNED mc-route helper + ack — the
# specialist there reaches for the owning skill (the client never names it). Sits
# ALONGSIDE the strict PRESENTATION_ROUTING_REFLEX_V2 (which stays REFLEX 0 for its
# high-stakes intake). Marker-guarded + BYTE-IDEMPOTENT: strip-then-insert right
# AFTER the presentations reflex END marker (a position-stable top anchor), or at
# the top when that reflex is absent — decoupled from the EOF appenders so re-runs
# are byte-for-byte no-ops. Skipped on a PA-only box (no departments to route to).
# The intent→department table below is kept in lockstep with the map by the
# MAP-CONSISTENCY dimension of qc-assert-repo-consistency.py (Layer-C coverage:
# every department that owns a client-facing skill MUST appear here).
SKILL_REFLEX_V1_MARKER="<!-- SKILL_INTENT_ROUTING_REFLEX_V1 -->"

if [ "$_REFLEX_BOXTYPE" = "PA" ]; then
  if grep -qF "$SKILL_REFLEX_V1_MARKER" "$AGENTS_FILE_EARLY" 2>/dev/null; then
    python3 - "$AGENTS_FILE_EARLY" <<'SKILLSTRIP_PY'
import re, sys
p = sys.argv[1]
c = open(p, encoding="utf-8", errors="replace").read()
c = re.sub(r"\n*<!-- SKILL_INTENT_ROUTING_REFLEX_V1 -->.*?<!-- END SKILL_INTENT_ROUTING_REFLEX_V1 -->[ \t]*\n*",
           "\n", c, flags=re.DOTALL)
open(p, "w", encoding="utf-8").write(c)
SKILLSTRIP_PY
    echo "[apply-fleet-standards] PA-only box — REMOVED SKILL_INTENT_ROUTING_REFLEX_V1 (no departments to route to)"
  else
    echo "[apply-fleet-standards] PA-only box — NOT stamping SKILL_INTENT_ROUTING_REFLEX_V1"
  fi
else
  SKILL_REFLEX_TMPL="$(mktemp)"; _APPLY_TMPFILES+=("$SKILL_REFLEX_TMPL")
  cat > "$SKILL_REFLEX_TMPL" <<'SKILL_REFLEX_V1'
<!-- SKILL_INTENT_ROUTING_REFLEX_V1 -->
## 🧭 SKILL-INTENT ROUTING — your departments natively operate skills

Your departments and their specialists **natively operate skills** — a client benefits from a skill even when
they have never heard of it and never name it. When an owner message matches an intent cluster below, your
FIRST action is to route the task to the OWNING department with the SIGNED helper, then send ONE short
acknowledgement. Do NOT self-intake, do NOT ask "which skill do you want?", and do NOT start the work
yourself — the owning department's specialist reaches for the skill (dept-scoped) after routing.

    bash @@MC_ROUTE_PATH@@ <department_slug> "<owner request, <=120 chars>" "<owner message, verbatim>"

**Trust engine (P1-04) — ALWAYS pass the originating chat id when the request came from a client.**
When the message you are routing came from a CLIENT (e.g. this Telegram chat), prefix the SIGNED helper
with the ORIGINATING chat id so the Command Center's report-back loop keeps the client informed
(assigned → in-progress + ETA → done + where-to-find-it) — a routed task must NEVER go silent:

    MC_ROUTE_REQUESTER_CHAT_ID="<originating client chat id>" MC_ROUTE_REQUESTER_CHANNEL="telegram" \
      bash @@MC_ROUTE_PATH@@ <department_slug> "<owner request, <=120 chars>" "<owner message, verbatim>"

Leave the chat id UNSET for operator/internal routes (those are never reported on). NEVER invent or
reuse another client's chat id — pass ONLY the real originating chat id of the message you are routing.

| When the owner says (plain-language intent) … | Route to department |
|---|---|
| "make me Facebook/Instagram ads", "ad creatives", "10 ad variations" | `paid-advertisement` |
| "make/produce a video", "plan/storyboard my video", "add captions/subtitles", "cut/trim/edit this clip", "a cinematic reel" | `video` |
| "run my social", "post my content this week", "a week of content end-to-end" | `social-media` |
| "build my funnel", "a landing page / opt-in", "build me a form or page in GHL" | `web-development` |
| "write my email/nurture sequence", "build my brand/avatar", "write my book/anthology", "make this sound human / less AI-sounding" | `marketing` |
| "match this brand style", "on-brand images", "a style card" | `graphics` |
| "write my product bio", "a sales page / upsell copy", "a master brain for my product" | `sales` |
| "build a workflow", "automate this", "an order-bump" | `crm` |
| "summarize this YouTube", "what does this video say", "pull the transcript" | `research` |
| "set up a booking bot", "a conversational qualifier / lead responder" | `communications` |
| "answer my customers automatically", "a live-chat / support bot" | `customer-support` |
| "a signature talk / keynote deck / 100-slide presentation" — handled by REFLEX 0 above (do not double-route) | `presentations` |
| "map/graph my workforce", "graph my company" | `openclaw-maintenance` |
| "produce a podcast episode", "turn this intake into a published episode", "run the podcast production engine", "generate this week's episode" | `podcast` |

Notes:
- Presentation/deck/slide requests are owned by REFLEX 0 (the strict presentation reflex) ABOVE — it fires first; do not double-route.
- Dept-scoped: the dispatched specialist is handed ONLY its department's skills (the Command Center ContextPack `matched_skills`). Rule-Zero paid-call approval (USD announce + budget cap) still applies.
- If the owner explicitly names a skill or types its slash command, that still works — this reflex is for plain-language intent the owner did NOT name.
- Binding (source of truth): `~/.openclaw/skills/23-ai-workforce-blueprint/skill-department-map.json`. Doctrine: `~/.openclaw/skills/universal-sops/native-skill-invocation.md`.
<!-- END SKILL_INTENT_ROUTING_REFLEX_V1 -->
SKILL_REFLEX_V1
  SKILL_REFLEX_RENDERED="$(mktemp)"; _APPLY_TMPFILES+=("$SKILL_REFLEX_RENDERED")
  RP_MC="$MC_ROUTE_HELPER_PATH" python3 -c 'import os,sys; sys.stdout.write(open(sys.argv[1]).read().replace("@@MC_ROUTE_PATH@@", os.environ["RP_MC"]))' "$SKILL_REFLEX_TMPL" > "$SKILL_REFLEX_RENDERED"
  # Byte-idempotent strip-then-insert: place the block right AFTER the presentations
  # reflex END marker (position-stable top anchor), else at the top of the file.
  AGENTS_SR="$AGENTS_FILE_EARLY" BLOCK_SR="$SKILL_REFLEX_RENDERED" python3 <<'SKILLINS_PY'
import os, re
p = os.environ["AGENTS_SR"]
block = open(os.environ["BLOCK_SR"], encoding="utf-8").read().rstrip("\n")
c = open(p, encoding="utf-8", errors="replace").read()
# strip any prior copy (+ hugging blank lines) so a re-run is byte-stable
c = re.sub(r"\n*<!-- SKILL_INTENT_ROUTING_REFLEX_V1 -->.*?<!-- END SKILL_INTENT_ROUTING_REFLEX_V1 -->[ \t]*\n*",
           "\n", c, flags=re.DOTALL)
marker = "<!-- END PRESENTATION_ROUTING_REFLEX_V2 -->"
i = c.find(marker)
if i != -1:
    head = c[:i + len(marker)]
    tail = c[i + len(marker):].lstrip("\n")
    new = head + "\n\n" + block + "\n\n" + tail
else:
    new = block + "\n\n" + c.lstrip("\n")
open(p, "w", encoding="utf-8").write(new)
SKILLINS_PY
  echo "[apply-fleet-standards] SKILL_INTENT_ROUTING_REFLEX_V1 stamped into $AGENTS_FILE_EARLY"
fi

if [ "$OC_ROOT" = "/data/.openclaw" ]; then
  chown "$OC_USER:$OC_USER" "$AGENTS_FILE_EARLY" 2>/dev/null || true
  [ -f "$PRES_REFLEX_HELPER_PATH" ] && chown "$OC_USER:$OC_USER" "$PRES_REFLEX_HELPER_PATH" 2>/dev/null || true
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

# ─── 5b. Inject PERSONA_REFLEX_V1 into workspace/AGENTS.md ──────────────────
# W5.5: persona-reflex standard — the agent MUST check persona assignment
# before responding to any task. Idempotent: guarded by <!-- PERSONA_REFLEX_V1 -->.
PERSONA_REFLEX_MARKER="<!-- PERSONA_REFLEX_V1 -->"

if grep -qF "$PERSONA_REFLEX_MARKER" "$AGENTS_FILE"; then
  echo "[apply-fleet-standards] PERSONA_REFLEX_V1 already present in $AGENTS_FILE — no-op"
else
  cat >> "$AGENTS_FILE" <<'PREOF'

<!-- PERSONA_REFLEX_V1 -->
## Persona Reflex (stamped by apply-fleet-standards.sh — do NOT edit manually)

> Marker: `PERSONA_REFLEX_V1`. Idempotent — re-stamped on every install/update.

Every department specialist MUST check persona assignment before producing any deliverable:

1. **Persona check first.** Before drafting any response or output, retrieve the assigned coaching persona for this task from `persona-categories.json`. If no persona is pinned for this department, apply the default department persona or escalate to the CEO.
2. **Persona reflex is not optional.** A department agent that answers without persona-matching has violated the persona-reflex rule. Route back to intake if assignment is unclear.
3. **Persona-matching**: the selected persona's tone, framework, and vocabulary must be detectable in the output — not just cited. If the persona requires a contrarian take, the output must be contrarian. If it requires structured frameworks, the output must use them.
4. **Anti-staleness.** Stale sticky picks (persona held for more than `ANTI_STALENESS_THRESHOLD` dispatches without recheck) must be busted on the next dispatch. The persona selector handles this automatically; agents must not hard-code persona slugs in SOPs.

PREOF
  echo "[apply-fleet-standards] PERSONA_REFLEX_V1 injected into $AGENTS_FILE"
fi

if [ "$OC_ROOT" = "/data/.openclaw" ]; then
  chown "$OC_USER:$OC_USER" "$AGENTS_FILE" 2>/dev/null || true
fi

# ─── 5c. Inject FULL_CONTEXT_HANDOFF_V1 into workspace/AGENTS.md ─────────────
# W6: full-context handoff standard — when routing a task or handing off to a
# sub-agent the FULL context (not a pointer) must land in the handoff payload.
# Idempotent: guarded by <!-- FULL_CONTEXT_HANDOFF_V1 -->.
FULL_CONTEXT_HANDOFF_MARKER="<!-- FULL_CONTEXT_HANDOFF_V1 -->"

if grep -qF "$FULL_CONTEXT_HANDOFF_MARKER" "$AGENTS_FILE"; then
  echo "[apply-fleet-standards] FULL_CONTEXT_HANDOFF_V1 already present in $AGENTS_FILE — no-op"
else
  cat >> "$AGENTS_FILE" <<'FCHEOF'

<!-- FULL_CONTEXT_HANDOFF_V1 -->
## Full Context Handoff (stamped by apply-fleet-standards.sh — do NOT edit manually)

> Marker: `FULL_CONTEXT_HANDOFF_V1`. Idempotent — re-stamped on every install/update.

When handing a task to any department, sub-agent, or specialist, you MUST pass the FULL context:

1. **Full-context, not a pointer reference.** Do not say "see the file" or "refer to doc X." Embed the complete task description, relevant background, constraints, and expected output format directly in the handoff payload. A sub-agent that must forage for context costs 20-50x in tokens.
2. **Where the documentation lives.** Workspace files (AGENTS.md, TOOLS.md, MEMORY.md, SOUL.md) are injected by the gateway from `$WORKSPACE_DIR`. Skills live at `$SKILLS_DIR/NN-<skill-name>/`. When you reference documentation in a handoff, include the full absolute path — never a relative path or a bare filename.
3. **Pointer references for read-access only.** File paths in a handoff are read-access pointers. The receiving agent reads the file; it does not search for it. Always confirm the path exists before embedding it.
4. **Session handoff.** When handing off between sessions, write the current task state, open threads, and next actions to `$WORKSPACE_DIR/MEMORY.md` before the session closes. The receiving agent reads MEMORY.md at session start.

FCHEOF
  echo "[apply-fleet-standards] FULL_CONTEXT_HANDOFF_V1 injected into $AGENTS_FILE"
fi

if [ "$OC_ROOT" = "/data/.openclaw" ]; then
  chown "$OC_USER:$OC_USER" "$AGENTS_FILE" 2>/dev/null || true
fi

# ─── 5d. Inject OWNER_REPORTING_V1 into workspace/AGENTS.md ──────────────────
# W6: owner reporting standard — how and when to report back to the owner.
# Idempotent: guarded by <!-- OWNER_REPORTING_V1 -->.
OWNER_REPORTING_MARKER="<!-- OWNER_REPORTING_V1 -->"

if grep -qF "$OWNER_REPORTING_MARKER" "$AGENTS_FILE"; then
  echo "[apply-fleet-standards] OWNER_REPORTING_V1 already present in $AGENTS_FILE — no-op"
else
  cat >> "$AGENTS_FILE" <<'OREOF'

<!-- OWNER_REPORTING_V1 -->
## Owner Reporting Rules (stamped by apply-fleet-standards.sh — do NOT edit manually)

> Marker: `OWNER_REPORTING_V1`. Idempotent — re-stamped on every install/update.

All agents report back to the owner according to these rules:

1. **Reporting to the owner is mandatory.** Every task that reaches a department MUST report back to the owner with: status (DONE / RUNNING / BLOCKED), a one-line summary of what was completed, and the location of any deliverable (absolute path or URL). Silent completions are a violation.
2. **Report by Telegram first.** Owner Telegram is the primary reporting channel. If Telegram is unavailable, write the status to `$WORKSPACE_DIR/MEMORY.md` and escalate via Rescue Rangers.
3. **Reports back to the owner use plain language.** No acronyms, no jargon, no internal codes. The owner is a business leader, not a developer.
4. **Blocked tasks escalate immediately.** Do not hold a blocked task for more than 2 hours without escalating to the owner. Include: what is blocked, what was tried, and what the owner needs to do to unblock.
5. **Never over-report.** Status updates fire at task completion, at BLOCKED state, and at owner-configured check-in intervals. Intermediate progress pings are only sent if the task will take longer than 30 minutes.

OREOF
  echo "[apply-fleet-standards] OWNER_REPORTING_V1 injected into $AGENTS_FILE"
fi

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
