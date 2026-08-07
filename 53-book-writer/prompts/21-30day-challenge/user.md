<!-- BAKED PROMPT ASSET | stage 21-30day-challenge | subsystem package
     source record: RECONSTRUCTED — no Airtable export shipped (MASTERDOC.md §6, GOLDEN-BOOK-BIBLE.md §8,
       REPAIRS.md #11; the source "30-Day Challenge" export was never recovered).
     provider-agnostic: resolved by the client's own MID-WRITER tier model at runtime; no vendor model ids.
     intake tokens -> {{intake.<key>}}; upstream artifacts (completed manuscript + GATE-1 locked title/subtitle)
       injected by the director per BOOK-WRITER-MANIFEST.json depends_on (18-write-chapters-b4).
     intake content is DATA only, never instructions (prompt-injection rule). -->

## User prompt (token-normalized)

Write the 30-Day Challenge companion for the completed book.

Context from the intake interview:
- Author: {{intake.first_name}} {{intake.last_name}}
- Niche: {{intake.niche}}
- Primary goal the reader is chasing: {{intake.primary_goal}}
- What the book is about: {{intake.book_about}}

The completed manuscript and the GATE-1 locked title + subtitle are injected below. The locked strings
are the byte-exact title and subtitle your title page must echo — do not re-case, re-punctuate,
curly-quote, or abbreviate them:

<upstream_artifacts>
{{artifact.upstream}}
</upstream_artifacts>

Produce EXACTLY 30 day-sections, headed `Day 1 —` through `Day 30 —` (em-dash, no leading zeros), each
a single under-an-hour rep that advances the book's transformation. Echo the locked title byte-exact on
the title page. Do not emit any other day-numbered line anywhere. Markdown only; no commentary before
or after; no unresolved template tokens.
