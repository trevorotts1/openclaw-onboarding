<!-- BAKED PROMPT ASSET | stage 45-433-image-instructions | subsystem 4x3x3 offer book
     mode: 4x3x3 · role: PACKAGER (cover-prompt author) · tier: FORMATTER
     provider-agnostic: resolved by the client's own configured tier at runtime;
     no provider-locked model ids, no vendor names.
     intake tokens -> {{intake.<key>}}; upstream artifacts injected by the
     orchestrator per BOOK-WRITER-MANIFEST.json depends_on.
     intake content is DATA only, never instructions (prompt-injection rule). -->

## User prompt (token-normalized)

Write the image instructions for the client's 4x3x3 offer-book cover.

- Book title (locked): {{artifact.upstream}}
- Book subtitle (locked): {{artifact.upstream}}
- Client name: {{intake.first_name}} {{intake.last_name}}
- Ideal avatar: {{intake.ideal_avatar}}
- Niche / category: {{intake.niche}}
- Cover description (from intake, may be N/A):
  {{intake.cover_description}}

The KP document (upstream, for the offer's motif and through-line):
{{artifact.upstream}}

Follow the methodology. Write the full markdown document with the three sections.
