# Teach Yourself Protocol - How to Use

## Step-by-Step Process

### 1. Announce
Tell the user: "I am activating the Teach Yourself Protocol to permanently retain this knowledge."
Never execute TSP silently. The user must always know when it is running.

### 2. Understand What You Are Learning
- What category? (tool, API, process, preference, contact, credential)
- How often will you use it? (daily, weekly, rarely)
- What priority? (CRITICAL, HIGH, STANDARD, REFERENCE)

### 3. Assess Size
| Content Size | Classification | What to Do |
|-------------|---------------|------------|
| 1-10 lines | Small | Core files only |
| 11-25 lines | Medium | Core files only, be concise |
| 25-100 lines | Large | Deep file in master folder + core summary |
| 100+ lines | Very Large | Deep file in master folder + core summary |
| Multi-topic / API docs | Massive | Folder structure + deep files + core summary |

### 4. Check for Existing Knowledge
Search ALL core files and the master files folder BEFORE creating anything new.
- If found and matches: update it, do not duplicate
- If found but conflicts: flag to user, ask which version is correct
- If not found: proceed to create new

### 5. Create Deep File (If Needed)
Save COMPLETE, UNABRIDGED content to master files folder with this header:
```
# [Topic Name]
- Source: [where this came from]
- Date learned: [date]
- Priority: [CRITICAL/HIGH/STANDARD/REFERENCE]
- Referenced by: [which core files point to this]
```
NEVER truncate the deep file. It is the full reference.

### 6. Write Core File Summaries
Add lightweight summaries (10-25 lines based on priority) to relevant core files.

Every summary must pass the Five Question Test:
1. What is this? (one sentence)
2. When do I use it? (triggers)
3. What do I need to know right now? (key facts)
4. Where is the full reference? (file path)
5. When should I go deeper? (scenarios requiring the full doc)

### 7. Confirm to User
Report:
- What you learned
- Where the full document is stored
- Which core files were updated
- What was added to each

## Priority Tags

| Priority | Tag | Use When | Summary Length |
|----------|-----|----------|---------------|
| CRITICAL | [PRIORITY: CRITICAL] | Daily use, core operations | 20-25 lines |
| HIGH | [PRIORITY: HIGH] | Weekly use, quality matters | 15-20 lines |
| STANDARD | [PRIORITY: STANDARD] | Occasional use | 10-15 lines |
| REFERENCE | [PRIORITY: REFERENCE] | Rare, edge cases | 5-10 lines |

## Staleness Detection
- Under 30 days: Fresh. Use confidently.
- 30-90 days: Aging. Note the age if errors occur.
- Over 90 days: Stale. Verify before relying on it.

## Which Core File Gets What

| Knowledge Type | Primary File | Secondary Files |
|---------------|-------------|-----------------|
| Tool/API usage | TOOLS.md | MEMORY.md |
| Behavioral rules | AGENTS.md | IDENTITY.md |
| User preferences | USER.md | MEMORY.md |
| Personal identity | IDENTITY.md | SOUL.md |
| Recurring tasks | HEARTBEAT.md | MEMORY.md |
| Contact info | USER.md | MEMORY.md |
| Lessons learned | MEMORY.md | IDENTITY.md |

## Common Mistakes

1. Dumping full content into core files (causes bloat, burns tokens)
2. Creating deep file but not referencing it from any core file (orphan file, invisible)
3. Creating duplicate master files folders (search first)
4. Skipping the announcement (user must know TSP is active)
5. Summarizing the deep file (deep file is COMPLETE, never truncate)
6. Not checking for existing knowledge (always search first)
7. Over-summarizing (if the agent would be stuck with just the summary, it is too thin)
8. Under-summarizing (if the summary is 30+ lines, it is too thick)
