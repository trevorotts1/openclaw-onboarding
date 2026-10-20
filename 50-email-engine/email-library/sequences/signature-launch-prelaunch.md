---
id: signature-launch-prelaunch
type: sequence
name: Signature Launch Pre-Launch Profile
tags: [sequence, signature-launch, signature-launch-profile, pre-launch, teaser, value, doors-soon, waitlist, opt-in, star-chain-hook, pastor-story, features-to-benefit, before-after-bridge, pas, paired-variants, founder-signature, launch-brief-intake, draft-only-handoff]
length: 150-300 words
best_for: [pre-launch, signature-launch-builds, waitlist-growth, warm-lists, doors-open-anticipation]
---

## Style / Definition
The **pre-launch profile** of the Email Engine: five short, honest emails that run before a Signature Launch opens. Three phases, in order — **teaser → value → "doors open soon"** — and every email points at the **opt-in / waitlist page**, never at a checkout. It rides the same launch contract as the other Signature Launch profiles: intake from the approved shared-launch brief (never a second questionnaire), paired subject/preview variants, a profile-fixed two-preview rule, review-document labels that never reach the recipient, and a draft-only handoff. This is a profile of the existing engine, not a second engine.

## Purpose & Intention
A launch sells twice: once to the list that hears about it early, once to everyone who finds out the day the doors open. This profile builds the first list. It earns the opt-in before there is anything to buy — a named promise, a reason to care, one piece of real value, and a truthful "the doors open soon" — so that the main launch 10 lands on people who already asked to be there. Nothing here is urgent unless the brief says it is urgent, and nothing here promises a result.

## The Phase Map (fixed — no deviation)
| Phase | Emails | Job |
|---|---|---|
| Teaser | E1 | Announce that something is being built, name the promise in one line, and ask for the early seat |
| Value | E2–E4 | Give the story, the mechanism, and the before/after — each email stands alone and asks for the same opt-in |
| Doors soon | E5 | Say plainly that the doors open soon, state only the dates the brief supplies, and send them to the opt-in page |

## The E1–E5 Framework Map (fixed — no deviation)
| # | Framework | Source Material / Rule |
|---|-----------|------------------------|
| 1 | Star-Chain-Hook | Teaser: one-line promise from the approved brief, the not-yet-open fact, the waitlist ask. No mechanism reveal yet |
| 2 | P.A.S.T.O.R. Story | The founder/offer story from the brief; the Why (landing Section 5) is woven in, never restated as a slogan |
| 3 | Features-to-Benefit | The offer's features from the brief translated into what the reader gets; no unapproved feature is invented |
| 4 | Before-After-Bridge | The honest contrast: where the reader is now, where the offer is designed to take them, the bridge is the opt-in |
| 5 | P.A.S. | Doors-open-soon: the problem the launch addresses, what waiting costs, the opt-in as the action. Deadline stated only when the brief supplies it |

## Profile Rules (on top of the shared sequence rules)
1. **Two subjects, two previews, as PAIRS.** Every email carries Pair A (subject A + preview A) and Pair B (subject B + preview B). Pair B is prolific and disruptive but truthful and on brand: no false account alert, no fake reply prefix, no fabricated urgency, no fake scarcity, no misleading price. The pairing is preserved through the draft handoff; it is never flattened into an unpaired preview list.
2. **The destination is the opt-in / waitlist page.** Every CTA in all five emails points there. No checkout link, no price page, no sales-page CTA before doors open. If the brief marks a segment as already opted in, the same emails point at the waitlist confirmation instead — the sequence never re-asks for an opt-in the contact already gave.
3. **Word band 150–300** for every email. A different exact length is honored only through the existing locked-brief override channel, recorded as an override.
4. **Timing is relative and truthful.** E1 at announcement, E2–E4 spaced across the pre-launch window, E5 on the day before doors open. Every date, deadline, or countdown in the copy comes from the launch calendar in the approved brief. If the brief has no calendar, E5 says "doors open soon" and names no date.
5. **No fabricated proof.** Testimonials, results, member counts, and revenue figures appear only when the brief carries the evidence. Otherwise the copy uses a clearly hypothetical illustration or a proof-free truthful variant.
6. **The objective is `promotional`.** The frozen objective enum has no pre-launch value; this profile defaults to promotional, and no lane file widens the enum.
7. **Labels live in the review document only.** The private client-review document labels each email with its framework and labels the body "Email Body:". The recipient payload is clean: no framework labels, no slot instructions, no production commentary.
8. **Founder's ACTUAL name** in every closing signature, from the brief. No placeholder ever ships.
9. **Draft-only, always.** The profile produces plans and drafts. The build-plan handoff to Skill 44 carries `draft_only=true`, the profile name, approved content hashes, the variant-pairing strategy, the launch calendar, and stop/suppression rules, and never any credential. This profile never sends.

