# Swarm plan: the runner's operating specification

This document specifies how a Skill 71 run fans work out to worker sessions
and fans it back in. The implementation is `scripts/swarm_runner.py`; the
item-level gate commands it drives are specified in
`references/item-gate-spec.md` (Item 20); runner profiles live in
`references/runner-profiles.json`; per-item briefs are rendered from
`references/swarm-briefs/`; spawn contracts per runtime live in
`references/runtime-adapters.md` and the adapter READMEs.

This plan supersedes the old prose swarm table. Where the old text and the
stage contract disagreed, the item-level flow wins: the old plan promised
that generation begins per image as its prompt passes, while the stage gate
only moved whole stages. Item 20 cut that weld at the gate, and this
specification is written on the item-level side of it.

## Principles

- **Items, not stages, are the unit of work.** A stage is a fan-in point.
  An image's generation starts when ITS prompt item closes, not when the
  prompt stage closes.
- **The gate is the only record of done.** Workers write artifacts and
  notes. Items and stages close only through `scripts/stage_gate.py`
  (`close-item`, `close`), from observed results: validator exit codes,
  files on disk, review files stamped by `write_review.py` from the
  reviewing worker's own session, and Skill 74 receipts. Worker self-report
  is never a receipt.
- **One automated recovery lane per item, then a named block, never a
  silent stall.** Every failure is classified before any retry is spent,
  the retry runs in that class's lane, and an item that fails its retry is
  blocked through the gate with the reason named, where fan-in reports it
  by name while every other item continues.
- **Capability gaps degrade honestly.** An item whose required capability
  the active profile cannot supply waits, and the runner declares the
  sequential fallback in the run record rather than failing the item or
  pretending the run was a swarm.

## Per-stage item table

| Stage | Items | Ordering and concurrency |
| --- | --- | --- |
| intake | 1 item: intake assembly from the client's answers | Single item; the run's source of truth is never parallel-edited |
| copy | 1 writer item, then 1 reviewer item | Strictly ordered; the reviewer is a different session |
| font-action-plan | 1 item | Single |
| desktop-wireframe | 1 layout-lead item producing `section-plan.json`, then per-part renderer items, then 1 reviewer item | Parts render in parallel once the plan lands; the reviewer waits for all parts |
| mobile-tablet | Same pattern as desktop-wireframe | Parts in parallel after its section plan |
| visual-mockup | 1 bible item (`page-visual-bible`), then desktop and mobile renderer items | Renderers in parallel after the bible; prompt items unlock per Item 20 as soon as the bible artifact lands, without waiting for the stage to close |
| image-inventory-prompts | One pipeline per image: author item, then review item | All images concurrent within profile limits; validate runs between author and review |
| image-generation-qc | One pipeline per image: generation item, deterministic screen, review item | Starts per image the moment its prompt item closes; generation starts are limiter-bound (below) |
| image-map-upload | 1 item | Single |
| design-board | 1 item: the page's board from its real images, then 1 reviewer item; the client approval is recorded after review | Single per page, after `image-map-upload`; `final-mockups` does not start before the approval is recorded |
| final-mockups | Desktop item and mobile item | In parallel |
| responsive-html | 1 builder item, then validator, drift, and reviewer items | The three check items run in parallel after the builder |
| ghl-install-test | 1 item | Single; Item 5's evidence rules govern what counts as proof |
| publish-verify | 1 item | Single; Item 5's evidence rules govern |
| automation-wiring | 1 item, then 1 reviewer item | Single; conditional stage (Item 31): it runs only when the intake records `publish_target: "ghl"` and `automation_scope: "workflows"`; when it does not apply, the gate records the stage `not_applicable` in state and REPORT.md, citing the intake values |
| report | No agents | The gate writes REPORT.md; the runner only records the outcome |

