# Golden set — `golden-signature-launch-10` (FICTIONAL FIXTURE)

The golden ten-email set for the named Signature Launch profile
`signature_launch_landing_10` (Skill 50 Email Engine). This is the artifact
acceptance runs against for the profile; the matching broken variants live in
`../broken-signature-launch-10/` with their observed rejection results.

**Fictional fixture.** Founder "Jordan Marsh" and the offer "The Momentum
Method" are invented, the same fictional world as `../golden-landing-10/`.
No real person, offer, customer, or result is described. The fixture supplies
NO testimonial evidence (see `landing-facts.json`), so the PASTOR stories are
written as clearly hypothetical illustrations ("Picture a builder who..."),
never as named happy customers, per spec 13 section 4.

## Files
- `emails.json` — the sequence ledger: `sequence_type` `signature_launch_landing_10`,
  `sequence_id` `sequence-signature-launch-landing-10`, ten emails on the exact
  LANDING_MAP (PASTOR x3, Features-to-Benefit, 6 W's, Before-After-Bridge,
  3-B Plan, Million Dollar Sales, AIDA, PAS), a signed process certificate,
  and `deploy_requested` for the DRAFT-ONLY Skill-44 handoff. Nothing sends.
- `brief.json` — the intake brief in the landing golden brief's shape, with
  `sequence_position` `signature-launch-landing-10`.
- `landing-facts.json` — the fixture landing page facts the copy is built
  from: Section 5 Why, the three Section 6 pains (refs
  `landing.section6.pain.1/.2/.3`, one per PASTOR email), the Section
  8/9/10 offer details Email 4 is built from (`source_sections: [8, 9, 10]`),
  and the one approved round-timing fact (`landing.offer.round_timing`:
  rolling thirty-day rounds; the next round begins on a Monday and
  enrollment for it closes the Thursday before) that every deadline line
  in the set traces to.

## Profile contract visible in this set
- Exactly 2 subjects and 2 previews per email, as Pair A / Pair B (Pair B is
  the prolific, disruptive, truthful variant). `merge_fallback` is declared
  wherever the first-name merge field is used.
- `sections[]` on every email, in the framework's canonical part order
  (PASTOR 6, Features-to-Benefit chains, 6 W's, BAB, 3-B exactly 3,
  Million Dollar Sales exactly 12 beats, AIDA, PAS).
- PASTOR emails carry at least 3 CTAs, placed beginning / middle / end of the
  body (first within the first half of body words, last inside the final
  quarter), each owning a distinct `pain_ref`.
- Email 5 carries `when_provenance: "brief"` and a declared `deadline`
  ("Thursday"), and its When states exactly the approved round-timing
  fact: the rounds keep rolling, the next round begins Monday, and
  enrollment for it closes the Thursday before. Every deadline line in
  the other nine emails traces to that same single fact; nothing beyond
  it (no reopening scarcity, no last-chance claims) appears anywhere.
- Email 7 is the deliberate short exception (under 150 words). Email 8 carries
  exactly 3 CTAs and a humorous P.S.
- Every body closes with the founder's actual fixture name. No placeholders.

## Prove it
```bash
python3 tools/prove-email.py examples/golden-signature-launch-10/emails.json --brief examples/golden-signature-launch-10/brief.json
# RESULT: PASS, exit 0
python3 tools/prove-email.py examples/golden-signature-launch-10/brief.json
# RESULT: PASS, exit 0 (intake gate)
```
