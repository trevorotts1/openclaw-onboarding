---
id: signature-launch-doors-closing
type: sequence
name: Signature Launch Doors-Closing Profile
tags: [sequence, signature-launch, signature-launch-profile, doors-closing, last-48-hours, final-call, deadline, truthful-deadline, landing-page, aida, pas, three-b-plan, paired-variants, founder-signature, launch-brief-intake, draft-only-handoff]
length: 150-300 words
best_for: [doors-closing, signature-launch-builds, final-48-hours, warm-lists, launch-close]
---

## Style / Definition
The **doors-closing profile** of the Email Engine: three short, honest emails that run in the **last 48 hours** before a Signature Launch closes. One job only — tell the reader the doors are closing, state the **one real deadline**, and send them to the approved landing / sales page. It rides the same launch contract as the other Signature Launch profiles: intake from the approved shared-launch brief (never a second questionnaire), paired subject/preview variants, a profile-fixed two-preview rule, review-document labels that never reach the recipient, and a draft-only handoff. This is a profile of the existing engine, not a second engine.

## Purpose & Intention
Most launches lose their last day to noise: three "final hours" emails with three different times, a bonus that quietly expires, a countdown to a deadline nobody set. This profile does the opposite. It says the real close time once, repeats the same real close time, and then says it plainly one last time. The only urgency it is allowed to have is the urgency that actually exists in `launch_calendar.doors_close_at`. That constraint is the profile's whole value: a reader can trust the deadline because it never moves, and the launch can be proved truthful because every deadline line traces to one approved field.

## The Phase Map (fixed — no deviation)
| Phase | Email | Job |
|---|---|---|
| Final 48 hours | E1 | Announce that the doors close in 48 hours, state the exact close time from the calendar, and point at the page |
| Final 24 hours | E2 | Name the problem of waiting, agitate it honestly, and give the same close time as the solution's boundary |
| Last call | E3 | The short email: doors close at the stated time, one link, no new argument |

## The E1–E3 Framework Map (fixed — no deviation)
| # | Framework | Source Material / Rule |
|---|-----------|------------------------|
| 1 | AIDA | Attention on the real close time, Interest in what is inside (approved offer facts), Desire stated as possibility, Action on the approved page |
| 2 | P.A.S. | The problem of starting another month without the offer, honest agitation, the offer plus the same close time as the solution |
| 3 | The 3-B Plan | **The short email** (under 150 words): brevity, bluntness, basic — the close time, the link, the founder's name |

## The Doors-Closing Law (truthful deadline only)
1. **One deadline, one source.** Every date, countdown, or closing-time line states `launch_calendar.doors_close_at` and `launch_calendar.timezone` from the approved launch plan. There is no other deadline in this profile.
2. **The same deadline in all three emails.** E1, E2, and E3 repeat the same approved time. No email may round it, shift it, or restate it as a different hour.
3. **No missing deadline, no email.** If `launch_calendar.doors_close_at` is absent, the unit **fails closed** and reports the missing field. A doors-closing email without a real close time is invented urgency, so none is written.
4. **Never extended, never reopened.** No "we're keeping it open", no second close date, no last-minute extension. The profile states the close; it never negotiates with it.
5. **Relative language cannot contradict the field.** "Today", "tonight", "end of day", and "midnight" appear only when they are true of `doors_close_at` in the calendar's timezone; otherwise the exact time is written instead.
6. **No invented scarcity.** Price changes, bonus expiry, and seat counts appear only when the approved brief states them, with the same source discipline as the deadline.
7. **Countdowns come from the calendar.** Any countdown is computed from `doors_close_at` at send time; nothing is hard-coded.

## Profile Rules (on top of the shared sequence rules)
1. **Two subjects, two previews, as PAIRS.** Every email carries Pair A (subject A + preview A) and Pair B (subject B + preview B). Pair B is prolific and disruptive but truthful and on brand: no false account alert, no fake reply prefix, no fabricated urgency, no fake scarcity, no misleading price, no invented deadline. The pairing is preserved through the draft handoff; it is never flattened into an unpaired preview list.
2. **The destination is the approved landing / sales page** for the current approved offer version. No checkout link, no second offer, no expired one-click link.
3. **Word band 150–300** for E1 and E2. **E3 is the deliberate short exception** (3-B Plan, under 150 words). Any other exact length is honored only through the existing locked-brief override channel, recorded as an override.
4. **Timing is anchored, not guessed.** E1 at `doors_close_at` minus 48 hours, E2 at minus 24 hours, E3 in the final hours of the closing day. The sequence does not run before the final 48 hours.
5. **No fabricated proof.** Testimonials, results, member counts, and revenue figures appear only when the brief carries the evidence. Otherwise the copy uses a clearly hypothetical illustration or a proof-free truthful variant, and Desire is stated as possibility, never as a guaranteed result.
6. **The objective is `promotional`.** The frozen objective enum has no doors-closing value; this profile defaults to promotional, and no lane file widens the enum.
7. **Labels live in the review document only.** The private client-review document labels each email with its framework and labels the body "Email Body:". The recipient payload is clean: no framework labels, no slot instructions, no production commentary.
8. **Founder's ACTUAL name** in every closing signature, from the brief. No placeholder ever ships.
9. **Draft-only, always.** The profile produces plans and drafts. The build-plan handoff to Skill 44 carries `draft_only=true`, the profile name, approved content hashes, the variant-pairing strategy, `launch_calendar.doors_close_at` with its timezone, and stop/suppression rules, and never any credential. This profile never sends.

