#!/usr/bin/env bash
# apply-fleet-standards.sh — Idempotent enforcer for the OpenClaw fleet standard:
#   • Sub-agents fully permitted (spawn + exec + read/write across all agents)
#   • Telegram media limit 50 MB (inbound + outbound)
#
# Why a script and not `openclaw config set`:
#   Per-agent overrides in agents.list[] override global defaults. The schema
#   validator (2026.5.20+) rejects deep nested keys via CLI. The supported
#   pattern is direct JSON merge against openclaw.json, then validate. This
#   script ships the canonical block verified on Sheila Reynolds' Mac (2026.5.28).
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

# ─── 2. Deep-merge the canonical fleet block into openclaw.json ──────────────
python3 - "$OC_CONFIG" <<'PYEOF'
import json
import sys
from pathlib import Path

cfg_path = Path(sys.argv[1])
cfg = json.loads(cfg_path.read_text())
before_json = json.dumps(cfg, sort_keys=True, indent=2)

# CANONICAL FLEET STANDARD BLOCK
# Verified against:
#   - docs.openclaw.ai/tools/subagents (allowAgents wildcard, per-agent override)
#   - docs.openclaw.ai/gateway/security (exec.security, exec.ask, sandbox)
#   - docs.openclaw.ai/tools/multi-agent-sandbox-tools (agent-specific policy)
#   - Live test on OpenClaw 2026.5.28 (Sheila Reynolds' Mac mini, session logs)
#
# Key insight: per-agent settings override global defaults. So we must:
#   1. Set the global default to ["*"]
#   2. Iterate all agents and set their explicit allowAgents to ["*"] OR
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
        }
    },
    "channels": {
        "telegram": {
            "mediaMaxMb": 50
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
echo "[apply-fleet-standards] DONE"
echo "[apply-fleet-standards] Backup: $OC_BACKUP"
echo "[apply-fleet-standards] Current: $OC_CONFIG"
