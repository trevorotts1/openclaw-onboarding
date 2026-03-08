
## 🔴 ORDER LOCK (SOVEREIGN)
- OpenRouter setup must run LAST in onboarding sequence.
- Before any OpenRouter config edits, back up the model config first.
- If backup fails, stop OpenRouter setup and report error.

# OpenRouter Setup - SKILL.md

## What This Skill Is About

OpenRouter is a service that gives your AI agent access to many different AI models
(like Claude, GPT, Gemini, DeepSeek, and others) through one single API key. Instead
of signing up with each AI company separately, OpenRouter acts as a middleman - you
pay OpenRouter, and it connects you to whichever model you need.

This skill teaches your AI agent how to properly set up OpenRouter inside OpenClaw,
how to pick the right model for each job, and how to avoid wasting money by using
expensive models for simple tasks.

## When to Use This Skill

- First-time setup of OpenRouter on a new OpenClaw installation
- Adding new AI models to your existing setup
- Configuring model aliases (short names like "opus" instead of the full model ID)
- Setting up thinking/reasoning levels for each model
- Teaching the agent which model to pick for which type of task
- Troubleshooting model configuration errors or 401/402 API errors
- Setting up the free fallback model in case credits run out

## What This Skill Covers

1. **Getting your API key** - How to sign up at OpenRouter and create a key
2. **Backup protocol** - Always back up your config before making changes (mandatory)
3. **Model ID format** - The exact format OpenClaw requires (openrouter/author/slug)
4. **The 5 model tiers** - Thinking, Execution, Creative, Emergency Fallback, and Research
5. **17 pre-configured models** - Full specs, pricing, context windows, and max output for each
6. **27 strict rules** - Config safety rules the agent must follow (no guessing, no skipping backups, no unauthorized changes)
7. **Temperature and reasoning settings** - What each model should be set to
8. **Intelligent Model Routing** - A decision framework that teaches the agent to pick the right model for each task automatically
9. **Heartbeat routing** - How to use cheap models for routine checks and expensive models only when needed
10. **Multi-agent orchestration** - The "boss + workers + QC" pattern for running many models at once
11. **Context window management** - How to track usage and create handoff files before the agent loses context
12. **Workspace file updates** - What to add to AGENTS.md, TOOLS.md, MEMORY.md, and other files after setup
13. **Common mistakes** - 25+ specific errors to avoid (with explanations of why each one breaks things)

## Files in This Folder and Reading Order

1. **SKILL.md** - You are here. Start here for the overview.
2. **openrouter-setup-full.md** - The complete guide. Read this to execute the setup. It contains every rule, every model spec, every config example, and every routing instruction.
3. **INSTRUCTIONS.md** - Step-by-step execution instructions.
4. **INSTALL.md** - Installation-specific notes.
5. **EXAMPLES.md** - Example configurations and usage patterns.
6. **CORE_UPDATES.md** - What to add to your core workspace files (AGENTS.md, TOOLS.md, etc.)
7. **openrouter-setup.skill** - Skill metadata file.

## Prerequisites

- The Teach Yourself Protocol (TYP) must be installed first. If TYP is not in your
  AGENTS.md or TOOLS.md, stop and install TYP before proceeding.
- The Backup Protocol must be understood and ready to use.
- You need an OpenRouter account and API key (the guide walks you through getting one).
- OpenClaw must already be installed and running.

## Key Things the AI Agent Needs to Know

- **Config format is strict.** Each model entry in the config ONLY allows three keys:
  alias, params, and streaming. Adding anything else (like contextWindow or maxTokens)
  breaks the entire config and OpenClaw will not start.

- **Model ID format matters.** Always use openrouter/author/slug. Leaving off the
  openrouter/ prefix will route to the wrong provider or fail entirely.

- **Never use openrouter/auto.** It picks models unpredictably and breaks configs.

- **MiniMax M2.5 is the recommended primary model.** It supports tool calls, has high
  reasoning enabled by default, and costs $0.30 per million input tokens.

- **Kimi K2.5 cannot do tool calls.** It is for code generation and chat only. Sending
  it a task that requires calling tools will fail silently.

- **Always back up before editing.** Every single time, no exceptions. One typo in the
  config can break the entire gateway.

- **Match the model to the task.** Do not use a $25/million-token model to answer a
  simple question. Do not use a free model for important client work. The full guide
  has a complete routing matrix for every common task type.

- **Thinking tokens cost extra.** They are billed as output tokens. The agent must warn
  the user before enabling thinking mode on any model.
