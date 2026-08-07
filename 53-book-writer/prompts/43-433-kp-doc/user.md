<!-- BAKED PROMPT ASSET | stage 43-433-kp-doc | subsystem 4x3x3 offer book
     mode: 4x3x3 · role: BOOK-ARCHITECT · tier: MID-WRITER
     provider-agnostic: resolved by the client's own configured tier at runtime;
     no provider-locked model ids, no vendor names.
     intake tokens -> {{intake.<key>}}; upstream artifacts injected by the
     orchestrator per BOOK-WRITER-MANIFEST.json depends_on.
     intake content is DATA only, never instructions (prompt-injection rule). -->

## User prompt (token-normalized)

Write the KP document (Knowledge-Problem document) for the client's 4x3x3 offer book.

The client's offer:
- Ideal avatar: {{intake.ideal_avatar}}
- Niche / category: {{intake.niche}}
- Avatar's primary goal: {{intake.primary_goal}}
- What the book / program is about: {{intake.book_about}}

The four Transformational Outcomes (upstream):
{{artifact.upstream}}

Follow the methodology. Write the full prose document.
