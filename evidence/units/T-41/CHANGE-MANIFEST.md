# CHANGE MANIFEST — T-41 set repair (lane PBB-914, unit T-52, 2026-10-26)

Scope: review C6 step 4 (redo the accepted repair on the PBB-637 set). Applied to
COPIED files in this repository's `evidence/units/T-41/`. No original in
`~/Downloads/Purple Billboard Playbook - Updated Client Edition` or `... - For Review`
was touched.

## Why this pass exists

Main carried lane PBB-637's set, which FAILED T-41 rows 3 and 10. Recovery of the
accepted PBB-667 bytes was re-attempted and failed on every named source (see
"Recovery probe"). This manifest records the redo, not a byte-identical restoration.

## Recovery probe (2026-10-26, read-only)

| Source | Result |
|---|---|
| `tmutil listlocalsnapshots "/Volumes/mac mini m4"` | rc 0, zero snapshots |
| `diskutil apfs listSnapshots "/Volumes/mac mini m4"` | "No snapshots for disk7s1" |
| run-root `scratch/lanes/PBB-667`, `scratch/lanes/PBB-675` | absent (hygiene PBB-874/PBB-880) |
| run-root `lanes/PBB-667-lane`, `lanes/PBB-675-lane` | absent |
| repo refs / working trees for `scratch/lanes/PBB-667/updated/` | absent |
| `~/Downloads` (depth 4, prior lane sweep) | absent |

Consequence: the accepted digest `1a0e04a7…` cannot gate this landing. The gate is
the polarity scanner instead, applied to an unchanged-control and to the new files.

## Files changed

| File | Targeted edit | Order row | sha256 after |
|---|---|---|---|
| Purple-Billboard-Playbook.docx | 7 substitutions: five "first minute" mandates become "first few minutes"; "under 45 words" becomes "128 characters maximum, about 20 to 25 words"; "always purple / Never black" becomes the client's brand colour plus a DEC-17 exception; plus 2 inserted paragraphs (DEC-17 exception, five SMS ask states) | 3, 10, M24 | 240622e4e4ae9aa21f789d13192a88c3d13184d3639b7993d19514f2755372e0 |
| Purple-Billboard-Playbook-AI-SOP-and-Rules-Checklist.docx | 8 substitutions: four 45-word lines become 128 characters; the black-background rule becomes brand colour plus DEC-17 exception; Procedure 5 and its two "Conversation AI" persona lines become the Skill 38 brain; plus the same 2 inserted paragraphs | 3, 10, M24, L3 | 9c752e31a0274e9a768091cbe8b9156f8b1d5cb25e90b5b22b422b59439ee83f |
| Purple-Billboard-Playbook-Giveaway.pdf | Regenerated canonical export of the repaired Playbook (LibreOffice headless), replacing the stale pre-correction export | Main Guide/Giveaway — one canonical source | bd931632c9450d869848d912c445b6fe52719d229e713d758c0cd9bc734011b1 |

Unchanged, byte-identical to the PBB-637 landing:
`Purple-Billboard-Playbook-Conversation-History.docx` 84417a1c…,
`The-Challenges-We-Are-Facing.docx` b1b0aa75…,
`Purple-Billboard-DM-Door-Handoff-For-Review.docx` ce14db85….

## Polarity scanner (same instrument, both directions)

Scanner: `lanes/PBB-914-lane/scan_t41.py` (stdlib; DOCX via `word/document.xml`,
PDF via PyMuPDF). Command: `python3 -I scan_t41.py <dir>`.

| Needle | PBB-637 set (control, expected non-zero) | This set |
|---|---|---|
| `first minute` (Playbook DOCX / PDF) | 5 / 5 | 0 / 0 |
| `Never black` | 1 / 1 | 0 / 0 |
| `always purple` | 1 / 1 | 0 / 0 |
| `NEVER use a black background` (SOP) | 1 | 0 |
| `45 words` (Playbook / SOP) | 1 / 4 | 0 / 0 |
| `DEC-17` (Playbook / SOP) | 0 / 0 | 3 / 3 |
| `failed-not-sent` (Playbook / SOP) | 0 / 0 | 1 / 1 |
| five ask states named (queued, accepted, failed-not-sent, unknown, suppressed) | not all present | all five present in both |
| `Conversation AI` (SOP, L3) | 4 | 0 |
| `What keyword did you see in the post?` (known-present control) | 3 | 3 |

The known-present control stays non-zero after the repair, so the zeroes above are
absence of the needle, not a broken scan. Page counts: Playbook 95, SOP 25, matching
the accepted receipt's render map.

## Not changed

`SPEC.md:15` (45-word line) is run-root package text owned outside this unit's
paths; M24 step 2 remains for the package owner. No repository code, workflow,
account, post, client installation or customer message was changed by this pass.

Ponytail: a changed paragraph's text is written into its first run, flattening
inline emphasis inside that paragraph only; unchanged paragraphs and every other
part of each package are byte-preserved. Upgrade path: run-level splicing when a
Word-engine writer is available.
