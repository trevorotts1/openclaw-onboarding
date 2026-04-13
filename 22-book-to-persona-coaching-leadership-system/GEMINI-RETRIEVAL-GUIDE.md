# GEMINI-RETRIEVAL-GUIDE.md - How Agents Query Personas at Runtime

## What Gemini Engine Does in This System

Gemini Embeddings 2 is the Layer 2 retrieval system for the persona library. It allows any agent to search
across all persona blueprints and pull the exact section they need - without loading every
full persona into context.

- **Layer 1** (always in context): Lightweight routing tags and persona summaries
- **Layer 2** (on-demand retrieval): Full methodology sections, question libraries, tools,
  frameworks - pulled surgically via Gemini Engine query

---

## Setup - Adding Personas to Gemini Engine

### Add the full persona library as a collection

```bash
python3 ~/.openclaw/workspace/scripts/gemini-indexer.py --add \
  --path ~/Downloads/openclaw-master-files/coaching-personas/personas \
  --name coaching-personas \
  --mask "**/*.md"
```

### Index it

```bash
python3 ~/.openclaw/workspace/scripts/gemini-indexer.py
```

### Verify

```bash
python3 ~/.openclaw/workspace/scripts/gemini-indexer.py --status
```

Expected output shows: `coaching-personas` collection with file count.

### After each new persona is built, re-index

```bash
python3 ~/.openclaw/workspace/scripts/gemini-indexer.py
```

---

## How Agents Query at Runtime

### Query Pattern 1 - Find the right persona for a situation

Use when: you need to identify which persona to activate for a specific human challenge or task

```bash
python3 ~/.openclaw/workspace/scripts/gemini-search.py "methodology for building habits and systems for consistency"
python3 ~/.openclaw/workspace/scripts/gemini-search.py "negotiation framework for difficult conversations and objection handling"
python3 ~/.openclaw/workspace/scripts/gemini-search.py "sales questioning technique for uncovering customer problems"
```

**Expected output format:**
```
[coaching-personas/clear-atomic-habits/persona-blueprint.md:142-158]
Score: 0.87
The habit loop consists of four stages: cue, craving, response, and reward. To build
a new habit, make the cue obvious, the craving attractive, the response easy, and
the reward satisfying...
```

Gemini Engine returns the most relevant sections from matching persona blueprints.
Read the results to identify which persona to activate.

### Query Pattern 2 - Pull a specific section from a known persona

Use when: you know which persona you want, and need a specific section (questions, tools, etc.)

```bash
python3 ~/.openclaw/workspace/scripts/gemini-search.py "Atomic Habits coaching questions assessment phase"
python3 ~/.openclaw/workspace/scripts/gemini-search.py "SPIN Selling decision logic framework agent governance"
python3 ~/.openclaw/workspace/scripts/gemini-search.py "Never Split the Difference objection handling resistance"
```

### Query Pattern 3 - Find execution standards for a task type

Use when: an agent is about to execute a specific type of professional task and needs
the governance standard

```bash
python3 ~/.openclaw/workspace/scripts/gemini-search.py "email outreach quality standard non-negotiable rules"
python3 ~/.openclaw/workspace/scripts/gemini-search.py "sales call preparation checklist execution standard"
python3 ~/.openclaw/workspace/scripts/gemini-search.py "leadership coaching session structure definition of done"
```

### Query Pattern 4 - Find failure patterns to avoid

Use when: an agent is reviewing their own output or checking for common mistakes

```bash
python3 ~/.openclaw/workspace/scripts/gemini-search.py "failure patterns amateur mistakes sales execution"
python3 ~/.openclaw/workspace/scripts/gemini-search.py "what bad coaching looks like versus expert coaching"
python3 ~/.openclaw/workspace/scripts/gemini-search.py "content writing failure patterns quality markers"
```

---

## Query Syntax Reference

### Simple hybrid query (recommended - combines BM25 + vector)
```bash
python3 ~/.openclaw/workspace/scripts/gemini-search.py "your question here"
```

**Example:**
```bash
python3 ~/.openclaw/workspace/scripts/gemini-search.py "habit stacking implementation guide"
```

