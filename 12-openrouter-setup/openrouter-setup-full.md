
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

RULE 2: DO NOT CHANGE THE OPERATOR'S INTENT
These instructions say exactly what to do. Execute them exactly as written.
- Do NOT reinterpret steps
- Do NOT "improve" the instructions
- Do NOT skip steps because they seem unnecessary
- Do NOT add steps that are not in the document
- Do NOT change the order of steps
If a step says do X, do X. Not Y. Not a better version of X. X.

RULE 3: OPENROUTER CONFIG - ABSOLUTE ZERO TOLERANCE FOR DEVIATIONS
This is where agents most commonly go off-script. This will not happen.

YOU MAY ONLY ADD OR CHANGE WHAT THE USER EXPLICITLY TOLD YOU TO ADD OR CHANGE.

SPECIFICALLY:
- Do NOT add any model the user did not explicitly choose or approve
- Do NOT remove any model that the user did not tell you to remove
- Do NOT change any temperature, reasoning, or parameter that the user did not specify
- Do NOT change any API key - copy it exactly character for character
- Do NOT reorganize the config structure
- Do NOT rename any model entry
- Do NOT add comments or extra fields to the JSON
- Do NOT "clean up" or "optimize" the config file
- The config file is the user's property. You have ZERO authority to edit anything
  beyond exactly what this document specifies.

IF ANYTHING IS UNCLEAR: STOP AND ASK. Do not guess. Do not assume.
One unauthorized change to the OpenRouter config can break the entire gateway.

RULE 4: BACKUP BEFORE TOUCHING THE CONFIG - NON-NEGOTIABLE
Before making any change to ~/.openclaw/openclaw.json:
1. Run the full backup procedure from the Backup Protocol tab
2. Verify the backup exists and is not empty
3. Only then make the change
If the backup fails, STOP. Do not edit. Tell the user.

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

There is no prescribed primary model in this guide. The primary model is the client's choice: ask the client which model they want to use as their primary. If the client has already configured a default model, use the client's configured default model. Do not prescribe a specific model by name.

When configuring OpenClaw for a new user who does NOT already have a primary model set, ask them which model they want as primary before writing anything. If they have no preference and no configured default exists, stop and ask; do not silently substitute a model of your own choosing.

Recommendation you may offer (guidance only, never a hidden default): for a primary model, recommend a model with reliable tool calling, reasoning support, and a large output limit, because daily work mixes tool execution with multi-step tasks and a small output cap truncates long results. The client can override the recommendation; their selection is what gets configured.

If the user already has a primary model set, you must NOT override it. Instead, you must ASK them:

"You currently have [current primary model] set as your primary. Would you like to keep it, or switch your primary to a different model you choose?"

If they say keep it, respect that. If they do not respond within 60 seconds, leave their primary model alone. This is non-negotiable.

For users who need a high-capability primary: some users may specifically need a more powerful model as their primary. That is their choice. The agent should not fight them on it.

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

Valid model entry examples (the slugs below are placeholders: use the exact slug of a model the client chose, copied from its OpenRouter page):

"openrouter/<author>/<client-chosen-model>": {
  "alias": "<an alias the client approves>",
  "params": {
    "temperature": 0.3,
    "reasoning": true
  }
}

"openrouter/<author>/<another-model-the-client-chose>": {
  "params": {
    "temperature": 0.3
  }
}

INVALID model entry (will break the config):

"openrouter/<author>/<client-chosen-model>": {
  "params": { "temperature": 0.3 },
  "contextWindow": 196608,
  "maxTokens": 196608
}

If you add ANY key that is not alias, params, or streaming, the config will fail validation, OpenClaw will not start, and the user's entire setup will be broken. This is the single most common configuration error. Do not make it.

Rule 12: Temperature Settings

Temperature should be set at 0.3 for ALL models by default. Use a different value only where the client's chosen model's own OpenRouter page or documentation requires it, and record that exception where the client can see it. No model gets temperature 0. If in doubt, use 0.3.

Rule 14: THINKING MODEL COST WARNING PROTOCOL

Whenever you are about to use or configure a thinking-enabled model, you MUST warn the user about the additional cost. Thinking tokens (also called reasoning tokens) are billed as output tokens. This means enabling thinking on any model will increase the cost of every request. You must notify the user before engaging thinking mode. You must explain the cost impact. You must give them the option to proceed or decline.

Rule 15: THINKING LEVELS ARE PER-MODEL, NOT UNIFORM

Each model has its own default thinking level based on its role and capabilities. Do NOT apply a blanket thinking level across all models. Use these defaults:

Most models the client chooses: default thinking level MEDIUM. Medium balances quality and cost for general work.
Models with opt-in reasoning (an on/off reasoning parameter instead of effort levels): pass reasoning: true when spawning sub-agents on them.
Models with always-on reasoning: no parameter to set; reasoning is part of how the model runs.
Models with built-in thinking and no configurable parameter: nothing to set.
Models with no thinking support (for example, research models whose capability is built-in web search): no thinking parameter.

When the client picks a model for a role, look up how that model handles thinking on its OpenRouter page and record the default in the client's config notes. Escalate above the default only with the client's agreement (see Rule 14).

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

If at any point the system detects that the user has run out of OpenRouter credits, has insufficient funds, or receives a billing error, a payment error, or a 402/payment-required response from the API, the agent MUST immediately and automatically switch to the fallback model the client configured at setup (a free model if the client picked one) as the active model.

The agent must notify the user that it has switched to their configured fallback model and explain why. The agent continues operating on the fallback model until the user confirms they have added more credits.

If no fallback model is configured, the agent must notify the user and ask which model to use. It must NEVER silently substitute a named model the client did not choose.

The agent should NOT stop working or refuse tasks just because paid models are unavailable, as long as a configured fallback exists.

Rule 19: BACKUP BEFORE EVERY CHANGE

This is a reinforcement of Rules 3, 4, and 9. Before ANY config file modification, no matter how small, you create a timestamped backup first. If you are adding one model, you back up. If you are changing a temperature, you back up. If you are fixing a typo, you back up. Every. Single. Time.

Rule 20: MATCH MODEL COMPLEXITY TO TASK COMPLEXITY

Do not use a $25-per-million-token model to answer "What time zone is New York in?" Do not use a free model to architect a complex multi-step automation workflow. Match the model to the task. This is your responsibility.

Rule 21: VERIFY TOOL-CALL SUPPORT BEFORE ROUTING TOOL TASKS

Not every model supports tool calls. Some models are chat and code generation only: they do NOT support tool calls, function execution, or agentic task completion. If a task requires calling tools, executing functions, making API calls, or performing any operation that requires tool use, do NOT assign it to a model without tool-call support. Use one of the client's chosen models that does support tool calls instead. Check the model's capabilities on its OpenRouter page before routing. Assigning a tool-call task to a model that cannot do tool calls will cause the task to fail silently or produce errors.

Rule 22: VERIFY MODEL SPECS BEFORE CONFIGURING

Before writing any model into a config file, verify its current specifications at its OpenRouter model page: https://openrouter.ai/models/<model-slug>. Models get updated. Pricing changes. Context windows expand. Max output limits change. Do not rely solely on this guide's static specs table. Cross-check the live model page before every configuration. If the live page shows different numbers than this guide, use the live page numbers and flag the discrepancy.

Rule 23: ALIAS CONFLICT PROTOCOL

When adding OpenRouter models to a config that already has direct provider models, alias conflicts will occur (e.g., the user already has opus pointing to a direct Anthropic connection). When this happens, prefix the OpenRouter version with or-. Examples: or-opus, or-sonnet, or-codex, or-kimi. This is the standard naming convention. Do not improvise alternative prefixes. Do not overwrite the user's existing aliases. The or- prefix is consistent, predictable, and easy for the user to remember.

Rule 24: HEARTBEAT MODEL RESTRICTIONS

Heartbeat Phase 1 (the check) must ALWAYS use a fast, low-cost model: use the client's configured default model at low thinking. Under NO circumstances should a high-capability Thinking Tier model with reasoning enabled be used for heartbeat Phase 1 checks. Heartbeat checks do not need deep reasoning. They need speed. If multiple sub-agents are all running heartbeat checks on a Thinking Tier model, the token cost adds up across every single tick.

Recommendation: if the client wants a dedicated heartbeat model, recommend a low-cost model with tool-call support, because Phase 1 reads inboxes, calendars, and queues through tools and runs on every tick.

Rule 25: PRIMARY MODEL RECOMMENDATION

For new users who do NOT have a primary model configured: ask the client which model they want to use as their primary. If the client has already configured a default model, use the client's configured default model. If neither exists, stop and ask the client; never silently substitute another named model.

Recommendation you may offer (guidance only, never a hidden default): for a primary model, recommend a model with reliable tool calling and reasoning support at a sustainable cost, because the primary handles daily tool execution and multi-step work all day. The client's selection always wins.

For users who ALREADY have a primary model, ask them if they want to change it and explain the tradeoffs. If they decline, respect their choice. If they do not respond within 60 seconds, leave their existing primary model in place.

