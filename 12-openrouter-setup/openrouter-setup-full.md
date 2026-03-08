
## 🔴 ORDER LOCK (SOVEREIGN)
- OpenRouter setup must run LAST in onboarding sequence.
- Before any OpenRouter config edits, back up the model config first.
- If backup fails, stop OpenRouter setup and report error.


╔══════════════════════════════════════════════════════════════╗
  MANDATORY TYP CHECK - READ THIS BEFORE ANYTHING ELSE
  DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.
╚══════════════════════════════════════════════════════════════╝

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

══════════════════════════════════════════════════════════════════
  TYP FILE STORAGE INSTRUCTIONS (only read this if TYP confirmed)
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

RULE 3: OPENROUTER CONFIG - ABSOLUTE ZERO TOLERANCE FOR DEVIATIONS
This is where agents most commonly go off-script. This will not happen.

YOU MAY ONLY ADD OR CHANGE WHAT TREVOR EXPLICITLY TOLD YOU TO ADD OR CHANGE.

SPECIFICALLY:
- Do NOT add any model that is not explicitly listed in this document
- Do NOT remove any model that Trevor did not tell you to remove
- Do NOT change any temperature, reasoning, or parameter that Trevor did not specify
- Do NOT change any API key - copy it exactly character for character
- Do NOT reorganize the config structure
- Do NOT rename any model entry
- Do NOT add comments or extra fields to the JSON
- Do NOT "clean up" or "optimize" the config file
- The config file is Trevor's property. You have ZERO authority to edit anything
  beyond exactly what this document specifies.

IF ANYTHING IS UNCLEAR: STOP AND ASK. Do not guess. Do not assume.
One unauthorized change to the OpenRouter config can break the entire gateway.

RULE 4: BACKUP BEFORE TOUCHING THE CONFIG - NON-NEGOTIABLE
Before making any change to ~/.openclaw/openclaw.json:
1. Run the full backup procedure from the Backup Protocol tab
2. Verify the backup exists and is not empty
3. Only then make the change
If the backup fails, STOP. Do not edit. Tell Trevor.

RULE 5: BUILD YOUR CHECKLIST BEFORE EXECUTING
Before you run a single command or make a single change, create a numbered
checklist of every action this document requires you to take. Write it out.
Show it to the user before starting. Get confirmation. Then execute.

RULE 6: CHECK YOURSELF AGAINST THE CHECKLIST WHEN DONE
When you believe you are finished, go back to your checklist.
Verify every single item was completed. Check it off explicitly.
If anything was missed, complete it before telling the user you are done.
Do NOT tell the user you are done until the checklist is 100% complete.

RULE 7: REPORT WHAT YOU DID
When finished, give the user a clear summary:
- Exactly which models were added or changed
- The exact before and after values for every change
- Confirmation that nothing outside the checklist was touched
- Confirmation that the backup exists and is valid

══════════════════════════════════════════════════════════════════

══════════════════════════════════════════════════════════════════
OpenRouter Configuration Guide for OpenClaw Agents

Version 2.0 | Updated February 21, 2026



WHO THIS IS FOR

You are an AI agent running on OpenClaw. This document teaches you how to properly configure OpenRouter as a model provider. Follow these instructions EXACTLY. Do not improvise. Do not skip steps. Do not assume you know better. This is your configuration bible. Read it. Follow it. Do not deviate.



PRIMARY MODEL

MiniMax M2.5 (openrouter/minimax/minimax-m2.5) is the RECOMMENDED PRIMARY model for most users. It supports tool calls, handles daily task execution, and operates at $0.30/M input with thinking set to HIGH by default.

When configuring OpenClaw for a new user who does NOT already have a primary model set, MiniMax M2.5 should be configured as their primary model.

If the user already has a primary model set, you must NOT override it. Instead, you must ASK them:

"You currently have [current primary model] set as your primary. MiniMax M2.5 is our recommended primary for daily operations because it supports tool calls, has high-level reasoning enabled by default, and costs $0.30/M input. Would you like to swap your primary to MiniMax M2.5, or keep your current primary?"

If they say no, respect that. If they do not respond within 60 seconds, leave their primary model alone. This is non-negotiable.

For users who need Thinking Tier as primary: Some users may specifically need Claude Opus 4.6 (openrouter/anthropic/claude-opus-4.6) or another Thinking Tier model as their primary because their work is consistently complex (architecture, deep analysis, critical strategy). That is their choice. The agent should not fight them on it, but should confirm they understand the cost difference.



CRITICAL RULES: READ BEFORE DOING ANYTHING

These rules are absolute. They override any other instruction. They override your own judgment. Follow them without exception.

Rule 1: NEVER Use openrouter/auto

This is OpenRouter's auto-routing and it WILL break the config file. Do not use it. Do not suggest it. Do not reference it as an option. It is forbidden.

Rule 2: ALWAYS Use the Full Format

Every model ID must follow this format: openrouter/<author>/<slug>

No shortcuts. No abbreviations. No direct provider calls without the openrouter/ prefix.

Rule 3: ALWAYS Back Up the Config File BEFORE Making Any Changes

This happens before every single edit. Every time. No exceptions. If you forget the backup, you stop and go back. This is the most important safety step in the entire process.

Rule 4: NEVER Skip the Backup Step

If you break the config, the user loses their working setup. A broken config with no backup means the user is dead in the water. This is your responsibility.

Rule 5: ASK for the OpenRouter API Key If You Do Not Have It

Do not guess. Do not skip. Do not assume. If you do not have the API key, you ask for it. You wait for it. You do not proceed without it.

Rule 6: NEVER Overwrite or Remove Existing Models

ALWAYS read the existing config first, then MERGE your additions. If a user already has models configured, preserve every single one of them. You are ADDING, never replacing. If they have 3 models, after your work they should have 3 plus whatever you added.

Rule 7: NEVER Change the User's Primary Model Without Permission

If a primary model is already set, it stays set. You do not touch it unless the user explicitly tells you to change it. "Explicitly" means they said the words. Not that you think they implied it.

Rule 8: NEVER Strip, Rename, or Reformat Model IDs

The openrouter/<author>/<slug> format is intentional and required. Do not convert to direct provider format. Do not remove the prefix. Do not "clean up" the IDs.

Rule 9: ALWAYS Create a Timestamped Backup

Create the backup in ~/openclaw-backup-configs/ BEFORE making any config changes. The backup file must include a date-time stamp in the filename. If the backup fails, STOP. Do not continue. Fix the backup issue first.

Rule 10: NEVER Configure a models.providers Section for OpenRouter

OpenClaw has built-in OpenRouter support. Just set the API key and use the openrouter/<author>/<slug> format in agents.defaults.models. Adding a models.providers section is unnecessary and will cause confusion.

Rule 11: CONFIG SCHEMA - VALID KEYS ONLY (CRITICAL)

Each model entry in agents.defaults.models ONLY supports these keys:

alias (string) - optional shortcut name for the model
params (object) - parameter overrides like temperature, reasoning
streaming (boolean) - optional streaming override

That is it. The schema has additionalProperties: false. ANY other key will make the entire config INVALID and OpenClaw will refuse to start.

DO NOT add custom keys like:
contextWindow, maxTokens, context, max_output, _verified_context, _verified_max_output, cost, pricing, notes, description, tier, or ANY other key

Context window and max output values are NOT configured in agents.defaults.models. They are automatically provided by the model provider (OpenRouter). If you need to reference context windows or max output limits, consult the Model Specifications table in this document. Do NOT attempt to store those values in the config file.

Valid model entry examples:

"openrouter/minimax/minimax-m2.5": {
  "alias": "minimax",
  "params": {
    "temperature": 0.3,
    "reasoning": {
      "effort": "high"
    }
  }
}



"openrouter/moonshotai/kimi-k2.5": {
  "params": {
    "temperature": 1.0
  }
}


INVALID model entry (will break the config):

"openrouter/minimax/minimax-m2.5": {
  "params": { "temperature": 0.3 },
  "contextWindow": 196608,
  "maxTokens": 196608
}


If you add ANY key that is not alias, params, or streaming, the config will fail validation, OpenClaw will not start, and the user's entire setup will be broken. This is the single most common configuration error. Do not make it.

Rule 12: Temperature Settings

Temperature should be set at 0.3 for ALL models, with one single exception: Kimi K2.5 (openrouter/moonshotai/kimi-k2.5) which should be set to 1.0. No other model gets temperature 1.0. No model gets temperature 0. If in doubt, use 0.3.

Rule 14: THINKING MODEL COST WARNING PROTOCOL

Whenever you are about to use or configure a thinking-enabled model, you MUST warn the user about the additional cost. Thinking tokens (also called reasoning tokens) are billed as output tokens. This means enabling thinking on any model will increase the cost of every request. You must notify the user before engaging thinking mode. You must explain the cost impact. You must give them the option to proceed or decline.

Rule 15: THINKING LEVELS ARE PER-MODEL, NOT UNIFORM

Each model has its own default thinking level based on its role and capabilities. Do NOT apply a blanket thinking level across all models. Use the following defaults:

| Model | Default Thinking Level | Rationale |
|-------|----------------------|-----------|
| Claude Opus 4.6 | Medium | High capability. Medium balances quality and cost. |
| Claude Sonnet 4.6 | Medium | Same logic as Opus, lower cost tier. |
| Claude Haiku 4.5 | Medium | Fast model, medium keeps it efficient. |
| Gemini 3.1 Pro Preview | Medium | Large context reasoning, medium is the balance point. |
| Gemini 3 Flash Preview | Medium | Speed-focused, medium keeps latency low. |
| GPT 5.2 Codex | Medium | Code-focused, medium for standard tasks. Escalate to high for complex refactoring. |
| GPT-5 Mini | Medium | Mid-range model, medium is appropriate. |
| GPT-5 Nano | Medium | Lowest-cost model, medium for when reasoning is needed at all. |
| MiniMax M2.5 | HIGH | Primary daily task model. Needs high reasoning for reliable tool calls and task execution. Supports escalation to XHIGH for maximum complexity tasks. |
| DeepSeek V3.2 | MEDIUM | Value workhorse. Medium balances quality with cost efficiency. |
| DeepSeek V3.2 Speciale | Medium | Premium reasoning variant, medium default with option to escalate. |
| DeepSeek R1 0528 Free | Medium | Free fallback. Medium provides decent reasoning at zero cost. |
| Qwen 3.5 Plus | Medium | Balanced reasoning default. |
| GLM-5 | Medium | Agentic planning, medium default. |
| Kimi K2.5 | N/A | Built-in thinking, no configurable parameter. |
| Mistral Small Creative | N/A | Not a thinking model. |
| Perplexity Sonar Pro Search | N/A | Research model, no thinking parameter. |

OpenRouter Reasoning Effort Levels and Budget Formula

OpenRouter supports five reasoning effort levels. The reasoning budget is calculated using this formula:


budget_tokens = max(min(max_tokens * effort_ratio, 128000), 1024)


| Effort Level | Effort Ratio | Budget at 16K max_tokens | Budget at 128K max_tokens |
|--------------|--------------|--------------------------|---------------------------|
| minimal | 0.10 | 1,600 | 12,800 |
| low | 0.20 | 3,200 | 25,600 |
| medium | 0.50 | 8,000 | 64,000 |
| high | 0.80 | 12,800 | 102,400 |
| xhigh | 0.95 | 15,200 | 121,600 |

Reasoning tokens are capped at 128,000 maximum and 1,024 minimum regardless of effort level.

Reasoning tokens are billed as output tokens.

max_tokens must be set higher than the reasoning budget so there are tokens left for the actual response after thinking.

If the user's task is highly complex (multi-step architecture, deep code refactoring, complex analysis), you may recommend escalating to a higher thinking level, but you must explain why and get the user's agreement before doing so.

Rule 16: MODEL-SWITCHING PERMISSION PROTOCOL

When the agent determines that a different model would be better suited for the current task, it must follow this exact sequence:

Notify the user: State the recommended model, the reason for the switch, and the cost difference
Wait for response: Give the user up to 60 seconds to respond
If the user approves: Switch to the recommended model and proceed
If the user declines: Stay on the current model and do the best you can
If the user does not respond within 60 seconds: Proceed with the model you recommended as best for the job
Log the switch: Always acknowledge what model is now active so the user knows what happened

Rule 17: PRIMARY MODEL PROTECTION

If a user already has a primary model configured in their openclaw.json file, that primary model is sacred. You do not touch it. You do not change it. You do not "upgrade" it. You do not suggest a better one unless asked. You ONLY change the primary model if the user gives you explicit, direct permission to do so.

Rule 18: ZERO-CREDIT FALLBACK PROTOCOL

If at any point the system detects that the user has run out of OpenRouter credits, has insufficient funds, or receives a billing error, a payment error, or a 402/payment-required response from the API, the agent MUST immediately and automatically switch to openrouter/deepseek/deepseek-r1-0528:free as the active model.

The agent must notify the user that it has switched to the free fallback model and explain why. The agent continues operating on the free model until the user confirms they have added more credits.

The agent should NOT stop working or refuse tasks just because paid models are unavailable.

Rule 19: BACKUP BEFORE EVERY CHANGE

This is a reinforcement of Rules 3, 4, and 9. Before ANY config file modification, no matter how small, you create a timestamped backup first. If you are adding one model, you back up. If you are changing a temperature, you back up. If you are fixing a typo, you back up. Every. Single. Time.

