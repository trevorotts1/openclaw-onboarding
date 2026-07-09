---
name: graphify-knowledge-graph
description: Turns the client's OWN AI workforce / codebase / docs into a persistent, queryable knowledge graph that the client's agent uses to answer "how is this wired / what depends on what / where does X live" questions. Maps once with the CLIENT'S OWN model (their Ollama / configured model — NEVER the operator's keys), installs a FREE git-commit auto-rebuild hook so the map stays current, and wires `/graphify` so the agent reaches for the graph first. The heavy semantic pass is on-demand (owner-triggered); the AST rebuild is free and automatic.
triggers:
  - "set up graphify"
  - "install the knowledge graph"
  - "map my workforce"
  - "graphify my workspace"
  - "build a knowledge graph of my company"
  - "knowledge graph"
  - "/graphify"
version: 1.0.4
---

# Skill 43: Graphify Knowledge Graph

## MANDATORY - Teach Yourself Protocol (TYP)

**Before using this skill, complete the Teach Yourself Protocol (Skill 01) on this folder.**

Required read order:
1. SKILL.md (this file) — what graphify is, the tier model (on-demand semantic vs free AST), the no-keys rule
2. INSTALL.md — one-time setup: install graphify, register the claw skill, map ONCE with the client's model, install the auto-rebuild hook, wire `/graphify`
3. INSTRUCTIONS.md — runtime guide: how the agent answers codebase/workforce questions via the graph
4. CORE_UPDATES.md — what gets appended to AGENTS.md + TOOLS.md + MEMORY.md
5. references/GRAPHIFY-COMMANDS.md — the exact CLI/skill command reference
6. CHANGELOG.md — version history

Per N3 ("read before act"), do not skip. Per N4, follow steps in declared order. Per N5, QC runs in a different sub-agent than the installer.

## Governing protocol (binding for this skill and all skills in the repo)

This skill is governed by ../QC-PROTOCOL.md (repo root) — the Sub-Agent Handoff and Mandatory QC Protocol. Every install runs the 10-category QC rubric (8.5 threshold) BEFORE declaring done. Sub-agents receive full instructions (never summaries).

## 🔴 NO CO-MINGLING (binding)

Graphify maps **THIS client's OWN** workspace and uses **THIS client's OWN** model (their Ollama / their configured model). It NEVER uses the operator's API keys, and the resulting `graphify-out/` graph belongs to this client alone — it is NEVER shared with, reused for, or seeded from another client's workspace. If the client's own model/Ollama is not yet available, **STOP and WAIT** — do not substitute the operator's keys or another client's model as a placeholder. See [`../NO-COMINGLING-RULE.md`](../NO-COMINGLING-RULE.md) and AGENTS.md N0. Co-mingling is a hard violation.

## What This Skill Is

**Skill 43 installs [graphify](https://github.com/safishamsi/graphify)** — a tool that reads a whole folder (code, docs, PDFs, images, audio/video) and builds a **knowledge graph**: a map where every important thing is a node and edges connect related things. The output lands in `graphify-out/` (`graph.html` clickable map, `GRAPH_REPORT.md` god-nodes + surprising connections + suggested questions, `graph.json` queryable).

Once installed and mapped, the client's agent reaches for the graph FIRST to answer questions like:
- "How is my workforce wired — what does the billing department send to sales?"
- "What depends on `department-naming-map.json`?"
- "Show the path from the AI Workforce Blueprint to the Command Center."
- "What are the most-connected (god-node) pieces of my company?"

This is the cheap, accurate alternative to grepping/spawning explore agents every time — build the map once, query it cheaply forever.

## The two tiers (READ THIS — it is the core design)

Graphify does two very different kinds of work, and Skill 43 treats them differently:

| Tier | What it does | When it runs | Cost | Who triggers |
|---|---|---|---|---|
| **AST structure pass** | Parses code structure LOCALLY via tree-sitter (classes, functions, imports, call-graphs). Deterministic. | **Automatically** on every git commit (the `graphify hook install` hook) | **FREE — no model call** | Automatic (hook) |
| **Semantic pass** | The model links concepts across docs/papers/images and writes the report. | **On demand only — owner-triggered** (`/graphify .` re-map) | Uses the **client's own model** (their Ollama → free + private) | Owner |

**Rule: the heavy semantic re-map is owner-triggered, NOT automatic.** We do NOT auto-run the semantic pass on a schedule or on every commit — that would burn the client's model time without their say-so. The free AST hook keeps the structural graph current between semantic re-maps.

## What gets mapped

By default, **the client's OWN workforce/workspace** — the `zero-human-company/<slug>/` tree (departments, role files, SOPs, personas) and/or the client's own code/docs folders. Mapped **once** at install with the client's own model. Re-mapped on demand when the owner wants a fresh semantic pass after big changes.

## The model rule (NON-NEGOTIABLE)

Graphify's semantic pass runs on the **CLIENT'S OWN model**:
- Preferred: the client's **genuinely-local Ollama** model (`--backend ollama`, `OLLAMA_BASE_URL=http://localhost:11434/v1` — the `/v1` suffix is **required**, or the OpenAI-style `POST /chat/completions` 404s and every map fails), using a model that runs ON the box with **no `:cloud` suffix** (e.g. `qwen2.5-coder:7b`, or whatever LOCAL model the client has pulled). Only a genuinely-local model is **free + nothing leaves the box**.
- ⚠️ **`:cloud` models are NOT local.** A `:cloud`-suffixed model (e.g. `deepseek-v4-pro:cloud`) runs on **Ollama Cloud servers off the box** and **bills the client's Ollama Cloud account** — it is neither free nor fully private. Use a `:cloud` model ONLY with the owner's **explicit opt-in**, and disclose the billing.
- Otherwise: whatever model the client already has configured.
- **NEVER** the operator's Anthropic/OpenAI/etc. keys, and **always pin `--backend ollama`** — a bare re-map lets graphify's `detect_backend()` auto-pick a resident key and can route the client's corpus to a paid/Anthropic backend. The operator does not pay for or route a client's graph build.

## What This Skill Ships

```
43-graphify-knowledge-graph/
├── SKILL.md                          # this file
├── INSTALL.md                        # one-time setup (7 steps)
├── INSTRUCTIONS.md                   # runtime: answering questions via the graph
├── CORE_UPDATES.md                   # AGENTS.md / TOOLS.md / MEMORY.md appends
├── CHANGELOG.md
├── skill-version.txt                 # tracks this skill's own version (see CHANGELOG.md)
├── qc-graphify-knowledge-graph.sh    # install QC (28-assertion)
├── scripts/
│   └── verify-graphify-install.sh    # lightweight structural/install check
└── references/
    └── GRAPHIFY-COMMANDS.md          # exact CLI + claw-skill command reference
```

## Relationship to other skills

- **Additive.** Skill 43 does not modify any other skill. It reads the workforce that Skill 23 builds and the Command Center that Skill 32 deploys; it does not change them.
- It pairs naturally with Skill 17 (Self-Improving Agent) and Skill 31 (Upgraded Memory) — the graph is a persistent, queryable "map" of the company that complements the memory stack.
- It is a SIBLING of the standalone skills (39/40/41/42): bolt-on, owner-facing, versioned independently via its own `skill-version.txt`.