Rule 26: CONTEXT WINDOW MANAGEMENT PROTOCOL (HANDOFF)

The agent MUST track its context window usage throughout every session. Without this protocol, compaction destroys session continuity and the agent loses all context.

Step 1: On session start, calculate thresholds.

The agent looks up the exact context window size for its current active model on that model's OpenRouter page (https://openrouter.ai/models). It then calculates:

80% threshold = context window * 0.80
90% threshold = context window * 0.90
95% threshold = context window * 0.95

Example thresholds (a worked example for a model with a 262,144-token context window; calculate the same way for whichever model the client chose, using its real context window from its OpenRouter page):

| Context Window | 80% | 90% | 95% |
|----------------|-----|-----|-----|
| 262,144 | 209,715 | 235,930 | 249,037 |

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

If the agent does not know its context window size: It cannot calculate these thresholds. In this case, the agent must immediately check which model it is running on, look up the context window on that model's OpenRouter page, and calculate the thresholds before proceeding with any work. If it cannot determine its model or context window, it must notify the user that context management is not possible and recommend they manually track session length.

Rule 27: SUB-AGENT MODEL SELECTION

When operating in multi-agent orchestration mode, the master agent must select the correct sub-agent model for each sub-task, from the models the client chose. The selection logic is capability-based:

Sub-task requires tool calls or function execution = one of the client's chosen models that supports tool calls. Never assign a tool-call sub-task to a model that does not support tool calls.
Sub-task is code generation = the client's chosen code model, or the client's configured default model.
Sub-task is creative writing = the client's chosen writing model, or the client's configured default model.
Sub-task is research or fact-checking = the client's chosen research model (a model with built-in web search), or the client's configured default model.
Sub-task is a general operation that does not fit the above = the client's configured default model.

If the client has not chosen a model for a sub-task type and no configured default fits, the master agent asks the client which model to use rather than silently substituting one.

The master agent must also set the thinking level per sub-task based on complexity (medium, high, or xhigh) and set max_tokens to the sub-agent model's actual maximum output limit so the model is not artificially capped. See the Multi-Agent Orchestration section for the full sub-agent selection guidance and the reasoning budget formula.

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

Model ID Format

Every model ID follows this format: openrouter/<author>/<slug>, where <author> and <slug> are copied exactly from the model's page on OpenRouter (https://openrouter.ai/models).

