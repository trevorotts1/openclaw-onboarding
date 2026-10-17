# S81-07 Terms / Claims / Entitlement Review - Skill 81

Status: build candidate review instrument. Governing sources: packet 11 sections 4, 6, 7, 10; packet 02 sections 3, 8; packet 16 section 8; packet 18 sections 4, 5, 6.

## Review checklist (every item must pass on the actual page + request before S81-08)

### Money and terms
- [ ] Due-now amount on the page equals the approved native price for D1 (integer minor units, declared currency; processor quote is authoritative for tax/discount/shipping).
- [ ] Trial/subscription: due now, trial length, renewal amount, renewal date or rule, interval, cancellation terms, and access implications all present adjacent to the action, at body size, in desktop and mobile (validator: validate_trial_disclosure, with due-now and renewal cross-checked against the offer).
- [ ] Installment D1: the full total obligation is stated; copy never presents the installment as the total price.
- [ ] No owner-sample amounts ($1 / $27 / $997) anywhere on any public surface unless they match this client's approved native pricing (validator: D1-COPY-EXAMPLE-PRICE-LEAK scans headings, bodies, CTA labels, missed items, decline label).

### Claims
- [ ] Every scarcity/urgency claim traces to a recorded real deadline, capacity limit, or time-sensitive consequence (validator: D1-COPY-FAKE-SCARCITY requires scarcity_evidence_ref). No countdown exists without a real deadline behind it.
- [ ] No testimonial, result, or proof appears that was not supplied and substantiated. Nothing fabricated.
- [ ] Section 8 contains exactly seven missed-out items, all distinct and substantive: no exact duplicates (validator: D1-COPY-MISSED-DUPLICATED), no paraphrase-padding of one consequence into two (validator: D1-COPY-MISSED-PARAPHRASE-DUPLICATE), none insubstantial (validator: D1-COPY-MISSED-INSUBSTANTIAL), count exactly seven (validator: D1-COPY-MISSED-COUNT-NOT-SEVEN). Spec 11 section 10 names "fewer or duplicated reasons presented as seven substantive reasons" as a negative test.
- [ ] Section 8's seven items are optional foregone benefits of D1 only. None asserts loss of the original purchase, the bump, or any included entitlement (validator: D1-COPY-FALSE-LOSS-OF-PURCHASE plus human read).
- [ ] Decline copy is free of shame, threats, and false loss of access. The three pains are distinct claims about the visitor's situation, never insults about the visitor.

### Entitlements
- [ ] Difference table recorded before copy: U1 deliverables, D1 deliverables, difference_kind, objection addressed, rationale. No identical-promise D1 (validator: D1-OFFER-IDENTICAL-PROMISE compares deliverables and entitlements).
- [ ] Mutual exclusion declared both directions on the offers (validator: D1-OFFER-EXCLUDES-U1-MISSING / D1-OFFER-U1-EXCLUDES-D1-MISSING) and enforced by the entry guard.
- [ ] D1 removes nothing already bought (validator: D1-OFFER-REMOVES-BASE-PURCHASE when the base offer is supplied).
- [ ] On D1 success, incremental entitlements recorded are exactly D1's; the thank-you page (S82) must show purchased items only, and S44 maps the event by verified product/page/slot, never an invented downsell trigger.

### Branch behavior spot-checks (negative tests from spec 11 section 10)
- [ ] Accepted U1 buyer cannot reach D1. Failed U1 payment is never labeled a decline. Clicking D1 decline charges nothing. D1 success creates exactly one canonical U2 instance. Final page shows no unpurchased U1 benefits. Duplicate D1 acceptance is refused. Direct D1 access without a verified main purchase is refused.
- [ ] Unknown transaction outcome (timeout): treated as neither acceptance nor decline; the outcome is reconciled from native records BEFORE any retry, and no second charge is attempted just to learn whether the first succeeded (spec 11 sections 6, 7 and 10).
- [ ] Every required route exists and terminates: D1 paid -> same U2 or thank-you, D1 declined -> thank-you, no orphan or missing route (doc 16 section 8 lists a missing required route as an automatic fail).

