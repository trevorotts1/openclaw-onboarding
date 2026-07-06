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

## Schema 1.2 — the optional `needs_retag` marker (F1.4 / DEP-12)

A persona entry MAY carry an additive optional field:

```json
"needs_retag": true
```

It is stamped by `orchestrator.py` Phase-6 **auto-repair** when normal
auto-classification / the categories write fails: rather than skip the entry
(which would leave the blueprint invisible to `persona-selector-v2.py`'s
`list_available_personas()` universe), the persona is registered with a
SAFE-DEFAULT `domain: ["leadership"]` and flagged `needs_retag: true` so the
persona stays selectable (never-to-zero) while signalling that an operator/tool
must re-classify its tags. The same run also exits non-zero
(`PHASE6_CATEGORIES_EXIT_CODE = 9`) so the failure is never a silent success.

`needs_retag` is a **workspace-only** field — `pipeline/persona_fleet.py
sync-categories` ships only the canonical seed fields
(`author`/`book`/`domain`/`perspective`/`custom`), so the marker never leaks
into this shipped seed.
