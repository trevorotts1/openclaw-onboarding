# BlackCEO Team Management - Examples

Real examples showing the dispatcher/worker system in action, from initial setup to daily operations.

---

## Example 1: First Message from a Team Member

**Scenario:** LeAnne (Telegram ID: 6663821679) sends her first message to the bot.

**What LeAnne types in Telegram:**

```
Hey, can you draft a social media post for the upcoming conference?
```

**What happens behind the scenes:**

1. Dispatcher receives the message
2. Dispatcher checks: Sender ID is 6663821679
3. Dispatcher looks up routing table: 6663821679 = LeAnne, worker label = leanne-worker
4. Dispatcher checks: Does leanne-worker exist? No (first message ever)
5. Dispatcher spawns a new worker with label "leanne-worker" and the task
6. The worker drafts the social media post
7. Dispatcher sends the result ONLY to LeAnne's Telegram DM

**What LeAnne sees in her Telegram:**

```
Here is a draft social media post for the upcoming conference:

"Excited to announce our team will be at the 2026 Business Innovation Summit!
Come find us at Booth 12 - we have some big announcements to share.

Who else is going? Drop a comment below!

#BusinessInnovation #Conference2026"

Would you like me to adjust the tone, add hashtags, or create versions for different platforms?
```

**What Trevor and Spaulding see:** Nothing. The response went only to LeAnne.

---

## Example 2: Multiple People Messaging at the Same Time

**Scenario:** Trevor and Spaulding both send messages within seconds of each other.

**Trevor types:**

```
Check my Gmail for anything from Pam Perry
```

**Spaulding types (3 seconds later):**

```
Create a project timeline for the Q3 launch
```

**What happens:**

1. Trevor's message arrives - dispatcher routes to trevor-worker
2. Spaulding's message arrives - dispatcher routes to spaulding-worker
3. Both workers run IN PARALLEL - neither one waits for the other
4. Trevor gets his Gmail results in his DM
5. Spaulding gets his project timeline in his DM
6. Neither person sees the other's request or result

**This is the whole point of the system.** Without it, Spaulding would have to wait for Trevor's Gmail check to finish before his timeline request even started.

---

## Example 3: Cross-Worker Communication (Forwarding Between People)

**Scenario:** Trevor wants to share something from his conversation with Spaulding.

**Trevor types:**

```
Send Spaulding the update from my last conversation about the Q3 budget
```

**What happens:**

1. Dispatcher reads Trevor's request
2. Dispatcher looks up trevor-worker's conversation history via sessions_history
3. Dispatcher finds the Q3 budget discussion
4. Dispatcher sends a summary to Spaulding's DM, tagged as forwarded

**What Spaulding sees in his Telegram:**

```
Forwarded from trevor-worker:

Q3 Budget Update:
- Total budget approved: $45,000
- Marketing allocation: $18,000
- Operations allocation: $15,000
- Technology allocation: $12,000
- Timeline: Budget active starting April 1

Trevor asked me to share this with you.
```

---

## Example 4: Client Interaction (Respectful, Not Directive)

**Scenario:** A client named Marcus (NOT a team member) messages the bot.

**Marcus types:**

```
Can you show me the progress report for my project?
```

**What the worker does (CORRECT):**

```
Here is your project progress report, Marcus:

Phase 1 (Research): Complete
Phase 2 (Design): 85% complete - expected done by Friday
Phase 3 (Development): Starting next week

Would you like more detail on any phase, or would you like me to
send this as a formatted PDF?
```

**What the worker must NEVER do (WRONG):**

```
Marcus, please send me the latest sales numbers so I can update
the report. Also, you need to approve the design mockups before
we can proceed.
```

The client is NEVER assigned tasks. The AI serves them - it does not boss them around.

---

## Example 5: Adding a New Team Member

**Scenario:** A new team member named Dana needs to be added. Her Telegram ID is 7788990011.

**Step 1: Add her ID to the allowFrom list**

Open ~/.openclaw/openclaw.json and add her ID:

```json
{
  "channels": {
    "telegram": {
      "allowFrom": [
        "5252140759",
        "6663821679",
        "6771245262",
        "7788990011"
      ]
    }
  }
}
```

**Step 2: Add her to the routing table**

Open ~/clawd/WORKFLOW_AUTO.md and add a row:

```
| 7788990011 | Dana | Content Coordinator | dana-worker | 7788990011 |
```

**Step 3: Add her to AGENTS.md and MEMORY.md**

Add her Telegram ID and role to the team tables in both files.

**Step 4: Validate and restart**

```bash
python3 -m json.tool ~/.openclaw/openclaw.json > /dev/null
openclaw gateway restart
```

**Step 5: Test**

Ask Dana to send a message to the bot. She should get a response in her own DM, and no one else should see it.

---

## Example 6: Archiving a Worker

**Scenario:** A team member has left and you want to clean up their worker.

**What you type:**

```
Archive spaulding-worker
```

Or use the command:

```
/subagents kill spaulding-worker
```

**What happens:**

1. The worker's session is terminated
2. Its conversation history is gone
3. Files it created on disk are still there (they live in the shared workspace)
4. If Spaulding sends a message later, a fresh worker is automatically created

---

## Example 7: After a Gateway Restart

**Scenario:** The OpenClaw gateway was restarted (maybe after a config change or an update).

**What happens to workers:** All workers are lost. This is normal and expected.

**What you need to do:** Nothing. The next time each person sends a message, the dispatcher automatically creates a fresh worker for them. Their files and shared memory are still on disk - only the conversation history resets.

**Example:** Trevor sends a message after the restart:

```
What did I ask you about yesterday?
```

**Worker response:**

```
I am sorry - my conversation history was reset when the system
restarted. I do not have a record of our previous conversation.

However, I can check the shared memory files and workspace for
any notes or outputs from previous sessions. Would you like me
to look?
```

---

## Example 8: Checking Active Workers

**What you type:**

```
/subagents list
```

**What you see:**

```
Active workers:
1. trevor-worker - IDLE (last active: 5 minutes ago)
2. leanne-worker - ACTIVE (currently drafting social media content)
3. spaulding-worker - IDLE (last active: 2 hours ago)
```

---

## Example 9: Model Override for a Specific Task

**Scenario:** Trevor needs complex strategic analysis, so the dispatcher uses a more powerful model.

**Trevor types:**

```
Analyze our Q3 revenue data and create a competitive strategy
for the next quarter. Include market positioning, pricing
recommendations, and risk assessment.
```

**What the dispatcher does:**

1. Reads the task and classifies it as "complex strategy" (not routine)
2. Spawns or routes to trevor-worker with model override: Opus 4.6
3. The more capable model handles the complex analysis

For routine tasks like "check my email" or "upload this file," the dispatcher uses the cheaper default model (MiniMax M2.5 or Codex).

---

## Example 10: The WORKFLOW_AUTO.md File (Complete Example)

Here is what a completed WORKFLOW_AUTO.md looks like for a real deployment:

```markdown
# WORKFLOW_AUTO.md - BLACK CEO Management Protocol (Dispatcher Routing)

## Dispatcher Pattern (ACTIVE)
Main session = dispatcher/router. Route all incoming messages by sender ID.

## BLACK CEO Management Team (Always Present)
| Sender ID | Name | Role | Worker Label | Reply To |
|---|---|---|---|---|
| 5252140759 | Trevor Otts | Operations Lead / AI Director | trevor-worker | 5252140759 |
| 6663821679 | LeAnne | Head of Marketing | leanne-worker | 6663821679 |
| 6771245262 | E.R. Spaulding | Chief of Operations | spaulding-worker | 6771245262 |

## Client Team
| Sender ID | Name | Role | Worker Label | Reply To |
|---|---|---|---|---|
| 9988776655 | Marcus Johnson | Client (NOT a worker) | marcus-worker | 9988776655 |
| 7788990011 | Dana | Content Coordinator | dana-worker | 7788990011 |

## Reply Rules
- Results go ONLY to requesting DM
- No cross-posting unless explicitly requested
- Tag: [Dispatcher] / [worker-label]

## Worker Config
- Model: openai-codex/gpt-5.3-codex
- Fallbacks: openrouter/minimax/MiniMax-M2.5, openrouter/google/gemini-3-flash-preview
- cleanup: keep
- archiveAfterMinutes: 43200

## Client Rules
- Marcus Johnson is the CLIENT - never assign tasks, serve respectfully
- BLACK CEO team members are workers - they give instructions, AI executes
```
