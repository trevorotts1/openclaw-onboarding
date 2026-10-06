---
name: kie-live-adapter
description: >
  Live KIE.ai adapter. One Python 3 standard-library tool that reads KIE's live
  model catalog and per-model schema, validates a payload against that schema,
  uploads input files, submits a job to the path the schema declares, polls to a
  result, saves the files before the links expire, and reads the credit balance.
  Ships in shadow mode by default: it observes and records drift but never
  dispatches a paid job. It never chooses or changes a model. Infrastructure
  skill for skills 66, 67 and 68; not a client-facing feature.
version: 1.0.0
priority: MEDIUM
---

# KIE Live Adapter (Skill 74)

KIE changes its model list and request shapes without notice. Skills 66, 67 and 68 hold static tables. This skill gives them a live way to check those tables, and a tested way to run a job when an operator turns dispatch on.

## What it is

`scripts/kie_live_adapter.py`, one entrypoint, Python 3 standard library only. Backend name: `native-live`. It is our own code that follows the contract in KIE's official `kie-models` instructions. KIE's published agent skills are instruction text only (no scripts), so there is nothing to install from them, and they are never a runtime dependency.

Commands (all print the same JSON shape, add `--json`): `health`, `discover`, `schema`, `validate`, `upload`, `submit`, `wait`, `run`, `credits`, `save`.

## Modes

Set `KIE_LIVE_ADAPTER_MODE` to `off`, `shadow` or `active`. If the variable is unset the adapter reads the first word of `$OC_CONFIG/kie-live-adapter-mode.conf` (default `~/.openclaw`), the same one-word store style as `decision-engine-mode.conf`. If neither is set the mode is `shadow`.

| Mode | What happens |
|---|---|
| off | Diagnostics (health, discover, schema, validate) work. submit and run return `skipped` with "adapter off: use static path". |
| shadow (default) | Diagnostics run and write drift receipts. submit and run refuse paid dispatch: `skipped`, `fallback_used: true`, "shadow: dispatch via existing static path". No duplicate generation, no double charge. |
| active | Full mechanics: validate, createTask, poll, download. |

## Hard rules

1. The adapter never picks a different model, never routes to a newly discovered model, and never overrides a pinned model. The caller decides the model and the fallback. The fleet image pin in AGENTS.md (sunburst) stays in force.
2. Never print or log the key. Receipts and errors are redacted. Presence checks print SET or NOT-SET only.
3. One attempt on a 401 or 403, no retry. The adapter stops and reports.
4. Check the `code` in the response body. HTTP 200 can carry 401, 402, 404, 422, 429, 433 or 455.
5. createTask is never retried after a network error (that could charge twice).
6. Never copy `scripts/kie_live_adapter.py` into a Presentations deck run directory. The deck render guard blocks scripts there that mention the KIE API. Run it from this skill folder only.
7. Nothing writes inside the skill folder at run time. The cache and receipts live in `~/.openclaw/cache/kie-live-adapter`.

See INSTRUCTIONS.md for usage and references/ for the contract, trust policy, research receipt and decision log.
