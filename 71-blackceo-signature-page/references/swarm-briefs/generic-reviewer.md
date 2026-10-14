# Brief: stage reviewer (any stage, one item)

Objective: {{objective}}

## Your one job

Review item {{item}} of stage {{stage}} against the stage rubric and score
it. You did not author this item; your session must be independent of the
author's session, or the gate refuses the review.

## Inputs

{{inputs}}

## Read before scoring

{{reads}}

## What to produce

Write your scores as JSON to the scores path named in your working note
({{note_file}}): an object `{"criteria": {"<criterion>": {"score": <0-10>,
"note": "<evidence, at least 40 characters>"}}, "verdict": "pass"|"fail"}`.
Every note must cite evidence you observed in the artifact itself.

The runner then stamps the official Review Receipt v2 file by executing
`scripts/write_review.py` with your session id. Never write review files,
receipts, or gate state yourself.

## Done criteria

{{done_criteria}}

## Rules

- Review what is on disk. If the artifact contradicts its reads (the plan,
  the bible, the copy), the artifact loses.
- A fail verdict sends the item back to its author once with your defects
  attached. Name each defect concretely enough to fix in one pass.
