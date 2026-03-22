# Upgraded Memory System - Core File Updates

## Add to MEMORY.md

```markdown
## Upgraded Memory System (5 Layers) - Installed [DATE]

| Layer | Component | Status |
|-------|-----------|--------|
| 1 | Markdown files (MEMORY.md + daily logs) | Active |
| 2 | Memory flush (8-category capture prompt) | Active |
| 3 | Session indexing (past conversations searchable) | Active |
| 4 | Gemini Embedding 2 (semantic search) | Active / PENDING |
| 5 | Mem0 (auto-capture + auto-recall) | Active |

- Layer 4 provider: gemini, model: models/gemini-embedding-2-preview
- Layer 5 plugin: openclaw-mem0 (mode: open-source)
- All 5 layers run simultaneously. They solve different problems.
- Weekly maintenance: clean MEMORY.md, remove stale entries
- Monthly maintenance: prune daily logs older than 90 days
```

## Add to AGENTS.md

```markdown
## Memory System Rules
- Do NOT disable any of the 5 memory layers without explicit permission
- Memory flush captures 8 categories: people, credentials, project status, decisions, preferences, errors, finances, deadlines
- Session indexing is enabled. Past conversations are searchable.
- Search backend is Gemini Embedding 2 (not Google Embedding 2). Config: memory.backend = "gemini"
- Mem0 handles auto-capture and auto-recall. Do not rely on manual memory saves alone.
- MEMORY.md is the long-term source of truth. Daily logs are session-specific.
- If MEMORY.md gets longer than 1500 lines, consolidate and trim old entries.
```

## Add to TOOLS.md

```markdown
## Memory Search
- Backend: Google Gemini Embedding 2 (API, no local database)
- Provider config: agents.defaults.memorySearch.provider = "gemini"
- Model: models/gemini-embedding-2-preview
- Requires: GOOGLE_API_KEY environment variable
- Hybrid search: 75% vector weight, 25% text weight
- Mem0 plugin: openclaw-mem0 (auto-capture on, auto-recall on)
```
