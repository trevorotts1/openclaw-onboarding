# Automation Hand-off and the automation-wiring Stage (Item 31)

Skill 71 delivers the page and the funnel. Skill 44 (Convert and Flow
Operator) builds the follow-up workflows that fire when visitors opt in,
buy, or book. This document is the contract between them: what Skill 71
hands over, when the conditional `automation-wiring` stage (stage 14)
runs, what evidence closes it, and how the conversational follow-up layer
(Skill 38) attaches.

## When the stage runs

`automation-wiring` is REQUIRED when the intake records
`publish_target = "ghl"` AND `automation_scope = "workflows"`. Otherwise
the gate records the stage as `not_applicable` in state and in REPORT.md,
citing the intake values it decided from; the stage is never silently
skipped. Intake refuses `automation_scope = "workflows"` with a non-GHL
publish target in writing: workflows live where the forms live.

## The hand-off

At `ghl-install-test` close, Skill 6 records
`handoff/automation-handoff.json`:

```json
{
  "location_id": "...", "funnel_id": "...", "page_id": "...",
  "forms": [{"form_id": "...", "form_name": "...", "page_section": "...",
             "optin_fields": ["name", "email", "phone"]}],
  "conversational_requirements": {"triggers": ["opt-in", "purchase", "booking"]}
}
```

Rules:

- IDs only. The hand-off never carries credentials, tokens, or secrets.
- The form IDs come from Item 32's `funnel-completion.json` forms array
  and from nowhere else; the gate refuses the install close when they
  disagree.
- `publish-verify` carries the hand-off forward UNCHANGED: the gate
  records its SHA-256 at install close and refuses the publish close when
  the file's hash no longer matches (the refusal names both hashes: the
  one locked at install close and the one the file on disk hashes to),
  when the file is missing, or, on a GHL run, when no hash is locked in
  state at all.
- `conversational_requirements` states which trigger classes the funnel
  creates (derived under the conversational rider below); a class with no
  trigger in this funnel is recorded `not_present` at wiring time, never
  invented.

## Execution and evidence (Skill 44)

Execution is delegated to Skill 44's full-funnel role: the Tier 0 `caf`
CLI is primary; the Tier 4 browser backstop (agent-browser) is used when
the CLI path cannot perform a write. The stage's receipt
(`private/receipts/automation-wiring.json`) records, per workflow:
`workflow_id`, `name`, the trigger (`form_submitted` + `form_id`),
`build_method` (`"caf-cli"` or `"tier4-browser-backstop"`), Skill 44's
own QC evidence (`qc.script` = `qc-built-workflow.sh`, its `exit_code`,
the filled checklist instance path, `checklist_complete: true`, and the
WF item count, e.g. `"21/21"`), and a read-back (`readback.exists`,
`readback.status`). The filled checklist instance is a required artifact
under `automation-wiring/`.

The gate verifies at close:

- every hand-off form is trigger-covered by a recorded workflow, or
  carries an explicit `no_workflow_reason` in the receipt;
- every workflow's QC exit code is 0, its checklist is complete, and its
  read-back exists;
- a workflow built through the Tier 4 browser backstop is PRINTED in
  REPORT.md whenever it was used (no silent fallback);
- review runs through the Item 2 machinery: an independent reviewer
  scores the wiring against the opt-in intent the forms express.

## The conversational rider (Amendment 5)

Opt-in, purchase, and booking triggers create conversations, not just
workflow runs. The trigger set is DERIVED, never hand-listed:

- one opt-in trigger per opt-in form (from Item 32's forms array);
- one purchase trigger per bound order form;
- one booking trigger per booking or calendar step.

The receipt's `conversational` array maps each derived trigger to a
workflow carrying a named Skill 38 playbook
(`playbook.system = "38-conversational-ai-system"`) with SMS and email
tracks (`channels` includes both) and the playbook document filed as an
artifact. Minimum playbook set, each required only when its trigger
exists: opt-in follow-up; purchase confirmation and onboarding; booking
confirmation and reminders. A trigger class with no instance in this
funnel is recorded `not_present` in the receipt.

The only exception is a recorded OWNER OVERRIDE in the receipt (trigger,
source, reason, approved by the owner), and overrides print in REPORT.md.
Skill 38 authors the playbooks; Skill 44 attaches them; a run's receipts
record the `ghl_pack_version` of the GHL pack (Skills 6 + 44 + 38's
conversational layer) that performed the work.

## Credentials (Amendment 4 rider)

Three credentials, scoped to targets. Intake records PRESENCE BOOLEANS
AND VARIABLE NAMES ONLY, never values:

- the GHL Private Integration Token and the location ID serve page
  install and Skill 44's standard operations;
- the Firebase refresh token serves workflow writes ONLY. A run that
  never touches workflows never demands it.

Where they live: fleet-mac reads all three from the operator's local
secrets.env. fleet-hostinger and fleet-contabo require an explicit
credential-supply step at provisioning, writing into that install's OWN
secrets.env (per-container on fleet-contabo; never shared across
containers, never host-aggregated).

Refusals, in writing, at intake:

- GHL publish target without the PIT or the location ID: intake refuses.
- Automation scope without the Firebase token: a recorded choice, not a
  silent gap: supply the token, declare the Tier 4 browser backstop in
  the intake record, or drop the automation scope. The page job may
  proceed either way; the workflows may not pretend to exist.

## The producer (R71H emitter)

`scripts/automation_handoff.py` produces the hand-off; the gate calls it
at `ghl-install-test` close, immediately before the hand-off check above,
so a close either derives the file from the run's own records or refuses,
naming why. Field sources, exhaustively:

- `forms`: Item 32's `ghl-install-test/funnel-completion.json` forms
  array, and nothing else. `form_id`, `form_name` (the record's `name`),
  `page_section` (the record's `attached_to_step`); `optin_fields` is
  copied only when the funnel record itself carries it, never invented.
  A funnel form without a `form_id` refuses the close by name.
- `funnel_id`: the funnel record's `funnel.funnel_id`.
- `page_id`: the install receipt's `install.target.page_id_or_url` for
  a GHL target, cross-checked against the funnel steps' `ghl_page`
  bindings; a mismatch refuses by name.
- `location_id`: the VALUE of the environment variable intake records
  for the location credential, read from the process environment at
  close time. Intake records presence and the variable name only; the
  value is never read from any other record, and the Private
  Integration Token is never read. Unsourced, the write refuses,
  naming the variable.
- `conversational_requirements.triggers`: the classes the funnel
  creates, derived from the funnel record under the rider above
  (opt-in per form, purchase per bound order form, booking per
  booking/calendar step).

Ownership: the emitter writes `handoff/emission-record.json` (the
hand-off's SHA-256, its origin, and the envelope state). A hand-off the
emitter wrote (emission record origin `emitted`, hash matching the
file) is regenerated from current records at a later close. Any other
hand-off is externally authored and is never overwritten: the emitter
verifies it against the records and the close refuses on any
disagreement, the form IDs first, in both directions, by name. The
gate's `record_close` stores the file's SHA-256 in state
(`stages.ghl-install-test.handoff_sha256`), which is the hash
`publish-verify` verifies and the dispatch envelope carries.

The dispatch envelope (`handoff/automation-request.json`) is the
automation request Skill 44's dispatch consumes: `request_id`
(`gxo_` + 12 hex, minted once per run and kept across redispatch),
`request_version` (monotonic per run), `location_id`, `launch_id`,
`requesting_room`, `deploy_mode` (exactly `"draft-only"`; construction
refuses any other value, and an absent value, never defaulting),
`approval` (`ref` plus `plan_hash`, the SHA-256 of the canonical wiring
plan), `handoff_sha256`, `plan`, and `workflows` (one build entry per
form with `slug`, `expected_steps`, `allow_multiple`, an origin of
`form_submitted` + the hand-off's `form_id`, and a mechanism:
`contact_tag` with the verbatim Phase-A tag string, or `native` with
`build_method` `"tier4-browser-backstop"`; a form the launch plan
excepts carries a `no_workflow_reason` entry instead). The emitter
constructs the envelope only when the run carries the launch wiring
inputs (launch identity, the plan approval reference, and the per-form
workflow spec) in `page-request.json` or `launch.json`: workflow
behavior, re-entry semantics, and tag strings are launch decisions,
not facts the page run's records contain, and the emitter does not
invent them. Without them the hand-off and its hash are still emitted
and the emission record names what is missing. The envelope is a run
artifact; nothing is dispatched by the emitter.

## The receipt (R71H seam, P2)

The same module files the returned stage-14 receipt:
`file_dispatch_receipt()` (CLI: `automation_handoff.py <run_dir>
--outcome <outcome.json>`). The receiving side's return, or an
operator's record of a refusal or a failure, is recorded in the run as
an outcome record; the filer maps it to
`private/receipts/automation-wiring.json` field for field (seam packet
section 4): `request_id`, `request_version`, `handoff_sha256`, the
`outcome` (`accepted`, `refused`, or `failed`), and, per workflow,
`workflow_id`, `name`, the `trigger` (the declared origin,
`form_submitted` + `form_id`, with the `mechanism` recorded alongside:
`contact_tag` with the verbatim tag string, or `native` with
`build_method` `"tier4-browser-backstop"`), `build_method` mapped from
the recorded execution provenance (`"caf-cli"` for tier 0 caf,
`"tier4-browser-backstop"` for Tier 4), the QC evidence (`qc.script`
= `qc-built-workflow.sh`, its `exit_code`, the filled checklist
instance, `checklist_complete`, and the WF item count carried
VERBATIM, e.g. `"22/22"`), the `readback` (`exists`, `status`), the
`conversational` array, and `ghl_pack_version`. Each workflow's filled
checklist instance is filed under `automation-wiring/` and the
receipt records that path; a filed instance is never overwritten.

The receipt is bound to the dispatch of record before anything is
written: its `handoff_sha256` must equal the hash locked in state at
`ghl-install-test` close and the dispatch envelope's, and its request
identity must match the envelope's. A disagreement is flagged by
name and nothing is filed; a receipt is never silently filed against
the wrong hand-off. Form exceptions default to the envelope's
`no_workflow_reason` entries when the outcome records none of its own.

Refusals are receipts too. A refused dispatch (blocked-auth, wrong
location, plan-hash mismatch, missing Phase-A dependencies) files
with status `blocked` and the refusal reason VERBATIM in
`dispatch_refusal`; the gate refuses the `automation-wiring` close
naming that reason, the stage stays open, and the refusal prints in
REPORT.md. A failed dispatch files with status `fail` and its reason
in `dispatch_failure`. Filing validates identity, binding, and the
presence of the evidence the packet names; execution quality (QC
exit codes, read-back truth, form and trigger coverage) is judged by
the gate at close, exactly as before.

## The fixture (R71H seam, P3)

A completed-install fixture for the joint dry-run with Skill 44
lives at `tests/fixtures/r71h-dry-run/`: `build_fixture.py` writes a
fictional install's input records and drives the real gate through
the `ghl-install-test` and `publish-verify` closes, so the hand-off,
the dispatch envelope, and the emission record in `run/handoff/` are
produced by the shipped emitter from those records, with the
hand-off's SHA-256 locked in the fixture's state. A fixture is never
live proof: no real location, funnel, or launch stands behind its
records, and nothing is dispatched. Skill 44's joint dry-run runs
its receiver against the fixture envelope and returns its stage-14
receipt (or its own outcome record) for filing by the receipt
machinery above; receiver compatibility is claimed, not verified,
until that dry-run runs. `tests/test_r71h_fixture.py` rebuilds the
fixture and asserts the hand-off is byte-identical and both closes
pass on the rebuild.
