# 06 - GHL Install Pages (ghl-install-pages)

> **Payment invariant across all routes:** every checkout, order bump, purchase
> action, one-click upsell, and downsell must use the native GoHighLevel payment
> component. HTML/CSS/embeds/iframes may surround it but cannot replace it. This
> applies equally to every fallback engine. No purchase or payment success is
> claimed without a separately verified transaction receipt.
>
> **Exact layout targeting:** GHL supports 1–6 columns. `pages.layout` accepts
> `layout={section_id, columns: 1..6}`. After capturing IDs, code/checkout placement
> targets `{section_id,row_id,column_id[,expected_columns]}` or
> `{section_id,row_id,column_index,expected_columns}` (zero-based). Existing section
> widths stay intact unless `width_policy="full"` is explicitly requested.
> The native-payment rule is an execution requirement; policy text, heuristic input
> checks, and DOM preservation do not guarantee detection of every nonnative markup.

Installs GoHighLevel (Convert and Flow) funnel and website pages from approved
designs: page builds, form and survey wiring, order forms, and the click
through verification that proves a visitor can travel the whole funnel.

Current engine doctrine (operator decision 2026-11-08): proven API/official
MCP/Skill 44 first; reusable Playwright recipes first for captured UI work;
then the current OpenClaw Chrome extension, managed Agent Browser and enabled
computer use. The new [recipe guide](references/PLAYWRIGHT-RECIPES.md) lists
all entry points, commands and remaining live verification work.

## Current build checkpoint : November 12, 2026 UTC

**v27.1.111: prepared source release.** The source catalog has 39 implemented recipes: 11 `LIVE_PATH`, 7 `PROFILE`, 17 `CAPTURED`, and 4 `API_FIRST`. These are source catalog classifications, not counts of end-to-end live acceptance. The compiler boundary asserts 76 covered actions / 104 bounded rows. Root's focused verification run passed 91 tests; the latest standalone page_embed suite passed 9 tests after the async initialization and aspect-ratio fixes. These are separate runs; required CI is next. Live capture created/reused a native Saved Template and moved it after an exact anchor; save/reload retained tablet 85% and desktop 100% on one row. Checkout field order, the custom Accent color `#3155AA`, and native component ID/parent binding were inspected. Six native V2 preset buttons were captured but not selected or saved. Funnel and website folders were independently reopened; the child Website 1 Page reopened under its same created ID. Live iframe preview, full buyer journey, and native payment acceptance remain pending. Nested layout containers and native mobile row-width editing are unavailable in this tenant; mobile columns stack natively. No purchase proof is claimed.

**Previous checkpoint v27.1.110: 34 source-built recorded operation contracts.** Its compiler covered 73 concrete actions / 102 bounded jobs; two focused front-door/compiler checks passed. Native layout save/reopen and payment behavior remained unverified. The v27.1.109 historical checkpoint is retained below.

**v27.1.109: 33 source-built recorded operation contracts / 0 source partials.**
All original ten partial areas now have integrated executable source within their recorded boundaries. Compiler coverage is **72 concrete actions / 101 bounded jobs**. The final merged source smoke passed **45 focused tests**.

The generated `ghl-install-pages.skill` archive contains the six canonical source documents with Skill metadata v27.1.111. Delivery status is tracked in Git merge history.

The **v27.1.109** source candidate was marked OWNER_APPROVED_PREPARED_RELEASE, with approval to publish and batch merge that build on November 11, 2026. Its delivery status is recorded in Git merge history. The documented verified preparation baseline remains v27.1.108 through batch PR3125.

Final maintained-script, respondent, member and notification acceptance remains **NOT_RUN / PENDING**. OAuth requires external user authorization. See the [progress ledger](references/PLAYWRIGHT-PROGRESS.md) and [machine-readable ledger](references/PLAYWRIGHT-BUILD-STATUS.json) for exact contracts and limits.

## Start here

1. SKILL.md - the governing doctrine for this skill. Read it first.
2. INSTALL.md - the install procedure, in order.
3. INSTRUCTIONS.md and DAY-0-CARD.md - operator cards for a live run.
4. ghl-browser-builder-full.md - the browser build procedure per lane.
5. QC.md - the quality gates a build must pass before it ships.

