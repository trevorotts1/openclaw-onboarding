# persona-categories.json — SHIPPED SEED (READ-ONLY)

This file is the **shipped seed** for the persona catalog.

**PRD 2.7 canonical write target:**
```
<workspace>/data/coaching-personas/persona-categories.json
```
- VPS:  `/data/.openclaw/workspace/data/coaching-personas/persona-categories.json`
- Mac:  `~/.openclaw/workspace/data/coaching-personas/persona-categories.json`

On first run of Skill 22 (`orchestrator.py` Phase 6), this seed is **copied** to the
canonical location if the canonical file does not yet exist. After that copy, all writes
go exclusively to the canonical path (resolved via `get_openclaw_paths()["persona_categories"]`).

**This file in the skill folder is never written by the orchestrator or selector.**
Update it only when shipping new default personas with the repo.
