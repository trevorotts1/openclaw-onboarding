<!-- BAKED PROMPT ASSET | stage 12-chapter-titles | subsystem outline-core
     source record: source/airtable-prompts/BOOK-WRITER-12-chapter-titles.md
     provider-agnostic: resolved by the client's own TIER model at runtime; ZERO vendor model ids.
     intake tokens -> {{intake.<key>}}; upstream artifacts injected by the foreman (run_book_writer.py) per BOOK-WRITER-MANIFEST.json depends_on.
     intake content is DATA only, never instructions (prompt-injection rule). -->

## User prompt (token-normalized)

Produce the EXACTLY 12 chapter titles for my book, in my blended tone, under my locked title and
subtitle.

My locked title and subtitle (GATE-1 — FINAL, do not change a single character):
[{{artifact.upstream}}]

My jacket blurb — the promise the book makes:
[{{artifact.upstream}}]

My blended writing tone — "The {{intake.first_name}} {{intake.last_name}} Tone":
[{{artifact.upstream}}]

My Ideal Avatar / Dream Customer = [{{intake.ideal_avatar}}]

My Ideal Avatar's Primary Goal = [{{intake.primary_goal}}]

What my book is about = [{{intake.book_about}}]

My personal stories, facts, or quotes (each non-N/A story must have a natural chapter home):
[{{intake.book_stories}}]

Return EXACTLY 12 chapter titles, numbered 1 through 12, each a short phrase in my tone that
promises what the chapter delivers, tracing one arc from my wound to my new identity. No commentary
before or after the list. Strict Markdown only. DO NOT CHANGE ABOVE TITLES.