## Engine lanes

- Lane 1: verified API/official MCP/Skill 44 operations with current tenant,
  version and scope receipts, including documented Courses v3 operations.
- Lane 2: ready Playwright recipes in the existing managed authenticated
  session. Profiles without captured controls are not eligible yet.
- Lane 3: the current OpenClaw Chrome extension for new controls and recovery.
- Lane 4: managed Agent Browser, with the existing CDP hybrid when needed.
- Lane 5: enabled computer use as the last resort.

The older procedure cards retain historical lane numbers. This ordering and
SKILL.md govern new runs. Editor completion is not full-funnel QC PASS.

Fail closed: if no lane verifies, the run stops and reports. It never
improvises a path.
## Maintenance crons (scheduled, every box)

Four maintenance-window jobs keep this skill honest between builds. The ONE
entry point is the aggregate installer; update-skills.sh runs it, so a box
registers all four on its next update:

    bash scripts/install-skill6-maintenance-crons.sh [--idempotent] [--check-only]

It names all four installers explicitly (the old first-match glob ran only
the archive-reconcile one), consumes `--idempotent` without forwarding it,
and reports REGISTERED / ABSENT / UNKNOWN per job from
`openclaw cron list --all --json`. The four jobs:

- `install-github-archive-reconcile-cron.sh` - nightly sweep that proves
  every Vercel page's source is archived to GitHub, and re-runs missing
  archives (`--retry`).
- `install-page-inventory-lifecycle-cron.sh` - retention sweep over
  generated page evidence (compress-only, zero live GHL calls), one operator
  card per unresolved candidate set.
- `install-routing-drift-check-cron.sh` - routing drift check.
- `install-selector-drift-probe-cron.sh` - selector drift probe
  (`run-selector-drift-probe.sh`).

`scripts/lib-cron-presence.sh` is the shared helper the installers source:
presence is judged on `--all` listings, a disabled job is a TOMBSTONE
(reported, never re-enabled or duplicated), new jobs get `--no-deliver` (a
maintenance tick must never announce into client chat), and an existing job
that announces is repaired in place. A failed or unparsable listing is
UNKNOWN, never "absent".

The reaper backstop is checked, never registered, here:

    bash scripts/check-agent-browser-reaper-schedule.sh

Exit 0 = registered AND enabled; 1 = absent; 2 = UNKNOWN; 3 = registered but
DISABLED (loud failure - a reaper that never runs is the false-done pattern).
Reactivation is an operator decision.
## Extension preflight (standing, every run)

Before an install run, verify the extension is installed and current:

    bash scripts/check-openclaw-extension-version.sh

Exit 0 means installed and current. Exit 2 means missing or behind; the
script prints the Chrome Web Store path. The capability probe
(tools/capability_probe.py) enforces the same check when it selects lanes:
the OpenClaw lane is eligible only when the extension is present and current.

## Auth

Token-only, always: Private Integration Token plus location ID, with the
recorded three-tier ladder for workflow writes. Browser lanes never type a
password; a login form appearing in a snapshot is a failure detector, not a
form to fill. See SKILL.md (decision D7) for the full rule.

## Layout of this folder

- tools/ - builders, the capability probe, and lane adapters.
- scripts/ - the extension preflight, the maintenance-cron installers
  (lib-cron-presence.sh, the four install-* installers, the aggregate
  install-skill6-maintenance-crons.sh), the reaper-schedule and
  extension-version checks, and local helpers.
- references/ - capability notes, including iframe drag capability.
- tests/ - the probe, doctrine and maintenance-schedule test suites.
- PREREQS.json - declared prerequisites, including the extension
  (tool-openclaw-chrome-extension) and both browser runtimes.
- ENV-MATRIX.md - which capabilities each environment shape carries.
- CORE_UPDATES.md and CHANGELOG.md - what changed, and when.

## Version

Skill version: see skill-version.txt. Repo release: see the repo root
/version and CHANGELOG.md. The compiled ghl-install-pages.skill package is
generated from these canonical documents; do not hand-edit it.
