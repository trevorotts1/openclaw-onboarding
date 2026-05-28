# Smart Booking Protocol

## Calendar integration

- Calendar system: <google | gohighlevel | calendly | outlook>
- Calendar ID: <BOOKING_CALENDAR_ID>
- Timezone: <client timezone>
- API access: <oauth token location | skill name>

## Booking rules

- Maximum booking window: <N days> from now
- Minimum lead time: <N hours> from now
- Daily booking cap: <N appointments | unlimited>
- Excluded times: <list>
- No-availability behavior:
  - Offer next available beyond window: <true | false>
  - Offer waitlist for earlier openings: <true | false>
- Decline escalation: after <3> total declines, escalate to <escalation contact>

## Smart booking flow

When customer requests an appointment:

### Step 1 — Identify intent
Agent confirms: what service / what duration / what timeframe customer wants.

### Step 2 — Check availability
Query the calendar for free slots within the booking window:
- For Google: `POST /calendar/v3/freeBusy` with timeMin=now+leadtime,
  timeMax=now+windowDays, items=[calendar_id]
- Compute free slots (free/busy returns busy intervals; agent computes
  complement)
- Apply excluded times
- Apply daily booking cap

### Step 3 — Recommend slots
Offer 2-3 specific slots, prioritizing:
- Within first 72 hours from now (highest priority — psychology of
  same-week commitment)
- Matching customer's stated preference (morning/afternoon/specific
  day)
- Slots that maximize the operator's calendar utilization
  (don't stack appointments back-to-back if there's a fragmented
  alternative; do consolidate same-day to leave full days open)

Example:
"I have these times open this week:
  - Wednesday, May 30 at 10:00 AM
  - Thursday, May 31 at 2:00 PM
  - Friday, June 1 at 11:30 AM

Which works best?"

### Step 4 — Handle declines (3-strike rule)

**First decline:** Customer says none work. Agent offers 2-3 alternative slots
(different days, different time-of-day mix). Tag contact `booking-decline-1`.

**Second decline:** Customer declines again. Agent offers ONE MORE slot
with a wider range — including slots up to the maximum booking window.
"I have one more option further out: <date> at <time>. Does that work?
If not, I can connect you with [operator name] directly to find time."
Tag contact `booking-decline-2`.

**Third decline:** Customer declines the third offer. Agent stops trying
and escalates:
"Let me get [operator name] in touch with you directly. They'll reach out
within [24 hours / operator's promise]. Thanks for your patience!"
Tag contact `booking-decline-3-escalated`. Notify operator per
notification-routing-protocol.md.

### Step 5 — No availability at all
If the booking window is entirely full (every slot taken):
- If `offer_next_available_beyond_window: true`: find the next free
  slot even beyond the window, offer it: "I don't have anything in
  the next 7 days but I can get you in next Tuesday, June 7 at 10 AM.
  Want that — and I can send you a reminder Sunday?"
- If `offer_waitlist: true`: offer to put the customer on a waitlist:
  "I'm fully booked but I can put you on the waitlist — if anything
  opens up, I'll text you first. Sound good?"
- If both `false`: escalate to operator with the customer's request.

### Step 6 — Confirm and book
When customer agrees to a slot:
- Create the calendar event via Google Calendar API (or GHL skill for
  Convert and Flow native)
- Add customer as attendee with their email
- Set event title: "<Service> with <Customer Name>"
- Send confirmation message to customer with the time, date, location/
  link, any prep info
- Tag contact `booked-<date>`
- If a reminder was offered, schedule a reminder per Feature 15 outreach
  infrastructure (once shipped) or directly via OpenClaw cron

## Waitlist management

If waitlist is enabled, the agent maintains a waitlist in
`<MASTER_FILES_DIR>/booking-waitlist.md`. When a booked slot frees up
(operator cancels, customer reschedules out), the agent auto-promotes
the first waitlist entry by texting them: "An earlier slot opened up:
<date> at <time>. Want me to book you in?"

## Capabilities playbook integration

This replaces and extends agent-capabilities-playbook.md Section 2.1
(Book appointments). The book-appointment action now uses this
protocol's intelligence rather than the basic version.
```

**D. Update agent-capabilities-playbook.md Section 2.1** to reference the smart booking protocol.

**E. Append to Run Manifest:** "Step 9.19 complete — smart-booking-protocol.md created, calendar configured (<system>, ID <id>), booking rules captured, capabilities playbook Section 2.1 upgraded."

