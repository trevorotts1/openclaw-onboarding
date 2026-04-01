## 🔴 ORDER LOCK (SOVEREIGN)
- OpenRouter setup must run LAST in onboarding sequence.
- Before any OpenRouter config edits, back up the model config first.
- If backup fails, stop OpenRouter setup and report error.

## 🔴 CONFIG SAFETY NOTE
Before ANY config edit:
1. Back up `~/.openclaw/openclaw.json` to `~/Downloads/openclaw-backups/` with a human-readable name.
2. Validate JSON after writing (`jq . < file` or `openclaw doctor`).
3. Reference https://docs.openclaw.ai for config structure.
4. Reference https://github.com/openclaw/openclaw for latest schema.

╔══════════════════════════════════════════════════════════════╗
  MANDATORY TYP CHECK - READ THIS BEFORE ANYTHING ELSE
  DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.
╚══════════════════════════════════════════════════════════════╝

STEP 1: AGENT VERIFIES TEACH YOURSELF PROTOCOL (TYP) KNOWLEDGE

Before executing ANY instruction in this document, the agent must verify that
TYP has been taught in prior context.

HOW TO CHECK:
- Search AGENTS.md, TOOLS.md, or MEMORY.md for "Teach Yourself Protocol" or "TYP"
- Check session context for prior TYP training
- Look for a tab called "Teach Yourself Protocol" in this same document

IF TYP IS CONFIRMED IN CONTEXT:
Agent proceeds to execute instructions below. Agent follows TYP file storage structure.

IF TYP IS NOT FOUND IN CONTEXT:
Agent STOPS IMMEDIATELY. Agent reports to requester:

  "TYP (Teach Yourself Protocol) not found in context. Cannot safely execute
   these instructions without TYP training first. Requester must provide TYP
   documentation before proceeding. Without TYP, core .md files will be bloated
   and tokens will be wasted."

DO NOT PROCEED PAST THIS POINT WITHOUT TYP CONFIRMED.

CONFLICT RULE (applies to all skill installs):
If this skill's SKILL.md, CORE_UPDATES.md, or any other file in this skill
folder conflicts with TYP regarding WHICH core .md files to update or WHAT
content to add, agent always follows this skill's files. The skill takes
precedence over TYP on core file update decisions. TYP governs the storage
method (lean summaries + file paths). The skill governs the content and which
files it touches. When in doubt: skill docs win.

══════════════════════════════════════════════════════════════════
  TYP FILE STORAGE INSTRUCTIONS (agent executes only if TYP confirmed)
══════════════════════════════════════════════════════════════════

WHEN AGENT LEARNS THIS DOCUMENT, AGENT FOLLOWS THIS STRUCTURE:

1. AGENT SAVES FULL DOCUMENTATION TO MASTER FILES FOLDER
   The canonical master files path is: ~/Downloads/openclaw-master-files/
   If this folder does not exist, agent creates it: mkdir -p ~/Downloads/openclaw-master-files/

   Agent saves this full document content as a .md file in that folder.

2. AGENT DOES NOT DUMP FULL CONTENT INTO CORE .MD FILES
   AGENTS.md, TOOLS.md, and MEMORY.md must stay lean.
   Agent adds only a brief summary and a file path reference to where the full
   documentation lives. Agent never pastes thousands of lines into core files.

3. AGENT USES THE LABELED SECTIONS BELOW TO KNOW WHAT GOES WHERE
   Agent looks for sections marked:
   [ADD TO AGENTS.md]
   [ADD TO TOOLS.md]
   [ADD TO MEMORY.md]
   Agent adds only what is labeled. Nothing else goes into core files.

EXECUTION DISCIPLINE - MANDATORY BEFORE AGENT STARTS
  *** OPENROUTER SPECIAL RULES - AGENT FOLLOWS THESE CAREFULLY ***
╚══════════════════════════════════════════════════════════════╝

These rules apply every single time agent executes instructions from this document.
No exceptions. No shortcuts. No improvising.

RULE 1: AGENT READS EVERYTHING BEFORE EXECUTING ANYTHING
Agent reads this entire document from top to bottom before executing a single step.
Agent does not start executing while still reading. Agent finishes reading first. Then starts.

