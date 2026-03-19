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

### 4.3 Add knowledge folders to the index (extraPaths)

By default, OpenClaw only indexes the workspace memory files and session transcripts. To index the full knowledge base (master files, personas, AI workforce docs, and all subfolders), you MUST configure `extraPaths`.

**Step 1: Find the master files folder.**

Search the user's machine for any folder matching these names (case-insensitive):
- openclaw-master-files
- OpenClaw Master Files
- openclaw master files
- Any folder in ~/Downloads/ containing "openclaw" and "master" or "onboarding"

```bash
find ~/Downloads -maxdepth 2 -type d -iname "*openclaw*master*" -o -iname "*openclaw*onboarding*" 2>/dev/null
```

**Step 2: Add the path to memorySearch.extraPaths.**

In `~/.openclaw/openclaw.json`, inside the `agents.defaults.memorySearch` section, add:

```json
"extraPaths": [
  "/Users/USERNAME/Downloads/openclaw-master-files"
]
```

**CRITICAL: Use the FULL ABSOLUTE path, not a tilde (~).** OpenClaw resolves non-absolute paths relative to the workspace directory, so `~/Downloads/...` becomes `~/clawd/~/Downloads/...` which does not exist.

To get the absolute path:
```bash
# This prints the full absolute path
echo "$(cd ~/Downloads/openclaw-master-files && pwd)"
```

Use the ACTUAL path found in Step 1. If the folder is named differently (e.g., "OpenClaw Master Files" with spaces), use that exact name with the full absolute path:

```json
"extraPaths": [
  "/Users/USERNAME/Downloads/OpenClaw Master Files"
]
```

This tells OpenClaw to index EVERYTHING in that folder and ALL subfolders, including:
- Coaching personas
- AI Workforce Blueprint docs
- Department SOPs
- All skill documentation
- Any other knowledge docs

### 4.4 Enable multimodal indexing

Gemini Embedding 2 supports images, audio, and video, not just text. To index ALL file types, enable multimodal in the `memorySearch` section:

```json
"multimodal": {
  "enabled": true,
  "modalities": ["all"]
}
```

This tells OpenClaw to embed:
- `.md` (markdown documents - always indexed, even without multimodal)
- `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.heic`, `.heif` (images - requires multimodal)
- `.mp3`, `.wav`, `.ogg`, `.opus`, `.m4a`, `.aac`, `.flac` (audio - requires multimodal)

**Not supported by the current indexer:** `.pdf`, `.txt`, `.mp4`, `.webm`, `.sh`, `.py`, `.json`. These file types are skipped during indexing. Only markdown and multimodal media files are indexed.

Do NOT skip this step. Without multimodal enabled, images and audio files in the master files folder will NOT be embedded.

### 4.5 Configure search quality

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

### 4.6 Complete Layer 4 config example

After all Layer 4 steps, the full `memorySearch` section should look like this:

```json
"memorySearch": {
  "enabled": true,
  "sources": ["memory", "sessions"],
  "experimental": {
    "sessionMemory": true
  },
  "provider": "gemini",
  "model": "models/gemini-embedding-2-preview",
  "extraPaths": [
    "/Users/USERNAME/Downloads/openclaw-master-files"
  ],
  "multimodal": {
    "enabled": true,
    "modalities": ["all"]
  },
  "sync": {
    "onSessionStart": true,
    "onSearch": true,
    "watch": true,
    "watchDebounceMs": 1200,
    "sessions": {
      "deltaBytes": 20000,
      "deltaMessages": 10
    }
  },
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
}
```

Replace the `extraPaths` value with the actual path found on the user's machine.

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

### Post-Restart: Knowledge Indexing and Embedding

After the user restarts the gateway, TWO things must happen:

1. **Indexing**: discovering and reading all knowledge files
2. **Embedding**: converting those files into vector representations via the Gemini Embedding 2 API

These are separate operations. Indexing without embedding means the files are known but not searchable. Both must complete.

#### Step 1: Discover knowledge folders

Search the user's machine for all knowledge folders. Check these locations (case-insensitive):

```bash
# Find all candidate knowledge folders
find ~/Downloads -maxdepth 2 -type d -iname "*openclaw*master*" -o -iname "*openclaw*onboarding*" 2>/dev/null
```

Also include:
- The workspace directory (check `agents.defaults.workspace` in openclaw.json, typically ~/clawd/ or ~/.openclaw/workspace)
- The memory/ subdirectory inside the workspace
- Any coaching-personas, AI-workforce-blueprint, or department folders inside the master files folder

Report to the user what you found:

> I found these knowledge folders to index and embed:
> - [list each folder and approximate file count]

