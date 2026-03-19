# QMD-RETRIEVAL-GUIDE.md - How Agents Query Personas at Runtime

## What QMD Does in This System

QMD is the Layer 2 retrieval system for the persona library. It allows any agent to search
across all persona blueprints and pull the exact section they need - without loading every
full persona into context.

- **Layer 1** (always in context): Lightweight routing tags and persona summaries
- **Layer 2** (on-demand retrieval): Full methodology sections, question libraries, tools,
  frameworks - pulled surgically via QMD query

---

## Setup - Adding Personas to QMD

### Add the full persona library as a collection

```bash
  --name coaching-personas \
  --mask "**/*.md"
```

### Index it

```bash
python3 ~/clawd/scripts/gemini-indexer.py
qmd embed
```

### Verify

```bash
qmd status
# Should show coaching-personas collection with file count
```

### After each new persona is built, re-index

```bash
python3 ~/clawd/scripts/gemini-indexer.py
qmd embed
```

---

## How Agents Query at Runtime

### Query Pattern 1 - Find the right persona for a situation

Use when: you need to identify which persona to activate for a specific human challenge or task

```bash
qmd query "methodology for building habits and systems for consistency"
qmd query "negotiation framework for difficult conversations and objection handling"
qmd query "sales questioning technique for uncovering customer problems"
```

QMD returns the most relevant sections from matching persona blueprints.
Read the results to identify which persona to activate.

### Query Pattern 2 - Pull a specific section from a known persona

Use when: you know which persona you want, and need a specific section (questions, tools, etc.)

```bash
qmd query "Atomic Habits coaching questions assessment phase"
qmd query "SPIN Selling decision logic framework agent governance"
qmd query "Never Split the Difference objection handling resistance"
```

### Query Pattern 3 - Find execution standards for a task type

Use when: an agent is about to execute a specific type of professional task and needs
the governance standard

```bash
qmd query "email outreach quality standard non-negotiable rules"
qmd query "sales call preparation checklist execution standard"
qmd query "leadership coaching session structure definition of done"
```

### Query Pattern 4 - Find failure patterns to avoid

Use when: an agent is reviewing their own output or checking for common mistakes

```bash
qmd query "failure patterns amateur mistakes sales execution"
qmd query "what bad coaching looks like versus expert coaching"
qmd query "content writing failure patterns quality markers"
```

---

## Query Syntax Reference

### Simple hybrid query (recommended - combines BM25 + vector)
```bash
qmd query "your question here"
```

### Structured query (when you need precise control)
```bash
qmd query 'lex:habits systems consistency
vec:building repeatable behaviors over time
hyde:a methodology for creating automatic daily routines'
```

### Get a specific file section
```bash
qmd get personas/clear-atomic-habits/persona-blueprint.md:1 -l 100
# Returns lines 1-100 of the Atomic Habits blueprint
```

### Search multiple personas at once
```bash
qmd multi-get "personas/*/persona-blueprint.md"
# Returns summaries of all persona blueprints
```

---

## How to Use QMD Results in Agent Context

When QMD returns results, the agent should:

1. **Read the returned section** - QMD returns the matching text with file path and line numbers
2. **Identify the persona** - note which persona blueprint the result came from
3. **Pull more context if needed** - use `qmd get [path]:[line] -l [count]` to expand
4. **Apply the methodology** - use the extracted framework, questions, or standards directly

### Example Agent Workflow

```
Agent task: Write a sales outreach email for a SaaS product

Step 1: Query for relevant governance standard
→ qmd query "sales outreach email quality standard execution rules"

Step 2: QMD returns sections from SPIN Selling and StoryBrand personas

Step 3: Agent reads the returned standards:
- SPIN: Open with situation question, not product pitch
- StoryBrand: Customer is the hero, not the product

Step 4: Agent writes email following those standards

Step 5: Agent self-reviews against the non-negotiable rules returned by QMD
```

---

## QMD Collection Maintenance

### Check collection health
```bash
qmd status
```

### After adding new persona blueprints
```bash
python3 ~/clawd/scripts/gemini-indexer.py
qmd embed
```

### If results seem stale or wrong
```bash
qmd cleanup
python3 ~/clawd/scripts/gemini-indexer.py
qmd embed
```

### View what is indexed
```bash
qmd ls coaching-personas
```

---

## Integration with Routing System

The routing system (trigger-matrix.md, task-routing-matrix.md) identifies WHICH persona to activate.
QMD retrieves the CONTENT from that persona on demand.

They work together:
1. Routing engine matches situation to persona (using keyword/tag triggers)
2. Persona summary activates (Layer 1 - already in context)
3. For deeper methodology detail, agent runs QMD query (Layer 2 - on-demand)
4. QMD returns the specific sections needed for that task or coaching moment
