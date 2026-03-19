# Skill 31: Upgraded Memory System (5-Layer Architecture)

## What This Skill Is About

This skill upgrades your OpenClaw agent from the default memory system to a 5-layer architecture that makes your agent genuinely remember everything, find information accurately, and improve over time. The default memory system works okay at first but degrades as memory grows. This fixes that.

## When to Use This Skill

- You are setting up a new OpenClaw installation and want the best memory from day one
- Your agent keeps forgetting things you told it
- Memory search returns irrelevant results
- Important information gets lost during compaction
- You want your agent to automatically capture and recall memory without being told
- You are migrating from the old QMD search system to Google Gemini Embedding 2

## The 5 Layers

| Layer | What It Does | How It Works |
|-------|-------------|--------------|
| 1. Markdown files | Stores the source of truth | MEMORY.md (long-term) and daily logs (memory/YYYY-MM-DD.md) |
| 2. Memory flush | Saves important context before compaction | Custom prompt with 8 categories tells the agent exactly what to capture |
| 3. Session indexing | Makes past conversations searchable | Agent can search what you talked about last week, not just today |
| 4. Gemini Embedding 2 | Finds information by meaning | Google's multimodal embedding API replaces the old local search |
| 5. Mem0 | Auto-captures and auto-recalls memory | Memory lives outside the context window, survives compaction |

## Files in This Folder and Reading Order

1. **SKILL.md** - You are here. Overview and context.
2. **INSTALL.md** - Step-by-step installation for all 5 layers.
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

1. All 5 layers run simultaneously. They do not compete. Each solves a different problem.
2. Layer 4 (Gemini Embedding 2) replaces the old QMD search engine. QMD is deprecated.
3. Layer 5 (Mem0) installs as an OpenClaw plugin. It occupies the memory plugin slot.
4. The memory flush prompt must include explicit categories or it saves junk.
5. Session indexing adds noise, so the flush prompt is even more important as a filter.
6. If migrating from QMD: run the migration steps in INSTALL.md before enabling Layer 4.
7. Do NOT install Cognee (Layer 6) as part of this skill. That is a separate advanced add-on requiring Docker.
