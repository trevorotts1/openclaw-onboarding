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
If this skill's SKILL.md, CORE_UPDATES.md, or any other file in this skill
folder conflicts with TYP regarding WHICH core .md files to update or WHAT
content to add, always follow this skill's files. The skill takes precedence
over TYP on core file update decisions. TYP governs the storage method (lean
summaries + file paths). The skill governs the content and which files it
touches. When in doubt: skill docs win.

TYP FILE STORAGE INSTRUCTIONS (only read this if TYP confirmed)

WHEN LEARNING THIS DOCUMENT, FOLLOW THIS STRUCTURE:

1. SAVE FULL DOCUMENTATION TO MASTER FILES FOLDER
   Find the OpenClaw master files folder in ~/Downloads/. It may be named:
   - OpenClaw Master Files
   - OpenClaw Master Documents
   - OpenClaw Documents
   - openclaw-master-files
   - openclaw master files
   - OpenClaw Files
   - openclaw-documents
   - Any variation of "openclaw" + "master" or "files" or "documents"
   Search case-insensitively. One word or two words. Plural or singular.
   If no folder is found, create: ~/Downloads/OpenClaw Master Files/

   Save this full document content as a .md file in that folder.

2. DO NOT DUMP FULL CONTENT INTO CORE .MD FILES
   AGENTS.md, TOOLS.md, and MEMORY.md must stay lean.
   Only add a brief summary and a file path reference to where the full
   documentation lives. Never paste thousands of lines into core files.

3. USE THE LABELED SECTIONS BELOW TO KNOW WHAT GOES WHERE
   Look for sections marked:
   [ADD TO AGENTS.md]
   [ADD TO TOOLS.md]
   [ADD TO MEMORY.md]
   Only add what is labeled. Nothing else goes into core files.

---

# INSTALL.md - Book-to-Persona Skill

## STEP 0 - TYP PREREQUISITE CHECK (Do This Before Anything Else)

**Before installing this skill, the agent must have already learned Skill 01: Teach Yourself Protocol.**

Check now:
```
Search AGENTS.md and MEMORY.md for: "Teach Yourself Protocol" or "TYP"
```

**If TYP IS found in your core files:** Proceed to Step 1.

**If TYP is NOT found:** Stop. Skill 01 - Teach Yourself Protocol must be installed first. Navigate to 01-teach-yourself-protocol/ in the onboarding package and complete that installation. Return here after TYP is confirmed installed.

Do NOT proceed with this installation until TYP is confirmed installed.

---

## Step 1 - Activate TYP on This Skill Folder (Teach Yourself Protocol)

Run the Teach Yourself Protocol on this skill folder now. Read every .md file in this order:

1. SKILL.md (already read if you are here)
2. PIPELINE.md
3. CHECKLIST.md
4. GOOD-AND-BAD-EXAMPLES.md
5. PERSONA-ROUTER.md
6. GEMINI-RETRIEVAL-GUIDE.md
7. CORE_UPDATES.md
8. INSTALL.md (this file - you are reading it now)

**Track read status internally. After each file, log it as read and proceed to the next.**
**Do not proceed to Step 2 until all 8 files are confirmed read.**
After all reads: log "TYP complete for book-to-persona skill. Proceeding with installation."

---

## Step 1b - Copy Skill to OpenClaw Skills Folder

Copy this entire skill folder into the standard OpenClaw skills directory so the agent can reference it at runtime.

Run:
```bash
mkdir -p ~/.openclaw/skills/22-book-to-persona-coaching-leadership-system
cp -r /tmp/openclaw-onboarding/22-book-to-persona-coaching-leadership-system/* ~/.openclaw/skills/22-book-to-persona-coaching-leadership-system/
```

**Note:** If the onboarding package was extracted to a different location, replace `/tmp/openclaw-onboarding/22-book-to-persona-coaching-leadership-system/` with the actual path to this skill folder.

Verify:
```bash
ls ~/.openclaw/skills/22-book-to-persona-coaching-leadership-system/
```

**Expected output:** SKILL.md, INSTALL.md, PIPELINE.md, CHECKLIST.md, CORE_UPDATES.md, GOOD-AND-BAD-EXAMPLES.md, PERSONA-ROUTER.md, GEMINI-RETRIEVAL-GUIDE.md, personas/, pipeline/, agent-prompts/ all present.

