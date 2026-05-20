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
anything in this document. Tell the user exactly this:

  "I have not been taught the Teach Yourself Protocol yet. I cannot safely
   learn or execute these instructions until I have been taught TYP first.
   Please share the Teach Yourself Protocol tab with me before we proceed.
   Without TYP, I will bloat your core .md files and waste your tokens."

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

# INSTALL.md

> **N24 — Use the teach-yourself-protocol (Skill 01):** Before any action in this skill, the installing sub-agent MUST read every file under skills/01-teach-yourself-protocol/ and follow its procedural read-order. No shortcuts.


## Purpose
Install summarize CLI and verify YouTube summary plus transcript extraction.

## Step 1
Open Terminal.

## Step 2
Go to the workspace root that contains `.env`.

## Step 3
Install summarize:
```bash
brew --version || /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install steipete/tap/summarize
summarize --help >/dev/null
```

## Step 4
Load keys from the first `.env` file found. Check these locations in order:
```bash
# Discover keys - check all known env file locations
_discover_key() {
  local key_name="$1"
  for env_file in \
    "$HOME/clawd/secrets/.env" \
    "$HOME/.openclaw/.env" \
    "$HOME/.config/openclaw/.env" \
    ".env"; do
    if [ -f "$env_file" ]; then
      val=$(grep "^${key_name}=" "$env_file" 2>/dev/null | cut -d= -f2- | tr -d '"')
      if [ -n "$val" ]; then
        echo "$val"
        return 0
      fi
    fi
  done
  return 1
}

OPENAI_API_KEY=$(_discover_key "OPENAI_API_KEY")
GEMINI_API_KEY=$(_discover_key "GEMINI_API_KEY")
export OPENAI_API_KEY GEMINI_API_KEY
```

## Step 5
Check which keys are available. Missing keys do not block install - the skill continues with whichever providers are available.

**For OPENAI_API_KEY:**
```bash
if [ -z "$OPENAI_API_KEY" ]; then
  echo "OPENAI_API_KEY not found in any .env file."
  echo "Options:"
  echo "  1. Enter your OpenAI API key now (paste it): "
  read -r key_input
  if [ -n "$key_input" ]; then
    export OPENAI_API_KEY="$key_input"
    echo "OPENAI_API_KEY set for this session."
  else
    echo "Skipping OpenAI provider. Summarize will use Gemini only (if available)."
    SKIP_OPENAI=1
  fi
else
  echo "OPENAI_API_KEY found."
fi
```

**For GEMINI_API_KEY:**
```bash
if [ -z "$GEMINI_API_KEY" ]; then
  echo "GEMINI_API_KEY not found in any .env file."
  echo "Options:"
  echo "  1. Enter your Gemini API key now (paste it): "
  read -r key_input
  if [ -n "$key_input" ]; then
    export GEMINI_API_KEY="$key_input"
    echo "GEMINI_API_KEY set for this session."
  else
    echo "Skipping Gemini provider. Summarize will use OpenAI only (if available)."
    SKIP_GEMINI=1
  fi
else
  echo "GEMINI_API_KEY found."
fi

if [ "${SKIP_OPENAI:-0}" = "1" ] && [ "${SKIP_GEMINI:-0}" = "1" ]; then
  echo "ERROR: Both providers skipped. At least one API key is required."
  echo "Add OPENAI_API_KEY or GEMINI_API_KEY to ~/clawd/secrets/.env and re-run."
  exit 1
fi
```

## Step 6
Run OpenAI-first test (skip if OPENAI_API_KEY unavailable):
```bash
if [ "${SKIP_OPENAI:-0}" != "1" ]; then
  OPENAI_API_KEY="$OPENAI_API_KEY" summarize "https://youtu.be/dQw4w9WgXcQ" --youtube auto --length short
else
  echo "OpenAI provider skipped."
fi
```

## Step 7
If Step 6 fails or was skipped, run Gemini fallback (uses `--provider gemini` to force the Gemini backend):
```bash
if [ "${SKIP_GEMINI:-0}" != "1" ]; then
  GEMINI_API_KEY="$GEMINI_API_KEY" summarize "https://youtu.be/dQw4w9WgXcQ" --youtube auto --length short --provider gemini
else
  echo "Gemini provider skipped."
fi
```

## Step 8
Run transcript extraction test:
```bash
summarize "https://youtu.be/dQw4w9WgXcQ" --youtube auto --extract-only
```

## Step 9
Update AGENTS.md, TOOLS.md, MEMORY.md using `CORE_UPDATES.md` snippets.

## Step 10
Report final status with key used and test results.
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
- Do NOT say "I will restart the gateway now" without asking first
- Do NOT assume the user wants the restart

---
