# Upgraded Memory System - Core File Updates

These are the EXACT additions to make to each core .md file.
Follow TYP rules: append only, never overwrite existing content.

---

## Add to MEMORY.md

```markdown
## Upgraded Memory System (5 Layers) - Installed [DATE]
- Layer 1: Markdown files (MEMORY.md + daily logs) - Active
- Layer 2: Memory flush (8-category capture) - Active
- Layer 3: Session indexing - Active
- Layer 4: Gemini Embedding 2 search - Active / PENDING
- Layer 5: Mem0 auto-capture + auto-recall - Active
- Maintenance: trim MEMORY.md at 1500 lines. Prune daily logs older than 90 days.
```

---

## Add to AGENTS.md

```markdown
## Memory System Rules
- 5 memory layers are active. Do not disable any without explicit permission.
- Memory flush captures: people, credentials, project status, decisions, preferences, errors, finances, deadlines.
- MEMORY.md is the long-term source of truth. Daily logs are session-specific.
- Do not rely on manual memory saves alone. Mem0 handles auto-capture.
- If MEMORY.md exceeds 1500 lines, consolidate and trim old entries.
```

---

## Add to TOOLS.md

```markdown
## Memory Search
- Backend: builtin (memory.backend = "builtin")
- Provider: gemini (memorySearch.provider = "gemini")
- Model: models/gemini-embedding-2-preview
- Requires: GOOGLE_API_KEY
- Hybrid search: 75% vector / 25% text
- Mem0 plugin: openclaw-mem0 (auto-capture on, auto-recall on)
```

---

## Add to HEARTBEAT.md

```markdown
## Memory Health Check
- Periodic: verify openclaw memory status shows Provider: gemini and indexed file count > 0
- If indexing drops to 0 or provider shows wrong value, flag for investigation
```

---

## Do NOT modify these files:
- USER.md (no memory system content belongs here)
- SOUL.md (no memory system content belongs here)
- IDENTITY.md (no memory system content belongs here)
