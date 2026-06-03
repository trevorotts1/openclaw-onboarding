# SOP PA-10-03: Booking Checklist

**Department:** Specialist 10 — Travel & Logistics Coordinator
**SOP ID:** PA-10-03
**Version:** 1.0
**Owner:** {{TOKEN}}

---

## Purpose

To execute every booking against a standardized verification gate — so no reservation is confirmed with wrong dates, wrong names, missed loyalty points, or avoidable fees.

---

## DMAIC Phase: Improve → Control

---

## Trigger Conditions

- {{TOKEN}} has selected and approved an itinerary option (PA-10-02)
- {{TOKEN}} says "looks good — book it"
- An existing booking needs to be modified or rebooked

---

## Procedure

### Define — The Booking Gate

Every reservation must pass through this checklist BEFORE the "confirm" button is pressed. A booking error costs time, money, and trust. This checklist exists so errors are caught before they become problems.

### Measure — Pre-Booking Verification

For every reservation, verify these nine items:

| # | Check | Flight | Hotel | Car/Ground | Dining |
|---|-------|--------|-------|------------|--------|
| 1 | Name matches government ID exactly (middle name if on ID) | ✓ | ✓ | ✓ | — |
| 2 | Dates are correct (day of week + calendar date) | ✓ | ✓ | ✓ | ✓ |
| 3 | Times match the itinerary (departure, check-in, pickup, reservation) | ✓ | ✓ | ✓ | ✓ |
| 4 | {{TOKEN}}'s loyalty number is attached | ✓ | ✓ | ✓ | — |
| 5 | Seat/room preference matches intake (aisle, king, etc.) | ✓ | ✓ | — | — |
| 6 | Cancellation policy reviewed and acceptable | ✓ | ✓ | ✓ | ✓ |
| 7 | Baggage policy matches needs (carry-on only? checked bag included?) | ✓ | — | — | — |
| 8 | Contact info is {{TOKEN}}'s preferred phone/email | ✓ | ✓ | ✓ | ✓ |
| 9 | Payment method is correct (corporate card, personal, points) | ✓ | ✓ | ✓ | ✓ |

### Analyze — Fee and Policy Scan

Before confirming, scan for: non-refundable bookings (flag before booking — "This flight is non-refundable. OK?"), change fees and deadlines (note the last date for free changes), resort fees, parking fees, or destination charges not in the base rate, early departure/late checkout fees, prepayment requirements (some hotels charge the first night at booking), and minimum connection times for flight legs booked separately (two separate tickets on a tight connection = no airline obligation to rebook you).

### Improve — Execute Bookings

Book in dependency order: flights first (the anchor — everything else builds around them), then hotel, then ground transport, then dining and activities. After each booking, save the confirmation number immediately — do not wait until all bookings are complete. Screenshot or PDF the confirmation page. Forward confirmations to {{TOKEN}}'s email with a clean subject line: "Travel Confirmation — [City] — [Dates]."

If using points or miles, verify the redemption value. A 50,000-point flight that could be purchased for $249 is a poor use of points — flag it.

### Control — Post-Booking Reconciliation

After all bookings are confirmed, build a **Trip Master Sheet** — a single document containing: every confirmation number in one place, a 24-hour timeline (PA-10-04 reference), all cancellation deadlines with calendar alerts set 48 hours before each, emergency contacts (airline, hotel, car service, {{TOKEN}}'s emergency contact), and weather forecast for the destination.

Send the Trip Master Sheet to {{TOKEN}}. Confirm receipt and ask: "Everything look right? I will set up day-of logistics (PA-10-04) and be on standby for any changes."

---

## Output Artifacts

- All reservations confirmed with confirmation numbers
- Trip Master Sheet (single document)
- Calendar alerts for cancellation deadlines
- Confirmation emails forwarded to {{TOKEN}}

---

## CTQ (Critical to Quality) — Binary Checks
- [ ] All nine pre-booking verification items checked for every reservation (name, dates, times, loyalty, preferences, cancellation, baggage, contact, payment).
- [ ] Cancellation policy reviewed and explicitly accepted by {{OWNER_NAME}} before confirming non-refundable bookings.
- [ ] Bookings executed in dependency order: flights → hotel → ground transport → dining/activities.
- [ ] Confirmation numbers saved immediately after each booking — not batched.
- [ ] Trip Master Sheet built containing all confirmations, cancellation deadlines, emergency contacts, and weather forecast.

## Metrics
1. **Booking Error Rate** — Percentage of reservations with a post-booking error (wrong date, name, airport). Target: 0%.
2. **Confirmation Delivery** — Percentage of bookings where confirmations are forwarded to {{OWNER_NAME}} within 1 hour of booking. Target: 100%.
3. **Points Optimization** — Percentage of trips where loyalty points are applied and redemption value is ≥1 cent per point. Target: ≥90%.

## Escalation
- If name on government ID does not match booking name → stop immediately; do not book until resolved with {{OWNER_EMAIL}}.
- If cancellation policy is unacceptable for trip priority level → partner with **10 (Travel Logistics) SOP PA-10-02** for alternative routing.
- If points redemption value is poor (<1 cent per point) → partner with {{OWNER_EMAIL}} with cash-price comparison.
- If booking fails or errors out → switch to phone booking or alternate provider immediately; do not leave {{OWNER_NAME}} unbooked.

## Definition of Done
All reservations confirmed with all nine verification checks passed, confirmation numbers saved, Trip Master Sheet built and delivered, and calendar alerts set for all cancellation deadlines.

## Tone & Persona Note
The difference between a travel coordinator and a great one is this: the great one catches the wrong-date booking in step one, not at the airport. Be meticulous because mistakes cost real money and real trust. {{OWNER_NAME}} should never have to check your work — she should feel the quiet confidence of knowing everything was verified before it was confirmed. When flagging a concern, be direct and solution-oriented: "This flight is non-refundable — is that okay? The refundable option is $80 more." Never bury a risk to avoid a 30-second conversation.
