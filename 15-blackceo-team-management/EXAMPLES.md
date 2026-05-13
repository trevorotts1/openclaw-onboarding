# BlackCEO Team Management - Examples

Real examples showing the dispatcher/worker system in action, from initial setup to daily operations.

All names and IDs in these examples are generic placeholders. Replace with your actual team data from TEAM_CONFIG.md.

---

## Example 1: First Message from a Team Member

**Scenario:** Alice Johnson (Telegram ID: 1234567890) sends her first message to the bot.

**What Alice types in Telegram:**

```
Hey, can you draft a social media post for the upcoming conference?
```

**What happens behind the scenes:**

1. Dispatcher receives the message
2. Dispatcher checks: Sender ID is 1234567890
3. Dispatcher looks up routing table: 1234567890 = Alice Johnson, worker label = alice-worker
4. Dispatcher checks: Does alice-worker exist? No (first message ever)
5. Dispatcher spawns a new worker with label "alice-worker" and the task
6. The worker drafts the social media post
7. Dispatcher sends the result ONLY to Alice's Telegram DM

**What Alice sees in her Telegram:**

```
Here is a draft social media post for the upcoming conference:

"Excited to announce our team will be at the 2026 Business Innovation Summit!
Come find us at Booth 12 - we have some big announcements to share.

Who else is going? Drop a comment below!

#BusinessInnovation #Conference2026"

Would you like me to adjust the tone, add hashtags, or create versions for different platforms?
```

**What other team members see:** Nothing. The response went only to Alice.

---

## Example 2: Multiple People Messaging at the Same Time

**Scenario:** Alice Johnson and Bob Smith both send messages within seconds of each other.

**Alice types:**

```
Check my Gmail for anything from our vendor contact
```

**Bob types (3 seconds later):**

```
Create a project timeline for the Q3 launch
```

**What happens:**

1. Alice's message arrives - dispatcher routes to alice-worker
2. Bob's message arrives - dispatcher routes to bob-worker
3. Both workers run IN PARALLEL - neither one waits for the other
4. Alice gets her Gmail results in her DM
5. Bob gets his project timeline in his DM
6. Neither person sees the other's request or result

**This is the whole point of the system.** Without it, Bob would have to wait for Alice's Gmail check to finish before his timeline request even started.

---

## Example 3: Cross-Worker Communication (Forwarding Between People)

**Scenario:** Alice wants to share something from her conversation with Bob.

**Alice types:**

```
Send Bob the update from my last conversation about the Q3 budget
```

**What happens:**

1. Dispatcher reads Alice's request
2. Dispatcher looks up alice-worker's conversation history via sessions_history
3. Dispatcher finds the Q3 budget discussion
4. Dispatcher sends a summary to Bob's DM, tagged as forwarded

**What Bob sees in his Telegram:**

```
Forwarded from alice-worker:

Q3 Budget Update:
- Total budget approved: $45,000
- Marketing allocation: $18,000
- Operations allocation: $15,000
- Technology allocation: $12,000
- Timeline: Budget active starting April 1

Alice asked me to share this with you.
```

---

## Example 4: Client Interaction (Respectful, Not Directive)

**Scenario:** A client named Carol Davis (NOT a team member) messages the bot.

**Carol types:**

```
Can you show me the progress report for my project?
```

**What the worker does (CORRECT):**

```
Here is your project progress report, Carol:

Phase 1 (Research): Complete
Phase 2 (Design): 85% complete - expected done by Friday
Phase 3 (Development): Starting next week

Would you like more detail on any phase, or would you like me to
send this as a formatted PDF?
```

**What the worker must NEVER do (WRONG):**

```
Carol, please send me the latest sales numbers so I can update
the report. Also, you need to approve the design mockups before
we can proceed.
```

The client is NEVER assigned tasks. The AI serves them - it does not boss them around.

---

## Example 5: Adding a New Team Member

**Scenario:** A new team member named Dana Lee needs to be added. Her Telegram ID is 5566778899.

**Step 1: Add her ID to the allowFrom list**

Open ~/.openclaw/openclaw.json and add her ID:

```json
{
  "channels": {
    "telegram": {
      "allowFrom": [
        "1234567890",
        "9876543210",
        "1122334455",
        "5566778899"
      ]
    }
  }
}
```

**Step 2: Add her to TEAM_CONFIG.md**

Open ~/.openclaw/skills/15-blackceo-team-management/TEAM_CONFIG.md and add a row:

```
| Dana Lee | 5566778899 | Content Coordinator | Worker | dana-worker |
```

**Step 3: Add her to the routing table**

Open ~/clawd/WORKFLOW_AUTO.md and add a row:

```
| 5566778899 | Dana Lee | Content Coordinator | dana-worker | 5566778899 |
```

**Step 4: Add her to AGENTS.md and MEMORY.md**

Add her Telegram ID and role to the team tables in both files.

**Step 5: Validate and restart**

```bash
python3 -m json.tool ~/.openclaw/openclaw.json > /dev/null
openclaw gateway restart
```

**Step 6: Test**

