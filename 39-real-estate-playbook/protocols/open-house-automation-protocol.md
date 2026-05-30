# Open-House Automation Protocol

Automates the open-house lifecycle: registration capture → instant thank-you →
timed follow-up sequence → feedback prompt. The follow-up sweep runs on the
`re-open-house-followup-scan` cron registered by `scripts/07-register-crons.sh`.

## Stages (each emits an `open_house` event with the `stage` field)

### Stage 1 — `registered`
A visitor registers (sign-in sheet, QR form, or sign call). Capture their
buyer/seller intent at a high level. Send an instant, warm thank-you. Tag the
lead per intent (`ZHC-buyer-lead` / `ZHC-seller-lead`). NEVER fabricate property
facts in the thank-you — only state verified details.

### Stage 2 — `followup`
On the cron sweep (daily 18:00), for each `registered` visitor not yet followed
up: send a relevant, low-pressure follow-up. If the visitor showed interest in a
specific listing and a property-data provider is keyed, include verified facts;
otherwise keep it general (honest gap — never invented comps or value).

### Stage 3 — `feedback`
Prompt for honest feedback on the home (price perception, condition, fit). Route
seller-relevant feedback to the listing agent. Capture buyer criteria to refine
future matches.

## Quiet hours & consent

Honor the operator's quiet hours (Skill 38 quiet-hours protocol) and any
do-not-contact flags. Follow-up is opt-out-respecting; never spam-blast.

## Fair-housing

All outreach and matching is on stated criteria + availability — never on
protected class.