## Registration Note (for the integrator — a lane file cannot do this)
The profile is authored as a file pair only. It is **not** in `catalog-index.json` / `catalog-built-index.json`, and `prove-email.py` does not yet know `signature_launch_prelaunch` in `SEQ_LENGTHS`, `PREVIEW_EXPECTED`, or `_sequence_type`. Until those shared files are updated by the integrator, a run resolving this `sequence_type` fails `AF-EMAIL-TYPE-MISMATCH` by design. `register.py --check` keeps its frozen 36-entry census, so adding this pair alone does not change or break it.

## Use Cases
- The email leg that runs before a Signature Launch doors-open date
- Waitlist or early-access builds ahead of a new offer
- Re-activation of a past buyer list before a re-launch of the same offer, using the approved facts with refreshed copy

## Detailed Example
Below: **Email 1 of 5** in full (Star-Chain-Hook teaser), demonstrating the complete format contract including the paired B-set.

**Email 1 — Framework: Star-Chain-Hook (Teaser)**

**Subject Line A:** Something is being built for you, {{contact.first_name}}
**Subject Line B:** We've been quiet. Here's the first twenty seconds of why.

**Preview Text A:** A door that isn't open yet — and why you'll want the first seat.
**Preview Text B:** Everyone will meet the offer. The list meets it first.

**Email Body:**

{{contact.first_name}},

Three months ago [Founder Name] wrote one sentence on a whiteboard: [approved one-line promise from the brief].

Today that sentence has a name, a date, and a room full of work behind it. Nothing is for sale yet. No link to buy, no countdown, no cart.

That's on purpose.

Here's what we can tell you now:
- **What it is:** [approved offer one-liner from the brief]
- **Who it's for:** [approved audience from the brief]
- **When the doors open:** [launch date — only if the brief supplies it]

Here's what we're not telling you yet: the mechanism. The part that makes this different from every other [category] you've tried. That comes next — to this list first.

If you want the full story before the doors open, including the early-entry window, get on the list now:

**[Put me on the early list →]**

This list is the only place the announcement lands first. Everyone else meets the offer the day the doors open. You'll already know what it is and why it matters.

[Founder Name]

*(Engine note: substitute the founder's actual name; the opt-in destination is the approved opt-in / waitlist page; word count 150–300, two subject lines, two previews, ≥1 CTA verified.)*

## Quality Checklist
- [ ] Resolved by name as `signature_launch_prelaunch`; intake consumed from the approved launch brief with provenance (no second interview)
- [ ] All 5 emails present; frameworks match the E1–E5 map exactly; phases run teaser → value → doors soon
- [ ] Every CTA points at the opt-in / waitlist page; no checkout, price page, or sales-page CTA before doors open
- [ ] E1 withholds the mechanism but names the approved promise and audience; E5 states a date only when the brief supplies one
- [ ] Every email 150–300 words; any other length is a recorded locked-brief override
- [ ] Every email: Pair A and Pair B subject+preview, explicitly paired; Pair B disruptive and truthful
- [ ] No fabricated proof, scarcity, deadline, or result; testimonials only when the brief carries the evidence
- [ ] Review document carries framework labels and "Email Body:" labels; recipient payload carries none of them
- [ ] Founder's ACTUAL name in every signature, zero placeholders
- [ ] Handoff is draft-only with content hashes, launch calendar, and stop/suppression rules; no credentials, nothing sent
