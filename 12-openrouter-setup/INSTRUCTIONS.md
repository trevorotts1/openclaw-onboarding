
## 🔴 ORDER LOCK (SOVEREIGN)
- OpenRouter setup must run LAST in onboarding sequence.
- Before any OpenRouter config edits, back up the model config first.
- If backup fails, stop OpenRouter setup and report error.

# OpenRouter Setup - Usage Instructions

This document covers how to use the OpenRouter model roster day to day. It assumes you have already completed the installation steps in INSTALL.md. If you have not set up OpenRouter yet, go do that first.

## Understanding the Five Model Tiers

Your models are organized into five tiers. Each tier is a kind of work, not a fixed model. At setup (INSTALL.md STEP 6) you chose which of your models fills each tier; if you did not choose one for a tier, your configured default model fills it. Using the wrong tier wastes money or gives you poor results.

### Tier 1: Thinking Tier (Complex Work)
For: Strategy, architecture, deep analysis, critical decisions, important writing.
Model: the client's choice for complex work, or the client's configured default model.
Recommendation: a model with strong extended thinking/reasoning support, because deep analysis is what this tier is for. These models cost more but deliver significantly deeper analysis.

### Tier 2: Execution Tier (Daily Work)
For: Routine tasks, tool calls, sending messages, file operations, heartbeat checks.
Model: the client's choice for daily work, or the client's configured default model.
Recommendation: a model with reliable tool calling at a low per-token cost, because daily work is mostly tool execution and runs all day.

CRITICAL: Some models cannot do tool calls. A model that does not support tool calls is for coding and chat only. If a task requires calling tools, executing functions, or making API calls, do NOT route it to a model without tool-call support; use the client's chosen tool-capable model instead. Check each model's capabilities on its OpenRouter page.

### Tier 3: Creative Tier (Writing)
For: All creative writing, blog posts, social media, emails, book chapters, marketing copy.
Model: the client's choice for writing, or the client's configured default model.
Recommendation: a model chosen for writing quality at a sustainable cost, because creative work is high-volume.

### Tier 4: Emergency Fallback Tier
For: When you run out of OpenRouter credits.
Model: the fallback the client configured at setup (a free model if the client picked one).
Automatically activated when paid models become unavailable. If no fallback is configured, the agent tells you and asks which model to use; it never silently substitutes a model you did not choose.

### Tier 5: Research Tier
For: Research, fact-checking, web search, validating information.
Model: the client's chosen research model, or the client's configured default model.
Recommendation: a model with built-in web search capabilities, because current facts cannot come from training data. Use this tier every time you need to verify facts or look up current information.

## How to Switch Models

To switch to a different model during a conversation, type:

   /model <alias>     (switches to the model that alias was set to at setup)

Your aliases are whatever was configured at setup for the models you chose. For example, if you set the alias "daily" for your chosen daily-work model, /model daily switches to it. You can list your configured aliases any time by checking agents.defaults.models in ~/.openclaw/openclaw.json.

The agent can also switch models automatically based on the task, but it must notify you first and explain why.

## How Thinking Levels Work

Thinking (also called reasoning) is a feature that lets models "think harder" about complex problems. It costs more because thinking tokens are billed as output tokens, but it produces better results for complex work.

### Available Thinking Levels

| Level | Effort Ratio | When to Use |
|-------|-------------|-------------|
| minimal | 0.10 | Almost never - too shallow to be useful |
| low | 0.20 | Simple scans, routine checks, quick messages |
| medium | 0.50 | DEFAULT for most work - good balance |
| high | 0.80 | Complex analysis, multi-step planning, debugging |
| xhigh | 0.95 | Maximum depth - only for critical work |

### Default Thinking Levels Per Model

Most models default to medium. Beyond that, thinking behavior is a property of each model you chose: some use opt-in reasoning instead of effort levels (pass reasoning: true), some have built-in thinking you cannot configure, and some research models have no thinking parameter at all. What applies to each of your models was recorded at setup from its OpenRouter page. When in doubt, check the model's page and your config.

### How to Change Thinking Level

During a session, type:

   /reasoning low       (for simple tasks)
   /reasoning medium    (for standard work)
   /reasoning high      (for complex analysis)

### Cost Impact of Thinking