If any files are missing, re-run the copy command above.

---

## Step 2 - Check Dependencies

### Gemini Embedding Engine (Required)

**Step 1:** Ensure the Google GenAI SDK is installed for multimodal vector search:
```bash
pip3 install google-genai numpy --break-system-packages
```

**Step 2:** Verify your Gemini API Key is in your `.env` file (`GOOGLE_API_KEY` or `GEMINI_API_KEY`).

### pdfplumber (Required for PDF extraction)

Run: `python3 -c "import pdfplumber; print('OK')"`

**If NOT installed:**
```bash
pip3 install pdfplumber --break-system-packages
```

### ebooklib (Required for EPUB extraction)

Run: `python3 -c "import ebooklib; print('OK')"`

**If NOT installed:**
```bash
pip3 install ebooklib --break-system-packages
```

### Calibre - ebook-convert (Required for MOBI, AZW, AZW3, KFX)

**Auto-install check:**
```bash
if ! command -v ebook-convert &>/dev/null; then
  echo "Calibre not found. Installing..."
  brew install --cask calibre
else
  echo "Calibre already installed: $(ebook-convert --version | head -1)"
fi
```

**Verify installation:**
```bash
ebook-convert --version
```

Calibre handles all Kindle formats including MOBI, AZW, AZW3, and KFX.
DRM-free files only - DRM-protected books cannot be converted.

### Python 3 (Required)

Run: `python3 --version`

Should return Python 3.8 or higher. If not installed, install from https://python.org

---

## Step 3 - Locate or Create Master Files Folder

The skill stores all output in a "master files" folder. It looks for one before creating anything.

**Search order (check these locations in this order):**

```bash
# Run this to find existing master files folder
find ~/Downloads -maxdepth 2 -type d -iname "*openclaw*master*" -o \
  -type d -iname "*master*file*" -o \
  -type d -iname "*openclawmaster*" 2>/dev/null | head -5
```

**If a folder is found:** Use that exact folder. Do NOT rename it. Do NOT create a new one.

**If no folder is found:** Create the standard one:
```bash
mkdir -p ~/Downloads/openclaw-master-files/coaching-personas/books
mkdir -p ~/Downloads/openclaw-master-files/coaching-personas/text
mkdir -p ~/Downloads/openclaw-master-files/coaching-personas/personas
```

**Record the detected path** - you will use it for all file operations in this session.

---

## Step 4 - Verify Model Access

This skill requires three model connections. Check each one:


### Google Gemini (Required for Multimodal Embeddings)
Check for `GOOGLE_API_KEY` or `GEMINI_API_KEY` across all known env file locations:
```bash
_find_key "GOOGLE_API_KEY" || _find_key "GEMINI_API_KEY"
```
If missing, you MUST add your Google API key to `~/clawd/secrets/.env`. The multimodal embedding engine will crash without it.

### Kimi K2.5 (Phase 1)
Check for `MOONSHOT_API_KEY` across all known env file locations:
```bash
_find_key() {
  local key_name="$1"
  for env_file in \
    "$HOME/clawd/secrets/.env" \
    "$HOME/.openclaw/.env" \
    "$HOME/.config/openclaw/.env"; do
    if [ -f "$env_file" ]; then
      val=$(grep "^${key_name}=" "$env_file" 2>/dev/null | cut -d= -f2- | tr -d '"')
      if [ -n "$val" ]; then
        echo "Found $key_name in $env_file"
        return 0
      fi
    fi
  done
  echo "$key_name not found in any env file"
  return 1
}
_find_key "MOONSHOT_API_KEY"
```
If missing, add your Moonshot API key to `~/clawd/secrets/.env`.

### DeepSeek V3.2-Speciale (Phase 2)
Routes via OpenRouter. Check across all known env files:
```bash
_find_key "OPENROUTER_API_KEY"
```