RULE 2: AGENT DOES NOT CHANGE INTENT
These instructions say exactly what to do. Agent executes them exactly as written.
- Agent does NOT reinterpret steps
- Agent does NOT "improve" the instructions
- Agent does NOT skip steps because they seem unnecessary
- Agent does NOT add steps that are not in the document
- Agent does NOT change the order of steps
If a step says do X, agent does X. Not Y. Not a better version of X. X.

RULE 3: AGENT NEVER MODIFIES THESE WITHOUT PERMISSION
- API keys - agent copies them exactly, character for character
- Terminal commands - agent runs them exactly as written, no edits
- Config values - agent uses the exact values specified
- Model names - agent uses the exact names specified, spelling matters
- File paths - agent uses the exact paths specified
If agent is unsure whether something should be changed, the answer is NO.
Agent asks requester first. Agent does not guess. Agent does not assume.

RULE 4: AGENT NEVER USES openrouter/auto
The auto-router picks models unpredictably and breaks configs. This is
forbidden. Agent does not use it under any circumstances.

RULE 5: CONFIG SCHEMA - VALID KEYS ONLY
Each model entry in agents.defaults.models ONLY supports these keys:
- alias (string) - optional shortcut name
- params (object) - parameter overrides like temperature, reasoning
- streaming (boolean) - optional streaming override

That is it. Agent does NOT add custom keys like: contextWindow, maxTokens, context,
max_output, cost, pricing, notes, description, tier, or ANY other key.
Adding invalid keys will break the config and OpenClaw will refuse to start.

RULE 6: AGENT BACKS UP BEFORE EVERY CHANGE
Before ANY edit to the config file, agent creates a timestamped backup first.
If the backup fails, agent STOPS. Agent does not continue.

RULE 7: AGENT BUILDS CHECKLIST BEFORE EXECUTING
Before agent runs a single command or makes a single change, agent creates a numbered
checklist of every action this document requires agent to take.

RULE 8: AGENT REPORTS WHAT IT DID
When finished, agent gives requester a clear summary of what was completed,
what commands were run, and what files were changed.

══════════════════════════════════════════════════════════════════

# OpenRouter Setup - Agent Execution Guide

This guide instructs the agent to set up OpenRouter as the model provider for OpenClaw.
OpenRouter is a service that gives access to dozens of AI models (Claude, GPT, Gemini,
and many others) through a single API key and a single account.

Agent executes every step in order. Agent does not skip anything.

## What Is OpenRouter?

OpenRouter is a universal remote control for AI models. Instead of having a separate
account and API key for each AI company, one OpenRouter account connects to all of them.

Benefits:
- One API key for all models
- One billing account instead of many
- Easy switching between models
- Access to models not available directly
- Built-in fallback if one model goes down

OpenClaw has built-in support for OpenRouter. Agent does NOT need to set up a separate
"provider" section. Agent adds the API key and configures the models.

## Agent Execution Steps

### STEP 1: AGENT CHECKS FOR EXISTING OPENROUTER API KEY

Agent checks environment and config files for an existing key:

```bash
# Check environment variable
echo $OPENROUTER_API_KEY

# Check secrets env file
grep "OPENROUTER_API_KEY" ~/clawd/secrets/.env 2>/dev/null

# Check existing openclaw config
grep "OPENROUTER_API_KEY" ~/.openclaw/openclaw.json 2>/dev/null
```

IF API key is found in any location:
- Agent captures the key value for use in STEP 5
- Agent skips to STEP 4 (backup config)

IF API key is NOT found anywhere:
- Agent asks requester: "No OpenRouter API key found. Do you have an OpenRouter account and API key (format: sk-or-...)? If not, I can configure the model definitions now and you can add the API key later."
- IF requester provides a key: Agent captures it and proceeds to STEP 4
- IF requester wants to skip: Agent sets key as PENDING, skips STEP 5 (API key insertion), proceeds with STEP 4 and STEP 6 (model config only). Agent notes in completion report that API key must be added before models will work.

### STEP 2: AGENT CREATES OPENROUTER ACCOUNT (if needed)

