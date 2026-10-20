---
id: signature-launch-welcome-access
type: sequence
name: Signature Launch Welcome / Access Profile
tags: [sequence, signature-launch, signature-launch-profile, welcome-access, post-purchase, access, receipt, next-steps, onboarding, transactional, six-ws, before-after-bridge, paired-variants, founder-signature, launch-brief-intake, draft-only-handoff]
length: 150-300 words
best_for: [post-purchase, welcome-access, signature-launch-builds, access-delivery, receipt-and-next-steps]
---

## Style / Definition
The **welcome / access profile** of the Email Engine: two operational emails that run the moment a Signature Launch purchase clears. They do one job — hand the buyer their access, their receipt, and their first next step — and they end on access and thank-you, not on a pitch. It rides the same launch contract as the other Signature Launch profiles: intake from the approved shared-launch brief (never a second questionnaire), paired subject/preview variants, a profile-fixed one-preview rule, review-document labels that never reach the recipient, and a draft-only handoff. This is a profile of the existing engine, not a second engine.

## Purpose & Intention
The sale is done. The next email decides whether the buyer ever gets inside. Everything here is operational: the access link, what was charged, what happens next, and a human thank-you. No urgency, no upsell, no manufactured excitement, no offer repeated. A buyer who reads only Email 1 should be able to log in and start; a buyer who reads only Email 2 should know they were not forgotten and should still be able to get in.

## The Phase Map (fixed — no deviation)
| Phase | Emails | Job |
|---|---|---|
| Access + receipt | E1 | Confirm the purchase, deliver access, state the receipt, list the first next steps |
| Next steps + thank-you | E2 | Check the access worked, restate the first step, say thank you — and end on access |