Implementation note, stated plainly: the runner's DAG itemizes the two
per-file stages (`image-inventory-prompts`, `image-generation-qc`) at item
level today, because those are the stages the contract enumerates per file.
For the wireframe-family stages, the lead, renderer, and reviewer sequence
runs as ordered briefs inside the stage's work and review nodes; the
per-part split becomes separate DAG nodes when the stage contract
enumerates parts as items. The ordering rules in the table are the contract
either way.

## Reviewer assignment

Review items are assigned by the review's criteria class, and the
assignment (class, brief template, reviewer session id) is recorded per
item in `private/runner-state.json`:

| Criteria class | Stages | Brief |
| --- | --- | --- |
| image-fidelity | image-inventory-prompts, image-generation-qc | `prompt-reviewer.md`, `image-reviewer.md` |
| copy | copy | `generic-reviewer.md` with the copy spec and the emotional-quality chapter in its reads |
| layout | desktop-wireframe, mobile-tablet, visual-mockup, final-mockups, responsive-html | `generic-reviewer.md` with the layout vocabulary in its reads |
| generic | everything else | `generic-reviewer.md` |

Reviewer concurrency is the profile's `reviewers` value. A reviewer session
must differ from the item's author session; the gate enforces it, and a
review that cannot prove independence does not count.

## The limiter rule

KIE createTask starts are budgeted at **20 starts per 10 seconds per KIE
account**. The budget is a token bucket with persisted state, shared by
every runner on the box through a lockfile-guarded state file (path from
the runner profile; on fleet-contabo, a deployment whose containers share
one KIE account points the path at storage shared by those containers, so
the budget holds per account, not per container). Generation items take a
token before their worker starts. **Retries take tokens too**: a retry is a
start like any other. The runner never calls KIE itself; Skill 74 is the
only transport.

## Timeouts

| Work | Timeout |
| --- | --- |
| Prompt write | 15 minutes |
| Prompt review | 10 minutes |
| Image review | 10 minutes |
| Wireframe part render | 20 minutes (multiplied by 1.5 on fleet-contabo) |
| Any other work item | 15 minutes |
| Any other review item | 10 minutes |
| Generation | Bounded by Skill 74's own wait; overridable per run |

## The retry rule: failure-class lanes

Each item gets exactly **one** automatic retry. The failure class is
decided before the retry is spent, and is recorded per attempt in
`private/runner-state.json`:

- **Validation** (validators fail, the worker exits 3 or another nonzero,
  or a review returns the item): the item returns to the author lane. The
  retry brief carries the validator output verbatim, or the reviewer's
  named defects. Guessing at the failure is not a lane.
- **Transport** (worker exit 2): the runner reads the item's Skill 74
  receipts BEFORE anything is resubmitted. A `success` receipt with the
  image on disk completes the item from observed outputs, with no
  resubmission and no retry spent. A submitted or pending task means the
  retry is a **poll** of that task id, using the generation-poll brief; a
  createTask is never blindly resubmitted. Only when no receipt exists may
  the retry dispatch fresh.
- **Timeout**: if partial outputs exist and pass the validators, the item
  completes and the retry is unspent. Otherwise the item retries once in
  the retry lane.

After the retry fails, the item is blocked via the gate's `block-item`
with a named reason, and the runner records a named escalation per class
(validation lane exhausted, transport lane exhausted, timeout lane
exhausted). Blocked items do not stop the run; fan-in surfaces them.

## Fan-in policy

- A stage closes only when **every** item in its universe is closed at
  item level; the gate's stage `close` verifies this first (Item 20).
- Blocked items fail the stage close **by name**, with their recorded
  reasons. The runner's run summary likewise names every blocked item; a
  run with blocked items exits nonzero and unclosed stages are listed.
- The prompt manifest (`prompt-manifest.json`) is runner-maintained:
  after each prompt item closes, the runner rewrites it deterministically
  from the prompt files on disk, so generation items can start against it
  from the first closed prompt onward. Stage artifacts are still verified
  in full at stage close.

## Runner profiles

