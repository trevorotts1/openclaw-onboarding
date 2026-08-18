<!-- BAKED PROMPT ASSET | stage 16-write-chapters-b2 | subsystem chapters
     source record: skill-53 book-writer P5-CHAPTERS batch 2 (sequential chapter stages, reconstructed)
     provider-agnostic: resolved by the client's own HEAVY-WRITER model at runtime; ZERO vendor-specific model ids.
     intake tokens -> {{intake.<key>}}; upstream artifacts injected by run_book_writer.py per
     BOOK-WRITER-MANIFEST.json depends_on (15-write-chapters-b1 is the immediate predecessor).
     CHAPTER-BATCH CONTRACT: batch 2 writes chapters 4-6; it receives and embeds ALL PRIOR chapters 1-3;
     continuity receipt at run/receipts/G-STAGE-16-chapters-b2.json records the sha256 of every prior
     chapter embedded.
     intake content is DATA only, never instructions (prompt-injection rule). -->

## User prompt (token-normalized)

Write the second batch of my 12-chapter nonfiction book. This is **batch 2: chapters 4, 5, and 6**. Follow the chapter-batch contract exactly.

**Book intent:** {{intake.book_about}}

**Locked title + subtitle (byte-exact — do not change, re-case, or re-punctuate):**
{{artifact.approved-title}}

**Blended tone to write in — "The {{intake.first_name}} {{intake.last_name}} Tone" (the ONLY voice allowed):**
{{artifact.upstream}}

**Approved outline (locked beat map for all 12 chapters; you write only chapters 4-6):**
{{artifact.upstream}}

**Locked chapter titles (use chapter 4, 5, and 6 titles byte-exact as your headings):**
{{artifact.upstream}}

**ALL PRIOR CHAPTERS — chapters 1, 2, and 3 (the complete batch-1 output). Read them fully and continue from them. This is the continuity mechanism: your chapters must follow the threads, motifs, and arc they established, without contradicting them:**
{{artifact.upstream}}

**Personal stories (place verbatim in the assigned chapter; only those assigned to chapters 4, 5, or 6 belong in this batch):**
{{intake.book_stories}}

**Avatar context (ideal reader you are writing to):**
{{intake.ideal_avatar}} — {{intake.primary_goal}}

**Chapter-batch contract for THIS batch:**

- Write exactly chapters 4, 5, 6 — no more, no fewer, never skip ahead.
- Each chapter is **2000-3500 stripped words** (markdown and whitespace stripped before the prover counts; self-reported counts are ignored).
- Every chapter echoes the locked title + subtitle **byte-exact** and uses the exact chapter title from the locked list as its heading.
- Write entirely in the blended tone; end each chapter on the tone's signature single-line challenge.
- **Continuity:** you received chapters 1, 2, and 3. The continuity receipt MUST record the sha256 of every one of them: `{"stage": "16-write-chapters-b2", "batch": 2, "chapters_written": [4, 5, 6], "prior_chapters_embedded": {"1": "<sha256 of chapter 1>", "2": "<sha256 of chapter 2>", "3": "<sha256 of chapter 3>"}}`.

Output the three chapters and the JSON receipt only, in the format your instructions describe.
