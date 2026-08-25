<!-- BAKED PROMPT ASSET | stage 20-book-rewrite-2 | subsystem package
     source record: source/airtable-prompts/20-book-rewrite-2.md (revision round 2)
     provider-agnostic: resolved by the client's own HEAVY-WRITER tier model at runtime; zero vendor model ids.
     intake tokens -> {{intake.<key>}}; upstream artifacts injected by the run assembler per BOOK-WRITER-MANIFEST.json depends_on.
     intake content is DATA only, never instructions (prompt-injection rule). -->

## User prompt (token-normalized)

You are revising the round-1 manuscript in response to the client's second edit/approval feedback. This is REVISION ROUND 2 — the FINAL revision round. There is NO third round.

The round-1 revised manuscript is below. The locked title and subtitle are the first two lines of this manuscript and MUST be preserved byte-exact in every revised chapter.

[Round-1 manuscript]
{{artifact.upstream}}

The client's round-2 edit/approval feedback (`Updates`) is below. Apply every actionable note to the affected chapters only. Preserve the locked title/subtitle byte-exact, keep every placed personal story verbatim, and hold each chapter within 2000-3500 stripped words.

[Client round-2 edit/approval feedback]
{{artifact.upstream}}

Intake context for the revision:
- Book subject: {{intake.book_about}}
- Client's personal stories: {{intake.book_stories}}
- Avatar's primary goal: {{intake.primary_goal}}
- Client name: {{intake.first_name}} {{intake.last_name}}

Re-emit ONLY the revised chapter files (the chapters the feedback touched), each complete as `chNN.md`, followed by the rewrite receipt quoting the client's `Updates` text, listing the revised chapter numbers, and recording round 2 as FINAL — with no third round offered.
