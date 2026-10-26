# CHANGE MANIFEST — T-41 targeted correction order application (lane PBB-637, 2026-10-25)

Scope: apply `MUSE-HANDOFF.md` ("Muse: targeted document change order") to Muse's
existing editable sources. All edits are COPIES produced in lane scratch
(`scratch/lanes/PBB-637/updated/`). No original in
`<operator-home>/Downloads/Purple Billboard Playbook - Updated Client Edition`
or `... - For Review` was modified (sha256 of originals re-verified unchanged).
Source of the eight message strings: parsed verbatim from MUSE-HANDOFF.md at build
time (regex over the "Message examples to update" section; assert len == 8 passed).

## Files changed

| File (in updated/) | Targeted edit | Order row | sha256 after |
|---|---|---|---|
| Purple-Billboard-Playbook.docx | Appended dated appendix "APPENDIX - APPROVED MESSAGE EXAMPLES (adopted 2026-10-25...)" carrying the 8 approved message examples verbatim + the shared reminder budget paragraph | "Playbook DOCX, sections 10–13 and copy block" + "Message examples to update" | 7fb38d045ebbf8d51161ae0f02fdb889b27064c65ba711ebc3bb1c1b045bd66a |
| Purple-Billboard-Playbook-AI-SOP-and-Rules-Checklist.docx | Same appendix (executable copy home for the one-SMS-ask and shared reminder budget) | "AI SOP and Rules Checklist DOCX" + "Message examples to update" | 3e0c83bf47cb1af396f5dd4981ca3eebea41547dee2308cd0fcd825c392ebec0 |
| Purple-Billboard-Playbook-Conversation-History.docx | Appended "STATUS/ERRATA NOTE - 2026-10-25"; historical text preserved byte-for-byte above the note | "History, DM Door Handoff and Challenges" | 84417a1ca682c7a605c4edbe997691b3582dae56ec380252ad56d48939a4c38c |
| The-Challenges-We-Are-Facing.docx | Same dated status/errata note (this file was missing from the Updated Client Edition set entirely; built from the For Review editable source) | "History, DM Door Handoff and Challenges" | b1b0aa7530068c8f11d98e0b0a3a6bb2571e8f8af80d7e87605f0c3b844c397f |
| Purple-Billboard-DM-Door-Handoff-For-Review.docx | Appended dated status/errata note only (its other corrections were already adopted upstream; incident record preserved) | "History, DM Door Handoff and Challenges" | ce14db8553df76c759e8f1041430448bdb6ee47d50b4c8ef3887d9fc4f88492b |
| Purple-Billboard-Playbook-Giveaway.pdf | Replaced by the corrected canonical export (byte-copy of the corrected `Purple-Billboard-Playbook.pdf`, sha ac1df6725193910359d62ef99f4250c529346e0e3c61f962f5053cb300228690) | "Main Guide/Giveaway — Correct one canonical source; exports were identical" | ac1df6725193910359d62ef99f4250c529346e0e3c61f962f5053cb300228690 |

Proof of the Giveaway substitution rule: `Purple Billboard Playbook - Main Guide.pdf`
and `Purple-Billboard-Playbook-Giveaway.pdf` in For Review are byte-identical
(sha256 4c438cb7e00d5cdc82efb18ed3aeaf57ce8a8dc672f8defafbe91b295ec653c5),
confirming "exports were identical". The Giveaway.pdf shipped in the Updated Client
Edition set is the stale pre-correction export (0 correction markers, "Comment 7" x7).

## Regenerated exports (candidates)

`updated/exports-candidate/*.pdf` — LibreOffice headless export of the five changed
DOCX (recorded in T-41-BUILD.md). Ponytail: exporter provenance differs from the
original Word exports; layout parity check is a named remaining item, add a
Word-engine re-export when the original exporter is available.

## Checks of changed pages

Last-page renders of each changed export in `evidence/pages/*.png`, visually read:
appended notes and the 8-message appendix render legibly, no clipping, no garbled
text, historical content above the notes unchanged.

## Not changed (by acceptance)

`.github/workflows/qc-static.yml` and every repo: untouched
(worktree blob == HEAD blob c036f75576d13f0e6056dbebc6e0187a821a374d).
Order line: "This is document cleanup only. Do not change repositories, workflows,
accounts, posts, client installations or customer messaging."