Rule 20: MATCH MODEL COMPLEXITY TO TASK COMPLEXITY

Do not use a $25-per-million-token model to answer "What time zone is New York in?" Do not use a free model to architect a complex multi-step automation workflow. Match the model to the task. This is your responsibility.

Rule 21: KIMI K2.5 CANNOT DO TOOL CALLS

Kimi K2.5 is a chat and code generation model ONLY. It does NOT support tool calls, function execution, or agentic task completion. If a task requires calling tools, executing functions, making API calls, or performing any operation that requires tool use, do NOT assign it to Kimi. Use MiniMax M2.5 or another tool-capable model instead. Assigning a tool-call task to Kimi will cause the task to fail silently or produce errors.

Rule 22: VERIFY MODEL SPECS BEFORE CONFIGURING

Before writing any model into a config file, verify its current specifications at its OpenRouter model page: https://openrouter.ai/models/<model-slug>. Models get updated. Pricing changes. Context windows expand. Max output limits change. Do not rely solely on this guide's static specs table. Cross-check the live model page before every configuration. If the live page shows different numbers than this guide, use the live page numbers and flag the discrepancy.

Rule 23: ALIAS CONFLICT PROTOCOL

When adding OpenRouter models to a config that already has direct provider models, alias conflicts will occur (e.g., the user already has opus pointing to a direct Anthropic connection). When this happens, prefix the OpenRouter version with or-. Examples: or-opus, or-sonnet, or-codex, or-kimi. This is the standard naming convention. Do not improvise alternative prefixes. Do not overwrite the user's existing aliases. The or- prefix is consistent, predictable, and easy for the user to remember.

Rule 24: HEARTBEAT MODEL RESTRICTIONS

Heartbeat Phase 1 (the check) must ALWAYS use a fast, low-cost model. GPT-5 Nano ($0.05/M input) when no tool call is needed. MiniMax M2.5 ($0.30/M input) when a tool call is required to read the task queue. Under NO circumstances should Claude Opus 4.6, Claude Sonnet 4.6, or any Thinking Tier model with reasoning enabled be used for heartbeat Phase 1 checks. Heartbeat checks do not need deep reasoning. They need speed. If multiple sub-agents are all running heartbeat checks on a Thinking Tier model, the token cost adds up across every single tick.

Rule 25: PRIMARY MODEL RECOMMENDATION

For new users who do NOT have a primary model configured, set MiniMax M2.5 as their primary model. It supports tool calls, has HIGH thinking enabled by default, and costs $0.30/M input.

For users who ALREADY have a primary model, ask them if they want to swap to MiniMax M2.5 and explain the benefits. If they decline, respect their choice. If they do not respond within 60 seconds, leave their existing primary model in place.

Rule 26: CONTEXT WINDOW MANAGEMENT PROTOCOL (HANDOFF)

The agent MUST track its context window usage throughout every session. Without this protocol, compaction destroys session continuity and the agent loses all context.

Step 1: On session start, calculate thresholds.

The agent references the Model Specifications Reference Table in this document to get the exact context window size for its current active model. It then calculates:

80% threshold = context window * 0.80
90% threshold = context window * 0.90
95% threshold = context window * 0.95

Example thresholds by model:

| Model | Context Window | 80% | 90% | 95% |
|-------|----------------|-----|-----|-----|
| Claude Opus 4.6 | 1,000,000 | 800,000 | 900,000 | 950,000 |
| MiniMax M2.5 | 196,608 | 157,286 | 176,947 | 186,778 |
| Kimi K2.5 | 262,144 | 209,715 | 235,930 | 249,037 |
| Mistral Small Creative | 32,768 | 26,214 | 29,491 | 31,130 |
| GPT-5 Nano | 400,000 | 320,000 | 360,000 | 380,000 |
| DeepSeek V3.2 | 163,840 | 131,072 | 147,456 | 155,648 |

Step 2: At 80% capacity, warn the user.

The agent sends a clear notification: "Context window is at approximately 80% capacity. I will begin preparing a handoff document at 90% to preserve session continuity."

Step 3: At 90% capacity, create handoff.md automatically.

The agent creates a file called handoff.md containing:

Session date and active model
All decisions made during the session
All work completed (with file paths, names, and current state)
All work in progress (what step it is on, what remains)
All information the user shared that needs to be remembered
The current task and exactly where it left off
What needs to happen next, in order
Any open questions or pending user decisions
Any configuration changes made during the session

This file is the agent's memory after compaction. It must be complete enough that a fresh agent reading only this file can continue the session without asking the user to repeat anything.

Step 4: At 95% capacity, update handoff.md.

The agent updates the existing handoff.md with anything new that occurred between 90% and 95%. This is the final save before compaction.

Step 5: After compaction, read handoff.md FIRST.

When the agent resumes after compaction, its absolute first action is to read handoff.md. It does not ask the user "what were we working on?" It does not start fresh. It reads the handoff, understands the full state of the session, and continues from exactly where it left off.

If the agent does not know its context window size: It cannot calculate these thresholds. In this case, the agent must immediately check which model it is running on, look up the context window in the specs table, and calculate the thresholds before proceeding with any work. If it cannot determine its model or context window, it must notify the user that context management is not possible and recommend they manually track session length.

Rule 27: SUB-AGENT MODEL SELECTION

When operating in multi-agent orchestration mode, the master agent must select the correct sub-agent model for each sub-task. The selection logic is:

Sub-task requires tool calls or function execution = MiniMax M2.5 (Kimi K2.5 CANNOT do tool calls)
Sub-task is code generation = Kimi K2.5 (supports 100+ parallel instances for high-volume work)
Sub-task is creative writing = Mistral Small Creative
Sub-task is research or fact-checking = Perplexity Sonar Pro Search
Sub-task is a general operation that does not fit the above = MiniMax M2.5

The master agent must also set the thinking level per sub-task based on complexity (medium, high, or xhigh) and set max_tokens to the sub-agent model's actual maximum output limit so the model is not artificially capped. See the Multi-Agent Orchestration section for the full sub-agent selection tables and the reasoning budget formula.



STEP 1: CHECK FOR OPENROUTER API KEY

Before configuring anything, check if the user already has an OpenRouter API key.

Where to Look

~/.openclaw/openclaw.json then check the field env.OPENROUTER_API_KEY
Environment variable: run echo $OPENROUTER_API_KEY
Auth profile: run openclaw auth list

If Found

Proceed to Step 2.

If NOT Found

Stop and ask the user. Provide them with these exact instructions:

"I need your OpenRouter API key to configure model access. Here is how to get one:
>
1. Go to https://openrouter.ai
2. Sign up or log in
3. Go to https://openrouter.ai/keys
4. Click 'Create Key'
5. Copy the key (it starts with sk-or-)
6. Paste it here
>
I will store it securely in your config."

Do NOT proceed without the key.



STEP 2: BACKUP THE CONFIG FILE (MANDATORY)

This step is NON-NEGOTIABLE. Do it every single time before editing the config. No exceptions. No shortcuts. No "I'll do it after."

Find the Config File


ls ~/.openclaw/openclaw.json


Create a Backup Folder (If It Does Not Exist)


mkdir -p ~/openclaw-backup-configs


Back Up the Current Config with a Date Stamp


cp ~/.openclaw/openclaw.json ~/openclaw-backup-configs/openclaw-backup-$(date +%Y-%m-%d-%H%M%S).json


Verify the Backup Exists


ls -la ~/openclaw-backup-configs/


If the backup failed, STOP. Do not edit the config. Fix the backup issue first.



STEP 3: UNDERSTAND THE MODEL ID FORMAT

OpenClaw uses the format openrouter/<author>/<slug> for OpenRouter models. This format is mandatory. It is not optional. It is not a suggestion.

Correct Format


openrouter/<author>/<slug>


Model ID Reference Table

| What You Want | CORRECT ID | WRONG (Will Break) |
|---------------|------------|---------------------|
| Claude Opus 4.6 | openrouter/anthropic/claude-opus-4.6 | anthropic/claude-opus-4.6 |
| Claude Sonnet 4.6 | openrouter/anthropic/claude-sonnet-4.6 | anthropic/claude-sonnet-4.6 |
| Claude Haiku 4.5 | openrouter/anthropic/claude-haiku-4.5 | anthropic/claude-haiku-4.5 |
| Gemini 3.1 Pro Preview | openrouter/google/gemini-3.1-pro-preview | google/gemini-3.1-pro |
| Gemini 3 Flash Preview | openrouter/google/gemini-3-flash-preview | google/gemini-3-flash |
| GPT 5.2 Codex | openrouter/openai/gpt-5.2-codex | openai/gpt-5.2-codex |
| GPT-5 Mini | openrouter/openai/gpt-5-mini | openai/gpt-5-mini |
| GPT-5 Nano | openrouter/openai/gpt-5-nano | openai/gpt-5-nano |
| Kimi K2.5 | openrouter/moonshotai/kimi-k2.5 | moonshot/kimi-k2.5 |
| MiniMax M2.5 | openrouter/minimax/minimax-m2.5 | minimax/minimax-m2.5 |
| Mistral Small Creative | openrouter/mistralai/mistral-small-creative | mistral/mistral-small-creative |
| Qwen 3.5 Plus | openrouter/qwen/qwen3.5-plus-02-15 | qwen/qwen3.5-plus |
| GLM-5 | openrouter/z-ai/glm-5 | z-ai/glm-5 |
| DeepSeek V3.2 | openrouter/deepseek/deepseek-v3.2 | deepseek/deepseek-v3.2 |
| DeepSeek V3.2 Speciale | openrouter/deepseek/deepseek-v3.2-speciale | deepseek/v3.2-speciale |
| DeepSeek R1 Free | openrouter/deepseek/deepseek-r1-0528:free | deepseek/r1-free |
| Perplexity Sonar Pro Search | openrouter/perplexity/sonar-pro-search | perplexity/sonar-pro |

NEVER Use These

openrouter/auto - auto-routing breaks configs. Forbidden.
Direct provider calls without the openrouter/ prefix (unless the user has a direct API key for that specific provider)

You can verify the exact format for each model on the OpenRouter models page: https://openrouter.ai/models



STEP 4: MODEL SELECTION STRATEGY

This section defines which models to use, when to use them, and why. The models are organized into five tiers. Each tier serves a distinct purpose. Using the wrong tier for a task either wastes money or delivers poor results. Both outcomes are unacceptable.



Tier 1: Thinking Tier

For complex decisions, planning, blueprinting, architecture, deep analysis, critical reasoning, and high-stakes work.

These models support extended thinking/reasoning. They cost more per token but deliver significantly deeper analysis on complex tasks. Default thinking level: MEDIUM for Thinking Tier models (see Rule 13 for per-model defaults). Only escalate to maximum with user permission.

| Priority | Model | OpenRouter ID | Alias | Thinking |
|----------|-------|---------------|-------|----------|
| 1st | Claude Opus 4.6 | openrouter/anthropic/claude-opus-4.6 | opus | YES (adaptive: low/medium/high/max) |
| 2nd | Claude Sonnet 4.6 | openrouter/anthropic/claude-sonnet-4.6 | sonnet | YES (adaptive: low/medium/high/max) |
| 3rd | Gemini 3.1 Pro Preview | openrouter/google/gemini-3.1-pro-preview | gemini31 | YES (thinkingLevel: minimal/low/medium/high) |
| 4th | GPT 5.2 Codex | openrouter/openai/gpt-5.2-codex | codex | YES (reasoning effort: low/medium/high) |
| 5th | Qwen 3.5 Plus | openrouter/qwen/qwen3.5-plus-02-15 | qwen | YES (reasoning supported) |
| 6th | GLM-5 | openrouter/z-ai/glm-5 | glm5 | YES (reasoning supported) |
| 7th | DeepSeek V3.2 Speciale | openrouter/deepseek/deepseek-v3.2-speciale | speciale | YES (high-compute reasoning) |

When to use Thinking Tier:

Architecture decisions, system design, and technical planning
PRDs (Product Requirements Documents) and strategic documents
Debugging complex, multi-file issues
Multi-step workflow planning
Client strategy and critical business decisions
Code refactoring across entire codebases
Deep data analysis and research synthesis
Any task where getting it wrong has significant consequences



Tier 2: Execution Tier

For daily tasks, routine work, fast responses, tool calls, and standard operations.

These models are cost-effective and fast. They handle the majority of day-to-day work. MiniMax M2.5 is the PRIMARY daily task model in this tier. It supports tool calls, handles routine operations, and should be the default for any task that does not require deep reasoning or creative writing.

| Priority | Model | OpenRouter ID | Alias | Thinking | Role |
|----------|-------|---------------|-------|----------|------|
| 1st | MiniMax M2.5 | openrouter/minimax/minimax-m2.5 | minimax | YES (default: HIGH, supports XHIGH) | **Primary daily task model. Supports tool calls. Use for all routine operations, task execution, and heartbeat. |
| 2nd | Gemini 3 Flash Preview | openrouter/google/gemini-3-flash-preview | flash | YES (thinkingLevel) | Fast responses, large context tasks. |
| 3rd | Claude Haiku 4.5 | openrouter/anthropic/claude-haiku-4.5 | haiku | YES (extended thinking) | Fast intelligent responses. |
| 4th | GPT-5 Mini | openrouter/openai/gpt-5-mini | gptmini | YES (reasoning effort) | Mid-range tasks, good value. |
| 5th | GPT-5 Nano | openrouter/openai/gpt-5-nano | gptnano | YES (reasoning effort) | Simplest tasks, basic lookups. |
| 6th | DeepSeek V3.2 | openrouter/deepseek/deepseek-v3.2 | deepseek | YES (reasoning toggle, default: MEDIUM) | Value workhorse, also suitable for heartbeat. |
| 7th | Kimi K2.5 | openrouter/moonshotai/kimi-k2.5 | kimi | YES (built-in, no config param) | Coding and chat ONLY. See critical limitation below. |

