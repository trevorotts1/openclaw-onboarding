
╔══════════════════════════════════════════════════════════════╗
  MANDATORY TSP CHECK - READ THIS BEFORE ANYTHING ELSE
  DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.
╚══════════════════════════════════════════════════════════════╝

STEP 1: CHECK IF YOU HAVE BEEN TAUGHT THE TEACH YOURSELF PROTOCOL (TSP)

Before you read, learn, or execute ANY instruction in this document, you must
verify that you have already been taught the Teach Yourself Protocol (TSP).

HOW TO CHECK:
- Look in your AGENTS.md, TOOLS.md, or MEMORY.md for any mention of:
  "Teach Yourself Protocol" or "TSP"
- Look in your session context for prior TSP training
- Look for a tab called "Teach Yourself Protocol" in this same document

IF YOU HAVE BEEN TAUGHT TSP:
Proceed to the instructions below. Follow the TSP file storage structure.

IF YOU HAVE NOT BEEN TAUGHT TSP:
STOP IMMEDIATELY. Do not read further. Do not attempt to learn or execute
anything in this document. Tell the user exactly this:

  "I have not been taught the Teach Yourself Protocol yet. I cannot safely
   learn or execute these instructions until I have been taught TSP first.
   Please share the Teach Yourself Protocol tab with me before we proceed.
   Without TSP, I will bloat your core .md files and waste your tokens."

DO NOT PROCEED PAST THIS POINT WITHOUT TSP CONFIRMED.

══════════════════════════════════════════════════════════════════
  TSP FILE STORAGE INSTRUCTIONS (only read this if TSP confirmed)
══════════════════════════════════════════════════════════════════

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

EXECUTION DISCIPLINE - MANDATORY BEFORE YOU START
  *** OPENROUTER SPECIAL RULES - READ THESE CAREFULLY ***
╚══════════════════════════════════════════════════════════════╝

These rules apply every single time you execute instructions from this document.
No exceptions. No shortcuts. No improvising.

RULE 1: READ EVERYTHING BEFORE YOU TOUCH ANYTHING
Read this entire document from top to bottom before executing a single step.
Do not start executing while still reading. Finish reading first. Then start.

RULE 2: DO NOT CHANGE TREVOR'S INTENT
These instructions say exactly what to do. Execute them exactly as written.
- Do NOT reinterpret steps
- Do NOT "improve" the instructions
- Do NOT skip steps because they seem unnecessary
- Do NOT add steps that are not in the document
- Do NOT change the order of steps
If a step says do X, do X. Not Y. Not a better version of X. X.

RULE 3: NEVER MODIFY THESE WITHOUT PERMISSION
- API keys - copy them exactly, character for character
- Terminal commands - run them exactly as written, no edits
- Config values - use the exact values specified
- Model names - use the exact names specified, spelling matters
- File paths - use the exact paths specified
If you are unsure whether something should be changed, the answer is NO.
Ask Trevor first. Do not guess. Do not assume.

RULE 4: NEVER USE openrouter/auto
The auto-router picks models unpredictably and breaks configs. This is
forbidden. Do not use it under any circumstances.

RULE 5: CONFIG SCHEMA - VALID KEYS ONLY
Each model entry in agents.defaults.models ONLY supports these keys:
- alias (string) - optional shortcut name
- params (object) - parameter overrides like temperature, reasoning
- streaming (boolean) - optional streaming override

That is it. Do NOT add custom keys like: contextWindow, maxTokens, context,
max_output, cost, pricing, notes, description, tier, or ANY other key.
Adding invalid keys will break the config and OpenClaw will refuse to start.

RULE 6: BACKUP BEFORE EVERY CHANGE
Before ANY edit to the config file, create a timestamped backup first.
If the backup fails, STOP. Do not continue.

RULE 7: BUILD YOUR CHECKLIST BEFORE EXECUTING
Before you run a single command or make a single change, create a numbered
checklist of every action this document requires you to take.

RULE 8: REPORT WHAT YOU DID
When finished, give the user a clear summary of what was completed,
what commands were run, and what files were changed.

══════════════════════════════════════════════════════════════════


# OpenRouter Setup - Installation and Configuration Guide

This guide walks you through setting up OpenRouter as the model provider for OpenClaw. OpenRouter is a service that gives you access to dozens of AI models (Claude, GPT, Gemini, and many others) through a single API key and a single account. Instead of signing up separately with Anthropic, OpenAI, and Google, you get access to all of them through OpenRouter.

Follow every step in order. Do not skip anything.


## What Is OpenRouter?

Think of OpenRouter like a universal remote control for AI models. Instead of having a separate account and API key for each AI company, you have one OpenRouter account that connects to all of them.

Benefits:
- One API key for all models
- One billing account instead of many
- Easy switching between models
- Access to models you might not be able to get directly
- Built-in fallback if one model goes down

