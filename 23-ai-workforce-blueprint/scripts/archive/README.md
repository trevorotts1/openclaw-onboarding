# Archive: Deprecated Scripts

## select-persona-for-task.py (v1)

**Deprecated as of v11.4.0 (PRD item 1.1).**

`select-persona-for-task.py` was the original persona selector (v1, v9.6.x).
It has been superseded by `../persona-selector-v2.py`, which is THE canonical
selector for all new work.

### Why it was deprecated

- v2 is the script the Command Center and AGENTS.md rule N16 call.
- v1 used flat-constant scoring for Layers 1-4; v2 uses LLM-backed scoring
  (DeepSeek V4 Pro via Ollama Cloud, OpenRouter fallback).
- v2 adds stickiness, adaptive weights, behavioral profile reading, hybrid mode,
  and anti-repetition variety logic.
- Both selectors now share the same pre-scoring funnel (governing-personas pool,
  DEPT_DOMAIN_TAGS keyword filter, gemini-search semantic retrieval), ported
  from v1 into v2 in this same release.

### Migration

Replace any call to `select-persona-for-task.py` with the equivalent v2 call:

```bash
# Old (v1 — DEPRECATED):
python3 select-persona-for-task.py --dept marketing --task "Write a launch email" --format json

# New (v2 — CANONICAL):
python3 persona-selector-v2.py --department marketing --task "Write a launch email" --format json
```

The shim at `../select-persona-for-task.py` still accepts the old `--dept` flag
and delegates to v2, printing a deprecation warning to stderr. It will be
removed one release after fleet-wide migration to v2.

### What the shim does

The shim (at `../select-persona-for-task.py`) translates `--dept` to
`--department` and delegates to v2 via `subprocess.run([sys.executable, v2_path,
...])`. It prints a deprecation warning to stderr on every call so stale callers
are visible in logs.

### Archive contents

- `select-persona-for-task.py` — original v1 implementation (reference only,
  never call directly). The shim at the parent level is the only supported path.
