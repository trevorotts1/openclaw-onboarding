# Skill 31: Upgraded Memory System (8-Layer Architecture)

> 🔴 **SOURCE OF TRUTH RULE**: This skill's instructions take precedence over generic OpenClaw memory documentation. When in doubt, follow SKILL.md + INSTALL.md in this folder.

> 🔴 **ALL 8 LAYERS ARE REQUIRED** (not optional): Markdown files, Memory flush, Session indexing, Gemini Embedding 2, memory-core, Cognee, Obsidian Vault, Wiki System.

> 🔴 **DREAMS.md IS REQUIRED** - Must exist in workspace root for active memory to function.

> 🔴 **ACTIVE MEMORY IS REQUIRED** - Layer 8 (Active Memory) requires memory-core with `autoCapture: true` and `autoRecall: true`. This is NOT optional.

## Active Memory Configuration (Layer 8)

Active Memory is the REQUIRED Layer 8 component that enables native memory capture and recall.

```json
"memory": {
  "backend": "builtin"
},
"agents": {
  "defaults": {
    "memory": {
      "autoCapture": true,
      "autoRecall": true
    },
    "activeMemory": {
      "enabled": true,
      "flushIntervalMinutes": 30,
      "contextInjection": {
        "memoryWiki": true,
        "cognee": true
      }
    }
  }
}
```

### Config Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `memory.backend` | string | "builtin" | MUST be "builtin" for memory-core |
| `agents.defaults.memory.autoCapture` | boolean | true | Automatically capture important context |
| `agents.defaults.memory.autoRecall` | boolean | true | Automatically recall relevant memory |
| `agents.defaults.activeMemory.enabled` | boolean | true | Master switch for Active Memory |
| `agents.defaults.activeMemory.flushIntervalMinutes` | number | 30 | How often to flush working memory |
| `agents.defaults.activeMemory.contextInjection.memoryWiki` | boolean | true | Inject memory wiki into context |
| `agents.defaults.activeMemory.contextInjection.cognee` | boolean | true | Inject Cognee graph knowledge |

## What This Skill Is About

This skill upgrades your OpenClaw agent from the default memory system to an 8-layer architecture that makes your agent genuinely remember everything, find information accurately, and improve over time. The default memory system works okay at first but degrades as memory grows. This fixes that.

## When to Use This Skill

- You are setting up a new OpenClaw installation and want the best memory from day one
- Your agent keeps forgetting things you told it
- Memory search returns irrelevant results
- Important information gets lost during compaction
- You want your agent to automatically capture and recall memory without being told
- You are migrating from the old Google Embedding 2 retrieval query system to Google Gemini Embedding 2

## The 8 Layers

| Layer | What It Does | How It Works |
|-------|-------------|--------------|
| 1. Markdown files | Stores the source of truth | MEMORY.md (long-term) and daily logs (memory/YYYY-MM-DD.md) |
| 2. Memory flush | Saves important context before compaction | Custom prompt with 8 categories tells the agent exactly what to capture |
| 3. Session indexing | Makes past conversations searchable | Agent can search what you talked about last week, not just today |
| 4. Gemini Embedding 2 | Finds information by meaning | Google's multimodal embedding API replaces the old local search |
| 5. memory-core | Auto-captures and auto-recalls memory | Native OpenClaw memory system - survives compaction, no external dependencies |
| 6. Cognee | Graph-based knowledge relationships | Connects facts, people, projects in a graph database for complex queries |
| 7. Obsidian Vault | Structured knowledge base | Obsidian-compatible markdown with wikilinks, frontmatter, and daily notes |
| 8. Active Memory + Wiki System | Native memory capture/recall + collaborative docs | memory-core auto-captures context; Wiki provides structured knowledge base |

## Files in This Folder and Reading Order

1. **SKILL.md** - You are here. Overview and context.
2. **INSTALL.md** - Step-by-step installation for all 8 layers.
3. **INSTRUCTIONS.md** - How to use and maintain the memory system after installation.
4. **EXAMPLES.md** - Example searches, flush outputs, and memory operations.
5. **CORE_UPDATES.md** - What to add to AGENTS.md, TOOLS.md, and MEMORY.md.
6. **upgraded-memory-system.skill** - Skill metadata file.

## Prerequisites

| Prerequisite | Required For | How to Check |
|-------------|-------------|--------------|
| Teach Yourself Protocol (TYP) | All skills | Check AGENTS.md for "Teach Yourself Protocol" |
| Google API key | Layer 4 (Gemini search) | `echo $GOOGLE_API_KEY` returns a key starting with AIza |
| Python 3.8+ | Layer 4 (Gemini search) | `python3 --version` |
| google-genai + numpy | Layer 4 (Gemini search) | `python3 -c "import google.genai; import numpy"` |
| OpenClaw running | All layers | `openclaw status` shows gateway running |

## Prerequisite Handling

**If prerequisites are NOT met:** Install all skill files anyway. Mark the skill as INSTALLED but NOT IMPLEMENTED. Add a note to AGENTS.md listing which prerequisites are missing. The agent should remind the user once per session until prerequisites are met.

**If prerequisites ARE met:** Install and implement fully. Run verification tests for each layer.

## Key Things the AI Agent Must Know

1. All 8 layers run simultaneously. They do not compete. Each solves a different problem.
2. Layer 4 (Gemini Embedding 2) replaces the old Google Embedding 2 retrieval query engine. Google Embedding 2 is deprecated.
3. Layer 5 (memory-core) is the native OpenClaw memory system. It replaces the legacy memory plugin.
4. Layer 8 (Active Memory + Wiki System) is REQUIRED - memory-core must be enabled with autoCapture and autoRecall.
5. Layers 6-7 (Cognee, Obsidian Vault) are advanced add-ons that extend memory capabilities.
4. The memory flush prompt must include explicit categories or it saves junk.
5. Session indexing adds noise, so the flush prompt is even more important as a filter.
6. If migrating from Google Embedding 2: run the migration steps in INSTALL.md before enabling Layer 4.
7. Cognee (Layer 6) requires Docker. Install only if you need graph-based knowledge relationships.
