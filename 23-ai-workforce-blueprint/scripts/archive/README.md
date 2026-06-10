# archived scripts

This directory contains deprecated scripts that have been superseded by the
canonical implementation.  Do NOT use these scripts for any new work.

## select-persona-for-task.py (v1)

**Canonical replacement:** `../persona-selector-v2.py`

`select-persona-for-task.py` was the v1 persona selector.  As of PRD item 1.1
(Wave 1, 2026-06-09), `persona-selector-v2.py` is declared the ONE canonical
selector:

- AGENTS.md rule N16 already pointed at v2.
- The Command Center (`src/lib/persona-selector.ts`) already calls v2.
- v2 now includes the two things v1 had that v2 lacked: semantic candidate
  retrieval via `gemini-search.py`, and the `DEPT_DOMAIN_TAGS` keyword filter.

The body of `select-persona-for-task.py` in this folder has been replaced with
a thin shim that delegates to v2 and emits a deprecation warning on stderr.
Any callers still pointed at the old path will continue to work but will see:

```
[select-persona-for-task v1] DEPRECATED: this entry point is a shim.
Use persona-selector-v2.py directly.
```

**Action required for operators:** update any local scripts, cron entries, or
AGENTS.md blocks that still reference `select-persona-for-task.py` to reference
`persona-selector-v2.py` instead.  The shim will be removed in a future release.
