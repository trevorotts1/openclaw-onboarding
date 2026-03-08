# BlackCEO Team Management - Usage Instructions

This document covers how to USE the dispatcher/worker system day to day, after you have completed the installation steps in INSTALL.md.

---

## How the Dispatcher Works

Your AI is now a "dispatcher." When a team member sends a message on Telegram, the AI does not handle it directly. Instead:

1. It reads the incoming message
2. It checks who sent it (using their Telegram ID)
3. It looks up the correct worker for that person
4. It sends the task to that worker
5. The worker does the work
6. The dispatcher sends the result back ONLY to the person who asked

This keeps everyone's conversations separate and private.

---

## Key Roles

There are four types of roles in this system:

### Dispatcher (Main Session)
- This is the AI's main brain
- It routes messages, manages workers, and bridges communication when asked
- It has FULL VISIBILITY across all workers - it can read any worker's history
- It NEVER does the actual work itself - it delegates to workers

### Management (BLACK CEO Team)
- Trevor Otts (5252140759) - Operations Lead / AI Director
- LeAnne (6663821679) - Head of Marketing
- E.R. Spaulding (6771245262) - Chief of Operations
- These team members give instructions and the AI executes
- Their IDs are ALWAYS present in every deployment

### Team Workers
- Additional team members added for specific client deployments
- They can send tasks and receive results through their own dedicated worker

### Client
- The client (business owner) is NEVER assigned tasks
- The AI serves them respectfully - executes what they ask, reports results
- Marked in the routing table as "Client (NOT a worker)"

---

## Message Flow (Step by Step)

### When a Message Arrives

1. **Dispatcher receives the message** from Telegram
2. **Dispatcher identifies the sender** by checking the Telegram user ID in the message metadata
3. **Dispatcher looks up the routing table** in WORKFLOW_AUTO.md to find the correct worker label

### If the Worker Already Exists and Is Active

4. **Dispatcher sends the task** to the existing worker using sessions_send
5. **Worker processes the task** using its own context window
6. **Worker completes the task** and returns the result
7. **Dispatcher sends the result** ONLY to the sender's Telegram DM

### If the Worker Does Not Exist Yet

4. **Dispatcher spawns a new worker** using sessions_spawn with the correct label, model, and cleanup: keep
5. The worker is now active and receives the task
6. Worker processes and returns the result
7. Dispatcher sends the result ONLY to the sender's Telegram DM

---

## Worker Lifecycle

Workers go through these states during their life:

### State 1: Not Yet Created
- The worker does not exist yet
- This happens when a person sends their very first message
- The dispatcher creates the worker automatically

### State 2: Active (Running a Task)
- The worker is busy doing something
- It has its own conversation history (context window)
- It can use all shared tools, files, and memory
- When the task is done, the worker stays alive and goes to Idle

### State 3: Idle (Waiting)
- The worker is alive but not currently doing anything
- Its conversation history is preserved
- When a new message comes from the same person, it picks right back up

### State 4: Archived
- The worker has been cleaned up (either automatically after 30 days of no activity, or manually)
- Its conversation history is gone
- Shared files and memory on disk are still there
- When the next message comes from that person, a fresh worker is spawned

### State 5: Gateway Restart
- All workers are lost when the OpenClaw gateway restarts
- This is normal and expected
- Workers are automatically re-created when each person sends their next message
- No manual action needed

---

## What Workers Share vs. What Is Isolated

### Shared (all workers can see these):
- The workspace directory and all files in it
- All shared workspace and memory files (AGENTS.md, TOOLS.md, etc.)
- All configured tools and skills (Google Workspace, etc.)
- Secrets and environment variables

