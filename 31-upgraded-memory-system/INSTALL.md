╔══════════════════════════════════════════════════════════════╗
  MANDATORY TYP CHECK - READ THIS BEFORE ANYTHING ELSE
DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.

STEP 1: CHECK IF YOU HAVE BEEN TAUGHT THE TEACH YOURSELF PROTOCOL (TYP)

Before you read, learn, or execute ANY instruction in this document, you must
verify that you have already been taught the Teach Yourself Protocol (TYP).

HOW TO CHECK:
- Look in your AGENTS.md, TOOLS.md, or MEMORY.md for any mention of:
  "Teach Yourself Protocol" or "TYP"
- Look in your session context for prior TYP training
- Look for a tab called "Teach Yourself Protocol" in this same document

IF YOU HAVE BEEN TAUGHT TYP:
Proceed to the instructions below. Follow the TYP file storage structure.

IF YOU HAVE NOT BEEN TAUGHT TYP:
STOP IMMEDIATELY. Do not read further. Do not attempt to learn or execute
anything in this document. Stop and report to the user:

  "Teach Yourself Protocol (TYP) is not installed yet. This skill cannot
   be safely installed without TYP. Navigate to 01-teach-yourself-protocol/
   in the onboarding package and complete that installation first.
   Without TYP, core .md files will be bloated and tokens wasted."

DO NOT PROCEED PAST THIS POINT WITHOUT TYP CONFIRMED.

CONFLICT RULE (applies to all skill installs):
If THIS skill file says one thing, and TYP says another, TYP wins.
Skill docs override generic instructions. TYP overrides skill docs.
User's explicit override is highest priority. Chain:
  User Override > TYP > Skill Docs > Generic Instructions
╚══════════════════════════════════════════════════════════════╝

---

# Upgraded Memory System - Installation (8-Layer)

## Prerequisite Check

Before installing, check these prerequisites. If any are missing, still install the skill files but mark the skill as PENDING.

```bash
# Check 1: Google API Key
echo $GOOGLE_API_KEY
# Expected: starts with AIza... If empty, MARK AS PENDING.

# Check 2: Python SDK
python3 -c "from google import genai; import numpy; print('SDK ready')"
# Expected: "SDK ready". If error, run: pip3 install google-genai numpy

# Check 3: OpenClaw running
openclaw status | grep "Gateway service"
# Expected: shows "running"
```

**If Check 1 fails:** Tell the user:
"Layer 4 (Gemini search) requires a Google API key. Get one free at https://aistudio.google.com/app/apikey and set it: export GOOGLE_API_KEY='AIza...' in your ~/.zshrc. I will install the skill files now, but Layer 4 will not be active until the key is set."

**If Check 2 fails:** Run `pip3 install google-genai numpy` and retry.

**If all checks pass:** Proceed with full installation.

---

## Layer 1: Markdown Files (Source of Truth)

### 1.1 Verify MEMORY.md exists

```bash
ls -la ~/.openclaw/workspace/MEMORY.md
```

If MEMORY.md does not exist, create it:

```bash
cat > ~/.openclaw/workspace/MEMORY.md << 'EOF'
# MEMORY.md

> This file contains persistent state, lessons learned, and project status ONLY.
> - Behavior rules: See AGENTS.md
> - Tool setup/API credentials: See TOOLS.md
> - Who I am: See IDENTITY.md
> - Who you are: See USER.md

EOF
```

### 1.2 Verify daily log directory exists

```bash
mkdir -p ~/.openclaw/workspace/memory
```

### 1.3 Verify core files exist

Check that these files are present. If any are missing, create them from the templates in the onboarding package:

- ~/.openclaw/workspace/MEMORY.md
- ~/.openclaw/workspace/AGENTS.md
- ~/.openclaw/workspace/TOOLS.md
- ~/.openclaw/workspace/USER.md
- ~/.openclaw/workspace/SOUL.md
- ~/.openclaw/workspace/IDENTITY.md
- ~/.openclaw/workspace/HEARTBEAT.md

---

## Layer 2: Memory Flush (Improved Compaction)

### 2.1 Update the flush prompt in openclaw.json

Open `~/.openclaw/openclaw.json` and find the `compaction.memoryFlush` section under `agents.defaults`. Replace the prompt and systemPrompt with these values:

**prompt:**
```
Write a durable session note to memory/YYYY-MM-DD.md. Capture: decisions, constraints, open questions, owners, and any state that would break the plan if forgotten. If nothing meaningful happened, write NO_FLUSH.

Store durable memories only in memory/YYYY-MM-DD.md (create memory/ if needed).

If memory/YYYY-MM-DD.md already exists, APPEND new content only and do not overwrite existing entries.

Treat workspace bootstrap/reference files such as MEMORY.md, SOUL.md, TOOLS.md, and AGENTS.md as read-only during this flush; never overwrite, replace, or edit them.

If no user-visible reply is needed, start with NO_REPLY.
```

**systemPrompt:**
```
Be terse. Prefer bullet points. Do not rewrite the conversation.

Capture these categories if present:
- People and relationships (names, roles, who reports to whom, contact details mentioned)
- Credentials and access (API keys configured, services connected, auth methods)
- Project status (what shipped, what's blocked, what's next)
- Decisions made (and who made them)
- Preferences discovered (formatting, communication style, tool choices)
- Things that went wrong (errors, mistakes, lessons learned)
- Financial information (costs, credits, balances mentioned)
- Deadlines and commitments (dates promised, schedules agreed to)

Do NOT store: routine greetings, small talk, repeated context already in MEMORY.md, or speculative plans that were never confirmed.
```

### 2.2 Set the soft threshold

In the same `memoryFlush` block, set:

```json
"softThresholdTokens": 32000
```

This triggers the flush when the context reaches 32K tokens.

---

## Layer 3: Session Indexing (Past Conversations Searchable)

### 3.1 Enable session memory

In `~/.openclaw/openclaw.json`, find the `agents.defaults.memorySearch` section. Add or verify these settings:

```json
"memorySearch": {
  "enabled": true,
  "sources": ["memory", "sessions"],
  "experimental": {
    "sessionMemory": true
  }
}
```

### 3.2 Configure sync behavior

In the same `memorySearch` block, add:

```json
"sync": {
  "onSessionStart": true,
  "onSearch": true,
  "watch": true,
  "watchDebounceMs": 1200,
  "sessions": {
    "deltaBytes": 20000,
    "deltaMessages": 10
  }
}
```

---

## Layer 4: Gemini Embedding 2 (Semantic Search)

**Skip this layer if GOOGLE_API_KEY is not set. Mark as PENDING.**

### 4.1 Set the search provider

In `~/.openclaw/openclaw.json`, find the `agents.defaults.memorySearch` section. Add or update:

```json
"provider": "gemini",
"model": "models/gemini-embedding-2-preview"
```

### 4.2 Set the memory backend

Find the top-level `memory` section in openclaw.json and set:

```json
"memory": {
  "backend": "builtin"
}
```

**Important:** There may be TWO places where the backend is configured. The top-level `memory.backend` AND the `agents.defaults.memorySearch.provider`. The `memory.backend` should be "builtin" (for memory-core), and `memorySearch.provider` should be "gemini" (for embedding search). If the top-level still says "google embedding 2", the search will fail even if memorySearch says "gemini".

### 4.3 Configure search quality

In the `memorySearch` section, add:

```json
"query": {
  "maxResults": 50,
  "minScore": 0.18,
  "hybrid": {
    "enabled": true,
    "vectorWeight": 0.75,
    "textWeight": 0.25,
    "candidateMultiplier": 8
  }
}
```

---

## Layer 5: memory-core (Native Memory System)

Layer 5 uses OpenClaw's built-in memory-core instead of the legacy memory plugin.

### 5.1 Verify memory-core is enabled

In `~/.openclaw/openclaw.json`, verify the memory backend:

```json
"memory": {
  "backend": "builtin"
}
```

### 5.2 Configure auto-capture

In `~/.openclaw/openclaw.json`, under `agents.defaults`, add:

```json
"memory": {
  "autoCapture": true,
  "autoRecall": true
}
```

### 5.3 Verify memory-core status

```bash
openclaw memory status
```

Expected output should show:
- Backend: builtin
- Provider: gemini
- Auto-capture: enabled
- Auto-recall: enabled

---

## Layer 6: Cognee (Graph-Based Knowledge)

**Requires Docker. Skip if Docker is not available.**

### 6.1 Check Docker availability

