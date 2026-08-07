# Book Writer Mini-App — Editable transcript + answer-your-way (U10)

Wave B, unit U10 of the Book Writer Mini-App Gauntlet. Owns the **editable
transcript** contract and the **answer-your-way** tab set from MASTER-PLAN
sections 4 and 5.

## What it does

`editable-transcript.js` is a self-contained, dependency-free module (no DOM
in the pure core, no external libraries). It is the wiring seam the SPA
(U05/U09) mounts inside a media tab panel, and it is the contract U13 (the
transcription engine) must satisfy.

1. **Inline editable transcript.** After a recording is transcribed, the words
   appear inline and editable, labeled **"from your recording"**, with the
   spoken **language shown for confirmation**. The client edits freely; the
   edit stays under the same `answer_id` (an edit, not a new recording).
2. **Re-record SUPERSEDES by answer_id — never appends.** A fresh recording
   carries a new `answer_id` and *replaces* the earlier recording's text for
   that question. `supersede` / `selectLiveAnswer` prove this: the newest
   answer_id wins, older text is dropped, never concatenated.
3. **Answer-your-way tab set** — Type / Upload PDF / Upload text / Audio /
   Video — config-driven per question (a question only offers the modes in its
   `answer_your_way`). Choice fields keep a single segmented enum (no tab wall,
   AF-BK-VERSION). Audio and video are separate gentle tabs when the config
   offers both; the best-fit mode is highlighted, none forced.

## Provider-neutral (NEVER Anthropic)

This module performs **no transcription** and names **no model provider**. It
carries the `verifyNoAnthropic` AF-BW-MA-ANTHROPIC re-check: any resolved
transcription model id matching `/anthropic|claude/i` is a **hard fail** —
never a silent fallback, never an Anthropic id. No operator keys, no client
credentials — the edge stays a dumb relay.

## Warm low-overwhelm

The module's copy is linted against the banned anti-anxiety words
(Submit / Required / Final / Deadline / You must / Error) on every
`--selftest` run. Every question keeps the "Save & come back later — your
answers are safe." chrome (owned by U05/U07).

## Files

- `editable-transcript.js` — the module: pure core + a DOM render helper
  (`renderTranscriptRegion`) + `--selftest` (41 assertions).
- `README.md` — this file.

## Gate

```bash
node -c editable-transcript.js
node editable-transcript.js --selftest
```

Self-test exit 0 = pass; exit 2 = fail. Run from the `pages/` directory.