IF requester does not have an OpenRouter account and wants to set one up now:
- Agent tells requester: "Navigate to https://openrouter.ai, click 'Sign Up' or 'Log In' in the top right corner, and create an account using Google, GitHub, or email. Let me know when your account is created."
- HUMAN ACTION REQUIRED (account auth): Requester creates account and confirms
- Agent proceeds to STEP 3

IF requester already has an OpenRouter account, or API key was found in STEP 1:
- Agent skips this step

### STEP 3: AGENT OBTAINS OPENROUTER API KEY (if needed)

IF agent does not yet have an API key and requester wants to provide one now:
- Agent tells requester: "Navigate to https://openrouter.ai/keys, click 'Create Key', name the key 'OpenClaw', copy the key (format: sk-or-...), and share it here."
- HUMAN ACTION REQUIRED (key creation): Requester creates and provides the key
- Agent captures the key and proceeds to STEP 4

IF agent already has an API key, or requester chose to skip:
- Agent skips this step

### STEP 4: AGENT BACKS UP CURRENT CONFIG FILE

Agent creates backup folder:

```bash
mkdir -p ~/openclaw-backup-configs
```

Agent backs up current config and captures the backup filename:

```bash
BACKUP_FILE="openclaw-backup-$(date +'%B %-d at %-I-%M %p').json"
cp ~/.openclaw/openclaw.json ~/openclaw-backup-configs/"$BACKUP_FILE"
echo "Backup saved as: $BACKUP_FILE"
```

Agent verifies backup exists and is not empty:

```bash
ls -la ~/openclaw-backup-configs/"$BACKUP_FILE"
```

IF backup file size is 0 or backup does not exist:
- Agent STOPS
- Agent reports backup failure to requester
- Agent does NOT proceed to next step

IF backup is successful and not empty:
- Agent continues to STEP 5

### STEP 5: AGENT ADDS API KEY TO CONFIG FILE

Agent opens config file and reads current content:

```bash
cat ~/.openclaw/openclaw.json
```

Agent parses the JSON to locate or create the "env" section.

Agent adds OPENROUTER_API_KEY to env section:

```json
"env": {
  "OPENROUTER_API_KEY": "sk-or-YOUR-KEY-HERE"
}
```

Agent replaces "sk-or-YOUR-KEY-HERE" with the actual API key obtained in STEP 3.

Agent writes updated config back to file:

```bash
# Agent uses jq or similar JSON tool to safely merge the key
jq '.env.OPENROUTER_API_KEY = "sk-or-YOUR-KEY-HERE"' ~/.openclaw/openclaw.json > ~/.openclaw/openclaw.json.tmp && mv ~/.openclaw/openclaw.json.tmp ~/.openclaw/openclaw.json
```

Agent verifies the key was added:

```bash
grep -A 2 '"env"' ~/.openclaw/openclaw.json
```

IF key is not found in config:
- Agent STOPS
- Agent reports error to requester
- Agent restores backup:
  ```bash
  cp ~/openclaw-backup-configs/"$BACKUP_FILE" ~/.openclaw/openclaw.json
  ```
- Agent does NOT proceed

IF key is found in config:
- Agent continues to STEP 6

### STEP 6: AGENT CONFIGURES MODELS IN CONFIG FILE

Agent reads current config:

```bash
cat ~/.openclaw/openclaw.json
```

Agent parses JSON to locate or create agents.defaults.models section.

Agent adds the following model configuration. Agent merges into existing agents section
if it already exists. Agent does NOT delete existing models or settings.

Agent adds this configuration:

```json
{
  "env": {
    "OPENROUTER_API_KEY": "sk-or-YOUR-KEY-HERE"
  },
  "agents": {
    "defaults": {
      "model": {
        "primary": "openrouter/minimax/minimax-m2.7",
        "fallbacks": [
          "openrouter/xiaomi/mimo-v2-pro",
          "openrouter/google/gemini-3.1-flash-lite-preview",
          "openrouter/openrouter/free",
          "openrouter/minimax/minimax-m2.7",
          "openrouter/moonshotai/kimi-k2.5",
          "openrouter/google/gemini-3-flash-preview",
          "openrouter/mistralai/mistral-small-creative",
          "openrouter/qwen/qwen3.5-plus-02-15",
          "openrouter/z-ai/glm-5",
          "openrouter/deepseek/deepseek-v3.2",
          "openrouter/deepseek/deepseek-v3.2-speciale",
          "openrouter/deepseek/deepseek-r1-0528:free",
          "openrouter/xiaomi/mimo-v2-omni",
          "openrouter/nvidia/nemotron-3-super-120b-a12b:free"
        ]
      },
      "thinkingDefault": "medium",
      "models": {
        },
        },
        },
        "openrouter/google/gemini-3.1-pro-preview": {
          "params": {
            "temperature": 0.3,
            "reasoning": { "effort": "medium" }
          }
        },
        "openrouter/google/gemini-3-flash-preview": {
          "params": {
            "temperature": 0.3,
            "reasoning": { "effort": "medium" }
          }
        },
        },
        },
        },
        "openrouter/moonshotai/kimi-k2.5": {
          "params": {
            "temperature": 1.0
          }
        },
        "openrouter/minimax/minimax-m2.7": {
          "params": {
            "temperature": 0.3,
            "reasoning": true
          }
        },
        "openrouter/mistralai/mistral-small-creative": {
          "params": {
            "temperature": 0.3
          }
        },
        "openrouter/qwen/qwen3.5-plus-02-15": {
          "params": {
            "temperature": 0.3,
            "reasoning": { "effort": "medium" }
          }
        },
        "openrouter/z-ai/glm-5": {
          "params": {
            "temperature": 0.3,
            "reasoning": { "effort": "medium" }
          }
        },
        "openrouter/deepseek/deepseek-v3.2": {
          "params": {
            "temperature": 0.3,
            "reasoning": { "effort": "medium" }
          }
        },
        "openrouter/deepseek/deepseek-v3.2-speciale": {
          "params": {
            "temperature": 0.3,
            "reasoning": { "effort": "medium" }
          }
        },
        "openrouter/deepseek/deepseek-r1-0528:free": {
          "params": {
            "temperature": 0.3,
            "reasoning": { "effort": "medium" }
          }
        },
        "openrouter/xiaomi/mimo-v2-omni": {
          "params": {
            "temperature": 0.3,
            "reasoning": true
          }
        },
        "openrouter/nvidia/nemotron-3-super-120b-a12b:free": {
          "params": {
            "temperature": 0.3,
            "reasoning": { "effort": "medium" }
          }
        },
        "openrouter/xiaomi/mimo-v2-pro": {
          "params": {
            "temperature": 0.3,
            "reasoning": true
          }
        },

      }
    }
  }
}
```

Agent uses jq to ADDITIVELY MERGE new models into the existing config (preserving any existing models):

