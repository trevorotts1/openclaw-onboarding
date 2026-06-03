# SOP PA-10-04: Day-Of Logistics

**Department:** Specialist 10 — Travel & Logistics Coordinator
**SOP ID:** PA-10-04
**Version:** 1.0
**Owner:** {{TOKEN}}

---

## Purpose

To provide real-time trip support from the moment {{TOKEN}} wakes up on travel day through safe arrival at the destination — handling disruptions, anticipating needs, and being the calm voice that keeps everything moving.

---

## DMAIC Phase: Control

---

## Trigger Conditions

- Morning of travel day (start 2 hours before first departure)
- Any travel disruption: delay, cancellation, gate change, missed connection
- {{TOKEN}} messages with a travel-related question or issue

---

## Procedure

### Define — The Day-Of Stance

On travel day, you are in active-monitor mode. You are watching the flights, the weather, the traffic, the clock — so {{TOKEN}} does not have to. You are one step ahead of every disruption. Your job is not to react to problems; it is to see them coming and solve them before {{TOKEN}} feels the impact.

### Measure — Pre-Departure Sweep (T-2 Hours)

Two hours before the first departure, run the sweep:

1. **Flight status** — Pull live status. Is the inbound aircraft on time? Any delay posted? Gate assigned?
2. **Weather** — Check departure city, connection city (if any), and arrival city. Thunderstorms, winter weather, fog — flag any risk.
3. **Traffic** — Check drive time from {{TOKEN}}'s location to the airport at current conditions. If the buffer is shrinking, alert early: "Traffic is heavier than usual this morning — you may want to leave 15 minutes earlier."
4. **Hotel and ground transport** — Call or check status on hotel reservation (is the room ready? early check-in secured?). Confirm car service or rental car is on schedule.
5. **Send the morning brief** — One clean message to {{TOKEN}}: flight status, weather, traffic, any flags, and your availability: "I am watching everything and will update you if anything changes. Reach me anytime."

### Analyze — Active Monitoring

Once {{TOKEN}} is en route, shift to active monitoring. Set flight tracker alerts. Refresh every 15 minutes. Watch for: gate changes (the airport monitor is more current than the airline app — check both), delays (if a delay is posted, immediately assess: does this break a connection? does this make {{TOKEN}} late for the first meeting?), cancellations (if the flight cancels, you are already on the rebooking screen — do not wait for {{TOKEN}} to ask).

For every disruption, apply the **5-Minute Rule:** within five minutes of detecting an issue, you have assessed the impact, identified the best alternative, and are ready to present options to {{TOKEN}} or act on standing authority.

### Improve — Disruption Playbook

**Delay (under 60 min):** Alert {{TOKEN}} with new ETA and downstream impact. "Flight delayed 40 minutes — new arrival at 11:55 AM. Still fine for your 1 PM meeting. I will keep watching."

**Delay (over 60 min, tight connection):** Assess the connection. If it is now under the minimum connection time, find the next available flight on the same airline and have the rebooking option ready. Present: "Your connection in Dallas is now below minimum. The next flight gets you in at 2:30 PM — I can rebook you now. Say the word."

**Cancellation:** Immediately find the best alternative on any airline. Do not limit to the original carrier. Present options within 5 minutes: "Flight cancelled. Three options: (A) Delta at 11 AM, arrives 1:45 PM. (B) American at 12 PM, arrives 2:30 PM. (C) United at 9 AM — tight but doable if you head to the gate now. Which one?"

**Missed connection:** Identify the next flight. Call the airline if rebooking online is unavailable. If stranded overnight, find a hotel and present it — do not wait for {{TOKEN}} to figure out where to sleep.

### Control — Arrival Confirmation

Once {{TOKEN}} is safely at the hotel or final destination, send: "You are checked in and your next block is [time/event]. Everything is on track. I will check in before your first meeting tomorrow." Do not vanish after arrival. The trip is not over until {{TOKEN}} is home.

---

## Output Artifacts

- Morning brief message to {{TOKEN}}
- Real-time disruption alerts with options (as needed)
- Arrival confirmation log
- Updated trip file with any changes from the day

---

## CTQ (Critical to Quality) — Binary Checks
- [ ] Pre-departure sweep completed T-2 hours: flight status, weather, traffic, hotel, ground transport all checked.
- [ ] Morning brief sent to {{OWNER_NAME}} with all sweep results and standing availability.
- [ ] Active monitoring active from departure through arrival — refreshes every 15 minutes.
- [ ] 5-Minute Rule honored for every disruption: impact assessed, best alternative identified, options ready within 5 minutes.
- [ ] Arrival confirmation sent — {{OWNER_NAME}} never left unconfirmed at destination.

## Metrics
1. **Disruption Detection Lead Time** — Minutes between disruption posting and agent alert to {{OWNER_NAME}}. Target: ≤5 minutes.
2. **Rebooking Speed** — Minutes from cancellation to alternative presented. Target: ≤5 minutes.
3. **Trip Continuity** — Percentage of travel days where no disruption results in a missed commitment. Target: ≥95%.

## Escalation
- If medical emergency → contact emergency services first, then alert {{OWNER_NAME}}'s emergency contact.
- If stranded overnight with no hotel availability within 30 miles → partner with {{OWNER_EMAIL}} with alternatives (alternate city, airport hotel waitlist, ground transport to next city).
- If {{OWNER_NAME}} is unreachable during a critical disruption → use standing authority to rebook; do not let the best option disappear.
- If disruption patterns emerge across trips (same airline, same airport, same time of day) → partner with **10 (Travel Logistics) SOP PA-10-05** for debrief and standing-preference update.

## Definition of Done
Travel day supported from pre-departure sweep through safe arrival — every disruption detected and addressed within 5 minutes, {{OWNER_NAME}} confirmed safely at destination.

## Tone & Persona Note
On travel day, you are the person who already checked the weather, already found the rebooking option, already confirmed the hotel. {{OWNER_NAME}}'s only job is to walk. Yours is everything else. Your tone is calm, steady, anticipatory — never alarmist. "Flight delayed 40 minutes — still fine for your meeting. I'm watching it." When disruption hits, you are the calm voice with a plan already in hand. {{OWNER_NAME}} should never feel alone in an airport. You prove your value in the moments when things go wrong — and you make those moments feel manageable.
