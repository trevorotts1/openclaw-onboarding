#!/bin/bash
# fix-active-memory-bug.sh — v9.6.6
#
# Recovery script for clients whose openclaw.json was written by a buggy install.
# REPAIRS the `plugins.entries.active-memory` block — nesting its option keys under
# `config` (it is a real Layer-8 plugin) — so the OpenClaw config validator accepts
# it. (Pre-v16.1.4 this script DELETED the block, dropping Layer-8 Active Memory;
# it now keeps Active Memory ENABLED and valid.)
#
# Symptom in client's terminal:
#   Config invalid
#   plugins.entries.active-memory: Unrecognized keys: "agents",
#     "allowedChatTypes", "queryMode", "promptStyle", "timeoutMs", "maxSummaryChars"
#   Restarting OpenClaw gateway…
#   Cannot resolve telegram target from openclaw.json
#
# After this script runs, restart the gateway:
#   openclaw gateway restart   (or just open a fresh Telegram chat with the bot)
#
# USAGE:
#   curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/scripts/fix-active-memory-bug.sh | bash
#
# OR run locally:
#   bash ~/Downloads/openclaw-master-files/scripts/fix-active-memory-bug.sh

set -u

# Platform detect
if [ -d "/data/.openclaw" ]; then
  OCJSON="/data/.openclaw/openclaw.json"
  BACKUP_DIR="/data/Downloads/openclaw-backups"
else
  OCJSON="$HOME/.openclaw/openclaw.json"
  BACKUP_DIR="$HOME/Downloads/openclaw-backups"
fi

if [ ! -f "$OCJSON" ]; then
  echo "ERROR: openclaw.json not found at $OCJSON"
  exit 1
fi

mkdir -p "$BACKUP_DIR"
TS=$(date +%Y-%m-%d-%H%M%S)
BACKUP="$BACKUP_DIR/openclaw.json-bugfix-${TS}.json"
cp "$OCJSON" "$BACKUP"
echo "Backed up: $BACKUP"

python3 - <<PYEOF
import json, sys

path = "$OCJSON"
with open(path) as f:
    cfg = json.load(f)

changed = False
plugins = cfg.setdefault("plugins", {})
entries = plugins.setdefault("entries", {})

# 1. Repair active-memory: nest any schema-invalid top-level option keys under
#    config (plugins.entries.<id> is additionalProperties:false -- only
#    enabled/hooks/subagent/llm/config). active-memory is a real Layer-8 plugin,
#    so KEEP it enabled -- never delete.
AM_ENTRY_TOP = ("enabled", "hooks", "subagent", "llm", "config")
am = entries.get("active-memory")
if isinstance(am, dict):
    am_cfg = am.get("config") if isinstance(am.get("config"), dict) else {}
    moved = [x for x in list(am) if x not in AM_ENTRY_TOP]
    for _k in moved:
        am_cfg.setdefault(_k, am.pop(_k))
    if moved:
        am["enabled"] = am.get("enabled", True)
        am["config"] = am_cfg
        entries["active-memory"] = am
        print("  ✓ Repaired plugins.entries.active-memory (nested %d option key(s) under config; Layer 8 preserved)" % len(moved))
        changed = True

# 2. Ensure memory-core is present + enabled (the REAL memory plugin)
mc = entries.setdefault("memory-core", {})
if not mc.get("enabled"):
    mc["enabled"] = True
    print("  ✓ Enabled plugins.entries.memory-core")
    changed = True

# 3. Ensure agents.defaults.memorySearch is set up
agents = cfg.setdefault("agents", {})
defaults = agents.setdefault("defaults", {})
ms = defaults.setdefault("memorySearch", {})
if not ms.get("enabled"):
    ms["enabled"] = True
    ms.setdefault("sources", ["memory"])
    ms.setdefault("provider", "gemini")
    ms.setdefault("fallback", "openai")
    print("  ✓ Configured agents.defaults.memorySearch")
    changed = True

# 4. plugins.slots.memory = memory-core
slots = plugins.setdefault("slots", {})
if slots.get("memory") != "memory-core":
    slots["memory"] = "memory-core"
    print("  ✓ Set plugins.slots.memory = memory-core")
    changed = True

if changed:
    cfg["plugins"] = plugins
    cfg["agents"] = agents
    with open(path, "w") as f:
        json.dump(cfg, f, indent=2)
    print()
    print("✓ openclaw.json repaired. Restart your gateway to apply:")
    print("  openclaw gateway restart")
    print("  (or send any message to your Telegram bot to trigger reload)")
else:
    print()
    print("Nothing to fix — config is already healthy.")
PYEOF
