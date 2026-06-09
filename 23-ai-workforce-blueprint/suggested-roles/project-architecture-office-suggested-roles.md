# Project Architecture Office — Suggested Roles

**Department:** Project Architecture Office (PAO)
**Slug:** `project-architecture-office`
**Short aliases:** `pao`, `prd`, `prd-creator`
**Purpose:** Governs every project from trigger to verifiable completion. Creates PRD folders, writes binary-verifiable success criteria, runs bounded execution loops (max 12 iterations, 72h deadline), spawns and kills specialist sub-agents, commits only ≥8.5 QC-passed work, and hands off completed projects to building departments.

---

## Mandatory Roles (every PAO department)

| # | Slug | Title | Type | Purpose |
|---|------|-------|------|---------|
| 0 | `chief-project-architect` | Chief Project Architect | leadership | Main orchestrator — creates PRD folders, runs loops, spawns/kills subs, owns ledger, handoff |
| 1 | `research-agent` | Research Agent | deep-research | Gathers requirements, prior art, API/stack docs for PRD.md; verifies all claims via Context7/WebFetch |
| 2 | `code-monitor` | Code Monitor | specialist | Watches CI/builds/tests, reports failures; NEVER edits; short-lived |
| 3 | `code-editor` | Code Editor | specialist | Implements work items; elevated reasoning; produces commits (gated ≥8.5); short-lived |
| 4 | `qc-agent` | QC Agent | qc | Scores every deliverable against QC.md; DIFFERENT model from writer (Rule 6); ≥8.5 gate |
| 5 | `sop-writer` | SOP Writer | on-call | Universal SOP-Writer — codifies reusable project patterns discovered during loops |

---

## PRD Folder Template

`templates/prd-folder/` ships in the role library. Chief Project Architect instantiates per-project at `<OPENCLAW_WORKSPACE>/projects/<project-slug>/`:

| File | Purpose |
|------|---------|
| `PRD.md` | Requirements: problem, goals, scope, non-goals, success metrics, milestones, stack, constraints |
| `checklist.md` | Binary acceptance checklist derived from PRD goals — each item is verifiable |
| `CHANGELOG.md` | Append-only log of every project decision/commit/handoff |
| `todo.md` | Live work queue: open → in-progress → done, with owner role + QC score + commit SHA |
| `QC.md` | Project-specific rubrics (code, copy, design, infra) + weighting + ≥8.5 gate |
| `loop-state.json` | Machine state: loop count, max_loops (12), deadline_iso (now+72h), gate (8.5), status, cron_id |

---

## Loop Engineering Bounds (mandatory)

- `max_loops: 12` — exceeded → stop, notify owner
- `deadline_iso: now+72h` — exceeded → stop, notify owner
- **pao-reaper** (daily 04:00 cron) — scans all `loop-state.json` files, kills crons for terminal/stale projects
- Max 3 defect-loop rounds per work item before flagging to owner
- Commit gate: ≥8.5 QC score required; sub-8.5 work NEVER reaches a commit

---

## Model Selection Policy

| Tier | Models | When |
|------|--------|------|
| 1 (default) | `ollama/deepseek-v4-pro:cloud` (orchestrator/QC/code-editor), `ollama/deepseek-v4-flash:cloud` (research/monitor), `ollama/kimi-k2.6:cloud` (long-context QC) | Always first |
| 2 (failover) | `openrouter/deepseek/deepseek-v3.2`, `openrouter/moonshotai/kimi-k2.6`, `openrouter/z-ai/glm-5`, `openrouter/qwen/qwen3.5-plus-02-15` | Ollama Cloud down/over-capacity |
| 3 (last resort) | Per-token frontier models | ONLY with owner approval |

---

## Role Library Status

All 6 roles are included in `templates/role-library/project-architecture-office/`. Added in v11.1.0.

---

## Routing

- **Routing priority:** `7`
- **Keywords:** `prd`, `project requirements`, `spec`, `scope`, `milestone`, `project plan`, `architecture`, `build plan`, `requirements doc`, `project architecture`
- **CC canonical slug:** `project-architecture-office` (aliases: `pao`, `prd`, `prd-creator`)
