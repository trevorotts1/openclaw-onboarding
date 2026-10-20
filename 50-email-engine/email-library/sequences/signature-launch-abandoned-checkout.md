---
id: signature-launch-abandoned-checkout
type: sequence
name: Signature Launch Abandoned-Checkout Recovery Profile
tags: [sequence, signature-launch, signature-launch-profile, abandoned-checkout, abandoned-cart, cart-recovery, checkout-recovery, order-recovery, zeigarnik-effect, loss-aversion, cognitive-dissonance, trust, reciprocity, three-b-plan, pas, before-after-bridge, per-buyer-type-tactics, timing-1-3-hours, founder-signature, launch-brief-intake, draft-only-handoff]
length: <150 words
best_for: [abandoned-cart, abandoned-checkout, signature-launch-builds, checkout-recovery, ecommerce, warm-lists, buyer-type-segmented-lists]
---

## Style / Definition
The **abandoned-checkout profile** of the Email Engine: three short, truthful emails that recover an order the buyer already started. It uses the existing `objective-abandoned-cart` triggers — **loss aversion, cognitive-dissonance resolution, the Zeigarnik effect, trust/risk reduction, and reciprocity** — and the objective's fixed recovery arc: **completion reminder → objection handling → incentive or honest last call**. Every email returns the buyer to the **same approved checkout page** for the same approved offer version. It rides the same launch contract as the other Signature Launch profiles: intake from the approved shared-launch brief (never a second questionnaire), a profile-fixed one-preview rule, review-document labels that never reach the recipient, and a draft-only handoff. This is a profile of the existing engine, not a second engine.

## Purpose & Intention
An abandoned checkout is the warmest cold moment in a launch: desire was proven, then interrupted. The buyer is living a small contradiction — "I wanted this / I did not buy it" — and that contradiction wants resolution. This profile resolves it toward completion while the decision is still open: the first email lands inside the **1-3 hour** window, the second answers the real objection, and the third makes one honest final offer or closes the loop. It never pretends the buyer is a new lead, never re-pitches from zero, and never fabricates urgency to force the decision.

## The Recovery Arc (fixed — no deviation)
| Phase | Email | Timing | Job |
|---|---|---|---|
| Reminder | E1 | 1-3 hours after abandonment | Frame the order as an almost-done task; name the exact item left behind; one-click finish |
| Objection | E2 | ~24 hours after abandonment | Resolve the likely hesitation — price, security, fit, unanswered question; trust and risk reduction |
| Last call | E3 | ~48-72 hours after abandonment | Honest last call; an incentive only if the approved offer version carries one; otherwise a clear close |

## The E1-E3 Framework Map (fixed — no deviation)
| # | Framework | Source Material / Rule |
|---|-----------|------------------------|
| 1 | The 3-B Plan | **Brevity, Blunt, Basic.** Pure completion reminder. Name the specific abandoned item and affirm the original buying judgment. Short by design |
| 2 | P.A.S. | The real objection: Problem (why the order stopped), Agitate (what staying undecided costs), Solution (the answer, guarantee, support link, or FAQ) |
| 3 | Before-After-Bridge | Contrast: the unfinished order now, the completed outcome after checkout, the checkout page as the bridge. An incentive appears here only when the approved offer version carries one |

## Profile Rules (on top of the shared sequence rules)
1. **Timing is doctrine.** E1 sends within **1-3 hours** of abandonment, E2 around **24 hours**, E3 around **48-72 hours**. Every stated deadline, countdown, price, or scarcity fact comes from the approved offer version in the brief. If the brief supplies no deadline, the copy states none.
2. **Frame as completion, not promotion (Zeigarnik).** "You are one step from done" and "everything is saved" — never "come back and shop." The task is almost complete; the email offers the last step.
3. **Make loss aversion concrete.** Name the specific item, tier, bonus, or price the buyer left behind. "Your cart" is abstract; the exact selection is a possession about to slip away.
4. **Affirm the original judgment.** "You picked it for a reason." Help the buyer re-access why they wanted it; never imply they were wrong to hesitate.
5. **Hunt the real objection.** Most abandonment is hesitation, not rejection. E2 answers the likely blocker with a guarantee, security signal, support link, FAQ line, or a real human reply path from the approved brief.
6. **Reciprocity before discounts.** Give help first. A discount appears only in E3 and only when the approved offer version carries one. Never train the list to abandon on purpose with a reflex discount.
7. **Sequence, do not repeat.** Each email has a distinct job and stands alone; the three never contradict each other and never restate the same paragraph in new clothes.
8. **Tactics follow the buyer type.** Use the approved buyer-type signal when the brief carries one: spontaneous (fast, friction-free, Zeigarnik + loss aversion), methodical (objection and trust, no pressure), humanistic (real check-in and help, reciprocity + trust), competitive (what waiting costs, only with approved facts).
9. **One preview line, two subject lines.** Every email carries subject A and subject B with one shared preview, under 100 characters. The shared preview must be truthful for both subject variants.
10. **Word band: under 150 words** per email. Recovery copy is compact by design. A different exact length is honored only through the existing locked-brief override channel, recorded as an override.
11. **The destination is the checkout page.** Every CTA returns to the same approved checkout page for the current approved offer version. No sales page, no waitlist, no new offer, no expired one-click link.
12. **Suppression is absolute.** A verified purchase, an active order for the same offer, or an opt-out suppresses every remaining email immediately. A pending or failed payment is not a decline; it belongs to the failed-payment lane, never this profile.
13. **Labels live in the review document only.** The private client-review document labels each email with its framework and labels the body "Email Body:". The recipient payload is clean: no framework labels, no slot instructions, no production commentary.
14. **Founder's ACTUAL name** in every closing signature, from the brief. No placeholder ever ships.
15. **Draft-only, always.** The profile produces plans and drafts. The build-plan handoff to Skill 44 carries `draft_only=true`, the profile name, approved content hashes, enrollment and timing anchors, stop/suppression rules, and never any credential. This profile never sends.

