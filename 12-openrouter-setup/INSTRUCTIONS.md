
## 🔴 ORDER LOCK (SOVEREIGN)
- OpenRouter setup must run LAST in onboarding sequence.
- Before any OpenRouter config edits, back up the model config first.
- If backup fails, stop OpenRouter setup and report error.

# OpenRouter Setup - Usage Instructions

This document covers how to use the OpenRouter model roster day to day. It assumes you have already completed the installation steps in INSTALL.md. If you have not set up OpenRouter yet, go do that first.

## Understanding the Five Model Tiers

Your models are organized into five tiers. Each tier serves a different purpose. Using the wrong tier wastes money or gives you poor results.

### Tier 1: Thinking Tier (Complex Work)
For: Strategy, architecture, deep analysis, critical decisions, important writing.
Models: Claude Opus 4.6, Claude Sonnet 4.6, Gemini 3.1 Pro, GPT 5.2 Codex, Qwen 3.5 Plus, GLM-5, DeepSeek V3.2 Speciale.
These models support extended thinking/reasoning. They cost more but deliver significantly deeper analysis.

### Tier 2: Execution Tier (Daily Work)
For: Routine tasks, tool calls, sending messages, file operations, heartbeat checks.
Models: MiniMax M2.7 (PRIMARY), Gemini 3 Flash, Claude Haiku 4.5, GPT-5 Mini, GPT-5 Nano, DeepSeek V3.2, Kimi K2.5.
MiniMax M2.7 is the default daily workhorse. It supports tool calls, has opt-in reasoning (pass reasoning: true), and costs $0.30 per million input tokens. 204K context, 131K max output.

CRITICAL: Kimi K2.5 CANNOT do tool calls. It is for coding and chat only. If a task requires calling tools, executing functions, or making API calls, do NOT use Kimi. Use MiniMax instead.

### Tier 3: Creative Tier (Writing)
For: All creative writing, blog posts, social media, emails, book chapters, marketing copy.
Model: Mistral Small Creative.
This model is purpose-built for writing at only $0.10 per million input tokens.

### Tier 4: Emergency Fallback Tier
For: When you run out of OpenRouter credits.
Model: DeepSeek R1 0528 Free.
Completely free. Automatically activated when paid models become unavailable.

### Tier 5: Research Tier
For: Research, fact-checking, web search, validating information.
Model: Perplexity Sonar Pro Search.
Has built-in web search capabilities. Use this every time you need to verify facts or look up current information.

## How to Switch Models

To switch to a different model during a conversation, type:

   /model opus        (switches to Claude Opus 4.6)
   /model sonnet      (switches to Claude Sonnet 4.6)
   /model minimax     (switches to MiniMax M2.7)
   /model kimi        (switches to Kimi K2.5)
   /model creative    (switches to Mistral Small Creative)
   /model research    (switches to Perplexity Sonar Pro)
   /model codex       (switches to GPT 5.2 Codex)
   /model haiku       (switches to Claude Haiku 4.5)
   /model flash       (switches to Gemini 3 Flash)
   /model deepseek    (switches to DeepSeek V3.2)
   /model fallback    (switches to DeepSeek R1 Free)

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

Most models default to medium. Two exceptions:
- MiniMax M2.7 defaults to opt-in reasoning (pass reasoning: true, no effort levels)
- DeepSeek V3.2 defaults to MEDIUM

Models that do not use thinking at all:
- Mistral Small Creative (creative writing model, no thinking parameter)
- Kimi K2.5 (has built-in thinking that you cannot configure)
- Perplexity Sonar Pro Search (research model, no thinking parameter)

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
| Simple factual question | GPT-5 Nano | low |
| Social media post or blog | Mistral Small Creative | none |
| Professional email to a client | Claude Opus 4.6 | medium |
| Debug a Python script | GPT 5.2 Codex or Kimi K2.5 | medium |
| Plan a multi-step automation | Claude Opus 4.6 | medium to high |
| Analyze a long document | Gemini 3.1 Pro | medium |
| Quick summary | GPT-5 Mini or Claude Haiku | low |
| Send a message or make an API call | MiniMax M2.7 | low |
| Research or fact-check something | Perplexity Sonar Pro | medium |
| Quick web lookup (single question) | Perplexity Sonar | low |
| Analyze images, video, or audio | MiMo V2 Omni | always on |
| Complex code or orchestration | MiMo V2 Pro | always on |
| Write code for a script | Kimi K2.5 | built-in |
| Build a project plan | Claude Sonnet 4.6 | medium |
| Review a business proposal | Claude Sonnet 4.6 | medium |
| Refactor an entire codebase | Claude Opus 4.6 | high |
| Scrape data in bulk | Kimi K2.5 (parallel instances) | built-in |
| Heartbeat scan (check emails, calendar) | MiniMax M2.7 | low |

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

1. Use MiniMax M2.7 as your daily driver. At $0.30 per million input tokens with tool call support and opt-in reasoning (reasoning: true), it is the best value for daily work. 131K max output -- double the previous M2.5.

2. Use Mistral Small Creative for all writing tasks. At $0.10 per million input tokens, it is the cheapest option for creative work.