### Structured query (when you need precise control)
```bash
python3 ~/.openclaw/workspace/scripts/gemini-search.py "habits systems consistency"
```

### Get a specific file section
```bash
head -100 ~/Downloads/openclaw-master-files/coaching-personas/personas/clear-atomic-habits/persona-blueprint.md
```

Returns lines 1-100 of the Atomic Habits blueprint.

### Search multiple personas at once
```bash
python3 ~/.openclaw/workspace/scripts/gemini-search.py "all personas"
```

Returns summaries of all persona blueprints.

---

## How to Use Gemini Engine Results in Agent Context

When Gemini Engine returns results, the agent should:

1. **Read the returned section** - Gemini Engine returns the matching text with file path and line numbers
2. **Identify the persona** - note which persona blueprint the result came from
3. **Pull more context if needed** - use `head` or `cat [path]` to read the full file directly to expand
4. **Apply the methodology** - use the extracted framework, questions, or standards directly

### Example Agent Workflow

```
Agent task: Write a sales outreach email for a SaaS product

Step 1: Query for relevant governance standard
-> python3 ~/.openclaw/workspace/scripts/gemini-search.py "sales outreach email quality standard execution rules"

Step 2: Gemini Engine returns sections from SPIN Selling and StoryBrand personas

Step 3: Agent reads the returned standards:
- SPIN: Open with situation question, not product pitch
- StoryBrand: Customer is the hero, not the product

Step 4: Agent writes email following those standards

Step 5: Agent self-reviews against the non-negotiable rules returned by Gemini Engine
```

---

## Gemini Engine Collection Maintenance

### Check collection health
```bash
python3 ~/.openclaw/workspace/scripts/gemini-indexer.py --status
```

**Example output:**
```
Collection: coaching-personas
Files indexed: 42
Last indexed: March 18 at 3:45 PM
Status: READY
```

### After adding new persona blueprints
```bash
python3 ~/.openclaw/workspace/scripts/gemini-indexer.py
```

### If results seem stale or wrong
```bash
python3 ~/.openclaw/workspace/scripts/gemini-indexer.py --rebuild
python3 ~/.openclaw/workspace/scripts/gemini-indexer.py
```

### View what is indexed
```bash
python3 ~/.openclaw/workspace/scripts/gemini-indexer.py --status
```

---

## Wiki Integration (Memory Surgery Phase 2)

The persona library is integrated with the OpenClaw Memory Wiki system for unified knowledge retrieval.

### How It Works

**Wiki search covers:**
- All persona blueprints (persona-blueprint.md files)
- Extraction notes and analysis notes
- Persona category tags and metadata

**Search command:**
```bash
wiki_search "coaching methodology for sales objections"
wiki_search "habit building frameworks"
```

**Wiki get for direct retrieval:**
```bash
wiki_get persona-hormozi-100m-offers
wiki_get coaching-personas/atomic-habits
```

### Wiki + Gemini Engine Together

| Use Case | Tool | When |
|----------|------|------|
| Quick persona lookup | `wiki_search` | Finding persona by name or tag |
| Deep methodology search | `wiki_get` | Reading full blueprint sections |
| Semantic content retrieval | `gemini-search.py` | Finding specific frameworks across all personas |
| Runtime agent queries | Gemini Engine | Task-specific methodology extraction |

**Best practice:** Use wiki for browsing/discovery, Gemini Engine for surgical content retrieval during task execution.

---

## Integration with Routing System

The routing system (trigger-matrix.md, task-routing-matrix.md) identifies WHICH persona to activate.
Gemini Engine retrieves the CONTENT from that persona on demand.

They work together:
1. Routing engine matches situation to persona (using keyword/tag triggers)
2. Persona summary activates (Layer 1 - already in context)
3. For deeper methodology detail, agent runs Gemini Engine query (Layer 2 - on-demand)
4. Gemini Engine returns the specific sections needed for that task or coaching moment

---

<!-- BREADCRUMB: memory-surgery/skill-22-mac | 2026-04-12 | v6.5.7 | Added wiki integration section -->
