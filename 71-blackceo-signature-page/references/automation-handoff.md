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
  the file's hash no longer matches.
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
