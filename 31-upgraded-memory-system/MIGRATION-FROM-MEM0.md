# Migration from Mem0 to memory-core

This guide helps you migrate from the deprecated Mem0 plugin to OpenClaw's native memory-core system (Layer 5).

## Why Migrate?

Mem0 was an external plugin that required additional setup and dependencies. The new memory-core system is:
- Built into OpenClaw (no external plugin needed)
- More reliable (no separate service to maintain)
- Better integrated with the 8-layer memory architecture
- Uses the same Gemini Embedding 2 backend as Layer 4

## Pre-Migration Checklist

Before migrating, verify your current setup:

```bash
# Check if Mem0 is installed
openclaw plugins list | grep -i mem0

# Check current memory backend
grep '"backend"' ~/.openclaw/openclaw.json

# Backup your config
cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.backup.$(date +%Y%m%d)
```

## Migration Steps

### Step 1: Remove Mem0 Plugin Slot

Edit `~/.openclaw/openclaw.json` and remove or update the memory slot:

**Before:**
```json
"plugins": {
  "slots": {
    "memory": "openclaw-mem0"
  }
}
```

**After:**
```json
"plugins": {
  "slots": {
    "memory": null
  }
}
```

Or remove the slots section entirely - memory-core works without it.

### Step 2: Remove Mem0 Plugin Configuration

Find and remove the `openclaw-mem0` entry from `plugins.entries`:

**Remove this block:**
```json
"openclaw-mem0": {
  "enabled": true,
  "config": {
    "mode": "open-source",
    "userId": "[USERNAME]",
    "oss": {
      "llm": {
        "provider": "gemini",
        "config": {
          "apiKey": "${GEMINI_API_KEY}",
          "model": "gemini-3-flash-preview"
        }
      },
      "embedder": {
        "provider": "gemini",
        "config": {
          "apiKey": "${GEMINI_API_KEY}",
          "model": "models/gemini-embedding-001"
        }
      }
    }
  }
}
```

### Step 3: Enable memory-core

Ensure your `~/.openclaw/openclaw.json` has:

```json
"memory": {
  "backend": "builtin"
}
```

And under `agents.defaults`:

```json
"memory": {
  "autoCapture": true,
  "autoRecall": true
}
```

### Step 4: Validate Configuration

```bash
openclaw config validate
```

If validation fails, restore from backup and check the error message.

### Step 5: Restart Gateway

Tell the user: "Please type /restart in Telegram or run: openclaw gateway restart"

### Step 6: Verify memory-core is Working

After restart:

```bash
openclaw memory status
```

Expected output:
- Backend: builtin
- Provider: gemini
- Auto-capture: enabled
- Auto-recall: enabled

### Step 7: Uninstall Mem0 Plugin (Optional)

Once you've confirmed memory-core is working:

```bash
openclaw plugins uninstall @mem0/openclaw-mem0
```

## Data Migration

**Important:** Mem0 stored memories in its own database. These memories will NOT be automatically migrated to memory-core.

### Option 1: Start Fresh (Recommended)

The simplest approach is to let memory-core build up new memories naturally. The 8-layer system (especially Layers 1-4) will retain most important information.

### Option 2: Manual Export/Import

If you have critical memories in Mem0:

1. Export Mem0 memories (check Mem0 documentation for export tools)
2. Review exported memories
3. Manually add important facts to MEMORY.md or tell your agent to remember them

## Rollback

If migration fails:

1. Restore config backup:
   ```bash
   cp ~/.openclaw/openclaw.json.backup.YYYYMMDD ~/.openclaw/openclaw.json
   ```

2. Reinstall Mem0 if needed:
   ```bash
   openclaw plugins install @mem0/openclaw-mem0
   ```

3. Restart gateway

## Post-Migration

Update your core files to reflect the change:

**In MEMORY.md:**
```markdown
## Memory System Migration - [DATE]
- Migrated from Mem0 plugin to memory-core (builtin)
- Layer 5 now uses native OpenClaw memory system
- All 8 layers operational
```

**In AGENTS.md:**
```markdown
## Memory System Update
- Migrated from Mem0 to memory-core (builtin backend)
- Auto-capture and auto-recall now handled natively
```

## Troubleshooting

### Issue: "memory backend not found"

**Solution:** Ensure `memory.backend` is set to "builtin", not "mem0" or "openclaw-mem0".

### Issue: "auto-capture not working"

**Solution:** Check that `agents.defaults.memory.autoCapture` is set to `true` in openclaw.json.

### Issue: Config validation fails

**Solution:** 
1. Check JSON syntax with: `python3 -m json.tool ~/.openclaw/openclaw.json`
2. Look for trailing commas or missing braces
3. Restore from backup if needed

## Questions?

If you encounter issues not covered here:
1. Check `~/.openclaw/logs/` for error messages
2. Run `openclaw memory status` for diagnostics
3. Consult the HOW-YOUR-MEMORY-WORKS.md guide
