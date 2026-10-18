# Skill 22 Preservation Map for Council of Wise Elders (WER-013)

**Owner-authorized Council membership is immutable:** Simon Sinek; T. D. Jakes; Oprah Winfrey; Tiffany Aliche; Russell Brunson; Michelle Obama; Brené Brown; Dr. Dennis Kimbro; Les Brown. These are the nine **and only** nine advisor seats. Steve Harvey is NOT on the roster and must never appear in a Council visual, model prompt, Knowledge pack, new persona registration, or portrait build. Any related book or external author is **source material only**, not a tenth seat.

**Primary sources of truth:**
- `77-council-of-wise-elders/runtime/src/contracts/enums.ts`, exports `SEAT_IDS` and `SEAT_ROSTER`
- `77-council-of-wise-elders/SKILL.md`, nine-seat list
- `22-book-to-persona-coaching-leadership-system/persona-categories.json`, canonical existing persona **registry**
- `22-book-to-persona-coaching-leadership-system/personas/<key>/`, existing **derived** book-persona files

## EXISTING CLIENT WORK , retain/reuse, do not replace or recreate

| Council advisor | Existing Skill 22 registered persona folders | Repo artifact maturity |
|---|---|---|
| Simon Sinek | `sinek-start-with-why`, `sinek-find-your-why` | Extraction notes + analysis notes + persona blueprint for both |
| T. D. Jakes | `jakes-instinct` | Extraction notes + analysis notes + persona blueprint |
| Oprah Winfrey | No registered existing Skill22 book-persona folder | Council seat retained. Do not add a new advisor as substitute |
| Tiffany Aliche | `aliche-get-good-with-money` | Existing persona blueprint |
| Russell Brunson | `brunson-marketing-secrets-blackbook`, `brunson-network-marketing-secrets`, `russell-brunson-lead-funnels`, `russell-brunson-the-funnel-hackers-cookbook`, `russell-brunson-traffic-secrets` | First four have extraction notes, analysis notes and blueprints; Traffic Secrets has a blueprint without separate extraction notes |
| Michelle Obama | `obama-becoming`, `obama-light-we-carry` | Extraction notes + analysis notes + persona blueprint for both |
| Brené Brown | `brown-atlas-of-heart` | Extraction notes + analysis notes + persona blueprint |
| Dr. Dennis Kimbro | `kimbro-the-wealth-choice`, `kimbro-what-makes-great-great` | Existing persona blueprints |
| Les Brown | No registered existing Skill22 book-persona folder | Council seat retained. Do not add a new advisor as substitute |

**Count as of audit:** 14 existing registered persona books across 7 of the 9 Council seats: **10 with extraction notes and blueprints, 4 blueprint-only**. This count is based on the current repository registry and tracked files. A user's local Skill 22 system may also hold additional authorized book originals or notes not committed here; do not interpret repository absence as proof that the user has never supplied a book elsewhere.

## Preserve availability, evaluate evidence independently

Presence of a derived Skill 22 extraction or blueprint is *valuable existing work*. It is not by itself verified lawful-access provenance, the actual original book or transcript, a verified full-book ingestion receipt, or permission to quote/redistribute. Current Skill 77 source packs have `bibliographic_only` source-quality status. Do NOT erase Skill 22's notes on that basis; do NOT silently promote them to `primary_substantive`.

Before WER-012/013 production acceptance, do these steps in order:

1. Run `cd 77-council-of-wise-elders/runtime && node --import tsx scripts/audit-skill22-preservation.ts`. The `--json` mode records relative paths, source-derived file hashes and factual scope, **without copying private assets**.
2. Run `node --import tsx scripts/audit-advisor-sources.ts` for *separate* primary-source qualification by required work. The gate's 0/17 current score means **no currently verified source anchors**, not zero existing book-persona files.
3. Check Skill 22 source/original rights and accessible local book assets on the **actual owner's host** (GitHub cannot inspect uncommitted local media), and preserve provenance/hashes of any lawfully accessed material. Explicitly ask the executor to bind the real files via the user's configured Skill 22 system rather than re-downloading or inventing books.
4. Map the existing derivative excerpts to the actual author/source and exact page, chapter, video-time, or retained-original locator. Screen invented quotations and user-private sources. Keep an unresolved or out-of-scope item labeled and unusable for verified citations.
5. Export only consented/permitted paraphrase-based, source-verified material into portable Skill 77 advisor packs. Do not move the full original book, unverified quotations, private user content or source files into shared public GitHub. Validate against exact `SEAT_IDS`.
6. Independently test each of the 17 required foundations (minimum of three distinct traceable concepts + one independently grounded application) as specified by WER-013. If an existing Skill 22 persona is a **supplementary** book rather than the Council's required anchor (e.g. `brown-atlas-of-heart` vs `Dare to Lead`), preserve and optionally cite it with correct scope, but do not pretend it satisfies the missing anchor.
7. Prove one live, authorized model request per seat uses correct approved evidence, with explicit provenance, no wrong-person prompt, no hidden provider change, and no unsupported quotes. Require independent QC.

**Exporter:** `scripts/export-skill22.mjs` now emits canonical per-seat packages from hash-bound selected derivative passages and explicit provenance mappings. See [repeatable invocation and mapping contract](skill22-canonical-export.md). Missing mappings and source qualification remain content/acceptance work; the bridge does not ingest books or invent provenance.

**Portraits:** `77-council-of-wise-elders/assets/portrait-manifest.json` has `assets: []`, meaning no approved illustrated portraits are shipped there. Command Center currently carries **abstract SVG medallions** for the nine seats. A draft collage or external screenshot is not an approved portrait. Command Center WER-017 must produce **exactly nine original illustrated portraits**, checked by identity and rights/provenance, with no outsider (especially no Steve Harvey), and wire them into the real Council UI. Never ship placeholders as if they were the finished images.

Do not modify Skill 22's registry or persona files as part of this *read-only* inventory. This document and its scripts are a map and preservation contract, not a replacement for WER-012/013 source verification or the final visual acceptance.