### GPT-5.3 Codex (Phase 3)
Routes via OpenClaw OAuth. Check:
```bash
cat ~/.openclaw/agents/main/agent/auth-profiles.json | python3 -c "
import json,sys,datetime
d=json.load(sys.stdin)
p=d.get('profiles',{}).get('openai-codex:default',{})
exp=p.get('expires',0)
if exp:
    dt=datetime.datetime.fromtimestamp(exp/1000)
    print(f'Codex OAuth expires: {dt.strftime(\"%B %d, %Y\")}')
else:
    print('Codex OAuth: NOT FOUND - reconnect via OpenClaw CLI')
"
```

If Codex OAuth is not found or expired: reconnect via OpenClaw settings using your ChatGPT subscription.

---

## Step 5 - Set Up Gemini Engine Collection (coaching-personas) - DOCUMENTATION ONLY

Pre-built personas are already included in this skill folder. They will be added to Gemini Engine during Skill 23 (AI Workforce Blueprint) installation.

**DO NOT run Gemini Engine embed here.** Skill 23 will run the embedding once after all personas AND workforce files are ready.

**What happens next:**
- Skill 23 will add the coaching-personas collection to Gemini Engine
- Skill 23 will run `python3 ~/clawd/scripts/gemini-indexer.py` to index all personas + workforce files together
- This avoids redundant double-embedding (after Skill 22 and again after Skill 23)

**Note:** If you need to verify personas are searchable after Skill 23 completes, run:
```bash
python3 ~/clawd/scripts/gemini-search.py "negotiation"
```

---

## Step 5a - SKILL 23 DEPENDENCY CHECK (MANDATORY)

**Skill 23 (AI Workforce Blueprint) requires Skill 22 to be fully installed first.**

**Pre-flight check for Skill 23:**
Before allowing Skill 23 to run, verify this Skill 22 installation is complete:

```bash
# Check if Gemini Vector Database "coaching-personas" exists
if python3 ~/clawd/scripts/gemini-indexer.py --status 2>/dev/null | grep -q "indexed"; then
  echo "✅ Skill 22 verified: coaching-personas collection exists"
  echo "Skill 23 may proceed"
else
  echo "❌ Skill 22 NOT complete: coaching-personas collection missing"
  echo "STOP: Install Skill 22 (Book-to-Persona) first before running Skill 23"
  exit 1
fi
```

**This check MUST pass before Skill 23 can run.**

---

## Step 6 - Set Up Weekly Auto-Update (Agent Handles This)

Run this command now - the agent executes it autonomously:

```bash
bash ~/.openclaw/skills/scripts/update-skills.sh --setup-cron
```

If the setup script does not exist yet, check the onboarding package:
```bash
mkdir -p ~/.openclaw/skills/scripts
SETUP_SCRIPT=""
for candidate in \
  "/tmp/openclaw-onboarding/scripts/setup-weekly-update.sh" \
  "$HOME/.openclaw/skills/scripts/setup-weekly-update.sh"; do
  if [ -f "$candidate" ]; then
    SETUP_SCRIPT="$candidate"
    break
  fi
done
if [ -n "$SETUP_SCRIPT" ]; then
  cp "$SETUP_SCRIPT" ~/.openclaw/skills/scripts/setup-weekly-update.sh
  chmod +x ~/.openclaw/skills/scripts/setup-weekly-update.sh
  bash ~/.openclaw/skills/scripts/setup-weekly-update.sh
else
  echo "Setup script not found in onboarding package. Skip and note in completion report."
fi
```

**What this does:** Installs a cron job that runs every Sunday at 2:00 AM. Checks GitHub for new skill versions, downloads updates, applies them to installed skills only, sends a Telegram notification with what changed.

**Verify it was installed:**
```bash
crontab -l | grep update-skills
```
Should show: `0 2 * * 0 $HOME/.openclaw/skills/scripts/update-skills.sh`

---

## Step 7 - Update Core Files

See `CORE_UPDATES.md` for exactly what to add to which files.
The updates are concise - a summary paragraph plus a reference path. No bulk content is added to core files.

---

## Step 8 - Pipeline Execution Test

After all infrastructure is set up, verify the pipeline is operational by running a dry test.

### 8a - Verify text extraction works

Pick any PDF in the books folder (or use a small test PDF) and confirm pdfplumber can extract text:

