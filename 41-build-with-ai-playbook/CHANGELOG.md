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

