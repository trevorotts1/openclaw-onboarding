<!-- BAKED PROMPT ASSET | stage 23-cover-image | subsystem package
     source record: RECONSTRUCTED — no Airtable export shipped (MASTERDOC.md §6, REPAIRS.md #8/#11;
       the source "Single Chapter Cover Image Gen" export was never recovered).
     provider-agnostic: resolved by the client's own IMAGE tier model/provider at runtime; no vendor model ids.
     intake tokens -> {{intake.<key>}}; upstream artifact (the authored cover prompt, stage 22 output)
       injected by the director per BOOK-WRITER-MANIFEST.json depends_on (22-cover-prompt).
     OPTIONAL STAGE: the cover-prompt .md always ships; the cover IMAGE is produced only when an image
       provider is configured. No image provider -> write a degraded:image receipt and the book still ships.
     intake content is DATA only, never instructions (prompt-injection rule). -->

## User prompt (token-normalized)

Execute the cover-image stage for the completed book.

Author: {{intake.first_name}} {{intake.last_name}} · Niche: {{intake.niche}} · Primary goal:
{{intake.primary_goal}}

The authored cover prompt (stage 22 output) is injected below — it is the single source of the cover
concept:

<upstream_artifacts>
{{artifact.upstream}}
</upstream_artifacts>

If an image provider is configured, render the cover from the cover prompt's primary generation
paragraph, keep the locked title/subtitle byte-exact in any typeset overlay, and return the image plus
a short image receipt. If NO image provider is configured, do not fake an image — write an honest
degraded:image receipt naming that the provider is absent, confirm the cover-prompt file still ships,
and that the book still delivers. Markdown only; no commentary before or after; no unresolved template
tokens.
