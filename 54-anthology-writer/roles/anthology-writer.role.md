# Role recipe — Anthology Chapter Author

**Department:** Content / Publishing (the Book engine department, O7).
**Role slug:** `anthology-chapter-author`
**Skill:** 54 — Anthology Writer.

## What this role does
Turns one contributor intake (premise + personal stories + tone influences) into
one finished, gated anthology chapter (2,000–3,500 words) in that contributor's
blended signature voice, plus the supporting tone doc, locked title/subtitle,
blurb, and outline — delivered as a labeled LOCAL bundle. Runs many contributors
in parallel; each chapter is independently certified.

## Trigger phrases (discoverability)
- "anthology chapter for <contributor>"
- "run anthology writer"
- "start my anthology"
- "add a contributor to book <id>"
- "anthology status"

## Success criteria (all machine-enforced, fail-closed)
- Intake complete; no credential-shaped fields.
- Blended tone from exactly 4 influence analyses, ≥3,000 stripped words.
- Chapter 2,000–3,500 stripped words, ONE per contributor.
- Locked title/subtitle carried byte-exact into outline AND chapter.
- Every non-N/A personal story placed in outline AND chapter.
- No unresolved placeholders; COMPLETION VERIFICATION block present.
- Every resolved model id is NON-Anthropic (client's own providers/keys).
- A signed process certificate is issued only on a full pass.

## Provider rule (binding)
Client box → the client's OWN configured providers and keys, resolved per box by
`preflight.sh` into `model-map.json`. Never Anthropic / `claude-*`, never the
operator's keys, never a key taken through intake.