#### Step 2: Trigger indexing

OpenClaw's builtin memory backend indexes files in the workspace directory and configured paths automatically after restart. Verify indexing has started:

```bash
openclaw memory status 2>&1 | grep -E 'Indexed|Provider|Model|Vector|Batch'
```

If the indexed count is 0 or very low and the restart happened more than 60 seconds ago, something is wrong. Check:
- Is GOOGLE_API_KEY / GEMINI_API_KEY set in the environment?
- Is memory.backend = "builtin"?
- Is memorySearch.provider = "gemini"?

#### Step 3: Verify embedding

Embedding happens automatically as part of the indexing pipeline when the provider is Gemini. Verify embeddings are being generated:

```bash
openclaw memory status 2>&1 | grep -E 'Vector dims|Embedding cache|chunks'
```

Expected output should show:
- Vector dims: 3072 (this confirms Gemini Embedding 2 is generating vectors)
- Embedding cache: enabled with entries
- Chunks: growing number (files being split and embedded)

If Vector dims shows 0 or is missing, the embedding pipeline is not running. Check the API key.

#### Step 4: Monitor progress

For large knowledge bases, indexing and embedding may take several minutes. Check progress:

```bash
# Run this every 30 seconds until counts stabilize
openclaw memory status 2>&1 | grep 'Indexed'
```

When the indexed file count stops growing and matches the expected file count, indexing and embedding are complete.

#### Step 5: Report to user in Telegram

Send a progress update, then a completion message:

During indexing:
> Indexing and embedding your knowledge base with Gemini Embedding 2...
> - [X] files found across [Y] folders
> - [Z] files indexed so far, [N] chunks embedded
> - Vector dimensions: 3072 (Gemini Embedding 2 confirmed)
> - Status: in progress...

After completion:
> Knowledge base indexing and embedding complete.
> - [X] files indexed
> - [N] chunks embedded
> - Vector dimensions: 3072
> - All knowledge files are now searchable.

**File types indexed by OpenClaw memory search:**
- `.md` (markdown - always indexed)
- `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.heic`, `.heif` (images - requires multimodal enabled)
- `.mp3`, `.wav`, `.ogg`, `.opus`, `.m4a`, `.aac`, `.flac` (audio - requires multimodal enabled)

**NOT indexed:** `.pdf`, `.txt`, `.mp4`, `.webm`, `.sh`, `.py`, `.json`, `.skill`. The current OpenClaw indexer only supports markdown + multimodal media files.

---

### Post-Restart: Live Memory Layer Testing

After indexing and embedding are confirmed complete, run a REAL test of each memory layer. Do not just check config values. Actually test whether each layer works.

#### Test Layer 1: Markdown Files

```bash
# Verify MEMORY.md exists and has real content
wc -l ~/clawd/MEMORY.md
# Expected: more than 10 lines of real content, not just a template header

# Verify daily logs exist
ls ~/clawd/memory/*.md 2>/dev/null | wc -l
# Expected: at least 1 daily log file
```

Report: "Layer 1: MEMORY.md has [X] lines. [Y] daily log files found."

#### Test Layer 2: Memory Flush

This layer cannot be tested directly without triggering a compaction event. Verify the config is set correctly:

```bash
grep -A2 '"memoryFlush"' ~/.openclaw/openclaw.json | head -3
```

Confirm: enabled = true, softThresholdTokens is set, prompt contains category-based capture instructions.

Report: "Layer 2: Memory flush configured with [X]-category capture prompt."

#### Test Layer 3: Session Indexing

```bash
# Check if past sessions are being indexed
openclaw memory status 2>&1 | grep -A2 'sessions'
```

Expected: shows session source with indexed count > 0 (if there have been previous conversations).

Report: "Layer 3: Session indexing active. [X] past sessions indexed."

#### Test Layer 4: Gemini Embedding 2 Search

Run an actual search query, not just a config check:

```bash
openclaw memory search "the user" 2>&1 | head -20
```

Expected: returns actual search results with content from the user's files.

If this returns nothing:
1. Check if GOOGLE_API_KEY is set: `echo $GOOGLE_API_KEY`
2. Check if indexing completed: `openclaw memory status`
3. Check if backend is correct: `grep '"backend"' ~/.openclaw/openclaw.json`

Report: "Layer 4: Gemini search returned [X] results. Search is operational." or "Layer 4: Search returned no results. [diagnosis]."

#### Test Layer 5: Mem0

```bash
openclaw status 2>&1 | grep -i 'mem0'
```

Expected: shows openclaw-mem0 registered with autoRecall: true, autoCapture: true.

