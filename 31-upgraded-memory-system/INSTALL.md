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

# Upgraded Memory System - Installation

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
ls -la ~/clawd/MEMORY.md
```

If MEMORY.md does not exist, create it:

```bash
cat > ~/clawd/MEMORY.md << 'EOF'
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
mkdir -p ~/clawd/memory
```

### 1.3 Verify core files exist

Check that these files are present. If any are missing, create them from the templates in the onboarding package:

- ~/clawd/MEMORY.md
- ~/clawd/AGENTS.md
- ~/clawd/TOOLS.md
- ~/clawd/USER.md
- ~/clawd/SOUL.md
- ~/clawd/IDENTITY.md
- ~/clawd/HEARTBEAT.md

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
  "backend": "gemini"
}
```

**Important:** There may be TWO places where the backend is configured. The top-level `memory.backend` AND the `agents.defaults.memorySearch.provider`. Both must say "gemini". If the top-level still says "qmd", the search will fail even if memorySearch says "gemini".

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

## Layer 5: Mem0 (Auto-Capture and Auto-Recall)

### 5.1 Install the Mem0 plugin

```bash
openclaw plugins install @mem0/openclaw-mem0
```

### 5.2 Set the memory slot

In `~/.openclaw/openclaw.json`, set:

```json
"plugins": {
  "slots": {
    "memory": "openclaw-mem0"
  }
}
```

### 5.3 Configure Mem0

In the plugins.entries section:

```json
"openclaw-mem0": {
  "enabled": true,
  "config": {
    "mode": "open-source",
    "userId": "[USERNAME]"
  }
}
```

Replace [USERNAME] with the user's Telegram username or preferred identifier.

### 5.4 Verify Mem0 is loaded

```bash
openclaw plugins list | grep -i "mem0"
```

Expected output should show Mem0 as "loaded" with autoRecall and autoCapture both true.

---

## Migration from QMD (Existing Users Only)

If the user previously had QMD installed, follow these additional steps:

### M.1 Check for existing QMD

```bash
which qmd 2>/dev/null && echo "QMD found" || echo "No QMD installed"
ls ~/.cache/qmd/index.sqlite 2>/dev/null && echo "QMD index found" || echo "No QMD index"
```

### M.2 If QMD is present, update the backend

The config change in Layer 4 (Step 4.2) handles this. Verify `memory.backend` is "gemini", not "qmd".

### M.3 Clean up old QMD (optional)

```bash
# Backup first (recommended)
mv ~/.cache/qmd/ ~/.cache/qmd-backup/

# Or remove entirely
rm -rf ~/.cache/qmd/
```

---

## Post-Installation Verification

After all layers are installed, run these checks:

```bash
# Layer 1: Markdown files exist
ls ~/clawd/MEMORY.md ~/clawd/memory/

# Layer 2: Flush prompt is configured
grep "memoryFlush" ~/.openclaw/openclaw.json | head -1

# Layer 3: Session indexing is on
grep "sessionMemory" ~/.openclaw/openclaw.json

# Layer 4: Gemini provider is set (skip if GOOGLE_API_KEY not set)
grep '"backend"' ~/.openclaw/openclaw.json
grep '"provider"' ~/.openclaw/openclaw.json | grep gemini

# Layer 5: Mem0 is loaded
openclaw plugins list | grep -i "mem0"
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
[ ] Layer 4: memory.backend set to "gemini" (or PENDING if no API key)
[ ] Layer 4: memorySearch.provider set to "gemini" (or PENDING if no API key)
[ ] Layer 5: Mem0 plugin installed and loaded
[ ] Layer 5: autoCapture and autoRecall both true
[ ] Gateway restarted by user
[ ] Memory search test returned results
[ ] Core files updated (see CORE_UPDATES.md)
```
