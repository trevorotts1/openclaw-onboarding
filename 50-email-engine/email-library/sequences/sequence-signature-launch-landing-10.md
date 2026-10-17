---
id: sequence-signature-launch-landing-10
type: sequence
name: Signature Launch Landing-Page 10-Email Profile
tags: [sequence, signature-launch, signature-launch-profile, landing-page, promo, ten-emails, pastor-solutions, pain-points, big-bold-who, big-bold-why, features-to-benefit, six-ws, before-after-bridge, three-b-plan, million-dollar-sales, aida, pas, paired-variants, ab-split-test, disruptive-subject-lines, founder-signature, launch-brief-intake, draft-only-handoff]
length: 150-300 words
best_for: [promotional, signature-launch-builds, signature-landing-page-clients, warm-lists, full-launch-builds]
---

## Style / Definition
The **named Signature Launch profile** of the Email Engine: the ten-email promotional sequence for a Signature Landing Page, produced inside a Signature Launch build. It rides the exact framework map of the landing-page promo sequence, and adds the launch contract on top of it: intake from the approved shared-launch brief (never a second questionnaire), explicit subject/preview variant pairs, a profile-fixed two-preview rule, review-document labels that never reach the recipient, and a draft-only handoff the Skill-44 consumer can build from.

This profile is a profile of the existing engine, not a second engine. The generic `landing_page_10` sequence and every legacy profile (Convert & Flow buyer-type 12 with its one-preview default, high-ticket 12) keep their own behavior unchanged.

## Purpose & Intention
A Signature Launch produces the landing page, the offer route, and the approvals in one governed build. The email sequence must consume those approved facts (the three Section 6 pain points, the refined Section 5 Why, the Section 8-10 offer details, the founder's actual name, the approved offer version) instead of re-interviewing the client or inventing facts at copy time. The profile exists so that a launch run resolves ONE named contract by name, and every rule below is a property of that contract, not a habit of whoever runs it.

## The E1-E10 Framework Map (fixed, no deviation)
| # | Framework | Source Material / Rule |
|---|-----------|------------------------|
| 1 | P.A.S.T.O.R. V1 (Solutions) | Pain point 1 from landing Section 6 ("Big Bold Who") |
| 2 | P.A.S.T.O.R. V1 (Solutions) | Pain point 2 from Section 6 (a DIFFERENT pain than E1) |
| 3 | P.A.S.T.O.R. V1 (Solutions) | Pain point 3 from Section 6 (a DIFFERENT pain than E1/E2) |
| 4 | Features-to-Benefit | Built from landing sections 8, 9 & 10 |
| 5 | The 6 W's | Full-information email; the When is stated only when the brief supplies it |
| 6 | Before-After-Bridge | Contrast email; possibility, never a guaranteed result |
| 7 | The 3-B Plan | **The short email**, the one exception to the word band |
| 8 | Million Dollar Sales | Full 12-part structure, exactly 3 CTAs, humorous P.S. |
| 9 | AIDA | Attention, Interest, Desire, Action, in order |
| 10 | PAS | Problem, Agitate, Solution, in order |

## Profile Rules (on top of the shared sequence rules)
1. **Two subjects, two previews, as PAIRS.** Every email carries Pair A (subject A + preview A) and Pair B (subject B + preview B). They are two testable pairs, not four loose messages. Pair B is prolific and disruptive but truthful and on brand: no false account alert, no fake reply prefix, no fabricated urgency, no offensive language, no misleading price. The pairing is preserved through the draft handoff; it is never flattened into an unpaired preview list.
2. **The two-preview rule belongs to the profile.** It is encoded in this profile and its locked brief, and in the floor prover's expectation for `signature_launch_landing_10`. A preview-count override cannot lower it, even when logged in a locked brief, and the Convert & Flow one-preview default never applies to this profile.
3. **Intake is the approved launch brief.** Audience pains, founder name, brand voice, landing sections, and offer facts arrive from the S49 shared-launch interview with provenance. This profile never re-asks the legacy one-block questionnaire after the shared interview, and never fabricates `answered=true` flags. The legacy questionnaire survives only in explicit legacy interactive mode.
4. **Word band 150-300** for every email except E7 (3-B Plan, shorter by design). A different exact length is honored only through the existing locked-brief override channel, recorded as an override.
5. **PASTOR slots E1-E3:** at least 3 CTAs each (beginning, middle, end), each email owns its own Section 6 pain point, the landing page's Why (Section 5) is woven into the story, and a testimonial is described as a real happy customer only when testimonial evidence exists in the brief; otherwise a clearly hypothetical illustration or a proof-free truthful variant.
6. **Labels live in the review document only.** The private client-review document labels each email with its framework and labels the body "Email Body:". The recipient payload is clean: no framework labels, no slot instructions, no production commentary.
7. **Founder's ACTUAL name** in every closing signature, from the brief. No placeholder ever ships.
8. **Offer consistency.** Every CTA points at the approved landing/offer destination for the current approved offer version. Price, benefit, deadline, and promise match that version. No unapproved second-offer (U2) sale, no expired one-click link.
9. **Draft-only, always.** The profile produces plans and drafts. The build-plan handoff to Skill 44 carries `draft_only=true`, the profile name, approved content hashes, the variant-pairing strategy, enrollment and timing rules, and stop/suppression rules, and never any credential. This profile never sends.

## Use Cases
- The email leg of a Signature Launch build (the standard path)
- Re-promotion of a launch offer using the same approved facts with refreshed copy
- Any landing-page promo run that must be provable against the launch approvals rather than a standalone brief

## Detailed Example
The format contract is identical to the landing-page promo record's worked example (framework label, labeled A/B subject and preview pairs, "Email Body:" label, founder signature). The golden example set for THIS profile is the profile-bound golden set under `examples/` (ten emails on this exact map, with broken variants), which is the artifact acceptance runs against; no separate example copy is duplicated into this record, so the record and the golden set can never drift apart.

## Quality Checklist
- [ ] Resolved by name as `signature_launch_landing_10`; intake consumed from the approved launch brief with provenance (no second interview)
- [ ] All 10 emails present; frameworks match the E1-E10 map exactly
- [ ] E1-E3 each own a DIFFERENT Section-6 pain point; at least 3 CTAs each (beginning / middle / end); Section 5 Why woven in; testimonial claims backed by brief evidence or clearly hypothetical
- [ ] E4 built from landing sections 8, 9 & 10; E5 states a When only when the brief supplies one; E8 carries the full 12-part structure with exactly 3 CTAs and a humorous P.S.
- [ ] Every email 150-300 words EXCEPT E7 (shorter); any other length is a recorded locked-brief override
- [ ] Every email: Pair A and Pair B subject+preview, explicitly paired; Pair B disruptive and truthful
- [ ] Review document carries framework labels and "Email Body:" labels; recipient payload carries none of them
- [ ] Founder's ACTUAL name in every signature, zero placeholders
- [ ] CTAs, price, deadline, and promise match the current approved offer version; handoff is draft-only with content hashes and no credentials
