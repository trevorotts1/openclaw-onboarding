## [v10.5.1] — 2026-05-17 — Wave 4: Hand-Touch Integration

### Changed

- **`scripts/build-workforce.py`** — Inline v10.5.1 hook at the end of `build_from_config()`. After all departments and persona matrix are created, spawns `post-build-role-workspaces.py` via subprocess (30s timeout) to augment every role folder with v2.1 files. Wrapped in try/except so failure doesn't break the main build.
- **`scripts/post-build-role-workspaces.py`** — Reworked to AUGMENT existing role folders rather than create duplicates. Detects pre-v2.1 role folders (any naming pattern, with or without numeric prefix) and adds IDENTITY.md, SOUL.md, MEMORY.md, HEARTBEAT.md, how-to.md stub, and AGENTS/TOOLS/USER symlinks in place. Master Orchestrator (CEO) created at company root with CEO deferral clause if missing. Pre-v2.1 files like `00-START-HERE.md` are preserved.

### Version

`skill-version.txt` bumped to `10.5.1`.

### What's no longer a hand-touch (RUNBOOK Section 5)

- ✅ `build-workforce.py` post-build call — now automatic
- ✅ `install.sh` shared-utils copy — fixed in install.sh
- ✅ Command Center `src/lib/persona-selector.ts` — created and points at `persona-selector-v2.py`

---

## [v10.5.0] — 2026-05-17 — Wave 3: v2.1 Integration Layer

### Added — scripts/

- **`post-build-role-workspaces.py`** — Post-hoc role-level workspace creator. Walks `[ZHC]/[company]/departments/` and creates role folders for every department missing them. Reads from `suggested-roles/[dept]-suggested-roles.md` to determine role list. Includes Master Orchestrator (CEO) creation at company root with CEO deferral clause variant. Idempotent.
- **`persona-selector-v2.py`** — v2.1-aware drop-in alternative to `select-persona-for-task.py`. Adds stickiness check, adaptive weights, behavioral profile reading, hybrid mode, weight override application.
- **`gemini-section-indexer.py`** — Section-level indexer. 14 vectors per persona (one per `##` section) instead of 80+ character chunks. Real Gemini embeddings when `GOOGLE_API_KEY` set; deterministic fallback otherwise.
- **`run-v2.1-migrations.sh`** — Orchestrates: platform detect → migrate deferral clauses → re-index Gemini at section level → create role workspaces. One command.
- **`verify-v2.1-installation.sh`** — End-to-end smoke test. 36 checks across file existence, Python syntax, bash syntax, and runtime execution.

### Added — root

- **`RUNBOOK-v2.1.md`** (in skill root) — Operator runbook covering upgrade flow, day-to-day scripts, persona stickiness walkthrough, hand-touch integration list, cron recommendations, troubleshooting, rollback.

### Version

`skill-version.txt` bumped to `10.5.0`.

---

## [v10.4.1] — 2026-05-17 — Wave 2 Execution

### Added

- `scripts/infer-task-category.py` — Classifies a task description into one of 14 task categories. Used by persona stickiness (v2.0 Ch 13) and adaptive weights (v2.0 Ch 17).
- `scripts/create-role-workspaces.py` — Creates role-level workspaces inside a department. Each role gets its own folder with unique IDENTITY/SOUL/MEMORY/HEARTBEAT/how-to.md files plus symlinks to the company-root AGENTS/TOOLS/USER.md. Master Orchestrator role uses the CEO variant of the Persona Governance Override clause.

### Moved

These previously-mandatory suggested-roles files moved to `suggested-roles/_deprecated/`:
- `creative-suggested-roles.md` (folded into Graphics + Video + Audio)
- `hr-people-suggested-roles.md` (no longer mandatory)
- `it-tech-suggested-roles.md` (replaced by OpenClaw Maintenance)
- `operations-suggested-roles.md` (distributed across departments)

Preserved for Audit/Resume mode (Option C) backward compatibility.

### Version

`skill-version.txt` bumped to `10.4.1`.

---

## [v10.4.0] — 2026-05-17 — Zero-Human Company Spec (PRD v2.1)

### Added
- `INSTRUCTIONS.md` rewritten for v2.1 — 30-question interview, 16 mandatory departments, 3 vertical packs
- `department-naming-map.json` reorganized into mandatory / vertical_packs / deprecated tiers
- `templates/universal-how-to-template.md` — 18-section template every role document follows
- `prompts/role-doc-generation-prompt.md` — sub-agent generation prompt with research protocol
- `suggested-roles/crm-suggested-roles.md` — CRM department roles including Email Deliverability flagship
- `suggested-roles/openclaw-maintenance-suggested-roles.md` — OpenClaw Maintenance department with recursive-modification guard
- `suggested-roles/social-media-suggested-roles.md` — Social Media organic department with 10 platform specialists
- `suggested-roles/paid-advertisement-suggested-roles.md` — Paid Advertisement department with 12 platform-specific ad specialists
- Persona Governance Override clause baked into INSTRUCTIONS.md (standard + CEO variant)

### Changed
- Interview density: ~50-65 questions → ~28-30 questions
- All assisting language preserved from v9.6.0: "I Don't Know" 6-step flow, hesitation detection, plain-English progress, pause/resume, specialist auto-staffing

### skill-version.txt
Bumped to `10.4.0`

---

## [v1.5.0] - March 7, 2026

### Changed
- Converted INSTALL.md to agent-executable, autonomous execution format.
- Ensured TYP guardrails are present: MANDATORY TYP CHECK, CONFLICT RULE, and TYP file storage instructions.
- Replaced "say to your AI" instructions with a real multi-phase autonomous execution flow.
