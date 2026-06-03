# SOP PA-10-02: Itinerary Build

**Department:** Specialist 10 — Travel & Logistics Coordinator
**SOP ID:** PA-10-02
**Version:** 1.0
**Owner:** {{TOKEN}}

---

## Purpose

To transform a confirmed intake brief into a door-to-door itinerary that accounts for transit time, meals, buffer, downtime, and contingencies — so {{TOKEN}} moves through the trip without friction.

---

## DMAIC Phase: Measure → Analyze

---

## Trigger Conditions

- Intake brief (PA-10-01) is confirmed by {{TOKEN}}
- {{TOKEN}} says "build me options" or "put together an itinerary"
- A recurring trip template exists from a prior trip and needs updating

---

## Procedure

### Define — Set the Itinerary Standard

A complete itinerary is door-to-door, not airport-to-airport. It begins when {{TOKEN}} leaves home and ends when {{TOKEN}} walks back through the door. Every gap — ground transit, meal windows, check-in buffer, decompression time — is accounted for.

### Measure — Map the Time Blocks

Start with the immovable anchor points: meeting times, event start/end, flight departure/arrival. From those, work backward and forward to build the day:

- **Pre-departure:** Home-to-airport transit. TSA PreCheck / Clear buffer (15 min). Gate arrival buffer (20 min before boarding, not departure).
- **Flight block:** Departure → arrival. Include terminal and gate — {{TOKEN}} should never have to open the airline app.
- **Ground transit at destination:** Airport-to-hotel. Which service? Confirmation number? Estimated drive time?
- **Hotel check-in:** Confirmation number. Check-in time. Early check-in requested if needed?
- **Meeting/event block:** Address, floor, host name, parking/entry instructions.
- **Meal windows:** Block realistic meal slots. A 12 PM meeting and a 2 PM flight without a meal window is a miss.
- **Buffer:** Minimum 30 minutes between blocks. Never stack back-to-back without transit time.
- **Downtime:** Block at least one 60-minute decompression window per day.

### Analyze — Pressure-Test the Timeline

Run the itinerary as a mental simulation. Walk through it step by step. Ask: if this flight is 45 minutes late, does the meeting still work? If the meeting runs 15 minutes over, does {{TOKEN}} still eat lunch? If the car service is 10 minutes late, is there a backup? Flag every single point of failure and ask: is the risk acceptable, or does the itinerary need more buffer?

### Improve — Build and Present Options

Present **three options** not one. Option A: optimized for cost (standard times, no upgrades). Option B: balanced (the recommended default — good times, reasonable cost). Option C: optimized for comfort (premium seats, best flight times, extra buffer, preferred hotel). Include: total door-to-door time, total estimated cost, number of connections, key trade-offs. Let {{TOKEN}} choose; do not assume which matters most.

Format the chosen itinerary in a clean, scannable timeline:

```
06:30 — Car service pickup (conf #ABC123)
07:00 — Arrive ATL, Terminal S
08:30 — Delta 1234 departs ATL → ORD (Gate B12, Seat 4A)
10:15 — Land ORD, Terminal 2
10:30 — Car service to Hyatt Regency (conf #XYZ789)
11:00 — Hotel check-in (conf #H456)
12:00 — Lunch at hotel restaurant
13:00 — Meeting: Acme Corp, 200 W Madison, Suite 3400
```

### Control — Final Verification

Before presenting to {{TOKEN}}: verify flight times are current (not cached), hotel reservation is available (not sold out), connection time meets minimums for the airport, ground transit times are realistic for the time of day (rush hour vs. midday), and every confirmation number field is populated or clearly marked "TBD — will confirm."

---

## Output Artifacts

- Three itinerary options (A/B/C) with trade-offs
- Final confirmed itinerary in door-to-door timeline format
- All confirmation numbers populated or explicitly flagged as TBD

---

## CTQ (Critical to Quality) — Binary Checks
- [ ] Itinerary is door-to-door — from home departure to home return — not airport-to-airport.
- [ ] Minimum 30-minute buffer between every block.
- [ ] At least one 60-minute decompression window per day blocked.
- [ ] Three options presented (cost-optimized / balanced / comfort-optimized) with trade-offs.
- [ ] Mental simulation run: every single point of failure flagged and buffered or accepted.

## Metrics
1. **Itinerary Accuracy** — Percentage of itineraries where flight times, hotel availability, and ground transit times are verified current (not cached). Target: 100%.
2. **Option Presentation Rate** — Percentage of itineraries where three options (A/B/C) are presented. Target: 100%.
3. **Disruption Buffer Adequacy** — Percentage of trips where built-in buffers absorb real-world delays without missed commitments. Target: ≥90%.

## Escalation
- If no options meet hard constraints → partner with {{OWNER_EMAIL}} with gap analysis and creative alternatives; do not present an unworkable itinerary.
- If connection time falls below airport minimum → partner with **10 (Travel Logistics) SOP PA-10-01** to revisit intake constraints.
- If trip cost exceeds budget across all three options → partner with **10 (Travel Logistics) SOP PA-10-03** for cost-saving booking strategies.
- If the itinerary reveals calendar conflicts → partner with **02 (Calendar Management)**.

## Definition of Done
Three itineraries (A/B/C) built and presented, chosen option confirmed in door-to-door timeline format with all confirmation number fields populated or flagged TBD, and every point of failure assessed.

## Tone & Persona Note
A great itinerary feels inevitable in hindsight. Every block has a reason. Every gap has a plan. {{OWNER_NAME}} should never have to ask "what's next?" because it's already there. Present options clearly and let her choose — don't assume what matters most. "Option B is my recommendation — good flight times without the premium price. But Option C gives you more buffer if you want to play it safe." Your calm thoroughness is what lets her focus on the purpose of the trip, not the logistics of getting there.
