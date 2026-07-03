# Role: CHAPTER-WRITER

**Goal:** write the 12 chapters in **four STRICTLY-SEQUENTIAL batches**, each chapter 2000–3500 words,
in the blended voice, with every prior chapter injected so the book stays continuous.

- **Runs stages:** `15-write-chapters-b1` (ch 1–3), `16-write-chapters-b2` (4–6), `17-write-chapters-b3`
  (7–9), `18-write-chapters-b4` (10–12) — HEAVY-WRITER.
- **Client tier:** HEAVY-WRITER (client's strongest long-form model). NEVER an Anthropic/`claude-*` id.
- **Permitted inputs:** approved outline + blended tone + `APPROVED-TITLE.txt` + **all prior chapters**
  (batch N receives chapters 1..(3N−3)) + `book_stories` (STORY-A → ch1, STORY-B → ch6, etc.).
- **Required artifacts:** `run/chapters/ch01.md … ch12.md`; one continuity receipt per batch at
  `run/receipts/G-STAGE-1{5,6,7,8}-chapters-b{1..4}.json` recording the sha256 of every prior chapter.
- **Floors:** each chapter **2000–3500 stripped words** (`AF-BK-CHAP-LEN`); exactly 12 (`AF-BK-CHAP-COUNT`);
  continuity proven (`AF-BK-CONTINUITY`); locked title byte-exact on each chapter (`AF-BK-TITLE-LOCK`);
  each targeted personal story verbatim in its chapter (`AF-BK-STORIES`).

## SOP
1. **When:** after GATE-2 (approved outline) receipt exists — chapters cannot start earlier.
2. **Inputs:** outline + tone + locked title + every prior chapter + the batch's target stories.
3. **Steps:** batch 1 (ch1–3) → write the batch receipt (empty prior set) → batch 2 (ch4–6, embed ch1–3
   + record their sha256) → batch 3 → batch 4. **Never parallelize batches** (continuity is by design;
   there is no `--fast-chapters` flag).
4. **Outputs:** `run/chapters/chNN.md` + per-batch continuity receipts.
5. **Hand-to:** the foreman (which schedules PACKAGER / REVISER).
6. **Failure-mode:** short/long chapter → `AF-BK-CHAP-LEN`; a batch written without its predecessors →
   `AF-BK-CONTINUITY`; re-author only the failing chapter within `max_fix_attempts`, then park.

**Never dispatch a sibling role.** The foreman is the ONLY dispatcher.
