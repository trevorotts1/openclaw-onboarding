# Anthology Writer — MASTERDOC (SACRED IP + rule→code map)

This is the anonymized canonical method for the Anthology Writer (Skill 54) and
the single human-readable index tying every SACRED rule to the fail-closed prover
that enforces it. **Enforcement, not description:** if a rule is here, a prover
measures it; a model's self-report is never trusted.

## The unit of work

One **contributor**, one **chapter**. An anthology is many contributors; this
skill authors and certifies each chapter independently, so contributors run in
parallel and one blocked chapter never strands the others.

## The pipeline (P0 → P7, no phase skips)

| Phase | Produces | Gate (AF-AW-*) |
|---|---|---|
| P0 INTAKE | `working/intake.json` | INTAKE-MISSING, INTAKE-CREDENTIAL |
| P1 FIDELITY | pinned prompts + tone-core lockstep | PROMPT-DRIFT, TONE-DRIFT |
| P2 TONE-AUTHOR | `working/tone-doc.md` | — |
| P3 TONE-QC | tone QC report | TONE-4, TONE-FLOOR |
| P4 TITLE-LOCK | `working/title.json` | TITLE-MISSING |
| P5 CHAPTER-AUTHOR | `working/outline.md` + `working/chapter.md` | — |
| P6 CHAPTER-QC | chapter QC report | CHAP-LEN, VERIFY-BLOCK, PLACEHOLDER, TITLE-LOCK, STORIES, ANTHROPIC, REWRITE-BUDGET |
| P7 DELIVER | `delivery/PROCESS-CERTIFICATE.json` | STAGE-SKIPPED, PROCESS-INTEGRITY |

## The SACRED floors (never floored, reordered, or reinterpreted)

1. **Chapter length:** 2,000–3,500 stripped words — measured, not self-reported.
   Whitespace/filler padding is inert. Exactly ONE chapter per contributor.
2. **Blended tone:** "The {First} {Last} Tone", synthesized from EXACTLY four
   tone-style influence analyses, ≥ 3,000 stripped words (shared tone-core R7).
3. **Title lock:** the contributor's chosen title + subtitle become byte-exact
   invariants carried into the outline AND the chapter; a rewrite can never
   change them.
4. **Story placement:** every non-`N/A` personal-story anchor is provably placed
   in the outline AND the chapter (assigned to a beat before prose is written).
5. **Completion block:** the chapter ends with a `COMPLETION VERIFICATION` block
   (its numbers are ignored; its presence is required).
6. **No placeholders:** no `{{..}}` / `[[..]]` / `<ALLCAPS>` survives into a
   finalized artifact.
7. **Rewrite budget:** at most two rewrites per contributor; a third escalates to
   the owner.
8. **Client sovereignty / NON-Anthropic:** every resolved model id is the
   client's own strongest NON-Anthropic model. No `claude-*` / `anthropic/*` id,
   no operator key, no key taken through intake.

## The tone core (referenced, never re-authored)

The four tone-style analyzers + the blended-tone author live ONCE in
`shared-utils/tone-writing-core/prompts/04..08`. Skill 54 bakes a **lockstep
copy** into `prompts/` and proves it byte-identical at build/CI time
(`verify_tone_core_sync.py`, AF-AW-TONE-DRIFT). A change to the shared core flags
both Skill 54 (Anthology) and Skill 53 (Book) for review. The two are separate
skills sharing one core — never merged (Trevor's standing decision).

## The NON-Anthropic build-fix (source → runtime)

The source anthology workflow pinned every extracted call to an Anthropic model
id and routed through "the client's OpenRouter primary". Those ids are
**capability tiers, not prescriptions**. Skill 54 bakes prompt BODIES only (no
concrete model id anywhere) and resolves the tiers per box:

| Tier | Stages | Resolves to |
|---|---|---|
| HEAVY-WRITER | aw-09 chapter, aw-10 rewrite | client's strongest long-form NON-Anthropic model |
| MID-WRITER | aw-01..08 tone/title/blurb/outline | client's mid NON-Anthropic model |
| RESEARCHER | optional grounding | client's own web-search tool (else `degraded:search`) |
| IMAGE | optional cover | client's own image provider (else `degraded:image`) |

There is NO formatter tier — the five source HTML-formatter LLM calls are
**retired**; formatting is deterministic Python. `aw_build_check.py`
(G-NOANTHROPIC) hard-fails any `/anthropic|claude/i` id in the run ledger, and
`verify.sh` statically scans the shipped skill for any concrete `claude-*` /
`anthropic/*` id.
