<!-- BAKED PROMPT ASSET | stage 11-book-blurb | subsystem outline-core
     source record: source/airtable-prompts/BOOK-WRITER-11-book-blurb.md
     provider-agnostic: resolved by the client's own TIER model at runtime; ZERO vendor model ids.
     intake tokens -> {{intake.<key>}}; upstream artifacts injected by the foreman (run_book_writer.py) per BOOK-WRITER-MANIFEST.json depends_on.
     intake content is DATA only, never instructions (prompt-injection rule). -->

## User prompt (token-normalized)

Write the back-cover jacket blurb for my book, in my blended tone, carrying my locked title and
subtitle byte-exact.

My locked title and subtitle (GATE-1 — FINAL, do not change a single character):
[{{artifact.upstream}}]

The title/subtitle candidates and the rationale for the winner:
[{{artifact.upstream}}]

My blended writing tone — "The {{intake.first_name}} {{intake.last_name}} Tone":
[{{artifact.upstream}}]

My Ideal Avatar / Dream Customer = [{{intake.ideal_avatar}}]

My Niche = [{{intake.niche}}]

My Ideal Avatar's Primary Goal = [{{intake.primary_goal}}]

What my book is about = [{{intake.book_about}}]

My personal stories, facts, or quotes (use them only if present; never invent any):
[{{intake.book_stories}}]

Write 150–220 words. Open with my locked title and subtitle verbatim. Name the wound, show the cost,
promise the transformation, weave in one of my stories only if I provided one, and end on a short
line that dares the reader to begin.

Do not add any commentary before or after your output. Strict Markdown only. DO NOT CHANGE ABOVE
TITLES.