OpenClaw has built-in support for OpenRouter. You do NOT need to set up a separate "provider" section. Just add your API key and configure your models.


## Step 1: Create an OpenRouter Account

1. Open your web browser.
2. Go to https://openrouter.ai
3. Click "Sign Up" or "Log In" in the top right corner.
4. Create an account using Google, GitHub, or your email address.
5. Once logged in, you will see your dashboard.


## Step 2: Create an API Key

1. While logged in to OpenRouter, go to https://openrouter.ai/keys
2. Click the "Create Key" button.
3. Give your key a name (something like "OpenClaw" so you remember what it is for).
4. A key will appear. It starts with "sk-or-" followed by a long string of characters.
5. COPY THIS KEY IMMEDIATELY. You will only see it once. If you lose it, you will need to create a new one.
6. Save the key somewhere safe. You will need it in Step 4.


## Step 3: Add Credits to Your Account

OpenRouter is pay-as-you-go. You add credits, and they get used as you make requests to AI models. Different models cost different amounts per request.

1. Go to https://openrouter.ai/credits
2. Click "Add Credits."
3. Enter an amount. For getting started, $10 to $20 is plenty. You can always add more later.
4. Complete the payment.
5. You should see your credit balance update on the dashboard.

Important note: Some models are free (like DeepSeek R1 Free). Even without credits, you can use free models. But paid models require credits.


## Step 4: Back Up Your Current Config File

Before you change anything, create a backup. This is mandatory. No exceptions.

1. Open your terminal.

2. Create a backup folder (if it does not already exist):

   mkdir -p ~/openclaw-backup-configs

3. Back up your current config:

   cp ~/.openclaw/openclaw.json ~/openclaw-backup-configs/openclaw-backup-$(date +%Y-%m-%d-%H%M%S).json

4. Verify the backup exists and is not empty:

   ls -la ~/openclaw-backup-configs/

   You should see your backup file listed with a size greater than 0.

5. If the backup failed or the file is empty, STOP. Fix the backup issue before continuing.


## Step 5: Add Your API Key to OpenClaw

There are two ways to add your API key. Choose one.

### Option A: Add to the Config File (Simpler)

1. Open the config file in a text editor:

   nano ~/.openclaw/openclaw.json

   (If you prefer a different text editor, use that instead of nano.)

2. Find or create the "env" section near the top of the file. Add your OpenRouter API key:

   "env": {
     "OPENROUTER_API_KEY": "sk-or-YOUR-KEY-HERE"
   }

   Replace sk-or-YOUR-KEY-HERE with the actual key you copied in Step 2.

3. Save the file and close the editor. In nano, press Ctrl+X, then Y, then Enter.

### Option B: Use the Auth Profile (More Secure)

1. Run this command in your terminal:

   openclaw auth set openrouter:default --key "sk-or-YOUR-KEY-HERE"

   Replace sk-or-YOUR-KEY-HERE with your actual key.

2. This stores the key in your system keychain instead of in a plain text file.


## Step 6: Configure Your Models

This is the most important step. You are telling OpenClaw which AI models to use and how to use them.

Important rules before you start:
- Model IDs must use the format: openrouter/author/model-name
- Each model entry can ONLY have these keys: alias, params, streaming
- Do NOT add keys like contextWindow, maxTokens, cost, or notes. They will break the config.
- Temperature should be 0.3 for all models EXCEPT Kimi K2.5 which should be 1.0
- Do NOT use openrouter/auto. Ever.

Open your config file:

   nano ~/.openclaw/openclaw.json

Add the following model configuration. If you already have an agents section, merge this into it. Do NOT delete your existing models or settings.

