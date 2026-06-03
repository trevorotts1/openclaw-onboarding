# PA-14-05 — Renewal & Expiration Tracking

**Department:** Life-Admin Archivist
**SOP ID:** PA-14-05
**Owner:** {{TOKEN}}
**Version:** 1.1.0
**Last Updated:** 2026-06-03

---

## Purpose

Ensure no subscription, license, certification, insurance policy, domain registration, payment method, or government filing ever expires unnoticed — preventing service interruptions, late fees, lapsed coverage, and last-minute panic.

## Trigger

Any new recurring commitment enters {{TOKEN}}'s ecosystem (new subscription, renewed policy, payment method update, domain registration, certification, business filing).

## Inputs / Prerequisites

- Google Calendar (shared with {{TOKEN}})
- Renewal Ledger (Notion or Google Sheets)
- Account Inventory (PA-14-03) — source data for tracked items and payment methods
- Gmail filters for subscription-renewal emails
- Provider billing portal access (credentials per PA-14-03)

## Scope

Every recurring commitment with a hard deadline: SaaS subscriptions, software licenses, SSL certificates, domain names, insurance policies, professional certifications, business registrations, tax filings, auto-renewal contracts, and payment methods (credit card expiration dates).

---

## DMAIC Procedure

### Define

1. **Create the Master Renewal Calendar** — a dedicated Google Calendar "Renewals & Expirations," shared with {{TOKEN}}, always visible. Every tracked item gets: an expiration-date event (name, amount, action); a 30-day warning ("⚠️ RENEW: [Item] in 30 days"); a 7-day warning ("🚨 RENEW: [Item] — action required this week," red); and a 1-day-before event for multi-step manual renewals.
2. **Build the Renewal Ledger** — a spreadsheet or Notion table with these fields:

   | Field | Example |
   |---|---|
   | Item | Google Workspace — Business Standard |
   | Provider | Google |
   | Account | {{OWNER_EMAIL}} |
   | Frequency | Annual |
   | Amount | $216.00 |
   | Next Renewal | 2026-09-15 |
   | Payment Method | {{PAYMENT_CARD_REF}} |
   | Auto-Renew? | Yes |
   | Cancellation Window | 30 days before |
   | Last Used (90-day check) | 2026-05-20 |
   | Notes | Impersonation via SA; do not cancel |
3. **Populate initial entries** from the Account Inventory (PA-14-03). Cross-reference bank/credit-card statements for recurring charges not yet inventoried.
4. **Set up Gmail filters** — filter subject lines containing "renewal," "subscription renews," "expiring," "billing," "payment receipt." Auto-label "Renewal-Notices" and skip the inbox (processed during the weekly scan).

### Measure

5. **Count total tracked items** in the Renewal Ledger — this is your baseline.
6. **For each item, verify all four calendar events exist.** Count items with complete warning events vs. items with gaps. Record the delta.
7. **Scan the next 90 days.** Tally: (a) auto-renew with valid payment, (b) manual action required, (c) payment method expiring before renewal date.
8. **Check last quarter's auto-renew usage audit** — completed? How many items were flagged "not used in 90 days"?
9. **Count credit cards expiring within 60 days** via PA-14-03. Verify a replacement is tracked for each.

### Analyze

10. **Identify failure patterns:** Are warning events missing for a specific category (domains, SaaS, insurance)? Are manual-renewal items gappier than auto-renew? Is the quarterly audit overdue? Are credit-card cascades originating from one card?
11. **Root-cause each gap.** Common patterns: domains get forgotten after initial annual setup; auto-renew items are assumed "handled"; quarterly audit lacks a calendar trigger; payment-method dates aren't synced from PA-14-03. Map each gap to an Improve step below.
12. **Document the top 3 root causes** in the Renewal Health Log (pinned in the ledger or a Notion page under Department 14).

### Improve

13. **Fix missing domain-renewal warnings:** Batch-create all four calendar events for every domain during the annual ledger refresh (Jan 1). Set a recurring task: "Populate domain renewal events for the year."
14. **Fix auto-renew neglect:** During the quarterly deep-dive, update the `Last Used` field for every auto-renew item. Items unused >90 days → flag to {{TOKEN}} for keep/cancel.
15. **Fix quarterly audit stall:** Add a recurring quarterly calendar event "📋 Renewal Audit — Auto-Renew Deep Dive" (Mar 1, Jun 1, Sep 1, Dec 1) with the ledger link in the description.
16. **Fix payment-method sync gap:** During the Monday scan, cross-reference the ledger's `Payment Method` field against PA-14-03 expiration dates. Flag any card expiring within 60 days that isn't already tracked.
17. **Fix price-increase blindness:** Add a `Prior Amount` field to the ledger. During the quarterly audit, compare `Amount` to `Prior Amount`. Increases >10% → flag to {{TOKEN}} with "Keep, Negotiate, or Cancel?" cc Specialist 11's PA-11-04 (Renewal Negotiation).
18. **After each Improve action, re-Measure** — did the gap close? If yes, lock in the fix (move to Control). If no, try the next candidate or escalate.

