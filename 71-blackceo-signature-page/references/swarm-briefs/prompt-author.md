# Brief: prompt author (stage image-inventory-prompts, one item per image)

Objective: {{objective}}

## Your one job

Write the generation prompt for image {{item}} and nothing else. One image,
one prompt file, written to the expected output path below.

## Inputs

{{inputs}}

## Read before writing

{{reads}}

## Expected outputs

{{outputs}}

## How your work will be checked

The stage gate re-runs these validators against your file; a failure returns
the item to you with the validator output attached:

{{validators}}

Done means:

{{done_criteria}}

## Rules

- Write only your expected output paths. Never write receipts, review files,
  or gate state; the runner and the gate record results from what they
  observe on disk, not from anything you report.
- Work only inside the run folder. Do not touch other images' prompt files.
- Put working notes, dead ends, and anything the reviewer should know in
  your note file: {{note_file}}
