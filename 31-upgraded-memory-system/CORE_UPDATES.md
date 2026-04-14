# Upgraded Memory System - Core File Updates

## Add to MEMORY.md

```markdown
## Upgraded Memory System (8 Layers) - Installed [DATE]

| Layer | Component | Status |
|-------|-----------|--------|
| 1 | Markdown files (MEMORY.md + daily logs) | Active |
| 2 | Memory flush (8-category capture prompt) | Active |
| 3 | Session indexing (past conversations searchable) | Active |
| 4 | Gemini Embedding 2 (semantic search) | Active / PENDING |
| 5 | memory-core (native auto-capture + auto-recall) | Active |
| 6 | Cognee (graph-based knowledge) | Active / PENDING |
| 7 | Obsidian Vault (structured knowledge base) | Active |
| 8 | Active Memory + Wiki System (REQUIRED) | Active |

- Layer 4 provider: gemini, model: models/gemini-embedding-2-preview
- Layer 5: memory-core backend (replaces the legacy memory plugin)
- Layer 6: Cognee requires Docker; marked PENDING if unavailable
- Layer 7: Obsidian app check via `ls /Applications/Obsidian.app` (Mac)
- Layer 8: Active Memory (REQUIRED) + Wiki vault with deterministic pages
- Active Memory config: autoCapture=true, autoRecall=true, backend="builtin"
- All 8 layers run simultaneously. They solve different problems.
- Weekly maintenance: clean MEMORY.md, remove stale entries
- Monthly maintenance: prune daily logs older than 90 days
```

## Add to AGENTS.md

```markdown
## Memory System Rules
- Do NOT disable any of the 8 memory layers without explicit permission
- Memory flush captures 8 categories: people, credentials, project status, decisions, preferences, errors, finances, deadlines
- Session indexing is enabled. Past conversations are searchable.
- Search backend is Gemini Embedding 2 (not Google Embedding 2). Config: memory.backend = "builtin", memorySearch.provider = "gemini"
- memory-core (Layer 5) handles auto-capture and auto-recall. Do not rely on manual memory saves alone.
- ACTIVE MEMORY (Layer 8) IS REQUIRED - must have autoCapture=true and autoRecall=true
- MEMORY.md is the long-term source of truth. Daily logs are session-specific.
- If MEMORY.md gets longer than 1500 lines, consolidate and trim old entries.
- Cognee (Layer 6) provides graph-based knowledge relationships for complex queries.
- Obsidian Vault (Layer 7) maintains structured knowledge with wikilinks and frontmatter.
- Wiki System (Layer 8) enables collaborative documentation with source-backed updates.
- Active Memory config: agents.defaults.memory.autoCapture=true, agents.defaults.memory.autoRecall=true
- Verify Active Memory: `openclaw memory status` should show Backend: builtin, Auto-capture: enabled
```

## Add to TOOLS.md

```markdown
## Memory Search
- Backend: Google Gemini Embedding 2 (API, no local database)
- Provider config: agents.defaults.memorySearch.provider = "gemini"
- Top-level config: memory.backend = "builtin"
- Model: models/gemini-embedding-2-preview
- Requires: GOOGLE_API_KEY environment variable
- Hybrid search: 75% vector weight, 25% text weight
- memory-core (Layer 5): Native OpenClaw memory with auto-capture and auto-recall
- Cognee (Layer 6): Graph-based knowledge relationships (requires Docker)
- Obsidian Vault (Layer 7): Structured knowledge base with wikilinks
- Active Memory + Wiki System (Layer 8): REQUIRED - native memory with auto-capture/recall + collaborative docs
- Active Memory config: agents.defaults.memory.autoCapture=true, agents.defaults.memory.autoRecall=true
- Active Memory check: `openclaw memory status` (should show Backend: builtin, Auto-capture: enabled)
```