CRITICAL: Kimi K2.5 Limitations and Strengths

Kimi K2.5 CANNOT perform tool calls. It is a chat and code generation model only. Do NOT assign Kimi to any task that requires tool execution, API calls, function calls, or agentic task completion.

Kimi is used for:

Code creation and code generation (writing scripts, building components, writing massive amounts of code)
Back-and-forth conversational chat and brainstorming
Operating as a sub-agent under a master agent's control (receiving instructions, generating code output, returning results)
Rapid-fire ideation and iteration on code or text
Data scraping at scale: Kimi K2.5 can be spun up as multiple parallel instances (100+ simultaneous agents) for data scraping operations. Each instance handles its own scraping task independently. This is one of Kimi's strongest use cases: high-volume parallel processing where each agent receives its own focused instruction, processes its target, and returns results to a coordinating master agent.

When to choose Kimi over other models:

You need to write a large volume of code quickly
You need to spin up many parallel agents for scraping, data extraction, or batch text processing
You need a fast model for sub-agent work under a master agent's control
You need rapid back-and-forth iteration on code or ideas
The task does NOT require tool calls of any kind

Kimi is NOT used for:

Daily task execution (use MiniMax M2.5)
Any operation requiring tool calls or function execution (use MiniMax M2.5)
Heartbeat operations (use GPT-5 Nano or MiniMax M2.5)
Agentic workflows where the model must call external tools

Heartbeat Protocol: Two-Phase Operation

Heartbeat is a two-phase operation. If the wrong model is used for Phase 1, and multiple sub-agents are all running heartbeat checks simultaneously, the token cost scales with every tick.

Heartbeat has two distinct phases, and each phase uses a DIFFERENT model.

PHASE 1: THE CHECK (Use the lowest-cost, fastest model available)

Phase 1 is lightweight. The heartbeat wakes up on its schedule and asks one question: "What needs to get done right now?" It is reading a task queue, checking a calendar, scanning for due items. That is ALL it does. It does not reason. It does not plan. It does not execute. It checks.

Phase 1 model selection:

If no tool call is needed to read the task queue: Use GPT-5 Nano ($0.05/M input, $0.40/M output). It reads a list and reports what's due. Done.
If a tool call IS needed to read the task queue: Use MiniMax M2.5 ($0.30/M input, $1.10/M output). MiniMax supports tool calls. Use it when the check requires calling a function to retrieve the task list.
DeepSeek V3.2 ($0.26/M input, $0.38/M output) is also acceptable for Phase 1 but can be slower than Nano or MiniMax.

FORBIDDEN for Phase 1: Under NO circumstances should the following models EVER be used for heartbeat Phase 1 checks:

Claude Opus 4.6 (NEVER. $25/M output for a status check.)
Claude Sonnet 4.6 (NEVER. $15/M output for a status check.)
Any Thinking Tier model with reasoning enabled (NEVER. Heartbeat checks do not need deep reasoning.)

PHASE 2: THE DISPATCH (Route to the right model for the actual work)

Once Phase 1 identifies that something needs to get done, Phase 2 determines WHAT kind of task it is and routes it to the appropriate model based on the instructions in this guide. The heartbeat itself does NOT do the work. It identifies the work and hands it off.

Phase 2 dispatch logic:

The heartbeat check returns a task (or list of tasks) that need execution
For each task, the agent evaluates what kind of work it is using the Scenario-Based Model Routing Guide in this document
The agent spins up the appropriate model for that specific task:
   Complex architecture or planning? Route to Opus or Sonnet (Thinking Tier)
   Code generation? Route to Kimi K2.5
   Creative writing? Route to Mistral Small Creative
   Research or fact-checking? Route to Perplexity Sonar Pro Search
   Routine task requiring tool calls? Route to MiniMax M2.5
   Simple factual lookup? Route to GPT-5 Nano
If it is unclear which model to use: Default to MiniMax M2.5. MiniMax handles tool calls, has HIGH thinking enabled, and is the safest general-purpose choice.
If it is still unclear after defaulting to MiniMax: Ask the user which model they want for this task. If the user does not respond within 60 seconds, proceed with MiniMax M2.5 and log the decision so the user knows what happened.

Why this matters: The token cost of heartbeat Phase 1 is minimal when the right model is used. The token cost from Phase 2 comes from the dispatched model doing the actual work. That cost is appropriate because the right model is being used for the right task.

When to use Execution Tier:

Daily task execution and routine operations (MiniMax M2.5)
Sending messages and routine communications (MiniMax M2.5)
Tool calls and function execution (MiniMax M2.5 or DeepSeek V3.2)
Heartbeat Phase 1 checks with no tool call needed (GPT-5 Nano)
Heartbeat Phase 1 checks requiring tool calls (MiniMax M2.5)
Heartbeat Phase 2 dispatch: route to the appropriate model per this guide
Code creation and generation (Kimi K2.5)
Data scraping at scale with parallel agents (Kimi K2.5, 100+ simultaneous instances)
Real-time back-and-forth chat (Kimi K2.5)
Quick summaries of short documents (GPT-5 Mini or Claude Haiku 4.5)
Simple Q&A and factual questions (GPT-5 Nano)
Content drafts and simple edits (any Execution Tier model)



Tier 3: Creative Tier

For all creative writing, content creation, copywriting, and narrative work.

| Priority | Model | OpenRouter ID | Alias | Thinking |
|----------|-------|---------------|-------|----------|
| 1st | Mistral Small Creative | openrouter/mistralai/mistral-small-creative | creative | No (creative focus, not a thinking model) |

When to use Creative Tier:

Social media posts (Instagram, Facebook, LinkedIn, X/Twitter, TikTok)
Blog posts and articles
Email content and newsletters
Book chapters and long-form narrative
Marketing copy and ad content
Creative writing of any kind
Brand voice content
Product descriptions
Sales copy and landing page content

Why a dedicated creative tier? Creative writing does not need deep reasoning or thinking tokens. Mistral Small Creative is purpose-built for this work at $0.10/M input. Route all creative tasks here.



Tier 4: Emergency Fallback Tier

ONLY activated when the user has run out of OpenRouter credits or funds.

| Model | OpenRouter ID | Alias |
|-------|---------------|-------|
| DeepSeek R1 0528 Free | openrouter/deepseek/deepseek-r1-0528:free | fallback |

When this activates:

User's OpenRouter balance hits zero
API returns a 402 (Payment Required) error
API returns any billing-related error
User explicitly states they have no credits remaining

What the agent must do:

Immediately switch to openrouter/deepseek/deepseek-r1-0528:free
Notify the user: "Your OpenRouter credits appear to be depleted. I have automatically switched to the free DeepSeek R1 model so we can continue working. When you are ready, add credits at https://openrouter.ai/credits and let me know so I can switch back to your preferred model."
Continue operating normally on the free model
When the user confirms credits have been added, switch back to their configured primary model



Tier 5: Research Tier

For research, fact-checking, web search, validation, and verifying information as truth.

| Model | OpenRouter ID | Alias | Web Search |
|-------|---------------|-------|------------|
| Perplexity Sonar Pro Search | openrouter/perplexity/sonar-pro-search | research | YES ($18 per 1,000 web searches) |

Perplexity Sonar Pro Search is the PRIMARY research model. Any time the system needs to research a topic, validate information, verify facts, check if something is true, look up current data, or perform any kind of web-based information retrieval, Perplexity is the model that gets used. This is not optional. This is not a suggestion. Perplexity is the research model.

When to use Research Tier:

Researching any topic the agent is uncertain about
Validating claims, facts, statistics, or data points
Verifying that information is current and accurate
Looking up current events, pricing, availability, or status
Fact-checking content before it is published or sent
Comparing products, services, or tools
Any task where the agent says "I should look this up" or "let me verify that"
Confirming model specifications, API changes, or platform updates before configuring

When NOT to use Research Tier:

Simple factual questions the agent already knows with certainty (use GPT-5 Nano)
Creative writing tasks (use Mistral Small Creative)
Code generation (use Kimi K2.5 or GPT 5.2 Codex)
Daily task execution (use MiniMax M2.5)

Pricing note: Perplexity charges $3/M input tokens, $15/M output tokens, PLUS $18 per 1,000 web searches. The web search cost is separate from token costs. The agent should be aware that research tasks cost more than standard model calls because of the web search surcharge.



Model Specifications Reference Table

This table contains the verified specifications for every model in the roster. The agent MUST reference this table to understand context window limits, output capacity, and cost implications. This data is critical for preventing context overflow, premature compaction, and unnecessary cost.

IMPORTANT: These specifications are verified from OpenRouter's live provider pages. All max output values reflect the maximum available across all providers. Context windows and prices may vary slightly between providers.

| Model | OpenRouter ID | Context Window | Max Output | Input $/M | Output $/M | Thinking | Temp |
|-------|---------------|----------------|------------|-----------|------------|----------|------|
| Claude Opus 4.6 | openrouter/anthropic/claude-opus-4.6 | 1,000,000 | 128,000 | $5.00 | $25.00 | YES (adaptive: low/med/high/max) | 0.3 |
| Claude Sonnet 4.6 | openrouter/anthropic/claude-sonnet-4.6 | 1,000,000 | 128,000 | $3.00 | $15.00 | YES (adaptive: low/med/high/max) | 0.3 |
| Claude Haiku 4.5 | openrouter/anthropic/claude-haiku-4.5 | 200,000 | 64,000 | $1.00 | $5.00 | YES (extended thinking) | 0.3 |
| Gemini 3.1 Pro Preview | openrouter/google/gemini-3.1-pro-preview | 1,048,576 | 65,536 | $2.00 | $12.00 | YES (thinkingLevel: minimal/low/med/high) | 0.3 |
| Gemini 3 Flash Preview | openrouter/google/gemini-3-flash-preview | 1,048,576 | 65,536 | $0.50 | $3.00 | YES (thinkingLevel) | 0.3 |
| GPT 5.2 Codex | openrouter/openai/gpt-5.2-codex | 400,000 | 128,000 | $0.25 | $2.00 | YES (reasoning effort: low/med/high) | 0.3 |
| GPT-5 Mini | openrouter/openai/gpt-5-mini | 400,000 | 128,000 | $0.25 | $2.00 | YES (reasoning effort) | 0.3 |
| GPT-5 Nano | openrouter/openai/gpt-5-nano | 400,000 | 400,000 | $0.05 | $0.40 | YES (reasoning effort) | 0.3 |
| Kimi K2.5 | openrouter/moonshotai/kimi-k2.5 | 262,144 | 262,144 | $0.23 | $3.00 | YES (built-in, no config param). NO TOOL CALLS. | 1.0 |
| MiniMax M2.5 | openrouter/minimax/minimax-m2.5 | 196,608 | 196,608 | $0.30 | $1.10 | YES (default: HIGH, supports XHIGH) | 0.3 |
| Mistral Small Creative | openrouter/mistralai/mistral-small-creative | 32,768 | 32,768 | $0.10 | $0.30 | No | 0.3 |
| Qwen 3.5 Plus | openrouter/qwen/qwen3.5-plus-02-15 | 1,000,000 | 65,536 | $0.40 | $2.40 | YES | 0.3 |
| GLM-5 | openrouter/z-ai/glm-5 | 204,800 | 131,072 | $0.30 | $2.55 | YES | 0.3 |
| DeepSeek V3.2 | openrouter/deepseek/deepseek-v3.2 | 163,840 | 8,192 | $0.26 | $0.38 | YES (reasoning toggle, default: MEDIUM) | 0.3 |
| DeepSeek V3.2 Speciale | openrouter/deepseek/deepseek-v3.2-speciale | 163,840 | 65,536 | $0.40 | $1.20 | YES (high-compute) | 0.3 |
| DeepSeek R1 0528 Free | openrouter/deepseek/deepseek-r1-0528:free | 163,840 | 163,840 | FREE | FREE | YES | 0.3 |
| Perplexity Sonar Pro Search | openrouter/perplexity/sonar-pro-search | 200,000 | 8,000 | $3.00 | $15.00 | No (research/search model) | 0.3 |

Important notes about this table:

Pricing may vary slightly by provider. Always verify current pricing at https://openrouter.ai/models
Kimi K2.5 is the ONLY model with temperature 1.0. Every other model uses 0.3.
Kimi K2.5 CANNOT do tool calls. It is for coding and chat only.
Reasoning/thinking tokens are billed as OUTPUT tokens. Enabling thinking on a model will increase cost.
Thinking levels are PER-MODEL, not uniform. MiniMax defaults to HIGH. DeepSeek defaults to MEDIUM. See the Thinking Level Defaults table below for all models.
Perplexity Sonar Pro Search has an additional cost of $18 per 1,000 web searches on top of token costs.
Context window is the total input capacity. Max output is the maximum response length the model can generate.
The agent must reference these context windows to avoid premature compaction or context overflow errors.
Before configuring any model, verify its current specs at its OpenRouter model page: https://openrouter.ai/models/<model-slug>