3. Reserve Opus for complex strategy and critical work. At $5.00 per million input tokens, it is 16x more expensive than MiniMax. Only use it when quality truly matters.

4. Use GPT-5 Nano for simple questions. At $0.05 per million input tokens, it is the cheapest paid model.

5. Use the free DeepSeek R1 for non-critical internal reasoning when cost is a concern.

6. Do not leave thinking on "high" for everything. Medium is the default for good reason. Only escalate when the task demands it.

## The Heartbeat Protocol (Automated Task Execution)

The heartbeat is when the agent automatically checks for tasks that need doing (emails, calendar events, alerts). It has two phases:

### Phase 1: The Check
- Model: MiniMax M2.7
- Thinking: low
- What it does: Checks emails, calendar, messages, alerts. Produces a list of tasks.
- Cost: Very cheap. This is just reading and summarizing.

### Phase 2: The Dispatch
Each task identified in Phase 1 gets routed to the right model:
- Send a summary to the user -> Stay on MiniMax, low thinking
- Reply to a client email -> Switch to Opus, medium thinking
- Fix a broken config -> Switch to Opus or Codex, medium-high thinking
- Research a topic -> Switch to Perplexity, medium thinking
- Write or debug code -> Switch to Kimi (no tools) or Codex (needs tools)
- Create images -> Stay on MiniMax, low thinking
- Process data or batch operations -> Stay on MiniMax or DeepSeek, low thinking

## Zero-Credit Fallback Protocol

If your OpenRouter credits run out (the API returns a 402 error or any billing error), the agent will:

1. Immediately switch to openrouter/deepseek/deepseek-r1-0528:free
2. Notify you that it switched to the free model and explain why.
3. Continue working normally on the free model.
4. When you confirm you have added more credits, it switches back to your primary model.

The agent should NEVER stop working just because paid models are unavailable. The free fallback keeps things running.

## Multi-Agent Orchestration

When the agent manages multiple sub-agents (workers) for a big task, each sub-agent uses the right model for its piece of the work:

- Sub-task requires tool calls -> MiniMax M2.7 (pass reasoning: true)
- Sub-task is code generation -> Kimi K2.5
- Sub-task is multimodal (images/video/audio) -> MiMo V2 Omni (pass reasoning: true)
- Sub-task is complex code/orchestration -> MiMo V2 Pro (pass reasoning: true, TEXT ONLY)
- Sub-task is creative writing -> Mistral Small Creative
- Sub-task is deep research -> Perplexity Sonar Pro Search
- Sub-task is quick lookup -> Perplexity Sonar
- General task that does not fit above -> MiniMax M2.7

The master agent (usually Opus) plans the work, assigns sub-tasks, and reviews the results. The sub-agents do the actual work. This pattern keeps costs down because the expensive model only plans and reviews, while cheaper models do the heavy lifting.

## Context Window Management

Each model has a maximum amount of text it can process in one session (called the context window). When you approach the limit, the agent needs to create a handoff document so it does not lose track of what it was doing.

Key thresholds:
- At 80% capacity: The agent warns you that context is getting full.
- At 90% capacity: The agent creates a handoff.md file with everything it needs to continue.
- At 95% capacity: The agent updates handoff.md with any new information.
- After compaction: The agent reads handoff.md first before doing anything else.

Large context models (1 million tokens): Claude Opus 4.6, Claude Sonnet 4.6, Gemini 3.1 Pro, Qwen 3.5 Plus. These rarely need handoff during a normal session.

Small context models (under 200K tokens): Mistral Small Creative (32K), DeepSeek V3.2 (163K), MiniMax M2.7 (196K). These need more careful context management for long sessions.

## Updating Your Workspace Files

After configuring OpenRouter, make sure your workspace files are consistent:

- AGENTS.md should have the model routing rule (brief version, pointing to the full reference)
- TOOLS.md should have the model specs and routing matrix
- HEARTBEAT.md should have the two-phase heartbeat instructions
- MEMORY.md should have context window capacities and routing quick reference

All files should use the same model names, thinking levels, and recommendations. If TOOLS.md says "use MiniMax for heartbeat" but HEARTBEAT.md says "use Opus for heartbeat," that is a conflict. Fix it.

## Common Config Mistakes to Avoid

1. Adding custom keys to model entries. Only alias, params, and streaming are valid. Adding contextWindow or maxTokens will break the config.

2. Forgetting the openrouter/ prefix. The format is openrouter/author/model-name. Without the prefix, models will not route correctly.

3. Using openrouter/auto. Never do this. It picks models unpredictably.

4. Not backing up before editing. One typo can break the gateway. Always back up first.

5. Assigning tool-call tasks to Kimi K2.5. Kimi cannot do tool calls. Use MiniMax instead.

6. Using Opus for simple questions. Match the model to the task. Simple questions go to Nano.

7. Setting everything to high thinking. Medium is the default for good reason. Only escalate when needed.

8. Not restarting after config changes. Changes do not take effect until you run: openclaw gateway restart

## For the Full Reference

The complete unabridged OpenRouter configuration guide with all model specifications, the full scenario-based routing guide, the complete multi-agent orchestration patterns, and detailed workspace file update instructions is in the openrouter-setup-full.md file.
