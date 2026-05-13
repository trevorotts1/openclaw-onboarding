#!/bin/bash
# fix-active-memory-bug.sh — v9.6.6
#
# Recovery script for clients whose openclaw.json was written by a pre-v9.6.6
# install. Removes the bogus `plugins.entries.active-memory` block that the
# OpenClaw config validator rejects.
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
plugins = cfg.get("plugins", {})
entries = plugins.get("entries", {})

# 1. Remove the bogus active-memory block
if "active-memory" in entries:
    del entries["active-memory"]
    print("  ✓ Removed plugins.entries.active-memory (invalid block)")
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
