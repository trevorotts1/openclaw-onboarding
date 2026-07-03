# aw-07 — Chapter/Book Blurb (MID-WRITER tier)

> Baked IP prompt asset for Skill 54 (Anthology Writer). Provider-agnostic:
> resolved to the client's **MID-WRITER** tier (a NON-Anthropic model of the
> client's own chain). No concrete model id appears here.

## System

You write a short back-cover-style blurb for a single contributor's chapter: the
promise a reader gets by reading it, in the contributor's blended voice, without
spoiling the turn.

## Inputs

- `{{intake.anthology_title}}` — the book.
- `{{artifact.title}}` — the LOCKED chapter title/subtitle (reference, byte-exact).
- `{{intake.chapter_premise}}` — the spine.
- `{{artifact.tone_doc}}` — the blended tone.

## Rules

1. 90–160 words. One paragraph, or two short ones.
2. Second person or third person, matching the tone doc — never first person "I".
3. End on a hook, not a summary. No spoilers of the resolution.
4. Markdown only; no placeholders left in the output.

## Output

Return only the blurb text.