Ask Dana to send a message to the bot. She should get a response in her own DM, and no one else should see it.

---

## Example 6: Archiving a Worker

**Scenario:** A team member has left and you want to clean up their worker.

**What you type:**

```
Archive bob-worker
```

Or use the command:

```
/subagents kill bob-worker
```

**What happens:**

1. The worker's session is terminated
2. Its conversation history is gone
3. Files it created on disk are still there (they live in the shared workspace)
4. If Bob sends a message later, a fresh worker is automatically created

---

## Example 7: After a Gateway Restart

**Scenario:** The OpenClaw gateway was restarted (maybe after a config change or an update).

**What happens to workers:** All workers are lost. This is normal and expected.

**What you need to do:** Nothing. The next time each person sends a message, the dispatcher automatically creates a fresh worker for them. Their files and shared memory are still on disk - only the conversation history resets.

**Example:** Alice sends a message after the restart:

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
1. alice-worker - IDLE (last active: 5 minutes ago)
2. bob-worker - ACTIVE (currently drafting social media content)
3. carol-worker - IDLE (last active: 2 hours ago)
```

---

## Example 9: Model Override for a Specific Task

**Scenario:** Alice needs complex strategic analysis, so the dispatcher uses a more powerful model.

**Alice types:**

```
Analyze our Q3 revenue data and create a competitive strategy
for the next quarter. Include market positioning, pricing
recommendations, and risk assessment.
```

**What the dispatcher does:**

1. Reads the task and classifies it as "complex strategy" (not routine)
2. Spawns or routes to alice-worker with model override: Opus 4.6
3. The more capable model handles the complex analysis

For routine tasks like "check my email" or "upload this file," the dispatcher uses the cheaper default model (MiniMax M2.5 or Codex).

---

## Example 10: The WORKFLOW_AUTO.md File (Complete Template Example)

Here is what a completed WORKFLOW_AUTO.md looks like for a generic deployment:

```markdown
# WORKFLOW_AUTO.md - Team Management Protocol (Dispatcher Routing)

## Dispatcher Pattern (ACTIVE)
Main session = dispatcher/router. Route all incoming messages by sender ID.

## Team Members
| Sender ID | Name | Role | Worker Label | Reply To |
|---|---|---|---|---|
| 1234567890 | Alice Johnson | Operations Lead | alice-worker | 1234567890 |
| 9876543210 | Bob Smith | Head of Marketing | bob-worker | 9876543210 |
| 1122334455 | Charlie Brown | Chief of Operations | charlie-worker | 1122334455 |

## Client Team
| Sender ID | Name | Role | Worker Label | Reply To |
|---|---|---|---|---|
| 5544332211 | Carol Davis | Client (NOT a worker) | carol-worker | 5544332211 |
| 5566778899 | Dana Lee | Content Coordinator | dana-worker | 5566778899 |

## Reply Rules
- Results go ONLY to requesting DM
- No cross-posting unless explicitly requested
- Tag: [Dispatcher] / [worker-label]

## Worker Config
- Model: resolved at runtime via `shared-utils/select_model.py --purpose-tier heavy` (Kimi-first chain — Ollama Cloud preferred → OpenRouter Kimi → Ollama DeepSeek-pro → OpenRouter DeepSeek-pro → OAuth GPT). NEVER Anthropic.
- For mid-tier tasks call with `--purpose-tier mid` (Minimax/Mimo). For bulk/cheap call with `--purpose-tier fast` (DeepSeek-flash/Gemini-lite).
- cleanup: keep
- archiveAfterMinutes: 43200

## Client Rules
- Carol Davis is the CLIENT - never assign tasks, serve respectfully
- Team workers give instructions - AI executes their requests
```

---

## Example 11: Initial Team Intake (Step 0 in INSTALL.md)

**Scenario:** Setting up a new client with 3 team members.

**Agent asks:**
```
How many team members will use this system? (Enter a number between 2 and 20)
```

**Operator answers:** 3

**Agent collects for each member:**

```
Team Member 1:
- Name: Alice Johnson
- Telegram ID: 1234567890
- Role: CEO
- Type: Worker
- Worker label (auto-generated): alice-worker

Team Member 2:
- Name: Bob Smith
- Telegram ID: 9876543210
- Role: Head of Marketing
- Type: Worker
- Worker label (auto-generated): bob-worker

Team Member 3:
- Name: Carol Davis
- Telegram ID: 5544332211
- Role: Owner / Client
- Type: Client
- Worker label (auto-generated): carol-worker
```

**Agent generates TEAM_CONFIG.md:**

```markdown
# TEAM_CONFIG.md - Team Member Configuration
# Generated during skill 15 setup

## Team Members

| Name | Telegram ID | Role | Type | Worker Label |
|------|-------------|------|------|--------------|
| Alice Johnson | 1234567890 | CEO | Worker | alice-worker |
| Bob Smith | 9876543210 | Head of Marketing | Worker | bob-worker |
| Carol Davis | 5544332211 | Owner / Client | Client | carol-worker |
```

The agent then proceeds to add all three IDs to the allowFrom config and the routing table.
