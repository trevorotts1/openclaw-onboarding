#!/usr/bin/env bash
# apply-tool-allowlist.sh -- Idempotent fleet-wide tool-allowlist patch (U134).
# Applies the fleet-standard per-agent tool allowlist to the main agent
# on every skills update. Ships tool-policy changes as part of the update flow.

set -euo pipefail

if [ -f /data/.openclaw/openclaw.json ]; then
  OC_ROOT="/data/.openclaw"; OC_USER="node"
elif [ -f "$HOME/.openclaw/openclaw.json" ]; then
  OC_ROOT="$HOME/.openclaw"; OC_USER="$(whoami)"
else
  echo "[apply-tool-allowlist] not a provisioned box; exit 0" >&2; exit 0
fi

OC_CONFIG="$OC_ROOT/openclaw.json"
TIMESTAMP=$(date +%Y%m%d%H%M%S)
OC_BACKUP="$OC_CONFIG.bak-tool-allowlist-$TIMESTAMP"
echo "[apply-tool-allowlist] config: $OC_CONFIG"
cp "$OC_CONFIG" "$OC_BACKUP"
echo "[apply-tool-allowlist] backed up: $OC_BACKUP"

OC_VERSION=""
if command -v openclaw >/dev/null 2>&1; then
  _oc_raw="$(openclaw --version 2>&1 | tr -d '\r' | head -n1 || true)"
  OC_VERSION="$(printf '%s' "$_oc_raw" | grep -oE '20[0-9]{2}\.[0-9]+\.[0-9]+' | head -n1 || true)"
fi
OC_VERSION="${FLEET_OC_VERSION_OVERRIDE:-$OC_VERSION}"

FLEET_TOOL_ALLOWLIST_SKIP="${FLEET_TOOL_ALLOWLIST_SKIP:-}" python3 - "$OC_CONFIG" <<'PYEOF'
import json, os, sys
from pathlib import Path

cfg_path = Path(sys.argv[1])
cfg = json.loads(cfg_path.read_text())
if os.environ.get("FLEET_TOOL_ALLOWLIST_SKIP", "") == "1":
    sys.exit(0)

before_json = json.dumps(cfg, sort_keys=True, indent=2)

FLEET_TOOL_ALLOW = [
    "read", "web_fetch", "web_search",
    "message", "telegram", "slack", "discord",
    "sessions_send", "sessions_list", "sessions_history",
    "mc-route__route_task", "exec",
    "memory_search", "memory_get",
    "cron", "gateway", "nodes",
]

FLEET_TOOL_DENY = [
    "write", "edit", "apply_patch",
    "browser", "canvas", "image", "process",
    "ghl-community-mcp__*", "ghl-mcp__*",
]

FLEET_MCP_DENY = {
    "ghl-community-mcp": {"deny": ["*"]},
    "ghl-mcp": {"deny": ["*"]},
}

agents_list = cfg.get("agents", {}).get("list", []) or []
target_agent = None
for ag in agents_list:
    if not isinstance(ag, dict): continue
    if ag.get("default") is True: target_agent = ag; break
if target_agent is None:
    for ag in agents_list:
        if not isinstance(ag, dict): continue
        if ag.get("id") == "main": target_agent = ag; break
if target_agent is None:
    print("[apply-tool-allowlist] no default/main agent found", file=sys.stderr)
    sys.exit(0)

ROUTER_IDS = {"main","ceo","dept-ceo","master-orchestrator","dept-master-orchestrator","dept-executive-office"}
def _is_router(ag):
    if not isinstance(ag, dict): return False
    if ag.get("is_master") is True: return True
    if isinstance(ag.get("role"), str) and ag.get("role").strip().lower() == "router": return True
    return ag.get("id") in ROUTER_IDS
if not _is_router(target_agent):
    print("[apply-tool-allowlist] non-router agent -- skipping", file=sys.stderr)
    sys.exit(0)

def _consent_active():
    cands = [os.environ.get("CEO_CONSENT_FILE","")]
    cands.append("/data/.openclaw/state/ceo-consent.json")
    cands.append(os.path.join(os.path.expanduser("~"),".openclaw","state","ceo-consent.json"))
    for c in cands:
        if not c: continue
        try:
            r = json.load(open(c))
            if isinstance(r, dict) and r.get("granted") is True:
                return True
        except Exception:
            continue
    return False
if _consent_active():
    print("[apply-tool-allowlist] owner-consent active -- skipping", file=sys.stderr)
    sys.exit(0)

tools = target_agent.setdefault("tools", {})
if not isinstance(tools, dict): tools = {}; target_agent["tools"] = tools

current_allow = tools.get("allow", [])
if not isinstance(current_allow, list): current_allow = []
fleet_allow_set = set(FLEET_TOOL_ALLOW)
local_only_allow = [t for t in current_allow if t not in fleet_allow_set]
new_allow = sorted(set(FLEET_TOOL_ALLOW + local_only_allow), key=str)

current_deny = tools.get("deny", [])
if not isinstance(current_deny, list): current_deny = []
fleet_deny_set = set(FLEET_TOOL_DENY)
local_only_deny = [t for t in current_deny if t not in fleet_deny_set]
new_deny = sorted(set(FLEET_TOOL_DENY + local_only_deny), key=str)
tools["deny"] = new_deny
tools["allow"] = [t for t in new_allow if t not in new_deny]

by_provider = tools.setdefault("byProvider", {})
for prov, rule in FLEET_MCP_DENY.items():
    by_provider[prov] = rule

tools["allow"] = sorted(tools["allow"], key=str)
tools["deny"] = sorted(tools["deny"], key=str)

after_json = json.dumps(cfg, sort_keys=True, indent=2)
if before_json == after_json:
    print("[apply-tool-allowlist] already canonical -- no-op", file=sys.stderr)
else:
    cfg_path.write_text(json.dumps(cfg, sort_keys=True, indent=2) + "\n")
    print("[apply-tool-allowlist] config patched", file=sys.stderr)
PYEOF

_PYRC=$?
if [ "$_PYRC" -ne 0 ]; then
  echo "[apply-tool-allowlist] ERROR: Python step failed" >&2
  cp "$OC_BACKUP" "$OC_CONFIG"; exit 1
fi

if [ "$OC_ROOT" = "/data/.openclaw" ]; then
  chown "$OC_USER:$OC_USER" "$OC_CONFIG" 2>/dev/null || true
fi

if [ "${FLEET_TOOL_ALLOWLIST_SKIP_VALIDATE:-}" = "1" ]; then
  echo "[apply-tool-allowlist] validate SKIPPED (FLEET_TOOL_ALLOWLIST_SKIP_VALIDATE=1)"
elif command -v openclaw >/dev/null 2>&1; then
  if ! openclaw config validate 2>&1; then
    echo "[apply-tool-allowlist] validate FAILED -- rolling back" >&2
    cp "$OC_BACKUP" "$OC_CONFIG"
    [ "$OC_ROOT" = "/data/.openclaw" ] && chown "$OC_USER:$OC_USER" "$OC_CONFIG" 2>/dev/null || true
    exit 1
  fi
  echo "[apply-tool-allowlist] config validate: PASS"
else
  echo "[apply-tool-allowlist] openclaw CLI not available (test env -- expected)"
fi
echo "[apply-tool-allowlist] DONE"
