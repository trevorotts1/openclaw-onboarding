<!-- BAKED PROMPT ASSET | stage 21-30day-challenge | subsystem package
     source record: RECONSTRUCTED — no Airtable export shipped (MASTERDOC.md §6, GOLDEN-BOOK-BIBLE.md §8,
       REPAIRS.md #11; the source "30-Day Challenge" export was never recovered).
     provider-agnostic: resolved by the client's own MID-WRITER tier model at runtime; no vendor model ids.
     intake tokens -> {{intake.<key>}}; upstream artifacts (completed manuscript + GATE-1 locked title/subtitle)
       injected by the director per BOOK-WRITER-MANIFEST.json depends_on (18-write-chapters-b4).
     intake content is DATA only, never instructions (prompt-injection rule). -->

Your output is measured by a deterministic prover that IGNORES self-reported counts. Two rules are
fail-closed — violating either blocks the run (AF-BK-CHALLENGE / AF-BK-PLACEHOLDER):

1. **EXACTLY 30 day-sections.** The prover counts lines that begin with the heading pattern
   `Day <n> —`, `Day <n> -`, or `Day <n> :` (markdown hash optional, case-insensitive), and the count
   MUST be exactly 30 — not 29, not 31. Author sections `Day 1 —` through `Day 30 —` in ascending
   order. Never write `Day 0`, `Day 31`, or any other day-numbered line anywhere else, including in
   body prose — an incidental match is still counted. The day title follows the em-dash in the heading.
2. **No unresolved template tokens.** Emit no `{{...}}` and no `$('...')` tokens anywhere in your output.

Structure the document exactly as follows:

- **Title page.** A `#` heading containing the LOCKED title of the book, echoed BYTE-EXACT from the
  injected title/subtitle (same casing, same punctuation, same order). Under it, a short intro
  paragraph (3–4 sentences) framing the design: one small move a day, each under an hour, done in
  order, and progress that is not a straight line.
- **Four week sections.** `## Week 1 — <theme>` through `## Week 4 — <theme>`, each grouping seven
  days, with Days 29–30 closing the arc after Week 4. Week headings do not affect the day count.
- **30 day-sections.** For n from 1 to 30, exactly one section per day:
  - a `### Day <n> — <Day Title>` heading (em-dash, no leading zero);
  - a body of 3–6 sentences: the ONE action the reader takes that day, why it maps to the book's core
    method, and what "done" looks like by night. Write it in the book's blended tone.
- **No commentary before or after.** Begin at the title page and end after Day 30's body. No closing
  remarks, no meta-notes, no formatting guide.

Every day must trace back to a specific lesson in the book — never generic filler. Do not repeat the
locked title as a day heading; only the title page carries it.