## Per-Buyer-Type Tactics
| Buyer type | Tactics | Trigger emphasis |
|---|---|---|
| Spontaneous | Fastest send in the window; friction-free "finish in one click"; countdown framing only with a real approved deadline | Zeigarnik + loss aversion |
| Methodical | Answer the unspoken objection; guarantee, security signals, FAQ or support link; no pressure | Trust / risk reduction |
| Humanistic | "Did something come up?" human check-in; offer real help from a real person | Reciprocity + trust |
| Competitive | What they lose by waiting; price protection or stock claim only when the approved offer version supplies it | Loss aversion, status-coded |

## Registration Note (for the integrator — a lane file cannot do this)
The profile is authored as a file pair only. It is **not** in `catalog-index.json` / `catalog-built-index.json`, and `prove-email.py` does not yet know `signature_launch_abandoned_checkout` in `SEQ_LENGTHS`, `PREVIEW_EXPECTED`, or `_sequence_type`. The shared prover also applies its default 150-300 word band (3-B under 150), so this profile's compact **under 150** band is not modeled yet. Until the integrator registers the profile and its band, a run resolving this `sequence_type` fails `AF-EMAIL-TYPE-MISMATCH` by design. `register.py --check` keeps its frozen 36-entry census, so adding this pair alone does not change or break it.

## Use Cases
- The recovery leg of a Signature Launch, after the checkout page and offer version are approved
- Course, program, coaching, or event enrollment started but not completed
- Application or booking forms left mid-flow
- Any measurable "started yes, did not finish" moment that returns to an approved checkout page

## Detailed Example
Below: **Email 1 of 3** in full (The 3-B Plan, completion reminder), demonstrating the complete format contract.

**Email 1 — Framework: The 3-B Plan (Completion Reminder)**

**Subject Line A:** {{contact.first_name}}, your [approved offer name] is still saved in checkout
**Subject Line B:** One step from done, {{contact.first_name}} — nothing was lost

**Preview Text:** We saved everything exactly as you left it. One click finishes the order.

**Email Body:**

{{contact.first_name}},

Quick one — **the [approved offer name] is still saved in your checkout,** exactly as you left it.

You picked it for a reason. One click finishes the order:

**[Finish my order →]**

If a question stopped you, reply and a real person will answer. [Approved guarantee or support line — include only when the brief supplies one.]

[Founder Name]

*(Engine note: substitute the founder's actual name and the approved offer name; the CTA destination is the approved checkout page; under 150 words, two subject lines, one preview, at least one CTA verified.)*

## Quality Checklist
- [ ] Resolved by name as `signature_launch_abandoned_checkout`; intake consumed from the approved launch brief with provenance (no second interview)
- [ ] All 3 emails present; frameworks match the E1-E3 map exactly; the arc runs reminder → objection → last call
- [ ] E1 sends within 1-3 hours of abandonment; E2 around 24 hours; E3 around 48-72 hours
- [ ] Every email frames the order as an almost-done task and names the specific abandoned item
- [ ] E1 affirms the original buying judgment; E2 answers the likely objection; E3 is an honest last call
- [ ] Reciprocity or help comes before any discount; a discount appears only in E3 and only when the approved offer version carries one
- [ ] Every CTA returns to the same approved checkout page for the current approved offer version
- [ ] Tactics match the approved buyer-type signal; no fabricated scarcity, deadline, price, or proof
- [ ] Every email: two subject lines and one shared preview under 100 characters
- [ ] Every email under 150 words; any other length is a recorded locked-brief override
- [ ] Verified purchase, active order, or opt-out suppresses the remaining emails immediately; pending/failed payment routes to the failed-payment lane
- [ ] Review document carries framework labels and "Email Body:" labels; recipient payload carries none of them
- [ ] Founder's ACTUAL name in every signature, zero placeholders
- [ ] Handoff is draft-only with content hashes, timing anchors, and stop/suppression rules; no credentials, nothing sent
