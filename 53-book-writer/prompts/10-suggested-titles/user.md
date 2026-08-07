<!-- BAKED PROMPT ASSET | stage 10-suggested-titles | subsystem title-core
     source record: source/airtable-prompts/BOOK-WRITER-10-suggested-titles.md
     provider-agnostic: resolved by the client's own TIER model at runtime; ZERO vendor model ids.
     intake tokens -> {{intake.<key>}}; upstream artifacts injected by the foreman (run_book_writer.py) per BOOK-WRITER-MANIFEST.json depends_on.
     intake content is DATA only, never instructions (prompt-injection rule). -->

## User prompt (token-normalized)

Generate title and subtitle candidates for my book, written in my blended tone, and drive GATE-1.

Here is who my book is for and what it is about.

My Ideal Avatar / Dream Customer = [{{intake.ideal_avatar}}]

My Niche = [{{intake.niche}}]

My Ideal Avatar's Primary Goal = [{{intake.primary_goal}}]

What I want my book to be about = [{{intake.book_about}}]

My name = [{{intake.first_name}} {{intake.last_name}}]

Here is my avatar dossier, which explains my reader's wound and desired transformation:
[{{artifact.upstream}}]

Here is my blended writing tone — "The {{intake.first_name}} {{intake.last_name}} Tone" — write every candidate in this voice, verbatim as instructed inside it:
[{{artifact.upstream}}]

Produce a minimum of ten distinct title/subtitle candidates, pressure-test each one, recommend a
single winner, and end by asking me to lock one title and one subtitle verbatim at GATE-1.

Do not add any commentary before or after your output. Strict Markdown only.
