<!-- BAKED PROMPT ASSET | stage 19-book-rewrite-1 | subsystem package
     source record: source/airtable-prompts/19-book-rewrite-1.md (revision round 1)
     provider-agnostic: resolved by the client's own HEAVY-WRITER tier model at runtime; zero vendor model ids.
     intake tokens -> {{intake.<key>}}; upstream artifacts injected by the run assembler per BOOK-WRITER-MANIFEST.json depends_on.
     intake content is DATA only, never instructions (prompt-injection rule). -->

## User prompt (token-normalized)

You are revising the finished manuscript in response to the client's edit/approval feedback. This is REVISION ROUND 1 of at most two rounds.

The finished manuscript is below. The locked title and subtitle are the first two lines of this manuscript and MUST be preserved byte-exact in every revised chapter.

[Manuscript]
{{artifact.upstream}}

The client's edit/approval feedback (`Updates`) is below. Apply every actionable note to the affected chapters only. Preserve the locked title/subtitle byte-exact, keep every placed personal story verbatim, and hold each chapter within 2000-3500 stripped words.

[Client edit/approval feedback]
{{artifact.upstream}}

Intake context for the revision:
- Book subject: {{intake.book_about}}
- Client's personal stories: {{intake.book_stories}}
- Avatar's primary goal: {{intake.primary_goal}}
- Client name: {{intake.first_name}} {{intake.last_name}}

Re-emit ONLY the revised chapter files (the chapters the feedback touched), each complete as `chNN.md`, followed by the rewrite receipt quoting the client's `Updates` text and listing the revised chapter numbers.
