# INSTALL.md - Book-to-Persona Skill

## STEP 0 - TSP PREREQUISITE CHECK (Do This Before Anything Else)

**Before installing this skill, the agent must have already learned Skill 01: Teach Yourself Protocol.**

Check now:
```
Search AGENTS.md and MEMORY.md for: "Teach Yourself Protocol" or "TSP"
```

**If TSP IS found in your core files:** Proceed to Step 1.

**If TSP is NOT found:** STOP immediately. Tell the user:

> "Before we can install this skill, you need to complete Skill 01 - Teach Yourself Protocol first.
> Download it from: https://github.com/trevorotts1/openclaw-onboarding (folder: 01-teach-yourself-protocol)
> Tell your AI to read SKILL.md in that folder and complete the full TSP installation.
> Come back to this skill after that is done."

Do NOT proceed with this installation until TSP is confirmed installed.

---

## Step 1 - Activate TSP on This Skill Folder (Teach Yourself Protocol)

Run the Teach Yourself Protocol on this skill folder now. Read every .md file in this order:

1. SKILL.md (already read if you are here)
2. PIPELINE.md
3. CHECKLIST.md
4. GOOD-AND-BAD-EXAMPLES.md
5. PERSONA-ROUTER.md
6. QMD-RETRIEVAL-GUIDE.md
7. CORE_UPDATES.md
8. INSTALL.md (this file - you are reading it now)

**Announce to the user after each file:** "Read [filename]. Moving to next."
**Do not proceed to Step 2 until all 8 files are confirmed read.**
After all reads: announce "TSP complete for book-to-persona skill. Proceeding with installation."

---

## Step 2 - Check Dependencies

### QMD (Required)

Run: `qmd --version`

**If QMD is installed:** You will see output like `qmd 1.1.0`. Proceed to Step 3.

**If QMD is NOT installed:** You will see "command not found". Install it now:

```bash
# Install via bun (recommended - this is how it was installed on BlackCEO systems)
bun install -g https://github.com/tobi/qmd

# Verify installation
qmd --version
```

If bun is not installed:
```bash
# Install bun first
curl -fsSL https://bun.sh/install | bash

# Then install qmd
bun install -g https://github.com/tobi/qmd
```

QMD documentation and source: https://github.com/tobi/qmd

**Do not proceed until `qmd --version` returns a version number.**

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

Run: `which ebook-convert`

**If NOT installed:**
```bash
brew install --cask calibre
```

After install, verify: `ebook-convert --version`

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

### Kimi K2.5 (Phase 1)
Check OpenClaw config for `moonshot` provider with `MOONSHOT_API_KEY`:
```bash
grep "MOONSHOT_API_KEY" ~/clawd/secrets/.env
```
Should return a key. If missing, add your Moonshot API key to `~/clawd/secrets/.env`.

### DeepSeek V3.2-Speciale (Phase 2)
Routes via OpenRouter. Check:
```bash
grep "OPENROUTER_API_KEY" ~/clawd/secrets/.env
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

## Step 5 - Set Up QMD Collection (coaching-personas)

The 40 pre-built personas are already in this skill folder. Now add them to QMD so agents can search them.

### 5a - Add the collection
```bash
qmd collection add ~/.openclaw/skills/21-book-to-persona/personas \
  --name coaching-personas \
  --mask "**/*.md"
```

**Expected output:** Something like "Added collection coaching-personas with 120 files"
If you see an error, check that the personas folder exists at the path above.

### 5b - Index the files
```bash
qmd update
```

**Expected output:** File count confirmation. Should show 120 files indexed (3 per persona x 40 personas).

### 5c - Run the embedding (this takes 3-8 minutes on first run)
```bash
qmd embed
```

**What this does:** Downloads a small local model (one time only) and generates semantic vectors for all 447 documents. This runs locally - no API keys needed, no data leaves your machine.

**Expected output:** Progress updates showing chunks processed. Final line will show total chunks embedded.

**This only runs once.** After the first embed, `qmd update` is all you need when adding new books.

### 5d - Verify it works
```bash
qmd search coaching-personas "negotiation objection handling"
```

**Expected output:** Results showing content from the Voss (Never Split the Difference) persona.
If you get no results, run `qmd embed` again and wait for it to complete fully.

---

## Step 6 - Set Up Weekly Auto-Update (Agent Handles This)

Run this command now - the agent executes it, the human does nothing:

```bash
bash ~/.openclaw/skills/scripts/update-skills.sh --setup-cron
```

If the setup script does not exist yet, run:
```bash
mkdir -p ~/.openclaw/skills/scripts
curl -s https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/scripts/setup-weekly-update.sh -o ~/.openclaw/skills/scripts/setup-weekly-update.sh
chmod +x ~/.openclaw/skills/scripts/setup-weekly-update.sh
bash ~/.openclaw/skills/scripts/setup-weekly-update.sh
```

**What this does:** Installs a cron job that runs every Sunday at 2:00 AM. Checks GitHub for new skill versions, downloads updates, applies them to installed skills only, sends a Telegram notification with what changed.

**Verify it was installed:**
```bash
crontab -l | grep update-skills
```
Should show: `0 2 * * 0 /Users/[you]/.openclaw/skills/scripts/update-skills.sh`

---

## Step 7 - Update Core Files

See `CORE_UPDATES.md` for exactly what to add to which files.
The updates are concise - a summary paragraph plus a reference path. No bulk content is added to core files.

---

## Step 7 - Confirm Ready

Run through this checklist:
- [ ] All 8 skill .md files read (TSP complete)
- [ ] QMD installed and returning version
- [ ] pdfplumber installed
- [ ] ebooklib installed
- [ ] Calibre ebook-convert available
- [ ] Master files folder located or created
- [ ] Moonshot API key confirmed in ~/clawd/secrets/.env
- [ ] OpenRouter API key confirmed in ~/clawd/secrets/.env
- [ ] Codex OAuth token confirmed and not expired
- [ ] QMD collection coaching-personas added and embedded (Step 5)
- [ ] QMD test query returns results
- [ ] Core files updated per CORE_UPDATES.md (Step 6)

When all boxes are checked: announce "Book-to-Persona skill fully installed. QMD collection active. 40 pre-built personas ready. Ready to add new books or query personas."