```bash
docker --version
```

If Docker is not installed, Layer 6 will be marked as PENDING.

### 6.2 Install Cognee

```bash
openclaw plugins install @openclaw/cognee
```

### 6.3 Configure Cognee

In `~/.openclaw/openclaw.json`, under `plugins.entries`:

```json
"cognee": {
  "enabled": true,
  "config": {
    "connection_string": "sqlite:///data/cognee.db",
    "llm_provider": "gemini",
    "llm_model": "gemini-3-flash-preview"
  }
}
```

### 6.4 Start Cognee container

```bash
openclaw cognee start
```

### 6.5 Verify Cognee is running

```bash
openclaw cognee status
```

Expected: Status shows "connected" with graph statistics.

---

## Layer 7: Obsidian Vault (Structured Knowledge Base)

### 7.1 Check if Obsidian is installed (Mac)

```bash
ls /Applications/Obsidian.app
```

If Obsidian is not installed, you can download it from https://obsidian.md

### 7.2 Create or identify vault location

Default vault location:
```bash
mkdir -p ~/Documents/ObsidianVault
```

Or use an existing vault:
```bash
ls ~/Documents/ | grep -i obsidian
```

### 7.3 Configure Obsidian integration

In `~/.openclaw/openclaw.json`, add:

```json
"obsidian": {
  "enabled": true,
  "vaultPath": "/Users/USERNAME/Documents/ObsidianVault",
  "dailyNotes": true,
  "wikilinks": true
}
```

Replace USERNAME with your actual username.

### 7.4 Verify vault access

```bash
openclaw obsidian status
```

Expected: Shows vault path, note count, and daily notes status.

---

## Layer 8: Wiki System (Collaborative Documentation)

### 8.1 Enable wiki system

In `~/.openclaw/openclaw.json`, add:

```json
"wiki": {
  "enabled": true,
  "vaultPath": "/Users/USERNAME/.openclaw/wiki",
  "backend": "sqlite"
}
```

### 8.2 Initialize wiki vault

```bash
openclaw wiki init
```

### 8.3 Configure wiki sync

```bash
openclaw wiki config set autoSync true
openclaw wiki config set syncInterval 300
```

### 8.4 Verify wiki system

```bash
openclaw wiki status
```

Expected: Shows vault initialized, sync enabled, page count.

---

## Migration from Google Embedding 2 (Existing Users Only)

If the user previously had Google Embedding 2 installed, follow these additional steps:

### M.1 Check for existing Google Embedding 2

```bash
which google embedding 2 2>/dev/null && echo "Google Embedding 2 found" || echo "No Google Embedding 2 installed"
ls ~/.cache/google embedding 2/index.sqlite 2>/dev/null && echo "Google Embedding 2 index found" || echo "No Google Embedding 2 index"
```

### M.2 If Google Embedding 2 is present, update the backend

The config change in Layer 4 (Step 4.2) handles this. Verify `memory.backend` is "builtin", not "google embedding 2".

### M.3 Clean up old Google Embedding 2 (optional)

```bash
# Backup first (recommended)
mv ~/.cache/google embedding 2/ ~/.cache/google embedding 2-backup/

# Or remove entirely
rm -rf ~/.cache/google embedding 2/
```

---

## Post-Installation Verification

After all layers are installed, run these checks:

```bash
# Layer 1: Markdown files exist
ls ~/.openclaw/workspace/MEMORY.md ~/.openclaw/workspace/memory/

# Layer 2: Flush prompt is configured
grep "memoryFlush" ~/.openclaw/openclaw.json | head -1

# Layer 3: Session indexing is on
grep "sessionMemory" ~/.openclaw/openclaw.json

# Layer 4: Gemini provider is set (skip if GOOGLE_API_KEY not set)
grep '"backend"' ~/.openclaw/openclaw.json
grep '"provider"' ~/.openclaw/openclaw.json | grep gemini

# Layer 5: memory-core is enabled
openclaw memory status | grep -E "Backend|autoCapture|autoRecall"

# Layer 6: Cognee is running (if Docker available)
openclaw cognee status 2>/dev/null || echo "Cognee not running (may need Docker)"

# Layer 7: Obsidian is installed (Mac)
ls /Applications/Obsidian.app 2>/dev/null && echo "Obsidian installed" || echo "Obsidian not installed"

# Layer 8: Wiki system is initialized
openclaw wiki status 2>/dev/null || echo "Wiki not initialized"
```