Thinking tokens are billed as output tokens. Higher thinking levels mean more output tokens, which means higher cost. This is why you do not set everything to "high." You match the level to the task.

The reasoning budget formula:
   budget_tokens = max(min(max_tokens * effort_ratio, 128000), 1024)

For example, if max_tokens is 16,000 and effort is medium (0.50), the reasoning budget is 8,000 tokens.

## Intelligent Model Routing (The Decision Framework)

Before every task, the agent should ask itself four questions:

1. What am I doing? (Classify the task)
2. Which model fits best? (Check the routing guide below)
3. What thinking level? (Match effort to complexity)
4. Do I need to switch? (If already on the right model, stay)

### Which Model for Which Task

| Task | Best Model | Thinking Level |
|------|-----------|----------------|
| Simple factual question | Model: the client's choice, or the client's configured default model | low |
| Social media post or blog | Model: the client's choice for writing, or the client's configured default model | none |
| Professional email to a client | Model: the client's choice for important writing, or the client's configured default model | medium |
| Debug a Python script | Model: the client's chosen code model (a tool-capable one if the fix has to run tools) | medium |
| Plan a multi-step automation | Model: the client's chosen high-capability model, or the client's configured default model | medium to high |
| Analyze a long document | Model: the client's chosen large-context model | medium |
| Quick summary | Model: the client's choice, or the client's configured default model | low |
| Send a message or make an API call | Model: the client's chosen tool-capable model | low |
| Research or fact-check something | Model: the client's chosen research model (built-in web search) | medium |
| Quick web lookup (single question) | Model: the client's chosen research model | low |
| Analyze images, video, or audio | Model: the client's chosen multimodal model | as the model requires |
| Complex code or orchestration | Model: the client's chosen code model with tool support | medium |
| Write code for a script | Model: the client's chosen code model | as the model requires |
| Build a project plan | Model: the client's chosen high-capability model, or the client's configured default model | medium |
| Review a business proposal | Model: the client's chosen high-capability model, or the client's configured default model | medium |
| Refactor an entire codebase | Model: the client's chosen high-capability model | high |
| Scrape data in bulk | Model: the client's chosen model for parallel sub-agent work | as the model requires |
| Heartbeat scan (check emails, calendar) | Model: the client's configured default model | low |

Recommendation: match capability to task (tool calling for tool work, a large context window for long documents, built-in web search for research, strong reasoning for planning and review), because capability fit gives better results at lower cost. These are recommendations only; your selection always wins.

## Model Switching Permission Protocol

When the agent decides a different model would be better for the current task, it must:

1. Tell you which model it recommends and why.
2. Tell you the cost difference.
3. Wait up to 60 seconds for your response.
4. If you approve, it switches.
5. If you decline, it stays on the current model and does its best.
6. If you do not respond within 60 seconds, it proceeds with its recommendation.
7. It always tells you what model is now active after any switch.

## Cost Management

### How to Check Your Spending

Go to https://openrouter.ai/activity to see your requests, costs, and token usage. You can filter by model, time range, and other criteria.

### Cost-Saving Tips

1. Use your configured default model as your daily driver. Recommendation: pick a daily driver with tool call support at a low per-token cost, because it runs all day and small price differences compound.

2. Use the model you chose for writing for all writing tasks. Writing is high-volume, so a sustainable per-token cost matters more than a small quality edge.

3. Reserve your chosen high-capability model for complex strategy and critical work. High-capability models cost many times more per token than daily models. Only use them when quality truly matters.

4. Use your configured default model for simple questions. Simple questions do not need a premium model.

5. If you configured a free fallback model at setup, it can be used for non-critical internal reasoning when cost is a concern.

6. Do not leave thinking on "high" for everything. Medium is the default for good reason. Only escalate when the task demands it.

## The Heartbeat Protocol (Automated Task Execution)

The heartbeat is when the agent automatically checks for tasks that need doing (emails, calendar events, alerts). It has two phases:

### Phase 1: The Check
- Model: the client's configured default model
- Thinking: low
- What it does: Checks emails, calendar, messages, alerts. Produces a list of tasks.
- Cost: Very cheap. This is just reading and summarizing.