Report: "Layer 5: Mem0 loaded. Auto-capture: [on/off]. Auto-recall: [on/off]."

#### Final Report to User in Telegram

After testing ALL 5 layers, send ONE comprehensive message:

> Memory system test results:
>
> Layer 1 (Markdown files): [PASS/FAIL] - MEMORY.md has [X] lines, [Y] daily logs
> Layer 2 (Memory flush): [PASS/FAIL] - Category-based capture prompt configured
> Layer 3 (Session indexing): [PASS/FAIL] - [X] past sessions indexed
> Layer 4 (Gemini search): [PASS/FAIL] - Search returned [X] results from [Y] indexed files
> Layer 5 (Mem0): [PASS/FAIL] - Auto-capture [on/off], auto-recall [on/off]
>
> Overall: [X]/5 layers operational.
> [If all pass]: Your upgraded memory system is fully installed and working.
> [If any fail]: [Specific layer] needs attention: [what to fix].

Do NOT say "all layers working" unless you ran real tests and every one passed.

---

### Rollback Procedure (If Layer Tests Fail)

If any layer test fails after the config changes and restart:

#### Layer 4 failure (search returns nothing, wrong provider, or config crash)

1. Restore the config backup you created before making changes:
   ```bash
   cp [BACKUP_PATH]/openclaw.json ~/.openclaw/openclaw.json
   ```
2. Ask the user to type /restart
3. Report to the user what failed and what was rolled back
4. Do NOT attempt to re-apply the changes until the root cause is diagnosed

#### Layer 5 failure (Mem0 not loading)

1. Check if the plugin is installed: `openclaw plugins list`
2. If missing, reinstall: `openclaw plugins install @mem0/openclaw-mem0`
3. Verify the memory slot is set correctly in openclaw.json
4. Ask the user to type /restart

#### Config validation failure (openclaw config validate says invalid)

1. Do NOT ask the user to restart
2. Immediately restore from backup:
   ```bash
   cp [BACKUP_PATH]/openclaw.json ~/.openclaw/openclaw.json
   ```
3. Re-validate: `openclaw config validate`
4. Report to the user exactly what value caused the failure
5. Only proceed after the invalid value is identified and corrected

#### General rollback rules

- Always have a backup BEFORE making config changes (this is mandatory in the install steps above)
- If you are unsure what broke, restore the full backup and start diagnosis from a known-good state
- Never leave the user on an invalid config. Restore first, debug second.
- Report every rollback action to the user in Telegram with a clear explanation of what happened and why

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
CONFIGURATION
[ ] Layer 1: MEMORY.md exists and has real content (not just template)
[ ] Layer 1: memory/ directory exists
[ ] Layer 2: Flush prompt updated with category-based capture
[ ] Layer 3: sessionMemory enabled
[ ] Layer 4: memory.backend set to "builtin" (or PENDING if no API key)
[ ] Layer 4: memorySearch.provider set to "gemini" (or PENDING if no API key)
[ ] Layer 4: extraPaths configured with master files folder path
[ ] Layer 4: multimodal.enabled = true, modalities = ["all"]
[ ] Layer 5: Mem0 plugin installed and loaded
[ ] Layer 5: autoCapture and autoRecall both true
[ ] Config validated with openclaw config validate - MUST PASS

RESTART
[ ] Gateway restarted by user (agent asked in Telegram, user typed /restart)

INDEXING AND EMBEDDING
[ ] Knowledge folders discovered (master files, subfolders, workspace, memory)
[ ] All supported file types included (md, txt, pdf, images, audio, video)
[ ] Indexing confirmed running (openclaw memory status shows file count growing)
[ ] Embedding confirmed (Vector dims: 3072 visible in memory status)
[ ] Indexing and embedding complete (file count stabilized)

LIVE TESTING (must run real queries, not just config checks)
[ ] Layer 1 tested: MEMORY.md readable with real content
[ ] Layer 2 tested: Flush prompt config verified
[ ] Layer 3 tested: Session indexing shows past sessions
[ ] Layer 4 tested: openclaw memory search returned real results
[ ] Layer 5 tested: Mem0 shows registered with autoCapture + autoRecall on

REPORTING
[ ] All layer test results reported to user in Telegram
[ ] Indexing/embedding status reported to user in Telegram
[ ] If any layer failed, specific diagnosis sent to user
[ ] Core files updated per CORE_UPDATES.md (using TYP rules)

CLIENT EDUCATION
[ ] HOW-YOUR-MEMORY-WORKS.md is available in the skill folder
[ ] If user asks how their memory works, reference this file for a plain-English explanation
```
