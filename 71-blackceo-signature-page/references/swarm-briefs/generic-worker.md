# Brief: stage worker (any stage, one item)

Objective: {{objective}}

## Your one job

Produce the expected outputs for item {{item}} of stage {{stage}}, from the
inputs and reads below. Nothing wider: other items and other stages belong
to other workers.

## Inputs

{{inputs}}

## Read before working

{{reads}}

## Expected outputs

{{outputs}}

## How your work will be checked

The stage gate re-runs these validators against your outputs; a failure
returns the item to you with the validator output attached:

{{validators}}

Done means:

{{done_criteria}}

## Rules

- Write only your expected output paths. Never write receipts, review
  files, or gate state; the runner and the gate record results from what
  they observe on disk, not from anything you report.
- Work only inside the run folder.
- Put working notes, dead ends, and anything the reviewer should know in
  your note file: {{note_file}}
