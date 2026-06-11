## [1.4.0] - 2026-06-10 — Skill 44 era: paste-step becomes fallback, dependency-first hard contract, 12-point checklist path-agnostic

### Why
Skill 44 ships an internal-API build path. Without these edits, skill 41's INSTRUCTIONS.md implied the paste step was always required and did not communicate the dependency-first contract to skill 44.

### Changes
- INSTRUCTIONS.md Step 5 gains a skill-44-era lead paragraph: when skill 44 is installed AND Firebase token is healthy, skill 44 builds directly; manual paste is the FALLBACK.
- INSTRUCTIONS.md Step 2 dependency-first contract documented as a HARD INPUT CONTRACT on skill 44: skill 44 will REFUSE to build if dependencies do not exist; GET-back verification + ZHC- standing approval bind skill 44's writes identically.
- INSTRUCTIONS.md Step 6 12-point checklist annotated as path-agnostic: skill 44 runs the same checklist after an internal-API build.
- Non-fabrication floor + GET-back + ZHC standing approval each gain a one-line cross-reference noting the rule extends to skill 44.

## [1.3.0] - 2026-06-03 - Executor stack + live L1-L5 browser-execution harness + version-marker reconciliation

### Added
- **Gap #4 -- MiniMax executor preflight** -- `scripts/05-configure-executor-model.sh`: detects
  Ollama Cloud and/or OpenRouter providers in `openclaw.json`, discovers the newest MiniMax M3
  model live (with fallback), and writes `agents.defaults.subagents.executorModel`
  (Ollama `ollama/minimax-m3:cloud` primary @ 512K ctx / OpenRouter `openrouter/minimax/minimax-m3`
  fallback @ 1M ctx). Removes stale `minimax-m2*` / `minimax-2.*` entries, sets `allowAgents:["*"]`,
  is platform-aware (Mac `$HOME/.openclaw` / VPS `/data/.openclaw` + `chown node:node`), idempotent,
  and validates with `openclaw config validate` (no silent corruption). `--dry-run` supported.
- **Gap #5 -- Agent Browser preflight** -- `scripts/06-verify-agent-browser.sh` +
  `protocols/agent-browser-preflight-protocol.md`: six hard-gate steps (Node>=18, npm, conditional
  platform-aware install, real headless Chrome CDP probe asserting `1+1==2`, encrypted auth-vault
  check, result record `skill-41-agent-browser-preflight.json`). Never fails silently -- every
  failure prints a loud banner + human-escalation directive. Exit 0 pass / 1 fail / 2 unsupported OS.
- **Gap #6 -- Live L1-L5 browser-execution harness** -- executable proof that build/browser
  execution works end-to-end, not docs-only. `scripts/12-run-browser-harness.sh` runs five levels
  (L1 auth/session fail-closed, L2 build-execution of the shipped `dependency-creation.sh`,
  L3 seeded-defect Big-Brother core, L4 safety/allowlist/headless-silent/PII-free logging,
  L5 forced-failure -> escalation), tallies results, computes the publish decision, and emits the
  f52 `qc_result` event (`--no-emit` in CI). Ships `scripts/test/lib-harness.sh`, the five `L*.sh`
  levels, seeded-defect fixtures (clean control + D1-D7 + INDEX), the L0 static gate
  `scripts/qc-browser-harness.sh` (auto-run by `11-run-qc-checklist.sh`'s `qc-*.sh` glob -> L0 goes
  6/6 -> 7/7), and negative self-tests for both the runner and the static gate. Safe: loopback mock
  GHL server only, no real credentials, no live external calls.
- **Gap #3 -- f52 `qc_result` event** -- `references/f52-data-contract.md`: added the `qc_result`
  event schema (counts + publish decision), PII-compliant (counts + boolean only).

### Changed
- **Gap #2 -- version-marker reconciliation** -- `CORE_UPDATES.md`: title + MEMORY.md / TOOLS.md
  block markers rolled `v1.2.1` -> `v1.3.0`.
- `SKILL.md`, `INSTALL.md`: install sequence extended 00--04 -> 00--06; new files added to the
  Files-in-This-Folder table and install order.
- `.github/workflows/qc-static.yml`: added a Skill 41 CI block (L0 checklist + browser-harness
  static gate & negative test + dynamic L1-L5 runner & negative test).

