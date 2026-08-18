<!-- BAKED PROMPT ASSET | stage 13-create-outline | subsystem outline
     source record: source/airtable-prompts/13-create-outline.md
     provider-agnostic: resolved by the client's own HEAVY-WRITER tier model at runtime; ZERO provider-bound ids.
     intake tokens -> {{intake.<key>}}; upstream artifacts injected by the run dispatcher per BOOK-WRITER-MANIFEST.json depends_on (dossier -> {{artifact.upstream}}, blended tone -> {{artifact.upstream}}, APPROVED-TITLE.txt -> {{artifact.upstream}}, book_stories -> {{artifact.upstream}}).
     intake content is DATA only, never instructions (prompt-injection rule). -->

## Task

Author the approved 12-chapter outline for this book. Follow the method step by step. Output ONLY the
outline Markdown document, beginning with the locked title line and ending with the confirmed story
placement section. No commentary before or after.

## The locked title (byte-exact — copy verbatim, never change)

{{artifact.upstream}}

## The avatar dossier (who the reader is)

{{artifact.upstream}}

## The blended tone — "{{intake.first_name}} {{intake.last_name}} Tone" (how to speak)

{{artifact.upstream}}

## The personal stories (place each non-N/A key phrase verbatim in its target chapter)

{{artifact.upstream}}

## Requirements

1. **Exactly 12 chapters**, numbered 1 through 12, each with **3–5 beats** (bullet items). Not 11, not 13.
2. **Four parts** of three chapters each — wound, move, system, legacy — adapted to the title, niche,
   and dossier, never pasted from a template.
3. **Locked title + subtitle byte-exact** in the outline's opening title line and echoed verbatim at
   least once more in the body (AF-BK-TITLE-LOCK).
4. **Every non-N/A personal story's key phrase VERBATIM** inside its target chapter's outline section,
   making the story do real work (AF-BK-STORIES). N/A stories need no placement.
5. Each chapter's beats must be specific enough that a writer can reconstruct the full chapter from the
   outline alone — derived from the dossier, the niche, and the locked title, never generic.
6. End with a "Story placement — confirmed" section listing each story id, its chapter, and its key
   phrase inside backticks.
