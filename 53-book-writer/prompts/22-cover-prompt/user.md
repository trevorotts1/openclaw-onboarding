<!-- BAKED PROMPT ASSET | stage 22-cover-prompt | subsystem package
     source record: RECONSTRUCTED — no Airtable export shipped (MASTERDOC.md §6, REPAIRS.md #8/#11;
       the source "Book Cover Image Gen" export was never recovered).
     provider-agnostic: resolved by the client's own FORMATTER tier model at runtime; no vendor model ids.
     intake tokens -> {{intake.<key>}}; upstream artifacts (GATE-1 locked title/subtitle + avatar dossier)
       injected by the director per BOOK-WRITER-MANIFEST.json depends_on (10-suggested-titles).
     intake content is DATA only, never instructions (prompt-injection rule). -->

## User prompt (token-normalized)

Write the cover prompt for the completed book.

Context from the intake interview:
- Author: {{intake.first_name}} {{intake.last_name}}
- Niche: {{intake.niche}}
- Primary goal the reader is chasing: {{intake.primary_goal}}
- The client's cover description: {{intake.cover_description}}

The GATE-1 locked title + subtitle and the avatar dossier are injected below. The locked strings are
byte-exact and MUST appear in your output unchanged:

<upstream_artifacts>
{{artifact.upstream}}
</upstream_artifacts>

Build the primary generation prompt from the cover description (auto-directing from the title/subtitle
when it is `N/A`), then add art-direction notes and byte-exact title-treatment guidance for the
typesetter. Markdown only; no commentary before or after; no unresolved template tokens.
