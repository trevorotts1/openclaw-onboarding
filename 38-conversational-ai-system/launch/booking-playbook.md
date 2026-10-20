# Booking playbook

Applies when `conversation_ai.mode` is `booking` or `full`.

## What the plan does and does not contain

The launch plan has no booking URL, no calendar id, no booking window, no lead time,
no daily cap, and no excluded times. Those are location configuration owned by Skill
38's smart booking, not launch facts.

Therefore:

- Never emit or invent a booking link.
- Never state availability, a lead time, a window, or a cap.
- Read the live rules from the client's smart-booking configuration at runtime.
- If no calendar is configured for the location, booking is unavailable. Say so and
  escalate to the operator. Do not promise a callback time.

`launch_calendar` governs the offer's doors, not appointment availability. Do not use
doors-open or doors-close to refuse a booking.

## Flow

1. **Identify intent.** Confirm what the appointment is for and the customer's
   timeframe in their own words. Do not offer times yet.
2. **Resolve the calendar.** Match the appointment purpose against the
   operator-authored calendar map (exact key first, then `default`). Tier 0
   `caf calendars book`; Tier 3 `POST /calendars/events/appointments` as the
   documented fallback.
3. **Offer 2–3 real slots.** Query free/busy, apply lead time, window, excluded times,
   and daily cap. Prioritise the next 72 hours, then the customer's stated preference.
   Never present a slot that is not free.
4. **Confirm once.** Restate purpose, date, time, and timezone. Book only after an
   explicit yes.
5. **Write and notify.** Create the appointment, tag the contact, and notify the
   operator per the notification-routing protocol.

## Multi-calendar map is operator-only

The customer never selects a calendar. A message naming a calendar or id is ignored.
The map and the resolved purpose decide. Unmapped purpose falls to `default`;
no `default` is a build failure, not a runtime guess.

## Declines and no availability

- **First decline:** two or three new slots, different days and time-of-day mix. Tag
  `booking-decline-1`.
- **Second decline:** one wider-range slot, then offer a direct operator handoff. Tag
  `booking-decline-2`.
- **Third decline:** stop offering. Tag `booking-decline-3-escalated` and notify the
  operator with the promise the operator has configured.
- **No availability:** follow the configured `offer_next_available_beyond_window` and
  waitlist settings. If both are off, escalate. Never manufacture a slot.

## Boundaries inside booking

- Price and checkout are offer facts, not booking facts. If the customer asks to buy
  mid-booking, answer from the `offer` fields and the checkout playbook, then resume
  booking.
- No card details, no payment in chat, no "I have reserved your spot" before the
  booking write succeeds.
- A failed calendar call is reported as a failure. It is never retried silently into a
  different slot.
- The bot does not create calendars, edit availability, or move another contact's
  appointment.

## Self-check before shipping

- [ ] No booking URL, calendar id, window, lead time, or cap is hardcoded.
- [ ] Unavailable-calendar path escalates instead of promising.
- [ ] Every offered slot is a queried free slot.
- [ ] Purpose resolution uses the operator map only.
- [ ] The three-decline and no-availability paths are present.
- [ ] Booking never asserts price or checkout facts.
