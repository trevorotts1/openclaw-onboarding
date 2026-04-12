# Upgraded Memory System - Usage Instructions

## How the 8 Layers Work Together

Every time you interact with your agent, all 8 layers are active:

1. **You say something.** The agent receives your message.
2. **Layer 5 (memory-core) auto-recalls** relevant memories before the agent responds.
3. **Layer 3 (Session indexing)** lets the agent search past conversations if needed.
4. **Layer 4 (Gemini search)** finds relevant content from your memory files by meaning.
5. **The agent responds** using all that context.
6. **Layer 5 (memory-core) auto-captures** important facts from the conversation.
7. **When context gets full, Layer 2 (flush)** saves important information to daily logs before compaction clears the context window.
8. **Layer 1 (markdown files)** stores everything permanently on disk.

You do not need to do anything special. The system works automatically.

## Maintaining Your Memory

### Weekly: Clean up MEMORY.md

At least once a week, open ~/clawd/MEMORY.md and:
- Remove entries that are no longer relevant
- Correct any information that has changed
- Consolidate duplicate entries

Use Obsidian if you want a nice UI for editing markdown files.

### Monthly: Review daily logs

Check ~/clawd/memory/ for old daily logs. Delete logs older than 90 days that contain only routine information. Keep logs that document important decisions.

### When things feel off: Test the search

If the agent seems to be forgetting things or returning bad search results:

```
Ask: "Search your memory for [topic]"
```

If results are poor, the index may need refreshing. This happens automatically but you can force it by restarting the gateway.

## Manual Memory Operations

### Save something important right now
Just tell your agent: "Remember that [fact]"

### Search for something specific
Ask: "Search your memory for [topic]"

### Review what was saved today
Ask: "Show me today's memory log" or check ~/clawd/memory/YYYY-MM-DD.md

### List key decisions from a conversation
At the end of an important session, say: "List the key decisions from this session that we should save to memory"
Then pick the ones you want saved.