```bash
python3 -c "
import pdfplumber, os, glob

books_dir = os.path.expanduser('~/Downloads/openclaw-master-files/coaching-personas/books')
pdfs = glob.glob(os.path.join(books_dir, '*.pdf'))
if not pdfs:
    print('NO PDFs found in books/ folder. Add a book PDF to test.')
else:
    pdf_path = pdfs[0]
    with pdfplumber.open(pdf_path) as pdf:
        text = ''
        for page in pdf.pages[:5]:
            t = page.extract_text()
            if t:
                text += t
    print(f'Extracted {len(text)} chars from first 5 pages of {os.path.basename(pdf_path)}')
    if len(text) > 100:
        print('Text extraction: PASS')
    else:
        print('Text extraction: FAIL - check PDF is not image-only or DRM-protected')
"
```

If no PDFs exist yet, skip this sub-step - extraction will be tested on the first real book run.

### 8b - Verify Phase 1 model connectivity (Kimi K2.5)

```bash
# Test Moonshot API key with a minimal request
curl -s https://api.moonshot.cn/v1/chat/completions \
  -H "Authorization: Bearer $(grep MOONSHOT_API_KEY ~/clawd/secrets/.env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"model":"kimi-k2.5","messages":[{"role":"user","content":"Reply with only: CONNECTED"}],"max_tokens":10}' \
  | python3 -c "import json,sys; r=json.load(sys.stdin); print('Phase 1 (Kimi):', r.get('choices',[{}])[0].get('message',{}).get('content','FAILED'))"
```

**Expected output:** `Phase 1 (Kimi): CONNECTED`
If it fails, verify MOONSHOT_API_KEY is correct in `~/clawd/secrets/.env`.

### 8c - Verify Phase 2 model connectivity (DeepSeek via OpenRouter)

```bash
curl -s https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $(grep OPENROUTER_API_KEY ~/clawd/secrets/.env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek/deepseek-chat","messages":[{"role":"user","content":"Reply with only: CONNECTED"}],"max_tokens":10}' \
  | python3 -c "import json,sys; r=json.load(sys.stdin); print('Phase 2 (DeepSeek):', r.get('choices',[{}])[0].get('message',{}).get('content','FAILED'))"
```

**Expected output:** `Phase 2 (DeepSeek): CONNECTED`
If it fails, verify OPENROUTER_API_KEY is correct.

### 8d - Verify Phase 3 model connectivity (Codex OAuth)

Phase 3 uses OpenClaw OAuth routing, so the connectivity test is confirming the token is valid and not expired (already done in Step 4). If the Codex OAuth check in Step 4 returned a future expiration date, Phase 3 is ready.

If Codex is unavailable, the pipeline automatically falls back to Kimi K2.5 (Phase 1 model) for synthesis. The fallback triggers on: API error, rate limit (429), timeout after 15 minutes, or output under 5,000 characters.

### 8e - Verify output directory structure

```bash
MASTER_DIR=~/Downloads/openclaw-master-files/coaching-personas
echo "Checking output directories..."
for dir in books text personas; do
  if [ -d "$MASTER_DIR/$dir" ]; then
    echo "  $dir/ EXISTS ($(ls "$MASTER_DIR/$dir" 2>/dev/null | wc -l | tr -d ' ') items)"
  else
    echo "  $dir/ MISSING - creating now"
    mkdir -p "$MASTER_DIR/$dir"
  fi
done
echo "Output structure: READY"
```

### 8f - Confirm pipeline is operational

After 8a-8e pass, the pipeline is ready. To process a book, the agent runs:

```
Run Book Intelligence Pipeline on: [book title or path to PDF]
```

This triggers the full sequence:
1. **Text extraction** - pdfplumber extracts to `text/[book-slug].txt`
2. **Phase 1 (Kimi K2.5)** - Spawns sub-agent with extraction prompt + book text. Output: `personas/[author]-[book-slug]/extraction-notes.md`
3. **Phase 2 (DeepSeek V3.2-Speciale)** - Spawns sub-agent with analysis prompt + extraction notes. Output: `personas/[author]-[book-slug]/analysis-notes.md`
4. **Phase 3 (GPT-5.3 Codex)** - Spawns sub-agent with synthesis prompt + extraction + analysis notes. Output: `personas/[author]-[book-slug]/persona-blueprint.md`. Falls back to Kimi K2.5 on failure.
5. **Gemini Engine indexing** - Runs `python3 ~/clawd/scripts/gemini-indexer.py` to make the new persona searchable.