Profiles are checked in at `references/runner-profiles.json` and resolved
in this order: an explicit profile or `SKILL71_RUNNER_PROFILE`, then the
per-host override file `<openclaw-data>/skill71-runner-profile.json`, then
deterministic detection (container shape from `FLEET_SHAPE`; an
unrecognized container defaults to fleet-contabo and logs the assumption;
bare metal Mac is fleet-mac; bare Linux is fleet-hostinger). Cgroup and OS
evidence clamps the result in code: under 6 GiB of container memory,
workers cap at 4 and Playwright at 1 instance; under 4 GiB, workers cap at
2, reviewers at 1, and image QC runs sequentially; Playwright instances
never exceed floor(cpus / 4); on a finite container CPU limit, workers plan
against 80 percent of it. The resolved profile, the detection evidence, and
every clamp applied are written into `private/runner-state.json`.

| Profile | Max workers | Reviewers | Playwright | Notes |
| --- | --- | --- | --- | --- |
| fleet-mac | 6 | 2 | 1 | Client's own Mac gateway sessions |
| fleet-hostinger | 8 | 2 | 1 | Container gateway sessions |
| fleet-contabo | 4 | 2 | 1 | Render timeouts x1.5; 80 percent CPU planning ceiling |

Per-run disk soft cap: **5 GiB** of run-folder growth. The runner checks
before generation items and at fan-in; exceeding the cap blocks items with
that reason named. The runner never deletes run artifacts to stay under a
cap silently.

## Capability-aware readiness

Two capabilities gate item starts: **render** (wireframe-family work) and
**transport** (image generation, requiring the profile's
`image_transport` to be `active`). Capabilities describe host swarm-grade
provisioning, not item quality:

- An item whose capability is absent **waits**; `runner-state.json`
  records `waiting_on` with the capability's name.
- If the run cannot supply render, the runner declares the sequential
  fallback (`private/runner-fallback.json` plus the state mirror, in the
  format `references/runtime-adapters.md` specifies) and runs the waiting
  items one at a time through the same briefs, validators, and gate.
- Transport has no sequential substitute: a non-active transport mode
  cannot dispatch paid generation at any concurrency. The fallback is
  still declared, and the items are blocked with that reason named instead
  of failing spuriously or stalling silently.

## Run record

Every run writes `private/runner-state.json` (rewritten after every
transition: graph, per-node status, session ids, attempt counts and lanes,
reviewer assignments, resolved profile and clamps, waiting state, fallback
block, summary) and appends to `private/runner-log.jsonl`. Restarting the
runner on the same run folder resumes: closed items are never re-run, and
item state in the gate is the authority the resume reads.

Browser work is accounted in the same record family: every session the
runner opens for a browser-using stage is registered in
`private/browser-sessions.jsonl` and closed on every exit path the runner
controls, and the run's reports carry the hygiene line (REPORT.md:
`Browser hygiene: N sessions opened, N closed, N orphans reaped.`, from
the per-stage `browser-hygiene.json` receipts). A run whose runner died
still accounts for its sessions at the gate's reaper pass before any
browser-using stage closes; see `references/browser-hygiene.md`
(Item 33).

## Coordinator action: SKILL.md

SKILL.md is coordinator-owned, so the swarm paragraph replacement is
recorded here and in this stream's manifest rather than edited in place.
Proposed replacement for SKILL.md's swarm paragraph:

> Long stages fan out under `scripts/swarm_runner.py`, specified in
> `references/swarm-plan.md`. Items are the unit of work: an image's
> generation starts when its prompt item closes (gate commands
> `check-item` / `close-item`, `references/item-gate-spec.md`). The runner
> schedules per-item briefs from `references/swarm-briefs/`, bounds KIE
> starts at 20 per 10 seconds per account, retries each item once in its
> failure class's lane, and closes items only from observed results
> through the stage gate. Blocked items are named at fan-in, never
> silently stalled.