## Registration Note (for the integrator — a lane file cannot do this)
The profile is authored as a file pair only. It is **not** in `catalog-index.json` / `catalog-built-index.json`, and `prove-email.py` does not yet know `signature_launch_doors_closing` in `SEQ_LENGTHS`, `PREVIEW_EXPECTED`, or `_sequence_type`. Until those shared files are updated by the integrator, a run resolving this `sequence_type` fails `AF-EMAIL-TYPE-MISMATCH` by design. `register.py --check` keeps its frozen 36-entry census, so adding this pair alone does not change or break it.

## Use Cases
- The closing leg of a Signature Launch, after the main launch 10
- A short final-call run for a launch with a fixed, approved close time
- Re-promotion of the last 48 hours of a re-run launch, using the same approved calendar and refreshed copy

## Detailed Example
Below: **Email 1 of 3** in full (AIDA), demonstrating the complete format contract including the paired B-set. Bracketed values are substitutions from the approved launch plan and landing facts — no date, price, or outcome may be typed into a real sequence.

**Email 1 — Framework: AIDA (Attention–Interest–Desire–Action)**

**Subject Line A:** Doors close [doors_close_at] — here is what is inside
**Subject Line B:** 48 hours left. Same deadline we gave you on day one.

**Preview Text A:** The exact closing time, the offer, and the link — nothing else.
**Preview Text B:** We said [doors_close_at]. That has not changed.

**Email Body:**

{{contact.first_name}},

The doors on [approved offer name] close at [doors_close_at] [timezone]. Not "sometime soon" — [doors_close_at], exactly as the page states. That is the only deadline in this email, and it is the one every email this week has carried.

Inside is [approved offer one-liner], built from the approved offer:
- [approved feature 1, in the reader's words]
- [approved feature 2, in the reader's words]
- [approved feature 3, in the reader's words]

Here is the honest picture of the week after someone joins: [approved outcome, stated as a possibility, never as a guaranteed result]. Nothing about that picture is new today. The offer is the same offer it was on day one.

What changes today is only the calendar: after [doors_close_at], the page stops taking new members until the next approved round.

If that week is the one you want, the door is open until [doors_close_at].

**[See the full offer and join before the doors close →]**

[Founder Name]

*(Engine note: substitute the founder's actual name; substitute `doors_close_at` and its timezone exactly from `launch_calendar`; the CTA destination is the approved landing / sales page; word count 150–300, two subject lines, two previews, ≥1 CTA verified.)*

## Quality Checklist
- [ ] Resolved by name as `signature_launch_doors_closing`; intake consumed from the approved launch brief with provenance (no second interview)
- [ ] All 3 emails present; frameworks match the E1–E3 map exactly; phases run final 48 hours → final 24 hours → last call
- [ ] Every deadline line states `launch_calendar.doors_close_at` and its timezone exactly; all three emails state the same deadline
- [ ] No deadline is extended, reopened, rounded, or restated as a different time; relative urgency language does not contradict the field
- [ ] Missing `doors_close_at` fails closed with the field reported; no urgency copy is written
- [ ] Every CTA points at the approved landing / sales page; no second offer, no expired link
- [ ] E1 and E2 are 150–300 words; E3 (3-B Plan) is under 150 words; any other length is a recorded locked-brief override
- [ ] Every email: Pair A and Pair B subject+preview, explicitly paired; Pair B disruptive and truthful
- [ ] No fabricated proof, scarcity, price change, or guaranteed result; testimonials only when the brief carries the evidence
- [ ] Review document carries framework labels and "Email Body:" labels; recipient payload carries none of them
- [ ] Founder's ACTUAL name in every signature, zero placeholders
- [ ] Handoff is draft-only with content hashes, the real close time and timezone, and stop/suppression rules; no credentials, nothing sent