**Verify each phase completed** by checking:
- File exists at the expected path
- File is not empty and exceeds minimum character thresholds (extraction: 5,000+, analysis: 3,000+, blueprint: 10,000+)
- `pipeline-status.json` in the master files folder shows `COMPLETE` for each phase

**Output files land in:**
```
~/Downloads/openclaw-master-files/coaching-personas/personas/[author]-[book-slug]/
  ├── extraction-notes.md     (Phase 1 output)
  ├── analysis-notes.md       (Phase 2 output)
  └── persona-blueprint.md    (Phase 3 output - the deployable persona)
```

---

## Step 8g - Full Pipeline Verification Test

Run one book through the complete 3-phase pipeline to verify the entire system works end-to-end:

1. Pick any PDF from the books/ folder (or use a provided sample book)
2. Run the orchestrator:
```bash
python3 ~/.openclaw/skills/22-book-to-persona-coaching-leadership-system/pipeline/orchestrator.py --single [book-slug]
```
Replace `[book-slug]` with the filename slug of the book (e.g., `clear-atomic-habits` for a book by James Clear on Atomic Habits).

3. Verify all three output files were created:
```bash
PERSONA_DIR=~/Downloads/openclaw-master-files/coaching-personas/personas/[book-slug]
echo "Checking pipeline output..."
for file in extraction-notes.md analysis-notes.md persona-blueprint.md; do
  if [ -f "$PERSONA_DIR/$file" ]; then
    chars=$(wc -c < "$PERSONA_DIR/$file" | tr -d ' ')
    echo "  $file: EXISTS ($chars characters)"
  else
    echo "  $file: MISSING - pipeline failed at this phase"
  fi
done
```

4. Check extraction-notes.md is at least 5,000 characters
5. Check persona-blueprint.md has all 14 sections present:
```bash
grep -c "^## Section" "$PERSONA_DIR/persona-blueprint.md"
```
Expected output: 14. If fewer, the synthesis phase did not complete fully.

If any check fails, the pipeline is not working. Review the error output from orchestrator.py and fix before proceeding.

If no PDF books are available yet, this step can be deferred until the first book is added. Mark it as PENDING in your checklist and run it on the first real book.

---

---

## 🔴 GATEWAY RESTART PROTOCOL - NEVER TRIGGER AUTONOMOUSLY

**During this installation, you may encounter instructions to restart the OpenClaw gateway.**

**YOU ARE FORBIDDEN from triggering gateway restarts yourself.**

### Correct Process
When a gateway restart is needed:
1. **STOP** - Do NOT execute the restart command
2. **NOTIFY** the user: "This installation requires an OpenClaw gateway restart to complete."
3. **INSTRUCT**: "Type `/restart` in Telegram to trigger it"
4. **WAIT** for user action - do NOT proceed until confirmed

### Forbidden Actions
- Do NOT run `openclaw gateway restart` without explicit user permission
- Do NOT say "I'll restart the gateway now" without asking first
- Do NOT assume the user wants the restart

---

## Step 9 - Confirm Ready

Run through this checklist:
- [ ] All 8 skill .md files read (TYP complete)
- [ ] Gemini Engine installed and returning version
- [ ] pdfplumber installed
- [ ] ebooklib installed
- [ ] Calibre ebook-convert available
- [ ] Master files folder located or created
- [ ] Moonshot API key confirmed in ~/clawd/secrets/.env
- [ ] OpenRouter API key confirmed in ~/clawd/secrets/.env
- [ ] Codex OAuth token confirmed and not expired
- [ ] Gemini Vector Database coaching-personas added and embedded (Step 5)
- [ ] Gemini Engine test query returns results
- [ ] Core files updated per CORE_UPDATES.md (Step 7)
- [ ] Pipeline execution test passed (Step 8)

When all boxes are checked: log "Book-to-Persona skill fully installed. Gemini Vector Database active. Pre-built personas ready (run: python3 ~/clawd/scripts/gemini-indexer.py --status to see count). Pipeline verified operational. Ready to process new books or query personas."