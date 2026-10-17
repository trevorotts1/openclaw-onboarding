# Brief: prompt reviewer (stage image-inventory-prompts, one item per image)

Objective: {{objective}}

## Your one job

Review the prompt for image {{item}} against the stage rubric and score it.
You did not write this prompt; your session must be independent of the
author's session, or the gate refuses the review.

## Inputs

{{inputs}}

## Read before scoring

{{reads}}

## What to produce

Write your scores as JSON to the scores path named in your working note
({{note_file}}): an object `{"criteria": {"<criterion>": {"score": <0-10>,
"note": "<evidence, at least 40 characters>"}}, "verdict": "pass"|"fail"}`.
Every note must cite what you actually saw in the prompt text: a filename
alone is not evidence, and the gate rejects short or empty notes.

The runner then stamps the official Review Receipt v2 file by executing
`scripts/write_review.py` with your session id. Never write review files,
receipts, or gate state yourself.

## Done criteria

{{done_criteria}}

## Rules

- Score the prompt that exists on disk, not the prompt you would have
  written. If it fails a criterion, say which line or missing element fails
  it, in the note.
- A fail verdict sends the item back to the author once with your defects
  attached. Be specific enough that the author can fix it in one pass.