### Phase 2: The Dispatch
Each task identified in Phase 1 gets routed to the right model:
- Send a summary to the user -> Stay on the configured default model, low thinking
- Reply to a client email -> Switch to the client's chosen model for important writing, medium thinking
- Fix a broken config -> Switch to the client's chosen high-capability model with tool support, medium-high thinking
- Research a topic -> Switch to the client's chosen research model, medium thinking
- Write or debug code -> Switch to the client's chosen code model (a tool-capable one if the work needs tools)
- Create images -> Stay on the configured default model, low thinking
- Process data or batch operations -> Stay on the configured default model, low thinking

## Zero-Credit Fallback Protocol

If your OpenRouter credits run out (the API returns a 402 error or any billing error), the agent will:

1. Immediately switch to the fallback model you configured at setup (a free model if you picked one).
2. Notify you that it switched to the fallback and explain why.
3. Continue working normally on the fallback model.
4. When you confirm you have added more credits, it switches back to your primary model.

If no fallback is configured, the agent notifies you and asks which model to use. It never silently substitutes a model you did not choose. The agent should NEVER stop working just because paid models are unavailable when a fallback is configured: the fallback keeps things running.

## Multi-Agent Orchestration

When the agent manages multiple sub-agents (workers) for a big task, each sub-agent uses the right model for its piece of the work:

- Sub-task requires tool calls -> the client's chosen tool-capable model
- Sub-task is code generation -> the client's chosen code model
- Sub-task is multimodal (images/video/audio) -> the client's chosen multimodal model
- Sub-task is complex code/orchestration -> the client's chosen code model with tool support
- Sub-task is creative writing -> the client's chosen writing model
- Sub-task is deep research -> the client's chosen research model
- Sub-task is quick lookup -> the client's chosen research model
- General task that does not fit above -> the client's configured default model

The master agent (the client's chosen high-capability model) plans the work, assigns sub-tasks, and reviews the results. The sub-agents do the actual work. This pattern keeps costs down because the expensive model only plans and reviews, while cheaper models do the heavy lifting.

## Context Window Management

Each model has a maximum amount of text it can process in one session (called the context window). When you approach the limit, the agent needs to create a handoff document so it does not lose track of what it was doing.

Key thresholds:
- At 80% capacity: The agent warns you that context is getting full.
- At 90% capacity: The agent creates a handoff.md file with everything it needs to continue.
- At 95% capacity: The agent updates handoff.md with any new information.
- After compaction: The agent reads handoff.md first before doing anything else.

Large context models (around 1 million tokens) rarely need handoff during a normal session. Small context models (under 200K tokens) need more careful context management for long sessions. Look up each of your chosen models' context windows on its OpenRouter page at setup and record them in TOOLS.md, so the agent always works from live numbers.

## Updating Your Workspace Files

After configuring OpenRouter, make sure your workspace files are consistent:

- AGENTS.md should have the model routing rule (brief version, pointing to the full reference)
- TOOLS.md should have the model specs and routing matrix
- HEARTBEAT.md should have the two-phase heartbeat instructions
- MEMORY.md should have context window capacities and routing quick reference

All files should use the same model names, thinking levels, and recommendations. If TOOLS.md says "use the configured default model for heartbeat" but HEARTBEAT.md says "use the high-capability model for heartbeat," that is a conflict. Fix it.

## Common Config Mistakes to Avoid

1. Adding custom keys to model entries. Only alias, params, and streaming are valid. Adding contextWindow or maxTokens will break the config.

2. Forgetting the openrouter/ prefix. The format is openrouter/author/model-name. Without the prefix, models will not route correctly.

3. Using openrouter/auto. Never do this. It picks models unpredictably.

4. Not backing up before editing. One typo can break the gateway. Always back up first.

5. Assigning tool-call tasks to a model that cannot do tool calls. Check the model's capabilities on its OpenRouter page first, and use the client's chosen tool-capable model.

6. Using your most expensive model for simple questions. Match the model to the task. Simple questions go to your configured default model.

7. Setting everything to high thinking. Medium is the default for good reason. Only escalate when needed.

8. Not restarting after config changes. Changes do not take effect until you run: openclaw gateway restart

## For the Full Reference

The complete unabridged OpenRouter configuration guide with all model specifications, the full scenario-based routing guide, the complete multi-agent orchestration patterns, and detailed workspace file update instructions is in the openrouter-setup-full.md file.
