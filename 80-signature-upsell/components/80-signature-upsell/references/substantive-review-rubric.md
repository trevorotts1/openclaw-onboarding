# Skill 80 — Substantive Copy Review Rubric (S80-03, human/independent reviewer)

Structural correctness alone is not emotional quality (spec 10 §4). The
validator (`scripts/validate_upsell_copy.py`) proves structure; an
**independent reviewer who is not the copy author** scores each instance
(U1 and U2 separately) on the criteria below. Each applicable criterion
must score at least 8/10 with evidence (doc 16 §8); any automatic fail
below ends the review as FAIL regardless of scores.

| # | Criterion | What the reviewer checks |
|---|---|---|
| R1 | Offer clarity | The incremental offer and its additional outcome are unmistakable from section 1; a cold reader can state what is being sold and what it adds. |
| R2 | Relevance | Each Pain (2–4) is a real remaining challenge for this offer's buyer, distinct in substance, not a restatement. |
| R3 | Progression | Claim → pains → why → who → what → reasons builds one argument; no section repeats the previous section's job. |
| R4 | Truthfulness | No benefit is promised as newly unlocked if the original purchase already includes it; no fabricated loss claim; base purchase acknowledged only as verified. |
| R5 | Who without shame | Section 6 identifies who benefits without shaming or penalising people who decline; declining keeps the original purchase whole. |
| R6 | What is exact | Section 7 lists exact incremental inclusions AND material limitations; nothing material is vague. |
| R7 | Seven real reasons | Section 8's seven reasons are substantive, distinct, and fit this offer and its inspiring phrase — not generic motivation. |
| R8 | U2 distinctness (U2 only) | U2 argues a genuinely different incremental outcome from U1; its reasons and pains are its own, and its copy is truthful for both entry paths (`from_upsell_1`, `from_downsell_1`) — it never tells a D1 buyer they bought the full U1 package. |
| R9 | CTA honesty | Every CTA's emotional wording is matched by the adjacent disclosure: exact amount, currency, one-time/recurring terms. No CTA conceals an immediate charge. |
| R10 | Scarcity integrity | Any urgency traces to a verified fact in the request's `factual_scarcity_evidence`; otherwise there is none. |

**Automatic fails (any one):** wrong product or price; undisclosed
recurring obligation; false prior-purchase statement; invented
testimonial/scarcity; private framework labels in public output;
U2 presented as independently built when it is renamed U1 copy;
self-review presented as independent review.

**Review receipt:** artifact hash, author session, reviewer session,
timestamp, per-criterion scores with evidence, defects, verdict, repair
count — recorded in the instance's `upsell-result.json` (S80-10 owns
the final independent review and packaging).