```bash
# Define the new models as a separate JSON block
NEW_MODELS='{

  "openrouter/google/gemini-3.1-pro-preview": {"params": {"temperature": 0.3, "reasoning": {"effort": "medium"}}},
  "openrouter/google/gemini-3-flash-preview": {"params": {"temperature": 0.3, "reasoning": {"effort": "medium"}}},
  "openrouter/google/gemini-3.1-flash-lite-preview": {"params": {"temperature": 0.3, "reasoning": {"effort": "medium"}}},
  "openrouter/moonshotai/kimi-k2.5": {"params": {"temperature": 1.0}},
  "openrouter/minimax/minimax-m2.7": {"params": {"temperature": 0.3, "reasoning": true}},
  "openrouter/mistralai/mistral-small-creative": {"params": {"temperature": 0.3}},
  "openrouter/qwen/qwen3.5-plus-02-15": {"params": {"temperature": 0.3, "reasoning": {"effort": "medium"}}},
  "openrouter/z-ai/glm-5": {"params": {"temperature": 0.3, "reasoning": {"effort": "medium"}}},
  "openrouter/deepseek/deepseek-v3.2": {"params": {"temperature": 0.3, "reasoning": {"effort": "medium"}}},
  "openrouter/deepseek/deepseek-v3.2-speciale": {"params": {"temperature": 0.3, "reasoning": {"effort": "medium"}}},
  "openrouter/deepseek/deepseek-r1-0528:free": {"params": {"temperature": 0.3, "reasoning": {"effort": "medium"}}},
  "openrouter/xiaomi/mimo-v2-omni": {"params": {"temperature": 0.3, "reasoning": true}},
  "openrouter/xiaomi/mimo-v2-pro": {"params": {"temperature": 0.3, "reasoning": true}},
  "openrouter/nvidia/nemotron-3-super-120b-a12b:free": {"params": {"temperature": 0.3, "reasoning": {"effort": "medium"}}},

}'

# Additive merge: existing models are preserved, new models are added/updated
jq --argjson new "$NEW_MODELS" '
  .agents.defaults.model.primary = "openrouter/minimax/minimax-m2.7" |
  .agents.defaults.model.fallbacks = ["openrouter/xiaomi/mimo-v2-pro", "openrouter/google/gemini-3.1-flash-lite-preview", "openrouter/openrouter/free", "openrouter/minimax/minimax-m2.7", "openrouter/moonshotai/kimi-k2.5", "openrouter/google/gemini-3-flash-preview", "openrouter/mistralai/mistral-small-creative", "openrouter/qwen/qwen3.5-plus-02-15", "openrouter/z-ai/glm-5", "openrouter/deepseek/deepseek-v3.2", "openrouter/deepseek/deepseek-v3.2-speciale", "openrouter/deepseek/deepseek-r1-0528:free", "openrouter/xiaomi/mimo-v2-omni", "openrouter/nvidia/nemotron-3-super-120b-a12b:free"] |
  .agents.defaults.thinkingDefault = "medium" |
  .agents.defaults.models = ((.agents.defaults.models // {}) * $new)
' ~/.openclaw/openclaw.json > ~/.openclaw/openclaw.json.tmp && mv ~/.openclaw/openclaw.json.tmp ~/.openclaw/openclaw.json
```

NOTE: The `* $new` operator merges new models INTO existing models. Any pre-existing models that are NOT in the new set remain untouched. Any models that exist in both are updated to the new config.

Agent verifies models were added:

```bash
grep -c "openrouter/xiaomi/mimo-v2-pro" ~/.openclaw/openclaw.json
```

IF models are not found in config:
- Agent STOPS
- Agent reports error to requester
- Agent restores backup:
  ```bash
  cp ~/openclaw-backup-configs/"$BACKUP_FILE" ~/.openclaw/openclaw.json
  ```
- Agent does NOT proceed

IF models are found in config:
- Agent continues to STEP 7

### STEP 7: AGENT VALIDATES CONFIG

Agent validates config syntax:

```bash
openclaw doctor
```

Expected output on success: All checks show green/pass status (e.g. "Config: OK", "Models: OK", "Gateway: OK"). No red/fail lines. If warnings appear (yellow) but no errors (red), config is valid.

IF validation PASSES (no errors):
- Agent continues to STEP 8

IF validation FAILS:
- Agent STOPS
- Agent reports validation error to requester
- Agent restores backup:
  ```bash
  cp ~/openclaw-backup-configs/"$BACKUP_FILE" ~/.openclaw/openclaw.json
  ```
- Agent does NOT proceed

### STEP 8: AGENT RESTARTS OPENCLAW GATEWAY

Agent restarts the gateway:

```bash
openclaw gateway restart
```

Agent waits for gateway to restart (approximately 5-10 seconds).

Agent verifies gateway is running:

```bash
openclaw gateway status
```

Expected output on success: Status shows "running" or "active" with a PID number and listening port (e.g. "Gateway is running (PID: 12345) on port 3578"). Any response other than "running"/"active" indicates a problem.

IF gateway is running:
- Agent continues to STEP 9

IF gateway is not running:
- Agent STOPS
- Agent reports error to requester
- Agent does NOT proceed

### STEP 9: AGENT SAVES DOCUMENTATION TO MASTER FILES

Agent locates or creates master files folder:

```bash
mkdir -p ~/Downloads/openclaw-master-files/openrouter-setup/
```

Agent saves this full document to:

```bash
~/Downloads/openclaw-master-files/openrouter-setup/openrouter-setup-instructions.md
```

Agent creates summary for AGENTS.md:

```
## Intelligent Model Routing - THINK BEFORE YOU ACT
Before executing ANY task, evaluate which model fits best and switch if needed.
Key rules:
- Kimi K2.5 CANNOT do tool calls. Never route tool tasks to Kimi.
- MiniMax M2.7 is the daily workhorse (cheap + tools + opt-in reasoning). Pass reasoning: true.
- MiMo V2 Pro for complex code/orchestration (TEXT ONLY, 1M context).
- MiMo V2 Omni for multimodal tasks (images+video+audio).
- Opus is the specialist (complex strategy, writing, client-facing).
- Perplexity Sonar Pro Search for deep research, Perplexity Sonar for quick lookups.
Full details: See ~/Downloads/openclaw-master-files/openrouter-setup/openrouter-setup-instructions.md
```

Agent creates summary for TOOLS.md:

```
## OpenRouter Model Configuration
22 models configured via OpenRouter. Primary: MiniMax M2.7.
Temperature: 0.3 for all models, 1.0 for Kimi K2.5 only.
Config file: ~/.openclaw/openclaw.json
Always back up before editing. Always validate with openclaw doctor after.
Full reference: ~/Downloads/openclaw-master-files/openrouter-setup/openrouter-setup-instructions.md
```

Agent adds these summaries to AGENTS.md and TOOLS.md respectively (agent does NOT paste full document content).

### STEP 10: AGENT REPORTS COMPLETION

Agent provides requester with summary:

```
OPENROUTER SETUP COMPLETE

Actions completed:
1. ✓ Verified or obtained OpenRouter API key
2. ✓ Backed up config to ~/openclaw-backup-configs/
3. ✓ Added OPENROUTER_API_KEY to ~/.openclaw/openclaw.json
4. ✓ Configured 22 models in agents.defaults.models
5. ✓ Validated config with openclaw doctor
6. ✓ Restarted openclaw gateway
7. ✓ Saved full documentation to ~/Downloads/openclaw-master-files/openrouter-setup/
8. ✓ Added summaries to AGENTS.md and TOOLS.md

Primary model: openrouter/minimax/minimax-m2.7
Fallback models: openrouter/xiaomi/mimo-v2-pro, openrouter/google/gemini-3.1-flash-lite-preview, openrouter/openrouter/free, openrouter/minimax/minimax-m2.7, openrouter/moonshotai/kimi-k2.5, (+ 12 more)

Config file: ~/.openclaw/openclaw.json
Backup location: ~/openclaw-backup-configs/

Setup is complete and ready for use.
```

## Model Reference - What Each Model Is For

| Model | Alias | Best For | Cost Level |
|-------|-------|----------|------------|
| Claude Opus 4.6 | opus | Complex strategy, architecture, critical work | High |
| Claude Sonnet 4.6 | sonnet | Balanced quality and speed | Medium-High |
| Claude Haiku 4.5 | haiku | Fast responses | Medium |
| Gemini 3.1 Pro | gemini31 | Long document analysis | Medium |
| Gemini 3 Flash | flash | Quick tasks, large context | Low-Medium |
| Kimi K2.5 | kimi | Code generation, chat (NO tool calls) | Low |
| MiniMax M2.7 | minimax | RECOMMENDED PRIMARY - daily tasks, tool calls | Low |
| MiMo V2 Pro | mimo-pro | Complex code, orchestration (TEXT ONLY, 1M context) | Medium |
| MiMo V2 Omni | mimo-omni | Multimodal (text+images+video+audio) | Low-Medium |
| Mistral Small Creative | creative | All writing and content creation | Very Low |
| Qwen 3.5 Plus | qwen | General purpose, large context | Low-Medium |
| GLM-5 | glm5 | Systems design, agent workflows | Low-Medium |
| DeepSeek V3.2 | deepseek | Value workhorse | Very Low |
| DeepSeek V3.2 Speciale | speciale | High-compute reasoning | Low |
| DeepSeek R1 Free | fallback | Emergency - zero credits | FREE |
| Perplexity Sonar Pro | research | Deep research, multi-step, fact-checking | Medium |
| Perplexity Sonar | sonar | Quick web lookups, single questions | Low |
| Gemini 3.1 Flash Lite | flashlite | Cheapest option, fallback | Very Low |

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
