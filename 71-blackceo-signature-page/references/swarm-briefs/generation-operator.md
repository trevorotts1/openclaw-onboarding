# Brief: generation operator (stage image-generation-qc, one item per image)

Objective: {{objective}}

## Your one job

Generate image {{item}} from its closed prompt, through the approved Skill
74 KIE route only, and land the image at the expected output path.

## Inputs

{{inputs}}

## Read before dispatching

{{reads}}

## Expected outputs

{{outputs}}

## Rules

- Dispatch only through Skill 74 (`74-kie-live-adapter`, policy
  `66-kie-image`, mode active). Never call the KIE API directly, never
  hand-roll a createTask, never substitute another provider or model. The
  runner holds the account's rate budget (20 createTask starts per 10
  seconds per KIE account) and starts you only when a slot is yours.
- The runner and Skill 74 record the transport receipt from observed
  results. Never write receipts, review files, or gate state yourself.
- If a Skill 74 task for this image already exists (your brief or note file
  names a task id), poll that task. Never submit a second createTask for an
  image that already has one.
- Put the task id, dispatch time, and any provider message in your note
  file: {{note_file}}

## Done criteria

{{done_criteria}}