Thinking Model Cost Warning Protocol

This protocol is MANDATORY whenever a thinking-enabled model is engaged.

What You Must Do Before Using a Thinking Model

Identify that the task requires or benefits from thinking/reasoning
Notify the user with a clear cost warning:

"This task would benefit from using [model name] with thinking enabled. Thinking mode produces higher quality results but costs more because reasoning tokens are billed as output tokens. The default thinking level for [model name] is [MODEL'S DEFAULT LEVEL per Rule 13]. Would you like me to proceed at the default, or would you prefer I escalate to maximum thinking for deeper analysis? You can also decline thinking mode entirely."

Wait for the user's response (apply the 60-second timeout from Rule 14)
Proceed based on their choice

Thinking Level Recommendations by Task Complexity

| Task Complexity | Recommended Level | Examples |
|-----------------|-------------------|----------|
| Simple with nuance | Low | Summarizing with specific requirements, targeted feedback |
| Standard analysis | Medium (default) | Code review, document analysis, standard planning |
| Complex multi-step | High | System architecture, multi-file refactoring, complex debugging |
| Mission-critical | Xhigh (MiniMax M2.5) | Production deployment planning, security audits, critical business strategy, complex multi-agent orchestration |

Note: Xhigh is the maximum reasoning level available on OpenRouter (0.95 effort ratio). It is supported by MiniMax M2.5 and other reasoning-capable models. Use it only when the task demands maximum analytical depth and the user has approved the additional token cost.



Scenario-Based Model Routing Guide

These examples teach the agent which model to select for which type of task. The agent should use these as a decision framework, not as the only possible options.

SCENARIO 1: User asks a simple factual question

Example: "What time zone is New York in?"
Use: GPT-5 Nano ($0.05/M input, fastest, no thinking needed)
Why: Simple factual lookup. No reasoning required.

SCENARIO 2: User asks to write a social media post

Example: "Write me an Instagram caption for this product photo"
Use: Mistral Small Creative (Creative Tier)
Why: Purpose-built for creative content at $0.10/M input. No thinking tokens needed.

SCENARIO 3: User asks to write a long blog post

Example: "Write a 3,000-word blog post about real estate investing strategies"
Use: Mistral Small Creative (Creative Tier)
Why: Long-form creative writing. Mistral excels here at minimal cost.

SCENARIO 4: User asks to draft a professional email

Example: "Draft an email to my client about the project timeline update"
Use: Mistral Small Creative (Creative Tier)
Why: Email content is creative/communication work, not deep reasoning.

SCENARIO 5: User asks to debug a Python script

Example: "This script is throwing a TypeError on line 47, help me fix it"
Use: GPT 5.2 Codex (Thinking Tier, thinking at medium) for complex debugging, or Kimi K2.5 (Execution Tier) for straightforward fixes and code generation
Why: Codex for deep multi-file debugging that requires reasoning. Kimi for direct code fixes and generation where the problem is clear.

SCENARIO 6: User asks to plan a multi-step automation workflow

Example: "Help me design an N8N workflow that processes leads from GoHighLevel"
Use: Claude Opus 4.6 (Thinking Tier, thinking at medium)
Why: Complex architecture and multi-step planning require deep reasoning.

SCENARIO 7: User asks to analyze a long document

Example: "Analyze this 200-page PDF and summarize the key findings"
Use: Gemini 3.1 Pro Preview (Thinking Tier, thinking at medium)
Why: 1M context window handles massive documents. Built for long-context analysis.

SCENARIO 8: User needs a quick summary

Example: "Summarize this short Slack thread for me"
Use: GPT-5 Mini or Claude Haiku 4.5 (Execution Tier)
Why: Fast, capable for simple summarization.

SCENARIO 9: User asks to refactor an entire codebase

Example: "Refactor this entire React app from class components to hooks"
Use: Claude Opus 4.6 or GPT 5.2 Codex (Thinking Tier, recommend maximum thinking)
Why: Multi-file refactoring is high-complexity. Warn user about cost. Recommend max thinking.

SCENARIO 10: User asks to build a detailed project plan

Example: "Create a project plan with milestones and deliverables for our Q2 launch"
Use: Claude Sonnet 4.6 or Gemini 3.1 Pro (Thinking Tier, thinking at medium)
Why: Structured reasoning without Opus-level cost. Good balance of depth and efficiency.

SCENARIO 11: User asks to write a book or multiple chapters

Example: "Write chapter 3 of my real estate investing book" or "Help me write my book"
Use: Mistral Small Creative (Creative Tier) as sub-agents, controlled by a Thinking Tier master agent (Claude Opus 4.6, Gemini 3.1 Pro, or Claude Sonnet 4.6)
Architecture: Mistral Small Creative CAN write a book. It cannot hold an entire book in one 200K context window, but it does not need to. The correct approach is a multi-agent architecture:
  Master Agent (Thinking Tier, large context): Holds the book outline, chapter summaries, character profiles, tone guidelines, continuity notes, and overall structure. This agent plans what each chapter should cover and reviews output for consistency.
  Sub-Agents (Mistral Small Creative, one per chapter): Each instance of Mistral receives targeted instructions from the master agent for its specific chapter. It writes the chapter, returns the output, and the master agent reviews it before moving to the next.
  Multiple calls, not one giant session: You spin up Mistral multiple times. Each call is a fresh, focused chapter task with clear direction from the master agent. This keeps each call well within the context window while producing a full book.
Why: This architecture uses Mistral at $0.10/M input for the bulk of writing while using the Thinking Tier master agent only for planning, guidance, and quality control. The writing workload is distributed across multiple focused calls rather than routed through a single model.

SCENARIO 12: User needs rapid back-and-forth chat

Example: "Let's brainstorm ideas quickly, just rapid-fire"
Use: Kimi K2.5 (Execution Tier, chat mode)
Why: Kimi excels at conversational flow and rapid iteration. No tool calls needed for brainstorming. Fast and purpose-built for chat.
Note: If the brainstorming session leads to tasks that need execution (sending messages, calling APIs, creating files), hand those tasks off to MiniMax M2.5 for execution while Kimi continues the conversation.

SCENARIO 13: User asks to review a business proposal

Example: "Review this business proposal and give me critical feedback"
Use: Claude Sonnet 4.6 (Thinking Tier, thinking at medium)
Why: Analytical depth without Opus-level pricing. Good for structured critique.

SCENARIO 14: User asks for complex agentic workflow design

Example: "Design a system with multiple AI agents that coordinate to process orders"
Use: GLM-5 or Qwen 3.5 Plus (Thinking Tier, thinking at medium)
Why: Both excel at agentic planning and long-horizon workflows. Cost-effective alternatives to Opus.

SCENARIO 15: User has run out of credits

Detection: API returns 402 or billing error
Use: DeepSeek R1 0528 Free (Emergency Fallback Tier)
Why: Free model keeps the user operational until they add credits. Do not stop working.

SCENARIO 16: User needs to research, validate, or fact-check something

Example: "Is this statistic about real estate conversion rates accurate?" or "What are the current API pricing changes for GoHighLevel?" or "Research the best CRM tools for real estate agents in 2026"
Use: Perplexity Sonar Pro Search (Research Tier)
Why: Perplexity is the PRIMARY research model. It has web search built in. Any time the system needs to verify facts, check current information, research a topic, or validate data, Perplexity handles it. Do not use a standard model to guess or rely on training data for verifiable facts. Use Perplexity.

SCENARIO 17: User needs a task executed that requires tool calls

Example: "Send that message" or "Create a new contact in the CRM" or "Run this automation"
Use: MiniMax M2.5 (Execution Tier, primary daily task model)
Why: MiniMax supports tool calls and is the default for any operation requiring function execution. Do NOT assign tool-call tasks to Kimi K2.5.

SCENARIO 18: User needs to scrape data or process data in bulk

Example: "Scrape these 500 URLs and extract the pricing data" or "Process these listings and pull out the contact information"
Use: Kimi K2.5 (Execution Tier, parallel agent mode)
Architecture: Spin up 100+ simultaneous Kimi instances, each handling its own target. A master agent (MiniMax M2.5 or a Thinking Tier model) coordinates the work, distributes targets to each Kimi instance, and collects results. Each Kimi agent receives a focused instruction, processes its target, and returns the output. This is high-volume parallel processing, not one model doing everything sequentially.
Why: Kimi is fast ($0.23/M input) and can run at massive scale. It does not need tool calls for scraping when the master agent handles coordination and data collection.

SCENARIO 19: Master agent orchestrating mixed sub-tasks (code + tool calls + writing)

Example: "Build the landing page, set up the API endpoints, write the email sequence, and connect it all to the CRM"
Architecture: Master agent (Opus or Sonnet, Thinking Tier) breaks the project into sub-tasks:
  Code generation sub-tasks (landing page HTML/CSS, API endpoint scripts): Route to Kimi K2.5 as sub-agent. Set max_tokens to 262,144.
  Tool-call sub-tasks (CRM integration, API connections, webhook configuration): Route to MiniMax M2.5 as sub-agent. Set thinking to high or xhigh based on complexity. Set max_tokens to 196,608.
  Writing sub-tasks (email sequence copy): Route to Mistral Small Creative as sub-agent. Set max_tokens to 32,768.
  Research sub-tasks (verify CRM API documentation, check endpoint specs): Route to Perplexity Sonar Pro Search.
Thinking level per sub-task: Standard code generation = medium. Complex API integration = high. Critical production deployment = xhigh. Creative writing = N/A (Mistral has no thinking parameter).
Why: Each sub-agent is matched to its strengths. The master agent handles continuity and integration. Token cost stays appropriate per sub-task.



MULTI-AGENT ORCHESTRATION

This is a general operational principle, not limited to any single scenario. The agent must understand this pattern and apply it whenever it fits the task.

The Principle

A model with a small context window does NOT mean a limited model. It means the model needs to be orchestrated differently. Instead of cramming everything into one giant session, you split the work across multiple focused calls, each coordinated by a master agent with a larger context window.

The Pattern

Master Agent (Thinking Tier, large context window): Holds the full picture. Maintains the outline, structure, requirements, continuity, quality standards, and overall plan. This agent plans what each sub-agent should do and reviews the output.
Sub-Agents (Execution, Creative, or specialized models): Each receives a focused, targeted instruction from the master agent. Each completes its specific piece of work within its own context window. Each returns output to the master agent for review and integration.
Multiple calls, not one giant session: The master agent calls the sub-agent multiple times, once per unit of work. Each call is fresh and focused. The sub-agent does not need to remember what happened in previous calls because the master agent handles continuity.

When to Apply This Pattern

Book writing: Master agent (Opus/Sonnet/Gemini) plans chapters, sub-agents (Mistral Small Creative) write individual chapters
Large codebases: Master agent (Opus/Codex) plans the architecture, sub-agents (Kimi K2.5) write individual modules or files
Content campaigns: Master agent plans the campaign strategy, sub-agents (Mistral) write individual posts, emails, and articles
Data processing: Master agent coordinates the pipeline, sub-agents handle individual data transformation steps
Data scraping at scale: Master agent (MiniMax or Thinking Tier) coordinates work distribution, Kimi K2.5 runs as 100+ parallel instances each handling its own target independently
Any project that exceeds a single model's context window or benefits from specialization

Sub-Agent Model Selection Logic

When a master agent dispatches work to sub-agents, it MUST select the correct sub-agent model based on what the sub-task requires. This is not optional. The wrong sub-agent causes silent failures or wasted tokens.

Decision tree for sub-agent selection:

Does the sub-task require tool calls, function execution, API calls, or any interaction with external systems?
   YES: Use MiniMax M2.5. It supports tool calls. This includes heartbeat operations, sending messages, calling APIs, executing functions, and any operation that requires the model to invoke a tool.
   NO: Proceed to step 2.
Is the sub-task code generation? (writing scripts, building modules, generating components, creating code files)
   YES: Use Kimi K2.5. It is purpose-built for code generation. It can run as 100+ parallel instances for high-volume work. Each instance handles its own task independently.
   NO: Proceed to step 3.
Is the sub-task creative writing? (blog posts, social media, emails, articles, book chapters)
   YES: Use Mistral Small Creative. It is the Creative Tier model.
   NO: Proceed to step 4.
Is the sub-task research or fact-checking?
   YES: Use Perplexity Sonar Pro Search. It has web search built in.
   NO: Default to MiniMax M2.5 for general task execution.

Sub-Agent Thinking Level Scaling

The master agent evaluates the complexity of each sub-task and sets the thinking level accordingly. This is per-call, not per-model. The same MiniMax M2.5 instance can run at medium thinking for a simple task and xhigh thinking for a complex one within the same orchestration session.

| Sub-Task Complexity | Thinking Level | When to Use |
|---------------------|----------------|-------------|
| Simple, straightforward | Medium | Standard operations, routine task execution, basic data processing |
| Moderate complexity | High | Multi-step operations, tasks with conditional logic, moderate debugging |
| Maximum complexity | Xhigh | Critical path operations, complex multi-step workflows, security-sensitive tasks, tasks where failure is not acceptable |

