# 06 - GHL Install Pages (ghl-install-pages)

Installs GoHighLevel (Convert and Flow) funnel and website pages from approved
designs: page builds, form and survey wiring, order forms, and the click
through verification that proves a visitor can travel the whole funnel.

Current engine doctrine (operator decision 2026-11-08): proven API/official
MCP/Skill 44 first; reusable Playwright recipes first for captured UI work;
then the current OpenClaw Chrome extension, managed Agent Browser and enabled
computer use. The new [recipe guide](references/PLAYWRIGHT-RECIPES.md) lists
all entry points, commands and remaining live verification work.

## Current build checkpoint - November 10, 2026

Actual v27.1.107 delivery is verified through
[batch #3123](https://github.com/trevorotts1/openclaw-onboarding/pull/3123),
merge `f859b9c72eedacf020686598247e51741a4eb625`, delivering member #3122 at
`b48d02e0f27cffe7dabd38576258a3c790231647`. The full Skill 6 subtree matches that
frozen member. The previous v106 unit was delivered through batch #3121.

This v27.1.108 unit adds one captured survey completion family: caller-approved
plain Message or HTTPS Redirect to URL through the existing executor. Exact
survey identity, conditional precedence, saved reopen and fresh completed replay
are bound; replay never repeats the write. The final source review is CONFIRMED.

Current source coverage is **54 completed behavior records: 53 delivered on
verified main and one in this prepared unit**, or **53/54 = 98.1%** delivered
for these records. The compiler covers **69 dynamic actions / 97 bounded jobs**.
Broad source coverage remains **23 BUILT / 10 PARTIAL / 0 GENERIC_ONLY**
across 33 operations (**69.7%** by equal-weight operation count). No broad row
was promoted. Compound predicates, conditional rich-message/disqualification
outcomes and other rule lifecycle remain explicit gaps.

Retained checks: four new tests PASS (0.068s), ten prior form regressions PASS,
two compiler/provider tests PASS (1.166s), and the one affected freshness replay
check PASS (0.032s). After the executor outage, all seven reviewed source files
were recovered from committed patches and independently matched by Git blob
hash. No source checks or reviews were repeated during release preparation.
Both modes were manually saved/reopened; final native maintained-script and
respondent acceptance is **NOT_RUN**. Source and delivery are separate from
that acceptance. See the [progress ledger](references/PLAYWRIGHT-PROGRESS.md)
and [machine-readable ledger](references/PLAYWRIGHT-BUILD-STATUS.json).

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
