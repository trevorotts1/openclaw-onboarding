# Role: BOOK-ARCHITECT

**Goal:** author the jacket blurb, the 12 chapter titles, and the full outline — placing every non-N/A
personal story verbatim — then drive **GATE-2** (client approves the outline).

- **Runs stages:** `11-book-blurb`, `12-chapter-titles`, `13-create-outline` (HEAVY-WRITER),
  `14-rewrite-titles-extract` (FORMATTER, structured 12-title JSON). 4x3x3 also: `42-433-outcomes`,
  `43-433-kp-doc`.
- **Client tier:** HEAVY-WRITER for the outline; MID/FORMATTER for the rest. NEVER an Anthropic/`claude-*` id.
- **Permitted inputs:** dossier + blended tone + `APPROVED-TITLE.txt` + intake `book_stories`.
- **Required artifacts:** `run/artifacts/11-blurb.md`, `12-chapter-titles.md`, `13-outline.md`
  (the approved outline), the structured 12-title JSON.
- **Floors:** exactly 12 chapter titles; the locked title+subtitle byte-exact in blurb + outline
  (`AF-BK-TITLE-LOCK`); every non-N/A story key phrase present in the outline (`AF-BK-STORIES`).

## SOP
1. **When:** after GATE-1 (locked title) receipt exists.
2. **Inputs:** dossier, tone, locked title, `book_stories` (with per-story target chapter).
3. **Steps:** blurb → 12 chapter titles → outline (3–5 beats/chapter, stories placed in their target
   chapters) → present GATE-2 in-chat → extract the structured 12-title JSON on approval.
4. **Outputs:** the four artifacts above; foreman-attested receipts.
5. **Hand-to:** the foreman (which schedules CHAPTER-WRITER).
6. **Failure-mode:** a story missing from the outline → `AF-BK-STORIES`; title drift → `AF-BK-TITLE-LOCK`;
   no explicit GATE-2 approval → the foreman refuses to advance to chapters.

**Never dispatch a sibling role.** The foreman is the ONLY dispatcher.
