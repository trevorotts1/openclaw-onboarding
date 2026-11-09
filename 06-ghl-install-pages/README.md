# 06 - GHL Install Pages (ghl-install-pages)

Installs GoHighLevel (Convert and Flow) funnel and website pages from approved
designs: page builds, form and survey wiring, order forms, and the click
through verification that proves a visitor can travel the whole funnel.

Current engine doctrine: v4.0 (operator decision 2026-10-13, repo release
v27.1.27). The OpenClaw Chrome extension is the PRIMARY browser engine,
agent-browser is the FALLBACK lane, Playwright is the escape hatch, the REST
ladder carries what the API officially carries, and CUA is the last resort.

## Start here

1. SKILL.md - the governing doctrine for this skill. Read it first.
2. INSTALL.md - the install procedure, in order.
3. INSTRUCTIONS.md and DAY-0-CARD.md - operator cards for a live run.
4. ghl-browser-builder-full.md - the browser build procedure per lane.
5. QC.md - the quality gates a build must pass before it ships.

## Engine lanes

- Lane 1 (PRIMARY): OpenClaw Chrome extension, driving the operator's real,
  signed-in Chrome. Default for funnel page builds, step bindings, forms,
  pop-ups, click actions, and order-form wiring.
- Lane 2 (FALLBACK): agent-browser, gateway-only pooled singleton. Carries a
  run when the extension channel is unavailable. Same snapshot discipline,
  same teardown rules.
- Lane 2b: hybrid iframe work (extension drives the GHL shell, CDP assist
  inside cross-origin iframes). See TECHNIQUES-cross-origin-iframe-dragdrop.md.
- Lane 3: Playwright escape hatch, used only when neither browser lane can
  carry the job.
- Lane 4: REST ladder (caf CLI, official MCP, direct REST) for the objects the
  public API officially carries: products, redirects, custom values, tags.
- Lane 5: CUA, last resort only.

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
