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
  "backend": "builtin"
}
```

**Important:** There may be TWO places where the backend is configured. The top-level `memory.backend` AND the `agents.defaults.memorySearch.provider`. The top-level must say "builtin" and memorySearch.provider must say "gemini". If the top-level still says "qmd", the search will fall back to QMD instead of using Gemini Embedding 2.

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

The config change in Layer 4 (Step 4.2) handles this. Verify `memory.backend is "builtin", not "qmd".

### M.3 Clean up old QMD (optional)

```bash
# Backup first (recommended)
mv ~/.cache/qmd/ ~/.cache/qmd-backup/

# Or remove entirely
rm -rf ~/.cache/qmd/
```

---

## Post-Installation Verification

After all layers are configured, verify each one before asking for a restart.

### Config Validation (MANDATORY)

Before asking the user to restart, validate the config:

```bash
openclaw config validate
```

If it says "Config valid", proceed. If it says "Invalid input" or any error, DO NOT ask for a restart. Fix the config issue first.

### Layer-by-Layer Verification

Run these checks and report the results to the user in Telegram:

```bash
# Layer 1: Markdown files
echo "Layer 1:" && ls ~/clawd/MEMORY.md 2>/dev/null && echo "MEMORY.md OK" || echo "MEMORY.md MISSING"
ls ~/clawd/memory/ 2>/dev/null | wc -l | xargs -I{} echo "Daily logs: {} files"

# Layer 2: Flush prompt
echo "Layer 2:" && grep -c "memoryFlush" ~/.openclaw/openclaw.json | xargs -I{} echo "Flush config entries: {}"

# Layer 3: Session indexing
echo "Layer 3:" && grep "sessionMemory" ~/.openclaw/openclaw.json | xargs echo

# Layer 4: Gemini search
echo "Layer 4:" && grep '"backend"' ~/.openclaw/openclaw.json | head -1
grep '"provider"' ~/.openclaw/openclaw.json | grep gemini | head -1

# Layer 5: Mem0
echo "Layer 5:" && openclaw plugins list 2>/dev/null | grep -i "mem0" || echo "Mem0 not detected"
```

**Send the results to the user in Telegram** in plain language:

> Memory system verification:
> - Layer 1 (Markdown files): [OK/MISSING]
> - Layer 2 (Memory flush): [CONFIGURED/NOT SET]
> - Layer 3 (Session indexing): [ENABLED/DISABLED]
> - Layer 4 (Gemini search): [READY/PENDING - needs API key]
> - Layer 5 (Mem0): [LOADED/NOT LOADED]
>
> Config validation: [PASSED/FAILED]

### Gateway Restart

After verification passes, send this message to the user in Telegram:

> All 5 memory layers are configured. I need you to restart the gateway for the changes to take effect. Please type /restart when you are ready.

Do NOT restart the gateway yourself. Wait for the user to do it.

### Post-Restart: Knowledge Indexing

After the user restarts the gateway, trigger indexing of all knowledge files.

The Gemini Embedding 2 search engine needs to index the user's knowledge base. Search for and index ALL of these:

**Required folders to index (search by name, case-insensitive):**
- Any folder in ~/Downloads/ containing "openclaw" AND ("master" OR "onboarding") in the name
- All subfolders within those folders
- The workspace directory (~/clawd/ or wherever the agent workspace is)
- The memory/ directory

**File types to index:**
Gemini Embedding 2 supports multimodal inputs. Index ALL of these file types:
- `.md` (markdown)
- `.txt` (text)
- `.pdf` (documents)
- `.png`, `.jpg`, `.jpeg`, `.webp` (images)
- `.mp3`, `.wav`, `.m4a` (audio, if present)

**How to verify indexing is working:**

```bash
openclaw memory status 2>&1 | head -10
```

Expected output should show:
- Provider: gemini
- Model: gemini-embedding-2-preview
- Indexed: [number] files
- Vector: ready

**Send indexing status to the user in Telegram:**

> Indexing your knowledge base with Gemini Embedding 2...
> - Found [X] files across [Y] folders
> - Indexed: [number] files, [number] chunks
> - Status: [ready/in progress]

### Post-Restart: Live Memory Test

After indexing, run a live search test to confirm the system is working end-to-end:

```bash
# Test with a query relevant to the user's data
openclaw memory search "important" 2>&1 | head -20
```

If results come back, the system is working. If no results, check:
1. Is GOOGLE_API_KEY set?
2. Did the restart happen?
3. Is memory.backend = "builtin"?

**Send test results to the user in Telegram:**

> Memory system test complete:
> - Search returned [X] results
> - All [5] layers are operational
>
> Your upgraded memory system is fully installed and working.

If any layer failed, report which one and what needs to be fixed.

---

## Update Flow (for future updates)

When the onboarding package is updated (via the weekly Sunday check or manual update), the agent should communicate the entire update process to the user in Telegram, not in the terminal.

### Update Status File

After an update runs, it writes a status file at:
`~/.openclaw/onboarding/.update-result.json`

The agent should check for this file on each heartbeat. If it exists, read it and send a summary to the user in Telegram:

> Your system was updated from [old version] to [new version].
> Here is what changed: [summary from status file]
> Backup saved to: [path]
> [If restart needed]: Type /restart when you are ready.

After sending, rename the file to `.update-result-sent.json` so it is not sent again.

### Update Progress

During an update, progress should be communicated in Telegram, not buried in terminal output. The agent should send brief status messages:

> Checking for updates...
> Update available: [old] to [new]. Reviewing impact...
> [X] changes found. Applying approved changes...
> Update complete. [details]

---

## Completion Checklist

```
[ ] Layer 1: MEMORY.md exists and has content
[ ] Layer 1: memory/ directory exists
[ ] Layer 2: Flush prompt updated with category-based capture
[ ] Layer 3: sessionMemory enabled
[ ] Layer 4: memory.backend set to "builtin" (or PENDING if no API key)
[ ] Layer 4: memorySearch.provider set to "gemini" (or PENDING if no API key)
[ ] Layer 5: Mem0 plugin installed and loaded
[ ] Layer 5: autoCapture and autoRecall both true
[ ] Config validated with openclaw config validate
[ ] Gateway restarted by user (agent asked, user typed /restart)
[ ] Knowledge base indexing triggered (all master files, subfolders, multimodal)
[ ] Live memory search test returned results
[ ] All layer statuses reported to user in Telegram
[ ] Core files updated per CORE_UPDATES.md (using TYP rules)
```