### Isolated (each worker has its own):
- Conversation history (what was discussed in that worker's session)
- Token usage (each worker tracks its own)

This means: Worker A cannot see Worker B's conversation. But both workers can read the same files on disk.

---

## Message Isolation Rules

These rules keep everyone's messages separate and private:

### Inbound (Messages Coming In)
- Every incoming message is routed by sender ID
- One person's instructions are NEVER mixed into another person's worker
- If the dispatcher cannot identify the sender, it asks who they are

### Execution (While Working)
- Each person's work runs inside their own worker
- Worker A cannot see Worker B's active tasks or conversation
- Workers share files on disk but not live conversation state

### Outbound (Results Going Out)
- Results go ONLY to the Telegram DM of the person who requested them
- No other DMs receive the result

### Cross-Posting
- **Default: No cross-posting. Ever.**
- **Exception:** Only when the sender explicitly says "send this to [person]" or "share this with [person]"
- Cross-posts are tagged so the recipient knows it was forwarded

### Dispatcher Visibility (Exception to Isolation)
The dispatcher (main session) has FULL visibility across ALL workers. It CAN:
- Read any worker's conversation history via sessions_history
- Summarize what was discussed in any worker's session
- Relay information between workers when explicitly asked by the sender
- Forward results from one worker to another person's DM when told to

The dispatcher MUST:
- Only relay when the sender explicitly asks (for example: "send Spaulding the update from my last conversation")
- Tag forwarded messages: "Forwarded from [worker-label]"
- Never auto-share between workers without being asked

---

## Model Selection for Workers

The models used for workers must support tool calls. Models that do not support tool calls will fail silently or produce incomplete results.

### Recommended Model Roles for Workers

| Task Type | Recommended Model | Why |
|-----------|-------------------|-----|
| Routine execution (file operations, API calls) | MiniMax M2.5 or Codex | Cheap and fast |
| Complex strategy or debugging | Opus 4.6 | Most capable reasoning |
| Creative writing (copy, emails, hooks) | Mistral Creative | Best creative output |
| Bulk or cost-sensitive tasks | Gemini Flash | Cheapest option |
| General purpose | Sonnet 4.6 | Good all-around fallback |

### Decision Tree

When the dispatcher is about to spawn a worker or assign a task:

1. Is this a complex strategy, architecture, or debugging task? Use Opus 4.6
2. Is this creative writing (copy, emails, scripts, hooks)? Use Mistral Creative
3. Is this routine execution (file operations, uploads, API calls)? Use MiniMax M2.5 or Codex
4. Is this bulk or cost-sensitive? Use Gemini Flash
5. None of the above? Use Sonnet 4.6

### Models to Avoid

- Models without tool-call capability (some reasoning-only models)
- Models with known rate-limit issues at your usage volume
- Pay-per-token premium models for routine tasks (costs will add up fast)

---

## Client vs. Worker Distinction

This is critical - treat these roles differently:

### Worker Sub-Agents (Team Members)
- Execute tasks assigned by team members
- Can receive directives like "do this, fix that, create this"
- Proactive suggestions are acceptable

### Client Sub-Agents
- Serve the client's requests respectfully
- NEVER assign the client tasks
- NEVER boss the client around
- Execute what they ask and report results
- Mark client sub-agents clearly in the routing table with "Client (NOT a worker)"

---

## Scaling Guidelines

| Team Size | maxConcurrent | Notes |
|-----------|---------------|-------|
| 1-3 people | 4 | Comfortable with overhead |
| 4-8 people | 8 | Standard team |
| 9-15 people | 12 | Monitor token usage |
| 16+ people | 16+ | Consider cost optimization - assign cheaper models to lower-priority workers |

Each worker has its own token usage. Monitor costs via usage-tracker reports. For high-volume teams, assign cheaper models to lower-priority workers.

---

## Quick Reference Commands

| What You Want to Do | Command |
|---------------------|---------|
| List all active workers | /subagents list |
| Kill a specific worker | /subagents kill [worker-label] |
| Kill all workers | /subagents kill all |
| Check worker history | sessions_history (ask the dispatcher) |
| Restart all workers | openclaw gateway restart (workers re-spawn on next message) |

---

## Troubleshooting

| Problem | Likely Cause | Fix |
|---------|-------------|-----|
| Bot ignores messages | Sender ID not in allowFrom | Add their ID to channels.telegram.allowFrom in openclaw.json |
| Wrong person gets the response | Routing table has wrong sender ID | Check WORKFLOW_AUTO.md for correct IDs |
| Worker keeps resetting | Gateway restarting frequently | Check gateway logs, ensure stable connection |
| "Model does not support tool calls" | Using a reasoning-only model | Switch to MiniMax M2.5, Codex, or Sonnet |
| Messages bleeding between workers | Dispatcher not checking sender ID | Verify the routing table is complete and accurate |
| Slow responses | Workers overloaded | Increase maxConcurrent or use faster models |
