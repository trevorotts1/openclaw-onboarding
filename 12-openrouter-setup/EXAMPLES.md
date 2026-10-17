# OpenRouter Setup - Examples

This document shows real examples of OpenRouter configuration and model routing in action. Each example includes what happens, what commands to run, and what to expect.

## Example 1: First-Time Setup (Complete Walkthrough)

**Scenario:** First-time OpenRouter setup on a new OpenClaw installation.

**The agent will execute the following when given an OpenRouter API key (format: sk-or-...):**

1. Creates a backup of your current config:
   cp ~/.openclaw/openclaw.json ~/openclaw-backup-configs/openclaw-backup-$(date +%Y-%m-%d-%H%M%S).json

2. Adds the API key to the env section of your config file.

3. Adds the models the client chose to agents.defaults.models.

4. Sets the model the client chose as the primary model, with the fallbacks the client chose.

5. Validates the config:
   openclaw doctor

6. Restarts the gateway:
   openclaw gateway restart

7. Reports what was done and confirms everything is working.

**What you should see after:** The agent responds to your next message using the primary model the client chose as the active model.

## Example 2: Switching Models During a Conversation

**Scenario:** You are chatting with the agent on your configured default model and need help planning a complex business strategy.

**What you type** (using the alias you set at setup for your chosen high-capability model; this example uses "planning"):

   /model planning

**What happens:** The agent switches to the model behind that alias and confirms: "Switched to your chosen high-capability model. This is the Thinking Tier model best suited for complex strategy and planning."

**Later, when you are done with the strategy and just want to send a quick message:**

   /model daily

**What happens:** The agent switches back to your configured default model (this example uses the alias "daily"): "Switched back to your default model, the daily workhorse."

## Example 3: Agent Recommends a Model Switch

**Scenario:** You are on your configured default model and ask the agent to refactor an entire codebase.

**What the agent says:**

"This task would benefit from your chosen high-capability model with high thinking enabled. A high-capability model excels at multi-file code refactoring that requires understanding the full architecture. The cost will be higher than your default model (check both models' live prices on their OpenRouter pages). Would you like me to switch to your high-capability model for this task?"

**If you say yes:** The agent switches to your chosen high-capability model, sets thinking to high, and begins the refactoring.

**If you say no:** The agent stays on your default model and does its best with the current model.

**If you do not respond within 60 seconds:** The agent proceeds with its recommendation and logs the decision.

## Example 4: Writing a Blog Post (Creative Tier)

**Scenario:** You ask the agent to write a 2,000-word blog post about real estate investing.

**What the agent does:** Switches to the model you chose for writing (the Creative Tier model) because this is a writing task. It does not need deep reasoning, it needs good writing.

**What the agent says:**

"Switching to your chosen writing model for this task. You picked it for content creation, so it is the most cost-effective option for writing."

**Result:** You get a well-written blog post at a fraction of the cost compared to using your high-capability model for the same task.

## Example 5: Researching Current Information

**Scenario:** You ask "What are the current API pricing changes for GoHighLevel?"

**What the agent does:** Switches to the research model you chose at setup, because this requires current, real-time information that cannot be answered from training data.

**What the agent says:**

"Let me research that using your chosen research model, which has built-in web search for current information."

**Result:** The agent returns verified, current pricing data with source citations, instead of guessing based on potentially outdated training data.

## Example 6: Running Out of Credits

**Scenario:** You are in the middle of a conversation and the API returns a 402 (Payment Required) error.

**What the agent does automatically:**

1. Switches to the fallback model you configured at setup (a free model if you picked one). If no fallback is configured, it tells you and asks which model to use instead of silently substituting one.
2. Tells you: "Your OpenRouter credits appear to be depleted. I have automatically switched to your configured fallback model so we can continue working. When you are ready, add credits at https://openrouter.ai/credits and let me know so I can switch back to your preferred model."
3. Continues working normally on the fallback model.

**When you add more credits and tell the agent:** It switches back to your configured primary model.

## Example 7: Heartbeat Morning Scan

**Scenario:** It is 7:00 AM and the automated heartbeat fires.

**Phase 1 (The Check):**
- Agent is on your configured default model with low thinking.
- It checks user@yourdomain.com for new emails.
- It checks the calendar for today's events.
- It scans for any alerts or failed payments.
- It produces a task list:
  1. Reply to client email about project timeline
  2. Send the daily briefing summary to the user
  3. Check on a failed Stripe payment

**Phase 2 (The Dispatch):**
- Task 1 (client email): Switches to your chosen model for important writing (client-facing, quality matters). Writes and sends the reply.
- Task 2 (briefing): Stays on the default model (just sending a summary message). Sends the briefing.
- Task 3 (Stripe check): Stays on the default model (tool call to check Stripe API). Checks the payment status.

**After all tasks:** Returns to the configured default model at low thinking and waits for the next heartbeat or user interaction.

## Example 8: Multi-Agent Orchestration (Building a Full Project)

**Scenario:** "Build the landing page, set up the API endpoints, write the email sequence, and connect it to the CRM."

**What the master agent (your chosen high-capability model) does:**

1. Plans the project and breaks it into four sub-tasks.