### Platform truth checks (doc 16 section 8 automatic fails, D1-applicable)
- [ ] Tenant and location on the installed page match the page request exactly; a wrong-tenant binding fails the review outright.
- [ ] Native action binding plan AND read-back are on file: the installed native action's product/price association was read back from the native system and matches the approved D1 mapping (spec 11 section 3 names the binding plan/read-back as a required output). A pretty local button is not binding evidence.
- [ ] No forged success: any success state, route advance, or entitlement grant rests on a verified native transaction record, never on a click, a redirect URL, or a client-side parameter.
- [ ] No leaked secrets or customer data: no credential, token, session material, or other customer's data appears in the page, its assets, screenshots, or receipts.

## Owner-accepted limitation: validator wording coverage (ruling S81-DEC-LEXRES-01)

Recorded 2026-10-16. Owner: Trevor. Ruling S81-DEC-LEXRES-01: fix the false-positive bug and accept the wording limit in writing; no cure round 4. On this ruling, S81-02 and S81-03 stand restored at L1 with the limitation below on the record.

The copy validators screen page wording against recorded phrasing families. For the three families below, that coverage is finite: three cure rounds each cured every recorded escape, and each independent re-review then found fresh ordinary phrasings one step outside the widened lists. The owner accepts that boundary in writing. Plainly stated: the machine screen's coverage of these three families is finite, and phrasings outside the recorded families can pass it:

- D-3 scarcity phrasings (validator: D1-COPY-FAKE-SCARCITY). Still passing at the ruling date: the limited predicate on offer subjects outside the anchor list ("Capacity is limited for this cohort.", "Intake is limited for the winter round."), the sibling capped predicate ("Registration is capped for this round."), the prices-rise family under a one-word insertion ("The price goes back up on Monday at this rate."), and the count-free depletion form ("Only while seats remain at this price.").
- D-8 private-label forms (validator: D1-COPY-PRIVATE-LABEL-LEAK). Still passing at the ruling date: internal document nouns outside the widened class ("Internal checklist for the launch team.", "Internal roster for event staff.", "Internal summary for the ops team.", "Internal agenda for the planning call.") and confidential content nouns outside its class ("Confidential workbook, not for buyers.", "Confidential plan, keep it off the sales page.").
- N-2 loss-threat verbs and objects (validator: D1-COPY-FALSE-LOSS-OF-PURCHASE). Still passing at the ruling date: loss verbs outside the list ("Pass and we pull what you purchased.", "Walk away and we shred the program you bought."), bought-object nouns outside the object lists ("Decline and your subscription gets cut off.", "Skip this and your membership will be terminated."), the passive wiped form on a named bought item ("Say no and the course you bought gets wiped."), and the paid-for object form ("Decline and you will lose the access you already paid for.").

Backstop: this checklist (S81-07), executed by a person against the actual page at installed proof, is the control that catches what the machine screen misses in these three families. Whoever runs this checklist at installed proof re-reads this limitation first and reads the page copy with these families in mind; a validator pass alone does not clear scarcity wording, private labels, or loss wording for D1.

Separate from this limitation, and not accepted as flagged: the contracted-negation false positive recorded by the round 3 re-review ("You won't lose what you bought with us." flagged as a loss threat) was a bug, and it was fixed under the same ruling (validators/validate_downsell.py: the _loss_scan_text contraction repair and the negation guard). Only the coverage boundary above is accepted; reassurance wording is not.

## Verdict rule

Any failure on money, entitlement, consent, source method, or branch behavior is an automatic fail regardless of aesthetic scores (spec 11 section 10). Doc 16 section 8 carries its own enumerated automatic-fail list (wrong product or price, concealed recurring charge, unapproved landing price, invented proof/scarcity, wrong tenant, leaked secrets/customer data, broken native pay/form action, forged success, incorrect entitlement, missing required route, new pitch on final thank-you, self-review as independent); the D1-applicable entries are checklist items above, not just a citation. Each applicable criterion at least 8/10, target average 8.5, from an independent reviewer who is never the author.