### Control

19. **Weekly Monday scan (sacred):** Pull the Renewal Calendar and ledger. Scan next 45 days. Auto-renew → confirm payment valid. Manual → start now. Cancellation window → surface to {{TOKEN}}. Payment method expiring → flag and update.
20. **Weekly CTQ self-audit:** Run checklist. Green = all 6 pass; yellow = 1 fails; red = 2+ fail.
21. **Red-status trigger:** If red, run Improve loop (steps 13–18) same week. Escalate if red persists two weeks.
22. **Credit Card Expiration Cascade:** 60 days out → verify replacement. 30 days out → update card on all billed services. After → spot-check 2–3.
23. **Monthly health report** to {{TOKEN}} via Specialist 09: "Renewal health: [color]. [X] items. [Y] gaps. [Z] due in 30d. Audit: [done/due]. Cards <60d: [list]."
24. **Quarterly deep-dive (Mar/Jun/Sep/Dec 1):** For each auto-renew item: "Used in last 90 days?" Update `Last Used`. Flag unused. Compare `Amount` vs `Prior Amount`; flag >10% increases.
25. **Annual ledger refresh (Jan 1):** Audit all — remove cancelled, add new, verify events. Set `Prior Amount` = `Amount`. Reset health log.

---

## Categories Tracked

SaaS & Software · Domains & Hosting · Insurance (health, auto, home, business, life) · Financial (credit cards, bank fees) · Legal & Compliance (registrations, filings, trademarks) · Professional Certifications · Memberships (gym, associations, retail)

---

## Tools

| Tool | Purpose |
|---|---|
| Google Calendar | Renewal dates + warning events |
| Notion / Google Sheets | Renewal ledger |
| Account Inventory (PA-14-03) | Source data for tracked items + payment methods |
| Gmail filters | "Your subscription renews" → labeled, auto-filed |

---

## CTQ Checks (Critical-to-Quality)

- [ ] Zero lapsed renewals in the last 90 days
- [ ] Weekly Monday scan completed (verified by health-log timestamp)
- [ ] Every item in the ledger has both a 30-day and 7-day warning calendar event
- [ ] Quarterly auto-renew usage audit completed (last date within 90 days)
- [ ] No credit card on file expires within 60 days without a replacement tracked
- [ ] Domain registrations have 90-day warning events (transfers can take longer)

---

## Metrics

| Metric | Target | Frequency |
|--------|--------|-----------|
| Lapsed renewals | 0 | Continuous (alert on any) |
| Warning-event coverage | 100% of ledger items | Weekly (Monday scan) |
| Quarterly audit currency | Within 90 days | Quarterly (Mar/Jun/Sep/Dec 1) |

---

## Escalation

- Renewal within 7 days, no action → flag {{TOKEN}} with action link; cc Specialist 09
- Payment method expiring before renewal → update all services; escalate to PA-14-03 (Account & Credential Hygiene) for ledger review
- Price increase >10% on auto-renew → flag {{TOKEN}} via Specialist 09; cc Specialist 11's PA-11-04 (Renewal Negotiation)
- Domain within 90 days of expiration → priority escalate; cc PA-14-03 for registrar credentials
- Lapsed renewal discovered → remediate within 1 hour; root-cause writeup within 24 hours; present to {{TOKEN}} with fix plan via Specialist 09
- CTQ red (2+ failures) two weeks in a row → escalate to {{TOKEN}} with root-cause summary and fix plan

## Definition of Done

Zero lapsed renewals in the last 90 days — every tracked item has advance warning events set, the Monday scan is complete and logged, and {{TOKEN}} has at least 30 days of lead time on every commitment.

## Tone & Persona Note

Renewal tracking is the quietest superpower in admin work. Nobody applauds the calendar reminder — until the domain doesn't expire and the insurance doesn't lapse. For Black women professionals juggling renewals across personal life, business, and family, a clean calendar is stewardship. A quiet Monday scan prevents a screaming Thursday emergency. Protect it.

*Generated by Life-Admin Archivist | Department 14 | {{TOKEN}}*