### Meta
- `skill-version.txt` bumped to `1.3.0`.
- Gap #1 (v1.2.2 injection hardening) confirmed present in main and preserved unchanged.

## [1.2.2] - 2026-06-01 - Hardening: injection safety, macOS compat, pagination, idempotency, prefix enforcement

### Fixed
- **Fix 1 (HIGH) Shell/JSON injection** -- `dependency-creation.sh`: all three `curl -d` bodies
  (tag, field, value) are now built with `jq -nc --arg` instead of direct shell interpolation.
  `lib-master-files.sh` `append_jsonl`: JSONL line is now assembled by `jq` from discrete
  `--arg` fields; callers pass a jq object expression + named `--arg` pairs, never a raw
  concatenated string.
- **Fix 2 (HIGH) `date +%s%N` macOS breakage** -- `lib-master-files.sh` `append_jsonl`:
  `session_ref` fallback now branches on `uname -s`; Darwin path uses
  `python3 -c 'import time;print(int(time.time()*1000)%1000000)'` with a `$RANDOM$RANDOM`
  fallback; Linux keeps `date +%s%N | tail -c 6`.
- **Fix 3 (HIGH) Pagination blind spot** -- `dependency-creation.sh`: all three existence-check
  GETs now loop incrementing `?page=N` until a page returns fewer than `limit` results before
  concluding the object does not exist. A single 100-item page no longer hides objects beyond it.
- **Fix 4 (MED) Stale idempotency marker** -- `scripts/04-update-core-files.sh`: MEMORY.md and
  TOOLS.md block markers are now built from `skill-version.txt` at runtime. On re-run with an
  older marker in the file, the stale block is removed and the current-version block is appended;
  if the current-version marker is already present the script skips (idempotent).
- **Fix 5 (MED) ZHC prefix not enforced at runtime** -- `dependency-creation.sh`: `create_tag`
  now rejects (exit 1) any name not starting with `ZHC-`; `create_field` rejects any name not
  starting with `ZHC_`. The logged `zhc_prefixed` field is now computed dynamically from the
  actual name instead of being hardcoded `true`. Custom values carry no prefix requirement and
  keep `zhc_prefixed:false` unchanged.

### Meta
- `skill-version.txt` bumped to `1.2.2`.
- `SKILL.md`: corrected "(00--05)" → "(00--04)" and version table cell `1.2.0` → `1.2.2`.

## [1.2.1] - 2026-06-01 - GHL accuracy pass (web-confirmed)

### Fixed
- If/Else reference: Select/Dropdown fields compared via Dynamic Values must use the stored option ID,
  not the display name (confirmed against the GHL If/Else help article).
- If/Else reference: noted Scenario Recipes ship about 10 prebuilt recipe types, and added the
  time-comparison operators (current day of week, day of month, month, year, hour).
- Trigger-filters protocol: corrected the removed-tag guidance to use the Contact Tag trigger with the
  Removed filter (the Contact Tag trigger fires on both add and remove), and added GHL's own
  no-filters warning as confirmation that an unfiltered trigger fires for everyone.

## [1.2.0] - 2026-05-31 - Trigger/action use cases, deep If/Else, trigger filters

### Added
- Every trigger and every action in the catalogs now carries a concise use case (Use when) so the
  agent knows what each one is for and when to reach for it. Triggers also list their own filters.
- references/ghl-conditions-reference.md rewritten as a deep If/Else treatment: Build My Own vs Scenario
  Recipe, Add Segment, AND/OR grouping, Add Branch, the auto-created None fallback branch, dynamic
  custom values and supported field types, the one-appointment-filter-per-condition rule, naming
  branches as questions, and concrete filtering use cases.
- protocols/trigger-filters-protocol.md: how trigger filters work and how to set them correctly per
  trigger type, Any of / None of tag operators, multiple-filter AND behavior, and re-fire guards. The
  build protocol and prompt template now require filters to be stated explicitly.
- references/platform-differences.md: Mac mini vs VPS Docker (paths handled by uname, the headless TTY
  consideration for 01-locate, and /data persistence).
- ADD-TO-REPO.md handoff file for the Cowork agent.
- qc-catalog-usecases.sh gate plus its negative test, enforcing the use cases and the If/Else and
  trigger-filter depth.

