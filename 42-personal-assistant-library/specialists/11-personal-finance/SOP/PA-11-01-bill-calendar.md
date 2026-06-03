# SOP PA-11-01: Bill Calendar

**Department:** Specialist 11 — Personal Finance Assistant
**SOP ID:** PA-11-01 | **Version:** 1.0 | **Owner:** {{TOKEN}}

---

## Purpose
Build and maintain a living calendar of every recurring financial obligation so {{TOKEN}} never misses a due date or pays a late fee.

## DMAIC — Analyze

Bills get missed from systemic gaps: variable-due-date drift, infrequent-obligation blindness (quarterly/annual), auto-pay complacency (expired card), new-obligation gaps, shared-account confusion. A working calendar needs: (1) absolute dates, (2) ≥10-day advance visibility, (3) balance awareness.

## Trigger Conditions
- New recurring financial commitment created
- Existing bill's due date or amount changes
- {{TOKEN}} mentions "I think I have a bill due" or "did I pay X yet?"
- Weekly review (every Sunday evening, auto-triggered)

## Procedure

### Step 1: Discovery — Build the Master List
1. **Bank statements** — scan last 3 months of checking and credit card accounts.
2. **Email search** — query "invoice," "bill," "payment due," "receipt," "renewal" across 12 months.
3. **Direct inquiry** — ask {{TOKEN}}: "Walk me through everything you pay recurring — monthly, quarterly, annually."
4. **Known-gap check** — cross-reference: domain registrations, cloud storage, software, gym, streaming, insurance, professional memberships, parking/tolls.

### Step 2: Structure Each Entry

| Field | Example |
|---|---|
| Name | Verizon Wireless |
| Category | Utilities — Phone |
| Amount | $45.00 (flag if variable) |
| Frequency | Monthly |
| Due Date | 14th |
| Payment Method | Auto-pay {{PAYMENT_CARD_REF}} |
| Next Due | June 14, 2026 |
| Reminders | 7 days + 1 day before |

### Step 3: Calendar Population
For each bill: due-date event with amount, 7-day reminder, 1-day urgency alert. Annual/semi-annual: additional 30-day advance.

### Step 4: Weekly Reconciliation
Sunday: review upcoming bills, confirm prior-week auto-pay, flag amount changes, update variables.

## Output Artifacts
- Master Bill Calendar (all recurring obligations)
- Weekly Bill Forecast (sent to {{TOKEN}} each Sunday)
- Bill Calendar Audit Log (additions, changes, removals)

## CTQ Checks (Critical-to-Quality)

- [ ] Master Bill Calendar has 100% of known recurring obligations logged with exact due dates
- [ ] Every bill has both a 7-day advance reminder AND a 1-day-before alert set
- [ ] Weekly reconciliation completed (Sunday) — zero missed reviews in the last 4 weeks
- [ ] No bill payment missed or late in the last 90 days

## Definition of Done

Every recurring financial obligation is on the calendar with exact dates and advance alerts, and {{TOKEN}} has received the weekly bill forecast — zero surprises.

## Escalation

- Bill unverifiable (no statement, login, record) → flag to {{TOKEN}} as "potential zombie subscription"; loop in Specialist 14 (Life-Admin Archivist)
- Payment about to be missed within 48 hours → immediate alert to {{TOKEN}} with payment link; cc Specialist 09 (Daily Check-In)
- Amount spike >50% over baseline → cross-reference Specialist 11's PA-11-04 (Renewal Negotiation) before flagging to {{TOKEN}}
- Pattern of missed payments (2+ in 60 days) → escalate to Specialist 09 (Daily Check-In) for root-cause conversation

*Version 1.0 — SOP PA-11-01 — {{TOKEN}}*