## The E1–E2 Framework Map (fixed — no deviation)
| # | Framework | Source Material / Rule |
|---|-----------|------------------------|
| 1 | Six W's | Who (buyer), what (offer and what is included), when (access start and any live session), where (access page), why (the outcome the buyer bought), how (the first step). Every answer comes from the order record and the approved brief |
| 2 | Before-After-Bridge | Before (purchased, not yet inside), After (the first milestone the offer is designed to reach, in the brief's words), Bridge (the access page and step one). No new promise, no result claim |

## Profile Rules (on top of the shared sequence rules)
1. **Two subjects, one preview, as PAIRS.** Every email carries Pair A (subject A + preview A) and Pair B (subject B + preview B). Pair B is plain and direct: no false account alert, no fake reply prefix, no fake security warning, no fabricated urgency. The pairing is preserved through the draft handoff; it is never flattened into an unpaired list.
2. **Access first, always.** The access link sits in the top third of Email 1, before the receipt and before the next steps. Email 2 restates it and closes on it. One CTA per email, and that CTA is the access page.
3. **The receipt states what happened, nothing more.** Amount charged, currency, plan and next charge only when the order record carries it, order reference. No card digits, no payment token, no password, no credential. The receipt is a record, not a sales surface.
4. **No invented access.** The link comes from the platform or the approved brief. It is never constructed from a guessed URL, never carries a password in the query string, and never asks the recipient to reply with a password. If the brief has no access URL, the email says access details follow from support and names the support address.
5. **Transactional consent.** The receipt and access delivery are transactional: a marketing opt-out does not suppress them. A full refund or cancelled order before the send does. Each email sends at most once per order, and a duplicate purchase event never re-sends an email already delivered.
6. **Word band 150–300** for every email. A different exact length is honored only through the existing locked-brief override channel, recorded as an override.
7. **Timing is relative and truthful.** E1 at payment success, E2 about 24 hours later. Every date, session time, or start date comes from the approved brief and launch calendar. If the brief has no date, the copy names none.
8. **No fabricated proof.** Testimonials, results, member counts, and revenue figures appear only when the approved brief carries the evidence. Operational email prefers none.
9. **The objective is `promotional`.** The frozen objective enum has no welcome/access or transactional value. This profile defaults to promotional and carries no promotional claim; no lane file widens the enum.
10. **Labels live in the review document only.** The private client-review document labels each email with its framework and labels the body "Email Body:". The recipient payload is clean: no framework labels, no slot instructions, no production commentary.
11. **Founder's ACTUAL name** in every closing signature, from the brief. No placeholder ever ships.
12. **Draft-only, always.** The profile produces plans and drafts. The build-plan handoff to Skill 44 carries `draft_only=true`, the profile name, approved content hashes, the variant-pairing strategy, the order-fact fields used, the launch calendar, and stop/suppression rules, and never any credential. This profile never sends.

## Registration Note (for the integrator — a lane file cannot do this)
The profile is authored as a file pair only. It is **not** in `catalog-index.json` / `catalog-built-index.json`, and `prove-email.py` does not yet know `signature_launch_welcome_access` in `SEQ_LENGTHS`, `PREVIEW_EXPECTED`, or `_sequence_type`. Until those shared files are updated by the integrator, a run resolving this `sequence_type` fails `AF-EMAIL-TYPE-MISMATCH` by design. `register.py --check` keeps its frozen 36-entry census, so adding this pair alone does not change or break it.

The launch plan's `email_count` for kind `welcome_access` is authoritative. This profile models the two-email core (2 in the elevation, multi-option and black-friday fixtures). The 7figurepreneur fixture declares 3; a plan that declares 3 needs the integrator to extend the profile first, and the lane never pads an email to reach a count.

## Use Cases
- The post-purchase leg of a Signature Launch, fired on payment success
- Access delivery for a live or recorded event, with the session time taken from the brief
- Re-sending access to a buyer who never opened the first email, as a replay of E2 only

## Detailed Example
Below: **Email 1 of 2** in full (Six W's — access, receipt, next steps), demonstrating the complete format contract including the paired B-set.

**Email 1 — Framework: Six W's (Access + Receipt + Next Steps)**

**Subject Line A:** You're in, {{contact.first_name}} — here's your access
**Subject Line B:** Your [Offer Name] access and receipt

**Preview Text A:** Your link, your receipt, and the first step. Everything in one place.
**Preview Text B:** Access details and what was charged — keep this one.

**Email Body:**

{{contact.first_name}},

You're in. Here is everything you need, in the order you need it.

**Your access**
[Access page link — the approved URL from the brief]
Sign in with the email address this message was sent to. If your login is not active yet, it activates within [activation window from the brief] of this email.

**Your receipt**
- Offer: [approved offer name from the brief]
- Amount charged: [amount actually charged from the order record] [currency]
- Plan: [one payment / the approved plan and next charge date, only when the order record carries it]
- Order reference: [order reference]
A formal invoice is available from [billing or support address from the brief].

**Your first three steps**
1. Open the access page and confirm you can sign in.
2. [First onboarding step named in the approved brief.]
3. [Second onboarding step named in the approved brief.]

That is the whole start. Nothing else is required today.

**[Open my access page →]**

If anything above looks wrong — the amount, the plan, or a link that will not open — reply to this email and a person will fix it.

[Founder Name]

*(Engine note: substitute the founder's actual name and every bracketed fact from the order record and the approved brief; the access destination is the approved access page; word count 150–300, two subject lines, one preview, ≥1 CTA verified; no credential, password, card digit, or payment token appears anywhere in the payload.)*

## Quality Checklist
- [ ] Resolved by name as `signature_launch_welcome_access`; intake consumed from the approved launch brief with provenance (no second interview)
- [ ] Both emails present; frameworks match the E1–E2 map exactly; phases run access/receipt → next steps/thank-you
- [ ] Access link is in the top third of E1 and restated in E2; E2 ends on access and thank-you, never on a pitch
- [ ] One CTA per email, pointing at the approved access page; no guessed URL, no password in a query string
- [ ] Receipt matches the order record exactly: amount, currency, plan and next charge only when present, order reference
- [ ] No card digits, payment token, password, or credential anywhere in either email
- [ ] Transactional rule honored: marketing opt-out does not suppress; refund or cancelled order before send does; no duplicate send per order
- [ ] Every email 150–300 words; any other length is a recorded locked-brief override
- [ ] Every email: Pair A and Pair B subject+preview, explicitly paired; Pair B plain and truthful
- [ ] No fabricated proof, date, session time, or result; all facts from the order record and the approved brief
- [ ] Review document carries framework labels and "Email Body:" labels; recipient payload carries none of them
- [ ] Founder's ACTUAL name in every signature, zero placeholders
- [ ] Handoff is draft-only with content hashes, order-fact fields, launch calendar, and stop/suppression rules; no credentials, nothing sent
