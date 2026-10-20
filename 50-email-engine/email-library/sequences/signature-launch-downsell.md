---
id: signature-launch-downsell
type: sequence
name: Signature Launch Downsell Profile
tags: [sequence, signature-launch, signature-launch-profile, downsell, declined-offer, smaller-option, face-saving, risk-reduction, incremental-commitment, foot-in-door, value-recalibration, future-opportunity, pas, before-after-bridge, aida, paired-variants, founder-signature, launch-brief-intake, draft-only-handoff]
length: 150-300 words
best_for: [downsell, post-decline, signature-launch-builds, smaller-entry-offer, warm-lists]
---

## Style / Definition
The **downsell profile** of the Email Engine: three short, honest emails that run after a contact says no. The job is not to re-argue the declined offer — it is to offer the **smaller option** bound to that approved downsell page, as a right-sized first step. The sequence is instantiated **once per downsell page**: each instance sells exactly one smaller option and points only at that page. It rides the same launch contract as the other Signature Launch profiles: intake from the approved shared-launch brief (never a second questionnaire), paired subject/preview variants, a profile-fixed two-preview rule, review-document labels that never reach the recipient, and a draft-only handoff. This is a profile of the existing engine, not a second engine.

## Purpose & Intention
A "no" is usually a no to the size of the commitment, not to the problem. This profile preserves the relationship by accepting the no plainly — face-saving first — then recalibrating value around a smaller entry point and preserving the future opportunity. It never pretends the main offer is still on the table, never invents a deadline to force a decision, and never guilts the reader. The smaller option must be a real approved option on that downsell page; if the brief has none for a page, that page gets no downsell instance.

## The Phase Map (fixed — no deviation)
| Phase | Emails | Job |
|---|---|---|
| After no | E1 | Accept the no, name the reason the smaller option exists, and point at the downsell page |
| Recalibrate | E2 | Value recalibration: the right-sized first step versus staying where they are, with risk reduced and proof only where the brief supplies it |
| Future opportunity | E3 | Preserve the future opportunity and make one honest last ask; a deadline appears only when the brief supplies one |

## The E1–E3 Framework Map (fixed — no deviation)
| # | Framework | Source Material / Rule |
|---|-----------|------------------------|
| 1 | P.A.S. | Problem (the real reason for the no — budget, timing, or commitment), Agitate (what staying stuck costs), Solution (the smaller option on this downsell page). Face-saving, never argumentative |
| 2 | Before-After-Bridge | Before (same problem at the current commitment level), After (the smaller first step actually taken), Bridge (the downsell page). Incremental commitment, risk reduction |
| 3 | AIDA | Attention on the smaller entry point, Interest (what it includes from the brief), Desire (future-opportunity preservation), Action (the downsell page). Deadline only when the brief supplies one |

## Profile Rules (on top of the shared sequence rules)
1. **One instance per downsell page.** The instance is bound to exactly one approved downsell page and the smaller option attached to it. The three emails never mix pages, never upsell to a larger offer, and never quietly re-offer the declined main offer. If two downsell pages exist, they are two instances with their own facts, prices, and links.
2. **Accept the no first.** E1 opens by acknowledging the decline without arguing with it. No guilt, no "you were wrong", no re-pitch of the declined offer, no implying the reader cannot afford the main offer. The smaller option is framed as a right-sized first step, and declining it too is accepted plainly.
3. **Two subjects, two previews, as PAIRS.** Every email carries Pair A (subject A + preview A) and Pair B (subject B + preview B). Pair B is prolific and disruptive but truthful and on brand: no false account alert, no fake reply prefix, no fabricated urgency, no fake scarcity, no misleading price. The pairing is preserved through the draft handoff; it is never flattened into an unpaired preview list.
4. **Word band 150–300** for every email. A different exact length is honored only through the existing locked-brief override channel, recorded as an override.
5. **Truthful deadline only.** Urgency may come from a real deadline the brief supplies for that downsell page (for example the launch close). If the brief supplies none, E3 asks plainly with no deadline, no countdown, and no "last chance".
6. **Prices, links, and what is included come from the approved brief and the approved downsell page.** No invented price, no invented inclusion, no expired one-click link, no second-offer (U2) sale. Every CTA points at that page for the current approved offer version.
7. **No fabricated proof.** Testimonials, results, member counts, and revenue figures appear only when the brief carries the evidence. Otherwise the copy uses a clearly hypothetical illustration or a proof-free truthful variant.
8. **Stop rules.** A purchase of the main offer, the smaller option, or any later upsell stops the sequence at once and moves the contact to access/welcome and the next follow-up. A second decline ends the sequence with no further promotional send.
9. **The objective is `downsell`.** The frozen objective enum already carries it; no lane file widens the enum.
10. **Labels live in the review document only.** The private client-review document labels each email with its framework and labels the body "Email Body:". The recipient payload is clean: no framework labels, no slot instructions, no production commentary.
11. **Founder's ACTUAL name** in every closing signature, from the brief. No placeholder ever ships.
12. **Draft-only, always.** The profile produces plans and drafts. The build-plan handoff to Skill 44 carries `draft_only=true`, the profile name, the downsell page id, approved content hashes, the variant-pairing strategy, enrollment timing, and stop/suppression rules, and never any credential. This profile never sends.

