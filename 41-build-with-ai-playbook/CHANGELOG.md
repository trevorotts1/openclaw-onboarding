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