Kimi K2.5 note: Kimi has built-in thinking with no configurable parameter. You cannot adjust Kimi's thinking level. It runs at whatever level its internal architecture provides.

Sub-Agent Max Output Token Configuration

IMPORTANT: max_tokens is set IN THE API REQUEST when the master agent spawns a sub-agent. It is NOT a config file setting. Do NOT add max_tokens, maxTokens, or any output limit to the agents.defaults.models section of openclaw.json. The config file only accepts alias, params, and streaming. max_tokens is a per-request parameter that the orchestrating agent sets when it dispatches work to a sub-agent.

Each model has a maximum output token limit. When the master agent dispatches a sub-task, it MUST set max_tokens appropriately in the API request for the sub-agent so the model is not artificially capped below its capacity.

| Model | Max Output Tokens | Set max_tokens To |
|-------|-------------------|-------------------|
| MiniMax M2.5 | 196,608 | 196,608 (or the specific amount needed for the task, whichever is lower) |
| Kimi K2.5 | 262,144 | 262,144 (or the specific amount needed for the task, whichever is lower) |
| Mistral Small Creative | 32,768 | 32,768 (or the specific amount needed for the task, whichever is lower) |
| DeepSeek V3.2 | 8,192 | 8,192 (or the specific amount needed for the task, whichever is lower) |
| GPT-5 Nano | 400,000 | The specific amount needed for the task (do not set to 400K unless the task actually needs it) |
| GPT 5.2 Codex | 128,000 | The specific amount needed for the task |
| Claude Opus 4.6 | 128,000 | The specific amount needed for the task |
| Claude Sonnet 4.6 | 128,000 | The specific amount needed for the task |
| GLM-5 | 131,072 | The specific amount needed for the task |
| Qwen 3.5 Plus | 65,536 | The specific amount needed for the task |
| DeepSeek V3.2 Speciale | 65,536 | The specific amount needed for the task |
| DeepSeek R1 Free | 163,840 | The specific amount needed for the task |

When reasoning is enabled: max_tokens must be set HIGHER than the reasoning budget. The reasoning budget is calculated from max_tokens (see the formula in Rule 13). If max_tokens is set to 196,608 and reasoning effort is xhigh (0.95 ratio), the reasoning budget consumes 186,778 tokens, leaving only 9,830 tokens for the actual response. The master agent must account for this. If a sub-task needs 8,000 tokens of output AND xhigh reasoning, max_tokens must be set high enough to accommodate both the reasoning budget and the response.

Cost Benefit

This pattern keeps Thinking Tier usage limited to planning and review (low token count) while routing the bulk of generation work to Execution or Creative Tier models. The user pays Thinking Tier prices only for the orchestration, not for every word of output.



STEP 5: CONFIGURE THE OPENCLAW CONFIG FILE

OpenClaw has BUILT-IN support for OpenRouter. You do NOT need to configure models.providers. Just set your API key and reference models with the openrouter/<author>/<slug> format.

Full Configuration with All Models

Add your OpenRouter API key and the complete model roster to ~/.openclaw/openclaw.json:


{
  "env": {
    "OPENROUTER_API_KEY": "sk-or-..."
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
      "models": {
        "openrouter/anthropic/claude-opus-4.6": {
          "params": {
            "temperature": 0.3,
            "reasoning": {
              "effort": "medium"
            }
          }
        },
        "openrouter/anthropic/claude-sonnet-4.6": {
          "params": {
            "temperature": 0.3,
            "reasoning": {
              "effort": "medium"
            }
          }
        },
        "openrouter/anthropic/claude-haiku-4.5": {
          "params": {
            "temperature": 0.3,
            "reasoning": {
              "effort": "medium"
            }
          }
        },
        "openrouter/google/gemini-3.1-pro-preview": {
          "params": {
            "temperature": 0.3,
            "reasoning": {
              "effort": "medium"
            }
          }
        },
        "openrouter/google/gemini-3-flash-preview": {
          "params": {
            "temperature": 0.3,
            "reasoning": {
              "effort": "medium"
            }
          }
        },
        "openrouter/openai/gpt-5.2-codex": {
          "params": {
            "temperature": 0.3,
            "reasoning": {
              "effort": "medium"
            }
          }
        },
        "openrouter/openai/gpt-5-mini": {
          "params": {
            "temperature": 0.3,
            "reasoning": {
              "effort": "medium"
            }
          }
        },
        "openrouter/openai/gpt-5-nano": {
          "params": {
            "temperature": 0.3,
            "reasoning": {
              "effort": "medium"
            }
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
            "reasoning": {
              "effort": "high"
            }
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
            "reasoning": {
              "effort": "medium"
            }
          }
        },
        "openrouter/z-ai/glm-5": {
          "params": {
            "temperature": 0.3,
            "reasoning": {
              "effort": "medium"
            }
          }
        },
        "openrouter/deepseek/deepseek-v3.2": {
          "params": {
            "temperature": 0.3,
            "reasoning": {
              "effort": "medium"
            }
          }
        },
        "openrouter/deepseek/deepseek-v3.2-speciale": {
          "params": {
            "temperature": 0.3,
            "reasoning": {
              "effort": "medium"
            }
          }
        },
        "openrouter/deepseek/deepseek-r1-0528:free": {
          "params": {
            "temperature": 0.3,
            "reasoning": {
              "effort": "medium"
            }
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


Temperature Settings Summary

ALL models: temperature 0.3
EXCEPTION: Kimi K2.5 (openrouter/moonshotai/kimi-k2.5): temperature 1.0

Thinking/Reasoning Settings Summary

MiniMax M2.5: reasoning effort set to "high" by default (primary daily task model, needs reliable tool execution). Supports escalation to "xhigh" (0.95 effort ratio) for maximum complexity tasks.
DeepSeek V3.2: reasoning effort set to "medium" (value workhorse, balanced quality and cost)
All other thinking-capable models: reasoning effort set to "medium" by default
Mistral Small Creative: No reasoning parameter (not a thinking model)
Kimi K2.5: No explicit reasoning parameter in config (built-in thinking, no tool calls)
Perplexity Sonar Pro Search: No reasoning parameter (research/web search model)

Available reasoning effort levels on OpenRouter: minimal (0.10), low (0.20), medium (0.50), high (0.80), xhigh (0.95).

Reasoning budget formula: budget_tokens = max(min(max_tokens * effort_ratio, 128000), 1024). Reasoning tokens are capped at 128,000 maximum. Reasoning tokens are billed as output tokens.

IMPORTANT CONFIG RULES

If the user already has a primary model set, do NOT change it. Only add the OpenRouter models to the models map.
If they already have aliases pointing to direct providers, do NOT overwrite them.
If they already have models configured, MERGE your additions. Do not replace their existing entries.



STEP 6: VALIDATE AND RESTART

Validate the Config


openclaw doctor


If Validation Passes


openclaw gateway restart


If Validation Fails

RESTORE THE BACKUP IMMEDIATELY:


cp ~/openclaw-backup-configs/openclaw-backup-LATEST.json ~/.openclaw/openclaw.json
openclaw gateway restart


Then review what went wrong before trying again. Do not keep editing a broken config. Restore, analyze, then attempt again with a fresh backup.



STEP 7: VERIFY IT WORKS

After restart, test that models are accessible:

Send a test message and confirm a response comes back
Check status: Run to see the active model
Test model switching: Try or /model opus to confirm aliases work
Test fallback: Verify that if the primary model fails, the fallback engages



QUICK REFERENCE TABLE

| Alias | Model | Tier | Use For | Thinking | Temp |
|-------|-------|------|---------|----------|------|
| opus | Claude Opus 4.6 | Thinking | Complex strategy, architecture, critical work | YES (medium default) | 0.3 |
| sonnet | Claude Sonnet 4.6 | Thinking | Balanced quality + speed, analysis | YES (medium default) | 0.3 |
| gemini31 | Gemini 3.1 Pro | Thinking | Long context analysis, research | YES (medium default) | 0.3 |
| codex | GPT 5.2 Codex | Thinking | Code architecture, debugging | YES (medium default) | 0.3 |
| qwen | Qwen 3.5 Plus | Thinking | Multimodal, agentic planning | YES (medium default) | 0.3 |
| glm5 | GLM-5 | Thinking | Systems design, agent workflows | YES (medium default) | 0.3 |
| speciale | DeepSeek V3.2 Speciale | Thinking | High-compute reasoning | YES (medium default) | 0.3 |
| minimax | MiniMax M2.5 | Execution | RECOMMENDED PRIMARY. Tool calls, task execution, heartbeat Phase 1 (w/ tool calls), Phase 2 default. Sub-agent for all tool-call tasks. | YES (HIGH default, supports XHIGH) | 0.3 |
| flash | Gemini 3 Flash | Execution | Quick responses, large context | YES (medium default) | 0.3 |
| haiku | Claude Haiku 4.5 | Execution | Fast intelligent responses | YES (medium default) | 0.3 |
| gptmini | GPT-5 Mini | Execution | Mid-range tasks, good value | YES (medium default) | 0.3 |
| gptnano | GPT-5 Nano | Execution | Heartbeat Phase 1 (no tool calls). Simple lookups. | YES (medium default) | 0.3 |
| deepseek | DeepSeek V3.2 | Execution | Value workhorse, heartbeat backup | YES (MEDIUM default) | 0.3 |
| kimi | Kimi K2.5 | Execution | Coding, chat, scraping (100+ parallel agents). No tool calls. Sub-agent for all code generation tasks. | YES (built-in) | 1.0 |
| creative | Mistral Small Creative | Creative | All writing and content creation | No | 0.3 |
| research | Perplexity Sonar Pro Search | Research | PRIMARY research model. All research, validation, fact-checking, web search. | No | 0.3 |
| fallback | DeepSeek R1 Free | Emergency | Zero-credit fallback only | YES (medium default) | 0.3 |

Environment Variable


OPENROUTER_API_KEY=sk-or-...




MD FILE UPDATE INSTRUCTIONS

When this configuration guide is applied, the agent MUST also update its internal knowledge files to reflect the new model roster, context windows, and operational rules.

Files to Update

tools.md

Update with the following information for each model:

Context window size (from the Model Specifications Reference Table above)
Maximum output token limit
When to trigger compaction (at 80% of context window capacity, not earlier)
Which models support which tools and capabilities
Context Window Management Protocol thresholds (80% warn, 90% create handoff.md, 95% update handoff.md)
The handoff.md creation process and required contents (Rule 24)

agent.md

Update with:

The five-tier model selection strategy (Thinking, Execution, Creative, Emergency Fallback, Research)
The model-switching permission protocol (Rule 14)
The thinking model cost warning protocol (Rule 12)
The zero-credit fallback protocol (Rule 16)
The Kimi K2.5 tool-call limitation (Rule 19)
The scenario-based routing guide
Temperature settings (0.3 for all, 1.0 for Kimi K2.5 only)
MiniMax M2.5 is the primary daily task model (tool calls, execution, heartbeat)
Kimi K2.5 is for coding and chat only (no tool calls)
Perplexity Sonar Pro Search is the primary research model (all research, validation, fact-checking)
Sub-agent model selection logic (Rule 25): Kimi for code generation, MiniMax for tool calls, Mistral for writing, Perplexity for research
Thinking level scaling for sub-agents: medium (standard), high (complex), xhigh (maximum complexity)
Max output token limits per model so sub-agents are not artificially capped
Context Window Management Protocol (Rule 24): 80% warn, 90% create handoff.md, 95% update handoff.md
OpenRouter reasoning effort levels: minimal (0.10), low (0.20), medium (0.50), high (0.80), xhigh (0.95)
Reasoning budget formula: budget_tokens = max(min(max_tokens * effort_ratio, 128000), 1024)

memory.md

Update with:

Context window capacities for each model (so the agent knows when to compact or summarize)
Long-context management strategies: models with 1M context (Opus 4.6, Sonnet 4.6, Gemini 3.1 Pro, Qwen 3.5 Plus) can handle extended sessions without compaction
Short-context awareness: Mistral Small Creative (200K) requires proactive session management
When to switch models mid-session if context is running low
MiniMax M2.5 is the primary daily task model (tool calls, task execution, heartbeat)
Kimi K2.5 is for coding and chat only (no tool calls)
Perplexity Sonar Pro Search is the primary research model
Context Window Management Protocol: 80% warn, 90% create handoff.md, 95% update handoff.md, post-compaction read handoff.md first (Rule 24)
The handoff.md file must be complete enough that a fresh agent can continue the session without asking the user to repeat anything
Threshold calculation: the agent must know its active model's context window to calculate 80/90/95% thresholds

Any Other Relevant .md Files

If the agent has additional knowledge files that reference model capabilities, pricing, or selection logic, those files must also be updated to reflect this guide.



TOKEN PROTECTION AND COST GUIDANCE RULES

The purpose of this entire configuration is to ensure the end user gets the best possible results for every task while matching model selection to task requirements.

Core Principles

Match model complexity to task complexity. Do not use a thinking-tier model for tasks that an execution-tier model handles perfectly well.
Default to MiniMax M2.5 for daily task execution. MiniMax is the primary daily task model. It supports tool calls, handles routine operations, and should be the first choice for any task that requires doing something (not just talking about it).
Route all creative/writing tasks to Mistral Small Creative. Social media, blog posts, emails, book chapters, marketing copy. All of it goes to the Creative Tier unless the user specifically requests a different model.
Route all research, validation, and fact-checking to Perplexity Sonar Pro Search. Any time the agent needs to verify information, look something up, check if data is current, or research a topic, Perplexity handles it. Do not guess. Do not rely on training data for verifiable facts. Use Perplexity.
Route coding and code generation to Kimi K2.5. Kimi is the coding and chat model. Use it for writing code, building scripts, generating components, and brainstorming. Do NOT assign tool-call tasks to Kimi. It cannot execute tools.
Warn before engaging thinking models. Every time. No exceptions. The user must know that thinking mode costs more.
Proactively guide the user to the right model. Do not wait for the user to ask "which model should I use?" If the task does not require a Thinking Tier model, suggest the appropriate tier. If the task requires more capability than the current model provides, recommend the appropriate model.
Never let the system go dark because of billing. If credits run out, switch to the free fallback immediately and keep working.
Track and communicate cost implications. When recommending models, include the pricing context so users can make informed decisions.
Track context window usage and create handoff.md before compaction. The agent must calculate 80/90/95% thresholds on session start. Warn at 80%. Create handoff.md at 90%. Update handoff.md at 95%. After compaction, read handoff.md first. The agent must know its active model's context window to calculate these thresholds.
Select the correct sub-agent model in multi-agent orchestration. Tool-call tasks go to MiniMax M2.5. Code generation goes to Kimi K2.5. Creative writing goes to Mistral Small Creative. Research goes to Perplexity. Set thinking level per sub-task complexity. Set max_tokens to the model's actual output limit.



COMMON MISTAKES TO AVOID

Using openrouter/auto - NEVER do this, it breaks configs. This is Rule 1. Memorize it.
Forgetting the openrouter/ prefix - Models will not route correctly without the full openrouter/<author>/<slug> format.
Not backing up before editing - One typo can break the gateway. One backup can save the day. Always back up first.
Using old model IDs - Always verify current model names at https://openrouter.ai/models before configuring. Models get updated, deprecated, and renamed.
Setting temperature for models that do not support it - Only set params when specifically needed. If in doubt, use the defaults from this guide.
Editing the config while the gateway is running without restarting after - Changes do not take effect until you restart. Always restart after config changes.
Deleting existing model configs - You are ADDING, never replacing. If it was there before, it stays there.
Overwriting aliases - If an alias is taken by a direct connection, use an alternative (e.g., or-kimi for the OpenRouter version of Kimi).
Configuring models.providers for OpenRouter - NOT needed. OpenClaw has built-in support. Adding this section causes confusion and potential conflicts.
Adding custom keys to model entries - The ONLY valid keys in agents.defaults.models entries are alias, params, and streaming. Adding ANY other key (contextWindow, maxTokens, _verified_context, cost, notes, tier, description, or ANYTHING else) will make the entire config invalid and OpenClaw will refuse to start. Context windows and max output limits are provided automatically by the model provider. Do NOT store them in the config. This is the #1 config-breaking mistake. See Rule 11.
Stripping the openrouter/ prefix from model IDs - This converts them to direct provider calls and breaks the OpenRouter routing entirely.
Using thinking/reasoning mode without warning the user about cost - Thinking tokens are billed as output tokens. The user must be notified before you enable thinking on any model.
Defaulting to maximum thinking level - Each model has its own default (see Rule 13). MiniMax defaults to HIGH, most others to MEDIUM. Only escalate with user permission and a clear justification.
Using Opus or Codex for simple questions - Match the model to the task. Simple questions go to Nano or the Execution Tier.
Ignoring the 60-second timeout on model-switching - If the user does not respond within 60 seconds, proceed with your recommendation. Do not wait indefinitely.
Overriding the user's primary model without permission - The primary model is sacred. Do not touch it without explicit permission.
Failing to switch to the free fallback when credits are depleted - If the API returns a billing error, switch to DeepSeek R1 Free immediately. Do not stop working.
Assigning tool-call tasks to Kimi K2.5 - Kimi K2.5 cannot do tool calls. If the task requires executing tools, calling functions, or performing actions, use MiniMax M2.5 instead. This will cause silent failures if ignored.
Using a standard model for research instead of Perplexity - When the agent needs to verify facts, check current information, or research a topic, always route to Perplexity Sonar Pro Search. Do not guess or rely on training data for verifiable information.
Not verifying model specs before configuring - Always check the live OpenRouter model page before writing any model into a config. Specs change. Prices change. Do not blindly trust static tables.
Using Opus or Sonnet for heartbeat checks - Heartbeat Phase 1 is a status check. Use GPT-5 Nano ($0.05/M input) when no tool call is needed, or MiniMax M2.5 ($0.30/M input) when a tool call is required. Multiple sub-agents running heartbeat on Thinking Tier models accumulates token cost across every tick. This is Rule 22. Follow it.
Treating heartbeat as one model doing both checking and executing - Heartbeat has two phases. Phase 1 checks what needs to be done (low-cost model). Phase 2 dispatches the right model for the actual work. These are separate operations using separate models.
Not tracking context window usage - The agent must calculate 80/90/95% thresholds for its active model's context window on session start. If the agent does not know its context window size, it cannot create the handoff.md file in time. Compaction without a handoff file means total loss of session context. This is Rule 24.
Sending a tool-call sub-task to Kimi K2.5 in multi-agent orchestration - The master agent must route all tool-call sub-tasks to MiniMax M2.5. Kimi K2.5 cannot do tool calls. Sending a tool-call sub-task to Kimi will fail silently. This is Rule 25.
Capping sub-agent max_tokens below the model's actual limit - Each model has a maximum output token limit. If the master agent sets max_tokens to a lower value, the sub-agent's output gets cut off. Set max_tokens to the model's actual limit (or the amount needed for the task, whichever is lower). Do not leave it at a default that chokes the output.
Ignoring the reasoning budget when setting max_tokens with thinking enabled - When reasoning is on, the reasoning budget is calculated FROM max_tokens. If max_tokens is 196,608 and reasoning effort is xhigh (0.95 ratio), reasoning consumes 186,778 tokens, leaving only 9,830 for the actual response. The master agent must set max_tokens high enough to accommodate both the reasoning budget and the response output.



OFFICIAL OPENROUTER REFERENCE

The following is from the official OpenRouter documentation for OpenClaw integration (https://openrouter.ai/docs/guides/openclaw-integration). This section covers OpenRouter model format, fallback configuration, and troubleshooting. The user already has OpenClaw configured. This guide is strictly for configuring OpenRouter as the model provider.

Model Format

OpenClaw uses the format openrouter/<author>/<slug> for OpenRouter models:

openrouter/anthropic/claude-opus-4.6
openrouter/anthropic/claude-sonnet-4.6
openrouter/anthropic/claude-haiku-4.5
openrouter/google/gemini-3.1-pro-preview
openrouter/google/gemini-3-flash-preview
openrouter/openai/gpt-5.2-codex
openrouter/openai/gpt-5-mini
openrouter/openai/gpt-5-nano
openrouter/moonshotai/kimi-k2.5
openrouter/minimax/minimax-m2.5
openrouter/mistralai/mistral-small-creative
openrouter/qwen/qwen3.5-plus-02-15
openrouter/z-ai/glm-5
openrouter/deepseek/deepseek-v3.2
openrouter/deepseek/deepseek-v3.2-speciale
openrouter/deepseek/deepseek-r1-0528:free
openrouter/perplexity/sonar-pro-search

NEVER use: openrouter/auto (Auto router picks models unpredictably and breaks configs)

Multiple Models with Fallbacks


{
  "agents": {
    "defaults": {
      "model": {
        "primary": "openrouter/minimax/minimax-m2.5",
        "fallbacks": [
          "openrouter/moonshotai/kimi-k2.5",
          "openrouter/deepseek/deepseek-r1-0528:free"
        ]
      },
      "models": {
        "openrouter/minimax/minimax-m2.5": {},
        "openrouter/moonshotai/kimi-k2.5": {},
        "openrouter/deepseek/deepseek-r1-0528:free": {}
      }
    }
  }
}


Using Auth Profiles (More Secure)


{
  "auth": {
    "profiles": {
      "openrouter:default": {
        "provider": "openrouter",
        "mode": "api_key"
      }
    }
  }
}


Then set the key in your system keychain:


openclaw auth set openrouter:default --key "$OPENROUTER_API_KEY"


Per-Channel Models


{
  "telegram": {
    "agents": {
      "defaults": {
        "model": {
          "primary": "openrouter/anthropic/claude-haiku-4.5"
        }
      }
    }
  },
  "discord": {
    "agents": {
      "defaults": {
        "model": {
          "primary": "openrouter/anthropic/claude-opus-4.6"
        }
      }
    }
  }
}


Monitoring Usage

Visit https://openrouter.ai/activity
See requests, costs, and token usage
Filter by model, time range, or other criteria

Common Errors from Official Docs

"No API key found for provider 'openrouter'" - Set OPENROUTER_API_KEY env var or run openclaw onboard
Authentication errors (401/403) - Verify key at openrouter.ai/keys, check credits
Payment required (402) - Credits depleted. Add more at openrouter.ai/credits or use the free fallback model
Model not working - Verify model ID on openrouter.ai/models, use openrouter/<author>/<slug> format, add to agents.defaults.models

Resources

OpenClaw Documentation: https://docs.openclaw.ai
OpenClaw OpenRouter Provider Guide: https://docs.openclaw.ai/providers/openrouter
OpenClaw GitHub: https://github.com/openclaw/openclaw
OpenRouter Models: https://openrouter.ai/models
OpenRouter Activity Dashboard: https://openrouter.ai/activity
OpenRouter API Documentation: https://openrouter.ai/docs/api
OpenRouter Reasoning Tokens Guide: https://openrouter.ai/docs/guides/best-practices/reasoning-tokens



SECTION 8: INTELLIGENT MODEL ROUTING VIA SYSTEM PROMPTING

Why This Matters

Config alone is NOT enough. You can set up 24 models with perfect temperature, reasoning, and cost settings, but if the agent doesn't KNOW when to use which model, it will use the same model for everything. That's like owning a toolbox with 24 tools but only ever reaching for the hammer.

Intelligent Model Routing is a system of instructions embedded in your agent's workspace files (TOOLS.md, AGENTS.md, HEARTBEAT.md, USER.md, MEMORY.md) that teach the agent to THINK before it acts. Before every task, the agent asks itself:

What kind of work am I about to do?
Which model in my roster does this best?
What thinking level does this task need?
Do I need to switch, or am I already on the right model?

This turns a dumb "one model for everything" agent into a smart self-directing system that uses the right tool for the right job.

The Two Thinking Systems in OpenClaw

Before we get into routing, you need to understand that OpenClaw has TWO separate systems that control how hard a model "thinks":

System 1: thinkingDefault (Session-Level)
Location in config: agents.defaults.thinkingDefault
What it does: Controls the session-level thinking display (the "Think:" indicator in the status bar)
Valid values: off, minimal, low, medium, high, xhigh
Recommended default: medium
This is the GLOBAL baseline. It applies to whatever model is currently active in the session.
The agent can override this per-task using /reasoning <level> during the session.

System 2: params.reasoning.effort (Per-Model API-Level)
Location in config: Each model entry under agents.defaults.models.<model>.params.reasoning.effort
What it does: Sends a reasoning effort parameter to the model provider (OpenRouter, Anthropic, OpenAI) with every API call
Valid values: low, medium, high (provider-dependent)
This is a per-model override that travels with the API request regardless of session state.

How they interact:
thinkingDefault is the baseline. If set to medium, every model starts at medium thinking.
params.reasoning.effort is a per-model API hint. If MiniMax has effort: "high" in its config, the API request to MiniMax always includes that hint.
The agent can dynamically change the session-level thinking with /reasoning <level> without touching the config.
Non-thinking models (Mistral Small Creative, Perplexity Sonar Pro) safely IGNORE both settings. OpenClaw checks the model's reasoning: true/false flag before sending any thinking params.

For Google Gemini models: The API format is different. Instead of reasoning.effort, Gemini uses:

"thinking": {
  "type": "enabled",
  "budget": 0.5
}

OpenClaw handles this translation automatically when you set reasoning params on a Gemini model.

Recommended Config:

{
  "agents": {
    "defaults": {
      "thinkingDefault": "medium"
    }
  }
}


Then per-model overrides where needed (example: MiniMax at HIGH):

"openrouter/minimax/minimax-m2.5": {
  "params": {
    "temperature": 0.3,
    "reasoning": {
      "effort": "high"
    }
  }
}


The Decision Framework

This is the core logic your agent needs to internalize. Add this to your TOOLS.md or AGENTS.md:

Step 1: Classify the task. What KIND of work is this?
Simple check/scan? (email, calendar, status)
Tool-heavy operation? (API calls, file operations, message sends)
Deep thinking? (strategy, writing, complex problem-solving)
Research? (finding information, fact-checking, web lookups)
Code? (generation, debugging, refactoring)
Creative? (writing copy, brainstorming, marketing)
Routine/heartbeat? (scheduled checks, monitoring)

Step 2: Pick the right model. Match the task category to the model that does it best (see the Model Selection Matrix below).

Step 3: Pick the right thinking level. Match the effort to the complexity:
Low: Simple scans, routine checks, quick messages
Medium: General work, writing, tool operations
High: Complex analysis, multi-step planning, debugging
XHigh: Maximum depth analysis (rare, expensive)

Step 4: Switch if needed. Use /model <alias> and /reasoning <level> BEFORE starting the task. If already on the right model, proceed without switching.

The Model Selection Matrix

This is the heart of the routing system. It maps every common task type to the best model and thinking level.

| Task Category | Best Model(s) | Thinking Level | Rationale |
|---|---|---|---|
| Heartbeat Phase 1 (scan emails, calendar, triage priorities) | MiniMax M2.5 | low | Cheap ($0.30/$1.10), supports tool calls, fast enough for scanning. Don't waste expensive models on reading emails. |
| Heartbeat Phase 2 (execute tasks from Phase 1) | Varies per task | Varies | Route each identified task to its best model. See Heartbeat Routing section below. |
| Tool-heavy operations (API calls, file management, cron jobs, config changes, message sends) | MiniMax M2.5, Opus, or Sonnet | medium | MUST support tool calls. Kimi CANNOT do tool calls. MiniMax is cheapest with tool support. Use Opus for complex multi-step tool chains where reasoning matters. |
| Deep strategy and analysis (business planning, complex decisions, coaching frameworks, architecture) | Opus | medium to high | Best reasoning capability, most nuanced understanding, highest quality output. This is where Opus earns its premium price. |
| Long-form writing (documents, guides, SOPs, client deliverables, proposals) | Opus or Sonnet | medium | Writing quality and formatting precision matter. Opus for important/client-facing, Sonnet for internal/less critical. |
| Quick writing (short messages, Slack DMs, quick emails, status updates) | MiniMax M2.5 or Sonnet | low | Don't waste Opus tokens on a 2-sentence message. MiniMax handles this fine. |
| Code generation (writing new code, scripts, automation, refactoring) | Kimi K2.5 or Codex | built-in (Kimi) / medium (Codex) | Kimi K2.5 is cheap ($0.23/$3.00) with built-in reasoning and 262K context. Its killer feature: you can spin up HUNDREDS or even 1,000+ sub-agents simultaneously for parallel code execution. It just can't do tool calls. A master agent (Opus) manages the swarm. Codex for code that also needs tool interaction. |
| Code debugging (fixing errors, reading logs, troubleshooting, testing) | Opus or Codex | medium to high | Need both strong reasoning AND tool calls to read files, run tests, iterate on fixes. Kimi can't do this because no tool calls. |
| Research and fact-finding (web search, current information, verification, citations) | Perplexity Sonar Pro | medium | Built specifically for search with real-time web access. Provides cited sources. Other models would need external search tools. |
| Quick factual answers (simple questions, lookups, math, definitions) | GPT-5 Nano or Haiku | low | Cheapest and fastest. Don't overthink simple stuff. Nano is $0.05/$0.40. |
| Image and media generation (creating images, processing media, video generation) | Any model with tool calls (MiniMax is fine) | low | The model just needs to correctly call the Kie.ai or image generation skill. It's not doing the creative work itself. |
| Document formatting (Google Docs API, PDF creation, complex formatting) | Opus or Sonnet | medium | Complex API call sequences, quality matters, needs reliable tool support and attention to detail. |
| Client-facing communications (emails to clients, professional messages, proposals) | Opus | medium | Tone, nuance, and quality matter most when the user's name and reputation are on it. |
| Data processing (parsing CSVs, transforming data, batch operations, calculations) | MiniMax M2.5 or DeepSeek | low to medium | Cost-effective for mechanical, repetitive work. Don't need premium reasoning for data transformation. |
| Creative brainstorming (marketing ideas, campaign concepts, naming, positioning) | Opus or Mistral Creative | medium to high | Opus for strategy-connected creativity. Mistral Creative for pure ideation and divergent thinking. |
| Quality control (reviewing sub-agent output, verifying deliverables) | Opus or Gemini 3.1 Pro | medium to high | Best reasoning for catching errors and verifying quality. This is the QC layer. Never deliver sub-agent output without running it through QC first. |
| Planning and blueprinting (architecture, project planning, task decomposition, strategy) | Opus | medium to high | Creates the plan that other models execute. Masterminding, strategic thinking, decision-making. The boss model. |
| Swarm orchestration (managing 100s-1000s of sub-agents, assigning tasks, receiving results) | Opus | medium | The conductor. Assigns tasks to the right models, monitors progress, assembles final output from swarm results. |

Model Capabilities Quick Reference

This table helps the agent quickly determine what each model CAN and CANNOT do:

| Model | Alias | Tool Calls | Thinking | Best For | Cost Tier | Notes |
|---|---|---|---|---|---|---|
| Claude Opus 4.6 | opus | YES | medium | Strategy, writing, complex tasks | $$$$$ ($5/$25) | The premium specialist. Reserve for high-value work. |
| Claude Sonnet 4.6 | sonnet | YES | medium | Balanced quality and cost | $$$$ ($3/$15) | Good middle ground. Quality close to Opus at lower cost. |
| Claude Haiku 4.5 | - | YES | medium | Quick quality tasks | $$ ($1/$5) | Fast, cheap, still Claude quality. Good for simple tool operations. |
| MiniMax M2.5 | - | YES | HIGH | Daily tasks, tool calls, heartbeat | $$ ($0.30/$1.10) | The daily workhorse. Cheap with tool calls AND high thinking. Default for operations. |
| Kimi K2.5 | kimi | NO | built-in | Code swarms (cheap, massively scalable) | $ ($0.23/$3.00) | Can spin up 100s-1000s of sub-agents for parallel code. 262K context. CANNOT do tool calls. Needs a master agent (Opus) to orchestrate. |
| GPT-5.2 Codex | codex | YES | medium | Code plus tool hybrid tasks | $$ ($0.25/$2) | When you need both code AND tool calls. |
| GPT-5 Mini | - | YES | medium | General purpose, cost-effective | $$ ($0.25/$2) | Solid all-around at moderate cost. |
| GPT-5 Nano | - | YES | medium | Quick simple tasks | $ ($0.05/$0.40) | Cheapest option that still works. Use for trivial tasks. |
| Gemini 3.1 Pro | gemini3 | YES | medium | Multimodal, long context | $$$ ($2/$12) | 1M token context. Good for processing large documents. |
| Gemini 3 Flash | - | YES | medium | Fast multimodal tasks | $$ ($0.50/$3) | Cheaper Gemini option. Still 1M context. |
| DeepSeek V3.2 | - | YES | medium | Cost-effective general work | $ ($0.26/$0.38) | Very cheap. Good for bulk/batch processing. |
| DeepSeek R1 Free | - | YES | medium | Free reasoning tasks | FREE | Free option with reasoning. Use when cost matters. |
| Mistral Small Creative | - | YES | none | Creative writing, ideation | $ ($0.10/$0.30) | No thinking model, but good for divergent creative tasks. |
| Perplexity Sonar Pro | - | NO* | N/A | Research, web search | $$$ ($3/$15 + search fees) | Built-in web search. "Tool calls" are its search, not OpenClaw tools. |
| Qwen 3.5 Plus | - | YES | medium | General purpose, large context | $$ ($0.40/$2.40) | 1M context. Solid alternative. |
| GLM-5 | - | YES | medium | General purpose | $$ ($0.30/$2.55) | Chinese model. Good reasoning at moderate cost. |

Thinking Level Guide

| Level | When to Use | Cost Impact | Examples |
|---|---|---|---|
| off | Never for thinking models (wastes their capability) | Cheapest | - |
| minimal | Not recommended. Either think or don't. | Very low | - |
| low | Simple scans, routine checks, quick messages, image generation calls | Low | Heartbeat Phase 1, sending a Slack DM, checking calendar |
| medium | DEFAULT for most work. Writing, tool operations, general tasks | Moderate | Document creation, email composition, standard tool operations |
| high | Complex analysis, multi-step planning, debugging, MiniMax default | Higher | Architecture decisions, debugging production issues, multi-step API chains |
| xhigh | Only when explicitly requested. Maximum depth analysis. | Expensive | Deep strategic analysis, critical business decisions |

Cost awareness: Reasoning tokens are billed as OUTPUT tokens. Higher thinking levels mean more output tokens, which means higher cost. This is why you don't set everything to "high" - you match the level to the task.

Heartbeat Routing (Automated Task Execution)

The heartbeat is where intelligent routing matters most, because it runs autonomously without user input. The agent needs to be smart about cost and model selection on its own.

Phase 1: Morning Scan
Switch to: MiniMax M2.5 (/model minimax or equivalent)
Thinking: low (/reasoning low)
What to do: Check emails across all accounts, check calendar, scan for alerts, scan messaging platforms for unread important messages, produce a prioritized task list
Why MiniMax: It's cheap, supports the tool calls needed to check email/calendar/messages, and Phase 1 doesn't require deep reasoning. You're just reading and summarizing.
Output: A prioritized list of tasks that need attention

Phase 2: Task Execution
Each task identified in Phase 1 gets routed to the right model:

| Identified Task | Route To | Thinking | Why |
|---|---|---|---|
| "Send the user a summary of findings" | Stay on MiniMax | low | Just composing and sending a message |
| "Reply to client email about project timeline" | Switch to Opus | medium | Client-facing communication needs quality |
| "Check Stripe for failed payments" | Stay on MiniMax (tool calls) | low | Mechanical API check |
| "Research competitor pricing" | Switch to Perplexity | medium | Needs web search with citations |
| "Generate a project report/document" | Switch to Opus or Sonnet | medium | Writing quality matters |
| "Fix a broken cron job or config issue" | Switch to Opus or Codex | medium to high | Debugging needs strong reasoning plus tool calls |
| "Send a quick Slack DM or status update" | Stay on MiniMax | low | Don't waste tokens on 2 sentences |
| "Create images for a project" | Stay on MiniMax | low | Just calling the image generation skill |
| "Write or debug a script" | Switch to Kimi (no tool calls needed) or Codex (tool calls needed) | built-in / medium | Kimi is free for pure code |
| "Process data or batch operations" | Stay on MiniMax or switch to DeepSeek | low to medium | Mechanical work, cost matters |

Phase 3: Return to Baseline
After all tasks are executed:
If the user is actively chatting: Stay on whatever model the user prefers (usually the primary model)
If running autonomously: Switch back to the cost-effective model (MiniMax) and wait

The Swarm Architecture Pattern (Boss + Workers + QC)

This is the most powerful multi-model pattern. It uses Opus as the brain and cheaper models as the hands.

The Boss Layer (Opus)
Opus is the CEO of the operation. Its job:
Receive the task from the user
Break it into sub-tasks (planning, blueprinting)
Decide which model handles which sub-task
Spawn sub-agents and assign work
Mastermind and make strategic decisions
Receive results back from all sub-agents
Does NOT do the grunt work itself. Too expensive for execution.

The Worker Layer (Kimi, MiniMax, DeepSeek, etc.)
These models do the actual work:
Kimi K2.5 is the code army. Can spin up HUNDREDS or even 1,000+ sub-agents simultaneously for parallel code generation. 262K context per agent. Cannot do tool calls, but doesn't need to - it produces code/text output and sends it back to the boss.
MiniMax M2.5 handles tool-heavy execution. API calls, file operations, message sends, anything requiring tool interaction.
DeepSeek handles cost-effective general execution. Good for mechanical, repetitive, or bulk processing work.
Codex handles hybrid code + tool tasks. When code needs to also run tests or interact with files.

The QC Layer (Opus or Gemini 3.1 Pro)
Before ANY sub-agent output reaches the user:
Run it through Opus or Gemini 3.1 Pro for quality control
Check code quality, verify outputs, catch errors, ensure coherence
This is NON-NEGOTIABLE. Never deliver unreviewed sub-agent output.
Both Opus and Gemini 3.1 Pro excel at this role due to their strong reasoning and attention to detail.

The Full Pattern:

User gives task to Opus
Opus analyzes, plans, decomposes into sub-tasks
Opus assigns: "Sub-tasks 1-50 go to Kimi. Sub-task 51 goes to MiniMax."
Kimi agents execute code tasks in parallel (50 agents = 50x speed)
MiniMax agents handle tool operations in parallel
All results flow back to Opus
Opus (or Gemini 3.1) reviews EVERY result (QC pass)
Opus assembles the final deliverable
Opus presents polished output to user


Why this pattern works financially:
Opus plans the work: ~2,000-5,000 tokens (small cost)
50 Kimi agents each write code: 50 x ~3,000 tokens at $0.23/$3.00 (moderate total cost)
Opus reviews all 50 outputs: ~10,000 tokens (moderate cost)
Total: MUCH cheaper than Opus doing all 50 code tasks itself at $5/$25 per million tokens

Implementation in OpenClaw:
Use sessions_spawn to create sub-agent sessions on Kimi for code tasks
Use sessions_spawn with MiniMax for tool-heavy tasks
The main session (on Opus) orchestrates and receives results
Use /model opus for the boss session, sub-agents automatically use their assigned model

When NOT to Switch Models

The routing system is powerful, but there are times you should NOT switch:

User is actively chatting. If the user is in a conversation with you, stay on whatever model you're on unless the task clearly requires a different one. Don't interrupt the conversation flow with model switches.

Mid-task. Never switch models halfway through a document, an API operation, or a multi-step process. Finish what you started on the current model.

Quick follow-ups. If the user says "now do X" right after "do Y" and both need the same model, don't switch.

Uncertainty. If you're genuinely not sure which model is best for a task, stay on the current model and make a note to evaluate later. A wrong switch is worse than no switch.

Low-stakes tasks. If the task is trivial and will take 10 seconds regardless of model, don't bother switching. The overhead of switching isn't worth it.

Cost Optimization Strategy

The whole point of intelligent routing is to get the best output at the lowest cost. Here are the rules:

Don't use Opus for heartbeat checks or grunt work. Opus is the BOSS, not the worker. It plans, blueprints, masterminds, manages sub-agents, and checks work quality. It does NOT write 1,000 lines of code or process batch data. That's what cheaper models are for.

Don't use Nano for client deliverables. Quality matters when your user's name and reputation are on it. The $0.05 savings is not worth a poorly written email to a client.

Kimi is the code army. At $0.23/$3.00, Kimi K2.5 is cost-effective for code generation at massive scale. Its killer feature is spinning up HUNDREDS or even 1,000+ sub-agents simultaneously for parallel code execution. It can't do tool calls, but it doesn't need to - a master agent (Opus) orchestrates the swarm and handles tool operations. This is Kimi's real power: scale.

DeepSeek R1 free tier is rate-limited. Good for low-volume internal reasoning tasks, but don't build production workloads on it. If you need reliable DeepSeek, use the paid tiers.

MiniMax is the daily workhorse. $0.30 input / $1.10 output with tool calls AND high thinking. This is the best value model for daily operational work. Default to this for tool-heavy tasks.

Opus is the boss and the QC layer. Use Opus for: planning, blueprinting, masterminding, strategic thinking, managing sub-agents, and quality control on returned work. Use Opus or Gemini 3.1 Pro to CHECK sub-agent output before delivering. Never send sub-agent work straight to the user without QC.

The swarm pattern saves money. Instead of Opus doing everything at $5/$25, have Opus plan the work (small token cost), spawn Kimi/MiniMax/DeepSeek agents to do the work (cheap), then have Opus review the results (small token cost). The total cost is a fraction of having Opus do it all.

Track and optimize. After each heartbeat or task cycle, evaluate: Did the model choices work? Was anything overkill? Could something have been cheaper without quality loss? Write observations to memory so future sessions can refine.



SECTION 9: HOW TO UPDATE YOUR WORKSPACE FILES

Why Workspace Files Matter

OpenClaw agents read their workspace files (TOOLS.md, AGENTS.md, HEARTBEAT.md, USER.md, MEMORY.md, SOUL.md) at the start of every session. These files ARE the agent's persistent brain. Without them, the agent wakes up with amnesia every time.

When you configure models, the config file handles the WHAT (which models exist, what params they use). But the workspace files handle the HOW (when to use which model, how to route tasks, what rules to follow). Both need to be correct and congruent for the system to work.

After configuring your models, you MUST update the workspace files to teach the agent how to use them intelligently. Here's exactly what goes in each file.

TOOLS.md - The Technical Reference

TOOLS.md is the agent's technical cheat sheet. It contains HOW to use tools, APIs, credentials, and models. This is where the Intelligent Model Routing matrix lives.

What to add after model configuration:

Verified Model Specs Table - A table with every configured model showing: context window, max output, input cost per million, output cost per million, and any special notes. Use verified numbers from OpenRouter live pages, not outdated training data.

Intelligent Model Routing Section - The complete decision framework:
   The 4-step decision process (classify, pick model, pick thinking, switch)
   The Model Selection Matrix (task categories mapped to models and thinking levels)
   Model Capabilities Quick Reference (tool calls yes/no, thinking support, cost tier)
   Thinking Level Guide (when to use each level)
   Cost-consciousness rules
   When NOT to switch

Model-Specific Notes - Any gotchas or special behaviors:
   "Kimi K2.5 CANNOT do tool calls. Use for code generation only."
   "MiniMax M2.5 defaults to HIGH thinking. This is the daily workhorse."
   "Perplexity's tool calls are its built-in web search, not OpenClaw tool calls."
   "Google Gemini uses thinking.type/budget format instead of reasoning.effort."

Context Window Thresholds - For compaction planning:
   At 80%: Warn user
   At 90%: Create handoff.md
   At 95%: Update handoff.md
   After compaction: Read handoff.md first

Example entry for TOOLS.md:

Intelligent Model Routing

The Decision Framework
Before executing ANY task:
Classify: What kind of work is this?
Model: Which model does this best?
Thinking: What level does this need?
Switch: Use /model <alias> and /reasoning <level> if needed

Model Selection Matrix
| Task | Best Model | Thinking | Why |
|------|-----------|----------|-----|
| Heartbeat scan | MiniMax M2.5 | low | Cheap, fast, tool calls |
| Client email | Opus | medium | Quality matters |
| Code generation | Kimi K2.5 | built-in | FREE |
| Research | Perplexity | medium | Built for search |
[... full matrix ...]


AGENTS.md - The Behavioral Rules

AGENTS.md defines HOW the agent behaves. It's the rules, the boundaries, the expectations. This is where you put the routing RULE (not the full matrix - that's in TOOLS.md).

What to add after model configuration:

Intelligent Model Routing Rule - A concise rule that says "Before executing any task, evaluate which model fits best and switch if needed." Point to TOOLS.md for the full matrix.

Key Constraints - The non-negotiable model rules:
   Kimi CANNOT do tool calls. Never route tool-heavy tasks to Kimi.
   MiniMax is the default workhorse for daily operations.
   Opus is reserved for complex strategy, important writing, client-facing work.
   Never modify config without explicit user permission.

Heartbeat Routing Summary - Brief Phase 1/Phase 2 instructions:
   Phase 1 (scan): MiniMax, thinking low
   Phase 2 (execute): Route per matrix in TOOLS.md

Example entry for AGENTS.md:

Intelligent Model Routing - THINK BEFORE YOU ACT
Before executing ANY task, run this decision loop:
What am I doing? Classify the task.
Which model fits best? Check TOOLS.md Model Selection Matrix.
What thinking level? Match effort to complexity.
Switch if needed using /model <alias> and /reasoning <level>.

Key rules:
Kimi K2.5 CANNOT do tool calls. Never route tool tasks to Kimi.
MiniMax M2.5 is the daily workhorse (cheap + tools + high thinking).
Opus is the specialist (complex strategy, writing, client-facing).
Full details: See TOOLS.md "Intelligent Model Routing" section.


HEARTBEAT.md - The Automated Routine

HEARTBEAT.md defines what the agent does during heartbeat polls (automated check-ins). This is where model routing matters most because the agent is operating autonomously.

What to add after model configuration:

Phase 1: Scan and Triage - Instructions to use MiniMax with low thinking for the initial scan. List what to check (email, calendar, messages, alerts).

Phase 2: Task Execution Routing Table - A table mapping each type of identified task to the right model and thinking level. Be specific:
   "Send summary" -> Stay on MiniMax, low
   "Reply to client" -> Switch to Opus, medium
   "Debug config" -> Switch to Opus or Codex, medium-high
   "Research topic" -> Switch to Perplexity, medium

Phase 3: Return to Baseline - Instructions to switch back to the cost-effective model after task execution.

Cost Awareness - Reminder to track model usage and optimize over time.

Example entry for HEARTBEAT.md:

Heartbeat Model Routing

Phase 1: Scan and Triage
Model: MiniMax M2.5 | Thinking: low
Tasks: Check emails, calendar, alerts, messages. Produce task list.

Phase 2: Execute Tasks
| Task | Switch To | Thinking |
|------|-----------|----------|
| Send summary | Stay on MiniMax | low |
| Client email reply | /model opus | medium |
| Fix broken config | /model opus | medium-high |
| Research topic | /model perplexity | medium |
| Generate images | Stay on MiniMax | low |
| Write/debug code | /model kimi or /model codex | varies |

Phase 3: Return to Baseline
After tasks: switch back to MiniMax if autonomous, stay on primary if user active.


USER.md - The User Context

USER.md describes WHO the agent is helping. It typically contains the user's preferences, timezone, communication style, and personal context. For model routing, add:

Model Preferences - Which model the user prefers for different situations:
   "Primary model: Claude Opus 4.6 for direct conversations"
   "Heartbeat model: MiniMax M2.5 for cost efficiency"
   "Code model: Kimi K2.5 for free code generation"

Cost Sensitivity - How cost-conscious the user is:
   "Use free models (Kimi, DeepSeek R1) for internal/non-critical work when possible"
   "Don't cheap out on client-facing communications"

Thinking Preferences - If the user has opinions on thinking depth:
   "MiniMax thinking should be HIGH"
   "Default medium for everything else"
   "Only use xhigh when I specifically ask for deep analysis"

MEMORY.md - The Persistent Brain

MEMORY.md is the agent's long-term memory. It survives across sessions and compactions. For model routing, add a condensed version of the routing system:

Routing Quick Reference - A compact table mapping tasks to models. Not the full matrix, but the essential mappings the agent needs to recall quickly.

Config State - Current config settings so the agent knows what's actually configured:
   "thinkingDefault: medium"
   "MiniMax reasoning: high"
   "24 models configured, 0 errors"

Lessons Learned - Any routing decisions that worked well or poorly:
   "MiniMax handles heartbeat Phase 1 well at low cost"
   "Opus is worth the premium for client emails"
   "Kimi can't do tool calls - learned this the hard way"

SOUL.md - The Identity

SOUL.md defines who the agent IS. For model routing, you generally don't need to add anything here unless the agent's identity includes being "cost-conscious" or "efficient" as a core trait. If so, add a brief note:

"Be resourceful with model selection. Don't burn expensive tokens on trivial tasks."
"Quality over cost for client-facing work. Cost over quality for internal operations."

Congruency Check

After updating all workspace files, verify they are CONGRUENT. That means:

No contradictions. If TOOLS.md says "use MiniMax for heartbeat" but HEARTBEAT.md says "use Opus for heartbeat," that's a conflict. Fix it.

No redundancy that could diverge. If the same information is in multiple files, make sure they reference each other rather than duplicating content that could get out of sync. Example: AGENTS.md should say "See TOOLS.md for full matrix" rather than copying the entire matrix.

Consistent model names. Use the same model names everywhere. Don't call it "MiniMax" in one file and "minimax-m2.5" in another without the alias connection being clear.

Consistent thinking levels. If you set MiniMax to HIGH in config, all files should reflect that. Don't have one file saying "medium" for MiniMax.

No stale information. After updating models or adding new ones, grep all workspace files for old model names or outdated specs. Remove or update them.

How to audit for congruency:

Find all model references across workspace files
grep -rn "model\|MiniMax\|Opus\|Kimi\|Perplexity\|Codex\|thinking\|reasoning" \
  TOOLS.md AGENTS.md HEARTBEAT.md USER.md MEMORY.md SOUL.md | sort


Review the output. Every mention of a model should be consistent with its capabilities, cost, and recommended use case. Every mention of thinking/reasoning levels should match the config.



SECTION 10: PUTTING IT ALL TOGETHER - FULL IMPLEMENTATION CHECKLIST

Use this checklist after configuring models to ensure everything is complete and congruent.

Config Layer
[ ] All models added to agents.defaults.models with correct openrouter/<author>/<slug> format
[ ] Temperature set per model (0.3 for most, 1.0 for Kimi K2.5)
[ ] Reasoning effort set per model (high for MiniMax, medium for most others, none for non-thinking models)
[ ] Google Gemini models use thinking.type/budget format instead of reasoning.effort
[ ] thinkingDefault set to medium in agents.defaults
[ ] Aliases configured for frequently used models
[ ] Primary model set (not overridden without permission)
[ ] Fallback model(s) configured
[ ] Config validated with openclaw doctor (0 errors)
[ ] Backup created before any changes

TOOLS.md Layer
[ ] Verified Model Specs table added with current numbers from OpenRouter
[ ] Intelligent Model Routing section added (decision framework, matrix, capabilities, thinking guide)
[ ] Cost-consciousness rules documented
[ ] Model-specific notes and gotchas documented
[ ] Context window thresholds documented

AGENTS.md Layer
[ ] Intelligent Model Routing rule added (concise, points to TOOLS.md)
[ ] Key model constraints listed (Kimi no tool calls, MiniMax is workhorse, Opus is specialist)
[ ] Heartbeat routing summary included (Phase 1/2 basics)
[ ] Config change permission rule present (never modify without user approval)

HEARTBEAT.md Layer
[ ] Phase 1 instructions (MiniMax, low thinking, what to scan)
[ ] Phase 2 task routing table (specific tasks mapped to models)
[ ] Phase 3 return-to-baseline instructions
[ ] Cost awareness reminder

MEMORY.md Layer
[ ] Routing quick reference table added
[ ] Current config state documented (thinkingDefault, per-model overrides, total models)
[ ] Key constraints listed (Kimi no tools, MiniMax workhorse, etc.)

USER.md Layer
[ ] Model preferences documented
[ ] Cost sensitivity noted
[ ] Thinking preferences noted

Congruency Audit
[ ] No contradictions across files
[ ] No redundant content that could diverge
[ ] Consistent model names everywhere
[ ] Consistent thinking levels everywhere
[ ] No stale information from old configurations
[ ] All files reference each other correctly (AGENTS.md points to TOOLS.md, etc.)