2. Assigns sub-tasks to the right models:
   - Landing page HTML/CSS code: Spawns a sub-agent on your chosen code model (code generation, no tool calls needed)
   - API endpoint scripts: Spawns another sub-agent on your chosen code model
   - Email sequence copy: Spawns a sub-agent on your chosen writing model (writing task)
   - CRM integration and webhook setup: Spawns a sub-agent on your chosen tool-capable model (needs tool calls)

3. All four sub-agents work in parallel.

4. Results flow back to the master agent.

5. The master agent reviews all four outputs for quality (QC pass).

6. The master agent assembles the final deliverable and presents it to you.

**Why this is cost-effective:** The high-capability model only does the planning and review (small token cost). The bulk of the work is done by cheaper models. Total cost is much less than having the high-capability model do everything.

## Example 9: Adding a Single New Model to Your Config

**Scenario:** A new model just launched on OpenRouter and you want to add it.

**What you tell the agent:**

"Add the new model openrouter/some-company/new-model-v1 to my config. Use temperature 0.3 and medium reasoning."

**What the agent does:**

1. Creates a backup:
   cp ~/.openclaw/openclaw.json ~/openclaw-backup-configs/openclaw-backup-$(date +%Y-%m-%d-%H%M%S).json

2. Opens the config file and adds:

   "openrouter/some-company/new-model-v1": {
     "params": {
       "temperature": 0.3,
       "reasoning": { "effort": "medium" }
     }
   }

3. Does NOT delete or change any existing model entries.

4. Validates: openclaw doctor

5. Restarts: openclaw gateway restart

6. Reports what was added and confirms it is working.

## Example 10: Changing a Model's Thinking Level

**Scenario:** You want your current model to use xhigh thinking for a particularly complex task.

**What you type:**

   /reasoning xhigh

**What happens:** The thinking level for the current session increases to xhigh (0.95 effort ratio). The agent warns you:

"Thinking level set to xhigh. This is the maximum reasoning depth available. Reasoning tokens are billed as output tokens, so this will cost more per request. For example, the reasoning budget at xhigh for a model with 196K max tokens is approximately 186K tokens for thinking plus 10K for the response."

**After the complex task is done, reset it:**

   /reasoning medium

**What happens:** Thinking drops back to medium (0.50 effort ratio), reducing cost for subsequent requests.

## Example 11: Checking Your Model Configuration

**Scenario:** You want to see what models are currently configured.

**What to check:**

1. Open the config file:
   cat ~/.openclaw/openclaw.json

2. Look at the agents.defaults.models section. Each model listed there is available.

3. Check the primary model:
   Look at agents.defaults.model.primary

4. Check the fallbacks:
   Look at agents.defaults.model.fallbacks

5. Check your credit balance:
   Go to https://openrouter.ai/activity in your browser.

## Example 12: Alias Conflict Resolution

**Scenario:** You already have a direct Anthropic API connection with the alias "opus" and now you are adding the OpenRouter version of Claude Opus.

**What the agent does:** Uses the prefix "or-" to avoid conflicts:
     }
   }

Now you can use:
- /model opus for the direct Anthropic version
- /model or-opus for the OpenRouter version

## Example 13: Correct vs. Incorrect Model Entries

**CORRECT model entry (will work):**

   "openrouter/<author>/<client-chosen-model>": {
     "params": {
       "temperature": 0.3,
       "reasoning": { "effort": "high" }
     }
   }

**INCORRECT model entry (will BREAK the config):**

   "openrouter/<author>/<client-chosen-model>": {
     "params": { "temperature": 0.3 },
     "contextWindow": 196608,
     "maxTokens": 196608,
     "cost": "$X/M input",
     "notes": "Some note"
   }

The second example has contextWindow, maxTokens, cost, and notes. These are all invalid keys. They will make the entire config fail validation and OpenClaw will refuse to start.

The ONLY valid keys for a model entry are: alias, params, and streaming. Nothing else.

## Example 14: Per-Channel Model Configuration

**Scenario:** You want different models for different messaging platforms. For example, a cheaper model on Telegram and a more powerful model on Discord.

   {
     "telegram": {
       "agents": {
         "defaults": {
           "model": {
             "primary": "           }
         }
       }
     },
     "discord": {
       "agents": {
         "defaults": {
           "model": {
             "primary": "           }
         }
       }
     }
   }

This gives you a fast, low-cost model you chose on one channel and a more powerful model you chose on the other.

## Example 15: Verifying Model Specs Before Configuring

**Scenario:** You want to add a model but want to check its current pricing first.

**What to do:**

1. Go to https://openrouter.ai/models in your browser.
2. Search for the model name.
3. Click on the model to see its full specs: context window, max output, input price per million tokens, output price per million tokens.
4. Use the LIVE page numbers, not numbers from this guide or any other document. Specs change.

For example, if this guide or your notes say a model costs $0.30 per million input tokens but the live page shows $0.25, use $0.25. Always trust the live page.

## Quick Reference: Model ID Format

CORRECT format (always use this):
   openrouter/<author>/<slug>, copied exactly from the model's OpenRouter page
   (for example: openrouter/<author>/<client-chosen-model>)

WRONG format (will break routing):
   <author>/<slug> without the openrouter/ prefix
   openrouter/auto                (forbidden - never use auto)

## Quick Reference: Temperature Settings

ALL models: temperature 0.3 by default.
A different value only where the chosen model's own OpenRouter page or documentation requires it, recorded at setup.

No model gets temperature 0. If in doubt, use 0.3.