## Registration Note (for the integrator — a lane file cannot do this)
The profile is authored as a file pair only. It is **not** in `catalog-index.json` / `catalog-built-index.json`, and `prove-email.py` does not yet know `signature_launch_downsell` in `SEQ_LENGTHS`, `PREVIEW_EXPECTED`, or `_sequence_type`. Until those shared files are updated by the integrator, a run resolving this `sequence_type` fails `AF-EMAIL-TYPE-MISMATCH` by design. `register.py --check` keeps its frozen 36-entry census, so adding this pair alone does not change or break it.

## Use Cases
- The email leg that follows a decline of the main launch offer, offering the approved smaller option
- The email leg that follows a decline of an upsell, offering that page's smaller option
- Re-engagement of a list that passed on a previous launch, using the approved facts with refreshed copy

## Detailed Example
Below: **Email 1 of 3** in full (P.A.S. after-no email), demonstrating the complete format contract including the paired B-set.

**Email 1 — Framework: P.A.S. (After No)**

**Subject Line A:** You said no. That was a fair call, {{contact.first_name}}.
**Subject Line B:** The door you didn't walk through is still a door.

**Preview Text A:** No argument, no re-pitch — just the smaller way in.
**Preview Text B:** The full build wasn't the only way to start. Here's the other one.

**Email Body:**

{{contact.first_name}},

You looked at [approved main offer from the brief] and said no. Fair enough — the timing, the budget, or the size of the commitment wasn't right for you. I'm not going to argue with that, and I'm not going to pretend the no didn't happen.

But I'd be a poor host if I let you leave thinking the only way in was the full build.

There is a smaller option: [approved smaller option from this downsell page — name and one line on what it is]. It exists for exactly the reason you passed — to start with something right-sized instead of waiting for the perfect moment, which is usually a moment that never comes.

What staying where you are actually costs: another [approved time unit from the brief] of the same problem, the same workaround, and the same result you already know. The smaller option doesn't fix everything the full build does. It does get you moving with less risk and less outlay.

You can see exactly what it includes, what it costs, and what it doesn't do here:

**[See the smaller option →]**

If it's still not right, that's a real answer too. No follow-up pressure from me.

[Founder Name]

*(Engine note: substitute the founder's actual name; the destination is that downsell page; every price, inclusion, and time unit comes from the approved brief; word count 150–300, two subject lines, two previews, ≥1 CTA verified.)*

## Quality Checklist
- [ ] Resolved by name as `signature_launch_downsell`; intake consumed from the approved launch brief with provenance (no second interview)
- [ ] One instance bound to exactly one downsell page and its smaller option; no page mixing, no larger upsell, no re-offer of the declined main offer
- [ ] All 3 emails present; frameworks match the E1–E3 map exactly; phases run after no → recalibrate → future opportunity
- [ ] E1 accepts the no without guilt or argument; declining the smaller option is accepted plainly
- [ ] Every CTA points at the matching downsell page; price, inclusions, and link match the current approved offer version
- [ ] A deadline appears only when the brief supplies one; no invented urgency, countdown, or scarcity
- [ ] Every email 150–300 words; any other length is a recorded locked-brief override
- [ ] Every email: Pair A and Pair B subject+preview, explicitly paired; Pair B disruptive and truthful
- [ ] No fabricated proof; testimonials only when the brief carries the evidence
- [ ] Stop rules carried into the handoff: purchase stops the sequence; second decline ends it
- [ ] Review document carries framework labels and "Email Body:" labels; recipient payload carries none of them
- [ ] Founder's ACTUAL name in every signature, zero placeholders
- [ ] Handoff is draft-only with content hashes, page id, and stop/suppression rules; no credentials, nothing sent
