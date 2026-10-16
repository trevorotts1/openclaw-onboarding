# Brief: generation poller (stage image-generation-qc, retry lane)

Objective: {{objective}}

## Your one job

A Skill 74 task for image {{item}} was already submitted. Poll that exact
task to completion and land the image at the expected output path. The task
id is in your inputs and your note file ({{note_file}}).

## Inputs

{{inputs}}

## Expected outputs

{{outputs}}

## Rules

- Poll only. Never submit a new createTask for this image, under any
  circumstances: a submitted task is paid work in flight, and a second
  submission double-charges the account and forks the receipt chain.
- Use the Skill 74 route's own polling (recordInfo until a terminal state),
  then persist the returned media immediately; KIE media links expire.
- If the existing task reached a terminal failure state, stop and report
  that state in your note file. Do not resubmit; the runner decides the
  next step from the observed receipt state.
- Never write receipts, review files, or gate state yourself.

## Done criteria

{{done_criteria}}