CORRECT: openrouter/<author>/<slug> (the full ID exactly as shown on the model's OpenRouter page)
WRONG (will break): the same ID without the openrouter/ prefix, or an abbreviated or renamed slug

NEVER Use These

openrouter/auto - auto-routing breaks configs. Forbidden.
Direct provider calls without the openrouter/ prefix (unless the user has a direct API key for that specific provider)

You can verify the exact format for each model on the OpenRouter models page: https://openrouter.ai/models

STEP 4: MODEL SELECTION STRATEGY

This section defines how to pick a model for a task, when, and why. The models are organized into five tiers. Each tier is a kind of work, not a fixed model. The client chose which of their models fills each tier at setup; if the client did not choose one for a tier, the client's configured default model fills it. Using the wrong tier for a task either wastes money or delivers poor results. Both outcomes are unacceptable.

Tier 1: Thinking Tier

For complex decisions, planning, blueprinting, architecture, deep analysis, critical reasoning, and high-stakes work.

Model: the client's choice for complex work, or the client's configured default model.
Recommendation: a model with strong extended thinking/reasoning support, because deep analysis is what this tier is for. These models cost more per token but deliver significantly deeper analysis on complex tasks. Default thinking level: MEDIUM for Thinking Tier models. Only escalate to maximum with user permission.

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

Model: the client's choice for daily work, or the client's configured default model.
Recommendation: a cost-effective, fast model with reliable tool calling, because this tier handles the majority of day-to-day work and runs all day. For multimodal tasks (images, video, audio), use the client's chosen multimodal model.

CRITICAL: Tool-call capability warning

Not every model can perform tool calls. A model without tool-call support is a chat and code generation model only. Do NOT assign it to any task that requires tool execution, API calls, function calls, or agentic task completion. Check each model's capabilities on its OpenRouter page before routing. A model without tool-call support can still be the client's choice for:

Code creation and code generation (writing scripts, building components, writing massive amounts of code)
Back-and-forth conversational chat and brainstorming
Operating as a sub-agent under a master agent's control (receiving instructions, generating code output, returning results)
Rapid-fire ideation and iteration on code or text
Data scraping at scale, where the chosen model supports running as many parallel instances: each instance handles its own scraping task independently, and a coordinating master agent collects the results. This is high-volume parallel processing where each agent receives its own focused instruction, processes its target, and returns results to a coordinating master agent.

Heartbeat Protocol: Two-Phase Operation

Heartbeat is a two-phase operation. If the wrong model is used for Phase 1, and multiple sub-agents are all running heartbeat checks simultaneously, the token cost scales with every tick.

Heartbeat has two distinct phases, and each phase uses a DIFFERENT model.

PHASE 1: THE CHECK (Use the client's configured default model)

Phase 1 is lightweight. The heartbeat wakes up on its schedule and asks one question: "What needs to get done right now?" It is reading a task queue, checking a calendar, scanning for due items. That is ALL it does. It does not reason. It does not plan. It does not execute. It checks.

Phase 1 model selection: use the client's configured default model at low thinking. If the check requires calling a function to retrieve the task list, the model used for the check must support tool calls; if the configured default does not, use the client's chosen tool-capable model for the check.

FORBIDDEN for Phase 1: Under NO circumstances should a Thinking Tier model with reasoning enabled EVER be used for heartbeat Phase 1 checks. Heartbeat checks do not need deep reasoning, and premium output pricing for a status check is waste.

PHASE 2: THE DISPATCH (Route to the right model for the actual work)

Once Phase 1 identifies that something needs to get done, Phase 2 determines WHAT kind of task it is and routes it to the appropriate model based on the instructions in this guide. The heartbeat itself does NOT do the work. It identifies the work and hands it off.

Phase 2 dispatch logic:

The heartbeat check returns a task (or list of tasks) that need execution
For each task, the agent evaluates what kind of work it is using the Scenario-Based Model Routing Guide in this document
The agent routes the task to the client's chosen model for that kind of work:
   Complex architecture or planning? Route to the client's chosen Thinking Tier model
   Code generation? Route to the client's chosen code model
   Creative writing? Route to the client's chosen writing model
   Research or fact-checking? Route to the client's chosen research model
   Routine task requiring tool calls? Route to the client's chosen tool-capable model
   Simple factual lookup? Route to the client's configured default model, or the client's configured fallback if they set one for this
If it is unclear which model to use: use the client's configured default model.
If there is no configured default and the choice is still unclear: Ask the user which model they want for this task. If the user does not respond within 60 seconds, proceed with the model currently active and log the decision so the user knows what happened.

Why this matters: The token cost of heartbeat Phase 1 is minimal when the right model is used. The token cost from Phase 2 comes from the dispatched model doing the actual work. That cost is appropriate because the right model is being used for the right task.

When to use Execution Tier:

Daily task execution and routine operations
Sending messages and routine communications
Tool calls and function execution
Heartbeat Phase 1 checks (the client's configured default model)
Heartbeat Phase 2 dispatch: route to the appropriate model per this guide
Code creation and generation (the client's chosen code model)
Data scraping at scale with parallel agents, where the client's chosen model supports it
Real-time back-and-forth chat
Quick summaries of short documents
Simple Q&A and factual questions
Content drafts and simple edits (any Execution Tier model the client chose)

Tier 3: Creative Tier

For all creative writing, content creation, copywriting, and narrative work.

Model: the client's choice for writing, or the client's configured default model.
Recommendation: a model chosen for writing quality at a sustainable per-token cost, because creative writing does not need deep reasoning or thinking tokens and runs at high volume.

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

Tier 4: Fallback Tier

The fallback models are the ones the client configured at setup, in the order the client approved. They activate in order when the primary model fails or credits are depleted. CRITICAL: DO NOT set any fallback as the user's primary model without their explicit permission. They are fallbacks only. If the client configured no fallback, there is no automatic switch: notify the user and ask (see Rule 18).

When this activates:

User's OpenRouter balance hits zero
API returns a 402 (Payment Required) error
API returns any billing-related error
User explicitly states they have no credits remaining

What the agent must do:

Immediately switch to the client's configured fallback model
Notify the user: "Your OpenRouter credits appear to be depleted. I have automatically switched to your configured fallback model so we can continue working. When you are ready, add credits at https://openrouter.ai/credits and let me know so I can switch back to your preferred model."
Continue operating normally on the fallback model
When the user confirms credits have been added, switch back to their configured primary model

Tier 5: Research Tier

For research, fact-checking, web search, validation, and verifying information as truth.

Model: the client's chosen research model, or the client's configured default model.
Recommendation: a model with built-in web search, because current facts, prices, and statuses cannot come from training data. For deep work (multi-source research, competitor analysis, technical lookups requiring multiple sources, market research), use the chosen research model at its full capability; for quick factual lookups and single-fact checks, a lighter pass on the same tier is fine.

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

Simple factual questions the agent already knows with certainty (use the client's configured default model)
Creative writing tasks (use the client's chosen writing model)
Code generation (use the client's chosen code model)
Daily task execution (use the client's chosen daily model)

Pricing note: research models with built-in web search may charge a per-search fee on top of token costs. Check the chosen model's OpenRouter page for its current pricing so the client can make an informed decision.

Model Specifications: Look Them Up Live

There is no static specifications table in this guide, on purpose: model specifications, prices, context windows, and output limits change, and a printed table goes stale and misleads. Before configuring or routing to any model, look up its current specifications on its OpenRouter page (https://openrouter.ai/models/<model-slug>) and record them in the client's TOOLS.md: context window, max output, input and output price per million tokens, thinking support and how it is configured, tool-call support, and any temperature requirement.

Important notes:

Always verify current pricing and specs at https://openrouter.ai/models before configuring. If a note in any document disagrees with the live page, the live page wins; flag the discrepancy.
Temperature is 0.3 for all models by default. A different value only where the chosen model's own documentation requires it.
Never route a tool-call task to a model that does not support tool calls. Verify tool-call support on the model's page.
Reasoning/thinking tokens are billed as OUTPUT tokens. Enabling thinking on a model will increase cost.
Thinking levels are PER-MODEL, not uniform. See Rule 15.
Research models with built-in web search may charge a per-search fee on top of token costs.
Context window is the total input capacity. Max output is the maximum response length the model can generate.
The agent must know the active model's context window to avoid premature compaction or context overflow errors (see Rule 26).

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
| Mission-critical | Xhigh | Production deployment planning, security audits, critical business strategy, complex multi-agent orchestration |

Note: Xhigh is the maximum reasoning level available on OpenRouter (0.95 effort ratio), supported by reasoning-capable models that offer effort levels. Use it only when the task demands maximum analytical depth and the user has approved the additional token cost.

Scenario-Based Model Routing Guide

These examples teach the agent how to pick a model for a type of task. In every scenario, "Use" means the client's choice for that kind of work, or the client's configured default model. Recommendations describe the capability profile to suggest when the client asks, with the reason; the client's selection always wins.

SCENARIO 1: User asks a simple factual question

Example: "What time zone is New York in?"
Use: Model: the client's choice, or the client's configured default model.
Why: Simple factual lookup. No reasoning required.

SCENARIO 2: User asks to write a social media post

Example: "Write me an Instagram caption for this product photo"
Use: Model: the client's choice for writing, or the client's configured default model.
Why: Creative content does not need thinking tokens.

SCENARIO 3: User asks to write a long blog post

Example: "Write a 3,000-word blog post about real estate investing strategies"
Use: Model: the client's choice for writing, or the client's configured default model.
Why: Long-form creative writing. Recommendation: a writing model with a sustainable per-token cost, because long-form work is high-volume.

SCENARIO 4: User asks to draft a professional email

Example: "Draft an email to my client about the project timeline update"
Use: Model: the client's choice for writing, or the client's configured default model.
Why: Email content is creative/communication work, not deep reasoning.

SCENARIO 5: User asks to debug a Python script

Example: "This script is throwing a TypeError on line 47, help me fix it"
Use: Model: the client's chosen code model (Thinking Tier settings, thinking at medium) for complex debugging, or the client's chosen code model for straightforward fixes and code generation.
Why: Deep multi-file debugging needs reasoning and, when the fix must run tools, tool-call support. Direct code fixes where the problem is clear do not.

SCENARIO 6: User asks to plan a multi-step automation workflow

Example: "Help me design an N8N workflow that processes leads from GoHighLevel"
Use: Model: the client's chosen high-capability model (Thinking Tier, thinking at medium), or the client's configured default model.
Why: Complex architecture and multi-step planning require deep reasoning.

SCENARIO 7: User asks to analyze a long document

Example: "Analyze this 200-page PDF and summarize the key findings"
Use: Model: the client's chosen large-context model (Thinking Tier, thinking at medium).
Why: Recommendation: a model with a very large context window (around 1M tokens), because the whole document has to fit in context at once.

SCENARIO 8: User needs a quick summary

Example: "Summarize this short Slack thread for me"
Use: Model: the client's choice, or the client's configured default model.
Why: Fast and capable enough for simple summarization.

SCENARIO 9: User asks to refactor an entire codebase

Example: "Refactor this entire React app from class components to hooks"
Use: Model: the client's chosen high-capability code model (Thinking Tier, recommend maximum thinking).
Why: Multi-file refactoring is high-complexity. Warn user about cost. Recommend max thinking.

SCENARIO 10: User asks to build a detailed project plan

Example: "Create a project plan with milestones and deliverables for our Q2 launch"
Use: Model: the client's chosen high-capability model (Thinking Tier, thinking at medium), or the client's configured default model.
Why: Structured reasoning without maximum-tier cost. Good balance of depth and efficiency.

SCENARIO 11: User asks to write a book or multiple chapters

Example: "Write chapter 3 of my real estate investing book" or "Help me write my book"
Use: Model: the client's chosen writing model as sub-agents, controlled by a Thinking Tier master agent (the client's chosen high-capability model).
Architecture: A writing model does not need to hold an entire book in one context window. The correct approach is a multi-agent architecture:
  Master Agent (Thinking Tier, large context): Holds the book outline, chapter summaries, character profiles, tone guidelines, continuity notes, and overall structure. This agent plans what each chapter should cover and reviews output for consistency.
  Sub-Agents (the client's chosen writing model, one per chapter): Each instance receives targeted instructions from the master agent for its specific chapter. It writes the chapter, returns the output, and the master agent reviews it before moving to the next.
  Multiple calls, not one giant session: Spin up the writing model multiple times. Each call is a fresh, focused chapter task with clear direction from the master agent. This keeps each call well within the context window while producing a full book.
Why: This architecture uses the client's chosen writing model for the bulk of writing while using the Thinking Tier master agent only for planning, guidance, and quality control. The writing workload is distributed across multiple focused calls rather than routed through a single model.

SCENARIO 12: User needs rapid back-and-forth chat

Example: "Let's brainstorm ideas quickly, just rapid-fire"
Use: Model: the client's choice for chat, or the client's configured default model.
Why: Conversational flow and rapid iteration. No tool calls needed for brainstorming.
Note: If the brainstorming session leads to tasks that need execution (sending messages, calling APIs, creating files), hand those tasks off to one of the client's chosen tool-capable models for execution while the conversation continues.

SCENARIO 13: User asks to review a business proposal

Example: "Review this business proposal and give me critical feedback"
Use: Model: the client's chosen high-capability model (Thinking Tier, thinking at medium).
Why: Analytical depth at a sustainable cost. Good for structured critique.

SCENARIO 14: User asks for complex agentic workflow design

Example: "Design a system with multiple AI agents that coordinate to process orders"
Use: Model: the client's chosen high-capability model (Thinking Tier, thinking at medium).
Why: Recommendation: a model strong at agentic planning and long-horizon workflows, because the design has to hold many coordinated steps at once.

SCENARIO 15: User has run out of credits

Detection: API returns 402 or billing error
Use: Model: the fallback the client configured at setup (Emergency Fallback Tier). If none is configured, notify the user and ask.
Why: A configured fallback keeps the user operational until they add credits. Do not stop working, and do not silently substitute a model the client did not choose.

SCENARIO 16: User needs to research, validate, or fact-check something

Example: "Is this statistic about real estate conversion rates accurate?" or "What are the current API pricing changes for GoHighLevel?" or "Research the best CRM tools for real estate agents in 2026"
Use: Model: the client's chosen research model (Research Tier).
Why: Recommendation: a model with built-in web search, because verifiable facts and current information cannot come from training data. Do not use a standard model to guess or rely on training data for verifiable facts.

SCENARIO 17: User needs a task executed that requires tool calls

Example: "Send that message" or "Create a new contact in the CRM" or "Run this automation"
Use: Model: the client's chosen tool-capable model (Execution Tier).
Why: The model must support tool calls. Do NOT assign tool-call tasks to a model without tool-call support.

SCENARIO 18: User needs to scrape data or process data in bulk

Example: "Scrape these 500 URLs and extract the pricing data" or "Process these listings and pull out the contact information"
Use: Model: the client's chosen model for parallel sub-agent work (Execution Tier, parallel agent mode), where that model supports running many instances at once.
Architecture: Spin up many simultaneous instances of the client's chosen model, each handling its own target. A master agent (the client's configured default model or a Thinking Tier model the client chose) coordinates the work, distributes targets to each instance, and collects results. Each agent receives a focused instruction, processes its target, and returns the output. This is high-volume parallel processing, not one model doing everything sequentially.
Why: Parallel instances are fast and cost-effective at scale. Tool calls are not needed for scraping when the master agent handles coordination and data collection.

SCENARIO 19: Master agent orchestrating mixed sub-tasks (code + tool calls + writing)

Example: "Build the landing page, set up the API endpoints, write the email sequence, and connect it all to the CRM"
Architecture: Master agent (the client's chosen high-capability model, Thinking Tier) breaks the project into sub-tasks:
  Code generation sub-tasks (landing page HTML/CSS, API endpoint scripts): Route to the client's chosen code model as sub-agent. Set max_tokens to that model's actual maximum output limit.
  Tool-call sub-tasks (CRM integration, API connections, webhook configuration): Route to the client's chosen tool-capable model as sub-agent. Set max_tokens to that model's actual maximum output limit.
  Writing sub-tasks (email sequence copy): Route to the client's chosen writing model as sub-agent. Set max_tokens to that model's actual maximum output limit.
  Research sub-tasks (verify CRM API documentation, check endpoint specs): Route to the client's chosen research model.
Thinking level per sub-task: Standard code generation = medium. Complex API integration = high. Critical production deployment = xhigh. Creative writing = as the chosen writing model requires.
Why: Each sub-agent is matched to its strengths. The master agent handles continuity and integration. Token cost stays appropriate per sub-task.

MULTI-AGENT ORCHESTRATION

This is a general operational principle, not limited to any single scenario. The agent must understand this pattern and apply it whenever it fits the task.

The Principle

A model with a small context window does NOT mean a limited model. It means the model needs to be orchestrated differently. Instead of cramming everything into one giant session, you split the work across multiple focused calls, each coordinated by a master agent with a larger context window.

The Pattern

Master Agent (Thinking Tier, large context window): Holds the full picture. Maintains the outline, structure, requirements, continuity, quality standards, and overall plan. This agent plans what each sub-agent should do and reviews the output. Use the client's chosen high-capability model, or the client's configured default model.
Sub-Agents (Execution, Creative, or specialized models the client chose): Each receives a focused, targeted instruction from the master agent. Each completes its specific piece of work within its own context window. Each returns output to the master agent for review and integration.
Multiple calls, not one giant session: The master agent calls the sub-agent multiple times, once per unit of work. Each call is fresh and focused. The sub-agent does not need to remember what happened in previous calls because the master agent handles continuity.

When to Apply This Pattern

Book writing: Master agent plans chapters, sub-agents (the client's chosen writing model) write individual chapters
Large codebases: Master agent plans the architecture, sub-agents (the client's chosen code model) write individual modules or files
Content campaigns: Master agent plans the campaign strategy, sub-agents (the client's chosen writing model) write individual posts, emails, and articles
Data processing: Master agent coordinates the pipeline, sub-agents handle individual data transformation steps
Data scraping at scale: Master agent coordinates work distribution, the client's chosen parallel-capable model runs as many simultaneous instances, each handling its own target independently
Any project that exceeds a single model's context window or benefits from specialization

Sub-Agent Model Selection Logic

When a master agent dispatches work to sub-agents, it MUST select the correct sub-agent model based on what the sub-task requires, from the models the client chose. This is not optional. The wrong sub-agent causes silent failures or wasted tokens.

Decision tree for sub-agent selection:

Does the sub-task require tool calls, function execution, API calls, or any interaction with external systems?
   YES: Use one of the client's chosen models that supports tool calls. This includes heartbeat operations, sending messages, calling APIs, executing functions, and any operation that requires the model to invoke a tool.
   NO: Proceed to step 2.
Is the sub-task code generation? (writing scripts, building modules, generating components, creating code files)
   YES: Use the client's chosen code model. If it supports parallel instances, it can run many at once for high-volume work. Each instance handles its own task independently.
   NO: Proceed to step 3.
Is the sub-task creative writing? (blog posts, social media, emails, articles, book chapters)
   YES: Use the client's chosen writing model.
   NO: Proceed to step 4.
Is the sub-task research or fact-checking?
   YES: Use the client's chosen research model (built-in web search).
   NO: Default to the client's configured default model for general task execution. If no default is configured, ask the client which model to use.

Sub-Agent Thinking Level Scaling

The master agent evaluates the complexity of each sub-task and sets the thinking level accordingly. This is per-call, not per-model. The same instance can run at medium thinking for a simple task and xhigh thinking for a complex one within the same orchestration session, where the model supports effort levels. Some models have built-in thinking with no configurable parameter; for those, the level is whatever the model provides.

| Sub-Task Complexity | Thinking Level | When to Use |
|---------------------|----------------|-------------|
| Simple, straightforward | Medium | Standard operations, routine task execution, basic data processing |
| Moderate complexity | High | Multi-step operations, tasks with conditional logic, moderate debugging |
| Maximum complexity | Xhigh | Critical path operations, complex multi-step workflows, security-sensitive tasks, tasks where failure is not acceptable |

Sub-Agent Max Output Token Configuration

IMPORTANT: max_tokens is set IN THE API REQUEST when the master agent spawns a sub-agent. It is NOT a config file setting. Do NOT add max_tokens, maxTokens, or any output limit to the agents.defaults.models section of openclaw.json. The config file only accepts alias, params, and streaming. max_tokens is a per-request parameter that the orchestrating agent sets when it dispatches work to a sub-agent.

Each model has a maximum output token limit; look it up on the model's OpenRouter page. When the master agent dispatches a sub-task, it MUST set max_tokens to the sub-agent model's actual maximum output (or the specific amount needed for the task, whichever is lower) so the model is not artificially capped below its capacity.

When reasoning is enabled: max_tokens must be set HIGHER than the reasoning budget. For models with effort-based reasoning, the budget is calculated from max_tokens using the formula in Rule 15. For models with on/off reasoning, reasoning tokens are consumed from the output budget. The master agent must set max_tokens high enough to accommodate both reasoning and response output.

Cost Benefit

This pattern keeps Thinking Tier usage limited to planning and review (low token count) while routing the bulk of generation work to Execution or Creative Tier models the client chose. The user pays Thinking Tier prices only for the orchestration, not for every word of output.

STEP 5: CONFIGURE THE OPENCLAW CONFIG FILE

OpenClaw has BUILT-IN support for OpenRouter. You do NOT need to configure models.providers. Just set your API key and reference models with the openrouter/<author>/<slug> format.

Configuration Template (the client's chosen models only)

Add your OpenRouter API key and the models the client chose to ~/.openclaw/openclaw.json. There is no fixed roster: primary is the client's chosen primary model (or their configured default), fallbacks are the client's chosen fallbacks in the client's approved order, and the models map contains one entry per model the client chose. If the client has not chosen a primary and has no configured default, stop and ask the client which model they want to use (see Rule 25). Never silently substitute another named model.

{
  "env": {
    "OPENROUTER_API_KEY": "sk-or-..."
  },
  "agents": {
    "defaults": {
      "model": {
        "primary": "openrouter/<author>/<client-chosen-primary-model>",
        "fallbacks": [
          "openrouter/<author>/<client-chosen-fallback-model>"
        ]
      },
      "models": {
        "openrouter/<author>/<client-chosen-primary-model>": {
          "params": {
            "temperature": 0.3,
            "reasoning": {
              "effort": "medium"
            }
          }
        },
        "openrouter/<author>/<each-additional-model-the-client-chose>": {
          "params": {
            "temperature": 0.3,
            "reasoning": {
              "effort": "medium"
            }
          }
        }
      }
    }
  }
}

Add one models-map entry per model the client chose, and only for those models. Use the params form each model actually supports: an effort object for effort-based reasoning models, reasoning: true for on/off reasoning models, and no reasoning key for models without reasoning support.

Temperature Settings Summary

ALL models: temperature 0.3 by default. A different value only where the chosen model's own OpenRouter page or documentation requires it, recorded where the client can see it.

Thinking/Reasoning Settings Summary

Default thinking level: medium for most models the client chooses, recorded per model at setup (see Rule 15).
Models with opt-in (on/off) reasoning: pass reasoning: true where the role needs it.
Models with built-in thinking and no configurable parameter: nothing to set.
Research models with built-in web search: no reasoning parameter.

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

LATEST_BACKUP="$(ls -t ~/openclaw-backup-configs/openclaw-backup-*.json | head -1)" && cp "$LATEST_BACKUP" ~/.openclaw/openclaw.json
openclaw gateway restart

Then review what went wrong before trying again. Do not keep editing a broken config. Restore, analyze, then attempt again with a fresh backup.

STEP 7: VERIFY IT WORKS

After restart, test that models are accessible:

Send a test message and confirm a response comes back
Check status: Run to see the active model
Test model switching: Try /model <alias> for one of the models the client chose, to confirm aliases work
Test fallback: Verify that if the primary model fails, the fallback engages

QUICK REFERENCE: BUILD THE ALIAS TABLE AT SETUP

There is no fixed quick reference table in this guide, because the aliases and models are the client's choices. At setup, build this table for the client's box from the models the client chose and record it in TOOLS.md:

| Alias | Model | Tier | Use For | Thinking | Temp |
|-------|-------|------|---------|----------|------|
| <alias the client approved> | <the client's chosen model slug> | <tier> | <the kind of work the client chose it for> | <per the model's OpenRouter page> | 0.3 unless the model's documentation requires otherwise |

One row per model the client chose. Keep it current whenever the client changes a model or an alias.

Environment Variable

OPENROUTER_API_KEY=sk-or-...

MD FILE UPDATE INSTRUCTIONS

When this configuration guide is applied, the agent MUST also update its internal knowledge files to reflect the models the client chose, their context windows, and the operational rules.

Files to Update

tools.md

Update with the following information for each model the client chose:

Context window size (looked up live on the model's OpenRouter page)
Maximum output token limit
When to trigger compaction (at 80% of context window capacity, not earlier)
Which models support which tools and capabilities (including tool-call support)
Context Window Management Protocol thresholds (80% warn, 90% create handoff.md, 95% update handoff.md)
The handoff.md creation process and required contents (Rule 26)

agent.md

Update with:

The five-tier model selection strategy (Thinking, Execution, Creative, Emergency Fallback, Research), filled by the client's chosen models or the client's configured default model
The model-switching permission protocol (Rule 16)
The thinking model cost warning protocol (Rule 14)
The zero-credit fallback protocol (Rule 18)
The tool-call capability rule (Rule 21): never route a tool-call task to a model that does not support tool calls
The scenario-based routing guide
Temperature settings (0.3 for all models by default; a different value only where a chosen model's documentation requires it)
The primary model is the client's choice, or the client's configured default model
The research model is the client's chosen model with built-in web search (all research, validation, fact-checking)
Sub-agent model selection logic (Rule 27): capability-based, from the models the client chose
Thinking level scaling for sub-agents: medium (standard), high (complex), xhigh (maximum complexity)
Max output token limits per chosen model so sub-agents are not artificially capped
Context Window Management Protocol (Rule 26): 80% warn, 90% create handoff.md, 95% update handoff.md
OpenRouter reasoning effort levels: minimal (0.10), low (0.20), medium (0.50), high (0.80), xhigh (0.95)
Reasoning budget formula: budget_tokens = max(min(max_tokens * effort_ratio, 128000), 1024)

memory.md

Update with:

Context window capacities for each model the client chose (so the agent knows when to compact or summarize)
Long-context management strategies: models with around 1M context can handle extended sessions without compaction
Short-context awareness: models with smaller windows require proactive session management
When to switch models mid-session if context is running low
The primary model is the client's choice, or the client's configured default model
The tool-call capability rule: never route tool tasks to a model that does not support tool calls
The research model is the client's chosen model with built-in web search
Context Window Management Protocol: 80% warn, 90% create handoff.md, 95% update handoff.md, post-compaction read handoff.md first (Rule 26)
The handoff.md file must be complete enough that a fresh agent can continue the session without asking the user to repeat anything
Threshold calculation: the agent must know its active model's context window to calculate 80/90/95% thresholds

Any Other Relevant .md Files

If the agent has additional knowledge files that reference model capabilities, pricing, or selection logic, those files must also be updated to reflect this guide.

TOKEN PROTECTION AND COST GUIDANCE RULES

The purpose of this entire configuration is to ensure the end user gets the best possible results for every task while matching model selection to task requirements.

Core Principles

Match model complexity to task complexity. Do not use a thinking-tier model for tasks that an execution-tier model handles perfectly well.
Default to the client's configured default model for daily task execution. It is the client's chosen workhorse: it should support tool calls and handle routine operations, and it is the first choice for any task that requires doing something (not just talking about it).
Route all creative/writing tasks to the client's chosen writing model. Social media, blog posts, emails, book chapters, marketing copy. All of it goes to the Creative Tier unless the user specifically requests a different model.
Route all research, validation, and fact-checking to the client's chosen research model (a model with built-in web search). Any time the agent needs to verify information, look something up, check if data is current, or research a topic, the research model handles it. Do not guess. Do not rely on training data for verifiable facts.
Route coding and code generation to the client's chosen code model. Never assign tool-call tasks to a model that cannot execute tools.
Warn before engaging thinking models. Every time. No exceptions. The user must know that thinking mode costs more.
Proactively guide the user to the right model. Do not wait for the user to ask "which model should I use?" Recommend the capability profile that fits, with the reason, as guidance the client can override. If the task does not require a Thinking Tier model, suggest the appropriate tier. If the task requires more capability than the current model provides, recommend the appropriate model.
Never let the system go dark because of billing. If credits run out, switch to the client's configured fallback immediately and keep working. If no fallback is configured, notify the user and ask.
Track and communicate cost implications. When recommending models, include the pricing context (from the models' live OpenRouter pages) so users can make informed decisions.
Track context window usage and create handoff.md before compaction. The agent must calculate 80/90/95% thresholds on session start. Warn at 80%. Create handoff.md at 90%. Update handoff.md at 95%. After compaction, read handoff.md first. The agent must know its active model's context window to calculate these thresholds.
Select the correct sub-agent model in multi-agent orchestration, by capability, from the models the client chose. Tool-call tasks go to a chosen model that supports tool calls. Code generation goes to the client's chosen code model. Creative writing goes to the client's chosen writing model. Research goes to the client's chosen research model. Set thinking level per sub-task complexity. Set max_tokens to the model's actual output limit.

COMMON MISTAKES TO AVOID

Using openrouter/auto - NEVER do this, it breaks configs. This is Rule 1. Memorize it.
Forgetting the openrouter/ prefix - Models will not route correctly without the full openrouter/<author>/<slug> format.
Not backing up before editing - One typo can break the gateway. One backup can save the day. Always back up first.
Using old model IDs - Always verify current model names at https://openrouter.ai/models before configuring. Models get updated, deprecated, and renamed.
Setting temperature for models that do not support it - Only set params when specifically needed. If in doubt, use the defaults from this guide.
Editing the config while the gateway is running without restarting after - Changes do not take effect until you restart. Always restart after config changes.
Deleting existing model configs - You are ADDING, never replacing. If it was there before, it stays there.
Overwriting aliases - If an alias is taken by a direct connection, use an alternative (e.g., or-<alias> for the OpenRouter version).
Configuring models.providers for OpenRouter - NOT needed. OpenClaw has built-in support. Adding this section causes confusion and potential conflicts.
Adding custom keys to model entries - The ONLY valid keys in agents.defaults.models entries are alias, params, and streaming. Adding ANY other key (contextWindow, maxTokens, _verified_context, cost, notes, tier, description, or ANYTHING else) will make the entire config invalid and OpenClaw will refuse to start. Context windows and max output limits are provided automatically by the model provider. Do NOT store them in the config. This is the #1 config-breaking mistake. See Rule 11.
Stripping the openrouter/ prefix from model IDs - This converts them to direct provider calls and breaks the OpenRouter routing entirely.
Using thinking/reasoning mode without warning the user about cost - Thinking tokens are billed as output tokens. The user must be notified before you enable thinking on any model.
Defaulting to maximum thinking level - Most models default to MEDIUM (see Rule 15). Only escalate with user permission and a clear justification.
Using a high-capability model for simple questions - Match the model to the task. Simple questions go to the client's configured default model or the Execution Tier.
Ignoring the 60-second timeout on model-switching - If the user does not respond within 60 seconds, proceed with your recommendation. Do not wait indefinitely.
Overriding the user's primary model without permission - The primary model is sacred. Do not touch it without explicit permission.
Failing to switch to the configured fallback when credits are depleted - If the API returns a billing error, switch to the client's configured fallback immediately. Do not stop working. If no fallback is configured, notify the user and ask which model to use.
Assigning tool-call tasks to a model that cannot do tool calls - If the task requires executing tools, calling functions, or performing actions, use one of the client's chosen models that supports tool calls. This will cause silent failures if ignored.
Using a standard model for research instead of the client's chosen research model - When the agent needs to verify facts, check current information, or research a topic, always route to the client's chosen research model with built-in web search. Do not guess or rely on training data for verifiable information.
Not verifying model specs before configuring - Always check the live OpenRouter model page before writing any model into a config. Specs change. Prices change. Do not blindly trust static tables.
Using Thinking Tier models for heartbeat checks - Heartbeat Phase 1 is a status check. Use the client's configured default model. Multiple sub-agents running heartbeat on Thinking Tier models accumulates token cost across every tick. This is Rule 24. Follow it.
Treating heartbeat as one model doing both checking and executing - Heartbeat has two phases. Phase 1 checks what needs to be done (the configured default model). Phase 2 dispatches the right model for the actual work. These are separate operations using separate models.
Not tracking context window usage - The agent must calculate 80/90/95% thresholds for its active model's context window on session start. If the agent does not know its context window size, it cannot create the handoff.md file in time. Compaction without a handoff file means total loss of session context. This is Rule 26.
Sending a tool-call sub-task to a model that cannot do tool calls in multi-agent orchestration - The master agent must route all tool-call sub-tasks to one of the client's chosen tool-capable models. Sending a tool-call sub-task to a model without tool-call support will fail silently. This is Rule 27.
Capping sub-agent max_tokens below the model's actual limit - Each model has a maximum output token limit. If the master agent sets max_tokens to a lower value, the sub-agent's output gets cut off. Set max_tokens to the model's actual limit (or the amount needed for the task, whichever is lower). Do not leave it at a default that chokes the output.
Ignoring the reasoning budget when setting max_tokens with thinking enabled - When reasoning is on, thinking tokens are billed as output tokens. For models with on/off reasoning, tokens are consumed from the output budget. For effort-based models, the reasoning budget is calculated FROM max_tokens. The master agent must set max_tokens high enough to accommodate both reasoning and the response output.

OFFICIAL OPENROUTER REFERENCE

The following is from the official OpenRouter documentation for OpenClaw integration (https://openrouter.ai/docs/guides/openclaw-integration). This section covers OpenRouter model format, fallback configuration, and troubleshooting. The user already has OpenClaw configured. This guide is strictly for configuring OpenRouter as the model provider.

Model Format

OpenClaw uses the format openrouter/<author>/<slug> for OpenRouter models:

openrouter/<author>/<slug-of-a-model-the-client-chose>
openrouter/<author>/<slug-of-another-model-the-client-chose>

Copy each slug exactly from the model's page at https://openrouter.ai/models.

NEVER use: openrouter/auto (Auto router picks models unpredictably and breaks configs)

Multiple Models with Fallbacks

{
  "agents": {
    "defaults": {
      "model": {
        "primary": "openrouter/<author>/<client-chosen-primary-model>",
        "fallbacks": [
          "openrouter/<author>/<client-chosen-fallback-model>"
        ]
      },
      "models": {
        "openrouter/<author>/<client-chosen-primary-model>": {},
        "openrouter/<author>/<client-chosen-fallback-model>": {}
      }
    }
  }
}

The primary and fallbacks are the client's choices, recorded at setup. A recommendation is never wired in as a primary or fallback value; only a model the client selected goes here.

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

Different channels can use different models the client chose (for example, a fast low-cost model on one channel and a more powerful model on another). Set each channel's agents.defaults.model.primary to the slug of the model the client chose for that channel.

Monitoring Usage

Visit https://openrouter.ai/activity
See requests, costs, and token usage
Filter by model, time range, or other criteria

Common Errors from Official Docs

"No API key found for provider 'openrouter'" - Set OPENROUTER_API_KEY env var or run openclaw onboard
Authentication errors (401/403) - Verify key at openrouter.ai/keys, check credits
Payment required (402) - Credits depleted. Add more at openrouter.ai/credits or use the client's configured fallback model
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

Config alone is NOT enough. You can set up your models with perfect temperature, reasoning, and cost settings, but if the agent doesn't KNOW when to use which model, it will use the same model for everything. That's like owning a toolbox full of tools but only ever reaching for the hammer.

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
params.reasoning.effort is a per-model API hint. If a model has effort: "high" in its config, the API request to that model always includes that hint.
The agent can dynamically change the session-level thinking with /reasoning <level> without touching the config.
Non-thinking models safely IGNORE both settings. OpenClaw checks the model's reasoning support before sending any thinking params.

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

Then per-model overrides where needed (example shape, using a model the client chose):

"openrouter/<author>/<client-chosen-model>": {
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

Step 2: Pick the right model. Match the task category to the model the client chose for it (see the Model Selection Matrix below).

Step 3: Pick the right thinking level. Match the effort to the complexity:
Low: Simple scans, routine checks, quick messages
Medium: General work, writing, tool operations
High: Complex analysis, multi-step planning, debugging
XHigh: Maximum depth analysis (rare, expensive)

Step 4: Switch if needed. Use /model <alias> and /reasoning <level> BEFORE starting the task. If already on the right model, proceed without switching.

The Model Selection Matrix

This is the heart of the routing system. It maps every common task type to the kind of model to use and the thinking level. In every row, the model is the client's choice for that category, or the client's configured default model.

| Task Category | Best Model | Thinking Level | Rationale |
|---|---|---|---|
| Heartbeat Phase 1 (scan emails, calendar, triage priorities) | Model: the client's configured default model | low | Cheap, supports tool calls, fast enough for scanning. Don't waste expensive models on reading emails. |
| Heartbeat Phase 2 (execute tasks from Phase 1) | Varies per task | Varies | Route each identified task to the client's chosen model for it. See Heartbeat Routing section below. |
| Tool-heavy operations (API calls, file management, cron jobs, config changes, message sends) | Model: the client's chosen tool-capable model | medium | MUST support tool calls. Recommendation: the lowest-cost tool-capable model for routine chains; the client's chosen high-capability model for complex multi-step tool chains where reasoning matters. |
| Deep strategy and analysis (business planning, complex decisions, coaching frameworks, architecture) | Model: the client's chosen high-capability model | medium to high | Best reasoning capability and most nuanced understanding. This is where a premium model earns its price. |
| Long-form writing (documents, guides, SOPs, client deliverables, proposals) | Model: the client's chosen writing model (a high-capability one for important or client-facing pieces) | medium | Writing quality and formatting precision matter. |
| Quick writing (short messages, Slack DMs, quick emails, status updates) | Model: the client's choice, or the client's configured default model | low | Don't waste premium tokens on a 2-sentence message. |
| Code generation (writing new code, scripts, automation, refactoring) | Model: the client's chosen code model | as the model requires / medium | Recommendation: a code model that can run many parallel sub-agents is ideal for large code work, because hundreds of instances can execute at once under a master agent. If the code also needs tool interaction, use the client's chosen tool-capable code model. |
| Code debugging (fixing errors, reading logs, troubleshooting, testing) | Model: the client's chosen high-capability code model with tool support | medium to high | Need both strong reasoning AND tool calls to read files, run tests, iterate on fixes. |
| Research and fact-finding (web search, current information, verification, citations) | Model: the client's chosen research model | medium | Recommendation: a model built for search with real-time web access and cited sources, because other models would need external search tools. |
| Quick factual answers (simple questions, lookups, math, definitions) | Model: the client's choice, or the client's configured default model (the configured fallback if the client set one for this) | low | Simple queries do not need a premium model. |
| Image and media generation (creating images, processing media, video generation) | Model: any of the client's chosen models with tool calls | low | The model just needs to correctly call the image generation skill. It's not doing the creative work itself. |
| Document formatting (Google Docs API, PDF creation, complex formatting) | Model: the client's chosen high-capability model with tool support | medium | Complex API call sequences, quality matters, needs reliable tool support and attention to detail. |
| Client-facing communications (emails to clients, professional messages, proposals) | Model: the client's chosen model for important writing | medium | Tone, nuance, and quality matter most when the user's name and reputation are on it. |
| Data processing (parsing CSVs, transforming data, batch operations, calculations) | Model: the client's choice, or the client's configured default model | low to medium | Cost-effective for mechanical, repetitive work. Don't need premium reasoning for data transformation. |
| Creative brainstorming (marketing ideas, campaign concepts, naming, positioning) | Model: the client's chosen writing or high-capability model | medium to high | Strategy-connected creativity goes to the high-capability model; pure ideation and divergent thinking go to the writing model. |
| Quality control (reviewing sub-agent output, verifying deliverables) | Model: the client's chosen high-capability model (never the model that produced the work) | medium to high | Best reasoning for catching errors and verifying quality. This is the QC layer. Never deliver sub-agent output without running it through QC first. |
| Planning and blueprinting (architecture, project planning, task decomposition, strategy) | Model: the client's chosen high-capability model | medium to high | Creates the plan that other models execute. Masterminding, strategic thinking, decision-making. |
| Swarm orchestration (managing 100s-1000s of sub-agents, assigning tasks, receiving results) | Model: the client's chosen high-capability model | medium | The conductor. Assigns tasks to the right models, monitors progress, assembles final output from swarm results. |

Model Capabilities Quick Reference

Build this table at setup for the models the client chose, from their live OpenRouter pages, and keep it in TOOLS.md:

| Model | Alias | Tool Calls | Thinking | Best For | Cost Tier | Notes |
|---|---|---|---|---|---|---|
| <client's chosen model slug> | <alias> | YES/NO per its OpenRouter page | <how it is configured> | <the work the client chose it for> | <from its live pricing> | <capability notes, e.g. context window, no tool calls> |

One row per model the client chose. A model's row must state plainly whether it supports tool calls, because that single fact decides whole classes of routing.

Thinking Level Guide

| Level | When to Use | Cost Impact | Examples |
|---|---|---|---|
| off | Never for thinking models (wastes their capability) | Cheapest | - |
| minimal | Not recommended. Either think or don't. | Very low | - |
| low | Simple scans, routine checks, quick messages, image generation calls | Low | Heartbeat Phase 1, sending a Slack DM, checking calendar |
| medium | DEFAULT for most work. Writing, tool operations, general tasks | Moderate | Document creation, email composition, standard tool operations |
| high | Complex analysis, multi-step planning, debugging; also the recorded default for some chosen models | Higher | Architecture decisions, debugging production issues, multi-step API chains |
| xhigh | Only when explicitly requested. Maximum depth analysis. | Expensive | Deep strategic analysis, critical business decisions |

Cost awareness: Reasoning tokens are billed as OUTPUT tokens. Higher thinking levels mean more output tokens, which means higher cost. This is why you don't set everything to "high" - you match the level to the task.

Heartbeat Routing (Automated Task Execution)

The heartbeat is where intelligent routing matters most, because it runs autonomously without user input. The agent needs to be smart about cost and model selection on its own.

Phase 1: Morning Scan
Switch to: the client's configured default model (/model <its alias> or equivalent)
Thinking: low (/reasoning low)
What to do: Check emails across all accounts, check calendar, scan for alerts, scan messaging platforms for unread important messages, produce a prioritized task list
Why the default model: It's the client's chosen low-cost workhorse, it supports the tool calls needed to check email/calendar/messages, and Phase 1 doesn't require deep reasoning. You're just reading and summarizing.
Output: A prioritized list of tasks that need attention

Phase 2: Task Execution
Each task identified in Phase 1 gets routed to the right model:

| Identified Task | Route To | Thinking | Why |
|---|---|---|---|
| "Send the user a summary of findings" | Stay on the configured default model | low | Just composing and sending a message |
| "Reply to client email about project timeline" | Switch to the client's chosen model for important writing | medium | Client-facing communication needs quality |
| "Check Stripe for failed payments" | Stay on the configured default model (tool calls) | low | Mechanical API check |
| "Research competitor pricing" | Switch to the client's chosen research model | medium | Needs web search with citations |
| "Generate a project report/document" | Switch to the client's chosen writing or high-capability model | medium | Writing quality matters |
| "Fix a broken cron job or config issue" | Switch to the client's chosen high-capability model with tool support | medium to high | Debugging needs strong reasoning plus tool calls |
| "Send a quick Slack DM or status update" | Stay on the configured default model | low | Don't waste tokens on 2 sentences |
| "Create images for a project" | Stay on the configured default model | low | Just calling the image generation skill |
| "Write or debug a script" | Switch to the client's chosen code model (a tool-capable one if the work needs tools) | as the model requires | Pure code generation needs no tool calls; fixing live code does |
| "Process data or batch operations" | Stay on the configured default model | low to medium | Mechanical work, cost matters |

Phase 3: Return to Baseline
After all tasks are executed:
If the user is actively chatting: Stay on whatever model the user prefers (usually the primary model)
If running autonomously: Switch back to the client's configured default model and wait

The Swarm Architecture Pattern (Boss + Workers + QC)

This is the most powerful multi-model pattern. It uses the client's chosen high-capability model as the brain and cheaper chosen models as the hands.

The Boss Layer (the client's chosen high-capability model)
Its job:
Receive the task from the user
Break it into sub-tasks (planning, blueprinting)
Decide which model handles which sub-task
Spawn sub-agents and assign work
Mastermind and make strategic decisions
Receive results back from all sub-agents
Does NOT do the grunt work itself. Too expensive for execution.

The Worker Layer (the client's other chosen models)
These models do the actual work:
The client's chosen code model is the code army. Where it supports parallel instances, it can spin up HUNDREDS or even 1,000+ sub-agents simultaneously for parallel code generation. It produces code/text output and sends it back to the boss.
The client's chosen tool-capable model handles tool-heavy execution. API calls, file operations, message sends, anything requiring tool interaction.
The client's chosen low-cost model handles cost-effective general execution. Good for mechanical, repetitive, or bulk processing work.
A tool-capable code model handles hybrid code + tool tasks, when code needs to also run tests or interact with files.

The QC Layer (the client's chosen high-capability model, or another chosen model with strong reasoning)
Before ANY sub-agent output reaches the user:
Run it through the QC layer for quality control
Check code quality, verify outputs, catch errors, ensure coherence
This is NON-NEGOTIABLE. Never deliver unreviewed sub-agent output.
The QC model must be different from the model that produced the work it reviews.

The Full Pattern:

User gives task to the boss model
Boss analyzes, plans, decomposes into sub-tasks
Boss assigns each sub-task to the client's chosen model for that kind of work
Worker agents execute in parallel (50 agents = 50x speed)
All results flow back to the boss
Boss (or the QC layer) reviews EVERY result (QC pass)
Boss assembles the final deliverable
Boss presents polished output to user

Why this pattern works financially:
The boss plans the work: small token cost
Worker agents do the generation: moderate total cost at worker prices
The boss reviews all outputs: moderate token cost
Total: MUCH cheaper than the boss model doing every task itself at premium prices

Implementation in OpenClaw:
Use sessions_spawn to create sub-agent sessions on the client's chosen models for each sub-task type
The main session (on the boss model) orchestrates and receives results
Use /model <alias> for the boss session, sub-agents automatically use their assigned model

When NOT to Switch Models

The routing system is powerful, but there are times you should NOT switch:

User is actively chatting. If the user is in a conversation with you, stay on whatever model you're on unless the task clearly requires a different one. Don't interrupt the conversation flow with model switches.

Mid-task. Never switch models halfway through a document, an API operation, or a multi-step process. Finish what you started on the current model.

Quick follow-ups. If the user says "now do X" right after "do Y" and both need the same model, don't switch.

Uncertainty. If you're genuinely not sure which model is best for a task, stay on the current model and make a note to evaluate later. A wrong switch is worse than no switch.

Low-stakes tasks. If the task is trivial and will take 10 seconds regardless of model, don't bother switching. The overhead of switching isn't worth it.

Cost Optimization Strategy

The whole point of intelligent routing is to get the best output at the lowest cost. Here are the rules:

Don't use the boss model for heartbeat checks or grunt work. The high-capability model is the BOSS, not the worker. It plans, blueprints, masterminds, manages sub-agents, and checks work quality. It does NOT write 1,000 lines of code or process batch data. That's what cheaper models are for.

Don't use the cheapest model for client deliverables. Quality matters when your user's name and reputation are on it. The small savings is not worth a poorly written email to a client.

Recommendation: for code generation at scale, recommend a code model that supports many parallel sub-agent instances, because parallel execution is where the cost and time savings are. It does not need tool calls for pure generation; a master agent orchestrates the swarm and handles tool operations.

Free tiers are rate-limited. Good for low-volume internal reasoning tasks, but don't build production workloads on them. If you need reliability, use the paid tiers of the models the client chose.

The daily workhorse is the client's configured default model. Default to it for tool-heavy tasks, because it is the model the client picked to run all day.

The boss model is the QC layer. Use the client's chosen high-capability model for: planning, blueprinting, masterminding, strategic thinking, managing sub-agents, and quality control on returned work. Never send sub-agent work straight to the user without QC.

The swarm pattern saves money. Instead of the boss model doing everything at premium prices, have it plan the work (small token cost), spawn worker agents on the client's cheaper chosen models to do the work, then review the results (small token cost). The total cost is a fraction of having the boss do it all.

Track and optimize. After each heartbeat or task cycle, evaluate: Did the model choices work? Was anything overkill? Could something have been cheaper without quality loss? Write observations to memory so future sessions can refine.

SECTION 9: HOW TO UPDATE YOUR WORKSPACE FILES

Why Workspace Files Matter

OpenClaw agents read their workspace files (TOOLS.md, AGENTS.md, HEARTBEAT.md, USER.md, MEMORY.md, SOUL.md) at the start of every session. These files ARE the agent's persistent brain. Without them, the agent wakes up with amnesia every time.

When you configure models, the config file handles the WHAT (which models exist, what params they use). But the workspace files handle the HOW (when to use which model, how to route tasks, what rules to follow). Both need to be correct and congruent for the system to work.

After configuring your models, you MUST update the workspace files to teach the agent how to use them intelligently. Here's exactly what goes in each file. In every example below, the models are the ones the client chose; fill in the client's actual choices where the brackets are.

TOOLS.md - The Technical Reference

TOOLS.md is the agent's technical cheat sheet. It contains HOW to use tools, APIs, credentials, and models. This is where the Intelligent Model Routing matrix lives.

What to add after model configuration:

Verified Model Specs Table - A table with every configured model showing: context window, max output, input cost per million, output cost per million, and any special notes. Use verified numbers from OpenRouter live pages, not outdated training data.

Intelligent Model Routing Section - The complete decision framework:
   The 4-step decision process (classify, pick model, pick thinking, switch)
   The Model Selection Matrix (task categories mapped to the client's chosen models and thinking levels)
   Model Capabilities Quick Reference (tool calls yes/no, thinking support, cost tier)
   Thinking Level Guide (when to use each level)
   Cost-consciousness rules
   When NOT to switch

Model-Specific Notes - Any gotchas or special behaviors of the client's chosen models, for example:
   "The client's chosen code model CANNOT do tool calls. Use for code generation only." (Record this for any chosen model without tool-call support.)
   "The client's configured default model is the daily workhorse." (Record its recorded thinking default with it.)
   "The client's chosen research model's tool calls are its built-in web search, not OpenClaw tool calls."
   "Google Gemini models use thinking.type/budget format instead of reasoning.effort." (If the client chose a Gemini model.)

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
Model: Which of the client's chosen models does this best, or the client's configured default model?
Thinking: What level does this need?
Switch: Use /model <alias> and /reasoning <level> if needed

Model Selection Matrix
| Task | Best Model | Thinking | Why |
|------|-----------|----------|-----|
| Heartbeat scan | The client's configured default model | low | Cheap, fast, tool calls |
| Client email | The client's chosen model for important writing | medium | Quality matters |
| Code generation | The client's chosen code model | as the model requires | Matched to code work |
| Research | The client's chosen research model | medium | Built for search |
[... full matrix ...]

AGENTS.md - The Behavioral Rules

AGENTS.md defines HOW the agent behaves. It's the rules, the boundaries, the expectations. This is where you put the routing RULE (not the full matrix - that's in TOOLS.md).

What to add after model configuration:

Intelligent Model Routing Rule - A concise rule that says "Before executing any task, evaluate which model fits best and switch if needed." Point to TOOLS.md for the full matrix.

Key Constraints - The non-negotiable model rules:
   Never route tool-heavy tasks to a model that cannot do tool calls.
   The client's configured default model is the default workhorse for daily operations.
   The client's chosen high-capability model is reserved for complex strategy, important writing, client-facing work.
   Never modify config without explicit user permission.

Heartbeat Routing Summary - Brief Phase 1/Phase 2 instructions:
   Phase 1 (scan): The client's configured default model, thinking low
   Phase 2 (execute): Route per matrix in TOOLS.md

Example entry for AGENTS.md:

Intelligent Model Routing - THINK BEFORE YOU ACT
Before executing ANY task, run this decision loop:
What am I doing? Classify the task.
Which model fits best? Check TOOLS.md Model Selection Matrix.
What thinking level? Match effort to complexity.
Switch if needed using /model <alias> and /reasoning <level>.

Key rules:
Never route tool tasks to a model that cannot do tool calls.
The client's configured default model is the daily workhorse.
The client's chosen high-capability model is the specialist (complex strategy, writing, client-facing).
Full details: See TOOLS.md "Intelligent Model Routing" section.

HEARTBEAT.md - The Automated Routine

HEARTBEAT.md defines what the agent does during heartbeat polls (automated check-ins). This is where model routing matters most because the agent is operating autonomously.

What to add after model configuration:

Phase 1: Scan and Triage - Instructions to use the client's configured default model with low thinking for the initial scan. List what to check (email, calendar, messages, alerts).

Phase 2: Task Execution Routing Table - A table mapping each type of identified task to the right model and thinking level. Be specific:
   "Send summary" -> Stay on the configured default model, low
   "Reply to client" -> Switch to the client's chosen model for important writing, medium
   "Debug config" -> Switch to the client's chosen high-capability model with tool support, medium-high
   "Research topic" -> Switch to the client's chosen research model, medium

Phase 3: Return to Baseline - Instructions to switch back to the configured default model after task execution.

Cost Awareness - Reminder to track model usage and optimize over time.

Example entry for HEARTBEAT.md:

Heartbeat Model Routing

Phase 1: Scan and Triage
Model: The client's configured default model | Thinking: low
Tasks: Check emails, calendar, alerts, messages. Produce task list.

Phase 2: Execute Tasks
| Task | Switch To | Thinking |
|------|-----------|----------|
| Send summary | Stay on the configured default model | low |
| Client email reply | /model <alias of the client's chosen writing model> | medium |
| Fix broken config | /model <alias of the client's chosen high-capability model> | medium-high |
| Research topic | /model <alias of the client's chosen research model> | medium |
| Generate images | Stay on the configured default model | low |
| Write/debug code | /model <alias of the client's chosen code model> | varies |

Phase 3: Return to Baseline
After tasks: switch back to the configured default model if autonomous, stay on primary if user active.

USER.md - The User Context

USER.md describes WHO the agent is helping. It typically contains the user's preferences, timezone, communication style, and personal context. For model routing, add:

Model Preferences - Which model the user prefers for different situations, recorded from the user's own choices:
   "Primary model: [the model the client chose for direct conversations]"
   "Heartbeat model: [the client's configured default model]"
   "Code model: [the model the client chose for code generation]"

Cost Sensitivity - How cost-conscious the user is:
   "Use the client's configured fallback or free models for internal/non-critical work when possible, where the client configured them"
   "Don't cheap out on client-facing communications"

Thinking Preferences - If the user has opinions on thinking depth:
   "Default medium for everything else"
   "Only use xhigh when I specifically ask for deep analysis"
   (Record per-model thinking preferences the user states, against the model they state them for.)

MEMORY.md - The Persistent Brain

MEMORY.md is the agent's long-term memory. It survives across sessions and compactions. For model routing, add a condensed version of the routing system:

Routing Quick Reference - A compact table mapping tasks to the client's chosen models. Not the full matrix, but the essential mappings the agent needs to recall quickly.

Config State - Current config settings so the agent knows what's actually configured:
   "thinkingDefault: medium"
   "Per-model overrides: [as recorded at setup]"
   "[N] models configured, 0 errors" (N = the number of models the client chose)

Lessons Learned - Any routing decisions that worked well or poorly, recorded against the capability involved, for example:
   "The configured default model handles heartbeat Phase 1 well at low cost"
   "The chosen high-capability model is worth the premium for client emails"
   "A chosen model without tool-call support can't take tool tasks - learned this the hard way"

SOUL.md - The Identity

SOUL.md defines who the agent IS. For model routing, you generally don't need to add anything here unless the agent's identity includes being "cost-conscious" or "efficient" as a core trait. If so, add a brief note:

"Be resourceful with model selection. Don't burn expensive tokens on trivial tasks."
"Quality over cost for client-facing work. Cost over quality for internal operations."

Congruency Check

After updating all workspace files, verify they are CONGRUENT. That means:

No contradictions. If TOOLS.md says "use the configured default model for heartbeat" but HEARTBEAT.md says "use the high-capability model for heartbeat," that's a conflict. Fix it.

No redundancy that could diverge. If the same information is in multiple files, make sure they reference each other rather than duplicating content that could get out of sync. Example: AGENTS.md should say "See TOOLS.md for full matrix" rather than copying the entire matrix.

Consistent model names. Use the same model names everywhere. Don't call a model by a short name in one file and by its full slug in another without the alias connection being clear.

Consistent thinking levels. If you set a model to HIGH in config, all files should reflect that. Don't have one file saying "medium" for the same model.

No stale information. After updating models or adding new ones, grep all workspace files for old model names or outdated specs. Remove or update them.

How to audit for congruency:

Find all model references across workspace files
grep -rn "model\|thinking\|reasoning" \
  TOOLS.md AGENTS.md HEARTBEAT.md USER.md MEMORY.md SOUL.md | sort

Review the output. Every mention of a model should be consistent with its capabilities, cost, and recommended use case. Every mention of thinking/reasoning levels should match the config.

SECTION 10: PUTTING IT ALL TOGETHER - FULL IMPLEMENTATION CHECKLIST

Use this checklist after configuring models to ensure everything is complete and congruent.

Config Layer
[ ] All models the client chose added to agents.defaults.models with correct openrouter/<author>/<slug> format
[ ] Temperature set per model (0.3 for most; a different value only where a chosen model's documentation requires it)
[ ] Reasoning effort set per model (medium for most, none for non-thinking models)
[ ] Google Gemini models use thinking.type/budget format instead of reasoning.effort
[ ] thinkingDefault set to medium in agents.defaults
[ ] Aliases configured for frequently used models
[ ] Primary model set to the client's choice or their configured default (not overridden without permission)
[ ] Fallback model(s) configured exactly as the client chose
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
[ ] Key model constraints listed (no tool tasks to models without tool-call support, configured default is workhorse, chosen high-capability model is specialist)
[ ] Heartbeat routing summary included (Phase 1/2 basics)
[ ] Config change permission rule present (never modify without user approval)

HEARTBEAT.md Layer
[ ] Phase 1 instructions (configured default model, low thinking, what to scan)
[ ] Phase 2 task routing table (specific tasks mapped to the client's chosen models)
[ ] Phase 3 return-to-baseline instructions
[ ] Cost awareness reminder

MEMORY.md Layer
[ ] Routing quick reference table added
[ ] Current config state documented (thinkingDefault, per-model overrides, total models)
[ ] Key constraints listed (no tool tasks to models without tool-call support, configured default is workhorse, etc.)

USER.md Layer
[ ] Model preferences documented (the client's own recorded choices)
[ ] Cost sensitivity noted
[ ] Thinking preferences noted

Congruency Audit
[ ] No contradictions across files
[ ] No redundant content that could diverge
[ ] Consistent model names everywhere
[ ] Consistent thinking levels everywhere
[ ] No stale information from old configurations
[ ] All files reference each other correctly (AGENTS.md points to TOOLS.md, etc.)