Here is the recommended full configuration:

   {
     "env": {
       "OPENROUTER_API_KEY": "sk-or-YOUR-KEY-HERE"
     },
     "agents": {
       "defaults": {
         "model": {
           "primary": "openrouter/minimax/minimax-m2.5",
           "fallbacks": [
             "openrouter/moonshotai/kimi-k2.5",
             "openrouter/deepseek/deepseek-r1-0528:free"
           ]
         },
         "thinkingDefault": "medium",
         "models": {
           "openrouter/anthropic/claude-opus-4.6": {
             "params": {
               "temperature": 0.3,
               "reasoning": { "effort": "medium" }
             }
           },
           "openrouter/anthropic/claude-sonnet-4.6": {
             "params": {
               "temperature": 0.3,
               "reasoning": { "effort": "medium" }
             }
           },
           "openrouter/anthropic/claude-haiku-4.5": {
             "params": {
               "temperature": 0.3,
               "reasoning": { "effort": "medium" }
             }
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
           "openrouter/openai/gpt-5.2-codex": {
             "params": {
               "temperature": 0.3,
               "reasoning": { "effort": "medium" }
             }
           },
           "openrouter/openai/gpt-5-mini": {
             "params": {
               "temperature": 0.3,
               "reasoning": { "effort": "medium" }
             }
           },
           "openrouter/openai/gpt-5-nano": {
             "params": {
               "temperature": 0.3,
               "reasoning": { "effort": "medium" }
             }
           },
           "openrouter/moonshotai/kimi-k2.5": {
             "params": {
               "temperature": 1.0
             }
           },
           "openrouter/minimax/minimax-m2.5": {
             "params": {
               "temperature": 0.3,
               "reasoning": { "effort": "high" }
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
           "openrouter/perplexity/sonar-pro-search": {
             "params": {
               "temperature": 0.3
             }
           }
         }
       }
     }
   }

Save and close the file.


## Step 7: Validate and Restart OpenClaw

1. Validate your config to make sure there are no errors:

   openclaw doctor

2. If validation passes (no errors), restart the gateway:

   openclaw gateway restart

3. If validation FAILS, restore your backup immediately:

   cp ~/openclaw-backup-configs/openclaw-backup-LATEST.json ~/.openclaw/openclaw.json
   openclaw gateway restart

   Then review what went wrong and try again.


## Step 8: Verify It Works

1. Send a test message to your OpenClaw agent through whatever channel you use (Telegram, WhatsApp, etc.). Confirm you get a response back.

2. Check which model is active by checking the status.

3. Try switching models. Type /model opus to switch to Claude Opus. You should see a confirmation.

4. Switch back to the primary model: /model minimax


## Step 9: Save the Full Documentation

Following the TSP (Teach Yourself Protocol):

1. Save the complete OpenRouter guide to:
   ~/Downloads/openclaw-master-files/openrouter-setup/openrouter-setup-instructions.md

2. Add a brief summary to AGENTS.md (do not paste the full document):

   ## Intelligent Model Routing - THINK BEFORE YOU ACT
   Before executing ANY task, evaluate which model fits best and switch if needed.
   Key rules:
   - Kimi K2.5 CANNOT do tool calls. Never route tool tasks to Kimi.
   - MiniMax M2.5 is the daily workhorse (cheap + tools + high thinking).
   - Opus is the specialist (complex strategy, writing, client-facing).
   - Perplexity is the research model (all fact-checking and web search).
   Full details: See openrouter-setup-full.md

3. Add a brief summary to TOOLS.md:

   ## OpenRouter Model Configuration
   18 models configured via OpenRouter. Primary: MiniMax M2.5.
   Temperature: 0.3 for all models, 1.0 for Kimi K2.5 only.
   Config file: ~/.openclaw/openclaw.json
   Always back up before editing. Always validate with openclaw doctor after.
   Full reference: ~/Downloads/openclaw-master-files/openrouter-setup/openrouter-setup-full.md


## What the Models Are For (Quick Reference)

Here is a simple overview of which models to use for which tasks:

| Model | Alias | Best For | Cost Level |
|-------|-------|----------|------------|
| Claude Opus 4.6 | opus | Complex strategy, architecture, critical work | High |
| Claude Sonnet 4.6 | sonnet | Balanced quality and speed | Medium-High |
| Claude Haiku 4.5 | haiku | Fast responses | Medium |
| Gemini 3.1 Pro | gemini31 | Long document analysis | Medium |
| Gemini 3 Flash | flash | Quick tasks, large context | Low-Medium |
| GPT 5.2 Codex | codex | Code architecture and debugging | Low-Medium |
| GPT-5 Mini | gptmini | Mid-range tasks | Low |
| GPT-5 Nano | gptnano | Simple questions, cheap lookups | Very Low |
| Kimi K2.5 | kimi | Code generation, chat (NO tool calls) | Low |
| MiniMax M2.5 | minimax | RECOMMENDED PRIMARY - daily tasks, tool calls | Low |
| Mistral Small Creative | creative | All writing and content creation | Very Low |
| Qwen 3.5 Plus | qwen | General purpose, large context | Low-Medium |
| GLM-5 | glm5 | Systems design, agent workflows | Low-Medium |
| DeepSeek V3.2 | deepseek | Value workhorse | Very Low |
| DeepSeek V3.2 Speciale | speciale | High-compute reasoning | Low |
| DeepSeek R1 Free | fallback | Emergency - zero credits | FREE |
| Perplexity Sonar Pro | research | All research and fact-checking | Medium |


## Installation Complete - What is Next?

You now have OpenRouter configured with a full model roster. Here is what you set up:

- An OpenRouter account with an API key
- Credits for pay-as-you-go model access
- 18 models configured in your OpenClaw config file
- A primary model (MiniMax M2.5) with fallbacks
- Thinking/reasoning settings customized per model

To learn how to use model routing, thinking levels, and cost management, see the INSTRUCTIONS.md file.
To see real examples of model switching and configuration scenarios, see the EXAMPLES.md file.
For the complete unabridged reference, see the openrouter-setup-full.md file.
