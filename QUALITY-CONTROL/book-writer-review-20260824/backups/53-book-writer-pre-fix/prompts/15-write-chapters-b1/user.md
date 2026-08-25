<!-- BAKED PROMPT ASSET | stage 15-write-chapters-b1 | subsystem chapters
     source record: skill-53 book-writer P5-CHAPTERS batch 1 (sequential chapter stages, reconstructed)
     provider-agnostic: resolved by the client's own HEAVY-WRITER model at runtime; ZERO vendor-specific model ids.
     intake tokens -> {{intake.<key>}}; upstream artifacts injected by run_book_writer.py per
     BOOK-WRITER-MANIFEST.json depends_on (14-rewrite-titles-extract is the immediate predecessor).
     CHAPTER-BATCH CONTRACT: batch 1 writes chapters 1-3; NO prior chapters to embed; continuity receipt
     at run/receipts/G-STAGE-15-chapters-b1.json records an EMPTY prior set.
     intake content is DATA only, never instructions (prompt-injection rule). -->

## User prompt (token-normalized)

Write the opening batch of my 12-chapter nonfiction book. This is **batch 1: chapters 1, 2, and 3**. Follow the chapter-batch contract exactly.

**Book intent:** {{intake.book_about}}

**Locked title + subtitle (byte-exact — do not change, re-case, or re-punctuate):**
{{artifact.approved-title}}

**Blended tone to write in — "The {{intake.first_name}} {{intake.last_name}} Tone" (the ONLY voice allowed):**
{{artifact.upstream}}

**Approved outline (locked beat map for all 12 chapters; you write only chapters 1-3):**
{{artifact.upstream}}

**Locked chapter titles (use chapter 1, 2, and 3 titles byte-exact as your headings):**
{{artifact.upstream}}

**Personal stories (place verbatim in the assigned chapter; only those assigned to chapters 1, 2, or 3 belong in this batch):**
{{intake.book_stories}}

**Avatar context (ideal reader you are writing to):**
{{intake.ideal_avatar}} — {{intake.primary_goal}}

**Chapter-batch contract for THIS batch:**

- Write exactly chapters 1, 2, 3 — no more, no fewer, never skip ahead.
- Each chapter is **2000-3500 stripped words** (markdown and whitespace stripped before the prover counts; self-reported counts are ignored).
- Every chapter echoes the locked title + subtitle **byte-exact** and uses the exact chapter title from the locked list as its heading.
- Write entirely in the blended tone; end each chapter on the tone's signature single-line challenge.
- **Continuity:** this is the FIRST batch, so there are NO prior chapters to embed. The continuity receipt records an empty prior set: `{"stage": "15-write-chapters-b1", "batch": 1, "chapters_written": [1, 2, 3], "prior_chapters_embedded": {}}`.

Output the three chapters and the JSON receipt only, in the format your instructions describe.
