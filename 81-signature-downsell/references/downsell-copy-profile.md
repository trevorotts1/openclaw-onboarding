# Downsell Copy Profile - Skill 81 (Signature Downsell, D1)

Status: build candidate, S81 room. Not installed, not merged.
Governing sources: packet 11_SKILL_81_DOWNSELL_SPEC.md sections 2 and 5; packet 20_OWNER_SOURCE_MATERIAL.md (owner corpus, preserved verbatim, never edited); packet 02 section 4 route law; packet 16 section 3 (page-specific copy contracts).

## Derivation (owner method, preserved exactly)

The downsell page is derived from the 12-section landing (Hero) format:

1. Keep original sections 1 to 7 unchanged in role: Big Bold Claim, Big Bold Pain 1, Big Bold Pain 2, Big Bold Pain 3, Big Bold Why, Big Bold Who, Big Bold What.
2. Remove original sections 8 to 11 entirely (the benefits sections and the how section). They must never reappear as extra sections in a downsell page.
3. Replace original section 12 (message from the founder) with a new final section, renumbered as section 8, that lists the 7 things the visitor will have missed out on by declining the additional offer.
4. The offer is clear from the very start of the page.
5. Every section carries a purchase CTA mapped to the same guarded native D1 action. The main-page no-CTA exceptions (for example the landing Who and Benefit sections) do NOT apply to this derived profile.
6. Scarcity and urgency run throughout, and must be truthful: cite only a real deadline, real limited delivery capacity, or a time-sensitive consequence supported by approved source facts. If no scarcity is real, omit any countdown and never use false "one time only" claims.
7. A visible non-purchasing decline action is present on the page in addition to the per-section CTAs. Declining preserves the original purchase in full.

## Section 8 heading - provenance and normalization (doc 19 conflict register, owner S81)

The owner corpus contains BOTH forms:

- Instructions prose form: "When Times Run Out" (the downsell instructions say: replace section 12 with "When Times Run Out: (list the 7 things they will have missed out on)"). Capital T on "Times", verified firsthand in the corpus.
- Sample page form: "When Time Runs Out" (the sample downsell page's Section 8 heading).

Proposed canonical display heading: **When Time Runs Out** (the sample form).
This is a recorded normalization for owner review, not a corpus edit. The corpus files (20_OWNER_SOURCE_MATERIAL.md and sources/OWNER_UPSELL_DOWNSELL_EMAIL_SOURCE.txt) are preserved verbatim and are never rewritten by this skill. Validators accept the sample form as canonical and record any use of the prose form as a normalization event, never as a silent pass.

Note: the legacy Skill 49 downsell profile on onboarding main also renders this heading as "When Time Runs Out", which is consistent with the sample form. That is an observation about existing repo behavior, not a change to Skill 49.

## Exact eight-section contract (spec 11 section 5)

| # | Job | Rules |
|---|---|---|
| 1 | Make the alternative clear immediately | Names the D1 offer and how it differs from U1 in the first section. CTA. |
| 2 | Big Bold Pain 1 | A specific relevant pain or objection this alternative addresses. Distinct from sections 3 and 4. CTA. |
| 3 | Big Bold Pain 2 | A second, different pain or objection. CTA. |
| 4 | Big Bold Pain 3 | A third, different pain or objection. CTA. |
| 5 | The Big Bold Why | The real reason this alternative exists. CTA. |
| 6 | The Big Bold Who | Who the alternative fits, without shaming anyone who declines. CTA. |
| 7 | The Big Bold What | Exact inclusions AND material limitations of D1. CTA. |
| 8 | When Time Runs Out | Exactly 7 distinct, substantive, optional foregone benefits (things missed by declining D1). No duplicates, no paraphrase-padding of one item into two. CTA. |

## Truth and dignity rules (spec 11 sections 4 and 5, doc 18 section 6)

- Section 8 items describe optional additional benefits the visitor will not receive. They must never claim the visitor loses anything already bought in the original checkout. Distinguish "you will not receive these optional additional benefits" from "you will lose your original purchase" - only the first is permitted.
- Declining must not create shame, threats, or false loss of access.
- No fabricated testimonials, proof, prices, or scarcity. The owner sample's prices ($1 trial, $27/month, $997/month regular) and community promises are example data, never client facts; they are blocked from production requests unless they match an approved native price mapping for that client.
- Private framework labels and internal numbering stay out of public production copy unless the client explicitly wants them.
- Refine the client's rough downsell description first, retaining actual offer facts, before authoring sections.

## Derivation checks (doc 18 section 6, enforced by validators/validate_downsell.py)

1. Exactly 8 sections, roles in the order above.
2. CTA present and mapped in every one of the 8 sections.
3. Section 8 contains exactly 7 distinct missed-out consequences (normalized-text distinctness check).
4. Original sections 8 to 11 are not reintroduced (no benefits-1/2/3 or how-to roles anywhere in the page).
5. Section 8 heading equals the canonical display form, or the prose form with a recorded normalization.
6. No section 8 item asserts loss of an already purchased benefit.
7. No example-only price from the owner sample appears unless it matches an approved price in the request.
