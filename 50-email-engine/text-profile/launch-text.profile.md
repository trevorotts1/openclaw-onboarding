---
id: text-profile-launch-text
type: text-profile
name: Launch Text Profile (launch-text voice)
tags: [text-profile, sms, launch, launch-text, skill-50-voice, skill-44-send-sms, draft-only, a2p-10dlc, quiet-hours, stop-opt-out, reply-invitation]
best_for: [signature-launch, black-friday-launch, opt-in-confirmation, event-reminders, doors-open, last-call, abandoned-checkout, access-link]
---

# Launch Text Profile (launch-text voice)

The copy profile for every launch text. It defines **voice and the copy contract only**.
The SMS steps themselves are built as Skill 44 `send-SMS` automation steps; Skill 50 never sends.

## Cardinal rules (all texts, every point)

1. **Every text ends with a reply invitation and STOP.** Both, always, in that order. The reply invitation is a real invitation to answer (`Reply YES and I'll ...`); STOP is literal.
2. **Send window 8:00 a.m. – 9:00 p.m. recipient local time.** A text that would land outside the window waits for the next window start; if that lands after the event it refers to, it is dropped, never sent early.
3. **Draft only.** `draft_only: true`, `never_sends: true`. Nothing is scheduled or sent to a live account during a launch build.
4. **A2P gate.** `a2p_ready=false` keeps every text a draft and the package warns: texts cannot send until A2P 10DLC is approved.
5. **Cap: 3–5 promotional texts per launch.** This profile allows up to 5 and ships 3 promotional points, so the cap holds by construction.
6. **One idea, one link, one question.** Maximum 320 characters (two 160-character GSM-7 segments). More than one link or a second idea means it should be an email, not a text.
7. **Stop on purchase.** A verified purchase stops abandonment recovery and the remaining promotional texts for that buyer.

## Voice

The launch-text voice is the approved `brand_voice` from the locked Skill 50 brief, rendered for SMS:

- **First person, founder to one person.** Same voice as the launch emails, compressed.
- **Plain, spoken language.** Short sentences. No marketing throat-clearing, no stacked adjectives.
- **Calm confidence.** State what is true and let the reader decide.
- **Name the person once when the brief provides a first name.** Never invent one.
- **Every text earns its place.** If it carries no new fact (time, link, confirmation, deadline), it does not send.

### Forbidden

- Persona names, quotes or book references (the Skill 50 `AF-EMAIL-PERSONA-NAMED` rule carries over).
- Invented deadlines, fake scarcity, countdown theatre.
- Guarantees of results; prices or bonuses outside the approved offer version.
- More than one link; more than one question.
- ALL CAPS beyond `STOP` and the reply keyword.
- Emoji unless the approved brand_voice sample uses them.
- The word `unsubscribe`; SMS opt-out is STOP only.

## The points and their voice

| Point | Kind | Voice intent | Links |
|---|---|---|---|
| `optin_confirm` | operational | Confirm the sign-up, say what arrives and when, ask one easy question. No offer pitch. | 0 |
| `keyword_optin` | operational | Confirm the keyword worked and deliver what it promised. The confirmation is the reply invitation. | 1 |
| `reminder_1d` | operational | Plain time-and-place reminder, one warm line, no new offer claims. | 1 |
| `reminder_1h` | operational | Short, calm, specific to the hour. | 1 |
| `reminder_15m` | operational | Two sentences at most: time, link, reply invitation. | 1 |
| `doors_open` | promotional | Doors are open, offer named once, approved deadline only. | 1 |
| `last_call` | promotional | Truthful deadline stated once. No invented scarcity. | 1 |
| `abandoned_checkout` | promotional | Neutral, no blame: checkout did not finish, cart still open. Stops on purchase. | 1 |
| `access_link` | operational | Access or receipt first, then the single next step. Never mixes in a sales pitch. | 1 |

## Compliant examples

Placeholders (`{first_name}`, `{offer_name}`, `{deadline}`, `{link}`) come from the approved brief and offer version.

**Doors open (promotional)**

> Doors are open, {first_name}. {offer_name} is live now, and the launch price holds until {deadline}. Take a look: {link}
> Reply YES and I'll send the details. Reply STOP to opt out.

**Reminder, 1 hour (operational)**

> We start in 1 hour, {first_name}. Join here: {link}
> Reply YES if you want the replay link instead. Reply STOP to opt out.

**Abandoned checkout (promotional)**

> Looks like your checkout did not finish, {first_name}. Your cart is still open: {link}
> Reply YES and I'll resend the link. Reply STOP to opt out.

**Access link (operational)**

> You're in, {first_name}. Here is your access: {link}
> Reply YES and I'll send the receipt and next steps. Reply STOP to opt out.

## Handoff

- **Skill 44** owns the `send-SMS` steps and the workflow that schedules them. This profile supplies the voice and the copy contract those steps render.
- **The launch plan** (`text_sets[]`) names the points, the launch calendar supplies event times, and `a2p_ready` gates every send.
- **Self-check:** `python3 validate_profile.py` must exit 0. It proves reply invitation + STOP, the 8–9 local window, the promo cap, link limits and length on every example.

Not in this profile: the automation steps themselves, the keyword opt-in flow, GHL workflow JSON, or any live send. Those are separate lanes.