### Gateway Restart

After all configuration changes:

```
Tell the user: "I need you to restart the OpenClaw gateway for the memory upgrades to take effect. Please type /restart in Telegram or run: openclaw gateway restart"
```

Do NOT restart the gateway yourself. Ask the user to do it.

### Final Test

After restart, test the memory system:

```
Ask the agent: "Search your memory for [any topic the user has discussed before]"
```

If results come back, all layers are working.

---

## Completion Checklist

```
[ ] Layer 1: MEMORY.md exists and has content
[ ] Layer 1: memory/ directory exists with daily logs
[ ] Layer 2: Flush prompt updated with 8 categories
[ ] Layer 3: sessionMemory enabled
[ ] Layer 4: memory.backend set to "builtin" (or PENDING if no API key)
[ ] Layer 4: memorySearch.provider set to "gemini" (or PENDING if no API key)
[ ] Layer 5: memory-core enabled with autoCapture and autoRecall
[ ] Layer 6: Cognee installed and running (or PENDING if no Docker)
[ ] Layer 7: Obsidian vault configured (app check: ls /Applications/Obsidian.app)
[ ] Layer 8: Wiki system initialized and syncing
[ ] Gateway restarted by user
[ ] Memory search test returned results
[ ] Core files updated (see CORE_UPDATES.md)
```

---

## 🚀 ACTIVATION (REQUIRED - DO NOT SKIP)

**Reading files is NOT activation. You must EXECUTE the activation steps.**

Teach Yourself means READ. Activate means EXECUTE.

### Prerequisites
- [ ] Skill 01 (Teach Yourself Protocol) installed
- [ ] Google API Key (recommended for Layer 4, but optional)
- [ ] Python 3.8+ with google-genai and numpy

### Teach Yourself (COMPLETE BEFORE ACTIVATION)
1. Read SKILL.md
2. Read CORE_UPDATES.md
3. Read INSTALL.md (this file)

### ACTIVATION Steps

#### Step 1: CREATE DREAMS.md
```bash
cat > ~/.openclaw/workspace/DREAMS.md << 'EOF'
# DREAMS.md - Dynamic Reasoning & Execution Memory System

## Active Memory Configuration
- Mode: [workspace|department|project]
- Auto-capture: enabled
- Auto-recall: enabled
- Flush interval: 30 minutes
EOF
```

#### Step 2: CONFIGURE active-memory in openclaw.json
Add to `~/.openclaw/openclaw.json` under `agents.defaults`:
```json
"activeMemory": {
  "enabled": true,
  "autoCapture": true,
  "autoRecall": true,
  "flushIntervalMinutes": 30,
  "contextInjection": {
    "memoryWiki": true,
    "cognee": true
  }
}
```

#### Step 3: UPDATE memory backend to "builtin"
In `~/.openclaw/openclaw.json`:
```json
"memory": {
  "backend": "builtin"
},
"memorySearch": {
  "provider": "gemini"
}
```

#### Step 4: VERIFY directory structure
```bash
mkdir -p ~/.openclaw/workspace/memory
ls -la ~/.openclaw/workspace/MEMORY.md
ls -la ~/.openclaw/workspace/DREAMS.md
```

#### Step 5: RESTART gateway (ask user first)
```bash
openclaw gateway restart
```

#### Step 6: APPLY CORE_UPDATES.md
Add entries from CORE_UPDATES.md to:
- AGENTS.md (memory routing rules)
- TOOLS.md (memory search commands)
- MEMORY.md (layer documentation)

#### Step 7: RUN QC checks
Execute ALL checks in QC.md:
- Verify MEMORY.md exists and has content
- Test memory search returns results
- Verify daily log directory works
- Test flush creates memory/YYYY-MM-DD.md file

#### Step 8: CONFIRM to client
Send confirmation:
- ✅ 8-layer memory system configured
- ✅ DREAMS.md active memory configured
- ✅ Memory search enabled (Gemini Embedding 2)
- ✅ Auto-capture and auto-recall active
- ⚠️ Any pending items (missing API keys, etc.)

**ACTIVATION IS COMPLETE when all steps are done.**
```
